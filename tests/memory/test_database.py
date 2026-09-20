"""Connection sharing, threading and schema."""

from __future__ import annotations

import asyncio
import sqlite3
import threading

import pytest

from omicsclaw.memory import Database


def test_schema_creates_every_table() -> None:
    with Database() as db:
        names = db.run(
            lambda c: {
                r[0]
                for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type IN "
                    "('table','view')"
                )
            }
        )
    assert {"sessions", "messages", "long_term_memories", "memories_fts"} <= names


def test_shared_connection_survives_thread_hops() -> None:
    """One database across worker threads, not one database per thread.

    ``check_same_thread=False`` is what lets this work. Opening a
    connection per thread would give ``:memory:`` a separate empty
    database in each one, so a write on the first hop would be invisible
    on the second — and every async method hops through
    ``asyncio.to_thread``.
    """

    async def scenario() -> list[tuple[str]]:
        db = Database()
        await db.arun(
            lambda c: c.execute(
                "INSERT INTO sessions (session_id, created_at, updated_at) "
                "VALUES ('s', 1.0, 1.0)"
            )
        )
        rows = await db.arun(
            lambda c: c.execute("SELECT session_id FROM sessions").fetchall()
        )
        db.close()
        return [tuple(r) for r in rows]

    assert asyncio.run(scenario()) == [("s",)]


def test_concurrent_writers_do_not_interleave() -> None:
    """The lock keeps two threads from sharing one transaction.

    Without it both threads write into the same implicit transaction and
    one ``commit`` publishes the other's half-finished work, so the row
    count comes out wrong under repetition.
    """
    db = Database()
    barrier = threading.Barrier(4)

    def writer(n: int) -> None:
        barrier.wait()
        for i in range(25):
            db.run(
                lambda c, n=n, i=i: c.execute(
                    "INSERT INTO sessions (session_id, created_at, updated_at) "
                    "VALUES (?, 1.0, 1.0)",
                    (f"s{n}-{i}",),
                )
            )

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    count = db.run(
        lambda c: c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    )
    db.close()
    assert count == 100


def test_failed_work_rolls_back() -> None:
    db = Database()

    def boom(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO sessions (session_id, created_at, updated_at) "
            "VALUES ('doomed', 1.0, 1.0)"
        )
        raise RuntimeError("halfway")

    with pytest.raises(RuntimeError):
        db.run(boom)

    count = db.run(
        lambda c: c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    )
    db.close()
    assert count == 0


def test_file_backed_database_creates_parent_directory(tmp_path) -> None:
    target = tmp_path / "nested" / "deeper" / "memory.db"
    with Database(target):
        pass
    assert target.exists()
