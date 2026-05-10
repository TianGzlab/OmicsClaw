"""Tests for MemoryEngine — namespace-aware hot-path writes.

PR #3a covers the three write verbs (upsert, upsert_versioned,
patch_edge_metadata). Read verbs are reserved for PR #3b.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine, MemoryRef, VersionedMemoryRef
from omicsclaw.memory.models import Edge, Memory, Path, SearchDocument
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def engine(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    yield MemoryEngine(db, search), db
    await db.close()


# ----------------------------------------------------------------------
# upsert (overwrite mode)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_creates_path_and_memory(engine):
    eng, db = engine

    ref = await eng.upsert(
        "core://agent", "you are a helpful agent", namespace="tg/userA"
    )

    assert isinstance(ref, MemoryRef)
    assert ref.namespace == "tg/userA"
    assert ref.uri == "core://agent"
    assert ref.memory_id > 0
    assert ref.node_uuid

    async with db.session() as s:
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == "tg/userA",
                    Path.domain == "core",
                    Path.path == "agent",
                )
            )
        ).scalar_one()
        assert path_row.edge_id is not None

        edge = await s.get(Edge, path_row.edge_id)
        assert edge.child_uuid == ref.node_uuid
        assert edge.name == "agent"

        memory = await s.get(Memory, ref.memory_id)
        assert memory.content == "you are a helpful agent"
        assert memory.deprecated is False
        assert memory.node_uuid == ref.node_uuid


@pytest.mark.asyncio
async def test_upsert_idempotent_same_namespace_updates_content(engine):
    eng, db = engine

    first = await eng.upsert("core://agent", "v1", namespace="tg/userA")
    second = await eng.upsert("core://agent", "v2", namespace="tg/userA")

    # Same memory row — overwrite mode does NOT create a new Memory.
    assert first.memory_id == second.memory_id
    assert first.node_uuid == second.node_uuid

    async with db.session() as s:
        memory = await s.get(Memory, second.memory_id)
        assert memory.content == "v2"

        # Exactly one Memory row total for this node.
        all_memories = (
            await s.execute(
                sa.select(Memory).where(Memory.node_uuid == second.node_uuid)
            )
        ).scalars().all()
        assert len(all_memories) == 1


@pytest.mark.asyncio
async def test_upsert_different_namespace_creates_separate_path(engine):
    eng, db = engine

    a = await eng.upsert("core://agent", "voice for A", namespace="tg/userA")
    b = await eng.upsert("core://agent", "voice for B", namespace="tg/userB")

    # Independent paths, independent nodes/memories.
    assert a.namespace != b.namespace
    assert a.node_uuid != b.node_uuid
    assert a.memory_id != b.memory_id

    async with db.session() as s:
        rows = (
            await s.execute(
                sa.select(Path).where(
                    Path.domain == "core", Path.path == "agent"
                )
            )
        ).scalars().all()
        namespaces = sorted(r.namespace for r in rows)
        assert namespaces == ["tg/userA", "tg/userB"]


@pytest.mark.asyncio
async def test_upsert_refreshes_search_document(engine):
    eng, db = engine

    ref = await eng.upsert(
        "core://agent", "search me", namespace="tg/userA", priority=5
    )

    async with db.session() as s:
        sd = (
            await s.execute(
                sa.select(SearchDocument).where(
                    SearchDocument.namespace == "tg/userA",
                    SearchDocument.domain == "core",
                    SearchDocument.path == "agent",
                )
            )
        ).scalar_one()
        assert sd.content == "search me"
        assert sd.memory_id == ref.memory_id
        assert sd.node_uuid == ref.node_uuid
        assert sd.uri == "core://agent"
        assert sd.priority == 5


@pytest.mark.asyncio
async def test_upsert_nested_path_requires_parent(engine):
    eng, _ = engine

    with pytest.raises(ValueError, match="Parent path"):
        await eng.upsert(
            "analysis://sc-de/run_42",
            "results",
            namespace="tg/userA",
        )


@pytest.mark.asyncio
async def test_upsert_nested_path_works_when_parent_exists(engine):
    eng, db = engine

    parent = await eng.upsert("analysis://sc-de", "parent", namespace="tg/userA")
    child = await eng.upsert(
        "analysis://sc-de/run_42", "results", namespace="tg/userA"
    )

    assert child.node_uuid != parent.node_uuid

    async with db.session() as s:
        edge = (
            await s.execute(
                sa.select(Edge).where(Edge.child_uuid == child.node_uuid)
            )
        ).scalar_one()
        assert edge.parent_uuid == parent.node_uuid
        assert edge.name == "run_42"


@pytest.mark.asyncio
async def test_upsert_priority_and_disclosure_on_create(engine):
    eng, db = engine

    ref = await eng.upsert(
        "core://agent",
        "content",
        namespace="tg/userA",
        priority=7,
        disclosure="user-set",
    )

    async with db.session() as s:
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == "tg/userA",
                    Path.domain == "core",
                    Path.path == "agent",
                )
            )
        ).scalar_one()
        edge = await s.get(Edge, path_row.edge_id)
        assert edge.priority == 7
        assert edge.disclosure == "user-set"


@pytest.mark.asyncio
async def test_upsert_does_not_clobber_priority_when_omitted_on_update(engine):
    """Re-calling upsert without priority should preserve the edge's priority."""
    eng, db = engine

    await eng.upsert("core://agent", "v1", namespace="tg/userA", priority=42)
    await eng.upsert("core://agent", "v2", namespace="tg/userA")  # priority omitted

    async with db.session() as s:
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == "tg/userA",
                    Path.domain == "core",
                    Path.path == "agent",
                )
            )
        ).scalar_one()
        edge = await s.get(Edge, path_row.edge_id)
        assert edge.priority == 42


