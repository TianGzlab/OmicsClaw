"""The tool seam: one span per call, four outcomes, never an opinion."""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.hooks import (
    AuditHook,
    AuditOutcome,
    HookCall,
    HookDenied,
    Hook,
    ToolHook,
    deny,
    hook_tools,
)
from omicsclaw.observability import TracingHook
from omicsclaw.observability.scope import current_parent, fixed, pop_parent, push_parent

from ._support import Echo, RecordingMeter, RecordingTracer, Slow, run


def _hooked(tool=None, *, capture_content=False, before=()):
    tracer, meter = RecordingTracer(), RecordingMeter()
    hook = TracingHook(tracer, meter, capture_content=capture_content)
    tool = Echo() if tool is None else tool
    return hook_tools([tool], (*before, hook))[0], tracer, meter


def test_it_is_a_tool_hook():
    assert isinstance(TracingHook(RecordingTracer(), RecordingMeter()), ToolHook)


def test_it_never_denies():
    """``before_execute`` exists to start a clock, not to have an opinion."""
    hook = TracingHook(RecordingTracer(), RecordingMeter())

    decision = run(hook.before_execute(HookCall(name="echo", arguments="{}")))

    assert decision.action == "allow"
    assert decision.arguments is None


def test_a_successful_call_gets_one_span_and_two_measurements():
    hooked, tracer, meter = _hooked()

    assert run(hooked.execute('{"x":1}')) == 'echoed {"x":1}'

    span = tracer.named("omicsclaw.tool")[0]
    assert span.attributes["tool.name"] == "echo"
    assert span.attributes["tool.status"] == "ok"
    assert span.attributes["tool.success"] is True
    assert span.ended == 1
    assert meter.totals("omicsclaw.tool.calls.total") == 1
    assert [n for n, _, _ in meter.records] == ["omicsclaw.tool.execution.duration"]


def test_the_output_is_returned_untouched():
    """An observer that changes what the model reads has stopped being one."""
    hooked, _, _ = _hooked()

    assert run(hooked.execute("{}")) == "echoed {}"


def test_a_failing_tool_is_recorded_as_an_error_without_its_message():
    """A tool's error text quotes the argument it could not use."""

    class Boom:
        @property
        def name(self):
            return "read_file"

        def definition(self):
            from omicsclaw.schema import ToolDefinition

            return ToolDefinition(name="read_file", description="", input_schema={})

        async def execute(self, arguments):
            raise FileNotFoundError("/data/GSE12345/patient_07.h5ad")

    hooked, tracer, meter = _hooked(Boom())

    with pytest.raises(FileNotFoundError):
        run(hooked.execute("{}"))

    span = tracer.named("omicsclaw.tool")[0]
    assert span.error == "FileNotFoundError"
    assert "patient_07" not in str(span.attributes)
    assert span.attributes["tool.status"] == "error"
    assert span.attributes["tool.success"] is False


def test_a_refusal_by_another_hook_is_recorded_as_denied():
    class Blocker(Hook):
        async def before_execute(self, call):
            return deny("not allowed")

    tracer, meter = RecordingTracer(), RecordingMeter()
    tracing = TracingHook(tracer, meter)
    # tracing first, blocker after it — the only order in which a deny can
    # reach a hook that already decided.
    hooked = hook_tools([Echo()], (tracing, Blocker()))[0]

    with pytest.raises(HookDenied):
        run(hooked.execute("{}"))

    span = tracer.named("omicsclaw.tool")[0]
    assert span.attributes["tool.status"] == AuditOutcome.DENIED.value
    assert span.attributes["tool.success"] is False


def test_a_cancelled_call_is_told_apart_from_a_failed_one():
    """A failure rate that is really a user pressing Ctrl-C is a wrong number."""

    class Cancelling:
        @property
        def name(self):
            return "slow"

        def definition(self):
            from omicsclaw.schema import ToolDefinition

            return ToolDefinition(name="slow", description="", input_schema={})

        async def execute(self, arguments):
            raise asyncio.CancelledError()

    hooked, tracer, _ = _hooked(Cancelling())

    with pytest.raises(asyncio.CancelledError):
        run(hooked.execute("{}"))

    assert tracer.named("omicsclaw.tool")[0].attributes["tool.status"] == "cancelled"


def test_the_status_vocabulary_is_the_audit_layers():
    """Two spellings of "how did this call end" would be two answers."""
    assert {member.value for member in AuditOutcome} == {
        "ok",
        "error",
        "denied",
        "cancelled",
    }


def test_the_duration_is_measured_and_is_positive():
    hooked, _, meter = _hooked(Slow(delay=0.02))

    run(hooked.execute("{}"))

    name, value, dims = meter.records[0]
    assert name == "omicsclaw.tool.execution.duration"
    assert value >= 0.02
    assert dims == {"tool.name": "slow", "tool.status": "ok"}


def test_concurrent_calls_do_not_close_each_others_spans():
    """One hook instance is mounted on every tool; a field would race."""
    tracer, meter = RecordingTracer(), RecordingMeter()
    hook = TracingHook(tracer, meter)
    fast = hook_tools([Echo("fast")], (hook,))[0]
    slow = hook_tools([Slow(delay=0.03, name="slow")], (hook,))[0]

    async def both():
        await asyncio.gather(slow.execute("{}"), fast.execute("{}"))

    run(both())

    spans = tracer.named("omicsclaw.tool")
    assert len(spans) == 2
    assert all(span.ended == 1 for span in spans)
    assert {s.attributes["tool.name"] for s in spans} == {"fast", "slow"}


