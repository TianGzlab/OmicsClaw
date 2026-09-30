"""Plan 0027 §12.4.1: the engine asks for its system prompt.

Two properties carry the design. The render is **one per exchange**, not
one per turn — a prompt that changed halfway through an exchange would
make the model's persona depend on when somebody saved a file — and the
render arrives as its renderer's own object, so whatever it carries
besides the text survives the trip and comes back on the
:class:`RunResult`.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Sequence

import pytest

from omicsclaw.engine import AgentEngine, PromptSource, RenderedPrompt
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


class Render:
    """A render that carries more than the engine reads."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.section_stats = (("persona", 3), ("skills", 41))

    @property
    def system_prompt(self) -> str:
        return self.text


class Assembler:
    def __init__(self, text: str = "you are OmicsClaw") -> None:
        self.text = text
        self.renders = 0

    def render(self) -> Render:
        self.renders += 1
        return Render(f"{self.text} #{self.renders}")


def _acting() -> Message:
    return Message.assistant("", tool_calls=[ToolCall(id="c1", name="bash")])


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5.0))


def test_the_protocols_are_structural():
    """No base class, no import of this package by the renderer.

    ``system_prompt`` is a property rather than a method, and
    ``runtime_checkable`` sees it: that is what lets the context layer's
    ``AssembledPrompt`` satisfy this with no adapter, which is the whole
    reason the seam hands back an object instead of a ``str``.
    """
    assert isinstance(Assembler(), PromptSource)
    assert isinstance(Render("hi"), RenderedPrompt)
    assert not isinstance(Render("hi"), PromptSource)


def test_the_render_becomes_message_zero_and_there_is_one_of_it():
    provider = Provider(Message.assistant("done"))
    engine = AgentEngine(provider, Tools(), prompt=Assembler())

    _run(engine.exchange("分析这份 Visium 数据"))

    sent = provider.seen[0]
    assert sent[0].role is Role.SYSTEM
    assert sent[0].content == "you are OmicsClaw #1"
    assert [m.role for m in sent] == [Role.SYSTEM, Role.USER]


def test_the_prompt_is_rendered_once_per_exchange_not_once_per_turn():
    """A four-turn exchange reads ``SOUL.md`` once, not four times.

    The counter is in the render, so a second render inside one exchange
    would also be *visible* to the model as a changed persona — which is
    the failure this pins, not merely the wasted file reads.
    """
    provider = Provider(_acting(), _acting(), _acting(), Message.assistant("done"))
    assembler = Assembler()
    engine = AgentEngine(provider, Tools(), prompt=assembler)

    result = _run(engine.exchange("go"))

    assert result.turns == 4
    assert assembler.renders == 1
    assert {sent[0].content for sent in provider.seen} == {"you are OmicsClaw #1"}


def test_the_run_result_carries_the_render_itself():
    """Not a copy of the text: the object, statistics and all."""
    assembler = Assembler()
    engine = AgentEngine(Provider(Message.assistant("done")), Tools(), prompt=assembler)

    result = _run(engine.exchange("go"))

    assert isinstance(result.prompt, RenderedPrompt)
    assert result.prompt.system_prompt == "you are OmicsClaw #1"
    assert result.prompt.section_stats == (("persona", 3), ("skills", 41))


def test_the_streaming_shell_renders_once_and_reports_the_render():
    provider = Provider(_acting(), Message.assistant("done"))
    assembler = Assembler()
    engine = AgentEngine(provider, Tools(), prompt=assembler)

    async def drive():
        return [event async for event in engine.exchange_stream("go")]

    events = _run(drive())

    assert assembler.renders == 1
    assert events[-1].result.prompt is not None
    assert events[-1].result.prompt.system_prompt == "you are OmicsClaw #1"


def test_no_prompt_source_means_no_system_message_and_no_render():
    provider = Provider(Message.assistant("done"))
    engine = AgentEngine(provider, Tools())

    result = _run(engine.exchange("go"))

    assert provider.seen[0] == (Message.user("go"),)
    assert result.prompt is None


def test_a_call_time_source_beats_the_engines_default():
    provider = Provider(Message.assistant("done"))
    default, per_call = Assembler("default"), Assembler("per call")
    engine = AgentEngine(provider, Tools(), prompt=default)

    _run(engine.exchange("go", prompt=per_call))

    assert provider.seen[0][0].content == "per call #1"
    assert default.renders == 0


def test_a_renderer_that_raises_ends_the_exchange_before_the_model_is_called():
    class Broken:
        def render(self):
            raise RuntimeError("SOUL.md is unreadable")

    provider = Provider(Message.assistant("done"))
    engine = AgentEngine(provider, Tools(), prompt=Broken())

    with pytest.raises(RuntimeError, match="SOUL.md is unreadable"):
        _run(engine.exchange("go"))
    assert provider.seen == []
