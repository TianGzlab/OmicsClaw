"""Turning a conversation into entries, and failing open when it cannot."""

from __future__ import annotations

import asyncio

from omicsclaw.memory import Database, LongTermStore, MemoryExtractor
from omicsclaw.schema import Message, Role


def run(coro):
    return asyncio.run(coro)


class FakeSummarizer:
    """A summarizer that replays a canned answer and records its prompts."""

    def __init__(self, answer: str = "[]") -> None:
        self.answer = answer
        self.prompts: list[tuple[str, str]] = []

    async def summarize(self, prompt: str, *, system: str) -> str:
        self.prompts.append((prompt, system))
        return self.answer


CONVERSATION = (
    Message(role=Role.USER, content="Always filter Visium spots at 500 counts"),
    Message(role=Role.ASSISTANT, content="Noted."),
)


def test_extracted_facts_become_entries() -> None:
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer(
        '[{"title": "Visium QC", "content": "min_counts=500", '
        '"category": "preference", "importance": 7}]'
    )

    result = run(MemoryExtractor(model, lt).extract(CONVERSATION))
    stored = run(lt.list())
    db.close()

    assert result.failure == ""
    assert len(result.stored) == 1
    assert [e.title for e in stored] == ["Visium QC"]
    assert stored[0].content == "min_counts=500"
    assert stored[0].category == "preference"
    assert stored[0].importance == 7


class Exploding:
    """A model that fails the way a timed-out or refused call does."""

    async def summarize(self, prompt: str, *, system: str) -> str:
        raise RuntimeError("upstream timed out")


def test_a_failing_model_leaves_the_caller_unharmed() -> None:
    """Extraction runs beside compaction; it must never take it down.

    Losing one pass of memory writing costs a fact. Raising out of here
    costs the turn that was being compacted, which is the conversation
    itself.
    """
    db = Database()
    lt = LongTermStore(db)

    result = run(MemoryExtractor(Exploding(), lt).extract(CONVERSATION))
    db.close()

    assert result.ok is False
    assert "upstream timed out" in result.failure
    assert result.stored == ()


def test_prose_instead_of_json_is_reported_not_raised() -> None:
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer("I think the user prefers 500 counts.")

    result = run(MemoryExtractor(model, lt).extract(CONVERSATION))
    stored = run(lt.list())
    db.close()

    assert result.ok is False
    assert "JSON" in result.failure
    assert stored == []


def test_a_fenced_answer_is_still_read() -> None:
    """Models fence JSON even when told not to."""
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer(
        '```json\n[{"title": "t", "content": "c", "importance": 3}]\n```'
    )

    result = run(MemoryExtractor(model, lt).extract(CONVERSATION))
    stored = run(lt.list())
    db.close()

    assert result.ok is True
    assert [e.content for e in stored] == ["c"]


def test_nothing_worth_keeping_is_a_success_not_a_failure() -> None:
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer("[]")

    result = run(MemoryExtractor(model, lt).extract(CONVERSATION))
    db.close()

    assert result.ok is True
    assert result.stored == ()


def test_facts_without_content_are_dropped() -> None:
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer(
        '[{"title": "empty", "content": "   "},'
        ' {"title": "real", "content": "keep me"}]'
    )

    result = run(MemoryExtractor(model, lt).extract(CONVERSATION))
    stored = run(lt.list())
    db.close()

    assert result.rejected == 1
    assert [e.content for e in stored] == ["keep me"]


def test_an_unknown_category_is_dropped_rather_than_stored() -> None:
    """A category the store does not know would break précis grouping."""
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer(
        '[{"title": "t", "content": "c", "category": "vibes"}]'
    )

    run(MemoryExtractor(model, lt).extract(CONVERSATION))
    stored = run(lt.list())
    db.close()

    assert stored[0].category == ""


def test_importance_outside_the_scale_is_clamped() -> None:
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer(
        '[{"title": "a", "content": "high", "importance": 99},'
        ' {"title": "b", "content": "low", "importance": -4},'
        ' {"title": "c", "content": "junk", "importance": "eight"}]'
    )

    run(MemoryExtractor(model, lt).extract(CONVERSATION))
    by_content = {e.content: e.importance for e in run(lt.list())}
    db.close()

    assert by_content == {"high": 10, "low": 0, "junk": 0}


def test_the_conversation_reaches_the_model_without_system_turns() -> None:
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer()

    run(
        MemoryExtractor(model, lt).extract(
            (
                Message(role=Role.SYSTEM, content="you are an omics agent"),
                Message(role=Role.USER, content="prefer 500 counts"),
                Message(role=Role.ASSISTANT, content=""),
            )
        )
    )
    db.close()

    prompt, system = model.prompts[0]
    assert prompt == "user: prefer 500 counts"
    assert "long-term memories" in system


def test_an_empty_conversation_never_reaches_the_model() -> None:
    """No text means no prompt, not a prompt with nothing in it."""
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer()

    result = run(
        MemoryExtractor(model, lt).extract(
            (Message(role=Role.ASSISTANT, content="   "),)
        )
    )
    db.close()

    assert result.ok is True
    assert model.prompts == []


class FlakyStore:
    """A store that takes one entry and then fails, as a full disk would."""

    def __init__(self) -> None:
        self.calls = 0

    async def add(self, entry) -> str:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("disk full")
        return "id-1"


def test_a_failing_store_is_reported_with_what_was_already_written() -> None:
    """The write half fails open too, and says how far it got.

    ``add`` no longer raises on the paths this package controls, so
    nothing in the normal run exercises this. What is left is the
    environment — a full disk, a revoked file, a lock held past the
    timeout — and a caller that has to know whether the first entry
    landed before the second one did not.
    """
    model = FakeSummarizer(
        '[{"title": "a", "content": "one"}, {"title": "b", "content": "two"}]'
    )

    result = run(MemoryExtractor(model, FlakyStore()).extract(CONVERSATION))

    assert result.ok is False
    assert "disk full" in result.failure
    assert result.stored == ("id-1",)


def test_repeated_extraction_of_the_same_fact_stays_one_entry() -> None:
    """The store deduplicates, so a second pass over the same window is safe."""
    db = Database()
    lt = LongTermStore(db)
    model = FakeSummarizer(
        '[{"title": "Visium QC", "content": "min_counts=500"}]'
    )
    extractor = MemoryExtractor(model, lt)

    first = run(extractor.extract(CONVERSATION))
    second = run(extractor.extract(CONVERSATION))
    stored = run(lt.list())
    db.close()

    assert first.stored == second.stored
    assert len(stored) == 1
