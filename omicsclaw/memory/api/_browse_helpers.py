# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportGeneralTypeIssues=false, reportOperatorIssue=false, reportReturnType=false

"""Private path-based memory operations for the ``/api/browse/*`` admin pane.

This module is the consolidated home for the legacy node/path/edge
admin operations that used to live on ``GraphService``. It is loaded
**only** by ``omicsclaw/memory/api/browse.py`` to serve the
``oc memory-server`` admin API and is intentionally private (leading
``_`` in the filename, no re-export through ``omicsclaw.memory``).

New code MUST use ``MemoryEngine`` / ``ReviewLog`` / ``MemoryClient``
instead. ``BrowseHelpers`` is preserved here only because the
``/api/browse/*`` write endpoints (``/create``, PUT ``/node``,
``/add-path``, DELETE ``/path``) expose a path-based UI contract
that has no direct equivalent on the URI-based engine. A future
rewrite can simplify or remove this module once the desktop UI is
ported to the engine's surface.
"""

import uuid as uuid_lib
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import (
    select,
    update,
    delete,
    func,
    and_,
    or_,
    not_,
)
from sqlalchemy.ext.asyncio import AsyncSession
from ..engine import MemoryEngine
from ..models import (
    ROOT_NODE_UUID,
    SHARED_NAMESPACE,
    Node,
    Memory,
    Edge,
    Path,
    GlossaryKeyword,
    ChangeCollector,
    escape_like_literal,
    serialize_row,
    serialize_memory_ref,
)

if TYPE_CHECKING:
    from ..database import DatabaseManager
    from ..search import SearchIndexer


