"""Append-only JSONL audit log for the bot surface.

Carved out of ``bot/core.py`` per ADR 0001. The log directory lives under
``OMICSCLAW_DIR/bot/logs``; ``OMICSCLAW_DIR`` is owned by ``bot.core`` so we
late-import it on first use to avoid a load-order circular.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("omicsclaw.bot.audit")

_audit_log_path: Path | None = None
_audit_log_dir_ready: bool = False


def _ensure_audit_log_path() -> Path | None:
    """Lazily resolve the audit log path on first call.

    Returns ``None`` when ``OMICSCLAW_DIR`` is not yet importable or the
    directory cannot be created — callers should treat the return value as
    "no log available, drop the event silently".
    """
    global _audit_log_path, _audit_log_dir_ready
    if _audit_log_dir_ready:
        return _audit_log_path
    try:
        from bot.core import OMICSCLAW_DIR
    except ImportError:
        return None
    log_dir = OMICSCLAW_DIR / "bot" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning(
            "Could not create audit log dir %s (%s) — audit events will be dropped",
            log_dir,
            exc,
        )
        _audit_log_dir_ready = True
        return None
    _audit_log_path = log_dir / "audit.jsonl"
    _audit_log_dir_ready = True
    return _audit_log_path


def audit(event: str, **kwargs):
    """Append an audit event to the JSONL log; tolerate any I/O failure."""
    path = _ensure_audit_log_path()
    if path is None:
        return
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs}
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as e:
        logger.warning(f"Audit log write failed: {e}")
