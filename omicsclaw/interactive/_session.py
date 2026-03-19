"""Lightweight SQLite session persistence for OmicsClaw interactive CLI.

Does NOT depend on LangGraph — uses aiosqlite directly.
Sessions are stored in ~/.config/omicsclaw/sessions.db
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

try:
    import aiosqlite
    _HAS_AIOSQLITE = True
except ImportError:
    _HAS_AIOSQLITE = False

from ._constants import AGENT_NAME, DB_NAME


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_config_dir() -> Path:
    """Return ~/.config/omicsclaw, creating it if absent."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    d = base / "omicsclaw"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_db_path() -> Path:
    return get_config_dir() / DB_NAME


def generate_session_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    agent_name  TEXT NOT NULL DEFAULT 'OmicsClaw',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    model       TEXT,
    workspace   TEXT,
    messages    TEXT NOT NULL DEFAULT '[]'
);
"""


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_db() -> AsyncIterator["aiosqlite.Connection"]:
    if not _HAS_AIOSQLITE:
        raise RuntimeError(
            "aiosqlite is required for session persistence.\n"
            "Install with: pip install aiosqlite"
        )
    db_path = str(get_db_path())
    async with aiosqlite.connect(db_path, timeout=30.0) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(_CREATE_SQL)
        await conn.commit()
        yield conn


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

async def list_sessions(limit: int = 20) -> list[dict]:
    """Return recent sessions, newest first."""
    if not _HAS_AIOSQLITE:
        return []
    try:
        async with get_db() as db:
            q = """
                SELECT session_id, created_at, updated_at, model, workspace, messages
                FROM sessions
                WHERE agent_name = ?
                ORDER BY updated_at DESC
            """
            params: tuple = (AGENT_NAME,)
            if limit > 0:
                q += " LIMIT ?"
                params = (AGENT_NAME, limit)
            async with db.execute(q, params) as cur:
                rows = await cur.fetchall()

            result = []
            for r in rows:
                msgs = json.loads(r["messages"] or "[]")
                preview = _extract_preview(msgs)
                result.append({
                    "session_id": r["session_id"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "model":      r["model"],
                    "workspace":  r["workspace"],
                    "preview":    preview,
                    "message_count": len(msgs),
                })
            return result
    except Exception:
        return []


async def load_session(session_id: str) -> dict | None:
    """Load a full session dict by ID (or prefix)."""
    if not _HAS_AIOSQLITE:
        return None
    try:
        async with get_db() as db:
            # Exact match first
            async with db.execute(
                "SELECT * FROM sessions WHERE session_id = ? AND agent_name = ?",
                (session_id, AGENT_NAME),
            ) as cur:
                row = await cur.fetchone()

            if not row:
                # Prefix match
                async with db.execute(
                    "SELECT * FROM sessions WHERE session_id LIKE ? AND agent_name = ? LIMIT 5",
                    (session_id + "%", AGENT_NAME),
                ) as cur:
                    rows = await cur.fetchall()
                if len(rows) == 1:
                    row = rows[0]
                elif len(rows) > 1:
                    # Ambiguous
                    return None

            if not row:
                return None

            return {
                "session_id":    row["session_id"],
                "created_at":    row["created_at"],
                "updated_at":    row["updated_at"],
                "model":         row["model"],
                "workspace":     row["workspace"],
                "messages":      json.loads(row["messages"] or "[]"),
            }
    except Exception:
        return None


async def save_session(
    session_id: str,
    messages: list[dict],
    *,
    model: str = "",
    workspace: str = "",
) -> None:
    """Upsert a session into the database."""
    if not _HAS_AIOSQLITE:
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        async with get_db() as db:
            # Check if exists
            async with db.execute(
                "SELECT created_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ) as cur:
                existing = await cur.fetchone()

            if existing:
                await db.execute(
                    """UPDATE sessions SET updated_at=?, model=?, workspace=?, messages=?
                       WHERE session_id=?""",
                    (now, model, workspace, json.dumps(messages, ensure_ascii=False), session_id),
                )
            else:
                await db.execute(
                    """INSERT INTO sessions
                       (session_id, agent_name, created_at, updated_at, model, workspace, messages)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, AGENT_NAME, now, now, model, workspace,
                     json.dumps(messages, ensure_ascii=False)),
                )
            await db.commit()
    except Exception:
        pass  # non-fatal


async def delete_session(session_id: str) -> bool:
    """Delete a session by exact ID. Returns True if deleted."""
    if not _HAS_AIOSQLITE:
        return False
    try:
        async with get_db() as db:
            cur = await db.execute(
                "DELETE FROM sessions WHERE session_id = ? AND agent_name = ?",
                (session_id, AGENT_NAME),
            )
            await db.commit()
            return cur.rowcount > 0
    except Exception:
        return False


async def session_exists(session_id: str) -> bool:
    if not _HAS_AIOSQLITE:
        return False
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT 1 FROM sessions WHERE session_id = ? AND agent_name = ? LIMIT 1",
                (session_id, AGENT_NAME),
            ) as cur:
                return (await cur.fetchone()) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _extract_preview(messages: list[dict], max_len: int = 60) -> str:
    """Extract first user message as preview text."""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                # multimodal
                parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                content = " ".join(parts)
            content = str(content).strip()
            if content:
                return content[:max_len] + ("..." if len(content) > max_len else "")
    return ""


def format_relative_time(iso_ts: str | None) -> str:
    """Convert ISO timestamp to human-readable relative string."""
    if not iso_ts:
        return ""
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        return f"{months}mo ago"
    except (ValueError, TypeError):
        return ""
