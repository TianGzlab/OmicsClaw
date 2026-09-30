"""The Desktop SSE body: every token, a resumable cursor, one ending.

Plan 0031 task D2, Q14, Q24 and traps 9 and 13. The file opens with the
defect that drove this task's design — a burst of deltas published between
two of the provider's ``await`` points, against an observer buffer sized for
a *slow* reader rather than an *unscheduled* one — because everything after
it is downstream of how that was answered.

The doubles come from ``test_turn_runner.py``: the app under test is the
real composition root over a scripted backend, so the burst these tests
publish is produced by the real engine rather than by hand.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from omicsclaw.engine.types import EngineEvent, EngineEventType
from omicsclaw.entry.desktop.turn_observation import (
    DesktopChatSSEBody,
    desktop_chat_frame,
    desktop_terminal_frames,
)
from omicsclaw.entry.desktop.interactions import DesktopInteractions
from omicsclaw.entry.desktop.server import open_chat_stream
from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.session import attach_sessions
from omicsclaw.entry.stream import DEFAULT_OBSERVER_QUEUE, TurnStream
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role, StreamChunk, StreamChunkType, Usage
from omicsclaw.tools import ApprovalRequest
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Exploding,
    Scripted,
    make_app,
)

WAIT_S = 5.0
"""Every await here is bounded by it. There is no timeout plugin on this
machine, so a body that fails to close is a hang unless the test says
otherwise itself."""

BURST = 200
"""Deltas one scripted model call emits without suspending.

