"""Projection contract for ``omicsclaw.entry.render`` (plan 0031, task C).

Two halves, tested apart because they fail apart:

:class:`TextRenderer` is the one with memory. Its bugs are ordering bugs —
a tool line printed above the sentence that preceded it — and they only
appear in batched mode, which is the mode the CLI never runs.

:func:`to_wire` is the one that crosses a process boundary, and its bugs
are silent. Three of them are pinned structurally rather than by reading
prose (plan 0031 §6, traps 6 and 7, and Q24):

- the elapsed figure can never be composed without saying it includes an
  approval wait;
- an unreported token count and a zero token count are different strings;
- ``ToolCall.arguments`` crosses byte for byte, and a ``tool_result``
  frame uses the key names the *published* Desktop renderer reaches for.

That last one is checked against the real ``surfaces/desktop/_chat_sse.py``
rather than against a copy of its rules, because a copy would agree with
itself forever. Its sibling ``wire_contract.py`` is *not* imported here:
it reaches ``run_wire``, which needs ``pydantic``, which this environment
does not have — and a permanently skipped test is coverage that is not
there. The eight schema version numbers are the Desktop sub-package's
acceptance item (§9-14), not this one's.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from omicsclaw.context.budget import BudgetReport, ContextBudget, Pressure
from omicsclaw.context.compaction import CompactionRecord
from omicsclaw.engine.types import EngineEvent
from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.render import (
    BATCH_CHARS,
    DESKTOP_CHAT_FRAME_TYPE,
    ELAPSED_INCLUDES_APPROVAL_WAIT,
    REASONING_PREFIX,
    USAGE_UNREPORTED,
    USAGE_ZERO,
    TextRenderer,
    to_wire,
)
from omicsclaw.schema import ToolCall, ToolResult, Usage
from omicsclaw.tools.base import ApprovalMode, RiskLevel
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, ProgressUpdate

_ARGUMENTS = '{"z":1,\n  "a":   [2,3],  "nested":{"b":false}}'
"""Deliberately un-canonical: key order, whitespace and a newline that a
``json.loads``/``json.dumps`` round trip would all quietly rewrite."""


def _text(delta: str, seq: int = 1) -> TurnEvent:
    return TurnEvent(
        type=TurnEventType.TEXT_DELTA,
        seq=seq,
        session_id="s",
        turn_id="t",
        engine=EngineEvent.text(delta, turn=1),
    )


def _reasoning(delta: str, seq: int = 1) -> TurnEvent:
    return TurnEvent(
        type=TurnEventType.REASONING_DELTA,
        seq=seq,
        session_id="s",
        turn_id="t",
        engine=EngineEvent.reasoning(delta, turn=1),
    )


def _tool_result(
    *, output: str = "ok", duration_s: float | None = 12.5, is_error: bool = False
) -> TurnEvent:
    result = ToolResult(
        tool_call_id="call-1", name="bash", output=output, is_error=is_error
    )
    return TurnEvent(
        type=TurnEventType.TOOL_RESULT,
        seq=5,
        session_id="s",
        turn_id="t",
        engine=EngineEvent.tool_finished(result, turn=1, duration_s=duration_s),
    )


def _turn_end(usage: Usage | None) -> TurnEvent:
    return TurnEvent(
        type=TurnEventType.TURN_END,
        seq=6,
        session_id="s",
        turn_id="t",
        engine=EngineEvent.turn_end(1, usage),
    )


def _report() -> BudgetReport:
    budget = ContextBudget(
        context_tokens=100_000, reserve_output_tokens=8_000, reserve_tool_tokens=2_000
    )
    return BudgetReport(
        budget=budget,
        message_tokens=40_000,
        tool_tokens=1_000,
        tool_reserve_shortfall=0,
        pressure=Pressure.WARN,
        ratio=0.61,
    )


def _record() -> CompactionRecord:
    return CompactionRecord(
        pressure=Pressure.FULL,
        tokens_before=90_000,
        tokens_after=30_000,
        msgs_before=42,
        msgs_after=12,
        summarized=30,
        preserved_tail=10,
        summary_text="a summary the model already has",
        degraded="",
    )


def _one_of_every_type() -> dict[TurnEventType, TurnEvent]:
    """One frame per member, so no projection branch goes unexercised."""
    request = ApprovalRequest(
        tool_name="bash",
        arguments=_ARGUMENTS,
        reason="delete 412 files under /data/run-7",
        risk_level=RiskLevel.HIGH,
        approval_mode=ApprovalMode.ASK,
    )
    frames = {
        TurnEventType.EXCHANGE_START: TurnEvent.exchange_start(
            seq=1, session_id="s", turn_id="t"
        ),
        TurnEventType.QUEUED: TurnEvent.queued(2, seq=2, session_id="s", turn_id="t"),
        TurnEventType.CONTEXT: TurnEvent.context(_report(), seq=3),
        TurnEventType.COMPACTION: TurnEvent.compacted(_record(), seq=4),
        TurnEventType.TEXT_DELTA: _text("hello"),
        TurnEventType.REASONING_DELTA: _reasoning("thinking"),
        TurnEventType.PROGRESS: TurnEvent.progress_update(
            ProgressUpdate(tool_name="bash", message="still going", fraction=0.25),
            seq=7,
        ),
        TurnEventType.TOOL_START: TurnEvent(
            type=TurnEventType.TOOL_START,
            seq=8,
            session_id="s",
            turn_id="t",
            engine=EngineEvent.tool_start(
                ToolCall(id="call-1", name="bash", arguments=_ARGUMENTS), turn=1
            ),
        ),
        TurnEventType.TOOL_RESULT: _tool_result(),
        TurnEventType.APPROVAL_REQUIRED: TurnEvent.approval_required(
            request, "req-1", seq=10
        ),
        TurnEventType.APPROVAL_SETTLED: TurnEvent.approval_settled(
            "req-1", ApprovalDecision(approved=False, reason="not today"), seq=11
        ),
        TurnEventType.TURN_END: _turn_end(Usage(input_tokens=10, output_tokens=4)),
        TurnEventType.GAP: TurnEvent.gap_at(8, 11, session_id="s", turn_id="t"),
        TurnEventType.EXCHANGE_END: TurnEvent.exchange_end(
            "failed", error=ValueError("token sk-live-abc leaked into the message")
        ),
    }
    assert set(frames) == set(TurnEventType)
    return frames


# ---- TextRenderer: the two modes ---------------------------------------


def test_the_cli_mode_puts_every_token_on_screen_as_it_arrives() -> None:
    renderer = TextRenderer()
    assert renderer.feed(_text("Hel")) == "Hel"
    assert renderer.feed(_text("lo")) == "lo"
    assert renderer.flush() == ""


def test_the_channel_mode_batches_across_events() -> None:
    """The reason :class:`TextRenderer` has state at all: an IM platform
    rate-limits edits, so one message per token is not a slow UI, it is a
    throttled bot."""
    renderer = TextRenderer(batched=True, batch_chars=10)
    assert renderer.feed(_text("1234")) is None
    assert renderer.feed(_text("5678")) is None
    assert renderer.feed(_text("90")) == "1234567890"
    assert renderer.feed(_text("tail")) is None
    assert renderer.flush() == "tail"
    assert renderer.flush() == ""


def test_the_default_batch_is_the_tightest_shipped_platform_limit() -> None:
    assert BATCH_CHARS == 2000
    renderer = TextRenderer(batched=True)
    assert renderer.feed(_text("x" * (BATCH_CHARS - 1))) is None
    assert renderer.feed(_text("y")) == "x" * (BATCH_CHARS - 1) + "y"


def test_a_control_frame_never_jumps_ahead_of_buffered_text() -> None:
    """Ordering is the batched mode's whole failure surface."""
    renderer = TextRenderer(batched=True, batch_chars=1000)
    assert renderer.feed(_text("Running the tool now.")) is None
    out = renderer.feed(_tool_result())
    assert out is not None
    assert out.startswith("Running the tool now.\n")
    assert out.splitlines()[1].startswith("<- bash ok")


