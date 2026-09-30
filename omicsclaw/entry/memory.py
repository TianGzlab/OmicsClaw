"""Long-term memory, bound to one deployment.

:func:`open_memory` opens the SQLite file under ``<workspace>/.omicsclaw/``
and builds the three objects the rest of this layer composes: the store,
the ``MEMORY.md`` précis rendered from it, and the extractor that fills
it. :func:`memory_section`, :func:`memory_tools`,
:func:`build_memory_extractor` and :func:`session_store` are the four
seams those objects reach the running agent through.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from omicsclaw.context import Section, Summarizer
from omicsclaw.memory import (
    Category,
    Database,
    ExtractionResult,
    LongTermStore,
    MemoryEntry,
    MemoryExtractor,
    Precis,
    SqliteSessionStore,
    truncate_utf8,
)
from omicsclaw.schema import Message
from omicsclaw.tools import (
    ApprovalMode,
    FunctionTool,
    RiskLevel,
    Tool,
    ToolArgumentError,
    ToolPolicy,
)

from .config import AppConfig

__all__ = [
    "CONTENT_TRUNCATED_KEY",
    "MAX_SEARCH_LIMIT",
    "MEMORY_DB_FILENAME",
    "MEMORY_SEARCH_SCHEMA",
    "MEMORY_SEARCH_TOOL_NAME",
    "MEMORY_SECTION_HEADING",
    "MEMORY_SECTION_KEY",
    "MEMORY_WRITE_SCHEMA",
    "MEMORY_WRITE_TOOL_NAME",
    "PRECIS_FILENAME",
    "SEARCH_RESULT_MAX_BYTES",
    "MemoryBinding",
    "PrecisRefreshingExtractor",
    "build_memory_extractor",
    "memory_db_path",
    "memory_search_tool",
    "memory_section",
    "memory_tools",
    "memory_write_tool",
    "open_memory",
    "precis_path",
    "prepare_memory",
    "session_store",
]

_log = logging.getLogger(__name__)

MEMORY_DB_FILENAME = "memory.db"
"""Database holding the conversations and the long-term entries."""

PRECIS_FILENAME = "MEMORY.md"
"""Rendered view of the top entries, read by the prompt's memory section."""

MEMORY_SECTION_KEY = "memory"
MEMORY_SECTION_HEADING = "## Long-term memory"

MEMORY_SEARCH_TOOL_NAME = "memory_search"
MEMORY_WRITE_TOOL_NAME = "memory_write"

DEFAULT_SEARCH_LIMIT = 5
"""Entries ``memory_search`` returns when the model names no limit."""

MAX_SEARCH_LIMIT = 20
"""Greatest number of entries one ``memory_search`` call may return."""

SEARCH_RESULT_MAX_BYTES = 4096
"""Greatest size of one ``memory_search`` answer in UTF-8 bytes."""

CONTENT_TRUNCATED_KEY = "content_truncated"
"""Set on a search hit whose body was shortened to fit the answer.

Present only when something was cut, so its absence is the statement
that the body is whole. Without it a shortened memory and a short one
read the same, and the model has no reason to go and read the rest.
"""

_CATEGORIES = tuple(category.value for category in Category)


def memory_db_path(config: AppConfig) -> Path:
    """The SQLite file this deployment's memory is kept in.

    :param config: Deployment to answer for.
    :returns: ``<workspace>/.omicsclaw/memory.db``.
    """
    return config.state_dir() / MEMORY_DB_FILENAME


def precis_path(config: AppConfig) -> Path:
    """The Markdown file the prompt's memory section is read from.

    :param config: Deployment to answer for.
    :returns: ``<workspace>/.omicsclaw/MEMORY.md``.
    """
    return config.state_dir() / PRECIS_FILENAME


@dataclass(frozen=True, slots=True)
class MemoryBinding:
    """One open memory database and the two views built over it."""

    database: Database
    """The connection everything here reads and writes through."""

    store: LongTermStore
    """The long-term entries, deduplicated and searchable."""

    precis: Precis
    """The bounded Markdown file the memory prompt section reads."""

    def close(self) -> None:
        """Close the database. Calling this twice is harmless."""
        self.database.close()


def open_memory(config: AppConfig) -> MemoryBinding | None:
    """Open this deployment's memory, or answer ``None`` when it is off.

    Creates ``<workspace>/.omicsclaw/`` when it is missing. The caller
    owns the result and is responsible for :meth:`MemoryBinding.close`.

    :param config: Deployment to open memory for.
    :returns: The binding, or ``None`` when :attr:`AppConfig.memory` is
        false.
    """
    if not config.memory:
        return None
    database = Database(memory_db_path(config))
    store = LongTermStore(database)
    return MemoryBinding(database, store, Precis(store, precis_path(config)))


