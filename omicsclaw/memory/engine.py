# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false

"""MemoryEngine — namespace-aware hot path for memory writes and reads.

This module is the "engine room" of the OmicsClaw memory architecture.
It owns the canonical CRUD verbs over Node/Memory/Edge/Path and is the
only layer that touches those tables directly.

Above it sits ``MemoryClient`` (strategy: which namespace, version vs.
overwrite); below it sits the ORM. The legacy ``GraphService`` is
unaffected during PR #3a/#3b — see ``docs/2026-05-09-memory-refactor-plan.md``
for the full migration path.

Write verbs (PR #3a):
    - upsert(uri, content, namespace, ...)
    - upsert_versioned(uri, content, namespace, ...)
    - patch_edge_metadata(uri, namespace, ...)
    - delete(uri, namespace)                  — subtree cascade with orphan prevention

Read verbs (PR #3b):
    - recall(uri, namespace, ...)             — single-row fetch with shared fallback
    - search(query, namespace, ...)           — FTS over (namespace, __shared__)
    - list_children(uri, namespace)           — strict-namespace children
    - get_subtree(uri, namespace, ...)        — flat listing under a prefix
    - get_recent(namespace, ...)              — recently-updated memory listing

Read-fallback policy (CONTEXT.md): ``recall`` and ``search`` fall back to
``__shared__`` so per-user contexts can see globally-shared content;
``list_children`` and ``get_subtree`` are strict so a user's listing
doesn't get polluted by shared structure they didn't ask for.
"""

from __future__ import annotations

import uuid as uuidlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

from sqlalchemy import and_, func, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ROOT_NODE_UUID,
    SHARED_NAMESPACE,
    ChangeCollector,
    Edge,
    Memory,
    Node,
    Path,
    escape_like_literal,
    serialize_row,
)
from .uri import MemoryURI

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .search import SearchIndexer


class _UnsetType:
    """Sentinel class for "argument was not supplied".

    Lets ``priority: int | None | _UnsetType`` distinguish
    "preserve the current value" (sentinel) from
    "set the value to None" (explicit None). A regular ``None`` default
    can't tell those apart.
    """

    _instance: Optional["_UnsetType"] = None

    def __new__(cls) -> "_UnsetType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "_UNSET"


_UNSET: _UnsetType = _UnsetType()

PriorityArg = Union[int, _UnsetType]
DisclosureArg = Union[Optional[str], _UnsetType]


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


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """Materialized result of ``recall``.

    ``namespace`` is the namespace the caller asked for; ``loaded_namespace``
    is the namespace the row actually came from. They differ when the read
    fell back to ``__shared__`` because the per-user namespace had no match.
    """

    memory_id: int
    node_uuid: str
    namespace: str
    uri: str
    content: str
    loaded_namespace: str


