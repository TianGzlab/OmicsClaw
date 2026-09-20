"""``omicsclaw/entry`` — one exchange's frames as text, and as JSON.

Plan 0031 §3.2. Two projections of :class:`~omicsclaw.entry.events.
TurnEvent`, deliberately of different kinds:

:class:`TextRenderer` is **stateful**, because the Channel Surface cannot
be served by a pure function. An IM platform rate-limits message edits, so
a bot that forwarded every text delta would be throttled within a
sentence; deltas have to be accumulated *across* events and sent in
batches. The CLI wants the opposite — a token on screen as it arrives —
so the same class does both, and which one is a constructor argument
rather than two classes with one shared bug.

:func:`to_wire` is **pure**, and is what crosses a process boundary.

Three things this module is careful about, each with a named trap in plan
0031 §6:

*The elapsed figure is not "how long the tool took"* (trap 6).
``EngineEvent.duration_s`` is wall-clock measured by the scheduler and
therefore **includes time a human spent deciding an approval**
(``engine/types.py:239-245``). The guard here is structural rather than
editorial: no field named for a tool's duration ever reaches a caller —
the text always carries :data:`ELAPSED_INCLUDES_APPROVAL_WAIT` and the
wire always uses ``elapsed_s`` plus an explicit
``elapsed_includes_approval_wait`` flag. Neither can be composed by
accident, and neither depends on anyone reading the prose.

*A missing token count and a zero token count are different facts*
(trap 7). ``usage=None`` only ever comes from a streamed run and means the
backend reported nothing; a zero :class:`~omicsclaw.schema.Usage` comes
from the blocking path and means "free **or** unreported", because
``Completion.usage`` cannot express the difference
(``engine/types.py:204-215``). They render as
:data:`USAGE_UNREPORTED` and :data:`USAGE_ZERO`, never as the same string.

*Tool arguments and tool output are not rendered as text* (Q22 rule 1).
Argument payloads and tool output can carry subject identifiers, and this
layer feeds a CLI, an IM transport and an HTTP stream from one place, so
:class:`TextRenderer` never puts either on a screen or in a chat; a
Surface that has decided it may show them reads them off
:attr:`~omicsclaw.entry.events.TurnEvent.engine` itself, having made that
decision explicitly.

:func:`to_wire` is the other case and the opposite rule: it **must**
carry both, because ``ToolCall.arguments`` crossing byte for byte is a
published contract (see below) and a ``tool_result`` without its content
is not a result. It follows that ``to_wire``'s **output** is itself
inside Q22 rule 1's protection: those dictionaries reach an SSE stream by
way of ``desktop/turn_observation.py``, whose ``_wire_json_value``
redacts by *key name* only and passes every string through untouched. A
frame is therefore not safe to log, and nothing here logs one.

**Wire compatibility** (Q24). ``POST /chat/stream`` is a published
contract with an external client, not this layer's to invent. Three
consequences are load-bearing and are pinned by tests:

- ``ToolCall.arguments`` crosses **byte for byte**. It is a raw JSON
  string precisely so that a decode/re-encode cannot reorder keys
  (``schema/message.py:81-89``); prompt-prefix caching and replay
  evidence both depend on those bytes.
- A ``tool_result`` frame uses the key names
  ``surfaces/desktop/_chat_sse.py`` reads — ``tool_use_id``,
  ``tool_name``, ``content``, ``is_error``. That renderer's 4 MiB
  oversize projection reaches into the payload by name, so a frame that
  spelled them differently would lose its correlation identity exactly
  when a result is too big to send.
- The terminal frame preserves the error's **type**
  (``wire_contract.py``: ``terminal_error_type_preserved``), and only its
  type: an exception's text can contain a URL with credentials in the
  query string.

The mapping from :class:`~omicsclaw.entry.events.TurnEventType` to that
client's frame names is :data:`DESKTOP_CHAT_FRAME_TYPE`; ``to_wire``
itself tags frames with the enum value, because the enum is this layer's
truth and the client's vocabulary is the Desktop Surface's to speak.
"""

from __future__ import annotations

import math
from typing import Any, Final

from omicsclaw.entry.events import TurnEvent, TurnEventType

ELAPSED_INCLUDES_APPROVAL_WAIT: Final = "s elapsed (includes any approval wait)"
"""Mandatory suffix for every rendered ``TOOL_RESULT`` timing.

A constant rather than a sentence inside a format string so that the
guarantee is testable by identity: a renderer change that starts calling
this "tool time" has to delete a name, not edit prose (trap 6).
"""

