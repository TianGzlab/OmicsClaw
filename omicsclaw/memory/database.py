"""SQLite connection management and schema for the memory layer.

One :class:`Database` owns one connection and serialises every statement
through a lock, so callers may reach it from any thread — which is what
``asyncio.to_thread`` does on their behalf.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    anchors     TEXT NOT NULL DEFAULT '',
    values_json TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    position    INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    reasoning   TEXT NOT NULL DEFAULT '',
    tool_calls  TEXT NOT NULL DEFAULT '',
    tool_call_id TEXT NOT NULL DEFAULT '',
    name        TEXT NOT NULL DEFAULT '',
    is_error    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages (session_id, position);

CREATE TABLE IF NOT EXISTS long_term_memories (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    content      TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT '',
    importance   INTEGER NOT NULL DEFAULT 0,
    signature    TEXT UNIQUE,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    last_used_at REAL,
    use_count    INTEGER NOT NULL DEFAULT 0,
    ttl_days     INTEGER,
    disabled     INTEGER NOT NULL DEFAULT 0,
    tags         TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
    USING fts5(id UNINDEXED, title, content);
"""


BUSY_TIMEOUT_S = 15.0
"""How long a statement waits for another connection to let go."""


class Database:
    """A SQLite connection shared safely across threads.

    :param path: File to open, or ``":memory:"`` for a transient database.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False plus the lock below: one connection
        # reached from many worker threads, rather than one connection per
        # thread, which would give ":memory:" a separate empty database per
        # thread.
        # ``timeout`` is the busy timeout: a statement blocked by another
        # connection waits this long before giving up, which is what makes
        # several processes on one file workable.
        self._conn = sqlite3.connect(
            self.path, check_same_thread=False, timeout=BUSY_TIMEOUT_S
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            # Switching the journal mode needs the database to itself, and
            # SQLite answers SQLITE_BUSY without consulting the busy
            # handler rather than waiting. Another process opening the same
            # file at the same moment is therefore expected, not an error:
            # whichever connection gets there first converts the file, and
            # the mode is a property of the file, not of this connection.
            try:
                self._conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError:
                pass
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def run(self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Call *work* with the connection held, committing on success.

        :param work: Receives the connection; its return value is passed
            through.
        :returns: Whatever *work* returned.
        :raises sqlite3.Error: Propagated after the transaction is rolled
            back.
        """
        with self._lock:
            try:
                result = work(self._conn)
            except BaseException:
                self._conn.rollback()
                raise
            self._conn.commit()
            return result

    async def arun(self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Await :meth:`run` on a worker thread.

        :param work: Receives the connection; its return value is passed
            through.
        :returns: Whatever *work* returned.
        """
        return await asyncio.to_thread(self.run, work)

    def close(self) -> None:
        """Close the connection. Calling this twice is harmless."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
