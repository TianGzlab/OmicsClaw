"""One exchange, instrumented: the canonical sequence and its traps.

Plan 0031 §3.3 and traps 1, 1b, 2, 3, 12. Everything here drives a real
:class:`~omicsclaw.entry.assembly.AgentApp` — real registry, real engine,
real context assembly — over a scripted provider, because the defects
this file is about live between those pieces rather than inside any one
of them.

The fakes below are exported for ``test_session.py``, which needs the
same app over the same scripted backend one layer further out.
"""

from __future__ import annotations

import asyncio
import pathlib
from contextlib import contextmanager
from typing import Iterator

import pytest

from omicsclaw.context import ContextBudget
from omicsclaw.engine import AgentEngine, EngineEvent
from omicsclaw.entry import assembly
from omicsclaw.entry.approval import ApprovalBroker
from omicsclaw.entry.assembly import build_app
from omicsclaw.entry.config import AppConfig
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.stream import TurnStream
from omicsclaw.entry.turn import TurnRunner
from omicsclaw.provider import Completion
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
)
from omicsclaw.tools import ApprovalMode, ToolPolicy, report_progress, require_approval
from omicsclaw.tools.context import ApprovalDecision

WAIT_S = 5.0
"""Every await in this file is bounded by it. A turn kernel defect is a
hang, and there is no timeout plugin on this machine."""


# ---- doubles -------------------------------------------------------------


class Scripted:
    """A provider that replays fixed replies and records what it was sent."""

    def __init__(self, *replies: Message) -> None:
        self.replies = list(replies) or [Message(role=Role.ASSISTANT, content="ok")]
        self.seen: list[tuple[Message, ...]] = []
        self.calls = 0

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None):
        self.seen.append(tuple(messages))
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return Completion(message=reply)

    async def _stream(self, messages, tools=None):
        completion = await self.generate(messages, tools)
        if completion.message.content:
            yield StreamChunk(
                type=StreamChunkType.TEXT_DELTA, delta=completion.message.content
            )
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)

    def generate_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    def bind(self, **overrides):
        return self


class Exploding(Scripted):
    """A backend that fails, for the paths a terminal frame must survive."""

    async def generate(self, messages, tools=None):
        raise RuntimeError("the backend fell over")


class Asking:
    """A tool that asks a human, then reports that it ran.

    ``concurrency_safe=True`` so that two calls in one model message are
    genuinely in flight together — which is the only arrangement in which
    trap 1's deadlock can happen at all.
    """

    policy = ToolPolicy(approval_mode=ApprovalMode.ASK, concurrency_safe=True)

    def __init__(self, name: str = "ask") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description="Does something that needs consent.",
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: str) -> str:
        await require_approval(self._name, arguments)
        return f"{self._name} ran"


class Reporting:
    """A tool that emits one progress update before finishing.

    Keeps :attr:`delivered` because
    :func:`~omicsclaw.tools.report_progress` answers whether anybody
    heard, and trap 8 is about what a tool does with a ``False``: nothing
    but carry on.
    """

    policy = ToolPolicy(approval_mode=ApprovalMode.AUTO, concurrency_safe=True)

    def __init__(self) -> None:
        self.delivered: bool | None = None

    @property
    def name(self) -> str:
        return "report"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="report",
            description="Reports progress.",
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: str) -> str:
        self.delivered = await report_progress(
            "halfway", tool_name="report", fraction=0.5
        )
        return "reported"


class Sleeping:
    """A tool that never finishes on its own, for the cancellation paths."""

    policy = ToolPolicy(approval_mode=ApprovalMode.AUTO, concurrency_safe=True)

    def __init__(self) -> None:
        self.entered = asyncio.Event()

    @property
    def name(self) -> str:
        return "sleep"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="sleep",
            description="Sleeps.",
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: str) -> str:
        self.entered.set()
        await asyncio.sleep(3600)
        return "slept"


