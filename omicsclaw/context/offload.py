"""Moving oversized tool results out of the conversation.

A tool result the model has already read can be replaced by a short
placeholder naming where the full text was kept and showing its first
lines; the model reads it back with ``read_file`` when it needs it again.

This module decides *which* messages move and *what the placeholder
says*. Where the bytes go is an :class:`OffloadStore` supplied by the
caller — nothing here touches a filesystem.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from omicsclaw.schema import Message, Role

from .tokens import TokenCounter, estimate_text_tokens

__all__ = [
    "MAX_REFERENCES",
    "OFFLOAD_MARKER",
    "REFERENCES_HEADING",
    "OffloadEntry",
    "OffloadOutcome",
    "OffloadStore",
    "Offloader",
    "is_offloaded",
    "offload_key",
    "offload_messages",
    "parse_placeholder",
    "parse_references",
    "render_placeholder",
    "render_references",
]

OFFLOAD_MARKER = "[offloaded: "
"""Prefix of every placeholder this module writes."""

REFERENCES_HEADING = "## Offloaded References"
"""Heading of the reference list a compaction message carries."""

MAX_REFERENCES = 50
"""Most references one compaction message lists; the newest are kept."""

_UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9_.-]")
_PLACEHOLDER_HEADER = re.compile(
    r"^\[offloaded: (?P<reference>.+?) \| (?P<lines>\d+) lines / "
    r"(?P<chars>\d+) chars\]$"
)
_REFERENCE_LINE = re.compile(
    r"^- (?P<reference>.+?) \((?P<lines>\d+) lines, (?P<chars>\d+) chars\)"
    r"(?: - output of (?P<name>.+))?$"
)


@dataclass(frozen=True, slots=True)
class OffloadEntry:
    """One tool result that was moved out of the conversation.

    :param reference: Where the full text can be read back, as the
        store reported it.
    :param lines: Line count of the full text.
    :param chars: Character count of the full text.
    :param tool_call_id: The call the result answered, when known.
    :param tool_name: The tool that produced it, when known.
    """

    reference: str
    lines: int
    chars: int
    tool_call_id: str = ""
    tool_name: str = ""


@runtime_checkable
class OffloadStore(Protocol):
    """Somewhere a tool result's full text can be kept and read back."""

    async def put(self, key: str, content: str) -> str:
        """Keep *content* under *key* and return its reference.

        :param key: Letters, digits, ``_``, ``.`` and ``-`` only, derived
            from the content — a store may skip the write when it already
            holds *key*.
        :param content: The full tool result.
        :returns: A path the model can pass to ``read_file``.
        :raises Exception: The content could not be kept. The message is
            then left in the conversation unchanged.
        """
        ...


@dataclass(frozen=True, slots=True)
class Offloader:
    """A store plus the rule for what is worth moving into it.

    :param store: Where full texts go.
    :param min_tokens: A tool result is moved only when its estimated
        size exceeds this.
    :param preview_lines: Leading lines the placeholder shows.
    :param preview_chars: Ceiling on the preview, whatever the line count.
    """

    store: OffloadStore
    min_tokens: int = 1000
    preview_lines: int = 10
    preview_chars: int = 800

    def __post_init__(self) -> None:
        for name in ("min_tokens", "preview_lines", "preview_chars"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True, slots=True)
class OffloadOutcome:
    """What :func:`offload_messages` did.

    :param messages: The input, with moved results replaced by
        placeholders. Same length and order as the input.
    :param entries: One per moved result, in message order.
    :param failures: One sentence per result the store refused.
    """

    messages: tuple[Message, ...]
    entries: tuple[OffloadEntry, ...] = ()
    failures: tuple[str, ...] = ()


def is_offloaded(message: Message) -> bool:
    """Whether *message* already carries a placeholder."""
    return message.content.startswith(OFFLOAD_MARKER)


def offload_key(tool_call_id: str, content: str) -> str:
    """The store key for a tool result: its call id plus a content digest.

    The digest makes the key follow the content, so two results sharing
    a call id never share a file, and a result without one still has a
    key.
    """
    digest = hashlib.sha256(content.encode("utf-8", "surrogatepass")).hexdigest()
    stem = _UNSAFE_KEY_CHARS.sub("_", tool_call_id).strip("._-")[:64]
    return f"{stem}-{digest[:16]}" if stem else digest[:16]