@pytest.mark.asyncio
async def test_upsert_accepts_memory_uri_object(engine):
    """upsert should accept either a string or a MemoryURI."""
    from omicsclaw.memory.uri import MemoryURI

    eng, db = engine
    ref = await eng.upsert(
        MemoryURI(domain="core", path="agent"),
        "content",
        namespace="tg/userA",
    )
    assert ref.uri == "core://agent"


# ----------------------------------------------------------------------
# upsert_versioned (deprecation chain mode)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_versioned_first_write_no_chain(engine):
    eng, db = engine

    ref = await eng.upsert_versioned(
        "core://agent", "v1", namespace="tg/userA"
    )

    assert isinstance(ref, VersionedMemoryRef)
    assert ref.old_memory_id is None
    assert ref.new_memory_id > 0
    assert ref.namespace == "tg/userA"
    assert ref.uri == "core://agent"

    async with db.session() as s:
        memory = await s.get(Memory, ref.new_memory_id)
        assert memory.deprecated is False
        assert memory.migrated_to is None
        assert memory.content == "v1"


@pytest.mark.asyncio
async def test_upsert_versioned_creates_chain_on_second_write(engine):
    eng, db = engine

    first = await eng.upsert_versioned("core://agent", "v1", namespace="tg/userA")
    second = await eng.upsert_versioned("core://agent", "v2", namespace="tg/userA")

    assert second.old_memory_id == first.new_memory_id
    assert second.new_memory_id != first.new_memory_id
    assert second.node_uuid == first.node_uuid

    async with db.session() as s:
        old = await s.get(Memory, first.new_memory_id)
        new = await s.get(Memory, second.new_memory_id)

        assert old.deprecated is True
        assert old.migrated_to == second.new_memory_id

        assert new.deprecated is False
        assert new.migrated_to is None
        assert new.content == "v2"


@pytest.mark.asyncio
async def test_upsert_versioned_old_search_doc_replaced(engine):
    eng, db = engine

    first = await eng.upsert_versioned("core://agent", "v1", namespace="tg/userA")
    second = await eng.upsert_versioned("core://agent", "v2", namespace="tg/userA")

    async with db.session() as s:
        rows = (
            await s.execute(
                sa.select(SearchDocument).where(
                    SearchDocument.namespace == "tg/userA",
                    SearchDocument.domain == "core",
                    SearchDocument.path == "agent",
                )
            )
        ).scalars().all()
        # Exactly one search_documents row at (namespace, domain, path) — the
        # composite PK guarantees that, but we also assert it points at the
        # new memory_id, not the deprecated one.
        assert len(rows) == 1
        assert rows[0].memory_id == second.new_memory_id
        assert rows[0].content == "v2"


@pytest.mark.asyncio
async def test_upsert_versioned_chain_can_have_3_links(engine):
    eng, db = engine

    r1 = await eng.upsert_versioned("core://agent", "v1", namespace="tg/userA")
    r2 = await eng.upsert_versioned("core://agent", "v2", namespace="tg/userA")
    r3 = await eng.upsert_versioned("core://agent", "v3", namespace="tg/userA")

    async with db.session() as s:
        m1 = await s.get(Memory, r1.new_memory_id)
        m2 = await s.get(Memory, r2.new_memory_id)
        m3 = await s.get(Memory, r3.new_memory_id)

        assert m1.deprecated is True and m1.migrated_to == r2.new_memory_id
        assert m2.deprecated is True and m2.migrated_to == r3.new_memory_id
        assert m3.deprecated is False and m3.migrated_to is None

        # All three memories share the same node_uuid (the conceptual entity).
        assert m1.node_uuid == m2.node_uuid == m3.node_uuid


