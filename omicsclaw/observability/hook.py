"""One span and two measurements per tool call, through the hook seam.

The counterpart of ``observability/hook.go``, and the reason
:mod:`omicsclaw.hooks` exists as a mechanism at all — plan 0042 built the
seam and shipped the one hook nobody owned, naming this as the piece it
was deliberately not doing ("**No OpenTelemetry.** … A deployment that
wants OTEL writes a twelve-line sink"). This is that deployment's side of
the bargain, written once here rather than twelve lines at a time.

**It is not a second audit log.** :class:`~omicsclaw.hooks.AuditHook`
writes a durable local record, one line per call, digest only, mounted
**first** so that it hears a refusal from a hook mounted after it. This
one opens a span and records two instruments, and is mounted **last** so
that its span measures the tool and not its neighbours. They answer
different questions, they are switched on by different settings, and
neither can be derived from the other — but they share one vocabulary for
*how a call ended*, :class:`~omicsclaw.hooks.AuditOutcome`, because two
spellings of that would be two answers to one question.

**Where it sits in the chain, and the blind spot that follows.** The hook
chain runs *inside* the permission gate, so a call a rule denied never
reaches a hook and therefore never appears as a span. That is the same
blind spot ``observability/hook.go`` has, for the same reason
(``cmd/harness9/main.go:411-416``), and it is the right trade: a refusal
is a permission event, and
:class:`~omicsclaw.hooks.AuditHook`'s record is where it is already
written down.

Imports :mod:`omicsclaw.hooks` and this package.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass

from omicsclaw.hooks import AuditOutcome, Hook, HookCall, HookDecision, outcome_of

from .attributes import (
    ATTR_LANGFUSE_OBSERVATION_INPUT,
    ATTR_LANGFUSE_OBSERVATION_OUTPUT,
    ATTR_TOOL_NAME,
    ATTR_TOOL_STATUS,
    ATTR_TOOL_SUCCESS,
    METRIC_TOOL_CALLS,
    METRIC_TOOL_DURATION,
    SPAN_TOOL,
)
from .contract import AttributeValue, Meter, Span, Tracer
from .scope import SpanSource, current_parent, fixed, pop_parent, push_parent
from .serialize import truncate_attr

_log = logging.getLogger(__name__)

__all__ = ["TracingHook"]


@dataclass(slots=True)
class _Call:
    """What :meth:`TracingHook.before_execute` leaves for its closing half."""

    span: Span
    token: Token[SpanSource | None]
    """Restores the parent binding this call displaced."""

    call_token: "Token[_Call | None] | None" = None
    """Restores the *enclosing* call's state, not ``None``.

    **A plain ``_CALL.set(None)`` on the way out was overwrite semantics
    where :data:`~omicsclaw.observability.scope._CURRENT` next door is
    stack semantics**, and the asymmetry was a latent defect rather than a
    style difference. Every tool call gets its own
    :class:`asyncio.Task` today (``tools/registry.py``), so nothing can
    currently nest inside one — but :meth:`TracingHook.before_execute`'s
    own docstring describes a tool that runs an agent of its own, and the
    day such a tool calls a second tool *in the same task*, the inner
    call's exit would blank the outer one's state: the outer span would
    never be ended, its parent binding never released, and every later
    span in that task would hang off a closed tool span. A token costs one
    field and makes the nesting correct instead of merely unreachable.
    """

    started: float = 0.0


_CALL: ContextVar[_Call | None] = ContextVar(
    "omicsclaw_observability_tool_call", default=None
)
"""The span of the tool call running in *this* task.

