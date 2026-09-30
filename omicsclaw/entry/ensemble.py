"""The ensemble layer, as one deployment uses it: ``run_skill`` and its runner.

:func:`open_ensemble` decides whether this deployment gets a runner. It needs
the started sandbox, because trials run where ``bash`` runs: it detects the
GPUs there, checks that the execution environment can supervise and score a
trial, and builds the resource pool. :func:`build_ensemble` is the synchronous
half that assembles a runner from a detection result.
"""

from __future__ import annotations

import logging
import os

from omicsclaw.ensemble import RUNS_DIRNAME
from omicsclaw.ensemble.execution import CommandExecutor, LocalExecutor, SandboxExecutor
from omicsclaw.ensemble.resources import (
    GpuDetection,
    ResourcePool,
    detect_gpus,
    parse_size_gb,
    pool_memory_gb,
)
from omicsclaw.ensemble.runner import SUPERVISE_RELATIVE, EnsembleRunner
from omicsclaw.ensemble.space import TuningCatalog
from omicsclaw.skills import SkillIndex

from .config import AppConfig, AppConfigError, SkillsIndex, mem_total_gib
from .sandbox import SandboxBinding
from .skill_env import describe_trial_environment

__all__ = [
    "SELF_CHECK_IMPORTS",
    "build_ensemble",
    "ensemble_executor",
    "open_ensemble",
    "self_check",
]

_log = logging.getLogger(__name__)

SELF_CHECK_IMPORTS = (
    "numpy",
    "scipy.spatial",
    "scipy.stats",
    "pandas",
    "h5py",
    "anndata",
    "sklearn.neighbors",
    "sklearn.metrics",
    "scanpy",
    "igraph",
)
"""Every module the scoring subprocess imports, checked at start-up."""

_SELF_CHECK_TIMEOUT_S = 300.0
_OUTPUT_CHARS = 2000


def ensemble_executor(config: AppConfig, binding: SandboxBinding) -> CommandExecutor:
    """Where trials run: the sandbox when it is running, else this machine."""
    if binding.environment is not None:
        return SandboxExecutor(binding.environment, python=config.ensemble_python)
    return LocalExecutor(python=config.ensemble_python)


def _catalog(config: AppConfig, skills: SkillIndex) -> TuningCatalog | None:
    if config.ensemble is False:
        _log.info("ensemble=off (disabled by configuration)")
        return None
    if config.skills_index is SkillsIndex.OFF:
        _log.info("ensemble=off: skills_index is off, so no skill can be run")
        return None
    catalog = TuningCatalog.from_skills(skills)
    for skipped in catalog.skipped:
        _log.warning("tuning file not used: %s", skipped.reason)
    if not len(catalog):
        _log.info("ensemble=off: no skill has a valid tuning.yaml")
        return None
    return catalog


def _pool_memory(config: AppConfig, binding: SandboxBinding) -> float:
    tmpfs = shm = 0.0
    base: float | None = None
    if binding.active and binding.config is not None:
        if binding.config.memory:
            base = parse_size_gb(binding.config.memory)
        tmpfs = parse_size_gb(binding.config.tmpfs_size) if binding.config.tmpfs_size else 0.0
        shm = parse_size_gb(binding.config.shm_size) if binding.config.shm_size else 0.0
    if base is None:
        total = mem_total_gib()
        if total is None:
            raise AppConfigError("cannot size the ensemble pool: /proc/meminfo is unreadable")
        base = total * 0.8
    try:
        return pool_memory_gb(
            base_gb=base,
            tmpfs_gb=tmpfs,
            shm_gb=shm,
            reserved_gb=config.ensemble_reserved_gb,
            configured_gb=config.ensemble_memory_gb,
        )
    except ValueError as exc:
        raise AppConfigError(str(exc)) from exc


def _pool_cpus(config: AppConfig, binding: SandboxBinding) -> int:
    cpus = config.ensemble_cpus or os.cpu_count() or 1
    if binding.active and binding.config is not None and binding.config.cpus:
        try:
            cpus = min(cpus, max(1, int(float(binding.config.cpus))))
        except ValueError:
            pass
    return cpus


