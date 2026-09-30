"""The ``/chat/stream`` SSE body: turn events projected onto Desktop frames.

Each frame is one ``data:`` line carrying a JSON object with exactly two
keys, ``type`` and ``data``, followed by a blank line. ``data`` is a
string: plain text for ``text``, ``thinking``, ``tool_output`` and the
terminal frames, and a JSON-encoded object for the rest.
:func:`~omicsclaw.entry.desktop._chat_sse.render_chat_sse_frame` keeps
every frame under 4 MiB.

A frame an event produced is preceded by an ``id:`` line holding that
event's sequence number, which is a resume cursor: a client that has
received ``id: N`` has every frame of the events numbered up to N, and a
``/chat/stream`` request with ``after_seq: N`` continues after them. The
frames that end the stream (a ``/compact`` exchange's reported
``status``, ``result``, ``error``, ``done``), the ``error`` and ``done``
a body adds when its observation ends early, and ``keep_alive`` carry no
``id:`` line. A client holds the frames without one until ``done``
arrives, and drops them if the connection breaks first, because a
resumed stream sends them again.

The frames of ``sse_schema_version`` 3:

* ``text`` / ``thinking`` — an answer delta / a reasoning delta.
* ``tool_use`` — ``tool_use_id``, ``tool_name``, ``arguments`` (the call's
  raw JSON string, byte for byte), ``turn``, and the identity keys.
* ``tool_result`` — ``tool_use_id``, ``tool_name``, ``content``,
  ``is_error``, ``elapsed_s`` (which includes any approval wait),
  ``elapsed_includes_approval_wait``, ``turn``, and the identity keys.
* ``tool_output`` — a tool's progress message.
* ``status`` — a compaction: ``kind`` is ``"compaction"``, with the
  before/after counts, ``degraded``, ``written_back`` and the identity
  keys. A ``/compact`` exchange always sends one, including when nothing
  was compacted (``written_back`` false).
* ``permission_request`` — ``request_id``, ``tool_name``, ``arguments``,
  ``reason``, ``reason_shows_call``, ``risk_level``, ``approval_mode``,
  ``ask_every_time``, ``can_remember`` (whether "always allow" can take
  effect for this call) and the identity keys. Sent only while the
  request is outstanding; a request a session grant or ``full_access``
  answers is allowed without a card.
* ``event_omitted`` — frames were lost to this cursor, or one frame was
  too large to send. Its ``id:`` is the sequence number just before the
  first event still available, or the oversized event's own.
* ``result`` — once, before ``done``, when the exchange converged:
  ``usage`` (the key-wise sum of every model call's ``input_tokens``,
  ``output_tokens``, ``cache_read_tokens`` and ``cache_write_tokens`` in
  the exchange, as read by this body and any earlier one over the same
  exchange, or ``null`` if none reported usage), ``usage_reported``
  (every call reported usage and no call can have gone unread),
  ``model_calls``, ``provider`` and ``model``.
* ``keep_alive`` — after :data:`KEEPALIVE_INTERVAL_S` of silence.
* ``error`` then ``done`` — the exchange was cancelled (``"cancelled"``) or
  failed (the exception's type name only); ``done`` alone — it converged.

The identity keys are ``sequence``, ``turn_id`` and ``session_id``.
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Any, Final

from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.render import DESKTOP_CHAT_FRAME_TYPE, to_wire
from omicsclaw.entry.stream import EventObserverDetached, TurnObservation
from omicsclaw.tools.preview import REDACTED, is_credential_key

from ._chat_sse import render_chat_sse_frame
from .interactions import TurnUsage

if TYPE_CHECKING:
    from omicsclaw.entry.approval import ApprovalBroker
    from omicsclaw.entry.turn import TurnHandle

    from .interactions import DesktopInteractions

__all__ = [
    "KEEPALIVE_INTERVAL_S",
    "DesktopChatSSEBody",
    "desktop_chat_frame",
    "desktop_terminal_frames",
]

KEEPALIVE_INTERVAL_S: Final = 25.0
"""Seconds of silence before an idle heartbeat frame.

