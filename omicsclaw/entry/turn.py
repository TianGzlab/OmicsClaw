"""One exchange: assemble its collaborators, run the loop, keep the result.

``AgentEngine.exchange`` renders a prompt, puts a history in front of it
and hands the finished trajectory back. This module is where all three of
those come from. Each turn hands the engine:

1. the app's prompt assembler, so an edited ``OMICSCLAW.md`` and
   today's date are both picked up — the engine renders
   it once, at the start of the exchange;
2. a :class:`_Carried`, this exchange's history and the place the engine
   leaves the conversation to carry forward;
3. a :class:`~omicsclaw.context.ProgressiveCompactor` that measures and,
   from the configured tier up, compacts the conversation before every
   model call of the run — and a
   :class:`~omicsclaw.planning.PlanInjector` that puts the session's
   outstanding plan back at the end of it afterwards, so that what
   compaction summarized away cannot take the plan with it.

:func:`_assemble` builds all of that in one place for all three paths
below (plan 0027 §12.4). The deadline stays out here: how long a
deployment is willing to wait is its own policy, not the loop's.

Each of the three paths below also wraps its exchange in
:meth:`~omicsclaw.observability.Telemetry.run` and feeds it the engine's
events. That is the whole of this layer's telemetry wiring: the scope
opens the interaction span, the events give it the turn boundaries, and
an unobserved deployment gets a scope whose spans are the shared no-op.
:mod:`omicsclaw.observability` explains why the engine was not given an
observer seam instead.

The history belongs to the caller. Nothing here is stored between calls
except what a caller chooses to carry: :class:`TurnOutcome` gives back
the conversation to keep and the compaction state to pass in next time.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import (
    AsyncIterator,
    Callable,
    Iterator,
    Literal,
    Mapping,
    Sequence,
    cast,
)

from omicsclaw.context import (
    PRESSURE_ORDER,
    AssembledPrompt,
    BudgetReport,
    CompactionRecord,
    CompactionState,
    ProgressiveCompactor,
    assemble,
    at_least,
)
from omicsclaw.engine import (
    EngineError,
    EngineEvent,
    RunResult,
    StopReason,
    TurnAugmentor,
)
from omicsclaw.schema import Message, Role
from omicsclaw.tools.context import (
    ApprovalDecision,
    ProgressUpdate,
    current_context,
    use_tool_context,
)

from .approval import ApprovalBroker
from .assembly import AgentApp
from .compaction import PINNED_SYSTEM_MESSAGES, build_compactor
from .events import Terminal, TurnEvent
from .planning import build_injector
from .stream import DEFAULT_RING_SIZE, TurnObservation, TurnStream

__all__ = [
    "PINNED_SYSTEM_MESSAGES",
    "PRESSURE_ORDER",
    "TurnHandle",
    "TurnOutcome",
    "TurnRunner",
    "TurnState",
    "at_least",
    "compose",
    "prepare",
    "run_turn",
    "stream_turn",
]

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    """What one exchange produced, and what the next one needs."""

    result: RunResult
    """The engine's own answer: trajectory, stop reason, usage, turns."""

    history: tuple[Message, ...]
    """The conversation to carry forward, **without** the system message.

    A caller passes this straight back in as *history* next turn. The
    system message is stripped because :func:`compose` always adds a
    fresh one; keeping it would stack a stale persona beside the current
    one on every exchange.
    """

    prompt: AssembledPrompt
    """The render this turn used. Holds ``section_stats``, which is the
    only way to answer "which block is eating the window"."""

    state: CompactionState = field(default_factory=CompactionState)
    """Summary and anchors so far. Pass back in so a second compaction
    extends the first summary instead of starting over."""

    compaction: CompactionRecord | None = None
    """The last compaction of this exchange; ``None`` when none ran."""

    compactions: tuple[CompactionRecord, ...] = ()
    """Every compaction of this exchange, oldest first — one model call
    may compact, and a long run may compact several times."""

    @property
    def reply(self) -> str:
        """The assistant's final text, or ``""`` if the run produced none."""
        for message in reversed(self.result.messages):
            if message.role is Role.ASSISTANT and message.content:
                return message.content
        return ""

    @property
    def hit_the_turn_ceiling(self) -> bool:
        """Whether the loop stopped because ``max_turns`` ran out."""
        return self.result.stop_reason is StopReason.MAX_TURNS


