"""The OpenTelemetry adapter — the only module here that knows OTEL exists.

The counterpart of ``observability/setup.go``, and the same relationship
to this package that ``openai_provider.py`` has to
:mod:`omicsclaw.provider`: one file where a vendor's names live, so that
importing the contract never requires the vendor to be installed.

**The import is inside the function**, which every other module in this
rebuild is forbidden from doing —
``tests/hooks/test_hooks_is_a_leaf_layer.py`` fails a package for it. The
exemption is argued rather than assumed: a runtime import is banned
because a module named as a string is a dependency the import rules
cannot see, and the fix is to make the dependency *visible*. Here it is
visible — the package is named in ``pyproject.toml`` under the ``otel``
extra, this module does nothing else, and
``tests/observability/test_otel.py`` skips itself when the import fails.
What a top-level import would buy is nothing, and what it would cost is
``import omicsclaw.entry`` failing on every machine that never wanted
telemetry.

**Failure is always a degradation, never a raise.** A missing SDK, an
unset endpoint, an exporter that cannot be constructed — each returns
``None`` and one log line, and
:func:`~omicsclaw.observability.telemetry.build_telemetry` falls back to
the no-op. **The reference does the same**, and saying so is a
correction: an earlier version of this docstring claimed ``main.go``
treats a failed ``Setup`` as fatal and counted the difference as this
layer being more forgiving. It is not a difference —
``cmd/harness9/main.go:127-131`` logs the error and substitutes
``observability.NewNoopProviders()``, and its three other
observability constructors degrade the same way. The claim was never
checked, which makes it the defect it would be anywhere else in this
tree.

**Export failures after construction are surfaced too**, which is the
one piece of ``setup.go`` this module was missing and its parity table
did not mention; see :func:`_surface_export_failures`.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .attributes import INSTRUMENTS, InstrumentKind
from .config import ExporterType, ObservabilityConfig
from .contract import NOOP_METER, AttributeValue, Meter, Span, Tracer

_log = logging.getLogger(__name__)

__all__ = ["OtelBackend", "build_otel_backend"]

_BATCH_DELAY_MS = 2000
"""How long a batch may wait before it is sent.

The SDK default is 5,000 ms. The reference shortens it to 2,000 with the
note that a short session otherwise waits on the timer for its first
export; the same applies here and more so, since an OmicsClaw exchange is
frequently one question and one answer.
"""

_METRIC_INTERVAL_MS = 30_000
"""Metric export period, matching the reference. Metrics are cumulative,
so a long period costs freshness rather than data."""

_FLUSH_TIMEOUT_MS = 5000
"""Ceiling on one :meth:`OtelBackend.force_flush`. The reference's
figure. A flush that cannot finish in five seconds is a backend that is
down, and the run is not waiting for it."""

_global_provider_set = False
"""Whether this process has already installed a global tracer provider.

OTEL logs a warning and ignores the second attempt, so a deployment that
rebuilds its app — a desktop server reloading configuration, a test
suite — would otherwise emit one warning per rebuild about a condition
nobody can act on.
"""


@dataclass(frozen=True, slots=True)
class OtelBackend:
    """A live OTEL pipeline, reduced to this package's four verbs."""

    tracer: Tracer
    meter: Meter
    shutdown: Callable[[], None]
    """Stop the providers and flush what is pending. Blocking; called
    from a worker thread by
    :meth:`~omicsclaw.observability.telemetry.Telemetry.aclose`."""

    force_flush: Callable[[], None]
    """Push every ended span now. Blocking, bounded by
    :data:`_FLUSH_TIMEOUT_MS`."""


