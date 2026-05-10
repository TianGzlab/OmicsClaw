"""Tests for migration 001_namespace — schema rebuild + disclosure backfill."""

import importlib

import pytest
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.models import Base


def _load_001():
    return importlib.import_module("omicsclaw.memory.migrations.001_namespace")


async def _build_legacy_schema(db: DatabaseManager) -> None:
    """Create the pre-001 schema (current ORM models — no namespace column)."""
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _pk_columns_in_order(s, table: str) -> list[str]:
    result = await s.execute(sa.text(f"PRAGMA table_info({table})"))
    rows = [(row[1], row[5]) for row in result.all() if row[5] > 0]
    rows.sort(key=lambda x: x[1])
    return [name for name, _ in rows]


@pytest.mark.asyncio
async def test_001_adds_namespace_column_to_paths(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema(db)

        mig = _load_001()
        await mig.apply(db)

        async with db.session() as s:
            result = await s.execute(sa.text("PRAGMA table_info(paths)"))
            cols = [row[1] for row in result.all()]
            assert "namespace" in cols
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_paths_pk_is_namespace_domain_path(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema(db)

        mig = _load_001()
        await mig.apply(db)

        async with db.session() as s:
            assert await _pk_columns_in_order(s, "paths") == ["namespace", "domain", "path"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_search_documents_pk_is_namespace_domain_path(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema(db)

        mig = _load_001()
        await mig.apply(db)

        async with db.session() as s:
            assert await _pk_columns_in_order(s, "search_documents") == [
                "namespace",
                "domain",
                "path",
            ]
            result = await s.execute(sa.text("PRAGMA table_info(search_documents)"))
            cols = [row[1] for row in result.all()]
            assert "namespace" in cols
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_is_idempotent(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema(db)

        mig = _load_001()
        await mig.apply(db)
        await mig.apply(db)  # second invocation must not raise or duplicate work

        async with db.session() as s:
            result = await s.execute(sa.text("PRAGMA table_info(paths)"))
            cols = [row[1] for row in result.all()]
            assert cols.count("namespace") == 1
            assert await _pk_columns_in_order(s, "paths") == [
                "namespace",
                "domain",
                "path",
            ]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_idempotent_does_not_reset_post_migration_namespaces(tmp_path):
    """Re-running 001 must preserve any namespace edits already applied."""
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema(db)

        # Seed a single legacy path
        async with db.session() as s:
            await s.execute(sa.text("INSERT INTO nodes (uuid) VALUES ('n1')"))
            await s.execute(
                sa.text(
                    "INSERT INTO edges (id, parent_uuid, child_uuid, name) "
                    "VALUES (1, 'n1', 'n1', 'test')"
                )
            )
            await s.execute(
                sa.text(
                    "INSERT INTO paths (domain, path, edge_id) "
                    "VALUES ('core', 'foo', 1)"
                )
            )

        mig = _load_001()
        await mig.apply(db)

        # Caller updates namespace after migration
        async with db.session() as s:
            await s.execute(
                sa.text(
                    "UPDATE paths SET namespace='tg/userA' "
                    "WHERE domain='core' AND path='foo'"
                )
            )

        # Re-running the migration must NOT reset that namespace
        await mig.apply(db)

        async with db.session() as s:
            result = await s.execute(
                sa.text(
                    "SELECT namespace FROM paths "
                    "WHERE domain='core' AND path='foo'"
                )
            )
            assert result.scalar_one() == "tg/userA"
    finally:
        await db.close()


async def _build_legacy_schema_with_fts(db: DatabaseManager) -> None:
    """Legacy schema + the legacy FTS5 virtual table (no namespace col)."""
    await _build_legacy_schema(db)
    async with db.session() as s:
        await s.execute(sa.text("""
            CREATE VIRTUAL TABLE search_documents_fts USING fts5(
                domain, path, node_uuid, uri, content, disclosure, search_terms,
                content=search_documents,
                content_rowid=rowid
            )
        """))


@pytest.mark.asyncio
async def test_001_rebuilds_fts5_with_namespace_column(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema_with_fts(db)

        mig = _load_001()
        await mig.apply(db)

        async with db.session() as s:
            # If namespace is a column on the FTS table, this query parses.
            await s.execute(sa.text("SELECT namespace FROM search_documents_fts LIMIT 0"))
    finally:
        await db.close()


async def _seed_path_with_disclosure(
    db: DatabaseManager,
    *,
    domain: str,
    path: str,
    disclosure: str,
) -> None:
    """Seed nodes/edges/paths/memories/search_documents for one path row."""
    async with db.session() as s:
        await s.execute(sa.text("INSERT OR IGNORE INTO nodes (uuid) VALUES ('n1')"))
        await s.execute(
            sa.text(
                "INSERT OR IGNORE INTO edges (id, parent_uuid, child_uuid, name) "
                "VALUES (1, 'n1', 'n1', 'seed')"
            )
        )
        await s.execute(
            sa.text(
                "INSERT INTO paths (domain, path, edge_id) "
                "VALUES (:d, :p, 1)"
            ),
            {"d": domain, "p": path},
        )
        await s.execute(
            sa.text(
                "INSERT INTO memories (node_uuid, content) "
                "VALUES ('n1', 'test-content')"
            )
        )
        result = await s.execute(sa.text("SELECT last_insert_rowid()"))
        memory_id = result.scalar_one()
        await s.execute(
            sa.text(
                "INSERT INTO search_documents "
                "(domain, path, node_uuid, memory_id, uri, content, "
                "disclosure, search_terms, priority) "
                "VALUES (:d, :p, 'n1', :mid, :uri, 'test-content', :disc, :st, 0)"
            ),
            {
                "d": domain,
                "p": path,
                "mid": memory_id,
                "uri": f"{domain}://{path}",
                "disc": disclosure,
                "st": path,
            },
        )


@pytest.mark.asyncio
async def test_001_backfills_namespace_from_memory_disclosure(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema_with_fts(db)
        await _seed_path_with_disclosure(
            db,
            domain="analysis",
            path="sc-de/run42",
            disclosure="Memory from session app:userA:abcdef",
        )

        mig = _load_001()
        await mig.apply(db)

        async with db.session() as s:
            result = await s.execute(
                sa.text(
                    "SELECT namespace FROM paths "
                    "WHERE domain='analysis' AND path='sc-de/run42'"
                )
            )
            assert result.scalar_one() == "app/userA"

            result = await s.execute(
                sa.text(
                    "SELECT namespace FROM search_documents "
                    "WHERE domain='analysis' AND path='sc-de/run42'"
                )
            )
            assert result.scalar_one() == "app/userA"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_backfills_namespace_from_session_disclosure(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema_with_fts(db)
        await _seed_path_with_disclosure(
            db,
            domain="session",
            path="abc123",
            disclosure="Session for user userA on tg",
        )

        mig = _load_001()
        await mig.apply(db)

        async with db.session() as s:
            result = await s.execute(
                sa.text(
                    "SELECT namespace FROM paths "
                    "WHERE domain='session' AND path='abc123'"
                )
            )
            assert result.scalar_one() == "tg/userA"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_falls_back_to_shared_when_disclosure_unparseable(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema_with_fts(db)
        await _seed_path_with_disclosure(
            db,
            domain="analysis",
            path="orphan",
            disclosure="some garbage that doesn't match",
        )

        mig = _load_001()
        await mig.apply(db)

        async with db.session() as s:
            result = await s.execute(
                sa.text(
                    "SELECT namespace FROM paths "
                    "WHERE domain='analysis' AND path='orphan'"
                )
            )
            assert result.scalar_one() == "__shared__"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_preserves_row_counts(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema_with_fts(db)

        for i in range(5):
            await _seed_path_with_disclosure(
                db,
                domain="analysis",
                path=f"run_{i}",
                disclosure=f"Memory from session app:user{i}:s{i}",
            )

        async def counts(s):
            return {
                tbl: (
                    await s.execute(sa.text(f"SELECT COUNT(*) FROM {tbl}"))
                ).scalar_one()
                for tbl in ("paths", "search_documents", "memories", "nodes", "edges")
            }

        async with db.session() as s:
            before = await counts(s)

        mig = _load_001()
        await mig.apply(db)

        async with db.session() as s:
            after = await counts(s)

        assert before == after
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_discovered_and_run_via_init_db(tmp_path):
    """End-to-end: init_db on a fresh DB applies 001 via discovery."""
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await db.init_db()

        async with db.session() as s:
            # paths has namespace column post-migration
            result = await s.execute(sa.text("PRAGMA table_info(paths)"))
            cols = [row[1] for row in result.all()]
            assert "namespace" in cols

            # 001 was recorded by the runner
            result = await s.execute(sa.text("SELECT version FROM _schema_version"))
            assert "001_namespace" in {row[0] for row in result.all()}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_001_glossary_keywords_has_namespace_in_unique_constraint(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await _build_legacy_schema(db)

        # Seed a node so glossary FK is valid
        async with db.session() as s:
            await s.execute(sa.text("INSERT INTO nodes (uuid) VALUES ('node-1')"))

        mig = _load_001()
        await mig.apply(db)

        # Same (keyword, node_uuid) but different namespace — both must succeed
        async with db.session() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO glossary_keywords (keyword, node_uuid, namespace) "
                    "VALUES ('foo', 'node-1', 'ns1')"
                )
            )
            await s.execute(
                sa.text(
                    "INSERT INTO glossary_keywords (keyword, node_uuid, namespace) "
                    "VALUES ('foo', 'node-1', 'ns2')"
                )
            )
            result = await s.execute(
                sa.text("SELECT COUNT(*) FROM glossary_keywords")
            )
            assert result.scalar_one() == 2

        # Duplicate (namespace, keyword, node_uuid) — must fail
        with pytest.raises(Exception):
            async with db.session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO glossary_keywords (keyword, node_uuid, namespace) "
                        "VALUES ('foo', 'node-1', 'ns1')"
                    )
                )
    finally:
        await db.close()
