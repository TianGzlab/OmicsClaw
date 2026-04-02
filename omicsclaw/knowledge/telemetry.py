"""Local JSONL telemetry for active knowledge-system events.

This module only retains the events that are part of the current runtime path:
- KH constraint injection
- explicit consult_knowledge tool calls
- CLI /tips toggles
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default telemetry log location
_DEFAULT_LOG_DIR = Path(os.getenv(
    "OMICSCLAW_DATA_DIR",
    os.path.expanduser("~/.config/omicsclaw"),
))
_TELEMETRY_LOG = _DEFAULT_LOG_DIR / "knowledge_telemetry.jsonl"


class KnowledgeTelemetry:
    """Append-only knowledge runtime telemetry."""

    def __init__(self, log_path: Optional[Path] = None):
        self._log_path = log_path or _TELEMETRY_LOG
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, event: dict) -> None:
        """Append a single event to the JSONL log."""
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("Telemetry write failed: %s", e)

    # ------------------------------------------------------------------
    # Event types
    # ------------------------------------------------------------------

    def log_kh_injection(
        self,
        session_id: str,
        skill: str,
        query: str,
        domain: str,
        injected_khs: list[str],
        constraints_length: int,
        latency_ms: float,
    ) -> None:
        """Log a KH preflight injection event."""
        self._write({
            "event": "kh_injection",
            "session_id": session_id,
            "skill": skill,
            "query": query[:200],
            "domain": domain,
            "injected_khs": injected_khs,
            "constraints_length": constraints_length,
            "latency_ms": round(latency_ms, 2),
        })

    def log_tips_toggle(
        self,
        session_id: str,
        enabled: bool,
        level: str = "basic",
    ) -> None:
        """Log user toggling /tips on/off."""
        self._write({
            "event": "tips_toggle",
            "session_id": session_id,
            "enabled": enabled,
            "level": level,
        })

    def log_consult_knowledge(
        self,
        session_id: str,
        query: str,
        category: str,
        domain: str,
        results_count: int,
        latency_ms: float,
    ) -> None:
        """Log LLM-initiated consult_knowledge tool call."""
        self._write({
            "event": "consult_knowledge",
            "session_id": session_id,
            "query": query[:200],
            "category": category,
            "domain": domain,
            "results_count": results_count,
            "latency_ms": round(latency_ms, 2),
        })


# Module-level singleton
_global_telemetry: Optional[KnowledgeTelemetry] = None


def get_telemetry() -> KnowledgeTelemetry:
    """Get or create the global KnowledgeTelemetry singleton."""
    global _global_telemetry
    if _global_telemetry is None:
        _global_telemetry = KnowledgeTelemetry()
    return _global_telemetry
