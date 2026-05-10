"""Tests for ReviewLog cold-path operations (PR #4b).

ReviewLog handles operations that don't sit on the hot write path:
  - version-chain inspection / rollback (4b.2)
  - orphan + GC (4b.3)
  - browse_shared (4b.4)
  - changeset list/approve/discard (4b.5)

These are the operations the desktop "Review & Audit" pane needs, and
the bot's /forget command will eventually call cascade_delete from here.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.models import Edge, Memory, Node, Path
from omicsclaw.memory.review_log import (
    NoVersionHistoryError,
    OrphanEntry,
    ReviewLog,
    VersionEntry,
)
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def env(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    engine = MemoryEngine(db, search)

    # Per-test changeset store so tests don't pollute the global singleton.
    from omicsclaw.memory.snapshot import ChangesetStore

    changeset_store = ChangesetStore(snapshot_dir=str(tmp_path / "changesets"))
    review = ReviewLog(db, engine, changeset_store=changeset_store)
    yield engine, review, db, changeset_store
    await db.close()


# ----------------------------------------------------------------------
# 4b.2 — version chain
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_version_chain_returns_chain_in_age_order(env):
    engine, review, _, _ = env
    await engine.upsert_versioned("core://agent", "v1", namespace="__shared__")
    await engine.upsert_versioned("core://agent", "v2", namespace="__shared__")
    await engine.upsert_versioned("core://agent", "v3", namespace="__shared__")

    entries = await review.list_version_chain(
        "core://agent", namespace="__shared__"
    )

    assert len(entries) == 3
    assert all(isinstance(e, VersionEntry) for e in entries)
    # Oldest (deprecated) first; newest (active) last.
    assert [e.content for e in entries] == ["v1", "v2", "v3"]
    assert [e.deprecated for e in entries] == [True, True, False]
    assert entries[-1].migrated_to is None
    assert entries[0].migrated_to == entries[1].memory_id
    assert entries[1].migrated_to == entries[2].memory_id


@pytest.mark.asyncio
async def test_list_version_chain_raises_for_overwrite_only_uri(env):
    """``dataset://`` is overwrite-only — there is no chain to list."""
    engine, review, _, _ = env
    await engine.upsert("dataset://pbmc.h5ad", "v1", namespace="tg/userA")

    with pytest.raises(NoVersionHistoryError, match="not versioned"):
        await review.list_version_chain(
            "dataset://pbmc.h5ad", namespace="tg/userA"
        )


@pytest.mark.asyncio
async def test_list_version_chain_returns_empty_for_missing_path(env):
    """An existent versioned URI with no chain row returns an empty list,
    not an exception. Distinguishes "no history" from "this URI cannot
    have history" (the overwrite case)."""
    _, review, _, _ = env
    entries = await review.list_version_chain(
        "core://agent", namespace="__shared__"
    )
    assert entries == []


@pytest.mark.asyncio
async def test_rollback_to_makes_old_version_active(env):
    engine, review, _, _ = env
    r1 = await engine.upsert_versioned(
        "core://agent", "v1", namespace="__shared__"
    )
    r2 = await engine.upsert_versioned(
        "core://agent", "v2", namespace="__shared__"
    )
    r3 = await engine.upsert_versioned(
        "core://agent", "v3", namespace="__shared__"
    )

    # Rollback to v1.
    await review.rollback_to(r1.new_memory_id, namespace="__shared__")

    # v1 is now active (deprecated=False); v2 and v3 are deprecated.
    record = await engine.recall("core://agent", namespace="__shared__")
    assert record is not None
    assert record.content == "v1"
    assert record.memory_id == r1.new_memory_id


@pytest.mark.asyncio
async def test_rollback_to_raises_when_memory_not_found(env):
    _, review, _, _ = env
    with pytest.raises(ValueError, match="not found"):
        await review.rollback_to(99999, namespace="__shared__")


@pytest.mark.asyncio
async def test_rollback_to_noop_when_already_active(env):
    engine, review, _, _ = env
    r1 = await engine.upsert_versioned(
        "core://agent", "v1", namespace="__shared__"
    )
    # Roll back to the active head — should be a no-op.
    result = await review.rollback_to(r1.new_memory_id, namespace="__shared__")
    assert result.was_already_active is True


