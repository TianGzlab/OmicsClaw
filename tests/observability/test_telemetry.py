"""The facade: an inactive deployment must not be a different deployment."""

from __future__ import annotations

import io

from omicsclaw.hooks import ToolHook
from omicsclaw.observability import (
    ConsoleMeter,
    ConsoleTracer,
    ExporterType,
    ObservabilityConfig,
    Telemetry,
    TracedProvider,
    TracingHook,
    build_telemetry,
)
from omicsclaw.observability.contract import NOOP_METER, NOOP_TRACER

from ._support import RecordingMeter, RecordingTracer, Scripted, assistant, run


def _stdout() -> ObservabilityConfig:
    return ObservabilityConfig(enabled=True, exporter=ExporterType.STDOUT)


# ---- the inactive deployment -------------------------------------------


def test_the_default_telemetry_records_nothing():
    telemetry = Telemetry()

    assert telemetry.active is False
    assert telemetry.tracer is NOOP_TRACER
    assert telemetry.meter is NOOP_METER


def test_an_inactive_telemetry_hands_the_provider_straight_back():
    """Identity: the object graph must be what it was before this layer."""
    provider = Scripted(assistant())

    assert Telemetry().trace_provider(provider) is provider


def test_an_inactive_telemetry_mounts_no_hook():
    assert Telemetry().tool_hooks() == ()


def test_an_inactive_telemetry_still_gives_a_usable_scope():
    """So ``entry/turn.py`` is written once and branches nowhere."""

    async def exercise():
        async with Telemetry().run(session_id="s") as scope:
            assert scope is not None

    run(exercise())


def test_closing_and_flushing_an_inactive_telemetry_does_nothing():
    run(Telemetry().force_flush())
    run(Telemetry().aclose())


def test_nothing_configured_builds_an_inactive_telemetry():
    assert build_telemetry(ObservabilityConfig()).active is False


def test_enabled_without_an_exporter_is_still_inactive():
    config = ObservabilityConfig(enabled=True, exporter=ExporterType.NOOP)

    assert build_telemetry(config).active is False


# ---- the active deployment ----------------------------------------------


def test_the_stdout_exporter_needs_nothing_installed():
    telemetry = build_telemetry(_stdout())

    assert telemetry.active is True
    assert isinstance(telemetry.tracer, ConsoleTracer)
    assert isinstance(telemetry.meter, ConsoleMeter)


def test_an_active_telemetry_wraps_the_provider():
    telemetry = build_telemetry(_stdout())
    provider = Scripted(assistant())

    wrapped = telemetry.trace_provider(provider, model="m")

    assert isinstance(wrapped, TracedProvider)
    assert wrapped.inner is provider
    assert wrapped.name == provider.name


def test_an_active_telemetry_mounts_exactly_one_hook():
    hooks = build_telemetry(_stdout()).tool_hooks()

    assert len(hooks) == 1
    assert isinstance(hooks[0], TracingHook)
    assert isinstance(hooks[0], ToolHook)


def test_the_stdout_backend_reports_its_metrics_at_shutdown():
    stream = io.StringIO()
    meter = ConsoleMeter(stream)
    telemetry = Telemetry(
        tracer=ConsoleTracer(io.StringIO()),
        meter=meter,
        config=_stdout(),
        on_shutdown=meter.dump,
    )
    telemetry.meter.count("omicsclaw.agent.turns.total", 2)

    run(telemetry.aclose())

    assert '"omicsclaw.agent.turns.total"' in stream.getvalue()


def test_an_otlp_configuration_without_an_endpoint_degrades():
    """And the config still says ``otlp`` — asked-for and achieved differ."""
    config = ObservabilityConfig(enabled=True, exporter=ExporterType.OTLP)

    telemetry = build_telemetry(config)

    assert telemetry.active is False
    assert telemetry.config.exporter is ExporterType.OTLP


def test_capture_content_reaches_both_seams():
    config = ObservabilityConfig(
        enabled=True, exporter=ExporterType.STDOUT, capture_content=True
    )
    telemetry = build_telemetry(config)

    assert telemetry.trace_provider(Scripted(assistant()))._capture is True
    assert telemetry.tool_hooks()[0]._capture is True


def test_build_telemetry_reads_the_environment_when_given_nothing(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_TYPE", "stdout")

    assert build_telemetry().active is True


# ---- flushing -----------------------------------------------------------


def test_a_clean_exchange_and_a_failed_one_both_flush():
    """The reference flushes unconditionally; a cancelled run is the one
    case where awaiting is unsafe. See ``RunScope.__aexit__``."""
    import asyncio

    flushes: list[int] = []
    telemetry = Telemetry(
        tracer=RecordingTracer(),
        meter=RecordingMeter(),
        config=_stdout(),
        on_flush=lambda: flushes.append(1),
    )

    async def clean():
        async with telemetry.run(session_id="s"):
            pass

    async def broken():
        try:
            async with telemetry.run(session_id="s"):
                raise RuntimeError("x")
        except RuntimeError:
            pass

    async def cancelled():
        try:
            async with telemetry.run(session_id="s"):
                raise asyncio.CancelledError()
        except asyncio.CancelledError:
            pass

    run(clean())
    assert flushes == [1]

    run(broken())
    assert flushes == [1, 1], "a failed exchange is the trace somebody wants"

    run(cancelled())
    assert flushes == [1, 1], "a cancelled task cannot safely await"


def test_a_flush_that_raises_is_contained():
    def boom() -> None:
        raise RuntimeError("backend down")

    telemetry = Telemetry(
        tracer=RecordingTracer(), meter=RecordingMeter(), on_flush=boom
    )

    run(telemetry.force_flush())


def test_a_shutdown_that_raises_is_contained():
    def boom() -> None:
        raise RuntimeError("backend down")

    telemetry = Telemetry(
        tracer=RecordingTracer(), meter=RecordingMeter(), on_shutdown=boom
    )

    run(telemetry.aclose())


def test_the_record_is_frozen():
    import pytest

    telemetry = Telemetry()

    with pytest.raises(Exception):
        telemetry.tracer = NOOP_TRACER  # type: ignore[misc]
