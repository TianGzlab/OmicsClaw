"""Tests for CompatMemoryStore namespace injection (PR #4a Task 4a.2).

The plan §4a.2 contract:
  - save_memory(session_id, mem) extracts (platform, user_id) from the
    session and writes to namespace = f"{platform}/{user_id}".
  - Sessions themselves stay in __shared__ so a session_id can be
    resolved to its user/platform globally.
  - All existing CompatMemoryStore tests continue to pass.

This is the production data path for Telegram/Feishu bots — a leak here
would mean user A could see user B's memories. Tests below explicitly
prove that isolation.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.compat import (
    CompatMemoryStore,
    DatasetMemory,
    PreferenceMemory,
)
from omicsclaw.memory.models import Path


@pytest_asyncio.fixture
async def store(tmp_path):
    store = CompatMemoryStore(database_url=f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await store.initialize()
    yield store
    await store.close()


# ----------------------------------------------------------------------
# Session storage stays shared
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_is_stored_in_shared_namespace(store):
    """Session storage stays globally addressable so any worker can
    resolve a session_id to its (user, platform) without knowing where
    to look."""
    session = await store.create_session("user42", "telegram")

    async with store._db.session() as s:
        rows = (
            await s.execute(
                sa.select(Path).where(
                    Path.domain == "session",
                    Path.path == session.session_id,
                )
            )
        ).scalars().all()

    assert len(rows) == 1
    assert rows[0].namespace == "__shared__"


@pytest.mark.asyncio
async def test_get_session_round_trips(store):
    session = await store.create_session("user42", "telegram")
    fetched = await store.get_session(session.session_id)
    assert fetched is not None
    assert fetched.user_id == "user42"
    assert fetched.platform == "telegram"


# ----------------------------------------------------------------------
# Memory storage uses session-derived namespace
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_memory_uses_session_derived_namespace(store):
    """A DatasetMemory saved under a tg session lands in tg/<user_id>."""
    session = await store.create_session("user42", "telegram")
    await store.save_memory(
        session.session_id, DatasetMemory(file_path="pbmc.h5ad")
    )

    async with store._db.session() as s:
        rows = (
            await s.execute(
                sa.select(Path).where(Path.domain == "dataset")
            )
        ).scalars().all()
        namespaces = [r.namespace for r in rows]

    assert "telegram/user42" in namespaces


@pytest.mark.asyncio
async def test_save_memory_isolates_users_on_same_platform(store):
    """The leak-prevention test: two telegram users save the same
    dataset URI; each only sees their own row."""
    sa_session = await store.create_session("alice", "telegram")
    sb_session = await store.create_session("bob", "telegram")

    await store.save_memory(
        sa_session.session_id, DatasetMemory(file_path="alpha.h5ad")
    )
    await store.save_memory(
        sb_session.session_id, DatasetMemory(file_path="beta.h5ad")
    )

    a_memories = await store.get_memories(sa_session.session_id, "dataset")
    b_memories = await store.get_memories(sb_session.session_id, "dataset")

    a_files = {m.file_path for m in a_memories}
    b_files = {m.file_path for m in b_memories}

    assert a_files == {"alpha.h5ad"}
    assert b_files == {"beta.h5ad"}


@pytest.mark.asyncio
async def test_save_memory_isolates_users_across_platforms(store):
    """A telegram user and a feishu user should not see each other's data."""
    tg = await store.create_session("user1", "telegram")
    fs = await store.create_session("user1", "feishu")

    await store.save_memory(
        tg.session_id, DatasetMemory(file_path="tg_only.h5ad")
    )
    await store.save_memory(
        fs.session_id, DatasetMemory(file_path="fs_only.h5ad")
    )

    tg_mem = await store.get_memories(tg.session_id, "dataset")
    fs_mem = await store.get_memories(fs.session_id, "dataset")

    assert {m.file_path for m in tg_mem} == {"tg_only.h5ad"}
    assert {m.file_path for m in fs_mem} == {"fs_only.h5ad"}


@pytest.mark.asyncio
async def test_save_preference_lands_in_user_namespace_versioned(store):
    """preference://* should be versioned in the user's namespace."""
    session = await store.create_session("user42", "telegram")
    await store.save_memory(
        session.session_id,
        PreferenceMemory(domain="qc", key="cutoff", value=0.5),
    )

    async with store._db.session() as s:
        rows = (
            await s.execute(
                sa.select(Path).where(
                    Path.domain == "preference",
                    Path.path == "qc/cutoff",
                )
            )
        ).scalars().all()

    # Exactly one Path at qc/cutoff (composite PK guarantees this) and
    # it lives in the user's namespace.
    assert len(rows) == 1
    assert rows[0].namespace == "telegram/user42"


@pytest.mark.asyncio
async def test_search_memories_filters_by_session_namespace(store):
    """search_memories(session_id, query) only finds the session's own
    memories — never another user's."""
    sa_session = await store.create_session("alice", "telegram")
    sb_session = await store.create_session("bob", "telegram")

    await store.save_memory(
        sa_session.session_id,
        DatasetMemory(file_path="alpha-secret.h5ad"),
    )
    await store.save_memory(
        sb_session.session_id,
        DatasetMemory(file_path="beta-secret.h5ad"),
    )

    a_hits = await store.search_memories(sa_session.session_id, "secret")
    a_files = {m.file_path for m in a_hits}

    assert "alpha-secret.h5ad" in a_files
    assert "beta-secret.h5ad" not in a_files


@pytest.mark.asyncio
async def test_save_memory_with_unknown_session_raises(store):
    """If the session can't be resolved, the write must NOT fall back to
    ``__shared__`` (every other user could read it). Instead
    ``_client_for_session`` raises ``LookupError`` and ``save_memory``
    propagates — the caller decides whether to log-and-skip
    (``_auto_capture_dataset``) or surface the error.

    This pins the privacy fix: the prior behavior was a silent
    fall-back to the shared partition, which leaked auto-captured
    datasets across users when a session was missing or evicted."""
    with pytest.raises(LookupError):
        await store.save_memory(
            "nonexistent-session-id", DatasetMemory(file_path="orphan.h5ad")
        )

    # Nothing landed anywhere — particularly not in __shared__.
    async with store._db.session() as s:
        rows = (
            await s.execute(
                sa.select(Path).where(
                    Path.domain == "dataset", Path.path == "orphan.h5ad"
                )
            )
        ).scalars().all()
    assert rows == []
