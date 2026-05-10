"""Tests for namespace isolation across legacy GraphService stragglers
and CompatMemoryStore session-fallback behavior.

These tests pin the contract that the surface-layer wiring promises but
the legacy GraphService methods (still wired into MemoryClient.forget,
MemoryClient.get_recent, and three /memory/* server endpoints) used to
break: namespace-scoped reads/writes must not cross into other users'
partitions.

Red→green pairs in this file:
  - test_forget_does_not_delete_other_namespace_path     (D2)
  - test_get_recent_only_returns_own_namespace            (D2')
  - test_get_children_filters_by_namespace                (D3)
  - test_get_all_paths_filters_by_namespace               (D3')
  - test_update_memory_respects_namespace                 (5th GraphService site)
  - test_client_for_session_refuses_when_session_missing  (D5)
  - test_desktop_chat_user_id_matches_desktop_namespace   (D1)
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.compat import CompatMemoryStore, DatasetMemory
from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.graph import GraphService
from omicsclaw.memory.memory_client import MemoryClient
from omicsclaw.memory.models import Path, SHARED_NAMESPACE
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def env(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    engine = MemoryEngine(db, search)
    graph = GraphService(db, search)
    yield engine, db, graph
    await db.close()


@pytest_asyncio.fixture
async def two_clients(env):
    engine, _, _ = env
    yield (
        MemoryClient(engine=engine, namespace="tg/userA"),
        MemoryClient(engine=engine, namespace="tg/userB"),
    )


# ----------------------------------------------------------------------
# D2 — forget must not cross namespace
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forget_does_not_delete_other_namespace_path(two_clients, env):
    """User A's forget('dataset://shared.h5ad') must NOT delete User B's
    same URI in their own namespace.

    This regression pins PR #131-class data-loss bugs: the legacy
    GraphService.remove_path used to do `WHERE domain=X AND path=Y` with
    no namespace filter, so userA.forget would race with whichever row
    .first() picked — sometimes userB's.
    """
    engine, _, _ = env
    client_a, client_b = two_clients

    await client_a.remember("dataset://shared.h5ad", "A's content")
    await client_b.remember("dataset://shared.h5ad", "B's content")

    await client_a.forget("dataset://shared.h5ad")

    # B's row must survive untouched.
    record_b = await engine.recall(
        "dataset://shared.h5ad", namespace="tg/userB", fallback_to_shared=False
    )
    assert record_b is not None, "User B's path was unexpectedly deleted"
    assert record_b.content == "B's content"

    # A's row must be gone.
    record_a = await engine.recall(
        "dataset://shared.h5ad", namespace="tg/userA", fallback_to_shared=False
    )
    assert record_a is None


# ----------------------------------------------------------------------
# D2 follow-up — forget must mirror remember's shared-prefix routing
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forget_routes_shared_prefix_uris_to_shared(env, two_clients):
    """``MemoryClient.remember("core://agent/style", ...)`` writes to
    ``__shared__`` via ``namespace_policy``. ``forget`` must mirror that
    routing so a per-user client can delete what it earlier wrote;
    otherwise ``remember(uri) → forget(uri)`` is asymmetric and the row
    becomes un-removable through the same client.
    """
    engine, _, _ = env
    client_a, _ = two_clients

    await client_a.remember("core://agent/style", "concise replies")

    # Sanity: it landed in __shared__, not tg/userA.
    record = await engine.recall(
        "core://agent/style",
        namespace=SHARED_NAMESPACE,
        fallback_to_shared=False,
    )
    assert record is not None
    assert record.content == "concise replies"

    await client_a.forget("core://agent/style")

    record_after = await engine.recall(
        "core://agent/style",
        namespace=SHARED_NAMESPACE,
        fallback_to_shared=False,
    )
    assert record_after is None, (
        "forget did not remove the shared-prefix row — remember/forget "
        "asymmetric"
    )


# ----------------------------------------------------------------------
# D2' — get_recent must not leak across namespaces
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_only_returns_own_namespace(two_clients):
    """A namespace-bound MemoryClient.get_recent must return rows only
    from that client's namespace (plus optionally __shared__), never
    from other users' partitions."""
    client_a, client_b = two_clients

    await client_a.remember("dataset://onlyA.h5ad", "A only")
    await client_b.remember("dataset://onlyB.h5ad", "B only")

    rows = await client_a.get_recent(limit=10)
    uris = {r["uri"] for r in rows}
    assert "dataset://onlyA.h5ad" in uris
    assert "dataset://onlyB.h5ad" not in uris, (
        "get_recent leaked another namespace's URI into the caller's view"
    )