def compose(
    app: AgentApp,
    history: Sequence[Message] = (),
    user_text: str = "",
) -> tuple[tuple[Message, ...], AssembledPrompt]:
    """Render the system prompt and put a conversation in front of it.

    Returns ``([system, *history, user?], prompt)``. *history* must not
    contain a system message of its own; :class:`TurnOutcome.history` is
    already stripped of one.

    The render happens here rather than at start-up, which is what makes
    a mid-run edit to any prompt file visible on the next exchange.
    """
    prompt = app.prompt.render()
    return assemble(prompt, history, user_text), prompt


async def prepare(
    app: AgentApp,
    history: Sequence[Message] = (),
    user_text: str = "",
    *,
    state: CompactionState | None = None,
) -> tuple[
    tuple[Message, ...],
    AssembledPrompt,
    CompactionState,
    CompactionRecord | None,
]:
    """Compose a conversation and compact it as the first model call would.

    Returns the conversation that call would be sent, the render behind
    it, the compaction state to carry, and the record if a compaction ran.
    Offloaded files and the compaction log are written as in a real turn.

    **The plan block is not applied**, so this is a preview of compaction
    rather than of the exact bytes a call would carry. Deliberate: a real
    call appends whatever
    :class:`~omicsclaw.planning.PlanInjector` renders *at that moment*,
    and a preview that reached into a session's live plan would report
    something that had already changed by the time it was read.
    """
    messages, prompt = compose(app, history, user_text)
    compactor = build_compactor(app, state=state)
    rewrite = await compactor.compact(messages, app.tools_snapshot)
    if rewrite is not None and rewrite[0]:
        messages = tuple(rewrite[0])
    return messages, prompt, compactor.state, compactor.last_record


@dataclass(slots=True)
class _Carried:
    """One exchange's history, and where the engine leaves the next one.

    Satisfies :class:`~omicsclaw.engine.Conversation` structurally — no
    base class, no import in the other direction. The engine reads
    :meth:`messages` once to compose its first call and calls
    :meth:`commit` once with the finished trajectory, system message
    already removed.

    **In memory only.** Writing a session to disk is
    :class:`~omicsclaw.entry.session.SessionRegistry`'s job, and it has
    to store the compaction state in the same breath — a thing the
    engine cannot see. One writer, holding both halves, rather than two
    each holding one.
    """

    history: tuple[Message, ...] = ()
    """What this exchange starts from, free of a system message (Q3)."""

    committed: tuple[Message, ...] | None = None
    """What the engine handed back, or ``None`` if it never got that far."""

    def messages(self) -> tuple[Message, ...]:
        return self.history

    async def commit(self, messages: Sequence[Message]) -> None:
        self.committed = tuple(messages)

    @property
    def carried(self) -> tuple[Message, ...]:
        """The conversation to keep: the commit, or the input unchanged.

        An exchange that raised or was abandoned never committed, and
        the right history for it is the one it was given — cancelling an
        exchange discards *it*, not the conversation (plan 0031 trap 3).
        """
        return self.history if self.committed is None else self.committed


@dataclass(frozen=True, slots=True)
class _Exchange:
    """The collaborators one exchange hands the engine, built once.

    Plan 0027 §12.4: this assembly used to be written out at each of the
    three call sites below, and a step missed at any of them failed
    silently — a compactor built without its listeners publishes no
    frames, an injector never built means the plan quietly stops being
    restated. One constructor, three callers, one place to get it wrong.
    """

    conversation: _Carried
    compactor: ProgressiveCompactor
    augmentor: TurnAugmentor | None