class Blind:
    """A registry wrapper that forwards execution but **not** the pause.

    The shape plan 0031 Q16 warns about, kept as a test double so the
    consequence is a test rather than a paragraph: it satisfies
    ``ToolExecutor`` and therefore runs, and it fails
    ``isinstance(..., DeadlineAwareExecutor)``, so the engine never hands
    down a :data:`~omicsclaw.tools.TimeoutPause` and a human's thinking
    time is charged to ``tool_timeout`` again — defect R3.
    """

    def __init__(self, registry) -> None:
        self._registry = registry

    def available_tools(self):
        return self._registry.available_tools()

    async def execute(self, call):
        return await self._registry.execute(call)


def calling(*names: str) -> Message:
    """One assistant message asking for *names*, all in one turn."""
    return Message(
        role=Role.ASSISTANT,
        tool_calls=tuple(
            ToolCall(id=f"c{index}", name=name, arguments="{}")
            for index, name in enumerate(names)
        ),
    )


def make_app(tmp_path: pathlib.Path, provider, *, tools=None, **overrides):
    """A real app over a fake backend, built by the real composition root.

    *tools* is passed straight through to
    :func:`~omicsclaw.entry.build_app`, which keeps ``bash`` out of these
    tests: several of them configure a sub-second ``tool_timeout_s``, and
    ``AppConfig.bash_timeout()`` derives a negative construction argument
    from that.
    """
    (tmp_path / "SOUL.md").write_text("You are OmicsClaw.", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("Route to a skill.", encoding="utf-8")
    config = AppConfig(workspace=tmp_path, **overrides)

    real = assembly.provider_from_env
    assembly.provider_from_env = lambda p, m: provider
    try:
        return build_app(config, tools=tools)
    finally:
        assembly.provider_from_env = real


@contextmanager
def runner_for(app, *, text: str = "hi", **kwargs) -> Iterator[TurnRunner]:
    """A runner over a fresh stream and broker, as the registry builds one."""
    stream = TurnStream("s1", "t1")
    broker = ApprovalBroker(stream, timeout_s=kwargs.pop("approval_timeout_s", None))
    yield TurnRunner(
        app,
        stream,
        session_id="s1",
        turn_id="t1",
        user_text=text,
        approval=broker,
        **kwargs,
    )


async def answer_every_question(
    stream: TurnStream,
    broker: ApprovalBroker,
    *,
    hold: float = 0.0,
    approved: bool = True,
) -> list[str]:
    """Consume the whole stream, settling every question it shows.

    *hold* makes this consumer stop consuming before it answers, which is
    the arrangement trap 1 is about: a design where the question and the
    answer travel on one generator deadlocks here.
    """
    answered: list[str] = []
    async with stream.observe() as observation:
        async for frame in observation:
            if frame.type is not TurnEventType.APPROVAL_REQUIRED:
                continue
            if hold:
                await asyncio.sleep(hold)
            broker.settle(frame.request_id, ApprovalDecision(approved=approved))
            answered.append(frame.request_id)
    return answered


def types_of(stream: TurnStream) -> list[TurnEventType]:
    return [frame.type for frame in stream.retained()]


# ---- the canonical sequence (§3.3) --------------------------------------


def test_the_sequence_is_published_in_the_order_the_plan_fixes(tmp_path):
    app = make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done")))

    async def drive():
        with runner_for(app) as runner:
            await asyncio.wait_for(runner.run(), WAIT_S)
            return runner._stream

    stream = asyncio.run(drive())
    kinds = types_of(stream)

    assert kinds[0] is TurnEventType.EXCHANGE_START
    assert kinds[1] is TurnEventType.CONTEXT
    assert kinds[-1] is TurnEventType.EXCHANGE_END
    assert kinds.count(TurnEventType.EXCHANGE_END) == 1
    assert TurnEventType.TEXT_DELTA in kinds
    assert TurnEventType.TURN_END in kinds


def test_the_sequence_numbers_are_dense_and_start_at_one(tmp_path):
    app = make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done")))

    async def drive():
        with runner_for(app) as runner:
            await asyncio.wait_for(runner.run(), WAIT_S)
            return runner._stream

    seqs = [frame.seq for frame in asyncio.run(drive()).retained()]

    assert seqs == list(range(1, len(seqs) + 1))


def test_the_context_frame_carries_what_measure_returned(tmp_path):
    """Q19: the pre-call pressure figure the engine structurally lacks."""
    app = make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done")))

    async def drive():
        with runner_for(app) as runner:
            await asyncio.wait_for(runner.run(), WAIT_S)
            return runner._stream

    context = [
        frame
        for frame in asyncio.run(drive()).retained()
        if frame.type is TurnEventType.CONTEXT
    ]

    assert len(context) == 1
    report = context[0].report
    assert report is not None
    assert report.message_tokens > 0
    assert report.tool_tokens >= 0


def test_a_pass_through_frame_carries_the_original_engine_event(tmp_path):
    app = make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done")))

    async def drive():
        with runner_for(app) as runner:
            await asyncio.wait_for(runner.run(), WAIT_S)
            return runner._stream

    deltas = [
        frame
        for frame in asyncio.run(drive()).retained()
        if frame.type is TurnEventType.TEXT_DELTA
    ]

    assert deltas
    assert isinstance(deltas[0].engine, EngineEvent)
    assert deltas[0].engine.delta == "done"


def test_the_history_carried_forward_has_no_system_message(tmp_path):
    app = make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done")))

    async def drive():
        with runner_for(app, text="one") as runner:
            return await asyncio.wait_for(runner.run(), WAIT_S)

    outcome = asyncio.run(drive())

    assert not any(m.role is Role.SYSTEM for m in outcome.history)
    assert outcome.history[0].content == "one"
    assert outcome.reply == "done"


def test_compaction_is_announced_before_the_engine_sees_anything(tmp_path):
    """Acceptance §9-8: compaction on the production path, observably."""
    import dataclasses

    app = make_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done")))
    app = dataclasses.replace(
        app,
        budget=ContextBudget(
            context_tokens=2_000,
            reserve_output_tokens=200,
            reserve_tool_tokens=200,
        ),
    )
    history = []
    for index in range(40):
        history.append(Message.user(f"question {index} " + "q" * 400))
        history.append(Message.assistant("answer " + "a" * 400))

    async def drive():
        with runner_for(app, text="next", history=history) as runner:
            outcome = await asyncio.wait_for(runner.run(), WAIT_S)
            return outcome, types_of(runner._stream)

    outcome, kinds = asyncio.run(drive())

    assert outcome.compaction is not None
    assert kinds.index(TurnEventType.COMPACTION) < kinds.index(TurnEventType.TURN_END)
    assert kinds.index(TurnEventType.CONTEXT) < kinds.index(TurnEventType.COMPACTION)


# ---- trap 1b: the terminal frame always exists --------------------------


def test_a_failing_backend_still_ends_the_stream(tmp_path):
    app = make_app(tmp_path, Exploding())

    async def drive():
        with runner_for(app) as runner:
            with pytest.raises(Exception):
                await asyncio.wait_for(runner.run(), WAIT_S)
            return runner._stream.retained()[-1], runner.terminal

    last, terminal = asyncio.run(drive())

    assert terminal == "failed"
    assert last.type is TurnEventType.EXCHANGE_END
    assert last.terminal == "failed"
    assert last.error is not None


def test_a_cancelled_exchange_says_cancelled_rather_than_vanishing(tmp_path):
    """Q5b: a consumer across HTTP cannot tell "stopped" from "finished"."""
    sleeping = Sleeping()
    app = make_app(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[sleeping],
    )

    async def drive():
        with runner_for(app) as runner:
            task = asyncio.create_task(runner.run())
            await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, WAIT_S)
            return runner._stream.retained()[-1], runner.terminal

    last, terminal = asyncio.run(drive())

    assert terminal == "cancelled"
    assert last.type is TurnEventType.EXCHANGE_END
    assert last.terminal == "cancelled"


