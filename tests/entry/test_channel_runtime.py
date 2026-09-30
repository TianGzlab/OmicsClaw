"""The reply pump: what it closes, what it batches, and who may answer it.

Plan 0031 task D1's two standing obligations live here, and both of them
are obligations the layers below **cannot** discharge:

1. ``TurnStream.observer_count()`` does not fall when an ``async for``
   breaks — an object with ``__anext__`` gives Python no ``break`` hook —
   so the grace period that abandons an unwatched exchange starts only if
   this surface calls ``aclose()``. Not calling it is safe in direction and
   leaks a running Task forever, which is the failure mode nobody notices
   because nothing goes wrong.
2. ``ApprovalBroker.settle`` resolves an :class:`asyncio.Future` and is
   only safe on the loop's own thread. Several vendor SDKs deliver their
   callbacks on their own. The hop is
   :meth:`ChannelRuntime.settle_approval_threadsafe`, and the test for it
   below uses a real :class:`threading.Thread` because the defect it is
   about does not exist in a single-threaded reproduction.

Every wait is bounded by :data:`WAIT_S`. A surface defect is a hang, and
this machine has no timeout plugin.
"""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib
import subprocess
import sys
import threading

import pytest

from omicsclaw.entry.approval import TIMEOUT_REASON
from omicsclaw.entry.channel.runtime import (
    DEFAULT_DELIVERED_TYPES,
    VALUE_REPLY_TARGET,
    ChannelRuntime,
)
from omicsclaw.entry.channel.delivery import DeliveryAttemptOutcome
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.ingress import InboundMessage
from omicsclaw.entry.session import attach_sessions
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role, StreamChunk, StreamChunkType
from omicsclaw.tools.context import ApprovalDecision
from tests.entry.test_channel_ingress import (  # type: ignore[import-not-found]
    OWNER,
    SpyRegistry,
    Transport,
    binding_for,
)
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Asking,
    Scripted,
    calling,
    make_app,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

WAIT_S = 5.0


class Trickling:
    """A backend that streams *count* small deltas for one reply.

    The shape that makes batching observable: one delta per token is what
    a real backend does, and a bot that forwarded each one would meet the
    platform's rate limiter inside a sentence.
    """

    def __init__(self, count: int = 200, piece: str = "0123456789") -> None:
        self.count = count
        self.piece = piece
        self.calls = 0

    @property
    def name(self) -> str:
        return "trickling"

    async def generate(self, messages, tools=None):
        self.calls += 1
        return Completion(message=Message(role=Role.ASSISTANT, content=self.whole()))

    def whole(self) -> str:
        return self.piece * self.count

    async def _stream(self, messages, tools=None):
        self.calls += 1
        for _ in range(self.count):
            yield StreamChunk(type=StreamChunkType.TEXT_DELTA, delta=self.piece)
        yield StreamChunk(
            type=StreamChunkType.DONE,
            message=Message(role=Role.ASSISTANT, content=self.whole()),
        )

    def generate_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    def bind(self, **overrides):
        return self


class AlwaysAsks:
    """Asks for one tool the first time it sees a conversation, then answers.

    Per *conversation*, decided from the messages it is handed rather than
    from a call counter: two exchanges running concurrently interleave their
    calls in an order nothing here controls, and a counter would hand one
    conversation's script step to the other.
    """

    @property
    def name(self) -> str:
        return "always-asks"

    async def generate(self, messages, tools=None):
        answered = any(message.role is Role.TOOL for message in messages)
        if answered:
            return Completion(message=Message(role=Role.ASSISTANT, content="done"))
        return Completion(message=calling("ask"))

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


class Holding(Scripted):
    """A backend that waits to be released before it answers.

    Lets a test observe an exchange *while* it is running, which is the
    only moment the questions here have an answer.
    """

    def __init__(self, *replies: Message) -> None:
        super().__init__(*replies)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, messages, tools=None):
        self.entered.set()
        await self.release.wait()
        return await super().generate(messages, tools)


