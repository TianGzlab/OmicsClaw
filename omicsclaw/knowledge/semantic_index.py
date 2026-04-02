from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True, slots=True)
class SemanticSearchHit:
    row: dict
    score: float


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split()).strip()


def _build_row_text(row: dict) -> str:
    return " \n ".join(
        part
        for part in (
            row.get("title", ""),
            row.get("section_title", ""),
            row.get("search_terms", ""),
            row.get("content", ""),
        )
        if str(part).strip()
    )


class KnowledgeSemanticIndex:
    """Lightweight semantic retriever over indexed chunks.

    This is intentionally local-first and dependency-light:
    - corpus comes from the SQLite knowledge index
    - vectorization uses TF-IDF character n-grams for robust fuzzy matching
    - results are used as a secondary recall channel, not the sole ranker
    """

    _CACHE: dict[tuple[object, ...], "KnowledgeSemanticIndex"] = {}

    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        corpus = [_build_row_text(row) for row in self._rows]
        self._vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 5),
            lowercase=True,
            sublinear_tf=True,
            min_df=1,
        )
        self._matrix = self._vectorizer.fit_transform(corpus) if corpus else None

    @classmethod
    def from_rows(
        cls,
        *,
        cache_key: tuple[object, ...],
        rows: list[dict],
    ) -> "KnowledgeSemanticIndex":
        cached = cls._CACHE.get(cache_key)
        if cached is not None:
            return cached
        built = cls(rows)
        cls._CACHE[cache_key] = built
        return built

    def search(
        self,
        query: str,
        *,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5,
    ) -> list[SemanticSearchHit]:
        query_text = _normalize_text(query)
        if not query_text or self._matrix is None or not self._rows:
            return []

        query_vector = self._vectorizer.transform([query_text])
        similarities = cosine_similarity(query_vector, self._matrix)[0]

        hits: list[SemanticSearchHit] = []
        for idx, score in enumerate(similarities):
            row = self._rows[idx]
            if domain and domain != "all" and row.get("domain") != domain:
                continue
            if doc_type and doc_type != "all" and row.get("doc_type") != doc_type:
                continue
            if score <= 0:
                continue
            hits.append(SemanticSearchHit(row=dict(row), score=float(score)))

        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:limit]
