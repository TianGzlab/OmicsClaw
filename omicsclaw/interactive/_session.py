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

from omicsclaw.runtime.transcript_store import (
    build_transcript_summary,
    sanitize_tool_history,
)

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
    metadata    TEXT NOT NULL DEFAULT '{}',
    transcript  TEXT NOT NULL DEFAULT '[]',
    transcript_summary TEXT NOT NULL DEFAULT '{}',
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
        await _ensure_schema(conn)
        yield conn


async def _ensure_schema(conn: "aiosqlite.Connection") -> None:
    await conn.execute(_CREATE_SQL)
    async with conn.execute("PRAGMA table_info(sessions)") as cur:
        columns = {
            row["name"] if isinstance(row, aiosqlite.Row) else row[1]
            for row in await cur.fetchall()
        }

    if "metadata" not in columns:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'"
        )
    if "transcript" not in columns:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN transcript TEXT NOT NULL DEFAULT '[]'"
        )
    if "transcript_summary" not in columns:
        await conn.execute(
            "ALTER TABLE sessions ADD COLUMN transcript_summary TEXT NOT NULL DEFAULT '{}'"
        )
    await conn.commit()


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
                SELECT session_id, created_at, updated_at, model, workspace, metadata, transcript, transcript_summary, messages
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
                metadata = _load_json_field(r["metadata"], default={})
                transcript = _load_session_transcript(
                    transcript_raw=r["transcript"],
                    messages_raw=r["messages"],
                )
                transcript_summary = _load_session_transcript_summary(
                    summary_raw=r["transcript_summary"],
                    transcript=transcript,
                    metadata=metadata,
                    workspace=r["workspace"],
                )
                preview = _extract_preview(transcript)
                result.append({
                    "session_id": r["session_id"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "model":      r["model"],
                    "workspace":  r["workspace"],
                    "metadata":   metadata,
                    "preview":    preview,
                    "message_count": len(transcript),
                    "compacted_tool_result_count": len(
                        transcript_summary["compacted_tool_results"]
                    ),
                    "plan_reference_count": len(transcript_summary["plan_references"]),
                    "advisory_event_count": len(transcript_summary["advisory_events"]),
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

            metadata = _load_json_field(row["metadata"], default={})
            transcript = _load_session_transcript(
                transcript_raw=row["transcript"],
                messages_raw=row["messages"],
            )
            transcript_summary = _load_session_transcript_summary(
                summary_raw=row["transcript_summary"],
                transcript=transcript,
                metadata=metadata,
                workspace=row["workspace"],
            )

            return {
                "session_id":    row["session_id"],
                "created_at":    row["created_at"],
                "updated_at":    row["updated_at"],
                "model":         row["model"],
                "workspace":     row["workspace"],
                "metadata":      metadata,
                "transcript":    transcript,
                "messages":      transcript,
                "transcript_summary": transcript_summary,
                "compacted_tool_results": transcript_summary["compacted_tool_results"],
                "plan_references": transcript_summary["plan_references"],
                "advisory_events": transcript_summary["advisory_events"],
            }
    except Exception:
        return None


async def save_session(
    session_id: str,
    messages: list[dict],
    *,
    model: str = "",
    workspace: str = "",
    metadata: dict | None = None,
    transcript: list[dict] | None = None,
) -> None:
    """Upsert a session into the database."""
    if not _HAS_AIOSQLITE:
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        normalized_metadata = dict(metadata or {})
        metadata_json = json.dumps(normalized_metadata, ensure_ascii=False)
        source_transcript = transcript if transcript is not None else messages
        sanitised_transcript = _sanitize_session_messages(source_transcript)
        transcript_summary_json = json.dumps(
            build_transcript_summary(
                sanitised_transcript,
                metadata=normalized_metadata,
                workspace=workspace,
            ).to_dict(),
            ensure_ascii=False,
        )
        transcript_json = json.dumps(sanitised_transcript, ensure_ascii=False)
        messages_json = json.dumps(sanitised_transcript, ensure_ascii=False)
        async with get_db() as db:
            # Check if exists
            async with db.execute(
                "SELECT created_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ) as cur:
                existing = await cur.fetchone()

            if existing:
                await db.execute(
                    """UPDATE sessions SET updated_at=?, model=?, workspace=?, metadata=?, transcript=?, transcript_summary=?, messages=?
                       WHERE session_id=?""",
                    (
                        now,
                        model,
                        workspace,
                        metadata_json,
                        transcript_json,
                        transcript_summary_json,
                        messages_json,
                        session_id,
                    ),
                )
            else:
                await db.execute(
                    """INSERT INTO sessions
                       (session_id, agent_name, created_at, updated_at, model, workspace, metadata, transcript, transcript_summary, messages)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        AGENT_NAME,
                        now,
                        now,
                        model,
                        workspace,
                        metadata_json,
                        transcript_json,
                        transcript_summary_json,
                        messages_json,
                    ),
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


def _load_json_field(raw: str | None, *, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _sanitize_session_messages(messages: list[dict] | object) -> list[dict]:
    if not isinstance(messages, list):
        return []
    safe_messages = [message for message in messages if isinstance(message, dict)]
    return sanitize_tool_history(safe_messages, warn=False)


def _load_session_transcript(
    *,
    transcript_raw: str | None,
    messages_raw: str | None,
) -> list[dict]:
    transcript = _sanitize_session_messages(
        _load_json_field(transcript_raw, default=[])
    )
    if transcript:
        return transcript
    return _sanitize_session_messages(_load_json_field(messages_raw, default=[]))


def _load_session_transcript_summary(
    *,
    summary_raw: str | None,
    transcript: list[dict],
    metadata: dict | None = None,
    workspace: str | None = None,
) -> dict[str, list[dict]]:
    summary = _load_json_field(summary_raw, default={})
    if not isinstance(summary, dict):
        summary = {}

    fallback = build_transcript_summary(
        transcript,
        metadata=metadata or {},
        workspace=workspace,
    ).to_dict()

    normalized = {
        "compacted_tool_results": summary.get("compacted_tool_results"),
        "plan_references": summary.get("plan_references"),
        "advisory_events": summary.get("advisory_events"),
    }
    for key, fallback_value in fallback.items():
        value = normalized.get(key)
        if isinstance(value, list):
            normalized[key] = [item for item in value if isinstance(item, dict)]
        else:
            normalized[key] = fallback_value
    return normalized


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


def export_conversation_to_markdown(session_id: str, messages: list[dict], out_path: Path) -> None:
    """Export the conversation to a formatted Markdown report."""
    transcript_summary = build_transcript_summary(messages).to_dict()
    compacted_tool_results = transcript_summary["compacted_tool_results"]
    plan_references = transcript_summary["plan_references"]
    advisory_events = transcript_summary["advisory_events"]
    lines = [
        f"# OmicsClaw Analysis Report",
        f"**Session ID:** `{session_id}`",
        f"**Exported:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n---"
    ]
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            if isinstance(content, list):
                parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                content = " ".join(parts)
            lines.append(f"\n### 👤 User\n{content}\n")
        elif role == "assistant":
            if not content and msg.get("tool_calls"):
                continue
            if content:
                lines.append(f"\n### 🤖 OmicsClaw\n{content}\n")

    if compacted_tool_results:
        lines.append("\n## Compacted Tool Results\n")
        for ref in compacted_tool_results:
            tool_name = str(ref.get("tool_name", "") or "unknown")
            lines.append(f"- Tool: `{tool_name}`")
            if ref.get("tool_call_id"):
                lines.append(f"  Call ID: `{ref['tool_call_id']}`")
            lines.append(f"  Path: `{ref.get('storage_path', '')}`")
            if int(ref.get("output_bytes", 0) or 0) > 0:
                lines.append(f"  Bytes: `{ref['output_bytes']}`")

    if plan_references:
        lines.append("\n## Plan References\n")
        for ref in plan_references:
            lines.append(f"- Path: `{ref.get('path', '')}`")
            if ref.get("workspace"):
                lines.append(f"  Workspace: `{ref['workspace']}`")
            lines.append(f"  Exists: `{bool(ref.get('exists', False))}`")

    if advisory_events:
        lines.append("\n## Advisory Events\n")
        for ref in advisory_events:
            lines.append(f"- `{ref.get('message', '')}`")
                
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
