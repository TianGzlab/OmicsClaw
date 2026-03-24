"""Tests for the CompatMemoryStore (omicsclaw.memory.compat).

Validates that the backward-compatible interface correctly maps
old-style Pydantic memory objects to the new graph memory system.
"""

import os
import tempfile
import pytest
import pytest_asyncio

from omicsclaw.memory.compat import (
    CompatMemoryStore,
    DatasetMemory,
    AnalysisMemory,
    PreferenceMemory,
    InsightMemory,
    ProjectContextMemory,
    Session,
)


@pytest_asyncio.fixture
async def store():
    """Create a CompatMemoryStore backed by a temporary SQLite database."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    db_url = f"sqlite+aiosqlite:///{db_path}"
    s = CompatMemoryStore(db_url)
    await s.initialize()

    yield s

    await s.close()
    os.unlink(db_path)


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_and_get_session(store):
    """Create a session and retrieve it."""
    session = await store.create_session("user123", "telegram", "chat456")
    assert isinstance(session, Session)
    assert session.user_id == "user123"
    assert session.platform == "telegram"

    retrieved = await store.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.user_id == "user123"


@pytest.mark.asyncio
async def test_delete_session(store):
    """Delete a session and verify it's gone."""
    session = await store.create_session("user123", "telegram", "chat456")
    await store.delete_session(session.session_id)

    retrieved = await store.get_session(session.session_id)
    assert retrieved is None


# ---------------------------------------------------------------------------
# Dataset Memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_and_get_dataset_memory(store):
    """Save a DatasetMemory and retrieve it."""
    session = await store.create_session("user1", "cli")

    mem = DatasetMemory(
        file_path="data/brain.h5ad",
        platform="Visium",
        n_obs=3000,
    )
    mid = await store.save_memory(session.session_id, mem)
    assert mid == mem.memory_id

    memories = await store.get_memories(session.session_id, "dataset")
    assert len(memories) >= 1
    assert any(m.file_path == "data/brain.h5ad" for m in memories)


# ---------------------------------------------------------------------------
# Preference Memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preference_memory(store):
    """Save and retrieve a PreferenceMemory."""
    session = await store.create_session("user1", "cli")

    pref = PreferenceMemory(domain="spatial", key="method", value="leiden")
    await store.save_memory(session.session_id, pref)

    memories = await store.get_memories(session.session_id, "preference")
    assert len(memories) >= 1
    assert any(m.key == "method" and m.value == "leiden" for m in memories)


# ---------------------------------------------------------------------------
# Security: Reject Absolute Paths
# ---------------------------------------------------------------------------

def test_reject_absolute_paths():
    """DatasetMemory rejects absolute file paths."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="Absolute paths not allowed"):
        DatasetMemory(file_path="/absolute/path/data.h5ad")


def test_relative_paths_allowed():
    """DatasetMemory accepts relative file paths."""
    mem = DatasetMemory(file_path="data/brain.h5ad")
    assert mem.file_path == "data/brain.h5ad"


# ---------------------------------------------------------------------------
# Context Loading
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_context(store):
    """Load context contains saved memories formatted for LLM."""
    session = await store.create_session("user1", "cli")

    await store.save_memory(
        session.session_id,
        DatasetMemory(file_path="data/visium.h5ad", platform="Visium", n_obs=5000),
    )
    await store.save_memory(
        session.session_id,
        PreferenceMemory(domain="spatial", key="cluster_method", value="leiden"),
    )

    context = await store.load_context(session.session_id)
    # Context should contain serialized memory data
    assert isinstance(context, str)
