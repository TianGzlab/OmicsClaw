"""The ``bash`` tool stops everything a command started, not only the shell.

``_locally`` runs ``bash -c`` in a session of its own, so the shell's pid is
also the id of a process group that holds every process the command
forked. A deadline, a cancellation, or anything else that abandons the call
kills that group. Killing the shell alone — what ``process.kill()`` does —
leaves a pipeline's other members, a ``& wait`` job, or the foreground child
of ``cd x && script.py && echo done`` running, reparented and unreachable,
with nothing left to bound it.

**Why cancellation has to kill, not just the timeout.** Before the shell had
a session of its own, ``Ctrl-C`` at the terminal reached the command
directly, because it sat in the terminal's foreground process group. It no
longer does: the terminal's SIGINT goes to OmicsClaw, which cancels the
turn, and the cancellation is the only thing that can reach the command. A
cancellation that killed only the shell would therefore leave *more*
behind than before the session was added.

**Why a command that finishes on its own is not killed.** Its background
jobs are meant to outlive the call — the tool's description tells the
model so, and ``test_bash.py`` pins it
(``test_a_backgrounded_child_is_still_running_when_the_call_returns``).
Only the abnormal exits kill.

Liveness is read from ``/proc`` rather than asked with ``os.kill(pid, 0)``:
a killed process that has not been reaped yet is a zombie, and a zombie
answers ``kill(pid, 0)`` as though it were alive. Every process a test
records is SIGKILLed in a ``finally``, so a failure here does not leave a
``sleep 60`` behind to fail something later.
"""

from __future__ import annotations

import asyncio
import errno
import json
import os
import signal
import time
from asyncio import base_subprocess
from pathlib import Path
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.tools import ApprovalDecision, ApprovalRequest
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.builtin import bash as bash_module
from omicsclaw.tools.builtin.bash import BashTool, CommandOutcome
from omicsclaw.tools.context import use_tool_context

pytestmark = pytest.mark.skipif(
    not os.path.isdir("/proc"), reason="reads process state from /proc"
)

_T = TypeVar("_T")

_DEADLINE = 20.0
"""Outer bound on one test's coroutine, so a hang fails instead of stalling."""

_DIES_WITHIN = 2.0
"""Seconds a SIGKILLed process is given to disappear from ``/proc``."""

_REAL_KILLPG = os.killpg
"""Kept before any test replaces ``os.killpg``, for cleaning up after it."""


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


def _yes(request: ApprovalRequest) -> ApprovalDecision:
    return ApprovalDecision(approved=True)


def _tool(tmp_path: Path, timeout: float) -> BashTool:
    return BashTool(Workspace(tmp_path), timeout=timeout)


def _sleeper(pidfile: Path, seconds: int = 60) -> str:
    """A subshell that records its pid and then *becomes* ``sleep``.

    ``exec`` keeps the pid, so what is recorded is the process that has to
    die. A subshell rather than a bare ``sleep`` because bash runs the last
    simple command of ``-c`` in place of itself, and a ``sleep`` that *is*
    the shell is killed by ``process.kill()`` too — the test would not tell
    the two kills apart.
    """
    return f"(echo $BASHPID > {pidfile}; exec sleep {seconds})"


_SHAPES = {
    # Both members of a pipeline are children of the shell.
    "pipeline": "{sleeper} | cat",
    # A background job the shell is waiting on.
    "background-and-wait": "{sleeper} & wait",
    # The shape a skill invocation has: a foreground child that is not the
    # last command, so bash forks it instead of exec-ing it.
    "foreground-child": "cd . && {sleeper} && echo finished",
}


def _recorded(pidfile: Path) -> int | None:
    try:
        text = pidfile.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _running(pid: int, name: str = "sleep") -> bool:
    """Whether *pid* is a live (not zombie) process called *name*.

    The name guards against a pid that was reaped and reused by something
    else between the kill and the check.
    """
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            stat = f.read()
    except OSError:
        return False
    comm = stat[stat.find("(") + 1 : stat.rfind(")")]
    state = stat[stat.rfind(")") + 2 :].split()[0]
    return comm == name and state != "Z"


