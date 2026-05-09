"""Lightweight migrations runner — see omicsclaw/memory/migrations/__init__.py."""

from __future__ import annotations

import importlib
import pkgutil
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, Protocol

import sqlalchemy as sa

if TYPE_CHECKING:
    from omicsclaw.memory.database import DatabaseManager

_DEFAULT_MIGRATIONS_PACKAGE = "omicsclaw.memory.migrations"


class Migration(Protocol):
    VERSION: str
    DESCRIPTION: str

    async def apply(self, db: "DatabaseManager") -> None: ...


_SCHEMA_VERSION_DDL = sa.text(
    "CREATE TABLE IF NOT EXISTS _schema_version ("
    "  version TEXT PRIMARY KEY,"
    "  applied_at TEXT NOT NULL"
    ")"
)


async def _ensure_schema_version_table(db: "DatabaseManager") -> None:
    async with db.session() as s:
        await s.execute(_SCHEMA_VERSION_DDL)


async def _get_applied_versions(db: "DatabaseManager") -> set[str]:
    async with db.session() as s:
        result = await s.execute(sa.text("SELECT version FROM _schema_version"))
        return {row[0] for row in result.all()}


async def _record_applied(db: "DatabaseManager", version: str) -> None:
    async with db.session() as s:
        await s.execute(
            sa.text(
                "INSERT INTO _schema_version (version, applied_at) "
                "VALUES (:v, :t)"
            ),
            {"v": version, "t": datetime.now(timezone.utc).isoformat()},
        )


def _discover_migrations(package: str = _DEFAULT_MIGRATIONS_PACKAGE) -> list[Migration]:
    """Import every NNN_*.py module in ``package`` and return them as migrations."""
    pkg = importlib.import_module(package)
    found: list[Migration] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if not info.name[:1].isdigit():
            continue
        mod = importlib.import_module(f"{package}.{info.name}")
        if all(hasattr(mod, attr) for attr in ("VERSION", "DESCRIPTION", "apply")):
            found.append(mod)  # type: ignore[arg-type]
    return found


async def run_pending(
    db: "DatabaseManager",
    *,
    migrations: Iterable[Migration] | None = None,
) -> list[str]:
    """Apply pending migrations in version-sorted order. Returns versions applied.

    If ``migrations`` is None, discovers them from
    ``omicsclaw.memory.migrations`` (numbered modules: ``001_*.py``).
    """
    if migrations is None:
        migrations = _discover_migrations()

    await _ensure_schema_version_table(db)
    applied = await _get_applied_versions(db)

    pending = [m for m in migrations if m.VERSION not in applied]
    pending.sort(key=lambda m: m.VERSION)

    versions_applied: list[str] = []
    for m in pending:
        await m.apply(db)
        await _record_applied(db, m.VERSION)
        versions_applied.append(m.VERSION)

    return versions_applied
