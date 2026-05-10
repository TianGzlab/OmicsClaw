"""Tests for SearchIndexer namespace-aware behavior (PR #3a Task 3a.5).

Covers:
  - SearchIndexer.refresh_search_documents_for(namespace, uri): surgical
    single-row rebuild without touching other namespaces' rows.
  - Glossary keyword join filter: only keywords in the current namespace
    or ``__shared__`` should feed into search_terms for that namespace's
    search rows.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.models import GlossaryKeyword, SearchDocument
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def env(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    yield MemoryEngine(db, search), search, db
    await db.close()


# ----------------------------------------------------------------------
# Surgical refresh
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_for_uri_creates_single_row(env):
    eng, search, db = env
    await eng.upsert("core://agent", "v1", namespace="tg/userA")

    # Wipe the search row, then surgically refresh just this (namespace, uri).
    async with db.session() as s:
        await s.execute(sa.delete(SearchDocument))

    await search.refresh_search_documents_for(
        namespace="tg/userA", uri="core://agent"
    )

    async with db.session() as s:
        rows = (
            await s.execute(sa.select(SearchDocument))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].namespace == "tg/userA"
        assert rows[0].path == "agent"
        assert rows[0].content == "v1"


@pytest.mark.asyncio
async def test_refresh_for_uri_is_noop_when_path_missing(env):
    _, search, db = env
    # Should not raise, just silently skip — the surgical refresh has nothing
    # to rebuild if the (namespace, uri) doesn't exist.
    await search.refresh_search_documents_for(
        namespace="tg/userA", uri="core://nope"
    )

    async with db.session() as s:
        rows = (
            await s.execute(sa.select(SearchDocument))
        ).scalars().all()
        assert rows == []


# ----------------------------------------------------------------------
# Glossary namespace filter
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_glossary_keyword_filtered_by_namespace(env):
    """A keyword bound to a node but in a foreign namespace must NOT appear
    in that node's search row.

    To exercise the filter we bind three keywords to the SAME node:
      - one with namespace='tg/userA' (current)
      - one with namespace='tg/userZ' (foreign — must be excluded)
      - one with namespace='__shared__' (must be included)

    Without the per-namespace glossary filter all three would appear in
    ``search_terms``.
    """
    eng, search, db = env
    ref = await eng.upsert("core://agent", "content", namespace="tg/userA")

    async with db.session() as s:
        s.add_all([
            GlossaryKeyword(
                keyword="alpha-current",
                node_uuid=ref.node_uuid,
                namespace="tg/userA",
            ),
            GlossaryKeyword(
                keyword="zeta-foreign",
                node_uuid=ref.node_uuid,
                namespace="tg/userZ",
            ),
            GlossaryKeyword(
                keyword="shared-keyword",
                node_uuid=ref.node_uuid,
                namespace="__shared__",
            ),
        ])

    await search.refresh_search_documents_for_node(ref.node_uuid)

    async with db.session() as s:
        sd = (
            await s.execute(
                sa.select(SearchDocument).where(
                    SearchDocument.namespace == "tg/userA"
                )
            )
        ).scalar_one()

    assert "alpha-current" in sd.search_terms
    assert "shared-keyword" in sd.search_terms
    assert "zeta-foreign" not in sd.search_terms


@pytest.mark.asyncio
async def test_glossary_shared_keyword_appears_in_all_namespaces(env):
    """A keyword with namespace='__shared__' should bleed into any per-user row."""
    eng, search, db = env
    ref_a = await eng.upsert("core://agent", "A", namespace="tg/userA")

    # Bind a shared-namespace keyword to A's node — semantically odd in
    # production, but it's what we'd see for core:// agents whose keywords
    # are seeded globally.
    async with db.session() as s:
        s.add(
            GlossaryKeyword(
                keyword="shared-token",
                node_uuid=ref_a.node_uuid,
                namespace="__shared__",
            )
        )

    await search.refresh_search_documents_for_node(ref_a.node_uuid)

    async with db.session() as s:
        sd = (
            await s.execute(
                sa.select(SearchDocument).where(
                    SearchDocument.namespace == "tg/userA"
                )
            )
        ).scalar_one()
        assert "shared-token" in sd.search_terms