def test_a_turn_deadline_is_a_failure_and_still_ends_the_stream(tmp_path):
    sleeping = Sleeping()
    app = make_app(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[sleeping],
        turn_timeout_s=0.05,
    )

    async def drive():
        with runner_for(app) as runner:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(runner.run(), WAIT_S)
            return runner._stream.retained()[-1], runner.terminal

    last, terminal = asyncio.run(drive())

    assert terminal == "failed"
    assert last.terminal == "failed"


# ---- trap 1: two questions, one consumer, no deadlock -------------------


def test_two_tools_asking_at_once_are_both_answered(tmp_path):
    """The deadlock trap 1 names, arranged as faithfully as this suite can.

    Two tools ask concurrently; the consumer stops consuming before it
    answers the first, which is what a UI showing a modal does. Both
    questions are answered and both tools succeed.
    """
    app = make_app(
        tmp_path,
        Scripted(
            calling("ask_one", "ask_two"),
            Message(role=Role.ASSISTANT, content="done"),
        ),
        tools=[Asking("ask_one"), Asking("ask_two")],
    )

    async def drive():
        stream = TurnStream("s1", "t1")
        broker = ApprovalBroker(stream)
        runner = TurnRunner(
            app, stream, session_id="s1", turn_id="t1",
            user_text="go", approval=broker,
        )
        consumer = asyncio.create_task(
            answer_every_question(stream, broker, hold=0.02)
        )
        outcome = await asyncio.wait_for(runner.run(), WAIT_S)
        answered = await asyncio.wait_for(consumer, WAIT_S)
        return outcome, answered

    outcome, answered = asyncio.run(drive())

    assert len(answered) == 2, "both questions must have reached the consumer"
    observations = [m for m in outcome.result.messages if m.role is Role.TOOL]
    assert len(observations) == 2
    assert not any(m.is_error for m in observations)


