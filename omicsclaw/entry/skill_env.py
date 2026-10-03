"""Wire the skill environment check, and ``install_skill_deps``, into a deployment.

:func:`build_skill_env` reads the dependency registry once and builds the
callback ``use_skill`` awaits to append its environment note, probing where
``bash`` runs, and — with ``skill_env=install`` and ``bash`` on this machine —
the ``install_skill_deps`` tool. :func:`log_skill_env` writes the start-up line and warns when
``bash``'s ``python`` and this process's interpreter are not the same program.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omicsclaw.permission import PermissionMode
from omicsclaw.skillenv import (
    DependencyFormatError,
    LocalProbeRunner,
    ProbeError,
    ProbeRunner,
    RegistryFormatError,
    SandboxContext,
    SandboxProbeRunner,
    parse_dependencies,
    probe_plan,
    read_registry,
    render_annotation,
    run_probe,
)
from omicsclaw.skillenv.overlay import InstallLimits, OverlayBuilder, default_root, find_overlays
from omicsclaw.skillenv.tool import install_skill_deps_tool
from omicsclaw.skills import Skill, SkillIndex
from omicsclaw.skills.use_skill import Annotator
from omicsclaw.tools.base import Tool
from omicsclaw.tools.builtin.bash import without_control_credentials

from .config import AppConfig, AppConfigError, SkillEnvMode, SkillsIndex
from .project import STEP_RUNNER
from .sandbox import SandboxBinding

__all__ = ["SkillEnvBinding", "build_skill_env", "log_skill_env"]

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SkillEnvBinding:
    """The environment check one deployment runs."""

    mode: SkillEnvMode
    runner: ProbeRunner
    location: str
    """``"local"`` or ``"sandbox"``."""
    workspace: str
    registry: dict[str, dict[str, Any]]
    """The dependency registry; empty when it could not be read."""
    registry_error: str = ""
    sandbox: SandboxContext | None = None
    annotate: Annotator | None = None
    """What ``use_skill`` awaits; ``None`` in read-only mode."""
    tool: Tool | None = None
    """``install_skill_deps``, when this deployment mounts it."""
    overlay_root: Path | None = None
    """Where overlays are kept."""
    environment: Callable[[], Mapping[str, str]] = without_control_credentials
    """Returns the environment an installation starts from: this process's,
    without the framework's control-plane credential, as ``bash`` gets it."""


def build_skill_env(
    config: AppConfig,
    skills: SkillIndex,
    binding: SandboxBinding,
) -> SkillEnvBinding | None:
    """The environment check for *config*, or ``None`` when it is off.

    ``None`` when ``skill_env`` is ``off`` or ``skills_index`` is ``off``.
    The registry is ``<skills root>/_sdk/deps.py``; when it cannot be read a
    warning is logged and every name is resolved by the fallback rule, the
    note saying why. The probe runs in the sandbox while one is running and
    on this machine otherwise. In read-only mode no callback is built.

    With ``skill_env=install`` the ``install_skill_deps`` tool is built
    whenever ``bash`` runs on this machine (no sandbox, or a requested one
    that did not start), never while a sandbox runs.

    :raises AppConfigError: ``skill_env=install`` and the registry cannot be read.
    """
    if config.skill_env is SkillEnvMode.OFF or config.skills_index is SkillsIndex.OFF:
        return None
    registry_error = ""
    try:
        registry = read_registry(skills.root / "_sdk" / "deps.py")
    except RegistryFormatError as exc:
        if config.skill_env is SkillEnvMode.INSTALL:
            raise AppConfigError(f"skill_env=install needs the dependency registry: {exc}") from exc
        registry, registry_error = {}, str(exc)
        _log.warning("dependency registry unreadable: %s", registry_error)
    if binding.active:
        runner: ProbeRunner = SandboxProbeRunner(binding.environment)
        location = "sandbox"
        network = binding.config.network if binding.config is not None else "none"
        sandbox = SandboxContext(
            image=binding.config.image if binding.config is not None else "",
            isolated=binding.isolates_network,
            network=network,
        )
    else:
        runner, location, sandbox = LocalProbeRunner(), "local", None
    environment = without_control_credentials
    root = config.skill_env_dir or default_root(environment())
    tool: Tool | None = None
    if config.skill_env is SkillEnvMode.INSTALL and location == "local":
        tool = install_skill_deps_tool(
            skills,
            registry=registry,
            probe_runner=runner,
            workspace=str(config.workspace),
            builder=OverlayBuilder(
                root,
                environment=environment,
                limits=InstallLimits(total_s=config.skill_env_install_timeout_s),
            ),
            pyproject=config.repo_root() / "pyproject.toml",
            step_runner=_step_runner(config),
        )
    made = SkillEnvBinding(
        mode=config.skill_env,
        runner=runner,
        location=location,
        workspace=str(config.workspace),
        registry=registry,
        registry_error=registry_error,
        sandbox=sandbox,
        tool=tool,
        overlay_root=root,
        environment=environment,
    )
    if config.permission_mode is PermissionMode.READ_ONLY:
        return made
    return dataclasses.replace(made, annotate=_annotator(made))


def _step_runner(config: AppConfig) -> str | None:
    """The step runner's path in this deployment's skill tree, if it has one."""
    runner = config.skills_root().joinpath(*STEP_RUNNER)
    return str(runner) if runner.is_file() else None


def _annotator(binding: SkillEnvBinding) -> Annotator:
    async def annotate(skill: Skill, body: str) -> str:
        try:
            names = parse_dependencies(body, source=skill.path)
        except DependencyFormatError as exc:
            return f"---\nEnvironment check unavailable: {exc}"
        plan = probe_plan(names, binding.registry)
        try:
            result = await run_probe(
                binding.runner, plan.imports, (), str(skill.directory), cwd=binding.workspace
            )
        except ProbeError as exc:
            return render_annotation(plan, None, error=str(exc), registry_error=binding.registry_error)
        overlays: tuple[str, ...] = ()
        if binding.location == "local" and binding.overlay_root is not None:
            absent = set(result.missing)
            names_missing = [r.name for r in plan.probed if r.kind == "pip" and r.module in absent]
            overlays = await find_overlays(
                binding.overlay_root, result, names_missing, binding.runner, cwd=binding.workspace
            )
        return render_annotation(
            plan,
            result,
            registry_error=binding.registry_error,
            sandbox=binding.sandbox,
            install_tool=binding.tool is not None,
            overlays=overlays,
        )

    return annotate


async def log_skill_env(binding: SkillEnvBinding | None, config: AppConfig) -> None:
    """Log ``skill_env=… location=… python=…`` and warn about differing interpreters.

    The ``python`` is the one the probe finds where ``bash`` runs. It is
    compared with this process's interpreter when ``bash`` runs on this
    machine. In read-only mode inside a sandbox nothing is run and the
    python is reported as unchecked. Never raises.
    """
    if binding is None:
        return
    python = "unchecked"
    if not (binding.location == "sandbox" and config.permission_mode is PermissionMode.READ_ONLY):
        try:
            result = await run_probe(binding.runner, (), (), "", cwd=binding.workspace)
            python = result.executable
        except (ProbeError, OSError, RuntimeError) as exc:
            python = f"unavailable ({exc})"
    _log.info("skill_env=%s location=%s python=%s", binding.mode.value, binding.location, python)
    if not python.startswith("/"):
        return
    if binding.location == "local" and not _same_program(python, sys.executable):
        _log.warning(
            "bash runs %s but this process runs %s; skills run with the former", python, sys.executable
        )


def _same_program(a: str, b: str) -> bool:
    return os.path.realpath(a) == os.path.realpath(b)
