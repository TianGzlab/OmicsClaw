"""One container's lifecycle: start, wait until running, stop and remove.

States move ``PENDING → RUNNING → STOPPING → TERMINATED``, or to
``FAILED`` from ``PENDING`` when the container cannot be started. A
failed start leaves nothing behind: the container is force-removed and
its exchange directory deleted before :exc:`SandboxError` is raised.
"""

from __future__ import annotations

import asyncio
import math
import os
import shutil
import socket
import tempfile
from enum import StrEnum
from pathlib import Path

from .config import SandboxConfig, SandboxConfigError, check_mount_path
from .runner import CommandRunner, CommandTimedOut, SandboxError

LABEL = "omicsclaw.sandbox"
"""Label set to ``1`` on every container this package starts."""

OWNER_LABEL = "omicsclaw.sandbox.owner"
"""Label holding ``<hostname>:<pid>`` of the process that started it."""

NAME_PREFIX = "omicsclaw-sandbox-"

EXCHANGE_DIR = Path(".omicsclaw") / "sandbox"
"""Where, under the workspace, each sandbox keeps its per-command pid and
log files. Inside the workspace so it needs no mount of its own."""

_POLL_INTERVAL_S = 0.2
_CLEANUP_TIMEOUT_S = 10.0
_MISSING_IMAGE = ("no such image", "unable to find image", "image not known")


class ContainerState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    TERMINATED = "terminated"
    FAILED = "failed"


def owner_token() -> str:
    """``<hostname>:<pid>`` of this process, for :data:`OWNER_LABEL`."""
    return f"{socket.gethostname()}:{os.getpid()}"


def run_arguments(
    config: SandboxConfig,
    *,
    sandbox_id: str,
    workspace: Path,
    owner: str,
) -> list[str]:
    """The ``run`` arguments that start one sandbox container.

    The workspace is mounted read-write and every
    :attr:`~SandboxConfig.read_only_mounts` entry read-only, each at the
    same path as on the host. The main process is ``sleep infinity``
    under ``--init``; commands arrive later through ``exec``.

    Credentials in the workspace are hidden from the container: an existing
    ``<workspace>/.env`` is covered by ``/dev/null``, and an existing
    ``<workspace>/.omicsclaw`` by an empty tmpfs, inside which the sandbox
    exchange directory (:data:`EXCHANGE_DIR`) is mounted again so commands can
    still record their pid and output.
    """
    args = [
        "run",
        "--detach",
        "--init",
        "--pull=never",
        "--name",
        f"{NAME_PREFIX}{sandbox_id}",
        "--label",
        f"{LABEL}=1",
        "--label",
        f"{OWNER_LABEL}={owner}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(config.pids_limit),
        "--network",
        config.network,
        "--tmpfs",
        f"/tmp:rw,nosuid,nodev,size={config.tmpfs_size}",
        "--env",
        "HOME=/tmp",
    ]
    if config.user is not None:
        args += ["--user", config.user]
    if config.memory:
        args += ["--memory", config.memory]
    if config.cpus:
        args += ["--cpus", config.cpus]
    if config.gpus:
        args += ["--gpus", config.gpus]
    if config.shm_size:
        args += ["--shm-size", config.shm_size]
    if config.nofile:
        args += ["--ulimit", f"nofile={config.nofile}:{config.nofile}"]
    args += ["--volume", f"{workspace}:{workspace}"]
    for mount in config.read_only_mounts:
        args += ["--volume", f"{mount}:{mount}:ro"]
    dotenv = workspace / ".env"
    if dotenv.is_file():
        args += ["--volume", f"/dev/null:{dotenv}:ro"]
    state = workspace / EXCHANGE_DIR.parts[0]
    if state.is_dir():
        exchange = workspace / EXCHANGE_DIR
        args += ["--tmpfs", f"{state}:rw,nosuid,nodev,size=1m"]
        if exchange.is_dir():
            args += ["--volume", f"{exchange}:{exchange}"]
    args += ["--workdir", str(workspace), config.image, "sleep", "infinity"]
    return args


