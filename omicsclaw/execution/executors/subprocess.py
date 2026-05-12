"""``SubprocessExecutor`` — spawn an OS process, stream its output.

This executor runs a real command built from a ``command_factory(ctx)``.
Stdout and stderr are merged and appended to ``ctx.stdout_log``
line-by-line so the Stage-4 SSE log-tail picks the output up live.

Cooperative cancel path (user clicks "Cancel"):
    asyncio cancels the run task → executor catches ``CancelledError`` →
    ``proc.terminate()`` → wait up to 5s → ``proc.kill()`` if still alive.

Failure modes are surfaced as ``JobOutcome`` values rather than raised
exceptions so the jobs router's terminal-state path never has to special-
case executor implementations.
"""

from __future__ import annotations

import asyncio
import collections
import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Optional, Union

from .base import JobContext, JobOutcome

CommandFactory = Callable[[JobContext], Union[list[str], Awaitable[list[str]]]]

_TAIL_LINES = 100
_TERMINATE_GRACE_SECONDS = 5.0


class SubprocessExecutor:
    def __init__(
        self,
        *,
        command_factory: CommandFactory,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[Path] = None,
    ) -> None:
        self._command_factory = command_factory
        self._env = env
        self._cwd = cwd

    async def run(self, ctx: JobContext) -> JobOutcome:
        try:
            command_or_awaitable = self._command_factory(ctx)
            if inspect.isawaitable(command_or_awaitable):
                command = await command_or_awaitable
            else:
                command = command_or_awaitable
            if not command or not isinstance(command, (list, tuple)):
                raise ValueError("command_factory must return a non-empty list")
        except Exception as exc:
            return JobOutcome(
                exit_code=1,
                error=f"command_factory_failed: {exc}",
                stdout_text=str(exc),
            )

        ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self._cwd or ctx.workspace),
                env=self._env,
            )
        except (OSError, FileNotFoundError) as exc:
            return JobOutcome(
                exit_code=127,
                error=f"spawn_failed: {exc}",
                stdout_text=str(exc),
            )

        tail: collections.deque[str] = collections.deque(maxlen=_TAIL_LINES)

        async def _pump_stdout() -> None:
            assert proc.stdout is not None
            with ctx.stdout_log.open("ab") as sink:
                async for raw in proc.stdout:
                    sink.write(raw)
                    sink.flush()
                    tail.append(raw.decode("utf-8", errors="replace").rstrip("\n"))

        try:
            await _pump_stdout()
            await proc.wait()
        except BaseException:
            # Any exit path — cancel, disk-full, interpreter shutdown —
            # must reap the subprocess to avoid orphaning a skill run.
            await _terminate_process(proc)
            raise

        exit_code = proc.returncode if proc.returncode is not None else -1
        return JobOutcome(
            exit_code=exit_code,
            error=None if exit_code == 0 else f"subprocess_exit_{exit_code}",
            stdout_text="\n".join(tail),
        )


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_GRACE_SECONDS)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            return
        try:
            await proc.wait()
        except Exception:
            pass
