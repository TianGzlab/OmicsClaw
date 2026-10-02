"""Advisory file locks for a module and for the project, built on ``fcntl.flock``.

The lock file keeps a one-line JSON description of its holder (host, pid,
subcommand, start time) so a refused caller can say who holds it. POSIX
only. ``flock`` is not guaranteed to exclude across network filesystems or
Docker Desktop's macOS file sharing.
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class LockBusy(RuntimeError):
    """Another process holds the lock; ``holder`` is what it wrote into the lock file."""

    def __init__(self, path: Path, holder: dict) -> None:
        self.path = path
        self.holder = holder
        who = ", ".join(f"{key} {value}" for key, value in holder.items()) or "unknown holder"
        super().__init__(f"{path} is held by another process ({who})")


def _holder(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return json.loads(text) if text else {}
    except (OSError, ValueError):
        return {}


@contextmanager
def hold(path: str | os.PathLike, *, command: str, wait: float = 0.0) -> Iterator[None]:
    """Hold an exclusive lock on *path* for the block.

    :param command: The subcommand recorded as the holder.
    :param wait: Seconds to keep retrying while another process holds it.
    :raises LockBusy: the lock is still held after *wait* seconds.
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + max(wait, 0.0)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockBusy(lock_path, _holder(lock_path)) from None
                time.sleep(0.2)
        holder = {
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "command": command,
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        os.ftruncate(fd, 0)
        os.pwrite(fd, (json.dumps(holder) + "\n").encode(), 0)
        try:
            yield
        finally:
            os.ftruncate(fd, 0)
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
