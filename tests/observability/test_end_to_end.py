"""The real engine, the real registry, the real hook chain, one trace.

The unit tests above each pin one seam. This file is the only one that
checks the thing a person actually looks at: that a run of the loop
produces a single, correctly nested trace with no phantom spans in it.
"""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.engine import AgentEngine, EngineConfig
from omicsclaw.hooks import AuditHook, JsonlAuditSink, hook_tools
from omicsclaw.observability import Telemetry
from omicsclaw.observability.hook import TracingHook
from omicsclaw.schema import Message, Role
from omicsclaw.tools import ToolRegistry

from ._support import (
    Echo,
    Exploding,
    RecordingMeter,
    RecordingTracer,
    Scripted,
    Slow,
    assistant,
    run,
    tool_turn,
)


def _stack(provider, tools, **telemetry_kwargs):
    tracer, meter = RecordingTracer(), RecordingMeter()
    telemetry = Telemetry(tracer=tracer, meter=meter, **telemetry_kwargs)
    traced = telemetry.trace_provider(provider, model="gpt-test")
    mounted = hook_tools(tools, telemetry.tool_hooks())
    engine = AgentEngine(traced, ToolRegistry(mounted), EngineConfig(max_turns=5))
    return telemetry, engine, tracer, meter


async def _drive(telemetry, engine, *, session_id="s", prompt="hi"):
    async with telemetry.run(session_id=session_id, prompt=prompt) as scope:
        async for event in engine.run_stream([Message(role=Role.USER, content=prompt)]):
            scope.observe(event)


def test_a_two_turn_run_produces_the_three_level_tree():
    telemetry, engine, tracer, meter = _stack(
        Scripted(
            tool_turn("echo", "echo", input_tokens=10, output_tokens=5),
            assistant("final", input_tokens=7, output_tokens=3),
        ),
        [Echo()],
    )

    run(_drive(telemetry, engine))

    assert [s.name for s in tracer.spans].count("omicsclaw.interaction") == 1
    assert len(tracer.named("omicsclaw.turn")) == 2
    assert len(tracer.named("omicsclaw.llm_request")) == 2
    assert len(tracer.named("omicsclaw.tool")) == 2

    for span in tracer.named("omicsclaw.tool"):
        assert span.chain == [
            "omicsclaw.tool",
            "omicsclaw.turn",
            "omicsclaw.interaction",
        ]
    for span in tracer.named("omicsclaw.llm_request"):
        assert span.chain[1:] == ["omicsclaw.turn", "omicsclaw.interaction"]


def test_every_span_is_ended_exactly_once():
    """An unended span is a span that never reaches a backend."""
    telemetry, engine, tracer, _ = _stack(
        Scripted(tool_turn("echo"), assistant()), [Echo()]
    )

    run(_drive(telemetry, engine))

    assert all(span.ended == 1 for span in tracer.spans)


def test_no_phantom_turn_survives_the_last_one():
    """The whole reason ``TurnScope`` is lazy."""
    telemetry, engine, tracer, _ = _stack(Scripted(assistant()), [Echo()])

    run(_drive(telemetry, engine))

    turns = tracer.named("omicsclaw.turn")
    assert len(turns) == 1
    assert turns[0].attributes["agent.turn"] == 1


def test_the_root_span_reports_the_run_that_happened():
    telemetry, engine, tracer, _ = _stack(
        Scripted(
            tool_turn("echo", input_tokens=10, output_tokens=5),
            assistant("final", input_tokens=7, output_tokens=3),
        ),
        [Echo()],
    )

    run(_drive(telemetry, engine, session_id="sess-9"))

    root = tracer.named("omicsclaw.interaction")[0]
    assert root.attributes["session.id"] == "sess-9"
    assert root.attributes["agent.turns"] == 2
    assert root.attributes["agent.stop_reason"] == "converged"
    assert root.attributes["llm.tokens.input"] == 17
    assert root.attributes["llm.tokens.output"] == 8