USAGE_UNREPORTED: Final = "tokens: not reported by this backend"
"""``TURN_END.usage is None`` — only a streamed run can say this."""

USAGE_ZERO: Final = "tokens: 0 (free, or not reported)"
"""``TURN_END.usage`` is all zeros — the blocking path cannot tell those
two apart, so neither does this string (trap 7)."""

REASONING_PREFIX: Final = "[reasoning] "
"""Marks the Reasoning half of ReAct so a reader can tell it from the
answer without the renderer having to interleave two streams."""

BATCH_CHARS: Final = 2000
"""Characters buffered before a batched renderer emits.

Sized to the tightest published per-message limit among the shipped
Channel adapters (Discord, ``surfaces/channels/capabilities.py:106``;
the rest are 4000 or 4096 except EMAIL, whose ``max_text_length=0`` at
``:151`` means *no practical limit* rather than *no characters*),
because a batch larger than the tightest has to be cut up by
``chunk_text`` before it can be sent anyway.

Batching is by character count and not by wall clock on purpose:
:meth:`TextRenderer.feed` takes no clock, so it stays deterministic under
test and the send *cadence* stays the adapter's own decision.
"""

DESKTOP_CHAT_FRAME_TYPE: Final[dict[TurnEventType, str]] = {
    TurnEventType.TEXT_DELTA: "text",
    TurnEventType.TOOL_START: "tool_use",
    TurnEventType.TOOL_RESULT: "tool_result",
    TurnEventType.PROGRESS: "tool_output",
    TurnEventType.APPROVAL_REQUIRED: "permission_request",
}
"""``/chat/stream`` frame names for the types the published contract has
one for.

Evidence: ``surfaces/desktop/server.py:2006-2020`` documents the frame
vocabulary, and the external client switches on it in
``OmicsClaw-App/src/hooks/useSSEStream.ts:143-431`` — ``text``,
``tool_use``, ``tool_result``, ``tool_output``, ``permission_request``,
``status``, ``done``, ``error`` and ten more each have a ``case``, and an
unrecognised type falls to ``default:`` at ``:430`` and is dropped in
silence. ``src/app/api/chat/route.ts`` is **not** that switch: it
recognises only the two terminal types while it validates a frame's
shape (``:87-101``).

The remaining types have **no** published name — inventing one here would
publish a vocabulary to an external client unilaterally, which Q24 puts
outside a backend-internal rebuild step. ``EXCHANGE_END`` is absent for a
second reason: it maps to ``done`` or to ``error`` depending on
:attr:`~omicsclaw.entry.events.TurnEvent.terminal`, which is a branch and
not a lookup.
"""

_WIRE_SCHEMA_VERSION: Final = 1


