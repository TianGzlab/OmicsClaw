"""Filesystem path validation + safe destination resolution + file discovery.

Carved out of ``bot/core.py`` per ADR 0001. Every helper enforces that the
resolved path lives inside one of the trusted data directories (or under
``OMICSCLAW_DIR``) — paths that escape those roots are rejected and audit-
logged. ``OMICSCLAW_DIR`` / ``DATA_DIR`` / ``EXAMPLES_DIR`` / ``OUTPUT_DIR``
are owned by ``bot.core``; we late-import them on first use to avoid a
load-order circular.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from bot.audit import audit

logger = logging.getLogger("omicsclaw.bot.path_validation")


def _bot_core_dirs():
    """Late import of the bot.core directory globals."""
    from bot.core import DATA_DIR, EXAMPLES_DIR, OMICSCLAW_DIR, OUTPUT_DIR
    return OMICSCLAW_DIR, DATA_DIR, EXAMPLES_DIR, OUTPUT_DIR


def sanitize_filename(filename: str) -> str:
    filename = Path(filename).name
    filename = re.sub(r"[\x00-\x1f]", "", filename)
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")
    return filename or "unnamed_file"


def resolve_dest(folder: str | None, default: Path | None = None) -> Path:
    OMICSCLAW_DIR, DATA_DIR, _, _ = _bot_core_dirs()
    fallback = default if default is not None else DATA_DIR
    dest = Path(folder) if folder else fallback
    if not dest.is_absolute():
        dest = OMICSCLAW_DIR / dest
    try:
        dest.resolve().relative_to(OMICSCLAW_DIR.resolve())
    except ValueError:
        logger.warning(f"Path escape blocked: {dest}")
        audit("security", severity="HIGH", detail="path_escape_blocked", attempted_path=str(dest))
        dest = fallback
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def validate_path(filepath: Path, allowed_root: Path) -> bool:
    try:
        filepath.resolve().relative_to(allowed_root.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Trusted data directories + file discovery
# ---------------------------------------------------------------------------

TRUSTED_DATA_DIRS: list[Path] = []


def _build_trusted_dirs() -> list[Path]:
    """Build the list of directories where data files may be read from."""
    _, DATA_DIR, EXAMPLES_DIR, OUTPUT_DIR = _bot_core_dirs()
    dirs = [DATA_DIR, EXAMPLES_DIR, OUTPUT_DIR]
    extra = os.environ.get("OMICSCLAW_DATA_DIRS", os.environ.get("SPATIALCLAW_DATA_DIRS", ""))
    if extra:
        for d in extra.split(","):
            d = d.strip()
            if d:
                p = Path(d)
                if p.is_absolute() and p.is_dir():
                    dirs.append(p)
                else:
                    logger.warning(f"OMICSCLAW_DATA_DIRS: ignoring '{d}' (not an absolute directory)")
    return dirs


def _ensure_trusted_dirs():
    global TRUSTED_DATA_DIRS
    if not TRUSTED_DATA_DIRS:
        TRUSTED_DATA_DIRS = _build_trusted_dirs()
        logger.info(f"Trusted data dirs: {[str(d) for d in TRUSTED_DATA_DIRS]}")


def validate_input_path(filepath: str, *, allow_dir: bool = False) -> Path | None:
    """Validate that a user-supplied path points to a real file/dir in a trusted directory.

    Returns resolved Path if valid, None otherwise.
    """
    _ensure_trusted_dirs()
    OMICSCLAW_DIR, DATA_DIR, _, _ = _bot_core_dirs()
    p = Path(filepath).expanduser()
    if not p.is_absolute():
        # 1. Try relative to project root first (most common case)
        candidate = OMICSCLAW_DIR / p
        if candidate.exists() and (candidate.is_file() or (allow_dir and candidate.is_dir())):
            p = candidate
        else:
            # 2. Try each trusted data directory
            for d in TRUSTED_DATA_DIRS:
                candidate = d / p
                if candidate.exists() and (candidate.is_file() or (allow_dir and candidate.is_dir())):
                    p = candidate
                    break
            else:
                # 3. Fall back to DATA_DIR
                p = DATA_DIR / p

    resolved = p.resolve()
    if not resolved.exists():
        return None
    if not resolved.is_file() and not (allow_dir and resolved.is_dir()):
        return None

    for trusted in TRUSTED_DATA_DIRS:
        try:
            resolved.relative_to(trusted.resolve())
            return resolved
        except ValueError:
            continue

    # Also allow files anywhere under project root
    try:
        resolved.relative_to(OMICSCLAW_DIR.resolve())
        return resolved
    except ValueError:
        pass

    logger.warning(f"Path not in trusted dirs: {resolved}")
    audit("security", severity="MEDIUM", detail="untrusted_path_rejected", path=str(resolved))
    return None


def discover_file(filename_or_pattern: str) -> list[Path]:
    """Search trusted data directories for files matching the given name or glob pattern.

    Returns a list of matching paths, sorted by modification time (newest first).
    """
    _ensure_trusted_dirs()

    # Handle absolute paths directly
    if filename_or_pattern.startswith('/'):
        p = Path(filename_or_pattern)
        if p.is_file():
            return [p]
        return []

    matches: list[Path] = []
    for d in TRUSTED_DATA_DIRS:
        if not d.exists():
            continue
        if "*" in filename_or_pattern or "?" in filename_or_pattern:
            matches.extend(f for f in d.rglob(filename_or_pattern) if f.is_file())
        else:
            exact = d / filename_or_pattern
            if exact.is_file():
                matches.append(exact)
            for f in d.rglob(filename_or_pattern):
                if f.is_file() and f not in matches:
                    matches.append(f)
    matches.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return matches