async def prepare_memory(binding: MemoryBinding | None) -> int:
    """Delete expired entries and rewrite the précis from what survives.

    Neither step may stop a deployment starting, so a failure in either
    is logged and swallowed.

    :param binding: Memory to maintain; ``None`` does nothing.
    :returns: How many expired entries were deleted.
    """
    if binding is None:
        return 0
    purged = 0
    try:
        purged = await binding.store.purge_expired()
        await binding.precis.regenerate()
    except Exception as error:  # noqa: BLE001 - start-up must not fail here
        _log.warning("memory maintenance failed: %s", error)
        return purged
    _log.info(
        "memory ready: %d expired entry(s) purged, précis at %s",
        purged,
        binding.precis.path,
    )
    return purged


def memory_section(binding: MemoryBinding) -> Section:
    """The prompt block carrying the précis, re-read on every render.

    The body is a closure rather than a snapshot because ``memory_write``
    rewrites the file while the agent runs; a snapshot would show the
    agent the version from before the one it just wrote.

    :param binding: Memory whose précis the section renders.
    :returns: A section that is empty, and therefore absent from the
        prompt, until something has been remembered.
    """
    precis = binding.precis

    def read() -> str:
        return precis.read()

    return Section(MEMORY_SECTION_KEY, MEMORY_SECTION_HEADING, read)


@dataclass(frozen=True, slots=True)
class PrecisRefreshingExtractor:
    """An extractor that rewrites the précis after it stores anything.

    :param extractor: Does the reading and the storing.
    :param precis: Rewritten whenever the extraction stored an entry.
    """

    extractor: MemoryExtractor
    precis: Precis

    async def extract(self, messages: Sequence[Message]) -> ExtractionResult:
        """Store what *messages* leave behind, then rewrite the précis.

        Never raises: the underlying extractor absorbs its own failures,
        and a précis that cannot be written is logged instead.

        :param messages: Conversation about to be summarized away.
        :returns: What the underlying extractor stored.
        """
        result = await self.extractor.extract(messages)
        if result.failure:
            _log.warning("memory extraction failed: %s", result.failure)
        if result.rejected:
            _log.info("%d extracted fact(s) were unusable", result.rejected)
        if not result.stored:
            return result
        _log.info("remembered %d entry(s) from a compaction", len(result.stored))
        try:
            await self.precis.regenerate()
        except Exception as error:  # noqa: BLE001 - a lost précis is not a lost turn
            _log.warning("could not rewrite the memory précis: %s", error)
        return result


def build_memory_extractor(
    binding: MemoryBinding | None,
    summarizer: Summarizer | None,
) -> PrecisRefreshingExtractor | None:
    """The extractor a compaction hands the messages it is about to drop.

    :param binding: Where extracted entries are stored.
    :param summarizer: Model access the extraction prompt runs through.
    :returns: An extractor, or ``None`` when either input is missing —
        extraction needs a model and somewhere to put the answer.
    """
    if binding is None or summarizer is None:
        return None
    return PrecisRefreshingExtractor(
        MemoryExtractor(summarizer, binding.store), binding.precis
    )


def session_store(binding: MemoryBinding | None) -> SqliteSessionStore | None:
    """The store conversations survive a restart in.

    Built over the same database as the memories, so a deployment keeps
    one file rather than two.

    :param binding: Open memory; ``None`` yields ``None``.
    :returns: A store satisfying the entry layer's ``SessionStore``, or
        ``None``.
    """
    if binding is None:
        return None
    return SqliteSessionStore(binding.database)


_WRITE_DESCRIPTION = (
    "Keep something across sessions. `action=add` writes down one thing "
    "that stays true after this conversation ends: a stated preference, a "
    "stable fact about the project or the data, a settled decision, a "
    "reusable procedure. `action=update` corrects an entry you already "
    "hold, and `action=remove` drops one that stopped being true — both "
    "take the `id` a search or an earlier write gave you.\n"
    "The highest-rated entries (see `importance`) are shown to you at the "
    "start of every later session and memory_search finds the rest, so "
    "keep one-off detail out of memory: paths for a single run, "
    "intermediate numbers, what you are about to do next. Adding content "
    "you have already stored updates that entry rather than making a "
    "second copy of it."
)

