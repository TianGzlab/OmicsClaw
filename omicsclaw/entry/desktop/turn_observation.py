"""Stable V1 Desktop Adapter for authoritative Turn observation.

This Module owns only HTTP/SSE projection. Durable truth and cursor recovery
remain behind the turn kernel; internal Event class names never leak into the
wire by reflection.

Ported from ``omicsclaw/surfaces/desktop/turn_observation.py`` (plan 0031
§5.2, task D2), and the port is much smaller than the plan's "3 lines to
change" implies. What came across is
:func:`_wire_json_value` — the credential-safe, cycle-safe,
non-finite-safe JSON projector — and the close-safe iterator discipline of
``DesktopTurnSSEBody``. What could not is everything in between: the source's
seven ``pydantic`` wire models describe ``/v1/turns`` receipts
(``revision``, ``transcript_ref``, ``content_sha256``) that this rebuild has
no counterpart for, its event mapper switches over ten classes from the
deleted ``omicsclaw.runtime.agent.events``, and its constructor takes a
``ControlTurnObservation`` from the deleted ``omicsclaw.control``. Only one of
the two names the plan expected to find here — ``EventObserverDetached`` — is
in fact provided by :mod:`omicsclaw.entry.stream`; ``TurnEventFrame`` is not,
because this layer's frame carries ``seq`` and a terminal *value* rather than
``sequence``, ``emitted_at_ms`` and a terminal *flag*.

**The frame vocabulary is the external client's, not this layer's** (Q24).
``OmicsClaw-App/src/app/api/chat/route.ts:87-101`` parses each frame as a
JSON object with **exactly two keys**, ``type`` and ``data``, and that is
*all* it recognises by type — ``done`` and ``error``, the two terminal
ones. The switch over the rest is
``OmicsClaw-App/src/hooks/useSSEStream.ts:143-431``, which has a ``case``
for ``text``, ``tool_use``, ``tool_result``, ``tool_output``,
``permission_request`` and ``status``, and drops anything else at
``default:`` (``:430``) without a word.
:data:`~omicsclaw.entry.render.DESKTOP_CHAT_FRAME_TYPE` holds the five-way
part of that map.

The two-key invariant is why nothing here adds an SSE ``id:`` line, however
convenient that would have been for resuming — ``route.ts:87-90`` requires
``lines.length === 1`` and slices ``"data: "`` off ``lines[0]``, so a frame
with an ``id:`` line ahead of the data line stops being recognisable as
terminal. Resumption is therefore addressed where the published contract does
have a mechanism for it: a redelivered ``source_request_id``
(``durable_ingress_idempotency``) resolves to the same exchange, and a new
observation over it is opened at whatever cursor the caller names.

A :class:`~omicsclaw.entry.events.TurnEventType` with **no** published name
produces no frame at all. Minting one would publish a vocabulary to an
external client unilaterally, which Q24 places outside a backend-internal
rebuild step.

**One frame this layer emits has no ``case`` on the client**, and it is
recorded rather than defended: ``event_omitted``, which
:func:`desktop_chat_frame` sends for a :attr:`~omicsclaw.entry.events.
TurnEventType.GAP`. The *name* is not invented here — the ported
``_chat_sse.py:151`` already emits it for an oversized frame, which is why
it was reused instead of a second name meaning the same thing — but no
version of this client has ever read it, so a GAP currently reaches
``default:`` and disappears. That is strictly better than a silent jump in
the sequence on the backend side and strictly worse than telling the user,
and closing it is a frontend change this step cannot make alone. Whoever
takes it up should add the ``case`` and then delete this paragraph.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any, Final

from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.render import DESKTOP_CHAT_FRAME_TYPE, to_wire
from omicsclaw.entry.stream import EventObserverDetached, TurnObservation

from ._chat_sse import render_chat_sse_frame

__all__ = [
    "KEEPALIVE_INTERVAL_S",
    "DesktopChatSSEBody",
    "desktop_chat_frame",
    "desktop_terminal_frames",
]

KEEPALIVE_INTERVAL_S: Final = 25.0
"""Seconds of silence before an idle heartbeat frame.

