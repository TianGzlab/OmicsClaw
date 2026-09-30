"""Where the probe runs: the local shell ``bash`` uses, or the sandbox (plan 0061 case 9).

The local runner goes through ``bash -c`` with the environment ``bash``
itself gets, so the ``python`` it finds is the one on the agent's ``PATH``.
The command changes into the skill directory when it exists there and
otherwise stays in the workspace — the ``sandbox_code_in_image`` case, where
the host path is absent inside the container. A probe that overruns its
limit is killed with its whole process group.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from omicsclaw.skillenv.probe import (
    LocalProbeRunner,
    ProbeError,
    SandboxProbeRunner,
    probe_command,
    run_probe,
)
from omicsclaw.tools.builtin.bash import CommandOutcome


def _fake_python_on_path(tmp_path, monkeypatch) -> Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    fake = bindir / "python"
    fake.symlink_to(sys.executable)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return fake


def test_local_runner_uses_the_python_on_path(tmp_path, monkeypatch):
    fake = _fake_python_on_path(tmp_path, monkeypatch)
    result = asyncio.run(run_probe(LocalProbeRunner(), ["json"], [], str(tmp_path), cwd=str(tmp_path)))
    assert result.executable == str(fake)
    assert LocalProbeRunner.location == "local"


def test_the_skill_directory_is_the_working_directory_when_it_exists(tmp_path, monkeypatch):
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    fake = bindir / "python"
    fake.write_text('#!/bin/sh\necho "cwd=$(pwd)"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    skill = tmp_path / "skill"
    skill.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    code, output = asyncio.run(
        LocalProbeRunner().run(probe_command(["os"], [], str(skill)), cwd=str(workspace), timeout=10)
    )
    assert (code, output.strip()) == (0, f"cwd={skill}")
    code, output = asyncio.run(
        LocalProbeRunner().run(probe_command(["os"], [], str(tmp_path / "gone")), cwd=str(workspace), timeout=10)
    )
    assert (code, output.strip()) == (0, f"cwd={workspace}")


def test_a_skill_directory_absent_here_leaves_the_probe_in_the_workspace(tmp_path, monkeypatch):
    _fake_python_on_path(tmp_path, monkeypatch)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "oc_ws_only.py").write_text("")
    missing = tmp_path / "not" / "here"
    result = asyncio.run(run_probe(LocalProbeRunner(), ["oc_ws_only"], [], str(missing), cwd=str(workspace)))
    assert result.missing == ("oc_ws_only",)


def test_a_probe_past_its_limit_is_killed_with_its_group(tmp_path):
    pidfile = tmp_path / "child.pid"
    command = f"sleep 60 & echo $! > {pidfile}; wait"
    started = time.monotonic()
    code, output = asyncio.run(LocalProbeRunner().run(command, cwd=str(tmp_path), timeout=0.5))
    assert time.monotonic() - started < 10
    assert code != 0
    child = int(pidfile.read_text().strip())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _alive(child):
        time.sleep(0.05)
    assert not _alive(child)


def _alive(pid: int) -> bool:
    status = Path(f"/proc/{pid}/status")
    if not status.exists():
        return False
    return "\nState:\tZ" not in status.read_text()


def test_a_timeout_is_reported_as_a_probe_error(tmp_path):
    class Slow:
        location = "local"

        async def run(self, command, *, cwd, timeout, env=None):
            return 124, "timed out"

    with pytest.raises(ProbeError, match="124"):
        asyncio.run(run_probe(Slow(), ["json"], [], str(tmp_path), cwd=str(tmp_path)))


class _FakeEnvironment:
    def __init__(self, output: str = "{}"):
        self.calls: list[tuple[str, str, float]] = []
        self.output = output

    async def run_bash(self, command: str, cwd: str, timeout: float) -> CommandOutcome:
        self.calls.append((command, cwd, timeout))
        return CommandOutcome(output=self.output, exit_code=0)


def test_sandbox_runner_hands_the_command_over_unchanged():
    environment = _FakeEnvironment("out")
    runner = SandboxProbeRunner(environment)
    assert runner.location == "sandbox"
    code, output = asyncio.run(runner.run("echo hi", cwd="/ws", timeout=10))
    assert (code, output) == (0, "out")
    assert environment.calls == [("echo hi", "/ws", 10)]


def test_sandbox_runner_prefixes_env_assignments():
    environment = _FakeEnvironment()
    asyncio.run(SandboxProbeRunner(environment).run("echo hi", cwd="/ws", timeout=10,
                                                     env={"PYTHONNOUSERSITE": "1"}))
    command = environment.calls[0][0]
    assert command.startswith("env PYTHONNOUSERSITE=1 ")
    assert "echo hi" in command
