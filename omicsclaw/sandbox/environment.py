"""Running a shell command inside a started sandbox container.

:class:`DockerEnvironment` has the ``run_bash(command, cwd, timeout)``
method the ``bash`` tool routes through when one is injected. File tools
are not routed: the workspace is bind-mounted at the same path, so the
host view and the container view of it are the same bytes. Each
command's pid and log files live in the sandbox's exchange directory
inside that workspace.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Coroutine

from .runner import CommandRunner, SandboxError

WRAPPER = 'echo "$$" > "$0" && exec bash -c "$1" > "$2" 2>&1 < /dev/null'
"""The script ``docker exec`` runs: ``$0`` pid file, ``$1`` command, ``$2`` log.

It records its own PID and then *becomes* the command, so the recorded
PID is the command's. Output goes to a file rather than to ``exec``'s
own stdio, so a process the command backgrounds cannot keep
``docker exec`` waiting.
"""

KILL = 'kill -KILL "$0" 2>/dev/null || true'
"""Kills the PID in ``$0``. A bash builtin, so no ``kill`` binary is needed."""

OWN_DEADLINE_GRACE_S = 5.0
"""Seconds past ``timeout`` before :meth:`DockerEnvironment.run_bash` stops
the command itself. A caller with its own deadline at ``timeout`` sees
that deadline fire first."""

PID_WAIT_S = 2.0
"""How long a kill waits for a just-started command to record its PID."""

KILL_TIMEOUT_S = 10.0

TIMED_OUT_EXIT = 137
"""Exit status reported for a command stopped by the deadline (SIGKILL)."""

_background: set[asyncio.Task[None]] = set()


@dataclass(frozen=True, slots=True)
class ExecResult:
    """How one command ended.

    Has the ``output`` and ``exit_code`` fields the ``bash`` tool reads.
    """

    output: str
    """stdout and stderr merged, in the order they were written."""

    exit_code: int
    """Shell convention: ``0`` for success, ``128 + signum`` for a signal."""

    timed_out: bool = False
    """``True`` when this environment's own deadline stopped the command."""


class DockerEnvironment:
    """Where ``bash`` commands run once a sandbox container is up.

    Created by :class:`~omicsclaw.sandbox.manager.SandboxManager`, which
    also owns the container's lifecycle; this object holds no resources
    of its own.
    """

    def __init__(
        self,
        *,
        sandbox_id: str,
        container_id: str,
        io_dir: Path,
        runner: CommandRunner,
    ) -> None:
        self._id = sandbox_id
        self._container_id = container_id
        self._io_dir = Path(io_dir)
        self._runner = runner

    @property
    def id(self) -> str:
        """The sandbox id (not the container id)."""
        return self._id

    @property
    def container_id(self) -> str:
        return self._container_id

    async def run_bash(self, command: str, cwd: str, timeout: float) -> ExecResult:
        """Run ``bash -c command`` in the container, with *cwd* as its directory.

        *cwd* must exist inside the container; the workspace does, at its
        host path. A non-zero exit is a result, not an exception.

        If *timeout* plus :data:`OWN_DEADLINE_GRACE_S` passes, the command
        is killed and the result has ``timed_out=True`` and whatever it had
        printed. If the caller is cancelled first, the command is killed
        inside the container before the cancellation propagates.

        Raises :exc:`SandboxError` when the command could not be started at
        all — the container is gone, the daemon is unreachable, or the
        image has no ``bash``.
        """
        token = secrets.token_hex(8)
        pid_file = self._io_dir / f"{token}.pid"
        log_file = self._io_dir / f"{token}.log"
        try:
            _create_private(pid_file)
            _create_private(log_file)
        except OSError as exc:
            _unlink(pid_file, log_file)
            raise SandboxError(
                f"the sandbox is not available (was it stopped?): {exc}"
            ) from exc
        args = [
            "exec",
            "--workdir",
            cwd,
            self._container_id,
            "bash",
            "-c",
            WRAPPER,
            str(pid_file),
            command,
            str(log_file),
        ]
        owns_files = True
        try:
            budget = asyncio.timeout(timeout + OWN_DEADLINE_GRACE_S)
            try:
                async with budget:
                    completed = await self._runner.run(args)
            except TimeoutError:
                if not budget.expired():
                    raise
                await self._kill(pid_file)
                return ExecResult(
                    output=_read_text(log_file),
                    exit_code=TIMED_OUT_EXIT,
                    timed_out=True,
                )
            except asyncio.CancelledError:
                owns_files = False
                await _shielded(self._abandon(pid_file, log_file))
                raise
            if not _read_text(pid_file).strip() and not completed.ok:
                raise SandboxError(
                    f"the sandbox could not start the command: {completed.detail()}"
                )
            return ExecResult(
                output=_read_text(log_file),
                exit_code=completed.returncode,
            )
        finally:
            if owns_files:
                _unlink(pid_file, log_file)

    async def _abandon(self, pid_file: Path, log_file: Path) -> None:
        """Kill the command and remove its files, for a cancelled caller."""
        try:
            await self._kill(pid_file)
        finally:
            _unlink(pid_file, log_file)

    async def _kill(self, pid_file: Path) -> None:
        """SIGKILL the command's process inside the container. Best effort.

        The ``docker exec`` client has already been killed by then; that
        does not stop the process it started, which is why this exists.
        """
        pid = await _wait_for_pid(pid_file)
        if not pid:
            return
        try:
            await self._runner.run(
                ["exec", self._container_id, "bash", "-c", KILL, pid],
                timeout=KILL_TIMEOUT_S,
            )
        except SandboxError:
            pass


async def _shielded(work: Coroutine[Any, Any, None]) -> None:
    """Await *work* to completion even if the caller is cancelled again.

    A second cancellation stops the waiting, not the work, which keeps
    running as a background task.
    """
    task = asyncio.ensure_future(work)
    _background.add(task)
    task.add_done_callback(_background.discard)
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        # Only ever called while a first cancellation is being handled, and
        # the caller re-raises that one; a second adds nothing to act on.
        pass


async def _wait_for_pid(pid_file: Path) -> str:
    """The PID the wrapper recorded, waiting briefly if it has not yet."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PID_WAIT_S
    while True:
        pid = _read_text(pid_file).strip()
        if pid.isdigit() or loop.time() >= deadline:
            return pid if pid.isdigit() else ""
        await asyncio.sleep(0.05)


def _create_private(path: Path) -> None:
    os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))


def _read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _unlink(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass


__all__ = [
    "DockerEnvironment",
    "ExecResult",
    "KILL",
    "OWN_DEADLINE_GRACE_S",
    "TIMED_OUT_EXIT",
    "WRAPPER",
]
