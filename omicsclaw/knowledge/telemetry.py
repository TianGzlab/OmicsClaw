"""
Knowledge System Telemetry (Plan Stage 0).

Tracks advisory events, KH injection metrics, and user engagement
to a local JSONL audit log.  This provides the observability baseline
needed to measure whether knowledge injection is helpful or noisy.

Tracked metrics:
- Which skill runs triggered advice queries
- Which KH rules were injected
- Frequency of advice displays
- Advice duplication rates (session-level)
- Latency impact of the retrieval process

Log location: ~/.config/omicsclaw/knowledge_telemetry.jsonl
"""

from __future__ import annotations

import json
import logging
import os
import time
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
    """Tracks knowledge system events for observability.

    All events are appended to a JSONL file for offline analysis.
    This is intentionally simple — no database, no async, no network.
    """

    def __init__(self, log_path: Optional[Path] = None):
        self._log_path = log_path or _TELEMETRY_LOG
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_stats: dict[str, dict] = {}  # session_id → stats

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
        # Track duplication
        stats = self._session_stats.setdefault(session_id, {
            "total_injections": 0,
            "kh_counts": {},
        })
        stats["total_injections"] += 1
        for kh in injected_khs:
            stats["kh_counts"][kh] = stats["kh_counts"].get(kh, 0) + 1

    def log_advice_resolved(
        self,
        session_id: str,
        skill: str,
        domain: str,
        snippets_count: int,
        deduped_count: int,
        latency_ms: float,
    ) -> None:
        """Log a post-execution advisory resolution event."""
        self._write({
            "event": "advice_resolved",
            "session_id": session_id,
            "skill": skill,
            "domain": domain,
            "snippets_returned": snippets_count,
            "snippets_deduped": deduped_count,
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

    def log_guide_query(
        self,
        session_id: str,
        query: str,
        results_count: int,
    ) -> None:
        """Log explicit /guide usage."""
        self._write({
            "event": "guide_query",
            "session_id": session_id,
            "query": query[:200],
            "results_count": results_count,
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

    # ------------------------------------------------------------------
    # Analytics helpers
    # ------------------------------------------------------------------

    def get_session_stats(self, session_id: str) -> dict:
        """Get injection stats for a session."""
        return self._session_stats.get(session_id, {})

    def get_duplication_rate(self, session_id: str) -> float:
        """Fraction of KH injections that were duplicates within session."""
        stats = self._session_stats.get(session_id)
        if not stats or stats["total_injections"] <= 1:
            return 0.0
        # Count how many total injections were repeats
        unique = len(stats["kh_counts"])
        total = sum(stats["kh_counts"].values())
        if total <= unique:
            return 0.0
        return (total - unique) / total


# Module-level singleton
_global_telemetry: Optional[KnowledgeTelemetry] = None


def get_telemetry() -> KnowledgeTelemetry:
    """Get or create the global KnowledgeTelemetry singleton."""
    global _global_telemetry
    if _global_telemetry is None:
        _global_telemetry = KnowledgeTelemetry()
    return _global_telemetry
