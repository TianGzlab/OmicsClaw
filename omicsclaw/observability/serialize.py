"""Turning a conversation into an attribute value, safely and briefly.

Three functions, the analogue of ``observability/helpers.go``. Nothing
here is called unless
:attr:`~omicsclaw.observability.config.ObservabilityConfig.capture_content`
is on — that check belongs to the callers, so that a deployment which
captures nothing never pays for a serialization it will discard.

**The hazard this module exists to contain** is that a span attribute is
a protobuf ``string`` field going over a network to somebody else's
service. Three properties have to hold and none of them hold for the
input:

1. It must be valid UTF-8. A tool's output can contain a lone surrogate,
   because reading a binary file through ``errors="surrogateescape"`` is
   how the standard library hands bytes back as ``str``.
2. It must be bounded. A ``read_file`` on a count matrix is megabytes,
   and an exporter that refuses an oversized payload drops the whole
   batch — so one large tool result loses the traces either side of it.
3. It must not silently become a different string. Truncation that cuts
   a multi-byte character in half produces exactly the corruption a
   reader will blame on their own pipeline.

Stdlib only.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from omicsclaw.schema import Message

__all__ = [
    "MAX_ATTRIBUTE_BYTES",
    "TRUNCATION_MARK",
    "serialize_messages",
    "serialize_output",
    "truncate_attr",
]

MAX_ATTRIBUTE_BYTES = 4096
"""Bytes, not characters, and the same figure the reference uses.

Bytes because that is what the wire counts: a 4,096-*character* limit
would be 16 KiB of Chinese, and a conversation in this repository's own
documentation language would blow a budget that an English one respects.
"""

TRUNCATION_MARK = "…[truncated]"
"""Appended to anything that was cut, so a reader can tell a short value
from a shortened one. Counted *outside* :data:`MAX_ATTRIBUTE_BYTES`,
which makes the bound a bound on the *content* — the alternative is
arithmetic that has to be redone whenever the mark is reworded."""


def truncate_attr(text: str) -> str:
    """Make *text* safe to put in a span attribute.

    Sanitises, then bounds, in that order — the reverse would measure a
    length that sanitising is about to change.

    **Sanitising is a Python problem with a different shape from Go's.**
    A Go ``string`` is arbitrary bytes and the reference has to check
    ``utf8.ValidString``. A Python ``str`` is always a sequence of code
    points, so the only way it can fail to encode is a **surrogate** —
    ``"\\udcff"`` — which ``surrogateescape`` puts there when binary is
    decoded as text. ``errors="replace"`` turns each such code point into
    ``?`` rather than raising, which is the same trade the reference makes
    by dropping invalid sequences: a byte that was never text does not
    become meaningful by being displayed.

    Truncation cuts on a code-point boundary. The mechanism is
    ``decode(..., errors="ignore")``, which discards a trailing partial
    sequence — the one place in this package where ``ignore`` is the
    precise answer rather than a shrug, since the bytes being dropped are
    by construction the front half of a character whose other half is
    already gone.
    """
    raw = text.encode("utf-8", "replace")
    if len(raw) <= MAX_ATTRIBUTE_BYTES:
        return raw.decode("utf-8")
    return raw[:MAX_ATTRIBUTE_BYTES].decode("utf-8", "ignore") + TRUNCATION_MARK


def serialize_messages(messages: Sequence[Message]) -> str:
    """The conversation as one JSON array, for a span's input attribute.

    A **view**, not the messages: ``role``, ``content``, ``tool_call_id``
    and the tool calls, and nothing else.

    Two omissions are deliberate.
    :attr:`~omicsclaw.schema.Message.reasoning_content` is dropped because
    a thought is the model's working and not the request — the reference
    has no equivalent field at all, its adapters discarding thinking after
    streaming it, so including it here would be inventing a payload for a
    pane that has nowhere to put it.
    :attr:`~omicsclaw.schema.Message.is_error` is dropped because a failed
    Observation is already visible as the tool span's status, and a second
    spelling of the same fact is a second thing to keep in step.

    The whole array is truncated *after* serialization rather than each
    message being truncated first. That keeps the result parseable right
    up to the cut — a reader gets valid JSON for the first N messages
    followed by an obvious mark, instead of a whole conversation each of
    whose messages has been quietly shortened.
    """
    views = [_message_view(message) for message in messages]
    return truncate_attr(_dumps(views))


def serialize_output(message: Message | None) -> str:
    """What the model said, for a span's output attribute.

    Tool calls win over text when both are present, matching the
    reference: a turn that requested an action is *about* the action, and
    the accompanying prose is usually a sentence of narration. ``None``
    and a message with neither produce ``""``.
    """
    if message is None:
        return ""
    if message.tool_calls:
        return truncate_attr(_dumps([_call_view(c) for c in message.tool_calls]))
    return truncate_attr(message.content)


def _message_view(message: Message) -> dict[str, Any]:
    view: dict[str, Any] = {"role": str(message.role), "content": message.content}
    if message.tool_call_id:
        view["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        view["tool_calls"] = [_call_view(call) for call in message.tool_calls]
    return view


def _call_view(call: Any) -> dict[str, Any]:
    """One tool call, with its arguments left as the **text** they are.

    :attr:`~omicsclaw.schema.ToolCall.arguments` is unparsed JSON by
    ruling (``schema/message.py``), and decoding it here to nest it as an
    object would reorder its keys — throwing away the byte-exactness that
    prompt-prefix caching and replay evidence rest on, in a *telemetry*
    module, where the only thing gained is a prettier pane.
    """
    return {"id": call.id, "name": call.name, "arguments": call.arguments}


def _dumps(payload: Any) -> str:
    """JSON with no ASCII escaping and no gratuitous whitespace.

    ``ensure_ascii=False`` because the alternative triples the byte cost
    of any non-Latin text and spends the attribute budget on backslashes.
    """
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