def test_reasoning_is_hidden_unless_asked_for_and_is_marked_when_shown() -> None:
    quiet = TextRenderer()
    assert quiet.feed(_reasoning("private thought")) is None

    loud = TextRenderer(show_reasoning=True)
    assert loud.feed(_reasoning("private thought")) == (
        REASONING_PREFIX + "private thought"
    )


def test_switching_between_reasoning_and_text_flushes_first() -> None:
    renderer = TextRenderer(batched=True, batch_chars=1000, show_reasoning=True)
    assert renderer.feed(_reasoning("hmm")) is None
    out = renderer.feed(_text("answer"))
    assert out == REASONING_PREFIX + "hmm"
    assert renderer.flush() == "answer"


def test_an_empty_delta_renders_nothing() -> None:
    assert TextRenderer().feed(_text("")) is None


def test_batch_chars_must_be_positive() -> None:
    with pytest.raises(ValueError):
        TextRenderer(batched=True, batch_chars=0)


def test_every_frame_type_renders_without_raising() -> None:
    renderer = TextRenderer(show_reasoning=True)
    for frame in _one_of_every_type().values():
        rendered = renderer.feed(frame)
        assert rendered is None or isinstance(rendered, str)


# ---- trap 6: the elapsed figure includes a human's thinking time -------


