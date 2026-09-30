"""The ``result.json`` envelope every skill writes, and a safe writer for output files.

``RESULT_SCHEMA`` is a pure literal so readers outside this package can load
it with ``ast.literal_eval`` instead of importing it. Its ``optional`` part
is documentation only: :func:`validate_result_envelope` checks the
``required`` keys and their types, the ``non_empty`` keys, and ``status``
when present, and nothing else.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "RESULT_SCHEMA",
    "write_result_json",
    "load_result_json",
    "mark_result_status",
    "write_owned_text",
]

logger = logging.getLogger(__name__)

RESULT_SCHEMA = {
    "required": {"skill": "str", "version": "str", "completed_at": "str",
                 "input_checksum": "str", "summary": "dict", "data": "dict"},
    "non_empty": ["skill", "version", "completed_at"],
    "status_values": ["ok", "partial", "failed", "scaffold"],
    "optional": {"lineage": "list", "status": "str", "replot": "dict"},
}

RESULT_STATUS_VALUES = ("ok", "partial", "failed")
"""Run outcomes :func:`mark_result_status` accepts; ``scaffold`` is not one."""

_TYPES = {"str": str, "dict": dict, "list": list}


def _has_symlink_on_the_way(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    return any(p.is_symlink() for p in (absolute, *absolute.parents))


def _inside(path: Path, root: Path) -> bool:
    try:
        Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(root)))
        path.resolve().relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def write_owned_text(path: str | Path, *, output_root: str | Path, text: str) -> Path:
    """Atomically write *text* to *path*, a file inside *output_root*.

    The write goes to a temporary file in the same directory, is flushed to
    disk and then renamed over *path*, so readers see the old or the new
    content and never a partial one; the temporary file is removed on failure.

    :returns: *path* as a :class:`~pathlib.Path`.
    :raises RuntimeError: If *path* or any directory above it is a symbolic
        link, *path* is outside *output_root*, or *path* exists and is not a
        regular file.
    :raises OSError: If writing or renaming fails.
    """
    candidate = Path(path)
    root = Path(output_root)
    if _has_symlink_on_the_way(candidate.parent):
        raise RuntimeError(f"refusing to write through a symbolic link: {candidate}")
    if not _inside(candidate.parent, root):
        raise RuntimeError(f"refusing to write outside output root {root}: {candidate}")
    if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
        raise RuntimeError(f"refusing to replace a link or non-regular file: {candidate}")

    fd, temporary_name = tempfile.mkstemp(dir=candidate.parent, prefix=f".{candidate.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, candidate)
        if os.name == "posix":
            directory = os.open(candidate.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return candidate


def _readable_result(output_root: Path) -> Path | None:
    result_path = output_root / "result.json"
    if (
        _has_symlink_on_the_way(result_path)
        or not result_path.is_file()
        or not _inside(result_path, output_root)
    ):
        return None
    return result_path


def load_result_json(output_dir: str | Path) -> dict[str, Any] | None:
    """The parsed ``result.json`` in *output_dir*, or ``None``.

    ``None`` when the file is missing, is or sits behind a symbolic link, lies
    outside *output_dir*, or is not valid JSON.
    """
    result_path = _readable_result(Path(output_dir))
    if result_path is None:
        return None
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_result_json(
    output_dir: str | Path,
    skill: str,
    version: str,
    summary: dict[str, Any],
    data: dict[str, Any],
    input_checksum: str = "",
    lineage: list[dict[str, Any]] | None = None,
) -> Path:
    """Write the standard ``result.json`` envelope into *output_dir*.

    The envelope has exactly the ``required`` keys of :data:`RESULT_SCHEMA`,
    plus ``lineage`` when it is given. *input_checksum* is written as
    ``sha256:<value>``, or ``""`` when empty.

    :returns: The path written.
    :raises RuntimeError: As :func:`write_owned_text`.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    envelope: dict[str, Any] = {
        "skill": skill,
        "version": version,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "input_checksum": f"sha256:{input_checksum}" if input_checksum else "",
        "summary": summary,
        "data": data,
    }
    if lineage is not None:
        envelope["lineage"] = lineage
    return write_owned_text(
        output_dir / "result.json",
        output_root=output_dir,
        text=json.dumps(envelope, indent=2, default=str),
    )


def validate_result_envelope(payload: Any) -> list[str]:
    """Problems with *payload* as a ``result.json`` envelope; empty when valid."""
    if not isinstance(payload, dict):
        return ["result.json must be a JSON object"]
    problems: list[str] = []
    for key, type_name in RESULT_SCHEMA["required"].items():
        if not isinstance(payload.get(key), _TYPES[type_name]):
            problems.append(f"{key} must be of type {type_name}")
    for key in RESULT_SCHEMA["non_empty"]:
        if isinstance(payload.get(key), str) and not payload[key]:
            problems.append(f"{key} must not be empty")
    status = payload.get("status")
    if status is not None and status not in RESULT_SCHEMA["status_values"]:
        problems.append(f"status {status!r} is not one of {RESULT_SCHEMA['status_values']}")
    return problems


def mark_result_status(output_dir: str | Path, status: str) -> bool:
    """Add a top-level ``status`` to the ``result.json`` in *output_dir*.

    Call it as the skill's last step. *status* must be one of
    :data:`RESULT_STATUS_VALUES`.

    :returns: ``True`` when written; ``False`` when *status* is not a run
        outcome or the envelope is missing, unreadable or not an object.
        Never raises.
    """
    if status not in RESULT_STATUS_VALUES:
        logger.warning(
            "mark_result_status: ignoring unknown status %r (allowed: %s)", status, list(RESULT_STATUS_VALUES)
        )
        return False
    output_root = Path(output_dir)
    envelope = load_result_json(output_root)
    if not isinstance(envelope, dict):
        return False
    envelope["status"] = status
    try:
        write_owned_text(
            output_root / "result.json",
            output_root=output_root,
            text=json.dumps(envelope, indent=2, default=str),
        )
    except (OSError, RuntimeError):
        return False
    return True