def deployment(tmp_path, provider=None, **overrides):
    overrides.setdefault("approval_timeout_s", WAIT_S)
    tools = overrides.pop("tools", ())
    app = make_app(tmp_path, provider or Scripted(), tools=tools, **overrides)
    attached = attach_sessions(app)
    return dataclasses.replace(attached, sessions=SpyRegistry(attached.sessions))


def message(text="hi", *, chat="c1", request="r1", session=None) -> InboundMessage:
    return InboundMessage(
        text=text,
        session_id=session or f"feishu:{chat}",
        source_request_id=request,
        sender=OWNER,
        surface="feishu",
        values={
            VALUE_REPLY_TARGET: {"adapter": "feishu", "destination_id": chat},
        },
    )


async def started(app, transport, **kwargs) -> ChannelRuntime:
    runtime = ChannelRuntime(app, [binding_for(transport)], **kwargs)
    await runtime.start()
    return runtime


async def until(predicate, *, timeout: float = WAIT_S):
    """Poll *predicate* until it holds, bounded. Never an unbounded wait."""

    async def poll():
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout)


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# ---- obligation 1: the observation is closed ---------------------------


def test_a_finished_reply_leaves_no_observer_attached(tmp_path):
    """The ordinary path — and, measured, the one that needs no help.

    An observation detaches *itself* when it yields the terminal frame, so
    a pump that always ran to the end would pass this even without
    ``async with``: removing the context manager leaves this test green.
    It is kept because it states the end state, and the test below is the
    one that pins the obligation — the path where the pump leaves early.
    """

    async def scenario():
        transport = Transport()
        app = deployment(tmp_path)
        runtime = await started(app, transport)
        result = await runtime.submit(message())
        assert result.handle is not None
        await result.handle.wait()
        await runtime.close(WAIT_S)
        return result.handle

    handle = run(scenario())

    assert handle.stream.observer_count() == 0
    assert handle.stream.sealed


def test_a_pump_that_stops_early_detaches_while_the_exchange_runs(tmp_path):
    """The path ``async with`` exists for: leaving by ``break``.

    A transport that refuses stops the pump partway. The exchange is still
    running, so if the observation were left attached the count would stay
    at one and the "last observer left" grace period could never fire —
    which is exactly the leak nobody sees, because a leaked Task looks
    like a busy agent.
    """

    async def scenario():
        transport = Transport(DeliveryAttemptOutcome.REJECTED_PERMANENT)
        provider = Holding()
        app = deployment(tmp_path, provider)
        runtime = await started(app, transport)

        first = await runtime.submit(message(request="a"))
        await asyncio.wait_for(provider.entered.wait(), WAIT_S)
        # The second exchange is queued behind the first, so its QUEUED
        # frame is published before it runs: a deliverable frame, refused
        # by the transport, which stops its pump mid-exchange.
        second = await runtime.submit(message(request="b"))
        assert second.handle is not None
        await until(lambda: transport.sent and second.handle.state != "terminal")
        detached = second.handle.stream.observer_count()
        running = second.handle.state

        provider.release.set()
        await asyncio.wait_for(first.handle.wait(), WAIT_S)
        await asyncio.wait_for(second.handle.wait(), WAIT_S)
        await runtime.close(WAIT_S)
        return detached, running

    detached, running = run(scenario())

    assert running == "queued", "the exchange had not finished when the pump left"
    assert detached == 0, "breaking out of the loop must still detach"


def test_the_pump_opens_its_observation_with_a_context_manager(tmp_path):
    """The source-level half, because the behavioural half is indirect.

    Pinned as source rather than behaviour on purpose: the assertions above
    prove the *effect*, and this one names the mechanism, so a rewrite that
    keeps the effect by some other means has to delete this test knowingly
    rather than pass it by accident.
    """
    import inspect

    from omicsclaw.entry.channel import runtime as module

    body = inspect.getsource(module.ChannelRuntime._pump_reply)
    assert "async with handle.observe()" in body


# ---- obligation 2: settling from a vendor SDK's own thread -------------


