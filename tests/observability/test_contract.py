"""The Protocols are structural, and the no-op really is free."""

from __future__ import annotations

from omicsclaw.observability.contract import (
    NOOP_METER,
    NOOP_SPAN,
    NOOP_TRACER,
    Meter,
    Span,
    Tracer,
)

from ._support import RecordingMeter, RecordingTracer


def test_a_double_that_imports_nothing_satisfies_the_protocols():
    """The property that lets ``_support.py`` import no production code."""
    tracer = RecordingTracer()

    assert isinstance(tracer, Tracer)
    assert isinstance(RecordingMeter(), Meter)
    assert isinstance(tracer.start_span("x"), Span)


def test_the_shipped_noops_satisfy_them_too():
    assert isinstance(NOOP_TRACER, Tracer)
    assert isinstance(NOOP_METER, Meter)
    assert isinstance(NOOP_SPAN, Span)


def test_the_disabled_path_allocates_no_span():
    """Identity, so "zero overhead" is a checked claim and not a comment."""
    first = NOOP_TRACER.start_span("a", attributes={"k": "v"})
    second = NOOP_TRACER.start_span("b", parent=first)

    assert first is NOOP_SPAN
    assert second is NOOP_SPAN


def test_a_noop_span_tolerates_everything_including_a_second_end():
    """Cancellation closes an open span from two places."""
    NOOP_SPAN.set_attributes({"a": 1})
    NOOP_SPAN.record_error(RuntimeError("boom"))
    NOOP_SPAN.end()
    NOOP_SPAN.end()


def test_the_noop_types_carry_no_per_instance_state():
    """``__slots__ = ()`` is what makes one shared instance safe."""
    for kind in (type(NOOP_SPAN), type(NOOP_TRACER), type(NOOP_METER)):
        assert kind.__slots__ == ()
        assert not hasattr(kind(), "__dict__")


def test_an_object_missing_a_method_is_not_a_tracer():
    class Half:
        def start_span(self, name):  # wrong signature is still structural
            return NOOP_SPAN

    class Nothing:
        pass

    assert isinstance(Half(), Tracer)
    assert not isinstance(Nothing(), Tracer)