def _assemble(
    app: AgentApp,
    history: Sequence[Message] = (),
    *,
    session_id: str = "",
    state: CompactionState | None = None,
    plan_block: bool = True,
    on_measure: Callable[[BudgetReport], None] | None = None,
    on_compact: Callable[[CompactionRecord], None] | None = None,
) -> _Exchange:
    """Everything one exchange needs before the engine is called.

    *plan_block* is false for the compaction-only path, which never
    calls a model: asking for the injector would restore the session's
    plan from its archive for an exchange that has no turn to remind.
    """
    return _Exchange(
        conversation=_Carried(tuple(history)),
        compactor=build_compactor(
            app,
            session_id=session_id,
            state=state,
            on_measure=on_measure,
            on_compact=on_compact,
        ),
        augmentor=build_injector(app, session_id=session_id) if plan_block else None,
    )


async def _run(app: AgentApp, exchange: _Exchange, user_text: str) -> RunResult:
    """The blocking engine call, spelled once.

    ``prompt=app.prompt`` is passed on every call rather than left to
    whatever default the engine was built with. :func:`build_app` gives
    its engine that same assembler, so this is usually the same object
    twice — but an app assembled around an engine somebody else built
    still renders *this* deployment's prompt, and a render is what
    :func:`_outcome` requires.
    """
    return await app.engine.exchange(
        user_text,
        conversation=exchange.conversation,
        prompt=app.prompt,
        compactor=exchange.compactor,
        augmentor=exchange.augmentor,
    )


def _stream(
    app: AgentApp, exchange: _Exchange, user_text: str
) -> AsyncIterator[EngineEvent]:
    """The streaming engine call, spelled once. See :func:`_run`."""
    return app.engine.exchange_stream(
        user_text,
        conversation=exchange.conversation,
        prompt=app.prompt,
        compactor=exchange.compactor,
        augmentor=exchange.augmentor,
    )


def _outcome(result: RunResult, exchange: _Exchange) -> TurnOutcome:
    """What the caller keeps, read off the run and its collaborators.

    The render comes back on the :class:`~omicsclaw.engine.RunResult`
    rather than from a second ``app.prompt.render()``: the engine did
    the reading, and re-reading ``OMICSCLAW.md`` here would report a prompt
    that may already differ from the one this exchange was sent. It is
    an :class:`~omicsclaw.context.AssembledPrompt` because every caller
    below hands the engine ``app.prompt`` for this call rather than
    relying on whatever default that engine was built with — a test's
    hand-built engine has none, and this layer's contract is that
    :attr:`TurnOutcome.prompt` is always a render.
    """
    compactor = exchange.compactor
    return TurnOutcome(
        result=result,
        history=exchange.conversation.carried,
        prompt=cast(AssembledPrompt, result.prompt),
        state=compactor.state,
        compaction=compactor.last_record,
        compactions=compactor.records,
    )


@contextmanager
def _session_bound(session_id: str) -> Iterator[None]:
    """Tell this exchange's tools which session they are running in.

    :class:`TurnRunner` binds the same fact through
    :meth:`TurnRunner.turn_values`; these two functions had no equivalent,
    so a tool that resolves its session from the context — ``plan_write``
    is the first — resolved every :func:`run_turn` exchange to the
    anonymous one. The symptom was a plan written in one turn and gone by
    the next, with nothing raised anywhere.

    **The outer context is inherited explicitly**, which
    :func:`~omicsclaw.tools.context.use_tool_context` documents as the way
    to do it: that function *replaces* rather than merges, so binding a
    bare ``values`` here would silently unbind an approval channel a
    caller had set around this call, and every gated tool would start
    failing closed.
    """
    outer = current_context()
    with use_tool_context(
        approval=outer.approval,
        progress=outer.progress,
        values={**outer.values, "session_id": session_id},
    ):
        yield


