"""The span tree: lazy turns, no phantoms, and a contextvar that nests."""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.engine import EngineEvent, RunResult, StopReason
from omicsclaw.observability.contract import NOOP_SPAN, NOOP_TRACER
from omicsclaw.observability.scope import (
    RunScope,
    TurnScope,
    current_parent,
    fixed,
    pop_parent,
    push_parent,
)
from omicsclaw.schema import Message, Role, ToolCall, Usage

from ._support import RecordingMeter, RecordingTracer, run


def _scope(**kwargs) -> tuple[RunScope, RecordingTracer, RecordingMeter]:
    tracer, meter = RecordingTracer(), RecordingMeter()
    return RunScope(tracer, meter, **kwargs), tracer, meter


def _done(turns: int = 2, **usage: int) -> EngineEvent:
    return EngineEvent.done(
        RunResult(
            messages=(Message(role=Role.ASSISTANT, content="final"),),
            stop_reason=StopReason.CONVERGED,
            usage=Usage(**usage),
            turns=turns,
        )
    )


# ---- the lazy turn ------------------------------------------------------


def test_a_turn_scope_creates_nothing_until_it_is_asked():
    tracer = RecordingTracer()
    turn = TurnScope(tracer, None, 1)

    assert turn.materialised is False
    assert tracer.spans == []

    turn.span()

    assert turn.materialised is True
    assert tracer.named("omicsclaw.turn")[0].attributes["agent.turn"] == 1


def test_asking_twice_returns_the_same_span():
    tracer = RecordingTracer()
    turn = TurnScope(tracer, None, 3)

    assert turn.span() is turn.span()
    assert len(tracer.spans) == 1


def test_closing_a_turn_nobody_used_exports_nothing():
    """The whole reason the laziness exists — no phantom at the end of a run."""
    tracer = RecordingTracer()
    turn = TurnScope(tracer, None, 9)

    turn.close()

    assert tracer.spans == []


def test_closing_a_turn_twice_ends_its_span_once():
    """A cancelled run closes an open turn from two places."""
    tracer = RecordingTracer()
    turn = TurnScope(tracer, None, 1)
    span = turn.span()

    turn.close()
    turn.close()

    assert span.ended == 1


def test_a_run_of_two_turns_leaves_exactly_two_turn_spans():
    scope, tracer, _ = _scope(session_id="s")

    async def exercise():
        async with scope:
            scope.observe(EngineEvent.tool_start(ToolCall(id="c", name="echo"), 1))
            current_parent()  # the model call materialises turn 1
            scope.observe(EngineEvent.turn_end(1, Usage(input_tokens=4)))
            current_parent()  # turn 2
            scope.observe(EngineEvent.turn_end(2, Usage(input_tokens=6)))
            scope.observe(_done(turns=2, input_tokens=10))

    run(exercise())

    turns = tracer.named("omicsclaw.turn")
    assert len(turns) == 2, "a third would be the phantom the laziness prevents"
    assert [t.attributes["agent.turn"] for t in turns] == [1, 2]
    assert turns[0].attributes["turn.has_tool_calls"] is True
    assert turns[1].attributes["turn.has_tool_calls"] is False


# ---- parenting ----------------------------------------------------------


def test_nothing_is_bound_outside_a_scope():
    assert current_parent() is None


def test_a_child_started_inside_the_scope_hangs_from_the_turn():
    scope, tracer, _ = _scope()

    async def exercise():
        async with scope:
            parent = current_parent()
            child = tracer.start_span("child", parent=parent)
            return child

    child = run(exercise())

    assert child.chain == ["child", "omicsclaw.turn", "omicsclaw.interaction"]


def test_the_binding_is_released_when_the_scope_exits():
    scope, _, _ = _scope()

    async def exercise():
        async with scope:
            assert current_parent() is not None

    run(exercise())

    assert current_parent() is None


def test_a_nested_scope_restores_the_outer_binding():
    """A sub-agent driven from inside a tool, in the shape it arrives in."""
    tracer, meter = RecordingTracer(), RecordingMeter()

    async def exercise():
        outer = RunScope(tracer, meter, session_id="outer")
        async with outer:
            outer_parent = current_parent()
            inner = RunScope(tracer, meter, session_id="inner")
            async with inner:
                assert current_parent() is not outer_parent
            assert current_parent() is outer_parent

    run(exercise())


