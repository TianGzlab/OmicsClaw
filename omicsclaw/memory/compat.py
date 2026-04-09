"""
Compatibility Layer — Drop-in replacement for bot.memory.MemoryStore.

Maps the old flat memory interface to the new graph memory system.
This allows bot/core.py to migrate with minimal code changes.

KEY MAPPINGS:
  - Session → session://<session_id>
  - DatasetMemory → dataset://<file_path>
  - AnalysisMemory → analysis://<skill>/<memory_id>
  - PreferenceMemory → preference://<domain>/<key>
  - InsightMemory → insight://<entity_type>/<entity_id>
  - ProjectContextMemory → project://<session_id>

PRESERVED FEATURES:
  - Deduplication (graph paths are unique by design)
  - TTL cleanup (via deprecated memory GC)
  - Session context loading (formatted for LLM injection)
"""

import base64
import json
import logging
import uuid
import os
from datetime import datetime, timezone
from typing import Any, Optional

from .memory_client import MemoryClient

logger = logging.getLogger(__name__)


def _decode_legacy_content(content: str) -> str:
    """Decode content that was base64-encoded by the old encryption system.

    The old CompatMemoryStore._encrypt() wrapped memory content in base64.
    This function transparently decodes such content so that the rest of
    the system sees plain-text JSON.  Content that is already plain text
    (starts with '{', '[', or looks like normal text) is returned as-is.
    """
    if not content:
        return content
    stripped = content.strip()
    # Already plain JSON or readable text — skip
    if stripped.startswith(("{", "[", "http", "#", "Memory ", "User ")):
        return content
    # Try base64 decode
    try:
        padded = stripped
        pad_needed = len(padded) % 4
        if pad_needed:
            padded += "=" * (4 - pad_needed)
        raw = base64.b64decode(padded, validate=True)
        decoded = raw.decode("utf-8")
        # Sanity check: decoded result should be mostly printable
        printable = sum(1 for c in decoded if c.isprintable() or c in "\n\r\t")
        if printable / max(len(decoded), 1) > 0.85:
            logger.info("Decoded legacy base64 content (%d chars -> %d chars)", len(content), len(decoded))
            return decoded
    except Exception:
        pass
    return content


def _utcnow():
    return datetime.now(timezone.utc)


# =============================================================================
# Legacy Pydantic models (re-exported for backward compatibility)
# =============================================================================

from pydantic import BaseModel, Field, field_validator
from typing import Literal


class Session(BaseModel):
    """User session across bot restarts."""
    session_id: str
    user_id: str
    platform: Literal["telegram", "feishu", "cli", "tui", "app"]
    created_at: datetime = Field(default_factory=_utcnow)
    last_activity: datetime = Field(default_factory=_utcnow)
    preferences: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class BaseMemory(BaseModel):
    """Base class for all memory types."""
    memory_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    memory_type: str
    created_at: datetime = Field(default_factory=_utcnow)