def test_the_elapsed_figure_can_only_be_rendered_with_its_caveat() -> None:
    """Structural, not editorial (§6 trap 6 / appendix C-Y13).

    ``duration_s`` is measured by the scheduler and so includes however
    long a person took to answer an approval. The renderer therefore
    cannot emit the number without the constant that says so — a change
    that started calling this "tool time" has to delete a name.
    """
    line = TextRenderer().feed(_tool_result(duration_s=612.0))
    assert line is not None
    assert line.endswith(ELAPSED_INCLUDES_APPROVAL_WAIT)
    assert "612.0" + ELAPSED_INCLUDES_APPROVAL_WAIT in line


def test_the_wire_never_offers_a_field_a_client_could_call_tool_time() -> None:
    wire = to_wire(_tool_result(duration_s=612.0))
    assert "duration_s" not in wire
    assert wire["elapsed_s"] == 612.0
    assert wire["elapsed_includes_approval_wait"] is True


def test_an_untimed_result_says_nothing_about_time() -> None:
    line = TextRenderer().feed(_tool_result(duration_s=None))
    assert line == "<- bash ok"
    assert to_wire(_tool_result(duration_s=None))["elapsed_s"] is None


# ---- trap 7: "not reported" is not "zero" ------------------------------


def test_an_unreported_usage_and_a_zero_usage_read_differently() -> None:
    renderer = TextRenderer()
    unreported = renderer.feed(_turn_end(None))
    zero = renderer.feed(_turn_end(Usage()))
    assert unreported != zero
    assert unreported is not None and unreported.endswith(USAGE_UNREPORTED)
    assert zero is not None and zero.endswith(USAGE_ZERO)


def test_the_two_usage_cases_stay_distinguishable_on_the_wire() -> None:
    assert to_wire(_turn_end(None))["usage_reported"] is False
    assert to_wire(_turn_end(None))["usage"] is None
    zero = to_wire(_turn_end(Usage()))
    assert zero["usage_reported"] is True
    assert zero["usage"]["input_tokens"] == 0


