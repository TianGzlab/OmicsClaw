"""
OmicsClaw Memory — Unified graph-based memory system.

Three layers over a SQLite/PostgreSQL graph database (SQLAlchemy):

  - MemoryEngine — namespace-aware hot path (upsert, recall, search,
    list_children, get_subtree, get_recent, delete).
  - ReviewLog — cold-path operations (version-chain inspection,
    rollback, orphans, GC, browse_shared, changeset approve/discard).
  - MemoryClient — strategy layer (which namespace, versioned vs.
    overwrite). Production callers build a client per surface.

Plus:

  - SearchIndexer — FTS search across memories.
  - GlossaryService — keyword-to-node bindings.
  - ChangesetStore — row-level before/after snapshots for review.
  - CompatMemoryStore — drop-in replacement for the legacy bot store.

Usage (lazy init):

    from omicsclaw.memory import (
        get_db_manager, get_memory_engine, get_memory_client,
    )

    db = get_db_manager()
    await db.init_db()

    engine = get_memory_engine()
    client = get_memory_client(namespace="tg/userA")
    await client.remember("dataset://pbmc.h5ad", "scRNA dataset")

Legacy admin path operations (used only by the `oc memory-server`
``/api/browse/*`` UI) live in ``omicsclaw/memory/api/_browse_helpers.py``.
Production code MUST NOT import that module.
"""

from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING

from .scoped_memory import (
    DEFAULT_SCOPED_MEMORY_SCOPE,
    SCOPED_MEMORY_DIRNAME,
    SCOPED_MEMORY_FRESHNESS_LEVELS,
    SCOPED_MEMORY_SCOPES,
    ScopedMemoryPruneCandidate,
    ScopedMemoryPruneResult,
    ScopedMemoryRecord,
    ensure_scoped_memory_root,
    normalize_scoped_memory_freshness,
    normalize_scoped_memory_scope,
    prune_scoped_memories,
    resolve_scoped_memory_root,
    write_scoped_memory,
)
from .scoped_memory_index import (
    ScopedMemoryHeader,
    list_scoped_memory_records,
    load_scoped_memory_record,
    scan_scoped_memory_headers,
)
from .scoped_memory_select import ScopedMemoryRecall, load_scoped_memory_context
from .snapshot import ChangesetStore, get_changeset_store

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .engine import MemoryEngine
    from .memory_client import MemoryClient
    from .review_log import ReviewLog
    from .search import SearchIndexer
    from .glossary import GlossaryService

_db_manager: Optional["DatabaseManager"] = None
_search_indexer: Optional["SearchIndexer"] = None
_glossary_service: Optional["GlossaryService"] = None
_memory_engine: Optional["MemoryEngine"] = None
_review_log: Optional["ReviewLog"] = None


def _ensure_initialized():
    global _db_manager, _search_indexer, _glossary_service
    global _memory_engine, _review_log
    if _db_manager is not None:
        return

    from .database import DatabaseManager
    from .engine import MemoryEngine
    from .review_log import ReviewLog
    from .search import SearchIndexer
    from .glossary import GlossaryService

    database_url = os.getenv("OMICSCLAW_MEMORY_DB_URL")
    # database_url can be None — DatabaseManager will use defaults

    _db_manager = DatabaseManager(database_url)
    _search_indexer = SearchIndexer(_db_manager)
    _glossary_service = GlossaryService(_db_manager, _search_indexer)
    _memory_engine = MemoryEngine(_db_manager, _search_indexer)
    _review_log = ReviewLog(_db_manager, _memory_engine)


def get_db_manager() -> DatabaseManager:
    _ensure_initialized()
    return _db_manager  # type: ignore[return-value]


def get_search_indexer() -> "SearchIndexer":
    _ensure_initialized()
    return _search_indexer  # type: ignore[return-value]


def get_glossary_service() -> "GlossaryService":
    _ensure_initialized()
    return _glossary_service  # type: ignore[return-value]


def get_memory_engine() -> "MemoryEngine":
    """Return the singleton MemoryEngine bound to the configured database."""
    _ensure_initialized()
    return _memory_engine  # type: ignore[return-value]


def get_engine_db() -> "DatabaseManager":
    """Sugar for ``get_memory_engine().db`` — used by surfaces that need
    to call ``init_db`` before opening any session."""
    return get_memory_engine().db


def get_review_log() -> "ReviewLog":
    """Return the singleton ReviewLog (cold-path operations)."""
    _ensure_initialized()
    return _review_log  # type: ignore[return-value]


