"""
High-level query interface for the OmicsClaw knowledge base.

KnowledgeAdvisor is the public facade that wraps KnowledgeStore and
provides formatted, context-aware search results for the LLM tool and CLI.
"""

from __future__ import annotations

from collections import deque
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .semantic_index import KnowledgeSemanticIndex
from .store import KnowledgeStore

logger = logging.getLogger(__name__)
_RUNTIME_NOTICES: deque[str] = deque(maxlen=16)

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


def _push_runtime_notice(message: str) -> None:
    text = " ".join(str(message or "").split()).strip()
    if not text:
        return
    if _RUNTIME_NOTICES and _RUNTIME_NOTICES[-1] == text:
        return
    _RUNTIME_NOTICES.append(text)


def consume_runtime_notice() -> str:
    if not _RUNTIME_NOTICES:
        return ""
    return _RUNTIME_NOTICES.popleft()


def clear_runtime_notices() -> None:
    _RUNTIME_NOTICES.clear()


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

    def ensure_available(self, *, auto_build: bool = True) -> bool:
        """Ensure the knowledge index is queryable.

        When ``auto_build`` is true and the document root exists, a missing
        or stale index is built lazily on first use.
        """
        root = self.kb_root
        if self._store.is_built() and self._store.is_up_to_date(root):
            return True
        if not auto_build:
            return False
        if not root.is_dir():
            return False

        try:
            was_built = self._store.is_built()
            if was_built:
                logger.info("Knowledge index is stale; rebuilding from %s", root)
            build_info = self.build(root)
        except Exception as exc:
            logger.warning("Knowledge auto-build failed: %s", exc)
            return False
        file_count = int(build_info.get("source_file_count", "0") or 0)
        if was_built:
            _push_runtime_notice(
                f"Knowledge base updated; index refreshed automatically ({file_count} file(s))."
            )
        else:
            _push_runtime_notice(
                f"Knowledge base indexed automatically ({file_count} file(s))."
            )
        return self._store.is_up_to_date(root)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    @dataclass(frozen=True, slots=True)
    class SearchTrace:
        query: str
        extra_queries: tuple[str, ...]
        stages: tuple[str, ...]
        result_count: int

    def _get_semantic_index(self) -> KnowledgeSemanticIndex:
        manifest = self._store.get_build_manifest()
        cache_key = (
            str(self._store.db_path),
            manifest.get("source_fingerprint", ""),
            manifest.get("source_file_count", ""),
        )
        rows = self._store.list_chunks()
        return KnowledgeSemanticIndex.from_rows(cache_key=cache_key, rows=rows)

    @staticmethod
    def _result_key(row: dict) -> tuple[str, str, str]:
        return (
            str(row.get("source_path", "")),
            str(row.get("section_title", "")),
            str(row.get("title", "")),
        )

    @staticmethod
    def _annotate_result(row: dict, *, stage: str, retrieval_query: str) -> dict:
        annotated = dict(row)
        annotated.setdefault("_retrieval_stage", stage)
        annotated.setdefault("_retrieval_query", retrieval_query)
        return annotated

    @staticmethod
    def _extract_query_terms(query: str) -> list[str]:
        normalized = " ".join(str(query or "").lower().split())
        if not normalized:
            return []
        terms: list[str] = []
        for word in re.findall(r"[a-z0-9][a-z0-9_\-+.]+", normalized):
            if len(word) >= 3:
                terms.append(word)
        for span in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            terms.append(span)
        return list(dict.fromkeys(terms))

    def _rerank_results(self, query: str, rows: list[dict]) -> list[dict]:
        query_terms = self._extract_query_terms(query)
        if not rows:
            return []

        def score(row: dict) -> tuple[float, float, str]:
            title = str(row.get("title", "")).lower()
            section = str(row.get("section_title", "")).lower()
            search_terms = str(row.get("search_terms", "")).lower()
            content = str(row.get("content", "")).lower()
            haystack = " ".join(part for part in (title, section, search_terms, content) if part)

            overlap = 0.0
            title_overlap = 0.0
            if query_terms:
                overlap = sum(1 for term in query_terms if term in haystack) / len(query_terms)
                title_overlap = sum(1 for term in query_terms if term in title or term in section) / len(query_terms)

            lexical_rank = row.get("rank")
            try:
                lexical_score = 1.0 / (1.0 + abs(float(lexical_rank)))
            except (TypeError, ValueError):
                lexical_score = 0.0

            semantic_score = float(row.get("_semantic_score", 0.0) or 0.0)
            stage_bonus = 0.15 if row.get("_retrieval_stage") == "lexical" else 0.05
            total = (semantic_score * 0.55) + (lexical_score * 0.2) + (overlap * 0.2) + (title_overlap * 0.2) + stage_bonus
            return (
                total,
                semantic_score,
                f"{row.get('source_path', '')}::{row.get('section_title', '')}",
            )

        return sorted(rows, key=score, reverse=True)

    def _merge_results(self, existing: list[dict], incoming: list[dict]) -> list[dict]:
        merged = {self._result_key(item): dict(item) for item in existing}
        for item in incoming:
            key = self._result_key(item)
            current = merged.get(key)
            if current is None:
                merged[key] = dict(item)
                continue
            if float(item.get("_semantic_score", 0.0) or 0.0) > float(current.get("_semantic_score", 0.0) or 0.0):
                merged[key]["_semantic_score"] = item["_semantic_score"]
            if current.get("_retrieval_stage") != "lexical" and item.get("_retrieval_stage") == "lexical":
                merged[key]["_retrieval_stage"] = "lexical"
                merged[key]["rank"] = item.get("rank", current.get("rank"))
            if not current.get("_retrieval_query") and item.get("_retrieval_query"):
                merged[key]["_retrieval_query"] = item["_retrieval_query"]
        return list(merged.values())

    def search_with_trace(
        self,
        query: str,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5,
        auto_build: bool = True,
        extra_queries: Optional[list[str]] = None,
    ) -> tuple[list[dict], SearchTrace]:
        if not self.ensure_available(auto_build=auto_build):
            raise RuntimeError(
                "Knowledge base not built yet. Run: python omicsclaw.py knowledge build"
            )

        queries = [
            value for value in (
                " ".join(str(query or "").split()).strip(),
                *(" ".join(str(item or "").split()).strip() for item in (extra_queries or [])),
            )
            if value
        ]
        deduped_queries = list(dict.fromkeys(queries))

        stages: list[str] = []
        merged: list[dict] = []
        lexical_limit = max(limit * 2, 6)
        semantic_limit = max(limit * 3, 8)
        semantic_index: KnowledgeSemanticIndex | None = None

        for current_query in deduped_queries:
            lexical_hits = [
                self._annotate_result(item, stage="lexical", retrieval_query=current_query)
                for item in self._store.search(
                    current_query,
                    domain=domain,
                    doc_type=doc_type,
                    limit=lexical_limit,
                )
            ]
            if lexical_hits:
                stages.append("lexical")
                merged = self._merge_results(merged, lexical_hits)

            if len(merged) < limit:
                if semantic_index is None:
                    semantic_index = self._get_semantic_index()
                semantic_hits = []
                for hit in semantic_index.search(
                    current_query,
                    domain=domain,
                    doc_type=doc_type,
                    limit=semantic_limit,
                ):
                    row = self._annotate_result(hit.row, stage="semantic", retrieval_query=current_query)
                    row["_semantic_score"] = hit.score
                    semantic_hits.append(row)
                if semantic_hits:
                    stages.append("semantic")
                    merged = self._merge_results(merged, semantic_hits)

        ranked = self._rerank_results(query, merged)[:limit]
        trace = self.SearchTrace(
            query=query,
            extra_queries=tuple(deduped_queries[1:]),
            stages=tuple(dict.fromkeys(stages)),
            result_count=len(ranked),
        )
        return ranked, trace

    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5,
        auto_build: bool = True,
        extra_queries: Optional[list[str]] = None,
    ) -> list[dict]:
        """Search the knowledge base and return ranked results.

        Returns an empty list when no results are found.
        Raises RuntimeError if the index has not been built yet.
        """
        results, _trace = self.search_with_trace(
            query=query,
            domain=domain,
            doc_type=doc_type,
            limit=limit,
            auto_build=auto_build,
            extra_queries=extra_queries,
        )
        return results

    @staticmethod
    def format_results(
        query: str,
        results: list[dict],
        *,
        max_snippet: int = 1500,
    ) -> str:
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

    def search_formatted(
        self,
        query: str,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5,
        max_snippet: int = 1500,
        auto_build: bool = True,
        extra_queries: Optional[list[str]] = None,
    ) -> str:
        """Search and return results as formatted text for LLM consumption."""
        try:
            results = self.search(
                query,
                domain,
                doc_type,
                limit,
                auto_build=auto_build,
                extra_queries=extra_queries,
            )
        except RuntimeError as e:
            return str(e)
        return self.format_results(query, results, max_snippet=max_snippet)

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
        return self.ensure_available(auto_build=True)

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