TRAP10_DEADLINE_S = 30.0
"""How long :func:`settle_from_a_real_thread` gets before it is killed.

Plan 0031 §6 and §8.4 rule that a "must not hang" criterion is rewritten
as a fast failure, and this probe is the one place in the suite where
that cannot be done inside the process. Without the
``call_soon_threadsafe`` hop, the exchange ends up suspended on a future
that is *already resolved*: no cancellation reaches it, ``asyncio.wait_for``
never fires because the loop is not running the waiter, and the loop's own
shutdown blocks too. Measured at over 150 s for the single test and a
timeout of the whole 900 s run.

Generous rather than tight because the failure it guards is unbounded and
the success it allows is under two seconds: a number close to the real
duration would turn a loaded machine into a red suite.
"""


def settle_from_a_real_thread(workspace: str) -> None:
    """Trap 10's probe: settle from a foreign thread, or raise.

    Exported at module scope because
    :func:`test_an_approval_settled_from_a_real_thread_arrives` runs it in
    a **child process**, which is the only place a hang can be bounded
    from outside. Raises :exc:`AssertionError` on a defect and returns
    ``None`` on success; the child's exit status carries the verdict.
    """
    tmp_path = pathlib.Path(workspace)

    async def scenario():
        tool = Asking()
        provider = Scripted(
            calling("ask"), Message(role=Role.ASSISTANT, content="done")
        )
        app = deployment(tmp_path, provider, tools=(tool,))
        transport = Transport()
        runtime = await started(app, transport)

        result = await runtime.submit(message())
        assert result.handle is not None
        handle = result.handle

        # A second observer, which Q14 allows: the pump has one of its own.
        request_id = ""
        async with handle.observe() as observation:
            async for frame in observation:
                if frame.type is TurnEventType.APPROVAL_REQUIRED:
                    request_id = frame.request_id
                    break

        failures: list[BaseException] = []

        def answer() -> None:
            try:
                runtime.settle_approval_threadsafe(
                    handle.turn_id,
                    request_id,
                    ApprovalDecision(approved=True, reason="from a thread"),
                )
            except BaseException as error:  # pragma: no cover - the defect
                failures.append(error)

        worker = threading.Thread(target=answer, name="vendor-sdk-callback")
        worker.start()
        await asyncio.to_thread(worker.join, WAIT_S)

        outcome = await asyncio.wait_for(handle.wait(), WAIT_S)
        await runtime.close(WAIT_S)
        return request_id, failures, outcome, handle

    # ``debug=True`` is what makes this test able to fail. Outside debug
    # mode ``loop.call_soon`` does not check which thread called it, so a
    # ``Future.set_result`` from a foreign thread usually appears to work —
    # measured: the mutation that drops the ``call_soon_threadsafe`` hop
    # survives without this flag. In debug mode the loop refuses, which is
    # the same defect made loud enough to assert on.
    request_id, failures, outcome, handle = asyncio.run(
        asyncio.wait_for(scenario(), WAIT_S * 2), debug=True
    )

    assert request_id, "the tool never asked"
    assert failures == []
    assert handle.terminal == "converged"
    assert outcome is not None
    observations = [
        message.content
        for message in outcome.result.messages
        if message.role is Role.TOOL
    ]
    assert any("ask ran" in (text or "") for text in observations)


def test_an_approval_settled_from_a_real_thread_arrives(tmp_path):
    """Plan 0031 trap 10, and the hole this task was told to close.

    A single-threaded reproduction cannot fail, which is why the probe
    spawns a real :class:`threading.Thread`: ``Future.set_result`` from a
    foreign thread does not raise, it simply may never wake the loop, and
    the symptom is a tool that waits forever for consent that was given.

    **Run in a child process with a hard deadline**, because its own
    mutation does not turn it red — it hangs the interpreter, and a
    criterion whose failure mode is "the suite never finishes" is a
    criterion nobody runs. ``asyncio.wait_for`` cannot bound it from
    inside: the loop is not running the waiter that would fire. §8.4 asks
    for a fast failure and this is the only shape of one available, since
    there is no timeout plugin on this machine.

    :data:`TRAP10_DEADLINE_S` is therefore the assertion, and the
    mechanism test below is what fails in milliseconds on an ordinary day.
    """
    probe = (
        "import sys;"
        "from tests.entry.test_channel_runtime import settle_from_a_real_thread;"
        "settle_from_a_real_thread(sys.argv[1])"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe, str(tmp_path)],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=TRAP10_DEADLINE_S,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "the settle never arrived and the child had to be killed after "
            f"{TRAP10_DEADLINE_S}s — without the call_soon_threadsafe hop the "
            "exchange waits on an already-resolved future that no "
            "cancellation reaches"
        )
    assert result.returncode == 0, result.stdout + result.stderr