def _dies(pid: int) -> bool:
    deadline = time.monotonic() + _DIES_WITHIN
    while _running(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


async def _written(pidfile: Path) -> int:
    """The pid in *pidfile*, waiting for the command to write it."""
    deadline = time.monotonic() + 5.0
    while (pid := _recorded(pidfile)) is None:
        if time.monotonic() > deadline:
            raise AssertionError(f"the command never wrote {pidfile}")
        await asyncio.sleep(0.02)
    return pid


def _cleanup(pidfile: Path, name: str = "sleep") -> None:
    """SIGKILL the process *pidfile* names, if it is still the one recorded."""
    pid = _recorded(pidfile)
    if pid is not None and _running(pid, name):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _cleanup_group(pgidfile: Path) -> None:
    """SIGKILL the group led by the shell *pgidfile* names, if it still runs.

    Uses the real ``os.killpg``, because the tests that need this have
    replaced it with one that refuses.
    """
    pgid = _recorded(pgidfile)
    if pgid is not None and _running(pgid, "bash"):
        try:
            _REAL_KILLPG(pgid, signal.SIGKILL)
        except OSError:
            pass


def _present(pid: int) -> bool:
    """Whether *pid* has a ``/proc`` entry at all, a zombie included."""
    return os.path.exists(f"/proc/{pid}")


async def _dies_on_the_loop(pid: int) -> bool:
    """:func:`_dies`, polled without blocking the loop the kill runs on."""
    deadline = time.monotonic() + _DIES_WITHIN
    while _running(pid):
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.02)
    return True


def _hold_the_transport(monkeypatch) -> asyncio.Event:
    """Hold every subprocess transport before it connects, until released.

    The child has been exec-ed by then and runs on; only
    ``create_subprocess_exec`` is kept from returning.
    """
    release = asyncio.Event()
    connect = base_subprocess.BaseSubprocessTransport._connect_pipes

    async def held(self, waiter):
        await release.wait()
        return await connect(self, waiter)

    monkeypatch.setattr(
        base_subprocess.BaseSubprocessTransport, "_connect_pipes", held
    )
    return release


def _recording_start(monkeypatch, started: list) -> None:
    """Make ``_start`` also hand each process it starts to *started*."""
    real_start = bash_module._start

    async def recording(command, cwd, sink):
        process = await real_start(command, cwd, sink)
        started.append(process)
        return process

    monkeypatch.setattr(bash_module, "_start", recording)


# ---- the timeout ---------------------------------------------------------


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_a_timeout_kills_what_the_command_started(tmp_path, shape):
    """The reported defect: after the banner, the child kept running.

    Measured before the fix with ``cd /tmp && sleep 7 && echo …`` and a
    0.5 s budget: the tool returned its ``[TIMEOUT`` banner and ``sleep 7``
    was still alive. The banner tells the model the command was stopped;
    a skill script carrying on in the background makes that untrue.
    """
    pidfile = tmp_path / "pid"
    command = _SHAPES[shape].format(sleeper=_sleeper(pidfile))
    try:
        with use_tool_context(approval=_yes):
            result = _run(
                _tool(tmp_path, 0.5).execute(json.dumps({"command": command}))
            )
        pid = _recorded(pidfile)

        assert "[TIMEOUT 0.5s" in result
        assert pid is not None, "the command never started its child"
        assert _dies(pid), f"{shape}: the child outlived the timeout"
    finally:
        _cleanup(pidfile)