@pytest.mark.asyncio
async def test_get_recent_excludes_shared_rows(env, two_clients):
    """get_recent is strict (no __shared__ fallback) by the same rule as
    list_children / get_subtree. A core://agent shared row written by
    one user must NOT bleed into another user's recent listing — that
    would re-introduce a different cross-namespace leak.
    """
    client_a, client_b = two_clients

    await client_a.remember("core://agent/style", "concise")  # → __shared__
    await client_b.remember("dataset://onlyB.h5ad", "B's data")

    rows_b = await client_b.get_recent(limit=10)
    uris_b = {r["uri"] for r in rows_b}
    assert "dataset://onlyB.h5ad" in uris_b
    assert "core://agent/style" not in uris_b, (
        "get_recent leaked a __shared__ row into a per-user listing"
    )


# ----------------------------------------------------------------------
# D3 — graph.get_children must filter by namespace
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_children_filters_by_namespace(env, two_clients):
    """When two namespaces have sibling top-level paths, get_children at
    root scoped to one namespace must surface only that namespace's
    children. The desktop /memory/children endpoint calls this with
    node_uuid=ROOT, so this is the real production call shape."""
    _, _, graph = env
    client_a, client_b = two_clients

    await client_a.remember("analysis://onlyA", "A's top-level analysis")
    await client_b.remember("analysis://onlyB", "B's top-level analysis")

    children = await graph.get_children(
        context_domain="analysis",
        namespace="tg/userA",
    )
    paths = {c["path"] for c in children}
    assert "onlyA" in paths
    assert "onlyB" not in paths, (
        "get_children leaked another namespace's top-level URI"
    )


# ----------------------------------------------------------------------
# D3' — graph.get_all_paths must filter by namespace
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_paths_filters_by_namespace(env, two_clients):
    """get_all_paths(namespace='A') must skip B's rows entirely."""
    _, _, graph = env
    client_a, client_b = two_clients

    await client_a.remember("dataset://onlyA.h5ad", "A")
    await client_b.remember("dataset://onlyB.h5ad", "B")

    rows = await graph.get_all_paths(namespace="tg/userA")
    uris = {r["uri"] for r in rows}
    assert "dataset://onlyA.h5ad" in uris
    assert "dataset://onlyB.h5ad" not in uris


# ----------------------------------------------------------------------
# Desktop UI mode — include_shared=True for /memory/* endpoints
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_children_include_shared_surfaces_user_writes(env, two_clients):
    """Desktop tree view (`include_shared=True`) must show shared-prefix
    rows the same client wrote via remember(). Without this the user
    can write a `core://agent/style` row but never see it in the tree."""
    _, _, graph = env
    client_a, client_b = two_clients

    await client_a.remember("core://agent/style", "concise replies")
    await client_b.remember("dataset://onlyB.h5ad", "B's data")

    children = await graph.get_children(
        context_domain="core",
        namespace="tg/userA",
        include_shared=True,
    )
    paths = {c["path"] for c in children}
    assert "agent" in paths or "agent/style" in paths, (
        "include_shared=True should surface user's __shared__ writes"
    )

    # User B's per-user dataset must NOT leak — include_shared adds
    # __shared__ only, not other namespaces.
    children_a_dataset = await graph.get_children(
        context_domain="dataset",
        namespace="tg/userA",
        include_shared=True,
    )
    a_paths = {c["path"] for c in children_a_dataset}
    assert "onlyB.h5ad" not in a_paths


