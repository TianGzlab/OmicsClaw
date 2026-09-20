"""``SubprocessRunner`` against real processes."""

from __future__ import annotations

import asyncio
import time

import pytest

from omicsclaw.sandbox import (
    CommandRunner,
    CommandTimedOut,
    SandboxError,
    SubprocessRunner,
)

from ._support import process_alive


def test_it_satisfies_the_protocol():
    assert isinstance(SubprocessRunner(), CommandRunner)


def test_stdout_stderr_and_status_are_kept_apart():
    runner = SubprocessRunner("bash")

    result = asyncio.run(runner.run(["-c", "echo out; echo err >&2; exit 3"]))

    assert result.returncode == 3
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
    assert not result.ok
    assert result.detail() == "err"


def test_a_missing_cli_is_a_sandbox_error_naming_it():
    runner = SubprocessRunner("definitely-not-a-container-runtime")

    with pytest.raises(SandboxError, match="definitely-not-a-container-runtime"):
        asyncio.run(runner.run(["info"]))


def test_a_timeout_kills_the_cli_and_says_so(tmp_path):
    runner = SubprocessRunner("bash")
    pid_file = tmp_path / "pid"

    async def main():
        await runner.run(["-c", f"echo $$ > {pid_file}; exec sleep 30"], timeout=0.5)

    started = time.monotonic()
    with pytest.raises(CommandTimedOut):
        asyncio.run(main())

    assert time.monotonic() - started < 5
    assert not process_alive(int(pid_file.read_text()))


def test_cancellation_kills_the_cli_and_propagates(tmp_path):
    runner = SubprocessRunner("bash")
    pid_file = tmp_path / "pid"

    async def main():
        task = asyncio.ensure_future(
            runner.run(["-c", f"echo $$ > {pid_file}; exec sleep 30"])
        )
        while not pid_file.exists() or not pid_file.read_text().strip():
            await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.2)

    asyncio.run(main())

    assert not process_alive(int(pid_file.read_text()))


def test_stdin_is_not_inherited():
    """A CLI that read the terminal would compete with the user for it."""
    result = asyncio.run(SubprocessRunner("bash").run(["-c", "cat; echo done"]))

    assert result.stdout == "done\n"
