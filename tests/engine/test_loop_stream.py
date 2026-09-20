"""Streaming contract for ``omicsclaw.engine.loop`` (plan 0027 §6, task B).

The kernel is shared, so nothing here re-tests convergence or the turn
ceiling — ``test_loop.py`` owns those, and one test below asserts the two
entry points agree rather than trusting that they do. What is left is
everything the blocking path cannot have: the chunk → event mapping, and
the two ways a stream can end without ever saying so (traps 10 and 11).

The fakes are ``test_loop.py``'s, deliberately. A streaming double and a
blocking double that drifted apart would make the equivalence test below
compare two different conversations and pass anyway.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine, Sequence
from typing import Any, TypeVar

import pytest

from omicsclaw.engine import AgentEngine, EngineConfig
from omicsclaw.engine.types import EngineEvent, EngineEventType, StopReason
from omicsclaw.provider import ProviderError
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)
from tests.engine.test_loop import (  # type: ignore[import-not-found]
    RecordingExecutor,
    ScriptedProvider,
    _acts,
    _answers,
    _call,
)

_T = TypeVar("_T")

_DEADLINE = 5.0
"""Seconds any one scenario may take. A hang guard, not a measurement."""


class StreamingProvider:
    """A model that streams the chunks it was told to stream.

    ``generate_stream`` is not ``async def``, following the Protocol: it
    hands back the iterator directly. ``generate`` is a landmine, because
    "the streaming path never blocks" is only worth asserting if reaching
    the blocking path is loud.
    """

    def __init__(self, *turns: Sequence[StreamChunk]) -> None:
        self._turns = list(turns)
        self.seen: list[tuple[Sequence[Message], tuple[ToolDefinition, ...]]]
        self.seen = []

    @property
    def name(self) -> str:
        return "streamer"

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Any:
        raise AssertionError("run_stream() must never reach the blocking path")

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.seen.append((messages, tuple(tools or ())))
        turn = self._turns[min(len(self.seen) - 1, len(self._turns) - 1)]
        return self._emit(turn)

    async def _emit(self, chunks: Sequence[StreamChunk]) -> AsyncIterator[StreamChunk]:
        for chunk in chunks:
            yield chunk

    def bind(self, **overrides: Any) -> StreamingProvider:
        return self


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


def _collect(
    provider: StreamingProvider,
    executor: RecordingExecutor | None = None,
    conversation: Sequence[Message] = (),
    config: EngineConfig | None = None,
) -> list[EngineEvent]:
    engine = AgentEngine(provider, executor or RecordingExecutor(), config)

    async def scenario() -> list[EngineEvent]:
        return [event async for event in engine.run_stream(conversation)]

    return _run(scenario())


def _spoke(
    text: str = "three markers",
    *,
    usage: Usage | None = None,
    finish_reason: str = "stop",
    calls: Sequence[ToolCall] = (),
) -> tuple[StreamChunk, ...]:
    """One turn's worth of chunks: the text, then the assembled DONE."""
    return (
        StreamChunk.text(text),
        StreamChunk.done(
            Message.assistant(text, tool_calls=tuple(calls)),
            usage,
            finish_reason,
        ),
    )


def _types(events: Sequence[EngineEvent]) -> list[EngineEventType]:
    return [event.type for event in events]


# --- the chunk to event mapping -------------------------------------------


def test_a_converging_turn_streams_its_text_then_ends_the_turn_then_done():
    events = _collect(StreamingProvider(_spoke("three markers")))

    assert _types(events) == [
        EngineEventType.TEXT_DELTA,
        EngineEventType.TURN_END,
        EngineEventType.DONE,
    ]
    assert events[0].delta == "three markers"


def test_thought_tokens_keep_an_event_type_of_their_own():
    """So a Surface can render or hide the Reasoning half of ReAct
    without parsing it back out of the text."""
    provider = StreamingProvider(
        (
            StreamChunk.reasoning("the user wants markers"),
            StreamChunk.text("three markers"),
            StreamChunk.done(Message.assistant("three markers")),
        )
    )

    events = _collect(provider)

    assert _types(events)[:2] == [
        EngineEventType.REASONING_DELTA,
        EngineEventType.TEXT_DELTA,
    ]
    assert events[0].delta == "the user wants markers"


