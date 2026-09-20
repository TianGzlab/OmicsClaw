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
from omicsclaw.entry.desktop.server import open_chat_stream
from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.session import attach_sessions
from omicsclaw.entry.stream import DEFAULT_OBSERVER_QUEUE, TurnStream
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role, StreamChunk, StreamChunkType
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


def decode(frame: str) -> dict:
    """One rendered SSE frame back to the object the client parses.

    Asserts the two invariants ``OmicsClaw-App/src/app/api/chat/route.ts``
    depends on (``:88-97``): the frame is one ``data: `` line, and the
    object it carries has exactly the two keys ``type`` and ``data``.
    """
    assert frame.startswith("data: "), frame[:40]
    assert frame.endswith("\n\n"), frame[-10:]
    payload = json.loads(frame[len("data: ") : -2])
    assert sorted(payload) == ["data", "type"], sorted(payload)
    return payload


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
    """Q14 and Q24 meeting: idempotent redelivery *is* the reconnect.

    ``/chat/stream`` frames carry no SSE ``id:`` line — the published
    client reads ``lines[0]`` and slices ``"data: "`` off it — so a
    reconnect cannot be a ``Last-Event-ID`` replay. It is a redelivery of
    the same ``source_request_id``, which resolves to the same exchange,
    plus a cursor the caller carries.

    **Mutation**: ignore ``source_request_id`` in
    ``SessionRegistry.submit`` ⇒ ``second.turn_id`` becomes a new
    exchange and the identity assertion fails.
    """
    app = stream_app(tmp_path, Chatty())

    async def scenario() -> tuple[str, str, bool, str, str]:
        first = await open_chat_stream(app, document(), keepalive_s=None)
        async with first.body as body:
            frame = await asyncio.wait_for(anext(body), WAIT_S)
            cursor = first.body.last_seq
        assert decode(frame)["type"] == "text"

        second = await open_chat_stream(
            app, document(), after_seq=cursor, keepalive_s=None
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
        TurnEventType.REASONING_DELTA,
        TurnEventType.TURN_END,
        TurnEventType.APPROVAL_SETTLED,
    ],
)
def test_an_event_with_no_published_name_produces_no_frame(kind: TurnEventType):
    """Q24's hard edge: a name this client has never seen is not minted here.

    Every type listed has a perfectly good internal meaning and no entry in
    ``route.ts``. Publishing one unilaterally would make a backend-internal
    rebuild step into a protocol change.
    """
    event = TurnEvent(type=kind, seq=1, session_id="s", turn_id="t")
    assert desktop_chat_frame(event) is None


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
