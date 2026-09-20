"""``omicsclaw/schema`` — streaming deltas from the model adapter.

The adapter yields :class:`StreamChunk` values; the Main Loop folds them
into one :class:`~omicsclaw.schema.message.Message`.

A chunk is a *transport* fact, and is deliberately not the same type as
whatever a user interface eventually renders: a UI needs things no model
ever sends — tool approval prompts, progress edits, compaction notices —
and tying the two together would make every UI change a transport change.

Partial tool-call arguments are never exposed as chunk state. The adapter
accumulates streamed argument fragments internally and publishes them
only on :attr:`StreamChunkType.DONE`, so no consumer can observe — or act
on — a half-decoded call.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .message import Message, Usage


class StreamChunkType(StrEnum):
    """Kind of incremental payload in a streamed completion."""

    TEXT_DELTA = "text_delta"
    """Assistant text, token by token."""

    REASONING_DELTA = "reasoning_delta"
    """Thought tokens (``reasoning_content`` / thinking / extended reasoning).

    Named for OmicsClaw's existing vocabulary — ``reasoning_content``,
    ``on_stream_reasoning``, ``events.StreamReasoning`` — rather than
    "thinking", so one word means one thing across the stack.
    """

    DONE = "done"
    """Stream finished. Carries the assembled ``message`` and ``usage``."""

    ERROR = "error"
    """The stream failed; ``error`` describes it."""


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """One increment of a streamed completion.

    Field validity follows :attr:`type`::

        TEXT_DELTA       -> delta
        REASONING_DELTA  -> delta
        DONE             -> message, usage, finish_reason
        ERROR            -> error
    """

    type: StreamChunkType
    delta: str = ""
    message: Message | None = None
    usage: Usage | None = None
    error: str = ""

    finish_reason: str = ""
    """Why the model stopped, as the vendor spelled it. Set on ``DONE``.

    Mirrors ``Completion.finish_reason`` so the blocking and streaming
    paths answer the same question. Without it a stream cut off by the
    output ceiling is **indistinguishable from a model that finished**:
    both end with a ``DONE`` chunk whose message requests no tools, so a
    loop reading only ``message.is_action`` reports a truncated answer as
    a completed task.

    Left as the raw vendor token ("stop" / "end_turn" / "tool_calls" /
    "tool_use" / "length" / "max_tokens") for the reason
    ``Completion.finish_reason`` is: promoting it to a neutral enum is
    deferred until something branches on more than the truncation case.
    """

    @classmethod
    def text(cls, delta: str) -> StreamChunk:
        return cls(type=StreamChunkType.TEXT_DELTA, delta=delta)

    @classmethod
    def reasoning(cls, delta: str) -> StreamChunk:
        return cls(type=StreamChunkType.REASONING_DELTA, delta=delta)

    @classmethod
    def done(
        cls,
        message: Message,
        usage: Usage | None = None,
        finish_reason: str = "",
    ) -> StreamChunk:
        return cls(
            type=StreamChunkType.DONE,
            message=message,
            usage=usage,
            finish_reason=finish_reason,
        )

    @classmethod
    def failed(cls, error: str) -> StreamChunk:
        return cls(type=StreamChunkType.ERROR, error=error)


__all__ = ["StreamChunk", "StreamChunkType"]
