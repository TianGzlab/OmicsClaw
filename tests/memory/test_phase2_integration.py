"""Test Phase 2 session management integration."""

import os
import tempfile
import pytest
import pytest_asyncio
from bot.memory import SQLiteBackend, SecureFieldEncryptor
from bot.core import SessionManager


@pytest_asyncio.fixture
async def session_env():
    """Create temporary store + session manager."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    key = b"0" * 32
    encryptor = SecureFieldEncryptor(key)
    store = SQLiteBackend(db_path, encryptor)
    await store.initialize()
    manager = SessionManager(store)

    yield store, manager

    await store.close()
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_session_creation(session_env):
    """Test session creation via manager."""
    store, manager = session_env
    session = await manager.get_or_create("user123", "telegram", "chat456")
    assert session.session_id == "telegram:user123:chat456"
    assert session.user_id == "user123"
    assert session.platform == "telegram"


@pytest.mark.asyncio
async def test_session_retrieval(session_env):
    """Test existing session is retrieved, not duplicated."""
    store, manager = session_env
    session1 = await manager.get_or_create("user123", "telegram", "chat456")
    session2 = await manager.get_or_create("user123", "telegram", "chat456")
    assert session1.session_id == session2.session_id


@pytest.mark.asyncio
async def test_session_deletion(session_env):
    """Test session deletion."""
    store, manager = session_env
    session = await manager.get_or_create("user123", "telegram", "chat456")
    await store.delete_session(session.session_id)
    deleted = await store.get_session(session.session_id)
    assert deleted is None
