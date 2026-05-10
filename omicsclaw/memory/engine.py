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

import uuid as uuidlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ROOT_NODE_UUID, Edge, Memory, Node, Path
from .uri import MemoryURI

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .search import SearchIndexer

_UNSET: Any = object()


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
        priority: Any = _UNSET,
        disclosure: Any = _UNSET,
    ) -> MemoryRef:
        """Overwrite-mode upsert: create-or-replace the active memory at (namespace, uri).

        Re-calling with the same (uri, namespace) UPDATEs the existing
        Memory row's content in place — no deprecation chain, no new
        Memory row. Use this for ``dataset://`` and ``analysis://`` URIs
        where history is not interesting.

        ``priority`` and ``disclosure`` use a sentinel so an update call
        without them preserves the existing edge's metadata; pass an
        explicit ``None`` (or any value) to overwrite.
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)
        canonical = str(parsed)

        async with self._db.session() as s:
            existing_path = await self._fetch_path(s, namespace, parsed)

            if existing_path is not None:
                memory_id, node_uuid = await self._upsert_existing(
                    s, existing_path, content, priority, disclosure
                )
            else:
                memory_id, node_uuid = await self._upsert_create(
                    s, parsed, namespace, content, priority, disclosure
                )

            await self._search.refresh_search_documents_for_node(
                node_uuid, session=s
            )

        return MemoryRef(
            memory_id=memory_id,
            node_uuid=node_uuid,
            namespace=namespace,
            uri=canonical,
        )

    # ------------------------------------------------------------------
    # Internal helpers (kept private — tests should drive only via verbs)
    # ------------------------------------------------------------------

    @staticmethod
    async def _fetch_path(
        s: AsyncSession, namespace: str, parsed: MemoryURI
    ) -> Optional[Path]:
        return (
            await s.execute(
                select(Path).where(
                    Path.namespace == namespace,
                    Path.domain == parsed.domain,
                    Path.path == parsed.path,
                )
            )
        ).scalar_one_or_none()

    async def _upsert_existing(
        self,
        s: AsyncSession,
        path_row: Path,
        content: str,
        priority: Any,
        disclosure: Any,
    ) -> tuple[int, str]:
        edge = await s.get(Edge, path_row.edge_id)
        if edge is None:
            raise RuntimeError(
                f"Path {path_row.namespace}/{path_row.domain}/{path_row.path} "
                f"references a missing edge — graph corruption."
            )

        memory = (
            await s.execute(
                select(Memory)
                .where(
                    Memory.node_uuid == edge.child_uuid,
                    Memory.deprecated == False,  # noqa: E712 — SQLAlchemy column comparison
                )
                .order_by(Memory.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if memory is None:
            # Edge exists but has no active memory — create one and attach.
            memory = Memory(
                node_uuid=edge.child_uuid, content=content, deprecated=False
            )
            s.add(memory)
            await s.flush()
        else:
            memory.content = content

        if priority is not _UNSET:
            edge.priority = priority
        if disclosure is not _UNSET:
            edge.disclosure = disclosure

        return memory.id, edge.child_uuid

    async def _upsert_create(
        self,
        s: AsyncSession,
        parsed: MemoryURI,
        namespace: str,
        content: str,
        priority: Any,
        disclosure: Any,
    ) -> tuple[int, str]:
        parent_uuid = await self._resolve_parent_node_uuid(s, parsed, namespace)

        node_uuid = str(uuidlib.uuid4())
        s.add(Node(uuid=node_uuid))
        await s.flush()

        memory = Memory(node_uuid=node_uuid, content=content, deprecated=False)
        s.add(memory)
        await s.flush()

        edge_name = parsed.path.rsplit("/", 1)[-1] if "/" in parsed.path else parsed.path
        edge = Edge(
            parent_uuid=parent_uuid,
            child_uuid=node_uuid,
            name=edge_name,
            priority=0 if priority is _UNSET else priority,
            disclosure=None if disclosure is _UNSET else disclosure,
        )
        s.add(edge)
        await s.flush()

        s.add(
            Path(
                namespace=namespace,
                domain=parsed.domain,
                path=parsed.path,
                edge_id=edge.id,
            )
        )
        await s.flush()

        return memory.id, node_uuid

    @staticmethod
    async def _resolve_parent_node_uuid(
        s: AsyncSession, parsed: MemoryURI, namespace: str
    ) -> str:
        """Resolve the parent node UUID for a new path, with shared fallback.

        Top-level URIs (``core://agent``, ``analysis://sc-de``) attach to
        ROOT. Nested URIs require the parent path to exist either in the
        current namespace or in ``__shared__``. Falling back to shared lets
        a per-user write attach under a globally-known structural parent.
        """
        parent_uri = parsed.parent()
        if parent_uri is None or parent_uri.is_root:
            return ROOT_NODE_UUID

        for ns in (namespace, "__shared__"):
            parent_path = (
                await s.execute(
                    select(Path).where(
                        Path.namespace == ns,
                        Path.domain == parent_uri.domain,
                        Path.path == parent_uri.path,
                    )
                )
            ).scalar_one_or_none()
            if parent_path is None:
                continue
            parent_edge = await s.get(Edge, parent_path.edge_id)
            if parent_edge is not None:
                return parent_edge.child_uuid

        raise ValueError(
            f"Parent path {parent_uri} does not exist in namespace "
            f"{namespace!r} or '__shared__' — create the parent first."
        )

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