def test_settling_from_a_thread_goes_through_the_loop_hop(tmp_path):
    """The mechanism, asserted directly, because the symptom is a deadlock.

    The behavioural test above needs ``debug=True`` to make the loop refuse
    a cross-thread call. Without the hop and without that flag, measured:
    ``Future.set_result`` marks the future done and then fails to schedule
    the waiting Task's wakeup, so the exchange is suspended on a future
    that is *already resolved* — which no cancellation can reach, and which
    hangs the loop's own shutdown. A test whose only failure mode is that
    hang is a test nobody can run, so this one asserts the hop itself and
    fails in milliseconds.
    """

    async def scenario():
        app = deployment(tmp_path)
        runtime = await started(app, Transport())
        loop = asyncio.get_running_loop()
        hops: list[tuple] = []
        original = loop.call_soon_threadsafe

        def recording(callback, *args, **kwargs):
            # ``asyncio.to_thread`` uses this hop for its own completion, so
            # only the settle is counted.
            # ``==`` and not ``is``: every attribute access on a method
            # makes a fresh bound object, and they compare equal, not
            # identical.
            if callback == runtime._settle_now:
                hops.append((callback, args))
            return original(callback, *args, **kwargs)

        loop.call_soon_threadsafe = recording  # type: ignore[method-assign]
        try:
            worker = threading.Thread(
                target=runtime.settle_approval_threadsafe,
                args=("t", "r", ApprovalDecision(approved=True)),
            )
            worker.start()
            await asyncio.to_thread(worker.join, WAIT_S)
        finally:
            loop.call_soon_threadsafe = original  # type: ignore[method-assign]
        await runtime.close(WAIT_S)
        return hops

    hops = run(scenario())

    assert len(hops) == 1, "the settle must be scheduled onto the loop's thread"
    callback, args = hops[0]
    assert args == ("t", "r", ApprovalDecision(approved=True))


def test_settling_an_exchange_nobody_knows_is_a_no_op(tmp_path):
    """Plan 0031 Q18, from a thread. A person clicking a stale card.

    Raising here would put a traceback inside a vendor SDK's callback,
    where nothing catches it and the next event may not be delivered.
    """

    async def scenario():
        app = deployment(tmp_path)
        runtime = await started(app, Transport())
        failures: list[BaseException] = []

        def answer() -> None:
            try:
                runtime.settle_approval_threadsafe(
                    "no-such-turn", "no-such-request", ApprovalDecision(approved=True)
                )
            except BaseException as error:  # pragma: no cover - the defect
                failures.append(error)

        worker = threading.Thread(target=answer)
        worker.start()
        await asyncio.to_thread(worker.join, WAIT_S)
        await asyncio.sleep(0)
        await runtime.close(WAIT_S)
        return failures

    assert asyncio.run(asyncio.wait_for(scenario(), WAIT_S), debug=True) == []


def test_settling_before_the_runtime_started_says_so(tmp_path):
    """There is no loop to hop to yet, and pretending otherwise loses it."""

    async def scenario():
        app = deployment(tmp_path)
        runtime = ChannelRuntime(app, [binding_for(Transport())])
        with pytest.raises(RuntimeError, match="not started"):
            runtime.settle_approval_threadsafe(
                "t", "r", ApprovalDecision(approved=True)
            )

    run(scenario())


