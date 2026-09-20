"""Tool results moved out of a conversation, kept as files."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path

__all__ = ["FileOffloadStore", "safe_name"]

_VALID_KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def safe_name(text: str, *, default: str = "default") -> str:
    """*text* as a single, portable path component.

    Characters outside letters, digits, ``_``, ``.`` and ``-`` become
    ``_``; when that changed anything, a short digest of the original is
    appended so two different names never collide. Empty input, ``.``
    and ``..`` become *default*.
    """
    cleaned = _UNSAFE_NAME_CHARS.sub("_", text).strip(".")[:80]
    if not cleaned:
        return default
    if cleaned != text:
        digest = hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()
        cleaned = f"{cleaned}-{digest[:8]}"
    return cleaned


class FileOffloadStore:
    """Keeps offloaded tool results as ``<key>.txt`` under one directory.

    Satisfies :class:`omicsclaw.context.OffloadStore`. A key that is
    already on disk is not written again, so offloading the same result
    on several turns costs one write. The directory is created ``0700``
    and files ``0600``.

    :param root: Parent of the per-session directories.
    :param session_id: Which conversation the results belong to; made
        path-safe with :func:`safe_name`.
    :param reference_base: When given, references are reported relative
        to it — pass the workspace so the model can read them back with
        ``read_file``. Otherwise they are absolute paths.
    """

    def __init__(
        self,
        root: Path,
        session_id: str = "",
        *,
        reference_base: Path | None = None,
    ) -> None:
        self._directory = Path(root) / safe_name(session_id)
        self._base = reference_base
        self._written: set[str] = set()
        self._lock = threading.Lock()

    @property
    def directory(self) -> Path:
        """Where this store's files are written."""
        return self._directory

    async def put(self, key: str, content: str) -> str:
        """Write *content* to ``<key>.txt`` unless it is already there.

        :returns: The file's reference.
        :raises ValueError: *key* is not a plain file-name component.
        :raises OSError: The file could not be written.
        """
        if not _VALID_KEY.match(key):
            raise ValueError(f"not a valid offload key: {key!r}")
        path = self._directory / f"{key}.txt"
        if key not in self._written:
            await asyncio.to_thread(self._write, path, content)
            self._written.add(key)
        return self._reference(path)

    async def purge(self) -> None:
        """Delete this session's directory and everything in it."""
        await asyncio.to_thread(shutil.rmtree, self._directory, ignore_errors=True)
        self._written.clear()

    def _write(self, path: Path, content: str) -> None:
        with self._lock:
            if path.exists():
                return
            self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(
                dir=self._directory, prefix=".", suffix=".tmp"
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(content)
                os.chmod(temporary, 0o600)
                os.replace(temporary, path)
            except BaseException:
                Path(temporary).unlink(missing_ok=True)
                raise

    def _reference(self, path: Path) -> str:
        if self._base is not None:
            try:
                return path.resolve().relative_to(
                    Path(self._base).resolve()
                ).as_posix()
            except ValueError:
                pass
        return str(path.resolve())
