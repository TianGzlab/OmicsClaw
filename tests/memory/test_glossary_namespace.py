"""Tests for namespace-aware GlossaryService (PR #3c Task 3c.1).

The existing public API stays backward-compatible: ``add_glossary_keyword``
without ``namespace`` still writes to ``__shared__`` so legacy callers
(server.py, api/browse.py) keep working unchanged. New callers can pass
an explicit namespace to scope a keyword to one user/surface, and use
``add_glossary_shared`` for the explicit shared variant.

``find_glossary_in_content`` gains an optional ``namespace`` filter so
the search reindexer can scope content scans to (current, ``__shared__``).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.glossary import GlossaryService
from omicsclaw.memory.search import SearchIndexer


@pytest_asyncio.fixture
async def env(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    eng = MemoryEngine(db, search)
    glossary = GlossaryService(db, search)
    yield eng, glossary, db
    await db.close()


# ----------------------------------------------------------------------
# add_glossary_keyword — namespace parameter
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_glossary_keyword_default_namespace_is_shared(env):
    eng, glossary, db = env
    ref = await eng.upsert("core://agent", "x", namespace="__shared__")

    await glossary.add_glossary_keyword("alpha", ref.node_uuid)

    keywords = await _all_keywords_with_namespace(db, ref.node_uuid)
    assert keywords == [("alpha", "__shared__")]


@pytest.mark.asyncio
async def test_add_glossary_keyword_with_explicit_namespace(env):
    eng, glossary, db = env
    ref = await eng.upsert("core://agent", "x", namespace="tg/userA")

    await glossary.add_glossary_keyword(
        "user-A-only", ref.node_uuid, namespace="tg/userA"
    )

    keywords = await _all_keywords_with_namespace(db, ref.node_uuid)
    assert keywords == [("user-A-only", "tg/userA")]


@pytest.mark.asyncio
async def test_add_glossary_shared_helper(env):
    eng, glossary, db = env
    ref = await eng.upsert("core://agent", "x", namespace="__shared__")

    await glossary.add_glossary_shared("globally-known", ref.node_uuid)

    keywords = await _all_keywords_with_namespace(db, ref.node_uuid)
    assert keywords == [("globally-known", "__shared__")]


@pytest.mark.asyncio
async def test_same_keyword_can_exist_in_multiple_namespaces(env):
    """Composite UNIQUE on (namespace, keyword, node_uuid) means the same
    (keyword, node_uuid) can co-exist across namespaces."""
    eng, glossary, db = env
    ref = await eng.upsert("core://agent", "x", namespace="__shared__")

    await glossary.add_glossary_keyword(
        "shared-token", ref.node_uuid, namespace="__shared__"
    )
    await glossary.add_glossary_keyword(
        "shared-token", ref.node_uuid, namespace="tg/userA"
    )

    keywords = sorted(
        await _all_keywords_with_namespace(db, ref.node_uuid)
    )
    assert keywords == [
        ("shared-token", "__shared__"),
        ("shared-token", "tg/userA"),
    ]


# ----------------------------------------------------------------------
# remove_glossary_keyword — namespace-scoped
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_glossary_keyword_namespace_scoped(env):
    """Removing in one namespace must not delete the same keyword in others."""
    eng, glossary, db = env
    ref = await eng.upsert("core://agent", "x", namespace="__shared__")

    await glossary.add_glossary_keyword(
        "ambiguous", ref.node_uuid, namespace="tg/userA"
    )
    await glossary.add_glossary_keyword(
        "ambiguous", ref.node_uuid, namespace="tg/userB"
    )

    await glossary.remove_glossary_keyword(
        "ambiguous", ref.node_uuid, namespace="tg/userA"
    )

    keywords = sorted(
        await _all_keywords_with_namespace(db, ref.node_uuid)
    )
    assert keywords == [("ambiguous", "tg/userB")]


# ----------------------------------------------------------------------
# find_glossary_in_content — namespace filter
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_glossary_in_content_filters_to_namespace_plus_shared(env):
    eng, glossary, db = env
    ref = await eng.upsert("core://agent", "x", namespace="__shared__")
    await glossary.add_glossary_keyword(
        "userA-tag", ref.node_uuid, namespace="tg/userA"
    )
    await glossary.add_glossary_keyword(
        "userB-tag", ref.node_uuid, namespace="tg/userB"
    )
    await glossary.add_glossary_keyword(
        "global-tag", ref.node_uuid, namespace="__shared__"
    )

    matches = await glossary.find_glossary_in_content(
        "userA-tag userB-tag global-tag",
        namespace="tg/userA",
    )

    assert "userA-tag" in matches
    assert "global-tag" in matches
    assert "userB-tag" not in matches


@pytest.mark.asyncio
async def test_find_glossary_in_content_no_namespace_returns_all(env):
    """Backward-compatible call (namespace=None) sees every keyword."""
    eng, glossary, db = env
    ref = await eng.upsert("core://agent", "x", namespace="__shared__")
    await glossary.add_glossary_keyword(
        "userA-tag", ref.node_uuid, namespace="tg/userA"
    )
    await glossary.add_glossary_keyword(
        "global-tag", ref.node_uuid, namespace="__shared__"
    )

    matches = await glossary.find_glossary_in_content(
        "userA-tag global-tag"
    )

    assert "userA-tag" in matches
    assert "global-tag" in matches


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


async def _all_keywords_with_namespace(db, node_uuid):
    import sqlalchemy as sa

    from omicsclaw.memory.models import GlossaryKeyword

    async with db.session() as s:
        result = await s.execute(
            sa.select(GlossaryKeyword.keyword, GlossaryKeyword.namespace).where(
                GlossaryKeyword.node_uuid == node_uuid
            )
        )
        return [(row[0], row[1]) for row in result.all()]
