"""Tests for the lightweight migrations framework runner."""

import pytest
import sqlalchemy as sa

from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.migrations.runner import run_pending


@pytest.mark.asyncio
async def test_run_pending_creates_schema_version_table(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await run_pending(db, migrations=[])

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
async def test_run_pending_applies_migration_and_records_version(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    apply_calls: list[DatabaseManager] = []

    class Mig:
        VERSION = "001_test"
        DESCRIPTION = "first"

        async def apply(self, d: DatabaseManager) -> None:
            apply_calls.append(d)

    try:
        versions = await run_pending(db, migrations=[Mig()])
        assert versions == ["001_test"]
        assert apply_calls == [db]

        async with db.session() as s:
            result = await s.execute(sa.text("SELECT version FROM _schema_version"))
            assert {row[0] for row in result.all()} == {"001_test"}
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_run_pending_skips_already_applied(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    apply_count = 0

    class Mig:
        VERSION = "001_test"
        DESCRIPTION = "first"

        async def apply(self, d: DatabaseManager) -> None:
            nonlocal apply_count
            apply_count += 1

    try:
        v1 = await run_pending(db, migrations=[Mig()])
        v2 = await run_pending(db, migrations=[Mig()])
        assert v1 == ["001_test"]
        assert v2 == []
        assert apply_count == 1  # idempotent
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_run_pending_applies_in_version_sorted_order(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    order_seen: list[str] = []

    def make_mig(v: str):
        class M:
            VERSION = v
            DESCRIPTION = f"m{v}"

            async def apply(self, d: DatabaseManager) -> None:
                order_seen.append(v)
        return M()

    try:
        # Caller passes in reversed order — runner must sort
        versions = await run_pending(
            db, migrations=[make_mig("003"), make_mig("001"), make_mig("002")]
        )
        assert versions == ["001", "002", "003"]
        assert order_seen == ["001", "002", "003"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_failed_migration_is_not_recorded(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")

    class GoodMig:
        VERSION = "001"
        DESCRIPTION = "good"

        async def apply(self, d: DatabaseManager) -> None:
            pass

    class BadMig:
        VERSION = "002"
        DESCRIPTION = "bad"

        async def apply(self, d: DatabaseManager) -> None:
            raise RuntimeError("boom")

    try:
        with pytest.raises(RuntimeError, match="boom"):
            await run_pending(db, migrations=[GoodMig(), BadMig()])

        # 001 succeeded → recorded; 002 raised → NOT recorded
        async with db.session() as s:
            result = await s.execute(sa.text("SELECT version FROM _schema_version"))
            assert {row[0] for row in result.all()} == {"001"}
    finally:
        await db.close()


def test_discover_migrations_imports_numbered_modules(tmp_path, monkeypatch):
    pkg_dir = tmp_path / "fake_mig_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "001_alpha.py").write_text(
        "VERSION = '001_alpha'\nDESCRIPTION = 'a'\n\n"
        "async def apply(db):\n    pass\n"
    )
    (pkg_dir / "002_beta.py").write_text(
        "VERSION = '002_beta'\nDESCRIPTION = 'b'\n\n"
        "async def apply(db):\n    pass\n"
    )
    # non-numbered modules in the package should be ignored
    (pkg_dir / "helper.py").write_text("# not a migration\n")

    monkeypatch.syspath_prepend(str(tmp_path))

    from omicsclaw.memory.migrations.runner import _discover_migrations
    found = _discover_migrations("fake_mig_pkg")

    versions = sorted(m.VERSION for m in found)
    assert versions == ["001_alpha", "002_beta"]
