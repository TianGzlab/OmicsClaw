"""Plan 0035: compaction inside a run, through the real composition root.

Everything below is the deployed path — ``build_app``, the engine, the
registry, the channel command — with only the model backend and the one
tool replaced. The budgets are chosen so the first compaction happens in
the *middle* of a run, which is the property this step exists for: before
it, a conversation could only shrink between two ``run()`` calls.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import pathlib

from omicsclaw.context import (
    COMPACTION_MARKER,
    OFFLOAD_MARKER,
    ContextBudget,
    Pressure,
    estimate_messages_tokens,
)
from omicsclaw.context.offload import parse_placeholder
from omicsclaw.engine import AgentEngine
from omicsclaw.entry.channel.commands import SlashCommandContext, dispatch
from omicsclaw.entry.compaction import (
    RECORDS_DIRNAME,
    STATE_DIRNAME,
    TOOL_RESULTS_DIRNAME,
)
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.session import Session, attach_sessions
from omicsclaw.entry.turn import run_turn
from omicsclaw.schema import Message, Role, ToolCall
from omicsclaw.tools import FunctionTool, ToolPolicy
from omicsclaw.tools.base import ApprovalMode, RiskLevel
from tests.entry.test_session import Canned  # type: ignore[import-not-found]
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    calling,
    make_app,
)

WAIT_S = 5.0

_OPEN = ToolPolicy(
    risk_level=RiskLevel.LOW, approval_mode=ApprovalMode.AUTO, concurrency_safe=True
)


class Table:
    """A tool whose every answer is a different, large table."""

    def __init__(self) -> None:
        self.outputs: list[str] = []

    def __call__(self) -> str:
        output = f"result {len(self.outputs)}\n" + "row\t1\t2\t3\n" * 700
        self.outputs.append(output)
        return output

    def tool(self) -> FunctionTool:
        return FunctionTool(
            "dump",
            "dump a table",
            self,
            parameters={"type": "object", "properties": {}},
            policy=_OPEN,
        )


def _quiet() -> FunctionTool:
    """A tool with a one-word answer, so only the model's own text is large."""
    return FunctionTool(
        "dump",
        "dump a table",
        lambda: "ok",
        parameters={"type": "object", "properties": {}},
        policy=_OPEN,
    )


class Failing(Canned):
    async def summarize(self, prompt: str, *, system: str) -> str:
        self.prompts.append(prompt)
        raise RuntimeError("summary model unavailable")


def _budget(tokens: int) -> ContextBudget:
    return ContextBudget(
        context_tokens=tokens,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )


def _app(tmp_path: pathlib.Path, provider, tool, *, tokens: int, **replace):
    app = make_app(tmp_path, provider, tools=(tool,))
    app = dataclasses.replace(app, budget=_budget(tokens), **replace)
    return dataclasses.replace(
        app, engine=AgentEngine(provider, app.registry, app.config.engine_config())
    )


def _thinking(index: int) -> Message:
    """An action whose own text is large, so offloading alone cannot help."""
    return Message(
        role=Role.ASSISTANT,
        content=f"step {index} " + "t" * 6_000,
        tool_calls=(ToolCall(id=f"c{index}", name="dump", arguments="{}"),),
    )


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# --- offloading, mid-run ---------------------------------------------------


def test_a_tool_result_is_offloaded_mid_run_and_can_be_read_back(tmp_path):
    table = Table()
    provider = Scripted(*([calling("dump")] * 6), Message.assistant("done"))
    app = _app(tmp_path, provider, table.tool(), tokens=14_000)

    outcome = _run(run_turn(app, [], "go", session_id="s1"))

    placeholders = [
        sum(m.content.startswith(OFFLOAD_MARKER) for m in seen)
        for seen in provider.seen
    ]
    assert placeholders[0] == 0
    assert placeholders[-1] > 0, "a later call of the same run saw a placeholder"
    moved = [m for m in outcome.history if m.content.startswith(OFFLOAD_MARKER)]
    assert moved, "the offload was written back into the history"
    entry = parse_placeholder(moved[0])
    assert entry is not None
    assert entry.reference.startswith(f"{STATE_DIRNAME}/{TOOL_RESULTS_DIRNAME}/s1/")
    assert (tmp_path / entry.reference).read_text() in table.outputs


