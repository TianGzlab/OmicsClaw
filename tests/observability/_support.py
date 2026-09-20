"""Doubles for the observability tests: a recorder, a provider, a tool.

None of them import :mod:`omicsclaw.observability`. That is the point of
the Protocols being structural, and it is also what makes these tests
able to fail for the right reason — a double that inherited from the
contract would keep satisfying :func:`isinstance` after the contract
changed underneath it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine, Sequence
from dataclasses import dataclass, field
from typing import Any, Mapping, TypeVar

from omicsclaw.provider import Completion, ProviderError
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    Usage,
)
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy

_T = TypeVar("_T")

_DEADLINE = 5.0
"""Seconds one scenario may take. A hang guard, not a measurement."""

__all__ = [
    "Echo",
    "Exploding",
    "Recorded",
    "RecordingMeter",
    "RecordingTracer",
    "Scripted",
    "Slow",
    "assistant",
    "run",
    "tool_turn",
]


def run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; this is the repository's convention."""

    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


@dataclass
class Recorded:
    """One span, as a test wants to read it."""

    name: str
    parent: "Recorded | None"
    attributes: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    ended: int = 0

    def set_attributes(self, attributes: Mapping[str, Any]) -> None:
        self.attributes.update(attributes)

    def record_error(self, error: BaseException) -> None:
        self.error = type(error).__name__

    def end(self) -> None:
        self.ended += 1

    @property
    def chain(self) -> list[str]:
        """This span's ancestry, innermost first — the assertion shape."""
        names, node = [], self
        while node is not None:
            names.append(node.name)
            node = node.parent
        return names


class RecordingTracer:
    """Keeps every span it started, in order."""

    def __init__(self) -> None:
        self.spans: list[Recorded] = []

    def start_span(
        self,
        name: str,
        *,
        parent: Any = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> Recorded:
        span = Recorded(name=name, parent=parent, attributes=dict(attributes or {}))
        self.spans.append(span)
        return span

    def named(self, name: str) -> list[Recorded]:
        return [span for span in self.spans if span.name == name]


class RecordingMeter:
    """Keeps every measurement as a ``(name, value, attributes)`` triple."""

    def __init__(self) -> None:
        self.counts: list[tuple[str, float, dict[str, str]]] = []
        self.records: list[tuple[str, float, dict[str, str]]] = []

    def count(
        self, name: str, value: int = 1, attributes: Mapping[str, str] | None = None
    ) -> None:
        self.counts.append((name, value, dict(attributes or {})))

    def record(
        self, name: str, value: float, attributes: Mapping[str, str] | None = None
    ) -> None:
        self.records.append((name, value, dict(attributes or {})))

    def totals(self, name: str) -> float:
        return sum(v for n, v, _ in self.counts + self.records if n == name)


def assistant(text: str = "done", **usage: int) -> Completion:
    return Completion(
        message=Message(role=Role.ASSISTANT, content=text),
        usage=Usage(**usage),
        finish_reason="stop",
    )


def tool_turn(*names: str, **usage: int) -> Completion:
    calls = tuple(
        ToolCall(id=f"call-{i}", name=name, arguments='{"x":%d}' % i)
        for i, name in enumerate(names)
    )
    return Completion(
        message=Message(role=Role.ASSISTANT, tool_calls=calls),
        usage=Usage(**usage),
        finish_reason="tool_calls",
    )


class Scripted:
    """A provider that replays a fixed list of completions.

    Satisfies :class:`~omicsclaw.provider.LLMProvider` structurally and
    imports nothing from the layer under test.
    """

    def __init__(self, *completions: Completion, name: str = "scripted") -> None:
        self._completions = list(completions)
        self._name = name
        self.calls = 0
        self.bound: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        index = min(self.calls, len(self._completions) - 1)
        self.calls += 1
        return self._completions[index]

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        async def chunks() -> AsyncIterator[StreamChunk]:
            completion = await self.generate(messages, tools)
            if completion.message.content:
                yield StreamChunk(
                    type=StreamChunkType.TEXT_DELTA, delta=completion.message.content
                )
            yield StreamChunk(
                type=StreamChunkType.DONE,
                message=completion.message,
                usage=completion.usage,
                finish_reason=completion.finish_reason,
            )

        return chunks()

    def bind(self, **overrides: Any) -> "Scripted":
        self.bound.append(dict(overrides))
        return Scripted(*self._completions, name=self._name)


class Exploding:
    """A provider whose every call fails, with a message worth checking."""

    def __init__(self, message: str = "429 rate limited") -> None:
        self._message = message

    @property
    def name(self) -> str:
        return "exploding"

    async def generate(self, messages: Any, tools: Any = None) -> Completion:
        raise ProviderError(self._message, provider="exploding")

    def generate_stream(self, messages: Any, tools: Any = None) -> Any:
        async def chunks() -> AsyncIterator[StreamChunk]:
            raise ProviderError(self._message, provider="exploding")
            yield  # pragma: no cover

        return chunks()

    def bind(self, **overrides: Any) -> "Exploding":
        return self


class Echo:
    """A tool that returns what it was given."""

    policy = ToolPolicy(
        risk_level=RiskLevel.LOW,
        approval_mode=ApprovalMode.AUTO,
        read_only=True,
        concurrency_safe=True,
    )

    def __init__(self, name: str = "echo") -> None:
        self._name = name
        self.seen: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(name=self._name, description="", input_schema={})

    async def execute(self, arguments: str) -> str:
        self.seen.append(arguments)
        return f"echoed {arguments}"


class Slow:
    """A tool that waits, so a duration histogram has something to see."""

    policy = Echo.policy

    def __init__(self, delay: float = 0.01, name: str = "slow") -> None:
        self._delay = delay
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(name=self._name, description="", input_schema={})

    async def execute(self, arguments: str) -> str:
        await asyncio.sleep(self._delay)
        return "slept"