**Why not an attribute on the hook.** One :class:`TracingHook` is mounted
on every tool and a turn runs its calls concurrently, so a field would be
overwritten by whichever sibling started last and every span would close
against the wrong call. ``hooks/audit.py`` names this exact hazard as the
reason it records no duration; a
:class:`~contextvars.ContextVar` is the answer it did not need and this
hook does, and it works because the executor gives each tool call its own
:class:`asyncio.Task` and a Task copies the context it was created in.
"""


class TracingHook(Hook):
    """Span and measure one tool execution. Never decides anything.

    :meth:`before_execute` always allows — it exists to start a clock, not
    to have an opinion — which is the constraint ``observability/hook.go``
    states about itself and the reason this hook is safe to mount in any
    deployment regardless of its permission posture.

    **Mount it last.** The chain closes in reverse, so the last hook
    mounted is the innermost: its span then measures the tool and nothing
    else, and it cannot be left unclosed by a neighbour's refusal because
    there is no neighbour after it. That is the opposite of
    :class:`~omicsclaw.hooks.AuditHook`'s position and the two reasons do
    not conflict — audit wants to *hear about* refusals, tracing wants to
    *not measure* them. The reference mounts its observability hook last
    for a third reason again (upstream context changes must be visible),
    and arrives at the same place.
    """

    __slots__ = ("_capture", "_meter", "_tracer")

    def __init__(
        self,
        tracer: Tracer,
        meter: Meter,
        *,
        capture_content: bool = False,
    ) -> None:
        self._tracer = tracer
        self._meter = meter
        self._capture = capture_content

    async def before_execute(self, call: HookCall) -> HookDecision:
        """Open the span, start the clock, allow.

        The span is also pushed as the current parent, so a tool that runs
        an agent of its own — a sub-agent, a skill that drives the loop —
        nests underneath the call that started it instead of beginning a
        second, unrelated trace.

        A failure here is swallowed and the call proceeds untraced.
        :class:`~omicsclaw.hooks.HookedTool` would contain a raise anyway
        and read it as ``ALLOW``; catching it here as well is what keeps
        the *pairing* honest, since a half-initialised
        :class:`_Call` is worse than none.
        """
        try:
            # Every attribute goes in at construction. A span created and
            # *then* decorated can be orphaned: if the second call raises,
            # the handler below records no state and nothing is left to
            # call `end()` on, so that tool disappears from the trace with
            # no log line explaining it.
            attributes: dict[str, AttributeValue] = {ATTR_TOOL_NAME: call.name}
            if self._capture and call.arguments:
                attributes[ATTR_LANGFUSE_OBSERVATION_INPUT] = truncate_attr(
                    call.arguments
                )
            span = self._tracer.start_span(
                SPAN_TOOL, parent=current_parent(), attributes=attributes
            )
            state = _Call(
                span=span,
                token=push_parent(fixed(span)),
                started=time.perf_counter(),
            )
            # The token comes back from the set that installs this call, so
            # resetting it restores whatever was bound before — the
            # enclosing call, or nothing. Assigned after construction
            # because the token cannot exist until the object it points
            # past does.
            state.call_token = _CALL.set(state)
        except Exception:
            # `_CALL` is deliberately left alone. Nothing was installed on
            # this path, and blanking it would destroy an *enclosing*
            # call's state to clean up after a call that never started.
            _log.exception("telemetry could not open a span for %s", call.name)
        return HookDecision()

    async def after_execute(self, call: HookCall, output: str) -> str:
        """Close a successful call and return *output* untouched.

        This hook never rewrites. The argument is returned as it arrived,
        and ``tests/observability/test_hook.py`` pins it, because an
        observer that changes what the model reads has stopped being one.
        """
        self._close(call, AuditOutcome.OK, output=output)
        return output

    async def on_failure(self, call: HookCall, error: BaseException) -> None:
        """Close a call that failed, was refused, or was cancelled.

        The outcome is classified by :func:`~omicsclaw.hooks.outcome_of`,
        the same function :class:`~omicsclaw.hooks.AuditHook` uses, so a
        span's ``tool.status`` and an audit line's ``outcome`` can never
        disagree about the same call.
        """
        self._close(call, outcome_of(error), error=error)

    # ---- internals -------------------------------------------------------

    def _close(
        self,
        call: HookCall,
        outcome: AuditOutcome,
        *,
        output: str = "",
        error: BaseException | None = None,
    ) -> None:
        """End the span, release the parent binding, record two instruments.

        The measurements are recorded for **every** outcome, refusals and
        cancellations included, because
        :data:`~omicsclaw.observability.attributes.ATTR_TOOL_STATUS` is a
        dimension of both instruments — a counter that only counted
        successes could not answer the question it exists for.
        """
        state = _CALL.get()
        if state is None:
            return
        try:
            _restore(state.call_token)
            pop_parent(state.token)
            elapsed = time.perf_counter() - state.started
            attributes: dict[str, AttributeValue] = {
                ATTR_TOOL_NAME: call.name,
                ATTR_TOOL_STATUS: outcome.value,
                ATTR_TOOL_SUCCESS: outcome is AuditOutcome.OK,
            }
            if self._capture and output:
                attributes[ATTR_LANGFUSE_OBSERVATION_OUTPUT] = truncate_attr(output)
            state.span.set_attributes(attributes)
            if error is not None:
                # The class name only — never ``str(error)``. A tool's
                # exception quotes the argument it could not use: a
                # ``read_file`` failure names the path, ``bash`` quotes the
                # command line. ``hooks/audit.py`` learned this from a test
                # that caught a requested path in an audit file, and a span
                # leaves the machine where an audit file does not.
                state.span.record_error(error)
            state.span.end()
            dimensions = {ATTR_TOOL_NAME: call.name, ATTR_TOOL_STATUS: outcome.value}
            self._meter.record(METRIC_TOOL_DURATION, elapsed, dimensions)
            self._meter.count(METRIC_TOOL_CALLS, 1, dimensions)
        except Exception:
            _log.exception("telemetry could not close the span for %s", call.name)


def _restore(token: "Token[_Call | None] | None") -> None:
    """Put back the call this one displaced. Safe from a foreign context.

    The same guard :func:`~omicsclaw.observability.scope.pop_parent` has,
    for the same reason: a :exc:`ValueError` here means the token was
    minted in a different :class:`~contextvars.Context`, whose binding is
    going away with it, so there is nothing to repair.
    """
    if token is None:
        return
    try:
        _CALL.reset(token)
    except ValueError:  # pragma: no cover - needs a cross-task close
        _log.debug("a telemetry tool call was closed from a foreign context")