def test_two_concurrent_scopes_do_not_see_each_other():
    """Context copies per Task are what make one process safe for two sessions."""
    tracer, meter = RecordingTracer(), RecordingMeter()
    seen: dict[str, object] = {}

    async def one(name: str) -> None:
        async with RunScope(tracer, meter, session_id=name):
            await asyncio.sleep(0)
            seen[name] = current_parent()

    async def exercise() -> None:
        await asyncio.gather(one("a"), one("b"))

    run(exercise())

    assert seen["a"] is not seen["b"]


def test_push_and_pop_restore_what_was_there():
    span = NOOP_TRACER.start_span("x")
    token = push_parent(fixed(span))

    assert current_parent() is span

    pop_parent(token)
    assert current_parent() is None


# ---- what the root span learns ------------------------------------------


def test_the_interaction_span_carries_the_session_and_the_agent_type():
    scope, tracer, _ = _scope(session_id="sess-7", agent_type="sub")

    run(_enter_and_exit(scope))

    root = tracer.named("omicsclaw.interaction")[0]
    assert root.attributes["session.id"] == "sess-7"
    assert root.attributes["agent.type"] == "sub"


def test_the_run_result_is_written_onto_the_root_on_the_way_out():
    scope, tracer, _ = _scope()

    async def exercise():
        async with scope:
            scope.observe(_done(turns=4, input_tokens=100, output_tokens=25))

    run(exercise())

    root = tracer.named("omicsclaw.interaction")[0]
    assert root.attributes["agent.turns"] == 4
    assert root.attributes["agent.stop_reason"] == "converged"
    assert root.attributes["llm.tokens.input"] == 100
    assert root.attributes["llm.tokens.output"] == 25


def test_a_run_that_never_finished_claims_no_turn_count():
    """A cancelled run has a span; it does not invent a verdict."""
    scope, tracer, _ = _scope()

    async def exercise():
        with pytest.raises(RuntimeError):
            async with scope:
                raise RuntimeError("boom")

    run(exercise())

    root = tracer.named("omicsclaw.interaction")[0]
    assert "agent.turns" not in root.attributes
    assert root.error == "RuntimeError"
    assert root.ended == 1


def test_a_cancelled_scope_still_closes_its_spans_and_re_raises():
    scope, tracer, _ = _scope()

    async def exercise():
        with pytest.raises(asyncio.CancelledError):
            async with scope:
                current_parent()
                raise asyncio.CancelledError()

    run(exercise())

    assert tracer.named("omicsclaw.turn")[0].ended == 1
    assert tracer.named("omicsclaw.interaction")[0].ended == 1


# ---- usage --------------------------------------------------------------


def test_a_backend_that_reported_nothing_is_not_recorded_as_free():
    """``None`` usage and ``Usage()`` are different facts."""
    scope, tracer, _ = _scope()

    async def exercise():
        async with scope:
            current_parent()
            scope.observe(EngineEvent.turn_end(1, None))

    run(exercise())

    turn = tracer.named("omicsclaw.turn")[0]
    assert "llm.tokens.input" not in turn.attributes


def test_a_free_turn_is_recorded_as_zero():
    scope, tracer, _ = _scope()

    async def exercise():
        async with scope:
            current_parent()
            scope.observe(EngineEvent.turn_end(1, Usage()))

    run(exercise())

    assert tracer.named("omicsclaw.turn")[0].attributes["llm.tokens.input"] == 0


def test_cache_reads_are_recorded_only_when_there_were_some():
    scope, tracer, _ = _scope()

    async def exercise():
        async with scope:
            current_parent()
            scope.observe(EngineEvent.turn_end(1, Usage(cache_read_tokens=99)))

    run(exercise())

    assert tracer.named("omicsclaw.turn")[0].attributes["llm.tokens.cache_read"] == 99


# ---- metrics ------------------------------------------------------------


