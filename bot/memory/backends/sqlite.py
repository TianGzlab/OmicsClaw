"""SQLite backend for memory storage."""

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiosqlite
from bot.memory.models import (
    Session,
    BaseMemory,
    DatasetMemory,
    AnalysisMemory,
    PreferenceMemory,
    InsightMemory,
    ProjectContextMemory,
)
from bot.memory.store import MemoryStore
from bot.memory.encryption import SecureFieldEncryptor

logger = logging.getLogger("omicsclaw.memory.sqlite")

MEMORY_CLASSES = {
    "dataset": DatasetMemory,
    "analysis": AnalysisMemory,
    "preference": PreferenceMemory,
    "insight": InsightMemory,
    "project_context": ProjectContextMemory,
}

# Default TTL in days (configurable via OMICSCLAW_MEMORY_TTL_DAYS)
DEFAULT_TTL_DAYS = int(os.getenv("OMICSCLAW_MEMORY_TTL_DAYS", "30"))


class SQLiteBackend(MemoryStore):
    """Async SQLite storage with encryption and connection pooling."""

    def __init__(self, db_path: str, encryptor: SecureFieldEncryptor):
        self.db_path = db_path
        self.encryptor = encryptor
        self._write_lock = asyncio.Lock()
        self._conn: aiosqlite.Connection | None = None
        self._initialized = False
        self._op_count = 0

    async def _ensure_connection(self) -> aiosqlite.Connection:
        """Get or create persistent connection with PRAGMAs set once."""
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    async def _ensure_initialized(self):
        """Lazy initialization: create tables on first use."""
        if self._initialized:
            return
        await self.initialize()

    async def initialize(self) -> None:
        """Create tables if not exist."""
        db = await self._ensure_connection()

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                preferences TEXT,
                active INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)

        await db.execute("CREATE INDEX IF NOT EXISTS idx_session_memories ON memories(session_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memories(memory_type)")
        await db.commit()
        self._initialized = True

        # Run TTL cleanup on startup
        await self.cleanup_expired()

    async def close(self) -> None:
        """Close the persistent connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def cleanup_expired(self, ttl_days: int | None = None) -> int:
        """Remove sessions (and their memories via CASCADE) older than ttl_days."""
        ttl = ttl_days if ttl_days is not None else DEFAULT_TTL_DAYS
        if ttl <= 0:
            return 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl)).isoformat()
        db = await self._ensure_connection()

        async with self._write_lock:
            cursor = await db.execute(
                "DELETE FROM sessions WHERE last_activity < ?", (cutoff,)
            )
            count = cursor.rowcount
            await db.commit()

        if count > 0:
            logger.info(f"TTL cleanup: removed {count} expired session(s) (>{ttl} days)")
        return count

    async def _maybe_cleanup(self):
        """Periodically trigger TTL cleanup (every 100 operations)."""
        self._op_count += 1
        if self._op_count % 100 == 0:
            await self.cleanup_expired()

    async def create_session(self, user_id: str, platform: str, chat_id: str) -> Session:
        """Create new session."""
        await self._ensure_initialized()
        session_id = f"{platform}:{user_id}:{chat_id}"
        session = Session(
            session_id=session_id,
            user_id=user_id,
            platform=platform,
        )

        db = await self._ensure_connection()
        async with self._write_lock:
            await db.execute(
                """INSERT INTO sessions (session_id, user_id, platform, created_at, last_activity, preferences)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session.session_id,
                    session.user_id,
                    session.platform,
                    session.created_at.isoformat(),
                    session.last_activity.isoformat(),
                    json.dumps(session.preferences),
                ),
            )
            await db.commit()

        await self._maybe_cleanup()
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Retrieve session by ID."""
        await self._ensure_initialized()
        db = await self._ensure_connection()

        async with db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            return Session(
                session_id=row[0],
                user_id=row[1],
                platform=row[2],
                created_at=datetime.fromisoformat(row[3]),
                last_activity=datetime.fromisoformat(row[4]),
                preferences=json.loads(row[5]) if row[5] else {},
                active=bool(row[6]),
            )

    async def update_session(self, session_id: str, updates: dict) -> None:
        """Update session fields."""
        await self._ensure_initialized()
        db = await self._ensure_connection()

        async with self._write_lock:
            if "last_activity" in updates:
                await db.execute(
                    "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
                    (datetime.now(timezone.utc).isoformat(), session_id),
                )
            if "preferences" in updates:
                await db.execute(
                    "UPDATE sessions SET preferences = ? WHERE session_id = ?",
                    (json.dumps(updates["preferences"]), session_id),
                )
            await db.commit()

    async def save_memory(self, session_id: str, memory: BaseMemory) -> str:
        """Save memory node with encryption and deduplication."""
        await self._ensure_initialized()

        # Deduplication check
        existing_id = await self._find_duplicate(session_id, memory)
        if existing_id:
            # Update existing memory instead of inserting duplicate
            updates = memory.model_dump()
            # Remove fields that shouldn't change
            updates.pop("memory_id", None)
            updates.pop("memory_type", None)
            updates.pop("created_at", None)
            await self.update_memory(existing_id, updates)
            logger.debug(f"Deduplicated {memory.memory_type}: updated {existing_id}")
            return existing_id

        encrypted_data = self.encryptor.encrypt_memory(memory)

        # Convert datetime objects to ISO strings for JSON serialization
        for key, value in encrypted_data.items():
            if isinstance(value, datetime):
                encrypted_data[key] = value.isoformat()

        db = await self._ensure_connection()
        async with self._write_lock:
            await db.execute(
                """INSERT INTO memories (memory_id, session_id, memory_type, content, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    memory.memory_id,
                    session_id,
                    memory.memory_type,
                    json.dumps(encrypted_data),
                    memory.created_at.isoformat(),
                ),
            )
            await db.commit()

        await self._maybe_cleanup()
        return memory.memory_id

    async def _find_duplicate(self, session_id: str, memory: BaseMemory) -> str | None:
        """Check if a duplicate memory already exists. Returns memory_id if found."""
        db = await self._ensure_connection()

        if isinstance(memory, DatasetMemory):
            # Deduplicate by file_path
            async with db.execute(
                "SELECT memory_id, content FROM memories WHERE session_id = ? AND memory_type = 'dataset'",
                (session_id,),
            ) as cursor:
                async for row in cursor:
                    try:
                        data = json.loads(row[1])
                        decrypted = self.encryptor.decrypt_memory("DatasetMemory", data)
                        if decrypted.get("file_path") == memory.file_path:
                            return row[0]
                    except Exception:
                        continue

        elif isinstance(memory, PreferenceMemory):
            # Deduplicate by domain + key
            async with db.execute(
                "SELECT memory_id, content FROM memories WHERE session_id = ? AND memory_type = 'preference'",
                (session_id,),
            ) as cursor:
                async for row in cursor:
                    try:
                        data = json.loads(row[1])
                        decrypted = self.encryptor.decrypt_memory("PreferenceMemory", data)
                        if decrypted.get("domain") == memory.domain and decrypted.get("key") == memory.key:
                            return row[0]
                    except Exception:
                        continue

        return None

    async def get_memories(
        self, session_id: str, memory_type: str | None = None, limit: int = 100
    ) -> list[BaseMemory]:
        """Retrieve memories for session."""
        await self._ensure_initialized()
        db = await self._ensure_connection()

        if memory_type:
            query = "SELECT * FROM memories WHERE session_id = ? AND memory_type = ? ORDER BY created_at DESC LIMIT ?"
            params = (session_id, memory_type, limit)
        else:
            query = "SELECT * FROM memories WHERE session_id = ? ORDER BY created_at DESC LIMIT ?"
            params = (session_id, limit)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        memories = []
        for row in rows:
            memory_type_str = row[2]
            encrypted_data = json.loads(row[3])
            memory_class = MEMORY_CLASSES.get(memory_type_str)
            if not memory_class:
                continue
            decrypted_data = self.encryptor.decrypt_memory(
                memory_class.__name__, encrypted_data
            )
            memories.append(memory_class(**decrypted_data))

        return memories

    async def update_memory(self, memory_id: str, updates: dict) -> None:
        """Update memory fields, re-encrypting sensitive data."""
        await self._ensure_initialized()
        db = await self._ensure_connection()

        async with self._write_lock:
            async with db.execute(
                "SELECT content, memory_type FROM memories WHERE memory_id = ?", (memory_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return

                encrypted_data = json.loads(row[0])
                memory_type_str = row[1]
                memory_class = MEMORY_CLASSES.get(memory_type_str)

                if memory_class:
                    # Decrypt existing data, merge updates, re-encrypt
                    decrypted = self.encryptor.decrypt_memory(
                        memory_class.__name__, encrypted_data
                    )
                    decrypted.update(updates)
                    # Convert datetime objects for serialization
                    for key, value in decrypted.items():
                        if isinstance(value, datetime):
                            decrypted[key] = value.isoformat()
                    # Re-encrypt the merged data
                    memory_obj = memory_class(**decrypted)
                    re_encrypted = self.encryptor.encrypt_memory(memory_obj)
                    for key, value in re_encrypted.items():
                        if isinstance(value, datetime):
                            re_encrypted[key] = value.isoformat()
                    data = re_encrypted
                else:
                    # Fallback: raw merge (unknown type)
                    encrypted_data.update(updates)
                    data = encrypted_data

                await db.execute(
                    "UPDATE memories SET content = ? WHERE memory_id = ?",
                    (json.dumps(data), memory_id),
                )
                await db.commit()

    async def delete_session(self, session_id: str) -> None:
        """Delete session and all memories (CASCADE)."""
        await self._ensure_initialized()
        db = await self._ensure_connection()

        async with self._write_lock:
            await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await db.commit()

    async def search_memories(
        self, session_id: str, query: str, memory_type: str | None = None
    ) -> list[BaseMemory]:
        """Search memories by decrypting content and matching against query."""
        await self._ensure_initialized()
        db = await self._ensure_connection()

        if memory_type:
            sql = "SELECT * FROM memories WHERE session_id = ? AND memory_type = ? ORDER BY created_at DESC"
            params = (session_id, memory_type)
        else:
            sql = "SELECT * FROM memories WHERE session_id = ? ORDER BY created_at DESC"
            params = (session_id,)

        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

        query_lower = query.lower()
        results = []
        for row in rows:
            memory_type_str = row[2]
            encrypted_data = json.loads(row[3])
            memory_class = MEMORY_CLASSES.get(memory_type_str)
            if not memory_class:
                continue
            try:
                decrypted = self.encryptor.decrypt_memory(
                    memory_class.__name__, encrypted_data
                )
                # Search across all string values in the decrypted data
                if any(
                    query_lower in str(v).lower()
                    for v in decrypted.values()
                    if v is not None
                ):
                    results.append(memory_class(**decrypted))
            except Exception:
                continue

        return results