def test_the_instruments_add_up_to_the_run():
    telemetry, engine, _, meter = _stack(
        Scripted(
            tool_turn("echo", "echo", input_tokens=10, output_tokens=5),
            assistant(input_tokens=7, output_tokens=3),
        ),
        [Echo()],
    )

    run(_drive(telemetry, engine))

    assert meter.totals("omicsclaw.agent.turns.total") == 2
    assert meter.totals("omicsclaw.llm.tokens.input") == 17
    assert meter.totals("omicsclaw.llm.tokens.output") == 8
    assert meter.totals("omicsclaw.tool.calls.total") == 2
    assert len([n for n, _, _ in meter.records if n.endswith("request.duration")]) == 2


def test_a_turn_that_acted_is_marked_and_one_that_did_not_is_not():
    telemetry, engine, tracer, _ = _stack(
        Scripted(tool_turn("echo"), assistant()), [Echo()]
    )

    run(_drive(telemetry, engine))

    flags = [t.attributes["turn.has_tool_calls"] for t in tracer.named("omicsclaw.turn")]
    assert flags == [True, False]


def test_tool_spans_of_one_turn_really_do_overlap():
    """Concurrency is the thing a reader uses to tell a parallel turn apart."""
    telemetry, engine, tracer, meter = _stack(
        Scripted(tool_turn("slow", "slow"), assistant()), [Slow(delay=0.05)]
    )

    started = asyncio.get_event_loop_policy().new_event_loop()
    started.close()
    run(_drive(telemetry, engine))

    durations = [v for n, v, _ in meter.records if n.endswith("execution.duration")]
    assert len(durations) == 2
    assert all(d >= 0.05 for d in durations)


def test_a_provider_failure_marks_the_root_and_re_raises():
    telemetry, engine, tracer, _ = _stack(Exploding(), [Echo()])

    with pytest.raises(Exception):
        run(_drive(telemetry, engine))

    root = tracer.named("omicsclaw.interaction")[0]
    assert root.error == "ProviderError"
    assert root.ended == 1
    assert "agent.turns" not in root.attributes


def test_a_cancelled_run_closes_every_span_it_opened():
    telemetry, engine, tracer, _ = _stack(
        Scripted(tool_turn("slow"), assistant()), [Slow(delay=5.0)]
    )

    async def cancel_mid_tool():
        task = asyncio.ensure_future(_drive(telemetry, engine))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(cancel_mid_tool())

    assert tracer.spans, "the run got far enough to open something"
    assert all(span.ended == 1 for span in tracer.spans)
    assert tracer.named("omicsclaw.interaction")[0].error == "CancelledError"


def test_the_blocking_path_gets_two_levels_and_still_counts_its_turns():
    """``AgentEngine.run`` drops its events; the trace says so honestly."""
    from omicsclaw.engine import EngineEvent

    telemetry, engine, tracer, _ = _stack(
        Scripted(tool_turn("echo"), assistant(input_tokens=4)), [Echo()]
    )

    async def blocking():
        async with telemetry.run(
            session_id="s", prompt="hi", turn_events=False
        ) as scope:
            result = await engine.run([Message(role=Role.USER, content="hi")])
            scope.observe(EngineEvent.done(result))

    run(blocking())

    assert tracer.named("omicsclaw.turn") == []
    assert len(tracer.named("omicsclaw.llm_request")) == 2
    assert tracer.named("omicsclaw.tool")[0].chain == [
        "omicsclaw.tool",
        "omicsclaw.interaction",
    ]
    assert tracer.named("omicsclaw.interaction")[0].attributes["agent.turns"] == 2


def test_two_concurrent_runs_produce_two_unmixed_traces():
    """One process, two sessions — the property a Channel surface needs."""

    async def exercise():
        stacks = [
            _stack(Scripted(tool_turn("echo"), assistant()), [Echo()])
            for _ in range(2)
        ]
        await asyncio.gather(
            *(
                _drive(telemetry, engine, session_id=f"s{i}")
                for i, (telemetry, engine, _, _) in enumerate(stacks)
            )
        )
        return stacks

    stacks = run(exercise())

    for index, (_, _, tracer, _) in enumerate(stacks):
        root = tracer.named("omicsclaw.interaction")[0]
        assert root.attributes["session.id"] == f"s{index}"
        for span in tracer.spans:
            assert span.chain[-1] == "omicsclaw.interaction"
            assert span.chain[-1:] == ["omicsclaw.interaction"]


