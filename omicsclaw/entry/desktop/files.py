"""``GET /files/tree`` and ``GET /files/serve``: read-only views of the workspace.

Both routes take a ``path`` that is absolute or relative to the workspace
and answer only for what lies inside it. ``~`` is not expanded, and
``..`` is collapsed on the spelling before any symlink is followed.

* A path outside the workspace, as written or once its symlinks are
  followed, is refused with 403 ``path_outside_workspace``.
* A path with a segment below the workspace that starts with ``.``, as
  written or once its symlinks are followed, is refused with 403
  ``hidden_path``. The directories above the workspace do not count.
* A missing path is 404 ``file_not_found`` or ``directory_not_found``; a
  path through a directory the backend may not search, or a file it may
  not read, is 403 ``permission_denied``; a path with a NUL or one that
  cannot be resolved is 422 ``invalid_path``.

The tree payload::

    {"root": "/ws/data", "truncated": false,
     "tree": [{"name": "fig", "path": "/ws/data/fig", "type": "directory",
               "children": []},
              {"name": "a.csv", "path": "/ws/data/a.csv", "type": "file",
               "size": 12, "extension": "csv"}]}

``root`` and every ``path`` are the requested directory joined with the
entry names as written, so the entries under a symlinked directory keep
the link's name. Directories come first, then names in case-insensitive
order. ``extension`` has no dot and is absent when the name has none. A
directory at the depth limit, or whose listing cannot be read, has
``children: []``. Hidden entries, entries whose real path is outside the
workspace or hidden, broken links, and the directories in
:data:`IGNORED_DIRECTORIES` are left out, and so is a directory link back
to one of its own ancestors. The walk is breadth-first and stops after
:data:`FILES_TREE_MAX_NODES` nodes with ``truncated: true``.

A served file is sent whole when it is at most
:data:`FILES_SERVE_MAX_BYTES`; a larger one needs a ``Range`` request.
See :func:`byte_span` for the ``Range`` rules and :func:`served_media_type`
for the ``Content-Type``.
"""

from __future__ import annotations

import asyncio
import io
import mimetypes
import os
import re
import stat
import urllib.parse
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Final

from .turn_submission import DesktopIngressError

__all__ = [
    "FILES_SERVE_CHUNK_BYTES",
    "FILES_SERVE_MAX_BYTES",
    "FILES_TREE_DEFAULT_DEPTH",
    "FILES_TREE_MAX_DEPTH",
    "FILES_TREE_MAX_NODES",
    "IGNORED_DIRECTORIES",
    "ByteSpan",
    "OpenedFile",
    "ServeTarget",
    "WorkspacePath",
    "byte_span",
    "content_disposition",
    "file_chunks",
    "file_tree",
    "open_served_file",
    "resolve_in_workspace",
    "serve_target",
    "served_media_type",
    "tree_depth",
]

FILES_SERVE_MAX_BYTES: Final = 64 * 1024 * 1024
"""Most bytes one ``/files/serve`` response carries."""

FILES_SERVE_CHUNK_BYTES: Final = 256 * 1024
"""Bytes read from the file per chunk of a ``/files/serve`` body."""

FILES_TREE_MAX_NODES: Final = 10_000
"""Most nodes one ``/files/tree`` response lists."""

FILES_TREE_DEFAULT_DEPTH: Final = 3
FILES_TREE_MAX_DEPTH: Final = 10

IGNORED_DIRECTORIES: Final = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        ".next",
        "__pycache__",
        ".cache",
        ".turbo",
        "coverage",
        ".output",
        "build",
    }
)
"""Directory names ``/files/tree`` leaves out, the same list the desktop
client uses for a local tree."""

_PLAIN_TEXT: Final = "text/plain; charset=utf-8"
_BINARY: Final = "application/octet-stream"
_SCRIPT_TYPES: Final = frozenset(
    {
        "text/html",
        "text/javascript",
        "text/ecmascript",
        "application/javascript",
        "application/x-javascript",
        "application/ecmascript",
    }
)
_SVG: Final = "image/svg+xml"

_OPEN_FLAGS: Final = (
    os.O_RDONLY
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_BINARY", 0)
)

_RANGE: Final = re.compile(
    r"\s*bytes\s*=\s*(\d{0,19})\s*-\s*(\d{0,19})\s*", re.IGNORECASE | re.ASCII
)


