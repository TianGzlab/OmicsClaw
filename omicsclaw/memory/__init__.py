"""Session persistence and long-term recall.

Two things live here. :class:`SqliteSessionStore` keeps conversations
between exchanges and satisfies the entry layer's ``SessionStore``
protocol structurally, so it is passed in rather than imported::

    from omicsclaw.entry import attach_sessions, build_app, resolve_app_config
    from omicsclaw.memory import Database, SqliteSessionStore

    db = Database("~/.omicsclaw/memory.db")
    app = attach_sessions(build_app(resolve_app_config(argv, env)),
                          store=SqliteSessionStore(db))

:class:`LongTermStore` keeps what is worth remembering across sessions,
deduplicated by content fingerprint and searchable through SQLite's FTS5;
:class:`Precis` renders its most valuable entries into a bounded Markdown
file for a prompt section to pick up.

:class:`MemoryExtractor` is what fills that store without anyone typing
into it. Run just before compaction, it reads the messages about to be
summarized away and writes down what stays true afterwards::

    extractor = MemoryExtractor(summarizer, LongTermStore(db))
    result = await extractor.extract(history_about_to_be_compacted)

It takes the same :class:`~omicsclaw.context.Summarizer` the compaction
layer summarizes through, so no model client is imported here, and it
never raises: a failed extraction costs a fact, while a raised one would
cost the turn being compacted.

Compaction leaves two kinds of file behind, and both are kept here.
:class:`FileOffloadStore` holds the tool results a compaction moved out of
the conversation — it satisfies :class:`omicsclaw.context.OffloadStore` —
and :class:`JsonlCompactionLog` appends one record per compaction.

Nothing here imports :mod:`omicsclaw.entry` — the dependency arrow points
one way, and the protocol is what keeps it pointing that way.
"""

from .compaction_log import JsonlCompactionLog, LoggedCompaction, record_from_dict
from .database import SCHEMA, Database
from .extractor import (
    EXTRACTION_SYSTEM_PROMPT,
    ExtractionResult,
    MemoryExtractor,
    parse_facts,
    render_conversation,
)
from .longterm import Category, MemoryEntry, normalize, signature
from .offload import FileOffloadStore, safe_name
from .precis import (
    PRECIS_MAX_BYTES,
    PRECIS_MAX_ENTRIES,
    Precis,
    render,
    truncate_utf8,
)
from .record import StoredSession
from .sessions import SqliteSessionStore
from .store import STALE_AFTER_DAYS, STALE_MAX_IMPORTANCE, LongTermStore

__all__ = [
    "EXTRACTION_SYSTEM_PROMPT",
    "PRECIS_MAX_BYTES",
    "PRECIS_MAX_ENTRIES",
    "SCHEMA",
    "STALE_AFTER_DAYS",
    "STALE_MAX_IMPORTANCE",
    "Category",
    "Database",
    "ExtractionResult",
    "FileOffloadStore",
    "JsonlCompactionLog",
    "LoggedCompaction",
    "LongTermStore",
    "MemoryEntry",
    "MemoryExtractor",
    "Precis",
    "SqliteSessionStore",
    "StoredSession",
    "normalize",
    "parse_facts",
    "record_from_dict",
    "render",
    "render_conversation",
    "safe_name",
    "signature",
    "truncate_utf8",
]
