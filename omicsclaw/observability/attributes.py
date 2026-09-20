"""Every name this layer writes: spans, attribute keys, instruments.

One module of constants, for the reason the reference harness gives its
own (``observability/attributes.go``): these strings are a **wire
contract** with whatever reads them — a Langfuse project, a Grafana
dashboard, a Jaeger query — so renaming one silently breaks a dashboard
nobody in this repository can see. Collecting them here means a rename is
a diff in one file rather than a grep, and means the parity table in
``docs/plans/0043-observability-layer.md`` can be checked against code
instead of against memory.

Four groups, and the split matters:

1. **Span names** — the shape of the trace tree.
2. **This layer's own attribute and metric names** — internal analysis
   dimensions, prefixed ``omicsclaw.`` where they are instruments and
   left unprefixed where they are attributes, exactly as the reference
   does. They are ours and no external specification constrains them.
3. **GenAI semantic-convention keys** — OpenTelemetry's, not ours. A
   backend recognises an LLM call by these, and getting one wrong costs
   token accounting and cost estimation rather than a missing label.
4. **Langfuse ingestion keys** — one vendor's, and the reason they are
   segregated into their own block: they are the group most likely to
   change under us, and a reader deciding whether an upgrade affects this
   repository should be able to answer it by reading one screen.

**Stdlib only, and no code.** Importing this module must stay free enough
that :mod:`omicsclaw.observability.config` can read it before deciding
whether observability is switched on at all.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

__all__ = [
    "ATTR_AGENT_TYPE",
    "ATTR_ERROR_MESSAGE",
    "ATTR_ERROR_STATUS",
    "ATTR_ERROR_TYPE",
    "ATTR_GENAI_INPUT_TOKENS",
    "ATTR_GENAI_OUTPUT_TOKENS",
    "ATTR_GENAI_REQUEST_MODEL",
    "ATTR_GENAI_SYSTEM",
    "ATTR_INPUT_TOKENS",
    "ATTR_LANGFUSE_OBSERVATION_INPUT",
    "ATTR_LANGFUSE_OBSERVATION_OUTPUT",
    "ATTR_LANGFUSE_TRACE_INPUT",
    "ATTR_LANGFUSE_TRACE_OUTPUT",
    "ATTR_OUTPUT_TOKENS",
    "ATTR_CACHE_READ_TOKENS",
    "ATTR_MODEL",
    "ATTR_SESSION_ID",
    "ATTR_STOP_REASON",
    "ATTR_TOOL_NAME",
    "ATTR_TOOL_STATUS",
    "ATTR_TOOL_SUCCESS",
    "ATTR_TURNS",
    "ATTR_TURN_HAS_TOOL_CALLS",
    "ATTR_TURN_NUMBER",
    "DEFAULT_SERVICE_NAME",
    "INSTRUMENTS",
    "InstrumentKind",
    "METRIC_LLM_DURATION",
    "METRIC_TOKENS_INPUT",
    "METRIC_TOKENS_OUTPUT",
    "METRIC_TOOL_CALLS",
    "METRIC_TOOL_DURATION",
    "METRIC_TURNS_TOTAL",
    "SPAN_INTERACTION",
    "SPAN_LLM_REQUEST",
    "SPAN_TOOL",
    "SPAN_TURN",
]

DEFAULT_SERVICE_NAME = "omicsclaw"
"""``service.name`` when nothing set one. The resource attribute every
backend groups by, so it is the one name a deployment is most likely to
want to override — ``OTEL_SERVICE_NAME`` does that."""


# ---- 1. span names -------------------------------------------------------

SPAN_INTERACTION = "omicsclaw.interaction"
"""One exchange, start to finish — the root of a trace.

Opened by :class:`~omicsclaw.observability.scope.RunScope` around a whole
``run_stream``, so it covers compaction, every model call, every tool and
the convergence check. A session with ten exchanges produces ten of
these, correlated by :data:`ATTR_SESSION_ID` rather than nested, because
a session is not a unit of work and a span that stayed open across one
would never be exported until the user went away.
"""

SPAN_TURN = "omicsclaw.turn"
"""One Thought→Action→Observation cycle, a child of the interaction.

**Created lazily**, which is this layer's one real departure from the
reference's span tree. See
:class:`~omicsclaw.observability.scope.TurnScope` for why: the engine
emits ``TURN_END`` and has no ``TURN_START``, so the only honest moment
to open turn *N+1* is the instant after turn *N* ended — at which point
nobody yet knows whether the run continues. Opening it eagerly would
export an empty phantom span at the end of every run.
"""

SPAN_LLM_REQUEST = "omicsclaw.llm_request"
"""One model call, a child of the turn it belongs to.

