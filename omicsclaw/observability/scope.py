"""The span tree of one run, built from the events the loop already emits.

This module is this layer's answer to ``engine/observer.go`` plus
``observability/observer.go``, and it is the one place where the design
genuinely departs from the reference rather than merely being spelled
differently. **No seam was added to the engine.**

The reference has to add one. Go's loop can only be observed by being
called back, so ``internal/engine`` declares a four-method
``EngineObserver`` interface, stores one, and invokes it at four points.
This rebuild's loop already publishes a richer record of the same four
moments — :class:`~omicsclaw.engine.EngineEvent`, yielded by
``AgentEngine.run_stream`` — so the observer is a *consumer* of something
that exists rather than a hook that had to be cut into a leaf layer whose
own docstring forbids I/O. ``omicsclaw/engine/`` is unmodified by this
step, and ``tests/observability/test_observability_boundaries.py``
asserts that nothing in ``engine`` imports this package.

Three consequences are worth knowing before reading the code.

**There is no ``TURN_START`` event, so a turn span is created lazily.**
The kernel begins turn *N+1*'s work inside the very ``__anext__`` that
follows turn *N*'s ``TURN_END``, so the only honest moment to open the
next turn span is the instant after the previous one closed — at which
point nobody knows yet whether the run continues. Opening it eagerly
would export one empty phantom span at the end of every run.
:class:`TurnScope` therefore holds the *intent* to open a span and
materialises it the first time somebody asks for a parent, which is the
model call. A run that stops instead discards an intent, which costs
nothing and exports nothing. The price, stated so it is not rediscovered
as a bug: a turn span starts at its **model call**, so the compaction and
plan-injection that precede it fall outside — they are inside the
interaction span, just not inside the turn.

**The blocking path gets two levels, not three, and has to say so.**
``AgentEngine.run`` drives the same kernel and the kernel produces the
same events — ``run`` then **drops them** ("a caller who wants to watch a
run asked for ``run_stream``"). So a scope driving it is never told where
a turn ended, and the honest answer to *why* is in two halves, because
only the first half is forced:

- Turn 1 genuinely cannot be inferred in time. Its model call asks for a
  parent *before* any event could have arrived, so no amount of waiting
  helps and eager staging is the only option.
- Turns 2..N are a different matter. ``TURN_END`` for turn *N* exists
  inside the kernel at the moment turn *N+1* begins; it is discarded by
  ``run``'s own pre-existing contract, not by anything this layer decided.

So **two levels here is the cost of ``run``'s contract, not a limit of
the event model**: an observer attached inside the kernel, the way the
reference's ``EngineObserver`` is, would get three levels on both paths.
That trade was taken deliberately — not cutting a seam into a leaf layer
beats three levels on a path no surface drives — and it is written down
here rather than left in a commit message, so that reopening it is a
decision rather than a discovery.

Hence :attr:`RunScope.turn_events`, which
:func:`~omicsclaw.entry.turn.run_turn` sets to ``False`` and every
streaming caller leaves alone.

Getting it wrong is what the flag is designed against rather than what it
invites. Told ``False`` and sent turn events anyway, a scope starts
grouping from the next boundary — self-correcting. Told ``True`` and sent
none, it warns at exit naming the run it could not segment, because the
alternative is the failure this flag exists to prevent: **one turn span
labelled ``agent.turn=1`` silently containing every model call of a
five-turn run**, which is not a missing level but a wrong number.
Every count, duration and token figure is unaffected either way.

**Parenting is carried by one :class:`~contextvars.ContextVar`, and it is
a stack of one slot.** :func:`current_parent` is what
:class:`~omicsclaw.observability.provider.TracedProvider` and
:class:`~omicsclaw.observability.hook.TracingHook` call; they never
receive a parent as an argument, because the engine sits between them and
this module and must not learn that either exists. A
:class:`~contextvars.ContextVar` is the right carrier for the same reason
``omicsclaw/tools/context.py`` already uses one: each tool call runs in
its own :class:`asyncio.Task`, a Task copies the context at creation, so
concurrent tool calls cannot see each other's bindings and two
simultaneous sessions in one process cannot see each other's traces.

Imports :mod:`omicsclaw.engine`, :mod:`omicsclaw.schema` and the standard
library.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Protocol, runtime_checkable

from omicsclaw.engine import EngineEvent, EngineEventType, RunResult
from omicsclaw.schema import Usage

from .attributes import (
    ATTR_AGENT_TYPE,
    ATTR_CACHE_READ_TOKENS,
    ATTR_INPUT_TOKENS,
    ATTR_LANGFUSE_TRACE_INPUT,
    ATTR_LANGFUSE_TRACE_OUTPUT,
    ATTR_OUTPUT_TOKENS,
    ATTR_SESSION_ID,
    ATTR_STOP_REASON,
    ATTR_TURN_HAS_TOOL_CALLS,
    ATTR_TURN_NUMBER,
    ATTR_TURNS,
    METRIC_TURNS_TOTAL,
    SPAN_INTERACTION,
    SPAN_TURN,
)
from .contract import NOOP_SPAN, AttributeValue, Meter, Span, Tracer
from .serialize import serialize_output, truncate_attr

_log = logging.getLogger(__name__)

__all__ = [
    "RunScope",
    "SpanSource",
    "TurnScope",
    "current_parent",
    "fixed",
    "pop_parent",
    "push_parent",
]


@runtime_checkable
class SpanSource(Protocol):
    """Something a child span can be parented to.

    A level of indirection over :class:`~omicsclaw.observability.contract.Span`
    that exists for exactly one implementation — :class:`TurnScope`, whose
    span may not have been created yet. Every other binder wraps a span
    that is already open; :func:`fixed` is the one-liner for that case.
    """

    def span(self) -> Span:
        """The span to parent to, creating it if it does not exist."""
        ...


class _Fixed:
    """A :class:`SpanSource` over a span that is already open."""

    __slots__ = ("_span",)

    def __init__(self, span: Span) -> None:
        self._span = span

    def span(self) -> Span:
        return self._span


def fixed(span: Span) -> SpanSource:
    """Bind an already-open *span* as the parent for whatever runs next."""
    return _Fixed(span)


_CURRENT: ContextVar[SpanSource | None] = ContextVar(
    "omicsclaw_observability_parent", default=None
)
"""The innermost open scope in this task.

