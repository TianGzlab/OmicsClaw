"""Contract tests for ``omicsclaw.engine.types`` (plan 0027 §2).

Most of what these types are worth is what they refuse to carry. There
is no ``StopReason.ERROR`` and no ``EngineEventType.ERROR``, because a
failure is raised rather than returned, and several tests below exist
only to go red the day somebody adds one back.

No provider, no tool and no loop is involved: these are data shapes, so
the assertions are about shape.
"""

from __future__ import annotations

import pytest

from omicsclaw.engine import types as types_module
from omicsclaw.engine.types import (
    EngineError,
    EngineEvent,
    EngineEventType,
    RunResult,
    StopReason,
)
from omicsclaw.provider import ProviderError
from omicsclaw.schema import Message, ToolCall, ToolResult, Usage


def _result(*messages: Message) -> RunResult:
    return RunResult(messages=messages, stop_reason=StopReason.CONVERGED)


# --- StopReason -----------------------------------------------------------


def test_stop_reason_compares_equal_to_its_literal():
    """A ``StrEnum``, so a stored or logged run reason round-trips."""
    assert StopReason.CONVERGED == "converged"
    assert StopReason.MAX_TURNS == "max_turns"
    assert StopReason.TRUNCATED == "truncated"
    assert StopReason("max_turns") is StopReason.MAX_TURNS


def test_a_run_stops_in_exactly_three_ways():
    assert {reason.value for reason in StopReason} == {
        "converged",
        "max_turns",
        "truncated",
    }


def test_there_is_no_stop_reason_for_a_failure_or_for_a_cancellation():
    """Plan 0027 §4 Q3: neither is a return value.

    A ``ProviderError`` propagates and a ``CancelledError`` propagates
    untouched, so a ``RunResult`` exists only when the loop stopped on
    its own terms. An ``ERROR`` member would invite a caller to check
    ``stop_reason`` for "did this actually work", which is precisely the
    question raising already answers.
    """
    assert not hasattr(StopReason, "ERROR")
    assert not hasattr(StopReason, "CANCELLED")
    with pytest.raises(ValueError):
        StopReason("error")
    with pytest.raises(ValueError):
        StopReason("cancelled")


def test_a_truncated_run_is_distinguishable_from_a_converged_one():
    """Both end with an assistant turn requesting no tools.

    If the two shared a value they would collapse into one enum member
    and a severed answer would be reported as a completed task.
    """
    assert StopReason.TRUNCATED is not StopReason.CONVERGED
    assert StopReason.TRUNCATED.value != StopReason.CONVERGED.value


# --- RunResult ------------------------------------------------------------


def test_final_message_is_the_last_message_of_the_trajectory():
    first = Message.user("run the spatial DE skill")
    last = Message.assistant("here are the markers")
    assert _result(first, last).final_message == last


def test_final_message_is_none_when_the_trajectory_is_empty():
    """An empty conversation is useless, not an error — reaching for the
    answer must not have to be guarded by a length check."""
    assert _result().final_message is None


def test_run_result_is_frozen():
    """A record of what happened that can be edited is not evidence."""
    result = _result(Message.assistant("done"))
    with pytest.raises(Exception):
        result.stop_reason = StopReason.MAX_TURNS  # type: ignore[misc]


def test_run_result_defaults_to_zero_usage_rather_than_to_none():
    """Totalling a session's cost is a plain sum with no ``None`` branch."""
    result = _result()
    assert result.usage == Usage()
    assert result.usage + Usage(input_tokens=3) == Usage(input_tokens=3)


def test_run_result_defaults_to_having_made_no_turns():
    assert _result().turns == 0


def test_a_run_that_hit_the_turn_ceiling_still_returns_its_work():
    """The reference harness discards the trajectory here; this does not."""
    messages = (Message.user("go"), Message.assistant("still working"))
    result = RunResult(
        messages=messages,
        stop_reason=StopReason.MAX_TURNS,
        usage=Usage(input_tokens=10, output_tokens=4),
        turns=50,
    )
    assert result.messages == messages
    assert result.final_message == messages[-1]
    assert result.usage.total_tokens == 14


# --- EngineEventType ------------------------------------------------------


def test_engine_event_type_compares_equal_to_its_literal():
    assert EngineEventType.TEXT_DELTA == "text_delta"
    assert EngineEventType.REASONING_DELTA == "reasoning_delta"
    assert EngineEventType.TOOL_START == "tool_start"
    assert EngineEventType.TOOL_RESULT == "tool_result"
    assert EngineEventType.TURN_END == "turn_end"
    assert EngineEventType.DONE == "done"