def build_otel_backend(config: ObservabilityConfig) -> OtelBackend | None:
    """Construct the pipeline *config* asks for, or ``None``.

    ``None`` means "fall back to the no-op", and the caller has already
    decided that is acceptable. Every return path that is not the happy
    one logs first, because a deployment that switched telemetry on and
    got silence has no other way to find out why.
    """
    if config.exporter is not ExporterType.OTLP:
        return None
    if not config.otlp_endpoint:
        _log.warning(
            "OTEL_EXPORTER_TYPE=otlp but OTEL_EXPORTER_OTLP_ENDPOINT is unset; "
            "telemetry is disabled"
        )
        return None
    try:
        return _build(config)
    except ImportError:
        _log.warning(
            "OTEL_EXPORTER_TYPE=otlp but the OpenTelemetry SDK is not "
            "installed; telemetry is disabled. Install it with "
            "`pip install 'omicsclaw[otel]'`"
        )
        return None
    except Exception:
        _log.exception("the OTLP exporter could not be built; telemetry is disabled")
        return None


def _build(config: ObservabilityConfig) -> OtelBackend:
    """The vendor half. Everything imported here is imported only here."""
    global _global_provider_set

    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _surface_export_failures()

    resource = Resource.create({"service.name": config.service_name})
    base = config.otlp_endpoint.rstrip("/")
    headers = dict(config.otlp_headers)

    # The suffix is appended here rather than left to the SDK. The
    # reference records that SDK versions have disagreed about whether
    # they add it, and the symptom of guessing wrong is a 404 on a host
    # nobody in this process can see.
    span_exporter = OTLPSpanExporter(endpoint=f"{base}/v1/traces", headers=headers)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(span_exporter, schedule_delay_millis=_BATCH_DELAY_MS)
    )

    # The tracer comes from *this* provider, never from the global
    # accessor. The reference found that the global wrapper could hand
    # back a tracer whose spans bypassed the batch processor and were
    # silently dropped; the global is still installed, below, so that a
    # third-party instrumentation exports through the same pipeline.
    tracer = provider.get_tracer(config.service_name)

    if not _global_provider_set:
        otel_trace.set_tracer_provider(provider)
        _global_provider_set = True

    meter_provider = _build_meter_provider(config, resource, base, headers)
    meter = (
        _OtelMeter(meter_provider.get_meter(config.service_name))
        if meter_provider is not None
        else None
    )

    def shutdown() -> None:
        # Both providers are shut down even if the first raises: the
        # second owns a background thread and an HTTP session, and
        # skipping it on the way out leaks both.
        try:
            provider.shutdown()
        finally:
            if meter_provider is not None:
                meter_provider.shutdown()

    def force_flush() -> None:
        provider.force_flush(timeout_millis=_FLUSH_TIMEOUT_MS)

    _log.info(
        "OTLP telemetry active: traces -> %s/v1/traces (headers: %d), metrics: %s",
        base,
        len(headers),
        "on" if meter_provider is not None else "off",
    )
    return OtelBackend(
        tracer=_OtelTracer(tracer),
        meter=meter if meter is not None else NOOP_METER,
        shutdown=shutdown,
        force_flush=force_flush,
    )


_export_failures_surfaced = False
"""Whether this process has already attached the stderr handler."""


def _surface_export_failures() -> None:
    """Make a *runtime* export failure visible, as ``setup.go:57-63`` does.

    **The gap this closes.** Everything else in this module guards
    *construction*: a missing SDK, a bad endpoint, an exporter that will
    not build. None of that helps once the pipeline is up and the failures
    move to a background thread — an expired Langfuse key, a proxy that
    starts refusing, a collector that goes away. The reference registers
    ``otel.SetErrorHandler`` for exactly this, and writes to
    :data:`sys.stderr` explicitly so that a TUI which has pointed the log
    package at ``io.Discard`` cannot hide it.

    **Python has no equivalent hook**, and that is the reason this is a
    handler rather than a callback: the OpenTelemetry Python SDK reports a
    failed batch through :mod:`logging`, on the ``opentelemetry`` logger
    hierarchy. So the translation of "register an error handler" is
    "ensure that hierarchy reaches somebody". A handler is attached
    **only when the logger would otherwise propagate into a root that has
    none**, so a deployment that configured logging keeps its own
    configuration, and ``propagate`` is left alone so nothing is
    swallowed.

    The symptom it prevents is the one nobody reports as a bug: traces
    simply stop appearing in the dashboard, days later, with a clean local
    log.
    """
    global _export_failures_surfaced
    if _export_failures_surfaced:
        return
    _export_failures_surfaced = True
    logger = logging.getLogger("opentelemetry")
    if logger.handlers or logging.getLogger().handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[OTEL] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)


