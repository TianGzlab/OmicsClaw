"""Plan 0027 §12.10.1: what is committed is the *compacted* conversation.

This file exists for one defect, and the defect is worth restating
because it is invisible until a conversation gets long. The first draft
of :class:`~omicsclaw.engine.conversation.Conversation` spelled the
write half as ``extend`` — append what this exchange added. Under that
design a compaction that the kernel *kept* (``keep=True``, which
replaces the run's history with the summary) would have written the
folded-away originals back into storage, because those are what the
caller still held; the summary would have lived only in the
:class:`RunResult` and never reached the next exchange. Compaction would
then work perfectly inside one exchange and not at all between two,
which is the only place a context window is ever actually exceeded.

So the assertion here is not "``commit`` was called". It is: **the
messages the compactor folded away are gone, and the summary it produced
is present** — in what storage received, not merely in what the run
returned.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Sequence

from omicsclaw.engine import AgentEngine
from omicsclaw.provider import Completion
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    ToolResult,
)

SUMMARY = "[compacted] everything before this was about Visium QC"


class Provider:
    def __init__(self, *replies: Message) -> None:
        self.replies = list(replies)
        self.seen: list[tuple[Message, ...]] = []

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None) -> Completion:
        self.seen.append(tuple(messages))
        reply = self.replies[min(len(self.seen) - 1, len(self.replies) - 1)]
        return Completion(message=reply, finish_reason="stop")

    async def _stream(self, messages, tools) -> AsyncIterator[StreamChunk]:
        completion = await self.generate(messages, tools)
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)

    def generate_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    def bind(self, **overrides: Any) -> "Provider":
        return self


class Tools:
    def available_tools(self) -> Sequence[ToolDefinition]:
        return ()

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(tool_call_id=call.id, name=call.name, output="ran")


class Folding:
    """Replaces the whole conversation with a summary, once, and keeps it.

    The keep flag is what the kernel reads to decide whether the rewrite
    becomes the run's history (``loop.py``, ``history = list(sent)``).
    Only the first call folds, so the turn after the compaction still has
    the summary rather than a summary of a summary.
    """

    def __init__(self, *, keep: bool = True) -> None:
        self.keep = keep
        self.calls = 0

    async def compact(self, history, tools):
        self.calls += 1
        if self.calls > 1:
            return None
        kept = tuple(m for m in history if m.role is Role.SYSTEM)
        return (*kept, Message.user(SUMMARY)), self.keep


class Chat:
    def __init__(self, *history: Message) -> None:
        self.history = tuple(history)
        self.commits: list[tuple[Message, ...]] = []

    def messages(self) -> tuple[Message, ...]:
        return self.history

    async def commit(self, messages: Sequence[Message]) -> None:
        self.commits.append(tuple(messages))
        self.history = tuple(messages)


class Prompt:
    def render(self) -> "Prompt":
        return self

    @property
    def system_prompt(self) -> str:
        return "persona"


def _long_history() -> tuple[Message, ...]:
    return (
        Message.user("load the Visium slide"),
        Message.assistant("loaded 4,992 spots"),
        Message.user("how many genes survived QC"),
        Message.assistant("18,110"),
    )


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5.0))


def test_a_kept_compaction_is_what_storage_receives():
    provider = Provider(Message.assistant("done"))
    chat = Chat(*_long_history())
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    result = _run(engine.exchange("carry on", compactor=Folding(keep=True)))

    committed = chat.commits[0]
    contents = [m.content for m in committed]

    assert SUMMARY in contents, "the summary never reached storage"
    assert "load the Visium slide" not in contents, (
        "a folded-away message was written back: commit is appending "
        "rather than replacing, and compaction is dead between exchanges"
    )
    assert "how many genes survived QC" not in contents
    assert contents[-1] == "done"
    assert committed == tuple(result.messages[1:])


def test_the_next_exchange_starts_from_the_summary():
    """The property that actually saves the context window.

    One engine, two exchanges, one compaction in the first: the second
    exchange must be *shorter* than the first was, and must carry the
    summary in place of what it stood for.
    """
    provider = Provider(Message.assistant("first"), Message.assistant("second"))
    chat = Chat(*_long_history())
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    _run(engine.exchange("carry on", compactor=Folding(keep=True)))
    _run(engine.exchange("and again"))

    second = [m.content for m in provider.seen[1]]

    assert second == ["persona", SUMMARY, "first", "and again"]
    assert "18,110" not in second


def test_a_rewrite_that_was_not_kept_leaves_storage_whole():
    """The other half of the flag, or the test above proves nothing.

    ``keep=False`` means the compactor produced a *view* for one model
    call. The trajectory — and therefore the commit — still holds the
    originals, and a commit that quietly wrote the view instead would be
    losing messages the run deliberately retained.
    """
    provider = Provider(Message.assistant("done"))
    chat = Chat(*_long_history())
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    _run(engine.exchange("carry on", compactor=Folding(keep=False)))

    contents = [m.content for m in chat.commits[0]]

    assert provider.seen[0][-1].content == SUMMARY
    assert "load the Visium slide" in contents
    assert SUMMARY not in contents


def test_the_streaming_shell_commits_the_same_compacted_conversation():
    provider = Provider(Message.assistant("done"))
    chat = Chat(*_long_history())
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    async def drive():
        compactor = Folding(keep=True)
        return [
            event
            async for event in engine.exchange_stream("carry on", compactor=compactor)
        ]

    events = _run(drive())
    contents = [m.content for m in chat.commits[0]]

    assert SUMMARY in contents
    assert "load the Visium slide" not in contents
    assert chat.commits[0] == tuple(events[-1].result.messages[1:])
