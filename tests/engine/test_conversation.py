"""Plan 0027 §12.4.2: the engine reads a history and hands one back.

The contract under test is ``commit``, and it has three edges worth
pinning: it receives the **whole** trajectory rather than the increment,
it receives it **without** the system message the engine itself added,
and it is not called at all by an exchange that did not finish.

The compaction half of the same contract — that what ``commit`` receives
is the *compacted* conversation and not the originals it folded away —
is in ``test_commit_carries_compaction.py``, because that is the
property the first draft of this design got wrong.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Sequence

import pytest

from omicsclaw.engine import AgentEngine, Conversation, EngineConfig
from omicsclaw.provider import Completion, ProviderError
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


class Broken(Provider):
    async def generate(self, messages, tools=None) -> Completion:
        raise ProviderError("the backend is down", provider="scripted")


class Tools:
    def available_tools(self) -> Sequence[ToolDefinition]:
        return (ToolDefinition(name="bash", description="run"),)

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(tool_call_id=call.id, name=call.name, output="ran")


class Chat:
    """A conversation that remembers what it was read and what it was given."""

    def __init__(self, *history: Message) -> None:
        self.history = tuple(history)
        self.reads = 0
        self.commits: list[tuple[Message, ...]] = []

    def messages(self) -> tuple[Message, ...]:
        self.reads += 1
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


def _acting() -> Message:
    return Message.assistant("", tool_calls=[ToolCall(id="c1", name="bash")])


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5.0))


def test_the_protocol_is_structural():
    assert isinstance(Chat(), Conversation)


def test_the_history_arrives_between_the_system_message_and_the_user_text():
    provider = Provider(Message.assistant("done"))
    chat = Chat(Message.user("earlier"), Message.assistant("answered"))
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    _run(engine.exchange("next"))

    assert [(m.role, m.content) for m in provider.seen[0]] == [
        (Role.SYSTEM, "persona"),
        (Role.USER, "earlier"),
        (Role.ASSISTANT, "answered"),
        (Role.USER, "next"),
    ]


def test_the_history_is_read_once_however_many_turns_the_exchange_takes():
    provider = Provider(_acting(), _acting(), Message.assistant("done"))
    chat = Chat(Message.user("earlier"))
    engine = AgentEngine(provider, Tools(), conversation=chat)

    result = _run(engine.exchange("go"))

    assert result.turns == 3
    assert chat.reads == 1


def test_commit_receives_the_whole_trajectory_without_the_system_message():
    """The increment would be a different design — see the module docstring.

    Tool calls and their Observations are part of what comes back: a
    conversation missing an answered ``tool_use`` block is a 400 on the
    next exchange, not a tidier history.
    """
    provider = Provider(_acting(), Message.assistant("done"))
    chat = Chat(Message.user("earlier"))
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    result = _run(engine.exchange("go"))

    assert len(chat.commits) == 1
    committed = chat.commits[0]
    assert all(m.role is not Role.SYSTEM for m in committed)
    assert committed == tuple(result.messages[1:])
    assert [m.role for m in committed] == [
        Role.USER,
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
    ]


def test_what_commit_received_is_what_the_next_exchange_starts_from():
    """The round trip, because that is what the seam is for."""
    provider = Provider(Message.assistant("first"), Message.assistant("second"))
    chat = Chat()
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    _run(engine.exchange("one"))
    _run(engine.exchange("two"))

    assert [(m.role, m.content) for m in provider.seen[1]] == [
        (Role.SYSTEM, "persona"),
        (Role.USER, "one"),
        (Role.ASSISTANT, "first"),
        (Role.USER, "two"),
    ]


def test_without_a_prompt_source_nothing_is_stripped():
    """A caller keeping its own system message keeps it.

    The engine removes system messages because it added one; if it added
    none, editing the trajectory would be this layer discarding a message
    somebody deliberately kept.
    """
    chat = Chat(Message.system("mine"), Message.user("earlier"))
    engine = AgentEngine(
        Provider(Message.assistant("done")), Tools(), conversation=chat
    )

    _run(engine.exchange("go"))

    assert chat.commits[0][0] == Message.system("mine")


def test_a_conversation_that_breaks_its_contract_loses_its_system_message():
    """The cost of the stripping rule, pinned rather than discovered.

    ``Conversation.messages`` documents a history **without** a system
    message. A conversation that carries one anyway, while the engine is
    also rendering one, loses it: removal is by role, so it takes both.

    Pinned because the alternative — matching the one message the
    opening added — would be position- or identity-based, and a
    compactor is free to rewrite the trajectory between those two
    points. Whoever writes the next :class:`Conversation` (plan 0046's
    sub-agent layer is next in line) should meet this as a stated
    consequence rather than as missing history.
    """
    chat = Chat(Message.system("smuggled"), Message.user("earlier"))
    engine = AgentEngine(
        Provider(Message.assistant("done")),
        Tools(),
        conversation=chat,
        prompt=Prompt(),
    )

    _run(engine.exchange("go"))

    assert not [m for m in chat.commits[0] if m.role is Role.SYSTEM]


def test_an_exchange_that_raised_commits_nothing():
    chat = Chat(Message.user("earlier"))
    engine = AgentEngine(
        Broken(),
        Tools(),
        EngineConfig(generate_retries=1),
        prompt=Prompt(),
        conversation=chat,
    )

    with pytest.raises(ProviderError):
        _run(engine.exchange("go"))

    assert chat.commits == []
    assert chat.history == (Message.user("earlier"),)


def test_the_streaming_shell_commits_after_the_last_event():
    """And the ``DONE`` it forwards is the committed trajectory.

    ``DONE`` comes *after* the commit deliberately: a consumer that stops
    reading as soon as it has its answer would otherwise leave the
    conversation unrecorded, because breaking out of an ``async for``
    throws ``GeneratorExit`` into the generator at its yield.
    """
    provider = Provider(Message.assistant("done"))
    chat = Chat(Message.user("earlier"))
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    seen_at: list[int] = []

    async def drive():
        events = []
        async for event in engine.exchange_stream("go"):
            seen_at.append(len(chat.commits))
            events.append(event)
        return events

    events = _run(drive())

    assert seen_at[-1] == 1, "DONE was delivered before the commit"
    assert seen_at[:-1] == [0] * (len(seen_at) - 1)
    assert chat.commits[0] == tuple(events[-1].result.messages[1:])


def test_a_stream_abandoned_before_done_commits_nothing():
    provider = Provider(_acting(), Message.assistant("done"))
    chat = Chat(Message.user("earlier"))
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=chat)

    async def drive():
        async for _event in engine.exchange_stream("go"):
            break

    _run(drive())

    assert chat.commits == []


def test_a_commit_that_raises_surfaces_rather_than_being_swallowed():
    class Unwritable(Chat):
        async def commit(self, messages):
            raise OSError("the session store is read-only")

    engine = AgentEngine(
        Provider(Message.assistant("done")),
        Tools(),
        conversation=Unwritable(),
    )

    with pytest.raises(OSError, match="read-only"):
        _run(engine.exchange("go"))


def test_a_call_time_conversation_beats_the_engines_default():
    """One engine, two sessions — the deployment shape this exists for."""
    provider = Provider(Message.assistant("done"))
    default, other = Chat(Message.user("theirs")), Chat(Message.user("mine"))
    engine = AgentEngine(provider, Tools(), conversation=default)

    _run(engine.exchange("go", conversation=other))

    assert provider.seen[0][0] == Message.user("mine")
    assert default.commits == []
    assert len(other.commits) == 1
