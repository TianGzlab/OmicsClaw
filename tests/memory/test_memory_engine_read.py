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
