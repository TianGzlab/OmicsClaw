"""The model's reasoning, set apart from its answer as it streams.

Reasoning arrives the way the answer does, one delta at a time, and the
shared :class:`~omicsclaw.entry.render.TextRenderer` can only mark it by
prefixing text: unbatched, that meant ``[reasoning]`` in front of every
token, so a paragraph of thought read as a column of labels. A terminal
can do better than a label, and this writer is that better:

.. code-block:: text

    ✻ Thinking
    │ The user wants the core architecture. README first, then
    │ SPEC.md and AGENTS.md.
    │
    │ Let me look.

    I'll explore the repository structure first.

One header per block, a dim gutter on every line, and a blank line
before whatever comes next. Dim because the reasoning is the working and
the answer is the result, and the eye should land on the result; a
gutter rather than indentation because a wrapped line still shows which
block it belongs to at its start.

Everything printed is first made inert by
:func:`~omicsclaw.entry.display.inert_prose`: line breaks are kept, every
other control or format character is written as an escape.

**Not Markdown.** The answer goes through
:class:`~omicsclaw.entry.cli.MarkdownStreamFormatter`, which holds back
any half-line that could still become markup. Reasoning is not a
document the model is presenting, and holding it back would make the
thinking appear in bursts —— the opposite of watching it happen.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from omicsclaw.entry.display import inert_prose

__all__ = ["REASONING_HEADER", "ReasoningStreamWriter"]

REASONING_HEADER = "✻ Thinking"
_GUTTER = "│ "
_STYLE = "dim"


class ReasoningStreamWriter:
    """Writes one or more reasoning blocks to a console, delta by delta.

    A block opens on the first non-blank delta and closes on
    :meth:`finish`. Between the two, every line starts with the gutter.
    Blank lines are drawn only between two lines of thought, and a run
    of them as one: models separate paragraphs with anywhere from one to
    three newlines and the difference carries nothing, while an empty
    gutter under the header or at the end of a block is a gap the reader
    has to jump.
    """

    __slots__ = ("_at_line_start", "_blank_pending", "_carry", "_console", "_open")

    def __init__(self, console: Any) -> None:
        self._console = console
        self._open = False
        self._at_line_start = True
        self._blank_pending = False
        self._carry = ""

    @property
    def is_open(self) -> bool:
        """Whether a block has been started and not yet finished."""
        return self._open

    def write(self, delta: str) -> None:
        """Take one delta of reasoning and print it.

        A ``\\r`` ending the delta is held back until the next one, so that
        a ``\\r\\n`` split across two deltas is read as one line break.
        """
        text = self._carry + str(delta or "")
        self._carry = "\r" if text.endswith("\r") else ""
        if self._carry:
            text = text[:-1]
        self._write(text)

    def finish(self) -> bool:
        """End the current block. Returns whether there was one to end.

        Ends the line if the block stopped mid-line, and nothing more:
        what follows the block decides how much space it wants, which is
        why the caller is told that a block closed. A blank line the
        model sent last is dropped rather than drawn, so a block never
        ends on an empty gutter.
        """
        if self._carry:
            self._carry = ""
            self._write("\r")
        if not self._open:
            return False
        if not self._at_line_start:
            self._console.print()
        self._open = False
        self._at_line_start = True
        self._blank_pending = False
        return True

    # ---- internals ------------------------------------------------------

    def _write(self, text: str) -> None:
        """Print *text*, made inert, one line at a time."""
        for piece in inert_prose(text).splitlines(keepends=True):
            self._write_piece(piece)

    def _write_piece(self, piece: str) -> None:
        body = piece.rstrip("\r\n")
        ends_line = body != piece
        if self._at_line_start and not body.strip():
            # A blank line is only drawn once something follows it:
            # nothing before the first line of thought, one between
            # paragraphs however many the model sent, none at the end.
            if ends_line and self._open:
                self._blank_pending = True
            return
        if not self._open:
            self._console.print(Text(REASONING_HEADER, style=f"{_STYLE} bold"))
            self._open = True
        elif self._at_line_start and self._blank_pending:
            self._console.print(Text(_GUTTER.rstrip(), style=_STYLE))
        self._blank_pending = False
        if self._at_line_start:
            self._console.print(Text(_GUTTER, style=_STYLE), end="")
        self._console.print(Text(body, style=_STYLE), end="", soft_wrap=True)
        self._at_line_start = ends_line
        if ends_line:
            self._console.print()
