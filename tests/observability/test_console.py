"""The stdlib backend: a real exporter that needs nothing installed."""

from __future__ import annotations

import io
import json

from omicsclaw.observability import ConsoleMeter, ConsoleTracer
from omicsclaw.observability.console import ConsoleSpan
from omicsclaw.observability.contract import NOOP_SPAN, Meter, Span, Tracer


def _lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_it_satisfies_the_contract():
    assert isinstance(ConsoleTracer(io.StringIO()), Tracer)
    assert isinstance(ConsoleMeter(io.StringIO()), Meter)
    assert isinstance(ConsoleTracer(io.StringIO()).start_span("x"), Span)


def test_a_span_is_written_when_it_ends_and_not_before():
    out = io.StringIO()
    span = ConsoleTracer(out).start_span("a", attributes={"k": "v"})

    assert out.getvalue() == ""

    span.end()

    (record,) = _lines(out)
    assert record["name"] == "a"
    assert record["attributes"] == {"k": "v"}
    assert record["duration_s"] >= 0
    assert record["parent_span_id"] == ""


def test_ending_twice_writes_once():
    out = io.StringIO()
    span = ConsoleTracer(out).start_span("a")

    span.end()
    span.end()

    assert len(_lines(out)) == 1


def test_a_child_inherits_the_trace_and_names_its_parent():
    out = io.StringIO()
    tracer = ConsoleTracer(out)
    parent = tracer.start_span("parent")
    child = tracer.start_span("child", parent=parent)

    child.end()
    parent.end()

    records = _lines(out)
    assert records[0]["name"] == "child", "children end before their parents"
    assert records[0]["parent_span_id"] == records[1]["span_id"]
    assert records[0]["trace_id"] == records[1]["trace_id"]


def test_two_roots_are_two_traces():
    tracer = ConsoleTracer(io.StringIO())

    first = tracer.start_span("a")
    second = tracer.start_span("b")

    assert first.trace_id != second.trace_id


def test_a_foreign_parent_is_treated_as_no_parent_rather_than_raising():
    """A mixed stack deserves a broken tree, not a crashed run."""
    out = io.StringIO()

    span = ConsoleTracer(out).start_span("a", parent=NOOP_SPAN)
    span.end()

    assert _lines(out)[0]["parent_span_id"] == ""


def test_an_error_is_recorded_by_class_name_only():
    out = io.StringIO()
    span = ConsoleTracer(out).start_span("a")

    span.record_error(FileNotFoundError("/data/patient_07.h5ad"))
    span.end()

    record = _lines(out)[0]
    assert record["error"] == "FileNotFoundError"
    assert "patient_07" not in json.dumps(record)


def test_attributes_merge_and_a_later_write_wins():
    out = io.StringIO()
    span = ConsoleTracer(out).start_span("a", attributes={"x": 1})

    span.set_attributes({"y": 2})
    span.set_attributes({"x": 3})
    span.end()

    assert _lines(out)[0]["attributes"] == {"x": 3, "y": 2}


def test_a_bool_attribute_stays_a_bool():
    """``bool`` is an ``int`` in Python; a backend that forgets records ``1``."""
    out = io.StringIO()
    span = ConsoleTracer(out).start_span("a", attributes={"ok": True})
    span.end()

    assert _lines(out)[0]["attributes"]["ok"] is True


def test_a_meter_says_nothing_until_it_has_something_to_say():
    out = io.StringIO()

    ConsoleMeter(out).dump()

    assert out.getvalue() == ""


def test_a_counter_reports_a_total_and_a_histogram_reports_a_shape():
    out = io.StringIO()
    meter = ConsoleMeter(out)

    meter.count("omicsclaw.tool.calls.total", 1, {"tool.name": "bash"})
    meter.count("omicsclaw.tool.calls.total", 1, {"tool.name": "bash"})
    meter.record("omicsclaw.tool.execution.duration", 0.5, {"tool.name": "bash"})
    meter.record("omicsclaw.tool.execution.duration", 1.5, {"tool.name": "bash"})
    meter.dump()

    metrics = _lines(out)[0]["metrics"]
    calls = metrics["omicsclaw.tool.calls.total"][0]
    duration = metrics["omicsclaw.tool.execution.duration"][0]
    assert calls == {"attributes": {"tool.name": "bash"}, "total": 2.0, "count": 2}
    assert duration["min"] == 0.5 and duration["max"] == 1.5 and duration["mean"] == 1.0


def test_measurements_are_grouped_by_their_attributes():
    out = io.StringIO()
    meter = ConsoleMeter(out)

    meter.count("omicsclaw.tool.calls.total", 1, {"tool.name": "a"})
    meter.count("omicsclaw.tool.calls.total", 3, {"tool.name": "b"})
    meter.dump()

    series = _lines(out)[0]["metrics"]["omicsclaw.tool.calls.total"]
    assert len(series) == 2
    assert {s["attributes"]["tool.name"]: s["total"] for s in series} == {
        "a": 1.0,
        "b": 3.0,
    }


def test_a_snapshot_is_ordered_so_two_runs_can_be_diffed():
    meter = ConsoleMeter(io.StringIO())
    meter.count("omicsclaw.tool.calls.total", 1, {"z": "1", "a": "2"})

    (entry,) = meter.snapshot()["omicsclaw.tool.calls.total"]

    assert list(entry["attributes"]) == ["a", "z"]


def test_an_undeclared_instrument_is_still_visible():
    """A caller's typo shows up under the wrong shape, not not at all."""
    meter = ConsoleMeter(io.StringIO())

    meter.count("omicsclaw.typo", 1)

    assert "omicsclaw.typo" in meter.snapshot()


def test_the_default_stream_is_stderr_not_stdout():
    """Two of three surfaces draw on stdout; a span there corrupts the screen."""
    import sys

    tracer = ConsoleTracer()
    span = tracer.start_span("a")

    assert isinstance(span, ConsoleSpan)
    assert ConsoleMeter()._stream is sys.stderr