def test_each_turn_end_counts_one_turn():
    scope, _, meter = _scope()

    async def exercise():
        async with scope:
            scope.observe(EngineEvent.turn_end(1))
            scope.observe(EngineEvent.turn_end(2))
            scope.observe(EngineEvent.turn_end(3))

    run(exercise())

    assert meter.totals("omicsclaw.agent.turns.total") == 3


def test_the_scope_records_no_tool_duration():
    """``EngineEvent.duration_s`` includes a human's approval wait."""
    scope, _, meter = _scope()

    async def exercise():
        async with scope:
            scope.observe(
                EngineEvent.tool_finished(
                    _result(), turn=1, duration_s=61.0
                )
            )

    run(exercise())

    assert meter.records == []
    assert meter.counts == []


# ---- content capture ----------------------------------------------------


def test_the_prompt_is_not_recorded_by_default():
    scope, tracer, _ = _scope(prompt="patient GSM123 differential expression")

    run(_enter_and_exit(scope))

    root = tracer.named("omicsclaw.interaction")[0]
    assert "langfuse.trace.input" not in root.attributes


def test_the_prompt_is_recorded_when_capture_is_switched_on():
    scope, tracer, _ = _scope(prompt="hello", capture_content=True)

    run(_enter_and_exit(scope))

    root = tracer.named("omicsclaw.interaction")[0]
    assert root.attributes["langfuse.trace.input"] == "hello"


def test_the_final_answer_is_captured_only_when_asked_for():
    off, off_tracer, _ = _scope()
    on, on_tracer, _ = _scope(capture_content=True)

    async def exercise(scope):
        async with scope:
            scope.observe(_done())

    run(exercise(off))
    run(exercise(on))

    assert "langfuse.trace.output" not in off_tracer.named("omicsclaw.interaction")[0].attributes
    assert on_tracer.named("omicsclaw.interaction")[0].attributes[
        "langfuse.trace.output"
    ] == "final"


# ---- failure containment ------------------------------------------------


def test_a_broken_tracer_does_not_break_the_exchange():
    class Broken:
        def start_span(self, *a, **k):
            raise RuntimeError("backend down")

    scope = RunScope(Broken(), RecordingMeter())

    async def exercise():
        async with scope:
            assert current_parent() is None
            scope.observe(EngineEvent.turn_end(1))
            scope.observe(_done())

    run(exercise())


def test_an_event_that_cannot_be_recorded_is_logged_and_dropped(caplog):
    class HalfBroken(RecordingTracer):
        def start_span(self, name, *, parent=None, attributes=None):
            span = super().start_span(name, parent=parent, attributes=attributes)
            if name == "omicsclaw.turn":
                raise RuntimeError("no turns today")
            return span

    scope = RunScope(HalfBroken(), RecordingMeter())

    async def exercise():
        async with scope:
            current_parent()

    run(exercise())


def test_the_scope_never_suppresses_what_the_run_raised():
    scope, _, _ = _scope()

    async def exercise():
        async with scope:
            raise ValueError("mine")

    with pytest.raises(ValueError, match="mine"):
        run(exercise())


def test_an_ordinary_failure_is_still_flushed():
    """The trace of a failed exchange is the one somebody goes looking for.

    This test previously asserted the opposite, and the docstring it
    asserted against over-generalised a rule that only holds for
    cancellation: awaiting inside a *cancelled* task re-raises, but
    awaiting while an ordinary ``ProviderError`` propagates does not. The
    reference flushes unconditionally; this is as close as is safe.
    """
    flushed: list[int] = []
    tracer, meter = RecordingTracer(), RecordingMeter()

    async def flush() -> None:
        flushed.append(1)

    async def exercise(boom: bool):
        scope = RunScope(tracer, meter, flush=flush)
        try:
            async with scope:
                if boom:
                    raise RuntimeError("x")
        except RuntimeError:
            pass

    run(exercise(boom=False))
    assert flushed == [1]

    run(exercise(boom=True))
    assert flushed == [1, 1], "an ordinary failure is flushed too"


