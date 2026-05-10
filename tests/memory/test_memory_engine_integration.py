"""End-to-end + cross-namespace integration tests for MemoryEngine.

Exercise the full upsert → recall → search → list_children → get_subtree
loop under realistic multi-tenant scenarios. These tests are the
checkpoint guardrails referenced in the plan §3b — if they regress,
namespace isolation has cracked somewhere.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def engine(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    yield MemoryEngine(db, search), db
    await db.close()


# ----------------------------------------------------------------------
# Plan checkpoint scenarios
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_across_three_namespaces(engine):
    """Upsert and recall round-trip independently for three users."""
    eng, _ = engine
    namespaces = ("tg/userA", "tg/userB", "app/desktop_user")
    for ns in namespaces:
        await eng.upsert(
            "preference://style",
            f"{ns}'s style",
            namespace=ns,
        )

    for ns in namespaces:
        record = await eng.recall("preference://style", namespace=ns)
        assert record is not None
        assert record.content == f"{ns}'s style"
        assert record.loaded_namespace == ns


@pytest.mark.asyncio
async def test_cross_namespace_isolation_without_fallback(engine):
    """A write in ns/A is invisible from ns/B when fallback is disabled."""
    eng, _ = engine
    await eng.upsert(
        "dataset://pbmc.h5ad", "user A's secret", namespace="tg/userA"
    )

    # Each surface gets a clean view without fallback.
    for other_ns in ("tg/userB", "app/desktop_user"):
        record = await eng.recall(
            "dataset://pbmc.h5ad",
            namespace=other_ns,
            fallback_to_shared=False,
        )
        assert record is None

        hits = await eng.search("secret", namespace=other_ns)
        assert all(h["uri"] != "dataset://pbmc.h5ad" for h in hits)

        children = await eng.list_children(
            "dataset://", namespace=other_ns
        )
        assert all(
            c.uri != "dataset://pbmc.h5ad" for c in children
        )


@pytest.mark.asyncio
async def test_shared_content_visible_via_recall_fallback(engine):
    """Globally-shared content (core://agent) is visible from any namespace."""
    eng, _ = engine
    await eng.upsert(
        "core://agent",
        "you are a helpful agent",
        namespace="__shared__",
    )

    for ns in ("tg/userA", "tg/userB", "app/desktop_user"):
        record = await eng.recall("core://agent", namespace=ns)
        assert record is not None
        assert record.content == "you are a helpful agent"
        assert record.loaded_namespace == "__shared__"


@pytest.mark.asyncio
async def test_user_override_shadows_shared_in_recall(engine):
    """When a per-user write exists, it shadows the shared one for that user."""
    eng, _ = engine
    await eng.upsert(
        "core://agent", "shared default", namespace="__shared__"
    )
    await eng.upsert(
        "core://agent", "user A override", namespace="tg/userA"
    )

    a = await eng.recall("core://agent", namespace="tg/userA")
    b = await eng.recall("core://agent", namespace="tg/userB")

    assert a.content == "user A override"
    assert a.loaded_namespace == "tg/userA"
    assert b.content == "shared default"
    assert b.loaded_namespace == "__shared__"


@pytest.mark.asyncio
async def test_search_combines_namespace_and_shared(engine):
    """Search returns both per-namespace and shared hits."""
    eng, _ = engine
    await eng.upsert(
        "core://agent", "helpful agent (shared)", namespace="__shared__"
    )
    await eng.upsert(
        "preference://style",
        "user A wants helpful style",
        namespace="tg/userA",
    )

    hits = await eng.search("helpful", namespace="tg/userA", limit=10)
    uris = {h["uri"] for h in hits}

    assert "core://agent" in uris
    assert "preference://style" in uris


@pytest.mark.asyncio
async def test_list_children_does_not_combine_with_shared(engine):
    """Strict listing — shared subtree is invisible to per-user list_children."""
    eng, _ = engine
    await eng.upsert(
        "core://agent", "shared parent", namespace="__shared__"
    )
    await eng.upsert(
        "core://agent/voice", "shared voice", namespace="__shared__"
    )

    user_children = await eng.list_children(
        "core://agent", namespace="tg/userA"
    )
    shared_children = await eng.list_children(
        "core://agent", namespace="__shared__"
    )

    assert user_children == []
    assert {c.uri for c in shared_children} == {"core://agent/voice"}


@pytest.mark.asyncio
async def test_get_subtree_strict_to_namespace(engine):
    """Subtree listing is strict — does not blend in shared content."""
    eng, _ = engine
    await eng.upsert(
        "core://agent", "shared", namespace="__shared__"
    )
    await eng.upsert(
        "core://agent/voice", "shared voice", namespace="__shared__"
    )
    await eng.upsert(
        "core://agent/style", "user A style", namespace="tg/userA"
    )

    subtree = await eng.get_subtree("core://agent", namespace="tg/userA")
    uris = sorted(r.uri for r in subtree)

    # Only the user's own writes — no shared parent, no shared voice.
    assert uris == ["core://agent/style"]


@pytest.mark.asyncio
async def test_versioned_chain_recall_returns_active_head(engine):
    """After three versioned writes, recall returns the active head only."""
    eng, _ = engine
    await eng.upsert_versioned("core://agent", "v1", namespace="tg/userA")
    await eng.upsert_versioned("core://agent", "v2", namespace="tg/userA")
    r3 = await eng.upsert_versioned(
        "core://agent", "v3", namespace="tg/userA"
    )

    record = await eng.recall("core://agent", namespace="tg/userA")
    assert record is not None
    assert record.content == "v3"
    assert record.memory_id == r3.new_memory_id
