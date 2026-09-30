"""Bounded wire rendering for the Desktop ``/chat/stream`` SSE frames.

The renderer owns the byte contract at the actual wire seam: an optional
``id: <n>`` line, then one ``data: {"type": ..., "data": ...}`` line per
frame, where ``data`` is a string (objects are JSON-encoded first).
Producers may hand it rich Python values, but every returned frame, its
``id:`` line included, is at most 4 MiB after UTF-8 encoding.
Oversized tool results retain their correlation identity and become an
explicit renderer projection; scientific content is never silently cut into
an invalid JSON fragment. A change to these bytes is a change to the wire
contract (:mod:`~omicsclaw.entry.desktop.wire_contract`).
"""

from __future__ import annotations

import json
from typing import Any, Final


CHAT_SSE_MAX_FRAME_BYTES: Final = 4 * 1024 * 1024
CHAT_SSE_QUEUE_MAX_ITEMS: Final = 8
CHAT_STREAM_COMPARISON_MAX_BYTES: Final = 1024 * 1024
_UTF8_COUNT_CHARS: Final = 16 * 1024
_TOOL_RESULT_MEDIA_RAW_MAX_BYTES: Final = 512 * 1024
_TOOL_RESULT_MEDIA_MAX_ITEMS: Final = 256


def utf8_size(value: str) -> int:
    """Return exact UTF-8 bytes without allocating one value-sized copy."""

    return sum(
        len(
            value[offset : offset + _UTF8_COUNT_CHARS].encode("utf-8", errors="replace")
        )
        for offset in range(0, len(value), _UTF8_COUNT_CHARS)
    )


def _payload_text(data: Any) -> str:
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False, default=str)
    return str(data)


def _raw_frame(event_type: str, payload: str, prefix: str = "") -> str:
    return (
        prefix
        + "data: "
        + json.dumps(
            {"type": event_type, "data": payload},
            # ASCII JSON guarantees the ASGI bytes are valid UTF-8 even if an
            # external tool returns a Python string containing lone surrogates.
            ensure_ascii=True,
            default=str,
        )
        + "\n\n"
    )


def _fits(frame: str) -> bool:
    return utf8_size(frame) <= CHAT_SSE_MAX_FRAME_BYTES


def _media_exceeds_projection_budget(media: Any) -> bool:
    if not isinstance(media, list):
        return False
    if len(media) > _TOOL_RESULT_MEDIA_MAX_ITEMS:
        return True
    remaining = _TOOL_RESULT_MEDIA_RAW_MAX_BYTES
    stack = list(media)
    seen_containers: set[int] = {id(media)}
    visited = 0
    while stack:
        value = stack.pop()
        visited += 1
        if visited > 4096:
            return True
        if isinstance(value, str):
            remaining -= utf8_size(value)
        elif isinstance(value, dict):
            identity = id(value)
            if identity in seen_containers:
                return True
            seen_containers.add(identity)
            stack.extend(value.keys())
            stack.extend(value.values())
        elif isinstance(value, (list, tuple)):
            identity = id(value)
            if identity in seen_containers:
                return True
            seen_containers.add(identity)
            stack.extend(value)
        else:
            remaining -= 16
        if remaining < 0:
            return True
    return False


def _bounded_tool_result(data: dict[str, Any], prefix: str) -> str:
    content = str(data.get("content") or "")
    content_size = utf8_size(content)
    media = data.get("media")
    media_count = len(media) if isinstance(media, list) else 0
    media_preemptively_omitted = _media_exceeds_projection_budget(media)

    # Avoid serialising a known-oversized scientific result only to reject it.
    if content_size <= CHAT_SSE_MAX_FRAME_BYTES:
        if not media_preemptively_omitted:
            candidate = _raw_frame("tool_result", _payload_text(data), prefix)
            if _fits(candidate):
                return candidate

        without_media = dict(data)
        without_media.pop("media", None)
        without_media.update(
            {
                "content_truncated": False,
                "content_size_bytes": content_size,
                "media_omitted_count": media_count,
            }
        )
        candidate = _raw_frame("tool_result", _payload_text(without_media), prefix)
        if _fits(candidate):
            return candidate

    projection: dict[str, Any] = {
        "tool_use_id": str(data.get("tool_use_id") or ""),
        "tool_name": str(data.get("tool_name") or ""),
        "content": (
            "Tool result omitted from this stream because it exceeds the "
            "4 MiB frame limit."
        ),
        "content_truncated": True,
        "content_size_bytes": content_size,
        "media_omitted_count": media_count,
    }
    if data.get("is_error") is True:
        projection["is_error"] = True
    frame = _raw_frame("tool_result", _payload_text(projection), prefix)
    if _fits(frame):
        return frame

    # Runtime-generated ids/names are short.  This fail-closed fallback still
    # protects the wire if an invalid producer hands us an enormous identity.
    fallback = _raw_frame(
        "event_omitted",
        _payload_text(
            {
                "omitted_event_type": "tool_result",
                "reason": "frame_too_large",
                "data_size_bytes": content_size,
            }
        ),
        prefix,
    )
    return fallback


def _id_line(event_id: int | None) -> str:
    if event_id is None:
        return ""
    if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id < 0:
        raise ValueError(f"an SSE event id is a non-negative integer, not {event_id!r}")
    return f"id: {event_id}\n"


def render_chat_sse_frame(
    event_type: str, data: Any, *, event_id: int | None = None
) -> str:
    """Render one bounded Desktop Chat SSE frame.

    *event_id*, when given, is written as the frame's ``id:`` line: the
    sequence number of the event the frame came from. The line counts
    towards the 4 MiB bound, and an oversized frame's projection keeps it.

    Non-terminal oversized events become an explicit ``event_omitted`` frame.
    An oversized terminal error remains an ``error`` so consumers do not
    accidentally reinterpret failure as a successful end of stream.

    :raises ValueError: *event_id* is not a non-negative integer.
    """

    prefix = _id_line(event_id)
    normalized_type = str(event_type)
    if normalized_type == "tool_result" and isinstance(data, dict):
        return _bounded_tool_result(data, prefix)

    payload = _payload_text(data)
    # A payload larger than the complete frame cannot possibly fit.  Avoid the
    # outer JSON allocation in that common oversized case.
    payload_size = utf8_size(payload)
    if payload_size <= CHAT_SSE_MAX_FRAME_BYTES:
        candidate = _raw_frame(normalized_type, payload, prefix)
        if _fits(candidate):
            return candidate

    if normalized_type == "error":
        candidate = _raw_frame(
            "error",
            f"Error payload omitted because it exceeds the 4 MiB frame limit "
            f"({payload_size} UTF-8 bytes).",
            prefix,
        )
    else:
        candidate = _raw_frame(
            "event_omitted",
            _payload_text(
                {
                    "omitted_event_type": normalized_type,
                    "reason": "frame_too_large",
                    "data_size_bytes": payload_size,
                }
            ),
            prefix,
        )
    if not _fits(candidate):  # pragma: no cover - fixed literals are tiny
        raise RuntimeError("bounded Desktop Chat SSE projection exceeded its limit")
    return candidate


__all__ = [
    "CHAT_SSE_MAX_FRAME_BYTES",
    "CHAT_SSE_QUEUE_MAX_ITEMS",
    "CHAT_STREAM_COMPARISON_MAX_BYTES",
    "render_chat_sse_frame",
    "utf8_size",
]