@pytest.mark.asyncio
async def test_get_recent_memories_include_shared(env, two_clients):
    """get_recent_memories(namespace=A, include_shared=True) returns
    A's rows + __shared__ rows (desktop UI mode), but not B's."""
    _, _, graph = env
    client_a, client_b = two_clients

    await client_a.remember("dataset://onlyA.h5ad", "A's data")
    await client_a.remember("core://agent/style", "concise")
    await client_b.remember("dataset://onlyB.h5ad", "B's data")

    rows = await graph.get_recent_memories(
        limit=10, namespace="tg/userA", include_shared=True
    )
    uris = {r["uri"] for r in rows}
    assert "dataset://onlyA.h5ad" in uris
    assert "core://agent/style" in uris, (
        "include_shared=True should include __shared__ rows"
    )
    assert "dataset://onlyB.h5ad" not in uris, (
        "include_shared=True must not leak other namespaces"
    )


@pytest.mark.asyncio
async def test_get_all_paths_include_shared(env, two_clients):
    """get_all_paths(namespace=A, include_shared=True) returns A's URIs
    plus __shared__ URIs, with namespace-matched rows preferred when
    the same URI appears in both."""
    _, _, graph = env
    client_a, client_b = two_clients

    await client_a.remember("dataset://onlyA.h5ad", "A")
    await client_a.remember("core://agent/style", "concise")
    await client_b.remember("dataset://onlyB.h5ad", "B")

    rows = await graph.get_all_paths(
        namespace="tg/userA", include_shared=True
    )
    uris = {r["uri"] for r in rows}
    assert "dataset://onlyA.h5ad" in uris
    assert "core://agent/style" in uris
    assert "dataset://onlyB.h5ad" not in uris


# ----------------------------------------------------------------------
# 5th GraphService site — update_memory must not be locked to __shared__
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_memory_respects_caller_namespace(env, two_clients):
    """graph.update_memory(path, namespace='A') must update A's row,
    not the __shared__ partition.

    The old shim hardcoded ``Path.namespace == SHARED_NAMESPACE``, which
    meant /memory/update could never edit a user's per-namespace memory.
    """
    engine, _, graph = env
    client_a, _ = two_clients

    await client_a.remember("preference://qc/threshold", "20%")

    await graph.update_memory(
        path="qc/threshold",
        domain="preference",
        content="25%",
        namespace="tg/userA",
    )

    record = await engine.recall(
        "preference://qc/threshold",
        namespace="tg/userA",
        fallback_to_shared=False,
    )
    assert record is not None
    assert record.content == "25%"


