"""The OpenTelemetry adapter, exercised against the real SDK when present.

Skipped wholesale when the SDK is not installed, which is the state the
rest of this suite runs in — the point being that everything else in the
package is testable without it.
"""

from __future__ import annotations

import pytest

from omicsclaw.observability.config import ExporterType, ObservabilityConfig
from omicsclaw.observability.contract import NOOP_SPAN, Meter, Span, Tracer
from omicsclaw.observability.otel import build_otel_backend

sdk = pytest.importorskip("opentelemetry.sdk.trace")

from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import (  # noqa: E402
    InMemoryMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from omicsclaw.observability.otel import _OtelMeter, _OtelTracer  # noqa: E402


@pytest.fixture()
def recorded():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield _OtelTracer(provider.get_tracer("test")), exporter
    provider.shutdown()


def test_the_adapter_satisfies_this_packages_contract(recorded):
    tracer, _ = recorded

    assert isinstance(tracer, Tracer)
    assert isinstance(tracer.start_span("x"), Span)


def test_a_span_carries_its_name_and_attributes(recorded):
    tracer, exporter = recorded

    span = tracer.start_span("omicsclaw.turn", attributes={"agent.turn": 3})
    span.set_attributes({"turn.has_tool_calls": True})
    span.end()

    (finished,) = exporter.get_finished_spans()
    assert finished.name == "omicsclaw.turn"
    assert finished.attributes["agent.turn"] == 3
    assert finished.attributes["turn.has_tool_calls"] is True


def test_explicit_parenting_produces_a_real_parent_child_pair(recorded):
    """No OTEL context is attached anywhere; the argument is the whole tree."""
    tracer, exporter = recorded

    parent = tracer.start_span("omicsclaw.interaction")
    child = tracer.start_span("omicsclaw.turn", parent=parent)
    child.end()
    parent.end()

    finished = {s.name: s for s in exporter.get_finished_spans()}
    turn = finished["omicsclaw.turn"]
    interaction = finished["omicsclaw.interaction"]
    assert turn.parent.span_id == interaction.context.span_id
    assert turn.context.trace_id == interaction.context.trace_id


def test_a_span_with_no_parent_is_its_own_trace(recorded):
    tracer, exporter = recorded

    first = tracer.start_span("a")
    second = tracer.start_span("b")
    first.end()
    second.end()

    traces = {s.context.trace_id for s in exporter.get_finished_spans()}
    assert len(traces) == 2


def test_a_foreign_parent_does_not_raise(recorded):
    tracer, exporter = recorded

    span = tracer.start_span("a", parent=NOOP_SPAN)
    span.end()

    assert exporter.get_finished_spans()[0].parent is None


def test_an_error_records_the_class_name_and_not_the_message(recorded):
    """A span leaves the machine; a tool's message quotes its argument."""
    tracer, exporter = recorded

    span = tracer.start_span("omicsclaw.tool")
    span.record_error(FileNotFoundError("/data/GSE12345/patient_07.h5ad"))
    span.end()

    (finished,) = exporter.get_finished_spans()
    assert finished.status.description == "FileNotFoundError"
    assert finished.events == (), "record_exception would attach the traceback"
    assert "patient_07" not in str(finished.status.description)


def test_ending_twice_is_harmless(recorded):
    tracer, exporter = recorded

    span = tracer.start_span("a")
    span.end()
    span.end()

    assert len(exporter.get_finished_spans()) == 1


def test_instruments_are_created_from_the_declared_table():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = _OtelMeter(provider.get_meter("test"))

    assert isinstance(meter, Meter)
    meter.count("omicsclaw.tool.calls.total", 2, {"tool.name": "bash"})
    meter.record("omicsclaw.tool.execution.duration", 0.25, {"tool.name": "bash"})

    data = reader.get_metrics_data()
    found = {
        metric.name: metric
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
    }
    assert found["omicsclaw.tool.calls.total"].unit == "{call}"
    assert found["omicsclaw.tool.execution.duration"].unit == "s"
    assert found["omicsclaw.tool.calls.total"].description
    provider.shutdown()


def test_an_instrument_is_created_once_and_cached():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = _OtelMeter(provider.get_meter("test"))

    meter.count("omicsclaw.agent.turns.total")
    first = meter._instruments["omicsclaw.agent.turns.total"]
    meter.count("omicsclaw.agent.turns.total")

    assert meter._instruments["omicsclaw.agent.turns.total"] is first
    provider.shutdown()


def test_an_undeclared_instrument_still_records():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = _OtelMeter(provider.get_meter("test"))

    meter.record("omicsclaw.typo", 1.0)

    assert "omicsclaw.typo" in meter._instruments
    provider.shutdown()


# ---- build_otel_backend -------------------------------------------------


def test_a_non_otlp_configuration_builds_nothing():
    config = ObservabilityConfig(enabled=True, exporter=ExporterType.STDOUT)

    assert build_otel_backend(config) is None


def test_otlp_without_an_endpoint_refuses_and_says_why(caplog):
    config = ObservabilityConfig(enabled=True, exporter=ExporterType.OTLP)

    with caplog.at_level("WARNING", logger="omicsclaw.observability.otel"):
        assert build_otel_backend(config) is None

    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in caplog.text


def test_a_real_pipeline_is_built_without_touching_the_network():
    """Constructing an exporter must not connect; only exporting does."""
    config = ObservabilityConfig(
        enabled=True,
        exporter=ExporterType.OTLP,
        otlp_endpoint="http://127.0.0.1:4318/",
        otlp_headers={"Authorization": "Basic x"},
    )

    backend = build_otel_backend(config)

    assert backend is not None
    assert isinstance(backend.tracer, Tracer)
    assert isinstance(backend.meter, Meter)
    span = backend.tracer.start_span("omicsclaw.interaction")
    span.end()
    backend.shutdown()


def test_the_endpoint_suffix_is_appended_exactly_once():
    """SDK versions have disagreed about appending it; guessing is a 404."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    seen: list[str] = []
    original = OTLPSpanExporter.__init__

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("endpoint", ""))
        return original(self, *args, **kwargs)

    OTLPSpanExporter.__init__ = spy
    try:
        backend = build_otel_backend(
            ObservabilityConfig(
                enabled=True,
                exporter=ExporterType.OTLP,
                otlp_endpoint="https://cloud.langfuse.test/api/public/otel/",
            )
        )
    finally:
        OTLPSpanExporter.__init__ = original

    assert seen == ["https://cloud.langfuse.test/api/public/otel/v1/traces"]
    assert backend is not None
    backend.shutdown()


# ---- runtime export failures stay visible -------------------------------


def test_the_opentelemetry_logger_is_given_somewhere_to_go():
    """``setup.go:57-63``'s job, in the shape Python actually offers.

    Go registers ``otel.SetErrorHandler``; Python has no such hook and
    reports a failed batch through :mod:`logging`. The symptom this
    prevents is the one nobody files: traces stop appearing days later
    with a clean local log.
    """
    import logging

    import omicsclaw.observability.otel as adapter

    logger = logging.getLogger("opentelemetry")
    root = logging.getLogger()
    saved = (list(logger.handlers), logger.level, list(root.handlers))
    logger.handlers.clear()
    root.handlers.clear()
    adapter._export_failures_surfaced = False
    try:
        adapter._surface_export_failures()

        assert logger.handlers, "nothing would surface an export failure"
        assert logger.level <= logging.WARNING
        assert logger.propagate is True, "propagation is left alone"
    finally:
        logger.handlers[:] = saved[0]
        logger.setLevel(saved[1])
        root.handlers[:] = saved[2]
        adapter._export_failures_surfaced = False


def test_a_deployment_that_configured_logging_keeps_its_configuration():
    """A library that installs handlers over an application's is a rude one."""
    import logging

    import omicsclaw.observability.otel as adapter

    root = logging.getLogger()
    logger = logging.getLogger("opentelemetry")
    saved = (list(logger.handlers), list(root.handlers))
    logger.handlers.clear()
    root.handlers.clear()
    mine = logging.NullHandler()
    root.addHandler(mine)
    adapter._export_failures_surfaced = False
    try:
        adapter._surface_export_failures()

        assert logger.handlers == [], "the root already reaches somebody"
    finally:
        logger.handlers[:] = saved[0]
        root.handlers[:] = saved[1]
        adapter._export_failures_surfaced = False


def test_it_is_attached_once_per_process():
    import logging

    import omicsclaw.observability.otel as adapter

    logger = logging.getLogger("opentelemetry")
    root = logging.getLogger()
    saved = (list(logger.handlers), list(root.handlers))
    logger.handlers.clear()
    root.handlers.clear()
    adapter._export_failures_surfaced = False
    try:
        adapter._surface_export_failures()
        adapter._surface_export_failures()

        assert len(logger.handlers) == 1
    finally:
        logger.handlers[:] = saved[0]
        root.handlers[:] = saved[1]
        adapter._export_failures_surfaced = False