def test_an_unanswered_question_is_denied_when_the_exchange_ends(tmp_path):
    """Fail closed: the deadline denies, and the tool is told no."""
    app = make_app(
        tmp_path,
        Scripted(calling("ask"), Message(role=Role.ASSISTANT, content="done")),
        tools=[Asking("ask")],
    )

    async def drive():
        with runner_for(app, approval_timeout_s=0.02) as runner:
            return await asyncio.wait_for(runner.run(), WAIT_S)

    outcome = asyncio.run(drive())

    observations = [m for m in outcome.result.messages if m.role is Role.TOOL]
    assert len(observations) == 1
    assert observations[0].is_error


# ---- trap 12 / Q16: the human is not charged to the tool timeout --------


def test_an_approval_longer_than_the_tool_timeout_still_succeeds(tmp_path):
    """Defect R3, on the first layer that ever binds an approval channel.

    ``tool_timeout`` is 0.2 s and the person takes 0.4 s. The engine hands
    the registry a :data:`~omicsclaw.tools.TimeoutPause`, the registry
    carries it to the tool, and ``require_approval`` stops the clock
    around the round trip — so what is charged is the tool's own work,
    which is none.
    """
    app = make_app(
        tmp_path,
        Scripted(calling("ask"), Message(role=Role.ASSISTANT, content="done")),
        tools=[Asking("ask")],
        tool_timeout_s=0.2,
    )

    async def drive():
        stream = TurnStream("s1", "t1")
        broker = ApprovalBroker(stream)
        runner = TurnRunner(
            app, stream, session_id="s1", turn_id="t1",
            user_text="go", approval=broker,
        )
        consumer = asyncio.create_task(answer_every_question(stream, broker, hold=0.4))
        outcome = await asyncio.wait_for(runner.run(), WAIT_S)
        await asyncio.wait_for(consumer, WAIT_S)
        return outcome

    outcome = asyncio.run(drive())

    observations = [m for m in outcome.result.messages if m.role is Role.TOOL]
    assert len(observations) == 1
    assert not observations[0].is_error, "the pause was not carried to the tool"