async def run_turn(
    app: AgentApp,
    history: Sequence[Message] = (),
    user_text: str = "",
    *,
    state: CompactionState | None = None,
    session_id: str = "",
) -> TurnOutcome:
    """Run one exchange to convergence and hand back what to keep.

    The conversation is compacted before every model call; *session_id*
    names where offloaded tool results and compaction records are kept.

    Applies :attr:`~omicsclaw.entry.config.AppConfig.turn_timeout_s` when
    one is configured; ``None`` means a turn may take as long as its
    tools do, which for a deconvolution is the honest answer.

    :raises TimeoutError: the turn deadline expired. The engine's tasks
        are cancelled by :func:`asyncio.timeout` on the way out, and the
        exchange leaves no partial history behind.
    """
    exchange = _assemble(app, history, session_id=session_id, state=state)

    timeout = app.config.turn_timeout_s
    with _session_bound(session_id):
        async with app.telemetry.run(
            session_id=session_id, prompt=user_text, turn_events=False
        ) as scope:
            if timeout is None:
                result = await _run(app, exchange, user_text)
            else:
                async with asyncio.timeout(timeout):
                    result = await _run(app, exchange, user_text)
            # ``run`` drops the engine's events by design, so the one
            # event the interaction span needs is re-made from what it
            # returned. This is not a fabrication: ``DONE`` carrying this
            # ``RunResult`` is exactly what ``run_stream`` would have
            # yielded last. What cannot be recovered is the turn
            # boundaries, so this path's trace has two levels rather than
            # three — see :mod:`omicsclaw.observability.scope`.
            scope.observe(EngineEvent.done(result))

    return _outcome(result, exchange)


async def stream_turn(
    app: AgentApp,
    history: Sequence[Message] = (),
    user_text: str = "",
    *,
    state: CompactionState | None = None,
    session_id: str = "",
) -> AsyncIterator[EngineEvent]:
    """Run one exchange, yielding the engine's events as they happen.

    The same composition and compaction as :func:`run_turn`; only the
    engine call differs. No turn deadline is applied — a consumer of a
    stream can stop consuming, and abandoning the iterator cancels the
    run, so the deadline belongs to whoever is reading.

    A caller that needs the trajectory afterwards should use
    :func:`run_turn`: an event stream reports what happened, not what to
    carry forward.
    """
    exchange = _assemble(app, history, session_id=session_id, state=state)
    with _session_bound(session_id):
        async with app.telemetry.run(
            session_id=session_id, prompt=user_text
        ) as scope:
            async for event in _stream(app, exchange, user_text):
                scope.observe(event)
                yield event


TurnState = Literal["queued", "running", "terminal"]
"""Where one submitted exchange is. ``"queued"`` is a real state, not a
transient: plan 0031 Q7 makes ``submit()`` return before the exchange
starts, so a surface can be holding a handle to something that has not
begun, and can cancel it."""