# ----------------------------------------------------------------------
# 4b.3 — orphans + GC
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_orphans_finds_deprecated_memories_with_no_successor(env):
    """An orphan is a deprecated memory whose successor was deleted —
    the chain points nowhere active. We seed the state explicitly via
    direct DB writes since the engine's normal API can't produce orphans."""
    engine, review, db, _ = env
    r1 = await engine.upsert_versioned(
        "core://agent", "v1", namespace="__shared__"
    )
    r2 = await engine.upsert_versioned(
        "core://agent", "v2", namespace="__shared__"
    )

    # Manually delete v2 to orphan v1.
    async with db.session() as s:
        await s.execute(sa.delete(Memory).where(Memory.id == r2.new_memory_id))

    orphans = await review.list_orphans()

    orphan_ids = {o.memory_id for o in orphans}
    assert r1.new_memory_id in orphan_ids
    assert all(isinstance(o, OrphanEntry) for o in orphans)


@pytest.mark.asyncio
async def test_list_orphans_filters_by_namespace(env):
    """Orphans visible only in a specific namespace partition."""
    engine, review, db, _ = env
    r_a = await engine.upsert_versioned(
        "core://agent", "for A", namespace="tg/userA"
    )
    await engine.upsert_versioned("core://agent", "for A v2", namespace="tg/userA")
    r_b = await engine.upsert_versioned(
        "core://agent", "for B", namespace="tg/userB"
    )
    await engine.upsert_versioned("core://agent", "for B v2", namespace="tg/userB")

    async with db.session() as s:
        # Orphan only A's chain by deleting A's active head.
        a_active = (
            await s.execute(
                sa.select(Memory)
                .where(
                    Memory.deprecated == False,  # noqa: E712
                    Memory.node_uuid == r_a.node_uuid,
                )
            )
        ).scalar_one()
        await s.execute(sa.delete(Memory).where(Memory.id == a_active.id))

    a_orphans = await review.list_orphans(namespace="tg/userA")
    b_orphans = await review.list_orphans(namespace="tg/userB")

    assert any(o.memory_id == r_a.new_memory_id for o in a_orphans)
    assert b_orphans == []


@pytest.mark.asyncio
async def test_cascade_delete_removes_node_and_paths(env):
    engine, review, db, _ = env
    await engine.upsert("dataset://pbmc.h5ad", "v1", namespace="tg/userA")

    await review.cascade_delete(
        "dataset://pbmc.h5ad", namespace="tg/userA"
    )

    record = await engine.recall(
        "dataset://pbmc.h5ad",
        namespace="tg/userA",
        fallback_to_shared=False,
    )
    assert record is None

    async with db.session() as s:
        path_count = (
            await s.execute(
                sa.select(sa.func.count())
                .select_from(Path)
                .where(
                    Path.namespace == "tg/userA",
                    Path.domain == "dataset",
                    Path.path == "pbmc.h5ad",
                )
            )
        ).scalar_one()
        assert path_count == 0


@pytest.mark.asyncio
async def test_cascade_delete_respects_namespace(env):
    """Deleting in ns/A doesn't touch ns/B's row at the same URI."""
    engine, review, _, _ = env
    await engine.upsert("dataset://pbmc.h5ad", "A", namespace="tg/userA")
    await engine.upsert("dataset://pbmc.h5ad", "B", namespace="tg/userB")

    await review.cascade_delete(
        "dataset://pbmc.h5ad", namespace="tg/userA"
    )

    a = await engine.recall(
        "dataset://pbmc.h5ad",
        namespace="tg/userA",
        fallback_to_shared=False,
    )
    b = await engine.recall(
        "dataset://pbmc.h5ad",
        namespace="tg/userB",
        fallback_to_shared=False,
    )
    assert a is None
    assert b is not None
    assert b.content == "B"


