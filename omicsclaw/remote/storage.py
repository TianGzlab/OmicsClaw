"""Filesystem layout helpers for remote control-plane state.

Workspace layout::

    <workspace>/.omicsclaw/remote/
        datasets/<dataset_id>/
            <original_filename>
            meta.json
        jobs/<job_id>/
            job.json
            stdout.log
            artifacts/<...>

Single source of truth for path resolution so every router resolves the
same workspace via :func:`resolve_workspace`.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

REMOTE_SUBDIR = ".omicsclaw/remote"
_CHECKSUM_HEAD_BYTES = 64 * 1024


def resolve_workspace(explicit: str = "") -> Path:
    """Resolve the active workspace, raising ``RuntimeError`` if unset.

    Resolution order matches existing server.py helpers (see
    ``_resolve_scoped_memory_workspace``): explicit arg > env > unset.
    """
    candidate = (explicit or "").strip() or os.environ.get("OMICSCLAW_WORKSPACE", "").strip()
    if not candidate:
        raise RuntimeError(
            "OMICSCLAW_WORKSPACE is not set. Configure a workspace via PUT /workspace first."
        )
    path = Path(candidate).expanduser().resolve()
    if not path.is_dir():
        raise RuntimeError(f"workspace directory does not exist: {path}")
    return path


def remote_root(workspace: Path) -> Path:
    root = workspace / REMOTE_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def datasets_root(workspace: Path) -> Path:
    root = remote_root(workspace) / "datasets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def jobs_root(workspace: Path) -> Path:
    root = remote_root(workspace) / "jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def path_modified_at_iso(path: Path) -> str:
    return timestamp_iso(path.stat().st_mtime)


def composite_checksum(path: Path) -> str:
    """sha256 of the first 64 KiB plus ``":<size_bytes>"``.

    Matches App ``src/lib/dataset-ref.ts`` so checksums round-trip.
    Cheap on multi-GB ``.h5ad`` files; collisions are vanishingly rare for
    deduplication purposes (UX-grade fingerprint, not cryptographic).
    """
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        head = fh.read(_CHECKSUM_HEAD_BYTES)
        hasher.update(head)
        size = path.stat().st_size
    return f"sha256-64k:{hasher.hexdigest()}:{size}"
