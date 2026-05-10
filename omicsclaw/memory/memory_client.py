"""MemoryClient — namespace-aware strategy layer over MemoryEngine.

This is the layer above ``MemoryEngine``: it owns the **strategy** of
"which namespace, versioned or overwrite" and decides which engine verb
to call. ``MemoryEngine`` itself stays mechanical — it does not know
about user identity or routing policy.

Two construction modes:

  - ``MemoryClient(engine=eng, namespace="tg/userA")``
        Lightweight, share an engine across many clients (one per user
        or per surface). This is the recommended form for new code.

  - ``MemoryClient(database_url="sqlite+aiosqlite:///...")``
        Backward-compat: builds an internal db + search + engine on
        ``initialize()``. Used by the three pre-existing callers
        (CompatMemoryStore, server.py boot, and the doc example).

Routing for ``remember(uri, content)``:

  - ``namespace_policy.resolve_namespace(uri, current=...)`` decides
    where the row goes — shared (``core://agent``, ``core://kh/*``,
    ``core://my_user_default``) or the client's current namespace.
  - ``namespace_policy.should_version(uri)`` decides whether to call
    ``engine.upsert_versioned`` (audit trail) or ``engine.upsert``
    (overwrite).

The audit-UI changeset capture (``snapshot.get_changeset_store``) still
fires on every ``remember`` and ``forget`` so the Review pane keeps
working unchanged for existing callers.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import and_, select

from .engine import MemoryEngine, MemoryRecord
from .models import (
    SHARED_NAMESPACE,
    Edge,
    Memory,
    Node,
    Path,
    serialize_memory_ref,
    serialize_row,
)
from .namespace_policy import resolve_namespace, should_version
from .uri import MemoryURI

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .search import SearchIndexer


class MemoryClient:
    """Namespace-aware strategy layer over MemoryEngine.

    See module docstring for the construction modes and routing policy.
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        *,
        engine: Optional[MemoryEngine] = None,
        namespace: str = SHARED_NAMESPACE,
    ):
        if engine is not None and database_url is not None:
            raise ValueError(
                "Pass either engine or database_url, not both."
            )

        self._namespace = namespace
        self._engine: Optional[MemoryEngine] = engine
        self._db_url = database_url
        self._db: Optional["DatabaseManager"] = None
        self._search: Optional["SearchIndexer"] = None
        # If an engine was supplied, this client is ready to use; the
        # legacy database_url path requires an explicit ``initialize()``.
        self._initialized = engine is not None
        self._owns_db = engine is None

    @property
    def namespace(self) -> str:
        """The namespace this client writes/reads in by default."""
        return self._namespace

    async def initialize(self) -> None:
        """Build the internal db/search/engine when constructed from a URL.

        No-op when the engine was supplied at construction time.
        """
        if self._initialized:
            return

        from .database import DatabaseManager
        from .search import SearchIndexer

        self._db = DatabaseManager(self._db_url)
        await self._db.init_db()
        self._search = SearchIndexer(self._db)
        self._engine = MemoryEngine(self._db, self._search)
        self._initialized = True

    async def _ensure_init(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def close(self) -> None:
        """Close the internal db connection if this client owns it."""
        if self._owns_db and self._db is not None:
            await self._db.close()
        self._initialized = False

    # ------------------------------------------------------------------
    # Write verbs
    # ------------------------------------------------------------------

    async def remember(
        self,
        uri: str,
        content: str,
        priority: int = 0,
        disclosure: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Store or update a memory at ``uri``.

        Routes to ``upsert_versioned`` for ``core://agent``/``core://my_user``/
        ``preference://*`` URIs, otherwise to overwrite-mode ``upsert``.
        Routes to ``__shared__`` for the three shared prefixes; otherwise
        the client's current namespace.

        Returns a dict with the canonical fields (id, node_uuid, uri,
        domain, path, namespace) plus ``rows_after`` for the audit UI.
        """
        await self._ensure_init()
        parsed = MemoryURI.parse(uri)
        target_ns = resolve_namespace(parsed, current=self._namespace)
        return await self._dispatch_remember(
            parsed, content, priority, disclosure, target_ns
        )

    async def remember_shared(
        self,
        uri: str,
        content: str,
        priority: int = 0,
        disclosure: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Force-write to the shared namespace regardless of URI prefix.

        Use for explicit globally-visible writes (KnowHow seed, agent
        defaults). Versioning policy still applies — a ``preference://``
        URI written via ``remember_shared`` still creates a chain.
        """
        await self._ensure_init()
        parsed = MemoryURI.parse(uri)
        return await self._dispatch_remember(
            parsed, content, priority, disclosure, SHARED_NAMESPACE
        )

    async def _dispatch_remember(
        self,
        parsed: MemoryURI,
        content: str,
        priority: int,
        disclosure: Optional[str],
        target_ns: str,
    ) -> Dict[str, Any]:
        """Route to the right engine verb and rebuild the legacy result dict."""
        # Auto-vivify intermediate parents — engine writes are strict but
        # the legacy MemoryClient contract was permissive (any nested URI
        # creates the chain on demand).
        await self._ensure_parent_chain(parsed, target_ns)

        assert self._engine is not None  # _ensure_init guarantees this
        if should_version(parsed):
            ref = await self._engine.upsert_versioned(
                parsed, content, namespace=target_ns,
                priority=priority,
                disclosure=disclosure,
            )
            memory_id = ref.new_memory_id
            node_uuid = ref.node_uuid
        else:
            single_ref = await self._engine.upsert(
                parsed, content, namespace=target_ns,
                priority=priority,
                disclosure=disclosure,
            )
            memory_id = single_ref.memory_id
            node_uuid = single_ref.node_uuid

        result = await self._materialize_result(
            parsed, target_ns, memory_id, node_uuid, priority
        )

        # Audit UI: surface the write to the review changeset store. The
        # store is a process-wide singleton so this works for the bot,
        # the desktop server, and CLI calls alike.
        try:
            from .snapshot import get_changeset_store

            store = get_changeset_store()
            store.record_many(
                before_state=result.get("rows_before", {}),
                after_state=result.get("rows_after", {}),
            )
        except Exception:
            # Audit recording is best-effort — never block a real write.
            pass

        return result

    async def _materialize_result(
        self,
        parsed: MemoryURI,
        target_ns: str,
        memory_id: int,
        node_uuid: str,
        priority: int,
    ) -> Dict[str, Any]:
        """Re-fetch the four written rows for the legacy result shape."""
        assert self._engine is not None
        db = self._engine.db
        import sqlalchemy as sa

        async with db.session() as s:
            path_row = (
                await s.execute(
                    sa.select(Path).where(
                        Path.namespace == target_ns,
                        Path.domain == parsed.domain,
                        Path.path == parsed.path,
                    )
                )
            ).scalar_one()
            edge = await s.get(Edge, path_row.edge_id)
            node = await s.get(Node, node_uuid)
            memory = await s.get(Memory, memory_id)

        return {
            "id": memory_id,
            "node_uuid": node_uuid,
            "domain": parsed.domain,
            "path": parsed.path,
            "uri": str(parsed),
            "namespace": target_ns,
            "priority": priority,
            "rows_before": {},
            "rows_after": {
                "nodes": [serialize_row(node)],
                "memories": [serialize_memory_ref(memory)],
                "edges": [serialize_row(edge)],
                "paths": [serialize_row(path_row)],
            },
        }

    async def _ensure_parent_chain(
        self, parsed: MemoryURI, namespace: str
    ) -> None:
        """Walk up parent URIs and create container nodes for missing ones.

        Engine writes refuse missing parents; the legacy MemoryClient
        contract allowed nested URIs to be created on demand. We replicate
        that by recursively calling ``upsert`` on each missing ancestor
        with placeholder content. Top-level URIs (no slash) need nothing.
        """
        if "/" not in parsed.path:
            return

        parent = parsed.parent()
        if parent is None or parent.is_root:
            return

        assert self._engine is not None
        existing = await self._engine.recall(
            parent, namespace=namespace, fallback_to_shared=True
        )
        if existing is not None:
            return

        # Walk further up first so the engine.upsert below has a parent.
        await self._ensure_parent_chain(parent, namespace)

        await self._engine.upsert(
            parent,
            f"Container node: {parent}",
            namespace=namespace,
        )

    # ------------------------------------------------------------------
    # Read verbs (delegate)
    # ------------------------------------------------------------------

    async def recall(
        self,
        uri: str,
        *,
        fallback_to_shared: bool = True,
    ) -> Optional[MemoryRecord]:
        """Fetch the active memory at the URI in the client's namespace."""
        await self._ensure_init()
        assert self._engine is not None
        return await self._engine.recall(
            uri,
            namespace=self._namespace,
            fallback_to_shared=fallback_to_shared,
        )

    async def search(
        self,
        query: str,
        limit: int = 10,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """FTS over the client's namespace (with shared fallback)."""
        await self._ensure_init()
        assert self._engine is not None
        return await self._engine.search(
            query, namespace=self._namespace, domain=domain, limit=limit
        )

    async def list_children(self, uri: str = "core://") -> List[Any]:
        """List direct children of ``uri`` strictly inside this namespace."""
        await self._ensure_init()
        assert self._engine is not None
        return await self._engine.list_children(uri, namespace=self._namespace)

    async def get_subtree(
        self, uri: str, *, limit: int = 100
    ) -> List[Any]:
        """Flat listing under (current namespace, uri)."""
        await self._ensure_init()
        assert self._engine is not None
        return await self._engine.get_subtree(
            uri, namespace=self._namespace, limit=limit
        )

    async def list_children_rich(
        self,
        uri: str = "core://",
        *,
        context_domain: Optional[str] = None,
        context_path: Optional[str] = None,
        include_shared: bool = False,
    ) -> List[Dict[str, Any]]:
        """Desktop-tree dicts for the children of ``uri``.

        Returns the rich shape (``content_snippet``, ``priority``,
        ``approx_children_count`` …) consumed by the desktop
        ``/memory/children`` endpoint. Strict by default;
        ``include_shared=True`` surfaces ``__shared__`` children too.
        """
        await self._ensure_init()
        assert self._engine is not None
        return await self._engine.list_children_rich(
            uri,
            namespace=self._namespace,
            context_domain=context_domain,
            context_path=context_path,
            include_shared=include_shared,
        )

    async def list_paths(
        self,
        *,
        domain: Optional[str] = None,
        include_shared: bool = False,
    ) -> List[Dict[str, Any]]:
        """Flat catalog of Paths in the client's namespace.

        Used by ``/memory/domains`` to count nodes per domain.
        ``include_shared=True`` returns a dedupe'd union with
        ``__shared__`` (namespace copy wins on URI collision).
        """
        await self._ensure_init()
        assert self._engine is not None
        return await self._engine.list_paths(
            namespace=self._namespace,
            domain=domain,
            include_shared=include_shared,
        )

    async def update_existing(
        self,
        uri: str,
        *,
        content: Optional[str] = None,
        priority: Optional[int] = None,
        disclosure: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing memory in this client's namespace.

        Path must already exist. Content change creates a new active
        ``Memory`` row (the previous one is deprecated, audit chain
        intact); a metadata-only call patches the ``Edge`` directly.

        Returns the legacy ``GraphService.update_memory`` audit shape
        (``old_memory_id``, ``new_memory_id``, ``rows_before``,
        ``rows_after`` …) so the desktop ``/memory/update`` endpoint
        can swap without UI changes.
        """
        await self._ensure_init()

        if content is None and priority is None and disclosure is None:
            raise ValueError(
                "update_existing requires at least one of content, "
                "priority, disclosure"
            )

        parsed = MemoryURI.parse(uri)
        if not parsed.path:
            raise ValueError("Cannot update the root path")

        target_ns = self._namespace
        assert self._engine is not None

        # Pre-flight: snapshot the active row so the audit dict can
        # show "what was there before" alongside "what is there now".
        async with self._engine.db.session() as s:
            row = (
                await s.execute(
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
                    .where(
                        Path.namespace == target_ns,
                        Path.domain == parsed.domain,
                        Path.path == parsed.path,
                    )
                    .order_by(Memory.created_at.desc())
                    .limit(1)
                )
            ).first()
            if not row:
                raise ValueError(
                    f"Path '{uri}' not found or memory is deprecated"
                )
            old_memory, edge, _ = row
            old_id = old_memory.id
            edge_id = edge.id
            node_uuid = edge.child_uuid
            edge_before = serialize_row(edge)
            old_memory_ref = serialize_memory_ref(old_memory)

        # Translate "preserve" semantics: omit kwargs whose value is
        # None so the engine's ``_UNSET`` sentinel preserves the
        # current edge metadata.
        engine_kwargs: Dict[str, Any] = {}
        if priority is not None:
            engine_kwargs["priority"] = priority
        if disclosure is not None:
            engine_kwargs["disclosure"] = disclosure

        if content is not None:
            ref = await self._engine.upsert_versioned(
                parsed, content, namespace=target_ns, **engine_kwargs
            )
            new_memory_id = ref.new_memory_id
        else:
            await self._engine.patch_edge_metadata(
                parsed, namespace=target_ns, **engine_kwargs
            )
            new_memory_id = old_id

        # Post-flight: rebuild rows_before / rows_after for the audit
        # changeset bookkeeper. Edge metadata is included only when it
        # actually changed; memory rows are included only on content
        # updates.
        #
        # rows_after["memories"] intentionally has TWO entries on a
        # content update — the now-deprecated old row (re-fetched so
        # it carries deprecated=True, migrated_to=new_id) followed by
        # the new active row. This mirrors GraphService.update_memory's
        # legacy shape so the desktop review pane can render both
        # sides of the chain transition without a separate query.
        rows_before: Dict[str, list] = {}
        rows_after: Dict[str, list] = {}
        async with self._engine.db.session() as s:
            edge_after = serialize_row(await s.get(Edge, edge_id))
            if edge_before != edge_after:
                rows_before["edges"] = [edge_before]
                rows_after["edges"] = [edge_after]

            if content is not None:
                rows_before["memories"] = [old_memory_ref]
                rows_after["memories"] = [
                    serialize_memory_ref(await s.get(Memory, old_id)),
                    serialize_memory_ref(
                        await s.get(Memory, new_memory_id)
                    ),
                ]

        return {
            "domain": parsed.domain,
            "path": parsed.path,
            "uri": str(parsed),
            "old_memory_id": old_id,
            "new_memory_id": new_memory_id,
            "node_uuid": node_uuid,
            "rows_before": rows_before,
            "rows_after": rows_after,
        }

    # ------------------------------------------------------------------
    # Composite verbs
    # ------------------------------------------------------------------

    async def boot(self) -> str:
        """Load the boot URIs (core://agent + core://my_user by default).

        ``OMICSCLAW_MEMORY_CORE_URIS`` overrides the URI list. Each URI is
        recalled with shared fallback, so a per-user ``core://my_user``
        with no row falls through to whatever the shared default is.
        """
        await self._ensure_init()
        core_uris_str = os.getenv(
            "OMICSCLAW_MEMORY_CORE_URIS",
            "core://agent,core://my_user",
        )
        core_uris = [u.strip() for u in core_uris_str.split(",") if u.strip()]

        parts = []
        for uri in core_uris:
            record = await self.recall(uri)
            if record is not None and record.content:
                parts.append(f"[{uri}]\n{record.content}")
        return "\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # forget — engine-routed since slice 2 of §6.2 GraphService
    # retirement; subtree cascade with orphan prevention and soft-
    # deprecate of the affected memories lives in MemoryEngine.delete.
    # ------------------------------------------------------------------

    async def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return recently updated memories scoped to the client's namespace.

        Strict — no shared fallback, by the same rule as
        ``MemoryEngine.list_children`` (recent listings should not bleed
        ``__shared__`` system rows into a per-user view).
        """
        await self._ensure_init()
        assert self._engine is not None
        return await self._engine.get_recent(
            namespace=self._namespace, limit=limit
        )

    async def forget(self, uri: str) -> Dict[str, Any]:
        """Remove a memory by URI, mirroring ``remember``'s routing policy.

        Resolves the target namespace via the same ``namespace_policy``
        that ``remember`` uses: ``core://agent/*``, ``core://kh/*``,
        ``core://my_user_default/*`` route to ``__shared__`` regardless of
        the caller's namespace; everything else stays in the caller's
        namespace. This keeps ``remember(uri) → forget(uri)`` symmetric
        — a per-user client can clean up its own shared-prefix writes —
        while still preventing cross-user deletes for non-shared URIs
        (``MemoryClient(namespace="A").forget("dataset://x")`` cannot
        reach namespace ``B``).

        Delegates to ``MemoryEngine.delete``: subtree cascade with
        orphan prevention and soft-deprecate of the affected memories
        (review pane can roll back).
        """
        await self._ensure_init()

        parsed = MemoryURI.parse(uri)
        target_ns = resolve_namespace(parsed, current=self._namespace)
        assert self._engine is not None
        result = await self._engine.delete(parsed, namespace=target_ns)

        try:
            from .snapshot import get_changeset_store

            store = get_changeset_store()
            store.record_many(
                before_state=result.get("rows_before", {}),
                after_state=result.get("rows_after", {}),
            )
        except Exception:
            pass

        return result
