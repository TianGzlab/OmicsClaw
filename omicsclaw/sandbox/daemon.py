"""Making sure the container daemon answers before a sandbox is created."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Awaitable, Callable

from .runner import CommandRunner, CommandTimedOut, SandboxError

PROBE_INTERVAL_S = 0.5
"""Seconds between two readiness probes."""

RESTART_GRACE_S = 2.0
"""How long to keep probing when nothing was started: covers a daemon
that is restarting, and fails fast when there is no daemon at all."""

START_TIMEOUT_S = 90.0
"""How long to keep probing after a daemon was started: a desktop VM's
cold start is slow."""

_PROBE_TIMEOUT_S = 10.0

DaemonStarter = Callable[[], Awaitable[bool]]
"""Tries to start the daemon; ``True`` means a start was attempted."""


async def ensure_daemon_ready(
    runner: CommandRunner,
    *,
    start_daemon: DaemonStarter | None = None,
    probe_interval_s: float = PROBE_INTERVAL_S,
    restart_grace_s: float = RESTART_GRACE_S,
    start_timeout_s: float = START_TIMEOUT_S,
) -> None:
    """Return once ``<cli> info`` succeeds; raise :exc:`SandboxError` if it will not.

    One probe first. If it fails, *start_daemon* is awaited (default: never
    start anything) and probing continues every *probe_interval_s* until
    *start_timeout_s* if a start was attempted, else *restart_grace_s*.

    A CLI that cannot be run at all raises at once, without waiting.
    """
    first = await _probe(runner)
    if first is None:
        return

    started = await start_daemon() if start_daemon is not None else False
    limit = start_timeout_s if started else restart_grace_s
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit
    last = first
    while loop.time() < deadline:
        await asyncio.sleep(probe_interval_s)
        failure = await _probe(runner)
        if failure is None:
            return
        last = failure
    raise SandboxError(
        f"the container daemon is not available after {limit:g}s "
        f"(start attempted: {'yes' if started else 'no'}): {last}"
    )


async def _probe(runner: CommandRunner) -> str | None:
    """``None`` when the daemon answers, else why not.

    A probe that hangs counts as a failure. Any other
    :exc:`SandboxError` — the CLI is missing — propagates.
    """
    try:
        result = await runner.run(
            ["info", "--format", "{{.ServerVersion}}"],
            timeout=_PROBE_TIMEOUT_S,
        )
    except CommandTimedOut as exc:
        return str(exc)
    return None if result.ok else result.detail()


def desktop_starter(runtime: str) -> DaemonStarter | None:
    """A starter for Docker Desktop on macOS, or ``None`` elsewhere.

    Linux daemons are managed by the init system and starting one needs
    root, so nothing is attempted there.
    """
    if sys.platform != "darwin" or os.path.basename(runtime) != "docker":
        return None

    async def start() -> bool:
        try:
            process = await asyncio.create_subprocess_exec(
                "open",
                "-a",
                "Docker",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return False
        return await process.wait() == 0

    return start


__all__ = [
    "DaemonStarter",
    "PROBE_INTERVAL_S",
    "RESTART_GRACE_S",
    "START_TIMEOUT_S",
    "desktop_starter",
    "ensure_daemon_ready",
]