def test_every_event_is_stamped_with_the_turn_that_produced_it():
    """Without it a Surface cannot attribute a late tool result to the
    turn that asked for it."""
    provider = StreamingProvider(
        _spoke("looking", calls=[_call(1)], finish_reason="tool_calls"),
        _spoke("found it"),
    )

    events = _collect(provider)

    turns = [(event.type, event.turn) for event in events]
    assert turns == [
        (EngineEventType.TEXT_DELTA, 1),
        (EngineEventType.TOOL_START, 1),
        (EngineEventType.TOOL_RESULT, 1),
        (EngineEventType.TURN_END, 1),
        (EngineEventType.TEXT_DELTA, 2),
        (EngineEventType.TURN_END, 2),
        (EngineEventType.DONE, 0),
    ]


def test_the_turn_end_carries_what_that_turn_actually_cost():
    """The measured figure, never an estimate. A consumer can trust it
    instead of having to ask which kind it received."""
    provider = StreamingProvider(
        _spoke(usage=Usage(input_tokens=11, output_tokens=4)),
    )

    events = _collect(provider)
    turn_end = [e for e in events if e.type is EngineEventType.TURN_END][0]

    assert turn_end.usage == Usage(input_tokens=11, output_tokens=4)


def test_the_turn_end_carries_no_usage_when_the_backend_reported_none():
    """``EngineEvent.usage`` promises ``None`` for a backend that says
    nothing, and zeros would claim the turn was free."""
    events = _collect(StreamingProvider(_spoke(usage=None)))
    turn_end = [e for e in events if e.type is EngineEventType.TURN_END][0]

    assert turn_end.usage is None


def test_tool_events_sit_between_the_turn_that_asked_and_the_one_that_answered():
    """Start and result are interleaved per tool rather than batched.

    These two tools never suspend, so each finishes before its sibling is
    scheduled — the executor emits each event when it happens, and the
    kernel forwards them without collecting them into phases.
    """
    provider = StreamingProvider(
        _spoke("looking", calls=[_call(1), _call(2)], finish_reason="tool_calls"),
        _spoke("found it"),
    )

    events = _collect(provider)

    assert _types(events) == [
        EngineEventType.TEXT_DELTA,
        EngineEventType.TOOL_START,
        EngineEventType.TOOL_RESULT,
        EngineEventType.TOOL_START,
        EngineEventType.TOOL_RESULT,
        EngineEventType.TURN_END,
        EngineEventType.TEXT_DELTA,
        EngineEventType.TURN_END,
        EngineEventType.DONE,
    ]
    started = [e.tool_call.id for e in events if e.tool_call]
    assert started == ["c1", "c2"]


def test_the_done_event_carries_the_whole_run_result():
    provider = StreamingProvider(
        _spoke("looking", calls=[_call(1)], finish_reason="tool_calls"),
        _spoke("found it", usage=Usage(input_tokens=2)),
    )

    events = _collect(provider, conversation=[Message.user("go")])
    result = events[-1].result

    assert events[-1].type is EngineEventType.DONE
    assert result is not None
    assert result.stop_reason is StopReason.CONVERGED
    assert result.turns == 2
    assert [m.role for m in result.messages] == [
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
    ]


def test_the_done_event_is_the_last_thing_a_stream_ever_yields():
    provider = StreamingProvider(
        _spoke("looking", calls=[_call(1)], finish_reason="tool_calls"),
        _spoke("found it"),
    )

    events = _collect(provider)

    assert _types(events).count(EngineEventType.DONE) == 1
    assert events[-1].type is EngineEventType.DONE


# --- the two entry points are one kernel ----------------------------------


def test_a_streamed_run_and_a_blocking_run_agree_on_the_same_conversation():
    """The claim the whole design rests on: one copy of the turn / tool /
    Observation logic, wearing two mouths. Two implementations would
    drift here first — and quietly, since each would still look correct
    on its own.
    """
    conversation = [Message.user("run the DE")]
    streamed = _collect(
        StreamingProvider(
            _spoke("looking", calls=[_call(1)], finish_reason="tool_calls"),
            _spoke("found it", usage=Usage(input_tokens=7)),
        ),
        conversation=conversation,
    )
    blocking = AgentEngine(
        ScriptedProvider(
            _acts(_call(1), text="looking"),
            _answers("found it", usage=Usage(input_tokens=7)),
        ),
        RecordingExecutor(),
    )

    assert streamed[-1].result == _run(blocking.run(conversation))