Created by :class:`~omicsclaw.observability.provider.TracedProvider`.
**A retried turn produces several of these under one turn span**, which
is the accounting the reference cannot express at all: its
``TracingProvider`` also spans per call, but Go's engine has no
application-level retry budget between the turn and the call.
"""

SPAN_TOOL = "omicsclaw.tool"
"""One tool execution, a child of the turn it was requested in.

Created by :class:`~omicsclaw.observability.hook.TracingHook`. Siblings
of one turn run concurrently and their spans overlap in wall-clock time;
that overlap is the point, since it is what a reader uses to tell a
parallel turn from a serialized one.
"""


# ---- 2. this layer's own names -------------------------------------------

ATTR_SESSION_ID = "session.id"
"""Which conversation this trace belongs to. Set on the interaction span.

The join key between a trace and everything else this deployment writes
about the same exchange — ``hooks/audit.py`` files its records under the
same value, read from the same ``ToolContext`` binding.
"""

ATTR_AGENT_TYPE = "agent.type"
"""``"main"`` or ``"sub"``. Set on the interaction span.

Carried even though nothing in this tree spawns sub-agents yet: the
alternative is a dashboard that silently mixes the two the day one does,
and a default of ``"main"`` costs one attribute.
"""

ATTR_TURN_NUMBER = "agent.turn"
"""1-based turn index. Set on the turn span and on its children."""

ATTR_TURNS = "agent.turns"
"""How many turns the whole run made. Set on the interaction span from
:attr:`~omicsclaw.engine.RunResult.turns`."""

ATTR_STOP_REASON = "agent.stop_reason"
"""``converged`` / ``max_turns`` / ``truncated``. Set on the interaction
span.

**The reference has no equivalent**, because its engine reports budget
exhaustion as an ordinary error and discards the trajectory, so a trace
there cannot distinguish "finished" from "ran out of room". This tree's
:class:`~omicsclaw.engine.StopReason` can, and a trace that cannot answer
it would be throwing away information the loop already computed.
"""

ATTR_TURN_HAS_TOOL_CALLS = "turn.has_tool_calls"
"""Whether the turn ended by requesting tools. Set on the turn span."""

ATTR_MODEL = "llm.model"
"""Model name, in this layer's own namespace. Written **beside**
:data:`ATTR_GENAI_REQUEST_MODEL`, not instead of it: the GenAI key is
what a backend reads, this one is what a query over our own attributes
groups by without depending on a semantic-convention version."""

ATTR_INPUT_TOKENS = "llm.tokens.input"
ATTR_OUTPUT_TOKENS = "llm.tokens.output"
ATTR_CACHE_READ_TOKENS = "llm.tokens.cache_read"
"""Prompt tokens served from the provider's cache.

No reference equivalent and no GenAI key at the version pinned here.
Recorded because :class:`~omicsclaw.schema.Usage` carries it and prompt
prefix caching (ADR 0024) is a thing this repository deliberately spends
effort on — a trace that cannot show the hit rate cannot show whether
that effort is working.
"""

ATTR_TOOL_NAME = "tool.name"
ATTR_TOOL_SUCCESS = "tool.success"
"""``True`` only for :attr:`~omicsclaw.hooks.AuditOutcome.OK`. A refusal
and a cancellation are both ``False`` here and are told apart by
:data:`ATTR_TOOL_STATUS`."""

ATTR_TOOL_STATUS = "tool.status"
"""``ok`` / ``error`` / ``denied`` / ``cancelled`` — the values of
:class:`~omicsclaw.hooks.AuditOutcome`, reused rather than redefined.

**Four, where the reference has two.** ``observability/hook.go`` derives
its status from ``result.IsError`` alone, so a call a permission rule
refused and a call whose tool crashed arrive in the same bucket, and a
cancelled turn inflates a failure rate that a person reading the
dashboard will try to fix. This deployment already answers the question
in one place, for the audit log; asking it a second way here would be the
second answer :mod:`omicsclaw.hooks` exists to avoid.
"""

ATTR_ERROR_TYPE = "error.type"
"""The failing exception's class name. OpenTelemetry's own key, not ours.

Set on **every** failed span, model call and tool alike, and never gated:
a class name is a fixed vocabulary that no argument and no prompt can
reach. It is what a dashboard groups failures by.
"""

ATTR_ERROR_STATUS = "error.status_code"
"""The HTTP status a vendor reported, where there was one.

``None`` for failures that never reached the wire, which is the
distinction :class:`~omicsclaw.provider.ProviderError` already draws.
Carried as its own attribute rather than being left inside the message,
so that "was this a 429?" is answerable without the message being
recorded at all.
"""

ATTR_ERROR_MESSAGE = "error.message"
"""The vendor's own error text. **Gated on**
:attr:`~omicsclaw.observability.config.ObservabilityConfig.capture_content`.

