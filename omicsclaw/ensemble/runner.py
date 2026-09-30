"""Run trials: one skill method with one parameter set, supervised, collected and scored.

:class:`EnsembleRunner` is the Python interface; the ``run_skill`` tool is a
thin wrapper around it. A trial goes through four stages, and a failure in any
of them is a result, not an exception:

``admission``
    The pool decides the device. A method that requires a GPU when there is
    none, or asks for more memory or CPUs than the pool has in total, fails
    here without starting anything. So does a trial that waits in the queue
    longer than ``max_queue_s``.
``run``
    The skill script runs under ``_supervise.py`` in the trial directory, with
    its own temporary directories and a whitelisted environment. It ends
    ``ok``, ``failed``, ``timeout`` or ``memory_exceeded``.
``collect``
    ``result.json`` and the label table must exist; the labels are rewritten as
    ``labels.csv.gz`` (``obs_id,label``).
``score``
    The analysis panel runs in a second supervised process under the same lease
    and writes ``metrics.json``. A trial that cannot be scored has failed.

Cancellation kills the trial's processes, records the trial as ``cancelled``
and propagates.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

from omicsclaw.ensemble.execution import CommandExecutor
from omicsclaw.ensemble.resources import Admission, Lease, QueueTimeout, ResourcePool, ResourceRequest
from omicsclaw.ensemble.space import SpecError, TuningCatalog, TuningSpec, render_cli_args, validate_params
from omicsclaw.ensemble.store import (
    RUN_ID_PATTERN,
    RunStore,
    log_tail,
    new_run_id,
    read_json,
    truncate_log,
)
from omicsclaw.tools.context import report_progress

__all__ = [
    "EnsembleRunner",
    "InsufficientSurvivors",
    "Limits",
    "DESCRIBE_TIMEOUT_S",
    "ENVIRONMENT_TIMEOUT_S",
    "EnvironmentDescriber",
    "HASH_TIMEOUT_S",
    "SCORE_TIMEOUT_S",
    "TrialResult",
    "TrialSpec",
]

SCORE_TIMEOUT_S = 120.0
HASH_TIMEOUT_S = 300.0
"""Longest a caller waits for the input's sha256 before a trial is prepared."""
DESCRIBE_TIMEOUT_S = 300.0
"""Time limit on reading the input's obs columns when a run is first bound."""
ENVIRONMENT_TIMEOUT_S = 60.0
"""Time limit on describing a trial's environment; past it the trial records an error and runs."""
SUPERVISE_RELATIVE = Path("omicsclaw") / "ensemble" / "_supervise.py"
SEED_DIR_RELATIVE = Path("omicsclaw") / "ensemble" / "_seed"
"""Directory whose ``sitecustomize.py`` seeds every trial process."""
DEFAULT_TRIAL_SEED = 0
_EXECUTOR_MARGIN_S = 60.0
_ERROR_TAIL_BYTES = 2048


@dataclass(frozen=True, slots=True)
class Limits:
    """A trial's run-time limit (scoring excluded) and memory limit."""

    timeout_s: float
    memory_gb: float


@dataclass(frozen=True, slots=True)
class TrialSpec:
    """One validated trial, ready to run."""

    skill: str
    method: str
    input: Path
    params: Mapping[str, object]
    run_id: str
    limits: Limits
    resources: ResourceRequest
    input_sha256: str = ""


@dataclass
class TrialResult:
    """How one trial ended, and everything recorded about it."""

    status: str
    stage: str
    run_id: str
    method: str
    trial: str
    output_dir: str
    params: dict[str, Any]
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    queued_s: float = 0.0
    wall_s: float = 0.0
    peak_mem_gb: float | None = None
    mem_metric: str | None = None
    lease_gpu: str | None = None
    device: str = "unknown"
    device_source: str = "unknown"
    gpu_mem_peak_mb: float | None = None
    degraded: str = ""
    metrics: dict[str, Any] | None = None
    score: float | None = None
    h5ad: str | None = None
    error: str = ""
    log: str = ""
    started_at: str = ""
    ended_at: str = ""
    id_column_used: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InsufficientSurvivors(RuntimeError):
    """Fewer trials than required ended ``ok``; :attr:`results` holds all of them."""

    def __init__(self, required: int, results: Sequence[TrialResult]) -> None:
        ok = sum(1 for result in results if result.status == "ok")
        super().__init__(f"{ok} of {len(results)} trials succeeded; {required} were required")
        self.required = required
        self.results = list(results)


