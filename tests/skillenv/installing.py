"""Shared set-up for the ``install_skill_deps`` tests: a skills tree, a base ``python`` on ``PATH``, recorders.

Every test builds its own skills tree, registry, wheel directory, pip
configuration and overlay root under ``tmp_path``. The agent environment the
tool sees is a small explicit mapping whose ``HOME`` is a temporary directory
and whose ``PIP_CONFIG_FILE`` names the test's pip configuration, so the
developer's own ``~/.pip/pip.conf`` never takes part.

The base interpreter is this test process's, or ``OMICSCLAW_TEST_BASE_PYTHON``
when set (plan 0061 §6: the real-overlay tests are also run with the
``OmicsClaw`` environment as the base).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omicsclaw.skillenv.overlay import CommandOutput, InstallLimits, LocalCommandRunner, OverlayBuilder
from omicsclaw.skillenv.probe import LocalProbeRunner
from omicsclaw.skillenv.registry import read_registry
from omicsclaw.skillenv.tool import install_skill_deps_tool
from omicsclaw.skills import SkillIndex, load_skills
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, use_tool_context

BASE_PYTHON = os.environ.get("OMICSCLAW_TEST_BASE_PYTHON") or sys.executable
SKILL = "oc-skill"

DEFAULT_REGISTRY: dict[str, dict[str, Any]] = {
    "pybanksy": {
        "module": "banksy",
        "kind": "git",
        "alt_env": "omicsclaw_banksy",
        "install": "pip install git+https://github.com/prabhakarlab/Banksy_py.git",
        "description": "BANKSY",
    },
    "xcms": {"module": "xcms", "kind": "r", "install": "Rscript -e 'install(\"xcms\")'", "description": "XCMS"},
    "oc-multi": {
        "module": "oc_multi",
        "kind": "pip",
        "install": "Rscript -e 'this string is never parsed'",
        "description": "a registry entry that installs two distributions",
        "also": ["oc-extra"],
    },
}

DEFAULT_DECLARED = (
    "json", "oc-leaf", "oc-needs-old", "oc-sdist-only", "oc-shadow", "oc-nsdir", "oc-near", "oc-multi",
    "oc-envspy", "oc-pthspy", "oc-hang", "oc-auth", "pybanksy", "xcms",
)


def make_skills(
    root: Path,
    *,
    declared: Sequence[str] = DEFAULT_DECLARED,
    registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> SkillIndex:
    """A skills tree with one skill, :data:`SKILL`, and a registry file ``_sdk/deps.py``."""
    skill_dir = root / "demo" / SKILL
    skill_dir.mkdir(parents=True, exist_ok=True)
    line = ", ".join(f"`{name}`" for name in declared)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {SKILL}\ndescription: A fixture skill for install_skill_deps tests.\n---\n\n"
        f"# {SKILL}\n\n## Dependencies\n\nPackages this skill needs.\n\n{line}\n"
    )
    (skill_dir / "oc_skill.py").write_text("print('ran')\n")
    sdk = root / "_sdk"
    sdk.mkdir(exist_ok=True)
    table = DEFAULT_REGISTRY if registry is None else registry
    (sdk / "deps.py").write_text(f"DEPENDENCIES = {json.dumps(table, indent=1)}\n")
    return load_skills(root)


def python_dir(tmp_path: Path) -> Path:
    """A directory holding ``python`` → the base interpreter, and a ``uv`` that must never run."""
    directory = tmp_path / "fakebin"
    directory.mkdir(exist_ok=True)
    link = directory / "python"
    if not link.exists():
        link.symlink_to(BASE_PYTHON)
    uv = directory / "uv"
    uv.write_text(f"#!/bin/sh\necho called > {tmp_path / 'UV_CALLED'}\nexit 1\n")
    uv.chmod(0o755)
    return directory


def agent_environment(tmp_path: Path, pip_config: Path | None, **extra: str) -> dict[str, str]:
    """The environment the tool sees as the agent's."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": f"{python_dir(tmp_path)}:/usr/bin:/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
    }
    if pip_config is not None:
        env["PIP_CONFIG_FILE"] = str(pip_config)
    env.update(extra)
    return env