# ----------------------------------------------------------------------
# D5 — _client_for_session must refuse silently writing to __shared__
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_for_session_refuses_when_session_missing(tmp_path):
    """When a session_id can't be resolved, CompatMemoryStore must NOT
    fall back to writing into __shared__ (where every user can read it).

    The defensive-fallback behavior was a privacy hole: an
    auto-captured dataset arriving before its session was created would
    land globally. The fix raises LookupError so the caller (which
    already wraps in try/except) silently skips the write."""
    store = CompatMemoryStore(database_url=f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await store.initialize()
    try:
        with pytest.raises(LookupError):
            await store._client_for_session("nonexistent-session-id")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_save_memory_swallows_missing_session(tmp_path):
    """save_memory called with an unknown session_id must surface as
    LookupError to the caller (not write to __shared__)."""
    store = CompatMemoryStore(database_url=f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await store.initialize()
    try:
        ds_mem = DatasetMemory(file_path="x.h5ad")
        with pytest.raises(LookupError):
            await store.save_memory("nonexistent-session-id", ds_mem)

        # The dataset URI must NOT appear in __shared__ (or anywhere).
        async with store._db.session() as s:
            rows = (
                await s.execute(
                    sa.select(Path).where(Path.domain == "dataset")
                )
            ).scalars().all()
        assert rows == [], (
            f"save_memory leaked {[(r.namespace, r.path) for r in rows]} "
            "despite missing session"
        )
    finally:
        await store.close()


# ----------------------------------------------------------------------
# D1 — Desktop chat namespace must converge with endpoint namespace
# ----------------------------------------------------------------------


def test_desktop_chat_user_id_matches_desktop_namespace(monkeypatch):
    """Whatever user_id the desktop chat agent loop hands to
    CompatMemoryStore must compose to the same string as
    desktop_namespace().

    Concretely: f"app/{desktop_chat_user_id()}" == desktop_namespace().
    Without this invariant, in multi-launch desktop deployments the
    /memory/* endpoints (read namespace=desktop_namespace()) and the
    chat path (write namespace=f"app/desktop_user") would diverge and
    the UI would not see chat-saved memories.
    """
    from omicsclaw.memory import desktop_chat_user_id, desktop_namespace

    monkeypatch.delenv("OMICSCLAW_DESKTOP_LAUNCH_ID", raising=False)
    assert f"app/{desktop_chat_user_id()}" == desktop_namespace()

    monkeypatch.setenv("OMICSCLAW_DESKTOP_LAUNCH_ID", "launch-xyz")
    assert desktop_chat_user_id() == "launch-xyz"
    assert f"app/{desktop_chat_user_id()}" == desktop_namespace()


# ----------------------------------------------------------------------
# MemoryEngine.get_recent — hot-path "recent listing" verb that replaces
# the GraphService.get_recent_memories call site inside MemoryClient.
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_get_recent_strict_namespace(env):
    """engine.get_recent(namespace=X) returns only rows in X — never
    rows from other namespaces, never __shared__ rows by default."""
    engine, _, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    b = MemoryClient(engine=engine, namespace="tg/B")

    await a.remember("dataset://only_a.h5ad", "A")
    await b.remember("dataset://only_b.h5ad", "B")
    await a.remember("core://agent/style", "concise")  # → __shared__

    rows = await engine.get_recent(namespace="tg/A", limit=10)
    uris = {r["uri"] for r in rows}
    assert "dataset://only_a.h5ad" in uris
    assert "dataset://only_b.h5ad" not in uris, "leaked B's row into A"
    assert "core://agent/style" not in uris, "leaked __shared__ row by default"


@pytest.mark.asyncio
async def test_engine_get_recent_include_shared(env):
    """engine.get_recent(include_shared=True) returns rows from
    (namespace, __shared__) — desktop UI mode."""
    engine, _, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")

    await a.remember("dataset://only_a.h5ad", "A")
    await a.remember("core://agent/style", "concise")  # → __shared__

    rows = await engine.get_recent(
        namespace="tg/A", limit=10, include_shared=True
    )
    uris = {r["uri"] for r in rows}
    assert "dataset://only_a.h5ad" in uris
    assert "core://agent/style" in uris


@pytest.mark.asyncio
async def test_engine_get_recent_return_shape(env):
    """Each row has memory_id, uri, priority, disclosure, created_at —
    matching the legacy GraphService.get_recent_memories shape so the
    MemoryClient swap is shape-preserving."""
    engine, _, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("dataset://x.h5ad", "X", priority=42)

    rows = await engine.get_recent(namespace="tg/A", limit=5)
    assert len(rows) == 1
    row = rows[0]
    assert row["uri"] == "dataset://x.h5ad"
    assert row["priority"] == 42
    assert "disclosure" in row
    assert "memory_id" in row
    assert "created_at" in row  # ISO-format string or None


@pytest.mark.asyncio
async def test_engine_get_recent_honors_limit(env):
    """limit parameter caps result count."""
    engine, _, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    for i in range(5):
        await a.remember(f"dataset://x{i}.h5ad", f"row {i}")

    rows = await engine.get_recent(namespace="tg/A", limit=3)
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_engine_get_recent_excludes_deprecated(env):
    """Versioned writes deprecate the old Memory; get_recent returns
    only the active head, not deprecated predecessors."""
    engine, _, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    # core://my_user is versioned per namespace_policy → upsert_versioned
    await a.remember("core://my_user/note", "v1")
    await a.remember("core://my_user/note", "v2")

    rows = await engine.get_recent(namespace="tg/A", limit=10)
    matching = [r for r in rows if r["uri"] == "core://my_user/note"]
    assert len(matching) == 1, (
        f"expected exactly one active row for the versioned URI, "
        f"got {len(matching)} — deprecated predecessor leaked"
    )