def test_a_wrapper_that_swallows_the_pause_puts_r3_back(tmp_path):
    """The same exchange with :class:`Blind` between engine and registry.

    Kept as a test rather than as a warning in a docstring: it is the
    executable form of the mutation plan 0031 Q16 asks for, and it fails
    the *other* way — the tool is cancelled at ``tool_timeout`` and the
    model is told it ran long, which is false twice over.
    """
    import dataclasses

    app = make_app(
        tmp_path,
        Scripted(calling("ask"), Message(role=Role.ASSISTANT, content="done")),
        tools=[Asking("ask")],
        tool_timeout_s=0.2,
    )
    app = dataclasses.replace(
        app,
        engine=AgentEngine(
            app.provider, Blind(app.registry), app.config.engine_config()
        ),
    )

    async def drive():
        stream = TurnStream("s1", "t1")
        broker = ApprovalBroker(stream)
        runner = TurnRunner(
            app, stream, session_id="s1", turn_id="t1",
            user_text="go", approval=broker,
        )
        consumer = asyncio.create_task(answer_every_question(stream, broker, hold=0.4))
        outcome = await asyncio.wait_for(runner.run(), WAIT_S)
        await asyncio.wait_for(consumer, WAIT_S)
        return outcome

    outcome = asyncio.run(drive())

    observations = [m for m in outcome.result.messages if m.role is Role.TOOL]
    assert observations[0].is_error
    assert "timed out" in observations[0].content


# ---- trap 2: contextvars are per Task ----------------------------------


def test_two_exchanges_from_one_coroutine_keep_their_channels_apart(tmp_path):
    """Q4.5's defect, which looks exactly like a correct diff.

    Both runners are constructed in *this* coroutine and then run
    concurrently. Binding the tool context at construction time would let
    the second binding win and send one session's question to the other
    session's prompt; binding it inside each runner's own Task — which is
    where :meth:`TurnRunner.run` does it — keeps them apart.
    """
    # One app per session: a scripted provider counts its own calls, and
    # two sessions sharing one would have the second read the first's
    # reply — which is a property of the double, not of the layer.
    apps = [
        make_app(
            tmp_path,
            Scripted(calling("ask"), Message(role=Role.ASSISTANT, content="done")),
            tools=[Asking("ask")],
        )
        for _ in (1, 2)
    ]

    async def drive():
        streams, brokers, runners = [], [], []
        for index in (1, 2):
            stream = TurnStream(f"s{index}", f"t{index}")
            broker = ApprovalBroker(stream)
            streams.append(stream)
            brokers.append(broker)
            runners.append(
                TurnRunner(
                    apps[index - 1],
                    stream,
                    session_id=f"s{index}",
                    turn_id=f"t{index}",
                    user_text="go",
                    approval=broker,
                )
            )
        consumers = [
            asyncio.create_task(answer_every_question(stream, broker, hold=0.02))
            for stream, broker in zip(streams, brokers)
        ]
        await asyncio.wait_for(
            asyncio.gather(*(runner.run() for runner in runners)), WAIT_S
        )
        answered = await asyncio.wait_for(asyncio.gather(*consumers), WAIT_S)
        return streams, answered

    streams, answered = asyncio.run(drive())

    for index, (stream, ids) in enumerate(zip(streams, answered), start=1):
        assert len(ids) == 1, f"session {index} answered {len(ids)} questions"
        assert all(request_id.startswith(f"t{index}#") for request_id in ids)
        asked = [
            frame
            for frame in stream.retained()
            if frame.type is TurnEventType.APPROVAL_REQUIRED
        ]
        assert len(asked) == 1