def _line_count(text: str) -> int:
    return text.count("\n") + 1


def render_placeholder(
    entry: OffloadEntry,
    content: str,
    *,
    preview_lines: int,
    preview_chars: int,
) -> str:
    """The text that stands in for *content* once it has been moved."""
    lines = content.split("\n")[:preview_lines]
    preview = "\n".join(lines)
    clipped = len(preview) > preview_chars
    if clipped:
        preview = preview[:preview_chars]
    shown = f"first {len(lines)} of {entry.lines} lines"
    parts = [
        f"{OFFLOAD_MARKER}{entry.reference} | {entry.lines} lines / "
        f"{entry.chars} chars]",
        f"Preview ({shown}{', clipped' if clipped else ''}):",
        preview,
        f"... full output saved to {entry.reference}; read it with read_file",
    ]
    return "\n".join(parts)


def parse_placeholder(message: Message) -> OffloadEntry | None:
    """Recover the entry behind a placeholder, or ``None`` if it is not one."""
    if not is_offloaded(message):
        return None
    header = message.content.split("\n", 1)[0]
    match = _PLACEHOLDER_HEADER.match(header)
    if match is None:
        return None
    return OffloadEntry(
        reference=match["reference"],
        lines=int(match["lines"]),
        chars=int(match["chars"]),
        tool_call_id=message.tool_call_id,
        tool_name=message.name,
    )


def render_references(entries: Sequence[OffloadEntry]) -> str:
    """A ``## Offloaded References`` block, or ``""`` for no entries."""
    if not entries:
        return ""
    lines = [REFERENCES_HEADING]
    for entry in entries[-MAX_REFERENCES:]:
        line = f"- {entry.reference} ({entry.lines} lines, {entry.chars} chars)"
        if entry.tool_name:
            line += f" - output of {entry.tool_name}"
        lines.append(line)
    return "\n".join(lines)


def parse_references(text: str) -> tuple[OffloadEntry, ...]:
    """Read back the block :func:`render_references` wrote into *text*."""
    entries: list[OffloadEntry] = []
    inside = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == REFERENCES_HEADING:
            inside = True
            continue
        if not inside:
            continue
        if stripped.startswith("#"):
            break
        match = _REFERENCE_LINE.match(stripped)
        if match is not None:
            entries.append(
                OffloadEntry(
                    reference=match["reference"],
                    lines=int(match["lines"]),
                    chars=int(match["chars"]),
                    tool_name=match["name"] or "",
                )
            )
    return tuple(entries)


async def offload_messages(
    messages: Sequence[Message],
    offloader: Offloader,
    *,
    counter: TokenCounter | None = None,
) -> OffloadOutcome:
    """Move every oversized tool result in *messages* into the store.

    A tool result is moved when it is not already a placeholder and its
    estimated size exceeds :attr:`Offloader.min_tokens`. A result the
    store refuses stays as it was and is reported in
    :attr:`OffloadOutcome.failures`; nothing here raises except
    :exc:`asyncio.CancelledError`.
    """
    count = estimate_text_tokens if counter is None else counter.count_text
    moved = list(messages)
    entries: list[OffloadEntry] = []
    failures: list[str] = []
    for index, message in enumerate(messages):
        if message.role != Role.TOOL or is_offloaded(message):
            continue
        if count(message.content) <= offloader.min_tokens:
            continue
        key = offload_key(message.tool_call_id, message.content)
        try:
            reference = await offloader.store.put(key, message.content)
        except Exception as error:
            failures.append(
                f"offloading {message.tool_call_id or key} failed: {error!r}"
            )
            continue
        entry = OffloadEntry(
            reference=reference,
            lines=_line_count(message.content),
            chars=len(message.content),
            tool_call_id=message.tool_call_id,
            tool_name=message.name,
        )
        moved[index] = message.replace(
            content=render_placeholder(
                entry,
                message.content,
                preview_lines=offloader.preview_lines,
                preview_chars=offloader.preview_chars,
            )
        )
        entries.append(entry)
    return OffloadOutcome(tuple(moved), tuple(entries), tuple(failures))