@dataclass(frozen=True, slots=True)
class WorkspacePath:
    """A requested path that lies inside the workspace."""

    lexical: Path
    """Absolute and normalised, with its symlinks not followed."""
    real: Path
    """The same path with every symlink followed."""
    root: Path
    """The workspace's real path."""


def resolve_in_workspace(
    workspace: Path | str, raw: str, *, directory: bool
) -> WorkspacePath:
    """Resolve *raw* against *workspace* and check that it may be read.

    *raw* is absolute or relative to the workspace. *directory* says which
    kind of entry the caller needs.

    :raises DesktopIngressError: 422 ``path_required`` for an empty *raw*;
        422 ``invalid_path`` for a NUL or a path that cannot be resolved;
        403 ``path_outside_workspace``; 403 ``hidden_path``; 403
        ``permission_denied`` for a directory on the way that the backend
        may not search; 404 ``directory_not_found`` or ``file_not_found``;
        422 ``not_a_directory`` or ``not_a_file``.
    """
    missing = "directory_not_found" if directory else "file_not_found"
    if not raw:
        raise DesktopIngressError("path_required")
    if "\x00" in raw:
        raise DesktopIngressError("invalid_path")
    try:
        root = Path(workspace).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DesktopIngressError(missing, status_code=404) from exc

    spelled_root = Path(os.path.abspath(workspace))
    lexical = Path(os.path.normpath(os.path.join(spelled_root, raw)))
    _check_segments(_segments_below(lexical, (spelled_root, root)))

    try:
        real = lexical.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise DesktopIngressError(missing, status_code=404) from exc
    except PermissionError as exc:
        raise DesktopIngressError("permission_denied", status_code=403) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise DesktopIngressError("invalid_path") from exc
    _check_segments(_segments_below(real, (root,)))

    if directory and not real.is_dir():
        raise DesktopIngressError("not_a_directory")
    if not directory and not real.is_file():
        raise DesktopIngressError("not_a_file")
    return WorkspacePath(lexical=lexical, real=real, root=root)


def _segments_below(path: Path, roots: tuple[Path, ...]) -> tuple[str, ...] | None:
    """The segments of *path* below the first of *roots* it is under."""
    for root in roots:
        try:
            return path.relative_to(root).parts
        except ValueError:
            continue
    return None


def _check_segments(segments: tuple[str, ...] | None) -> None:
    if segments is None:
        raise DesktopIngressError("path_outside_workspace", status_code=403)
    if any(segment.startswith(".") for segment in segments):
        raise DesktopIngressError("hidden_path", status_code=403)


def _visible_inside(real: Path, root: Path) -> bool:
    segments = _segments_below(real, (root,))
    return segments is not None and not any(s.startswith(".") for s in segments)


# ---- the tree ---------------------------------------------------------------


def tree_depth(raw: str | None) -> int:
    """Read the ``depth`` query parameter: 1 to 10, 3 when absent.

    :raises DesktopIngressError: 422 ``invalid_depth``.
    """
    if raw is None or not raw.strip():
        return FILES_TREE_DEFAULT_DEPTH
    try:
        depth = int(raw.strip())
    except ValueError as exc:
        raise DesktopIngressError("invalid_depth") from exc
    if not 1 <= depth <= FILES_TREE_MAX_DEPTH:
        raise DesktopIngressError("invalid_depth")
    return depth


@dataclass(frozen=True, slots=True)
class _Entry:
    name: str
    real: Path
    is_dir: bool
    size: int


