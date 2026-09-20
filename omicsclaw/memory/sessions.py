"""Session persistence backed by SQLite."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Sequence

from omicsclaw.context import CompactionState
from omicsclaw.context.summary import Anchors
from omicsclaw.schema import Message, Role, ToolCall

from .database import Database
from .record import StoredSession

_ANCHOR_FIELDS = (
    "user_intent",
    "execution_progress",
    "key_decisions",
    "tried_solutions",
    "next_steps",
)


def _dump_tool_calls(calls: Sequence[ToolCall]) -> str:
    """Serialise *calls* to JSON, or to ``""`` when there are none."""
    if not calls:
        return ""
    return json.dumps(
        [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls],
        ensure_ascii=False,
    )


def _load_tool_calls(raw: str) -> tuple[ToolCall, ...]:
    """Rebuild tool calls from the JSON written by :func:`_dump_tool_calls`."""
    if not raw:
        return ()
    return tuple(
        ToolCall(id=d["id"], name=d["name"], arguments=d["arguments"])
        for d in json.loads(raw)
    )


def _dump_anchors(anchors: Anchors) -> str:
    """Serialise *anchors* to JSON, or to ``""`` when every field is blank."""
    data = {f: getattr(anchors, f) for f in _ANCHOR_FIELDS}
    if not any(data.values()):
        return ""
    return json.dumps(data, ensure_ascii=False)


def _load_anchors(raw: str) -> Anchors:
    """Rebuild anchors from the JSON written by :func:`_dump_anchors`."""
    if not raw:
        return Anchors()
    data = json.loads(raw)
    return Anchors(**{f: data.get(f, "") for f in _ANCHOR_FIELDS})


class SqliteSessionStore:
    """Keeps conversations in SQLite so they survive the process.

    Satisfies the entry layer's ``SessionStore`` protocol structurally;
    pass an instance as ``attach_sessions(app, store=...)``.

    :param database: Open database to read and write through.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    async def load(self, session_id: str) -> StoredSession | None:
        """Read one session back.

        :param session_id: Identifier to look up.
        :returns: The stored session, or ``None`` if it was never saved.
        """
        return await self._db.arun(lambda c: self._load(c, session_id))

    async def save(self, session: StoredSession) -> None:
        """Write *session* out, replacing any previous copy of it.

        System messages in ``session.history`` are dropped: the prompt
        assembly adds a fresh one every turn, so storing one would stack a
        stale copy beside the current one.

        ``session.values`` is stored as JSON, and only values JSON can
        represent come back unchanged — a tuple returns as a list and a
        non-string key as a string.

        :param session: Session to persist.
        :raises TypeError: If ``session.values`` holds something JSON
            cannot encode. Nothing is written in that case.
        """
        await self._db.arun(lambda c: self._save(c, session))

    async def list(self, limit: int = 50) -> Sequence[StoredSession]:
        """Every session in this database file, newest first.

        **The scope is the database file itself; this method isolates
        nothing.** The query carries no ``WHERE`` and the ``sessions``
        table carries no owner or scope column, so whatever a caller is
        allowed to see is decided entirely by which file the
        :class:`~omicsclaw.memory.Database` was opened on. A deployment
        that points several people at one file and then offers them this
        listing hands each of them the others' conversations, and nothing
        here will stop it.

        :param limit: Greatest number of sessions to return.
        :returns: Sessions ordered by creation time, newest first.
        """
        return await self._db.arun(lambda c: self._list(c, limit))

    async def delete(self, session_id: str) -> bool:
        """Remove one session and its messages.

        :param session_id: Identifier to delete.
        :returns: ``True`` if a session was removed.
        """
        return await self._db.arun(lambda c: self._delete(c, session_id))

    @staticmethod
    def _load(conn: sqlite3.Connection, session_id: str) -> StoredSession | None:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        messages = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY position ASC",
            (session_id,),
        ).fetchall()
        history = tuple(
            Message(
                role=Role(m["role"]),
                content=m["content"],
                reasoning_content=m["reasoning"],
                tool_calls=_load_tool_calls(m["tool_calls"]),
                tool_call_id=m["tool_call_id"],
                name=m["name"],
                is_error=bool(m["is_error"]),
            )
            for m in messages
        )
        values: dict[str, Any] = (
            json.loads(row["values_json"]) if row["values_json"] else {}
        )
        return StoredSession(
            session_id=row["session_id"],
            history=history,
            compaction=CompactionState(
                summary=row["summary"], anchors=_load_anchors(row["anchors"])
            ),
            created_at=row["created_at"],
            values=values,
        )

    @staticmethod
    def _save(conn: sqlite3.Connection, session: StoredSession) -> None:
        conn.execute(
            """INSERT INTO sessions
                   (session_id, created_at, updated_at, summary, anchors,
                    values_json)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (session_id) DO UPDATE SET
                   updated_at  = excluded.updated_at,
                   summary     = excluded.summary,
                   anchors     = excluded.anchors,
                   values_json = excluded.values_json""",
            (
                session.session_id,
                session.created_at,
                time.time(),
                session.compaction.summary,
                _dump_anchors(session.compaction.anchors),
                json.dumps(dict(session.values), ensure_ascii=False)
                if session.values
                else "",
            ),
        )
        conn.execute(
            "DELETE FROM messages WHERE session_id = ?", (session.session_id,)
        )
        keep = [m for m in session.history if m.role is not Role.SYSTEM]
        conn.executemany(
            """INSERT INTO messages
                   (session_id, position, role, content, reasoning, tool_calls,
                    tool_call_id, name, is_error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    session.session_id,
                    i,
                    m.role.value,
                    m.content,
                    m.reasoning_content,
                    _dump_tool_calls(m.tool_calls),
                    m.tool_call_id,
                    m.name,
                    int(m.is_error),
                )
                for i, m in enumerate(keep)
            ],
        )

    @classmethod
    def _list(cls, conn: sqlite3.Connection, limit: int) -> list[StoredSession]:
        rows = conn.execute(
            "SELECT session_id FROM sessions ORDER BY created_at DESC LIMIT ?",
            (max(limit, 0),),
        ).fetchall()
        loaded = [cls._load(conn, r["session_id"]) for r in rows]
        return [s for s in loaded if s is not None]

    @staticmethod
    def _delete(conn: sqlite3.Connection, session_id: str) -> bool:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cur = conn.execute(
            "DELETE FROM sessions WHERE session_id = ?", (session_id,)
        )
        return cur.rowcount > 0
