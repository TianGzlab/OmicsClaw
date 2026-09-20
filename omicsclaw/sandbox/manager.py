"""Every live sandbox of one process: create, list, destroy, reap.

The manager reports through return values, :class:`SandboxInfo`
snapshots and an optional change listener. It never logs.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import SandboxConfig
from .container import LABEL, OWNER_LABEL, Container, ContainerState, owner_token
from .daemon import DaemonStarter, desktop_starter, ensure_daemon_ready
from .environment import DockerEnvironment
from .runner import CommandRunner, SandboxError, SubprocessRunner

_LIST_TIMEOUT_S = 30.0


@dataclass(frozen=True, slots=True)
class BootstrapOutcome:
    """How the configured bootstrap command ended."""

    exit_code: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(frozen=True, slots=True)
class SandboxInfo:
    """A read-only snapshot of one sandbox."""

    id: str
    label: str
    state: ContainerState
    image: str
    workspace: Path
    docker_id: str = ""
    """First 12 characters of the container id; empty before ``run``."""

    error: str = ""
    bootstrap: BootstrapOutcome | None = None
    """``None`` when no bootstrap command is configured."""


@dataclass(frozen=True, slots=True)
class ReapReport:
    """What :meth:`SandboxManager.reap_orphans` did."""

    removed: tuple[str, ...] = ()
    """Short ids of orphaned containers that were removed."""

    failed: tuple[str, ...] = ()
    """Short ids of orphaned containers that could not be removed."""

    kept: int = 0
    """Labelled containers left alone: live owner, other host, or ours."""


ChangeListener = Callable[[tuple[SandboxInfo, ...]], None]
"""Called with a fresh :meth:`SandboxManager.list_all` after every change.
Exceptions it raises are ignored."""


class SandboxManager:
    """Creates sandboxes from one :class:`SandboxConfig` and tracks them.

    Each :meth:`create` starts one container for one agent; a sub-agent
    gets its own with a different *label*. :meth:`aclose` removes them
    all. Safe to use from one event loop; not thread-safe.
    """

    def __init__(
        self,
        config: SandboxConfig,
        *,
        runner: CommandRunner | None = None,
        on_change: ChangeListener | None = None,
        start_daemon: DaemonStarter | None = None,
    ) -> None:
        """*runner* defaults to :class:`SubprocessRunner` over
        :attr:`SandboxConfig.runtime`; *start_daemon* defaults to Docker
        Desktop on macOS and nothing elsewhere."""
        self.config = config
        self._runner = runner if runner is not None else SubprocessRunner(
            config.runtime
        )
        self._on_change = on_change
        if start_daemon is None:
            start_daemon = desktop_starter(config.runtime)
        self._start_daemon = start_daemon
        self._owner = owner_token()
        self._containers: dict[str, Container] = {}
        self._bootstraps: dict[str, BootstrapOutcome] = {}

    async def create(
        self,
        workspace: Path,
        *,
        label: str = "main",
    ) -> DockerEnvironment:
        """Start a sandbox over *workspace* and return where to run commands.

        The configured bootstrap command, if any, runs once before this
        returns; its failure is recorded in :class:`SandboxInfo` and does
        not fail creation. Raises :exc:`SandboxError` if the container
        cannot be started, leaving nothing behind.
        """
        sandbox_id = secrets.token_hex(8)
        container = Container(
            sandbox_id,
            workspace,
            self.config,
            self._runner,
            label=label,
            owner=self._owner,
        )
        self._containers[sandbox_id] = container
        self._notify()
        ready = False
        try:
            await container.start()
            assert container.io_dir is not None
            environment = DockerEnvironment(
                sandbox_id=sandbox_id,
                container_id=container.docker_id,
                io_dir=container.io_dir,
                runner=self._runner,
            )
            if self.config.bootstrap.strip():
                result = await environment.run_bash(
                    self.config.bootstrap,
                    str(container.workspace),
                    self.config.bootstrap_timeout_s,
                )
                self._bootstraps[sandbox_id] = BootstrapOutcome(
                    exit_code=result.exit_code, timed_out=result.timed_out
                )
            ready = True
        finally:
            if not ready:
                self._containers.pop(sandbox_id, None)
                await container.stop()
            self._notify()
        return environment

    async def create_with_retry(
        self,
        workspace: Path,
        *,
        label: str = "main",
    ) -> DockerEnvironment:
        """:meth:`create`, after making sure the daemon answers, retried once.

        Raises :exc:`SandboxError` naming both failures when the retry
        fails too, or at once when the daemon never becomes available.
        """
        await ensure_daemon_ready(self._runner, start_daemon=self._start_daemon)
        try:
            return await self.create(workspace, label=label)
        except SandboxError as first:
            try:
                return await self.create(workspace, label=label)
            except SandboxError as second:
                raise SandboxError(
                    f"{second} (first attempt: {first})"
                ) from second

    async def destroy(self, sandbox_id: str) -> None:
        """Stop and remove one sandbox. Unknown ids are ignored."""
        container = self._containers.pop(sandbox_id, None)
        if container is None:
            return
        try:
            await container.stop()
        finally:
            self._bootstraps.pop(sandbox_id, None)
            self._notify()

    async def aclose(self) -> None:
        """Stop and remove every sandbox, concurrently."""
        containers = list(self._containers.values())
        self._containers.clear()
        self._bootstraps.clear()
        try:
            await asyncio.gather(*(container.stop() for container in containers))
        finally:
            if containers:
                self._notify()

    async def reap_orphans(self) -> ReapReport:
        """Remove labelled containers whose owning process has died.

        Only containers labelled with this host's name and the PID of a
        process that no longer exists are removed. Containers of live
        processes, of other hosts, of this process, or without a readable
        owner are kept.

        Raises :exc:`SandboxError` if the containers cannot be listed.
        """
        listed = await self._runner.run(
            ["ps", "--all", "--quiet", "--filter", f"label={LABEL}=1"],
            timeout=_LIST_TIMEOUT_S,
        )
        if not listed.ok:
            raise SandboxError(f"cannot list sandbox containers: {listed.detail()}")
        removed: list[str] = []
        failed: list[str] = []
        kept = 0
        for short_id in dict.fromkeys(listed.stdout.split()):
            if not await self._is_orphan(short_id):
                kept += 1
                continue
            try:
                result = await self._runner.run(
                    ["rm", "--force", short_id], timeout=_LIST_TIMEOUT_S
                )
            except SandboxError:
                failed.append(short_id[:12])
                continue
            (removed if result.ok else failed).append(short_id[:12])
        return ReapReport(removed=tuple(removed), failed=tuple(failed), kept=kept)

    def list_all(self) -> tuple[SandboxInfo, ...]:
        """Snapshots of every sandbox being started or running."""
        return tuple(self._info(container) for container in self._containers.values())

    def info(self, sandbox_id: str) -> SandboxInfo | None:
        container = self._containers.get(sandbox_id)
        return None if container is None else self._info(container)

    # ---- internals ------------------------------------------------------

    def _info(self, container: Container) -> SandboxInfo:
        return SandboxInfo(
            id=container.id,
            label=container.label,
            state=container.state,
            image=self.config.image,
            workspace=container.workspace,
            docker_id=container.short_id,
            error=container.error,
            bootstrap=self._bootstraps.get(container.id),
        )

    async def _is_orphan(self, container_id: str) -> bool:
        """``True`` only when the owner label names a dead local process."""
        try:
            result = await self._runner.run(
                [
                    "inspect",
                    "--format",
                    f'{{{{index .Config.Labels "{OWNER_LABEL}"}}}}',
                    container_id,
                ],
                timeout=_LIST_TIMEOUT_S,
            )
        except SandboxError:
            return False
        return result.ok and owner_is_dead(result.stdout.strip())

    def _notify(self) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(self.list_all())
        except Exception:
            pass


def owner_is_dead(owner: str) -> bool:
    """Is *owner* (``<hostname>:<pid>``) a process on this host that has exited?

    Anything that cannot be proved dead — another host, this process, a
    live or inaccessible PID, a malformed value — answers ``False``.
    """
    host, _, raw_pid = owner.rpartition(":")
    if sys.platform == "win32":
        return False  # os.kill(pid, 0) sends CTRL_C_EVENT there.
    if host != socket.gethostname() or not raw_pid.isdigit():
        return False
    pid = int(raw_pid)
    if pid == os.getpid() or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


__all__ = [
    "BootstrapOutcome",
    "ChangeListener",
    "ReapReport",
    "SandboxInfo",
    "SandboxManager",
    "owner_is_dead",
]