class TextRenderer:
    """Frames in, human-readable text out — with memory between calls.

    :meth:`feed` returns ``None`` when an event produces nothing *yet*,
    which in batched mode is the common case: deltas accumulate until
    :data:`BATCH_CHARS` is reached or until a control event forces the
    buffer out ahead of it, so that a tool line never appears above the
    sentence that preceded it.

    Whatever is still buffered when the exchange ends is returned by
    :meth:`flush`. A caller that forgets to call it loses the tail of the
    last answer, which is why ``EXCHANGE_END`` also drains the buffer.
    """

    __slots__ = ("_batch_chars", "_batched", "_buf", "_kind", "_show_reasoning")

    def __init__(
        self,
        *,
        batched: bool = False,
        batch_chars: int = BATCH_CHARS,
        show_reasoning: bool = False,
    ) -> None:
        """``batched=False`` is the CLI; ``batched=True`` is a Channel."""
        if not isinstance(batch_chars, int) or batch_chars <= 0:
            raise ValueError("batch_chars must be a positive integer")
        self._batched = batched
        self._batch_chars = batch_chars
        self._show_reasoning = show_reasoning
        self._buf: list[str] = []
        self._kind = ""

    def feed(self, event: TurnEvent) -> str | None:
        """Render one frame, or ``None`` when it produces nothing yet."""
        if event.type in (TurnEventType.TEXT_DELTA, TurnEventType.REASONING_DELTA):
            return self._feed_delta(event)
        prefix = self._drain()
        line = self._control_line(event)
        if line is None:
            return prefix or None
        return f"{prefix}\n{line}" if prefix else line

    def flush(self) -> str:
        """Return and clear whatever is still buffered; ``""`` if nothing."""
        return self._drain()

    # ---- internals ------------------------------------------------------

    def _feed_delta(self, event: TurnEvent) -> str | None:
        reasoning = event.type is TurnEventType.REASONING_DELTA
        if reasoning and not self._show_reasoning:
            return None
        delta = event.engine.delta if event.engine is not None else ""
        if not delta:
            return None
        kind = "reasoning" if reasoning else "text"
        carried = self._drain() if self._kind and self._kind != kind else ""
        self._kind = kind
        self._buf.append(delta)
        if self._batched and sum(map(len, self._buf)) < self._batch_chars:
            return carried or None
        emitted = self._drain()
        return f"{carried}\n{emitted}" if carried else emitted

    def _drain(self) -> str:
        if not self._buf:
            return ""
        text = "".join(self._buf)
        kind = self._kind
        self._buf.clear()
        self._kind = ""
        return f"{REASONING_PREFIX}{text}" if kind == "reasoning" else text

    def _control_line(self, event: TurnEvent) -> str | None:
        kind = event.type
        if kind is TurnEventType.EXCHANGE_START:
            return None
        if kind is TurnEventType.QUEUED:
            if event.queued_ahead <= 0:
                return "Queued."
            return f"Queued behind {event.queued_ahead} on this session."
        if kind is TurnEventType.CONTEXT:
            return _context_line(event)
        if kind is TurnEventType.COMPACTION:
            return _compaction_line(event)
        if kind is TurnEventType.PROGRESS:
            return _progress_line(event)
        if kind is TurnEventType.TOOL_START:
            call = event.engine.tool_call if event.engine is not None else None
            return f"-> {call.name if call is not None else '?'}"
        if kind is TurnEventType.TOOL_RESULT:
            return _tool_result_line(event)
        if kind is TurnEventType.APPROVAL_REQUIRED:
            return _approval_line(event)
        if kind is TurnEventType.APPROVAL_SETTLED:
            return _settled_line(event)
        if kind is TurnEventType.TURN_END:
            return _usage_line(event)
        if kind is TurnEventType.GAP:
            oldest, latest = event.gap or (0, 0)
            return (
                f"[gap] frames before {oldest} are no longer available "
                f"(stream is at {latest})"
            )
        if kind is TurnEventType.EXCHANGE_END:
            return _terminal_line(event)
        return None  # pragma: no cover - StrEnum is exhaustive above


def _context_line(event: TurnEvent) -> str:
    report = event.report
    if report is None:
        return "Context: unreported"
    used = report.message_tokens + report.tool_tokens
    line = (
        f"Context: {used} tokens of {report.budget.context_tokens}, "
        f"pressure {report.pressure.value} ({_ratio(report.ratio)})"
    )
    if report.tool_reserve_shortfall:
        line += f", tool reserve short by {report.tool_reserve_shortfall}"
    return line


def _compaction_line(event: TurnEvent) -> str:
    record = event.compaction
    if record is None:
        return "Compacted."
    line = (
        f"Compacted [{record.pressure.value}]: "
        f"{record.msgs_before} -> {record.msgs_after} messages, "
        f"{record.tokens_before} -> {record.tokens_after} tokens"
    )
    if record.tokens_before > 0:
        line += f" ({1 - record.compression_ratio:.0%} smaller)"
    details = []
    if record.offloaded:
        chars = sum(entry.chars for entry in record.offloaded)
        details.append(f"{len(record.offloaded)} offloaded ({chars} chars)")
    if record.summarized:
        details.append(f"{record.summarized} summarized")
        details.append(f"{record.preserved_tail} kept verbatim")
    if not record.written_back:
        details.append("this call only")
    if details:
        line += f"; {', '.join(details)}"
    if record.degraded:
        line += f" (degraded: {record.degraded})"
    return line


def _progress_line(event: TurnEvent) -> str:
    update = event.progress
    if update is None:
        return "..."
    head = f"... {update.tool_name}" if update.tool_name else "..."
    body = f": {update.message}" if update.message else ""
    share = ""
    if update.fraction is not None and math.isfinite(update.fraction):
        share = f" [{update.fraction * 100:.0f}%]"
    return f"{head}{body}{share}"