def test_every_compaction_is_logged_for_its_session(tmp_path):
    provider = Scripted(*([calling("dump")] * 6), Message.assistant("done"))
    app = _app(tmp_path, provider, Table().tool(), tokens=14_000)

    outcome = _run(run_turn(app, [], "go", session_id="s1"))

    log = tmp_path / STATE_DIRNAME / RECORDS_DIRNAME / "s1.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert lines
    assert len(lines) <= len(outcome.compactions)
    assert all(line["session_id"] == "s1" for line in lines)
    assert any(line["offloaded"] for line in lines)


def test_a_failed_compaction_is_logged_and_a_broken_listener_does_not_stop_it(
    tmp_path,
):
    from omicsclaw.entry.compaction import build_compactor, compaction_log

    history = (Message.system("sys"), *[_thinking(i) for i in range(4)])
    history = (*history, *(Message.user("u" * 4_000) for _ in range(6)))
    at_full = int(estimate_messages_tokens(history) / 0.85)
    provider = Scripted(Message.assistant("done"))
    app = _app(tmp_path, provider, _quiet(), tokens=at_full, summarizer=Failing())

    def broken(record):
        raise RuntimeError("renderer crashed")

    compactor = build_compactor(app, session_id="s1", on_compact=broken)
    _run(compactor.compact(history, ()))

    (logged,) = _run(compaction_log(app.config).list("s1"))
    assert logged.record.pressure is Pressure.FULL
    assert logged.record.degraded
    assert not logged.record.written_back


# --- summarizing, mid-run --------------------------------------------------


def test_a_summary_mid_run_is_written_back(tmp_path):
    provider = Scripted(*[_thinking(i) for i in range(8)], Message.assistant("done"))
    summarizer = Canned()
    app = _app(
        tmp_path, provider, _quiet(), tokens=10_000, summarizer=summarizer
    )

    outcome = _run(run_turn(app, [], "go", session_id="s1"))

    assert summarizer.prompts, "the run summarized without waiting for its end"
    assert provider.seen[0][1].content == "go"
    assert any(s[1].content.startswith(COMPACTION_MARKER) for s in provider.seen)
    assert outcome.history[0].content.startswith(COMPACTION_MARKER)
    assert outcome.state.summary == "they discussed it at length"
    summarized = [record for record in outcome.compactions if record.summarized]
    assert all(record.written_back for record in summarized)


def test_a_failed_summary_is_sent_once_and_not_kept(tmp_path):
    provider = Scripted(*[_thinking(i) for i in range(8)], Message.assistant("done"))
    app = _app(tmp_path, provider, _quiet(), tokens=10_000, summarizer=Failing())

    outcome = _run(run_turn(app, [], "go", session_id="s1"))

    records = outcome.compactions
    failed = [
        index
        for index, record in enumerate(records)
        if record.degraded and record.pressure is not Pressure.EMERGENCY
    ]
    assert failed
    for index in failed:
        record = records[index]
        assert not record.written_back
        assert record.msgs_after < record.msgs_before, "the call got a view that fits"
        if index + 1 < len(records):
            # The next call measured the whole history again, grown by one
            # action and its answer: the truncated view was not kept.
            assert records[index + 1].msgs_before == record.msgs_before + 2
    assert not any(m.content.startswith(COMPACTION_MARKER) for m in outcome.history)
    assert outcome.history[0].content == "go", "the task survived every truncation"


def test_an_emergency_truncation_leaves_room_to_summarize_next(tmp_path):
    """The outage path: summaries keep failing, the history keeps growing
    until EMERGENCY truncates it — and the call after that is a summary
    attempt again, not another truncation."""
    provider = Scripted(*[_thinking(i) for i in range(8)], Message.assistant("done"))
    app = _app(tmp_path, provider, _quiet(), tokens=10_000, summarizer=Failing())

    outcome = _run(run_turn(app, [], "go", session_id="s1"))

    tiers = [record.pressure for record in outcome.compactions]
    assert Pressure.EMERGENCY in tiers
    for earlier, later in zip(tiers, tiers[1:]):
        assert not (earlier is later is Pressure.EMERGENCY), tiers