def _build_meter_provider(
    config: ObservabilityConfig,
    resource: Any,
    base: str,
    headers: Mapping[str, str],
) -> Any | None:
    """Metrics, and ``None`` when they cannot be had.

    **Fail-open, independently of traces**, which is the reference's
    decision and its reason: Langfuse — the backend this configuration
    block is most often pointed at — ingests traces and answers 404 on
    ``/v1/metrics``. Letting that take the traces down with it would mean
    the common deployment gets nothing.
    """
    try:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{base}/v1/metrics", headers=dict(headers)),
            export_interval_millis=_METRIC_INTERVAL_MS,
        )
        return MeterProvider(resource=resource, metric_readers=[reader])
    except Exception:
        _log.warning(
            "the OTLP metric exporter could not be built; traces are unaffected",
            exc_info=True,
        )
        return None


class _OtelSpan:
    """One OTEL span behind this package's three verbs."""

    __slots__ = ("_ended", "_span")

    def __init__(self, span: Any) -> None:
        self._span = span
        self._ended = False

    @property
    def raw(self) -> Any:
        """The OTEL span, for :class:`_OtelTracer` to parent against."""
        return self._span

    def set_attributes(self, attributes: Mapping[str, AttributeValue]) -> None:
        self._span.set_attributes(dict(attributes))

    def record_error(self, error: BaseException) -> None:
        """Mark the span failed, recording the type and **not** the message.

        ``record_exception`` would attach the formatted traceback, which
        carries the message and, for this repository's tools, the file
        path or command inside it. The status description is the class
        name for the same reason
        :meth:`~omicsclaw.observability.console.ConsoleSpan.record_error`
        gives.
        """
        from opentelemetry.trace import Status, StatusCode

        self._span.set_status(Status(StatusCode.ERROR, type(error).__name__))

    def end(self) -> None:
        if self._ended:
            return
        self._ended = True
        self._span.end()


class _OtelTracer:
    """Explicit parenting on top of OTEL's context-based API.

    ``start_span`` is used rather than ``start_as_current_span``: this
    package passes the parent as an argument and never attaches anything
    to OTEL's context, so a span's position in the tree is decided by one
    expression instead of by whichever frame happens to be current. See
    :class:`~omicsclaw.observability.contract.Tracer`.
    """

    __slots__ = ("_tracer",)

    def __init__(self, tracer: Any) -> None:
        self._tracer = tracer

    def start_span(
        self,
        name: str,
        *,
        parent: Span | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> Span:
        from opentelemetry import trace as otel_trace

        context = (
            otel_trace.set_span_in_context(parent.raw)
            if isinstance(parent, _OtelSpan)
            else None
        )
        return _OtelSpan(
            self._tracer.start_span(
                name, context=context, attributes=dict(attributes or {})
            )
        )


class _OtelMeter:
    """Instruments resolved by name, created once, cached.

    An instrument this package does not declare in
    :data:`~omicsclaw.observability.attributes.INSTRUMENTS` is created
    anyway, with no unit and no description, so a caller's typo produces a
    visible unlabelled series rather than a silently dropped measurement.
    """

    __slots__ = ("_instruments", "_meter")

    def __init__(self, meter: Any) -> None:
        self._meter = meter
        self._instruments: dict[str, Any] = {}

    def count(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self._instrument(name, InstrumentKind.COUNTER).add(
            value, attributes=dict(attributes or {})
        )

    def record(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self._instrument(name, InstrumentKind.HISTOGRAM).record(
            value, attributes=dict(attributes or {})
        )

    def _instrument(self, name: str, fallback_kind: str) -> Any:
        existing = self._instruments.get(name)
        if existing is not None:
            return existing
        kind, unit, description = INSTRUMENTS.get(name, (fallback_kind, "", ""))
        if kind == InstrumentKind.COUNTER:
            made = self._meter.create_counter(name, unit=unit, description=description)
        else:
            made = self._meter.create_histogram(
                name, unit=unit, description=description
            )
        self._instruments[name] = made
        return made
