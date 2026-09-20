"""Delivery contract for ``omicsclaw.entry.stream`` (plan 0031 Q14, task C).

``pytest-asyncio`` is not installed, so every async scenario is driven by
:func:`_run`, which wraps it in ``asyncio.wait_for``. That is not a
formality: ``pytest-timeout`` is not installed either, so a test that
waits for a frame which never arrives would hang the whole suite instead
of failing it (plan 0031 §6 header).

The scenarios map onto the traps they exist for:

- trap 1b — the terminal frame reaches a consumer even when a downstream
  observer is broken, and even when the producer's body raised.
- trap 9  — an observer leaving is *observable*, and is not by itself a
  reason to cancel anything.
- trap 10 — a producer on a foreign thread has one supported route, and
  it is the ``loop.call_soon_threadsafe`` hop.
- Q14     — sequence identity, bounded retention, many cursors, and a
  ``GAP`` frame in front of every discontinuity.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest

from omicsclaw.engine.types import EngineEvent
from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.stream import (
    EventObserverDetached,
    ObserverCapacityError,
    TurnObservation,
    TurnStream,
)

_T = TypeVar("_T")

_DEADLINE = 5.0
"""Seconds one scenario may take. A hang guard, not a measurement."""

_PARK_DELAY = 0.15
"""Seconds a worker thread waits so the loop is parked in its selector
before the cross-thread frame is published. Long enough to be sure, and
the direction is safe: a spurious early wakeup makes the test lenient,
never red."""

_PROMPT_DELIVERY = 2.0
"""Seconds a cross-thread frame may take to arrive. A 13x margin over
:data:`_PARK_DELAY`, chosen so that only the missed-wakeup failure — which
waits out :data:`_DEADLINE` — can exceed it."""


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(asyncio.wait_for(coro, _DEADLINE))


def _text(delta: str = "x") -> TurnEvent:
    return TurnEvent(
        type=TurnEventType.TEXT_DELTA,
        seq=0,
        session_id="s",
        turn_id="t",
        engine=EngineEvent.text(delta, turn=1),
    )


def _tool_start(name: str = "bash") -> TurnEvent:
    from omicsclaw.schema import ToolCall

    return TurnEvent(
        type=TurnEventType.TOOL_START,
        seq=0,
        session_id="s",
        turn_id="t",
        engine=EngineEvent.tool_start(ToolCall(id="c1", name=name), turn=1),
    )


def _end(terminal: str = "converged", error: BaseException | None = None) -> TurnEvent:
    return TurnEvent.exchange_end(terminal, error=error, session_id="s", turn_id="t")


async def _drain(observation: TurnObservation) -> list[TurnEvent]:
    collected: list[TurnEvent] = []
    async for frame in observation:
        collected.append(frame)
    return collected


def _assert_no_silent_jump(frames: list[TurnEvent], *, start_after: int = 0) -> None:
    """Every step in a delivered stream is +1, or it follows a ``GAP``.

    This is the invariant the whole design exists for, and it is the one a
    weaker assertion misses: a buffer that discarded frames from the
    *front* still hands back an ascending, gap-annotated-looking sequence
    — it just quietly loses the frames a consumer had not read yet.
    """
    previous = start_after
    for frame in frames:
        if frame.type is TurnEventType.GAP:
            assert frame.gap is not None
            assert frame.seq == frame.gap[0] - 1
            previous = frame.seq
            continue
        assert frame.seq == previous + 1, f"seq {frame.seq} followed {previous}"
        previous = frame.seq


# ---- Q14: sequence identity -------------------------------------------


def test_sequence_starts_at_one_and_is_stamped_by_the_stream() -> None:
    """A producer's arithmetic is not the cursor's warranty.

    The events below are published with nonsense sequences on purpose:
    the number a reconnecting client resumes from comes from one counter
    in one place, or it comes from every producer and is worth nothing.
    """

    async def scenario() -> list[int]:
        stream = TurnStream("s", "t")
        observation = stream.observe()
        for bogus in (99, 0, -4):
            stream.publish(
                TurnEvent(
                    type=TurnEventType.TEXT_DELTA,
                    seq=bogus,
                    session_id="s",
                    turn_id="t",
                    engine=EngineEvent.text("x"),
                )
            )
        stream.publish(_end())
        return [frame.seq for frame in await _drain(observation)]

    assert _run(scenario()) == [1, 2, 3, 4]


def test_a_correctly_stamped_frame_keeps_its_identity() -> None:
    async def scenario() -> bool:
        stream = TurnStream("s", "t")
        observation = stream.observe()
        published = TurnEvent.exchange_start(seq=1, session_id="s", turn_id="t")
        stream.publish(published)
        stream.publish(_end())
        first = await observation.__anext__()
        await observation.aclose()
        return first is published

    assert _run(scenario()) is True


def test_publish_ignores_none_so_the_kernel_need_not_branch_on_done() -> None:
    async def scenario() -> int:
        stream = TurnStream("s", "t")
        stream.publish(None)
        stream.publish(_text())
        return stream.latest_seq

    assert _run(scenario()) == 1


# ---- Q14: many observers, any cursor ----------------------------------


def test_three_observers_see_the_same_exchange() -> None:
    async def scenario() -> list[list[str]]:
        stream = TurnStream("s", "t")
        observations = [stream.observe() for _ in range(3)]
        assert stream.observer_count() == 3
        stream.publish(_text("a"))
        stream.publish(_tool_start())
        stream.publish(_end())
        return [
            [frame.type.value for frame in await _drain(observation)]
            for observation in observations
        ]

    seen = _run(scenario())
    assert seen == [["text_delta", "tool_start", "exchange_end"]] * 3


def test_a_late_observer_replays_from_its_cursor() -> None:
    """The Desktop reconnect: a *new* request, an old cursor."""

    async def scenario() -> list[int]:
        stream = TurnStream("s", "t")
        for _ in range(5):
            stream.publish(_text())
        stream.publish(_end())
        late = stream.observe(after_seq=3)
        return [frame.seq for frame in await _drain(late)]

    assert _run(scenario()) == [4, 5, 6]


def test_the_same_exchange_can_be_observed_again_after_it_ended() -> None:
    async def scenario() -> tuple[list[int], list[int]]:
        stream = TurnStream("s", "t")
        stream.publish(_text())
        stream.publish(_end())
        first = [frame.seq for frame in await _drain(stream.observe())]
        second = [frame.seq for frame in await _drain(stream.observe())]
        return first, second

    first, second = _run(scenario())
    assert first == second == [1, 2]


def test_a_cursor_past_the_end_is_caught_up_not_an_error() -> None:
    async def scenario() -> list[TurnEvent]:
        stream = TurnStream("s", "t")
        stream.publish(_text())
        stream.publish(_end())
        return await _drain(stream.observe(after_seq=99))

    assert _run(scenario()) == []


def test_capacity_is_bounded_and_says_so() -> None:
    async def scenario() -> None:
        stream = TurnStream("s", "t", max_observers=2)
        stream.observe()
        stream.observe()
        with pytest.raises(ObserverCapacityError):
            stream.observe()

    _run(scenario())


# ---- Q14: bounded ring and the GAP in front of every hole --------------


def test_an_evicted_cursor_gets_a_gap_frame_and_never_a_silent_jump() -> None:
    async def scenario() -> list[TurnEvent]:
        stream = TurnStream("s", "t", ring_size=4)
        for _ in range(10):
            stream.publish(_text())
        stream.publish(_end())
        return await _drain(stream.observe(after_seq=1))

    frames = _run(scenario())
    assert frames[0].type is TurnEventType.GAP
    # 11 frames published, ring of 4 -> 8..11 survive.
    assert frames[0].gap == (8, 11)
    assert frames[0].seq == 7
    assert [frame.seq for frame in frames[1:]] == [8, 9, 10, 11]
    _assert_no_silent_jump(frames, start_after=1)


def test_a_cursor_inside_the_ring_gets_no_gap() -> None:
    async def scenario() -> list[TurnEvent]:
        stream = TurnStream("s", "t", ring_size=4)
        for _ in range(3):
            stream.publish(_text())
        stream.publish(_end())
        return await _drain(stream.observe(after_seq=2))

    frames = _run(scenario())
    assert [frame.type for frame in frames] == [
        TurnEventType.TEXT_DELTA,
        TurnEventType.EXCHANGE_END,
    ]


def test_a_slow_observer_loses_deltas_and_keeps_every_control_frame() -> None:
    """Trap 1/Q14: the split between "behind" and "wrong".

    The consumer never iterates until the producer is finished, so its
    buffer overflows by construction. What it must still receive is every
    control frame — an approval prompt it never saw is a person waiting
    for a question that was never asked.
    """

    async def scenario() -> list[TurnEvent]:
        stream = TurnStream("s", "t", observer_queue_size=4)
        observation = stream.observe()
        for _ in range(20):
            stream.publish(_text())
        stream.publish(_tool_start())
        stream.publish(_end())
        return await _drain(observation)

    frames = _run(scenario())
    types = [frame.type for frame in frames]
    assert TurnEventType.TOOL_START in types
    assert types[-1] is TurnEventType.EXCHANGE_END
    assert TurnEventType.GAP in types
    assert len(frames) < 22  # deltas really were dropped
    gap_index = types.index(TurnEventType.GAP)
    # The gap sits immediately in front of the first frame that survived
    # the drop, and its cursor is that frame's predecessor.
    assert frames[gap_index].seq == frames[gap_index + 1].seq - 1
    assert frames[gap_index].gap[0] == frames[gap_index + 1].seq
    _assert_no_silent_jump(frames)


def test_a_slow_observer_never_loses_a_control_frame_even_in_a_burst() -> None:
    async def scenario() -> list[TurnEvent]:
        stream = TurnStream("s", "t", observer_queue_size=2)
        observation = stream.observe()
        for _ in range(8):
            stream.publish(_tool_start())
        stream.publish(_end())
        return await _drain(observation)

    frames = _run(scenario())
    assert [frame.seq for frame in frames] == list(range(1, 10))
    assert TurnEventType.GAP not in [frame.type for frame in frames]


# ---- trap 1b: the terminal frame always arrives ------------------------


def test_the_terminal_frame_is_published_exactly_once() -> None:
    async def scenario() -> list[TurnEvent]:
        stream = TurnStream("s", "t")
        observation = stream.observe()
        stream.publish(_end("converged"))
        stream.publish(_end("failed"))
        stream.publish(_text())
        return await _drain(observation)

    frames = _run(scenario())
    assert [frame.type for frame in frames] == [TurnEventType.EXCHANGE_END]
    assert frames[0].terminal == "converged"


def test_a_broken_observer_cannot_stop_the_terminal_frame() -> None:
    """Trap 1b, from the direction the plan names: something downstream
    throws, and the *other* consumer must still see the exchange end."""

    class _BrokenObservation(TurnObservation):
        """Stands in for an SSE writer whose socket died mid-frame."""

        __slots__ = ()

        def _offer(self, event: TurnEvent) -> None:
            raise RuntimeError("a disconnected SSE writer")

    async def scenario() -> tuple[list[str], bool]:
        stream = TurnStream("s", "t")
        healthy = stream.observe()
        broken = _BrokenObservation(
            stream=stream, pending=deque(), capacity=4
        )
        stream._observers.append(broken)
        stream.publish(_text())
        stream.publish(_end("failed", error=ValueError("boom")))
        frames = [frame.type.value for frame in await _drain(healthy)]
        detached = broken.detached
        with pytest.raises(EventObserverDetached):
            await broken.__anext__()
        return frames, detached

    frames, detached = _run(scenario())
    assert frames[-1] == "exchange_end"
    assert detached is True


def test_a_producer_that_raises_still_seals_the_stream_from_finally() -> None:
    """The shape task B has to write, checked here from the consumer side:
    a consumer that waits on ``queue.get()`` forever is a hung REPL and an
    SSE stream that never closes."""

    async def scenario() -> TurnEvent:
        stream = TurnStream("s", "t")
        observation = stream.observe()

        async def producer() -> None:
            try:
                stream.publish(TurnEvent.exchange_start())
                raise ZeroDivisionError("the tool layer blew up")
            except ZeroDivisionError as exc:
                stream.publish(_end("failed", error=exc))

        asyncio.get_running_loop().create_task(producer())
        frames = await _drain(observation)
        return frames[-1]

    last = _run(scenario())
    assert last.type is TurnEventType.EXCHANGE_END
    assert last.terminal == "failed"
    assert isinstance(last.error, ZeroDivisionError)


def test_cancellation_is_a_terminal_value_and_not_a_failure() -> None:
    async def scenario() -> TurnEvent:
        stream = TurnStream("s", "t")
        observation = stream.observe()
        stream.publish(_end("cancelled", error=asyncio.CancelledError()))
        frames = await _drain(observation)
        return frames[-1]

    last = _run(scenario())
    assert last.terminal == "cancelled"
    assert isinstance(last.error, asyncio.CancelledError)


def test_publish_does_not_block_a_producer_with_no_observers() -> None:
    async def scenario() -> int:
        stream = TurnStream("s", "t", observer_queue_size=1)
        for _ in range(500):
            stream.publish(_text())
        stream.publish(_end())
        return stream.latest_seq

    assert _run(scenario()) == 501


# ---- trap 9: leaving is observable, and is not cancellation ------------


def test_one_observer_leaving_does_not_end_the_exchange() -> None:
    async def scenario() -> tuple[int, list[int], list[int]]:
        counts: list[int] = []
        stream = TurnStream("s", "t", on_observer_change=counts.append)
        first = stream.observe()
        second = stream.observe()
        stream.publish(_text())
        await first.aclose()
        remaining_after_leave = stream.observer_count()
        stream.publish(_text())
        stream.publish(_end())
        survivor = [frame.seq for frame in await _drain(second)]
        return remaining_after_leave, survivor, counts

    remaining, survivor, counts = _run(scenario())
    assert remaining == 1
    assert survivor == [1, 2, 3]
    assert counts[-1] == 0  # the survivor detached on the terminal frame


def test_breaking_out_of_a_loop_does_not_detach_but_aclose_does() -> None:
    """Stated rather than assumed: an object with ``__anext__`` is not a
    generator, so ``break`` has no hook. A registry that counted on
    ``break`` would free an exchange nobody released."""

    async def scenario() -> tuple[int, int]:
        stream = TurnStream("s", "t")
        observation = stream.observe()
        stream.publish(_text())
        async for _frame in observation:
            break
        after_break = stream.observer_count()
        await observation.aclose()
        return after_break, stream.observer_count()

    assert _run(scenario()) == (1, 0)


def test_aclose_is_idempotent_and_safe_before_iteration() -> None:
    async def scenario() -> int:
        stream = TurnStream("s", "t")
        observation = stream.observe()
        await observation.aclose()
        await observation.aclose()
        observation.close()
        return stream.observer_count()

    assert _run(scenario()) == 0


def test_async_with_detaches_on_the_way_out() -> None:
    async def scenario() -> int:
        stream = TurnStream("s", "t")
        async with stream.observe():
            assert stream.observer_count() == 1
        return stream.observer_count()

    assert _run(scenario()) == 0


def test_a_closed_observation_stops_instead_of_hanging() -> None:
    async def scenario() -> list[TurnEvent]:
        stream = TurnStream("s", "t")
        observation = stream.observe()
        await observation.aclose()
        return await _drain(observation)

    assert _run(scenario()) == []


# ---- trap 10: threads are not Tasks ------------------------------------


def test_a_foreign_thread_publishes_through_call_soon_threadsafe() -> None:
    """The Channel Surface's normal case: a vendor SDK callback on its own
    thread. ``asyncio`` primitives are Task-safe, not thread-safe, so the
    supported route is the explicit hop — and it has to actually work.

    Two details are what make this discriminating rather than decorative.
    The worker sleeps first, so the loop is genuinely parked in
    ``select()`` rather than merely runnable. And the arrival is *timed*:
    the naive version — calling ``publish`` straight from the thread —
    still delivers eventually, because the missed wakeup is repaired the
    next time the loop wakes for any other reason. "Arrived, with no
    ``RuntimeError``" is therefore true of both implementations; "arrived
    promptly" is true only of the hop.
    """

    async def scenario() -> tuple[list[str], float]:
        stream = TurnStream("s", "t")
        observation = stream.observe()
        errors: list[BaseException] = []

        def from_another_thread() -> None:
            time.sleep(_PARK_DELAY)
            try:
                stream.publish_threadsafe(_text("from-thread"))
                stream.publish_threadsafe(_end())
            except BaseException as exc:  # pragma: no cover - the assertion
                errors.append(exc)

        worker = threading.Thread(target=from_another_thread)
        started = time.monotonic()
        worker.start()
        frames = await _drain(observation)
        elapsed = time.monotonic() - started
        worker.join(timeout=_DEADLINE)
        assert not errors
        assert not worker.is_alive()
        return [frame.type.value for frame in frames], elapsed

    types, elapsed = _run(scenario())
    assert types == ["text_delta", "exchange_end"]
    assert elapsed < _PROMPT_DELIVERY


def test_cross_thread_publishing_needs_a_bound_loop_and_says_so() -> None:
    stream = TurnStream("s", "t")  # constructed outside any event loop
    with pytest.raises(RuntimeError, match="event loop"):
        stream.publish_threadsafe(_text())


def test_the_thread_safety_claim_is_written_down_where_it_is_read() -> None:
    """Trap 10 is a docstring defect before it is a code defect: the
    reference harness's ``p.Send`` really is goroutine-safe, so the
    tempting sentence to copy is a confident false one."""
    doc = TurnStream.__doc__ or ""
    assert "not thread-safe" in doc
    assert "call_soon_threadsafe" in doc


# ---- construction guards ------------------------------------------------


def test_the_ring_default_cannot_drift_from_the_configured_one() -> None:
    """Two copies of 2048 is one copy too many.

    ``AppConfig.delta_ring_size`` is where a deployment sets this, and the
    constant here is what a stream built without a config uses. They are
    allowed to be the same number; they are not allowed to become
    different numbers quietly.
    """
    from pathlib import Path

    from omicsclaw.entry.config import AppConfig
    from omicsclaw.entry.stream import DEFAULT_RING_SIZE

    assert DEFAULT_RING_SIZE == AppConfig(workspace=Path(".")).delta_ring_size


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ring_size": 0},
        {"observer_queue_size": -1},
        {"max_observers": True},
    ],
)
def test_sizes_must_be_positive_integers(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TurnStream("s", "t", **kwargs)


def test_a_negative_cursor_is_rejected() -> None:
    async def scenario() -> None:
        stream = TurnStream("s", "t")
        with pytest.raises(ValueError):
            stream.observe(after_seq=-1)
        with pytest.raises(TypeError):
            stream.observe(after_seq=True)

    _run(scenario())
