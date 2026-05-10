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
    Memory,
    Path,
    SHARED_NAMESPACE,
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
