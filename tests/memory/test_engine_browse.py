"""Tests for ``MemoryEngine.list_children_rich`` and
``MemoryEngine.list_paths`` — the engine-level browse verbs that
replace ``GraphService.get_children`` / ``GraphService.get_all_paths``
inside the desktop ``/memory/{children,domains}`` endpoints.

Both verbs return the rich UI dict shape that the desktop tree view
expects (``content_snippet``, ``approx_children_count``, ``name``,
``priority``, ``disclosure``, ``node_uuid`` …). The wire shape is
preserved so the server endpoint swap is shape-stable for the React
front-end.

Slice 3 of §6.2 GraphService retirement.
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


# ----------------------------------------------------------------------
# list_children_rich — rich children listing for /memory/children
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_children_rich_returns_rich_dicts(env):
    """Each child carries the wire-shape keys the desktop UI parses."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("analysis://run", "parent")
    await a.remember(
        "analysis://run/step1", "result " + "x" * 300, priority=5
    )

    children = await engine.list_children_rich(
        "analysis://run", namespace="tg/A"
    )
    assert len(children) == 1
    c = children[0]
    for key in (
        "node_uuid",
        "edge_id",
        "name",
        "domain",
        "path",
        "content_snippet",
        "priority",
        "disclosure",
        "approx_children_count",
    ):
        assert key in c, f"missing key {key} in {c}"
    assert c["domain"] == "analysis"
    assert c["path"] == "run/step1"
    assert c["priority"] == 5
    assert c["content_snippet"].startswith("result xxx")
    # snippet is 100 chars + "..."
    assert len(c["content_snippet"]) <= 103


@pytest.mark.asyncio
async def test_list_children_rich_strict_namespace(env):
    """A child whose only Path is in another namespace must not appear."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    b = MemoryClient(engine=engine, namespace="tg/B")
    await a.remember("analysis://onlyA", "A's analysis")
    await b.remember("analysis://onlyB", "B's analysis")

    children = await engine.list_children_rich("analysis://", namespace="tg/A")
    paths = {c["path"] for c in children}
    assert "onlyA" in paths
    assert "onlyB" not in paths, "leaked B's child into A's listing"


@pytest.mark.asyncio
async def test_list_children_rich_include_shared(env):
    """include_shared=True surfaces both namespace and __shared__ children."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("core://my_user/note", "personal")  # tg/A
    await a.remember("core://agent/style", "concise")  # __shared__

    # Browse from core:// root with include_shared=True; both children
    # of core should be listed.
    children = await engine.list_children_rich(
        "core://", namespace="tg/A", include_shared=True
    )
    paths = {c["path"] for c in children}
    # both my_user (personal) and agent (shared) live under core://
    assert "my_user" in paths or "agent" in paths
    # at least one of these must be the shared child
    has_shared = any(c["path"] == "agent" for c in children)
    has_user = any(c["path"] == "my_user" for c in children)
    assert has_shared, f"shared core://agent did not surface: {children}"
    assert has_user, f"per-user core://my_user did not surface: {children}"


@pytest.mark.asyncio
async def test_list_children_rich_approx_children_count(env):
    """approx_children_count reflects the number of grandchildren."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("analysis://run", "parent")
    await a.remember("analysis://run/step1", "child")
    await a.remember("analysis://run/step1/sub1", "grandchild 1")
    await a.remember("analysis://run/step1/sub2", "grandchild 2")

    children = await engine.list_children_rich(
        "analysis://run", namespace="tg/A"
    )
    step1 = next(c for c in children if c["path"] == "run/step1")
    assert step1["approx_children_count"] == 2


# ----------------------------------------------------------------------
# list_paths — flat path listing for /memory/domains
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_paths_returns_flat_list(env):
    """Returns dicts with the wire-shape keys the desktop UI parses."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("dataset://x.h5ad", "data x", priority=3)

    paths = await engine.list_paths(namespace="tg/A")
    matching = [p for p in paths if p["uri"] == "dataset://x.h5ad"]
    assert len(matching) == 1
    p = matching[0]
    for key in (
        "domain",
        "path",
        "namespace",
        "uri",
        "name",
        "priority",
        "memory_id",
        "node_uuid",
    ):
        assert key in p, f"missing key {key} in {p}"
    assert p["domain"] == "dataset"
    assert p["path"] == "x.h5ad"
    assert p["priority"] == 3
    assert p["name"] == "x.h5ad"


