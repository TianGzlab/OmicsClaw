"""
High-level query interface for the OmicsClaw knowledge base.

KnowledgeAdvisor is the public facade that wraps KnowledgeStore and
provides formatted, context-aware search results for the LLM tool and CLI.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from .store import KnowledgeStore

logger = logging.getLogger(__name__)

# Knowledge base document root — configurable via env var
_DEFAULT_KB_PATH = Path(
    os.getenv("OMICSCLAW_KNOWLEDGE_PATH", "")
) if os.getenv("OMICSCLAW_KNOWLEDGE_PATH") else None


def _find_kb_root() -> Path:
    """Locate the knowledge_base directory."""
    if _DEFAULT_KB_PATH and _DEFAULT_KB_PATH.is_dir():
        return _DEFAULT_KB_PATH

    # Check relative to this file (omicsclaw/knowledge/retriever.py → project root)
    project_root = Path(__file__).resolve().parent.parent.parent
    kb = project_root / "knowledge_base"
    if kb.is_dir():
        return kb

    # Check CWD
    cwd_kb = Path.cwd() / "knowledge_base"
    if cwd_kb.is_dir():
        return cwd_kb

    return kb  # Return default even if missing — build() will warn


class KnowledgeAdvisor:
    """Public facade for the knowledge base system."""

    def __init__(self, db_path: Optional[Path] = None):
        self._store = KnowledgeStore(db_path)
        self._kb_root: Optional[Path] = None

    @property
    def kb_root(self) -> Path:
        if self._kb_root is None:
            self._kb_root = _find_kb_root()
        return self._kb_root

    @kb_root.setter
    def kb_root(self, path: Path):
        self._kb_root = path

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, kb_path: Optional[Path] = None) -> dict:
        """Build/rebuild the knowledge index from documents on disk."""
        root = kb_path or self.kb_root
        if not root.is_dir():
            raise FileNotFoundError(
                f"Knowledge base directory not found: {root}\n"
                "Set OMICSCLAW_KNOWLEDGE_PATH or pass --path."
            )
        return self._store.build(root)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """Search the knowledge base and return ranked results.

        Returns an empty list when no results are found.
        Raises RuntimeError if the index has not been built yet.
        """
        if not self._store.is_built():
            raise RuntimeError(
                "Knowledge base not built yet. Run: python omicsclaw.py knowledge build"
            )
        return self._store.search(query, domain, doc_type, limit)

    def search_formatted(
        self,
        query: str,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5,
        max_snippet: int = 1500,
    ) -> str:
        """Search and return results as formatted text for LLM consumption."""
        try:
            results = self.search(query, domain, doc_type, limit)
        except RuntimeError as e:
            return str(e)

        if not results:
            return f"No knowledge base results found for: {query}"

        parts = [f"Knowledge base results for: \"{query}\"\n"]
        for i, r in enumerate(results, 1):
            snippet = r.get("content", "")
            if len(snippet) > max_snippet:
                snippet = snippet[:max_snippet] + "\n[...truncated]"

            parts.append(
                f"--- Result {i} ---\n"
                f"Source: {r.get('source_path', 'unknown')}\n"
                f"Title: {r.get('title', 'unknown')}\n"
                f"Section: {r.get('section_title', '')}\n"
                f"Domain: {r.get('domain', '')} | Type: {r.get('doc_type', '')}\n\n"
                f"{snippet}\n"
            )
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # List / stats
    # ------------------------------------------------------------------

    def list_topics(self, domain: Optional[str] = None) -> list[dict]:
        """List available knowledge topics."""
        if not self._store.is_built():
            return []
        return self._store.list_topics(domain)

    def stats(self) -> dict:
        """Return index statistics."""
        if not self._store.is_built():
            return {"error": "Knowledge base not built yet."}
        return self._store.stats()

    def is_available(self) -> bool:
        """Check if the knowledge base is indexed and ready."""
        return self._store.is_built()

    # ------------------------------------------------------------------
    # Get full document
    # ------------------------------------------------------------------

    def get_document(self, source_path: str) -> str:
        """Return the full content of a specific document."""
        chunks = self._store.get_document(source_path)
        if not chunks:
            return f"Document not found: {source_path}"
        parts = []
        for c in chunks:
            parts.append(f"## {c.get('section_title', '')}\n\n{c.get('content', '')}")
        return f"# {chunks[0].get('title', source_path)}\n\n" + "\n\n".join(parts)
