"""Tests for ``MemoryEngine.seed_shared`` — idempotent write to ``__shared__``.

Used by KH bootstrap (Phase 1) so that re-running ``init_db()`` on a
populated database does not produce duplicate version chains or
needlessly bump version counters for unchanged knowledge entries.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.models import Memory, Path, SHARED_NAMESPACE
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def engine(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    yield MemoryEngine(db, search), db
    await db.close()


@pytest.mark.asyncio
async def test_seed_shared_first_call_writes_under_shared_namespace(engine):
    eng, db = engine

    ref, written = await eng.seed_shared(
        "core://kh/safety", "do not invent gene-disease associations"
    )

    assert written is True
    assert ref.namespace == SHARED_NAMESPACE
    assert ref.uri == "core://kh/safety"

    async with db.session() as s:
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == SHARED_NAMESPACE,
                    Path.domain == "core",
                    Path.path == "kh/safety",
                )
            )
        ).scalar_one()
        assert path_row.edge_id is not None


@pytest.mark.asyncio
async def test_seed_shared_same_content_is_noop(engine):
    eng, db = engine

    await eng.seed_shared("core://kh/safety", "rules v1")
    _, written = await eng.seed_shared("core://kh/safety", "rules v1")

    assert written is False

    async with db.session() as s:
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == SHARED_NAMESPACE,
                    Path.path == "kh/safety",
                )
            )
        ).scalar_one()
        memories = (
            await s.execute(
                sa.select(Memory).where(
                    Memory.node_uuid
                    == (
                        await s.execute(
                            sa.select(sa.text("child_uuid"))
                            .select_from(sa.text("edges"))
                            .where(sa.text("id = :eid")),
                            {"eid": path_row.edge_id},
                        )
                    ).scalar_one()
                )
            )
        ).scalars().all()
        # Exactly one memory row — no version proliferation, no overwrite churn.
        assert len(memories) == 1
        assert memories[0].content == "rules v1"


@pytest.mark.asyncio
async def test_seed_shared_changed_content_overwrites_for_kh(engine):
    eng, db = engine

    _, written_first = await eng.seed_shared("core://kh/safety", "rules v1")
    _, written_second = await eng.seed_shared("core://kh/safety", "rules v2")

    assert written_first is True
    assert written_second is True

    async with db.session() as s:
        # core://kh/* is not in VERSIONED_PREFIXES — overwrite mode keeps
        # exactly one Memory row whose content reflects the latest seed.
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == SHARED_NAMESPACE,
                    Path.path == "kh/safety",
                )
            )
        ).scalar_one()
        edge_child = (
            await s.execute(
                sa.text(
                    "SELECT child_uuid FROM edges WHERE id = :eid"
                ),
                {"eid": path_row.edge_id},
            )
        ).scalar_one()
        memories = (
            await s.execute(
                sa.select(Memory).where(Memory.node_uuid == edge_child)
            )
        ).scalars().all()
        assert len(memories) == 1
        assert memories[0].content == "rules v2"
        assert memories[0].deprecated is False


@pytest.mark.asyncio
async def test_seed_shared_versioned_uri_creates_version_chain(engine):
    """For URIs in VERSIONED_PREFIXES (e.g., core://agent), changed
    content must produce a new active row and deprecate the previous
    one — same versioning policy as ``MemoryClient.remember_shared``.
    """
    eng, db = engine

    _, w1 = await eng.seed_shared("core://agent", "voice v1")
    _, w2 = await eng.seed_shared("core://agent", "voice v2")

    assert w1 is True
    assert w2 is True

    async with db.session() as s:
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == SHARED_NAMESPACE,
                    Path.path == "agent",
                )
            )
        ).scalar_one()
        edge_child = (
            await s.execute(
                sa.text("SELECT child_uuid FROM edges WHERE id = :eid"),
                {"eid": path_row.edge_id},
            )
        ).scalar_one()
        memories = (
            await s.execute(
                sa.select(Memory)
                .where(Memory.node_uuid == edge_child)
                .order_by(Memory.id)
            )
        ).scalars().all()
        assert len(memories) == 2
        assert memories[0].content == "voice v1"
        assert memories[0].deprecated is True
        assert memories[1].content == "voice v2"
        assert memories[1].deprecated is False


@pytest.mark.asyncio
async def test_seed_shared_always_targets_shared_namespace(engine):
    """``seed_shared`` is hard-locked to ``__shared__`` — there is no
    way to redirect it via a caller-provided namespace. This is what
    distinguishes it from ``MemoryClient.remember``.
    """
    eng, db = engine

    await eng.seed_shared("core://kh/policy", "policy v1")

    async with db.session() as s:
        # Nothing landed in any per-user namespace.
        rows = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace != SHARED_NAMESPACE,
                    Path.path == "kh/policy",
                )
            )
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_seed_shared_unchanged_versioned_uri_is_noop(engine):
    """Even for versioned URIs, seeding the same content twice must
    not append a new version — that's the whole point of an
    idempotent seed.
    """
    eng, db = engine

    await eng.seed_shared("core://agent", "voice v1")
    _, written = await eng.seed_shared("core://agent", "voice v1")

    assert written is False

    async with db.session() as s:
        path_row = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == SHARED_NAMESPACE,
                    Path.path == "agent",
                )
            )
        ).scalar_one()
        edge_child = (
            await s.execute(
                sa.text("SELECT child_uuid FROM edges WHERE id = :eid"),
                {"eid": path_row.edge_id},
            )
        ).scalar_one()
        memories = (
            await s.execute(
                sa.select(Memory).where(Memory.node_uuid == edge_child)
            )
        ).scalars().all()
        assert len(memories) == 1
