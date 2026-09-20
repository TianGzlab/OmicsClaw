"""The event vocabulary of ``omicsclaw.entry.events`` (plan 0031, task C).

Nothing here touches transport or text — ``test_stream.py`` owns delivery
and ``test_render.py`` owns projection. What is left is the two decisions
that the other two files then depend on and cannot re-check:

1. **The droppable/control partition.** A bounded buffer is only as
   trustworthy as this split, and a member that drifts into the wrong
   half fails nowhere else: dropping ``APPROVAL_REQUIRED`` under load
   produces a deadlock in production and a green suite everywhere.
2. **The two scopes** (Q21). ``TURN_END`` is per *model call*;
   ``EXCHANGE_END`` is per *user round-trip*. The cheap way to break that
   is to give ``EngineEventType.DONE`` a frame, which would put two
   terminal frames on every successful exchange.
"""

from __future__ import annotations

import dataclasses

import pytest

from omicsclaw.engine.types import EngineEvent, EngineEventType, RunResult, StopReason
from omicsclaw.entry.events import (
    CONTROL_TYPES,
    DROPPABLE_TYPES,
    TurnEvent,
    TurnEventType,
    is_droppable,
)
from omicsclaw.schema import ToolCall, ToolResult, Usage
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, ProgressUpdate


def test_the_vocabulary_is_the_fourteen_members_the_plan_froze() -> None:
    assert [member.value for member in TurnEventType] == [
        "exchange_start",
        "queued",
        "context",
        "compaction",
        "text_delta",
        "reasoning_delta",
        "progress",
        "tool_start",
        "tool_result",
        "approval_required",
        "approval_settled",
        "turn_end",
        "gap",
        "exchange_end",
    ]


def test_only_increments_are_droppable() -> None:
    """The partition, member by member — not by counting.

    A test that only asserted "the two sets are disjoint and cover" would
    stay green if a control member and a delta member swapped halves.
    """
    assert DROPPABLE_TYPES == {
        TurnEventType.TEXT_DELTA,
        TurnEventType.REASONING_DELTA,
        TurnEventType.PROGRESS,
    }
    assert CONTROL_TYPES == {
        TurnEventType.EXCHANGE_START,
        TurnEventType.QUEUED,
        TurnEventType.CONTEXT,
        TurnEventType.COMPACTION,
        TurnEventType.TOOL_START,
        TurnEventType.TOOL_RESULT,
        TurnEventType.APPROVAL_REQUIRED,
        TurnEventType.APPROVAL_SETTLED,
        TurnEventType.TURN_END,
        TurnEventType.GAP,
        TurnEventType.EXCHANGE_END,
    }
    assert DROPPABLE_TYPES.isdisjoint(CONTROL_TYPES)
    assert DROPPABLE_TYPES | CONTROL_TYPES == set(TurnEventType)
    for member in TurnEventType:
        assert is_droppable(member) is (member in DROPPABLE_TYPES)


def test_an_approval_prompt_is_never_droppable() -> None:
    """Named separately because this is the one that deadlocks a human."""
    assert not is_droppable(TurnEventType.APPROVAL_REQUIRED)
    assert not is_droppable(TurnEventType.APPROVAL_SETTLED)
    assert not is_droppable(TurnEventType.EXCHANGE_END)


def test_every_engine_event_type_is_accounted_for() -> None:
    samples = {
        EngineEventType.TEXT_DELTA: EngineEvent.text("hi", turn=1),
        EngineEventType.REASONING_DELTA: EngineEvent.reasoning("hm", turn=1),
        EngineEventType.TOOL_START: EngineEvent.tool_start(
            ToolCall(id="c1", name="bash"), turn=1
        ),
        EngineEventType.TOOL_RESULT: EngineEvent.tool_finished(
            ToolResult(tool_call_id="c1", name="bash"), turn=1
        ),
        EngineEventType.TURN_END: EngineEvent.turn_end(1, Usage(input_tokens=3)),
        EngineEventType.DONE: EngineEvent.done(
            RunResult(messages=(), stop_reason=StopReason.CONVERGED)
        ),
    }
    assert set(samples) == set(EngineEventType)
    mapped = {
        member: TurnEvent.from_engine(event, session_id="s", turn_id="t")
        for member, event in samples.items()
    }
    assert mapped[EngineEventType.TEXT_DELTA].type is TurnEventType.TEXT_DELTA
    assert (
        mapped[EngineEventType.REASONING_DELTA].type is TurnEventType.REASONING_DELTA
    )
    assert mapped[EngineEventType.TOOL_START].type is TurnEventType.TOOL_START
    assert mapped[EngineEventType.TOOL_RESULT].type is TurnEventType.TOOL_RESULT
    assert mapped[EngineEventType.TURN_END].type is TurnEventType.TURN_END


