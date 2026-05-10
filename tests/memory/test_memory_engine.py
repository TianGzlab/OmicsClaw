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
