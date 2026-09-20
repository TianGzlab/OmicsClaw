"""``omicsclaw/entry`` — what one user exchange emits, with an identity.

Plan 0031, step 6 of the staged framework rebuild. Step 3
(:mod:`omicsclaw.engine`) already emits :class:`~omicsclaw.engine.types.
EngineEvent`; this module is its **superset**, and the superset exists for
three reasons that are all structural rather than stylistic:

``APPROVAL_REQUIRED`` / ``APPROVAL_SETTLED``
    The engine has no representation for "a human is being asked". It
    cannot grow one honestly either: the ``await`` that waits for a person
    happens *inside* a tool, inside the engine generator's ``__anext__``,
    so the generator that would have to report the question is the same
    generator that is blocked on its answer. The layer that binds
    ``ApprovalChannel`` is this one, so the layer that can say so is this
    one (plan 0031 Q5).

``CONTEXT`` / ``COMPACTION``
    Both come from the compactor the engine consults before each model
    call, not from the engine: the engine does not know what a budget or
    a compaction record is. They are published by the exchange that
    supplied the compactor, so they reach the stream ahead of that model
    call's own events.

``QUEUED`` / ``GAP`` / ``EXCHANGE_*``
    Facts about *delivery*, not about the loop: a second message arriving
    while the first is still running, an observer whose cursor fell off
    the ring, and the boundary of one user round-trip.

**Two scopes, deliberately not the same word** (Q21)
------------------------------------------------------

``TURN_END`` is the engine's, and it fires **once per model call** — the
emit site is ``engine/loop.py:287``, inside the ``while`` that starts at
``:234``, so one user round-trip produces *N* of them, one per
Thought→Action→Observation cycle.

``EXCHANGE_START`` / ``EXCHANGE_END`` are this layer's, and they fire
**once per user round-trip** — exactly one each, whatever happened in
between. Pairing a new ``*_START`` with the engine's ``TURN_END`` would
have mismatched their cardinality, which is the drafting error Q21
records.

**Pass-through events carry the original** :class:`EngineEvent`, on
:attr:`TurnEvent.engine`, never a re-packed copy. Re-packing would create
a second place that has to change every time the engine's event grows a
field, and the first place would keep compiling while the second silently
dropped it.

This module is types only: no I/O, no clock, no logging. Transport lives
in :mod:`omicsclaw.entry.stream` and projection in
:mod:`omicsclaw.entry.render`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from omicsclaw.context.budget import BudgetReport
from omicsclaw.context.compaction import CompactionRecord
from omicsclaw.engine.types import EngineEvent, EngineEventType
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest, ProgressUpdate


class TurnEventType(StrEnum):
    """Kind of payload in one :class:`TurnEvent`.

    The members split into two classes with different delivery
    guarantees, and the split is the whole point of the bounded ring in
    :mod:`omicsclaw.entry.stream`: losing a text token costs a consumer a
    cosmetic hole, losing an approval prompt costs it a deadlock. See
    :data:`DROPPABLE_TYPES` and :data:`CONTROL_TYPES`.
    """

    EXCHANGE_START = "exchange_start"
    """One user round-trip began. Exactly one per exchange (Q21)."""

    QUEUED = "queued"
    """This exchange is waiting behind :attr:`TurnEvent.queued_ahead`
    others on the same session. Published by the registry *before* the
    turn's own Task exists, because ``submit()`` returns a handle
    immediately rather than blocking on a lock (Q7)."""

    CONTEXT = "context"
    """Context pressure measured before a model call, carrying a
    :class:`~omicsclaw.context.budget.BudgetReport`. One per model call."""

    COMPACTION = "compaction"
    """History was compacted before a model call. Carries the
    :class:`~omicsclaw.context.CompactionRecord`, whose ``written_back``
    says whether the result replaced the history."""

    TEXT_DELTA = "text_delta"
    """Pass-through. Assistant text, token by token."""

    REASONING_DELTA = "reasoning_delta"
    """Pass-through. Thought tokens, kept separate from text."""

    PROGRESS = "progress"
    """A tool reporting that it is still working (Q20).

    For a ten-minute exchange this is the only thing that tells a user
    the process is alive, which is why it exists at all — but it is
    still droppable, because a heartbeat that was missed is replaced by
    the next one."""

    TOOL_START = "tool_start"
    """Pass-through. The loop is about to execute one tool call."""

    TOOL_RESULT = "tool_result"
    """Pass-through. One tool finished, failures included."""

    APPROVAL_REQUIRED = "approval_required"
    """A tool is asking a human. Never dropped: a consumer that misses
    this one waits for an answer to a question it was never shown."""

    APPROVAL_SETTLED = "approval_settled"
    """The question was answered, timed out, or the exchange ended
    without it being answered."""

    TURN_END = "turn_end"
    """Pass-through. **One model call** finished — *N* per exchange, not
    one (Q21)."""

    GAP = "gap"
    """A discontinuity in *this observer's* view of the stream.

    Synthesized per observation, not published by the producer: two
    observers of the same exchange can legitimately see different gaps,
    because a gap is a fact about a cursor and not about the exchange.
    """

    EXCHANGE_END = "exchange_end"
    """The terminal frame. **Always sent, and exactly once** (trap 1b).

    A consumer on the far side of HTTP or an IM transport cannot see a
    raised exception, so "the stream stopped" would otherwise be
    ambiguous between finished, cancelled, crashed and disconnected —
    and a Desktop client cannot decide whether to reconnect from an
    ambiguous ending (Q5b).
    """


DROPPABLE_TYPES: Final[frozenset[TurnEventType]] = frozenset(
    {
        TurnEventType.TEXT_DELTA,
        TurnEventType.REASONING_DELTA,
        TurnEventType.PROGRESS,
    }
)
"""Types a bounded buffer may discard when a consumer falls behind.