class _Failed(Exception):
    def __init__(self, status: str, stage: str, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.stage = stage
        self.error = error


EnvironmentDescriber = Callable[[CommandExecutor, str], Awaitable[Mapping[str, Any]]]
"""Given the executor and a skill name, what to record as the trial's ``provenance.environment``."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class EnsembleRunner:
    """Prepare and run trials of catalogued skills on a shared resource pool.

    :param catalog: The runnable skills.
    :param pool: The resource pool every trial draws from.
    :param executor: Where commands run.
    :param runs_root: ``<workspace>/ensemble_runs``.
    :param repo_root: The directory holding ``omicsclaw/`` and ``skills/``, put on
        ``PYTHONPATH`` for every trial.
    :param max_trial_s: Ceiling on any trial's run time.
    :param max_queue_s: Ceiling on any trial's wait for resources.
    :param score_timeout_s: Time limit of the scoring step.
    :param keep_all: Keep every trial's full output.
    :param memory_cap_gb: Lower every method's memory limit to this; 0 keeps them.
    :param image: The sandbox image, recorded in provenance.
    :param seed: Seed of every trial process (``random``, numpy, torch, with
        torch's deterministic algorithms and ``PYTHONHASHSEED=0``); ``None``
        leaves trials unseeded.
    :param determinism: ``"strict"`` makes a non-deterministic torch operation
        raise, ``"warn"`` only warn.
    :param describe_environment: Awaited once per trial, before its stages, with the
        executor and the skill name; what it returns is recorded as
        ``provenance.environment``. If it raises or takes longer than
        :data:`ENVIRONMENT_TIMEOUT_S`, ``{"error": …}`` is recorded instead and the
        trial runs on. ``None`` records nothing.
    """

    def __init__(
        self,
        *,
        catalog: TuningCatalog,
        pool: ResourcePool,
        executor: CommandExecutor,
        runs_root: Path,
        repo_root: Path,
        max_trial_s: float = 7200.0,
        max_queue_s: float = 7200.0,
        score_timeout_s: float = SCORE_TIMEOUT_S,
        keep_all: bool = False,
        memory_cap_gb: float = 0.0,
        image: str = "",
        describe_environment: EnvironmentDescriber | None = None,
        seed: int | None = DEFAULT_TRIAL_SEED,
        determinism: str = "strict",
    ) -> None:
        if determinism not in ("strict", "warn"):
            raise ValueError(f"determinism must be strict or warn, got {determinism!r}")
        self.catalog = catalog
        self.pool = pool
        self.executor = executor
        self.store = RunStore(Path(runs_root))
        self.repo_root = Path(repo_root)
        self.max_trial_s = float(max_trial_s)
        self.max_queue_s = float(max_queue_s)
        self.score_timeout_s = float(score_timeout_s)
        self.keep_all = keep_all
        self.memory_cap_gb = float(memory_cap_gb)
        self.image = image
        self.describe_environment = describe_environment
        self.seed = seed
        self.determinism = determinism
        self._hashes: dict[tuple[str, int, int], str] = {}
        self._hash_lock = threading.Lock()

    @property
    def call_ceiling_s(self) -> float:
        """Longest one trial can take end to end.

        Hashing the input, describing it when the run is first bound, the
        queue, the run, scoring and a margin.
        """
        return (
            HASH_TIMEOUT_S
            + DESCRIBE_TIMEOUT_S
            + self.max_queue_s
            + self.max_trial_s
            + self.score_timeout_s
            + _EXECUTOR_MARGIN_S
        )

    # ---- preparing ------------------------------------------------------------

    def input_sha256(self, path: Path) -> str:
        """The input's sha256, computed once per (path, size, mtime)."""
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        with self._hash_lock:
            cached = self._hashes.get(key)
            if cached is None:
                cached = file_sha256(path)
                self._hashes[key] = cached
            return cached

    def prepare(
        self,
        *,
        skill: str,
        method: str,
        input: Path,
        params: Mapping[str, object] | None = None,
        run_id: str | None = None,
        timeout_s: float | None = None,
    ) -> TrialSpec:
        """Validate one trial. Reads the input once to hash it; starts nothing.

        :raises SpecError: An unknown skill or method, bad parameters, an input
            that is not a file, a malformed ``run_id``, a ``run_id`` bound to
            another skill or input, or a ``timeout_s`` above the ceiling.
        """
        spec = self.catalog.get(skill)
        if spec is None:
            known = ", ".join(self.catalog.names()) or "none"
            raise SpecError(f"skill {skill!r} cannot be run by run_skill; runnable skills: {known}")
        method_spec = spec.method(method)
        values = validate_params(spec, method, params or {})
        path = Path(input)
        if not path.is_file():
            raise SpecError(f"input {path} is not a file")
        if run_id is None or run_id == "":
            run_id = new_run_id()
        elif not RUN_ID_PATTERN.fullmatch(run_id):
            raise SpecError(
                f"run_id {run_id!r} must match {RUN_ID_PATTERN.pattern} "
                "(lowercase letters, digits, '-' and '_', at most 64 characters)"
            )
        if timeout_s is not None:
            if timeout_s <= 0:
                raise SpecError("timeout_s must be positive")
            if timeout_s > self.max_trial_s:
                raise SpecError(
                    f"timeout_s {timeout_s:g} exceeds this deployment's ceiling of {self.max_trial_s:g} s"
                )
        sha = self.input_sha256(path)
        self.store.check_run(run_id, skill=skill, input_sha256=sha)
        resources = method_spec.resources
        memory = resources.memory_gb
        if self.memory_cap_gb > 0:
            memory = min(memory, self.memory_cap_gb)
        timeout = min(resources.timeout_s, self.max_trial_s)
        if timeout_s is not None:
            timeout = min(timeout, timeout_s)
        return TrialSpec(
            skill=skill,
            method=method,
            input=path,
            params=values,
            run_id=run_id,
            limits=Limits(timeout_s=timeout, memory_gb=memory),
            resources=ResourceRequest(resources.gpu, memory, resources.cpus),  # type: ignore[arg-type]
            input_sha256=sha,
        )

    # ---- running ----------------------------------------------------------------

    async def fan_out(
        self,
        specs: Sequence[TrialSpec],
        *,
        required_survivors: int | None = None,
    ) -> list[TrialResult]:
        """Run *specs* concurrently; results in input order.

        One trial's failure does not affect the others. Cancelling kills every
        trial still running and waits for them.

        :raises InsufficientSurvivors: Fewer than *required_survivors* ended ``ok``.
        """
        tasks = [asyncio.ensure_future(self.run(spec)) for spec in specs]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        if required_survivors is not None:
            ok = sum(1 for result in results if result.status == "ok")
            if ok < required_survivors:
                raise InsufficientSurvivors(required_survivors, results)
        return list(results)

    async def run(self, spec: TrialSpec, *, backstop_s: float | None = None) -> TrialResult:
        """Run one trial to its end. Only cancellation propagates.

        *backstop_s* bounds everything after admission (run, collection and
        scoring together); when it passes, the trial's processes are killed and
        the trial ends ``timeout``. Queueing is not counted.
        """
        tuning = self.catalog.get(spec.skill)
        if tuning is None:
            raise SpecError(f"skill {spec.skill!r} is not in the catalogue")
        sha = spec.input_sha256 or await asyncio.wait_for(
            asyncio.to_thread(self.input_sha256, spec.input), HASH_TIMEOUT_S
        )
        await self._bind(spec, tuning, sha)
        trial_dir = await self.store.allocate_trial(spec.run_id, spec.method)
        result = TrialResult(
            status="failed",
            stage="admission",
            run_id=spec.run_id,
            method=spec.method,
            trial=trial_dir.name,
            output_dir=str(trial_dir),
            params=dict(spec.params),
            log=str(trial_dir / "run.log"),
            started_at=_now(),
            provenance={
                "script_sha256": await asyncio.to_thread(file_sha256, tuning.script_path),
                "tuning_sha256": tuning.sha256,
                "input_sha256": sha,
                "python": self.executor.python,
                "location": self.executor.location,
                "image": self.image,
                "seed": self.seed,
                "determinism": self.determinism if self.seed is not None else None,
                "seed_sitecustomize_sha256": self.seed_sitecustomize_sha256(),
            },
        )
        try:
            if self.describe_environment is not None:
                result.provenance["environment"] = await self._environment(
                    self.describe_environment, spec.skill
                )
            await self._run_stages(spec, tuning, trial_dir, result, backstop_s)
        except asyncio.CancelledError:
            result.status = "cancelled"
            result.error = result.error or "the trial was cancelled"
            await asyncio.shield(self._finish(spec, trial_dir, result, tuning))
            raise
        await self._finish(spec, trial_dir, result, tuning)
        return result

    async def _environment(self, describe: EnvironmentDescriber, skill: str) -> dict[str, Any]:
        try:
            described = await asyncio.wait_for(describe(self.executor, skill), ENVIRONMENT_TIMEOUT_S)
        except TimeoutError:
            return {"error": f"describing the environment timed out after {ENVIRONMENT_TIMEOUT_S:g} s"}
        except Exception as exc:  # noqa: BLE001 - a failed description must not lose the trial
            return {"error": f"{type(exc).__name__}: {exc}"}
        return dict(described)

    async def _bind(self, spec: TrialSpec, tuning: TuningSpec, sha: str) -> None:
        if self.store.existing_run(spec.run_id) is not None:
            self.store.check_run(spec.run_id, skill=spec.skill, input_sha256=sha)
            return
        description = await self._describe_input(spec.input)
        await self.store.bind_run(
            spec.run_id,
            {
                "run_id": spec.run_id,
                "skill": spec.skill,
                "analysis": tuning.analysis,
                "input": str(spec.input),
                "input_sha256": sha,
                "input_n_obs": description.get("n_obs"),
                "input_obs_columns": description.get("obs_columns"),
                "tuning_sha256": tuning.sha256,
                "script_sha256": await asyncio.to_thread(file_sha256, tuning.script_path),
                "panel_version": _panel_version(tuning.analysis),
                "limits": {"max_trial_s": self.max_trial_s, "max_queue_s": self.max_queue_s,
                           "score_timeout_s": self.score_timeout_s},
                "location": self.executor.location,
                "python": self.executor.python,
                "image": self.image,
                "created_at": _now(),
            },
        )

    async def _describe_input(self, path: Path) -> dict[str, Any]:
        result = await self.executor.capture(
            [self.executor.python, "-m", "omicsclaw.ensemble.metrics.score", "--describe-input", str(path)],
            cwd=path.parent,
            timeout=DESCRIBE_TIMEOUT_S,
            env={"PYTHONPATH": str(self.repo_root), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        for line in result.output.splitlines():
            if line.startswith("DESCRIBE="):
                try:
                    return json.loads(line[len("DESCRIBE="):])
                except ValueError:
                    break
        return {"error": result.output[-_ERROR_TAIL_BYTES:]}

    async def _run_stages(
        self,
        spec: TrialSpec,
        tuning: TuningSpec,
        trial_dir: Path,
        result: TrialResult,
        backstop_s: float | None = None,
    ) -> None:
        admission = self.pool.admit(spec.resources)
        result.degraded = admission.degraded
        if not admission.admitted:
            result.error = admission.refused
            return
        began_queue = time.monotonic()
        if self.pool.snapshot()["queued"] or not self._fits_now(admission):
            await report_progress(f"{spec.method} {trial_dir.name}: queued for resources", tool_name="run_skill")
        try:
            async with self.pool.acquire(admission, max_wait_s=self.max_queue_s) as lease:
                result.queued_s = round(time.monotonic() - began_queue, 3)
                result.lease_gpu = lease.gpu
                await report_progress(
                    f"{spec.method} {trial_dir.name}: running"
                    + (f" on GPU {lease.gpu}" if lease.gpu is not None else " on CPU"),
                    tool_name="run_skill",
                )
                budget = asyncio.timeout(backstop_s)
                try:
                    async with budget:
                        await self._run_leased(spec, tuning, trial_dir, lease, result)
                except TimeoutError:
                    if not budget.expired():
                        raise
                    result.status = "timeout"
                    result.error = (
                        f"the trial did not finish within its {backstop_s:g} s budget "
                        "(run, collection and scoring)\n" + log_tail(trial_dir / "run.log", _ERROR_TAIL_BYTES)
                    )
        except QueueTimeout as exc:
            result.queued_s = round(time.monotonic() - began_queue, 3)
            result.status, result.stage, result.error = "failed", "admission", str(exc)

    def _fits_now(self, admission: Admission) -> bool:
        snapshot = self.pool.snapshot()
        needs_gpu = 1 if admission.use_gpu else 0
        return (
            self.pool.gpu_slots_free >= needs_gpu
            and snapshot["memory_free_gb"] >= admission.request.memory_gb
            and snapshot["cpus_free"] >= admission.request.cpus
        )

    def trial_environment(self, trial_dir: Path, lease: Lease) -> dict[str, str]:
        """The variables every command of a trial gets.

        With a seed, the seeding ``sitecustomize`` directory comes first on
        ``PYTHONPATH`` and ``OMICSCLAW_TRIAL_SEED``, ``PYTHONHASHSEED=0`` and
        ``CUBLAS_WORKSPACE_CONFIG=:4096:8`` are set.
        """
        tmp = trial_dir / "tmp"
        threads = str(lease.cpus)
        env = {
            "PYTHONPATH": str(self.repo_root),
            "PYTHONDONTWRITEBYTECODE": "1",
            "CUDA_VISIBLE_DEVICES": lease.gpu if lease.gpu is not None else "",
            "OMP_NUM_THREADS": threads,
            "MKL_NUM_THREADS": threads,
            "OPENBLAS_NUM_THREADS": threads,
            "NUMBA_NUM_THREADS": threads,
            "TMPDIR": str(tmp),
            "TMP": str(tmp),
            "TEMP": str(tmp),
            "MPLCONFIGDIR": str(tmp / "mpl"),
            "NUMBA_CACHE_DIR": str(tmp / "numba"),
        }
        env.update(self.seed_environment())
        return env

    def seed_sitecustomize_sha256(self) -> str | None:
        """sha256 of the seeding ``sitecustomize.py``, or ``None`` without a seed."""
        if self.seed is None:
            return None
        return file_sha256(self.repo_root / SEED_DIR_RELATIVE / "sitecustomize.py")

    def seed_environment(self) -> dict[str, str]:
        """The seeding variables of a trial, or ``{}`` without a seed."""
        if self.seed is None:
            return {}
        return {
            "PYTHONPATH": f"{self.repo_root / SEED_DIR_RELATIVE}{os.pathsep}{self.repo_root}",
            "OMICSCLAW_TRIAL_SEED": str(int(self.seed)),
            "OMICSCLAW_TRIAL_DETERMINISM": self.determinism,
            "PYTHONHASHSEED": "0",
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        }

    def _supervised(self, trial_dir: Path, status: Path, timeout: float, memory_gb: float, command: list[str]) -> list[str]:
        return [
            self.executor.python,
            str(self.repo_root / SUPERVISE_RELATIVE),
            "--timeout", repr(float(timeout)),
            "--max-mem-mb", repr(float(memory_gb) * 1024),
            "--status", str(status),
            "--",
            *command,
        ]

    async def _run_leased(
        self,
        spec: TrialSpec,
        tuning: TuningSpec,
        trial_dir: Path,
        lease: Lease,
        result: TrialResult,
    ) -> None:
        env = self.trial_environment(trial_dir, lease)
        for sub in ("mpl", "numba"):
            (trial_dir / "tmp" / sub).mkdir(parents=True, exist_ok=True)
        log = trial_dir / "run.log"
        output = trial_dir / "output"
        command = [
            self.executor.python,
            str(tuning.script_path),
            "--input", str(spec.input),
            "--output", str(output),
            *render_cli_args(tuning, spec.method, spec.params),
        ]
        result.command = command
        status_file = trial_dir / "supervisor.json"
        result.stage = "run"
        began = time.monotonic()
        executed = await self.executor.run(
            self._supervised(trial_dir, status_file, spec.limits.timeout_s, spec.limits.memory_gb, command),
            cwd=trial_dir,
            env=env,
            log=log,
            timeout=spec.limits.timeout_s + _EXECUTOR_MARGIN_S,
        )
        result.wall_s = round(time.monotonic() - began, 3)
        report = read_json(status_file)
        if report is None:
            result.exit_code = executed.exit_code
            result.status = "timeout" if executed.timed_out else "failed"
            result.error = "the supervisor did not report how the run ended\n" + log_tail(log, _ERROR_TAIL_BYTES)
            return
        result.exit_code = report.get("exit_code")
        result.wall_s = float(report.get("wall_s") or result.wall_s)
        result.peak_mem_gb = round(float(report.get("peak_mem_mb") or 0) / 1024, 3)
        result.mem_metric = report.get("mem_metric")
        if report.get("gpu_mem_peak_mb"):
            result.gpu_mem_peak_mb = float(report["gpu_mem_peak_mb"])
        self._device(result, report, output / "result.json")
        status = report.get("status")
        if status != "ok":
            result.status = status if status in ("timeout", "memory_exceeded", "cancelled") else "failed"
            limit = {
                "timeout": f"exceeded the {spec.limits.timeout_s:g} s time limit",
                "memory_exceeded": f"exceeded the {spec.limits.memory_gb:g} GB memory limit",
            }.get(status, f"exited with status {result.exit_code}")
            result.error = f"the skill {limit}\n" + log_tail(log, _ERROR_TAIL_BYTES)
            return

        result.stage = "collect"
        try:
            result.id_column_used = await asyncio.to_thread(self._collect, tuning, output, trial_dir)
        except _Failed as exc:
            result.status, result.error = exc.status, exc.error
            return

        result.stage = "score"
        score_status = trial_dir / "tmp" / "score_supervisor.json"
        with open(log, "ab") as sink:
            sink.write(b"\n==== scoring ====\n")
        cache = self.store.cache_dir(result.provenance["input_sha256"])
        cache.mkdir(parents=True, exist_ok=True)
        score_command = [
            self.executor.python, "-m", "omicsclaw.ensemble.metrics.score",
            "--trial", str(trial_dir),
            "--input", str(spec.input),
            "--analysis", tuning.analysis,
            "--cache", str(cache),
            "--reference-json", json.dumps(dict(tuning.reference), sort_keys=True),
        ]
        await self.executor.run(
            self._supervised(trial_dir, score_status, self.score_timeout_s, spec.limits.memory_gb, score_command),
            cwd=trial_dir,
            env=env,
            log=log,
            timeout=self.score_timeout_s + _EXECUTOR_MARGIN_S,
        )
        scored = read_json(score_status)
        metrics = read_json(trial_dir / "metrics.json")
        if scored is None or scored.get("status") != "ok" or metrics is None:
            how = (scored or {}).get("status", "no report")
            result.status = "failed"
            result.error = f"scoring did not complete ({how})\n" + log_tail(log, _ERROR_TAIL_BYTES)
            return
        result.metrics = metrics
        result.score = metrics.get("score")
        result.status = "ok"

    def _device(self, result: TrialResult, report: Mapping[str, Any], result_json: Path) -> None:
        """The device the trial really used.

        Observed from ``nvidia-smi`` when its processes can be attributed.
        Otherwise a trial without a GPU lease ran with ``CUDA_VISIBLE_DEVICES=""``
        and is ``cpu`` (source ``inferred_no_lease``); a leased trial takes the
        device the skill reported, with any CUDA device written as
        ``cuda:<lease>``, or stays ``unknown``.
        """
        if report.get("gpu_probe") == "ok":
            result.device_source = "observed"
            if report.get("gpu_used"):
                result.device = f"cuda:{result.lease_gpu}" if result.lease_gpu is not None else "cuda"
            else:
                result.device = "cpu"
            return
        if result.lease_gpu is None:
            result.device, result.device_source = "cpu", "inferred_no_lease"
            return
        envelope = read_json(result_json) or {}
        summary = envelope.get("summary") if isinstance(envelope.get("summary"), dict) else {}
        device = str(summary.get("device") or "").strip() if summary else ""
        if not device:
            return
        lowered = device.lower()
        if lowered.startswith("cuda") or lowered == "gpu":
            device = f"cuda:{result.lease_gpu}"
        result.device, result.device_source = device, "skill"

    def _collect(self, tuning: TuningSpec, output: Path, trial_dir: Path) -> str:
        if not (output / "result.json").is_file():
            raise _Failed("failed", "collect", "the skill wrote no result.json")
        table = output / (tuning.output.labels_table or "")
        if not tuning.output.labels_table or not table.is_file():
            raise _Failed("failed", "collect", f"the skill wrote no {tuning.output.labels_table}")
        label_column = tuning.output.label_column or ""
        with open(table, newline="", encoding="utf-8") as source:
            reader = csv.reader(source)
            try:
                header = next(reader)
            except StopIteration:
                raise _Failed("failed", "collect", f"{table.name} is empty") from None
            if label_column not in header:
                raise _Failed("failed", "collect", f"{table.name} has no column {label_column!r}")
            wanted = tuning.output.id_column
            if wanted and wanted in header:
                id_column = wanted
            elif header and header[0] != label_column:
                id_column = header[0]
            else:
                raise _Failed("failed", "collect", f"{table.name} has no observation id column")
            id_index = header.index(id_column)
            label_index = header.index(label_column)
            with gzip.open(trial_dir / "labels.csv.gz", "wt", newline="", encoding="utf-8") as sink:
                writer = csv.writer(sink)
                writer.writerow(["obs_id", "label"])
                for row in reader:
                    if len(row) <= max(id_index, label_index):
                        continue
                    writer.writerow([row[id_index], row[label_index]])
        return id_column

    async def _finish(
        self,
        spec: TrialSpec,
        trial_dir: Path,
        result: TrialResult,
        tuning: TuningSpec,
    ) -> None:
        kept = await self.store.retain(
            spec.run_id,
            spec.method,
            trial_dir,
            score=result.score if result.status == "ok" else None,
            h5ad=tuning.output.h5ad,
            keep_all=self.keep_all,
        )
        result.h5ad = str(kept) if kept is not None else None
        truncate_log(trial_dir / "run.log")
        result.ended_at = _now()
        await self.store.record_trial(spec.run_id, trial_dir, result.to_dict())


def _panel_version(analysis: str) -> str | None:
    from omicsclaw.ensemble.metrics import get_panel

    panel = get_panel(analysis)
    return panel.version if panel else None