Chosen to exceed :data:`~omicsclaw.entry.stream.DEFAULT_OBSERVER_QUEUE`
(64) by enough that a partial delivery is unmistakable rather than
borderline. A real backend streaming over HTTP suspends on the socket
between chunks; a buffered response handing several SSE lines out of one
TCP segment does not, which is the production shape of this test.
"""


# ---- doubles -------------------------------------------------------------


class Chatty(Scripted):
    """A backend whose answer arrives as many deltas and no suspension.

    ``Scripted`` emits one delta carrying the whole reply, which cannot
    show the defect: the buffer is only asked to hold one frame. This one
    splits the same reply into :data:`BURST` chunks and — crucially —
    never awaits anything that suspends between them, so no consumer Task
    is scheduled for the whole burst.
    """

    def __init__(self, chunks: int = BURST) -> None:
        self.chunks = chunks
        self.text = "".join(f"t{index:04d} " for index in range(chunks))
        super().__init__(Message(role=Role.ASSISTANT, content=self.text))

    async def _stream(self, messages, tools=None):
        completion = await self.generate(messages, tools)
        for index in range(self.chunks):
            yield StreamChunk(
                type=StreamChunkType.TEXT_DELTA, delta=f"t{index:04d} "
            )
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)


class Paused(Scripted):
    """A backend that holds its answer open until a test releases it.

    The exchanges in this file otherwise finish inside one scheduling slot,
    which makes "is it still running?" unanswerable. This one is genuinely
    mid-flight between :attr:`started` and :attr:`release`, which is the
    only state in which an abandonment window means anything.
    """

    def __init__(self) -> None:
        super().__init__(Message(role=Role.ASSISTANT, content="first second"))
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def _stream(self, messages, tools=None):
        completion = await self.generate(messages, tools)
        yield StreamChunk(type=StreamChunkType.TEXT_DELTA, delta="first ")
        self.started.set()
        await self.release.wait()
        yield StreamChunk(type=StreamChunkType.TEXT_DELTA, delta="second")
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)


def split_frame(frame: str) -> tuple[int | None, dict]:
    """One rendered SSE frame: its ``id:`` if it has one, and the object
    the client parses.

    Asserts the invariants ``OmicsClaw-App/src/app/api/chat/route.ts``
    depends on: at most one ``id: <n>`` line, then exactly one ``data: ``
    line, and the object it carries has exactly the two keys ``type`` and
    ``data``.
    """
    assert frame.endswith("\n\n"), frame[-10:]
    lines = frame[:-2].split("\n")
    event_id: int | None = None
    if lines[0].startswith("id: "):
        event_id = int(lines[0][len("id: ") :])
        lines = lines[1:]
    assert len(lines) == 1 and lines[0].startswith("data: "), frame[:60]
    payload = json.loads(lines[0][len("data: ") :])
    assert sorted(payload) == ["data", "type"], sorted(payload)
    return event_id, payload


def decode(frame: str) -> dict:
    """The object a rendered SSE frame carries (see :func:`split_frame`)."""
    return split_frame(frame)[1]


def id_of(frame: str) -> int | None:
    return split_frame(frame)[0]


def text_of(frames: list[str]) -> str:
    return "".join(f["data"] for f in map(decode, frames) if f["type"] == "text")


def types_of(frames: list[str]) -> list[str]:
    return [decode(frame)["type"] for frame in frames]


def a_delta(index: int) -> TurnEvent:
    return TurnEvent(
        type=TurnEventType.TEXT_DELTA,
        seq=0,
        session_id="s",
        turn_id="t",
        engine=EngineEvent(
            type=EngineEventType.TEXT_DELTA, delta=f"t{index:04d} ", turn=1
        ),
    )


async def drain(stream: TurnStream, observation) -> list[TurnEvent]:
    got: list[TurnEvent] = []
    async for event in observation:
        got.append(event)
    return got


# ---- the defect this task had to answer first ----------------------------


def test_an_observer_buffer_sized_for_a_slow_reader_loses_a_burst():
    """The reproduction. 200 deltas in, 64 out, and a ``GAP`` where the rest was.

    Pinned as a *mechanism*, not as a policy: nothing in the shipped
    configuration builds a stream this way any more, and this test says why
    it must not. ``publish`` fans out synchronously, so the whole burst is
    offered before any consumer Task can be scheduled — which makes "the
    consumer is behind" indistinguishable from "the consumer has not run
    yet", and the buffer discards on the first reading.
    """

    async def scenario() -> tuple[int, int, int]:
        stream = TurnStream(
            "s", "t", observer_queue_size=DEFAULT_OBSERVER_QUEUE
        )
        observation = stream.observe()
        task = asyncio.create_task(drain(stream, observation))
        await asyncio.sleep(0)
        for index in range(BURST):
            stream.publish(a_delta(index))
        stream.publish(
            TurnEvent.exchange_end("converged", session_id="s", turn_id="t")
        )
        got = await asyncio.wait_for(task, WAIT_S)
        deltas = [e for e in got if e.type is TurnEventType.TEXT_DELTA]
        gaps = [e for e in got if e.type is TurnEventType.GAP]
        return len(deltas), len(gaps), len(stream.retained())

    delivered, gaps, retained = asyncio.run(scenario())
    assert delivered < BURST
    assert delivered <= DEFAULT_OBSERVER_QUEUE
    assert gaps == 1
    # The frames were never lost by the *stream* — the ring still holds all
    # of them. They were lost by this observation, which is what makes an
    # observer bound tighter than retention a pure cost.
    assert retained == BURST + 1


def test_a_handle_sizes_an_observer_to_what_the_stream_retains():
    """The fix, at the seam where it is made.

    :class:`~omicsclaw.entry.turn.TurnHandle` derives the observer buffer
    from ``ring_size`` instead of leaving it at the stream's own default,
    so a burst no consumer could have been scheduled for is held rather
    than discarded. Both structures hold references to the same frames, so
    the tighter bound was buying one pointer per frame.

    **Mutation**: pass ``observer_queue_size=DEFAULT_OBSERVER_QUEUE``
    through here, or drop the derivation in ``TurnHandle.__init__`` ⇒ this
    fails and ``test_an_sse_body_delivers_every_token_of_a_burst`` fails
    with it.
    """

    async def scenario() -> tuple[int, int]:
        handle = TurnHandle(session_id="s", turn_id="t", ring_size=BURST * 2)
        observation = handle.observe()
        task = asyncio.create_task(drain(handle.stream, observation))
        await asyncio.sleep(0)
        for index in range(BURST):
            handle.stream.publish(a_delta(index))
        handle.stream.publish(
            TurnEvent.exchange_end("converged", session_id="s", turn_id="t")
        )
        got = await asyncio.wait_for(task, WAIT_S)
        deltas = [e for e in got if e.type is TurnEventType.TEXT_DELTA]
        gaps = [e for e in got if e.type is TurnEventType.GAP]
        return len(deltas), len(gaps)

    delivered, gaps = asyncio.run(scenario())
    assert delivered == BURST
    assert gaps == 0


def test_an_explicit_observer_bound_still_sheds_load():
    """The parameter is injectable, not merely defaulted.

    A consumer that genuinely wants to shed load — a monitor tailing an
    exchange it does not have to reproduce — asks for it, and gets the
    discard plus the ``GAP`` that announces it.
    """

    async def scenario() -> tuple[int, int]:
        handle = TurnHandle(
            session_id="s", turn_id="t", ring_size=BURST * 2, observer_queue_size=8
        )
        observation = handle.observe()
        task = asyncio.create_task(drain(handle.stream, observation))
        await asyncio.sleep(0)
        for index in range(BURST):
            handle.stream.publish(a_delta(index))
        handle.stream.publish(
            TurnEvent.exchange_end("converged", session_id="s", turn_id="t")
        )
        got = await asyncio.wait_for(task, WAIT_S)
        deltas = [e for e in got if e.type is TurnEventType.TEXT_DELTA]
        gaps = [e for e in got if e.type is TurnEventType.GAP]
        return len(deltas), len(gaps)

    delivered, gaps = asyncio.run(scenario())
    assert delivered <= 8
    assert gaps == 1


def test_a_handle_never_buffers_less_than_the_registry_configured(
    tmp_path: pathlib.Path,
):
    """``AppConfig.delta_ring_size`` is the single knob for both bounds.

    The registry passes it as ``ring_size``; the handle derives the
    observer buffer from that. A deployment that raises retention raises
    what one reader may fall behind by, and never has to discover a second
    number.
    """
    app = attach_sessions(
        make_app(tmp_path, Scripted(), tools=(), delta_ring_size=777)
    )

    async def scenario() -> int:
        handle = await app.sessions.submit("s1", "hi", source_request_id="k")
        handle.cancel()
        await asyncio.wait_for(handle.wait(), WAIT_S)
        return handle.stream._observer_queue_size

    assert asyncio.run(scenario()) == 777


# ---- the same defect, through the real route -----------------------------


def stream_app(tmp_path: pathlib.Path, provider, **overrides):
    """A real app with a session registry, as a deployment assembles one."""
    return attach_sessions(
        make_app(tmp_path, provider, tools=(), **overrides),
        abandon_grace_s=None,
    )


def document(**overrides) -> dict:
    body = {
        "ingress_schema_version": 3,
        "content": "分析这份 Visium 数据",
        "session_id": "s1",
        "source_request_id": "a" * 32,
    }
    body.update(overrides)
    return body


async def collect(stream) -> list[str]:
    frames: list[str] = []
    async with stream.body as body:
        async for frame in body:
            frames.append(frame)
    return frames


def test_an_sse_body_delivers_every_token_of_a_burst(tmp_path: pathlib.Path):
    """End to end: what the client receives equals what the model said.

    The whole value of an SSE Surface is that it is token-by-token, so a
    stream that drops tokens is wrong rather than degraded — this is the
    assertion the delta problem was solved *for*, and it goes through the
    real registry, the real turn kernel and the real engine.
    """
    app = stream_app(tmp_path, Chatty())

    async def scenario() -> list[str]:
        stream = await open_chat_stream(app, document(), keepalive_s=None)
        return await asyncio.wait_for(collect(stream), WAIT_S)

    frames = asyncio.run(scenario())
    assert text_of(frames) == Chatty().text
    assert "event_omitted" not in types_of(frames)
    assert types_of(frames)[-1] == "done"


def test_a_converged_exchange_ends_with_exactly_one_done(tmp_path: pathlib.Path):
    app = stream_app(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="ok")))

    async def scenario() -> list[str]:
        stream = await open_chat_stream(app, document(), keepalive_s=None)
        return await asyncio.wait_for(collect(stream), WAIT_S)

    kinds = types_of(asyncio.run(scenario()))
    assert kinds.count("done") == 1
    assert kinds[-1] == "done"
    assert "error" not in kinds


def test_a_failed_exchange_names_the_type_and_not_the_message(
    tmp_path: pathlib.Path,
):
    """``terminal_error_type_preserved``, and Q22 rule 1 on the same frame.

    ``Exploding`` raises ``RuntimeError("the backend fell over")``. The
    type reaches the client; the message does not, because an exception's
    text is where a fetched URL and its query string end up.

    **Mutation**: return ``str(error)`` from ``desktop_terminal_frames`` ⇒
    this fails on the substring assertion.
    """
    app = stream_app(tmp_path, Exploding())

    async def scenario() -> list[str]:
        stream = await open_chat_stream(app, document(), keepalive_s=None)
        return await asyncio.wait_for(collect(stream), WAIT_S)

    frames = asyncio.run(scenario())
    kinds = types_of(frames)
    assert kinds[-2:] == ["error", "done"]
    error = [decode(f) for f in frames if decode(f)["type"] == "error"][0]
    assert error["data"] == "RuntimeError"
    assert "fell over" not in json.dumps(frames)


def test_a_cancelled_exchange_still_closes_its_stream(tmp_path: pathlib.Path):
    """Q5b: cancellation is a terminal *value*, not a stream that stopped.

    A consumer that saw the frames merely stop could not tell cancelled
    from crashed from disconnected, and would not know whether to
    reconnect.
    """
    app = stream_app(tmp_path, Scripted())

    async def scenario() -> list[str]:
        stream = await open_chat_stream(app, document(), keepalive_s=None)
        app.sessions.handle(stream.turn_id).cancel()
        return await asyncio.wait_for(collect(stream), WAIT_S)

    kinds = types_of(asyncio.run(scenario()))
    assert kinds[-2:] == ["error", "done"]


# ---- cursor recovery and observer lifetime (Q14, trap 9) -----------------


def test_a_disconnect_detaches_one_observer_and_keeps_the_exchange(
    tmp_path: pathlib.Path,
):
    """Trap 9, in the shape that motivated it: a browser refresh.

    Leaving the ``async with`` is a disconnect. It must detach *this*
    cursor and nothing else — the exchange keeps running, because the
    alternative is that a reload kills an eight-minute deconvolution.

    **Mutation**: drop the ``await self._observation.aclose()`` from
    ``DesktopChatSSEBody.aclose`` ⇒ the observer count stays at 1, an
    exchange nobody is watching never learns it, and this fails.
    """
    app = stream_app(tmp_path, Chatty())

    async def scenario() -> tuple[int, str, int]:
        stream = await open_chat_stream(app, document(), keepalive_s=None)
        handle = app.sessions.handle(stream.turn_id)
        async with stream.body as body:
            first = await asyncio.wait_for(anext(body), WAIT_S)
        assert decode(first)["type"] == "text"
        attached_after_close = handle.stream.observer_count()
        await asyncio.wait_for(handle.wait(), WAIT_S)
        return attached_after_close, handle.terminal or "", handle.stream.latest_seq

    attached, terminal, latest = asyncio.run(scenario())
    assert attached == 0
    assert terminal == "converged"
    assert latest > BURST


def test_a_refresh_inside_the_grace_period_keeps_the_exchange_alive(
    tmp_path: pathlib.Path,
):
    """Trap 9's condition is "the *last* observer left **and** the grace
    period expired", and this is the half a naive reading loses.

    The exchange here is genuinely mid-flight — the backend is holding its
    second delta — when the only client disconnects. A reconnect inside the
    window must find it still running and still able to finish.

    **Mutation**: replace ``self._arm_timer()`` in ``TurnHandle.
    _observers_changed`` with ``self.cancel()`` — the design plan 0031 Q14
    rejected, "any iterator breaks ⇒ cancel" ⇒ this fails and no other
    test in the suite notices. Dropping the ``_cancel_timer()`` from the
    "somebody attached" branch does *not* kill it, and that is a fact
    about the implementation rather than a hole in this test:
    ``_abandoned`` re-checks :meth:`TurnStream.observer_count` before it
    cancels, so disarming on re-attach is the second of two guards.

    The reconnect is inside the window by construction, not by luck:
    detaching and re-observing both complete without suspending, so a
    ``call_later`` callback cannot be scheduled between them. The wait
    afterwards is what makes the mutation fatal — it runs the clock past
    the abandoned window while somebody is watching.
    """
    grace = 0.05
    provider = Paused()
    app = attach_sessions(
        make_app(tmp_path, provider, tools=()), abandon_grace_s=grace
    )

    async def scenario() -> tuple[str, str, str]:
        first = await open_chat_stream(app, document(), keepalive_s=None)
        handle = app.sessions.handle(first.turn_id)
        async with first.body as body:
            head = decode(await asyncio.wait_for(anext(body), WAIT_S))["data"]
            await asyncio.wait_for(provider.started.wait(), WAIT_S)
            cursor = first.body.last_seq
        assert handle.stream.observer_count() == 0

        second = await open_chat_stream(
            app, document(), after_seq=cursor, keepalive_s=None
        )
        await asyncio.sleep(grace * 4)
        assert handle.state == "running"
        provider.release.set()
        rest = await asyncio.wait_for(collect(second), WAIT_S)
        await asyncio.wait_for(handle.wait(), WAIT_S)
        return head, text_of(rest), handle.terminal or ""

    head, tail, terminal = asyncio.run(scenario())
    assert head + tail == "first second"
    assert terminal == "converged"


def test_an_abandoned_exchange_is_cancelled_once_the_grace_expires(
    tmp_path: pathlib.Path,
):
    """The other direction, or the previous test passes for a deployment
    that never cancels anything.

    Nobody reconnects, the window closes, and the exchange stops — which
    is what keeps a closed tab from holding a model call open.
    """
    provider = Paused()
    app = attach_sessions(
        make_app(tmp_path, provider, tools=()), abandon_grace_s=0.01
    )

    async def scenario() -> str:
        stream = await open_chat_stream(app, document(), keepalive_s=None)
        handle = app.sessions.handle(stream.turn_id)
        async with stream.body as body:
            await asyncio.wait_for(anext(body), WAIT_S)
            await asyncio.wait_for(provider.started.wait(), WAIT_S)
        await asyncio.wait_for(handle.wait(), WAIT_S)
        return handle.terminal or ""

    assert asyncio.run(scenario()) == "cancelled"


def test_a_reconnect_resumes_the_same_exchange_from_its_cursor(
    tmp_path: pathlib.Path,
):
    """Q14 and Q24 meeting: idempotent redelivery resolves to the same
    exchange.

    A redelivery of the same ``source_request_id`` resolves to the same
    exchange, observed from a cursor the caller carries. The desktop
    client reconnects with ``resume: true`` instead (see
    ``test_resuming_from_the_last_id_loses_and_repeats_nothing``), because
    a redelivery that no longer finds its exchange starts a new one.

    **Mutation**: ignore ``source_request_id`` in
    ``SessionRegistry.submit`` ⇒ ``second.turn_id`` becomes a new
    exchange and the identity assertion fails.
    """
    app = stream_app(tmp_path, Chatty())
    interactions = DesktopInteractions(app)

    async def scenario() -> tuple[str, str, bool, str, str]:
        first = await open_chat_stream(
            app, document(), keepalive_s=None, interactions=interactions
        )
        async with first.body as body:
            frame = await asyncio.wait_for(anext(body), WAIT_S)
            cursor = first.body.last_seq
        assert decode(frame)["type"] == "text"

        second = await open_chat_stream(
            app,
            document(),
            after_seq=cursor,
            keepalive_s=None,
            interactions=interactions,
        )
        rest = await asyncio.wait_for(collect(second), WAIT_S)
        return (
            first.turn_id,
            second.turn_id,
            second.resumed,
            decode(frame)["data"],
            text_of(rest),
        )

    first_id, second_id, resumed, head, tail = asyncio.run(scenario())
    assert first_id == second_id
    assert resumed is True
    # Nothing between the cursor and the resumed stream was skipped, and
    # nothing before it was replayed twice.
    assert head + tail == Chatty().text


def test_a_reconnect_without_a_cursor_replays_from_the_start(
    tmp_path: pathlib.Path,
):
    """A fresh tab has no cursor, and gets everything the ring still holds.

    Duplicating what the previous connection already showed is the right
    answer for a client that lost its transcript, and the only one this
    layer can give without a durable log.
    """
    app = stream_app(tmp_path, Chatty())

    async def scenario() -> str:
        first = await open_chat_stream(app, document(), keepalive_s=None)
        async with first.body as body:
            await asyncio.wait_for(anext(body), WAIT_S)
        second = await open_chat_stream(app, document(), keepalive_s=None)
        return text_of(await asyncio.wait_for(collect(second), WAIT_S))

    assert asyncio.run(scenario()) == Chatty().text


def test_two_observers_of_one_exchange_both_see_the_ending(
    tmp_path: pathlib.Path,
):
    """``observe`` is called twice over one exchange and neither starves."""
    app = stream_app(tmp_path, Chatty())

    async def scenario() -> tuple[list[str], list[str]]:
        one = await open_chat_stream(app, document(), keepalive_s=None)
        two = await open_chat_stream(app, document(), keepalive_s=None)
        assert one.turn_id == two.turn_id
        return await asyncio.wait_for(
            asyncio.gather(collect(one), collect(two)), WAIT_S
        )

    left, right = asyncio.run(scenario())
    assert text_of(left) == text_of(right) == Chatty().text
    assert types_of(left)[-1] == types_of(right)[-1] == "done"


# ---- frame projection ----------------------------------------------------


def test_a_gap_becomes_an_event_omitted_frame():
    """A hole is announced in a name the client already parses.

    ``event_omitted`` is what ``_chat_sse.py`` itself emits when a frame
    will not fit, which makes it the published way to say "something is
    missing here" — reused rather than joined by a second name meaning the
    same thing (Q24).
    """
    gap = TurnEvent.gap_at(40, 200, session_id="s", turn_id="t")
    name, data = desktop_chat_frame(gap)
    assert name == "event_omitted"
    assert data["reason"] == "cursor_evicted"
    assert (data["oldest_available"], data["latest"]) == (40, 200)


@pytest.mark.parametrize(
    "kind",
    [
        TurnEventType.EXCHANGE_START,
        TurnEventType.QUEUED,
        TurnEventType.CONTEXT,
        TurnEventType.TURN_END,
        TurnEventType.APPROVAL_SETTLED,
    ],
)
def test_an_event_with_no_frame_in_the_contract_produces_none(kind: TurnEventType):
    """Contract v2 names every frame it sends; these types have none.

    ``TURN_END`` is not a frame of its own: its usage is summed into the
    ``result`` frame the body sends before ``done``.
    """
    event = TurnEvent(type=kind, seq=1, session_id="s", turn_id="t")
    assert desktop_chat_frame(event) is None


def a_reasoning_delta(delta: str) -> TurnEvent:
    return TurnEvent(
        type=TurnEventType.REASONING_DELTA,
        seq=3,
        session_id="s",
        turn_id="t",
        engine=EngineEvent(type=EngineEventType.REASONING_DELTA, delta=delta, turn=1),
    )


def test_a_reasoning_delta_becomes_a_thinking_frame():
    """v2 sends reasoning as ``thinking``, a plain-string delta like ``text``."""
    assert desktop_chat_frame(a_reasoning_delta("weighing Visium vs Xenium")) == (
        "thinking",
        "weighing Visium vs Xenium",
    )
    assert desktop_chat_frame(a_reasoning_delta("")) is None


def test_a_permission_request_frame_carries_the_v2_fields():
    """Field by field, because the client's admission check reads them all.

    ``reason_shows_call``, ``ask_every_time`` and ``can_remember`` are not
    in ``to_wire``'s approval payload; the desktop projection adds them —
    the first two from the request, ``can_remember`` from its caller
    (``False`` unless told). ``arguments`` stays the raw JSON string.
    """
    request = ApprovalRequest(
        tool_name="bash",
        arguments='{"command": "echo hi"}',
        reason="run: echo hi",
        reason_shows_call=True,
        ask_every_time=True,
    )
    event = TurnEvent.approval_required(
        request, "t" * 32 + "#1", seq=9, session_id="s1", turn_id="t" * 32
    )
    name, data = desktop_chat_frame(event)

    assert name == "permission_request"
    assert data == {
        "sequence": 9,
        "session_id": "s1",
        "turn_id": "t" * 32,
        "request_id": "t" * 32 + "#1",
        "tool_name": "bash",
        "arguments": '{"command": "echo hi"}',
        "reason": "run: echo hi",
        "risk_level": "high",
        "approval_mode": "ask",
        "reason_shows_call": True,
        "ask_every_time": True,
        "can_remember": False,
    }
    assert desktop_chat_frame(event, can_remember=True)[1]["can_remember"] is True


def a_turn_end(usage: Usage | None) -> TurnEvent:
    return TurnEvent(
        type=TurnEventType.TURN_END,
        seq=0,
        session_id="s",
        turn_id="t",
        engine=EngineEvent(type=EngineEventType.TURN_END, turn=1, usage=usage),
    )


def body_over(events: list[TurnEvent], **options) -> list[str]:
    """Publish *events* then a converged ending, and drain a body over them."""

    async def scenario() -> list[str]:
        stream = TurnStream("s", "t")
        body = DesktopChatSSEBody(stream.observe(), keepalive_s=None, **options)
        for event in events:
            stream.publish(event)
        stream.publish(
            TurnEvent.exchange_end("converged", session_id="s", turn_id="t")
        )
        frames: list[str] = []
        async with body:
            async for frame in body:
                frames.append(frame)
        return frames

    return asyncio.run(scenario())


def test_a_converged_body_sends_one_result_with_summed_usage_before_done():
    """``result.usage`` sums every model call the body saw, key by key.

    Two model calls — a tool call and the answer — is the ordinary shape of
    one exchange, and the client records one usage per exchange. The keys
    are ``to_wire``'s, including ``cache_write_tokens``.
    """
    frames = body_over(
        [
            a_turn_end(Usage(10, 2, cache_read_tokens=4, cache_write_tokens=1)),
            a_turn_end(Usage(20, 3, cache_read_tokens=5, cache_write_tokens=0)),
        ],
        provider="deepseek",
        model="deepseek-chat",
    )

    assert types_of(frames) == ["result", "done"]
    result = json.loads(decode(frames[0])["data"])
    assert result == {
        "usage": {
            "input_tokens": 30,
            "output_tokens": 5,
            "cache_read_tokens": 9,
            "cache_write_tokens": 1,
        },
        "usage_reported": True,
        "model_calls": 2,
        "provider": "deepseek",
        "model": "deepseek-chat",
    }


def test_a_call_that_reported_no_usage_is_not_counted_as_zero():
    """``usage_reported`` is true only when every observed call reported.

    A missing count and a zero count are different facts, so a partial sum
    says so rather than passing for the whole.
    """
    partial = json.loads(
        decode(body_over([a_turn_end(Usage(7, 1)), a_turn_end(None)])[0])["data"]
    )
    assert partial["usage"]["input_tokens"] == 7
    assert partial["usage_reported"] is False
    assert partial["model_calls"] == 2

    silent = json.loads(decode(body_over([a_turn_end(None)])[0])["data"])
    assert silent["usage"] is None
    assert silent["usage_reported"] is False


def test_a_cancelled_or_failed_exchange_sends_no_result():
    """``result`` means "completed"; the client marks the turn done on it."""
    for terminal in ("cancelled", "failed"):
        event = TurnEvent.exchange_end(terminal, session_id="s", turn_id="t")
        assert all(name != "result" for name, _ in desktop_terminal_frames(event))

    async def scenario() -> list[str]:
        stream = TurnStream("s", "t")
        body = DesktopChatSSEBody(stream.observe(), keepalive_s=None)
        stream.publish(a_turn_end(Usage(1, 1)))
        stream.publish(
            TurnEvent.exchange_end("cancelled", session_id="s", turn_id="t")
        )
        return [frame async for frame in body]

    assert types_of(asyncio.run(scenario())) == ["error", "done"]


class Thoughtful(Scripted):
    """A backend that reasons, answers, and reports what it cost."""

    async def _stream(self, messages, tools=None):
        completion = await self.generate(messages, tools)
        yield StreamChunk(type=StreamChunkType.REASONING_DELTA, delta="hmm ")
        yield StreamChunk(type=StreamChunkType.TEXT_DELTA, delta="ok")
        yield StreamChunk(
            type=StreamChunkType.DONE,
            message=completion.message,
            usage=Usage(input_tokens=12, output_tokens=3),
        )


def test_a_real_exchange_streams_thinking_text_result_then_done(
    tmp_path: pathlib.Path,
):
    """End to end through the registry and the engine, in wire order."""
    app = stream_app(tmp_path, Thoughtful(Message(role=Role.ASSISTANT, content="ok")))

    async def scenario() -> list[str]:
        stream = await open_chat_stream(app, document(), keepalive_s=None)
        return await asyncio.wait_for(collect(stream), WAIT_S)

    frames = asyncio.run(scenario())
    assert types_of(frames) == ["thinking", "text", "result", "done"]
    assert decode(frames[0])["data"] == "hmm "
    result = json.loads(decode(frames[2])["data"])
    assert result["usage"]["input_tokens"] == 12
    assert result["model_calls"] == 1
    assert result["provider"] == "scripted"


def test_the_terminal_projection_always_ends_in_done():
    for terminal in ("converged", "cancelled", "failed"):
        event = TurnEvent.exchange_end(terminal, session_id="s", turn_id="t")
        frames = desktop_terminal_frames(event)
        assert frames[-1] == ("done", "")
        assert sum(1 for name, _ in frames if name == "done") == 1


# ---- the heartbeat -------------------------------------------------------


def test_an_idle_stream_emits_a_keep_alive_and_keeps_waiting():
    """``server.py:3241``. Silence is not an ending.

    The interval is injected rather than waited out: the shipped 25 seconds
    is a production number, and a test that slept for it would be a test
    nobody runs.
    """

    async def scenario() -> list[str]:
        stream = TurnStream("s", "t", observer_queue_size=16)
        body = DesktopChatSSEBody(stream.observe(), keepalive_s=0.01)
        frames = [await asyncio.wait_for(anext(body), WAIT_S) for _ in range(2)]
        stream.publish(
            TurnEvent.exchange_end("converged", session_id="s", turn_id="t")
        )
        async with body:
            async for frame in body:
                frames.append(frame)
        return frames

    frames = asyncio.run(scenario())
    assert types_of(frames[:2]) == ["keep_alive", "keep_alive"]
    assert types_of(frames)[-1] == "done"


def test_a_body_opened_after_the_stream_sealed_still_ends():
    """A late cursor gets an ending rather than an open connection.

    The stream is already sealed, so this observation will never see an
    ``EXCHANGE_END`` of its own; without the ``StopAsyncIteration`` branch
    the client would hold a socket open for an exchange that finished
    before it asked.
    """

    async def scenario() -> list[str]:
        stream = TurnStream("s", "t")
        stream.publish(
            TurnEvent.exchange_end("converged", session_id="s", turn_id="t")
        )
        body = DesktopChatSSEBody(stream.observe(after_seq=99), keepalive_s=None)
        frames: list[str] = []
        async with body:
            async for frame in body:
                frames.append(frame)
        return frames

    assert types_of(asyncio.run(scenario()))[-1] == "done"


def test_leaving_the_body_early_detaches_it():
    """``async with`` is the contract, and this is what it buys.

    ``TurnObservation.__anext__`` drops itself when it yields the terminal
    frame, so the normal path needs no close; a consumer that leaves
    *early* — which is every SSE disconnect — is the leak, and the body is
    a context manager for exactly that case.
    """

    async def scenario() -> tuple[int, int]:
        stream = TurnStream("s", "t")
        body = DesktopChatSSEBody(stream.observe(), keepalive_s=None)
        stream.publish(a_delta(0))
        during = 0
        async with body:
            await asyncio.wait_for(anext(body), WAIT_S)
            during = stream.observer_count()
        return during, stream.observer_count()

    during, after = asyncio.run(scenario())
    assert (during, after) == (1, 0)


def test_the_wire_hides_credential_keys_by_the_tool_layer_s_rule():
    """The Desktop wire and the approval-card preview hide the same keys.

    The key list lives in ``omicsclaw/tools/preview.py`` so the preview can
    share it, since the tool layer may not import this one. Two things are
    pinned: the list itself, written out, so a change to it is a visible
    change to what the wire hides; and the projection still applies it, at
    depth, while leaving usage counts such as ``input_tokens`` alone.
    """
    from omicsclaw.entry.desktop.turn_observation import _wire_json_value
    from omicsclaw.tools.preview import CREDENTIAL_KEY_FAMILIES

    assert CREDENTIAL_KEY_FAMILIES == frozenset(
        {
            "accesskey",
            "accesskeyid",
            "accesstoken",
            "apikey",
            "authorization",
            "clientsecret",
            "cookie",
            "credential",
            "credentials",
            "password",
            "passwd",
            "privatekey",
            "refreshtoken",
            "secret",
            "secretaccesskey",
            "secretkey",
            "setcookie",
            "token",
        }
    )

    projected = _wire_json_value(
        {"usage": {"input_tokens": 3}, "headers": [{"X-Api-Key": "k", "ok": 1}]}
    )

    assert projected == {
        "usage": {"input_tokens": 3},
        "headers": [{"X-Api-Key": "[redacted]", "ok": 1}],
    }


def _a_compaction_record(written_back: bool):
    from omicsclaw.context.budget import Pressure
    from omicsclaw.context.compaction import CompactionRecord

    return CompactionRecord(
        pressure=Pressure.FULL,
        tokens_before=9_000,
        tokens_after=3_000 if written_back else 9_000,
        msgs_before=12,
        msgs_after=4 if written_back else 12,
        summarized=8 if written_back else 0,
        preserved_tail=3,
        written_back=written_back,
    )


class _FinishedCompaction:
    def __init__(self, record) -> None:
        self._record = record

    async def wait(self):
        from types import SimpleNamespace

        return SimpleNamespace(compaction=self._record)


def test_a_compact_body_reports_a_published_compaction_exactly_once():
    record = _a_compaction_record(written_back=True)
    frames = body_over(
        [TurnEvent.compacted(record, seq=1, session_id="s", turn_id="t")],
        compaction=_FinishedCompaction(record),
    )
    assert types_of(frames) == ["status", "result", "done"]
    status = json.loads(decode(frames[0])["data"])
    assert (status["kind"], status["written_back"]) == ("compaction", True)
    assert status["msgs_before"] - status["msgs_after"] == 8


def test_a_compact_body_reports_a_compaction_that_changed_nothing():
    frames = body_over([], compaction=_FinishedCompaction(_a_compaction_record(False)))
    assert types_of(frames) == ["status", "result", "done"]
    status = json.loads(decode(frames[0])["data"])
    assert (status["kind"], status["written_back"]) == ("compaction", False)
    assert status["turn_id"] == "t"


def test_an_ordinary_body_invents_no_compaction_report():
    assert types_of(body_over([])) == ["result", "done"]


# ---- contract v3: the id line, resume, usage per exchange ----------------


def test_a_frame_an_event_produced_carries_that_event_s_sequence_number():
    """Non-terminal frames carry ``id: <seq>``; ``TURN_END`` takes a
    number and sends nothing, so the ids skip it rather than counting
    frames. The ending (``result``, ``done``) carries none."""
    frames = body_over(
        [a_delta(0), a_turn_end(Usage(1, 1)), a_delta(1), a_reasoning_delta("hm")]
    )

    assert [(id_of(f), decode(f)["type"]) for f in frames] == [
        (1, "text"),
        (3, "text"),
        (4, "thinking"),
        (None, "result"),
        (None, "done"),
    ]


def test_the_frames_that_end_a_stream_carry_no_id():
    """``error`` and ``done`` of a cancelled exchange, the ``done`` a body
    adds when its observation ends without one, and ``keep_alive``."""

    async def cancelled() -> list[str]:
        stream = TurnStream("s", "t")
        body = DesktopChatSSEBody(stream.observe(), keepalive_s=None)
        stream.publish(a_delta(0))
        stream.publish(TurnEvent.exchange_end("cancelled", session_id="s", turn_id="t"))
        return [frame async for frame in body]

    async def late() -> list[str]:
        stream = TurnStream("s", "t")
        stream.publish(TurnEvent.exchange_end("converged", session_id="s", turn_id="t"))
        body = DesktopChatSSEBody(stream.observe(after_seq=99), keepalive_s=None)
        return [frame async for frame in body]

    async def idle() -> str:
        stream = TurnStream("s", "t")
        body = DesktopChatSSEBody(stream.observe(), keepalive_s=0.01)
        async with body:
            return await asyncio.wait_for(anext(body), WAIT_S)

    assert [(id_of(f), decode(f)["type"]) for f in asyncio.run(cancelled())] == [
        (1, "text"),
        (None, "error"),
        (None, "done"),
    ]
    assert [id_of(f) for f in asyncio.run(late())] == [None]
    keep_alive = asyncio.run(idle())
    assert (id_of(keep_alive), decode(keep_alive)["type"]) == (None, "keep_alive")


def test_an_event_omitted_frame_carries_a_cursor_that_resumes_after_the_hole():
    """A gap's id is one before the oldest event still held, so resuming
    from it asks for exactly what the gap did not eat. An oversized frame
    keeps the id of the event it replaced."""

    async def scenario() -> list[str]:
        stream = TurnStream("s", "t", ring_size=4)
        for index in range(6):
            stream.publish(a_delta(index))
        huge = TurnEvent(
            type=TurnEventType.TEXT_DELTA,
            seq=0,
            session_id="s",
            turn_id="t",
            engine=EngineEvent(
                type=EngineEventType.TEXT_DELTA, delta="x" * (5 * 1024 * 1024), turn=1
            ),
        )
        body = DesktopChatSSEBody(stream.observe(), keepalive_s=None)
        stream.publish(huge)
        stream.publish(TurnEvent.exchange_end("converged", session_id="s", turn_id="t"))
        return [frame async for frame in body]

    frames = asyncio.run(scenario())
    first_id, first = split_frame(frames[0])
    assert first["type"] == "event_omitted"
    assert first_id == 2
    assert json.loads(first["data"])["oldest_available"] == 3
    assert [id_of(f) for f in frames[1:5]] == [3, 4, 5, 6]
    oversized_id, oversized = split_frame(frames[5])
    assert (oversized_id, oversized["type"]) == (7, "event_omitted")
    assert json.loads(oversized["data"])["reason"] == "frame_too_large"


def test_resuming_from_the_last_id_loses_and_repeats_nothing(tmp_path: pathlib.Path):
    """The client's cursor is the last ``id:`` it received, not the last
    event the server read: ``last_seq`` may be ahead of what reached the
    socket, and resuming from it would lose the difference."""
    app = stream_app(tmp_path, Chatty())
    interactions = DesktopInteractions(app)

    async def scenario() -> tuple[str, list[str], bool, str, str]:
        first = await open_chat_stream(
            app, document(), keepalive_s=None, interactions=interactions
        )
        received: list[str] = []
        async with first.body as body:
            for _ in range(7):
                received.append(await asyncio.wait_for(anext(body), WAIT_S))
        cursor = id_of(received[-1])
        assert cursor is not None
        second = await open_chat_stream(
            app,
            document(resume=True, content=""),
            after_seq=cursor,
            keepalive_s=None,
            interactions=interactions,
        )
        rest = await asyncio.wait_for(collect(second), WAIT_S)
        return first.turn_id, rest, second.resumed, second.turn_id, text_of(received)

    first_turn, rest, resumed, second_turn, head = asyncio.run(scenario())
    assert (resumed, second_turn) == (True, first_turn)
    assert head + text_of(rest) == Chatty().text
    assert types_of(rest)[-2:] == ["result", "done"]


def test_a_resume_of_nothing_retained_starts_nothing(tmp_path: pathlib.Path):
    """A restarted backend, or an exchange aged out: 409, not a new run."""
    from omicsclaw.entry.desktop.turn_submission import DesktopIngressError

    provider = Scripted(Message(role=Role.ASSISTANT, content="ok"))
    app = stream_app(tmp_path, provider)

    async def scenario() -> None:
        await open_chat_stream(
            app, document(resume=True), keepalive_s=None
        )

    with pytest.raises(DesktopIngressError) as caught:
        asyncio.run(scenario())
    assert (caught.value.code, caught.value.status_code) == (
        "exchange_not_retained",
        409,
    )
    assert provider.calls == 0
    assert app.sessions.running() == ()


def _usage_events() -> list[TurnEvent]:
    """Two model calls around a stretch of text: seqs 1–7."""
    return [
        a_delta(0),
        a_turn_end(Usage(10, 2, cache_read_tokens=4, cache_write_tokens=1)),
        a_delta(1),
        a_delta(2),
        a_turn_end(Usage(20, 3, cache_read_tokens=5, cache_write_tokens=0)),
        a_delta(3),
    ]


def test_a_resumed_body_reports_the_usage_of_the_whole_exchange(
    tmp_path: pathlib.Path,
):
    """The first body reads past the second ``TURN_END`` but the client
    only received up to id 3; the second body reads that ``TURN_END``
    again. Each call counts once, and the sum is what one unbroken body
    reports."""
    interactions = DesktopInteractions(stream_app(tmp_path, Scripted()))
    unbroken = json.loads(decode(body_over(_usage_events())[-2])["data"])

    async def scenario() -> list[str]:
        stream = TurnStream("s", "t")
        first = DesktopChatSSEBody(
            stream.observe(), keepalive_s=None, interactions=interactions
        )
        for event in _usage_events():
            stream.publish(event)
        async with first:
            seen = [await asyncio.wait_for(anext(first), WAIT_S) for _ in range(4)]
        assert [id_of(f) for f in seen] == [1, 3, 4, 6]
        second = DesktopChatSSEBody(
            stream.observe(after_seq=3), keepalive_s=None, interactions=interactions
        )
        stream.publish(TurnEvent.exchange_end("converged", session_id="s", turn_id="t"))
        async with second:
            return [frame async for frame in second]

    rest = asyncio.run(scenario())
    assert [id_of(f) for f in rest] == [4, 6, None, None]
    resumed = json.loads(decode(rest[-2])["data"])
    assert resumed == unbroken
    assert resumed["model_calls"] == 2
    assert resumed["usage_reported"] is True


def test_a_call_that_left_the_ring_unread_makes_the_usage_unreported():
    """Nobody observed the exchange while its first ``TURN_END`` was
    pushed out of the ring. The sum is what was read; it does not claim
    to be the whole."""

    async def scenario() -> list[str]:
        stream = TurnStream("s", "t", ring_size=4)
        stream.publish(a_turn_end(Usage(7, 1)))
        for index in range(5):
            stream.publish(a_delta(index))
        body = DesktopChatSSEBody(stream.observe(), keepalive_s=None)
        stream.publish(a_turn_end(Usage(20, 3)))
        stream.publish(TurnEvent.exchange_end("converged", session_id="s", turn_id="t"))
        async with body:
            return [frame async for frame in body]

    frames = asyncio.run(scenario())
    assert decode(frames[0])["type"] == "event_omitted"
    result = json.loads(decode(frames[-2])["data"])
    assert result["usage"]["input_tokens"] == 20
    assert result["model_calls"] == 1
    assert result["usage_reported"] is False


def test_deltas_a_slow_observer_dropped_do_not_make_the_usage_unreported():
    """A ``GAP`` in the middle of a body only ever stands for deltas, so
    no model call can hide in it."""

    async def scenario() -> list[str]:
        handle = TurnHandle(
            session_id="s", turn_id="t", ring_size=BURST * 2, observer_queue_size=8
        )
        body = DesktopChatSSEBody(handle.observe(), keepalive_s=None)
        handle.stream.publish(a_turn_end(Usage(1, 1)))
        for index in range(BURST):
            handle.stream.publish(a_delta(index))
        handle.stream.publish(a_turn_end(Usage(2, 2)))
        handle.stream.publish(
            TurnEvent.exchange_end("converged", session_id="s", turn_id="t")
        )
        async with body:
            return [frame async for frame in body]

    frames = asyncio.run(scenario())
    assert "event_omitted" in types_of(frames)
    result = json.loads(decode(frames[-2])["data"])
    assert (result["model_calls"], result["usage_reported"]) == (2, True)


def _compacting_app(tmp_path: pathlib.Path):
    """A registry whose ``/compact`` really compacts a long session."""
    import dataclasses

    from omicsclaw.context import ContextBudget
    from omicsclaw.entry.session import Session
    from tests.entry.test_session import Canned  # type: ignore[import-not-found]

    app = make_app(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        tools=(),
        memory=False,
        subagents=False,
    )
    app = dataclasses.replace(
        app,
        summarizer=Canned(),
        budget=ContextBudget(
            context_tokens=9_000, reserve_output_tokens=200, reserve_tool_tokens=200
        ),
    )
    attached = attach_sessions(app, abandon_grace_s=None)
    history: list[Message] = []
    for index in range(30):
        history.append(Message.user(f"question {index} " + "q" * 300))
        history.append(Message.assistant("answer " + "a" * 300))
    return attached, Session(session_id="s1", history=tuple(history))


def test_a_resumed_compaction_does_not_report_its_status_twice(
    tmp_path: pathlib.Path,
):
    """The client received the ``status`` of a real compaction, then lost
    the connection before the ending. Resuming after its id sends the
    ending only."""
    app, session = _compacting_app(tmp_path)
    interactions = DesktopInteractions(app)

    async def scenario() -> tuple[list[str], list[str]]:
        await app.sessions._store.save(session)
        first = await open_chat_stream(
            app, document(content="/compact"), keepalive_s=None, interactions=interactions
        )
        async with first.body as body:
            head = [await asyncio.wait_for(anext(body), WAIT_S)]
        cursor = id_of(head[0])
        assert cursor is not None
        second = await open_chat_stream(
            app,
            document(resume=True),
            after_seq=cursor,
            keepalive_s=None,
            interactions=interactions,
        )
        return head, await asyncio.wait_for(collect(second), WAIT_S)

    head, rest = asyncio.run(scenario())
    assert types_of(head) == ["status"]
    assert json.loads(decode(head[0])["data"])["written_back"] is True
    assert types_of(rest) == ["result", "done"]


def test_a_resumed_compaction_that_changed_nothing_still_reports(
    tmp_path: pathlib.Path,
):
    """Nothing was compacted, so no event carried the ``status``; it is
    part of the ending, which a resume sends whole."""
    app = stream_app(tmp_path, Scripted())
    interactions = DesktopInteractions(app)

    async def scenario() -> list[str]:
        first = await open_chat_stream(
            app, document(content="/compact"), keepalive_s=None, interactions=interactions
        )
        await first.body.aclose()
        second = await open_chat_stream(
            app, document(resume=True), keepalive_s=None, interactions=interactions
        )
        return await asyncio.wait_for(collect(second), WAIT_S)

    frames = asyncio.run(scenario())
    assert types_of(frames) == ["status", "result", "done"]
    assert json.loads(decode(frames[0])["data"])["written_back"] is False


def test_an_exchange_with_every_observer_slot_taken_answers_429(
    tmp_path: pathlib.Path,
):
    from omicsclaw.entry.desktop.turn_submission import DesktopIngressError

    app = stream_app(tmp_path, Paused())
    interactions = DesktopInteractions(app)

    async def scenario() -> None:
        first = await open_chat_stream(
            app, document(), keepalive_s=None, interactions=interactions
        )
        handle = app.sessions.handle(first.turn_id)
        held = [handle.observe() for _ in range(15)]
        try:
            await open_chat_stream(
                app, document(resume=True), keepalive_s=None, interactions=interactions
            )
        finally:
            for observation in held:
                await observation.aclose()
            await first.body.aclose()
            handle.cancel()

    with pytest.raises(DesktopIngressError) as caught:
        asyncio.run(scenario())
    assert (caught.value.code, caught.value.status_code) == ("too_many_observers", 429)
