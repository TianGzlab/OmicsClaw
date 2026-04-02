"""Scoped memory primitives for project- and experiment-local context.

This layer is intentionally separate from:

- graph memory: durable cross-session structured state
- knowledge base: general scientific guidance and standardized methodology

Scoped memory stores local heuristics and project-specific context as
Markdown files with lightweight frontmatter under the active workspace.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

SCOPED_MEMORY_SCOPES = (
    "user",
    "project",
    "dataset",
    "lab_policy",
    "workflow_hint",
)
SCOPED_MEMORY_FRESHNESS_LEVELS = (
    "stable",
    "evolving",
    "volatile",
)
DEFAULT_SCOPED_MEMORY_SCOPE = "project"
SCOPED_MEMORY_DIRNAME = ".omicsclaw/scoped_memory"

_SCOPE_ALIASES = {
    "lab-policy": "lab_policy",
    "workflow-hint": "workflow_hint",
}
_FRESHNESS_ALIASES = {
    "long": "stable",
    "short": "volatile",
    "medium": "evolving",
}
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.DOTALL)
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_DEFAULT_FRESHNESS_BY_SCOPE = {
    "user": "stable",
    "project": "evolving",
    "dataset": "evolving",
    "lab_policy": "stable",
    "workflow_hint": "volatile",
}
_STALE_DAYS_BY_FRESHNESS = {
    "stable": 365,
    "evolving": 120,
    "volatile": 30,
}


@dataclass(frozen=True, slots=True)
class ScopedMemoryRecord:
    memory_id: str
    scope: str
    title: str
    description: str
    body: str
    owner: str
    freshness: str
    updated_at: str
    created_at: str
    path: Path
    root: Path
    domain: str = ""
    keywords: tuple[str, ...] = ()
    dataset_refs: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def relative_path(self) -> str:
        try:
            return str(self.path.relative_to(self.root))
        except Exception:
            return self.path.name


@dataclass(frozen=True, slots=True)
class ScopedMemoryPruneCandidate:
    record: ScopedMemoryRecord
    reason: str


@dataclass(frozen=True, slots=True)
class ScopedMemoryPruneResult:
    root: Path
    scope: str
    apply_changes: bool
    candidates: tuple[ScopedMemoryPruneCandidate, ...] = ()
    deleted_count: int = 0


def _utc_now_iso(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.isoformat()


def normalize_scoped_memory_scope(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    normalized = _SCOPE_ALIASES.get(normalized, normalized)
    return normalized if normalized in SCOPED_MEMORY_SCOPES else ""


def normalize_scoped_memory_freshness(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    normalized = _FRESHNESS_ALIASES.get(normalized, normalized)
    return normalized if normalized in SCOPED_MEMORY_FRESHNESS_LEVELS else ""


def default_freshness_for_scope(scope: str) -> str:
    normalized_scope = normalize_scoped_memory_scope(scope) or DEFAULT_SCOPED_MEMORY_SCOPE
    return _DEFAULT_FRESHNESS_BY_SCOPE[normalized_scope]


def resolve_scoped_memory_root(
    *,
    workspace_dir: str = "",
    pipeline_workspace: str = "",
    root_dir: str | Path | None = None,
) -> Path | None:
    if root_dir is not None and str(root_dir).strip():
        return Path(root_dir).expanduser().resolve()

    anchor = str(pipeline_workspace or "").strip() or str(workspace_dir or "").strip()
    if not anchor:
        return None
    return Path(anchor).expanduser().resolve() / SCOPED_MEMORY_DIRNAME


def ensure_scoped_memory_root(
    *,
    workspace_dir: str = "",
    pipeline_workspace: str = "",
    root_dir: str | Path | None = None,
) -> Path | None:
    root = resolve_scoped_memory_root(
        workspace_dir=workspace_dir,
        pipeline_workspace=pipeline_workspace,
        root_dir=root_dir,
    )
    if root is None:
        return None
    root.mkdir(parents=True, exist_ok=True)
    return root


def derive_scoped_memory_title(body: str) -> str:
    text = " ".join(str(body or "").strip().split())
    if not text:
        return "Untitled memory"
    sentence = re.split(r"[.!?。！？]\s*", text, maxsplit=1)[0].strip() or text
    words = sentence.split()
    title = " ".join(words[:8]) if words else sentence
    title = title[:80].strip()
    return title or "Untitled memory"


def derive_scoped_memory_description(body: str) -> str:
    text = " ".join(str(body or "").strip().split())
    if not text:
        return ""
    sentence = re.split(r"[.!?。！？]\s*", text, maxsplit=1)[0].strip() or text
    return sentence[:140].strip()


def strip_scoped_memory_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", str(text or ""), count=1).strip()


def scoped_memory_markdown_from_record(record: ScopedMemoryRecord) -> str:
    frontmatter = {
        "memory_id": record.memory_id,
        "scope": record.scope,
        "title": record.title,
        "description": record.description,
        "owner": record.owner,
        "freshness": record.freshness,
        "updated_at": record.updated_at,
        "created_at": record.created_at,
    }
    if record.domain:
        frontmatter["domain"] = record.domain
    if record.keywords:
        frontmatter["keywords"] = list(record.keywords)
    if record.dataset_refs:
        frontmatter["dataset_refs"] = list(record.dataset_refs)

    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend(("---", "", record.body.strip(), ""))
    return "\n".join(lines)


def _slugify(value: str) -> str:
    lowered = str(value or "").strip().lower()
    if not lowered:
        return "memory"
    return _SLUG_RE.sub("-", lowered).strip("-") or "memory"


def write_scoped_memory(
    *,
    body: str,
    scope: str = DEFAULT_SCOPED_MEMORY_SCOPE,
    title: str = "",
    description: str = "",
    owner: str = "",
    freshness: str = "",
    domain: str = "",
    keywords: Iterable[str] = (),
    dataset_refs: Iterable[str] = (),
    workspace_dir: str = "",
    pipeline_workspace: str = "",
    root_dir: str | Path | None = None,
    now: datetime | None = None,
) -> ScopedMemoryRecord:
    normalized_scope = normalize_scoped_memory_scope(scope) or DEFAULT_SCOPED_MEMORY_SCOPE
    normalized_body = str(body or "").strip()
    if not normalized_body:
        raise ValueError("Scoped memory body cannot be empty.")

    root = ensure_scoped_memory_root(
        workspace_dir=workspace_dir,
        pipeline_workspace=pipeline_workspace,
        root_dir=root_dir,
    )
    if root is None:
        raise ValueError("Scoped memory requires an active workspace or pipeline workspace.")

    current_time = _utc_now_iso(now)
    normalized_title = str(title or "").strip() or derive_scoped_memory_title(normalized_body)
    normalized_description = (
        str(description or "").strip()
        or derive_scoped_memory_description(normalized_body)
    )
    normalized_owner = str(owner or "").strip() or "interactive"
    normalized_freshness = (
        normalize_scoped_memory_freshness(freshness)
        or default_freshness_for_scope(normalized_scope)
    )
    normalized_domain = str(domain or "").strip().lower()
    normalized_keywords = tuple(
        dict.fromkeys(
            token
            for token in (str(item).strip() for item in keywords)
            if token
        )
    )
    normalized_dataset_refs = tuple(
        dict.fromkeys(
            token
            for token in (str(item).strip() for item in dataset_refs)
            if token
        )
    )

    scope_dir = root / normalized_scope
    scope_dir.mkdir(parents=True, exist_ok=True)
    memory_id = uuid4().hex[:12]
    filename = f"{_slugify(normalized_title)}-{memory_id}.md"
    path = scope_dir / filename

    record = ScopedMemoryRecord(
        memory_id=memory_id,
        scope=normalized_scope,
        title=normalized_title,
        description=normalized_description,
        body=normalized_body,
        owner=normalized_owner,
        freshness=normalized_freshness,
        updated_at=current_time,
        created_at=current_time,
        path=path,
        root=root,
        domain=normalized_domain,
        keywords=normalized_keywords,
        dataset_refs=normalized_dataset_refs,
    )
    path.write_text(scoped_memory_markdown_from_record(record), encoding="utf-8")
    return record


def prune_scoped_memories(
    *,
    workspace_dir: str = "",
    pipeline_workspace: str = "",
    root_dir: str | Path | None = None,
    scope: str = "",
    stale_days: int | None = None,
    apply_changes: bool = False,
    now: datetime | None = None,
) -> ScopedMemoryPruneResult:
    from .scoped_memory_index import list_scoped_memory_records

    root = ensure_scoped_memory_root(
        workspace_dir=workspace_dir,
        pipeline_workspace=pipeline_workspace,
        root_dir=root_dir,
    )
    if root is None:
        raise ValueError("Scoped memory requires an active workspace or pipeline workspace.")

    normalized_scope = normalize_scoped_memory_scope(scope)
    records = list_scoped_memory_records(
        root,
        scope=normalized_scope,
        limit=0,
    )
    if not records:
        return ScopedMemoryPruneResult(
            root=root,
            scope=normalized_scope,
            apply_changes=apply_changes,
        )

    threshold_now = now or datetime.now(timezone.utc)
    candidates: list[ScopedMemoryPruneCandidate] = []
    fingerprint_latest: dict[tuple[str, str], ScopedMemoryRecord] = {}

    def _fingerprint(record: ScopedMemoryRecord) -> tuple[str, str]:
        body_key = re.sub(r"\s+", " ", record.body.strip().lower())
        return record.scope, f"{record.title.strip().lower()}::{body_key}"

    sorted_records = sorted(
        records,
        key=lambda item: (
            _parse_iso_datetime(item.updated_at) or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    for record in sorted_records:
        key = _fingerprint(record)
        existing = fingerprint_latest.get(key)
        if existing is None:
            fingerprint_latest[key] = record
            continue
        candidates.append(
            ScopedMemoryPruneCandidate(
                record=record,
                reason=f"duplicate of {existing.memory_id}",
            )
        )

    seen_paths = {candidate.record.path for candidate in candidates}
    for record in sorted_records:
        if record.path in seen_paths:
            continue
        age_limit = stale_days
        if age_limit is None:
            age_limit = _STALE_DAYS_BY_FRESHNESS.get(record.freshness, 120)
        updated_at = _parse_iso_datetime(record.updated_at)
        if updated_at is None:
            continue
        if updated_at > threshold_now - timedelta(days=age_limit):
            continue
        candidates.append(
            ScopedMemoryPruneCandidate(
                record=record,
                reason=f"stale {record.freshness} memory older than {age_limit} day(s)",
            )
        )

    deleted_count = 0
    if apply_changes:
        for candidate in candidates:
            try:
                candidate.record.path.unlink(missing_ok=True)
                deleted_count += 1
            except Exception:
                continue

    return ScopedMemoryPruneResult(
        root=root,
        scope=normalized_scope,
        apply_changes=apply_changes,
        candidates=tuple(candidates),
        deleted_count=deleted_count,
    )


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = [
    "DEFAULT_SCOPED_MEMORY_SCOPE",
    "SCOPED_MEMORY_DIRNAME",
    "SCOPED_MEMORY_FRESHNESS_LEVELS",
    "SCOPED_MEMORY_SCOPES",
    "ScopedMemoryPruneCandidate",
    "ScopedMemoryPruneResult",
    "ScopedMemoryRecord",
    "default_freshness_for_scope",
    "derive_scoped_memory_description",
    "derive_scoped_memory_title",
    "ensure_scoped_memory_root",
    "normalize_scoped_memory_freshness",
    "normalize_scoped_memory_scope",
    "prune_scoped_memories",
    "resolve_scoped_memory_root",
    "scoped_memory_markdown_from_record",
    "strip_scoped_memory_frontmatter",
    "write_scoped_memory",
]
