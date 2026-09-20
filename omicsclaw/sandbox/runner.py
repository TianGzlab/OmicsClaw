"""Invoking the container CLI: one Protocol, one subprocess implementation.

Every ``docker`` call in this package goes through a :class:`CommandRunner`,
so tests can substitute a scripted one and a deployment can point
:class:`SubprocessRunner` at ``podman``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable


class SandboxError(OSError):
    """The sandbox could not do what was asked of it.

    An :exc:`OSError` because every cause is outside the caller's
    arguments: no container CLI, no daemon, a container that stopped.
    """


class CommandTimedOut(SandboxError):
    """A CLI invocation ran past its timeout and was killed."""


@dataclass(frozen=True, slots=True)
class Completed:
    """One finished CLI invocation."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def detail(self) -> str:
        """The most useful single line for an error message."""
        text = (self.stderr.strip() or self.stdout.strip()).splitlines()
        return text[-1] if text else f"exit status {self.returncode}"


@runtime_checkable
class CommandRunner(Protocol):
    """Runs the container CLI with *args* and reports how it ended."""

    async def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> Completed:
        """Run ``<cli> *args``.

        A non-zero exit is a :class:`Completed`, not an exception. Raises
        :exc:`SandboxError` if the CLI cannot be started, and
        :exc:`CommandTimedOut` if *timeout* seconds pass first; in both
        cases no process is left running. Cancellation kills the CLI
        process and propagates.
        """
        ...


class SubprocessRunner:
    """:class:`CommandRunner` over :mod:`asyncio.subprocess`.

    Standard input is ``/dev/null``; standard output and error are
    captured separately and decoded as UTF-8 with replacement.
    """

    def __init__(self, binary: str = "docker") -> None:
        self.binary = binary

    async def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> Completed:
        try:
            process = await asyncio.create_subprocess_exec(
                self.binary,
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise SandboxError(
                f"cannot run {self.binary!r}: {exc.strerror or exc}. Is the "
                "container runtime installed and on PATH?"
            ) from exc

        try:
            async with asyncio.timeout(timeout):
                stdout, stderr = await process.communicate()
        except TimeoutError:
            await _reap(process)
            raise CommandTimedOut(
                f"{self.binary} {args[0] if args else ''} did not finish "
                f"within {timeout:g}s"
            ) from None
        except asyncio.CancelledError:
            _kill(process)
            raise
        return Completed(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )


def _kill(process: asyncio.subprocess.Process) -> None:
    try:
        process.kill()
    except ProcessLookupError:
        pass


async def _reap(process: asyncio.subprocess.Process) -> None:
    _kill(process)
    await process.wait()


__all__ = [
    "CommandRunner",
    "CommandTimedOut",
    "Completed",
    "SandboxError",
    "SubprocessRunner",
]