class TurnRunner:
    """One exchange's canonical sequence, run inside its own Task.

    Plan 0031 §3.3, instrumented. :func:`run_turn` is the same sequence
    for a caller that wants an answer; this is the same sequence for a
    caller that wants to *watch* one, and the difference is not cosmetic:
    every step publishes a frame, the approval channel and the progress
    sink are bound for the tools, and the terminal frame is emitted from
    ``finally`` so it exists on the paths where the sequence did not
    finish.

    The compactor it hands the engine publishes a ``CONTEXT`` frame for
    every measurement and a ``COMPACTION`` frame for every compaction,
    ahead of the model call they precede.

    ``force_compaction=True`` makes the exchange a compaction only: the
    session's history is summarized as a FULL compaction regardless of
    pressure, no model turn runs, and the history is replaced only when
    the compaction is written back.

    **Await it inside a Task of its own.** :meth:`run` binds the tool
    context with :func:`~omicsclaw.tools.use_tool_context`, and
    ``contextvars`` isolate per Task rather than per coroutine: two
    exchanges awaited from *one* Task would see the second binding win,
    and one user's tool call would be offered to the other user's
    approval prompt (``omicsclaw/tools/context.py`` Q4.5). The binding is
    inside :meth:`run` — not in ``__init__`` — so that constructing two
    runners in one coroutine and running them concurrently is safe;
    :class:`~omicsclaw.entry.session.SessionRegistry` always gives each
    exchange its own Task.
    """

    __slots__ = (
        "_app",
        "_approval",
        "_compaction",
        "_force",
        "_history",
        "_shortfall_reported",
        "_stream",
        "_user_text",
        "_values",
        "error",
        "outcome",
        "session_id",
        "terminal",
        "turn_id",
    )

    def __init__(
        self,
        app: AgentApp,
        stream: TurnStream,
        *,
        session_id: str = "",
        turn_id: str = "",
        history: Sequence[Message] = (),
        compaction: CompactionState | None = None,
        user_text: str = "",
        values: Mapping[str, object] | None = None,
        approval: ApprovalBroker | None = None,
        force_compaction: bool = False,
    ) -> None:
        """*history* must already be free of a system message (Q3).

        *approval* is typed as the broker rather than as the wider
        :data:`~omicsclaw.tools.ApprovalChannel` because this layer owes
        two things a bare callable cannot give: an outstanding question
        that can be answered **by id** from another Task, and a way to
        fail every outstanding question closed when the exchange ends.
        """
        self._app = app
        self._stream = stream
        self.session_id = session_id
        self.turn_id = turn_id
        self._history = tuple(history)
        self._compaction = compaction or CompactionState()
        self._user_text = user_text
        self._values = dict(values or {})
        self._approval = approval
        self._force = force_compaction
        self._shortfall_reported = False
        self.terminal: Terminal = "failed"
        self.error: BaseException | None = None
        self.outcome: TurnOutcome | None = None

    async def run(self) -> TurnOutcome:
        """Run the exchange, publishing every step, and return what to keep.

        The terminal frame is published from ``finally`` whatever
        happened, so a consumer on the far side of HTTP or an IM
        transport always sees an ending rather than a stream that merely
        stopped (plan 0031 trap 1b). :attr:`terminal`, :attr:`error` and
        :attr:`outcome` record the same verdict for the caller that owns
        the Task, which is what lets
        :class:`~omicsclaw.entry.session.SessionRegistry` decide about
        persistence without deriving the verdict a second time.

        Exceptions still propagate. A cancelled exchange raises
        :exc:`asyncio.CancelledError` after reporting
        ``terminal="cancelled"`` — the frame says so *and* the Task is
        genuinely cancelled, because folding cancellation into a return
        value is how a cancelled Task starts looking finished to
        :mod:`asyncio`.
        """
        self._publish(
            TurnEvent.exchange_start(
                session_id=self.session_id, turn_id=self.turn_id
            )
        )
        _log.info(
            "exchange started: session=%s turn=%s", self.session_id, self.turn_id
        )
        try:
            with use_tool_context(
                approval=self._approval,
                progress=self._on_progress,
                values=self.turn_values(),
            ):
                outcome = await self._deadline()
            self.outcome = outcome
            self.terminal = "converged"
            return outcome
        except asyncio.CancelledError as exc:
            self.terminal, self.error = "cancelled", exc
            raise
        except BaseException as exc:
            self.terminal, self.error = "failed", exc
            raise
        finally:
            if self._approval is not None:
                self._approval.abandon()
            self._publish(
                TurnEvent.exchange_end(
                    self.terminal,
                    error=self.error,
                    session_id=self.session_id,
                    turn_id=self.turn_id,
                )
            )
            _log.info(
                "exchange ended: session=%s turn=%s terminal=%s error=%s",
                self.session_id,
                self.turn_id,
                self.terminal,
                type(self.error).__name__ if self.error is not None else "",
            )

    def turn_values(self) -> dict[str, object]:
        """Session-level facts, plus the two this exchange adds.

        The session's own bag is the base and the exchange's identity is
        written over it, so a stale ``turn_id`` stored on a session
        cannot shadow the running one. This is what reaches a tool
        through :func:`~omicsclaw.tools.context_value`.
        """
        return {
            **self._values,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
        }

    # ---- internals ------------------------------------------------------

    def _publish(self, event: TurnEvent | None) -> None:
        self._stream.publish(event)

    def _on_progress(self, update: ProgressUpdate) -> None:
        """The progress sink bound for this exchange's tools.

        Synchronous and incapable of raising, because
        :func:`~omicsclaw.tools.report_progress` treats a sink that
        raises as no progress at all and a sink that *blocks* would make
        a heartbeat cost a tool its throughput.
        :meth:`TurnStream.publish` neither blocks nor raises, which is
        the whole implementation.
        """
        self._publish(
            TurnEvent.progress_update(
                update, session_id=self.session_id, turn_id=self.turn_id
            )
        )

    async def _deadline(self) -> TurnOutcome:
        """Apply ``turn_timeout_s`` to the **whole** exchange (Q12).

        Wider than :func:`run_turn`, which times only the engine call:
        the number exists so that one stuck ``bash`` cannot hold a
        session for ``tool_timeout_s × max_turns``, and compaction is
        inside the same wall clock because a summarizer that hangs holds
        the session just as effectively.

        An expiry is ``terminal="failed"``, not ``"cancelled"``: nobody
        asked for it to stop, a deadline this deployment configured ran
        out, and a surface that retries cancellations but not failures
        would otherwise retry straight back into the same wall.
        """
        timeout = self._app.config.turn_timeout_s
        if timeout is None:
            return await self._sequence()
        async with asyncio.timeout(timeout):
            return await self._sequence()

    async def _sequence(self) -> TurnOutcome:
        """assemble → exchange_stream → carry, publishing every step."""
        app = self._app
        user_text = "" if self._force else self._user_text
        exchange = _assemble(
            app,
            self._history,
            session_id=self.session_id,
            state=self._compaction,
            plan_block=not self._force,
            on_measure=self._on_measure,
            on_compact=self._on_compacted,
        )
        if self._force:
            messages, prompt = compose(app, self._history, user_text)
            return await self._compact_only(exchange.compactor, messages, prompt)

        result: RunResult | None = None
        async with app.telemetry.run(
            session_id=self.session_id, prompt=user_text
        ) as scope:
            async for event in _stream(app, exchange, user_text):
                scope.observe(event)
                if event.result is not None:
                    result = event.result
                self._publish(
                    TurnEvent.from_engine(
                        event, session_id=self.session_id, turn_id=self.turn_id
                    )
                )
        if result is None:  # pragma: no cover - the engine's own invariant
            raise EngineError("the engine's event stream ended without a result")
        return _outcome(result, exchange)

    async def _compact_only(
        self,
        compactor: ProgressiveCompactor,
        messages: tuple[Message, ...],
        prompt: AssembledPrompt,
    ) -> TurnOutcome:
        """Summarize the session now; keep the result only if written back."""
        compacted, record = await compactor.force(messages, self._app.tools_snapshot)
        kept = compacted if record.written_back else messages
        return TurnOutcome(
            result=RunResult(messages=kept, stop_reason=StopReason.CONVERGED),
            history=tuple(kept[PINNED_SYSTEM_MESSAGES:]),
            prompt=prompt,
            state=compactor.state,
            compaction=record,
            compactions=compactor.records,
        )

    def _on_measure(self, report: BudgetReport) -> None:
        self._publish(
            TurnEvent.context(report, session_id=self.session_id, turn_id=self.turn_id)
        )
        if report.tool_reserve_shortfall and not self._shortfall_reported:
            self._shortfall_reported = True
            _log.warning(
                "tool declarations exceed their reserve by %d tokens; "
                "the window left for the conversation is smaller than budgeted",
                report.tool_reserve_shortfall,
            )

    def _on_compacted(self, record: CompactionRecord) -> None:
        self._publish(
            TurnEvent.compacted(
                record, session_id=self.session_id, turn_id=self.turn_id
            )
        )