def test_the_turn_facts_reach_the_tools(tmp_path):
    """J3: session-level values, with this exchange's identity over them."""
    app = make_app(tmp_path, Scripted())
    with runner_for(app, values={"chat_id": "c-7", "turn_id": "stale"}) as runner:
        facts = runner.turn_values()

    assert facts["chat_id"] == "c-7"
    assert facts["turn_id"] == "t1"
    assert facts["session_id"] == "s1"


# ---- Q20: progress has a landing place ---------------------------------


def test_a_tool_reporting_progress_produces_a_frame(tmp_path):
    app = make_app(
        tmp_path,
        Scripted(calling("report"), Message(role=Role.ASSISTANT, content="done")),
        tools=[Reporting()],
    )

    async def drive():
        with runner_for(app) as runner:
            await asyncio.wait_for(runner.run(), WAIT_S)
            return runner._stream

    updates = [
        frame
        for frame in asyncio.run(drive()).retained()
        if frame.type is TurnEventType.PROGRESS
    ]

    assert len(updates) == 1
    assert updates[0].progress.message == "halfway"
    assert updates[0].progress.fraction == 0.5


def test_a_progress_sink_that_raises_does_not_fail_the_tool(tmp_path):
    """Trap 8, whose sink **this** layer writes.

    ``tools/context.py`` already treats a raising sink as no progress at
    all, and the plan says the reason in one line: the sink that raises
    is the one on this side of the seam — an SSE connection the browser
    closed, a chat edit that hit a rate limit. Letting that escape turns
    a finished tool's work into ``tool 'report' raised RuntimeError`` and
    hands a Surface transport fault to a model that will try to fix the
    tool.

    The obligation is therefore on ``report_progress``'s contract rather
    than on this layer's sink, and it is checked from this layer because
    nothing else here ever exercises the failing branch: the whole
    ``tests/entry/`` suite had no test that made a sink raise at all.

    ``except Exception`` and never ``BaseException``, at both ends:
    :exc:`asyncio.CancelledError` is a ``BaseException`` and is how a
    cancelled exchange stops, so a sink that swallowed it would make
    every exchange uncancellable while a tool was reporting.
    """

    class Brittle(TurnStream):
        """A stream whose fan-out fails the way a closed connection does."""

        def publish(self, event) -> None:
            if event is not None and event.type is TurnEventType.PROGRESS:
                raise RuntimeError("the websocket closed")
            super().publish(event)

    tool = Reporting()
    app = make_app(
        tmp_path,
        Scripted(calling("report"), Message(role=Role.ASSISTANT, content="done")),
        tools=[tool],
    )

    async def drive():
        stream = Brittle("s1", "t1")
        runner = TurnRunner(
            app,
            stream,
            session_id="s1",
            turn_id="t1",
            user_text="hi",
            approval=ApprovalBroker(stream, timeout_s=None),
        )
        outcome = await asyncio.wait_for(runner.run(), WAIT_S)
        return runner, outcome

    runner, outcome = asyncio.run(drive())

    assert runner.terminal == "converged"
    assert tool.delivered is False, "the tool was told nobody heard"
    observations = [
        message.content
        for message in outcome.result.messages
        if message.role is Role.TOOL
    ]
    assert observations == ["reported"]


def test_a_cancellation_is_never_swallowed_by_the_progress_sink(tmp_path):
    """The limit of the rule above, stated the tightening way.

    ``BaseException`` covers :exc:`asyncio.CancelledError`, and a sink
    that caught it — or a ``report_progress`` that did — would make an
    exchange uncancellable for as long as a tool kept reporting, which is
    exactly the long-running tool a user is most likely to interrupt.
    """
    source = pathlib.Path("omicsclaw/entry/stream.py").read_text(encoding="utf-8")

    assert "except Exception:" in source
    assert "except BaseException" not in source
