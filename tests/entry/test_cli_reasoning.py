"""The terminal's reasoning block: one header, a gutter, no stray gaps.

Before this writer the REPL printed reasoning through the shared text
renderer, which labelled every emission —— and unbatched, an emission is
one token. What a person saw was ``[reasoning] The[reasoning]  user``.
These tests pin the shape that replaced it, character for character,
because "more readable" is only a property if something fails when it
stops being true.
"""

from __future__ import annotations

import io

from omicsclaw.entry.cli._reasoning import REASONING_HEADER, ReasoningStreamWriter
from omicsclaw.entry.cli._screen import Screen


def _written(*deltas: str, finish: bool = True) -> str:
    buffer = io.StringIO()
    writer = ReasoningStreamWriter(Screen.into(buffer, width=100).console)
    for delta in deltas:
        writer.write(delta)
    if finish:
        writer.finish()
    return buffer.getvalue()


def test_a_block_has_one_header_and_a_gutter_on_every_line():
    out = _written("The", " user", " asks.", "\n", "Read", " the README.")

    assert out == (
        f"{REASONING_HEADER}\n"
        "│ The user asks.\n"
        "│ Read the README.\n"
    )
    assert "[reasoning]" not in out


def test_a_token_split_across_deltas_is_not_split_on_screen():
    """The gutter belongs to a *line*, and a delta is not a line."""
    out = _written("介绍", "当前", "框架", "\n")

    assert out == f"{REASONING_HEADER}\n│ 介绍当前框架\n"


def test_paragraphs_are_one_blank_gutter_apart_however_many_newlines():
    out = _written("First.", "\n\n\n\n", "Second.")

    assert out == f"{REASONING_HEADER}\n│ First.\n│\n│ Second.\n"


def test_no_empty_gutter_under_the_header_or_at_the_end():
    out = _written("\n\n", "Only line.", "\n\n")

    assert out == f"{REASONING_HEADER}\n│ Only line.\n"


def test_whitespace_alone_opens_no_block():
    """A header over nothing reads as a model that thought and said nothing."""
    buffer = io.StringIO()
    writer = ReasoningStreamWriter(Screen.into(buffer).console)
    writer.write("\n  \n")

    assert writer.finish() is False
    assert buffer.getvalue() == ""


def test_finish_reports_whether_a_block_closed_and_reopens_with_a_header():
    buffer = io.StringIO()
    writer = ReasoningStreamWriter(Screen.into(buffer, width=100).console)
    writer.write("one")

    assert writer.is_open
    assert writer.finish() is True
    assert writer.finish() is False

    writer.write("two")
    writer.finish()

    assert buffer.getvalue().count(REASONING_HEADER) == 2
