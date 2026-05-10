# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false

"""MemoryEngine — namespace-aware hot path for memory writes and reads.

This module is the "engine room" of the OmicsClaw memory architecture.
It owns the canonical CRUD verbs over Node/Memory/Edge/Path and is the
only layer that touches those tables directly.

Above it sits ``MemoryClient`` (strategy: which namespace, version vs.
overwrite); below it sits the ORM. The legacy ``GraphService`` is
unaffected during PR #3a — see ``docs/2026-05-09-memory-refactor-plan.md``
for the full migration path.

Verbs landed in this PR (PR #3a):
    - upsert(uri, content, namespace, ...)
    - upsert_versioned(uri, content, namespace, ...)
    - patch_edge_metadata(uri, namespace, ...)

Verbs reserved for PR #3b:
    - recall(uri, namespace, ...)
    - search(query, namespace, ...)
    - list_children(uri, namespace)
    - get_subtree(uri, namespace, ...)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import select

from .models import Edge, Memory, Node, Path
from .uri import MemoryURI

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .search import SearchIndexer


@dataclass(frozen=True, slots=True)
class MemoryRef:
    """Pointer to a single materialized memory at one (namespace, uri)."""

    memory_id: int
    node_uuid: str
    namespace: str
    uri: str


@dataclass(frozen=True, slots=True)
class VersionedMemoryRef:
    """Result of a version-creating upsert.

    ``old_memory_id`` is ``None`` on the first write (no chain yet).
    """

    old_memory_id: Optional[int]
    new_memory_id: int
    node_uuid: str
    namespace: str
    uri: str


class MemoryEngine:
    """Namespace-aware CRUD over the memory graph.

    Constructed once per process and reused. Holds no per-namespace state —
    every verb takes ``namespace`` as a required argument.
    """

    def __init__(self, db: "DatabaseManager", search: "SearchIndexer") -> None:
        self._db = db
        self._search = search

    # ------------------------------------------------------------------
    # Write verbs (PR #3a)
    # ------------------------------------------------------------------

    async def upsert(
        self,
        uri: str | MemoryURI,
        content: str,
        *,
        namespace: str,
        priority: int = 0,
        disclosure: Optional[str] = None,
    ) -> MemoryRef:
        """Overwrite-mode upsert: create-or-replace the active memory at (namespace, uri).

        Re-calling with the same (uri, namespace) UPDATEs the existing
        Memory row's content in place — no deprecation chain, no new
        Memory row. Use this for ``dataset://`` and ``analysis://`` URIs
        where history is not interesting.
        """
        raise NotImplementedError("Task 3a.2")

    async def upsert_versioned(
        self,
        uri: str | MemoryURI,
        content: str,
        *,
        namespace: str,
        priority: int = 0,
        disclosure: Optional[str] = None,
    ) -> VersionedMemoryRef:
        """Versioned upsert: deprecate the old Memory, insert a new one.

        For ``core://*`` and ``preference://*`` URIs where the version
        chain is the audit trail. The old Memory keeps ``deprecated=True``
        and ``migrated_to=new_memory_id``; only the newest is active.
        """
        raise NotImplementedError("Task 3a.3")

    async def patch_edge_metadata(
        self,
        uri: str | MemoryURI,
        *,
        namespace: str,
        priority: Optional[int] = None,
        disclosure: Optional[str] = None,
    ) -> None:
        """Update Edge metadata (priority, disclosure) without touching Memory.

        At least one of ``priority``/``disclosure`` must be provided.
        """
        raise NotImplementedError("Task 3a.4")

    # ------------------------------------------------------------------
    # Read verbs (PR #3b)
    # ------------------------------------------------------------------

    async def recall(
        self,
        uri: str | MemoryURI,
        *,
        namespace: str,
        fallback_to_shared: bool = True,
    ) -> Optional[Any]:
        raise NotImplementedError("PR #3b")

    async def search(
        self,
        query: str,
        *,
        namespace: str,
        domain: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        raise NotImplementedError("PR #3b")

    async def list_children(
        self, uri: str | MemoryURI, *, namespace: str
    ) -> list[MemoryRef]:
        raise NotImplementedError("PR #3b")

    async def get_subtree(
        self,
        uri: str | MemoryURI,
        *,
        namespace: str,
        limit: int = 100,
    ) -> list[MemoryRef]:
        raise NotImplementedError("PR #3b")
