"""Reading a sub-agent definition out of a Markdown file with a YAML header.

The supported subset is what an agent file uses and no more:

* ``---`` on the first line and a closing ``---`` on its own line;
* ``key: value`` at column zero, with matching surrounding quotes removed;
* block sequences — ``- item`` lines under a bare key;
* comma-separated scalars, accepted wherever a sequence is.

A key whose value continues onto further lines — a block scalar (``>``,
``|`` and their chomping variants) or a plain scalar folded over an
indented line — is outside that subset, and the **whole key is dropped**
rather than half-read. Keeping the first line would hand back ``'>'`` or
a sentence cut at its first newline, which passes validation and is worse
than the field being absent: an absent ``description`` falls back to the
body's first line and an absent ``name`` to the file's stem.

Everything after the closing delimiter is the sub-agent's system prompt.
Nothing here touches the filesystem; :func:`parse_agent_file` takes text.
"""

from __future__ import annotations

import re
from typing import Mapping

from .definition import InvalidDefinition, SubAgentDefinition

__all__ = ["DELIMITER", "parse_agent_file"]

DELIMITER = "---"
"""A line equal to this opens and closes the header."""

_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.\-]*):(.*)$")

_LIST_FIELDS = ("tools", "disallowed_tools", "skills")

_BLOCK_SCALARS = frozenset({">", "|", ">-", "|-", ">+", "|+"})
"""Indicators announcing a value that continues on the following lines."""


def parse_agent_file(
    content: str,
    *,
    source: str = "",
    fallback_name: str = "",
) -> SubAgentDefinition:
    """Turn one agent file's text into a definition.

    :param content: the whole file, header included.
    :param source: recorded on the definition for diagnostics.
    :param fallback_name: used when the header names none — normally the
        file's stem, so a file that forgot ``name:`` is still reachable.
    :returns: a validated :class:`~omicsclaw.subagent.SubAgentDefinition`.
    :raises ~omicsclaw.subagent.definition.InvalidDefinition: there is no
        header, or the definition it describes does not validate.

    ``description`` falls back to the first non-blank line of the body,
    so a file that only states its instructions still says something the
    model can choose it by.
    """
    fields, body = _split(content)
    if fields is None:
        raise InvalidDefinition(
            "no YAML frontmatter: an agent file opens with a '---' line and "
            "closes the header with another"
        )

    name = _text(fields, "name") or fallback_name
    description = _text(fields, "description") or _first_line(body)
    definition = SubAgentDefinition(
        name=name,
        description=description,
        system_prompt=body.strip(),
        tools=_items(fields, "tools"),
        disallowed_tools=_items(fields, "disallowed_tools"),
        model=_text(fields, "model"),
        max_turns=_int(_text(fields, "max_turns")),
        skills=_items(fields, "skills"),
        source=source,
    )
    definition.validate()
    return definition


def _split(
    content: str,
) -> tuple[Mapping[str, str | tuple[str, ...]] | None, str]:
    """The header fields and the body, or ``(None, content)`` with no header."""
    lines = content.split("\n")
    if not lines or lines[0].rstrip("\r") != DELIMITER:
        return None, content
    close = next(
        (
            index
            for index in range(1, len(lines))
            if lines[index].rstrip("\r") == DELIMITER
        ),
        None,
    )
    if close is None:
        return None, content
    body = "\n".join(lines[close + 1 :])
    return _fields(lines[1:close]), body.removeprefix("\n")


def _fields(lines: list[str]) -> dict[str, str | tuple[str, ...]]:
    """Parse header *lines*; a key outside the subset is dropped entirely.

    A block-scalar indicator, and an indented line under a key that already
    has a scalar, both mean the value carries on past what this parser
    reads — so the key is discarded instead of being truncated.
    """
    parsed: dict[str, str | tuple[str, ...]] = {}
    key = ""
    sequence: list[str] = []
    scalar = False

    for raw in lines:
        line = raw.rstrip("\r")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _KEY.match(line) if not line[:1].isspace() else None
        if match is not None:
            if key and sequence:
                parsed[key] = tuple(sequence)
            key, sequence, scalar = match.group(1), [], False
            value = match.group(2).strip()
            if value in _BLOCK_SCALARS:
                parsed.pop(key, None)
                key = ""
            elif value:
                parsed[key] = _unquote(value)
                scalar = True
            continue
        if not key:
            continue
        if stripped.startswith("-"):
            item = _unquote(stripped[1:].strip())
            if item:
                sequence.append(item)
        elif scalar:
            parsed.pop(key, None)
            key = ""

    if key and sequence:
        parsed[key] = tuple(sequence)
    return parsed


def _text(fields: Mapping[str, str | tuple[str, ...]], key: str) -> str:
    """The scalar at *key*, or ``""`` when absent or a sequence."""
    value = fields.get(key)
    return value.strip() if isinstance(value, str) else ""


def _items(fields: Mapping[str, str | tuple[str, ...]], key: str) -> tuple[str, ...]:
    """The sequence at *key*, accepting a comma-separated scalar as one."""
    value = fields.get(key)
    if isinstance(value, tuple):
        return value
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return ()


def _int(value: str) -> int:
    """*value* as an integer, or ``0`` when it is absent or not a number."""
    try:
        return int(value)
    except ValueError:
        return 0


def _first_line(body: str) -> str:
    """The first non-blank line of *body*, or ``""``."""
    for line in body.split("\n"):
        if line.strip():
            return line.strip()
    return ""


def _unquote(value: str) -> str:
    """Strip matching surrounding quotes from *value*."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value