def test_the_streaming_path_never_reaches_the_blocking_entry_point():
    provider = StreamingProvider(_spoke())

    events = _collect(provider)

    assert events[-1].result is not None
    with pytest.raises(AssertionError):
        _run(provider.generate(()))


def test_run_stream_hands_back_its_iterator_without_being_awaited():
    """Following ``LLMProvider.generate_stream``: callers write ``async
    for event in engine.run_stream(…)`` with no intervening ``await``."""
    engine = AgentEngine(StreamingProvider(_spoke()), RecordingExecutor())

    stream = engine.run_stream([])

    assert not asyncio.iscoroutine(stream)
    assert hasattr(stream, "__aiter__")
    _run(_drain(stream))


async def _drain(stream: AsyncIterator[EngineEvent]) -> list[EngineEvent]:
    return [event async for event in stream]


# --- trap 3 on the streaming path -----------------------------------------


def test_a_truncated_stream_does_not_execute_the_calls_it_accumulated():
    """This is the path the trap was written for: a call accumulated from
    a stream that stopped mid-argument may be half-parsed, and the
    ``finish_reason`` on the DONE chunk is the only thing that says so."""
    provider = StreamingProvider(
        _spoke(
            "I will remo",
            calls=[_call(1, "delete_everything")],
            finish_reason="length",
        )
    )
    executor = RecordingExecutor()

    events = _collect(provider, executor)

    assert executor.executed == []
    assert _types(events) == [
        EngineEventType.TEXT_DELTA,
        EngineEventType.TURN_END,
        EngineEventType.DONE,
    ]
    assert events[-1].result.stop_reason is StopReason.TRUNCATED


# --- trap 10: an error chunk is a failure, not a quiet turn ---------------


def test_an_error_chunk_becomes_a_raised_provider_error():
    """Neither shipped adapter emits one, but a third-party adapter
    satisfying the Protocol structurally may — and ignoring it would turn
    a failed stream into a turn that merely said nothing."""
    provider = StreamingProvider(
        (StreamChunk.text("par"), StreamChunk.failed("upstream reset"))
    )

    with pytest.raises(ProviderError) as raised:
        _collect(provider, config=EngineConfig(generate_retries=1))

    assert "upstream reset" in str(raised.value)
    assert raised.value.provider == "streamer"


def test_an_error_chunk_is_retried_like_any_other_provider_failure():
    """Converting it to the layer's own exception type is what puts it
    inside the retry budget, rather than beside it."""
    provider = StreamingProvider(
        (StreamChunk.failed("upstream reset"),), _spoke("recovered")
    )
    config = EngineConfig(generate_retries=2, generate_retry_base=0.001)

    events = _collect(provider, config=config)

    assert len(provider.seen) == 2
    assert events[-1].result.final_message == Message.assistant("recovered")


# --- trap 11: a stream that stops is not a stream that finished ----------

_ONE_ATTEMPT = EngineConfig(generate_retries=1)
"""Retrying is the subject of three tests below; everywhere else a dead
stream should fail once and say why, without paying any backoff."""


def test_a_stream_that_ends_without_a_done_chunk_is_a_contract_violation():
    """Reading it as an empty turn would report success on a connection
    that died — and the run would carry on, one message short."""
    provider = StreamingProvider((StreamChunk.text("half an ans"),))

    with pytest.raises(ProviderError) as raised:
        _collect(provider, config=_ONE_ATTEMPT)

    assert "DONE" in str(raised.value)
    assert raised.value.provider == "streamer"


def test_a_done_chunk_carrying_no_message_is_not_an_empty_turn_either():
    """The other half of the same contract: a DONE that assembled
    nothing is as dead as a stream that never sent one."""
    provider = StreamingProvider(
        (StreamChunk(type=StreamChunkType.DONE, message=None),),
    )

    with pytest.raises(ProviderError):
        _collect(provider, config=_ONE_ATTEMPT)