All three are *increments*: a later frame makes an earlier one
redundant, so a consumer that missed one is behind rather than wrong —
and it is told it is behind by a :attr:`TurnEventType.GAP`.
"""

CONTROL_TYPES: Final[frozenset[TurnEventType]] = frozenset(TurnEventType) - (
    DROPPABLE_TYPES
)
"""Types that are never discarded. Each one is a state change: dropping
it leaves the consumer holding a description of the exchange that is not
merely incomplete but wrong."""


def is_droppable(event_type: TurnEventType) -> bool:
    """Whether a buffer under pressure may discard this type."""

    return event_type in DROPPABLE_TYPES


Terminal = Literal["converged", "cancelled", "failed"]
"""The three ways an exchange can end.

``"cancelled"`` is deliberately not folded into ``"failed"``:
:exc:`asyncio.CancelledError` is not a failure, and step 3 already
refused to turn it into one (``engine/types.py:53-57``). Q5b keeps that
decision and adds only the other half — a cancelled exchange still says
so on the wire instead of vanishing.
"""

_ENGINE_PASSTHROUGH: Final[dict[EngineEventType, TurnEventType]] = {
    EngineEventType.TEXT_DELTA: TurnEventType.TEXT_DELTA,
    EngineEventType.REASONING_DELTA: TurnEventType.REASONING_DELTA,
    EngineEventType.TOOL_START: TurnEventType.TOOL_START,
    EngineEventType.TOOL_RESULT: TurnEventType.TOOL_RESULT,
    EngineEventType.TURN_END: TurnEventType.TURN_END,
}
"""Five of the engine's six event types map straight through.

