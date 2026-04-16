"""``SubprocessExecutor`` — real-process runner for remote jobs.

Spawns an OS subprocess, merges stdout + stderr, and streams the combined
output into ``ctx.stdout_log`` so the Stage-4 SSE tail picks it up live.
Cooperative cancellation terminates the process (SIGTERM, then SIGKILL on
timeout) so a user's "Cancel" button cannot leak runaway skill runs.

Opt-in: callers build a ``command_factory`` that maps a ``JobContext`` to
an argv list. The factory is the seam where skill routing lives — this
class owns process lifecycle only.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest


def _ctx(tmp_path: Path) -> "JobContext":
    from omicsclaw.execution.executors import JobContext

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return JobContext(
        job_id="job-1",
        workspace=workspace,
        skill="noop",
        inputs={},
        params={},
        artifact_root=workspace / "artifacts",
        stdout_log=workspace / "stdout.log",
    )


def test_subprocess_executor_captures_stdout(tmp_path: Path) -> None:
    from omicsclaw.execution.executors import SubprocessExecutor

    ctx = _ctx(tmp_path)
    executor = SubprocessExecutor(
        command_factory=lambda c: [sys.executable, "-c", "print('hello-world')"]
    )
    outcome = asyncio.run(executor.run(ctx))
    assert outcome.exit_code == 0
    assert outcome.error is None
    assert "hello-world" in ctx.stdout_log.read_text(encoding="utf-8")
    assert "hello-world" in outcome.stdout_text


def test_subprocess_executor_nonzero_exit_is_failure(tmp_path: Path) -> None:
    from omicsclaw.execution.executors import SubprocessExecutor

    ctx = _ctx(tmp_path)
    executor = SubprocessExecutor(
        command_factory=lambda c: [sys.executable, "-c", "raise SystemExit(7)"]
    )
    outcome = asyncio.run(executor.run(ctx))
    assert outcome.exit_code == 7
    assert outcome.error is not None
    assert "7" in outcome.error


def test_subprocess_executor_merges_stderr_into_stdout_log(tmp_path: Path) -> None:
    from omicsclaw.execution.executors import SubprocessExecutor

    ctx = _ctx(tmp_path)
    executor = SubprocessExecutor(
        command_factory=lambda c: [
            sys.executable,
            "-c",
            "import sys; print('to-out'); print('to-err', file=sys.stderr)",
        ]
    )
    outcome = asyncio.run(executor.run(ctx))
    assert outcome.exit_code == 0
    content = ctx.stdout_log.read_text(encoding="utf-8")
    assert "to-out" in content
    assert "to-err" in content


def test_subprocess_executor_streams_lines_before_exit(tmp_path: Path) -> None:
    """stdout.log must contain the first line long before the subprocess
    returns — otherwise SSE log-tail stays silent for slow skills."""
    from omicsclaw.execution.executors import SubprocessExecutor

    ctx = _ctx(tmp_path)

    async def run_and_poll() -> tuple[bool, object]:
        executor = SubprocessExecutor(
            command_factory=lambda c: [
                sys.executable,
                "-u",  # unbuffered so the first line flushes immediately
                "-c",
                "import sys,time\nprint('first-flush',flush=True)\ntime.sleep(0.4)\nprint('second')\n",
            ]
        )
        run_task = asyncio.create_task(executor.run(ctx))
        observed_first = False
        for _ in range(30):
            await asyncio.sleep(0.05)
            if ctx.stdout_log.is_file():
                text = ctx.stdout_log.read_text(encoding="utf-8")
                if "first-flush" in text and "second" not in text:
                    observed_first = True
                    break
        outcome = await run_task
        return observed_first, outcome

    observed_first, outcome = asyncio.run(run_and_poll())
    assert outcome.exit_code == 0
    assert observed_first, "expected 'first-flush' to appear before process exit"


def test_subprocess_executor_spawn_failure_yields_outcome(tmp_path: Path) -> None:
    from omicsclaw.execution.executors import SubprocessExecutor

    ctx = _ctx(tmp_path)
    executor = SubprocessExecutor(
        command_factory=lambda c: ["/definitely/not/a/real/binary-9a8b7c"]
    )
    outcome = asyncio.run(executor.run(ctx))
    assert outcome.exit_code != 0
    assert outcome.error is not None
    assert "spawn_failed" in outcome.error


def test_subprocess_executor_command_factory_failure_yields_outcome(
    tmp_path: Path,
) -> None:
    from omicsclaw.execution.executors import SubprocessExecutor

    def boom(ctx):
        raise RuntimeError("planned failure")

    ctx = _ctx(tmp_path)
    outcome = asyncio.run(SubprocessExecutor(command_factory=boom).run(ctx))
    assert outcome.exit_code != 0
    assert outcome.error is not None
    assert "command_factory_failed" in outcome.error


def test_subprocess_executor_cancel_terminates_process(tmp_path: Path) -> None:
    """Cancelling the run task must kill the subprocess promptly; no
    stranded skill run after the user clicks Cancel."""
    from omicsclaw.execution.executors import SubprocessExecutor

    ctx = _ctx(tmp_path)

    async def scenario() -> float:
        executor = SubprocessExecutor(
            command_factory=lambda c: [
                sys.executable,
                "-c",
                "import time; time.sleep(30)",
            ]
        )
        run_task = asyncio.create_task(executor.run(ctx))
        await asyncio.sleep(0.2)  # give subprocess time to start
        start = time.monotonic()
        run_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass
        return time.monotonic() - start

    elapsed = asyncio.run(scenario())
    assert elapsed < 6.0, f"cancel took too long: {elapsed:.2f}s"


def test_subprocess_executor_factory_receives_job_context(tmp_path: Path) -> None:
    from omicsclaw.execution.executors import JobContext, SubprocessExecutor

    seen: list[JobContext] = []

    def factory(ctx: JobContext) -> list[str]:
        seen.append(ctx)
        return [sys.executable, "-c", "pass"]

    ctx = _ctx(tmp_path)
    asyncio.run(SubprocessExecutor(command_factory=factory).run(ctx))
    assert len(seen) == 1
    assert seen[0].job_id == "job-1"
    assert seen[0].workspace == ctx.workspace


def test_subprocess_executor_appends_to_existing_stdout_log(tmp_path: Path) -> None:
    """If another caller (e.g. an earlier phase) seeded stdout.log, the
    executor must append rather than truncate so prior context survives."""
    from omicsclaw.execution.executors import SubprocessExecutor

    ctx = _ctx(tmp_path)
    ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
    ctx.stdout_log.write_text("pre-existing\n", encoding="utf-8")

    executor = SubprocessExecutor(
        command_factory=lambda c: [sys.executable, "-c", "print('after')"]
    )
    asyncio.run(executor.run(ctx))
    content = ctx.stdout_log.read_text(encoding="utf-8")
    assert "pre-existing" in content
    assert "after" in content
