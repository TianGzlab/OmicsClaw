"""Tests for MemoryEngine read verbs (PR #3b).

Covers ``recall`` (with shared fallback), ``search`` (namespace-combined),
``list_children`` (strict-namespace), ``get_subtree`` (flat listing), and
the cross-namespace integration scenarios from the plan checkpoint.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine, MemoryRecord, MemoryRef
from omicsclaw.memory.models import Memory
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def engine(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    yield MemoryEngine(db, search), db
    await db.close()


# ----------------------------------------------------------------------
# recall — happy path
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_returns_record_when_present(engine):
    eng, _ = engine
    await eng.upsert("core://agent", "you are an agent", namespace="tg/userA")

    record = await eng.recall("core://agent", namespace="tg/userA")

    assert record is not None
    assert isinstance(record, MemoryRecord)
    assert record.content == "you are an agent"
    assert record.namespace == "tg/userA"
    assert record.loaded_namespace == "tg/userA"
    assert record.uri == "core://agent"
    assert record.memory_id > 0


@pytest.mark.asyncio
async def test_recall_returns_none_when_missing(engine):
    eng, _ = engine
    record = await eng.recall("core://nope", namespace="tg/userA")
    assert record is None


@pytest.mark.asyncio
async def test_recall_returns_none_when_only_deprecated_versions_exist(engine):
    eng, db = engine
    ref = await eng.upsert("core://agent", "v1", namespace="tg/userA")

    async with db.session() as s:
        memory = await s.get(Memory, ref.memory_id)
        memory.deprecated = True

    record = await eng.recall("core://agent", namespace="tg/userA")
    assert record is None


# ----------------------------------------------------------------------
# recall — shared fallback
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_falls_back_to_shared_when_default(engine):
    eng, _ = engine
    # Seed the same URI in __shared__ only.
    await eng.upsert("core://agent", "shared content", namespace="__shared__")

    record = await eng.recall("core://agent", namespace="tg/userA")

    assert record is not None
    assert record.content == "shared content"
    # Fields preserve the *requested* namespace; loaded_namespace tells the
    # caller where the row actually came from.
    assert record.namespace == "tg/userA"
    assert record.loaded_namespace == "__shared__"


@pytest.mark.asyncio
async def test_recall_strict_does_not_fall_back(engine):
    eng, _ = engine
    await eng.upsert("core://agent", "shared content", namespace="__shared__")

    record = await eng.recall(
        "core://agent", namespace="tg/userA", fallback_to_shared=False
    )

    assert record is None


@pytest.mark.asyncio
async def test_recall_prefers_namespace_over_shared(engine):
    eng, _ = engine
    await eng.upsert("core://agent", "shared", namespace="__shared__")
    await eng.upsert("core://agent", "user A own", namespace="tg/userA")

    record = await eng.recall("core://agent", namespace="tg/userA")

    assert record.content == "user A own"
    assert record.loaded_namespace == "tg/userA"


@pytest.mark.asyncio
async def test_recall_namespace_isolation(engine):
    """Without fallback, a write in ns/A is invisible from ns/B."""
    eng, _ = engine
    await eng.upsert("dataset://pbmc.h5ad", "user A's dataset", namespace="tg/userA")

    record = await eng.recall(
        "dataset://pbmc.h5ad",
        namespace="tg/userB",
        fallback_to_shared=False,
    )
    assert record is None


@pytest.mark.asyncio
async def test_recall_shared_recall_from_shared_returns_directly(engine):
    """Reading from __shared__ shouldn't try to fall back to itself twice."""
    eng, _ = engine
    await eng.upsert("core://agent", "shared", namespace="__shared__")

    record = await eng.recall("core://agent", namespace="__shared__")

    assert record is not None
    assert record.loaded_namespace == "__shared__"


@pytest.mark.asyncio
async def test_recall_accepts_memory_uri_object(engine):
    from omicsclaw.memory.uri import MemoryURI

    eng, _ = engine
    await eng.upsert("core://agent", "x", namespace="tg/userA")

    record = await eng.recall(
        MemoryURI(domain="core", path="agent"), namespace="tg/userA"
    )
    assert record is not None
    assert record.uri == "core://agent"


# ----------------------------------------------------------------------
# search — namespace-combined FTS
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_finds_in_namespace(engine):
    eng, _ = engine
    await eng.upsert(
        "analysis://sc-de", "perform differential expression", namespace="tg/userA"
    )

    hits = await eng.search("differential", namespace="tg/userA")

    assert any(hit["uri"] == "analysis://sc-de" for hit in hits)


@pytest.mark.asyncio
async def test_search_finds_shared_content(engine):
    eng, _ = engine
    await eng.upsert(
        "core://agent",
        "you are a helpful spatial omics agent",
        namespace="__shared__",
    )

    hits = await eng.search("spatial omics", namespace="tg/userA")

    assert any(hit["uri"] == "core://agent" for hit in hits)


