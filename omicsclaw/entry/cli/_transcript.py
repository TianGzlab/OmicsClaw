"""Tool calls as they read in the terminal transcript, after the fact.

Turns one ``TOOL_START`` or ``TOOL_RESULT`` frame into the lines a
terminal prints for it: the neutral head line it is handed, a call
number, the call's arguments and a bounded preview of its output.
Every other frame comes back as the single line it arrived as.

Behaviour that decides how this is called:

- a result is paired to its call through ``ToolResult.tool_call_id``, so
  the number is right even when two calls to one tool finish in the
  other order; a result whose call is unknown is left unnumbered rather
  than given a number that would be wrong;
- ``detail=False`` keeps arguments and output off the screen entirely,
  leaving only the head and the number, for a deployment that must not
  put payload in a scrollback;
- tools in :data:`_RENDERED_ELSEWHERE` never show either, because the
  surface prints their payload itself;
- every line is made inert by
  :func:`~omicsclaw.entry.display.inert_line` before it is shown, the
  head included, and a multi-line head (an approval card) by
  :func:`~omicsclaw.entry.display.inert_prose`: a tool's output can carry
  ANSI, and a terminal executes what it is sent;
- in arguments that decode as JSON, the value under every credential-named
  key is hidden by :func:`~omicsclaw.tools.preview.redact_credentials`;
- arguments that do not are shown only as their length, by
  :func:`~omicsclaw.entry.display.unreadable_arguments_note`, as on the
  approval card, and nothing here raises on any input.

Every line returned is a :class:`~rich.text.Text`, so a bracket in an
argument or in output is never read as rich markup.
"""

from __future__ import annotations

import json
from typing import Any

from rich.text import Text

from omicsclaw.entry.display import (
    inert_line,
    inert_prose,
    unreadable_arguments_note,
)
from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.planning import PLAN_WRITE_TOOL_NAME
from omicsclaw.tools.preview import redact_credentials

__all__ = [
    "ARGUMENT_CHARS",
    "OUTPUT_CHARS",
    "OUTPUT_LINES",
    "ToolTranscript",
]

ARGUMENT_CHARS = 120
"""Characters of the argument preview kept on the call line.

Enough for the ``command`` of an ordinary ``bash`` call or a URL, and
short enough that the line does not wrap on an 80-column terminal twice
over. A truncated preview is marked, because an unmarked one reads as
the whole argument and sends a person looking for a bug in a command
that was never run that way.
"""

OUTPUT_LINES = 3
"""Lines of a tool's output shown under its result.

Three is what fits under a result without the transcript becoming the
output rather than a log of it. The model still gets all of it; this is
the person's preview, and ``read_file`` is how they see the rest.
"""

OUTPUT_CHARS = 160
"""Characters kept from each previewed output line."""

_RENDERED_ELSEWHERE = frozenset({PLAN_WRITE_TOOL_NAME})
"""Tools whose payload the surface prints itself, so neither half is
previewed here and only the head line remains.

``plan_write`` is the one: :meth:`~omicsclaw.entry.cli._repl.Repl.
_show_plan` prints the resulting list underneath in the shape a person
reads, its output is that list as JSON, and its arguments are the items
being changed — previewing either would put the same plan on screen
twice, in the worse of the two forms.
"""

_ELLIPSIS = "…"

_INDENT = "      "
"""Where an output preview sits: under the head, clear of the ``(n)``
column, so a block of output reads as belonging to the line above it
rather than as four more events."""