@pytest.mark.asyncio
async def test_upsert_versioned_returns_namespace_isolated(engine):
    eng, db = engine

    a = await eng.upsert_versioned("core://agent", "for A", namespace="tg/userA")
    b = await eng.upsert_versioned("core://agent", "for B", namespace="tg/userB")

    # Different namespaces → independent chains, independent nodes.
    assert a.node_uuid != b.node_uuid
    assert a.old_memory_id is None
    assert b.old_memory_id is None  # B's first write also has no chain


# ----------------------------------------------------------------------
# patch_edge_metadata
# ----------------------------------------------------------------------


async def _get_edge_for(eng, uri: str, namespace: str):
    """Helper: load the edge backing (namespace, uri)."""
    from omicsclaw.memory.uri import MemoryURI

    parsed = MemoryURI.parse(uri)
    async with eng._db.session() as s:
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == namespace,
                    Path.domain == parsed.domain,
                    Path.path == parsed.path,
                )
            )
        ).scalar_one()
        return await s.get(Edge, path_row.edge_id)


@pytest.mark.asyncio
async def test_patch_edge_metadata_updates_priority(engine):
    eng, db = engine
    await eng.upsert("core://agent", "content", namespace="tg/userA", priority=0)

    await eng.patch_edge_metadata(
        "core://agent", namespace="tg/userA", priority=9
    )

    edge = await _get_edge_for(eng, "core://agent", "tg/userA")
    assert edge.priority == 9


@pytest.mark.asyncio
async def test_patch_edge_metadata_updates_disclosure(engine):
    eng, db = engine
    await eng.upsert("core://agent", "content", namespace="tg/userA")

    await eng.patch_edge_metadata(
        "core://agent", namespace="tg/userA", disclosure="hidden from search"
    )

    edge = await _get_edge_for(eng, "core://agent", "tg/userA")
    assert edge.disclosure == "hidden from search"


@pytest.mark.asyncio
async def test_patch_edge_metadata_updates_both(engine):
    eng, db = engine
    await eng.upsert("core://agent", "content", namespace="tg/userA")

    await eng.patch_edge_metadata(
        "core://agent",
        namespace="tg/userA",
        priority=3,
        disclosure="why this exists",
    )

    edge = await _get_edge_for(eng, "core://agent", "tg/userA")
    assert edge.priority == 3
    assert edge.disclosure == "why this exists"


@pytest.mark.asyncio
async def test_patch_edge_metadata_does_not_touch_memory(engine):
    eng, db = engine
    ref = await eng.upsert("core://agent", "content", namespace="tg/userA")

    async with db.session() as s:
        before = (await s.get(Memory, ref.memory_id)).content
    await eng.patch_edge_metadata(
        "core://agent", namespace="tg/userA", priority=1
    )
    async with db.session() as s:
        memory = await s.get(Memory, ref.memory_id)
        # Same content; same row id (no new memory created).
        assert memory.content == before
        all_memories = (
            await s.execute(
                sa.select(Memory).where(Memory.node_uuid == ref.node_uuid)
            )
        ).scalars().all()
        assert len(all_memories) == 1


@pytest.mark.asyncio
async def test_patch_edge_metadata_refreshes_search_doc(engine):
    eng, db = engine
    await eng.upsert("core://agent", "content", namespace="tg/userA", priority=0)

    await eng.patch_edge_metadata(
        "core://agent", namespace="tg/userA", priority=7
    )

    async with db.session() as s:
        sd = (
            await s.execute(
                sa.select(SearchDocument).where(
                    SearchDocument.namespace == "tg/userA",
                    SearchDocument.domain == "core",
                    SearchDocument.path == "agent",
                )
            )
        ).scalar_one()
        assert sd.priority == 7


@pytest.mark.asyncio
async def test_patch_edge_metadata_namespace_isolated(engine):
    eng, db = engine
    await eng.upsert("core://agent", "A", namespace="tg/userA", priority=1)
    await eng.upsert("core://agent", "B", namespace="tg/userB", priority=1)

    await eng.patch_edge_metadata(
        "core://agent", namespace="tg/userA", priority=99
    )

    edge_a = await _get_edge_for(eng, "core://agent", "tg/userA")
    edge_b = await _get_edge_for(eng, "core://agent", "tg/userB")
    assert edge_a.priority == 99
    assert edge_b.priority == 1  # B unchanged


@pytest.mark.asyncio
async def test_patch_edge_metadata_raises_if_path_missing(engine):
    eng, _ = engine
    with pytest.raises(LookupError, match="not found"):
        await eng.patch_edge_metadata(
            "core://nonexistent", namespace="tg/userA", priority=1
        )


@pytest.mark.asyncio
async def test_patch_edge_metadata_requires_at_least_one_field(engine):
    eng, _ = engine
    await eng.upsert("core://agent", "x", namespace="tg/userA")
    with pytest.raises(ValueError, match="at least one"):
        await eng.patch_edge_metadata("core://agent", namespace="tg/userA")
