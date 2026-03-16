"""Test Phase 4 automatic memory capture."""

import os
import tempfile
import pytest
import pytest_asyncio
from pathlib import Path
from bot.memory import SQLiteBackend, SecureFieldEncryptor
from bot.core import SessionManager, _auto_capture_analysis


@pytest_asyncio.fixture
async def capture_env():
    """Create store + manager with global state set."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    key = b"0" * 32
    encryptor = SecureFieldEncryptor(key)
    store = SQLiteBackend(db_path, encryptor)
    await store.initialize()

    import bot.core as core
    core.memory_store = store
    core.session_manager = SessionManager(store)

    session = await core.session_manager.get_or_create("user123", "telegram", "chat456")

    yield store, core.session_manager, session

    core.memory_store = None
    core.session_manager = None
    await store.close()
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_auto_capture_saves_analysis(capture_env):
    """Auto-capture creates an AnalysisMemory."""
    store, manager, session = capture_env
    args = {
        "skill": "spatial-preprocessing",
        "method": "leiden",
        "file_path": "data/test.h5ad",
    }
    await _auto_capture_analysis(
        session.session_id, "spatial-preprocessing", args, Path("/tmp/test_output"), True
    )

    memories = await store.get_memories(session.session_id, "analysis")
    assert len(memories) == 1
    assert memories[0].skill == "spatial-preprocessing"
    assert memories[0].method == "leiden"
    assert memories[0].status == "completed"


@pytest.mark.asyncio
async def test_auto_capture_failed_status(capture_env):
    """Auto-capture records failed status."""
    store, manager, session = capture_env
    await _auto_capture_analysis(
        session.session_id, "spatial-de", {}, Path("/tmp/test"), False
    )

    memories = await store.get_memories(session.session_id, "analysis")
    assert len(memories) == 1
    assert memories[0].status == "failed"