One slot rather than a list: the nesting is maintained by
:class:`~contextvars.Token` restoration, which is what makes it correct
under concurrency without a lock. A sub-agent driven from inside a tool
therefore lands where a reader expects — interaction → turn → tool →
*its own* interaction → …
"""


def push_parent(source: SpanSource) -> Token[SpanSource | None]:
    """Make *source* the parent for spans started in this task.

    Returns the token :func:`pop_parent` needs. A pair of functions rather
    than a context manager because the two halves happen in *different
    methods* on the one caller that matters —
    :class:`~omicsclaw.observability.hook.TracingHook` binds in
    ``before_execute`` and releases in ``after_execute`` or
    ``on_failure`` — and a context manager cannot span that.
    """
    return _CURRENT.set(source)


def pop_parent(token: Token[SpanSource | None]) -> None:
    """Undo one :func:`push_parent`. Safe to call from a wrong task.

    A :exc:`ValueError` here means the token was created in a different
    :class:`~contextvars.Context` — which happens when a generator is
    closed by the garbage collector rather than by its consumer. The
    binding in *that* context is going away with it, so there is nothing
    to repair and nothing to report beyond a debug line.
    """
    try:
        _CURRENT.reset(token)
    except ValueError:  # pragma: no cover - needs a cross-task close
        _log.debug("a telemetry parent was released from a foreign context")


def current_parent() -> Span | None:
    """The span a new child should hang from, or ``None`` for a root.

    ``None`` is a legitimate answer and not an error: a tool driven
    directly from a script, or a model call made outside any
    :class:`RunScope`, produces a span that is its own trace. Reporting
    that as a failure would make telemetry refuse to observe exactly the
    cases somebody is debugging.
    """
    source = _CURRENT.get()
    return None if source is None else source.span()


class _Flush(Protocol):
    """What :class:`RunScope` calls at the end of a clean exchange."""

    async def __call__(self) -> None: ...


class TurnScope:
    """The intent to open a turn span, and the span once somebody needs it.

    See this module's docstring for why the laziness is required rather
    than clever. The object is cheap enough to create per turn and to
    throw away unused, which is what makes "open one speculatively" the
    right shape.
    """

    __slots__ = (
        "_closed",
        "_failed",
        "_parent",
        "_span",
        "_tool_calls",
        "_tracer",
        "_turn",
    )

    def __init__(self, tracer: Tracer, parent: Span | None, turn: int) -> None:
        self._tracer = tracer
        self._parent = parent
        self._turn = turn
        self._span: Span | None = None
        self._tool_calls = False
        self._closed = False
        self._failed = False

    @property
    def turn(self) -> int:
        """Which turn this is, 1-based."""
        return self._turn

    @property
    def materialised(self) -> bool:
        """Whether a span was ever actually created.

        The property ``tests/observability/test_scope.py`` asserts on to
        pin that a finished run leaves no phantom turn behind.
        """
        return self._span is not None

    def span(self) -> Span:
        """The turn span, created on this call if it does not exist.

        **A tracer that raises here degrades the tree rather than the
        run**, and this is the one place in the package where that could
        not be left to the caller. :func:`current_parent` is called from
        inside
        :meth:`~omicsclaw.observability.provider.TracedProvider.generate`,
        on the path of an actual model call, so an exception escaping this
        method would take down an exchange because a metrics backend went
        away mid-run. The fallback is the parent — the interaction span,
        or nothing at all — so the trace loses its turn level and keeps
        everything else. Recorded in a flag so a backend that is down is
        reported **once per turn** rather than once per model call: a turn
        retried three times logs one line, and a five-turn run against a
        dead backend logs five. Each turn gets a fresh :class:`TurnScope`,
        so the flag cannot carry across one — which is a smaller promise
        than "once per run" and is the one that is true.
        """
        if self._span is not None:
            return self._span
        if self._failed:
            return self._parent if self._parent is not None else NOOP_SPAN
        try:
            self._span = self._tracer.start_span(
                SPAN_TURN,
                parent=self._parent,
                attributes={ATTR_TURN_NUMBER: self._turn},
            )
        except Exception:
            self._failed = True
            _log.exception("telemetry could not open a span for turn %d", self._turn)
            return self._parent if self._parent is not None else NOOP_SPAN
        return self._span

    def saw_tool_calls(self) -> None:
        """Remember that this turn requested at least one tool."""
        self._tool_calls = True

    def close(self, usage: Usage | None = None) -> None:
        """End the span if there is one. Idempotent, and a no-op if not.

        *usage* is recorded as **attributes only**. The token counters are
        :class:`~omicsclaw.observability.provider.TracedProvider`'s to
        add, because it is the seam that sees every model call including
        the retried ones; adding them here as well would double every
        figure on the streaming path and leave the blocking path at half.
        """
        if self._closed:
            return
        self._closed = True
        if self._span is None:
            return
        attributes: dict[str, AttributeValue] = {
            ATTR_TURN_HAS_TOOL_CALLS: self._tool_calls
        }
        attributes.update(_usage_attributes(usage))
        self._span.set_attributes(attributes)
        self._span.end()


class RunScope:
    """One exchange, observed. An async context manager around a run.

    Usage, and the whole of what a surface has to write::

        async with telemetry.run(session_id=sid, prompt=text) as scope:
            async for event in engine.run_stream(messages, ...):
                scope.observe(event)
                yield event

    **Nothing it does may change how the run ends.** Every public method
    contains its own failures: a backend that raises is logged and the
    exchange continues, which is the direction
    :class:`~omicsclaw.hooks.HookedTool` already established for
    interposition a deployment merely mounted. :exc:`BaseException` is
    deliberately *not* contained — a
    :exc:`~asyncio.CancelledError` arriving inside a telemetry call is a
    genuine cancellation of the turn, and the hooks layer has already paid
    for absorbing one of those once.
    """

    __slots__ = (
        "_agent_type",
        "_capture",
        "_flush",
        "_interaction",
        "_meter",
        "_prompt",
        "_result",
        "_saw_turn_end",
        "_session_id",
        "_token",
        "_tracer",
        "_turn",
        "_turn_events",
    )

    def __init__(
        self,
        tracer: Tracer,
        meter: Meter,
        *,
        session_id: str = "",
        prompt: str = "",
        capture_content: bool = False,
        agent_type: str = "main",
        turn_events: bool = True,
        flush: _Flush | None = None,
    ) -> None:
        self._tracer = tracer
        self._meter = meter
        self._session_id = session_id
        self._prompt = prompt
        self._capture = capture_content
        self._agent_type = agent_type
        self._turn_events = turn_events
        self._saw_turn_end = False
        self._flush = flush
        self._interaction: Span | None = None
        self._turn: TurnScope | None = None
        self._token: Token[SpanSource | None] | None = None
        self._result: RunResult | None = None

    @property
    def turn_events(self) -> bool:
        """Whether this scope will be shown ``TURN_END``.

        ``True`` for :meth:`~omicsclaw.engine.AgentEngine.run_stream`,
        which is what every live surface drives; ``False`` for
        :meth:`~omicsclaw.engine.AgentEngine.run`, which drops its events.
        See this module's docstring for why it cannot be inferred.
        """
        return self._turn_events

    @property
    def interaction(self) -> Span | None:
        """The root span, once entered. ``None`` before and after."""
        return self._interaction

    @property
    def turn(self) -> TurnScope | None:
        """The turn currently open, including one never materialised."""
        return self._turn

    async def __aenter__(self) -> RunScope:
        """Open the interaction span, and the scope for turn 1 if there is one.

        Turn 1 is staged without the hesitation the later turns get,
        because the kernel's ``while`` condition admits at least one turn
        for every configured ceiling — so unlike turn *N+1*, turn 1 is
        certain to happen. It is still a :class:`TurnScope` and so still
        lazy; what is certain is only that something will ask it for a
        span.

        When :attr:`turn_events` is ``False`` the interaction span is
        bound directly instead, and the model calls and tools of the whole
        run hang from it. A caller that cannot report boundaries gets no
        boundaries, rather than one span claiming to be a boundary it is
        not.
        """
        try:
            # Every attribute goes in at construction. A span created and
            # *then* decorated can be orphaned: if the second call raises,
            # the handler below drops the reference and nothing is left to
            # call `end()` on, so that trace disappears with no log line
            # explaining it. One all-or-nothing step instead, which is what
            # `TracedProvider._start` already did.
            attributes: dict[str, AttributeValue] = {
                ATTR_SESSION_ID: self._session_id,
                ATTR_AGENT_TYPE: self._agent_type,
            }
            if self._capture and self._prompt:
                attributes[ATTR_LANGFUSE_TRACE_INPUT] = truncate_attr(self._prompt)
            self._interaction = self._tracer.start_span(
                SPAN_INTERACTION, attributes=attributes
            )
            if self._turn_events:
                self._turn = TurnScope(self._tracer, self._interaction, 1)
                self._token = push_parent(self._turn)
            else:
                self._token = push_parent(fixed(self._interaction))
        except Exception:
            _log.exception("telemetry could not open an interaction span")
            self._interaction = None
            self._turn = None
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        """Close everything, then flush unless the run was cancelled.

        The reference flushes unconditionally in a ``defer``
        (``observer.go:86-93``). This flushes on a clean exit **and on an
        ordinary failure** — a ``ProviderError`` is exactly the trace
        somebody is about to go looking for — and skips it only for what
        is not an :exc:`Exception`.

        **That last clause is a correctness rule, not an optimisation.**
        Awaiting anything inside a task that is being cancelled raises
        :exc:`~asyncio.CancelledError` again, and catching it to protect
        the flush would swallow a real cancellation — precisely the defect
        ``omicsclaw/hooks/chain.py`` was repaired for. The same covers
        :exc:`GeneratorExit`, which is how an abandoned ``stream_turn``
        unwinds. Nothing is lost by skipping: the spans were handed to the
        exporter by :meth:`Span.end` above and go out with the next batch
        or at shutdown.

        A cancellation arriving *during* a legitimate flush is re-raised
        rather than absorbed, and
        ``test_scope.py::test_a_cancellation_during_a_flush_is_not_swallowed``
        pins it — because the argument above is exactly the kind a later
        refactor "tidies" back into the historic defect.

        Always returns ``False`` — a telemetry scope never suppresses what
        the run raised.
        """
        try:
            self._check_turn_reporting()
            if self._turn is not None:
                self._turn.close()
            if self._interaction is not None:
                if isinstance(exc, BaseException):
                    self._interaction.record_error(exc)
                self._interaction.set_attributes(self._final_attributes())
                self._interaction.end()
        except Exception:
            _log.exception("telemetry could not close an interaction span")
        finally:
            if self._token is not None:
                pop_parent(self._token)
            self._token = None
            self._turn = None
            self._interaction = None

        if self._flush is not None and (exc is None or isinstance(exc, Exception)):
            await self._flush()
        return False

    def _check_turn_reporting(self) -> None:
        """Warn when a scope expecting turn events was shown none.

        The symptom this catches is silent and the number it produces is
        wrong rather than missing: one span labelled ``agent.turn=1``
        containing every model call of the run. Only worth saying when the
        run actually had more than one turn — a one-turn run is correctly
        described by a single turn span either way.
        """
        if not self._turn_events or self._saw_turn_end:
            return
        if self._result is not None and self._result.turns > 1:
            _log.warning(
                "a telemetry scope was told to expect turn events and got none; "
                "%d model calls are grouped under one turn span. A caller "
                "driving AgentEngine.run should pass turn_events=False",
                self._result.turns,
            )

    def observe(self, event: EngineEvent) -> None:
        """Fold one engine event into the span tree.

        Three of the six event types are read and three are ignored, and
        the silence is as deliberate as the reading:

        ``TOOL_START``
            marks the turn as having acted. That is the whole of what this
            scope takes from the tool events — the spans and the timings
            belong to
            :class:`~omicsclaw.observability.hook.TracingHook`, which is
            inside the call and can tell a refusal from a crash.

        ``TURN_END``
            closes the turn and opens the intent for the next one. This is
            the only place a turn boundary is known.

        ``DONE``
            carries the :class:`~omicsclaw.engine.RunResult`, which is
            kept for :meth:`__aexit__` to write onto the root span.

        ``TOOL_RESULT`` is ignored so that the tool duration has exactly
        one owner: ``EngineEvent.duration_s`` is measured around the
        executor seam and *includes* a human's approval wait, which is a
        number no dashboard should show as "how long the tool took".
        ``hooks/audit.py`` refused a third timing for the same reason.
        ``TEXT_DELTA`` and ``REASONING_DELTA`` are ignored because the
        assembled message is already on the model call's own span.
        """
        try:
            self._observe(event)
        except Exception:
            _log.exception("telemetry could not record a %s event", event.type)

    def _observe(self, event: EngineEvent) -> None:
        if event.type is EngineEventType.TOOL_START:
            if self._turn is not None:
                self._turn.saw_tool_calls()
        elif event.type is EngineEventType.TURN_END:
            self._end_turn(event)
        elif event.type is EngineEventType.DONE:
            self._result = event.result

    def _end_turn(self, event: EngineEvent) -> None:
        """Close the turn this event ends and stage its successor.

        The successor is staged unconditionally, including after the turn
        that turns out to be the last. That costs one discarded
        :class:`TurnScope` per run and is what buys the phantom-free trace
        — see this module's docstring.
        """
        self._saw_turn_end = True
        if self._turn is not None:
            self._turn.close(event.usage)
        if self._interaction is not None:
            self._meter.count(METRIC_TURNS_TOTAL, 1)
        self._turn = TurnScope(self._tracer, self._interaction, event.turn + 1)
        if self._token is not None:
            # Rebinding rather than pushing: the slot is replaced in
            # place, so the single token taken in __aenter__ still
            # restores whatever was bound before this scope.
            _CURRENT.set(self._turn)

    def _final_attributes(self) -> dict[str, AttributeValue]:
        """What the root span learns from the run's own verdict.

        Empty when no ``DONE`` event arrived, which is what a cancelled or
        failed run looks like — the span still exists, still carries its
        session and its error, and simply does not claim a turn count it
        never saw.
        """
        result = self._result
        if result is None:
            return {}
        attributes: dict[str, AttributeValue] = {
            ATTR_TURNS: result.turns,
            ATTR_STOP_REASON: str(result.stop_reason),
        }
        attributes.update(_usage_attributes(result.usage))
        if self._capture:
            attributes[ATTR_LANGFUSE_TRACE_OUTPUT] = serialize_output(
                result.final_message
            )
        return attributes


def _usage_attributes(usage: Usage | None) -> dict[str, AttributeValue]:
    """Token figures as span attributes, or nothing at all.

    ``None`` produces an empty mapping rather than zeros. The distinction
    is real and this layer is the wrong place to erase it:
    ``EngineEvent.usage`` is ``None`` when the backend reported nothing
    and ``Usage()`` when it reported a free turn, and a span that wrote
    ``0`` for both would tell a cost dashboard that a silent backend is
    free.
    """
    if usage is None:
        return {}
    attributes: dict[str, AttributeValue] = {
        ATTR_INPUT_TOKENS: usage.input_tokens,
        ATTR_OUTPUT_TOKENS: usage.output_tokens,
    }
    if usage.cache_read_tokens:
        attributes[ATTR_CACHE_READ_TOKENS] = usage.cache_read_tokens
    return attributes