def test_the_span_is_parented_to_whatever_is_current():
    tracer, meter = RecordingTracer(), RecordingMeter()
    hooked = hook_tools([Echo()], (TracingHook(tracer, meter),))[0]
    outer = tracer.start_span("outer")
    token = push_parent(fixed(outer))
    try:
        run(hooked.execute("{}"))
    finally:
        pop_parent(token)

    assert tracer.named("omicsclaw.tool")[0].chain == ["omicsclaw.tool", "outer"]


def test_the_tool_span_becomes_the_parent_for_whatever_the_tool_runs():
    """A sub-agent nests under the call that started it."""
    tracer, meter = RecordingTracer(), RecordingMeter()
    seen = []

    class Nesting:
        @property
        def name(self):
            return "agent"

        def definition(self):
            from omicsclaw.schema import ToolDefinition

            return ToolDefinition(name="agent", description="", input_schema={})

        async def execute(self, arguments):
            seen.append(current_parent())
            return "ok"

    hooked = hook_tools([Nesting()], (TracingHook(tracer, meter),))[0]
    run(hooked.execute("{}"))

    assert seen[0] is tracer.named("omicsclaw.tool")[0]


def test_the_binding_is_released_after_the_call():
    hooked, _, _ = _hooked()

    run(hooked.execute("{}"))

    assert current_parent() is None


def test_arguments_are_not_recorded_by_default():
    hooked, tracer, _ = _hooked()

    run(hooked.execute('{"command": "rm -rf /data/cohort"}'))

    assert "rm -rf" not in str(tracer.named("omicsclaw.tool")[0].attributes)


def test_arguments_and_output_are_recorded_when_capture_is_on():
    hooked, tracer, _ = _hooked(capture_content=True)

    run(hooked.execute('{"x":1}'))

    span = tracer.named("omicsclaw.tool")[0]
    assert span.attributes["langfuse.observation.input"] == '{"x":1}'
    assert span.attributes["langfuse.observation.output"] == 'echoed {"x":1}'


def test_a_broken_tracer_does_not_break_the_tool():
    class Broken:
        def start_span(self, *a, **k):
            raise RuntimeError("down")

    hooked = hook_tools([Echo()], (TracingHook(Broken(), RecordingMeter()),))[0]

    assert run(hooked.execute("{}")) == "echoed {}"


def test_a_broken_meter_does_not_break_the_tool():
    class BrokenMeter(RecordingMeter):
        def record(self, *a, **k):
            raise RuntimeError("down")

    hooked = hook_tools([Echo()], (TracingHook(RecordingTracer(), BrokenMeter()),))[0]

    assert run(hooked.execute("{}")) == "echoed {}"


def test_it_coexists_with_the_audit_hook_without_duplicating_it():
    """Two records of one call, answering two questions."""
    import tempfile
    from pathlib import Path

    from omicsclaw.hooks import JsonlAuditSink

    tracer, meter = RecordingTracer(), RecordingMeter()
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "audit.jsonl"
        hooked = hook_tools(
            [Echo()],
            (AuditHook(JsonlAuditSink(path)), TracingHook(tracer, meter)),
        )[0]

        run(hooked.execute('{"x":1}'))

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert '"outcome": "ok"' in lines[0]
        assert '{"x":1}' not in lines[0], "the audit log records a digest only"

    assert tracer.named("omicsclaw.tool")[0].attributes["tool.status"] == "ok"


def test_a_tool_that_calls_a_tool_in_its_own_task_does_not_blank_the_outer_call():
    """Stack semantics, matching ``scope.py``'s parent binding next door.

    Nothing in the tree reaches this today — the executor gives every tool
    call its own Task — but :meth:`TracingHook.before_execute`'s docstring
    describes a tool that runs an agent of its own, and with overwrite
    semantics the inner call's exit blanked the outer one's state: the
    outer span was never ended, its parent binding never released, and
    every later span in that task hung off a closed tool span.
    """
    tracer, meter = RecordingTracer(), RecordingMeter()
    hook = TracingHook(tracer, meter)
    inner = hook_tools([Echo("inner")], (hook,))[0]

    class Outer:
        @property
        def name(self):
            return "outer"

        def definition(self):
            from omicsclaw.schema import ToolDefinition

            return ToolDefinition(name="outer", description="", input_schema={})

        async def execute(self, arguments):
            # Deliberately awaited inline rather than in a child Task —
            # that is the shape the guard exists for.
            return await inner.execute("{}")

    outer = hook_tools([Outer()], (hook,))[0]
    run(outer.execute("{}"))

    spans = {span.attributes["tool.name"]: span for span in tracer.named("omicsclaw.tool")}
    assert set(spans) == {"outer", "inner"}
    assert all(span.ended == 1 for span in spans.values()), "both spans were closed"
    assert spans["inner"].chain == ["omicsclaw.tool", "omicsclaw.tool"], (
        "the inner call nests under the outer one"
    )
    assert current_parent() is None, "the task's binding is fully unwound"