def test_a_real_usage_reports_its_figures() -> None:
    wire = to_wire(_turn_end(Usage(input_tokens=11, output_tokens=5)))
    assert wire["usage"] == {
        "input_tokens": 11,
        "output_tokens": 5,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


# ---- to_wire: JSON, byte exactness, and the published contract ---------


def test_every_frame_type_survives_strict_json() -> None:
    """``allow_nan=False`` on purpose: ``NaN`` is not JSON, and a frame
    that emitted one would be rejected by a conforming client instead of
    by this process."""
    for kind, frame in _one_of_every_type().items():
        wire = to_wire(frame)
        encoded = json.dumps(wire, allow_nan=False)
        assert json.loads(encoded)["type"] == kind.value
        assert wire["sequence"] == frame.seq


def test_a_non_finite_float_becomes_a_string_instead_of_invalid_json() -> None:
    frame = TurnEvent.progress_update(
        ProgressUpdate(tool_name="bash", message="?", fraction=math.nan), seq=1
    )
    assert to_wire(frame)["fraction"] == "NaN"
    json.dumps(to_wire(frame), allow_nan=False)


def test_tool_call_arguments_cross_the_wire_byte_for_byte() -> None:
    """Plan 0027's ruling, inherited: the raw payload is what prompt-prefix
    caching and replay evidence are matched on, and a decode plus re-encode
    can reorder keys."""
    frames = _one_of_every_type()
    decoded = json.loads(json.dumps(to_wire(frames[TurnEventType.TOOL_START])))
    assert decoded["arguments"] == _ARGUMENTS
    assert decoded["arguments"] != json.dumps(json.loads(_ARGUMENTS))


def test_an_approval_prompt_shows_the_arguments_that_will_actually_run() -> None:
    frames = _one_of_every_type()
    wire = to_wire(frames[TurnEventType.APPROVAL_REQUIRED])
    assert wire["arguments"] == _ARGUMENTS
    assert wire["risk_level"] == "high"
    assert wire["request_id"] == "req-1"


def test_the_terminal_frame_keeps_the_error_type_and_drops_its_text() -> None:
    """``wire_contract.py`` promises ``terminal_error_type_preserved``; the
    text is withheld because an exception message can carry a fetched URL
    with its query string (Q22 rule 1)."""
    frames = _one_of_every_type()
    wire = to_wire(frames[TurnEventType.EXCHANGE_END])
    assert wire["terminal"] == "failed"
    assert wire["error_type"] == "ValueError"
    assert "sk-live-abc" not in json.dumps(wire)


def test_a_converged_end_carries_no_error_type() -> None:
    wire = to_wire(TurnEvent.exchange_end("converged"))
    assert wire["terminal"] == "converged"
    assert wire["error_type"] is None


def test_the_compaction_frame_is_a_notification_not_a_transcript() -> None:
    frames = _one_of_every_type()
    wire = to_wire(frames[TurnEventType.COMPACTION])
    assert wire["msgs_before"] == 42 and wire["msgs_after"] == 12
    assert wire["degraded"] == ""
    assert "summary_text" not in wire


def test_the_context_frame_carries_the_figures_the_engine_cannot(
) -> None:
    frames = _one_of_every_type()
    wire = to_wire(frames[TurnEventType.CONTEXT])
    assert wire["message_tokens"] == 40_000
    assert wire["pressure"] == "warn"
    assert wire["context_tokens"] == 100_000


def test_a_gap_frame_names_the_hole() -> None:
    wire = to_wire(TurnEvent.gap_at(8, 11))
    assert (wire["oldest_available"], wire["latest"]) == (8, 11)
    assert wire["sequence"] == 7


# ---- Q24: compatibility with the published Desktop renderer ------------


def test_a_tool_result_frame_renders_through_the_published_sse_renderer() -> None:
    sse = pytest.importorskip("omicsclaw.surfaces.desktop._chat_sse")
    wire = to_wire(_tool_result(output="42 spots kept"))
    frame = sse.render_chat_sse_frame("tool_result", wire)
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    envelope = json.loads(frame[len("data: ") :])
    assert envelope["type"] == "tool_result"
    assert json.loads(envelope["data"])["content"] == "42 spots kept"


def test_an_oversized_tool_result_keeps_its_correlation_identity() -> None:
    """The one place the published renderer reaches *into* the payload.

    Over 4 MiB it rebuilds the frame from ``tool_use_id`` / ``tool_name``
    / ``content``. A payload that spelled those differently would lose the
    identity of the result exactly when the result is too big to send —
    and would do it silently.
    """
    sse = pytest.importorskip("omicsclaw.surfaces.desktop._chat_sse")
    huge = "x" * (sse.CHAT_SSE_MAX_FRAME_BYTES + 16)
    wire = to_wire(_tool_result(output=huge, is_error=True))
    envelope = json.loads(
        sse.render_chat_sse_frame("tool_result", wire)[len("data: ") :]
    )
    assert envelope["type"] == "tool_result"
    projected = json.loads(envelope["data"])
    assert projected["tool_use_id"] == "call-1"
    assert projected["tool_name"] == "bash"
    assert projected["content_truncated"] is True
    assert projected["is_error"] is True


def test_every_frame_type_fits_the_published_sse_renderer() -> None:
    sse = pytest.importorskip("omicsclaw.surfaces.desktop._chat_sse")
    for kind, frame in _one_of_every_type().items():
        rendered = sse.render_chat_sse_frame(kind.value, to_wire(frame))
        envelope = json.loads(rendered[len("data: ") :])
        assert envelope["type"] == kind.value
        assert json.loads(envelope["data"])["type"] == kind.value


def test_the_desktop_frame_names_are_the_clients_and_not_invented() -> None:
    """Q24: ``/chat/stream``'s vocabulary belongs to the external client
    (``server.py:2006-2020``, and the matching literals in the App's
    ``api/chat/route.ts``). Types with no published name are absent rather
    than given one here."""
    published = {
        "status",
        "mode_changed",
        "text",
        "tool_use",
        "tool_output",
        "tool_log",
        "tool_result",
        "tool_timeout",
        "permission_request",
        "ask_user_question",
        "task_update",
        "result",
        "keep_alive",
        "done",
        "error",
    }
    assert set(DESKTOP_CHAT_FRAME_TYPE) <= set(TurnEventType)
    assert set(DESKTOP_CHAT_FRAME_TYPE.values()) <= published
    assert TurnEventType.EXCHANGE_END not in DESKTOP_CHAT_FRAME_TYPE


def _keys(wire: dict[str, Any]) -> set[str]:
    return set(wire)


def test_identity_is_on_every_frame_so_any_of_them_can_be_resumed_from() -> None:
    for frame in _one_of_every_type().values():
        wire = to_wire(frame)
        assert _keys(wire) >= {
            "schema_version",
            "type",
            "sequence",
            "session_id",
            "turn_id",
        }