class Container:
    """A sandbox container and the host directory it exchanges files through.

    *workspace* is resolved, so it is mounted at the path the file tools
    see. *io_dir* is a private directory under :data:`EXCHANGE_DIR` in the
    workspace, created by :meth:`start` and deleted by :meth:`stop`. Not
    safe for concurrent :meth:`start` calls.
    """

    def __init__(
        self,
        sandbox_id: str,
        workspace: Path,
        config: SandboxConfig,
        runner: CommandRunner,
        *,
        label: str = "main",
        owner: str | None = None,
    ) -> None:
        self.id = sandbox_id
        self.label = label
        self.workspace = Path(workspace).resolve()
        self.config = config
        self.state = ContainerState.PENDING
        self.docker_id = ""
        self.error = ""
        self.io_dir: Path | None = None
        self._runner = runner
        self._owner = owner if owner is not None else owner_token()

    async def start(self) -> None:
        """Run the container and wait until it reports running.

        Raises :exc:`SandboxError` — with the state set to ``FAILED`` and
        everything cleaned up — if a mount source is missing, the image is
        not present locally, the container exits, or
        :attr:`~SandboxConfig.start_timeout_s` passes first. Cancellation
        cleans up the same way and propagates.
        """
        if self.state is not ContainerState.PENDING:
            raise SandboxError(f"sandbox {self.id} was already started")
        self._check_mounts()
        self.io_dir = self._make_io_dir()
        deadline = asyncio.get_running_loop().time() + self.config.start_timeout_s
        try:
            await self._run_detached(deadline)
            await self._wait_running(deadline)
        except CommandTimedOut:
            reason = (
                f"the container did not start within "
                f"{self.config.start_timeout_s:g}s"
            )
            await self._discard(reason)
            raise SandboxError(reason) from None
        except SandboxError as exc:
            await self._discard(str(exc))
            raise
        except asyncio.CancelledError:
            await self._discard("start was cancelled")
            raise
        self.state = ContainerState.RUNNING

    async def stop(self) -> None:
        """Stop with the configured grace, then remove. Idempotent.

        Removal is attempted whether or not the stop succeeded. Failures
        are recorded in :attr:`error` rather than raised.
        """
        if self.state in (ContainerState.TERMINATED, ContainerState.FAILED):
            return
        if not self.docker_id:
            self.state = ContainerState.TERMINATED
            self._remove_io_dir()
            return
        self.state = ContainerState.STOPPING
        grace = self.config.stop_grace_s
        try:
            await self._quietly(
                ["stop", "--time", str(math.ceil(grace)), self.docker_id],
                timeout=grace + _CLEANUP_TIMEOUT_S,
            )
            removed = await self._quietly(
                ["rm", "--force", self.docker_id], timeout=_CLEANUP_TIMEOUT_S
            )
            if not removed:
                self.error = f"container {self.short_id} could not be removed"
        finally:
            self._remove_io_dir()
            self.state = ContainerState.TERMINATED

    @property
    def name(self) -> str:
        return f"{NAME_PREFIX}{self.id}"

    @property
    def short_id(self) -> str:
        return self.docker_id[:12]

    # ---- internals ------------------------------------------------------

    def _check_mounts(self) -> None:
        """Refuse mounts that do not exist or collide with the workspace.

        A missing ``-v`` source would otherwise be created, empty and
        root-owned, on the host.
        """
        workspace = self.workspace
        problem = ""
        try:
            check_mount_path(workspace)
            for mount in self.config.read_only_mounts:
                check_mount_path(mount)
        except SandboxConfigError as exc:
            problem = str(exc)
        if not problem and not workspace.is_dir():
            problem = f"workspace {workspace} is not a directory"
        for mount in self.config.read_only_mounts:
            if problem:
                break
            if not mount.exists():
                problem = f"mount source {mount} does not exist"
            elif mount == workspace:
                problem = (
                    f"mount {mount} is the workspace, which is already "
                    "mounted read-write"
                )
        if problem:
            self.state = ContainerState.FAILED
            self.error = problem
            raise SandboxError(problem)

    async def _run_detached(self, deadline: float) -> None:
        arguments = run_arguments(
            self.config,
            sandbox_id=self.id,
            workspace=self.workspace,
            owner=self._owner,
        )
        result = await self._runner.run(arguments, timeout=_remaining(deadline))
        lines = result.stdout.split()
        if result.ok and lines:
            self.docker_id = lines[-1]
            return
        detail = result.detail()
        if any(marker in detail.lower() for marker in _MISSING_IMAGE):
            detail += (
                f". Images are never pulled automatically: run "
                f"`{self.config.runtime} pull {self.config.image}` first"
            )
        raise SandboxError(f"the container could not be created: {detail}")

    async def _wait_running(self, deadline: float) -> None:
        loop = asyncio.get_running_loop()
        while True:
            result = await self._runner.run(
                [
                    "inspect",
                    "--format",
                    "{{.State.Status}} {{.State.ExitCode}}",
                    self.docker_id,
                ],
                timeout=_remaining(deadline),
            )
            status, _, code = result.stdout.strip().partition(" ")
            if result.ok and status == "running":
                return
            if result.ok and status in ("exited", "dead"):
                raise SandboxError(
                    f"the container exited with status {code or '?'} right "
                    "after starting; does the image provide `sleep`?"
                )
            if loop.time() >= deadline:
                raise CommandTimedOut("readiness wait expired")
            await asyncio.sleep(min(_POLL_INTERVAL_S, _remaining(deadline)))

    async def _discard(self, reason: str) -> None:
        """Mark failed and remove whatever was created. Never raises."""
        self.state = ContainerState.FAILED
        self.error = reason
        try:
            if self.io_dir is not None:
                # By name when the id never arrived: a ``run`` that timed out
                # may still have created the container.
                await self._quietly(
                    ["rm", "--force", self.docker_id or self.name],
                    timeout=_CLEANUP_TIMEOUT_S,
                )
        finally:
            self._remove_io_dir()

    async def _quietly(self, args: list[str], *, timeout: float) -> bool:
        """Run a cleanup command; ``True`` if it succeeded."""
        try:
            result = await self._runner.run(args, timeout=timeout)
        except SandboxError:
            return False
        return result.ok

    def _make_io_dir(self) -> Path:
        root = self.workspace / EXCHANGE_DIR
        try:
            root.mkdir(parents=True, exist_ok=True)
            return Path(tempfile.mkdtemp(prefix=f"{self.id}-", dir=root))
        except OSError as exc:
            self.state = ContainerState.FAILED
            self.error = f"cannot create {root}: {exc}"
            raise SandboxError(self.error) from exc

    def _remove_io_dir(self) -> None:
        if self.io_dir is None:
            return
        shutil.rmtree(self.io_dir, ignore_errors=True)
        try:
            self.io_dir.parent.rmdir()
        except OSError:
            pass  # other sandboxes still use it, or it is already gone


def _remaining(deadline: float) -> float:
    return max(deadline - asyncio.get_running_loop().time(), 0.001)


__all__ = [
    "Container",
    "ContainerState",
    "EXCHANGE_DIR",
    "LABEL",
    "NAME_PREFIX",
    "OWNER_LABEL",
    "owner_token",
    "run_arguments",
]
