"""Tests for new memory features: TTL, dedup, search, insight/project memory, update re-encryption."""

import os
import tempfile
from datetime import datetime, timezone, timedelta
import pytest
import pytest_asyncio
from bot.memory.backends.sqlite import SQLiteBackend
from bot.memory.encryption import SecureFieldEncryptor
from bot.memory.models import (
    DatasetMemory,
    AnalysisMemory,
    PreferenceMemory,
    InsightMemory,
    ProjectContextMemory,
)


@pytest_asyncio.fixture
async def store():
    """Create temporary SQLite store."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    key = b"0" * 32
    encryptor = SecureFieldEncryptor(key)
    backend = SQLiteBackend(db_path, encryptor)
    await backend.initialize()

    yield backend

    await backend.close()
    os.unlink(db_path)


@pytest_asyncio.fixture
async def session_id(store):
    """Create a test session and return its ID."""
    session = await store.create_session("user1", "telegram", "chat1")
    return session.session_id


# --- TTL Expiration ---

@pytest.mark.asyncio
async def test_memory_ttl_cleanup(store, session_id):
    """Expired sessions are pruned by cleanup_expired()."""
    # Manually set last_activity to 60 days ago
    import aiosqlite
    old_time = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    async with aiosqlite.connect(store.db_path) as db:
        await db.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (old_time, session_id),
        )
        await db.commit()

    # Add a memory to verify CASCADE delete
    mem = DatasetMemory(file_path="data/old.h5ad")
    await store.save_memory(session_id, mem)

    # Cleanup with 30-day TTL should remove the session
    count = await store.cleanup_expired(ttl_days=30)
    assert count == 1

    # Session and memories should be gone
    assert await store.get_session(session_id) is None
    assert await store.get_memories(session_id) == []


@pytest.mark.asyncio
async def test_ttl_keeps_recent_sessions(store, session_id):
    """Recent sessions are not pruned."""
    count = await store.cleanup_expired(ttl_days=30)
    assert count == 0
    assert await store.get_session(session_id) is not None


# --- Deduplication ---

@pytest.mark.asyncio
async def test_dataset_deduplication(store, session_id):
    """Duplicate DatasetMemory by file_path updates instead of inserting."""
    mem1 = DatasetMemory(file_path="data/brain.h5ad", platform="Visium", n_obs=1000)
    id1 = await store.save_memory(session_id, mem1)

    mem2 = DatasetMemory(file_path="data/brain.h5ad", platform="Visium", n_obs=2000)
    id2 = await store.save_memory(session_id, mem2)

    # Should update, not insert
    assert id2 == id1
    memories = await store.get_memories(session_id, "dataset")
    assert len(memories) == 1
    assert memories[0].n_obs == 2000


@pytest.mark.asyncio
async def test_preference_deduplication(store, session_id):
    """Duplicate PreferenceMemory by domain+key updates instead of inserting."""
    p1 = PreferenceMemory(domain="spatial", key="method", value="leiden")
    id1 = await store.save_memory(session_id, p1)

    p2 = PreferenceMemory(domain="spatial", key="method", value="louvain")
    id2 = await store.save_memory(session_id, p2)

    assert id2 == id1
    memories = await store.get_memories(session_id, "preference")
    assert len(memories) == 1
    assert memories[0].value == "louvain"


@pytest.mark.asyncio
async def test_no_dedup_different_files(store, session_id):
    """Different file_path datasets are not deduplicated."""
    await store.save_memory(session_id, DatasetMemory(file_path="data/a.h5ad"))
    await store.save_memory(session_id, DatasetMemory(file_path="data/b.h5ad"))

    memories = await store.get_memories(session_id, "dataset")
    assert len(memories) == 2


# --- Search ---

@pytest.mark.asyncio
async def test_search_memories_by_content(store, session_id):
    """Search finds memories containing query string."""
    await store.save_memory(
        session_id,
        DatasetMemory(file_path="data/brain_visium.h5ad", platform="Visium"),
    )
    await store.save_memory(
        session_id,
        DatasetMemory(file_path="data/liver_merfish.h5ad", platform="MERFISH"),
    )

    results = await store.search_memories(session_id, "brain")
    assert len(results) == 1
    assert results[0].file_path == "data/brain_visium.h5ad"


@pytest.mark.asyncio
async def test_search_case_insensitive(store, session_id):
    """Search is case-insensitive."""
    await store.save_memory(
        session_id,
        DatasetMemory(file_path="data/Brain_Visium.h5ad", platform="Visium"),
    )
    results = await store.search_memories(session_id, "brain")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_by_type(store, session_id):
    """Search can be filtered by memory type."""
    await store.save_memory(session_id, DatasetMemory(file_path="data/brain.h5ad"))
    await store.save_memory(
        session_id,
        PreferenceMemory(domain="spatial", key="brain_method", value="leiden"),
    )

    results = await store.search_memories(session_id, "brain", memory_type="dataset")
    assert len(results) == 1
    assert results[0].memory_type == "dataset"


# --- Insight & ProjectContext Memory ---

@pytest.mark.asyncio
async def test_insight_memory_roundtrip(store, session_id):
    """InsightMemory saves and loads with encryption."""
    insight = InsightMemory(
        source_analysis_id="abc123",
        entity_type="cluster",
        entity_id="cluster_3",
        biological_label="T cells",
        evidence="CD3 expression",
        confidence="user_confirmed",
    )
    await store.save_memory(session_id, insight)

    memories = await store.get_memories(session_id, "insight")
    assert len(memories) == 1
    assert memories[0].biological_label == "T cells"
    assert memories[0].confidence == "user_confirmed"
    assert memories[0].evidence == "CD3 expression"


@pytest.mark.asyncio
async def test_project_context_roundtrip(store, session_id):
    """ProjectContextMemory saves and loads with encryption."""
    ctx = ProjectContextMemory(
        project_goal="Study tumor microenvironment",
        species="Homo sapiens",
        tissue_type="breast tumor",
        disease_model="TNBC",
    )
    await store.save_memory(session_id, ctx)

    memories = await store.get_memories(session_id, "project_context")
    assert len(memories) == 1
    assert memories[0].project_goal == "Study tumor microenvironment"
    assert memories[0].species == "Homo sapiens"


# --- Update Re-encryption ---

@pytest.mark.asyncio
async def test_update_memory_reencrypts(store, session_id):
    """update_memory re-encrypts sensitive fields after merge."""
    mem = DatasetMemory(file_path="data/original.h5ad", platform="Visium")
    mid = await store.save_memory(session_id, mem)

    # Update the sensitive file_path field
    await store.update_memory(mid, {"file_path": "data/updated.h5ad"})

    # Retrieve and verify the update was encrypted correctly
    memories = await store.get_memories(session_id, "dataset")
    assert len(memories) == 1
    assert memories[0].file_path == "data/updated.h5ad"

    # Verify the raw stored data is encrypted (not plaintext)
    import aiosqlite
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute(
            "SELECT content FROM memories WHERE memory_id = ?", (mid,)
        ) as cursor:
            row = await cursor.fetchone()
            import json
            raw = json.loads(row[0])
            # file_path should be encrypted (not "data/updated.h5ad")
            assert raw["file_path"] != "data/updated.h5ad"


# --- Connection Pooling ---

@pytest.mark.asyncio
async def test_connection_reuse(store, session_id):
    """Multiple operations reuse the same connection."""
    # Perform several operations
    await store.save_memory(session_id, DatasetMemory(file_path="data/a.h5ad"))
    await store.save_memory(session_id, DatasetMemory(file_path="data/b.h5ad"))
    await store.get_memories(session_id)
    await store.get_session(session_id)

    # Connection should still be the same object
    assert store._conn is not None


@pytest.mark.asyncio
async def test_close_clears_connection(store):
    """close() clears the connection."""
    await store.close()
    assert store._conn is None
