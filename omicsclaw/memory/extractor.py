"""Reading a conversation for things worth keeping past it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from omicsclaw.context import Summarizer
from omicsclaw.schema import Message, Role

from .longterm import Category, MemoryEntry
from .store import LongTermStore

EXTRACTION_SYSTEM_PROMPT = (
    "You extract long-term memories from a conversation. Keep only what "
    "stays true after this conversation ends: stated preferences, stable "
    "facts about the project or the data, decisions that were settled, and "
    "reusable procedures. Leave out anything tied to this session — file "
    "paths for one run, intermediate results, what the assistant is about "
    "to do next.\n\n"
    "Answer with a JSON array and nothing else. Each element is "
    '{"title", "content", "category", "importance"}, where category is one '
    "of knowledge, preference, task, skill, and importance is an integer "
    "from 0 to 10. Write title and content in the language the "
    "conversation used. When nothing is worth keeping, answer []."
)

_VALID_CATEGORIES = {c.value for c in Category}


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """What one extraction pass managed to do.

    :param stored: Ids of the entries written, in the order written.
    :param rejected: How many facts the model returned that were dropped
        for being empty or malformed.
    :param failure: Why the pass produced nothing, or ``""`` on success.
    """

    stored: tuple[str, ...] = ()
    rejected: int = 0
    failure: str = ""

    @property
    def ok(self) -> bool:
        """Whether the pass ran to completion."""
        return not self.failure


def render_conversation(messages: Sequence[Message]) -> str:
    """Flatten *messages* into the transcript the prompt is built on.

    Messages with no text of their own — a tool call, an empty
    assistant turn — contribute nothing and are left out.

    :param messages: Conversation to render.
    :returns: One ``role: content`` line per message with text.
    """
    return "\n".join(
        f"{m.role.value}: {m.content}"
        for m in messages
        if m.role is not Role.SYSTEM and m.content.strip()
    )


def parse_facts(raw: str) -> list[dict[str, object]]:
    """Read the model's answer as a list of facts.

    Tolerates the `````json`` fence models add around JSON even when
    asked not to.

    :param raw: The model's raw answer.
    :returns: The decoded list.
    :raises ValueError: If *raw* is not a JSON array.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
        text = text.strip()
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"answer was not JSON: {exc}") from exc
    if not isinstance(decoded, list):
        raise ValueError(f"answer was {type(decoded).__name__}, not a list")
    return [item for item in decoded if isinstance(item, dict)]


def _to_entry(fact: dict[str, object]) -> MemoryEntry | None:
    """Build an entry from one decoded fact, or ``None`` if unusable."""
    content = str(fact.get("content", "")).strip()
    if not content:
        return None
    category = str(fact.get("category", "")).strip().lower()
    try:
        importance = int(fact.get("importance", 0))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        importance = 0
    return MemoryEntry(
        title=str(fact.get("title", "")).strip() or content[:60],
        content=content,
        category=category if category in _VALID_CATEGORIES else "",
        importance=max(0, min(10, importance)),
    )


class MemoryExtractor:
    """Writes down what a conversation said that outlives it.

    Built to run just before compaction, where the messages about to be
    summarized away are still intact.

    Every failure is absorbed: a model that times out, refuses, or
    answers with prose instead of JSON leaves the conversation exactly
    as it was and reports the reason on
    :attr:`ExtractionResult.failure`. Losing a memory is a smaller
    problem than losing the turn that would have recorded it. Nothing
    here logs — that belongs to the layer that composes this one.

    :param summarizer: Anything that can answer a prompt; the same
        protocol the compaction layer summarizes through.
    :param store: Where the extracted entries are written.
    """

    def __init__(self, summarizer: Summarizer, store: LongTermStore) -> None:
        self._summarizer = summarizer
        self._store = store

    async def extract(
        self, messages: Sequence[Message]
    ) -> ExtractionResult:
        """Read *messages* and store what is worth keeping.

        :param messages: Conversation to read, usually the part about to
            be compacted away.
        :returns: What was stored, and why nothing was if that is the
            case.
        """
        transcript = render_conversation(messages)
        if not transcript:
            return ExtractionResult()

        try:
            answer = await self._summarizer.summarize(
                transcript, system=EXTRACTION_SYSTEM_PROMPT
            )
        except Exception as exc:  # noqa: BLE001 - fail open, see the class
            return ExtractionResult(failure=f"model call failed: {exc}")

        try:
            facts = parse_facts(answer)
        except ValueError as exc:
            return ExtractionResult(failure=str(exc))

        stored: list[str] = []
        rejected = 0
        for fact in facts:
            entry = _to_entry(fact)
            if entry is None:
                rejected += 1
                continue
            try:
                stored.append(await self._store.add(entry))
            except Exception as exc:  # noqa: BLE001 - fail open
                return ExtractionResult(
                    stored=tuple(stored),
                    rejected=rejected,
                    failure=f"store rejected an entry: {exc}",
                )
        return ExtractionResult(stored=tuple(stored), rejected=rejected)