# ---- cancellation --------------------------------------------------------


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_a_cancelled_call_kills_what_the_command_started(tmp_path, shape):
    """User ``Ctrl-C``, the engine's per-tool deadline and a session shutting
    down all reach this tool as a cancelled Task. The terminal's own SIGINT
    does not reach the command any more (see this module's docstring), so
    this kill is the only one that happens."""
    pidfile = tmp_path / "pid"
    command = _SHAPES[shape].format(sleeper=_sleeper(pidfile))
    tool = _tool(tmp_path, 30.0)

    async def scenario() -> tuple[bool, int]:
        with use_tool_context(approval=_yes):
            task = asyncio.ensure_future(
                tool.execute(json.dumps({"command": command}))
            )
            pid = await _written(pidfile)
            task.cancel()
            await asyncio.wait({task})
            return task.cancelled(), pid

    try:
        cancelled, pid = _run(scenario())

        assert cancelled, "the cancellation was not passed on"
        assert _dies(pid), f"{shape}: the child outlived the cancellation"
    finally:
        _cleanup(pidfile)


def test_a_cancelled_call_reaps_the_shell_before_the_cancellation_moves_on(
    tmp_path, monkeypatch
):
    """Killed *and* reaped, before ``CancelledError`` leaves ``_locally``.

    The kill alone is not enough when the cancellation is a shutdown: the
    loop that would notice the shell exit may be closed right after, which
    leaves the shell a zombie and its transport unclosed. Awaiting the exit
    on the cancellation path settles it while the loop still runs.

    Observed in the same step the exception arrives in, so the loop gets no
    chance to reap the shell on its own in between: without the wait,
    ``returncode`` is still ``None`` here.
    """
    started: list[Any] = []
    _recording_start(monkeypatch, started)
    pidfile = tmp_path / "pid"
    seen: list[int | None] = []

    async def call() -> None:
        try:
            await bash_module._locally(f"{_sleeper(pidfile)} | cat", tmp_path, 30.0)
        except asyncio.CancelledError:
            seen.append(started[0].returncode)
            raise

    async def scenario() -> bool:
        task = asyncio.ensure_future(call())
        await _written(pidfile)
        task.cancel()
        await asyncio.wait({task})
        return task.cancelled()

    try:
        assert _run(scenario()) is True
        assert seen == [-signal.SIGKILL]
    finally:
        _cleanup(pidfile)


# ---- a cancellation while the shell is still starting --------------------


def test_a_call_cancelled_while_its_shell_is_still_starting_kills_the_group(
    tmp_path, monkeypatch
):
    """The window between ``exec`` and ``create_subprocess_exec`` returning.

    ``create_subprocess_exec`` returns only once the transport has connected
    its pipes, and the shell is already running by then — long enough, on
    a busy loop, to have started a pipeline. A cancellation that lands in
    that window never reaches ``_locally``'s own handler: asyncio's cleanup
    inside the spawn closes the transport, which SIGKILLs the shell and
    nothing else, and the pipeline runs on in a session the terminal's
    SIGINT does not reach. At twice CPU oversubscription the window was hit
    on five runs out of five; the transport is held open here so that it is
    hit every time.

    Also checked: the shell is reaped before ``CancelledError`` leaves
    ``_locally``, as on the ordinary cancellation path.
    """
    release = _hold_the_transport(monkeypatch)
    pidfile = tmp_path / "pid"
    shellfile = tmp_path / "shell"
    shell_left: list[bool] = []

    async def call() -> None:
        try:
            await bash_module._locally(
                f"echo $$ > {shellfile}; {_sleeper(pidfile)} | cat", tmp_path, 30.0
            )
        except asyncio.CancelledError:
            shell = _recorded(shellfile)
            shell_left.append(shell is None or _present(shell))
            raise

    async def scenario() -> tuple[bool, int]:
        task = asyncio.ensure_future(call())
        pid = await _written(pidfile)
        task.cancel()
        await asyncio.sleep(0)  # the cancellation lands while the transport is held
        release.set()
        await asyncio.wait({task})
        return task.cancelled(), pid

    try:
        cancelled, pid = _run(scenario())

        assert cancelled, "the cancellation was not passed on"
        assert _dies(pid), "the pipeline outlived a cancellation during the spawn"
        assert shell_left == [False], "the shell was not reaped first"
    finally:
        _cleanup(pidfile)


