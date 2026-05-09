"""Tests that DatabaseManager.init_db() invokes the migrations runner."""

import pytest
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager


@pytest.mark.asyncio
async def test_init_db_creates_schema_version_table(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await db.init_db()

        async with db.session() as s:
            result = await s.execute(
                sa.text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='_schema_version'"
                )
            )
            assert result.scalar_one_or_none() == "_schema_version"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_init_db_is_idempotent(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await db.init_db()

        # Capture version count after first init
        async with db.session() as s:
            result = await s.execute(sa.text("SELECT COUNT(*) FROM _schema_version"))
            count_after_first = result.scalar_one()

        # Second init must not raise and must not re-apply anything
        await db.init_db()

        async with db.session() as s:
            result = await s.execute(sa.text("SELECT COUNT(*) FROM _schema_version"))
            assert result.scalar_one() == count_after_first
    finally:
        await db.close()