class BrowseHelpers:
    """Private helper bundle for the ``/api/browse/*`` admin endpoints.

    Carries the path-based memory operations the admin UI needs:
    - read: Get memory by path (Path -> Edge -> Memory via node_uuid)
    - create: New node + memory + edge + path
    - update: New memory version on same node; update edge metadata
    - add_path: Create alias (new Path, maybe new Edge)
    - remove_path: Delete paths; refuse if children would become unreachable

    Receives a DatabaseManager for session access and a SearchIndexer
    for post-mutation index refreshes. Not exported through
    ``omicsclaw.memory`` — production callers must use
    ``MemoryEngine`` / ``ReviewLog`` / ``MemoryClient`` instead.
    """

    def __init__(self, db: "DatabaseManager", search: "SearchIndexer"):
        self.session = db.session
        self._optional_session = db._optional_session
        self._search = search
        # Transitional shim (PR #3c): the mutating verbs delegate to
        # MemoryEngine with namespace='__shared__', preserving the legacy
        # observable behaviour. PR #6 deletes the shim entirely once
        # callers have moved to MemoryClient/MemoryEngine directly.
        self._engine = MemoryEngine(db, search)

    @staticmethod
    def _decode_legacy(content: str) -> str:
        """Decode content that was base64-encoded by the old encryption system.

        Returns the original content unchanged if it's already plain text.
        """
        import base64 as _b64
        if not content:
            return content
        stripped = content.strip()
        if stripped.startswith(("{", "[", "http", "#", "Memory ", "User ")):
            return content
        try:
            padded = stripped
            pad_needed = len(padded) % 4
            if pad_needed:
                padded += "=" * (4 - pad_needed)
            raw = _b64.b64decode(padded, validate=True)
            decoded = raw.decode("utf-8")
            printable = sum(1 for c in decoded if c.isprintable() or c in "\n\r\t")
            if printable / max(len(decoded), 1) > 0.85:
                return decoded
        except Exception:
            pass
        return content

    # =========================================================================
    # Read Operations
    # =========================================================================

    async def get_memory_by_path(
        self, path: str, domain: str = "core"
    ) -> Optional[Dict[str, Any]]:
        """
        Get a memory by its path.

        Returns:
            Memory dict with id, node_uuid, content, priority, disclosure,
            created_at, domain, path -- or None if not found.
        """
        if path == "":
            return {
                "id": 0,
                "node_uuid": ROOT_NODE_UUID,
                "content": f"Root node for domain '{domain}'.",
                "priority": 0,
                "disclosure": None,
                "deprecated": False,
                "created_at": None,
                "domain": domain,
                "path": "",
                "alias_count": 0,
            }

        async with self.session() as session:
            result = await session.execute(
                select(Memory, Edge, Path)
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .join(
                    Memory,
                    and_(
                        Memory.node_uuid == Edge.child_uuid,
                        Memory.deprecated == False,
                    ),
                )
                .where(Path.domain == domain)
                .where(Path.path == path)
                .order_by(Memory.created_at.desc())
                .limit(1)
            )
            row = result.first()

            if not row:
                return None

            memory, edge, path_obj = row

            # Count total paths (aliases) for this node
            total_paths = await self._count_incoming_paths(session, edge.child_uuid)
            alias_count = max(0, total_paths - 1)

            # Auto-decode legacy base64 content from old encryption system
            content = memory.content
            decoded = self._decode_legacy(content)
            if decoded != content:
                # Fix in DB permanently
                from sqlalchemy import update as sql_update
                await session.execute(
                    sql_update(Memory)
                    .where(Memory.id == memory.id)
                    .values(content=decoded)
                )
                content = decoded

            return {
                "id": memory.id,
                "node_uuid": edge.child_uuid,
                "content": content,
                "priority": edge.priority,
                "disclosure": edge.disclosure,
                "deprecated": memory.deprecated,
                "created_at": memory.created_at.isoformat()
                if memory.created_at
                else None,
                "domain": path_obj.domain,
                "path": path_obj.path,
                "alias_count": alias_count,
            }

    async def get_memory_by_node_uuid(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        """Get the current active (non-deprecated) memory for a node."""
        async with self.session() as session:
            result = await session.execute(
                select(Memory)
                .where(Memory.node_uuid == node_uuid, Memory.deprecated == False)
                .order_by(Memory.created_at.desc())
                .limit(1)
            )
            memory = result.scalar_one_or_none()

            if not memory:
                return None

            paths_result = await session.execute(
                select(Path.domain, Path.path)
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .where(Edge.child_uuid == node_uuid)
            )
            paths = [f"{r[0]}://{r[1]}" for r in paths_result.all()]

            return {
                "id": memory.id,
                "node_uuid": node_uuid,
                "content": memory.content,
                "deprecated": memory.deprecated,
                "created_at": memory.created_at.isoformat()
                if memory.created_at
                else None,
                "paths": paths,
            }

    async def get_children(
        self,
        node_uuid: str = ROOT_NODE_UUID,
        context_domain: Optional[str] = None,
        context_path: Optional[str] = None,
        *,
        namespace: Optional[str] = None,
        include_shared: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get direct children of a node via the edges table.

        When *context_domain* / *context_path* are supplied the returned
        ``path`` for each child is chosen with affinity:
          1. Same domain AND path starts with ``context_path/``
          2. Same domain (any path)
          3. Any path at all

        ``namespace`` filtering modes:
          * ``namespace=None`` — legacy unfiltered admin view.
          * ``namespace=X``, ``include_shared=False`` (default) — strict,
            matches ``MemoryEngine.list_children`` semantics. A child
            whose only path lives outside ``X`` is dropped.
          * ``namespace=X``, ``include_shared=True`` — UI/desktop mode.
            Children with paths in ``X`` *or* ``__shared__`` are listed,
            with namespace-matched paths preferred when picking the
            display path. The desktop ``/memory/children`` endpoint
            uses this mode so the user can browse their own writes
            *and* shared system rows (``core://agent/*``, future
            ``core://kh/*`` seeds) from one tree.
        """
        async with self.session() as session:
            stmt = (
                select(Edge, Memory)
                .join(
                    Memory,
                    and_(
                        Memory.node_uuid == Edge.child_uuid,
                        Memory.deprecated == False,
                    ),
                )
                .where(Edge.parent_uuid == node_uuid)
                .order_by(Edge.priority.asc(), Edge.name)
            )
            result = await session.execute(stmt)
            rows = result.all()

            prefix = f"{context_path}/" if context_path else None

            child_uuids = {edge.child_uuid for edge, _ in rows}
            approx_children_count_map: Dict[str, int] = {}
            if child_uuids:
                count_result = await session.execute(
                    select(Edge.parent_uuid, func.count(Edge.id))
                    .where(Edge.parent_uuid.in_(child_uuids))
                    .group_by(Edge.parent_uuid)
                )
                approx_children_count_map = {
                    parent_uuid: count for parent_uuid, count in count_result.all()
                }

            children = []
            seen = set()
            for edge, memory in rows:
                if edge.child_uuid in seen:
                    continue
                seen.add(edge.child_uuid)

                path_stmt = select(Path).where(Path.edge_id == edge.id)
                if namespace is not None:
                    if include_shared:
                        path_stmt = path_stmt.where(
                            Path.namespace.in_([namespace, SHARED_NAMESPACE])
                        )
                    else:
                        path_stmt = path_stmt.where(Path.namespace == namespace)
                path_result = await session.execute(path_stmt)
                all_paths = path_result.scalars().all()

                # Drop children that have no path in the requested scope.
                if namespace is not None and not all_paths:
                    continue

                # Prefer namespace-matched paths over shared when both
                # exist (mirrors engine.search ordering).
                if namespace is not None and include_shared and len(all_paths) > 1:
                    all_paths = sorted(
                        all_paths,
                        key=lambda p: 0 if p.namespace == namespace else 1,
                    )

                if node_uuid == ROOT_NODE_UUID and context_domain:
                    has_domain_path = any(p.domain == context_domain for p in all_paths)
                    if not has_domain_path:
                        continue

                path_obj = self._pick_best_path(all_paths, context_domain, prefix)

                approx_children_count = approx_children_count_map.get(
                    edge.child_uuid, 0
                )

                # Auto-decode legacy base64 content
                content = memory.content
                decoded = self._decode_legacy(content)
                if decoded != content:
                    from sqlalchemy import update as sql_update
                    await session.execute(
                        sql_update(Memory)
                        .where(Memory.id == memory.id)
                        .values(content=decoded)
                    )
                    content = decoded

                children.append(
                    {
                        "node_uuid": edge.child_uuid,
                        "edge_id": edge.id,
                        "name": edge.name,
                        "domain": path_obj.domain if path_obj else "core",
                        "path": path_obj.path if path_obj else edge.name,
                        "content_snippet": content[:100] + "..."
                        if len(content) > 100
                        else content,
                        "priority": edge.priority,
                        "disclosure": edge.disclosure,
                        "approx_children_count": approx_children_count,
                    }
                )

            return children

    @staticmethod
    def _pick_best_path(
        paths: List[Path],
        context_domain: Optional[str],
        prefix: Optional[str],
    ) -> Optional[Path]:
        """Pick the most contextually relevant path from a list of aliases."""
        if not paths:
            return None
        if len(paths) == 1:
            return paths[0]

        # Tier 1: same domain + path is under the caller's current prefix
        if context_domain and prefix:
            for p in paths:
                if p.domain == context_domain and p.path.startswith(prefix):
                    return p

        # Tier 2: same domain, any path
        if context_domain:
            for p in paths:
                if p.domain == context_domain:
                    return p

        # Tier 3: whatever is available
        return paths[0]

    async def get_all_paths(
        self,
        domain: Optional[str] = None,
        *,
        namespace: Optional[str] = None,
        include_shared: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get all paths with their node/edge info.

        ``namespace`` filtering modes:
          * ``namespace=None`` — legacy admin view (all rows). The
            ``namespace`` key is included in the output dict so admin
            consumers can distinguish same-URI rows across partitions.
          * ``namespace=X``, ``include_shared=False`` (default) — strict
            scope to ``X``.
          * ``namespace=X``, ``include_shared=True`` — UI/desktop mode.
            Returns rows in ``X`` *or* ``__shared__``, with
            namespace-matched rows ordered first so dedupe (by
            ``(domain, path)`` URI within this scoped view) keeps the
            user's own copy when both partitions hold the same URI.
        """
        async with self.session() as session:
            stmt = (
                select(Path, Edge, Memory)
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .join(
                    Memory,
                    and_(
                        Memory.node_uuid == Edge.child_uuid,
                        Memory.deprecated == False,
                    ),
                )
            )

            if domain is not None:
                stmt = stmt.where(Path.domain == domain)
            if namespace is not None:
                if include_shared:
                    stmt = stmt.where(
                        Path.namespace.in_([namespace, SHARED_NAMESPACE])
                    )
                else:
                    stmt = stmt.where(Path.namespace == namespace)

            stmt = stmt.order_by(Path.domain, Path.path)
            result = await session.execute(stmt)

            rows = list(result.all())

            # Within a scoped view (namespace given), order namespace-matched
            # rows before shared so the (domain, path) dedupe below keeps
            # the caller's own copy when both partitions hold the same URI.
            scoped_view = namespace is not None
            if scoped_view and include_shared:
                rows.sort(
                    key=lambda triple: 0
                    if triple[0].namespace == namespace
                    else 1
                )

            paths = []
            seen = set()
            for path_obj, edge, memory in rows:
                # In admin view, dedupe by (namespace, domain, path) so
                # two namespaces' same URI both surface; in scoped view
                # dedupe by (domain, path) so a shared duplicate of a
                # user-namespace row collapses (user's row wins via the
                # CASE order above).
                key = (
                    (path_obj.domain, path_obj.path)
                    if scoped_view
                    else (path_obj.namespace, path_obj.domain, path_obj.path)
                )
                if key in seen:
                    continue
                seen.add(key)
                paths.append(
                    {
                        "domain": path_obj.domain,
                        "path": path_obj.path,
                        "namespace": path_obj.namespace,
                        "uri": f"{path_obj.domain}://{path_obj.path}",
                        "name": path_obj.path.rsplit("/", 1)[-1],
                        "priority": edge.priority,
                        "memory_id": memory.id,
                        "node_uuid": edge.child_uuid,
                    }
                )

            return paths

    # =========================================================================
    # Layer 0: Row-Level Primitives
    # =========================================================================

    async def _ensure_node(self, session: AsyncSession, node_uuid: str) -> Node:
        """Create a node if it doesn't exist; return it either way."""
        result = await session.execute(select(Node).where(Node.uuid == node_uuid))
        node = result.scalar_one_or_none()
        if node:
            return node
        node = Node(uuid=node_uuid)
        session.add(node)
        await session.flush()
        return node

    async def _insert_memory(
        self,
        session: AsyncSession,
        node_uuid: str,
        content: str,
        *,
        deprecated: bool = False,
    ) -> Memory:
        """Insert a new memory row and flush to obtain its ID."""
        memory = Memory(
            content=content,
            node_uuid=node_uuid,
            deprecated=deprecated,
        )
        session.add(memory)
        await session.flush()
        return memory

    async def _get_or_create_edge(
        self,
        session: AsyncSession,
        parent_uuid: str,
        child_uuid: str,
        name: str,
        priority: int = 0,
        disclosure: Optional[str] = None,
    ) -> tuple:
        """Get an existing edge or create a new one. Returns (edge, created: bool)."""
        result = await session.execute(
            select(Edge).where(
                Edge.parent_uuid == parent_uuid,
                Edge.child_uuid == child_uuid,
            )
        )
        edge = result.scalar_one_or_none()
        if edge:
            return edge, False

        edge = Edge(
            parent_uuid=parent_uuid,
            child_uuid=child_uuid,
            name=name,
            priority=priority,
            disclosure=disclosure,
        )
        session.add(edge)
        await session.flush()
        return edge, True

    async def _insert_path(
        self, session: AsyncSession, domain: str, path: str, edge_id: int
    ) -> Path:
        """Insert a new path row."""
        path_obj = Path(domain=domain, path=path, edge_id=edge_id)
        session.add(path_obj)
        return path_obj

    async def _resolve_path(
        self,
        session: AsyncSession,
        path: str,
        domain: str = "core",
        namespace: Optional[str] = None,
    ) -> Optional[tuple]:
        """Resolve domain+path to (Path, Edge, node_uuid). Returns None if not found.

        When ``namespace`` is given, the lookup is restricted to that
        namespace — preventing one user's resolve from picking up another
        user's row with the same ``(domain, path)``. ``namespace=None``
        preserves the legacy unfiltered behavior for admin tooling.
        """
        stmt = (
            select(Path, Edge)
            .join(Edge, Path.edge_id == Edge.id)
            .where(Path.domain == domain, Path.path == path)
        )
        if namespace is not None:
            stmt = stmt.where(Path.namespace == namespace)
        result = await session.execute(stmt)
        row = result.first()
        if not row:
            return None
        path_obj, edge = row
        return path_obj, edge, edge.child_uuid

    async def _count_paths_for_edge(self, session: AsyncSession, edge_id: int) -> int:
        """Count how many path rows reference a given edge."""
        result = await session.execute(
            select(func.count()).select_from(Path).where(Path.edge_id == edge_id)
        )
        return result.scalar()

    async def _count_incoming_paths(
        self,
        session: AsyncSession,
        node_uuid: str,
        *,
        exclude_domain: Optional[str] = None,
        exclude_path_prefix: Optional[str] = None,
    ) -> int:
        """Count paths whose edge points TO this node (edge.child_uuid)."""
        stmt = (
            select(func.count())
            .select_from(Path)
            .join(Edge, Path.edge_id == Edge.id)
            .where(Edge.child_uuid == node_uuid)
        )

        if exclude_domain and exclude_path_prefix:
            safe_prefix = escape_like_literal(exclude_path_prefix)
            stmt = stmt.where(
                not_(
                    and_(
                        Path.domain == exclude_domain,
                        Path.path.like(f"{safe_prefix}/%", escape="\\"),
                    )
                )
            )

        result = await session.execute(stmt)
        return result.scalar()

    async def _count_memories_for_node(
        self, session: AsyncSession, node_uuid: str
    ) -> int:
        """Count all memory rows (including deprecated) for a node."""
        result = await session.execute(
            select(func.count())
            .select_from(Memory)
            .where(Memory.node_uuid == node_uuid)
        )
        return result.scalar()

    async def _get_next_child_number(
        self, session: AsyncSession, parent_uuid: str
    ) -> int:
        """Get the next numeric name for auto-naming under a parent node."""
        result = await session.execute(
            select(Edge.name).where(Edge.parent_uuid == parent_uuid)
        )
        max_num = 0
        for (name,) in result.all():
            try:
                num = int(name)
                max_num = max(max_num, num)
            except ValueError:
                pass
        return max_num + 1

    async def _would_create_cycle(
        self,
        session: AsyncSession,
        parent_uuid: str,
        child_uuid: str,
    ) -> bool:
        """Check if adding edge parent_uuid->child_uuid would create a cycle."""
        if parent_uuid == ROOT_NODE_UUID:
            return False
        if parent_uuid == child_uuid:
            return True

        visited = {child_uuid}
        queue = [child_uuid]
        while queue:
            current = queue.pop(0)
            result = await session.execute(
                select(Edge.child_uuid).where(Edge.parent_uuid == current)
            )
            for (next_uuid,) in result.all():
                if next_uuid == parent_uuid:
                    return True
                if next_uuid not in visited:
                    visited.add(next_uuid)
                    queue.append(next_uuid)
        return False

    # =========================================================================
    # Layer 1: Table-Scoped Operations
    # =========================================================================

    async def _deprecate_node_memories(
        self,
        session: AsyncSession,
        node_uuid: str,
        *,
        successor_id: Optional[int] = None,
    ) -> List[int]:
        """Mark active memories for a node as deprecated."""
        conditions = [
            Memory.node_uuid == node_uuid,
            Memory.deprecated == False,
        ]
        if successor_id is not None:
            conditions.append(Memory.id != successor_id)

        result = await session.execute(select(Memory.id).where(and_(*conditions)))
        ids = [row[0] for row in result.all()]

        if ids:
            await session.execute(
                update(Memory)
                .where(Memory.id.in_(ids))
                .values(deprecated=True, migrated_to=successor_id)
            )
        return ids

    async def _safely_delete_memory(
        self,
        session: AsyncSession,
        memory_id: int,
        *,
        require_deprecated: bool = False,
    ) -> Dict[str, Any]:
        """Safely delete one memory row with chain repair."""
        target_result = await session.execute(
            select(Memory).where(Memory.id == memory_id)
        )
        target = target_result.scalar_one_or_none()
        if not target:
            raise ValueError(f"Memory ID {memory_id} not found")

        if require_deprecated and not target.deprecated:
            raise PermissionError(
                f"Memory {memory_id} is active (deprecated=False). Deletion aborted."
            )

        successor_id = target.migrated_to
        await session.execute(
            update(Memory)
            .where(Memory.migrated_to == memory_id)
            .values(migrated_to=successor_id)
        )

        result = await session.execute(delete(Memory).where(Memory.id == memory_id))
        if result.rowcount == 0:
            raise ValueError(f"Memory ID {memory_id} not found")

        return {
            "deleted_memory_id": memory_id,
            "chain_repaired_to": successor_id,
            "node_uuid": target.node_uuid,
            "deleted_memory_before": serialize_memory_ref(target),
        }

    async def _get_subtree_path_rows(
        self,
        session: AsyncSession,
        domain: str,
        base_path: str,
    ) -> List[Dict[str, Any]]:
        """Return serialized path rows for base_path and all descendants."""
        safe = escape_like_literal(base_path)
        result = await session.execute(
            select(Path).where(
                Path.domain == domain,
                or_(
                    Path.path == base_path,
                    Path.path.like(f"{safe}/%", escape="\\"),
                ),
            )
        )
        return [serialize_row(p) for p in result.scalars().all()]

    async def _cascade_create_paths(
        self,
        session: AsyncSession,
        node_uuid: str,
        domain: str,
        base_path: str,
        _visited: Optional[set] = None,
    ):
        """Recursively create path entries for all descendants of a node."""
        if _visited is None:
            _visited = set()
        if node_uuid in _visited:
            return
        _visited.add(node_uuid)
        try:
            result = await session.execute(
                select(Edge).where(Edge.parent_uuid == node_uuid)
            )
            child_edges = result.scalars().all()

            for child_edge in child_edges:
                child_path = f"{base_path}/{child_edge.name}"

                existing = await session.execute(
                    select(Path)
                    .where(Path.domain == domain)
                    .where(Path.path == child_path)
                )
                if not existing.scalar_one_or_none():
                    session.add(
                        Path(domain=domain, path=child_path, edge_id=child_edge.id)
                    )

                await self._cascade_create_paths(
                    session, child_edge.child_uuid, domain, child_path, _visited
                )
        finally:
            _visited.remove(node_uuid)

    # =========================================================================
    # Layer 2: Cross-Table Cascades
    # =========================================================================

    async def _delete_subtree_paths(
        self,
        session: AsyncSession,
        domain: str,
        path: str,
        *,
        namespace: Optional[str] = None,
        collector: Optional[ChangeCollector] = None,
    ) -> None:
        """Delete a path and all its descendant paths in the given domain.

        When ``namespace`` is given, the deletion is scoped to that
        namespace — so userA's remove_path can never delete userB's
        same ``(domain, path)`` row.
        """
        safe = escape_like_literal(path)
        stmt = (
            select(Path)
            .where(Path.domain == domain)
            .where(
                or_(
                    Path.path == path,
                    Path.path.like(f"{safe}/%", escape="\\"),
                )
            )
        )
        if namespace is not None:
            stmt = stmt.where(Path.namespace == namespace)
        result = await session.execute(stmt)
        paths = result.scalars().all()

        for p in paths:
            serialized = serialize_row(p)
            if collector:
                collector.record("paths", serialized)
            await session.delete(p)

    async def _cascade_delete_edge(
        self,
        session: AsyncSession,
        edge: Edge,
        *,
        namespace: Optional[str] = None,
        collector: Optional[ChangeCollector] = None,
    ) -> None:
        """Delete an edge, all its path references, and descendant paths.

        ``namespace`` propagates the strict scope from a namespaced
        ``remove_path`` call. The current call graph would be safe
        without this propagation (``_gc_node_soft`` only fires post-
        global-orphan-check on a per-namespace ``node_uuid``, so
        descendants live in the same namespace), but encoding the
        contract on the helper prevents a future caller from
        re-introducing a cross-namespace cascade. ``namespace=None``
        preserves the legacy unfiltered behavior for ``cascade_delete_node``
        and similar admin paths.
        """
        paths_result = await session.execute(
            select(Path).where(Path.edge_id == edge.id)
        )
        edge_paths = paths_result.scalars().all()

        for p in edge_paths:
            await self._delete_subtree_paths(
                session,
                p.domain,
                p.path,
                namespace=namespace,
                collector=collector,
            )

        if collector:
            collector.record("edges", serialize_row(edge))
        await session.delete(edge)

    async def cascade_delete_node(
        self, session: AsyncSession, node_uuid: str
    ) -> Optional[Dict[str, list]]:
        """Hard-delete a node, all its memories, edges, and paths."""
        if node_uuid == ROOT_NODE_UUID:
            return None

        collector = ChangeCollector()

        edges_result = await session.execute(
            select(Edge).where(
                or_(Edge.parent_uuid == node_uuid, Edge.child_uuid == node_uuid)
            )
        )
        for edge in edges_result.scalars().all():
            await self._cascade_delete_edge(
                session,
                edge,
                collector=collector,
            )

        mem_result = await session.execute(
            select(Memory).where(Memory.node_uuid == node_uuid)
        )
        for mem in mem_result.scalars().all():
            collector.record("memories", serialize_row(mem))

        kw_result = await session.execute(
            select(GlossaryKeyword).where(GlossaryKeyword.node_uuid == node_uuid)
        )
        for kw in kw_result.scalars().all():
            collector.record("glossary_keywords", serialize_row(kw))

        await session.execute(
            delete(Memory).where(Memory.node_uuid == node_uuid)
        )
        node_row = await session.execute(select(Node).where(Node.uuid == node_uuid))
        node = node_row.scalar_one_or_none()
        if node:
            collector.record("nodes", serialize_row(node))
        await session.execute(delete(Node).where(Node.uuid == node_uuid))

        return collector.to_dict()

    async def _create_edge_with_paths(
        self,
        session: AsyncSession,
        parent_uuid: str,
        child_uuid: str,
        name: str,
        domain: str,
        path: str,
        priority: int = 0,
        disclosure: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create (or get) an edge, its path entry, and cascade sub-paths."""
        edge, edge_created = await self._get_or_create_edge(
            session, parent_uuid, child_uuid, name, priority, disclosure
        )
        path_obj = await self._insert_path(session, domain, path, edge.id)
        await self._cascade_create_paths(session, child_uuid, domain, path)
        return {
            "edge": edge,
            "edge_id": edge.id,
            "edge_created": edge_created,
            "path": path_obj,
        }

    # =========================================================================
    # Layer 3: GC / Conditional Logic
    # =========================================================================

    async def _gc_edge_if_pathless(
        self,
        session: AsyncSession,
        edge: Edge,
        *,
        collector: Optional[ChangeCollector] = None,
    ) -> Optional[Dict[str, Any]]:
        """Delete an edge only if it has no remaining path references."""
        if await self._count_paths_for_edge(session, edge.id) > 0:
            return None
        if collector:
            collector.record("edges", serialize_row(edge))
        info = {
            "edge_id": edge.id,
            "parent_uuid": edge.parent_uuid,
            "child_uuid": edge.child_uuid,
            "name": edge.name,
            "priority": edge.priority,
            "disclosure": edge.disclosure,
        }
        await session.delete(edge)
        return info

    async def _gc_node_soft(
        self,
        session: AsyncSession,
        node_uuid: str,
        *,
        namespace: Optional[str] = None,
        collector: Optional[ChangeCollector] = None,
    ) -> None:
        """Soft GC: if a node has no incoming paths, deprecate its memories
        and cascade-delete all edges/paths around it.

        ``namespace`` propagates the strict scope from a namespaced
        ``remove_path`` so the cascade through ``_cascade_delete_edge``
        cannot stray into another namespace. ``namespace=None`` preserves
        the legacy admin-cascade behavior.
        """
        if await self._count_incoming_paths(session, node_uuid) > 0:
            return

        incoming = await session.execute(
            select(Edge).where(Edge.child_uuid == node_uuid)
        )
        for edge in incoming.scalars().all():
            await self._gc_edge_if_pathless(session, edge, collector=collector)

        outgoing = await session.execute(
            select(Edge).where(Edge.parent_uuid == node_uuid)
        )
        for edge in outgoing.scalars().all():
            await self._cascade_delete_edge(
                session,
                edge,
                namespace=namespace,
                collector=collector,
            )

        if collector:
            active_mems = await session.execute(
                select(Memory).where(
                    Memory.node_uuid == node_uuid,
                    Memory.deprecated == False,
                )
            )
            for mem in active_mems.scalars().all():
                collector.record("memories", serialize_row(mem))

        await self._deprecate_node_memories(session, node_uuid)

    async def _gc_node_if_memoryless(
        self, session: AsyncSession, node_uuid: str
    ) -> Optional[Dict[str, list]]:
        """Hard GC: if a node has zero memory rows, cascade-delete everything."""
        if await self._count_memories_for_node(session, node_uuid) > 0:
            return None
        return await self.cascade_delete_node(session, node_uuid)

    # =========================================================================
    # Public Write API
    # =========================================================================

    async def create_memory(
        self,
        parent_path: str,
        content: str,
        priority: int,
        title: Optional[str] = None,
        disclosure: Optional[str] = None,
        domain: str = "core",
    ) -> Dict[str, Any]:
        """
        Create a new memory under a parent path.

        Creates: Node -> Memory -> Edge (parent->child) -> Path.

        PR #3c shim: delegates the actual write to ``MemoryEngine.upsert_versioned``
        with ``namespace='__shared__'``. The path-computation policy
        (auto-numbering when ``title`` is omitted, the duplicate-path check)
        stays here because it has no engine equivalent. PR #6 removes the
        shim once callers move to ``MemoryClient`` / ``MemoryEngine`` directly.
        """
        # Pre-flight: resolve parent, compute final path, reject duplicates.
        async with self.session() as session:
            if not parent_path:
                parent_uuid = ROOT_NODE_UUID
            else:
                parent = await self._resolve_path(session, parent_path, domain)
                if not parent:
                    raise ValueError(
                        f"Parent '{domain}://{parent_path}' does not exist. "
                        f"Create the parent first, or use '{domain}://' as root."
                    )
                _, _, parent_uuid = parent

            if title:
                final_path = f"{parent_path}/{title}" if parent_path else title
            else:
                next_num = await self._get_next_child_number(session, parent_uuid)
                final_path = (
                    f"{parent_path}/{next_num}" if parent_path else str(next_num)
                )

            existing = await session.execute(
                select(Path).where(
                    Path.namespace == SHARED_NAMESPACE,
                    Path.domain == domain,
                    Path.path == final_path,
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Path '{domain}://{final_path}' already exists")

        # Delegate the row-creating part to MemoryEngine. Engine produces
        # Node + Memory + Edge + Path inside ``__shared__`` and refreshes
        # the search index. Returned ref carries memory_id and node_uuid.
        ref = await self._engine.upsert_versioned(
            f"{domain}://{final_path}",
            content,
            namespace=SHARED_NAMESPACE,
            priority=priority,
            disclosure=disclosure,
        )

        # Re-fetch the four rows we just created so the caller's changeset
        # bookkeeping (rows_after) gets the canonical serialised shape.
        async with self.session() as session:
            path_row = (
                await session.execute(
                    select(Path).where(
                        Path.namespace == SHARED_NAMESPACE,
                        Path.domain == domain,
                        Path.path == final_path,
                    )
                )
            ).scalar_one()
            edge = await session.get(Edge, path_row.edge_id)
            node = await session.get(Node, ref.node_uuid)
            memory = await session.get(Memory, ref.new_memory_id)

        return {
            "id": ref.new_memory_id,
            "node_uuid": ref.node_uuid,
            "domain": domain,
            "path": final_path,
            "uri": f"{domain}://{final_path}",
            "priority": priority,
            "rows_after": {
                "nodes": [serialize_row(node)],
                "memories": [serialize_memory_ref(memory)],
                "edges": [serialize_row(edge)],
                "paths": [serialize_row(path_row)],
            },
        }

    async def update_memory(
        self,
        path: str,
        content: Optional[str] = None,
        priority: Optional[int] = None,
        disclosure: Optional[str] = None,
        domain: str = "core",
        *,
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a memory.

        Content change -> new Memory row with the same node_uuid (deprecation chain).
        Metadata change -> update the Edge directly.

        PR #3c shim: delegates to ``MemoryEngine.upsert_versioned`` (when
        content changes) or ``MemoryEngine.patch_edge_metadata`` (metadata
        only). Pre-flight resolves the path and snapshots ``rows_before``;
        post-flight re-fetches to build ``rows_after``. The
        ``priority``/``disclosure`` defaults of ``None`` mean "preserve"
        in the legacy contract — we translate that into the engine's
        ``_UNSET`` sentinel by simply omitting unset kwargs from the
        engine call.

        ``namespace=None`` preserves the legacy ``__shared__`` lock so
        existing admin tooling (``oc memory-server`` browse routes) keeps
        editing shared memories. User-facing surfaces (desktop
        ``/memory/update``) pass their own namespace so the user's
        per-namespace memories are addressable.
        """
        if path == "":
            raise ValueError("Cannot update the root node.")

        if content is None and priority is None and disclosure is None:
            raise ValueError(
                f"No update fields provided for '{domain}://{path}'. "
                "At least one of content, priority, or disclosure must be set."
            )

        target_ns = namespace if namespace is not None else SHARED_NAMESPACE

        # Pre-flight: snapshot the current edge + active memory.
        async with self.session() as session:
            result = await session.execute(
                select(Memory, Edge, Path)
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .join(
                    Memory,
                    and_(
                        Memory.node_uuid == Edge.child_uuid,
                        Memory.deprecated == False,
                    ),
                )
                .where(
                    Path.namespace == target_ns,
                    Path.domain == domain,
                    Path.path == path,
                )
                .order_by(Memory.created_at.desc())
                .limit(1)
            )
            row = result.first()
            if not row:
                raise ValueError(
                    f"Path '{domain}://{path}' not found or memory is deprecated"
                )
            old_memory, edge, _ = row
            old_id = old_memory.id
            edge_id = edge.id
            node_uuid = edge.child_uuid
            edge_before = serialize_row(edge)
            old_memory_ref = serialize_memory_ref(old_memory)

        # Translate legacy "None means preserve" into engine's _UNSET via
        # kwargs omission. Engine helpers preserve current values when an
        # arg isn't supplied.
        engine_kwargs: Dict[str, Any] = {}
        if priority is not None:
            engine_kwargs["priority"] = priority
        if disclosure is not None:
            engine_kwargs["disclosure"] = disclosure

        if content is not None:
            ref = await self._engine.upsert_versioned(
                f"{domain}://{path}",
                content,
                namespace=target_ns,
                **engine_kwargs,
            )
            new_memory_id = ref.new_memory_id
        else:
            await self._engine.patch_edge_metadata(
                f"{domain}://{path}",
                namespace=target_ns,
                **engine_kwargs,
            )
            new_memory_id = old_id

        # Post-flight: re-fetch updated rows for changeset bookkeeping.
        rows_before: Dict[str, list] = {}
        rows_after: Dict[str, list] = {}

        async with self.session() as session:
            edge_after_obj = await session.get(Edge, edge_id)
            edge_after = serialize_row(edge_after_obj)
            if edge_before != edge_after:
                rows_before["edges"] = [edge_before]
                rows_after["edges"] = [edge_after]

            if content is not None:
                rows_before["memories"] = [old_memory_ref]
                old_after = await session.get(Memory, old_id)
                new_after = await session.get(Memory, new_memory_id)
                rows_after["memories"] = [
                    serialize_memory_ref(old_after),
                    serialize_memory_ref(new_after),
                ]

        return {
            "domain": domain,
            "path": path,
            "uri": f"{domain}://{path}",
            "old_memory_id": old_id,
            "new_memory_id": new_memory_id,
            "node_uuid": node_uuid,
            "rows_before": rows_before,
            "rows_after": rows_after,
        }

    async def rollback_to_memory(
        self, target_memory_id: int, session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Restore a deprecated memory as the active version."""
        async with self._optional_session(session) as session:
            target_row = await session.execute(
                select(Memory).where(Memory.id == target_memory_id)
            )
            target_memory = target_row.scalar_one_or_none()
            if not target_memory:
                raise ValueError(f"Memory ID {target_memory_id} not found")

            if not target_memory.deprecated:
                return {
                    "restored_memory_id": target_memory_id,
                    "was_already_active": True,
                }

            await self._deprecate_node_memories(
                session,
                target_memory.node_uuid,
                successor_id=target_memory_id,
            )

            await session.execute(
                update(Memory)
                .where(Memory.id == target_memory_id)
                .values(deprecated=False, migrated_to=None)
            )

            await self._search.refresh_search_documents_for_node(
                target_memory.node_uuid, session=session
            )

            return {
                "restored_memory_id": target_memory_id,
                "node_uuid": target_memory.node_uuid,
            }

    async def add_path(
        self,
        new_path: str,
        target_path: str,
        new_domain: str = "core",
        target_domain: str = "core",
        priority: int = 0,
        disclosure: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an alias path pointing to the same node as target_path."""
        if new_path == "":
            raise ValueError("Cannot create an alias at the root path.")

        async with self.session() as session:
            target = await self._resolve_path(session, target_path, target_domain)
            if not target:
                raise ValueError(
                    f"Target path '{target_domain}://{target_path}' not found"
                )
            _, _, target_node_uuid = target

            if "/" in new_path:
                parent_path = new_path.rsplit("/", 1)[0]
                parent = await self._resolve_path(session, parent_path, new_domain)
                if not parent:
                    raise ValueError(
                        f"Parent '{new_domain}://{parent_path}' does not exist. "
                        f"Create the parent first, or use a shallower alias path."
                    )
                _, _, parent_uuid = parent
            else:
                parent_uuid = ROOT_NODE_UUID

            existing = await session.execute(
                select(Path).where(Path.domain == new_domain, Path.path == new_path)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Path '{new_domain}://{new_path}' already exists")

            before_subtree = await self._get_subtree_path_rows(
                session, new_domain, new_path
            )
            before_path_keys = {(row["domain"], row["path"]) for row in before_subtree}

            if await self._would_create_cycle(session, parent_uuid, target_node_uuid):
                raise ValueError(
                    f"Cannot create alias '{new_domain}://{new_path}': "
                    f"target node is an ancestor of the destination parent, "
                    f"which would create a cycle in the graph."
                )

            result = await self._create_edge_with_paths(
                session,
                parent_uuid,
                target_node_uuid,
                new_path.rsplit("/", 1)[-1],
                new_domain,
                new_path,
                priority,
                disclosure,
            )
            await session.flush()

            after_subtree = await self._get_subtree_path_rows(
                session, new_domain, new_path
            )
            created_paths = [
                row
                for row in after_subtree
                if (row["domain"], row["path"]) not in before_path_keys
            ]

            rows_after: Dict[str, list] = {
                "paths": created_paths,
            }
            if result["edge_created"]:
                rows_after["edges"] = [serialize_row(result["edge"])]

            affected_nodes = await self._search.get_node_uuids_for_prefix(session, new_domain, new_path)
            for node_uuid in affected_nodes:
                await self._search.refresh_search_documents_for_node(node_uuid, session=session)

            return {
                "new_uri": f"{new_domain}://{new_path}",
                "target_uri": f"{target_domain}://{target_path}",
                "node_uuid": target_node_uuid,
                "edge_id": result["edge_id"],
                "edge_created": result["edge_created"],
                "rows_after": rows_after,
            }

    async def remove_path(
        self,
        path: str,
        domain: str = "core",
        session: Optional[AsyncSession] = None,
        *,
        namespace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Remove a path and its sub-paths with orphan prevention.

        When ``namespace`` is given, lookup and deletion are scoped to
        that namespace — ``MemoryClient(namespace="A").forget(...)`` can
        never delete a row in namespace ``B``. ``namespace=None``
        preserves the legacy unfiltered behavior for admin tooling.
        """
        if path == "":
            raise ValueError("Cannot remove the root path.")

        async with self._optional_session(session) as session:
            target = await self._resolve_path(session, path, domain, namespace=namespace)
            if not target:
                raise ValueError(f"Path '{domain}://{path}' not found")
            _, target_edge, target_node_uuid = target

            # Pre-flight orphan check
            child_edges_result = await session.execute(
                select(Edge).where(Edge.parent_uuid == target_node_uuid)
            )
            child_edges = child_edges_result.scalars().all()

            would_orphan = []
            for child_edge in child_edges:
                surviving_count = await self._count_incoming_paths(
                    session,
                    child_edge.child_uuid,
                    exclude_domain=domain,
                    exclude_path_prefix=path,
                )
                if surviving_count == 0:
                    would_orphan.append(child_edge)

            if would_orphan:
                details = ", ".join(
                    f"'{e.name}' (node: {e.child_uuid[:8]}...)" for e in would_orphan
                )
                raise ValueError(
                    f"Cannot remove '{domain}://{path}': "
                    f"the following child node(s) would become unreachable: "
                    f"{details}. "
                    f"Create alternative paths for these children first, "
                    f"or remove them explicitly."
                )

            collector = ChangeCollector()
            affected_nodes = await self._search.get_node_uuids_for_prefix(session, domain, path)
            await self._delete_subtree_paths(
                session, domain, path, namespace=namespace, collector=collector
            )
            await session.flush()

            await self._gc_edge_if_pathless(session, target_edge, collector=collector)
            await self._gc_node_soft(
                session, target_node_uuid, namespace=namespace, collector=collector
            )

            for node_uuid in affected_nodes:
                await self._search.refresh_search_documents_for_node(node_uuid, session=session)

            return {
                "rows_before": collector.to_dict(),
                "rows_after": {},
            }

    async def restore_path(
        self,
        path: str,
        domain: str,
        node_uuid: str,
        parent_uuid: Optional[str] = None,
        priority: int = 0,
        disclosure: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """Restore a path pointing to a node (used for rollback of delete)."""
        if path == "":
            raise ValueError("Cannot restore the root path.")

        async with self._optional_session(session) as session:
            node_result = await session.execute(
                select(Node).where(Node.uuid == node_uuid)
            )
            if not node_result.scalar_one_or_none():
                raise ValueError(f"Node '{node_uuid}' not found")

            active_mem = await session.execute(
                select(Memory).where(
                    Memory.node_uuid == node_uuid, Memory.deprecated == False
                )
            )
            if not active_mem.scalar_one_or_none():
                latest = await session.execute(
                    select(Memory)
                    .where(Memory.node_uuid == node_uuid)
                    .order_by(Memory.created_at.desc())
                    .limit(1)
                )
                latest_mem = latest.scalar_one_or_none()
                if not latest_mem:
                    raise ValueError(f"Node '{node_uuid}' has no memory versions")
                await session.execute(
                    update(Memory)
                    .where(Memory.id == latest_mem.id)
                    .values(deprecated=False, migrated_to=None)
                )

            existing = await session.execute(
                select(Path).where(Path.domain == domain, Path.path == path)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Path '{domain}://{path}' already exists")

            if parent_uuid is None:
                if "/" in path:
                    parent_path_str = path.rsplit("/", 1)[0]
                    parent = await self._resolve_path(session, parent_path_str, domain)
                    if parent:
                        _, _, parent_uuid = parent
                    else:
                        parent_uuid = ROOT_NODE_UUID
                else:
                    parent_uuid = ROOT_NODE_UUID

            edge_name = path.rsplit("/", 1)[-1]
            edge, _ = await self._get_or_create_edge(
                session, parent_uuid, node_uuid, edge_name, priority, disclosure
            )
            await self._insert_path(session, domain, path, edge.id)
            await self._search.refresh_search_documents_for_node(node_uuid, session=session)

            return {"uri": f"{domain}://{path}", "node_uuid": node_uuid}

    # =========================================================================
    # Recent Memories
    # =========================================================================

    async def get_recent_memories(
        self,
        limit: int = 10,
        *,
        namespace: Optional[str] = None,
        include_shared: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get the most recently created/updated non-deprecated memories.

        ``namespace`` filtering modes:
          * ``namespace=None`` — legacy admin view (all rows).
          * ``namespace=X``, ``include_shared=False`` (default) — strict.
            ``MemoryClient(namespace="A").get_recent()`` uses this so a
            user does not see other users' or system shared rows in
            their own recent listing.
          * ``namespace=X``, ``include_shared=True`` — UI/desktop mode.
            Returns rows in ``X`` *or* ``__shared__``. The desktop
            ``/memory/recent`` endpoint uses this so user-customized
            ``core://agent/*`` rows surface alongside per-user rows.
        """
        async with self.session() as session:
            stmt = (
                select(Memory, Edge, Path)
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .join(
                    Memory,
                    and_(
                        Memory.node_uuid == Edge.child_uuid,
                        Memory.deprecated == False,
                    ),
                )
                .order_by(Memory.created_at.desc())
            )
            if namespace is not None:
                if include_shared:
                    stmt = stmt.where(
                        Path.namespace.in_([namespace, SHARED_NAMESPACE])
                    )
                else:
                    stmt = stmt.where(Path.namespace == namespace)
            result = await session.execute(stmt)

            seen = set()
            memories = []

            for memory, edge, path_obj in result.all():
                if memory.id in seen:
                    continue
                seen.add(memory.id)

                memories.append(
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

                if len(memories) >= limit:
                    break

            return memories

    # =========================================================================
    # Deprecated Memory Operations (for human review)
    # =========================================================================

    async def get_memory_by_id(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Get a memory by its ID (including deprecated ones)."""
        async with self.session() as session:
            result = await session.execute(select(Memory).where(Memory.id == memory_id))
            memory = result.scalar_one_or_none()

            if not memory:
                return None

            paths = []
            if memory.node_uuid:
                paths_result = await session.execute(
                    select(Path.domain, Path.path)
                    .select_from(Path)
                    .join(Edge, Path.edge_id == Edge.id)
                    .where(Edge.child_uuid == memory.node_uuid)
                )
                paths = [f"{r[0]}://{r[1]}" for r in paths_result.all()]

            return {
                "memory_id": memory.id,
                "node_uuid": memory.node_uuid,
                "content": memory.content,
                "created_at": memory.created_at.isoformat()
                if memory.created_at
                else None,
                "deprecated": memory.deprecated,
                "migrated_to": memory.migrated_to,
                "paths": paths,
            }

    async def get_deprecated_memories(self) -> List[Dict[str, Any]]:
        """Get all deprecated memories for human review."""
        async with self.session() as session:
            result = await session.execute(
                select(Memory)
                .where(Memory.deprecated == True)
                .order_by(Memory.created_at.desc())
            )

            return [
                {
                    "id": m.id,
                    "content_snippet": m.content[:200] + "..."
                    if len(m.content) > 200
                    else m.content,
                    "migrated_to": m.migrated_to,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in result.scalars().all()
            ]

    async def _resolve_migration_chain(
        self, session: AsyncSession, start_id: int, max_hops: int = 50
    ) -> Optional[Dict[str, Any]]:
        """Follow the migrated_to chain to the final target."""
        current_id = start_id
        for _ in range(max_hops):
            result = await session.execute(
                select(Memory).where(Memory.id == current_id)
            )
            memory = result.scalar_one_or_none()
            if not memory:
                return None
            if memory.migrated_to is None:
                paths = []
                if memory.node_uuid:
                    paths_result = await session.execute(
                        select(Path.domain, Path.path)
                        .select_from(Path)
                        .join(Edge, Path.edge_id == Edge.id)
                        .where(Edge.child_uuid == memory.node_uuid)
                    )
                    paths = [f"{r[0]}://{r[1]}" for r in paths_result.all()]
                return {
                    "id": memory.id,
                    "content": memory.content,
                    "content_snippet": memory.content[:200] + "..."
                    if len(memory.content) > 200
                    else memory.content,
                    "created_at": memory.created_at.isoformat()
                    if memory.created_at
                    else None,
                    "deprecated": memory.deprecated,
                    "paths": paths,
                }
            current_id = memory.migrated_to
        return None

    async def get_all_orphan_memories(self) -> List[Dict[str, Any]]:
        """Get all orphan memories (deprecated=True)."""
        async with self.session() as session:
            orphans = []

            result = await session.execute(
                select(Memory)
                .where(Memory.deprecated == True)
                .order_by(Memory.created_at.desc())
            )

            for memory in result.scalars().all():
                category = "deprecated" if memory.migrated_to else "orphaned"
                item = {
                    "id": memory.id,
                    "content_snippet": memory.content[:200] + "..."
                    if len(memory.content) > 200
                    else memory.content,
                    "created_at": memory.created_at.isoformat()
                    if memory.created_at
                    else None,
                    "deprecated": True,
                    "migrated_to": memory.migrated_to,
                    "category": category,
                    "migration_target": None,
                }

                if memory.migrated_to:
                    target = await self._resolve_migration_chain(
                        session, memory.migrated_to
                    )
                    if target:
                        item["migration_target"] = {
                            "id": target["id"],
                            "paths": target["paths"],
                            "content_snippet": target["content_snippet"],
                        }

                orphans.append(item)

            return orphans

    async def get_orphan_detail(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Get full detail of an orphan memory."""
        async with self.session() as session:
            result = await session.execute(select(Memory).where(Memory.id == memory_id))
            memory = result.scalar_one_or_none()
            if not memory:
                return None

            if not memory.deprecated:
                category = "active"
            elif memory.migrated_to:
                category = "deprecated"
            else:
                category = "orphaned"

            detail = {
                "id": memory.id,
                "content": memory.content,
                "created_at": memory.created_at.isoformat()
                if memory.created_at
                else None,
                "deprecated": memory.deprecated,
                "migrated_to": memory.migrated_to,
                "category": category,
                "migration_target": None,
            }

            if memory.migrated_to:
                target = await self._resolve_migration_chain(
                    session, memory.migrated_to
                )
                if target:
                    detail["migration_target"] = {
                        "id": target["id"],
                        "content": target["content"],
                        "paths": target["paths"],
                        "created_at": target["created_at"],
                    }

            return detail

    async def permanently_delete_memory(self, memory_id: int) -> Dict[str, Any]:
        """Permanently delete a memory version (human only)."""
        async with self.session() as session:
            delete_result = await self._safely_delete_memory(
                session,
                memory_id,
                require_deprecated=True,
            )

            rows_before: Dict[str, list] = {
                "nodes": [],
                "memories": [delete_result["deleted_memory_before"]],
                "edges": [],
                "paths": [],
                "glossary_keywords": [],
            }

            response: Dict[str, Any] = {
                "deleted_memory_id": delete_result["deleted_memory_id"],
                "chain_repaired_to": delete_result["chain_repaired_to"],
            }

            node_uuid = delete_result["node_uuid"]
            if node_uuid:
                gc_snapshot = await self._gc_node_if_memoryless(session, node_uuid)
                if gc_snapshot:
                    for table in ("nodes", "memories", "edges", "paths", "glossary_keywords"):
                        rows_before[table].extend(gc_snapshot.get(table, []))

            response["rows_before"] = rows_before
            response["rows_after"] = {}

            return response