class PathProbeRunner(LocalProbeRunner):
    """The local probe runner, with ``PATH`` from the test's agent environment."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._path = environment["PATH"]
        self.calls = 0

    async def run(self, command, *, cwd, timeout, env=None):
        self.calls += 1
        return await super().run(command, cwd=cwd, timeout=timeout, env={**(env or {}), "PATH": self._path})


@dataclass
class Call:
    argv: list[str]
    cwd: str
    env: dict[str, str]
    output: CommandOutput | None = None

    @property
    def stage(self) -> str:
        if "venv" in self.argv[:4]:
            return "venv"
        if self.argv[2:4] == ["-m", "pip"]:
            rest = self.argv[4:]
            if rest[:2] == ["config", "list"]:
                return "config"
            if rest[:1] == ["check"]:
                return "check"
            if rest[:1] == ["install"]:
                return "dry-run" if "--dry-run" in rest else "install"
        return "verify"


@dataclass
class RecordingRunner:
    """The real command runner, recording every call; *after* hooks run once a stage finishes."""

    after: dict[str, Callable[[], None]] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    inner: LocalCommandRunner = field(default_factory=LocalCommandRunner)

    async def run(self, argv, *, cwd, env, timeout) -> CommandOutput:
        call = Call(list(argv), cwd, dict(env))
        self.calls.append(call)
        output = await self.inner.run(argv, cwd=cwd, env=env, timeout=timeout)
        call.output = output
        hook = self.after.pop(call.stage, None)
        if hook is not None:
            hook()
        return output

    def stages(self) -> list[str]:
        return [call.stage for call in self.calls]


@dataclass
class Harness:
    """One tool over one skills tree, with its recorders."""

    tmp_path: Path
    skills: SkillIndex
    root: Path
    environment: dict[str, str]
    runner: RecordingRunner
    probe: PathProbeRunner
    tool: Any
    asked: list[ApprovalRequest] = field(default_factory=list)
    calls_at_ask: list[int] = field(default_factory=list)
    """How many installation commands had run each time the card was shown."""

    def call(self, packages: Sequence[str], *, skill: str = SKILL, approve: bool = True) -> str:
        """Call the tool through ``execute``; returns its output, raising on ``is_error`` is left to the caller."""

        def channel(request: ApprovalRequest) -> ApprovalDecision:
            self.asked.append(request)
            self.calls_at_ask.append(len(self.runner.calls))
            return ApprovalDecision(approved=approve, reason="" if approve else "no, thank you")

        async def main() -> str:
            with use_tool_context(approval=channel):
                return await self.tool.execute(json.dumps({"skills": [skill], "packages": list(packages)}))

        return asyncio.run(asyncio.wait_for(main(), 300))

    def key_dirs(self) -> list[Path]:
        return sorted(p for p in self.root.iterdir() if len(p.name) == 16) if self.root.is_dir() else []


def harness(
    tmp_path: Path,
    pip_config: Path | None,
    *,
    declared: Sequence[str] = DEFAULT_DECLARED,
    registry: Mapping[str, Mapping[str, Any]] | None = None,
    limits: InstallLimits = InstallLimits(),
    root: Path | None = None,
    pyproject: Path | None = None,
    **extra_env: str,
) -> Harness:
    skills = make_skills(tmp_path / "skills", declared=declared, registry=registry)
    environment = agent_environment(tmp_path, pip_config, **extra_env)
    runner = RecordingRunner()
    probe = PathProbeRunner(environment)
    overlay_root = root or tmp_path / "envs"
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    tool = install_skill_deps_tool(
        skills,
        registry=read_registry(tmp_path / "skills" / "_sdk" / "deps.py"),
        probe_runner=probe,
        workspace=str(workspace),
        builder=OverlayBuilder(overlay_root, environment=lambda: environment, runner=runner, limits=limits),
        pyproject=pyproject,
    )
    return Harness(tmp_path, skills, overlay_root, environment, runner, probe, tool)