def test_done_has_no_frame_so_a_terminal_frame_stays_singular() -> None:
    """Q21's cardinality guard.

    ``DONE`` arrives once per successful run; ``EXCHANGE_END`` is emitted
    from ``finally`` on every path. Mapping the first onto the second
    would put two terminal frames on the happy path and none on the
    cancelled one.
    """
    done = EngineEvent.done(
        RunResult(messages=(), stop_reason=StopReason.CONVERGED)
    )
    assert TurnEvent.from_engine(done) is None


def test_pass_through_carries_the_original_engine_event() -> None:
    """Identity, not equality: a re-packed copy is a second place to
    maintain, and the first one keeps working while the second rots."""
    engine_event = EngineEvent.text("token", turn=4)
    frame = TurnEvent.from_engine(engine_event, seq=7, session_id="s", turn_id="t")
    assert frame is not None
    assert frame.engine is engine_event
    assert frame.seq == 7
    assert frame.session_id == "s"
    assert frame.turn_id == "t"


def test_turn_end_passes_through_and_is_not_the_exchange_boundary() -> None:
    turn_end = TurnEvent.from_engine(EngineEvent.turn_end(3, None))
    assert turn_end is not None
    assert turn_end.type is TurnEventType.TURN_END
    assert turn_end.type is not TurnEventType.EXCHANGE_END
    assert turn_end.engine.turn == 3


def test_a_gap_frames_cursor_is_the_one_to_resume_from() -> None:
    gap = TurnEvent.gap_at(50, 90, session_id="s", turn_id="t")
    assert gap.type is TurnEventType.GAP
    assert gap.gap == (50, 90)
    # A consumer that stores every frame's ``seq`` as its cursor must be
    # able to store this one too: reopening at 49 asks for 50 onwards,
    # which is exactly what survived.
    assert gap.seq == 49
    assert TurnEvent.gap_at(1, 1).seq == 0


def test_the_three_terminals_and_the_untouched_exception() -> None:
    boom = RuntimeError("provider said no")
    for terminal in ("converged", "cancelled", "failed"):
        frame = TurnEvent.exchange_end(terminal, session_id="s", turn_id="t")
        assert frame.terminal == terminal
        assert frame.type is TurnEventType.EXCHANGE_END
    failed = TurnEvent.exchange_end("failed", error=boom)
    assert failed.error is boom
    cancelled = TurnEvent.exchange_end("cancelled", error=_cancelled())
    assert cancelled.terminal == "cancelled"
    assert isinstance(cancelled.error, BaseException)


def _cancelled() -> BaseException:
    import asyncio

    return asyncio.CancelledError()


def test_the_constructors_fill_the_field_the_type_declares() -> None:
    request = ApprovalRequest(tool_name="bash", arguments='{"cmd":"ls"}')
    decision = ApprovalDecision(approved=False, reason="not today")
    update = ProgressUpdate(tool_name="bash", message="still going", fraction=0.5)
    assert TurnEvent.queued(3).queued_ahead == 3
    assert TurnEvent.approval_required(request, "r1").approval is request
    assert TurnEvent.approval_required(request, "r1").request_id == "r1"
    settled = TurnEvent.approval_settled("r1", decision)
    assert settled.decision is decision
    assert settled.request_id == "r1"
    assert TurnEvent.progress_update(update).progress is update
    assert TurnEvent.exchange_start().type is TurnEventType.EXCHANGE_START


def test_a_frame_is_a_record_and_cannot_be_edited_afterwards() -> None:
    frame = TurnEvent.exchange_start(seq=1, session_id="s", turn_id="t")
    with pytest.raises(dataclasses.FrozenInstanceError):
        frame.seq = 2  # type: ignore[misc]