class DatasetMemory(BaseMemory):
    """Physical dataset metadata."""
    memory_type: Literal["dataset"] = "dataset"
    file_path: str
    platform: str | None = None
    n_obs: int | None = None
    n_vars: int | None = None
    preprocessing_state: Literal["raw", "qc", "normalized", "clustered"] = "raw"
    file_exists: bool = True

    @field_validator("file_path")
    @classmethod
    def validate_relative_path(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        return v


class AnalysisMemory(BaseMemory):
    """Analysis execution record with lineage."""
    memory_type: Literal["analysis"] = "analysis"
    source_dataset_id: str
    parent_analysis_id: str | None = None
    skill: str
    method: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_path: str | None = None
    status: Literal["completed", "failed", "interrupted"] = "completed"
    executed_at: datetime = Field(default_factory=_utcnow)
    duration_seconds: float = 0.0


class PreferenceMemory(BaseMemory):
    """User preferences and habits."""
    memory_type: Literal["preference"] = "preference"
    domain: str
    key: str
    value: Any
    is_strict: bool = False
    updated_at: datetime = Field(default_factory=_utcnow)


class InsightMemory(BaseMemory):
    """Biological interpretations."""
    memory_type: Literal["insight"] = "insight"
    source_analysis_id: str
    entity_type: str
    entity_id: str
    biological_label: str
    evidence: str = ""
    confidence: Literal["user_confirmed", "ai_predicted"] = "ai_predicted"


class ProjectContextMemory(BaseMemory):
    """Global scientific context."""
    memory_type: Literal["project_context"] = "project_context"
    project_goal: str = ""
    species: str | None = None
    tissue_type: str | None = None
    disease_model: str | None = None


# =============================================================================
# Type → URI domain mapping
# =============================================================================

_TYPE_TO_DOMAIN = {
    "dataset": "dataset",
    "analysis": "analysis",
    "preference": "preference",
    "insight": "insight",
    "project_context": "project",
}

_DOMAIN_TO_TYPE = {v: k for k, v in _TYPE_TO_DOMAIN.items()}

_TYPE_CLASSES = {
    "dataset": DatasetMemory,
    "analysis": AnalysisMemory,
    "preference": PreferenceMemory,
    "insight": InsightMemory,
    "project_context": ProjectContextMemory,
}


def _memory_to_uri_path(memory: BaseMemory) -> str:
    """Convert a memory object to a URI path within its domain."""
    if isinstance(memory, DatasetMemory):
        return memory.file_path.replace("/", "_")
    elif isinstance(memory, AnalysisMemory):
        return f"{memory.skill}/{memory.memory_id}"
    elif isinstance(memory, PreferenceMemory):
        return f"{memory.domain}/{memory.key}"
    elif isinstance(memory, InsightMemory):
        return f"{memory.entity_type}/{memory.entity_id}"
    elif isinstance(memory, ProjectContextMemory):
        return memory.memory_id
    return memory.memory_id


def _memory_to_content(memory: BaseMemory) -> str:
    """Serialize a memory to JSON content for graph storage."""
    return memory.model_dump_json()


def _content_to_memory(content: str, memory_type: str) -> Optional[BaseMemory]:
    """Deserialize graph memory content to a Pydantic model."""
    cls = _TYPE_CLASSES.get(memory_type)
    if not cls:
        return None
    try:
        return cls.model_validate_json(content)
    except Exception:
        return None


# =============================================================================
# CompatMemoryStore — implements the old MemoryStore interface
# =============================================================================


class CompatMemoryStore:
    """Drop-in replacement for bot.memory.store.MemoryStore.

    Maps flat memory operations to graph memory URIs.
    Preserves: deduplication, session management, search.
    """

    def __init__(self, database_url: Optional[str] = None):
        self._client = MemoryClient(database_url)

    async def initialize(self) -> None:
        """Initialize storage backend."""
        await self._client.initialize()

    async def close(self) -> None:
        """Close backend resources."""
        await self._client.close()

    async def create_session(self, user_id: str, platform: str, chat_id: str = "", session_id: str = None) -> Session:
        """Create a new session in the graph memory."""
        session_id = session_id or uuid.uuid4().hex[:16]
        session = Session(
            session_id=session_id,
            user_id=user_id,
            platform=platform,
        )

        await self._client.remember(
            uri=f"session://{session_id}",
            content=session.model_dump_json(),
            disclosure=f"Session for user {user_id} on {platform}",
        )

        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve session by ID."""
        mem = await self._client.recall(f"session://{session_id}")
        if not mem or not mem.get("content"):
            return None
        content = mem["content"]
        # Auto-decode legacy base64 content from old encryption system
        decoded = _decode_legacy_content(content)
        if decoded != content:
            # Fix in database so this decoding only happens once
            logger.info("Auto-fixing legacy encoded session: %s", session_id)
            await self._client.remember(
                uri=f"session://{session_id}",
                content=decoded,
            )
            content = decoded
        try:
            return Session.model_validate_json(content)
        except Exception as e:
            logger.warning("Failed to parse session %s: %s", session_id, e)
            return None

    async def update_session(self, session_id: str, updates: dict) -> None:
        """Update session fields."""
        session = await self.get_session(session_id)
        if not session:
            return

        data = session.model_dump()
        data.update(updates)
        data["last_activity"] = _utcnow().isoformat()

        updated = Session.model_validate(data)
        await self._client.remember(
            uri=f"session://{session_id}",
            content=updated.model_dump_json(),
        )

    async def save_memory(self, session_id: str, memory: BaseMemory) -> str:
        """Save a memory, return memory_id."""
        domain = _TYPE_TO_DOMAIN.get(memory.memory_type, "core")
        path = _memory_to_uri_path(memory)
        content = _memory_to_content(memory)

        await self._client.remember(
            uri=f"{domain}://{path}",
            content=content,
            disclosure=f"Memory from session {session_id}",
        )

        # Sync preference to the session object for frontend visibility
        if memory.memory_type == "preference" and hasattr(memory, "key") and hasattr(memory, "value"):
            session = await self.get_session(session_id)
            if session:
                updates = session.preferences.copy()
                updates[memory.key] = memory.value
                await self.update_session(session_id, {"preferences": updates})

        return memory.memory_id

    async def get_memories(
        self, session_id: str, memory_type: Optional[str] = None, limit: int = 100
    ) -> list[BaseMemory]:
        """Retrieve memories, optionally filtered by type."""
        if memory_type:
            domain = _TYPE_TO_DOMAIN.get(memory_type)
            if not domain:
                return []
        else:
            domain = None

        results: list[BaseMemory] = []

        async def _collect(uri: str, mtype: str):
            """Recursively collect leaf memories from a domain tree."""
            if len(results) >= limit:
                return
            children = await self._client.list_children(uri)
            for child in children:
                if len(results) >= limit:
                    return
                child_uri = f"{child['domain']}://{child['path']}"
                mem = await self._client.recall(child_uri)
                if mem and mem.get("content"):
                    content = _decode_legacy_content(mem["content"])
                    if content != mem["content"]:
                        await self._client.remember(uri=child_uri, content=content)
                    obj = _content_to_memory(content, mtype)
                    if obj:
                        results.append(obj)
                    else:
                        # Not a valid leaf — recurse into this container node
                        await _collect(child_uri, mtype)

        if domain:
            await _collect(f"{domain}://", memory_type or "")
        else:
            for mtype, dom in _TYPE_TO_DOMAIN.items():
                await _collect(f"{dom}://", mtype)
                if len(results) >= limit:
                    break

        return results[:limit]

    async def update_memory(self, memory_id: str, updates: dict) -> None:
        """Update memory fields — search and update in place."""
        # Search for the memory by ID substring
        results = await self._client.search(memory_id, limit=5)
        for r in results:
            mem = await self._client.recall(r["uri"])
            if mem and mem.get("content"):
                content = mem["content"]
                try:
                    data = json.loads(content)
                    if data.get("memory_id") == memory_id:
                        data.update(updates)
                        new_content = json.dumps(data)
                        await self._client.remember(
                            uri=r["uri"],
                            content=new_content,
                        )
                        return
                except json.JSONDecodeError:
                    continue

    async def delete_session(self, session_id: str) -> None:
        """Delete session."""
        try:
            await self._client.forget(f"session://{session_id}")
        except ValueError:
            pass

    async def search_memories(
        self, session_id: str, query: str, memory_type: Optional[str] = None
    ) -> list[BaseMemory]:
        """Search memories by content."""
        domain = _TYPE_TO_DOMAIN.get(memory_type) if memory_type else None
        results = await self._client.search(query, limit=20, domain=domain)

        memories = []
        for r in results:
            mem = await self._client.recall(r["uri"])
            if mem and mem.get("content"):
                content = mem["content"]
                # Try to detect memory type from the domain
                rd = r.get("domain", "")
                mt = _DOMAIN_TO_TYPE.get(rd, memory_type or "")
                obj = _content_to_memory(content, mt)
                if obj:
                    memories.append(obj)

        return memories

    async def cleanup_expired(self, ttl_days: Optional[int] = None) -> int:
        """Remove expired sessions/memories. Returns count deleted."""
        # The graph memory system uses deprecation instead of TTL
        # Expired memories are cleaned via the maintenance API
        return 0

    # ------------------------------------------------------------------
    # Load context (for LLM prompt injection)
    # ------------------------------------------------------------------

    async def load_context(self, session_id: str) -> str:
        """Load all memories for a session, formatted for LLM context."""
        parts = []

        for memory_type, domain in _TYPE_TO_DOMAIN.items():
            memories = await self.get_memories(session_id, memory_type, limit=20)
            if not memories:
                continue

            section_name = memory_type.replace("_", " ").title()
            items = []
            for m in memories:
                items.append(f"  - {m.model_dump_json()}")

            if items:
                parts.append(f"## {section_name}\n" + "\n".join(items))

        return "\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