def test_there_is_no_error_event_because_a_failure_is_raised_instead():
    """An async generator can carry an exception; a Go channel cannot.

    The consumer's ``async for`` re-raises at the iteration point, so an
    error event would only force every consumer to hand-write a branch
    the language already provides.
    """
    assert {kind.value for kind in EngineEventType} == {
        "text_delta",
        "reasoning_delta",
        "tool_start",
        "tool_result",
        "turn_end",
        "done",
    }
    with pytest.raises(ValueError):
        EngineEventType("error")


# --- EngineEvent ----------------------------------------------------------


def test_a_text_event_carries_the_delta_and_the_turn_it_belongs_to():
    event = EngineEvent.text("mark", turn=3)
    assert event.type is EngineEventType.TEXT_DELTA
    assert event.delta == "mark"
    assert event.turn == 3


def test_reasoning_is_tagged_separately_from_assistant_text():
    """A Surface must be able to hide the Thought without parsing it out."""
    event = EngineEvent.reasoning("the user wants markers", turn=1)
    assert event.type is EngineEventType.REASONING_DELTA
    assert event.delta == "the user wants markers"
    assert EngineEvent.text("x").type is not EngineEvent.reasoning("x").type


def test_a_tool_start_event_carries_the_call_about_to_run():
    call = ToolCall(id="c1", name="spatial_de", arguments='{"demo": true}')
    event = EngineEvent.tool_start(call, turn=2)
    assert event.type is EngineEventType.TOOL_START
    assert event.tool_call == call
    assert event.turn == 2
    assert event.tool_result is None


def test_a_finished_tool_event_carries_the_observation_errors_included():
    result = ToolResult(tool_call_id="c1", name="spatial_de", output="", is_error=True)
    event = EngineEvent.tool_finished(result, turn=2)
    assert event.type is EngineEventType.TOOL_RESULT
    assert event.tool_result == result
    assert event.tool_result.is_error
    assert event.tool_call is None


def test_the_finished_tool_constructor_is_not_named_tool_done():
    """``done`` already means "the whole run ended" on this type.

    A ``tool_done`` sitting beside ``done`` would spell one word for two
    different scopes, which is a trap rather than a convenience.
    """
    assert hasattr(EngineEvent, "tool_finished")
    assert not hasattr(EngineEvent, "tool_done")


def test_a_turn_end_event_carries_the_turns_actual_token_cost():
    usage = Usage(input_tokens=120, output_tokens=17, cache_read_tokens=100)
    event = EngineEvent.turn_end(4, usage)
    assert event.type is EngineEventType.TURN_END
    assert event.turn == 4
    assert event.usage == usage


def test_turn_end_usage_is_none_when_the_backend_reported_nothing():
    """``None`` rather than zeros, so "not reported" stays distinguishable
    from "genuinely cost nothing"."""
    assert EngineEvent.turn_end(1).usage is None


def test_the_done_event_carries_the_whole_run_result():
    result = _result(Message.assistant("here are the markers"))
    event = EngineEvent.done(result)
    assert event.type is EngineEventType.DONE
    assert event.result is result


def test_an_event_belongs_to_no_turn_until_one_is_given():
    assert EngineEvent.text("a").turn == 0
    assert EngineEvent.reasoning("a").turn == 0
    assert EngineEvent.tool_start(ToolCall(id="c", name="t")).turn == 0
    assert EngineEvent.tool_finished(ToolResult(tool_call_id="c")).turn == 0
    assert EngineEvent.done(_result()).turn == 0


def test_engine_event_is_frozen():
    event = EngineEvent.text("mark")
    with pytest.raises(Exception):
        event.delta = "rewritten"  # type: ignore[misc]


# --- EngineError ----------------------------------------------------------


def test_engine_error_is_a_runtime_error():
    with pytest.raises(RuntimeError):
        raise EngineError("provider stream ended without a done chunk")


def test_a_provider_failure_is_not_an_engine_error():
    """``except EngineError`` must never swallow a backend outage.

    The two questions — did the model fail, did we break our own
    invariant — stay separately answerable only while the types are
    unrelated.
    """
    assert not issubclass(ProviderError, EngineError)
    assert not issubclass(EngineError, ProviderError)
    with pytest.raises(ProviderError):
        try:
            raise ProviderError("rate limited", provider="deepseek", status_code=429)
        except EngineError:  # pragma: no cover — must not match
            pytest.fail("a ProviderError was caught as an EngineError")


# --- the module's public surface ------------------------------------------


def test_the_module_exports_exactly_its_five_public_names():
    assert types_module.__all__ == [
        "EngineError",
        "EngineEvent",
        "EngineEventType",
        "RunResult",
        "StopReason",
    ]