@pytest.mark.asyncio
async def test_gc_pathless_edges_removes_edges_with_no_paths(env):
    """An edge whose only Path was deleted is dead-weight; GC removes it."""
    engine, review, db, _ = env
    await engine.upsert("dataset://pbmc.h5ad", "v1", namespace="tg/userA")

    async with db.session() as s:
        edge_id_before = (
            await s.execute(
                sa.select(Path.edge_id).where(
                    Path.namespace == "tg/userA",
                    Path.domain == "dataset",
                    Path.path == "pbmc.h5ad",
                )
            )
        ).scalar_one()
        # Manually delete the path row (simulating an orphan-edge state).
        await s.execute(
            sa.delete(Path).where(
                Path.namespace == "tg/userA",
                Path.domain == "dataset",
                Path.path == "pbmc.h5ad",
            )
        )

    removed = await review.gc_pathless_edges()
    assert removed >= 1

    async with db.session() as s:
        edge_after = await s.get(Edge, edge_id_before)
        assert edge_after is None


@pytest.mark.asyncio
async def test_gc_pathless_edges_preserves_edges_referenced_from_other_namespaces(env):
    """An edge referenced by ANY namespace's Path must survive GC.

    The previous design accepted a `namespace` parameter that silently
    deleted edges referenced only by other namespaces — the data-loss
    bug PR #4b's review caught. Test guards against the regression.
    """
    engine, review, db, _ = env
    await engine.upsert("dataset://shared.h5ad", "A", namespace="tg/userA")
    await engine.upsert("dataset://shared.h5ad", "B", namespace="tg/userB")

    # Snapshot the two edge ids; both must survive GC.
    async with db.session() as s:
        edge_ids = [
            row.edge_id
            for row in (
                await s.execute(
                    sa.select(Path).where(
                        Path.domain == "dataset",
                        Path.path == "shared.h5ad",
                    )
                )
            ).scalars().all()
        ]

    removed = await review.gc_pathless_edges()
    # Other tests in this module may have left orphan edges around; we
    # only assert that OUR two edges still exist.
    async with db.session() as s:
        for eid in edge_ids:
            edge_after = await s.get(Edge, eid)
            assert edge_after is not None, (
                f"GC removed edge {eid} that was still referenced"
            )


# ----------------------------------------------------------------------
# 4b.4 — browse_shared
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browse_shared_lists_only_shared_partition(env):
    engine, review, _, _ = env
    await engine.upsert("core://agent", "shared root", namespace="__shared__")
    await engine.upsert(
        "core://agent/voice", "shared voice", namespace="__shared__"
    )
    await engine.upsert(
        "core://agent/style", "user style", namespace="tg/userA"
    )

    children = await review.browse_shared("core://agent")
    uris = sorted(c.uri for c in children)

    assert uris == ["core://agent/voice"]


@pytest.mark.asyncio
async def test_browse_shared_root_lists_top_level_shared(env):
    engine, review, _, _ = env
    await engine.upsert("core://agent", "x", namespace="__shared__")
    await engine.upsert("core://other", "y", namespace="__shared__")
    await engine.upsert("dataset://A", "z", namespace="tg/userA")  # not shared

    from omicsclaw.memory.uri import MemoryURI

    children = await review.browse_shared(MemoryURI(domain="core", path=""))
    uris = sorted(c.uri for c in children)

    assert uris == ["core://agent", "core://other"]


# ----------------------------------------------------------------------
# 4b.5 — changesets
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pending_changes_reads_changeset_store(env):
    """ReviewLog reads from the changeset store passed to its constructor.
    The fixture injects a per-test ChangesetStore so we don't pollute
    the global singleton."""
    _, review, _, store = env

    store.record_many(
        before_state={},
        after_state={"nodes": [{"uuid": "test-uuid-1"}]},
    )

    pending = await review.list_pending_changes()
    assert isinstance(pending, list)
    assert len(pending) >= 1


@pytest.mark.asyncio
async def test_discard_pending_changes_clears_the_store(env):
    _, review, _, store = env

    store.record_many(
        before_state={},
        after_state={"nodes": [{"uuid": "test-uuid-2"}]},
    )
    assert store.get_change_count() >= 1

    discarded = await review.discard_pending_changes()
    assert discarded >= 1
    assert store.get_change_count() == 0


@pytest.mark.asyncio
async def test_approve_changes_clears_all_when_no_ids(env):
    _, review, _, store = env
    store.record_many(
        before_state={},
        after_state={"nodes": [{"uuid": "approve-uuid"}]},
    )
    assert store.get_change_count() >= 1

    approved = await review.approve_changes()
    assert approved >= 1
    assert store.get_change_count() == 0
