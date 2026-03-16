"""Test Phase 3 memory context injection."""

import os
import tempfile
import pytest
import pytest_asyncio
from bot.memory import SQLiteBackend, SecureFieldEncryptor
from bot.memory.models import DatasetMemory, AnalysisMemory, PreferenceMemory
from bot.core import SessionManager


@pytest_asyncio.fixture
async def context_env():
    """Create store + manager with pre-populated memories."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    key = b"0" * 32
    encryptor = SecureFieldEncryptor(key)
    store = SQLiteBackend(db_path, encryptor)
    await store.initialize()
    manager = SessionManager(store)

    session = await manager.get_or_create("user123", "telegram", "chat456")

    # Add memories
    dataset = DatasetMemory(
        file_path="data/brain_visium.h5ad",
        platform="Visium",
        n_obs=3000,
        n_vars=2000,
        preprocessing_state="clustered",
    )
    await store.save_memory(session.session_id, dataset)

    analysis = AnalysisMemory(
        source_dataset_id=dataset.memory_id,
        skill="spatial-preprocessing",
        method="leiden",
        parameters={"resolution": 0.8},
        status="completed",
    )
    await store.save_memory(session.session_id, analysis)

    pref = PreferenceMemory(
        domain="spatial-genes",
        key="svg_method",
        value="SPARK-X",
    )
    await store.save_memory(session.session_id, pref)

    yield store, manager, session

    await store.close()
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_memory_context_contains_dataset(context_env):
    """Context includes dataset info."""
    store, manager, session = context_env
    context = await manager.load_context(session.session_id)
    assert "brain_visium.h5ad" in context
    assert "Visium" in context


@pytest.mark.asyncio
async def test_memory_context_contains_analysis(context_env):
    """Context includes analysis info."""
    store, manager, session = context_env
    context = await manager.load_context(session.session_id)
    assert "spatial-preprocessing" in context


@pytest.mark.asyncio
async def test_memory_context_contains_preferences(context_env):
    """Context includes user preferences."""
    store, manager, session = context_env
    context = await manager.load_context(session.session_id)
    assert "SPARK-X" in context