def test_a_dead_stream_is_the_providers_contract_breaking_and_so_is_retried():
    """R6, and the scenario ``retry.py``'s own docstring opens with.

    "A proxy that drops a half-streamed response" is the failure that
    module exists to absorb — and while a dead stream was attributed to
    the engine, it was the one failure the module could not absorb: not a
    ``ProviderError``, therefore not caught, therefore fatal on first
    occurrence. The reference harness returns an ordinary error here and
    gives the turn its three attempts.
    """
    provider = StreamingProvider((StreamChunk.text("half"),), _spoke("recovered"))
    config = EngineConfig(generate_retries=3, generate_retry_base=0.001)

    events = _collect(provider, config=config)

    assert len(provider.seen) == 2
    assert events[-1].result.final_message == Message.assistant("recovered")
    assert events[-1].result.stop_reason is StopReason.CONVERGED


def test_a_stream_that_keeps_dying_still_ends_the_run_once_the_budget_is_out():
    """The other side of the boundary: retryable is not infinite."""
    provider = StreamingProvider((StreamChunk.text("half"),))
    config = EngineConfig(generate_retries=3, generate_retry_base=0.001)

    with pytest.raises(ProviderError):
        _collect(provider, config=config)

    assert len(provider.seen) == 3


def test_a_generate_stream_that_handed_back_no_iterator_is_retried_too():
    """R8 on this side: the streaming shape of "the provider returned
    nothing".

    ``async for`` over it raises ``TypeError: 'NoneType' object is not
    async iterable``, which no budget catches and no strategy expects —
    the same crash the blocking path takes on ``None``, arriving through
    a different door. Structural typing lets it in either way.
    """

    class NoStreamProvider(StreamingProvider):
        def generate_stream(self, messages, tools=None):
            self.seen.append((messages, tuple(tools or ())))
            return None

    provider = NoStreamProvider()
    config = EngineConfig(generate_retries=3, generate_retry_base=0.001)

    with pytest.raises(ProviderError) as raised:
        _collect(provider, config=config)

    assert len(provider.seen) == 3
    assert "no completion" in str(raised.value)


def test_a_generate_stream_that_handed_back_a_plain_list_is_retried_too():
    """``None`` is not the only way to hand back something unusable.

    ``generate_stream`` is documented as returning the iterator directly
    rather than awaiting one, and the easy misreading of that is to build
    the chunks eagerly and return the list. It is not async-iterable, so
    the crash is the same class as the ``None`` case — a ``TypeError``
    outside every budget — and so is the correct answer: one wasted
    attempt, not a dead run.

    The guard tests for ``__aiter__`` rather than for ``None``, which is
    the structural check this layer argues for and not an exception to
    it: possessing ``__aiter__`` *is* what makes something an async
    iterable, so nothing legitimate is turned away.
    """

    class ListStreamProvider(StreamingProvider):
        def generate_stream(self, messages, tools=None):
            self.seen.append((messages, tuple(tools or ())))
            return [StreamChunk.text("eagerly"), _spoke("built")]

    provider = ListStreamProvider()
    config = EngineConfig(generate_retries=2, generate_retry_base=0.001)

    with pytest.raises(ProviderError) as raised:
        _collect(provider, config=config)

    assert len(provider.seen) == 2
    assert "no completion" in str(raised.value)


def test_a_retried_turn_never_reports_the_answer_of_the_attempt_that_failed():
    """R5. The outcome holder is per turn, so it outlives an attempt.

    Attempt 1 here delivers a usable ``DONE`` and *then* fails, leaving a
    perfectly well-formed completion in the holder. Attempt 2 dies
    without delivering one. Unless the holder is emptied before each
    attempt, the check that is supposed to notice attempt 2's silence
    reads attempt 1's answer instead, finds nothing wrong, and the run
    converges — reporting a reply the provider took back as the model's
    final word.
    """
    provider = StreamingProvider(
        (
            StreamChunk.text("stale"),
            StreamChunk.done(Message.assistant("stale answer")),
            StreamChunk.failed("upstream reset"),
        ),
        (StreamChunk.text("half"),),
    )
    config = EngineConfig(generate_retries=2, generate_retry_base=0.001)

    with pytest.raises(ProviderError):
        _collect(provider, config=config)

    assert len(provider.seen) == 2