def file_tree(
    workspace: Path | str,
    raw: str | None = None,
    *,
    depth: int = FILES_TREE_DEFAULT_DEPTH,
    max_nodes: int = FILES_TREE_MAX_NODES,
) -> dict[str, Any]:
    """What ``GET /files/tree`` answers for the directory *raw*.

    *raw* ``None`` or empty lists the workspace. *depth* 1 lists the
    directory's own entries.

    A symlinked directory is left out when it points back to one of its
    own ancestors in the walk; a link to any other directory is listed
    with its children under the link's name. The same directory can
    therefore appear more than once, still bounded by *depth* and
    *max_nodes*.

    :raises DesktopIngressError: as :func:`resolve_in_workspace`, and 422
        ``invalid_depth`` for a *depth* outside 1 to 10.
    """
    if not 1 <= depth <= FILES_TREE_MAX_DEPTH:
        raise DesktopIngressError("invalid_depth")
    base = resolve_in_workspace(workspace, raw or ".", directory=True)

    tree: list[dict[str, Any]] = []
    pending = deque([(tree, base.lexical, base.real, frozenset({base.real}), depth)])
    listed = 0
    truncated = False
    while pending and not truncated:
        nodes, spelled_dir, real_dir, ancestors, remaining = pending.popleft()
        for entry in _entries(real_dir, base.root):
            if entry.is_dir and entry.real in ancestors:
                continue
            if listed >= max_nodes:
                truncated = True
                break
            listed += 1
            spelled = spelled_dir / entry.name
            if entry.is_dir:
                children: list[dict[str, Any]] = []
                nodes.append(
                    {
                        "name": entry.name,
                        "path": str(spelled),
                        "type": "directory",
                        "children": children,
                    }
                )
                if remaining > 1:
                    pending.append(
                        (
                            children,
                            spelled,
                            entry.real,
                            ancestors | {entry.real},
                            remaining - 1,
                        )
                    )
            else:
                node: dict[str, Any] = {
                    "name": entry.name,
                    "path": str(spelled),
                    "type": "file",
                    "size": entry.size,
                }
                extension = os.path.splitext(entry.name)[1][1:]
                if extension:
                    node["extension"] = extension
                nodes.append(node)
    return {"root": str(base.lexical), "tree": tree, "truncated": truncated}


def _entries(real_dir: Path, root: Path) -> list[_Entry]:
    """The listable entries of *real_dir*, sorted; ``[]`` if unreadable."""
    found: list[_Entry] = []
    try:
        with os.scandir(real_dir) as scan:
            for item in scan:
                entry = _entry(item, real_dir, root)
                if entry is not None:
                    found.append(entry)
    except OSError:
        return []
    found.sort(key=lambda e: (not e.is_dir, e.name.casefold(), e.name))
    return found


def _entry(item: os.DirEntry[str], real_dir: Path, root: Path) -> _Entry | None:
    name = item.name
    if name.startswith("."):
        return None
    try:
        if item.is_symlink():
            real = Path(item.path).resolve(strict=True)
            if not _visible_inside(real, root):
                return None
            info = real.stat()
        else:
            real = real_dir / name
            info = item.stat(follow_symlinks=False)
    except (OSError, RuntimeError):
        return None
    if stat.S_ISDIR(info.st_mode):
        if name in IGNORED_DIRECTORIES:
            return None
        return _Entry(name=name, real=real, is_dir=True, size=0)
    if stat.S_ISREG(info.st_mode):
        return _Entry(name=name, real=real, is_dir=False, size=info.st_size)
    return None


# ---- one file ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ServeTarget:
    """The file a ``/files/serve`` request names."""

    path: Path
    """Its real path, which is what is opened."""
    name: str
    """Its name as requested, for ``Content-Disposition``."""
    media_type: str


def serve_target(workspace: Path | str, raw: str) -> ServeTarget:
    """Resolve the ``path`` of a ``/files/serve`` request.

    :raises DesktopIngressError: as :func:`resolve_in_workspace`.
    """
    found = resolve_in_workspace(workspace, raw, directory=False)
    name = found.lexical.name
    return ServeTarget(path=found.real, name=name, media_type=served_media_type(name))


def served_media_type(name: str) -> str:
    """The ``Content-Type`` a file called *name* is served with.

    The type is guessed from the name. HTML, JavaScript and every XML type
    except SVG are sent as ``text/plain; charset=utf-8``, so a browser
    shows them instead of running them. A guess that carries an encoding,
    such as ``.svgz``, and a name with no guess are sent as
    ``application/octet-stream``.
    """
    guessed, encoding = mimetypes.guess_type(name)
    if guessed is None or encoding is not None:
        return _BINARY
    guessed = guessed.lower()
    if guessed == _SVG:
        return guessed
    if guessed in _SCRIPT_TYPES or guessed.endswith(("/xml", "+xml")):
        return _PLAIN_TEXT
    return guessed


def content_disposition(name: str) -> str:
    """An ``inline`` ``Content-Disposition`` carrying *name*, UTF-8 safe."""
    quoted = urllib.parse.quote(name)
    if quoted == name:
        return f'inline; filename="{name}"'
    return f"inline; filename*=utf-8''{quoted}"


