"""Index and scan helpers for scoped memory files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from omicsclaw.knowledge.registry import parse_frontmatter

from .scoped_memory import (
    ScopedMemoryRecord,
    normalize_scoped_memory_freshness,
    normalize_scoped_memory_scope,
    strip_scoped_memory_frontmatter,
)


@dataclass(frozen=True, slots=True)
class ScopedMemoryHeader:
    memory_id: str
    scope: str
    title: str
    description: str
    owner: str
    freshness: str
    updated_at: str
    created_at: str
    path: Path
    root: Path
    domain: str = ""
    keywords: tuple[str, ...] = ()
    dataset_refs: tuple[str, ...] = ()

    @property
    def relative_path(self) -> str:
        try:
            return str(self.path.relative_to(self.root))
        except Exception:
            return self.path.name


def load_scoped_memory_record(path: str | Path, *, root: str | Path | None = None) -> ScopedMemoryRecord | None:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        return None

    text = target.read_text(encoding="utf-8")
    metadata = parse_frontmatter(text)
    body = strip_scoped_memory_frontmatter(text)
    record_root = Path(root).expanduser().resolve() if root is not None else target.parent.parent

    scope = normalize_scoped_memory_scope(metadata.get("scope"))
    if not scope:
        return None

    title = str(metadata.get("title", "") or "").strip()
    memory_id = str(metadata.get("memory_id", "") or "").strip() or target.stem.rsplit("-", 1)[-1]
    description = str(metadata.get("description", "") or "").strip()
    owner = str(metadata.get("owner", "") or "").strip()
    freshness = normalize_scoped_memory_freshness(metadata.get("freshness")) or "evolving"
    updated_at = str(metadata.get("updated_at", "") or "").strip() or _stat_timestamp(target)
    created_at = str(metadata.get("created_at", "") or "").strip() or updated_at
    domain = str(metadata.get("domain", "") or "").strip().lower()
    keywords = _normalize_tuple(metadata.get("keywords"))
    dataset_refs = _normalize_tuple(metadata.get("dataset_refs"))
    extra_metadata = {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            "memory_id",
            "scope",
            "title",
            "description",
            "owner",
            "freshness",
            "updated_at",
            "created_at",
            "domain",
            "keywords",
            "dataset_refs",
        }
    }

    return ScopedMemoryRecord(
        memory_id=memory_id,
        scope=scope,
        title=title,
        description=description,
        body=body,
        owner=owner,
        freshness=freshness,
        updated_at=updated_at,
        created_at=created_at,
        path=target,
        root=record_root,
        domain=domain,
        keywords=keywords,
        dataset_refs=dataset_refs,
        metadata=extra_metadata,
    )


def scan_scoped_memory_headers(
    root: str | Path | None,
    *,
    scope: str = "",
    limit: int = 200,
) -> list[ScopedMemoryHeader]:
    if root is None:
        return []
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        return []

    normalized_scope = normalize_scoped_memory_scope(scope)
    patterns = [root_path / normalized_scope] if normalized_scope else [root_path]
    headers: list[ScopedMemoryHeader] = []
    for pattern_root in patterns:
        if not pattern_root.is_dir():
            continue
        for file_path in sorted(pattern_root.rglob("*.md")):
            record = load_scoped_memory_record(file_path, root=root_path)
            if record is None:
                continue
            headers.append(header_from_scoped_memory(record))

    headers.sort(
        key=lambda item: (
            _parse_iso_datetime(item.updated_at)
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    if limit > 0:
        return headers[:limit]
    return headers


def list_scoped_memory_records(
    root: str | Path | None,
    *,
    scope: str = "",
    query: str = "",
    limit: int = 20,
) -> list[ScopedMemoryRecord]:
    headers = scan_scoped_memory_headers(root, scope=scope, limit=0)
    records: list[ScopedMemoryRecord] = []
    for header in headers:
        record = load_scoped_memory_record(header.path, root=header.root)
        if record is None:
            continue
        if query and not matches_scoped_memory_query(record, query):
            continue
        records.append(record)
        if limit > 0 and len(records) >= limit:
            break
    return records


def matches_scoped_memory_query(record: ScopedMemoryRecord, query: str) -> bool:
    tokens = [token for token in str(query or "").lower().split() if token]
    if not tokens:
        return True
    haystack = " ".join(
        part
        for part in (
            record.scope,
            record.title,
            record.description,
            record.body,
            record.owner,
            record.freshness,
            record.domain,
            " ".join(record.keywords),
            " ".join(record.dataset_refs),
        )
        if part
    ).lower()
    return all(token in haystack for token in tokens)


def header_from_scoped_memory(record: ScopedMemoryRecord) -> ScopedMemoryHeader:
    return ScopedMemoryHeader(
        memory_id=record.memory_id,
        scope=record.scope,
        title=record.title,
        description=record.description,
        owner=record.owner,
        freshness=record.freshness,
        updated_at=record.updated_at,
        created_at=record.created_at,
        path=record.path,
        root=record.root,
        domain=record.domain,
        keywords=record.keywords,
        dataset_refs=record.dataset_refs,
    )


def _normalize_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = [str(item) for item in value]
    else:
        return ()
    return tuple(
        dict.fromkeys(
            item.strip()
            for item in values
            if str(item).strip()
        )
    )


def _stat_timestamp(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return datetime.now(timezone.utc).isoformat()


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = [
    "ScopedMemoryHeader",
    "header_from_scoped_memory",
    "list_scoped_memory_records",
    "load_scoped_memory_record",
    "matches_scoped_memory_query",
    "scan_scoped_memory_headers",
]
