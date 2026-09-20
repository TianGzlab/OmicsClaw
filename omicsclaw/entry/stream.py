"""``omicsclaw/entry`` — one exchange's event truth, observable more than once.

Plan 0031 Q14. The drafted design had a single ``TurnHandle`` that was the
exchange's identity *and* its only consumer *and* the approval entry point.
Two of the three Surfaces break that shape immediately:

- **Desktop.** An SSE reconnect is a *new HTTP request*. It cannot be
  handed the iterator the previous request was holding, and the frames
  that request already consumed are gone.
- **Channel.** A failed IM delivery is retried, which means replaying from
  a cursor.

So identity and observation are separated here: one :class:`TurnStream`
per exchange, any number of :class:`TurnObservation` over it, each with
its own cursor. The vocabulary is deliberately the deleted control
plane's — ``sequence``, a bounded ring, ``cursor_evicted``,
``EventObserverDetached`` — because that code had already solved
cross-process streaming delivery, and a rebuild that renamed the concepts
would have had to re-derive them (``git show
HEAD:omicsclaw/control/event_hub.py``).

**What is new, and why** — three departures from that implementation, each
because the old behaviour has a failure mode this layer must not inherit:

1. *A slow observer is no longer detached.* The old hub dropped an
   observer whose queue filled up (``_DETACHED``). Here the **droppable**
   types are discarded instead and the observer is told, because a Desktop
   client on a slow link should lose text tokens, not the approval prompt
   that its user is expected to answer.
2. *A gap does not throw the retained suffix away.* The old hub skipped
   replay entirely on a gap, on the grounds that the retained suffix was
   incomplete. Once a ``GAP`` frame names the hole the suffix is no longer
   ambiguous, and discarding frames the process is still holding buys
   nothing.
3. *A cursor past the end is not an error.* ``cursor_ahead`` made sense
   against a durable log. Against a live in-process stream it just means
   "caught up", so the cursor is clamped and no gap is reported.

**Concurrency: Tasks, not threads.**
:meth:`TurnStream.publish` is safe between Tasks of **one** event loop and
is *not* thread-safe — neither ``asyncio.Queue`` nor a ``deque`` plus an
``asyncio.Event`` is, whatever the reference harness's goroutine-safe
``p.Send`` may suggest (plan 0031 trap 10). A callback running on a vendor
SDK's own thread — the normal case on the Channel Surface — must go
through :meth:`TurnStream.publish_threadsafe`, which is the
``loop.call_soon_threadsafe`` hop spelled out.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from typing import Final

from omicsclaw.entry.events import TurnEvent, TurnEventType, is_droppable

DEFAULT_RING_SIZE: Final = 2048
"""Frames retained per exchange for replay, when no config says otherwise.

``AppConfig.delta_ring_size`` (plan 0031 §3.2) is the authoritative knob —
a deployment sets it there and the registry passes it in; this constant is
only what a stream built without a config gets. A test pins the two equal
so the pair cannot drift apart silently.

It bounds *retention*, and retention is dominated by text deltas: control
frames are O(tool calls per model call) and ``AppConfig.max_turns`` is 50,
so an exchange would need ~40 control frames per model call before they
alone filled this ring.
"""

DEFAULT_OBSERVER_QUEUE: Final = 64
"""Frames one observer may fall behind before deltas start being dropped.

