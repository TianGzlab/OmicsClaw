"""Plan 0039: the loop consults an augmentor after the compactor.

Three properties carry the whole seam, and each is a different failure if
it is wrong: the extra messages reach *this* call, they reach it after
compaction, and they reach nothing else — not the history the run carries
forward, not the trajectory it returns, and not the next call.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Sequence

import pytest

from omicsclaw.engine import AgentEngine, EngineConfig, TurnAugmentor
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


class Reminder:
    """Appends one message, recording what it was asked about."""

    def __init__(self, text: str = "remember this") -> None:
        self.text = text
        self.seen: list[tuple[Message, ...]] = []
        self.tools_seen: list[tuple[ToolDefinition, ...]] = []

    async def augment(self, history, tools):
        self.seen.append(tuple(history))
        self.tools_seen.append(tuple(tools))
        return (Message(role=Role.USER, content=self.text),)


class Silent:
    async def augment(self, history, tools):
        return ()


class Shrinker:
    """A compactor that replaces the conversation with one message."""

    def __init__(self, keep: bool = False) -> None:
        self.keep = keep

    async def compact(self, history, tools):
        return ([Message(role=Role.USER, content="[summary]")], self.keep)


_DONE = Message(role=Role.ASSISTANT, content="finished")
_ACT = Message(
    role=Role.ASSISTANT,
    content="",
    tool_calls=(ToolCall(id="c1", name="bash", arguments="{}"),),
)


def _engine(provider: Provider, turns: int = 5) -> AgentEngine:
    return AgentEngine(provider, Tools(), EngineConfig(max_turns=turns))


def test_the_protocol_is_satisfied_structurally():
    """Nothing outside the engine imports this type to implement it."""
    assert isinstance(Reminder(), TurnAugmentor)
    assert not isinstance(object(), TurnAugmentor)


def test_no_augmentor_sends_the_conversation_unchanged():
    provider = Provider(_DONE)
    history = (Message(role=Role.USER, content="hello"),)

    asyncio.run(_engine(provider).run(history))

    assert provider.seen[0] == history


def test_what_the_augmentor_returns_reaches_the_model():
    provider = Provider(_DONE)

    asyncio.run(
        _engine(provider).run(
            (Message(role=Role.USER, content="hello"),), augmentor=Reminder()
        )
    )

    assert provider.seen[0][-1].content == "remember this"


def test_an_empty_return_changes_nothing():
    provider = Provider(_DONE)
    history = (Message(role=Role.USER, content="hello"),)

    asyncio.run(_engine(provider).run(history, augmentor=Silent()))

    assert provider.seen[0] == history


def test_it_is_consulted_before_every_model_call_not_once():
    provider = Provider(_ACT, _DONE)
    reminder = Reminder()

    asyncio.run(
        _engine(provider).run(
            (Message(role=Role.USER, content="go"),), augmentor=reminder
        )
    )

    assert len(reminder.seen) == 2
    assert all(sent[-1].content == "remember this" for sent in provider.seen)


def test_nothing_accumulates_across_turns():
    """One copy per call, never two — the block is not part of the history."""
    provider = Provider(_ACT, _DONE)

    asyncio.run(
        _engine(provider).run(
            (Message(role=Role.USER, content="go"),), augmentor=Reminder()
        )
    )

    reminders = [
        sum(1 for m in sent if m.content == "remember this") for sent in provider.seen
    ]
    assert reminders == [1, 1]


def test_the_appended_message_never_enters_the_returned_trajectory():
    provider = Provider(_DONE)

    result = asyncio.run(
        _engine(provider).run(
            (Message(role=Role.USER, content="hello"),), augmentor=Reminder()
        )
    )

    assert [m.content for m in result.messages] == ["hello", "finished"]


def test_it_runs_after_the_compactor_so_compaction_cannot_remove_it():
    """The ordering is the contract: an augmentor exists to be read."""
    provider = Provider(_DONE)
    reminder = Reminder()

    asyncio.run(
        _engine(provider).run(
            (Message(role=Role.USER, content="a long conversation"),),
            compactor=Shrinker(),
            augmentor=reminder,
        )
    )

    assert [m.content for m in reminder.seen[0]] == ["[summary]"]
    assert [m.content for m in provider.seen[0]] == ["[summary]", "remember this"]


def test_a_written_back_compaction_still_does_not_keep_the_appended_message():
    """``keep=True`` replaces the history; the augmentor's output is not in it."""
    provider = Provider(_DONE)

    result = asyncio.run(
        _engine(provider).run(
            (Message(role=Role.USER, content="hello"),),
            compactor=Shrinker(keep=True),
            augmentor=Reminder(),
        )
    )

    assert [m.content for m in result.messages] == ["[summary]", "finished"]


def test_it_is_given_this_call_s_tool_definitions():
    provider = Provider(_DONE)
    reminder = Reminder()

    asyncio.run(
        _engine(provider).run(
            (Message(role=Role.USER, content="hello"),), augmentor=reminder
        )
    )

    assert [t.name for t in reminder.tools_seen[0]] == ["bash"]


def test_a_raising_augmentor_stops_the_run():
    """The loop cannot tell a plan it could not read from a plan that says stop."""

    class Broken:
        async def augment(self, history, tools):
            raise RuntimeError("the plan store is on fire")

    provider = Provider(_DONE)

    with pytest.raises(RuntimeError):
        asyncio.run(
            _engine(provider).run(
                (Message(role=Role.USER, content="hello"),), augmentor=Broken()
            )
        )


def test_the_streaming_path_behaves_the_same_way():
    """Two copies of this logic is how the two paths start disagreeing."""
    provider = Provider(_DONE)

    async def drive():
        async for _event in _engine(provider).run_stream(
            (Message(role=Role.USER, content="hello"),), augmentor=Reminder()
        ):
            pass

    asyncio.run(drive())

    assert provider.seen[0][-1].content == "remember this"


def test_the_two_seams_are_independent():
    """An augmentor with no compactor, and a compactor with no augmentor."""
    provider = Provider(_DONE)
    asyncio.run(
        _engine(provider).run(
            (Message(role=Role.USER, content="hello"),), augmentor=Reminder()
        )
    )
    assert len(provider.seen[0]) == 2

    other = Provider(_DONE)
    asyncio.run(
        _engine(other).run(
            (Message(role=Role.USER, content="hello"),), compactor=Shrinker()
        )
    )
    assert len(other.seen[0]) == 1
