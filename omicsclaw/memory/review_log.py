# pyright: reportArgumentType=false, reportCallIssue=false, reportOperatorIssue=false

"""ReviewLog — namespace-aware cold path for memory review and audit.

Sits next to ``MemoryEngine``: where the engine is the **hot** path
(reads + writes per request), ReviewLog is the **cold** path — the
operations the desktop "Review & Audit" pane needs and the bot's
``/forget`` command will eventually call:

  * version-chain inspection / rollback
  * orphan + GC
  * browse_shared
  * pending-changes list / approve / discard

Constructed once per process; takes the same ``DatabaseManager`` and
``MemoryEngine`` as the rest of the layer. Optionally takes a
``ChangesetStore`` override for test isolation; in production it falls
through to the global singleton from ``snapshot.get_changeset_store``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa

from .engine import MemoryEngine, MemoryRef
from .models import (
    Edge,
    GlossaryKeyword,
    Memory,
    Node,
    Path,
    ROOT_NODE_UUID,
    SHARED_NAMESPACE,
    serialize_memory_ref,
    serialize_row,
)
from .namespace_policy import should_version
from .uri import MemoryURI

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .snapshot import ChangesetStore


class NoVersionHistoryError(RuntimeError):
    """Raised when an operation requires a version chain but the URI is
    overwrite-only (``dataset://``, ``analysis://``)."""


@dataclass(frozen=True, slots=True)
class VersionEntry:
    """One row in a memory's version chain, ordered oldest → newest."""

    memory_id: int
    deprecated: bool
    migrated_to: Optional[int]
    content: str
    created_at: Optional[datetime]
    namespace: str
    uri: str


@dataclass(frozen=True, slots=True)
class OrphanEntry:
    """A deprecated Memory whose successor was deleted, leaving no active
    head — the chain is broken at this row."""

    memory_id: int
    node_uuid: str
    deprecated: bool
    migrated_to: Optional[int]
    namespace: Optional[str]
    uri: Optional[str]
    created_at: Optional[datetime]


@dataclass(frozen=True, slots=True)
class RollbackResult:
    restored_memory_id: int
    node_uuid: str
    was_already_active: bool


class ReviewLog:
    """Namespace-aware cold-path operations.

    All write verbs leave ``snapshot.ChangesetStore`` updated so the
    review pane stays consistent with the live DB.
    """

    def __init__(
        self,
        db: "DatabaseManager",
        engine: MemoryEngine,
        *,
        changeset_store: Optional["ChangesetStore"] = None,
    ) -> None:
        self._db = db
        self._engine = engine
        self._changeset_override = changeset_store

    def _store(self) -> "ChangesetStore":
        if self._changeset_override is not None:
            return self._changeset_override
        from .snapshot import get_changeset_store

        return get_changeset_store()

    # ------------------------------------------------------------------
    # 4b.2 — version chain
    # ------------------------------------------------------------------

    async def list_version_chain(
        self, uri: str | MemoryURI, *, namespace: str
    ) -> list[VersionEntry]:
        """Return the chain in age order (oldest → newest = active head).

        Raises ``NoVersionHistoryError`` if the URI is overwrite-only —
        ``dataset://`` and ``analysis://`` URIs structurally cannot have
        a chain, so an empty-list return would be misleading. Returns
        an empty list when the URI is versioned but currently has no
        rows (path doesn't exist yet).
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)
        if not should_version(parsed):
            raise NoVersionHistoryError(
                f"URI {parsed} is not versioned — version chain not applicable."
            )

        async with self._db.session() as s:
            path_row = await self._fetch_path(s, namespace, parsed)
            if path_row is None:
                return []

            edge = await s.get(Edge, path_row.edge_id)
            if edge is None:
                return []

            rows = (
                await s.execute(
                    sa.select(Memory)
                    .where(Memory.node_uuid == edge.child_uuid)
                    .order_by(Memory.id)
                )
            ).scalars().all()

            return [
                VersionEntry(
                    memory_id=r.id,
                    deprecated=bool(r.deprecated),
                    migrated_to=r.migrated_to,
                    content=r.content,
                    created_at=r.created_at,
                    namespace=namespace,
                    uri=str(parsed),
                )
                for r in rows
            ]

    async def rollback_to(
        self, memory_id: int, *, namespace: str
    ) -> RollbackResult:
        """Make ``memory_id`` the active head of its chain.

        Deprecates everything else on the same node and clears the
        new active row's ``migrated_to`` pointer. Returns the rollback
        result with ``was_already_active=True`` when the target is
        already the head (idempotent).
        """
        async with self._db.session() as s:
            target = await s.get(Memory, memory_id)
            if target is None:
                raise ValueError(f"Memory ID {memory_id} not found")

            if not target.deprecated:
                return RollbackResult(
                    restored_memory_id=memory_id,
                    node_uuid=target.node_uuid,
                    was_already_active=True,
                )

            # Mark every other memory on this node deprecated with
            # migrated_to pointing at the new active head.
            await s.execute(
                sa.update(Memory)
                .where(
                    Memory.node_uuid == target.node_uuid,
                    Memory.id != memory_id,
                    Memory.deprecated == False,  # noqa: E712
                )
                .values(deprecated=True, migrated_to=memory_id)
            )
            await s.execute(
                sa.update(Memory)
                .where(Memory.id == memory_id)
                .values(deprecated=False, migrated_to=None)
            )

            await self._engine.search_indexer.refresh_search_documents_for_node(
                target.node_uuid, session=s
            )

        return RollbackResult(
            restored_memory_id=memory_id,
            node_uuid=target.node_uuid,
            was_already_active=False,
        )

    # ------------------------------------------------------------------
    # 4b.3 — orphans + GC
    # ------------------------------------------------------------------

    async def list_orphans(
        self, *, namespace: Optional[str] = None
    ) -> list[OrphanEntry]:
        """Find deprecated memories whose successor row has been deleted.

        ``namespace=None`` scans every partition (admin view). Otherwise
        restricts to the given namespace via the path join.
        """
        async with self._db.session() as s:
            stmt = (
                sa.select(
                    Memory.id,
                    Memory.node_uuid,
                    Memory.deprecated,
                    Memory.migrated_to,
                    Memory.created_at,
                    Path.namespace,
                    Path.domain,
                    Path.path,
                )
                .select_from(Memory)
                .outerjoin(Edge, Edge.child_uuid == Memory.node_uuid)
                .outerjoin(Path, Path.edge_id == Edge.id)
                .where(Memory.deprecated == True)  # noqa: E712
            )
            if namespace is not None:
                stmt = stmt.where(Path.namespace == namespace)
            rows = (await s.execute(stmt)).all()

            # Distinct memory_ids (a memory with multiple Paths produces
            # multiple rows) — we want one OrphanEntry per memory.
            seen: set[int] = set()
            entries: list[OrphanEntry] = []
            for memory_id, node_uuid, deprecated, migrated_to, created_at, ns, domain, path in rows:
                # Filter to true orphans: migrated_to either NULL or
                # points at a memory that no longer exists.
                if migrated_to is not None:
                    successor = await s.get(Memory, migrated_to)
                    if successor is not None and not successor.deprecated:
                        continue
                if memory_id in seen:
                    continue
                seen.add(memory_id)
                uri = (
                    f"{domain}://{path}"
                    if domain is not None and path is not None
                    else None
                )
                entries.append(
                    OrphanEntry(
                        memory_id=memory_id,
                        node_uuid=node_uuid,
                        deprecated=bool(deprecated),
                        migrated_to=migrated_to,
                        namespace=ns,
                        uri=uri,
                        created_at=created_at,
                    )
                )
        return entries

    async def cascade_delete(
        self, uri: str | MemoryURI, *, namespace: str
    ) -> dict:
        """Delete a path + its edge + its node + every memory on the node.

        Strict-namespace: only touches the row at ``(namespace, uri)``;
        other namespaces' rows at the same URI are untouched. Returns a
        summary dict with the counts removed.
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)
        async with self._db.session() as s:
            path_row = await self._fetch_path(s, namespace, parsed)
            if path_row is None:
                return {
                    "deleted": False,
                    "namespace": namespace,
                    "uri": str(parsed),
                }
            edge = await s.get(Edge, path_row.edge_id)
            if edge is None:
                return {
                    "deleted": False,
                    "namespace": namespace,
                    "uri": str(parsed),
                }

            node_uuid = edge.child_uuid

            # Delete the Path first (frees the structural alias).
            await s.execute(
                sa.delete(Path).where(
                    Path.namespace == namespace,
                    Path.domain == parsed.domain,
                    Path.path == parsed.path,
                )
            )
            # If no other Path references this edge, drop the edge,
            # node, and memories.
            other_paths = (
                await s.execute(
                    sa.select(sa.func.count())
                    .select_from(Path)
                    .where(Path.edge_id == edge.id)
                )
            ).scalar_one()
            removed_memories = 0
            if other_paths == 0:
                await s.execute(sa.delete(Edge).where(Edge.id == edge.id))
                # Remove memories on the node (no path reaches them now).
                deleted = await s.execute(
                    sa.delete(Memory).where(Memory.node_uuid == node_uuid)
                )
                removed_memories = deleted.rowcount or 0
                # Refresh search index so the now-gone rows disappear.
                await self._engine.search_indexer._delete_search_documents_for_node(
                    s, node_uuid
                )

        return {
            "deleted": True,
            "namespace": namespace,
            "uri": str(parsed),
            "memories_removed": removed_memories,
        }

    async def gc_pathless_edges(self) -> int:
        """Drop edges that have no Path row referencing them, in any namespace.

        These accumulate from interrupted writes or manual DB pokes.
        Returns the number of edges removed.

        Note: this operates globally on purpose. Edges aren't namespaced
        — they describe structural parent→child relationships between
        nodes, and a single edge can be referenced by Paths from multiple
        namespaces (the alias mechanism). A per-namespace GC would have
        to delete edges that A's Paths don't reference, which would
        silently destroy B's data. Global is the only safe scope.
        """
        async with self._db.session() as s:
            referenced_rows = (
                await s.execute(sa.select(Path.edge_id).distinct())
            ).scalars().all()
            # SQL "x NOT IN (..., NULL, ...)" returns UNKNOWN for every row,
            # which makes the DELETE a no-op. Filter NULLs explicitly so a
            # Path with edge_id IS NULL doesn't poison the subquery.
            referenced_ids = [eid for eid in referenced_rows if eid is not None]

            stmt = sa.delete(Edge)
            if referenced_ids:
                stmt = stmt.where(Edge.id.notin_(referenced_ids))
            removed = await s.execute(stmt)
            return removed.rowcount or 0

    # ------------------------------------------------------------------
    # 4b.4 — browse_shared
    # ------------------------------------------------------------------

    async def browse_shared(
        self, uri: str | MemoryURI = "core://"
    ) -> list[MemoryRef]:
        """List children of ``uri`` strictly inside ``__shared__``.

        Used by the desktop UI when the user wants to see globally-known
        content (KnowHow seeds, agent defaults). Sugar for
        ``engine.list_children(uri, namespace='__shared__')``.
        """
        return await self._engine.list_children(uri, namespace=SHARED_NAMESPACE)

    # ------------------------------------------------------------------
    # 4b.5 — changesets
    # ------------------------------------------------------------------

    async def list_pending_changes(self) -> list[dict]:
        """Return the rows pending review across all namespaces.

        The current ``ChangesetStore`` doesn't record namespace per row,
        so a per-namespace filter would silently drop everything. PR #5
        will add the column once surfaces wire namespace through the
        record-many call; until then this is global.
        """
        store = self._store()
        return store.get_changed_rows()

    async def approve_changes(
        self, change_ids: Optional[list[str]] = None
    ) -> int:
        """Mark rows as integrated and remove them from the pending pool.

        Without ``change_ids`` clears every pending row (common case for
        the "approve all" UI button). Returns the count cleared.
        """
        store = self._store()
        if change_ids:
            return store.remove_keys(change_ids)
        return store.clear_all()

    async def discard_pending_changes(self) -> int:
        """Drop every pending row without integrating. Returns count dropped."""
        return self._store().discard_all()

    # ------------------------------------------------------------------
    # Desktop maintenance pane: dict-shaped orphan operations.
    #
    # These mirror the legacy GraphService contract used by
    # ``/api/maintenance/*``. The shape is preserved so the existing
    # frontend keeps working without changes; Phase 2a routed the API
    # off GraphService onto these methods. Phase 3 will delete the
    # GraphService copy once review.py and browse.py also migrate.
    # ------------------------------------------------------------------

    _SNIPPET_LIMIT: int = 200

    async def list_orphans_with_chain(self) -> list[dict]:
        """Return every deprecated memory with migration-target context.

        Each entry carries ``id, content_snippet, created_at, deprecated,
        migrated_to, category, migration_target``. ``category`` is
        ``"deprecated"`` when ``migrated_to`` is set, else ``"orphaned"``.
        ``migration_target`` contains the chain head's id/paths/snippet
        when the chain still resolves, otherwise ``None``.
        """
        orphans: list[dict] = []
        async with self._db.session() as s:
            rows = (
                await s.execute(
                    sa.select(Memory)
                    .where(Memory.deprecated == True)  # noqa: E712
                    .order_by(Memory.created_at.desc())
                )
            ).scalars().all()

            for memory in rows:
                category = (
                    "deprecated" if memory.migrated_to else "orphaned"
                )
                snippet = self._snippet(memory.content)
                item: dict = {
                    "id": memory.id,
                    "content_snippet": snippet,
                    "created_at": (
                        memory.created_at.isoformat()
                        if memory.created_at
                        else None
                    ),
                    "deprecated": True,
                    "migrated_to": memory.migrated_to,
                    "category": category,
                    "migration_target": None,
                }
                if memory.migrated_to:
                    target = await self._resolve_migration_chain(
                        s, memory.migrated_to
                    )
                    if target is not None:
                        item["migration_target"] = {
                            "id": target["id"],
                            "paths": target["paths"],
                            "content_snippet": target["content_snippet"],
                        }
                orphans.append(item)
        return orphans

    async def get_orphan_detail(self, memory_id: int) -> Optional[dict]:
        """Return the full body + chain context for one memory id.

        Returns ``None`` if the id doesn't exist. Used by the desktop
        "view orphan" dialog. ``category`` is one of ``"active"``,
        ``"deprecated"``, ``"orphaned"`` so the dialog can pick the
        right banner.
        """
        async with self._db.session() as s:
            memory = (
                await s.execute(
                    sa.select(Memory).where(Memory.id == memory_id)
                )
            ).scalar_one_or_none()
            if memory is None:
                return None

            if not memory.deprecated:
                category = "active"
            elif memory.migrated_to:
                category = "deprecated"
            else:
                category = "orphaned"

            detail: dict = {
                "id": memory.id,
                "content": memory.content,
                "created_at": (
                    memory.created_at.isoformat()
                    if memory.created_at
                    else None
                ),
                "deprecated": memory.deprecated,
                "migrated_to": memory.migrated_to,
                "category": category,
                "migration_target": None,
            }
            if memory.migrated_to:
                target = await self._resolve_migration_chain(
                    s, memory.migrated_to
                )
                if target is not None:
                    detail["migration_target"] = {
                        "id": target["id"],
                        "content": target["content"],
                        "paths": target["paths"],
                        "created_at": target["created_at"],
                    }
            return detail

    async def permanently_delete_orphan(self, memory_id: int) -> dict:
        """Hard-delete a deprecated memory row with chain repair + node GC.

        Repairs the chain: any predecessor that pointed at this row now
        points at this row's successor (``migrated_to``). After the row
        is gone, if the node has no remaining ``Memory`` rows, the node
        and all of its edges / paths / glossary keywords are cleaned up.

        Raises ``ValueError`` if the id doesn't exist, ``PermissionError``
        if the row is still active (deletion is gated on deprecated=True).
        Returns the legacy audit dict shape:
        ``{deleted_memory_id, chain_repaired_to, rows_before, rows_after}``.
        """
        async with self._db.session() as s:
            target = (
                await s.execute(
                    sa.select(Memory).where(Memory.id == memory_id)
                )
            ).scalar_one_or_none()
            if target is None:
                raise ValueError(f"Memory ID {memory_id} not found")
            if not target.deprecated:
                raise PermissionError(
                    f"Memory {memory_id} is active (deprecated=False). "
                    f"Deletion aborted."
                )

            successor_id = target.migrated_to
            node_uuid = target.node_uuid
            deleted_before = serialize_memory_ref(target)

            # Chain repair: anyone pointing at us now points at our successor.
            await s.execute(
                sa.update(Memory)
                .where(Memory.migrated_to == memory_id)
                .values(migrated_to=successor_id)
            )

            await s.execute(
                sa.delete(Memory).where(Memory.id == memory_id)
            )
            # The count query below relies on the autoflush default to
            # see the DELETE we just issued. Explicit flush here so
            # future session-factory changes can't silently break the GC.
            await s.flush()

            rows_before: dict[str, list] = {
                "nodes": [],
                "memories": [deleted_before],
                "edges": [],
                "paths": [],
                "glossary_keywords": [],
            }

            # GC the node if it now has zero memories. We keep this scoped:
            # a memoryless node by definition has no remaining version chain,
            # so we only clear its own structural rows (no recursive
            # descent into children — the desktop maintenance API never
            # exposes orphan branches with active descendants).
            remaining = (
                await s.execute(
                    sa.select(sa.func.count())
                    .select_from(Memory)
                    .where(Memory.node_uuid == node_uuid)
                )
            ).scalar_one()
            if remaining == 0:
                await self._collect_and_clear_memoryless_node(
                    s, node_uuid, rows_before
                )

            return {
                "deleted_memory_id": memory_id,
                "chain_repaired_to": successor_id,
                "rows_before": rows_before,
                "rows_after": {},
            }

    # ------------------------------------------------------------------
    # Desktop review pane: diff fetch + path restoration.
    #
    # ``get_memory_by_id`` powers the ``/api/review/diff`` content
    # lookup; ``restore_path`` is the rollback target for changeset
    # entries that record a path deletion (``after is None``). Both
    # mirror the legacy GraphService contract returned to the frontend.
    # ``restore_path`` intentionally tightens one guard: see its
    # docstring for the namespace-scope divergence vs legacy.
    # ------------------------------------------------------------------

    async def get_memory_by_id(self, memory_id: int) -> Optional[dict]:
        """Return one memory row (active or deprecated) with incident paths.

        Returns ``None`` if the id doesn't exist. Used by the diff view
        to render before/after content for a memories row in the
        changeset.
        """
        async with self._db.session() as s:
            memory = (
                await s.execute(
                    sa.select(Memory).where(Memory.id == memory_id)
                )
            ).scalar_one_or_none()
            if memory is None:
                return None

            paths: list[str] = []
            if memory.node_uuid:
                rows = (
                    await s.execute(
                        sa.select(Path.domain, Path.path)
                        .select_from(Path)
                        .join(Edge, Path.edge_id == Edge.id)
                        .where(Edge.child_uuid == memory.node_uuid)
                    )
                ).all()
                paths = [f"{d}://{p}" for d, p in rows]

            return {
                "memory_id": memory.id,
                "node_uuid": memory.node_uuid,
                "content": memory.content,
                "created_at": (
                    memory.created_at.isoformat()
                    if memory.created_at
                    else None
                ),
                "deprecated": memory.deprecated,
                "migrated_to": memory.migrated_to,
                "paths": paths,
            }

    async def restore_path(
        self,
        *,
        path: str,
        domain: str,
        namespace: str,
        node_uuid: str,
        parent_uuid: Optional[str] = None,
        priority: int = 0,
        disclosure: Optional[str] = None,
    ) -> dict:
        """Re-attach ``(domain, path)`` to ``node_uuid`` in ``namespace``.

        Used by the desktop review pane to undo a path deletion. The
        caller supplies the original ``node_uuid`` from the changeset
        snapshot; the method:

        1. verifies the node still exists,
        2. re-activates the latest memory if the chain head was
           deprecated (so the restored path resolves to a live row),
        3. resolves or defaults the parent edge,
        4. recreates the edge (or reuses an existing one) and the path,
        5. refreshes the search index.

        Raises ``ValueError`` on root path, missing node, or
        already-existing path. Returns ``{"uri": ..., "node_uuid": ...}``.

        **Deliberate divergence from legacy:** the "already exists"
        check is scoped to ``(namespace, domain, path)`` rather than
        the legacy ``(domain, path)`` only. The legacy check would
        falsely reject a rollback whenever a *different* namespace
        held the same ``(domain, path)``; the namespace-scoped check
        matches the actual ``Path`` unique index and is the correct
        invariant. The legacy GraphService method had this latent bug.

        TODO(Phase 3): delete the duplicate ``GraphService.restore_path``
        at ``omicsclaw/memory/graph.py:1464`` when ``graph.py`` is removed.
        """
        if path == "":
            raise ValueError("Cannot restore the root path.")

        async with self._db.session() as s:
            node = (
                await s.execute(
                    sa.select(Node).where(Node.uuid == node_uuid)
                )
            ).scalar_one_or_none()
            if node is None:
                raise ValueError(f"Node '{node_uuid}' not found")

            # If no active memory remains on the node, re-activate the
            # most-recent deprecated one so the restored path resolves.
            active = (
                await s.execute(
                    sa.select(Memory).where(
                        Memory.node_uuid == node_uuid,
                        Memory.deprecated == False,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if active is None:
                latest = (
                    await s.execute(
                        sa.select(Memory)
                        .where(Memory.node_uuid == node_uuid)
                        .order_by(Memory.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if latest is None:
                    raise ValueError(
                        f"Node '{node_uuid}' has no memory versions"
                    )
                await s.execute(
                    sa.update(Memory)
                    .where(Memory.id == latest.id)
                    .values(deprecated=False, migrated_to=None)
                )

            existing = (
                await s.execute(
                    sa.select(Path).where(
                        Path.namespace == namespace,
                        Path.domain == domain,
                        Path.path == path,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError(
                    f"Path '{domain}://{path}' already exists"
                )

            if parent_uuid is None:
                if "/" in path:
                    parent_path_str = path.rsplit("/", 1)[0]
                    parent_row = (
                        await s.execute(
                            sa.select(Path).where(
                                Path.namespace == namespace,
                                Path.domain == domain,
                                Path.path == parent_path_str,
                            )
                        )
                    ).scalar_one_or_none()
                    if parent_row is not None:
                        parent_edge = await s.get(Edge, parent_row.edge_id)
                        parent_uuid = (
                            parent_edge.child_uuid
                            if parent_edge is not None
                            else ROOT_NODE_UUID
                        )
                    else:
                        parent_uuid = ROOT_NODE_UUID
                else:
                    parent_uuid = ROOT_NODE_UUID

            edge_name = path.rsplit("/", 1)[-1] if "/" in path else path
            edge = (
                await s.execute(
                    sa.select(Edge).where(
                        Edge.parent_uuid == parent_uuid,
                        Edge.child_uuid == node_uuid,
                        Edge.name == edge_name,
                    )
                )
            ).scalar_one_or_none()
            if edge is None:
                edge = Edge(
                    parent_uuid=parent_uuid,
                    child_uuid=node_uuid,
                    name=edge_name,
                    priority=priority,
                    disclosure=disclosure,
                )
                s.add(edge)
                await s.flush()

            s.add(
                Path(
                    namespace=namespace,
                    domain=domain,
                    path=path,
                    edge_id=edge.id,
                )
            )
            await s.flush()

            await self._engine.search_indexer.refresh_search_documents_for_node(
                node_uuid, session=s
            )

            return {"uri": f"{domain}://{path}", "node_uuid": node_uuid}

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _snippet(cls, content: str) -> str:
        if len(content) <= cls._SNIPPET_LIMIT:
            return content
        return content[: cls._SNIPPET_LIMIT] + "..."

    async def _resolve_migration_chain(
        self,
        s: sa.ext.asyncio.AsyncSession,  # type: ignore[name-defined]
        start_id: int,
        *,
        max_hops: int = 50,
    ) -> Optional[dict]:
        """Walk the ``migrated_to`` chain until a head (or dead end).

        TODO(Phase 3): delete the duplicate ``GraphService._resolve_migration_chain``
        at ``omicsclaw/memory/graph.py:1660`` when ``graph.py`` is removed.
        """
        current_id = start_id
        for _ in range(max_hops):
            memory = (
                await s.execute(
                    sa.select(Memory).where(Memory.id == current_id)
                )
            ).scalar_one_or_none()
            if memory is None:
                return None
            if memory.migrated_to is None:
                paths: list[str] = []
                if memory.node_uuid:
                    rows = (
                        await s.execute(
                            sa.select(Path.domain, Path.path)
                            .select_from(Path)
                            .join(Edge, Path.edge_id == Edge.id)
                            .where(Edge.child_uuid == memory.node_uuid)
                        )
                    ).all()
                    paths = [f"{d}://{p}" for d, p in rows]
                return {
                    "id": memory.id,
                    "content": memory.content,
                    "content_snippet": self._snippet(memory.content),
                    "created_at": (
                        memory.created_at.isoformat()
                        if memory.created_at
                        else None
                    ),
                    "deprecated": memory.deprecated,
                    "paths": paths,
                }
            current_id = memory.migrated_to
        return None

    async def _collect_and_clear_memoryless_node(
        self,
        s,
        node_uuid: str,
        rows_before: dict[str, list],
    ) -> None:
        """Snapshot + delete edges/paths/glossary + node for a memoryless node.

        Conservative scope: pathless aliases (``Path`` rows whose edge no
        longer points at this node) are deliberately preserved, as are
        any descendant subtrees reachable via outgoing edges. The legacy
        ``GraphService.cascade_delete_node`` swept them all; the
        ``permanently_delete_orphan`` contract intentionally avoids that
        so an admin-button click cannot delete still-live descendants.
        See ``test_permanently_delete_orphan_only_removes_direct_edges``.
        """
        edge_rows = (
            await s.execute(
                sa.select(Edge).where(
                    sa.or_(
                        Edge.parent_uuid == node_uuid,
                        Edge.child_uuid == node_uuid,
                    )
                )
            )
        ).scalars().all()
        edge_ids = [e.id for e in edge_rows]
        for e in edge_rows:
            rows_before["edges"].append(serialize_row(e))

        if edge_ids:
            path_rows = (
                await s.execute(
                    sa.select(Path).where(Path.edge_id.in_(edge_ids))
                )
            ).scalars().all()
            for p in path_rows:
                rows_before["paths"].append(serialize_row(p))
            await s.execute(
                sa.delete(Path).where(Path.edge_id.in_(edge_ids))
            )

        if edge_ids:
            await s.execute(
                sa.delete(Edge).where(Edge.id.in_(edge_ids))
            )

        gk_rows = (
            await s.execute(
                sa.select(GlossaryKeyword).where(
                    GlossaryKeyword.node_uuid == node_uuid
                )
            )
        ).scalars().all()
        for gk in gk_rows:
            rows_before["glossary_keywords"].append(serialize_row(gk))
        await s.execute(
            sa.delete(GlossaryKeyword).where(
                GlossaryKeyword.node_uuid == node_uuid
            )
        )

        node = (
            await s.execute(
                sa.select(Node).where(Node.uuid == node_uuid)
            )
        ).scalar_one_or_none()
        if node is not None:
            rows_before["nodes"].append(serialize_row(node))
            await s.execute(sa.delete(Node).where(Node.uuid == node_uuid))

    # ------------------------------------------------------------------
    # internal helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _fetch_path(s, namespace: str, parsed: MemoryURI) -> Optional[Path]:
        return (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == namespace,
                    Path.domain == parsed.domain,
                    Path.path == parsed.path,
                )
            )
        ).scalar_one_or_none()