@pytest.mark.asyncio
async def test_search_does_not_leak_across_namespaces(engine):
    """Critical: writes in ns/A must not appear in searches from ns/B."""
    eng, _ = engine
    await eng.upsert(
        "dataset://pbmc.h5ad",
        "user A's secret dataset",
        namespace="tg/userA",
    )

    hits = await eng.search("secret", namespace="tg/userB")

    assert all(hit["uri"] != "dataset://pbmc.h5ad" for hit in hits)


@pytest.mark.asyncio
async def test_search_respects_domain_filter(engine):
    eng, _ = engine
    await eng.upsert(
        "analysis://sc-de", "differential expression", namespace="tg/userA"
    )
    await eng.upsert(
        "dataset://pbmc.h5ad", "differential dataset", namespace="tg/userA"
    )

    hits = await eng.search(
        "differential", namespace="tg/userA", domain="analysis"
    )

    assert all(hit["domain"] == "analysis" for hit in hits)


@pytest.mark.asyncio
async def test_search_respects_limit(engine):
    eng, _ = engine
    for i in range(5):
        await eng.upsert(
            f"analysis://run_{i}",
            f"differential expression run {i}",
            namespace="tg/userA",
        )

    hits = await eng.search("differential", namespace="tg/userA", limit=2)

    assert len(hits) <= 2


@pytest.mark.asyncio
async def test_search_returns_empty_for_no_match(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "alpha", namespace="tg/userA")

    hits = await eng.search("zeta-not-present", namespace="tg/userA")

    assert hits == []


@pytest.mark.asyncio
async def test_search_orders_namespace_before_shared(engine):
    """Per-namespace hits should outrank __shared__ hits with comparable score.

    Both rows match the same query token; the namespace's row should appear
    in the result list before the shared one.
    """
    eng, _ = engine
    await eng.upsert(
        "core://agent", "you are a helpful agent", namespace="__shared__"
    )
    await eng.upsert(
        "preference://style",
        "user A prefers helpful agents",
        namespace="tg/userA",
    )

    hits = await eng.search("helpful", namespace="tg/userA", limit=10)

    uris = [h["uri"] for h in hits]
    a_idx = uris.index("preference://style")
    shared_idx = uris.index("core://agent")
    assert a_idx < shared_idx


# ----------------------------------------------------------------------
# list_children — strict-namespace
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_children_returns_direct_children_in_namespace(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "parent", namespace="tg/userA")
    await eng.upsert(
        "analysis://sc-de/run_42", "child A", namespace="tg/userA"
    )
    await eng.upsert(
        "analysis://sc-de/run_99", "child B", namespace="tg/userA"
    )

    children = await eng.list_children(
        "analysis://sc-de", namespace="tg/userA"
    )

    uris = sorted(c.uri for c in children)
    assert uris == ["analysis://sc-de/run_42", "analysis://sc-de/run_99"]
    assert all(c.namespace == "tg/userA" for c in children)


@pytest.mark.asyncio
async def test_list_children_does_not_include_grandchildren(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "parent", namespace="tg/userA")
    await eng.upsert(
        "analysis://sc-de/run_42", "child", namespace="tg/userA"
    )
    await eng.upsert(
        "analysis://sc-de/run_42/sub", "grandchild", namespace="tg/userA"
    )

    children = await eng.list_children(
        "analysis://sc-de", namespace="tg/userA"
    )
    uris = [c.uri for c in children]

    assert "analysis://sc-de/run_42" in uris
    assert "analysis://sc-de/run_42/sub" not in uris


@pytest.mark.asyncio
async def test_list_children_strict_excludes_shared_children(engine):
    """When the parent is shared and a child also lives in __shared__, that
    shared child must NOT appear in a per-user listing — strict semantics."""
    eng, _ = engine
    await eng.upsert("core://agent", "shared parent", namespace="__shared__")
    await eng.upsert(
        "core://agent/voice", "shared voice", namespace="__shared__"
    )
    await eng.upsert(
        "core://agent/style",
        "user A's style override",
        namespace="tg/userA",
    )

    children = await eng.list_children("core://agent", namespace="tg/userA")
    uris = sorted(c.uri for c in children)

    assert uris == ["core://agent/style"]


@pytest.mark.asyncio
async def test_list_children_returns_empty_when_no_children(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "parent only", namespace="tg/userA")

    children = await eng.list_children(
        "analysis://sc-de", namespace="tg/userA"
    )
    assert children == []


@pytest.mark.asyncio
async def test_list_children_returns_empty_when_parent_missing(engine):
    eng, _ = engine
    children = await eng.list_children(
        "analysis://nonexistent", namespace="tg/userA"
    )
    assert children == []


@pytest.mark.asyncio
async def test_list_children_root_lists_top_level(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "top1", namespace="tg/userA")
    await eng.upsert("analysis://sc-velocity", "top2", namespace="tg/userA")

    from omicsclaw.memory.uri import MemoryURI

    children = await eng.list_children(
        MemoryURI(domain="analysis", path=""), namespace="tg/userA"
    )
    uris = sorted(c.uri for c in children)

    assert "analysis://sc-de" in uris
    assert "analysis://sc-velocity" in uris


