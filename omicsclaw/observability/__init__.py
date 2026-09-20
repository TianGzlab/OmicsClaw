"""Seeing what the loop did: spans, measurements, and no engine changes.

Step 6.11 of the staged rebuild, plan 0043. The layer that answers *is it
working, what does it cost, what is slow* about a running agent, modelled
on ``internal/observability`` in the Go reference harness at
``/workspace/dataset/private/zhouwg_data/harness9``.

Usage — three lines at the composition root, two at the exchange::

    telemetry = build_telemetry()                       # reads OTEL_* env
    provider  = telemetry.trace_provider(provider, model=config.model)
    hooks     = (*build_hooks(config), *telemetry.tool_hooks())

    async with telemetry.run(session_id=sid, prompt=text) as scope:
        async for event in engine.run_stream(messages, ...):
            scope.observe(event)

The trace tree that produces::

    omicsclaw.interaction               session.id, agent.turns, agent.stop_reason
    ├── omicsclaw.turn        agent.turn=1
    │   ├── omicsclaw.llm_request       gen_ai.*, llm.tokens.*
    │   ├── omicsclaw.tool              tool.name, tool.status
    │   └── omicsclaw.tool              (siblings overlap: a parallel turn)
    └── omicsclaw.turn        agent.turn=2
        └── omicsclaw.llm_request

Six instruments, all declared in
:data:`~omicsclaw.observability.attributes.INSTRUMENTS`: LLM duration,
input and output tokens, tool calls, tool duration, turns.

Four decisions worth not re-deriving.

**No seam was cut into the engine.** The reference adds an
``EngineObserver`` interface to ``internal/engine`` and calls it at four
points, because a Go loop can only be watched by being called back. This
rebuild's loop already publishes those moments as
:class:`~omicsclaw.engine.EngineEvent`, so
:class:`~omicsclaw.observability.scope.RunScope` *consumes* an existing
stream instead. ``omicsclaw/engine/`` is unchanged by this step — the
layer whose own docstring says "no I/O, no logging" keeps that property,
and ``tests/observability/test_observability_boundaries.py`` asserts the
arrow never points back.

**This is an adapter layer, not a leaf.** It imports
:mod:`omicsclaw.schema`, :mod:`omicsclaw.provider`,
:mod:`omicsclaw.engine` and :mod:`omicsclaw.hooks`, and none of the four
imports it — the same one-way shape ``internal/observability`` has, and
the reason it can be deleted from a deployment without anything else
noticing. It does **not** import :mod:`omicsclaw.entry`: the composition
root joins them, in the three lines above.

**OpenTelemetry is optional, and the contract is ours.**
:mod:`omicsclaw.observability.contract` declares ``Span`` / ``Tracer`` /
``Meter`` in the standard library, :mod:`omicsclaw.observability.otel` is
the only module that knows the SDK exists, and
:mod:`omicsclaw.observability.console` is a working backend that needs
nothing installed. So ``import omicsclaw.entry`` keeps working on a
machine that never wanted telemetry — the same property
``provider/base.py`` claims for vendor SDKs — and the test suite can
exercise a real backend rather than only the no-op. What is given up is
named in :mod:`omicsclaw.observability.contract`: a third-party OTEL
instrumentation will not nest inside these spans.

**Payloads do not leave the machine unless somebody says so.** The
reference always serializes the conversation, the tool arguments and the
tool output into span attributes, which is reasonable for a coding
harness and is not reasonable here: ``CLAUDE.md`` states *"Genetic data
never leaves this machine"*, and an OmicsClaw prompt routinely names a
cohort, a sequencing run or a patient sample. So
:attr:`~omicsclaw.observability.config.ObservabilityConfig.capture_content`
is off by default and every ``langfuse.*`` attribute is gated on it.
Counts, durations, token usage, model, outcome and turn structure are
recorded either way — everything a dashboard needs, and nothing that
names a person or a gene.

Configuration is the reference's five environment variables plus that
one::

    OTEL_ENABLED=true
    OTEL_SERVICE_NAME=omicsclaw
    OTEL_EXPORTER_TYPE=noop|stdout|otlp
    OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
    OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20...
    OMICSCLAW_OTEL_CAPTURE_CONTENT=false
"""

from __future__ import annotations

from .attributes import DEFAULT_SERVICE_NAME, INSTRUMENTS
from .config import ExporterType, ObservabilityConfig
from .console import ConsoleMeter, ConsoleTracer
from .contract import NOOP_METER, NOOP_TRACER, Meter, NoopMeter, NoopTracer, Span, Tracer
from .hook import TracingHook
from .provider import TracedProvider
from .scope import RunScope, TurnScope, current_parent
from .serialize import MAX_ATTRIBUTE_BYTES, truncate_attr
from .telemetry import Telemetry, build_telemetry

__all__ = [
    "ConsoleMeter",
    "ConsoleTracer",
    "DEFAULT_SERVICE_NAME",
    "ExporterType",
    "INSTRUMENTS",
    "MAX_ATTRIBUTE_BYTES",
    "Meter",
    "NOOP_METER",
    "NOOP_TRACER",
    "NoopMeter",
    "NoopTracer",
    "ObservabilityConfig",
    "RunScope",
    "Span",
    "Telemetry",
    "TracedProvider",
    "Tracer",
    "TracingHook",
    "TurnScope",
    "build_telemetry",
    "current_parent",
    "truncate_attr",
]
