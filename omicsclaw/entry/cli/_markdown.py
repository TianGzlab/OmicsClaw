"""Streaming Markdown for a terminal: emit what is safe, hold the rest.

**Ported** from ``omicsclaw/surfaces/cli/interactive.py`` — the regex block
at its lines 36-50 and the renderer at its lines 417-556 — with two
changes and no third:

1. the :class:`rich.console.Console` is a constructor argument rather than
   a module global, so a test can read what was written instead of
   capturing a process's stdout, and so a single-shot run and a REPL can
   render to different places;
2. lines over 88 columns are wrapped (plan 0031 §9-3).

**Why a streaming formatter and not ``rich.markdown.Markdown``.** The
model's answer arrives one delta at a time and a Markdown parser needs a
whole document. The rule this file implements instead is: a *complete
line* can be rendered, and of an incomplete line only the prefix that
cannot still turn into markup — :func:`_find_safe_plain_prefix_length`
stops at the first character that could begin an emphasis, a link or a
fence. Everything after it waits for the newline that settles what it
was. The cost is that a paragraph with no newline sits in the buffer until
:meth:`MarkdownStreamFormatter.finish`; the alternative is printing
``**bold`` and then having to unprint it.
"""

from __future__ import annotations

import re
from typing import Any

from rich.text import Text

__all__ = ["MarkdownStreamFormatter", "render_markdown_line"]

_INLINE_MARKDOWN_TOKEN_RE = re.compile(
    r"(?P<link>\[(?P<link_label>[^\]\n]+)\]\((?P<link_url>[^)\n]+)\))"
    r"|(?P<bold>\*\*(?P<bold_text>[^*\n]+)\*\*)"
    r"|(?P<underline>__(?P<underline_text>[^_\n]+)__)"
    r"|(?P<code>`(?P<code_text>[^`\n]+)`)"
    r"|(?P<italic>(?<!\*)\*(?P<italic_text>[^*\n]+)\*(?!\*))"
    r"|(?P<italic_u>(?<!_)_(?P<italic_u_text>[^_\n]+)_(?!_))"
)
_STRONG_LINE_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")
_ATX_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
_BULLET_LINE_RE = re.compile(r"^(?P<indent>\s*)[-*+]\s+(?P<body>.*)$")
_NUMBERED_LINE_RE = re.compile(r"^(?P<indent>\s*)(?P<number>\d+)\.\s+(?P<body>.*)$")
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s*>\s?(?P<body>.*)$")
_MARKDOWN_LINE_START_RE = re.compile(
    r"^\s*(?:[-*+]\s|#{1,6}\s|>\s|\d+\.\s|\*\*|__|`{1,3})"
)
_UNCERTAIN_MARKDOWN_PREFIX_RE = re.compile(r"^\s*(?:[-*+#>]?|\d+\.?)?\s*$")


def _append_inline_markdown(target: Text, source: str) -> None:
    cursor = 0
    for match in _INLINE_MARKDOWN_TOKEN_RE.finditer(source):
        start, end = match.span()
        if start > cursor:
            target.append(source[cursor:start])

        if match.group("link"):
            target.append(match.group("link_label"), style="underline cyan")
            target.append(f" ({match.group('link_url')})", style="dim")
        elif match.group("bold"):
            target.append(match.group("bold_text"), style="bold")
        elif match.group("underline"):
            target.append(match.group("underline_text"), style="bold")
        elif match.group("code"):
            target.append(match.group("code_text"), style="bold yellow")
        elif match.group("italic"):
            target.append(match.group("italic_text"), style="italic")
        elif match.group("italic_u"):
            target.append(match.group("italic_u_text"), style="italic")

        cursor = end

    if cursor < len(source):
        target.append(source[cursor:])


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def render_markdown_line(line: str) -> Text:
    """One line of Markdown as styled :class:`rich.text.Text`."""
    body, ending = _split_line_ending(line)
    output = Text()

    if not body.strip():
        if ending:
            output.append(ending)
        return output

    stripped = body.strip()
    if stripped.startswith("```"):
        if ending:
            output.append(ending)
        return output

    strong_match = _STRONG_LINE_RE.match(body)
    atx_heading_match = _ATX_HEADING_RE.match(body)
    bullet_match = _BULLET_LINE_RE.match(body)
    numbered_match = _NUMBERED_LINE_RE.match(body)
    blockquote_match = _BLOCKQUOTE_LINE_RE.match(body)

    if strong_match:
        _append_inline_markdown(output, strong_match.group(1).strip())
        output.stylize("bold cyan", 0, len(output))
    elif atx_heading_match:
        _append_inline_markdown(output, atx_heading_match.group(1).strip())
        output.stylize("bold cyan", 0, len(output))
    elif bullet_match:
        indent = bullet_match.group("indent")
        output.append(f"{indent}- ", style="dim")
        _append_inline_markdown(output, bullet_match.group("body"))
    elif numbered_match:
        indent = numbered_match.group("indent")
        number = numbered_match.group("number")
        output.append(f"{indent}{number}. ", style="dim")
        _append_inline_markdown(output, numbered_match.group("body"))
    elif blockquote_match:
        output.append("| ", style="dim")
        _append_inline_markdown(output, blockquote_match.group("body"))
    else:
        _append_inline_markdown(output, body)

    if ending:
        output.append(ending)
    return output


def _find_safe_plain_prefix_length(buffer: str) -> int:
    if not buffer:
        return 0

    if _MARKDOWN_LINE_START_RE.match(buffer) or _UNCERTAIN_MARKDOWN_PREFIX_RE.match(
        buffer
    ):
        return 0

    positions: list[int] = []
    for marker in ("**", "__", "```", "`", "[", "*", "_"):
        idx = buffer.find(marker)
        if idx >= 0:
            positions.append(idx)

    if positions:
        first = min(positions)
        return first if first > 0 else 0

    return len(buffer)


class MarkdownStreamFormatter:
    """Accumulates deltas and prints the part that has stopped moving.

    Stateful across calls, like
    :class:`~omicsclaw.entry.render.TextRenderer` and for the same reason:
    a token is not a unit of meaning. Unlike that class this one *writes*,
    because the decision it makes — how much of a half-written line is
    safe to show — is only worth making where the cursor is.
    """

    def __init__(self, console: Any) -> None:
        self._console = console
        self._pending = ""

    def write(self, chunk: str) -> None:
        """Take one delta and print whatever it made safe."""
        self._pending += str(chunk or "")
        self._emit_available()

    def finish(self) -> None:
        """Print the tail, markup or not. The answer is over."""
        if not self._pending:
            return
        self._emit_rendered(self._pending)
        self._pending = ""

    def _emit_available(self) -> None:
        while True:
            newline_index = self._pending.find("\n")
            if newline_index < 0:
                break
            line = self._pending[: newline_index + 1]
            self._pending = self._pending[newline_index + 1 :]
            self._emit_rendered(line)

        safe_prefix_len = _find_safe_plain_prefix_length(self._pending)
        if safe_prefix_len <= 0:
            return
        plain_prefix = self._pending[:safe_prefix_len]
        self._pending = self._pending[safe_prefix_len:]
        self._console.print(Text(plain_prefix), end="", soft_wrap=True)

    def _emit_rendered(self, line: str) -> None:
        self._console.print(render_markdown_line(line), end="", soft_wrap=True)