def test_an_unanswered_approval_is_denied_at_the_deadline(tmp_path):
    """Plan 0031 Q12: on a channel the expiry denies, and the turn goes on.

    The person may have closed the app. An approval that expired into
    consent would be a security control a silent user disables, and an
    approval that expired into an exception would lose the exchange.
    """

    async def scenario():
        tool = Asking()
        provider = Scripted(
            calling("ask"), Message(role=Role.ASSISTANT, content="done")
        )
        app = deployment(tmp_path, provider, tools=(tool,), approval_timeout_s=0.05)
        transport = Transport()
        runtime = await started(app, transport)

        result = await runtime.submit(message())
        assert result.handle is not None
        await asyncio.wait_for(result.handle.wait(), WAIT_S)
        await runtime.close(WAIT_S)
        return result.handle

    handle = run(scenario())

    settled = [
        frame
        for frame in handle.stream.retained()
        if frame.type is TurnEventType.APPROVAL_SETTLED
    ]
    assert settled, "the question was never settled"
    assert settled[0].decision is not None
    assert settled[0].decision.approved is False
    assert settled[0].decision.reason == TIMEOUT_REASON
    assert handle.terminal == "converged"


# ---- throttling --------------------------------------------------------


def test_two_hundred_deltas_become_one_complete_outbound_message(tmp_path):
    """One send, and the whole answer — which are two separate claims.

    *One send*, because an IM platform rate-limits sends and edits, and a
    message per token stops a bot inside its first sentence.

    *Complete*, and this is the one that took a measurement to get right.
    An observation buffers 64 frames and discards **deltas** under pressure
    by design (plan 0031 Q14). ``Trickling`` yields two hundred chunks
    without awaiting once, so every delta is published before this pump is
    ever scheduled, and an implementation that assembled the answer out of
    those frames delivers 640 characters and a ``[gap]`` notice instead of
    2,000 characters — measured, not predicted. The answer therefore comes
    from the exchange's trajectory, which has no gaps.
    """

    async def scenario():
        provider = Trickling(count=200)
        transport = Transport()
        app = deployment(tmp_path, provider)
        runtime = await started(app, transport)
        result = await runtime.submit(message())
        assert result.handle is not None
        await asyncio.wait_for(result.handle.wait(), WAIT_S)
        await runtime.close(WAIT_S)
        return transport, provider

    transport, provider = run(scenario())

    deltas = provider.count
    assert deltas == 200
    assert len(transport.sent) == 1, f"{deltas} deltas produced {len(transport.sent)}"
    assert transport.sent[0] == provider.whole()
    assert "[gap]" not in transport.sent[0]


def test_a_reply_longer_than_the_platform_limit_is_chunked(tmp_path):
    """Batching is not chunking: the batch still has to fit in a message."""

    async def scenario():
        provider = Trickling(count=60, piece="x" * 100)  # 6,000 characters
        transport = Transport()
        app = deployment(tmp_path, provider)
        runtime = ChannelRuntime(
            app, [binding_for(transport, text_chunk_limit=1000)]
        )
        await runtime.start()
        result = await runtime.submit(message())
        assert result.handle is not None
        await asyncio.wait_for(result.handle.wait(), WAIT_S)
        await runtime.close(WAIT_S)
        return transport

    transport = run(scenario())

    assert len(transport.sent) > 1
    assert all(len(chunk) <= 1000 for chunk in transport.sent)
    assert {request.item_id for request in transport.requests} == {
        request.item_id for request in transport.requests
    }
    assert len({request.item_id for request in transport.requests}) == len(
        transport.requests
    ), "every chunk needs its own idempotency key"


def test_tool_activity_is_not_delivered_by_default(tmp_path):
    """Surface policy, stated once and pinned.

    A message per tool call is how a chat window becomes unreadable and how
    a rate limiter is met. A deployment that wants the trace passes its own
    set; the default is the answer and anything the person must act on.
    """
    assert TurnEventType.TOOL_START not in DEFAULT_DELIVERED_TYPES
    assert TurnEventType.TOOL_RESULT not in DEFAULT_DELIVERED_TYPES
    assert TurnEventType.PROGRESS not in DEFAULT_DELIVERED_TYPES
    assert TurnEventType.TURN_END not in DEFAULT_DELIVERED_TYPES
    assert TurnEventType.APPROVAL_REQUIRED in DEFAULT_DELIVERED_TYPES
    assert TurnEventType.EXCHANGE_END in DEFAULT_DELIVERED_TYPES


