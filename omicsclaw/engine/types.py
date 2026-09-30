"""``omicsclaw/engine`` — what one ReAct run returns, and what it emits.

Plan 0027, step 3 of the staged framework rebuild. Step 1
(:mod:`omicsclaw.schema`, ADR 0077) gave the system a vocabulary and step
2 (:mod:`omicsclaw.provider`, plan 0026) gave it a way to speak; this
layer is the loop that drives

    Message → ToolCall → ToolResult → Message

to convergence. The types here are that loop's two outputs:
:class:`RunResult`, what a blocking run returns, and :class:`EngineEvent`,
what a streaming run yields.

Three names were drafted in step 1 and then removed again. This is the
step that owns them, and the answer is **one of the three**:

``StopReason``
    Kept. A run has three ways to stop and only an error string told them
    apart in the reference harness; an enum is the cheapest way to let
    "did it finish, or did it run out of room" be answered by data.

``Trajectory``
    Dropped. The trajectory *is* the ``tuple[Message, ...]`` on
    :class:`RunResult`. Wrapping a list of messages in a type pays for
    itself only when the list needs annotating, and nothing needs that
    yet.

``AgentStep``
    Dropped. A per-turn record's only plausible consumer is persistence,
    which is step 6. Fixing its shape before the layer that stores it
    exists is precisely the mistake step 1 avoided by removing it.

**Leaf-adjacent.** ``omicsclaw.schema`` and the standard library, nothing
else. No I/O, no logging, no vendor SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from omicsclaw.schema import Message, ToolCall, ToolResult, Usage

from .prompt import RenderedPrompt


class StopReason(StrEnum):
    """Why a run stopped — and there are exactly three ways.

    **What is absent is the point.** There is no ``ERROR`` member and no
    ``CANCELLED`` member, because neither is a return value:

    - A provider failure leaves the loop as a raised
      ``ProviderError``. Step 2 already chose between raising and
      yielding an error value; the loop does not reopen that question.
    - A cancelled scope leaves as :exc:`asyncio.CancelledError`,
      untouched. Cancellation is not a failure and it is not a result —
      turning it into either would tell a caller who cancelled a run that
      the run had an opinion about it.

    So a :class:`RunResult` exists only when the loop stopped on its own
    terms, and a ``stop_reason`` never has to be checked for "did this
    actually work".
    """

    CONVERGED = "converged"
    """The assistant turn requested no tools — the ReAct exit.

    The single branch the loop turns on, expressed as
    ``Message.is_action`` being false: tools requested means continue,
    no tools means the model considers the task answered.
    """

    MAX_TURNS = "max_turns"
    """The turn ceiling was reached with the model still asking to act.

    Not an error, and not convergence: the work is real and the
    trajectory is kept. The reference harness discards the whole
    trajectory here, which is what makes its budget exhaustion
    indistinguishable from a crash.
    """

    TRUNCATED = "truncated"
    """The output ceiling cut the turn off mid-sentence.

    Reported when the vendor's ``finish_reason`` says the response hit
    ``length`` / ``max_tokens``. Distinct from ``CONVERGED`` because a
    truncated reply also requests no tools, so without this member a
    severed answer would be handed back as a completed task.
    """


class EngineEventType(StrEnum):
    """Kind of payload in one :class:`EngineEvent`.

    Six members, and no ``ERROR``. The reference harness needs an error
    event because a Go channel cannot carry an exception; an async
    generator can — the consumer's ``async for`` re-raises at the
    iteration point, which is what a Python caller already expects.
    Inventing an error event would make every consumer hand-write a
    branch the language gives away for free.

    No approval event either. A tool waits for a person's answer inside
    the generator's ``__anext__``, so the generator cannot yield while the
    question is open; the entry layer reports it instead, as
    ``TurnEventType.APPROVAL_REQUIRED`` and ``APPROVAL_SETTLED`` in
    :mod:`omicsclaw.entry.events`.
    """

    TEXT_DELTA = "text_delta"
    """Assistant text, token by token."""

    REASONING_DELTA = "reasoning_delta"
    """Thought tokens, kept separate from text so a Surface can render or
    hide the Reasoning half of ReAct without parsing it back out."""

    TOOL_START = "tool_start"
    """The loop is about to execute one :class:`~omicsclaw.schema.ToolCall`."""

    TOOL_RESULT = "tool_result"
    """One tool finished. Carries the Observation, including a failed one:
    ``ToolResult.is_error`` is shown, never swallowed."""

    TURN_END = "turn_end"
    """One Thought→Action→Observation cycle completed."""

    DONE = "done"
    """The run ended. Carries the :class:`RunResult`."""


@dataclass(frozen=True, slots=True)
class RunResult:
    """Everything one finished run produced.

    Returned instead of raising-or-nothing so that a run which stopped on
    a ceiling still hands back its work. The reference harness's ``Run``
    returns only an ``error`` and drops the trajectory when it hits
    ``maxTurns``, which throws away exactly the turns that cost the most.

    Frozen for the same reason :class:`~omicsclaw.schema.Message` is: a
    result is a record of what happened, and a record that can be edited
    after the fact is not evidence.
    """

    messages: tuple[Message, ...]
    """The full trajectory, **inputs included** — as last rewritten by the
    run's compactor, when one was given and kept a rewrite.

    The conversation the caller passed in is at the front, so the tuple
    is a conversation that can be fed straight back into the next run.
    Returning only the newly generated messages would make every caller
    re-splice history by hand, and get the ordering wrong once.
    """

    stop_reason: StopReason
    """Which of the three exits was taken."""

    usage: Usage = field(default_factory=Usage)
    """Token accounting summed across every turn of this run.

    Defaults to zeros rather than to ``None``, mirroring
    ``Completion.usage``, so totalling a session's cost is a plain sum
    and never special-cases a backend that reports nothing.
    """

    turns: int = 0
    """How many model calls this run made."""

    prompt: RenderedPrompt | None = None
    """The render this run opened with, or ``None`` when nothing rendered
    one — a bare :meth:`~omicsclaw.engine.loop.AgentEngine.run`, or an
    :meth:`~omicsclaw.engine.loop.AgentEngine.exchange` with no
    :class:`~omicsclaw.engine.prompt.PromptSource`.

    The one field here that is not a record of what the run *did*: it
    says how the run's input was assembled. It is carried anyway because
    the alternative is worse — a caller that wants the render's section
    statistics would have to render a second time, paying for the file
    reads again and getting a *different* answer whenever a prompt file
    changed in between. Reporting the bytes this run actually opened with
    is the only version of that fact worth having.
    """

    @property
    def final_message(self) -> Message | None:
        """The last message, or ``None`` when the trajectory is empty.

        ``None`` rather than an ``IndexError``: a run that was handed an
        empty conversation and stopped immediately is a legitimate — if
        useless — outcome, and a caller reaching for the answer should
        not have to guard the access with a length check first.
        """
        return self.messages[-1] if self.messages else None


@dataclass(frozen=True, slots=True)
class EngineEvent:
    """One increment of a streaming run.

    A single frozen dataclass with an enum tag, not a union of six small
    classes. That shape was established by
    :class:`~omicsclaw.schema.StreamChunk` in step 1, and matching the
    delivered schema is worth more than the marginal benefit of an
    exhaustive ``match``.

    Field validity follows :attr:`type`::

        TEXT_DELTA       -> delta, turn
        REASONING_DELTA  -> delta, turn
        TOOL_START       -> tool_call, turn
        TOOL_RESULT      -> tool_result, turn, duration_s
        TURN_END         -> turn, usage
        DONE             -> result
    """

    type: EngineEventType
    turn: int = 0
    """Which model call this event belongs to, 1-based once a run starts.
    Absent from ``DONE``, which is about the run and not about a turn."""

    delta: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    result: RunResult | None = None

    usage: Usage | None = None
    """The turn's **actual** token cost, as the provider reported it. Set
    on ``TURN_END``.

    ``None`` means the backend reported nothing — but **only a streamed
    run can say so**. ``StreamChunk.usage`` is optional, so the streaming
    path passes a missing figure through as ``None``; ``Completion.usage``
    is not, so the blocking path has only zeros to report and a silent
    backend is indistinguishable there from a turn that genuinely cost
    nothing. A consumer of :meth:`~omicsclaw.engine.loop.AgentEngine.run`
    therefore never sees ``None`` here, and should read a zero ``Usage``
    as "either" rather than as "free". Closing that gap needs
    ``Completion`` to be able to express it, which is
    :mod:`omicsclaw.provider`'s to change.

    Never an estimate. The reference harness emits a second, *pre-call*
    token event so a TUI can show context pressure before the model
    answers, but that needs a token counter this layer does not have and
    must not grow — it belongs to step 5. Carrying only the measured
    figure keeps the event honest: a consumer can trust it instead of
    having to ask which kind it received.

    Without it, a stream watcher learns the cost of a run only after the
    whole run ends, via :attr:`RunResult.usage`.
    """

    duration_s: float | None = None
    """Wall-clock seconds one tool took, measured by the scheduler. Set on
    ``TOOL_RESULT``.

    Measured around the :class:`~omicsclaw.engine.executor.ToolExecutor`
    call, so it counts the seam and the engine's own timeout wrapper as
    well as the tool. That is what makes it distinct from
    ``ToolResult.metadata["duration_s"]``, which a tool layer may or may
    not record and which ``observations`` drops before the message reaches
    a model. ``None`` means nothing timed this event.

    **It includes time the per-call budget deliberately excludes.** A tool
    that waited on a human is not charged for that wait by
    ``tool_timeout``, and *is* charged for it here, because this is
    wall-clock from the scheduler's side and a paused budget is not.
    Rendering this as "how long the tool took" therefore shows a person
    their own thinking time — the very number this layer argues a model
    must not be shown.
    """

    # ---- constructors ---------------------------------------------------

    @classmethod
    def text(cls, delta: str, turn: int = 0) -> EngineEvent:
        return cls(type=EngineEventType.TEXT_DELTA, turn=turn, delta=delta)

    @classmethod
    def reasoning(cls, delta: str, turn: int = 0) -> EngineEvent:
        return cls(type=EngineEventType.REASONING_DELTA, turn=turn, delta=delta)

    @classmethod
    def tool_start(cls, call: ToolCall, turn: int = 0) -> EngineEvent:
        return cls(type=EngineEventType.TOOL_START, turn=turn, tool_call=call)

    @classmethod
    def tool_finished(
        cls,
        result: ToolResult,
        turn: int = 0,
        duration_s: float | None = None,
    ) -> EngineEvent:
        """Named ``tool_finished``, deliberately not ``tool_done``.

        ``done`` already means "the whole run ended" on this type, and a
        constructor called ``tool_done`` sitting next to ``done`` would
        read as the same word twice for two different scopes.
        """
        return cls(
            type=EngineEventType.TOOL_RESULT,
            turn=turn,
            tool_result=result,
            duration_s=duration_s,
        )

    @classmethod
    def turn_end(cls, turn: int, usage: Usage | None = None) -> EngineEvent:
        return cls(type=EngineEventType.TURN_END, turn=turn, usage=usage)

    @classmethod
    def done(cls, result: RunResult) -> EngineEvent:
        return cls(type=EngineEventType.DONE, result=result)


class EngineError(RuntimeError):
    """A loop-level failure that is not the provider's fault.

    Reserved for invariants of **ours** that broke: the canonical one is
    :meth:`~omicsclaw.engine.loop.AgentEngine.run` finding that its own
    kernel ended without emitting a ``DONE`` event, since the kernel is
    code this package wrote and no backend can be blamed for it. A
    ``ProviderError`` passes through untouched rather than being wrapped
    in this, so ``except EngineError`` never silently catches a backend
    outage, and the two questions "did the model fail" and "did something
    break our own invariant" stay separately answerable.

    **A stream that ended without a ``DONE`` chunk is deliberately not
    one of these**, though it was once the example this docstring gave. A
    provider that stopped mid-answer broke the *provider's* contract, so
    it raises ``ProviderError`` — which is also what lets the retry
    budget absorb it, a dropped half-stream being precisely the failure
    :mod:`omicsclaw.engine.retry` exists to survive. Naming it here made
    that budget unreachable and killed such a run on first occurrence.
    """


__all__ = ["EngineError", "EngineEvent", "EngineEventType", "RunResult", "StopReason"]