``subscriber_queue_size`` from the deleted hub
(``HEAD:omicsclaw/control/event_hub.py``), kept because that number was
in production against the same Desktop client. Note that the Desktop SSE
writer has its own, much tighter bound downstream —
``CHAT_SSE_QUEUE_MAX_ITEMS = 8`` in ``surfaces/desktop/_chat_sse.py`` —
so this is the slack before *this* layer starts discarding, not the
slack before the wire does.
"""

DEFAULT_MAX_OBSERVERS: Final = 16
"""Concurrent observers of one exchange. ``max_subscribers_per_turn``
from the deleted hub, unchanged."""


class ObserverCapacityError(RuntimeError):
    """Too many concurrent observers of one exchange.

    Successor to the deleted ``EventHubCapacityError``; renamed because
    there is no hub here — a stream belongs to one exchange and is
    created with it — and a name that described a component this package
    does not have would be the sort of confident wrong sentence plan 0031
    §8.6 aims its second reviewer at.
    """


class EventObserverDetached(RuntimeError):
    """This observation was forcibly detached and cannot be resumed.

    Name kept verbatim from the deleted control plane, which the Desktop
    Surface still imports (plan 0031 Q23, family ①). Raised only when an
    observation's own buffer raised while being offered a frame: a broken
    observer is detached rather than allowed to propagate into the
    producer, because observer failure is never execution authority.
    """


class TurnStream:
    """Every frame of one exchange, plus who is currently watching.

    Created by the turn kernel, one per exchange.
    :meth:`publish` **never blocks and never raises** — it is called from
    a ``finally`` block that must reach ``EXCHANGE_END`` however the
    exchange ended (trap 1b), so an exception escaping it would be the
    exact failure the terminal frame exists to prevent.

    Task-safe within one event loop; **not thread-safe**. Cross-thread
    producers must use :meth:`publish_threadsafe`, which is the
    ``loop.call_soon_threadsafe`` hop (trap 10).
    """

    __slots__ = (
        "_latest",
        "_loop",
        "_next_seq",
        "_observer_queue_size",
        "_observers",
        "_max_observers",
        "_on_observer_change",
        "_ring",
        "_sealed",
        "session_id",
        "turn_id",
    )

    def __init__(
        self,
        session_id: str = "",
        turn_id: str = "",
        *,
        ring_size: int = DEFAULT_RING_SIZE,
        observer_queue_size: int = DEFAULT_OBSERVER_QUEUE,
        max_observers: int = DEFAULT_MAX_OBSERVERS,
        on_observer_change: Callable[[int], None] | None = None,
    ) -> None:
        """``on_observer_change`` is the "last observer left" seam (trap 9).

        Cancelling an exchange because nobody is watching any more is the
        registry's decision, not this object's, and a grace period cannot
        be started by polling :meth:`observer_count`. So the count is
        published here and what to do about it stays upstairs — a browser
        refresh must not kill an eight-minute exchange.
        """
        for name, value in (
            ("ring_size", ring_size),
            ("observer_queue_size", observer_queue_size),
            ("max_observers", max_observers),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.session_id = session_id
        self.turn_id = turn_id
        self._ring: deque[TurnEvent] = deque(maxlen=ring_size)
        self._observer_queue_size = observer_queue_size
        self._max_observers = max_observers
        self._on_observer_change = on_observer_change
        self._observers: list[TurnObservation] = []
        self._next_seq = 1
        self._latest = 0
        self._sealed = False
        self._loop: asyncio.AbstractEventLoop | None = _running_loop()

    # ---- producer -------------------------------------------------------

    def publish(self, event: TurnEvent | None) -> None:
        """Stamp one frame, retain it, and fan it out. Never blocks.

        Accepts ``None`` so that the turn kernel can write
        ``publish(TurnEvent.from_engine(ev))`` without first branching on
        the engine's ``DONE`` event, which has no frame (see
        :meth:`~omicsclaw.entry.events.TurnEvent.from_engine`).

        **The sequence is assigned here**, overriding whatever the caller
        put on the event. One counter in one place is what makes "1, 2,
        3, … with no holes" a property of the stream rather than of every
        producer's arithmetic, and a reconnecting client's cursor is only
        worth as much as that property. A caller that already stamped the
        right number keeps its object identity.

        **Sealing.** After ``EXCHANGE_END`` the stream ignores everything
        further, so "exactly one terminal frame" holds even if a producer
        publishes two. Late frames are dropped rather than rejected:
        consumers have already stopped iterating, so there is nobody left
        to tell.
        """
        if event is None or self._sealed:
            return
        if self._loop is None:
            self._loop = _running_loop()
        seq = self._next_seq
        stamped = event if event.seq == seq else replace(event, seq=seq)
        self._next_seq = seq + 1
        self._latest = seq
        self._ring.append(stamped)
        if stamped.type is TurnEventType.EXCHANGE_END:
            self._sealed = True
        for observation in tuple(self._observers):
            try:
                observation._offer(stamped)
            except Exception:  # pragma: no cover - a buffer bug, not a flow
                observation._detach("observation buffer failed")
                self._drop_observer(observation)

    def publish_threadsafe(self, event: TurnEvent | None) -> None:
        """Publish from a thread that is not running this stream's loop.

        The Channel Surface is the reason this exists: several vendor SDKs
        deliver callbacks on their own threads, and ``put_nowait`` on an
        ``asyncio`` primitive from there corrupts the loop's bookkeeping
        instead of failing loudly.

        Delivery is asynchronous — this returns as soon as the callback is
        scheduled — so ordering is guaranteed only among calls from the
        same thread.
        """
        loop = self._loop
        if loop is None:
            raise RuntimeError(
                "TurnStream has no bound event loop; publish once from the "
                "loop, or construct the stream inside it, before publishing "
                "from another thread"
            )
        loop.call_soon_threadsafe(self.publish, event)

    # ---- consumers ------------------------------------------------------

    def observe(self, *, after_seq: int = 0) -> TurnObservation:
        """Open one cursor over this exchange. May be called many times.

        The replay/gap decision is made **now**, not on first iteration,
        so that a frame published between ``observe()`` returning and the
        consumer's first ``__anext__`` cannot slip between the replayed
        suffix and the live tail.

        ``after_seq=0`` means "from the beginning". A cursor older than
        the retained ring yields a :attr:`~omicsclaw.entry.events.
        TurnEventType.GAP` frame first, never a silent jump in sequence
        numbers.
        """
        if not isinstance(after_seq, int) or isinstance(after_seq, bool):
            raise TypeError("after_seq must be an integer")
        if after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        if len(self._observers) >= self._max_observers:
            raise ObserverCapacityError(
                f"exchange {self.turn_id!r} already has "
                f"{self._max_observers} observers"
            )
        if self._loop is None:
            self._loop = _running_loop()

        cursor = min(after_seq, self._latest)
        retained = tuple(self._ring)
        oldest = retained[0].seq if retained else None
        pending: deque[TurnEvent] = deque()
        if oldest is not None and cursor + 1 < oldest:
            pending.append(
                TurnEvent.gap_at(
                    oldest,
                    self._latest,
                    session_id=self.session_id,
                    turn_id=self.turn_id,
                )
            )
        pending.extend(frame for frame in retained if frame.seq > cursor)

        observation = TurnObservation(
            stream=self,
            pending=pending,
            capacity=self._observer_queue_size,
        )
        self._observers.append(observation)
        self._notify_observers()
        return observation

    def observer_count(self) -> int:
        """How many observations are currently attached.

        Breaking out of an ``async for`` does **not** decrement this —
        only :meth:`TurnObservation.aclose` (or ``async with``) does. An
        object with ``__anext__`` is not a generator, so Python has no
        ``break`` hook to close it, and inventing one via ``__del__``
        would tie an exchange's lifetime to the garbage collector.
        """
        return len(self._observers)

    @property
    def latest_seq(self) -> int:
        """Highest sequence published so far; ``0`` before the first."""
        return self._latest

    @property
    def sealed(self) -> bool:
        """Whether the terminal frame has been published."""
        return self._sealed

    def retained(self) -> tuple[TurnEvent, ...]:
        """Frames still available for replay, oldest first."""
        return tuple(self._ring)

    # ---- internals ------------------------------------------------------

    def _drop_observer(self, observation: TurnObservation) -> None:
        try:
            self._observers.remove(observation)
        except ValueError:
            return
        self._notify_observers()

    def _notify_observers(self) -> None:
        callback = self._on_observer_change
        if callback is None:
            return
        try:
            callback(len(self._observers))
        except Exception:  # pragma: no cover - a listener bug, not a flow
            pass


class TurnObservation:
    """One cursor over one :class:`TurnStream`.

    Iterating yields frames in sequence order and ends after the terminal
    frame. Every discontinuity this observation suffers — from a cursor
    that fell off the retained ring, or from deltas discarded because this
    particular consumer fell behind — is announced by a ``GAP`` frame
    immediately before the next frame that *is* delivered. Sequence
    numbers therefore may jump, but never silently.

    ``aclose()`` is idempotent and detaches only this observation.
    """

    __slots__ = (
        "_capacity",
        "_closed",
        "_detached_reason",
        "_exhausted",
        "_pending",
        "_skipped",
        "_stream",
        "_wake",
    )

    def __init__(
        self,
        *,
        stream: TurnStream,
        pending: deque[TurnEvent],
        capacity: int,
    ) -> None:
        self._stream = stream
        self._pending = pending
        self._capacity = capacity
        self._wake = asyncio.Event()
        self._closed = False
        self._exhausted = False
        self._detached_reason = ""
        self._skipped = False
        if pending:
            self._wake.set()

    def __aiter__(self) -> TurnObservation:
        return self

    async def __anext__(self) -> TurnEvent:
        while True:
            if self._pending:
                frame = self._pending.popleft()
                if frame.type is TurnEventType.EXCHANGE_END:
                    self._exhausted = True
                    self._stream._drop_observer(self)
                return frame
            if self._detached_reason:
                reason = self._detached_reason
                self.close()
                raise EventObserverDetached(reason)
            if self._closed or self._exhausted or self._stream.sealed:
                self.close()
                raise StopAsyncIteration
            self._wake.clear()
            await self._wake.wait()

    async def __aenter__(self) -> TurnObservation:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Detach. Idempotent, and safe to call while not iterating."""
        self.close()

    def close(self) -> None:
        """Synchronous :meth:`aclose`, for a consumer outside a coroutine."""
        if self._closed:
            return
        self._closed = True
        self._stream._drop_observer(self)
        self._wake.set()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def detached(self) -> bool:
        """Whether this observation was forcibly detached."""
        return bool(self._detached_reason)

    # ---- internals ------------------------------------------------------

    def _offer(self, event: TurnEvent) -> None:
        """Take one frame from the producer. Never blocks, never raises.

        Under pressure the droppable types are discarded — from the *tail*
        only, so that what has already been accepted stays contiguous and
        the skipped window is always one unbroken range ending just before
        the frame that displaced it. Dropping from the middle instead
        would leave a hole that no single ``GAP`` frame could describe.

        A control frame is never discarded. If nothing droppable is left
        to evict, the buffer is allowed to exceed its bound: an exchange
        whose control frames alone overflow this buffer is pathological,
        and the alternative is losing the approval prompt a human is
        waiting to answer.
        """
        if self._closed or self._exhausted or self._detached_reason:
            return
        if len(self._pending) >= self._capacity:
            if is_droppable(event.type):
                self._skipped = True
                return
            while (
                len(self._pending) >= self._capacity
                and self._pending
                and is_droppable(self._pending[-1].type)
            ):
                self._pending.pop()
                self._skipped = True
        self._flush_gap(event.seq)
        self._pending.append(event)
        self._wake.set()

    def _flush_gap(self, next_seq: int) -> None:
        if not self._skipped:
            return
        self._skipped = False
        self._pending.append(
            TurnEvent.gap_at(
                next_seq,
                self._stream.latest_seq,
                session_id=self._stream.session_id,
                turn_id=self._stream.turn_id,
            )
        )

    def _detach(self, reason: str) -> None:
        self._detached_reason = reason
        self._wake.set()


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


__all__ = [
    "DEFAULT_MAX_OBSERVERS",
    "DEFAULT_OBSERVER_QUEUE",
    "DEFAULT_RING_SIZE",
    "EventObserverDetached",
    "ObserverCapacityError",
    "TurnObservation",
    "TurnStream",
]