def test_a_converged_exchange_does_not_announce_that_it_is_done(tmp_path):
    """"Done." is noise in a chat window; a failure is not.

    The terminal frame is fed to the renderer only when something went
    wrong, because silence after a cancellation is indistinguishable from
    an answer still being written.
    """

    async def scenario():
        transport = Transport()
        app = deployment(tmp_path)
        runtime = await started(app, transport)
        result = await runtime.submit(message())
        assert result.handle is not None
        await asyncio.wait_for(result.handle.wait(), WAIT_S)
        await runtime.close(WAIT_S)
        return transport

    transport = run(scenario())

    assert transport.sent == ["ok"]


def test_a_failed_exchange_says_so_instead_of_going_quiet(tmp_path):
    """A person who is told nothing waits; a person told "Failed" retries."""

    async def scenario():
        class Exploding(Scripted):
            async def generate(self, messages, tools=None):
                raise RuntimeError("the backend fell over")

        transport = Transport()
        app = deployment(tmp_path, Exploding())
        runtime = await started(app, transport)
        result = await runtime.submit(message())
        assert result.handle is not None
        await asyncio.wait_for(result.handle.wait(), WAIT_S)
        await runtime.close(WAIT_S)
        return transport, result.handle

    transport, handle = run(scenario())

    assert handle.terminal == "failed"
    assert transport.sent and "Failed" in transport.sent[-1]


# ---- Q6: two conversations, two pumps ----------------------------------


def test_two_conversations_get_their_own_task_and_their_own_target(tmp_path):
    """Plan 0031 Q6, at the surface that makes it the normal case.

    ``contextvars`` isolate per Task, so two exchanges driven from one
    Task would offer one person's tool call to the other person's approval
    prompt. The registry gives each exchange its own; this asserts the
    surface did not undo that by pumping both replies from one loop, and
    that neither answer went to the other chat.
    """

    async def scenario():
        transport = Transport()
        app = deployment(tmp_path)
        runtime = await started(app, transport)
        first = await runtime.submit(message(chat="alice", request="a"))
        second = await runtime.submit(message(chat="bob", request="b"))
        assert first.handle is not None and second.handle is not None
        await asyncio.wait_for(first.handle.wait(), WAIT_S)
        await asyncio.wait_for(second.handle.wait(), WAIT_S)
        await runtime.close(WAIT_S)
        return transport, first.handle, second.handle

    transport, first, second = run(scenario())

    assert first.session_id != second.session_id
    targets = [
        request.reply_target["destination_id"] for request in transport.requests
    ]
    assert sorted(targets) == ["alice", "bob"]


def test_two_approvals_on_two_conversations_do_not_cross(tmp_path):
    """The defect Q6 names, made observable.

    Each request id is namespaced by its own exchange, and each exchange's
    stream carries only its own question. A shared Task would have bound
    one approval channel for both, and the second binding would have won.
    """

    async def scenario():
        app = deployment(tmp_path, AlwaysAsks(), tools=(Asking(),))
        transport = Transport()
        runtime = await started(app, transport)

        first = await runtime.submit(message(chat="alice", request="a"))
        second = await runtime.submit(message(chat="bob", request="b"))
        assert first.handle is not None and second.handle is not None

        async def answer(handle):
            async with handle.observe() as observation:
                async for frame in observation:
                    if frame.type is TurnEventType.APPROVAL_REQUIRED:
                        handle.approvals.settle(
                            frame.request_id, ApprovalDecision(approved=True)
                        )

        await asyncio.wait_for(
            asyncio.gather(answer(first.handle), answer(second.handle)), WAIT_S
        )
        await runtime.close(WAIT_S)
        return first.handle, second.handle

    first, second = run(scenario())

    for handle in (first, second):
        asked = [
            frame.request_id
            for frame in handle.stream.retained()
            if frame.type is TurnEventType.APPROVAL_REQUIRED
        ]
        assert len(asked) == 1
        assert asked[0].startswith(handle.turn_id)
    assert first.terminal == "converged"
    assert second.terminal == "converged"