def build_ensemble(
    config: AppConfig,
    skills: SkillIndex,
    binding: SandboxBinding,
    *,
    gpus: GpuDetection,
    executor: CommandExecutor | None = None,
    catalog: TuningCatalog | None = None,
) -> EnsembleRunner | None:
    """A runner over the skills that have a valid ``tuning.yaml``, or ``None``.

    ``None`` when :attr:`AppConfig.ensemble` is ``False``, when the skill index
    is off, or when no skill has a valid ``tuning.yaml`` (the last two are
    logged). Performs no self-check; :func:`open_ensemble` does. *catalog*
    reuses a catalogue already loaded from *skills*. Every trial records its
    interpreter and declared package versions (see
    :func:`~omicsclaw.entry.skill_env.describe_trial_environment`).

    :raises AppConfigError: The pool would have no memory.
    """
    if catalog is None:
        catalog = _catalog(config, skills)
    if catalog is None:
        return None
    pool = ResourcePool(
        gpu_ids=gpus.ids,
        slots_per_gpu=config.ensemble_slots_per_gpu,
        memory_gb=_pool_memory(config, binding),
        cpus=_pool_cpus(config, binding),
        gpu_detail=gpus.describe(),
    )
    runner = EnsembleRunner(
        catalog=catalog,
        pool=pool,
        executor=executor or ensemble_executor(config, binding),
        runs_root=config.workspace / RUNS_DIRNAME,
        repo_root=config.repo_root(),
        max_trial_s=config.ensemble_max_trial_s,
        max_queue_s=config.ensemble_max_queue_s,
        keep_all=config.ensemble_keep_all,
        memory_cap_gb=config.ensemble_memory_gb_cap,
        image=binding.config.image if binding.active and binding.config is not None else "",
        describe_environment=describe_trial_environment(skills),
        seed=config.ensemble_seed,
    )
    _log.info(
        "ensemble=on gpus=%s memory=%.0fGB cpus=%d skills=%s",
        gpus.describe(),
        pool.memory_gb,
        pool.cpus,
        ",".join(catalog.names()),
    )
    if config.turn_timeout_s is not None and config.turn_timeout_s < runner.call_ceiling_s:
        _log.warning(
            "turn_timeout_s=%g is shorter than one run_skill call can take (%g s: queue + "
            "trial + scoring); a turn that times out cancels its running trials",
            config.turn_timeout_s,
            runner.call_ceiling_s,
        )
    return runner


async def self_check(
    config: AppConfig,
    executor: CommandExecutor,
    catalog: TuningCatalog,
) -> str:
    """Check the execution environment can run and score trials; ``""`` when it can.

    The interpreter must be Python 3.11 or newer and import every module in
    :data:`SELF_CHECK_IMPORTS` and the scoring module; the supervisor script
    and every catalogued skill script must exist there.

    :returns: A description of what failed, with the command output.
    """
    repo = config.repo_root()
    code = (
        "import sys; assert sys.version_info >= (3, 11), sys.version\n"
        f"import {', '.join(SELF_CHECK_IMPORTS)}\n"
        "import omicsclaw.ensemble.metrics.score\n"
    )
    env = {"PYTHONPATH": str(repo), "PYTHONDONTWRITEBYTECODE": "1"}
    probe = await executor.capture(
        [executor.python, "-c", code], cwd=config.workspace, timeout=_SELF_CHECK_TIMEOUT_S, env=env
    )
    if probe.exit_code != 0 or probe.timed_out:
        return (
            f"{executor.python} cannot score trials (exit {probe.exit_code}): "
            f"{probe.output.strip()[-_OUTPUT_CHARS:]}"
        )
    required = [repo / SUPERVISE_RELATIVE]
    required += [spec.script_path for spec in catalog.specs()]
    for path in required:
        found = await executor.capture(["test", "-f", str(path)], cwd=config.workspace, timeout=60.0)
        if found.exit_code != 0:
            return f"{path} is not visible to the execution environment ({executor.location})"
    return ""


async def open_ensemble(
    config: AppConfig,
    skills: SkillIndex,
    binding: SandboxBinding,
) -> EnsembleRunner | None:
    """Detect GPUs, self-check the execution environment and build the runner.

    A failed self-check, or a host whose memory leaves the trial pool
    nothing after :attr:`AppConfig.ensemble_reserved_gb`, refuses start-up
    when :attr:`AppConfig.ensemble` is ``True``. Otherwise either one logs a
    warning and returns ``None``, so the rest of the deployment starts
    without ``run_skill``.

    :raises AppConfigError: The self-check failed or the pool would have no
        memory, and the ensemble was explicitly enabled.
    """
    catalog = _catalog(config, skills)
    if catalog is None:
        return None
    executor = ensemble_executor(config, binding)
    gpus = await detect_gpus(
        config.ensemble_gpus,
        environment=binding.environment,
        cwd=str(config.workspace),
        sandbox_gpus=config.sandbox_gpus,
    )
    if gpus.warning:
        _log.warning("ensemble: %s", gpus.warning)
    failure = await self_check(config, executor, catalog)
    if failure:
        if config.ensemble is True:
            raise AppConfigError(f"ensemble is enabled but its self-check failed: {failure}")
        _log.warning(
            "run_skill is not mounted: the ensemble self-check failed: %s "
            "(set --ensemble false to silence this warning)",
            failure,
        )
        return None
    try:
        return build_ensemble(config, skills, binding, gpus=gpus, executor=executor, catalog=catalog)
    except AppConfigError as exc:
        if config.ensemble is True:
            raise
        _log.warning(
            "run_skill is not mounted: %s (lower OMICSCLAW_ENSEMBLE_RESERVED_GB to leave the "
            "pool memory, or set --ensemble false to silence this warning)",
            exc,
        )
        return None