def _tool_result_line(event: TurnEvent) -> str:
    engine = event.engine
    result = engine.tool_result if engine is not None else None
    name = result.name if result is not None and result.name else "?"
    status = "error" if result is not None and result.is_error else "ok"
    line = f"<- {name} {status}"
    elapsed = engine.duration_s if engine is not None else None
    if elapsed is not None and math.isfinite(elapsed):
        line += f", {elapsed:.1f}{ELAPSED_INCLUDES_APPROVAL_WAIT}"
    return line


def _approval_line(event: TurnEvent) -> str:
    request = event.approval
    if request is None:
        return f"Approval required [{event.request_id}]"
    line = (
        f"Approval required [{event.request_id}]: {request.tool_name} "
        f"(risk {request.risk_level.value})"
    )
    if request.reason:
        line += f" - {request.reason}"
    return line


def _settled_line(event: TurnEvent) -> str:
    decision = event.decision
    if decision is None:
        return f"Approval settled [{event.request_id}]"
    verdict = "granted" if decision.approved else "denied"
    line = f"Approval {verdict} [{event.request_id}]"
    if decision.reason:
        line += f": {decision.reason}"
    return line


def _usage_line(event: TurnEvent) -> str:
    engine = event.engine
    turn = engine.turn if engine is not None else 0
    usage = engine.usage if engine is not None else None
    if usage is None:
        return f"Turn {turn} done, {USAGE_UNREPORTED}"
    if usage.total_tokens == 0:
        return f"Turn {turn} done, {USAGE_ZERO}"
    return (
        f"Turn {turn} done, tokens: {usage.input_tokens} in / "
        f"{usage.output_tokens} out"
    )


def _terminal_line(event: TurnEvent) -> str:
    terminal = event.terminal or "converged"
    if terminal == "converged":
        return "Done."
    if terminal == "cancelled":
        return "Cancelled."
    error = event.error
    named = type(error).__name__ if error is not None else "unknown"
    return f"Failed: {named}"


def _ratio(value: float) -> str:
    return f"{value * 100:.0f}%" if math.isfinite(value) else "unknown"


def to_wire(event: TurnEvent) -> dict[str, Any]:
    """Project one frame into a JSON-serializable dictionary.

    Strictly serializable: the result survives ``json.dumps(...,
    allow_nan=False)``, because ``NaN`` and ``Infinity`` are not JSON and
    a frame that produced them would be rejected by a conforming client
    rather than by this process. Non-finite floats become the strings the
    deleted wire projection used (``"NaN"``, ``"Infinity"``).

    Identity (``sequence``, ``turn_id``, ``session_id``) is on every
    frame, so a reconnecting client can resume from any frame it
    received.
    """
    wire: dict[str, Any] = {
        "schema_version": _WIRE_SCHEMA_VERSION,
        "type": event.type.value,
        "sequence": event.seq,
        "session_id": event.session_id,
        "turn_id": event.turn_id,
    }
    wire.update(_payload(event))
    return wire


def _payload(event: TurnEvent) -> dict[str, Any]:
    kind = event.type
    engine = event.engine
    if kind in (TurnEventType.TEXT_DELTA, TurnEventType.REASONING_DELTA):
        return {
            "turn": engine.turn if engine is not None else 0,
            "delta": engine.delta if engine is not None else "",
        }
    if kind is TurnEventType.TOOL_START:
        call = engine.tool_call if engine is not None else None
        return {
            "turn": engine.turn if engine is not None else 0,
            "tool_use_id": call.id if call is not None else "",
            "tool_name": call.name if call is not None else "",
            # Verbatim. Never ``parsed_arguments()``: a decode plus
            # re-encode can reorder keys, and those bytes are what
            # prompt-prefix caching and replay evidence are matched on.
            "arguments": call.arguments if call is not None else "",
        }
    if kind is TurnEventType.TOOL_RESULT:
        return _tool_result_payload(event)
    if kind is TurnEventType.TURN_END:
        return _turn_end_payload(event)
    if kind is TurnEventType.PROGRESS:
        update = event.progress
        return {
            "tool_name": update.tool_name if update is not None else "",
            "message": update.message if update is not None else "",
            "fraction": _json_float(update.fraction if update is not None else None),
        }
    if kind is TurnEventType.CONTEXT:
        return _context_payload(event)
    if kind is TurnEventType.COMPACTION:
        return _compaction_payload(event)
    if kind is TurnEventType.APPROVAL_REQUIRED:
        return _approval_payload(event)
    if kind is TurnEventType.APPROVAL_SETTLED:
        decision = event.decision
        return {
            "request_id": event.request_id,
            "approved": decision.approved if decision is not None else None,
            "reason": decision.reason if decision is not None else "",
        }
    if kind is TurnEventType.QUEUED:
        return {"ahead": event.queued_ahead}
    if kind is TurnEventType.GAP:
        oldest, latest = event.gap or (0, 0)
        return {"oldest_available": oldest, "latest": latest}
    if kind is TurnEventType.EXCHANGE_END:
        error = event.error
        return {
            "terminal": event.terminal,
            # Type only. An exception's text can carry a fetched URL with
            # its query string, which Q22 rule 1 keeps off every shared
            # channel; the original object stays on ``TurnEvent.error``
            # for a same-process consumer to re-raise.
            "error_type": type(error).__name__ if error is not None else None,
        }
    return {}