# --- liveness and cancellation --------------------------------------------


def test_a_delta_reaches_the_consumer_before_the_turn_it_belongs_to_ends():
    """Otherwise this is not streaming, it is a slow blocking call that
    yields its whole answer at the end."""

    async def scenario() -> tuple[EngineEvent, bool]:
        released = asyncio.Event()

        class GatedProvider(StreamingProvider):
            async def _emit(self, chunks):
                yield StreamChunk.text("first")
                await released.wait()
                yield StreamChunk.done(Message.assistant("first and then some"))

        engine = AgentEngine(GatedProvider(()), RecordingExecutor())
        stream = engine.run_stream([])
        first = await anext(stream)
        still_gated = not released.is_set()
        released.set()
        await _drain(stream)
        return first, still_gated

    first, still_gated = _run(scenario())

    assert still_gated
    assert first.type is EngineEventType.TEXT_DELTA
    assert first.delta == "first"


def test_abandoning_the_stream_leaves_no_tool_still_running():
    """A consumer that walks away mid-turn must not orphan the turn's
    tools. The kernel closes what it opened; without that the workers
    outlive the stream that created them, still holding whatever the tool
    layer gave them.
    """

    async def scenario() -> int:
        blocked = asyncio.Event()
        observed = {"cancelled": 0}

        async def behaviour(call: ToolCall) -> ToolResult:
            try:
                await blocked.wait()
            except asyncio.CancelledError:
                observed["cancelled"] += 1
                raise
            raise AssertionError("unreachable")  # pragma: no cover

        provider = StreamingProvider(
            _spoke("acting", calls=[_call(1), _call(2)], finish_reason="tool_calls")
        )
        engine = AgentEngine(provider, RecordingExecutor(behaviour=behaviour))
        stream = engine.run_stream([])
        while True:
            event = await anext(stream)
            if event.type is EngineEventType.TOOL_START:
                break
        await stream.aclose()
        return observed["cancelled"]

    assert _run(scenario()) == 2


def test_abandoning_the_stream_closes_the_providers_stream_too():
    """Both shipped adapters release their HTTP connection in a
    ``finally`` that only runs when a ``GeneratorExit`` reaches their
    yield. So the closure has to travel the whole way down — kernel, then
    retry, then turn strategy, then the adapter — and a plain ``async
    for`` anywhere along it breaks the chain and leaks the socket until
    the garbage collector happens to notice.
    """

    async def scenario() -> bool:
        closed = asyncio.Event()

        class ClosableProvider(StreamingProvider):
            async def _emit(self, chunks):
                try:
                    yield StreamChunk.text("first")
                    yield StreamChunk.done(Message.assistant("first"))
                finally:
                    closed.set()

        engine = AgentEngine(ClosableProvider(()), RecordingExecutor())
        stream = engine.run_stream([])
        await anext(stream)
        assert not closed.is_set()
        await stream.aclose()
        return closed.is_set()

    assert _run(scenario())


def test_a_cancelled_stream_stays_cancelled():
    """Trap 4 on the streaming path: ``CancelledError`` propagates
    untouched rather than ending the run with a ``DONE`` event that would
    read as success."""

    async def scenario() -> tuple[bool, BaseException]:
        reached = asyncio.Event()

        class HangingProvider(StreamingProvider):
            async def _emit(self, chunks):
                reached.set()
                await asyncio.Event().wait()
                yield StreamChunk.text("unreachable")  # pragma: no cover

        engine = AgentEngine(HangingProvider(()), RecordingExecutor())
        task = asyncio.ensure_future(_drain(engine.run_stream([])))
        await reached.wait()
        task.cancel()
        outcome = (await asyncio.gather(task, return_exceptions=True))[0]
        return task.cancelled(), outcome

    cancelled, outcome = _run(scenario())

    assert cancelled
    assert isinstance(outcome, asyncio.CancelledError)
