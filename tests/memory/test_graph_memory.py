"""Tests for the Graph Memory Engine (omicsclaw.memory).

Validates core CRUD operations, graph traversal, search, and
the MemoryClient high-level API against the current architecture.
"""

import os
import tempfile
import pytest
import pytest_asyncio

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.search import SearchIndexer
from omicsclaw.memory.glossary import GlossaryService
from omicsclaw.memory.graph import GraphService
from omicsclaw.memory.models import ROOT_NODE_UUID


@pytest_asyncio.fixture
async def graph_env():
    """Create an in-memory SQLite graph engine for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    db_url = f"sqlite+aiosqlite:///{db_path}"
    db = DatabaseManager(db_url)
    await db.init_db()

    search = SearchIndexer(db)
    glossary = GlossaryService(db, search)
    graph = GraphService(db, search)

    yield graph, search, db

    await db.close()
    os.unlink(db_path)


# ---------------------------------------------------------------------------
# Create & Read
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_and_read_memory(graph_env):
    """Create a memory at root and read it back by path."""
    graph, search, db = graph_env

    result = await graph.create_memory(
        parent_path="",
        content="Test dataset: brain_visium.h5ad",
        priority=0,
        title="brain_visium",
        domain="dataset",
    )

    assert result is not None
    assert "node_uuid" in result

    # Read back by path
    mem = await graph.get_memory_by_path("brain_visium", "dataset")
    assert mem is not None
    assert "brain_visium.h5ad" in mem["content"]
    assert mem["domain"] == "dataset"
    assert mem["path"] == "brain_visium"


@pytest.mark.asyncio
async def test_create_nested_memory(graph_env):
    """Create nested memories (parent/child) and traverse."""
    graph, search, db = graph_env

    # Create parent
    await graph.create_memory(
        parent_path="",
        content="Spatial analyses container",
        priority=0,
        title="spatial",
        domain="analysis",
    )

    # Create child under parent
    await graph.create_memory(
        parent_path="spatial",
        content="Ran leiden clustering, resolution=0.8",
        priority=0,
        title="clustering_run1",
        domain="analysis",
    )

    # Read child
    child = await graph.get_memory_by_path("spatial/clustering_run1", "analysis")
    assert child is not None
    assert "leiden" in child["content"]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_memory(graph_env):
    """Update an existing memory and verify new content."""
    graph, search, db = graph_env

    await graph.create_memory(
        parent_path="",
        content="Original content",
        priority=0,
        title="updatable",
        domain="core",
    )

    await graph.update_memory(
        path="updatable",
        content="Updated content",
        domain="core",
    )

    mem = await graph.get_memory_by_path("updatable", "core")
    assert mem is not None
    assert mem["content"] == "Updated content"


# ---------------------------------------------------------------------------
# Children & Traversal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_children(graph_env):
    """List direct children of the root node."""
    graph, search, db = graph_env

    await graph.create_memory("", "Child A", 0, title="child_a", domain="core")
    await graph.create_memory("", "Child B", 0, title="child_b", domain="core")

    children = await graph.get_children(ROOT_NODE_UUID, context_domain="core")
    names = [c["name"] for c in children]

    assert "child_a" in names
    assert "child_b" in names


# ---------------------------------------------------------------------------
# Remove Path (Soft Delete)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_path(graph_env):
    """Remove a path and verify memory is no longer reachable."""
    graph, search, db = graph_env

    await graph.create_memory("", "Ephemeral", 0, title="temp_node", domain="core")
    mem = await graph.get_memory_by_path("temp_node", "core")
    assert mem is not None

    await graph.remove_path(path="temp_node", domain="core")

    mem_after = await graph.get_memory_by_path("temp_node", "core")
    assert mem_after is None


# ---------------------------------------------------------------------------
# Root Node
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_root_node_returns_virtual(graph_env):
    """Accessing the empty path returns the virtual root node."""
    graph, search, db = graph_env

    root = await graph.get_memory_by_path("", "core")
    assert root is not None
    assert root["node_uuid"] == ROOT_NODE_UUID
    assert root["id"] == 0
