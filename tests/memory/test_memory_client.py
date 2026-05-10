"""Tests for the rewritten MemoryClient (PR #4a Task 4a.1).

Constructor: ``MemoryClient(engine=..., namespace="...")``. The legacy
``MemoryClient(database_url=...)`` form still works for the three
existing callers (bot, server.py, CompatMemoryStore) and defaults
``namespace`` to ``__shared__``.

Routing policy (delegated to ``namespace_policy``):
  - ``core://agent``, ``core://kh/*``, ``core://my_user_default`` → ``__shared__``
  - everything else → the client's current namespace
  - ``core://agent``, ``core://my_user``, ``preference://*`` → versioned upsert
  - everything else → overwrite upsert
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.memory_client import MemoryClient
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def env(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    engine = MemoryEngine(db, search)
    yield engine, db
    await db.close()


@pytest_asyncio.fixture
async def client_a(env):
    engine, _ = env
    yield MemoryClient(engine=engine, namespace="tg/userA")


# ----------------------------------------------------------------------
# remember — routing via namespace_policy
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remember_dataset_writes_to_current_namespace(client_a, env):
    """dataset:// is per-user — write goes into the client's namespace."""
    engine, _ = env
    await client_a.remember("dataset://pbmc.h5ad", "user A's data")

    record = await engine.recall(
        "dataset://pbmc.h5ad", namespace="tg/userA", fallback_to_shared=False
    )
    assert record is not None
    assert record.content == "user A's data"


@pytest.mark.asyncio
async def test_remember_dataset_overwrites_no_chain(client_a, env):
    """dataset:// uses overwrite mode — re-remembering does not create a chain."""
    engine, db = env
    await client_a.remember("dataset://pbmc.h5ad", "v1")
    await client_a.remember("dataset://pbmc.h5ad", "v2")

    import sqlalchemy as sa

    from omicsclaw.memory.models import Memory, Path

    async with db.session() as s:
        path = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == "tg/userA",
                    Path.domain == "dataset",
                    Path.path == "pbmc.h5ad",
                )
            )
        ).scalar_one()
        from omicsclaw.memory.models import Edge

        edge = await s.get(Edge, path.edge_id)
        memories = (
            await s.execute(
                sa.select(Memory).where(Memory.node_uuid == edge.child_uuid)
            )
        ).scalars().all()
    assert len(memories) == 1
    assert memories[0].content == "v2"


@pytest.mark.asyncio
async def test_remember_core_agent_writes_shared_and_versions(client_a, env):
    """core://agent is shared+versioned — first write to __shared__, second
    creates a deprecation chain in __shared__."""
    engine, db = env
    await client_a.remember("core://agent", "v1")
    await client_a.remember("core://agent", "v2")

    import sqlalchemy as sa

    from omicsclaw.memory.models import Memory, Path

    async with db.session() as s:
        path = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == "__shared__",
                    Path.domain == "core",
                    Path.path == "agent",
                )
            )
        ).scalar_one()
        from omicsclaw.memory.models import Edge

        edge = await s.get(Edge, path.edge_id)
        memories = (
            await s.execute(
                sa.select(Memory)
                .where(Memory.node_uuid == edge.child_uuid)
                .order_by(Memory.id)
            )
        ).scalars().all()

    assert len(memories) == 2
    assert memories[0].content == "v1"
    assert memories[0].deprecated is True
    assert memories[1].content == "v2"
    assert memories[1].deprecated is False


@pytest.mark.asyncio
async def test_remember_preference_versioned_in_user_namespace(client_a, env):
    """preference://* is per-user but versioned (so a user can audit changes)."""
    engine, db = env
    await client_a.remember("preference://style", "v1")
    await client_a.remember("preference://style", "v2")

    import sqlalchemy as sa

    from omicsclaw.memory.models import Edge, Memory, Path

    async with db.session() as s:
        path = (
            await s.execute(
                sa.select(Path).where(
                    Path.namespace == "tg/userA",
                    Path.domain == "preference",
                    Path.path == "style",
                )
            )
        ).scalar_one()
        edge = await s.get(Edge, path.edge_id)
        memories = (
            await s.execute(
                sa.select(Memory)
                .where(Memory.node_uuid == edge.child_uuid)
                .order_by(Memory.id)
            )
        ).scalars().all()

    assert len(memories) == 2
    assert memories[0].deprecated is True