# ---- there is exactly one way in and one way out -----------------------


def test_a_channel_runtime_offers_no_way_to_run_an_exchange_without_a_reply():
    """Criterion 1, enumerated.

    ``submit(deliver_reply=False)`` was the whole of the second outbound
    path: it ran the exchange with no pump, and the adapter sent the answer
    itself through a call that classified nothing. Both halves are gone, and
    the way to keep them gone is to name them here — an argument that comes
    back would otherwise look like a convenience.
    """
    import inspect

    from omicsclaw.entry.channel import runtime as module

    assert not hasattr(module, "collect_reply")
    for name in ("submit", "submit_and_wait"):
        signature = inspect.signature(getattr(module.ChannelRuntime, name))
        assert "deliver_reply" not in signature.parameters, name


def test_a_channel_has_no_outbound_path_of_its_own():
    """The other half of criterion 1, on the base class.

    "There is no such method" is a stronger guarantee than "there is one
    and it raises", because the second still reads as a thing to call.
    ``send_command_output`` survives and is the exception this names: one
    direct provider call per chunk for a listing somebody just asked for,
    carrying no answer and classifying nothing.
    """
    from omicsclaw.entry.channel.base import Channel

    for name in (
        "send",
        "_send_chunk",
        "send_media",
        "_format_chunk",
        "process_message",
    ):
        assert not hasattr(Channel, name), name
    assert hasattr(Channel, "send_command_output")
    assert hasattr(Channel, "inbound")


# ---- shutdown ----------------------------------------------------------


def test_close_reaps_every_reply_task(tmp_path):
    """An un-awaited cancelled Task prints into a log nobody reads by then."""

    async def scenario():
        provider = Holding()
        transport = Transport()
        app = deployment(tmp_path, provider)
        runtime = await started(app, transport)
        result = await runtime.submit(message())
        await asyncio.wait_for(provider.entered.wait(), WAIT_S)
        await runtime.close(0.0)
        provider.release.set()
        return runtime, result.handle

    runtime, handle = run(scenario())

    assert runtime._replies == {}
    assert not runtime.started


def test_a_closed_runtime_admits_nothing(tmp_path):
    async def scenario():
        app = deployment(tmp_path)
        runtime = await started(app, Transport())
        await runtime.close(0.0)
        return await runtime.submit(message())

    assert run(scenario()).acceptance.code == "not_started"


# ---- trap 13: no optional dependency is imported -----------------------


_PROBE = """
import sys
import omicsclaw.entry.channel as channel

telegram = channel.get_channel_class("telegram")
feishu = channel.get_channel_class("feishu")
from omicsclaw.entry.channel.telegram import TelegramConfig
from omicsclaw.entry.channel.feishu import FeishuConfig

bot = telegram(TelegramConfig(bot_token="x"))
lark = feishu(FeishuConfig(app_id="a", app_secret="s"))
assert bot.name == "telegram" and lark.name == "feishu"
assert bot.authoritative_ingress and lark.authoritative_ingress

replaced = (
    "omicsclaw.runtime",
    "omicsclaw.control",
    "omicsclaw.providers",
    "omicsclaw.skill",
    "omicsclaw.surfaces",
)
leaked = sorted(
    name
    for name in sys.modules
    if name.split(".")[0] in ("telegram", "lark_oapi", "discord", "fastapi")
    or any(name == package or name.startswith(package + ".") for package in replaced)
)
print(leaked)
"""


def test_importing_and_constructing_a_channel_costs_no_vendor_sdk():
    """Plan 0031 trap 13 and §9-18, behaviourally, in a subprocess.

    Neither SDK is installed here, so a module-scope import of either would
    not be a slow start — it would make the whole package unimportable. The
    factories import them inside the function that builds a client, in
    plainly visible syntax, which is what makes the boundary checkable.

    The same probe asks the question a port fails: moving six thousand
    lines of adapter across and bringing one of its imports with it. The
    deleted packages are named in the list below for that reason, and the
    check is over ``sys.modules`` rather than over the source, so an import
    two levels down is caught as readily as one at the top of a file.
    """
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