def test_a_spawn_slower_than_the_grace_neither_holds_the_cancellation_nor_escapes(
    tmp_path, monkeypatch
):
    """The wait for a spawn to finish is bounded, and the kill is not.

    A cancelled turn — or a shutdown — must not stay open for as long as a
    starved loop takes to connect a transport, so the cancellation moves on
    after the grace period. The process is still started, though, and still
    needs killing: the kill is attached to the spawn's completion, so it
    happens whenever that is.
    """
    monkeypatch.setattr(bash_module, "_REAP_GRACE", 0.2)
    release = _hold_the_transport(monkeypatch)
    pidfile = tmp_path / "pid"

    async def scenario() -> tuple[bool, float, bool]:
        task = asyncio.ensure_future(
            bash_module._locally(f"{_sleeper(pidfile)} | cat", tmp_path, 30.0)
        )
        pid = await _written(pidfile)
        asyncio.get_running_loop().call_later(1.0, release.set)
        started = time.monotonic()
        task.cancel()
        await asyncio.wait({task})
        elapsed = time.monotonic() - started
        await release.wait()
        return task.cancelled(), elapsed, await _dies_on_the_loop(pid)

    try:
        cancelled, elapsed, died = _run(scenario())

        assert cancelled, "the cancellation was not passed on"
        assert elapsed < 0.8, f"the cancellation waited {elapsed:.1f}s for the spawn"
        assert died, "the pipeline outlived a spawn that finished after the grace"
    finally:
        _cleanup(pidfile)


# ---- anything else that abandons the call --------------------------------


class _Unforeseen(Exception):
    """Stands in for an exit path the code does not name."""


def test_an_unforeseen_exception_while_waiting_still_kills_the_group(
    tmp_path, monkeypatch
):
    """Neither the deadline nor a cancellation, and the group still dies.

    The realistic cases are a ``GeneratorExit`` when a pending Task is
    destroyed with its loop, or a ``KeyboardInterrupt`` raised in the
    frame; an exception out of ``wait()`` takes the same path through
    ``_locally`` and is one a test can raise on cue.
    """
    pidfile = tmp_path / "pid"
    real_start = bash_module._start
    started: list[Any] = []

    async def start_with_a_breaking_wait(command, cwd, sink):
        process = await real_start(command, cwd, sink)
        started.append((process, process.wait))

        async def breaking_wait() -> int:
            await _written(pidfile)
            raise _Unforeseen()

        process.wait = breaking_wait
        return process

    monkeypatch.setattr(bash_module, "_start", start_with_a_breaking_wait)

    async def scenario() -> tuple[bool, int | None]:
        with pytest.raises(_Unforeseen):
            await bash_module._locally(
                f"{_sleeper(pidfile)} | cat", tmp_path, 30.0
            )
        pid = _recorded(pidfile)
        died = pid is not None and _dies(pid)
        # Reap the shell on the loop that started it, killing it first if
        # the code under test did not.
        process, real_wait = started[0]
        if process.returncode is None and not died:
            process.kill()
        await asyncio.wait_for(real_wait(), 5.0)
        return died, pid

    try:
        died, pid = _run(scenario())

        assert pid is not None, "the command never started its child"
        assert died, "the child outlived an exception while waiting"
    finally:
        _cleanup(pidfile)


# ---- signalling what is already gone, or not ours to signal --------------


def test_signalling_a_command_that_has_already_exited_is_not_an_error(
    tmp_path,
):
    """The deadline can fire as the shell exits. By the time the kill runs
    the group may be empty, and ``killpg`` says so with ``ESRCH``; the
    thing asked for has already happened."""

    async def scenario() -> tuple[int, int]:
        with open(os.devnull, "wb") as sink:
            process = await bash_module._start("exit 3", tmp_path, sink)
            code = await process.wait()
            bash_module._signal(process)
            return code, await bash_module._kill(process)

    assert _run(scenario()) == (3, 3)


