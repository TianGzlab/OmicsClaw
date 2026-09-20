"""Plan 0030 task B: the seams through which outside knowledge arrives.

Everything a system prompt is made of — a persona file, a skills index,
today's date, long-term memory — is knowledge this package is forbidden
to hold. :data:`SectionSource` is the one shape all of it comes through,
and the two properties that make it work are tested here: it is called
again on every render, and it is never a snapshot.
"""

from __future__ import annotations

import dataclasses
import pathlib

import pytest

from omicsclaw.context.sections import Section, static, text_from_file


def test_static_hands_back_exactly_what_it_was_given():
    source = static("## 项目规范\n\n保持简洁。")

    assert source() == "## 项目规范\n\n保持简洁。"


def test_a_file_source_is_read_again_on_every_call(tmp_path: pathlib.Path):
    """The reason a source is a callable at all (``builder.go:56-59``).

    ``memory_write`` rewrites ``MEMORY.md`` *while the agent is
    running*, ``create_omics_skill`` adds skills, ``edit_file`` rewrites
    ``AGENTS.md``. A source read once at construction would have the
    agent reasoning from the version before the one it just wrote, and
    nothing would look wrong.
    """
    path = tmp_path / "AGENTS.md"
    path.write_text("first", encoding="utf-8")
    source = text_from_file(path)

    assert source() == "first"

    path.write_text("second", encoding="utf-8")

    assert source() == "second"


def test_a_file_that_is_not_there_yields_an_empty_section(
    tmp_path: pathlib.Path,
):
    """Absence is a state, not a failure — ``builder.go:107-110``.

    The harness skips a missing ``AGENTS.md`` in silence, and plan 0030
    §5.1 asks for the same of a missing ``SOUL.md``: the persona section
    is simply empty and the caller supplies its own fallback, because
    the three-level fallback chain the replaced layer had was a policy
    and policies live above this line.
    """
    assert text_from_file(tmp_path / "nothing-here.md")() == ""


def test_a_file_that_cannot_be_decoded_raises(tmp_path: pathlib.Path):
    """The other half: a *failure* is loud, and nothing here logs.

    The replaced layer caught everything a block raised, logged a
    warning and carried on, which turned "``SOUL.md`` is unreadable"
    into "the agent has no persona" — a correctness loss nobody finds
    out about. A source is an arbitrary callable, so swallowing its
    exceptions would also be swallowing the caller's.
    """
    path = tmp_path / "SOUL.md"
    path.write_bytes(b"\xff\xfe\x00 not utf-8")

    with pytest.raises(UnicodeDecodeError):
        text_from_file(path)()


def test_a_section_cannot_be_edited_after_it_is_built():
    """Frozen, like every value in this package and for the same reason."""
    section = Section(key="persona", heading="", source=static("x"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        section.key = "other"  # type: ignore[misc]
