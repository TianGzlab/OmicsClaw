"""Test SQLite backend."""

import os
import tempfile
import pytest
import pytest_asyncio
from bot.memory.backends.sqlite import SQLiteBackend
from bot.memory.encryption import SecureFieldEncryptor
from bot.memory.models import DatasetMemory, AnalysisMemory, Session


@pytest_asyncio.fixture
async def memory_store():
    """Create temporary SQLite store."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    key = b"0" * 32
    encryptor = SecureFieldEncryptor(key)
    store = SQLiteBackend(db_path, encryptor)
    await store.initialize()

    yield store

    os.unlink(db_path)


@pytest.mark.asyncio
async def test_create_and_get_session(memory_store):
    """Test session creation and retrieval."""
    session = await memory_store.create_session("user123", "telegram", "chat456")

    assert session.session_id == "telegram:user123:chat456"
    assert session.user_id == "user123"
    assert session.platform == "telegram"

    retrieved = await memory_store.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id


@pytest.mark.asyncio
async def test_save_and_get_memory(memory_store):
    """Test memory save and retrieval."""
    session = await memory_store.create_session("user123", "telegram", "chat456")

    memory = DatasetMemory(
        file_path="data/test.h5ad",
        platform="Visium",
        n_obs=1000,
    )

    memory_id = await memory_store.save_memory(session.session_id, memory)
    assert memory_id == memory.memory_id

    memories = await memory_store.get_memories(session.session_id, "dataset")
    assert len(memories) == 1
    assert memories[0].file_path == "data/test.h5ad"
    assert memories[0].platform == "Visium"


@pytest.mark.asyncio
async def test_delete_session(memory_store):
    """Test session deletion cascades to memories."""
    session = await memory_store.create_session("user123", "telegram", "chat456")

    memory = DatasetMemory(file_path="data/test.h5ad")
    await memory_store.save_memory(session.session_id, memory)

    await memory_store.delete_session(session.session_id)

    retrieved = await memory_store.get_session(session.session_id)
    assert retrieved is None

    memories = await memory_store.get_memories(session.session_id)
    assert len(memories) == 0