def _short(value: str, limit: int) -> str:
    """*value* as one inert line, cut to *limit* and marked when cut.

    The line is :func:`~omicsclaw.entry.display.inert_line`'s, with runs of
    spaces folded to one.
    """
    flat = " ".join(inert_line(str(value)).split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + _ELLIPSIS


def _arguments(raw: str) -> str:
    """A compact ``k=v`` preview of one call's JSON arguments.

    Arguments that decode as JSON have every credential-named value
    replaced by :func:`~omicsclaw.tools.preview.redact_credentials`, at any
    depth. Arguments that do not are shown as
    :func:`~omicsclaw.entry.display.unreadable_arguments_note`, their
    length only. Never raises.
    """
    text = (raw or "").strip()
    if not text or text == "{}":
        return ""
    try:
        decoded: Any = redact_credentials(json.loads(text))
        if not isinstance(decoded, dict):
            return _short(json.dumps(decoded, ensure_ascii=False), ARGUMENT_CHARS)
        parts = []
        for key, value in decoded.items():
            if isinstance(value, str):
                parts.append(f'{key}="{value}"')
            else:
                parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    except (ValueError, TypeError, RecursionError):
        return unreadable_arguments_note(raw)
    return _short("  ".join(parts), ARGUMENT_CHARS)


def _output_preview(output: str) -> tuple[str, ...]:
    """The first few meaningful lines of a result, flattened and cut.

    Leading blank lines are dropped rather than shown: a tool whose
    output starts with a newline would otherwise spend the whole preview
    on nothing.
    """
    lines = [line for line in (output or "").splitlines() if line.strip()]
    if not lines:
        return ()
    kept = [_short(line, OUTPUT_CHARS) for line in lines[:OUTPUT_LINES]]
    if len(lines) > OUTPUT_LINES:
        kept.append(f"{_ELLIPSIS} {len(lines) - OUTPUT_LINES} more line(s)")
    return tuple(kept)


class ToolTranscript:
    """Numbers each tool call of one exchange and pairs its result back.

    One instance per exchange, like the renderer and the markdown
    formatter it is printed beside: the numbers restart because they are
    a way to read *this* answer, not an identifier anybody keeps.
    """

    __slots__ = ("_detail", "_next", "_numbers")

    def __init__(self, *, detail: bool = True) -> None:
        """
        :param detail: Show each call's arguments and a preview of its
            output. ``False`` leaves only the head line and the number.
        """
        self._numbers: dict[str, int] = {}
        self._next = 1
        self._detail = detail

    def render(self, event: TurnEvent, head: str) -> tuple[Text, ...]:
        """The lines a terminal prints for *event*, given its neutral *head*.

        :param event: The frame being printed.
        :param head: What
            :class:`~omicsclaw.entry.render.TextRenderer` made of it.
        :returns: One line for anything that is not a tool call, and for
            one that is, the head with its call number and argument
            preview plus any output preview beneath it.
        """
        if event.type is TurnEventType.TOOL_START:
            return self._call(event, head)
        if event.type is TurnEventType.TOOL_RESULT:
            return self._result(event, head)
        return (Text(inert_prose(head), style="dim"),)

    def _call(self, event: TurnEvent, head: str) -> tuple[Text, ...]:
        call = event.engine.tool_call if event.engine is not None else None
        number = self._number_for(call.id if call is not None else "")
        line = Text(_label(number), style="dim")
        line.append(inert_line(head), style="dim")
        name = call.name if call is not None else ""
        preview = (
            _arguments(call.arguments if call is not None else "")
            if self._detail and name not in _RENDERED_ELSEWHERE
            else ""
        )
        if preview:
            line.append("  ")
            line.append(preview, style="dim cyan")
        return (line,)

    def _result(self, event: TurnEvent, head: str) -> tuple[Text, ...]:
        result = event.engine.tool_result if event.engine is not None else None
        number = self._numbers.get(
            result.tool_call_id if result is not None else "", 0
        )
        failed = result is not None and result.is_error
        line = Text(_label(number), style="dim")
        line.append(inert_line(head), style="dim red" if failed else "dim")
        lines = [line]
        style = "dim red" if failed else "dim"
        name = result.name if result is not None else ""
        previews = (
            _output_preview(result.output if result is not None else "")
            if self._detail and name not in _RENDERED_ELSEWHERE
            else ()
        )
        for preview in previews:
            lines.append(Text(_INDENT + preview, style=style))
        return tuple(lines)

    def _number_for(self, call_id: str) -> int:
        """This call's number, minting one the result can find again.

        A call with no id still gets a number so the transcript reads the
        same; its result simply cannot be paired back, which is reported
        as a missing number rather than as a wrong one.
        """
        number = self._next
        self._next += 1
        if call_id:
            self._numbers[call_id] = number
        return number


def _label(number: int) -> str:
    """``(3) `` for a numbered call, or blank padding for an unpaired one.

    Padded to a fixed width either way, so the heads line up into a
    column whether or not every result found its call.
    """
    return f"({number}) " if number else "    "
