"""001_namespace: Add namespace partition to paths, search_documents, glossary_keywords.

Idempotent — checks for the namespace column on ``paths`` before doing any
work. Backfills namespace from the ``disclosure`` field of session and memory
records (best-effort; rows without parseable disclosure stay at ``__shared__``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from omicsclaw.memory.database import DatabaseManager

VERSION = "001_namespace"
DESCRIPTION = "Add namespace partition to paths, search_documents, glossary_keywords"

# Disclosure formats produced by compat.py:
#   "Memory from session <platform>:<user_id>:<session_uuid>"
#   "Session for user <user_id> on <platform>"
_DISCLOSURE_MEMORY_RE = re.compile(r"Memory from session (\S+?):(\S+?):")
_DISCLOSURE_SESSION_RE = re.compile(r"Session for user (\S+) on (\S+)")


async def _column_exists(s, table: str, column: str) -> bool:
    result = await s.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result.all())


def _parse_disclosure_namespace(disclosure: str | None) -> str | None:
    """Extract ``f"{platform}/{user_id}"`` from a disclosure string, if possible."""
    if not disclosure:
        return None
    m = _DISCLOSURE_MEMORY_RE.search(disclosure)
    if m:
        platform, user_id = m.group(1), m.group(2)
        return f"{platform}/{user_id}"
    m = _DISCLOSURE_SESSION_RE.search(disclosure)
    if m:
        user_id, platform = m.group(1), m.group(2)
        return f"{platform}/{user_id}"
    return None


async def _backfill_namespace_from_disclosure(s) -> None:
    """Update ``namespace`` on paths + search_documents based on disclosure data."""
    result = await s.execute(
        sa.text(
            "SELECT domain, path, disclosure FROM search_documents "
            "WHERE disclosure IS NOT NULL"
        )
    )
    for domain, path, disclosure in result.all():
        ns = _parse_disclosure_namespace(disclosure)
        if not ns:
            continue
        await s.execute(
            sa.text(
                "UPDATE paths SET namespace = :ns "
                "WHERE namespace = '__shared__' AND domain = :d AND path = :p"
            ),
            {"ns": ns, "d": domain, "p": path},
        )
        await s.execute(
            sa.text(
                "UPDATE search_documents SET namespace = :ns "
                "WHERE namespace = '__shared__' AND domain = :d AND path = :p"
            ),
            {"ns": ns, "d": domain, "p": path},
        )


async def apply(db: "DatabaseManager") -> None:
    async with db.session() as s:
        # Idempotent guard — column already added means migration has been applied.
        if await _column_exists(s, "paths", "namespace"):
            return

        # 1. Rebuild paths with composite PK (namespace, domain, path)
        await s.execute(sa.text("""
            CREATE TABLE paths_new (
                namespace  VARCHAR(128) NOT NULL DEFAULT '__shared__',
                domain     VARCHAR(64)  NOT NULL DEFAULT 'core',
                path       VARCHAR(512) NOT NULL,
                edge_id    INTEGER REFERENCES edges(id),
                created_at DATETIME,
                PRIMARY KEY (namespace, domain, path)
            )
        """))
        await s.execute(sa.text("""
            INSERT INTO paths_new (namespace, domain, path, edge_id, created_at)
            SELECT '__shared__', domain, path, edge_id, created_at FROM paths
        """))
        await s.execute(sa.text("DROP TABLE paths"))
        await s.execute(sa.text("ALTER TABLE paths_new RENAME TO paths"))

        # 2. Rebuild search_documents with composite PK
        await s.execute(sa.text("""
            CREATE TABLE search_documents_new (
                namespace    VARCHAR(128) NOT NULL DEFAULT '__shared__',
                domain       VARCHAR(64)  NOT NULL DEFAULT 'core',
                path         VARCHAR(512) NOT NULL,
                node_uuid    VARCHAR(36)  NOT NULL REFERENCES nodes(uuid) ON DELETE CASCADE,
                memory_id    INTEGER      NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                uri          TEXT         NOT NULL,
                content      TEXT         NOT NULL,
                disclosure   TEXT,
                search_terms TEXT         NOT NULL DEFAULT '',
                priority     INTEGER      NOT NULL DEFAULT 0,
                updated_at   DATETIME,
                PRIMARY KEY (namespace, domain, path)
            )
        """))
        await s.execute(sa.text("""
            INSERT INTO search_documents_new
                (namespace, domain, path, node_uuid, memory_id, uri,
                 content, disclosure, search_terms, priority, updated_at)
            SELECT '__shared__', domain, path, node_uuid, memory_id, uri,
                   content, disclosure, search_terms, priority, updated_at
            FROM search_documents
        """))
        await s.execute(sa.text("DROP TABLE search_documents"))
        await s.execute(sa.text("ALTER TABLE search_documents_new RENAME TO search_documents"))

        # 3. Rebuild glossary_keywords with namespace + new UNIQUE constraint
        await s.execute(sa.text("""
            CREATE TABLE glossary_keywords_new (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword    TEXT         NOT NULL,
                node_uuid  VARCHAR(36)  NOT NULL REFERENCES nodes(uuid) ON DELETE CASCADE,
                namespace  VARCHAR(128) NOT NULL DEFAULT '__shared__',
                created_at DATETIME,
                UNIQUE (namespace, keyword, node_uuid)
            )
        """))
        await s.execute(sa.text("""
            INSERT INTO glossary_keywords_new (id, keyword, node_uuid, namespace, created_at)
            SELECT id, keyword, node_uuid, '__shared__', created_at FROM glossary_keywords
        """))
        await s.execute(sa.text("DROP TABLE glossary_keywords"))
        await s.execute(sa.text("ALTER TABLE glossary_keywords_new RENAME TO glossary_keywords"))

        # 4. Best-effort namespace backfill from disclosure metadata
        await _backfill_namespace_from_disclosure(s)

        # 5. Rebuild FTS5 virtual table with namespace column, repopulate from search_documents
        await s.execute(sa.text("DROP TABLE IF EXISTS search_documents_fts"))
        await s.execute(sa.text("""
            CREATE VIRTUAL TABLE search_documents_fts USING fts5(
                namespace, domain, path, node_uuid, uri, content,
                disclosure, search_terms,
                content=search_documents,
                content_rowid=rowid
            )
        """))
        await s.execute(sa.text("""
            INSERT INTO search_documents_fts (
                rowid, namespace, domain, path, node_uuid, uri,
                content, disclosure, search_terms
            )
            SELECT rowid, namespace, domain, path, node_uuid, uri,
                   content, disclosure, search_terms
            FROM search_documents
        """))
