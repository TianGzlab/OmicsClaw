"""Tests for ReviewLog orphan-management API used by the desktop pane.

Three methods power ``/api/maintenance/*`` after Phase 2a:
  - ``list_orphans_with_chain()`` — orphan inventory with migration target
  - ``get_orphan_detail(memory_id)`` — full content + chain info
  - ``permanently_delete_orphan(memory_id)`` — hard-delete with chain repair
    and GC of the now-memoryless node.

These mirror the legacy GraphService dict-shaped contract so the existing
desktop frontend keeps working without changes.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.models import (
    Edge,
    GlossaryKeyword,
    Memory,
    Node,
    Path,
    SHARED_NAMESPACE,
)
from omicsclaw.memory.review_log import ReviewLog
from omicsclaw.memory.search import SearchIndexer
from omicsclaw.memory.snapshot import ChangesetStore


@pytest_asyncio.fixture
async def env(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    engine = MemoryEngine(db, search)
    changeset_store = ChangesetStore(snapshot_dir=str(tmp_path / "changesets"))
    review = ReviewLog(db, engine, changeset_store=changeset_store)
    yield engine, review, db
    await db.close()


# ----------------------------------------------------------------------
# list_orphans_with_chain
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_orphans_with_chain_returns_dict_shape(env):
    engine, review, _ = env
    # Two versions of core://agent → v1 becomes deprecated.
    await engine.upsert_versioned(
        "core://agent", "old voice", namespace=SHARED_NAMESPACE
    )
    await engine.upsert_versioned(
        "core://agent", "new voice", namespace=SHARED_NAMESPACE
    )

    orphans = await review.list_orphans_with_chain()

    assert isinstance(orphans, list)
    assert len(orphans) == 1
    item = orphans[0]
    # Desktop contract: every entry must carry these fields.
    for key in (
        "id",
        "content_snippet",
        "created_at",
        "deprecated",
        "migrated_to",
        "category",
        "migration_target",
    ):
        assert key in item
    assert item["deprecated"] is True
    assert item["category"] == "deprecated"  # has migrated_to
    assert item["migration_target"] is not None
    assert "id" in item["migration_target"]
    assert "paths" in item["migration_target"]
    assert "content_snippet" in item["migration_target"]


@pytest.mark.asyncio
async def test_list_orphans_with_chain_truncates_long_content(env):
    engine, review, _ = env
    long_body = "x" * 500
    await engine.upsert_versioned(
        "core://agent", long_body, namespace=SHARED_NAMESPACE
    )
    await engine.upsert_versioned(
        "core://agent", "short v2", namespace=SHARED_NAMESPACE
    )

    orphans = await review.list_orphans_with_chain()

    assert len(orphans) == 1
    snippet = orphans[0]["content_snippet"]
    # GraphService legacy contract: 200 chars + "..." trailer.
    assert snippet.endswith("...")
    assert len(snippet) == 203


@pytest.mark.asyncio
async def test_list_orphans_with_chain_classifies_orphaned_vs_deprecated(env):
    """A memory with migrated_to=NULL is 'orphaned'; with target is 'deprecated'."""
    engine, review, db = env
    await engine.upsert_versioned(
        "core://agent", "v1", namespace=SHARED_NAMESPACE
    )
    await engine.upsert_versioned(
        "core://agent", "v2", namespace=SHARED_NAMESPACE
    )

    # Manually null out migrated_to on v1 to simulate the successor having
    # been hard-deleted (this is how "orphaned" arises in practice).
    async with db.session() as s:
        await s.execute(
            sa.update(Memory)
            .where(Memory.deprecated == True)  # noqa: E712
            .values(migrated_to=None)
        )

    orphans = await review.list_orphans_with_chain()

    assert len(orphans) == 1
    assert orphans[0]["category"] == "orphaned"
    assert orphans[0]["migrated_to"] is None
    assert orphans[0]["migration_target"] is None


# ----------------------------------------------------------------------
# get_orphan_detail
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_orphan_detail_returns_full_content(env):
    engine, review, db = env
    await engine.upsert_versioned(
        "core://agent", "deprecated body", namespace=SHARED_NAMESPACE
    )
    await engine.upsert_versioned(
        "core://agent", "active body", namespace=SHARED_NAMESPACE
    )

    async with db.session() as s:
        old_id = (
            await s.execute(
                sa.select(Memory.id).where(Memory.deprecated == True)  # noqa: E712
            )
        ).scalar_one()

    detail = await review.get_orphan_detail(old_id)

    assert detail is not None
    assert detail["id"] == old_id
    assert detail["content"] == "deprecated body"  # full body, not snippet
    assert detail["deprecated"] is True
    assert detail["category"] == "deprecated"
    assert detail["migration_target"]["content"] == "active body"
    assert "paths" in detail["migration_target"]


@pytest.mark.asyncio
async def test_get_orphan_detail_returns_none_for_missing(env):
    _, review, _ = env
    assert await review.get_orphan_detail(999_999) is None


@pytest.mark.asyncio
async def test_get_orphan_detail_marks_active_memory_as_active(env):
    engine, review, db = env
    await engine.upsert("dataset://foo.h5ad", "alive", namespace="tg/userA")
    async with db.session() as s:
        active_id = (
            await s.execute(sa.select(Memory.id))
        ).scalar_one()

    detail = await review.get_orphan_detail(active_id)
    assert detail is not None
    assert detail["category"] == "active"
    assert detail["deprecated"] is False


# ----------------------------------------------------------------------
# permanently_delete_orphan
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permanently_delete_orphan_removes_deprecated_memory(env):
    engine, review, db = env
    await engine.upsert_versioned("core://agent", "v1", namespace=SHARED_NAMESPACE)
    await engine.upsert_versioned("core://agent", "v2", namespace=SHARED_NAMESPACE)

    async with db.session() as s:
        old_id = (
            await s.execute(
                sa.select(Memory.id).where(Memory.deprecated == True)  # noqa: E712
            )
        ).scalar_one()

    result = await review.permanently_delete_orphan(old_id)

    assert result["deleted_memory_id"] == old_id
    assert "rows_before" in result and "rows_after" in result

    async with db.session() as s:
        gone = (
            await s.execute(sa.select(Memory).where(Memory.id == old_id))
        ).scalar_one_or_none()
        assert gone is None
        # Active row survives.
        survivors = (
            await s.execute(
                sa.select(Memory).where(Memory.deprecated == False)  # noqa: E712
            )
        ).scalars().all()
        assert len(survivors) == 1
        assert survivors[0].content == "v2"


@pytest.mark.asyncio
async def test_permanently_delete_orphan_refuses_active_memory(env):
    engine, review, db = env
    await engine.upsert("dataset://x.h5ad", "active", namespace="tg/userA")
    async with db.session() as s:
        active_id = (
            await s.execute(sa.select(Memory.id))
        ).scalar_one()

    with pytest.raises(PermissionError, match="active"):
        await review.permanently_delete_orphan(active_id)


@pytest.mark.asyncio
async def test_permanently_delete_orphan_raises_on_missing(env):
    _, review, _ = env
    with pytest.raises(ValueError, match="not found"):
        await review.permanently_delete_orphan(999_999)


@pytest.mark.asyncio
async def test_permanently_delete_orphan_repairs_chain(env):
    """Deleting a middle link rewrites the surviving link's migrated_to."""
    engine, review, db = env
    await engine.upsert_versioned("core://agent", "v1", namespace=SHARED_NAMESPACE)
    await engine.upsert_versioned("core://agent", "v2", namespace=SHARED_NAMESPACE)
    await engine.upsert_versioned("core://agent", "v3", namespace=SHARED_NAMESPACE)

    async with db.session() as s:
        v1_id, v2_id, v3_id = [
            mid
            for (mid,) in (
                await s.execute(sa.select(Memory.id).order_by(Memory.id))
            ).all()
        ]

    await review.permanently_delete_orphan(v2_id)

    async with db.session() as s:
        v1 = await s.get(Memory, v1_id)
        v3 = await s.get(Memory, v3_id)
        assert v1 is not None and v3 is not None
        # v1's migrated_to was v2; after deletion it must point to v3.
        assert v1.migrated_to == v3_id