MEMORY_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["add", "update", "remove"],
            "description": (
                "What to do. `add` needs `content`; the other two need `id`."
            ),
        },
        "id": {
            "type": "string",
            "description": (
                "The entry to change, as `memory_search` or an earlier "
                "write reported it. Required for update and remove."
            ),
        },
        "content": {
            "type": "string",
            "description": (
                "The memory itself. Write it so that it still makes sense "
                "months from now, without this conversation to explain it."
            ),
        },
        "title": {
            "type": "string",
            "description": (
                "Short label shown in the long-term memory section of the "
                "system prompt. Defaults to the start of `content`."
            ),
        },
        "category": {
            "type": "string",
            "enum": list(_CATEGORIES),
            "description": "What kind of thing this records.",
        },
        "importance": {
            "type": "integer",
            "description": (
                "How much this is worth keeping, 0 to 10. Only the "
                "highest-rated entries reach the system prompt."
            ),
        },
        "ttl_days": {
            "type": "integer",
            "description": (
                "Days before the entry expires and is deleted. 0, the "
                "default, never expires."
            ),
        },
    },
    "required": ["action"],
    "additionalProperties": False,
}

_SEARCH_DESCRIPTION = (
    "Look through what you remembered in earlier sessions. The system "
    "prompt carries only the highest-rated entries, so search before "
    "asking the user something they may already have told you, and "
    "before assuming a project convention."
)

MEMORY_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Words to look for. Titles and bodies are both searched "
                "and any word may match, so a short phrase works better "
                "than a sentence."
            ),
        },
        "limit": {
            "type": "integer",
            "description": (
                f"Greatest number of entries to return, up to "
                f"{MAX_SEARCH_LIMIT}. Defaults to {DEFAULT_SEARCH_LIMIT}."
            ),
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}

_WRITE_POLICY = ToolPolicy(
    risk_level=RiskLevel.LOW,
    approval_mode=ApprovalMode.AUTO,
    read_only=False,
    concurrency_safe=False,
    writes_workspace=True,
    allowed_in_background=True,
    tags=frozenset({"memory"}),
)
"""Declared rather than defaulted, and each field for its own reason.

``LOW`` / ``AUTO``: the blast radius is the agent's own notes under
``<workspace>/.omicsclaw/``. The default ``HIGH`` / ``ASK`` would put a
human prompt in front of every memory the agent tries to keep, which
would not make the deployment safer — it would make the agent stop
remembering.

``concurrency_safe=False`` makes the call a barrier. Two writes in one
turn would each rewrite the précis from a store the other was still
changing, and the file the next render reads is whichever finished last.
"""

_SEARCH_POLICY = ToolPolicy(
    risk_level=RiskLevel.LOW,
    approval_mode=ApprovalMode.AUTO,
    read_only=False,
    concurrency_safe=True,
    writes_workspace=True,
    allowed_in_background=True,
    tags=frozenset({"memory", "inspection"}),
)
"""``read_only=False`` for a search, which is not a slip.

A hit has its use count raised and its last-used time set, and that
counter is what keeps an entry from being proposed as stale. Claiming
``read_only=True`` here would be claiming an effect the tool does have.
The writes are counters inside the database, serialised by it, so the
call is still safe to run beside others.
"""


def memory_tools(binding: MemoryBinding) -> tuple[Tool, ...]:
    """``memory_search`` and ``memory_write``, both over *binding*.

    :param binding: Memory the two tools read and write.
    :returns: The pair, search first.
    """
    return (memory_search_tool(binding), memory_write_tool(binding))