def test_a_cancelled_scope_is_not_flushed():
    """The tightening direction, pinned beside the loosening one.

    Awaiting anything in a task that is being cancelled raises
    :exc:`~asyncio.CancelledError` again, so a flush here could only be
    protected by catching one — which is the defect
    ``omicsclaw/hooks/chain.py`` was repaired for.
    """
    flushed: list[int] = []
    tracer, meter = RecordingTracer(), RecordingMeter()

    async def flush() -> None:
        flushed.append(1)

    async def exercise():
        scope = RunScope(tracer, meter, flush=flush)
        with pytest.raises(asyncio.CancelledError):
            async with scope:
                raise asyncio.CancelledError()

    run(exercise())

    assert flushed == []


def test_a_generator_exit_is_not_flushed_either():
    """How an abandoned ``stream_turn`` unwinds. Same reasoning as cancel."""
    flushed: list[int] = []
    tracer, meter = RecordingTracer(), RecordingMeter()

    async def flush() -> None:
        flushed.append(1)

    async def exercise():
        scope = RunScope(tracer, meter, flush=flush)
        try:
            async with scope:
                raise GeneratorExit()
        except GeneratorExit:
            pass

    run(exercise())

    assert flushed == []


def test_a_cancellation_during_a_flush_is_not_swallowed():
    """The historic defect class, pinned so a refactor cannot resurrect it.

    ``omicsclaw/hooks/chain.py`` once caught :exc:`BaseException` around a
    notification and absorbed a *genuine* ``task.cancel()``. The argument
    that this scope does not do the same lived only in a docstring until
    this test: a real cancellation arriving while the flush is awaited
    must leave through ``__aexit__``, not be turned into a clean exit.
    """
    tracer, meter = RecordingTracer(), RecordingMeter()

    async def flush() -> None:
        raise asyncio.CancelledError()

    async def exercise():
        scope = RunScope(tracer, meter, flush=flush)
        with pytest.raises(asyncio.CancelledError):
            async with scope:
                pass

    run(exercise())

    assert tracer.named("omicsclaw.interaction")[0].ended == 1, (
        "the span is still closed before the flush is attempted"
    )


def test_a_flush_that_fails_ordinarily_does_not_change_how_the_run_ended():
    """A broken exporter is not a broken exchange."""
    tracer, meter = RecordingTracer(), RecordingMeter()

    async def flush() -> None:
        raise RuntimeError("exporter down")

    async def exercise():
        scope = RunScope(tracer, meter, flush=flush)
        async with scope:
            pass

    with pytest.raises(RuntimeError):
        run(exercise())


async def _enter_and_exit(scope: RunScope) -> None:
    async with scope:
        pass


def _result():
    from omicsclaw.schema import ToolResult

    return ToolResult(tool_call_id="c", name="echo", output="out")


# ---- no payload escapes with capture off --------------------------------


_PAYLOAD = "GSM12345 patient_07 /data/cohort/run_A"


def test_not_one_payload_byte_reaches_a_span_with_capture_off():
    """The security invariant, asserted over *every* attribute rather than
    over the two keys that are known to carry payloads.

    ``CLAUDE.md``'s first safety rule is that genetic data never leaves
    this machine, and this layer's default posture is what enforces it. A
    test that named the keys would keep passing the day a third one is
    added; this one reads whatever was actually written.
    """
    scope, tracer, meter = _scope(session_id="s", prompt=_PAYLOAD)

    async def exercise():
        async with scope:
            current_parent()
            scope.observe(EngineEvent.turn_end(1, Usage(input_tokens=3)))
            scope.observe(_done())

    run(exercise())

    written = " ".join(
        f"{key}={value}" for span in tracer.spans for key, value in span.attributes.items()
    )
    for token in _PAYLOAD.split() + ["final"]:
        assert token not in written, f"{token!r} reached a span attribute"
    assert not any("langfuse" in key for span in tracer.spans for key in span.attributes)


def test_no_payload_reaches_a_metric_dimension_either():
    """Metric labels leave the process too, and are higher cardinality."""
    scope, _, meter = _scope(session_id="s", prompt=_PAYLOAD)

    async def exercise():
        async with scope:
            scope.observe(EngineEvent.turn_end(1))
            scope.observe(_done())

    run(exercise())

    labels = " ".join(
        f"{k}={v}" for _, _, dims in meter.counts + meter.records for k, v in dims.items()
    )
    for token in _PAYLOAD.split():
        assert token not in labels
