"""Tests for ``MemoryEngine.delete`` — the engine-level cascade delete
verb that replaces ``GraphService.remove_path`` for ``MemoryClient.forget``.

Contract pinned by these tests:

  * Single-path delete removes the target Path and prunes the orphan
    edge + node (soft delete: memories stay as deprecated rows).
  * Subtree delete removes the prefix's whole namespace-scoped subtree.
  * Orphan check refuses deletion when a child node would lose its only
    incoming Path (would become unreachable in any namespace).
  * Strict-namespace: ``delete(uri, namespace="A")`` cannot touch
    namespace ``"B"`` rows even when the URI matches.
  * Memories on the deleted node are *deprecated*, not physically
    removed — review pane can later roll back via ``ReviewLog``.
  * Missing path raises ``ValueError`` (mirrors legacy contract).
  * Return shape ``{"rows_before": {...}, "rows_after": {}}`` for the
    audit/changeset UI.

Slice 2 of §6.2 GraphService retirement.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.memory_client import MemoryClient
from omicsclaw.memory.models import Memory, Path
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def env(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    engine = MemoryEngine(db, search)
    yield engine, db
    await db.close()


@pytest.mark.asyncio
async def test_delete_removes_single_path(env):
    """A single-leaf delete removes the target Path row in the namespace."""
    engine, db = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("dataset://x.h5ad", "x")

    result = await engine.delete("dataset://x.h5ad", namespace="tg/A")

    assert result["rows_after"] == {}
    record = await engine.recall(
        "dataset://x.h5ad", namespace="tg/A", fallback_to_shared=False
    )
    assert record is None


@pytest.mark.asyncio
async def test_delete_refuses_when_children_would_orphan(env):
    """Removing a parent whose children only have Paths under the same
    prefix is refused — the orphan precheck protects the user from
    silently losing reachability into a subtree.

    Mirrors ``GraphService.remove_path``'s behaviour: callers must
    delete bottom-up (or attach an alias to the children first) to
    take down a parent. This is intentionally conservative — the
    only forget call sites in production are leaf URIs, so this case
    is the safety net for the rare misuse, not the common path.
    """
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("analysis://run", "parent")
    await a.remember("analysis://run/step1", "child 1")
    await a.remember("analysis://run/step2", "child 2")

    with pytest.raises(ValueError, match="unreachable"):
        await engine.delete("analysis://run", namespace="tg/A")

    # Parent and children must all survive the rejected delete.
    for uri in (
        "analysis://run",
        "analysis://run/step1",
        "analysis://run/step2",
    ):
        record = await engine.recall(
            uri, namespace="tg/A", fallback_to_shared=False
        )
        assert record is not None, (
            f"{uri} was destroyed despite the orphan check raising"
        )


@pytest.mark.asyncio
async def test_delete_strict_namespace(env):
    """delete(uri, namespace='A') must not touch namespace 'B'."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    b = MemoryClient(engine=engine, namespace="tg/B")
    await a.remember("dataset://shared.h5ad", "A")
    await b.remember("dataset://shared.h5ad", "B")

    await engine.delete("dataset://shared.h5ad", namespace="tg/A")

    rec_a = await engine.recall(
        "dataset://shared.h5ad", namespace="tg/A", fallback_to_shared=False
    )
    rec_b = await engine.recall(
        "dataset://shared.h5ad", namespace="tg/B", fallback_to_shared=False
    )
    assert rec_a is None, "A's row survived its own delete"
    assert rec_b is not None, "delete leaked into namespace B"
    assert rec_b.content == "B"


@pytest.mark.asyncio
async def test_delete_soft_deprecates_memories(env):
    """Memories on the deleted node must be marked deprecated, not
    physically removed — the review pane can roll the version chain
    back if the user changes their mind.
    """
    engine, db = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("core://my_user/note", "v1")
    await a.remember("core://my_user/note", "v2")

    # Capture the node_uuid before delete via an engine recall.
    record_before = await engine.recall(
        "core://my_user/note", namespace="tg/A", fallback_to_shared=False
    )
    assert record_before is not None
    node_uuid = record_before.node_uuid

    await engine.delete("core://my_user/note", namespace="tg/A")

    # The Path is gone but the Memory rows still exist (deprecated).
    async with db.session() as s:
        memories = (
            await s.execute(
                sa.select(Memory).where(Memory.node_uuid == node_uuid)
            )
        ).scalars().all()
    assert len(memories) >= 1, (
        "soft-delete contract broken: all memory rows for the node were "
        "physically removed; review-pane rollback impossible"
    )
    assert all(m.deprecated for m in memories), (
        "soft-delete should mark memories deprecated, not leave any active"
    )


@pytest.mark.asyncio
async def test_delete_raises_on_missing_path(env):
    """ValueError mirrors GraphService.remove_path's contract — callers
    (forget) rely on it for "URI not found" UX."""
    engine, _ = env
    with pytest.raises(ValueError, match="not found"):
        await engine.delete("dataset://nonexistent.h5ad", namespace="tg/A")


@pytest.mark.asyncio
async def test_delete_raises_on_root_path(env):
    """Root-path deletion is structurally meaningless — refuse it."""
    engine, _ = env
    with pytest.raises(ValueError, match="root"):
        await engine.delete("core://", namespace="tg/A")


@pytest.mark.asyncio
async def test_delete_returns_audit_dict(env):
    """Return shape ``{rows_before: {...}, rows_after: {}}`` so
    MemoryClient.forget can pipe into ``snapshot.get_changeset_store``
    without code change."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("dataset://x.h5ad", "x")

    result = await engine.delete("dataset://x.h5ad", namespace="tg/A")

    assert "rows_before" in result
    assert "rows_after" in result
    assert result["rows_after"] == {}
    rows_before = result["rows_before"]
    # ChangeCollector buckets — paths must be populated.
    assert "paths" in rows_before
    assert any(
        p.get("domain") == "dataset" and p.get("path") == "x.h5ad"
        for p in rows_before["paths"]
    ), f"expected the deleted path in rows_before.paths, got {rows_before}"
