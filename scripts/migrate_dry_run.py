"""Dry-run for OmicsClaw memory schema migrations.

Copies a memory.db to a temp location and runs all pending migrations against
the copy, printing a diff (table row counts before/after, namespace
distribution after, count of disclosures we couldn't parse). Exit code 0
only if the migration ran cleanly and row counts are preserved.

The original memory.db is never touched.

Usage:

    python scripts/migrate_dry_run.py
        # Defaults to ~/.config/omicsclaw/memory.db

    python scripts/migrate_dry_run.py --db-path /path/to/memory.db

Recommended workflow before deploying a new migration:

    1. cp ~/.config/omicsclaw/memory.db ~/.config/omicsclaw/memory.db.pre-NNN.bak
    2. python scripts/migrate_dry_run.py
    3. Inspect output; rollback recipe is `cp memory.db.pre-NNN.bak memory.db`
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

import sqlalchemy as sa


_TABLES = ("nodes", "memories", "edges", "paths", "search_documents", "glossary_keywords")


async def _row_counts(db) -> dict[str, int]:
    counts: dict[str, int] = {}
    async with db.session() as s:
        for table in _TABLES:
            try:
                result = await s.execute(sa.text(f"SELECT COUNT(*) FROM {table}"))
                counts[table] = result.scalar_one()
            except Exception as e:
                counts[table] = -1  # table missing in this state
    return counts


async def _namespace_distribution(db) -> dict[str, int]:
    """After migration, count rows per namespace across paths."""
    async with db.session() as s:
        result = await s.execute(
            sa.text(
                "SELECT namespace, COUNT(*) FROM paths GROUP BY namespace ORDER BY 2 DESC"
            )
        )
        return {row[0]: row[1] for row in result.all()}


async def _unparseable_disclosures(db) -> int:
    """Count search_documents rows that have a non-empty disclosure but
    still ended up in __shared__ (likely unparseable)."""
    async with db.session() as s:
        result = await s.execute(
            sa.text(
                "SELECT COUNT(*) FROM search_documents "
                "WHERE namespace = '__shared__' "
                "AND disclosure IS NOT NULL "
                "AND TRIM(disclosure) <> ''"
            )
        )
        return result.scalar_one()


async def main_async(db_path: Path) -> int:
    if not db_path.exists():
        print(f"ERROR: source DB not found at {db_path}", file=sys.stderr)
        return 2

    # Copy to a temp file so the original is untouched
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        copy_path = Path(tmp.name)
    shutil.copy2(db_path, copy_path)
    print(f"Copied {db_path} -> {copy_path}")
    print(f"Source size:  {db_path.stat().st_size:,} bytes")

    # Defer DatabaseManager import so the script remains usable even with a
    # partial install; if memory deps are missing it will surface here.
    from omicsclaw.memory.database import DatabaseManager

    url = f"sqlite+aiosqlite:///{copy_path}"
    db = DatabaseManager(url)
    try:
        before = await _row_counts(db)
        print(f"\nRow counts BEFORE migration:")
        for tbl, n in before.items():
            print(f"  {tbl:24s} {n:>8d}")

        # init_db runs all pending migrations via the runner
        await db.init_db()

        after = await _row_counts(db)
        print(f"\nRow counts AFTER migration:")
        for tbl, n in after.items():
            change = "" if before[tbl] == after[tbl] else f"  ← was {before[tbl]}"
            print(f"  {tbl:24s} {n:>8d}{change}")

        ns_dist = await _namespace_distribution(db)
        print(f"\nNamespace distribution (paths) after migration:")
        for ns, n in ns_dist.items():
            print(f"  {ns:32s} {n:>8d}")

        unparseable = await _unparseable_disclosures(db)
        print(f"\nUnparseable disclosures: {unparseable}")

        # Assertions
        ok = True
        for tbl in _TABLES:
            if before[tbl] >= 0 and before[tbl] != after[tbl]:
                print(
                    f"\n❌ Row count changed for {tbl}: {before[tbl]} -> {after[tbl]}",
                    file=sys.stderr,
                )
                ok = False

        if ok:
            print("\n✅ Migration applied cleanly. Row counts preserved.")
            return 0
        return 1
    finally:
        await db.close()
        try:
            copy_path.unlink()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    default = Path.home() / ".config" / "omicsclaw" / "memory.db"
    parser.add_argument(
        "--db-path",
        type=Path,
        default=default,
        help=f"Path to source memory.db (default: {default})",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args.db_path))


if __name__ == "__main__":
    sys.exit(main())
