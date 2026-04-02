"""
OmicsClaw Memory — Unified graph-based memory system.

Replaces the former bot/memory/ flat store with a nocturne_memory-derived
graph engine. Provides:

  - GraphService  — core CRUD + graph traversal
  - SearchIndexer — FTS search across memories
  - GlossaryService — keyword-to-node bindings
  - ChangesetStore — row-level before/after snapshots for review/rollback
  - MemoryClient — high-level API for multi-agent pipelines
  - CompatMemoryStore — drop-in replacement for old bot.memory.MemoryStore

Usage (lazy init):

    from omicsclaw.memory import get_graph_service, get_db_manager

    db = get_db_manager()
    await db.init_db()

    graph = get_graph_service()
    result = await graph.create_memory("", "Hello", priority=0, title="greeting", domain="core")
"""

import os
from typing import Optional, TYPE_CHECKING

from .database import DatabaseManager
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
from .models import (
    Base, ROOT_NODE_UUID, Node, Memory, Edge, Path,
    GlossaryKeyword, SearchDocument, ChangeCollector,
)

if TYPE_CHECKING:
    from .graph import GraphService
    from .search import SearchIndexer
    from .glossary import GlossaryService

_db_manager: Optional[DatabaseManager] = None
_graph_service: Optional["GraphService"] = None
_search_indexer: Optional["SearchIndexer"] = None
_glossary_service: Optional["GlossaryService"] = None


def _ensure_initialized():
    global _db_manager, _graph_service, _search_indexer, _glossary_service
    if _db_manager is not None:
        return

    from .search import SearchIndexer
    from .glossary import GlossaryService
    from .graph import GraphService

    database_url = os.getenv("OMICSCLAW_MEMORY_DB_URL")
    # database_url can be None — DatabaseManager will use defaults

    _db_manager = DatabaseManager(database_url)
    _search_indexer = SearchIndexer(_db_manager)
    _glossary_service = GlossaryService(_db_manager, _search_indexer)
    _graph_service = GraphService(_db_manager, _search_indexer)


def get_db_manager() -> DatabaseManager:
    _ensure_initialized()
    return _db_manager  # type: ignore[return-value]


def get_graph_service() -> "GraphService":
    _ensure_initialized()
    return _graph_service  # type: ignore[return-value]


def get_search_indexer() -> "SearchIndexer":
    _ensure_initialized()
    return _search_indexer  # type: ignore[return-value]


def get_glossary_service() -> "GlossaryService":
    _ensure_initialized()
    return _glossary_service  # type: ignore[return-value]


async def close_db():
    """Tear down all services and close the database connection."""
    global _db_manager, _graph_service, _search_indexer, _glossary_service
    if _db_manager:
        await _db_manager.close()
    _db_manager = None
    _graph_service = None
    _search_indexer = None
    _glossary_service = None


__all__ = [
    "DatabaseManager",
    "get_db_manager", "get_graph_service",
    "get_search_indexer", "get_glossary_service",
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
