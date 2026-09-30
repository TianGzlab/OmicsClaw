"""Where a trial's commands run: on this machine, or in the ``bash`` sandbox.

Both executors run an argv with a working directory, extra environment
variables, a log file and a time limit, and return how it ended. The local one
starts the command as the leader of a new process group and kills the whole
group on timeout or cancellation. The sandbox one hands a quoted command line
to the same ``BashEnvironment`` that ``bash`` uses, so trials run wherever
``bash`` runs.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from omicsclaw.tools.builtin.bash import BashEnvironment, spawn_group_leader, without_control_credentials

__all__ = [
    "CommandExecutor",
    "CommandResult",
    "ENV_WHITELIST",
    "LocalExecutor",
    "SandboxExecutor",
    "whitelisted_environment",
]

ENV_WHITELIST: frozenset[str] = frozenset(
    {
        "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE", "SHELL",
        "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
        "R_HOME", "R_LIBS", "R_LIBS_USER", "JAVA_HOME", "XDG_CACHE_HOME",
        "LD_LIBRARY_PATH", "CUDA_HOME", "CUDA_PATH",
    }
)
"""Variables a local trial inherits from this process. Everything else —
API keys and bot tokens above all — is left behind; the trial's own variables
(``PYTHONPATH``, ``CUDA_VISIBLE_DEVICES``, thread counts, temporary and cache
directories) are set explicitly on top."""

_KILL_GRACE_S = 2.0


def whitelisted_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """The :data:`ENV_WHITELIST` subset of *source* (default ``os.environ``)."""
    source = os.environ if source is None else source
    return {name: value for name, value in source.items() if name in ENV_WHITELIST}


@dataclass(frozen=True, slots=True)
class CommandResult:
    """How a command ended: its exit status, whether the executor's deadline hit, and output."""

    exit_code: int
    timed_out: bool = False
    output: str = ""


class CommandExecutor(Protocol):
    """Runs trial commands somewhere."""

    location: str
    """``"local"`` or ``"sandbox"``."""

    python: str
    """The interpreter trials and scoring run under, as that location names it."""

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        log: Path,
        timeout: float,
    ) -> CommandResult:
        """Run *argv* in *cwd* with *env* added, stdout and stderr appended to *log*.

        Cancellation kills the command before it propagates.
        """
        ...

    async def capture(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Run *argv* with *env* added and return its merged output; for short probes."""
        ...


class LocalExecutor:
    """Run commands on this machine.

    :param python: Interpreter for trials; defaults to this process's.
    :param base_env: Where the whitelisted variables come from; defaults to ``os.environ``.
    """

    location = "local"

    def __init__(self, *, python: str = "", base_env: Mapping[str, str] | None = None) -> None:
        self.python = python or sys.executable
        self._base_env = base_env

    def environment(self, extra: Mapping[str, str]) -> dict[str, str]:
        """The full environment a command gets: whitelisted inherited variables, then *extra*,
        with the framework's control-plane credentials removed from both."""
        return without_control_credentials({**whitelisted_environment(self._base_env), **extra})

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        log: Path,
        timeout: float,
    ) -> CommandResult:
        with open(log, "ab") as sink:
            process = await spawn_group_leader(
                asyncio.create_subprocess_exec(
                    *argv,
                    cwd=str(cwd),
                    env=self.environment(env),
                    stdout=sink,
                    stderr=subprocess.STDOUT,
                    stdin=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
            )
            try:
                async with asyncio.timeout(timeout):
                    code = await process.wait()
            except TimeoutError:
                code = await _kill_group(process)
                return CommandResult(exit_code=_status(code), timed_out=True)
            except asyncio.CancelledError:
                await _kill_group(process)
                raise
        return CommandResult(exit_code=_status(code))

    async def capture(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        process = await spawn_group_leader(
            asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                env=self.environment(env or {}),
                stdout=asyncio.subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        )
        try:
            async with asyncio.timeout(timeout):
                output, _ = await process.communicate()
        except TimeoutError:
            code = await _kill_group(process)
            return CommandResult(exit_code=_status(code), timed_out=True)
        except asyncio.CancelledError:
            await _kill_group(process)
            raise
        return CommandResult(
            exit_code=_status(process.returncode or 0),
            output=output.decode("utf-8", errors="replace"),
        )


class SandboxExecutor:
    """Run commands through a ``BashEnvironment``, as ``env K=V … argv > log 2>&1``.

    Only the command's own variables are passed; the container's environment
    supplies the rest. *log* must be a path the container sees at the same
    location, which holds for anything under the workspace.

    :param environment: The sandbox's ``BashEnvironment``.
    :param python: Interpreter name inside the container.
    """

    location = "sandbox"

    def __init__(self, environment: BashEnvironment, *, python: str = "") -> None:
        self.environment = environment
        self.python = python or "python"

    def command_line(self, argv: Sequence[str], env: Mapping[str, str], log: Path | None) -> str:
        """The shell command handed to ``run_bash``."""
        parts = ["env"]
        parts += [shlex.quote(f"{name}={value}") for name, value in env.items()]
        parts += [shlex.quote(arg) for arg in argv]
        line = " ".join(parts)
        if log is not None:
            line += f" >> {shlex.quote(str(log))} 2>&1"
        return line

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        log: Path,
        timeout: float,
    ) -> CommandResult:
        outcome = await self.environment.run_bash(self.command_line(argv, env, log), str(cwd), timeout)
        return CommandResult(
            exit_code=outcome.exit_code,
            timed_out=bool(getattr(outcome, "timed_out", False)),
            output=outcome.output,
        )

    async def capture(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        outcome = await self.environment.run_bash(
            self.command_line(argv, env or {}, None), str(cwd), timeout
        )
        return CommandResult(
            exit_code=outcome.exit_code,
            timed_out=bool(getattr(outcome, "timed_out", False)),
            output=outcome.output,
        )


def _status(returncode: int) -> int:
    return 128 - returncode if returncode < 0 else returncode


async def _kill_group(process: asyncio.subprocess.Process) -> int:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        return await asyncio.wait_for(process.wait(), _KILL_GRACE_S)
    except TimeoutError:
        return -signal.SIGKILL
