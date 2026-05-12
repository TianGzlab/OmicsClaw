# pyright: reportArgumentType=false, reportCallIssue=false

"""
Database connection and session management for OmicsClaw Graph Memory.

Ported from nocturne_memory with OmicsClaw configuration.
Supports both SQLite (local, default) and PostgreSQL (remote).
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# async_sessionmaker added in SQLAlchemy 2.0; fall back to sessionmaker for 1.4+
try:
    from sqlalchemy.ext.asyncio import async_sessionmaker as _async_sessionmaker
except ImportError:
    _async_sessionmaker = None  # type: ignore

from .models import Base


# Default DB URL — uses ~/.config/omicsclaw/memory.db
_DEFAULT_DB_DIR = Path.home() / ".config" / "omicsclaw"
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{_DEFAULT_DB_DIR / 'memory.db'}"


def _get_database_url() -> str:
    """Resolve database URL from environment or default."""
    return os.getenv("OMICSCLAW_MEMORY_DB_URL", _DEFAULT_DB_URL)


class DatabaseManager:
    """Async database connection manager.

    Provides session lifecycle management (commit/rollback) and table creation.
    All business-logic services receive a ``DatabaseManager`` via injection.
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or _get_database_url()
        self.db_type = self._detect_database_type(self.database_url)

        # Ensure SQLite directory exists
        if self.db_type == "sqlite":
            db_path = self.database_url.split("///", 1)[-1] if "///" in self.database_url else ""
            if db_path:
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        engine_kwargs = {"echo": False}
        if self.db_type == "postgresql":
            parsed = urlparse(self.database_url)
            is_local = parsed.hostname in ("localhost", "127.0.0.1", "::1")

            connect_args = {}
            parsed_qs = parse_qs(parsed.query, keep_blank_values=True)
            ssl_values = parsed_qs.get("ssl", []) + parsed_qs.get("sslmode", [])
            ssl_value = ssl_values[-1].lower() if ssl_values else ""
            ssl_disabled = ssl_value in ("disable", "false", "off", "0", "no")

            if not is_local and not ssl_disabled:
                connect_args["ssl"] = "require"
                connect_args["statement_cache_size"] = 0

            engine_kwargs.update(
                {
                    "pool_size": 10,
                    "max_overflow": 20,
                    "pool_recycle": 3600,
                    "pool_pre_ping": True,
                    "connect_args": connect_args,
                }
            )

        self.engine = create_async_engine(self.database_url, **engine_kwargs)

        if self.db_type == "sqlite":
            @event.listens_for(self.engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        if _async_sessionmaker is not None:
            self.async_session = _async_sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
        else:
            # SQLAlchemy 1.4 fallback
            self.async_session = sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False  # type: ignore
            )

    @staticmethod
    def _detect_database_type(url: str) -> str:
        if "postgresql" in url:
            return "postgresql"
        return "sqlite"

    @asynccontextmanager
    async def session(self):
        """Get an async session context manager."""
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @asynccontextmanager
    async def _optional_session(self, session: Optional[AsyncSession] = None):
        """Helper to use an existing session or create a new one."""
        if session:
            yield session
        else:
            async with self.session() as new_session:
                yield new_session

    async def init_db(self):
        """Create tables if they don't exist, and ensure root node is present."""
        try:
            from sqlalchemy import inspect as sa_inspect

            def check_initialized(connection):
                return sa_inspect(connection).has_table("memories")

            async with self.engine.begin() as conn:
                is_initialized = await conn.run_sync(check_initialized)
                if not is_initialized:
                    await conn.run_sync(Base.metadata.create_all)

            # Run any pending schema migrations after the base schema exists.
            # Imported lazily to avoid a circular import at module load time.
            from omicsclaw.memory.migrations import run_pending
            await run_pending(self)

            # Ensure the root node exists (all edges reference it as parent)
            await self._ensure_root_node()

            # Create FTS5 virtual table for SQLite if not exists
            if self.db_type == "sqlite":
                await self._create_fts_table()

        except Exception as e:
            db_url = self.database_url
            if "@" in db_url and ":" in db_url:
                try:
                    parsed = urlparse(db_url)
                    if parsed.password:
                        db_url = db_url.replace(f":{parsed.password}@", ":***@")
                except Exception:
                    pass
            raise RuntimeError(
                f"Failed to connect to database.\n"
                f"  URL: {db_url}\n"
                f"  Error: {e}\n\n"
                f"Troubleshooting:\n"
                f"  - Check OMICSCLAW_MEMORY_DB_URL in .env\n"
                f"  - For SQLite, ensure the directory exists\n"
                f"  - For PostgreSQL, ensure the host is reachable"
            ) from e

    async def _ensure_root_node(self):
        """Insert the root node into the nodes table if it doesn't exist.

        The graph is a tree rooted at ROOT_NODE_UUID. All top-level edges
        reference it as parent_uuid, so the row in `nodes` MUST exist before
        any edge can be created (due to FOREIGN KEY constraints).
        """
        from sqlalchemy import select
        from .models import Node, ROOT_NODE_UUID

        async with self.async_session() as session:
            result = await session.execute(
                select(Node).where(Node.uuid == ROOT_NODE_UUID)
            )
            if result.scalars().first() is None:
                session.add(Node(uuid=ROOT_NODE_UUID))
                await session.commit()

    async def _create_fts_table(self):
        """Create SQLite FTS5 virtual table for full-text search."""
        from sqlalchemy import text

        async with self.async_session() as session:
            try:
                # Check if FTS table already exists
                result = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='search_documents_fts'")
                )
                if result.scalar() is None:
                    await session.execute(
                        text("""
                            CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts
                            USING fts5(
                                namespace,
                                domain,
                                path,
                                node_uuid,
                                uri,
                                content,
                                disclosure,
                                search_terms,
                                content=search_documents,
                                content_rowid=rowid
                            )
                        """)
                    )
                    await session.commit()
            except Exception:
                # FTS5 may not be available on all SQLite builds
                await session.rollback()

    async def close(self):
        """Close the database connection."""
        await self.engine.dispose()
