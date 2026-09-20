"""Contract tests for ``omicsclaw.provider.base`` (plan 0026 §2).

The interface is valuable for what it refuses to accept. Model,
temperature, ``max_tokens`` and thinking budget are absent from every
method signature, so the Engine cannot learn them; a change that adds one
back would make the layer optional rather than load-bearing, and several
of the tests here exist only to fail loudly when that happens.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Sequence

import pytest

from omicsclaw.provider import (
    Completion,
    LLMProvider,
    ProviderConfig,
    ProviderError,
)
from omicsclaw.schema import (
    Message,
    StreamChunk,
    StreamChunkType,
    ToolDefinition,
    Usage,
)


class FakeProvider:
    """A backend that records what it was asked, and nothing else.

    Structurally typed on purpose: it never subclasses ``LLMProvider``,
    which is how we know the Protocol is satisfiable by shape and a test
    double needs no import from the layer it stands in for.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self.calls: list[tuple[Sequence[ToolDefinition] | None, str]] = []

    @property
    def name(self) -> str:
        return self._config.provider

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        self.calls.append((tools, self._config.model))
        return Completion(
            message=Message.assistant(f"answered by {self._config.model}"),
            usage=Usage(input_tokens=7, output_tokens=2),
            finish_reason="stop",
        )

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append((tools, self._config.model))
        return self._stream()

    async def _stream(self) -> AsyncIterator[StreamChunk]:
        yield StreamChunk.text("par")
        yield StreamChunk.text("tial")
        yield StreamChunk.done(Message.assistant("partial"), Usage(output_tokens=2))

    def bind(self, **overrides: object) -> "FakeProvider":
        return FakeProvider(self._config.with_overrides(**overrides))


def _provider(**overrides: object) -> FakeProvider:
    config = ProviderConfig(provider="fake", model="test-model")
    return FakeProvider(config.with_overrides(**overrides))


def _drain(stream: AsyncIterator[StreamChunk]) -> list[StreamChunk]:
    async def collect() -> list[StreamChunk]:
        return [chunk async for chunk in stream]

    return asyncio.run(collect())


# --- Protocol conformance -------------------------------------------------


def test_a_structurally_matching_class_satisfies_the_protocol():
    assert isinstance(_provider(), LLMProvider)


def test_a_class_missing_a_method_does_not_satisfy_the_protocol():
    """``bind`` is part of the contract, not an optional convenience."""

    class Incomplete:
        name = "incomplete"

        async def generate(self, messages, tools=None):  # pragma: no cover
            raise NotImplementedError

        def generate_stream(self, messages, tools=None):  # pragma: no cover
            raise NotImplementedError

    assert not isinstance(Incomplete(), LLMProvider)


# --- What the signature is allowed to contain -----------------------------


def test_generate_takes_only_the_conversation_and_the_tools():
    """Model configuration has nowhere to enter on the hot path."""
    parameters = list(inspect.signature(LLMProvider.generate).parameters)
    assert parameters == ["self", "messages", "tools"]


def test_generate_stream_takes_the_same_two_parameters():
    parameters = list(inspect.signature(LLMProvider.generate_stream).parameters)
    assert parameters == ["self", "messages", "tools"]


def test_tools_default_to_none_so_the_thinking_phase_needs_no_new_method():
    default = inspect.signature(LLMProvider.generate).parameters["tools"].default
    assert default is None


def test_generate_stream_is_not_a_coroutine_function():
    """``async for`` over it directly; an extra ``await`` would be a break."""
    assert inspect.iscoroutinefunction(LLMProvider.generate)
    assert not inspect.iscoroutinefunction(LLMProvider.generate_stream)


# --- Tool stripping -------------------------------------------------------


def test_none_tools_reach_the_adapter_as_none():
    """The Thinking/Action phase switch: no tools must mean no tools.

    An adapter that substitutes a default tool list when it receives
    ``None`` silently re-arms a phase that was meant to reason only.
    """
    provider = _provider()
    asyncio.run(provider.generate([Message.user("think")], None))
    assert provider.calls == [(None, "test-model")]


def test_tools_are_passed_through_untouched():
    provider = _provider()
    tools = [ToolDefinition(name="run", description="run a skill")]
    asyncio.run(provider.generate([Message.user("act")], tools))
    assert provider.calls[0][0] is tools


# --- Completion -----------------------------------------------------------


def test_generate_returns_message_usage_and_finish_reason_together():
    completion = asyncio.run(_provider().generate([Message.user("hi")]))

    assert completion.message.content == "answered by test-model"
    assert completion.usage == Usage(input_tokens=7, output_tokens=2)
    assert completion.finish_reason == "stop"


def test_completion_is_frozen():
    completion = Completion(message=Message.assistant("a"))
    with pytest.raises(Exception):
        completion.finish_reason = "stop"  # type: ignore[misc]


def test_completion_defaults_to_zero_usage_not_none():
    """Accumulating a run's cost must never need a ``None`` branch."""
    completion = Completion(message=Message.assistant("a"))
    assert completion.usage == Usage()
    assert completion.usage + Usage(input_tokens=1) == Usage(input_tokens=1)


def test_usage_defaults_are_not_shared_between_completions():
    first = Completion(message=Message.assistant("a"))
    second = Completion(message=Message.assistant("b"))
    assert first.usage == second.usage == Usage()


# --- Streaming ------------------------------------------------------------


def test_the_stream_ends_with_a_done_chunk_carrying_the_message():
    chunks = _drain(_provider().generate_stream([Message.user("hi")]))

    assert [chunk.type for chunk in chunks[:-1]] == [
        StreamChunkType.TEXT_DELTA,
        StreamChunkType.TEXT_DELTA,
    ]
    assert chunks[-1].type is StreamChunkType.DONE
    assert chunks[-1].message is not None
    assert chunks[-1].message.content == "partial"


# --- bind -----------------------------------------------------------------


def test_bind_does_not_mutate_the_receiver():
    """Two turns holding two binds must not observe each other's settings."""
    original = _provider()
    bound = original.bind(model="other-model")

    assert bound._config.model == "other-model"
    assert original._config.model == "test-model"


def test_bind_returns_something_that_is_still_a_provider():
    bound = _provider().bind(max_tokens=512)
    assert isinstance(bound, LLMProvider)
    assert bound._config.max_tokens == 512


def test_bind_reaches_the_model_actually_used_for_the_call():
    bound = _provider().bind(model="bound-model")
    completion = asyncio.run(bound.generate([Message.user("hi")]))
    assert completion.message.content == "answered by bound-model"


# --- ProviderError --------------------------------------------------------


def test_provider_error_is_catchable_without_importing_a_vendor_sdk():
    with pytest.raises(ProviderError) as caught:
        raise ProviderError("rate limited", provider="deepseek", status_code=429)

    assert caught.value.provider == "deepseek"
    assert caught.value.status_code == 429


def test_provider_error_names_the_backend_in_its_message():
    assert str(ProviderError("boom", provider="openai")) == "[openai] boom"
    assert str(ProviderError("boom")) == "boom"


def test_a_failure_that_never_reached_the_wire_has_no_status_code():
    """How a retry policy tells a 500 from a malformed request."""
    assert ProviderError("bad tool arguments").status_code is None
