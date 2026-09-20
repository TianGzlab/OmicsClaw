"""``DockerEnvironment.run_bash`` against real processes.

Driven through :class:`FakeDocker`, whose ``exec`` really runs the
wrapper script on this machine as a child of the fake client. Killing
the client therefore leaves the command running — the property of a
real ``docker exec`` that the in-container kill exists for — so every
test here that asserts a process is gone is asserting that kill worked.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import signal
import time
from pathlib import Path

import pytest

from omicsclaw.sandbox import (
    DockerEnvironment,
    ExecResult,
    SandboxError,
    SandboxManager,
)
from omicsclaw.sandbox import environment as environment_module
from omicsclaw.tools import ToolRegistry, Workspace
from omicsclaw.tools.builtin.bash import BashEnvironment, BashTool, CommandOutcome
from omicsclaw.tools.context import ApprovalDecision, use_tool_context
from omicsclaw.schema import ToolCall

from ._support import FakeDocker, process_alive

_DEADLINE = 60.0


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, _DEADLINE))


@pytest.fixture
def docker(tmp_path: Path) -> FakeDocker:
    return FakeDocker.install(tmp_path / "fake")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "ws"
    path.mkdir()
    return path.resolve()


async def _started(docker: FakeDocker, workspace: Path, **overrides):
    manager = SandboxManager(docker.config(**overrides))
    environment = await manager.create(workspace)
    return manager, environment


def _kill_quietly(pid_file: Path) -> None:
    try:
        os.kill(int(pid_file.read_text().strip()), signal.SIGKILL)
    except (OSError, ValueError):
        pass


# ---- the contract with the bash tool -------------------------------------


def test_it_satisfies_the_bash_tools_protocol_structurally(docker, workspace):
    """The sandbox package imports nothing from ``omicsclaw.tools``; this is
    the only place the two are checked against each other."""

    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            assert isinstance(environment, BashEnvironment)
        finally:
            await manager.aclose()

    _run(main())


def test_its_result_carries_every_field_the_bash_tool_reads():
    ours = {field.name for field in dataclasses.fields(ExecResult)}
    theirs = {field.name for field in dataclasses.fields(CommandOutcome)}

    assert theirs <= ours


def test_file_methods_are_deliberately_absent():
    """File tools stay on the host: the workspace is the same bytes on both
    sides of the bind mount, and routing them would load a whole file into
    memory where line mode streams it."""
    assert not hasattr(DockerEnvironment, "read_file")
    assert not hasattr(DockerEnvironment, "write_file")


# ---- running a command ---------------------------------------------------


def test_output_and_exit_status_come_back_and_nothing_is_left(docker, workspace):
    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            result = await environment.run_bash(
                "echo out; echo err >&2; pwd; exit 3", str(workspace), 30
            )
            io_dir = manager._containers[environment.id].io_dir
            return result, list(io_dir.iterdir())
        finally:
            await manager.aclose()

    result, leftovers = _run(main())

    assert result.exit_code == 3
    assert result.output == f"out\nerr\n{workspace}\n"
    assert not result.timed_out
    assert leftovers == []


def test_a_command_is_one_argument_and_needs_no_quoting(docker, workspace):
    command = """printf '%s|' "a b" 'c"d' "$HOME_NOT_SET"; echo"""

    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            return await environment.run_bash(command, str(workspace), 30)
        finally:
            await manager.aclose()

    assert _run(main()).output == 'a b|c"d||\n'


def test_a_backgrounded_process_does_not_hold_the_call_open(docker, workspace):
    """The command's output goes to a file, not to ``exec``'s own stdio, so
    a daemon it starts cannot keep ``docker exec`` waiting for EOF."""
    marker = workspace / "bg.pid"

    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            started = time.monotonic()
            result = await environment.run_bash(
                f"sleep 30 & echo $! > {marker}; echo started", str(workspace), 30
            )
            return result, time.monotonic() - started
        finally:
            await manager.aclose()

    try:
        result, elapsed = _run(main())
    finally:
        _kill_quietly(marker)

    assert result.output == "started\n"
    assert elapsed < 10


def test_its_own_deadline_kills_the_command_inside_the_container(
    docker, workspace, monkeypatch
):
    """For a caller without a deadline of its own — the bootstrap."""
    monkeypatch.setattr(environment_module, "OWN_DEADLINE_GRACE_S", 0.0)
    marker = workspace / "cmd.pid"

    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            return await environment.run_bash(
                f"echo partial; echo $$ > {marker}; sleep 30", str(workspace), 1.0
            )
        finally:
            await manager.aclose()

    try:
        result = _run(main())
        time.sleep(0.3)
        alive = process_alive(int(marker.read_text()))
    finally:
        _kill_quietly(marker)

    assert result.timed_out
    assert result.exit_code == 137
    assert result.output == "partial\n"
    assert not alive, "the command survived its deadline"


def test_a_cancelled_caller_kills_the_command_inside_the_container(
    docker, workspace
):
    """Killing the ``docker exec`` client is not enough: the process it
    started keeps running. harness9 stops at the client."""
    marker = workspace / "cmd.pid"

    async def main():
        manager, environment = await _started(docker, workspace)
        io_dir = manager._containers[environment.id].io_dir
        try:
            task = asyncio.ensure_future(
                environment.run_bash(
                    f"echo $$ > {marker}; sleep 30", str(workspace), 60
                )
            )
            while not marker.exists() or not marker.read_text().strip():
                await asyncio.sleep(0.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return list(io_dir.iterdir())
        finally:
            await manager.aclose()

    try:
        leftovers = _run(main())
        time.sleep(0.3)
        alive = process_alive(int(marker.read_text()))
    finally:
        _kill_quietly(marker)

    assert not alive, "the command survived its caller's cancellation"
    assert leftovers == []


def test_a_stopped_container_is_a_sandbox_error_not_a_failed_command(
    docker, workspace
):
    """harness9 folds both into one output string; a model told "exit 1"
    would go and fix a command that never ran."""

    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            record = docker.containers()[0]
            record["status"] = "exited"
            path = docker.state / "containers" / f"{record['id']}.json"
            path.write_text(json.dumps(record))
            await environment.run_bash("echo hi", str(workspace), 30)
        finally:
            await manager.aclose()

    with pytest.raises(SandboxError, match="is not running"):
        _run(main())


def test_a_destroyed_sandbox_says_so(docker, workspace):
    async def main():
        manager, environment = await _started(docker, workspace)
        await manager.aclose()
        await environment.run_bash("echo hi", str(workspace), 30)

    with pytest.raises(SandboxError, match="not available"):
        _run(main())


def test_a_command_that_fails_to_run_is_still_a_result(docker, workspace):
    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            return await environment.run_bash(
                "no-such-program-anywhere", str(workspace), 30
            )
        finally:
            await manager.aclose()

    result = _run(main())

    assert result.exit_code == 127
    assert "no-such-program-anywhere" in result.output


# ---- through the real bash tool ------------------------------------------


def _approve(request):
    return ApprovalDecision(approved=True)


def test_the_bash_tool_routes_into_the_sandbox(docker, workspace):
    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            registry = ToolRegistry(
                [BashTool(Workspace(workspace), environment=environment)]
            )
            with use_tool_context(approval=_approve):
                return await registry.execute(
                    ToolCall(id="1", name="bash", arguments='{"command": "echo hi"}')
                )
        finally:
            await manager.aclose()

    result = _run(main())

    assert result.output == "hi\n"
    assert not result.is_error
    execs = [call for call in docker.calls() if call[0] == "exec"]
    assert execs and execs[0][-2] == "echo hi"


def test_the_bash_tools_own_deadline_wins_and_the_command_dies(docker, workspace):
    """The environment's own deadline sits past the tool's, so the model
    reads the tool's ``[TIMEOUT …]`` banner — and cancellation still
    reaches the process inside the container."""
    marker = workspace / "cmd.pid"

    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            tool = BashTool(Workspace(workspace), timeout=1.0, environment=environment)
            with use_tool_context(approval=_approve):
                return await tool.execute(
                    json.dumps({"command": f"echo $$ > {marker}; sleep 30"})
                )
        finally:
            await manager.aclose()

    try:
        text = _run(main())
        time.sleep(0.3)
        alive = process_alive(int(marker.read_text()))
    finally:
        _kill_quietly(marker)

    assert "[TIMEOUT 1s" in text
    assert not alive


def test_the_approval_prompt_says_the_command_runs_in_the_environment(
    docker, workspace
):
    seen = []

    def channel(request):
        seen.append(request)
        return ApprovalDecision(approved=True)

    async def main():
        manager, environment = await _started(docker, workspace)
        try:
            tool = BashTool(Workspace(workspace), environment=environment)
            with use_tool_context(approval=channel):
                await tool.execute(json.dumps({"command": "true"}))
        finally:
            await manager.aclose()

    _run(main())

    assert "injected execution environment" in seen[0].reason
    assert "no OS isolation" not in seen[0].reason