class MemoryEngine:
    """Namespace-aware CRUD over the memory graph.

    Constructed once per process and reused. Holds no per-namespace state —
    every verb takes ``namespace`` as a required argument.
    """

    def __init__(self, db: "DatabaseManager", search: "SearchIndexer") -> None:
        self._db = db
        self._search = search

    @property
    def db(self) -> "DatabaseManager":
        """The underlying ``DatabaseManager`` — exposed read-only so the
        client and review layers can run their own short queries without
        reaching into a private attribute."""
        return self._db

    @property
    def search_indexer(self) -> "SearchIndexer":
        """The underlying ``SearchIndexer``.

        Note: not named ``search`` because the engine has a ``search``
        verb (full-text query) that would shadow it.
        """
        return self._search

    # ------------------------------------------------------------------
    # Write verbs (PR #3a)
    # ------------------------------------------------------------------

    async def upsert(
        self,
        uri: str | MemoryURI,
        content: str,
        *,
        namespace: str,
        priority: PriorityArg = _UNSET,
        disclosure: DisclosureArg = _UNSET,
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
        priority: PriorityArg,
        disclosure: DisclosureArg,
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
            # Edge exists but no active memory: a deprecated chain might
            # exist with no successor (a crash window in upsert_versioned,
            # or a direct DB poke). We deliberately do NOT silently
            # fabricate a fresh active memory — that would disconnect a
            # deprecated tail from any successor and lose audit lineage.
            # Surface the corruption so callers can route to ReviewLog.
            raise RuntimeError(
                f"Path {path_row.namespace}/{path_row.domain}/{path_row.path} "
                f"has no active memory but the edge persists; refusing to "
                f"silently rebuild. Inspect the deprecated chain for node "
                f"{edge.child_uuid} and resolve via ReviewLog before retrying."
            )

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
        priority: PriorityArg,
        disclosure: DisclosureArg,
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

    async def _resolve_parent_node_uuid(
        self, s: AsyncSession, parsed: MemoryURI, namespace: str
    ) -> str:
        """Resolve the parent node UUID for a new path, with shared fallback.

        Top-level URIs (``core://agent``, ``analysis://sc-de``) attach to
        ROOT. Nested URIs require the parent path to exist either in the
        current namespace or in ``__shared__`` — falling back to shared
        lets a per-user write attach under a globally-known parent.
        """
        parent_uri = parsed.parent()
        if parent_uri is None or parent_uri.is_root:
            return ROOT_NODE_UUID

        uuid = await self._resolve_node_for_uri(s, parent_uri, namespace)
        if uuid is None:
            raise ValueError(
                f"Parent path {parent_uri} does not exist in namespace "
                f"{namespace!r} or '__shared__' — create the parent first."
            )
        return uuid

    @staticmethod
    async def _resolve_node_for_uri(
        s: AsyncSession, parsed: MemoryURI, namespace: str
    ) -> Optional[str]:
        """Look up the node UUID for ``parsed`` in ``(namespace, __shared__)``.

        Returns the first match's ``child_uuid`` (which is the conceptual
        node id), or ``None`` if neither namespace has the path. Used by
        both the write-side parent resolver and the read-side listing
        parent resolver — see CONTEXT.md for why the loop order matters
        (per-namespace match wins over a shared one).
        """
        for ns in (namespace, SHARED_NAMESPACE):
            path_row = (
                await s.execute(
                    select(Path).where(
                        Path.namespace == ns,
                        Path.domain == parsed.domain,
                        Path.path == parsed.path,
                    )
                )
            ).scalar_one_or_none()
            if path_row is None:
                continue
            edge = await s.get(Edge, path_row.edge_id)
            if edge is not None:
                return edge.child_uuid
        return None

    async def upsert_versioned(
        self,
        uri: str | MemoryURI,
        content: str,
        *,
        namespace: str,
        priority: PriorityArg = _UNSET,
        disclosure: DisclosureArg = _UNSET,
    ) -> VersionedMemoryRef:
        """Versioned upsert: deprecate the old Memory, insert a new one.

        For ``core://*`` and ``preference://*`` URIs where the version
        chain is the audit trail. The old Memory keeps ``deprecated=True``
        and ``migrated_to=new_memory_id``; only the newest is active.
        First write returns ``old_memory_id=None``.
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)
        canonical = str(parsed)

        async with self._db.session() as s:
            existing_path = await self._fetch_path(s, namespace, parsed)

            if existing_path is None:
                # No existing path: this is a first write — same shape as upsert
                # but routed through the versioned helper for return-type symmetry.
                new_memory_id, node_uuid = await self._upsert_create(
                    s, parsed, namespace, content, priority, disclosure
                )
                old_memory_id: Optional[int] = None
            else:
                old_memory_id, new_memory_id, node_uuid = (
                    await self._upsert_versioned_chain(
                        s, existing_path, content, priority, disclosure
                    )
                )

            await self._search.refresh_search_documents_for_node(
                node_uuid, session=s
            )

        return VersionedMemoryRef(
            old_memory_id=old_memory_id,
            new_memory_id=new_memory_id,
            node_uuid=node_uuid,
            namespace=namespace,
            uri=canonical,
        )

    async def _upsert_versioned_chain(
        self,
        s: AsyncSession,
        path_row: Path,
        content: str,
        priority: PriorityArg,
        disclosure: DisclosureArg,
    ) -> tuple[Optional[int], int, str]:
        """Insert a new active Memory and deprecate the previous active one.

        Returns ``(old_memory_id, new_memory_id, node_uuid)``. ``old_memory_id``
        is ``None`` only when no active Memory existed (orphan path), which
        we recover from by treating the new write as the chain's first link.
        """
        edge = await s.get(Edge, path_row.edge_id)
        if edge is None:
            raise RuntimeError(
                f"Path {path_row.namespace}/{path_row.domain}/{path_row.path} "
                f"references a missing edge — graph corruption."
            )
        node_uuid = edge.child_uuid

        old = (
            await s.execute(
                select(Memory)
                .where(
                    Memory.node_uuid == node_uuid,
                    Memory.deprecated == False,  # noqa: E712
                )
                .order_by(Memory.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        new_memory = Memory(node_uuid=node_uuid, content=content, deprecated=False)
        s.add(new_memory)
        await s.flush()

        old_id: Optional[int] = None
        if old is not None:
            old.deprecated = True
            old.migrated_to = new_memory.id
            old_id = old.id

        if priority is not _UNSET:
            edge.priority = priority
        if disclosure is not _UNSET:
            edge.disclosure = disclosure

        return old_id, new_memory.id, node_uuid

    async def delete(
        self,
        uri: str | MemoryURI,
        *,
        namespace: str,
    ) -> dict:
        """Delete a path and its namespace-scoped subtree.

        Soft-delete semantics: Memory rows on the deleted node are
        marked ``deprecated=True`` rather than physically removed, so
        the review pane can roll the version chain back. Path / Edge /
        Node structural rows are physically deleted.

        Pre-flight orphan check: if removing this prefix would leave a
        child node with no remaining incoming Path in any namespace,
        the call raises ``ValueError`` instead of creating an
        unreachable subgraph. The caller can re-route the child first
        and retry.

        Strict-namespace: only Path rows in ``namespace`` are touched.
        ``MemoryClient(namespace="A").forget(uri)`` cannot reach
        namespace ``"B"``.

        Returns ``{"rows_before": <ChangeCollector dict>, "rows_after": {}}``
        — same audit shape as the legacy ``GraphService.remove_path``
        so ``snapshot.get_changeset_store().record_many(...)`` keeps
        working unchanged for the desktop review pane.
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)
        if parsed.is_root or not parsed.path:
            raise ValueError("Cannot delete the root path.")

        async with self._db.session() as s:
            target = await self._delete_resolve_target(s, parsed, namespace)
            if target is None:
                raise ValueError(f"Path '{parsed}' not found")
            target_edge, target_node_uuid = target

            await self._delete_check_orphans(s, target_node_uuid, parsed)

            # Pre-collect node UUIDs whose search docs need rebuilding
            # AFTER the deletes complete. Done before mutation so the
            # query sees the pre-deletion structure. Cross-namespace by
            # design — search docs reflect current DB state regardless
            # of which namespace's Path was just removed.
            affected_nodes = await self._search.get_node_uuids_for_prefix(
                s, parsed.domain, parsed.path
            )

            collector = ChangeCollector()
            await self._delete_subtree_paths(s, parsed, namespace, collector)
            await s.flush()

            await self._delete_gc_edge_if_pathless(s, target_edge, collector)
            await self._delete_gc_node_soft(
                s, target_node_uuid, namespace, collector
            )

            for node_uuid in affected_nodes:
                await self._search.refresh_search_documents_for_node(
                    node_uuid, session=s
                )

        return {"rows_before": collector.to_dict(), "rows_after": {}}

    @staticmethod
    async def _delete_resolve_target(
        s: AsyncSession, parsed: MemoryURI, namespace: str
    ) -> Optional[tuple[Edge, str]]:
        """Find the Edge + child_uuid for ``(namespace, parsed)``."""
        row = (
            await s.execute(
                select(Path, Edge)
                .join(Edge, Path.edge_id == Edge.id)
                .where(
                    Path.namespace == namespace,
                    Path.domain == parsed.domain,
                    Path.path == parsed.path,
                )
            )
        ).first()
        if row is None:
            return None
        _, edge = row
        return edge, edge.child_uuid

    async def _delete_check_orphans(
        self, s: AsyncSession, target_node_uuid: str, parsed: MemoryURI
    ) -> None:
        """Refuse the delete if any direct child would lose its only
        incoming Path. Raises ``ValueError`` listing the would-orphan
        children so the caller can re-route them first.
        """
        child_edges = (
            await s.execute(
                select(Edge).where(Edge.parent_uuid == target_node_uuid)
            )
        ).scalars().all()

        would_orphan: list[Edge] = []
        for child_edge in child_edges:
            surviving = await self._delete_count_incoming_paths(
                s,
                child_edge.child_uuid,
                exclude_domain=parsed.domain,
                exclude_path_prefix=parsed.path,
            )
            if surviving == 0:
                would_orphan.append(child_edge)

        if would_orphan:
            details = ", ".join(
                f"'{e.name}' (node: {e.child_uuid[:8]}...)"
                for e in would_orphan
            )
            raise ValueError(
                f"Cannot remove '{parsed}': the following child node(s) "
                f"would become unreachable: {details}. Create alternative "
                f"paths for these children first, or remove them explicitly."
            )

    @staticmethod
    async def _delete_count_incoming_paths(
        s: AsyncSession,
        node_uuid: str,
        *,
        exclude_domain: str,
        exclude_path_prefix: str,
    ) -> int:
        """Count Paths whose Edge points TO ``node_uuid``, excluding
        Paths under the soon-to-be-deleted prefix (so the orphan
        precheck asks "would this child still have any path AFTER the
        delete completes")."""
        safe_prefix = escape_like_literal(exclude_path_prefix)
        stmt = (
            select(func.count())
            .select_from(Path)
            .join(Edge, Path.edge_id == Edge.id)
            .where(Edge.child_uuid == node_uuid)
            .where(
                not_(
                    and_(
                        Path.domain == exclude_domain,
                        Path.path.like(f"{safe_prefix}/%", escape="\\"),
                    )
                )
            )
        )
        return (await s.execute(stmt)).scalar() or 0

    @staticmethod
    async def _delete_subtree_paths(
        s: AsyncSession,
        parsed: MemoryURI,
        namespace: str,
        collector: ChangeCollector,
    ) -> None:
        """Delete every Path in ``namespace`` whose ``(domain, path)``
        matches the prefix or sits under it.

        Captures each row into the collector before deleting so the
        audit/changeset UI can reconstruct what was removed.
        """
        safe = escape_like_literal(parsed.path)
        stmt = (
            select(Path)
            .where(Path.namespace == namespace)
            .where(Path.domain == parsed.domain)
            .where(
                or_(
                    Path.path == parsed.path,
                    Path.path.like(f"{safe}/%", escape="\\"),
                )
            )
        )
        for p in (await s.execute(stmt)).scalars().all():
            collector.record("paths", serialize_row(p))
            await s.delete(p)

    @staticmethod
    async def _delete_gc_edge_if_pathless(
        s: AsyncSession,
        edge: Edge,
        collector: ChangeCollector,
    ) -> None:
        """Drop ``edge`` if no Path row references it after the subtree
        delete. Other Paths (aliases) reaching the same edge keep it
        alive."""
        remaining = (
            await s.execute(
                select(func.count())
                .select_from(Path)
                .where(Path.edge_id == edge.id)
            )
        ).scalar() or 0
        if remaining > 0:
            return
        collector.record("edges", serialize_row(edge))
        await s.delete(edge)

    async def _delete_gc_node_soft(
        self,
        s: AsyncSession,
        node_uuid: str,
        namespace: str,
        collector: ChangeCollector,
    ) -> None:
        """If ``node_uuid`` has no remaining incoming Path (any
        namespace), deprecate its active memories and cascade-clean
        edges around it.

        Soft semantics: Memory rows stay (with ``deprecated=True``) so
        the review pane can roll back. Edges incident to the now-dead
        node are physically deleted via ``_delete_gc_edge_if_pathless``
        / ``_delete_cascade_edge``.
        """
        still_reachable = (
            await s.execute(
                select(func.count())
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .where(Edge.child_uuid == node_uuid)
            )
        ).scalar() or 0
        if still_reachable > 0:
            return

        # Edges pointing TO this node (parents → us): drop pathless ones.
        incoming = (
            await s.execute(
                select(Edge).where(Edge.child_uuid == node_uuid)
            )
        ).scalars().all()
        for edge in incoming:
            await self._delete_gc_edge_if_pathless(s, edge, collector)

        # Edges pointing FROM this node (us → children): cascade-clean
        # the path forest under each. The orphan precheck guarantees
        # children survive through some other path; this just tidies
        # the namespace-scoped path rows we own here.
        outgoing = (
            await s.execute(
                select(Edge).where(Edge.parent_uuid == node_uuid)
            )
        ).scalars().all()
        for edge in outgoing:
            await self._delete_cascade_edge(s, edge, namespace, collector)

        # Snapshot active memories before deprecation so the audit log
        # can reconstruct what the user "forgot".
        active = (
            await s.execute(
                select(Memory).where(
                    Memory.node_uuid == node_uuid,
                    Memory.deprecated == False,  # noqa: E712
                )
            )
        ).scalars().all()
        for m in active:
            collector.record("memories", serialize_row(m))

        if active:
            await s.execute(
                update(Memory)
                .where(
                    Memory.node_uuid == node_uuid,
                    Memory.deprecated == False,  # noqa: E712
                )
                .values(deprecated=True)
            )

    async def _delete_cascade_edge(
        self,
        s: AsyncSession,
        edge: Edge,
        namespace: str,
        collector: ChangeCollector,
    ) -> None:
        """Strip ``namespace``-scoped Paths off ``edge`` and drop the
        edge itself when it falls pathless.

        Only acts inside ``namespace`` so an outgoing-edge cascade from
        a soft-GCed node cannot stray into another user's partition.
        """
        for p in (
            await s.execute(
                select(Path).where(
                    Path.edge_id == edge.id,
                    Path.namespace == namespace,
                )
            )
        ).scalars().all():
            collector.record("paths", serialize_row(p))
            await s.delete(p)

        await s.flush()
        await self._delete_gc_edge_if_pathless(s, edge, collector)

    async def patch_edge_metadata(
        self,
        uri: str | MemoryURI,
        *,
        namespace: str,
        priority: PriorityArg = _UNSET,
        disclosure: DisclosureArg = _UNSET,
    ) -> None:
        """Update Edge metadata (priority, disclosure) without touching Memory.

        At least one of ``priority``/``disclosure`` must be provided. Pass
        an explicit ``None`` to clear ``disclosure``. Memory rows and the
        version chain are untouched; the search_documents row is refreshed
        because priority and disclosure feed into search_terms.
        """
        if priority is _UNSET and disclosure is _UNSET:
            raise ValueError(
                "patch_edge_metadata requires at least one of priority "
                "or disclosure to be set."
            )

        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)

        async with self._db.session() as s:
            path_row = await self._fetch_path(s, namespace, parsed)
            if path_row is None:
                raise LookupError(
                    f"Path for {parsed} in namespace {namespace!r} not found."
                )
            edge = await s.get(Edge, path_row.edge_id)
            if edge is None:
                raise RuntimeError(
                    f"Path {namespace}/{parsed} references a missing edge "
                    f"— graph corruption."
                )

            if priority is not _UNSET:
                edge.priority = priority
            if disclosure is not _UNSET:
                edge.disclosure = disclosure

            await self._search.refresh_search_documents_for_node(
                edge.child_uuid, session=s
            )

    # ------------------------------------------------------------------
    # Read verbs (PR #3b)
    # ------------------------------------------------------------------

    async def recall(
        self,
        uri: str | MemoryURI,
        *,
        namespace: str,
        fallback_to_shared: bool = True,
    ) -> Optional[MemoryRecord]:
        """Fetch the active memory at ``(namespace, uri)``.

        Returns ``None`` if no active memory exists. When the per-namespace
        lookup misses and ``fallback_to_shared=True`` (the default), falls
        back to ``__shared__`` — this is how per-user contexts see
        globally-shared content like ``core://agent``.

        ``MemoryRecord.loaded_namespace`` records which namespace produced
        the row (the caller-supplied one or ``__shared__``).
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)
        canonical = str(parsed)

        async with self._db.session() as s:
            record = await self._recall_in_namespace(s, parsed, canonical, namespace)
            if record is not None:
                return record

            if (
                fallback_to_shared
                and namespace != SHARED_NAMESPACE
            ):
                shared = await self._recall_in_namespace(
                    s, parsed, canonical, SHARED_NAMESPACE
                )
                if shared is not None:
                    # Echo the caller's requested namespace; tag origin separately.
                    return MemoryRecord(
                        memory_id=shared.memory_id,
                        node_uuid=shared.node_uuid,
                        namespace=namespace,
                        uri=canonical,
                        content=shared.content,
                        loaded_namespace=SHARED_NAMESPACE,
                    )

        return None

    async def _recall_in_namespace(
        self,
        s: AsyncSession,
        parsed: MemoryURI,
        canonical: str,
        namespace: str,
    ) -> Optional[MemoryRecord]:
        """Fetch the active memory for ``(namespace, parsed)`` or ``None``."""
        path_row = await self._fetch_path(s, namespace, parsed)
        if path_row is None:
            return None

        edge = await s.get(Edge, path_row.edge_id)
        if edge is None:
            return None

        memory = (
            await s.execute(
                select(Memory)
                .where(
                    Memory.node_uuid == edge.child_uuid,
                    Memory.deprecated == False,  # noqa: E712
                )
                .order_by(Memory.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if memory is None:
            return None

        return MemoryRecord(
            memory_id=memory.id,
            node_uuid=edge.child_uuid,
            namespace=namespace,
            uri=canonical,
            content=memory.content,
            loaded_namespace=namespace,
        )

    async def search(
        self,
        query: str,
        *,
        namespace: str,
        domain: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Full-text search restricted to ``namespace`` + ``__shared__``.

        Per-namespace hits are returned ahead of shared hits when scores
        are otherwise comparable. Each result dict carries a
        ``namespace`` key indicating which partition the hit came from.
        """
        return await self._search.search(
            query, limit=limit, domain=domain, namespace=namespace
        )

    async def list_children(
        self, uri: str | MemoryURI, *, namespace: str
    ) -> list[MemoryRef]:
        """List direct children of ``uri`` strictly inside ``namespace``.

        Strict semantics: a child only appears if it has a Path in
        ``namespace``. Shared children of the same parent are intentionally
        invisible — use ReviewLog.browse_shared (PR #4b) to see those.

        The parent itself can live in ``namespace`` or in ``__shared__``;
        we resolve the parent through the same fallback the writer uses,
        so per-user children of shared parents (e.g., ``core://agent/style``
        under shared ``core://agent``) list correctly.
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)

        async with self._db.session() as s:
            parent_uuid = await self._resolve_listing_parent(s, parsed, namespace)
            if parent_uuid is None:
                return []

            child_edges = (
                await s.execute(
                    select(Edge).where(Edge.parent_uuid == parent_uuid)
                )
            ).scalars().all()
            if not child_edges:
                return []

            edge_id_to_child_uuid = {e.id: e.child_uuid for e in child_edges}
            edge_ids = list(edge_id_to_child_uuid)

            path_rows = (
                await s.execute(
                    select(Path)
                    .where(
                        Path.namespace == namespace,
                        Path.edge_id.in_(edge_ids),
                    )
                    .order_by(Path.path)
                )
            ).scalars().all()

            return await self._materialize_listing(
                s, path_rows, edge_id_to_child_uuid, namespace
            )

    async def _resolve_listing_parent(
        self, s: AsyncSession, parsed: MemoryURI, namespace: str
    ) -> Optional[str]:
        """Return the parent's child_uuid, or ``None`` if the path is missing.

        For root URIs (path=""), returns ``ROOT_NODE_UUID`` directly.
        Listing through a missing parent returns no children — strict
        listings don't fail loudly, they just produce nothing.
        """
        if parsed.is_root:
            return ROOT_NODE_UUID
        return await self._resolve_node_for_uri(s, parsed, namespace)

    async def _materialize_listing(
        self,
        s: AsyncSession,
        path_rows: list[Path],
        edge_id_to_child_uuid: dict[int, str],
        namespace: str,
    ) -> list[MemoryRef]:
        """Turn a list of Path rows into MemoryRef objects.

        Shared by ``list_children`` and ``get_subtree``. Active-memory
        lookup is batched to a single query so a 1000-row subtree pays
        for 2 queries (one for paths, one for memories) instead of 1001.
        Rows whose node has no active memory (a deprecated chain with no
        successor) are silently skipped — surface nothing rather than a
        half-result.
        """
        if not path_rows:
            return []

        unique_uuids = {edge_id_to_child_uuid[p.edge_id] for p in path_rows}
        memory_rows = (
            await s.execute(
                select(Memory.node_uuid, Memory.id).where(
                    Memory.node_uuid.in_(unique_uuids),
                    Memory.deprecated == False,  # noqa: E712
                )
            )
        ).all()

        # Pick max id per node — newest active wins on the rare path with
        # multiple non-deprecated rows (shouldn't happen post-3a but the
        # code is defensive at minimal cost).
        active_by_node: dict[str, int] = {}
        for node_uuid, mid in memory_rows:
            if mid > active_by_node.get(node_uuid, -1):
                active_by_node[node_uuid] = mid

        results: list[MemoryRef] = []
        for path_row in path_rows:
            child_uuid = edge_id_to_child_uuid[path_row.edge_id]
            memory_id = active_by_node.get(child_uuid)
            if memory_id is None:
                continue
            results.append(
                MemoryRef(
                    memory_id=memory_id,
                    node_uuid=child_uuid,
                    namespace=namespace,
                    uri=f"{path_row.domain}://{path_row.path}",
                )
            )
        return results

    async def get_subtree(
        self,
        uri: str | MemoryURI,
        *,
        namespace: str,
        limit: int = 100,
    ) -> list[MemoryRef]:
        """Flat list of MemoryRef under ``(namespace, uri)`` up to ``limit``.

        Includes the prefix URI itself plus all descendants. Strict
        namespace — no shared fallback. Sorted lexicographically by path
        for deterministic output. A root URI (``analysis://``) lists every
        path in the namespace under that domain.
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)

        async with self._db.session() as s:
            stmt = select(Path).where(
                Path.namespace == namespace,
                Path.domain == parsed.domain,
            )
            if not parsed.is_root:
                base = parsed.path
                safe = escape_like_literal(base)
                stmt = stmt.where(
                    or_(
                        Path.path == base,
                        Path.path.like(f"{safe}/%", escape="\\"),
                    )
                )
            stmt = stmt.order_by(Path.path).limit(limit)
            path_rows = (await s.execute(stmt)).scalars().all()
            if not path_rows:
                return []

            edge_ids = [p.edge_id for p in path_rows]
            edges = (
                await s.execute(select(Edge).where(Edge.id.in_(edge_ids)))
            ).scalars().all()
            edge_id_to_child = {e.id: e.child_uuid for e in edges}

            return await self._materialize_listing(
                s, list(path_rows), edge_id_to_child, namespace
            )

    async def get_recent(
        self,
        *,
        namespace: str,
        limit: int = 10,
        include_shared: bool = False,
    ) -> list[dict]:
        """Return recently-updated active memories scoped to ``namespace``.

        Strict by default: only rows whose Path is in ``namespace`` show
        up — same rule as ``list_children`` and ``get_subtree``. Pass
        ``include_shared=True`` for the desktop UI mode that also surfaces
        ``__shared__`` rows (so user-customised ``core://agent/*`` shows
        up in the recent listing alongside per-user writes).

        Output dict shape mirrors the legacy
        ``GraphService.get_recent_memories`` so the call sites that swap
        over need no result-shape changes.

        Note: this verb is intentionally namespace-required — engine reads
        always carry a partition. The legacy ``namespace=None`` admin
        mode lives in ``GraphService.get_recent_memories`` and remains
        for ``oc memory-server``-style admin tooling.
        """
        async with self._db.session() as s:
            stmt = (
                select(Memory, Edge, Path)
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .join(
                    Memory,
                    and_(
                        Memory.node_uuid == Edge.child_uuid,
                        Memory.deprecated == False,  # noqa: E712
                    ),
                )
                .order_by(Memory.created_at.desc())
            )
            if include_shared:
                stmt = stmt.where(
                    Path.namespace.in_([namespace, SHARED_NAMESPACE])
                )
            else:
                stmt = stmt.where(Path.namespace == namespace)

            rows = (await s.execute(stmt)).all()

            seen: set[int] = set()
            results: list[dict] = []
            for memory, edge, path_obj in rows:
                if memory.id in seen:
                    continue
                seen.add(memory.id)
                results.append(
                    {
                        "memory_id": memory.id,
                        "uri": f"{path_obj.domain}://{path_obj.path}",
                        "priority": edge.priority,
                        "disclosure": edge.disclosure,
                        "created_at": memory.created_at.isoformat()
                        if memory.created_at
                        else None,
                    }
                )
                if len(results) >= limit:
                    break
            return results
