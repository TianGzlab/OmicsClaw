"""SQLite backend for memory storage."""

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
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


MEMORY_CLASSES = {
    "dataset": DatasetMemory,
    "analysis": AnalysisMemory,
    "preference": PreferenceMemory,
    "insight": InsightMemory,
    "project_context": ProjectContextMemory,
}


class SQLiteBackend(MemoryStore):
    """Async SQLite storage with encryption."""

    def __init__(self, db_path: str, encryptor: SecureFieldEncryptor):
        self.db_path = db_path
        self.encryptor = encryptor
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create tables if not exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")  # Enable CASCADE delete

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

    async def create_session(self, user_id: str, platform: str, chat_id: str) -> Session:
        """Create new session."""
        session_id = f"{platform}:{user_id}:{chat_id}"
        session = Session(
            session_id=session_id,
            user_id=user_id,
            platform=platform,
        )

        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as db:
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

        return session

    async def get_session(self, session_id: str) -> Session | None:
        """Retrieve session by ID."""
        async with aiosqlite.connect(self.db_path) as db:
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
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as db:
                if "last_activity" in updates:
                    await db.execute(
                        "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
                        (datetime.utcnow().isoformat(), session_id),
                    )
                if "preferences" in updates:
                    await db.execute(
                        "UPDATE sessions SET preferences = ? WHERE session_id = ?",
                        (json.dumps(updates["preferences"]), session_id),
                    )
                await db.commit()

    async def save_memory(self, session_id: str, memory: BaseMemory) -> str:
        """Save memory node with encryption."""
        encrypted_data = self.encryptor.encrypt_memory(memory)

        # Convert datetime objects to ISO strings for JSON serialization
        for key, value in encrypted_data.items():
            if isinstance(value, datetime):
                encrypted_data[key] = value.isoformat()

        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as db:
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

        return memory.memory_id

    async def get_memories(
        self, session_id: str, memory_type: str | None = None, limit: int = 100
    ) -> list[BaseMemory]:
        """Retrieve memories for session."""
        async with aiosqlite.connect(self.db_path) as db:
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
                decrypted_data = self.encryptor.decrypt_memory(
                    MEMORY_CLASSES[memory_type_str].__name__, encrypted_data
                )
                memory_class = MEMORY_CLASSES[memory_type_str]
                memories.append(memory_class(**decrypted_data))

            return memories

    async def update_memory(self, memory_id: str, updates: dict) -> None:
        """Update memory fields."""
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT content FROM memories WHERE memory_id = ?", (memory_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return

                    data = json.loads(row[0])
                    data.update(updates)

                    await db.execute(
                        "UPDATE memories SET content = ? WHERE memory_id = ?",
                        (json.dumps(data), memory_id),
                    )
                    await db.commit()

    async def delete_session(self, session_id: str) -> None:
        """Delete session and all memories."""
        async with self._write_lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA foreign_keys=ON")  # Enable CASCADE
                await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                await db.commit()

