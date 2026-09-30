"""The span tree of one streamed exchange, through the production assembly.

``tests/observability/test_end_to_end.py`` checks the tree over an
engine assembled by hand, and ``tests/entry/test_telemetry_wiring.py``
goes through ``build_app`` on the blocking path but swaps the provider
in afterwards, so its tree has no ``llm_request`` spans. This runs a
two-turn scripted case through the Runner: ``build_app(provider=)``,
``SessionRegistry.submit`` and the streamed exchange, with a recording
tracer and meter from ``tests/observability/_support.py``.

It lives in ``tests/evals/`` but outside ``dataset/``, so it is a unit
test (job 1) rather than a scripted eval case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from omicsclaw.evals import Case, NoError, ScriptedProvider, ScriptedTurn, run_case, tool_call
from omicsclaw.observability import Telemetry
from omicsclaw.observability.attributes import (
    ATTR_AGENT_TYPE,
    ATTR_GENAI_INPUT_TOKENS,
    ATTR_GENAI_OUTPUT_TOKENS,
    ATTR_GENAI_REQUEST_MODEL,
    ATTR_GENAI_SYSTEM,
    ATTR_INPUT_TOKENS,
    ATTR_LANGFUSE_OBSERVATION_INPUT,
    ATTR_LANGFUSE_OBSERVATION_OUTPUT,
    ATTR_LANGFUSE_TRACE_INPUT,
    ATTR_LANGFUSE_TRACE_OUTPUT,
    ATTR_OUTPUT_TOKENS,
    ATTR_SESSION_ID,
    ATTR_STOP_REASON,
    ATTR_TOOL_NAME,
    ATTR_TOOL_STATUS,
    ATTR_TOOL_SUCCESS,
    ATTR_TURN_HAS_TOOL_CALLS,
    ATTR_TURN_NUMBER,
    ATTR_TURNS,
    METRIC_TOKENS_INPUT,
    METRIC_TOOL_CALLS,
    METRIC_TURNS_TOTAL,
    SPAN_INTERACTION,
    SPAN_LLM_REQUEST,
    SPAN_TOOL,
    SPAN_TURN,
)
from omicsclaw.observability.config import ObservabilityConfig
from tests.observability._support import RecordingMeter, RecordingTracer


@dataclass
class _Recorder:
    """Holds what one run's telemetry recorded, since the case builds it lazily."""

    capture: bool = False
    tracer: RecordingTracer = field(default_factory=RecordingTracer)
    meter: RecordingMeter = field(default_factory=RecordingMeter)
    flushes: int = 0

    def telemetry(self) -> Telemetry:
        def flushed() -> None:
            self.flushes += 1

        return Telemetry(
            tracer=self.tracer,
            meter=self.meter,
            config=ObservabilityConfig(capture_content=self.capture),
            on_flush=flushed,
        )


def _run(tmp_path, *, capture: bool = False) -> _Recorder:
    recorder = _Recorder(capture=capture)
    case = Case(
        id="context/traced",
        category="context",
        prompt="Read a.txt.",
        provider=lambda: ScriptedProvider(
            ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "a.txt"}),)),
            ScriptedTurn(text="It says alpha."),
        ),
        assertions=(NoError(),),
        files={"a.txt": "alpha\n"},
        telemetry=recorder.telemetry,
    )
    result = run_case(case, tmp_path)
    assert result.passed, result.failures
    return recorder


@pytest.fixture
def recorded(tmp_path) -> _Recorder:
    return _run(tmp_path)


def test_one_interaction_with_its_session_type_turns_and_stop_reason(recorded):
    (interaction,) = recorded.tracer.named(SPAN_INTERACTION)
    assert interaction.parent is None
    assert interaction.attributes[ATTR_SESSION_ID] == "eval"
    assert interaction.attributes[ATTR_AGENT_TYPE] == "main"
    assert interaction.attributes[ATTR_TURNS] == 2
    assert interaction.attributes[ATTR_STOP_REASON] == "converged"


def test_two_turns_and_no_empty_third(recorded):
    turns = recorded.tracer.named(SPAN_TURN)
    assert [turn.attributes[ATTR_TURN_NUMBER] for turn in turns] == [1, 2]
    assert [turn.attributes[ATTR_TURN_HAS_TOOL_CALLS] for turn in turns] == [True, False]
    assert all(turn.chain == [SPAN_TURN, SPAN_INTERACTION] for turn in turns)


def test_one_llm_request_per_turn_with_genai_attributes(recorded):
    turns = recorded.tracer.named(SPAN_TURN)
    requests = recorded.tracer.named(SPAN_LLM_REQUEST)
    assert [request.parent for request in requests] == turns
    for request in requests:
        attributes = request.attributes
        assert request.chain == [SPAN_LLM_REQUEST, SPAN_TURN, SPAN_INTERACTION]
        assert attributes[ATTR_GENAI_SYSTEM] == "scripted"
        assert attributes[ATTR_GENAI_REQUEST_MODEL] == "claude-sonnet-4-5"
        assert attributes[ATTR_GENAI_INPUT_TOKENS] == 100 == attributes[ATTR_INPUT_TOKENS]
        assert attributes[ATTR_GENAI_OUTPUT_TOKENS] == 50 == attributes[ATTR_OUTPUT_TOKENS]


def test_the_tool_span_sits_under_the_first_turn(recorded):
    first_turn = recorded.tracer.named(SPAN_TURN)[0]
    (tool,) = recorded.tracer.named(SPAN_TOOL)
    assert tool.parent is first_turn
    assert tool.attributes[ATTR_TOOL_NAME] == "read_file"
    assert tool.attributes[ATTR_TOOL_STATUS] == "ok"
    assert tool.attributes[ATTR_TOOL_SUCCESS] is True


def test_every_span_ended_exactly_once(recorded):
    assert recorded.tracer.spans
    assert all(span.ended == 1 for span in recorded.tracer.spans)


def test_no_content_is_captured_by_default(recorded):
    keys = {key for span in recorded.tracer.spans for key in span.attributes}
    assert not [key for key in keys if key.startswith("langfuse.")]


def test_capture_puts_the_four_langfuse_keys_on_their_spans(tmp_path):
    recorder = _run(tmp_path, capture=True)
    (interaction,) = recorder.tracer.named(SPAN_INTERACTION)
    assert {ATTR_LANGFUSE_TRACE_INPUT, ATTR_LANGFUSE_TRACE_OUTPUT} <= set(interaction.attributes)
    for span in (*recorder.tracer.named(SPAN_LLM_REQUEST), *recorder.tracer.named(SPAN_TOOL)):
        assert {ATTR_LANGFUSE_OBSERVATION_INPUT, ATTR_LANGFUSE_OBSERVATION_OUTPUT} <= set(span.attributes)


def test_metrics_add_up_over_the_exchange(recorded):
    assert recorded.meter.totals(METRIC_TOKENS_INPUT) == 200
    assert recorded.meter.totals(METRIC_TURNS_TOTAL) == 2
    assert recorded.meter.totals(METRIC_TOOL_CALLS) == 1


def test_one_exchange_flushes_once(recorded):
    assert recorded.flushes == 1