def test_the_memory_extractor_reads_what_is_summarized_away(tmp_path):
    seen: list[tuple[Message, ...]] = []

    class Extractor:
        async def extract(self, messages):
            seen.append(tuple(messages))

    provider = Scripted(*[_thinking(i) for i in range(8)], Message.assistant("done"))
    app = _app(
        tmp_path,
        provider,
        _quiet(),
        tokens=10_000,
        summarizer=Canned(),
        memory_extractor=Extractor(),
    )

    _run(run_turn(app, [], "go", session_id="s1"))

    assert seen
    assert seen[0][0].content == "go"


# --- the frames a surface sees --------------------------------------------


def test_each_model_call_is_measured_and_each_compaction_announced(tmp_path):
    provider = Scripted(*([calling("dump")] * 6), Message.assistant("done"))
    app = attach_sessions(_app(tmp_path, provider, Table().tool(), tokens=14_000))

    async def drive():
        handle = await app.sessions.submit("s1", "go")
        observed = handle.observe()
        frames = [frame async for frame in observed]
        return frames, await handle.wait()

    frames, outcome = _run(drive())

    kinds = [frame.type for frame in frames]
    assert kinds.count(TurnEventType.CONTEXT) == len(provider.seen)
    compactions = [f for f in frames if f.type is TurnEventType.COMPACTION]
    assert compactions
    assert all(frame.compaction.offloaded for frame in compactions)
    first_compaction = kinds.index(TurnEventType.COMPACTION)
    assert TurnEventType.CONTEXT in kinds[:first_compaction]


# --- /compact --------------------------------------------------------------


def _bulk() -> tuple[Message, ...]:
    messages: list[Message] = []
    for index in range(20):
        messages.append(Message.user(f"question {index} " + "q" * 300))
        messages.append(Message.assistant("answer " + "a" * 300))
    return tuple(messages)


def test_compact_summarizes_a_quiet_session_in_its_lane(tmp_path):
    provider = Scripted(Message.assistant("done"))
    app = attach_sessions(
        _app(tmp_path, provider, Table().tool(), tokens=200_000, summarizer=Canned())
    )

    async def drive():
        await app.sessions._store.save(Session(session_id="s1", history=_bulk()))
        first = await app.sessions.submit("s1", "one more")
        compaction = await app.sessions.compact("s1")
        await first.wait()
        return first, await compaction.wait(), app.sessions.session("s1")

    first, outcome, session = _run(drive())

    assert first.outcome is not None, "the exchange ahead of it finished first"
    record = outcome.compaction
    assert record.forced and record.written_back
    assert session.history[0].content.startswith(COMPACTION_MARKER)
    assert session.history[-1].content == "done", "it compacted after the exchange"
    assert session.compaction.summary
    assert provider.calls == 1, "no model turn ran for the compaction"


def test_a_failed_compact_leaves_the_session_as_it_was(tmp_path):
    """Tight enough that the truncating fallback really removes messages,
    so keeping it and not keeping it are distinguishable."""
    provider = Scripted(Message.assistant("done"))
    tight = int(estimate_messages_tokens(_bulk()) / 0.72)
    app = attach_sessions(
        _app(tmp_path, provider, Table().tool(), tokens=tight, summarizer=Failing())
    )

    async def drive():
        await app.sessions._store.save(Session(session_id="s1", history=_bulk()))
        handle = await app.sessions.compact("s1")
        return await handle.wait(), app.sessions.session("s1")

    outcome, session = _run(drive())

    record = outcome.compaction
    assert record.degraded and record.msgs_after < record.msgs_before
    assert not record.written_back
    assert session.history == _bulk()


def test_the_channel_command_reports_the_compaction(tmp_path):
    provider = Scripted(Message.assistant("done"))
    app = attach_sessions(
        _app(tmp_path, provider, Table().tool(), tokens=200_000, summarizer=Canned())
    )

    def context(text: str) -> SlashCommandContext:
        return SlashCommandContext(
            chat_id="c1",
            user_id="u1",
            platform="feishu",
            user_text=text,
            workspace=str(tmp_path),
            app=app,
            session_id="s1",
        )

    async def drive():
        empty = await dispatch(context("/compact"))
        await app.sessions._store.save(Session(session_id="s1", history=_bulk()))
        app.sessions._sessions.pop("s1", None)
        full = await dispatch(context("/compact"))
        return empty, full

    empty, full = _run(drive())

    assert empty.startswith("Nothing to compact")
    assert full.startswith("Compacted:")
    assert "summarized" in full