@pytest.mark.asyncio
async def test_permanently_delete_orphan_only_removes_direct_edges(env):
    """When the orphan node has active descendants, the GC only cleans
    up that node's own edges/paths — it does NOT recursively descend
    into children. The legacy ``cascade_delete_node`` was more
    aggressive; the conservative ReviewLog behaviour avoids ever
    deleting still-live data through a maintenance operation.

    The desktop pane is admin-only, so the operator can clean up any
    descendant orphans afterwards. This test pins that contract.
    """
    engine, review, db = env

    # Build a parent → child relationship in __shared__, then turn the
    # parent's only memory into an orphan.
    await engine.upsert_versioned(
        "core://agent", "parent body", namespace=SHARED_NAMESPACE
    )
    await engine.upsert(
        "core://agent/child", "child body", namespace=SHARED_NAMESPACE
    )

    async with db.session() as s:
        parent_path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == SHARED_NAMESPACE,
                    Path.path == "agent",
                )
            )
        ).scalar_one()
        parent_edge = await s.get(Edge, parent_path_row.edge_id)
        parent_node_uuid = parent_edge.child_uuid
        parent_mem_id = (
            await s.execute(
                sa.select(Memory.id).where(
                    Memory.node_uuid == parent_node_uuid
                )
            )
        ).scalar_one()
        await s.execute(
            sa.update(Memory)
            .where(Memory.id == parent_mem_id)
            .values(deprecated=True, migrated_to=None)
        )

    await review.permanently_delete_orphan(parent_mem_id)

    async with db.session() as s:
        # Child memory survives — never touched.
        child_mem = (
            await s.execute(
                sa.select(Memory).where(Memory.content == "child body")
            )
        ).scalar_one_or_none()
        assert child_mem is not None


@pytest.mark.asyncio
async def test_permanently_delete_orphan_gcs_memoryless_node(env):
    """When the last memory on a node is deleted, the node + its edges +
    paths + glossary keywords must be cleared."""
    engine, review, db = env
    # Single-version chain whose only memory we'll deprecate then delete.
    await engine.upsert_versioned(
        "core://agent", "lonely", namespace=SHARED_NAMESPACE
    )
    async with db.session() as s:
        await s.execute(
            sa.update(Memory).values(deprecated=True, migrated_to=None)
        )
        mem_id = (await s.execute(sa.select(Memory.id))).scalar_one()
        node_uuid = (
            await s.execute(sa.select(Memory.node_uuid))
        ).scalar_one()

    await review.permanently_delete_orphan(mem_id)

    async with db.session() as s:
        # Node gone.
        node = await s.get(Node, node_uuid)
        assert node is None
        # No edges referencing this node.
        leftover_edges = (
            await s.execute(
                sa.select(Edge).where(Edge.child_uuid == node_uuid)
            )
        ).scalars().all()
        assert leftover_edges == []
        # No paths referencing those edges.
        leftover_paths = (
            await s.execute(
                sa.select(Path).where(Path.path == "agent")
            )
        ).scalars().all()
        assert leftover_paths == []