@pytest.mark.asyncio
async def test_list_paths_strict_namespace(env):
    """Strict mode: no rows from other namespaces."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    b = MemoryClient(engine=engine, namespace="tg/B")
    await a.remember("dataset://onlyA.h5ad", "A")
    await b.remember("dataset://onlyB.h5ad", "B")

    paths = await engine.list_paths(namespace="tg/A")
    uris = {p["uri"] for p in paths}
    assert "dataset://onlyA.h5ad" in uris
    assert "dataset://onlyB.h5ad" not in uris, "leaked B's path into A"


@pytest.mark.asyncio
async def test_list_paths_include_shared_dedupes(env):
    """When the same URI exists in both namespace and __shared__,
    include_shared=True returns one row — namespace-matched wins.
    """
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    # remember_shared lets us write to __shared__ regardless of URI prefix.
    await a.remember_shared("dataset://shared.h5ad", "shared copy")
    await a.remember("dataset://shared.h5ad", "user copy")  # tg/A

    paths = await engine.list_paths(namespace="tg/A", include_shared=True)
    matching = [p for p in paths if p["uri"] == "dataset://shared.h5ad"]
    assert len(matching) == 1, (
        f"expected one row after dedupe, got {len(matching)}: {matching}"
    )
    # namespace-matched copy wins
    assert matching[0]["namespace"] == "tg/A"


@pytest.mark.asyncio
async def test_list_paths_filter_by_domain(env):
    """domain= filters to a single domain only."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember("dataset://x.h5ad", "x")
    await a.remember("analysis://run", "y")

    paths = await engine.list_paths(namespace="tg/A", domain="dataset")
    assert all(p["domain"] == "dataset" for p in paths)
    assert any(p["uri"] == "dataset://x.h5ad" for p in paths)
    assert not any(p["domain"] == "analysis" for p in paths)


@pytest.mark.asyncio
async def test_list_paths_admin_view_returns_all_namespaces(env):
    """``namespace=None`` is the admin view: every namespace's paths show
    up, deduped by (namespace, domain, path) so each row appears once.

    Used by ``/memory/domains?namespace=`` so an operator can find data
    written under another desktop user-id or a legacy launch-id partition
    without spinning up that client.
    """
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    b = MemoryClient(engine=engine, namespace="tg/B")
    await a.remember("dataset://onlyA.h5ad", "A")
    await b.remember("dataset://onlyB.h5ad", "B")

    paths = await engine.list_paths(namespace=None)
    uris = {p["uri"] for p in paths}
    assert "dataset://onlyA.h5ad" in uris
    assert "dataset://onlyB.h5ad" in uris
    # Namespaces preserved on each row so the caller can group/filter.
    by_uri = {p["uri"]: p["namespace"] for p in paths}
    assert by_uri["dataset://onlyA.h5ad"] == "tg/A"
    assert by_uri["dataset://onlyB.h5ad"] == "tg/B"


@pytest.mark.asyncio
async def test_list_namespaces_returns_distinct_used_namespaces(env):
    """``list_namespaces()`` powers the admin UI's namespace dropdown:
    every partition that currently holds at least one path is returned,
    deduped, sorted for a stable display order. Empty namespaces are
    omitted — there's nothing to inspect there."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    b = MemoryClient(engine=engine, namespace="tg/B")
    await a.remember("dataset://x.h5ad", "x")
    await b.remember("dataset://y.h5ad", "y")
    await a.remember_shared("core://agent/style", "shared")

    namespaces = await engine.list_namespaces()
    assert namespaces == sorted(set(namespaces)), "should be deduped + sorted"
    assert "tg/A" in namespaces
    assert "tg/B" in namespaces
    assert "__shared__" in namespaces


@pytest.mark.asyncio
async def test_list_paths_admin_view_ignores_include_shared(env):
    """``namespace=None`` already covers every partition, including
    ``__shared__``; ``include_shared`` becomes a no-op rather than a
    contradiction. Pin the behavior so the endpoint can accept any
    combination without surprising the caller."""
    engine, _ = env
    a = MemoryClient(engine=engine, namespace="tg/A")
    await a.remember_shared("core://agent/style", "shared")
    await a.remember("dataset://x.h5ad", "user")

    with_shared = await engine.list_paths(namespace=None, include_shared=True)
    without_shared = await engine.list_paths(namespace=None, include_shared=False)
    assert {p["uri"] for p in with_shared} == {p["uri"] for p in without_shared}
