"""Plan 0035: the loop consults a compactor before every model call.

The seam has two outputs and both are pinned: what *this* call is sent,
and whether that also becomes the run's history. A test that only looked
at what the provider received could not tell a write-back from a view,
and the difference is whether the next turn pays for the same compaction
again.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Sequence

import pytest

from omicsclaw.engine import AgentEngine, HistoryCompactor
from omicsclaw.provider import Completion
from omicsclaw.schema import (
    Message,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


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
        return (ToolDefinition(name="bash", description="run"),)

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(tool_call_id=call.id, name=call.name, output="ran")


class Compactor:
    """Replaces everything but the last message with a marker each turn."""

    def __init__(self, *, keep: bool) -> None:
        self.keep = keep
        self.calls: list[tuple[tuple[Message, ...], tuple[ToolDefinition, ...]]] = []

    async def compact(self, history, tools):
        self.calls.append((history, tools))
        return (Message.user(f"summary of {len(history)}"), history[-1]), self.keep


def _acting() -> Message:
    return Message.assistant("", tool_calls=[ToolCall(id="c1", name="bash")])


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5.0))


def test_the_compactor_is_consulted_before_every_model_call():
    provider = Provider(_acting(), Message.assistant("done"))
    compactor = Compactor(keep=False)
    engine = AgentEngine(provider, Tools())

    result = _run(engine.run([Message.user("go")], compactor=compactor))

    assert result.turns == 2
    assert len(compactor.calls) == 2
    assert [d.name for d in compactor.calls[0][1]] == ["bash"]
    assert provider.seen[0][0].content == "summary of 1"
    assert provider.seen[1][0].content == "summary of 3"


def test_a_kept_rewrite_becomes_the_history():
    provider = Provider(_acting(), Message.assistant("done"))
    compactor = Compactor(keep=True)
    engine = AgentEngine(provider, Tools())

    result = _run(engine.run([Message.user("go")], compactor=compactor))

    # Turn 2 saw the kept turn-1 rewrite (two messages) plus the action and
    # its answer; a view that was not kept would have shown three.
    assert compactor.calls[1][0][0].content == "summary of 1"
    assert len(compactor.calls[1][0]) == 4
    assert result.messages[0].content == "summary of 4"
    assert result.messages[-1].content == "done"


def test_a_view_is_sent_but_the_history_stays_whole():
    provider = Provider(_acting(), Message.assistant("done"))
    compactor = Compactor(keep=False)
    engine = AgentEngine(provider, Tools())

    result = _run(engine.run([Message.user("go")], compactor=compactor))

    assert compactor.calls[1][0][0].content == "go"
    assert result.messages[0].content == "go"
    assert len(result.messages) == 4


def test_no_rewrite_and_an_empty_rewrite_both_send_the_history():
    class Declines:
        def __init__(self, answer) -> None:
            self.answer = answer

        async def compact(self, history, tools):
            return self.answer

    for answer in (None, ((), True)):
        provider = Provider(Message.assistant("done"))
        result = _run(
            AgentEngine(provider, Tools()).run(
                [Message.user("go")], compactor=Declines(answer)
            )
        )
        assert provider.seen[0] == (Message.user("go"),)
        assert result.messages[0] == Message.user("go")


def test_the_streaming_path_consults_it_too():
    provider = Provider(Message.assistant("done"))
    compactor = Compactor(keep=True)
    engine = AgentEngine(provider, Tools())

    async def drive():
        return [event async for event in engine.run_stream(
            [Message.user("go")], compactor=compactor
        )]

    events = _run(drive())

    assert provider.seen[0][0].content == "summary of 1"
    assert events[-1].result.messages[0].content == "summary of 1"


def test_a_compactor_that_raises_ends_the_run():
    class Broken:
        async def compact(self, history, tools):
            raise RuntimeError("compactor bug")

    engine = AgentEngine(Provider(Message.assistant("done")), Tools())

    with pytest.raises(RuntimeError, match="compactor bug"):
        _run(engine.run([Message.user("go")], compactor=Broken()))


def test_the_protocol_is_structural():
    assert isinstance(Compactor(keep=True), HistoryCompactor)
