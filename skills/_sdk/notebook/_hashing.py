"""SHA-256 digests of files and directories."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

_CHUNK = 1 << 20
_SKIPPED_DIRS = {"__pycache__", ".ipynb_checkpoints"}


def sha256_file(path: str | os.PathLike) -> str:
    """The hex SHA-256 of one file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_files(path: str | os.PathLike) -> list[Path]:
    """Every file under *path*, sorted, skipping caches and dot-directories."""
    base = Path(path)
    found: list[Path] = []
    for current, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in _SKIPPED_DIRS and not d.startswith("."))
        found.extend(Path(current) / name for name in files)
    return sorted(found, key=lambda p: p.relative_to(base).as_posix())


def sha256_path(path: str | os.PathLike) -> str:
    """The SHA-256 of a file, or of a directory's sorted ``relative path, file hash`` list."""
    target = Path(path)
    if not target.is_dir():
        return sha256_file(target)
    digest = hashlib.sha256()
    for file in directory_files(target):
        digest.update(f"{file.relative_to(target).as_posix()}\0{sha256_file(file)}\n".encode())
    return digest.hexdigest()


def size_of(path: str | os.PathLike) -> int:
    """The size in bytes of a file, or the total size of a directory's files."""
    target = Path(path)
    if not target.is_dir():
        return target.stat().st_size
    return sum(file.stat().st_size for file in directory_files(target))
