"""
Unified Advisory Event Schema (Plan Stage 2).

Defines a structured signal that every skill can emit after execution.
The Knowledge Resolver uses these signals to determine which knowledge
to surface — replacing unreliable LLM-based "should I search?" guesswork
with deterministic, metadata-driven routing.

This module also provides the KnowledgeResolver (Plan Stage 4) which
performs: routing → candidate narrowing → FTS5 retrieval → session dedup.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Advisory Event — emitted by skills after execution
# ---------------------------------------------------------------------------

@dataclass
class AdvisoryEvent:
    """Structured signal emitted after skill execution.

    This schema replaces free-text output parsing.  The Knowledge Resolver
    uses these fields to route to the correct knowledge documents.

    Attributes:
        skill:      Skill identifier (e.g. "sc-filter")
        phase:      Execution phase that triggered this event
        domain:     Omics domain (e.g. "singlecell", "bulkrna")
        toolchain:  Underlying tool (e.g. "scanpy", "deseq2")
        signals:    List of semantic signal tags for routing
        severity:   Event severity level
        metrics:    Numeric metrics from execution (for conditional triggers)
        message:    Human-readable summary (optional)
    """
    skill: str
    phase: str = "post_run"  # before_run, post_run, on_warning, on_error
    domain: str = "general"
    toolchain: str = ""
    signals: list[str] = field(default_factory=list)
    severity: str = "info"   # info, warning, error
    metrics: dict = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "phase": self.phase,
            "domain": self.domain,
            "toolchain": self.toolchain,
            "signals": self.signals,
            "severity": self.severity,
            "metrics": self.metrics,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Knowledge Resolver — deterministic routing + retrieval (Plan Stage 4)
# ---------------------------------------------------------------------------

class KnowledgeResolver:
    """Deterministic knowledge routing engine.

    Instead of asking the LLM "should I look up knowledge?", this resolver
    uses structured AdvisoryEvents to:

    1. Filter candidate documents by skill + phase + signals (routing)
    2. Rank candidates via FTS5/BM25 (retrieval)
    3. Apply session-level deduplication (cooldown)
    4. Return 0-2 concise advice snippets

    The key insight: routing first, retrieval second.
    """

    def __init__(self, max_snippets: int = 2, cooldown_seconds: float = 300.0):
        self._max_snippets = max_snippets
        self._cooldown_seconds = cooldown_seconds
        # Session dedup: {session_id: {doc_id: last_shown_timestamp}}
        self._shown_docs: dict[str, dict[str, float]] = {}

    def resolve(
        self,
        event: AdvisoryEvent,
        session_id: str = "",
    ) -> list[dict]:
        """Resolve knowledge for an advisory event.

        Returns a list of advice snippet dicts, each containing:
        - source_path, title, section_title, content, domain, doc_type
        """
        try:
            from .retriever import KnowledgeAdvisor

            advisor = KnowledgeAdvisor()
            if not advisor.is_available():
                return []

            # Step 1: Build a targeted query from the event
            query_parts = [event.skill]
            if event.signals:
                query_parts.extend(event.signals[:3])
            if event.message:
                # Extract key terms from message (first 50 chars)
                query_parts.append(event.message[:50])
            query = " ".join(query_parts)

            # Step 2: Search with domain filter
            domain_filter = event.domain if event.domain != "general" else None
            results = advisor.search(
                query=query,
                domain=domain_filter,
                limit=self._max_snippets * 2,  # fetch extra for dedup filtering
            )

            if not results:
                return []

            # Step 3: Session deduplication
            if session_id:
                results = self._apply_cooldown(results, session_id)

            # Step 4: Truncate to max snippets
            return results[:self._max_snippets]

        except Exception as e:
            logger.warning("Knowledge resolver failed: %s", e)
            return []

    def _apply_cooldown(
        self,
        results: list[dict],
        session_id: str,
    ) -> list[dict]:
        """Remove results that were shown recently in this session."""
        now = time.time()
        shown = self._shown_docs.setdefault(session_id, {})

        filtered = []
        for r in results:
            doc_key = r.get("source_path", "") + "::" + r.get("section_title", "")
            last_shown = shown.get(doc_key, 0.0)
            if now - last_shown > self._cooldown_seconds:
                filtered.append(r)
                shown[doc_key] = now

        return filtered

    def format_advice(self, snippets: list[dict], channel: str = "cli") -> str:
        """Format resolved snippets for presentation.

        Args:
            snippets: List of result dicts from resolve()
            channel:  One of "cli", "bot", "guide"
        """
        if not snippets:
            return ""

        if channel == "cli":
            # Concise block format for terminal
            parts = ["", "💡 Advice:"]
            for s in snippets:
                title = s.get("title", "")
                section = s.get("section_title", "")
                content = s.get("content", "")
                # Truncate to 200 chars for CLI
                if len(content) > 200:
                    content = content[:200].rsplit(" ", 1)[0] + "…"
                label = f"{title}" + (f" › {section}" if section else "")
                parts.append(f"  • {label}")
                parts.append(f"    {content}")
            parts.append("")
            return "\n".join(parts)

        elif channel == "bot":
            # Brief hint for messaging bots
            hints = []
            for s in snippets:
                content = s.get("content", "")
                # Extract first sentence
                first_sentence = content.split(".")[0].strip() + "."
                if len(first_sentence) > 150:
                    first_sentence = first_sentence[:150] + "…"
                hints.append(first_sentence)
            return "💡 " + " ".join(hints)

        else:
            # Full format for /guide deep-dive
            parts = []
            for s in snippets:
                parts.append(f"### {s.get('title', '')}")
                if s.get("section_title"):
                    parts.append(f"**{s['section_title']}**\n")
                parts.append(s.get("content", ""))
                parts.append("")
            return "\n".join(parts)

    def clear_session(self, session_id: str) -> None:
        """Clear dedup history for a session."""
        self._shown_docs.pop(session_id, None)


# Module-level singleton
_global_resolver: Optional[KnowledgeResolver] = None


def get_resolver() -> KnowledgeResolver:
    """Get or create the global KnowledgeResolver singleton."""
    global _global_resolver
    if _global_resolver is None:
        _global_resolver = KnowledgeResolver()
    return _global_resolver
