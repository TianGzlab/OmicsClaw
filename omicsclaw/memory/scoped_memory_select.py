"""Selection helpers for injecting only a small set of relevant scoped memories."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .scoped_memory import (
    ScopedMemoryRecord,
    normalize_scoped_memory_scope,
    resolve_scoped_memory_root,
)
from .scoped_memory_index import (
    ScopedMemoryHeader,
    load_scoped_memory_record,
    scan_scoped_memory_headers,
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]{2,}")


@dataclass(frozen=True, slots=True)
class ScopedMemoryRecall:
    root: Path | None = None
    preferred_scope: str = ""
    selected: tuple[ScopedMemoryRecord, ...] = ()
    total_candidates: int = 0
    total_chars: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    def to_context_text(self) -> str:
        if not self.selected:
            return ""

        lines = [
            "Local project/dataset/lab heuristics. Treat these as contextual hints, not global scientific knowledge. If current files, workspace state, or user instructions conflict, trust the current evidence.",
            "",
        ]
        for index, record in enumerate(self.selected, start=1):
            meta_parts = [
                f"scope={record.scope}",
                f"owner={record.owner or 'unknown'}",
                f"freshness={record.freshness}",
                f"updated={record.updated_at[:10]}",
            ]
            if record.domain:
                meta_parts.append(f"domain={record.domain}")
            lines.append(f"{index}. {record.title}")
            lines.append(f"   {' | '.join(meta_parts)}")
            if record.description:
                lines.append(f"   Summary: {record.description}")
            excerpt = _condense_excerpt(record.body)
            if excerpt:
                lines.append(f"   Details: {excerpt}")
        return "\n".join(lines).strip()


def load_scoped_memory_context(
    *,
    query: str,
    domain: str = "",
    workspace: str = "",
    pipeline_workspace: str = "",
    preferred_scope: str = "",
    root_dir: str | Path | None = None,
    limit: int = 3,
    char_budget: int = 2200,
) -> ScopedMemoryRecall:
    root = resolve_scoped_memory_root(
        workspace_dir=workspace,
        pipeline_workspace=pipeline_workspace,
        root_dir=root_dir,
    )
    if root is None or not root.is_dir():
        return ScopedMemoryRecall(root=root, preferred_scope=normalize_scoped_memory_scope(preferred_scope))

    normalized_scope = normalize_scoped_memory_scope(preferred_scope)
    headers = scan_scoped_memory_headers(root, limit=0)
    if not headers:
        return ScopedMemoryRecall(root=root, preferred_scope=normalized_scope)

    query_terms = _extract_terms(query)
    ranked = [
        (header, _score_memory_header(header, query_terms, domain=domain, preferred_scope=normalized_scope))
        for header in headers
    ]
    ranked = [(header, score) for header, score in ranked if score > 0]
    ranked.sort(key=lambda item: item[1], reverse=True)

    selected: list[ScopedMemoryRecord] = []
    total_chars = 0
    for header, _score in ranked:
        if limit > 0 and len(selected) >= limit:
            break
        record = load_scoped_memory_record(header.path, root=root)
        if record is None:
            continue
        projected = total_chars + len(_condense_excerpt(record.body)) + len(record.description) + len(record.title)
        if selected and projected > char_budget:
            continue
        selected.append(record)
        total_chars = projected

    return ScopedMemoryRecall(
        root=root,
        preferred_scope=normalized_scope,
        selected=tuple(selected),
        total_candidates=len(headers),
        total_chars=total_chars,
        metadata={
            "selected_count": len(selected),
            "char_budget": char_budget,
        },
    )


def _score_memory_header(
    header: ScopedMemoryHeader,
    query_terms: list[str],
    *,
    domain: str = "",
    preferred_scope: str = "",
) -> int:
    title = header.title.lower()
    description = header.description.lower()
    keywords_blob = " ".join(header.keywords).lower()
    dataset_blob = " ".join(header.dataset_refs).lower()
    domain_value = header.domain.lower()
    score = 0
    matched = False

    for term in query_terms:
        if term in title:
            score += 24
            matched = True
        elif term in description:
            score += 14
            matched = True
        elif term in keywords_blob or term in dataset_blob:
            score += 10
            matched = True

    if domain and domain.strip().lower() and domain.strip().lower() == domain_value:
        score += 10
        matched = True

    if preferred_scope and header.scope == preferred_scope:
        score += 8

    age_days = _age_in_days(header.updated_at)
    if age_days is not None:
        if age_days <= 7:
            score += 4
        elif age_days <= 30:
            score += 2
        elif header.freshness == "volatile" and age_days > 90:
            score -= 8
        elif header.freshness == "evolving" and age_days > 180:
            score -= 4

    if not matched and preferred_scope and header.scope == preferred_scope:
        if age_days is not None and age_days <= 14:
            score += 3
        elif header.freshness == "stable":
            score += 1

    return score if score > 0 else 0


def _extract_terms(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).lower() for match in _TOKEN_RE.finditer(str(text or ""))))


def _age_in_days(value: str) -> int | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - parsed).days, 0)


def _condense_excerpt(body: str, *, max_chars: int = 260) -> str:
    text = " ".join(str(body or "").strip().split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


__all__ = [
    "ScopedMemoryRecall",
    "load_scoped_memory_context",
]