def get_memory_client(*, namespace: str) -> "MemoryClient":
    """Return a MemoryClient bound to ``namespace`` and the singleton engine.

    This is the canonical way for a surface (CLI, Desktop, Bot) to obtain
    a namespaced client. The underlying engine is shared so per-call
    construction is cheap.
    """
    from .memory_client import MemoryClient

    return MemoryClient(engine=get_memory_engine(), namespace=namespace)


# ----------------------------------------------------------------------
# Surface namespace derivation helpers
# ----------------------------------------------------------------------


def cli_namespace_from_workspace(workspace_dir: Optional[str]) -> str:
    """Derive a CLI/TUI namespace from a workspace directory.

    Resolves to an absolute path so two terminals running in the same
    directory share a namespace, and two different directories don't.
    A relative path resolves against the current working directory.
    ``None`` means "use cwd" — the natural default for ``oc interactive``
    invoked without ``--workspace``.
    """
    # Local import — module-level ``from pathlib import Path`` would
    # shadow the lazy ``omicsclaw.memory.Path`` ORM export below.
    from pathlib import Path as _PathlibPath

    if workspace_dir is None or workspace_dir == "":
        target = _PathlibPath.cwd()
    else:
        target = _PathlibPath(workspace_dir)
    return str(target.resolve())


_DESKTOP_DEFAULT_USER_ID = "desktop_user"


def desktop_chat_user_id() -> str:
    """User-id portion of the Desktop chat agent loop's CompatMemoryStore session.

    The chat path constructs its namespace as ``f"app/{user_id}"`` (see
    ``CompatMemoryStore._client_for_session``). Returning the same id
    component ``desktop_namespace()`` derives keeps the chat-write and
    endpoint-read namespaces aligned, including under
    ``OMICSCLAW_DESKTOP_LAUNCH_ID`` multi-launch deployments where
    they would otherwise diverge.
    """
    launch_id = (os.getenv("OMICSCLAW_DESKTOP_LAUNCH_ID") or "").strip()
    return launch_id or _DESKTOP_DEFAULT_USER_ID


def desktop_namespace() -> str:
    """Derive the Desktop FastAPI namespace.

    Reads ``OMICSCLAW_DESKTOP_LAUNCH_ID`` if set (multi-user desktop or
    sandboxed launch), otherwise the single-user default. The launch id
    is prefixed with ``app/`` so cross-surface collisions with bot
    namespaces (``telegram/...``, ``feishu/...``) are impossible.
    """
    return f"app/{desktop_chat_user_id()}"


def __getattr__(name: str):
    if name == "DatabaseManager":
        from .database import DatabaseManager

        return DatabaseManager

    model_exports = {
        "Base",
        "ROOT_NODE_UUID",
        "Node",
        "Memory",
        "Edge",
        "Path",
        "GlossaryKeyword",
        "SearchDocument",
        "ChangeCollector",
    }
    if name in model_exports:
        from . import models

        return getattr(models, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def close_db():
    """Tear down all services and close the database connection."""
    global _db_manager, _search_indexer, _glossary_service
    global _memory_engine, _review_log
    if _db_manager:
        await _db_manager.close()
    _db_manager = None
    _search_indexer = None
    _glossary_service = None
    _memory_engine = None
    _review_log = None


__all__ = [
    "DatabaseManager",
    "get_db_manager",
    "get_search_indexer", "get_glossary_service",
    "get_memory_engine", "get_review_log", "get_memory_client",
    "get_engine_db",
    "cli_namespace_from_workspace", "desktop_namespace",
    "desktop_chat_user_id",
    "close_db",
    "ChangesetStore", "get_changeset_store",
    "Base", "ROOT_NODE_UUID", "Node", "Memory", "Edge", "Path",
    "GlossaryKeyword", "SearchDocument", "ChangeCollector",
    "DEFAULT_SCOPED_MEMORY_SCOPE",
    "SCOPED_MEMORY_DIRNAME",
    "SCOPED_MEMORY_FRESHNESS_LEVELS",
    "SCOPED_MEMORY_SCOPES",
    "ScopedMemoryHeader",
    "ScopedMemoryPruneCandidate",
    "ScopedMemoryPruneResult",
    "ScopedMemoryRecall",
    "ScopedMemoryRecord",
    "ensure_scoped_memory_root",
    "list_scoped_memory_records",
    "load_scoped_memory_context",
    "load_scoped_memory_record",
    "normalize_scoped_memory_freshness",
    "normalize_scoped_memory_scope",
    "prune_scoped_memories",
    "resolve_scoped_memory_root",
    "scan_scoped_memory_headers",
    "write_scoped_memory",
]