@dataclass(frozen=True, slots=True)
class OpenedFile:
    """A regular file opened for reading, and its size at opening."""

    handle: io.FileIO
    size: int

    def close(self) -> None:
        self.handle.close()


def open_served_file(path: Path | str) -> OpenedFile:
    """Open *path* read-only and check that the open handle is a regular file.

    The open neither follows a symlink in the last component nor waits on
    a FIFO, so a path swapped after :func:`serve_target` checked it fails
    here instead of blocking. It blocks on disk I/O, so an event loop calls
    it in a thread.

    :raises DesktopIngressError: 404 ``file_not_found``; 403
        ``permission_denied``; 422 ``not_a_file`` for anything that is not
        a regular file, including a symlink.
    """
    try:
        fd = os.open(path, _OPEN_FLAGS)
    except FileNotFoundError as exc:
        raise DesktopIngressError("file_not_found", status_code=404) from exc
    except PermissionError as exc:
        raise DesktopIngressError("permission_denied", status_code=403) from exc
    except OSError as exc:
        raise DesktopIngressError("not_a_file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise DesktopIngressError("not_a_file")
        handle = io.FileIO(fd, "rb", closefd=True)
    except BaseException:
        os.close(fd)
        raise
    return OpenedFile(handle=handle, size=info.st_size)


@dataclass(frozen=True, slots=True)
class ByteSpan:
    """The bytes ``[start, stop)`` of a file of *size* bytes to send."""

    start: int
    stop: int
    size: int
    partial: bool
    """Whether this answers a ``Range`` request (206) or not (200)."""

    @property
    def length(self) -> int:
        return self.stop - self.start

    @property
    def status(self) -> int:
        return 206 if self.partial else 200

    @property
    def content_range(self) -> str:
        return f"bytes {self.start}-{self.stop - 1}/{self.size}"


def byte_span(
    range_header: str | None, size: int, *, limit: int = FILES_SERVE_MAX_BYTES
) -> ByteSpan:
    """Which bytes of a file of *size* bytes a request gets.

    Only one ``bytes=a-b``, ``bytes=a-`` or ``bytes=-n`` range is honoured,
    with ASCII digits and at most 19 of them per number. A missing,
    malformed or multi-part ``Range`` is ignored, and so is any ``Range``
    on an empty file. The last byte sent is capped at
    ``start + limit - 1``, so an open range on a large file is answered
    with its first *limit* bytes.

    :raises DesktopIngressError: 413 ``file_too_large`` for a file over
        *limit* requested without a range; 416 ``range_not_satisfiable``
        for a range starting at or after *size*, or ``bytes=-0``.
    """
    requested = _single_range(range_header)
    if requested is None or size == 0:
        if size > limit:
            raise DesktopIngressError("file_too_large", status_code=413)
        return ByteSpan(start=0, stop=size, size=size, partial=False)

    first, last = requested
    if first is None:
        suffix = last or 0
        if suffix == 0:
            raise DesktopIngressError("range_not_satisfiable", status_code=416)
        first, last = max(size - suffix, 0), size - 1
    elif first >= size:
        raise DesktopIngressError("range_not_satisfiable", status_code=416)
    last = size - 1 if last is None else min(last, size - 1)
    last = min(last, first + limit - 1)
    return ByteSpan(start=first, stop=last + 1, size=size, partial=True)


def _single_range(header: str | None) -> tuple[int | None, int | None] | None:
    if not header:
        return None
    match = _RANGE.fullmatch(header)
    if match is None:
        return None
    first_text, last_text = match.groups()
    if not first_text and not last_text:
        return None
    first = int(first_text) if first_text else None
    last = int(last_text) if last_text else None
    if first is not None and last is not None and last < first:
        return None
    return first, last


async def file_chunks(
    opened: OpenedFile, span: ByteSpan, *, chunk_bytes: int = FILES_SERVE_CHUNK_BYTES
) -> AsyncIterator[bytes]:
    """Yield the bytes of *span* from *opened*, reading in a thread.

    Closes *opened* when the iteration ends, fails or is abandoned. A file
    that shrank since it was opened ends the iteration early.
    """
    try:
        await asyncio.to_thread(opened.handle.seek, span.start)
        remaining = span.length
        while remaining > 0:
            chunk = await asyncio.to_thread(
                opened.handle.read, min(chunk_bytes, remaining)
            )
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        opened.close()