def _tool_result_payload(event: TurnEvent) -> dict[str, Any]:
    engine = event.engine
    result = engine.tool_result if engine is not None else None
    elapsed = engine.duration_s if engine is not None else None
    return {
        "turn": engine.turn if engine is not None else 0,
        "tool_use_id": result.tool_call_id if result is not None else "",
        "tool_name": result.name if result is not None else "",
        "content": result.output if result is not None else "",
        "is_error": bool(result.is_error) if result is not None else False,
        # Not ``duration_s``: the engine measures wall clock from the
        # scheduler's side, so this includes however long a human took to
        # answer an approval (trap 6). The flag travels with the number so
        # a client cannot label it "tool time" without overriding a fact
        # it was handed.
        "elapsed_s": _json_float(elapsed),
        "elapsed_includes_approval_wait": True,
    }


def _turn_end_payload(event: TurnEvent) -> dict[str, Any]:
    engine = event.engine
    usage = engine.usage if engine is not None else None
    payload: dict[str, Any] = {
        "turn": engine.turn if engine is not None else 0,
        # ``False`` is a fact a streamed run can report and a blocking run
        # cannot; keeping it distinct from an all-zero ``Usage`` is trap 7.
        "usage_reported": usage is not None,
        "usage": None,
    }
    if usage is not None:
        payload["usage"] = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "cache_write_tokens": usage.cache_write_tokens,
        }
    return payload


def _context_payload(event: TurnEvent) -> dict[str, Any]:
    report = event.report
    if report is None:
        return {}
    return {
        "context_tokens": report.budget.context_tokens,
        "message_tokens": report.message_tokens,
        "tool_tokens": report.tool_tokens,
        "tool_reserve_shortfall": report.tool_reserve_shortfall,
        "pressure": report.pressure.value,
        "ratio": _json_float(report.ratio),
    }


def _compaction_payload(event: TurnEvent) -> dict[str, Any]:
    record = event.compaction
    if record is None:
        return {}
    # Counts and the failure gate only. The summary text itself is already
    # in the conversation the model sees, and repeating it here would put
    # transcript content on a channel whose whole purpose is a
    # notification.
    return {
        "pressure": record.pressure.value,
        "tokens_before": record.tokens_before,
        "tokens_after": record.tokens_after,
        "msgs_before": record.msgs_before,
        "msgs_after": record.msgs_after,
        "summarized": record.summarized,
        "preserved_tail": record.preserved_tail,
        "degraded": record.degraded,
        "trigger": record.trigger.value,
        "offloaded": len(record.offloaded),
        "written_back": record.written_back,
        "forced": record.forced,
    }


def _approval_payload(event: TurnEvent) -> dict[str, Any]:
    request = event.approval
    if request is None:
        return {"request_id": event.request_id}
    return {
        "request_id": event.request_id,
        "tool_name": request.tool_name,
        # Raw, for the reason ``ApprovalRequest`` keeps it raw: an
        # approval prompt showing re-encoded arguments is showing
        # something other than what will run.
        "arguments": request.arguments,
        "reason": request.reason,
        "risk_level": request.risk_level.value,
        "approval_mode": request.approval_mode.value,
    }


def _json_float(value: float | None) -> Any:
    """JSON has no ``NaN`` and no ``Infinity``; say so in words instead."""
    if value is None:
        return None
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return value


__all__ = [
    "BATCH_CHARS",
    "DESKTOP_CHAT_FRAME_TYPE",
    "ELAPSED_INCLUDES_APPROVAL_WAIT",
    "REASONING_PREFIX",
    "USAGE_UNREPORTED",
    "USAGE_ZERO",
    "TextRenderer",
    "to_wire",
]
