"""SHA-256 file checksum utility."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(filepath: str | Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    filepath = Path(filepath)
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