@pytest.mark.asyncio
async def test_list_children_returns_active_memory_ref(engine):
    eng, db = engine
    parent = await eng.upsert("analysis://sc-de", "parent", namespace="tg/userA")
    child = await eng.upsert(
        "analysis://sc-de/run_42", "child", namespace="tg/userA"
    )

    children = await eng.list_children(
        "analysis://sc-de", namespace="tg/userA"
    )

    assert len(children) == 1
    ref = children[0]
    assert isinstance(ref, MemoryRef)
    assert ref.memory_id == child.memory_id
    assert ref.node_uuid == child.node_uuid


# ----------------------------------------------------------------------
# get_subtree — flat listing under a prefix
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_subtree_returns_root_and_descendants(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "root", namespace="tg/userA")
    await eng.upsert(
        "analysis://sc-de/run_1", "child1", namespace="tg/userA"
    )
    await eng.upsert(
        "analysis://sc-de/run_1/sub", "grand", namespace="tg/userA"
    )
    await eng.upsert(
        "analysis://sc-de/run_2", "child2", namespace="tg/userA"
    )

    subtree = await eng.get_subtree("analysis://sc-de", namespace="tg/userA")
    uris = [r.uri for r in subtree]

    assert uris == [
        "analysis://sc-de",
        "analysis://sc-de/run_1",
        "analysis://sc-de/run_1/sub",
        "analysis://sc-de/run_2",
    ]


@pytest.mark.asyncio
async def test_get_subtree_excludes_other_namespaces(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "user A's", namespace="tg/userA")
    await eng.upsert(
        "analysis://sc-de/run_1", "user A's child", namespace="tg/userA"
    )
    await eng.upsert("analysis://sc-de", "user B's", namespace="tg/userB")
    await eng.upsert(
        "analysis://sc-de/run_99", "user B's child", namespace="tg/userB"
    )
    await eng.upsert("analysis://sc-de", "shared", namespace="__shared__")

    subtree = await eng.get_subtree("analysis://sc-de", namespace="tg/userA")
    uris = sorted(r.uri for r in subtree)
    namespaces = {r.namespace for r in subtree}

    assert uris == ["analysis://sc-de", "analysis://sc-de/run_1"]
    assert namespaces == {"tg/userA"}


@pytest.mark.asyncio
async def test_get_subtree_excludes_paths_outside_prefix(engine):
    """Sibling paths that share a prefix substring (not a directory prefix)
    must not be included — e.g. ``sc-de-bonus`` is not under ``sc-de``."""
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "x", namespace="tg/userA")
    await eng.upsert("analysis://sc-de/run_1", "y", namespace="tg/userA")
    await eng.upsert("analysis://sc-de-bonus", "z", namespace="tg/userA")

    subtree = await eng.get_subtree("analysis://sc-de", namespace="tg/userA")
    uris = [r.uri for r in subtree]

    assert "analysis://sc-de-bonus" not in uris
    assert "analysis://sc-de/run_1" in uris


@pytest.mark.asyncio
async def test_get_subtree_respects_limit(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "root", namespace="tg/userA")
    for i in range(10):
        await eng.upsert(
            f"analysis://sc-de/run_{i}", f"r{i}", namespace="tg/userA"
        )

    subtree = await eng.get_subtree(
        "analysis://sc-de", namespace="tg/userA", limit=3
    )
    assert len(subtree) == 3


@pytest.mark.asyncio
async def test_get_subtree_returns_empty_when_no_match(engine):
    eng, _ = engine
    subtree = await eng.get_subtree(
        "analysis://nope", namespace="tg/userA"
    )
    assert subtree == []


@pytest.mark.asyncio
async def test_get_subtree_root_uri_lists_namespace_in_domain(engine):
    eng, _ = engine
    await eng.upsert("analysis://sc-de", "x", namespace="tg/userA")
    await eng.upsert("analysis://sc-velocity", "y", namespace="tg/userA")
    await eng.upsert("dataset://pbmc.h5ad", "z", namespace="tg/userA")

    from omicsclaw.memory.uri import MemoryURI

    subtree = await eng.get_subtree(
        MemoryURI(domain="analysis", path=""), namespace="tg/userA"
    )
    uris = sorted(r.uri for r in subtree)

    assert uris == ["analysis://sc-de", "analysis://sc-velocity"]
    assert all(r.uri.startswith("analysis://") for r in subtree)


@pytest.mark.asyncio
async def test_get_subtree_skips_paths_with_no_active_memory(engine):
    eng, db = engine
    await eng.upsert("analysis://sc-de", "root", namespace="tg/userA")
    ref = await eng.upsert(
        "analysis://sc-de/run_1", "child", namespace="tg/userA"
    )

    async with db.session() as s:
        memory = await s.get(Memory, ref.memory_id)
        memory.deprecated = True

    subtree = await eng.get_subtree("analysis://sc-de", namespace="tg/userA")
    uris = [r.uri for r in subtree]

    assert "analysis://sc-de" in uris
    assert "analysis://sc-de/run_1" not in uris