It was ungated once, on the argument that a provider error describes an
HTTP exchange rather than a payload — ``429 rate limited``,
``connection error``. That argument holds for most of them and not for
all: a content-policy refusal quotes the text it refused, and a
validation error quotes the field it could not parse. With capture off
this layer promises that **no** payload leaves the process, and a promise
with one exception that depends on which error a vendor happened to
return is not a promise.

What is kept ungated is everything that makes the failure diagnosable
without it: :data:`ATTR_ERROR_TYPE`, :data:`ATTR_ERROR_STATUS`, and
:data:`ATTR_MODEL`, which is already on the span. A 404 on a named model
is still a 404 on a named model.

**Never set for a tool failure at all** — see
:class:`~omicsclaw.observability.hook.TracingHook`, matching
``hooks/audit.py``'s rule that a tool's error text quotes the argument it
could not use.
"""


METRIC_LLM_DURATION = "omicsclaw.llm.request.duration"
METRIC_TOKENS_INPUT = "omicsclaw.llm.tokens.input"
METRIC_TOKENS_OUTPUT = "omicsclaw.llm.tokens.output"
METRIC_TOOL_CALLS = "omicsclaw.tool.calls.total"
METRIC_TOOL_DURATION = "omicsclaw.tool.execution.duration"
METRIC_TURNS_TOTAL = "omicsclaw.agent.turns.total"


class InstrumentKind:
    """The two shapes of instrument this layer uses.

    Spelled as constants rather than as an enum because the only consumer
    is :data:`INSTRUMENTS`, a backend reads it once at construction, and
    an enum would have to be imported by every backend adapter to be
    compared against.
    """

    COUNTER = "counter"
    HISTOGRAM = "histogram"


INSTRUMENTS: Mapping[str, tuple[str, str, str]] = MappingProxyType(
    {
        METRIC_LLM_DURATION: (
            InstrumentKind.HISTOGRAM,
            "s",
            "Wall-clock seconds one model call took",
        ),
        METRIC_TOKENS_INPUT: (
            InstrumentKind.COUNTER,
            "{token}",
            "Prompt tokens consumed",
        ),
        METRIC_TOKENS_OUTPUT: (
            InstrumentKind.COUNTER,
            "{token}",
            "Completion tokens generated",
        ),
        METRIC_TOOL_CALLS: (
            InstrumentKind.COUNTER,
            "{call}",
            "Tool calls, by tool name and outcome",
        ),
        METRIC_TOOL_DURATION: (
            InstrumentKind.HISTOGRAM,
            "s",
            "Wall-clock seconds one tool execution took",
        ),
        METRIC_TURNS_TOTAL: (
            InstrumentKind.COUNTER,
            "{turn}",
            "ReAct turns executed",
        ),
    }
)
"""Every instrument, with its kind, unit and description.

A **table rather than six constructor calls** spread across three
modules, which is where the reference keeps them
(``observer.go``, ``hook.go``, ``provider.go`` each build their own). The
difference is checkable: a backend can assert it knows every instrument
before a run starts, and
``tests/observability/test_attributes.py`` asserts that every
``METRIC_`` constant appears here — so an instrument added without a unit
fails a test instead of reaching a dashboard with a blank axis.

Units follow the OpenTelemetry convention: UCUM for real units (``s``),
and ``{curly}`` annotations for dimensionless counts.
"""


# ---- 3. GenAI semantic conventions (OpenTelemetry's, not ours) -----------

ATTR_GENAI_SYSTEM = "gen_ai.system"
ATTR_GENAI_REQUEST_MODEL = "gen_ai.request.model"
ATTR_GENAI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_GENAI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"


# ---- 4. Langfuse ingestion keys (one vendor's) ---------------------------

ATTR_LANGFUSE_TRACE_INPUT = "langfuse.trace.input"
ATTR_LANGFUSE_TRACE_OUTPUT = "langfuse.trace.output"
ATTR_LANGFUSE_OBSERVATION_INPUT = "langfuse.observation.input"
ATTR_LANGFUSE_OBSERVATION_OUTPUT = "langfuse.observation.output"
"""The v4 keys. The older ``langfuse.input`` / ``langfuse.output`` land in
attribute metadata instead of the Input/Output panes, which is the
mistake the reference's own comment records having made.

**Nothing is written to any of these four unless content capture is
switched on**; see
:attr:`~omicsclaw.observability.config.ObservabilityConfig.capture_content`.
They are the only keys in this module that carry a payload rather than a
measurement, which is exactly why they are the ones gated.
"""