@pytest.mark.asyncio
async def test_remember_shared_forces_shared_namespace(client_a, env):
    """remember_shared writes to __shared__ regardless of URI prefix."""
    engine, _ = env
    await client_a.remember_shared(
        "dataset://global_ref.h5ad", "everyone sees this"
    )

    record = await engine.recall(
        "dataset://global_ref.h5ad",
        namespace="__shared__",
        fallback_to_shared=False,
    )
    assert record is not None
    assert record.content == "everyone sees this"

    # Not visible from another namespace if fallback is off.
    other = await engine.recall(
        "dataset://global_ref.h5ad",
        namespace="tg/userB",
        fallback_to_shared=False,
    )
    assert other is None


# ----------------------------------------------------------------------
# recall / search / list_children — namespace pass-through
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_uses_current_namespace_with_fallback(client_a, env):
    engine, _ = env
    await engine.upsert("core://agent", "shared", namespace="__shared__")

    record = await client_a.recall("core://agent")

    assert record is not None
    assert record.content == "shared"
    assert record.loaded_namespace == "__shared__"


@pytest.mark.asyncio
async def test_search_filters_to_current_namespace_plus_shared(client_a, env):
    engine, _ = env
    await engine.upsert("dataset://A", "user A's data", namespace="tg/userA")
    await engine.upsert("dataset://B", "user B's data", namespace="tg/userB")
    await engine.upsert("core://agent", "shared agent", namespace="__shared__")

    hits = await client_a.search("user")

    uris = {h["uri"] for h in hits}
    assert "dataset://A" in uris
    assert "dataset://B" not in uris


@pytest.mark.asyncio
async def test_list_children_strict_to_current_namespace(client_a, env):
    engine, _ = env
    await engine.upsert("analysis://sc-de", "parent", namespace="tg/userA")
    await engine.upsert(
        "analysis://sc-de/run_1", "user A child", namespace="tg/userA"
    )
    await engine.upsert("analysis://sc-de", "shared parent", namespace="__shared__")
    await engine.upsert(
        "analysis://sc-de/shared_child", "shared child", namespace="__shared__"
    )

    children = await client_a.list_children("analysis://sc-de")
    uris = sorted(c.uri for c in children)

    assert uris == ["analysis://sc-de/run_1"]


# ----------------------------------------------------------------------
# boot — load core identity URIs for LLM context
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boot_loads_default_core_uris(client_a, env, monkeypatch):
    monkeypatch.setenv(
        "OMICSCLAW_MEMORY_CORE_URIS", "core://agent,core://my_user"
    )
    engine, _ = env
    await engine.upsert(
        "core://agent", "you are a helpful agent", namespace="__shared__"
    )
    await engine.upsert("core://my_user", "user A profile", namespace="tg/userA")

    boot = await client_a.boot()

    assert "you are a helpful agent" in boot
    assert "user A profile" in boot


# ----------------------------------------------------------------------
# Constructor variants
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_constructor_with_database_url(tmp_path):
    """Legacy callers passing database_url still work; default namespace
    is __shared__ so they keep writing into the legacy partition."""
    url = f"sqlite+aiosqlite:///{tmp_path}/legacy.db"
    client = MemoryClient(database_url=url)
    try:
        await client.initialize()
        await client.remember("dataset://x.h5ad", "legacy write")

        record = await client.recall("dataset://x.h5ad")
        assert record is not None
        assert record.content == "legacy write"
    finally:
        await client.close()


def test_constructor_rejects_both_url_and_engine():
    with pytest.raises(ValueError, match="Pass either"):
        MemoryClient(database_url="sqlite:///x", engine=object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_engine_constructor_uses_supplied_namespace(env):
    engine, _ = env
    client = MemoryClient(engine=engine, namespace="app/desktop_user")
    assert client.namespace == "app/desktop_user"