def memory_search_tool(binding: MemoryBinding) -> FunctionTool:
    """Build the ``memory_search`` tool over *binding*.

    No ``policy`` parameter: a deployment that disagrees with the default
    passes its own to :meth:`~omicsclaw.tools.ToolRegistry.register`.

    :param binding: Memory to search.
    :returns: The tool, ready to mount.
    """

    async def run(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> str:
        return await _search(binding, query, limit)

    return FunctionTool(
        MEMORY_SEARCH_TOOL_NAME,
        _SEARCH_DESCRIPTION,
        run,
        parameters=MEMORY_SEARCH_SCHEMA,
        policy=_SEARCH_POLICY,
    )


def memory_write_tool(binding: MemoryBinding) -> FunctionTool:
    """Build the ``memory_write`` tool over *binding*.

    No ``policy`` parameter, for the reason
    :func:`memory_search_tool` gives.

    :param binding: Memory to write to.
    :returns: The tool, ready to mount.
    """

    async def run(
        action: str,
        id: str = "",  # noqa: A002 - the schema property the model is shown
        content: str = "",
        title: str = "",
        category: str = "",
        importance: int | None = None,
        ttl_days: int | None = None,
    ) -> str:
        return await _write(
            binding,
            action=action,
            entry_id=id,
            content=content,
            title=title,
            category=category,
            importance=importance,
            ttl_days=ttl_days,
        )

    return FunctionTool(
        MEMORY_WRITE_TOOL_NAME,
        _WRITE_DESCRIPTION,
        run,
        parameters=MEMORY_WRITE_SCHEMA,
        policy=_WRITE_POLICY,
    )


async def _search(binding: MemoryBinding, query: str, limit: int) -> str:
    """Answer one ``memory_search`` call as JSON.

    JSON rather than the précis's Markdown because every hit carries its
    ``id``, and the id is what ``memory_write``'s update and remove
    actions take — a rendering without it is a search the model cannot
    act on.

    :param binding: Memory to search.
    :param query: Free text to match against titles and bodies.
    :param limit: Requested number of entries; clamped to
        ``1..MAX_SEARCH_LIMIT``.
    :returns: A JSON array of the matching entries, cut down by
        :func:`_fit` until it fits :data:`SEARCH_RESULT_MAX_BYTES`.
        ``[]`` only when nothing matched, which is what an empty answer
        must look like to a model reading JSON.
    :raises ToolArgumentError: If *query* has no searchable text, which
        the model can correct from the message.
    """
    text = query.strip()
    if not text:
        raise ToolArgumentError(
            "input.query is empty; give the words to look for"
        )
    wanted = min(max(_as_int(limit, "limit"), 1), MAX_SEARCH_LIMIT)
    found = [_as_dict(entry) for entry in await binding.store.search(text, wanted)]
    return _dump(_fit(found))


def _fits(found: list[dict[str, object]]) -> bool:
    """Whether *found* renders inside :data:`SEARCH_RESULT_MAX_BYTES`."""
    return len(_dump(found).encode("utf-8")) <= SEARCH_RESULT_MAX_BYTES


def _fit(found: list[dict[str, object]]) -> list[dict[str, object]]:
    """*found*, cut down until its JSON fits the answer's byte bound.

    Whole entries go first and from the end, since the store ranks best
    match first and a JSON array cut to a byte count is not JSON — the
    model would read a parse failure as "the memory is broken" rather
    than "there was more".

    **The best match is never dropped.** When it alone does not fit, its
    body is shortened instead and :data:`CONTENT_TRUNCATED_KEY` is set on
    it. Dropping it would answer ``[]`` for a memory the store did find,
    which the model reads as "you were never told this" — and the hit's
    use count has already gone up, so the entry stops looking stale on
    the strength of a read that never reached anyone.

    :param found: Hits, best first; modified in place.
    :returns: The entries to answer with, possibly one of them shortened.
    """
    while len(found) > 1 and not _fits(found):
        found.pop()
    if not found or _fits(found):
        return found
    return [_shortened(found[0])]


def _shortened(entry: dict[str, object]) -> dict[str, object]:
    """*entry* with its text halved until a one-entry answer fits.

    Halved rather than computed: JSON escaping means the room a body has
    is not its own length, and two or three passes over a few kilobytes
    is cheaper than being clever about it. Title and body shrink
    together, so an entry made unanswerable by either one is still
    answerable — what has to survive is the ``id``, which is how the
    model reaches the entry again.

    :param entry: The hit to shorten.
    :returns: A copy carrying :data:`CONTENT_TRUNCATED_KEY`.
    """
    cut = {**entry, CONTENT_TRUNCATED_KEY: True}
    body, title = str(entry.get("content", "")), str(entry.get("title", ""))
    while not _fits([cut]) and (body or title):
        body = truncate_utf8(body, len(body.encode("utf-8")) // 2)
        title = truncate_utf8(title, len(title.encode("utf-8")) // 2)
        cut["content"], cut["title"] = body, title
    return cut


async def _write(
    binding: MemoryBinding,
    *,
    action: str,
    entry_id: str,
    content: str,
    title: str,
    category: str,
    importance: int | None,
    ttl_days: int | None,
) -> str:
    """Carry out one ``memory_write`` call and refresh the précis.

    The précis is rebuilt after any of the three actions succeeds, so the
    next render of the system prompt shows what the store now holds.

    :param binding: Memory to write to.
    :param action: ``add``, ``update`` or ``remove``. Which values are
        legal is enforced by the ``enum`` in :data:`MEMORY_WRITE_SCHEMA`
        and not re-checked here — the schema is validated before this
        runs, and a second guard that can only fire once the first is
        gone is a branch no test can reach.
    :param entry_id: Entry to change; required by update and remove.
    :param content: Body of the entry; deduplication is over this.
    :param title: Label for the précis, or ``""`` to derive one on add.
    :param category: One of the long-term categories, or ``""``.
    :param importance: 0 to 10, clamped. ``None`` means the model did not
        say, which on update leaves the stored rating alone — the
        distinction a plain ``0`` default cannot make.
    :param ttl_days: Days until expiry, ``None`` for unsaid, ``0`` for
        never.
    :returns: JSON naming the entry that was written, including its id.
    :raises ToolArgumentError: If the action's required argument is
        missing, or the named entry does not exist. Both reach the model
        as something it can correct.
    """
    if action == "remove":
        removed = await binding.store.soft_delete(_required_id(entry_id, action))
        if not removed:
            raise _no_such_entry(entry_id)
        return await _written(binding, {"action": action, "id": entry_id})

    if action == "update":
        changed = _changes(content, title, category, importance, ttl_days)
        if not changed:
            raise ToolArgumentError(
                "input has nothing to update; send at least one of content, "
                "title, category, importance or ttl_days"
            )
        if not await binding.store.update(_required_id(entry_id, action), **changed):
            raise _no_such_entry(entry_id)
        return await _written(
            binding, {"action": action, "id": entry_id, "changed": sorted(changed)}
        )

    body = content.strip()
    if not body:
        raise ToolArgumentError(
            "input.content is empty; give the thing you want to remember"
        )
    stored = await binding.store.add(
        MemoryEntry(
            title=title.strip() or body[:60],
            content=body,
            category=category.strip().lower(),
            importance=_rating(importance),
            ttl_days=max(_as_int(ttl_days, "ttl_days"), 0) if ttl_days else 0,
        )
    )
    return await _written(binding, {"action": action, "id": stored})


def _required_id(entry_id: str, action: str) -> str:
    """The id *action* cannot run without.

    :raises ToolArgumentError: If it is blank; ``memory_search`` is where
        the model gets one, and the message says so.
    """
    if not entry_id.strip():
        raise ToolArgumentError(
            f"input.id is required for action {action!r}; memory_search "
            f"reports the id of every entry it finds"
        )
    return entry_id.strip()


def _no_such_entry(entry_id: str) -> ToolArgumentError:
    """The complaint for an id the store does not hold."""
    return ToolArgumentError(
        f"input.id {entry_id!r} is not a memory this store holds; search "
        f"for it again to get its current id"
    )


def _changes(
    content: str,
    title: str,
    category: str,
    importance: int | None,
    ttl_days: int | None,
) -> dict[str, object]:
    """The fields an update actually asked to change.

    Only what the model sent is included, so an update of one field
    cannot blank the others.
    """
    changed: dict[str, object] = {}
    if content.strip():
        changed["content"] = content.strip()
    if title.strip():
        changed["title"] = title.strip()
    if category.strip():
        changed["category"] = category.strip().lower()
    if importance is not None:
        changed["importance"] = _rating(importance)
    if ttl_days is not None:
        changed["ttl_days"] = max(_as_int(ttl_days, "ttl_days"), 0)
    return changed


def _rating(importance: int | None) -> int:
    """*importance* as a 0-10 rating, with ``None`` reading as 0."""
    if importance is None:
        return 0
    return min(max(_as_int(importance, "importance"), 0), 10)


async def _written(binding: MemoryBinding, answer: dict[str, object]) -> str:
    """Rebuild the précis after a successful write and report *answer*.

    A précis that cannot be written does not fail the call — the memory
    is already stored, and telling the model otherwise would have it
    write the same thing again.
    """
    try:
        await binding.precis.regenerate()
    except OSError as error:
        _log.warning("could not rewrite the memory précis: %s", error)
        answer = {**answer, "precis": "not rewritten"}
    return _dump(answer)


def _dump(value: object) -> str:
    """One rule for the JSON these tools answer with."""
    return json.dumps(value, ensure_ascii=False)


def _as_dict(entry: MemoryEntry) -> dict[str, object]:
    """One search hit, in the fields the model can act on."""
    category = (
        entry.category.value
        if isinstance(entry.category, Category)
        else str(entry.category)
    )
    return {
        "id": entry.id,
        "title": entry.title,
        "content": entry.content,
        "category": category,
        "importance": entry.importance,
    }


def _as_int(value: object, field: str) -> int:
    """Read one numeric argument the schema only typed loosely.

    :param value: What the model sent.
    :param field: Property name, for the complaint.
    :returns: *value* as an integer.
    :raises ToolArgumentError: If it is not a whole number.
    """
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError) as exc:
        raise ToolArgumentError(
            f"input.{field} is {value!r}; it must be a whole number"
        ) from exc