class TurnHandle:
    """What a surface holds onto after submitting: identity, not a cursor.

    Plan 0031 Q14. The drafted design had one object that was the
    exchange's identity *and* its only event consumer *and* the approval
    entry point, which breaks the first time a Desktop client reconnects:
    the new HTTP request cannot be handed the iterator the old one was
    holding. So a handle owns a :class:`~omicsclaw.entry.stream.
    TurnStream` and hands out as many :class:`~omicsclaw.entry.stream.
    TurnObservation` cursors over it as anybody asks for.

    It also owns this exchange's :class:`~omicsclaw.entry.approval.
    ApprovalBroker`, because "which exchange is being asked about" and
    "which exchange is being watched" are the same question, and an
    approval addressed to an exchange nobody can name is an approval that
    cannot be routed.

    Created by :class:`~omicsclaw.entry.session.SessionRegistry`, which
    drives the state machine through the underscore-prefixed methods
    below. They are private to the package rather than to the class: the
    registry is the only legitimate driver, and a surface calling
    ``_settle`` would be writing the verdict on an exchange it did not
    run.
    """

    __slots__ = (
        "_grace_s",
        "_had_observer",
        "_settled",
        "_task",
        "_timer",
        "approvals",
        "compaction_only",
        "error",
        "outcome",
        "session_id",
        "state",
        "stream",
        "terminal",
        "text",
        "turn_id",
        "values",
    )

    def __init__(
        self,
        *,
        session_id: str,
        turn_id: str,
        text: str = "",
        values: Mapping[str, object] | None = None,
        ring_size: int = DEFAULT_RING_SIZE,
        observer_queue_size: int | None = None,
        approval_timeout_s: float | None = None,
        abandon_grace_s: float | None = None,
        compaction_only: bool = False,
    ) -> None:
        """``abandon_grace_s=None`` means an unwatched exchange keeps running.

        ``compaction_only=True`` marks an exchange that compacts the
        session instead of sending it a message.

        The grace period is the answer to "the last observer left" and
        **not** to "an observer stopped iterating" (plan 0031 trap 9,
        Q14): a browser refresh must not kill an exchange that has been
        running for eight minutes, and a cursor that broke out of its
        ``async for`` without closing is still attached as far as
        :meth:`TurnStream.observer_count` is concerned.

        ``observer_queue_size=None`` sizes one observer's buffer to
        *ring_size*, and that default is load-bearing rather than tidy.
        The engine publishes every delta of one model call between two of
        the provider's ``await`` points, so no consumer Task is scheduled
        during the burst: an observer buffer tighter than the ring starts
        discarding text a stream that retains it is still holding, and a
        chat that drops tokens is wrong rather than degraded. Both
        structures hold *references to the same frames*, so the tighter
        bound bought one pointer per frame and paid for it in characters
        the user never sees. ``AppConfig.delta_ring_size`` is therefore
        the one knob for both, and an explicit value here is for a
        consumer that genuinely wants to shed load.
        """
        self.session_id = session_id
        self.turn_id = turn_id
        self.text = text
        self.compaction_only = compaction_only
        self.values: Mapping[str, object] = dict(values or {})
        self.state: TurnState = "queued"
        self.terminal: Terminal | None = None
        self.error: BaseException | None = None
        self.outcome: TurnOutcome | None = None
        self._task: asyncio.Task[TurnOutcome] | None = None
        self._settled = asyncio.Event()
        self._had_observer = False
        self._timer: asyncio.TimerHandle | None = None
        self._grace_s = abandon_grace_s
        self.stream = TurnStream(
            session_id,
            turn_id,
            ring_size=ring_size,
            observer_queue_size=(
                ring_size if observer_queue_size is None else observer_queue_size
            ),
            on_observer_change=self._observers_changed,
        )
        self.approvals = ApprovalBroker(self.stream, timeout_s=approval_timeout_s)

    def observe(self, *, after_seq: int = 0) -> TurnObservation:
        """Open a cursor over this exchange. May be called many times.

        ``after_seq`` is a resume point, so a reconnecting client passes
        the ``seq`` of the last frame it processed and gets the rest —
        including, when its cursor has fallen off the retained ring, an
        explicit ``GAP`` frame rather than a silent jump.
        """
        return self.stream.observe(after_seq=after_seq)

    async def approve(self, request_id: str, decision: ApprovalDecision) -> None:
        """Answer one of this exchange's outstanding approval requests.

        An unknown or already-settled ``request_id`` is a **no-op and not
        an error** (plan 0031 Q18): the input comes from a person, and a
        person clicking twice, clicking after the deadline or clicking a
        card their client re-rendered after a reconnect are all ordinary.

        ``async`` although nothing here awaits: answering is a surface's
        act on a handle it may only hold across a network, and a
        coroutine is the shape that stays right when that answer has to
        travel. The blocking work is elsewhere by construction — the
        exchange's own Task is what resumes.
        """
        if self.approvals.settle(request_id, decision):
            return
        _log.debug(
            "approval %s on turn %s had nothing to settle",
            request_id,
            self.turn_id,
        )

    def cancel(self) -> None:
        """Ask this exchange to stop. Idempotent, and safe at any state.

        A queued exchange is marked and never starts; a running one has
        its Task cancelled. A terminal one is a no-op, because a handle
        outlives its exchange for exactly as long as somebody might still
        be replaying it.

        Cancelling does **not** discard the conversation — it discards
        *this* exchange. ``session.history`` is left byte-for-byte as it
        was, because the engine's trajectory only exists on its ``DONE``
        event and reconstructing it from the event stream would be lossy
        (plan 0031 trap 3).
        """
        self._cancel_timer()
        if self.state == "terminal":
            return
        if self._task is not None:
            self._task.cancel()
            return
        self.terminal = "cancelled"

    async def wait(self) -> TurnOutcome | None:
        """Block until this exchange reaches a terminal state.

        Returns the outcome, or ``None`` when the exchange was cancelled
        or failed — the same distinction :attr:`terminal` carries, for a
        caller that has no use for the event stream. A CLI that submits
        one question and prints one answer is that caller.
        """
        await self._settled.wait()
        return self.outcome

    @property
    def done(self) -> bool:
        """Whether this exchange has reached a terminal state."""
        return self.state == "terminal"

    # ---- driven by the registry -----------------------------------------

    def _publish_queued(self, ahead: int) -> None:
        """Announce the queue depth this exchange arrived behind (Q7)."""
        self.stream.publish(
            TurnEvent.queued(
                ahead, session_id=self.session_id, turn_id=self.turn_id
            )
        )

    def _start(self, task: asyncio.Task[TurnOutcome]) -> None:
        """Adopt the Task running this exchange."""
        self.state = "running"
        self._task = task

    def _settle(
        self,
        terminal: Terminal,
        error: BaseException | None = None,
        outcome: TurnOutcome | None = None,
    ) -> None:
        """Record the verdict and release :meth:`wait`."""
        self._cancel_timer()
        self.state = "terminal"
        self.terminal = terminal
        self.error = error
        self.outcome = outcome
        self._settled.set()

    def _publish_terminal(self, terminal: Terminal) -> None:
        """Emit the terminal frame for an exchange that had no runner.

        The frame is this layer's obligation however an exchange ended,
        and two paths reach a terminal state without a
        :class:`TurnRunner` ever entering its ``try``: an exchange
        cancelled while still queued, and one whose Task was cancelled
        before it executed a statement. The stream seals on the first
        such frame, so this is a backstop rather than a second emitter.
        """
        self.stream.publish(
            TurnEvent.exchange_end(
                terminal, session_id=self.session_id, turn_id=self.turn_id
            )
        )

    def _end_unstarted(self) -> None:
        """Close an exchange that was cancelled while it was still queued."""
        self._publish_terminal("cancelled")
        self._settle("cancelled")

    # ---- the "nobody is watching" seam ----------------------------------

    def _observers_changed(self, count: int) -> None:
        """React to an observer attaching or detaching (trap 9).

        Arms the grace timer only on a transition to *zero* observers and
        only once there has been at least one: an exchange nobody ever
        watched — a scripted run, a channel that will observe later — is
        not an abandoned exchange, and cancelling it would make "submit
        and await the answer" unusable.
        """
        if count > 0:
            self._had_observer = True
            self._cancel_timer()
            return
        if not self._had_observer or self.state == "terminal":
            return
        self._arm_timer()

    def _arm_timer(self) -> None:
        if self._grace_s is None or self._timer is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - a detach outside the loop
            return
        self._timer = loop.call_later(self._grace_s, self._abandoned)

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _abandoned(self) -> None:
        self._timer = None
        if self.state == "terminal" or self.stream.observer_count():
            return
        _log.info(
            "cancelling turn %s: no observer for %.1fs",
            self.turn_id,
            self._grace_s or 0.0,
        )
        self.cancel()
