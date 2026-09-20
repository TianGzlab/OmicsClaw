"""YAML frontmatter parsing for ``SKILL.md`` files.

Supports the subset the skill headers actually use:

* ``---`` on the first line and a closing ``---`` on its own line;
* ``key: value`` at column zero, with matching surrounding quotes removed;
* folded continuation — indented lines join the preceding scalar with
  single spaces;
* block sequences — ``- item`` lines collect into a tuple;
* ``|`` and ``>`` block scalars, dedented, literal and folded;
* ``#`` comment lines at column zero.

Nested mappings, anchors, aliases, flow collections, tags and multi
document streams are not supported; a key using one is dropped rather
than mis-parsed. An inline ``# comment`` after a value is kept as part of
the value.

Nothing here touches the filesystem — :func:`parse_frontmatter` takes text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

__all__ = ["Frontmatter", "parse_frontmatter"]

DELIMITER = "---"
"""A line equal to this opens and closes the header."""

_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.\-]*):(.*)$")
"""A mapping key at column zero."""

_BLOCK_SCALAR = re.compile(r"^([|>])[0-9]*[+\-]?$|^([|>])[+\-]?[0-9]*$")
"""``|`` / ``>`` with optional indentation and chomping indicators.

Only the style character is read; the indicators are recognised so the
header is not mistaken for a plain scalar, but they are not honoured.
"""


@dataclass(frozen=True, slots=True)
class Frontmatter:
    """A parsed header and the text that followed it."""

    fields: Mapping[str, str | tuple[str, ...]]
    """Scalars as :class:`str`, sequences as :class:`tuple`. Read-only."""

    body: str
    """Everything after the closing delimiter, with one leading newline
    removed. Otherwise verbatim: not stripped, dedented or reflowed."""

    has_frontmatter: bool = False
    """Whether delimiters were found, distinguishing "no header" from "a
    header with nothing recognisable in it"."""

    def text(self, key: str, default: str = "") -> str:
        """Return the scalar at *key*, or *default* if absent or a sequence."""
        value = self.fields.get(key)
        return value if isinstance(value, str) else default

    def items(self, key: str) -> tuple[str, ...]:
        """Return the sequence at *key*.

        A non-empty scalar answers as a one-element tuple; an absent or
        empty value answers ``()``.
        """
        value = self.fields.get(key)
        if isinstance(value, tuple):
            return value
        if isinstance(value, str) and value:
            return (value,)
        return ()


def parse_frontmatter(content: str) -> Frontmatter:
    """Split *content* into its header fields and its body.

    A file with no opening delimiter, or no closing one, is treated as
    having no frontmatter: the returned :attr:`Frontmatter.body` is the
    whole of *content* and :attr:`Frontmatter.fields` is empty.

    Never raises. Any construct the subset does not cover leaves its key
    out of :attr:`Frontmatter.fields`.
    """
    lines = content.split("\n")
    if not lines or lines[0].rstrip("\r") != DELIMITER:
        return Frontmatter(MappingProxyType({}), content)

    close = _closing_index(lines)
    if close is None:
        return Frontmatter(MappingProxyType({}), content)

    body = "\n".join(lines[close + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    return Frontmatter(MappingProxyType(_parse_fields(lines[1:close])), body, True)


def _closing_index(lines: list[str]) -> int | None:
    """Return the index of the closing delimiter, or ``None`` if unclosed."""
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r") == DELIMITER:
            return index
    return None


class _Accumulator:
    """The key currently being read and the value collected for it so far."""

    def __init__(self) -> None:
        self.fields: dict[str, str | tuple[str, ...]] = {}
        self.key: str | None = None
        self.style: str | None = None
        self.parts: list[str] = []
        self.literal = True

    def start(self, key: str, rest: str) -> None:
        """Commit any pending key and begin *key*, whose first line is *rest*.

        An empty *rest* leaves the style undecided: a sequence and a
        nested mapping are only distinguishable from the next line.
        """
        self.take()
        self.key = key
        if not rest:
            self.style = "pending"
        elif _BLOCK_SCALAR.match(rest):
            self.style = "block"
            self.literal = rest[0] == "|"
        else:
            self.style = "scalar"
            self.parts.append(rest)

    def take(self) -> None:
        """Commit the pending key, then reset. A dropped key is discarded."""
        if self.key is not None and self.style != "drop":
            if self.style == "sequence":
                self.fields[self.key] = tuple(self.parts)
            elif self.style == "block":
                self.fields[self.key] = _join_block(self.parts, self.literal)
            else:
                self.fields[self.key] = _unquote(" ".join(self.parts))
        self.key = None
        self.style = None
        self.parts = []
        self.literal = True


def _parse_fields(lines: list[str]) -> dict[str, str | tuple[str, ...]]:
    """Parse header *lines* into a mapping, in the order the keys appear."""
    state = _Accumulator()

    for raw in lines:
        line = raw.rstrip("\r")
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if state.style == "block":
            # A block scalar owns every blank or indented line under it and
            # ends at the first line back at column zero, which is then
            # re-read below as whatever it actually is.
            if not stripped or indent > 0:
                state.parts.append(line)
                continue
            state.take()

        if not stripped:
            # A blank line ends a folded scalar rather than folding into it.
            state.take()
            continue

        if indent == 0 and stripped.startswith("#"):
            state.take()
            continue

        match = _KEY.match(line) if indent == 0 else None
        if match is not None:
            state.start(match.group(1), match.group(2).strip())
            continue

        if state.key is None:
            continue

        if state.style == "scalar" and indent > 0:
            state.parts.append(stripped)
            continue

        if state.style in ("pending", "sequence") and stripped.startswith("-"):
            state.style = "sequence"
            item = stripped[1:].strip()
            if item:
                state.parts.append(_unquote(item))
            continue

        if state.style == "pending":
            # An indented non-sequence line under a bare key is a nested
            # mapping; drop the key rather than flatten half of it.
            state.style = "drop"

    state.take()
    return state.fields


def _join_block(lines: list[str], literal: bool) -> str:
    """Join a ``|`` or ``>`` block, dedented to its least-indented line.

    *literal* keeps line breaks; otherwise lines fold into paragraphs
    separated by blank lines. Trailing blank lines are dropped.
    """
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""

    base = min(len(line) - len(line.lstrip(" ")) for line in lines if line.strip())
    dedented = [line[base:] if len(line) > base else line.strip() for line in lines]
    if literal:
        return "\n".join(dedented)

    paragraphs: list[str] = []
    current: list[str] = []
    for line in dedented:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs)


def _unquote(value: str) -> str:
    """Strip matching surrounding quotes from *value*.

    Escape sequences inside a double-quoted scalar are not decoded.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value
