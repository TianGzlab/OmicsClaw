"""What one sandbox deployment decides: image, isolation and limits.

:class:`SandboxConfig` is built by the composition root and validated on
construction. Nothing in this package reads environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

NETWORK_NONE = "none"
"""The Docker network mode with no interfaces but loopback."""


class SandboxConfigError(ValueError):
    """A sandbox configuration that cannot be used, and why."""


def host_user() -> str | None:
    """``"uid:gid"`` of this process, or ``None`` where there is no such thing.

    Used as the container user so that files a command writes into the
    bind-mounted workspace belong to the person running the agent. Where
    it is ``None`` the image's own user applies, which is often root.
    """
    if not hasattr(os, "getuid"):
        return None
    return f"{os.getuid()}:{os.getgid()}"


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """How containers are started. Validated in :meth:`__post_init__`.

    Empty strings for ``memory``, ``cpus`` and ``gpus`` mean "do not pass
    the flag": no memory cap, no CPU cap, no GPU.
    """

    image: str
    """Image to run. Must already be present locally; nothing is pulled."""

    network: str = NETWORK_NONE
    """Docker network mode or network name. ``"none"`` isolates the
    container from every network; anything else lets commands reach
    whatever that network reaches."""

    memory: str = ""
    """``docker run --memory`` value, e.g. ``"32g"``."""

    cpus: str = ""
    """``docker run --cpus`` value, e.g. ``"8"``."""

    gpus: str = ""
    """``docker run --gpus`` value, e.g. ``"all"``. Needs the NVIDIA
    container toolkit on the host."""

    pids_limit: int = 65536
    """Ceiling on processes **and threads** inside the container. Threads of
    every BLAS, OpenMP, torch and numba pool count, so concurrent analyses need
    tens of thousands."""

    user: str | None = field(default_factory=host_user)
    """``--user`` value. ``None`` keeps the image's default user."""

    read_only_mounts: tuple[Path, ...] = ()
    """Host directories mounted read-only at the same path."""

    tmpfs_size: str = "64g"
    """Size of the tmpfs mounted at ``/tmp``. A tmpfs takes memory only for
    what is written to it, and counts against :attr:`memory`."""

    shm_size: str = "128g"
    """``--shm-size`` for ``/dev/shm``; empty keeps the runtime's default
    (64 MiB for Docker). PyTorch data loaders and joblib memory-map through it."""

    nofile: int = 65536
    """``--ulimit nofile`` soft and hard limit; ``0`` keeps the image's."""

    bootstrap: str = ""
    """Command run once in the workspace after the container is ready.
    Empty means none."""

    bootstrap_timeout_s: float = 600.0
    """Budget for :attr:`bootstrap`, separate from any tool timeout."""

    start_timeout_s: float = 60.0
    """How long ``docker run`` plus the readiness wait may take."""

    stop_grace_s: float = 5.0
    """Seconds between SIGTERM and SIGKILL when a container is stopped."""

    runtime: str = "docker"
    """The container CLI to invoke: a name on ``PATH`` or a path. Any CLI
    that accepts Docker's arguments works (``podman`` does)."""

    def __post_init__(self) -> None:
        """Refuse values that would fail later or change the command line.

        Raises :exc:`SandboxConfigError` naming the first bad field.
        """
        _require_token("image", self.image)
        _require_token("network", self.network)
        if not self.runtime.strip():
            raise SandboxConfigError("runtime must not be empty")
        for name in ("memory", "cpus", "gpus", "tmpfs_size", "shm_size"):
            value = getattr(self, name)
            if value:
                _require_token(name, value)
        if self.user is not None:
            _require_token("user", self.user)
        if self.pids_limit < 1:
            raise SandboxConfigError(
                f"pids_limit must be at least 1; got {self.pids_limit}"
            )
        if self.nofile < 0:
            raise SandboxConfigError(f"nofile must not be negative; got {self.nofile}")
        for name in ("bootstrap_timeout_s", "start_timeout_s"):
            if getattr(self, name) <= 0:
                raise SandboxConfigError(f"{name} must be positive")
        if self.stop_grace_s < 0:
            raise SandboxConfigError("stop_grace_s must not be negative")
        mounts = tuple(Path(mount) for mount in self.read_only_mounts)
        for mount in mounts:
            check_mount_path(mount)
        object.__setattr__(self, "read_only_mounts", mounts)

    @property
    def isolates_network(self) -> bool:
        """``True`` when commands cannot reach any network."""
        return self.network == NETWORK_NONE


def check_mount_path(path: Path) -> None:
    """Raise :exc:`SandboxConfigError` unless *path* can be a ``-v`` source.

    The path must be absolute and free of ``:``, which ``docker run -v``
    uses as its field separator.
    """
    if not path.is_absolute():
        raise SandboxConfigError(f"mount {str(path)!r} must be an absolute path")
    if ":" in str(path):
        raise SandboxConfigError(
            f"mount {str(path)!r} contains ':', which docker -v cannot express"
        )


def _require_token(name: str, value: str) -> None:
    """A non-empty value that cannot be read as an option or split in two."""
    if not value or not value.strip():
        raise SandboxConfigError(f"{name} must not be empty")
    if value.startswith("-"):
        raise SandboxConfigError(
            f"{name} {value!r} starts with '-', which the container CLI "
            "would read as an option"
        )
    if any(char.isspace() for char in value):
        raise SandboxConfigError(f"{name} {value!r} must not contain whitespace")


__all__ = [
    "NETWORK_NONE",
    "SandboxConfig",
    "SandboxConfigError",
    "check_mount_path",
    "host_user",
]