def test_an_unobserved_run_changes_nothing_about_the_object_graph():
    """The claim the whole design rests on, checked rather than asserted."""
    telemetry = Telemetry()
    provider = Scripted(tool_turn("echo"), assistant())
    tool = Echo()

    traced = telemetry.trace_provider(provider, model="m")
    mounted = hook_tools([tool], telemetry.tool_hooks())

    assert traced is provider
    assert mounted[0] is tool


def test_the_audit_log_and_the_trace_agree_about_an_outcome(tmp_path):
    """Two records of one call that cannot contradict each other."""
    tracer, meter = RecordingTracer(), RecordingMeter()
    telemetry = Telemetry(tracer=tracer, meter=meter)
    path = tmp_path / "audit.jsonl"

    mounted = hook_tools(
        [Echo()],
        (AuditHook(JsonlAuditSink(path)), TracingHook(tracer, meter)),
    )
    engine = AgentEngine(
        telemetry.trace_provider(Scripted(tool_turn("echo"), assistant())),
        ToolRegistry(mounted),
        EngineConfig(max_turns=5),
    )
    real = Telemetry(tracer=tracer, meter=meter)

    run(_drive(real, engine))

    import json

    (line,) = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["outcome"] == "ok"
    assert tracer.named("omicsclaw.tool")[0].attributes["tool.status"] == "ok"


def test_a_blocking_caller_that_forgets_the_flag_is_warned(caplog):
    """The wrong number this flag exists to prevent, caught out loud.

    Without it a five-turn run is one span saying ``agent.turn=1``, which
    is not a missing level but a lie. The scope cannot fix the parenting
    after the fact — the first model call asked for a parent before any
    event could have arrived — so the next best thing is to say so.
    """
    from omicsclaw.engine import EngineEvent

    telemetry, engine, tracer, _ = _stack(
        Scripted(tool_turn("echo"), assistant()), [Echo()]
    )

    async def miswired():
        async with telemetry.run(session_id="s") as scope:
            result = await engine.run([Message(role=Role.USER, content="hi")])
            scope.observe(EngineEvent.done(result))

    with caplog.at_level("WARNING", logger="omicsclaw.observability.scope"):
        run(miswired())

    assert "turn_events=False" in caplog.text
    assert len(tracer.named("omicsclaw.turn")) == 1


def test_a_scope_told_there_are_no_turn_events_corrects_itself_if_sent_one():
    """Self-correcting, so the flag cannot make the trace worse than it was."""
    telemetry, engine, tracer, _ = _stack(
        Scripted(tool_turn("echo"), assistant()), [Echo()]
    )

    async def mislabelled():
        async with telemetry.run(session_id="s", turn_events=False) as scope:
            async for event in engine.run_stream(
                [Message(role=Role.USER, content="hi")]
            ):
                scope.observe(event)

    run(mislabelled())

    turns = tracer.named("omicsclaw.turn")
    assert [t.attributes["agent.turn"] for t in turns] == [2]
    assert all(span.ended == 1 for span in tracer.spans)


def test_a_one_turn_blocking_run_is_not_warned_about(caplog):
    """A single turn span is a correct description of a one-turn run."""
    from omicsclaw.engine import EngineEvent

    telemetry, engine, _, _ = _stack(Scripted(assistant()), [Echo()])

    async def single():
        async with telemetry.run(session_id="s") as scope:
            result = await engine.run([Message(role=Role.USER, content="hi")])
            scope.observe(EngineEvent.done(result))

    with caplog.at_level("WARNING", logger="omicsclaw.observability.scope"):
        run(single())

    assert "turn_events" not in caplog.text