A ``keep_alive`` frame is what stops an intermediary from closing a
connection during a ten-minute deconvolution; its data is ``""`` and the
client discards it.
"""

COMPACTION_OUTCOME_WAIT_S: Final = 10.0
"""How long a ``/compact`` body waits for the outcome it reports."""


def _wire_json_value(
    value: Any,
    *,
    path: str = "$",
    depth: int = 0,
    active_containers: set[int] | None = None,
) -> Any:
    """Project internal values to deterministic, credential-safe JSON.

    Non-finite built-in floats use explicit strings because JSON has no NaN or
    Infinity values. Arbitrary objects and non-string mapping keys fail closed;
    their ``str`` methods are never invoked on the observation wire.

    A *string* passes through untouched, which is what keeps
    ``ToolCall.arguments`` byte-exact across this seam: only mapping
    **keys** are inspected, so redaction can never rewrite the bytes a
    prompt cache and a replay are matched on.
    """

    if depth > 32:
        raise TypeError(f"Turn Event value exceeds maximum depth at {path}")
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value

    if isinstance(value, (dict, list, tuple)):
        containers = active_containers if active_containers is not None else set()
        identity = id(value)
        if identity in containers:
            raise TypeError(f"circular Turn Event value at {path}")
        containers.add(identity)
        try:
            if isinstance(value, dict):
                projected: dict[str, Any] = {}
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise TypeError(
                            f"Turn Event mapping key must be a string at {path}"
                        )
                    projected[key] = (
                        REDACTED
                        if is_credential_key(key)
                        else _wire_json_value(
                            child,
                            path=f"{path}.{key}",
                            depth=depth + 1,
                            active_containers=containers,
                        )
                    )
                return projected
            return [
                _wire_json_value(
                    child,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                    active_containers=containers,
                )
                for index, child in enumerate(value)
            ]
        finally:
            containers.remove(identity)

    raise TypeError(f"unsupported Turn Event wire value at {path}")


def _identity(event: TurnEvent) -> dict[str, Any]:
    """The three keys every payload dictionary carries.

    The frame itself cannot carry them — it is the two-key ``{type, data}``
    pair the client parses — so identity rides *inside* ``data`` for the
    frame kinds whose data is an object. A consumer correlating a
    ``tool_result`` with its ``tool_use`` across a reconnect needs the
    exchange it belongs to.
    """
    return {
        "sequence": event.seq,
        "turn_id": event.turn_id,
        "session_id": event.session_id,
    }


def desktop_chat_frame(
    event: TurnEvent, *, can_remember: bool = False
) -> tuple[str, Any] | None:
    """One frame as ``(type, data)``, or ``None`` when it has no wire name.

    ``data`` is a plain string for ``text``, ``thinking`` and
    ``tool_output``, and an object for ``tool_use``, ``tool_result``,
    ``permission_request``, ``status`` and ``event_omitted``;
    ``_chat_sse.render_chat_sse_frame`` serialises the object and keeps the
    whole frame under 4 MiB.

    ``TURN_END`` and ``EXCHANGE_END`` return ``None``: model-call usage is
    summed into the ``result`` frame and the ending is one or two frames,
    both of which :class:`DesktopChatSSEBody` and
    :func:`desktop_terminal_frames` own. ``permission_request`` is returned
    for every ``APPROVAL_REQUIRED``; whether a card is sent is the body's
    decision. *can_remember* is the card's ``can_remember``.
    """
    kind = event.type
    if kind is TurnEventType.TEXT_DELTA:
        delta = event.engine.delta if event.engine is not None else ""
        return ("text", delta) if delta else None
    if kind is TurnEventType.REASONING_DELTA:
        delta = event.engine.delta if event.engine is not None else ""
        return ("thinking", delta) if delta else None
    if kind is TurnEventType.PROGRESS:
        update = event.progress
        if update is None:
            return None
        text = update.message or update.tool_name
        return ("tool_output", text) if text else None
    if kind in (TurnEventType.TOOL_START, TurnEventType.TOOL_RESULT):
        payload = to_wire(event)
        payload.pop("schema_version", None)
        payload.pop("type", None)
        return (DESKTOP_CHAT_FRAME_TYPE[kind], _wire_json_value(payload))
    if kind is TurnEventType.APPROVAL_REQUIRED:
        payload = to_wire(event)
        payload.pop("schema_version", None)
        payload.pop("type", None)
        request = event.approval
        payload["reason_shows_call"] = (
            request.reason_shows_call if request is not None else False
        )
        payload["ask_every_time"] = (
            request.ask_every_time if request is not None else False
        )
        payload["can_remember"] = can_remember
        return (DESKTOP_CHAT_FRAME_TYPE[kind], _wire_json_value(payload))
    if kind is TurnEventType.COMPACTION:
        payload = to_wire(event)
        payload["kind"] = "compaction"
        payload.pop("schema_version", None)
        payload.pop("type", None)
        return ("status", _wire_json_value(payload))
    if kind is TurnEventType.GAP:
        oldest, latest = event.gap or (0, 0)
        return (
            "event_omitted",
            {
                "omitted_event_type": "text",
                "reason": "cursor_evicted",
                "oldest_available": oldest,
                "latest": latest,
                **_identity(event),
            },
        )
    return None


def desktop_terminal_frames(event: TurnEvent) -> tuple[tuple[str, Any], ...]:
    """The one or two frames that close a stream.

    ``done`` is always last and always has ``data == ""``. A cancelled
    exchange is preceded by ``("error", "cancelled")`` and a failed one by
    an ``error`` frame, so "the stream ended" never means three different
    things.

    The ``error`` payload is the exception's **type name only**
    (``terminal_error_type_preserved``). Its text is withheld deliberately:
    a ``web_fetch`` failure's message can contain the URL it was given,
    query string and all, and this frame is the one that crosses a process
    boundary.
    """
    if event.terminal == "converged":
        return (("done", ""),)
    if event.terminal == "cancelled":
        return (("error", "cancelled"), ("done", ""))
    error = event.error
    named = type(error).__name__ if error is not None else "unknown"
    return (("error", named), ("done", ""))


def _count_usage(ledger: TurnUsage, event: TurnEvent) -> None:
    """Record the model call a ``TURN_END`` closes in *ledger*."""
    wire = to_wire(event)
    usage = wire.get("usage")
    reported = bool(wire.get("usage_reported")) and isinstance(usage, dict)
    ledger.record_call(event.seq, usage if reported else None)


class DesktopChatSSEBody:
    """Close-safe SSE iterator over one already-open turn observation.

    Iterating yields complete SSE frames as ``str``; the caller writes them
    to the response and never has to know the frame vocabulary. The stream
    ends after the terminal ``done`` frame.

    **Closing is the whole reason this is a class.** An ``async for`` that
    a client disconnect interrupts leaves the underlying
    :class:`~omicsclaw.entry.stream.TurnObservation` attached — an object
    with ``__anext__`` is not a generator, so Python has no ``break`` hook
    that would close it — and an exchange whose observer count never falls
    back to zero never arms its abandonment timer. So this is an async
    context manager and :meth:`aclose` is idempotent.

    Detaching is **not** cancelling. A browser refresh detaches one
    observer of an exchange that may have been running for eight minutes;
    whether the exchange should then stop is the registry's decision,
    taken when the *last* observer has been gone for the grace period.
    """

    __slots__ = (
        "_approvals",
        "_closed",
        "_compaction",
        "_compaction_seen",
        "_interactions",
        "_keepalive_s",
        "_ledger",
        "_model",
        "_observation",
        "_pending",
        "_provider",
        "last_seq",
    )

    def __init__(
        self,
        observation: TurnObservation,
        *,
        keepalive_s: float | None = KEEPALIVE_INTERVAL_S,
        after_seq: int = 0,
        approvals: ApprovalBroker | None = None,
        interactions: DesktopInteractions | None = None,
        provider: str = "",
        model: str = "",
        compaction: TurnHandle | None = None,
    ) -> None:
        """*after_seq* is remembered, not applied.

        The cursor is applied by whoever called ``observe(after_seq=…)``;
        it is recorded here only so that :attr:`last_seq` is a valid resume
        point even before the first frame arrives — a client that
        reconnects and immediately disconnects again must not be told to
        resume from zero.

        *approvals* is the observed exchange's broker. With it, a
        ``permission_request`` card is sent only while its request is
        outstanding, and with *interactions* as well a session grant
        allows a request without a card (see
        :meth:`~omicsclaw.entry.desktop.interactions.DesktopInteractions.admit_approval`).
        Without it every ``APPROVAL_REQUIRED`` becomes a card.

        *provider* and *model* are reported in the ``result`` frame.
        With *interactions*, its usage comes from the exchange's shared
        :class:`~omicsclaw.entry.desktop.interactions.TurnUsage`, so a
        resumed body reports the calls an earlier body read; without it,
        from the calls this body read.

        *compaction* is the handle of the observed exchange when it is a
        ``/compact``. A compaction that changed nothing publishes no
        ``COMPACTION`` event, so when the exchange converged without one
        this body sends a ``status`` frame built from the outcome's
        record, and ``/compact`` never ends silently.
        """
        self._observation = observation
        self._keepalive_s = keepalive_s
        self._approvals = approvals
        self._interactions = interactions
        self._provider = provider
        self._model = model
        self._pending: list[str] = []
        self._closed = False
        self._ledger: TurnUsage | None = None
        self._compaction = compaction
        self._compaction_seen = False
        self.last_seq = after_seq

    async def __aenter__(self) -> DesktopChatSSEBody:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    def __aiter__(self) -> DesktopChatSSEBody:
        return self

    async def __anext__(self) -> str:
        """Buffered frames first, then one live frame, then the heartbeat.

        The order is load-bearing: the terminal paths queue their frames and
        close in the same step, so a body that checked ``_closed`` before
        ``_pending`` would swallow the ``done`` frame it had just produced —
        and a client that never sees ``done`` reconnects forever.
        """
        while True:
            if self._pending:
                return self._pending.pop(0)
            if self._closed:
                raise StopAsyncIteration
            event = await self._next_event()
            if event is None:
                if self._pending or self._closed:
                    continue
                return render_chat_sse_frame("keep_alive", "")
            ledger = self._mark_read(event)
            self.last_seq = max(self.last_seq, event.seq)
            if event.type is TurnEventType.EXCHANGE_END:
                if event.terminal == "converged":
                    report = await self._compaction_report(event)
                    if report is not None:
                        self._queue((report,))
                    self._queue((("result", self.result()),))
                self._queue(desktop_terminal_frames(event))
                await self.aclose()
                continue
            if event.type is TurnEventType.TURN_END:
                _count_usage(ledger, event)
                continue
            if event.type is TurnEventType.COMPACTION:
                self._compaction_seen = True
            if event.type is TurnEventType.APPROVAL_REQUIRED:
                if not self._shows_card(event):
                    continue
                frame = desktop_chat_frame(
                    event, can_remember=self._can_remember(event)
                )
            else:
                frame = desktop_chat_frame(event)
            if frame is None:
                continue
            return render_chat_sse_frame(*frame, event_id=event.seq)

    def result(self) -> dict[str, Any]:
        """The ``result`` frame's data, for an exchange whose last event
        is :attr:`last_seq`."""
        ledger = self._ledger if self._ledger is not None else TurnUsage()
        return {
            **ledger.result(self.last_seq),
            "provider": self._provider,
            "model": self._model,
        }

    def _mark_read(self, event: TurnEvent) -> TurnUsage:
        """Record *event* as read in the exchange's usage ledger, and
        return the ledger.

        A ``GAP`` that opens a body stands for events the ring no longer
        holds, so they stay unread. A later ``GAP`` stands for deltas this
        observer's buffer discarded; no ``TURN_END`` is ever discarded
        that way, so those count as read.
        """
        ledger = self._ledger
        first = ledger is None
        if ledger is None:
            ledger = (
                self._interactions.usage_for(event.turn_id)
                if self._interactions is not None
                else TurnUsage()
            )
            self._ledger = ledger
        if event.type is TurnEventType.GAP:
            if not first:
                ledger.cover(self.last_seq + 1, event.seq)
        else:
            ledger.cover(event.seq, event.seq)
        return ledger

    def _can_remember(self, event: TurnEvent) -> bool:
        if self._interactions is None:
            return False
        return self._interactions.can_remember(event.approval)

    async def _compaction_report(self, end: TurnEvent) -> tuple[str, Any] | None:
        """The ``status`` frame a ``/compact`` that published none is owed.

        The exchange's last event is published before its outcome is
        recorded, so this waits (briefly) for the outcome.
        """
        handle = self._compaction
        if handle is None or self._compaction_seen:
            return None
        try:
            async with asyncio.timeout(COMPACTION_OUTCOME_WAIT_S):
                outcome = await handle.wait()
        except TimeoutError:
            return None
        record = outcome.compaction if outcome is not None else None
        if record is None:
            return None
        return desktop_chat_frame(
            TurnEvent.compacted(
                record,
                seq=end.seq,
                session_id=end.session_id,
                turn_id=end.turn_id,
            )
        )

    def _shows_card(self, event: TurnEvent) -> bool:
        if self._approvals is None:
            return True
        if self._interactions is None:
            return event.request_id in self._approvals.pending()
        return self._interactions.admit_approval(event, self._approvals)

    async def _next_event(self) -> TurnEvent | None:
        """The next frame, or ``None`` for "nothing to report right now".

        ``None`` covers three endings the caller distinguishes by looking at
        :attr:`_pending` and ``_closed`` afterwards — a heartbeat tick, a
        stream that sealed without this cursor reaching the terminal frame,
        and a forcibly detached observation.

        Every other exit closes this body, including the one nobody plans
        for: ``BaseException`` covers the :exc:`asyncio.CancelledError` an
        ASGI server raises into a response body when the client goes away,
        and that is exactly the path that leaks an attached observation.
        """
        try:
            if self._keepalive_s is None:
                return await anext(self._observation)
            try:
                async with asyncio.timeout(self._keepalive_s):
                    return await anext(self._observation)
            except TimeoutError:
                return None
        except StopAsyncIteration:
            self._queue((("done", ""),))
            await self.aclose()
            return None
        except EventObserverDetached:
            self._queue((("error", "EventObserverDetached"), ("done", "")))
            await self.aclose()
            return None
        except BaseException:
            await self.aclose()
            raise

    def _queue(self, frames: tuple[tuple[str, Any], ...]) -> None:
        self._pending.extend(render_chat_sse_frame(*frame) for frame in frames)

    async def aclose(self) -> None:
        """Detach this observation. Idempotent; never cancels the exchange.

        Frames already queued survive: closing stops the *source*, and a
        terminal frame that was produced before the close is still owed to
        the consumer.
        """
        self._closed = True
        await self._observation.aclose()