``DONE`` is the sixth and has **no** counterpart on purpose: it carries
the :class:`~omicsclaw.engine.types.RunResult`, which is the turn
kernel's input for persistence rather than a frame for a Surface, and
the terminal frame a Surface waits for is ``EXCHANGE_END`` — which is
emitted from ``finally`` so that it also exists on the paths where
``DONE`` never arrives. Mapping ``DONE`` onto ``EXCHANGE_END`` would
produce two terminal frames on the happy path.
"""


@dataclass(frozen=True, slots=True)
class TurnEvent:
    """One frame of one exchange, with an identity it can be resumed from.

    Frozen for the reason :class:`~omicsclaw.engine.types.RunResult` is
    frozen: a frame is a record of what happened, and a record that can
    be edited afterwards is not evidence. It is also what makes a frame
    safe to hand to several observers at once — the fan-out in
    :mod:`omicsclaw.entry.stream` shares one object rather than copying.

    Field validity follows :attr:`type`::

        EXCHANGE_START    -> (identity only)
        QUEUED            -> queued_ahead
        CONTEXT           -> report
        COMPACTION        -> compaction
        TEXT_DELTA        -> engine
        REASONING_DELTA   -> engine
        PROGRESS          -> progress
        TOOL_START        -> engine
        TOOL_RESULT       -> engine
        APPROVAL_REQUIRED -> approval, request_id
        APPROVAL_SETTLED  -> request_id, decision
        TURN_END          -> engine
        GAP               -> gap
        EXCHANGE_END      -> terminal, error
    """

    type: TurnEventType
    seq: int
    """Position in this exchange, monotonic and 1-based.

    **Stamped by :meth:`omicsclaw.entry.stream.TurnStream.publish`**, not
    by the producer: the stream is the only object that knows what it has
    already retained, and a cursor that a reconnecting client resumes
    from is worth exactly as much as the guarantee behind these numbers.
    ``0`` means "not published yet".
    """

    session_id: str
    turn_id: str

    engine: EngineEvent | None = None
    """The **original** engine event for a pass-through type, never a
    re-packed copy. See this module's docstring."""

    approval: ApprovalRequest | None = None
    request_id: str = ""
    """Correlates ``APPROVAL_REQUIRED`` with ``APPROVAL_SETTLED`` and
    with ``TurnHandle.approve(request_id, ...)``."""

    progress: ProgressUpdate | None = None
    report: BudgetReport | None = None
    compaction: CompactionRecord | None = None

    terminal: Terminal | None = None
    """Set on ``EXCHANGE_END`` and nowhere else."""

    error: BaseException | None = None
    """The **original** exception on a ``terminal="failed"`` frame.

    Not a string: a same-process consumer can ``raise`` it and keep the
    traceback, which is the behaviour step 3 gave an ``async for``
    consumer for free and which this layer must not take away just
    because it also serves consumers that cannot receive exceptions. A
    cancelled exchange may carry the :exc:`asyncio.CancelledError` here
    while still reporting ``terminal="cancelled"`` (Q5b).

    :func:`omicsclaw.entry.render.to_wire` projects only the exception's
    **type** onto the wire, never its text.
    """

    gap: tuple[int, int] | None = None
    """``(oldest_available, latest)`` on a ``GAP`` frame.

    Read it as: everything after your cursor and before
    ``oldest_available`` is gone, and the exchange had reached ``latest``
    when the gap was noticed. Resuming from :attr:`seq` on a ``GAP``
    frame is always correct — it is ``oldest_available - 1``.
    """

    queued_ahead: int = 0
    """How many exchanges are ahead of this one on the same session.

    **Not in the plan's §3.2 sketch**, and added here because Q7 requires
    ``QUEUED`` to carry "how many are ahead" and the sketch left it
    nowhere to live. Appended last so every positional use of the sketched
    fields is unaffected.
    """

    decision: ApprovalDecision | None = None
    """The answer on an ``APPROVAL_SETTLED`` frame.

    Also absent from §3.2, and added for the same reason: a settled
    approval whose outcome cannot be read renders as "something was
    decided", which is not a thing a Surface can show anyone.
    """

    # ---- constructors ---------------------------------------------------
    #
    # Mirrors ``EngineEvent``'s classmethod style. ``seq`` defaults to 0
    # throughout because the stream stamps it; passing one is allowed and
    # is what §3.3 writes, but it is never load-bearing.

    @classmethod
    def from_engine(
        cls,
        event: EngineEvent,
        *,
        seq: int = 0,
        session_id: str = "",
        turn_id: str = "",
    ) -> TurnEvent | None:
        """Wrap one engine event, or return ``None`` for ``DONE``.

        ``None`` rather than an exception: ``DONE`` is a normal member of
        the engine's stream, and the turn kernel's loop over
        ``run_stream`` should not have to special-case it before calling
        this. :meth:`omicsclaw.entry.stream.TurnStream.publish` ignores
        ``None`` for the same reason.
        """
        mapped = _ENGINE_PASSTHROUGH.get(event.type)
        if mapped is None:
            return None
        return cls(
            type=mapped,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
            engine=event,
        )

    @classmethod
    def exchange_start(
        cls, *, seq: int = 0, session_id: str = "", turn_id: str = ""
    ) -> TurnEvent:
        return cls(
            type=TurnEventType.EXCHANGE_START,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
        )

    @classmethod
    def queued(
        cls, ahead: int, *, seq: int = 0, session_id: str = "", turn_id: str = ""
    ) -> TurnEvent:
        return cls(
            type=TurnEventType.QUEUED,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
            queued_ahead=ahead,
        )

    @classmethod
    def context(
        cls,
        report: BudgetReport,
        *,
        seq: int = 0,
        session_id: str = "",
        turn_id: str = "",
    ) -> TurnEvent:
        return cls(
            type=TurnEventType.CONTEXT,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
            report=report,
        )

    @classmethod
    def compacted(
        cls,
        record: CompactionRecord,
        *,
        seq: int = 0,
        session_id: str = "",
        turn_id: str = "",
    ) -> TurnEvent:
        return cls(
            type=TurnEventType.COMPACTION,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
            compaction=record,
        )

    @classmethod
    def progress_update(
        cls,
        update: ProgressUpdate,
        *,
        seq: int = 0,
        session_id: str = "",
        turn_id: str = "",
    ) -> TurnEvent:
        return cls(
            type=TurnEventType.PROGRESS,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
            progress=update,
        )

    @classmethod
    def approval_required(
        cls,
        request: ApprovalRequest,
        request_id: str,
        *,
        seq: int = 0,
        session_id: str = "",
        turn_id: str = "",
    ) -> TurnEvent:
        return cls(
            type=TurnEventType.APPROVAL_REQUIRED,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
            approval=request,
            request_id=request_id,
        )

    @classmethod
    def approval_settled(
        cls,
        request_id: str,
        decision: ApprovalDecision,
        *,
        seq: int = 0,
        session_id: str = "",
        turn_id: str = "",
    ) -> TurnEvent:
        return cls(
            type=TurnEventType.APPROVAL_SETTLED,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
            request_id=request_id,
            decision=decision,
        )

    @classmethod
    def gap_at(
        cls,
        oldest_available: int,
        latest: int,
        *,
        session_id: str = "",
        turn_id: str = "",
    ) -> TurnEvent:
        """A per-observer discontinuity; :attr:`seq` is fixed by the gap.

        ``seq`` is ``oldest_available - 1`` so that a consumer which
        stores every frame's ``seq`` as its cursor stays correct across a
        gap: reopening at that cursor asks for exactly the frames the gap
        did not eat.
        """
        return cls(
            type=TurnEventType.GAP,
            seq=max(0, oldest_available - 1),
            session_id=session_id,
            turn_id=turn_id,
            gap=(oldest_available, latest),
        )

    @classmethod
    def exchange_end(
        cls,
        terminal: Terminal,
        *,
        error: BaseException | None = None,
        seq: int = 0,
        session_id: str = "",
        turn_id: str = "",
    ) -> TurnEvent:
        return cls(
            type=TurnEventType.EXCHANGE_END,
            seq=seq,
            session_id=session_id,
            turn_id=turn_id,
            terminal=terminal,
            error=error,
        )


__all__ = [
    "CONTROL_TYPES",
    "DROPPABLE_TYPES",
    "Terminal",
    "TurnEvent",
    "TurnEventType",
    "is_droppable",
]
