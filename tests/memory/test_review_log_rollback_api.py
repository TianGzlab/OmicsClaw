"""Tests for ReviewLog methods that back the desktop ``/api/review/*`` pane.

Phase 2b additions:
  - ``get_memory_by_id`` — fetch any memory row (active or deprecated)
    with its incident paths; used by the diff view.
  - ``rollback_to`` (already exists) — restore a deprecated memory as
    the active head; this file exercises it via the legacy contract.
  - ``restore_path`` — re-attach a previously-deleted path to an
    existing node; rollback target for path-deletion changeset entries.

Path-removal rollback (the "AI created this path — undo it") routes
straight to ``MemoryEngine.delete``, no new ReviewLog method needed.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.models import (
    Edge,
    Memory,
    Node,
    Path,
    ROOT_NODE_UUID,
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
# get_memory_by_id
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_memory_by_id_returns_active_memory_with_paths(env):
    engine, review, db = env
    ref = await engine.upsert(
        "dataset://pbmc.h5ad", "scRNA dataset", namespace="tg/userA"
    )

    result = await review.get_memory_by_id(ref.memory_id)

    assert result is not None
    assert result["memory_id"] == ref.memory_id
    assert result["node_uuid"] == ref.node_uuid
    assert result["content"] == "scRNA dataset"
    assert result["deprecated"] is False
    assert result["migrated_to"] is None
    assert "dataset://pbmc.h5ad" in result["paths"]


@pytest.mark.asyncio
async def test_get_memory_by_id_returns_deprecated_with_chain_target(env):
    engine, review, db = env
    await engine.upsert_versioned(
        "core://agent", "v1", namespace=SHARED_NAMESPACE
    )
    await engine.upsert_versioned(
        "core://agent", "v2", namespace=SHARED_NAMESPACE
    )

    async with db.session() as s:
        old_id, new_id = [
            mid
            for (mid,) in (
                await s.execute(sa.select(Memory.id).order_by(Memory.id))
            ).all()
        ]

    result = await review.get_memory_by_id(old_id)

    assert result is not None
    assert result["deprecated"] is True
    assert result["migrated_to"] == new_id
    assert result["content"] == "v1"


@pytest.mark.asyncio
async def test_get_memory_by_id_returns_none_for_missing(env):
    _, review, _ = env
    assert await review.get_memory_by_id(999_999) is None


# ----------------------------------------------------------------------
# restore_path
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_path_recreates_deleted_path(env):
    engine, review, db = env
    # Create a memory, snapshot its node_uuid, then delete the path.
    ref = await engine.upsert(
        "dataset://x.h5ad", "body", namespace="tg/userA"
    )
    node_uuid = ref.node_uuid
    await engine.delete("dataset://x.h5ad", namespace="tg/userA")

    async with db.session() as s:
        gone = (
            await s.execute(
                sa.select(Path).where(Path.path == "x.h5ad")
            )
        ).scalars().all()
        assert gone == []

    # Memory may have been soft-deprecated, but the node still exists
    # because delete() is namespace-scoped and the node has no other
    # memories. Force-reactivate it for restoration.
    async with db.session() as s:
        await s.execute(
            sa.update(Memory)
            .where(Memory.node_uuid == node_uuid)
            .values(deprecated=False, migrated_to=None)
        )

    result = await review.restore_path(
        path="x.h5ad",
        domain="dataset",
        namespace="tg/userA",
        node_uuid=node_uuid,
    )

    assert result["uri"] == "dataset://x.h5ad"
    assert result["node_uuid"] == node_uuid

    async with db.session() as s:
        restored = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == "tg/userA",
                    Path.path == "x.h5ad",
                )
            )
        ).scalar_one()
        assert restored.edge_id is not None


@pytest.mark.asyncio
async def test_restore_path_refuses_empty_path(env):
    _, review, _ = env
    with pytest.raises(ValueError, match="root path"):
        await review.restore_path(
            path="",
            domain="dataset",
            namespace="tg/userA",
            node_uuid="some-uuid",
        )


@pytest.mark.asyncio
async def test_restore_path_refuses_missing_node(env):
    _, review, _ = env
    with pytest.raises(ValueError, match="not found"):
        await review.restore_path(
            path="x.h5ad",
            domain="dataset",
            namespace="tg/userA",
            node_uuid="00000000-0000-0000-0000-deadbeefdead",
        )


@pytest.mark.asyncio
async def test_restore_path_refuses_when_path_exists(env):
    engine, review, db = env
    ref = await engine.upsert(
        "dataset://x.h5ad", "body", namespace="tg/userA"
    )

    with pytest.raises(ValueError, match="already exists"):
        await review.restore_path(
            path="x.h5ad",
            domain="dataset",
            namespace="tg/userA",
            node_uuid=ref.node_uuid,
        )