``server.py:2249``, unchanged. A ``keep_alive`` frame is what stops an
intermediary from closing a connection during a ten-minute deconvolution;
it carries no data and the client discards it.
"""

_REDACTED = "[redacted]"
_SENSITIVE_WIRE_KEYS = frozenset(
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

    Ported unchanged from ``surfaces/desktop/turn_observation.py:59-125``.
    Note that a *string* passes through untouched, which is what keeps
    ``ToolCall.arguments`` byte-exact across this seam (plan 0031 §3.2 task
    C): only mapping **keys** are inspected, so redaction can never rewrite
    the bytes a prompt cache and a replay are matched on.
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
                    normalized_key = "".join(ch for ch in key.lower() if ch.isalnum())
                    projected[key] = (
                        _REDACTED
                        if any(
                            normalized_key == family or normalized_key.endswith(family)
                            for family in _SENSITIVE_WIRE_KEYS
                        )
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


def desktop_chat_frame(event: TurnEvent) -> tuple[str, Any] | None:
    """One frame as ``(type, data)``, or ``None`` when it has no wire name.

    ``data`` is a plain string for the frame kinds the client reads as text
    (``text``, ``tool_output``) and an object for the kinds it parses
    (``tool_use``, ``tool_result``, ``permission_request``, ``status``,
    ``event_omitted``); ``_chat_sse.render_chat_sse_frame`` serialises the
    object and keeps the whole frame under 4 MiB.

    ``EXCHANGE_END`` returns ``None`` here on purpose: it is one or two
    frames depending on how the exchange ended, which is a branch rather
    than a lookup, and :func:`desktop_terminal_frames` owns it.
    """
    kind = event.type
    if kind is TurnEventType.TEXT_DELTA:
        delta = event.engine.delta if event.engine is not None else ""
        return ("text", delta) if delta else None
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
        return (DESKTOP_CHAT_FRAME_TYPE[kind], _wire_json_value(payload))
    if kind is TurnEventType.COMPACTION:
        # ``_compaction_event_bridge.py:52-56`` is the precedent: a
        # compaction is reported to this client as a ``status`` frame whose
        # data is the compaction payload. The bridge's own
        # ``build_compaction_status_payload`` belonged to the deleted
        # ``runtime.context`` package; ``render.to_wire`` produces the same
        # counts from ``CompactionRecord``.
        payload = to_wire(event)
        payload["kind"] = "compaction"
        payload.pop("schema_version", None)
        payload.pop("type", None)
        return ("status", _wire_json_value(payload))
    if kind is TurnEventType.GAP:
        oldest, latest = event.gap or (0, 0)
        # ``event_omitted`` is a name ``_chat_sse.py:151`` already emits
        # when it cannot fit a frame, so it is reused rather than joined by
        # a second name meaning the same thing. It is **not** a name this
        # client reads: see the module docstring's last paragraph.
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

    ``done`` is always last and always has ``data == ""``, because that pair
    is literally how ``route.ts:98`` recognises a clean ending. A failed or
    cancelled exchange is preceded by an ``error`` frame, which is what the
    old handler did on a disconnect (``server.py:3276-3277``) and what keeps
    "the stream ended" from meaning three different things (Q5b).

    The ``error`` payload is the exception's **type name only**
    (``terminal_error_type_preserved``). Its text is withheld deliberately:
    a ``web_fetch`` failure's message can contain the URL it was given,
    query string and all (Q22 rule 1), and this frame is the one that
    crosses a process boundary.
    """
    if event.terminal == "converged":
        return (("done", ""),)
    if event.terminal == "cancelled":
        return (("error", "cancelled"), ("done", ""))
    error = event.error
    named = type(error).__name__ if error is not None else "unknown"
    return (("error", named), ("done", ""))


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

    Detaching is **not** cancelling (plan 0031 trap 9, Q14). A browser
    refresh detaches one observer of an exchange that may have been running
    for eight minutes; whether the exchange should then stop is the
    registry's decision, taken when the *last* observer has been gone for
    the grace period.
    """

    __slots__ = ("_closed", "_keepalive_s", "_observation", "_pending", "last_seq")

    def __init__(
        self,
        observation: TurnObservation,
        *,
        keepalive_s: float | None = KEEPALIVE_INTERVAL_S,
        after_seq: int = 0,
    ) -> None:
        """*after_seq* is remembered, not applied.

        The cursor is applied by whoever called ``observe(after_seq=…)``;
        it is recorded here only so that :attr:`last_seq` is a valid resume
        point even before the first frame arrives — a client that
        reconnects and immediately disconnects again must not be told to
        resume from zero.
        """
        self._observation = observation
        self._keepalive_s = keepalive_s
        self._pending: list[str] = []
        self._closed = False
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
            self.last_seq = max(self.last_seq, event.seq)
            if event.type is TurnEventType.EXCHANGE_END:
                self._queue(desktop_terminal_frames(event))
                await self.aclose()
                continue
            frame = desktop_chat_frame(event)
            if frame is None:
                continue
            return render_chat_sse_frame(*frame)

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