def _refusing_killpg(monkeypatch) -> None:
    """``os.killpg`` refuses, and the wait for the unkilled shell is short.

    ``killpg`` answers ``EPERM`` when no member of the group is one this
    process may signal: a setuid program such as ``sudo`` that the shell
    exec-ed into. There is nothing further to try, and raising would turn
    a cancellation into an error the model is then asked to fix.
    """

    def refuse(pgid: int, signum: int) -> None:
        raise PermissionError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "killpg", refuse)
    monkeypatch.setattr(bash_module, "_REAP_GRACE", 0.2)


def test_a_cancellation_stays_prompt_and_stays_a_cancellation_when_the_kill_fails(
    tmp_path, monkeypatch
):
    """The cancellation path waits for the killed shell, and that wait is
    bounded. A process SIGKILL does not reach must not hold a cancelled
    turn — or a shutdown — open for as long as it cares to run."""
    _refusing_killpg(monkeypatch)
    pidfile = tmp_path / "pgid"
    tool = _tool(tmp_path, 30.0)
    command = f"echo $$ > {pidfile}; sleep 3; true"

    async def scenario() -> tuple[bool, float]:
        with use_tool_context(approval=_yes):
            task = asyncio.ensure_future(
                tool.execute(json.dumps({"command": command}))
            )
            await _written(pidfile)
            started = time.monotonic()
            task.cancel()
            await asyncio.wait({task})
            return task.cancelled(), time.monotonic() - started

    try:
        cancelled, elapsed = _run(scenario())

        assert cancelled, "a failed kill turned the cancellation into an error"
        assert elapsed < 1.5, f"the cancellation waited {elapsed:.1f}s"
    finally:
        _cleanup_group(pidfile)


def test_a_timeout_still_reports_its_banner_when_the_kill_fails(
    tmp_path, monkeypatch
):
    """The same bound on the timeout path: the model reads the tool's own
    banner rather than waiting for the engine's deadline."""
    _refusing_killpg(monkeypatch)
    pidfile = tmp_path / "pgid"
    command = f"echo $$ > {pidfile}; sleep 3; true"

    try:
        started = time.monotonic()
        with use_tool_context(approval=_yes):
            result = _run(
                _tool(tmp_path, 0.3).execute(json.dumps({"command": command}))
            )
        elapsed = time.monotonic() - started

        assert "[TIMEOUT 0.3s" in result
        assert elapsed < 1.5, f"the timeout waited {elapsed:.1f}s"
    finally:
        _cleanup_group(pidfile)


# ---- what the model is told ----------------------------------------------


def test_the_description_says_a_killed_command_takes_its_background_with_it(
    tmp_path,
):
    """The description promises that background jobs keep running. That is
    true of a command that finishes in time and false of one the deadline
    kills, and a model planning ``nohup server & sleep 50`` needs the
    difference."""
    description = _tool(tmp_path, 45.0).definition().description

    assert "everything they started is killed with them" in description
    assert "in a command that finishes in time keeps running" in description


class _Environment:
    async def run_bash(self, command: str, cwd: str, timeout: float) -> CommandOutcome:
        return CommandOutcome(output="", exit_code=0)


def test_through_an_injected_environment_the_description_promises_no_group_kill(
    tmp_path,
):
    """What a kill reaches depends on where the command runs. Locally it is
    the whole process group. The sandbox's environment kills the one pid it
    recorded, so a pipeline's other members and a background job survive
    it, and an injected environment in general is not this tool's to vouch
    for. A model told that everything was killed would start a second
    server on top of the first one a timed-out command left behind."""
    tool = BashTool(Workspace(tmp_path), environment=_Environment())
    description = tool.definition().description

    assert "killed with them" not in description
    assert "what they started may keep running" in description
    assert "in a command that finishes in time keeps running" in description
