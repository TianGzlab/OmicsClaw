"""Tests for the MemoryClient high-level API (omicsclaw.memory.memory_client).

Validates remember/recall/forget/search/boot operations against the
current graph-based memory architecture.
"""

import os
import tempfile
import pytest
import pytest_asyncio

from omicsclaw.memory.memory_client import MemoryClient


@pytest_asyncio.fixture
async def client():
    """Create a MemoryClient backed by a temporary SQLite database."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    db_url = f"sqlite+aiosqlite:///{db_path}"
    mc = MemoryClient(db_url)
    await mc.initialize()

    yield mc

    await mc.close()
    os.unlink(db_path)


# ---------------------------------------------------------------------------
# remember / recall
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remember_and_recall(client):
    """Store a memory and retrieve it by URI."""
    await client.remember(
        uri="dataset://brain_visium",
        content='{"file_path": "data/brain.h5ad", "platform": "Visium"}',
    )

    mem = await client.recall("dataset://brain_visium")
    assert mem is not None
    assert "brain.h5ad" in mem["content"]


@pytest.mark.asyncio
async def test_remember_updates_existing(client):
    """Calling remember twice on the same URI updates the content."""
    await client.remember(uri="preference://method", content="leiden")
    await client.remember(uri="preference://method", content="louvain")

    mem = await client.recall("preference://method")
    assert mem is not None
    assert mem["content"] == "louvain"


# ---------------------------------------------------------------------------
# forget
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forget(client):
    """Forget a memory and verify it's no longer reachable."""
    await client.remember(uri="temp://deletable", content="temporary data")
    mem = await client.recall("temp://deletable")
    assert mem is not None

    await client.forget("temp://deletable")
    mem_after = await client.recall("temp://deletable")
    assert mem_after is None


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search(client):
    """Search memories by content keyword."""
    await client.remember(uri="dataset://liver_merfish", content="liver MERFISH data")
    await client.remember(uri="dataset://brain_visium", content="brain Visium data")

    results = await client.search("brain")
    assert len(results) >= 1
    uris = [r.get("uri", "") for r in results]
    assert any("brain" in u for u in uris)


# ---------------------------------------------------------------------------
# list_children
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_children(client):
    """List children under a URI."""
    await client.remember(uri="project://analysis/step1", content="Preprocessing done")
    await client.remember(uri="project://analysis/step2", content="Clustering done")

    children = await client.list_children("project://analysis")
    names = [c.get("name", "") for c in children]
    assert "step1" in names
    assert "step2" in names


# ---------------------------------------------------------------------------
# boot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_boot_empty(client):
    """Boot returns empty string when no core memories exist."""
    result = await client.boot()
    assert result == ""


@pytest.mark.asyncio
async def test_boot_with_data(client, monkeypatch):
    """Boot loads core URIs into a context string."""
    monkeypatch.setenv("OMICSCLAW_MEMORY_CORE_URIS", "project://identity")

    await client.remember(uri="project://identity", content="I am OmicsBot.")

    result = await client.boot()
    assert "OmicsBot" in result
