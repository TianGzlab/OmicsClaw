"""Contract tests for ``omicsclaw.tools.builtin.read`` (plan 0029 task B).

Three families, and the third is the one that would otherwise be missed.

*What the model is handed.* The line-number prefix, the truncation
notices and the description's warning about that prefix are a **contract
with a tool that does not exist yet** — ``edit`` ships in a later step,
and whoever writes it will read this tool's description rather than plan
0029. So those strings are pinned literally rather than checked for
plausibility (plan 0029 trap 10, Q9).

*What the reference could not tell us.* Every literal taken from
harness9's ``read_file.go`` is re-verified here under Python semantics,
because the one that mattered most — its 512 KiB line ceiling — is a
property of ``bufio.Scanner`` that Python simply does not have (plan 0029
trap 11). A translated-looking implementation that dropped the guard
would pass a test that only asked "does line mode work".

*Refusals, each with a positive twin.* A test suite made only of "this
malicious path is rejected" assertions is green under an implementation
that rejects everything, so every refusal below sits next to a legitimate
path that must still work. That is plan 0029 §10-9, and it is the one
discipline that distinguishes a boundary from a wall.

**The layering rule does not apply to this file**, for the reason
``test_write.py`` and ``test_bash.py`` record: the guard globs
``omicsclaw/tools/**/*.py``, and a test proving a production rule holds
has to be able to see both sides of it.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.schema import ToolCall
from omicsclaw.tools import ApprovalMode, RiskLevel, Tool, ToolRegistry
from omicsclaw.tools._pathlock import PATH_LOCKS, write_lock
from omicsclaw.tools._workspace import (
    PathEscapesWorkspace,
    PathIsSensitive,
    Workspace,
)
from omicsclaw.tools.builtin.read import (
    LINE_NUMBER_WIDTH,
    MAX_LIMIT_BYTES,
    MAX_LINE_CHARS,
    MAX_LINES,
    MAX_READ_BYTES,
    TOOL_NAME,
    numbered_line,
    read_tool,
)
from omicsclaw.tools.context import use_tool_context
from omicsclaw.tools.function_tool import ToolArgumentError

_T = TypeVar("_T")

_DEADLINE = 10.0
"""Seconds. Long enough for a 512 KiB fixture, short enough that a
deadlock is a failing test rather than a hung suite."""


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; the suite drives this way."""
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


def _args(**kwargs: Any) -> str:
    return json.dumps(kwargs)


def _read(workspace: Workspace, **kwargs: Any) -> str:
    return _run(read_tool(workspace).execute(_args(**kwargs)))


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path)


# ---- the numbers, spelled out where they cannot move with the code -------


def test_every_literal_carried_over_is_the_one_the_reference_uses():
    """Plan 0029 §10-8: each borrowed number, pinned against its source.

    **This test exists because of a mutation that survived without it.**
    The behavioural tests above compare what the tool did against the
    module's own constants, which is right for behaviour and worthless as
    a check on the constant: changing ``MAX_READ_BYTES`` to 4,096 moves
    both sides of ``len(body) == MAX_READ_BYTES`` and the suite stays
    green. A borrowed literal has to be asserted somewhere it cannot
    follow the implementation, and this is that somewhere.

    Four of the five are harness9's, re-derived under Python semantics in
    the module's own docstrings. :data:`MAX_LIMIT_BYTES` is **not**: it is
    this repository's existing ``file_read`` ceiling
    (``engineering.py:630``), kept so migration does not remove a guard
    harness9 never had.
    """
    assert MAX_READ_BYTES == 8192  # read_file.go:30
    assert MAX_LINES == 500  # read_file.go:109
    assert MAX_LINE_CHARS == 512 * 1024  # read_file.go:200
    assert LINE_NUMBER_WIDTH == 6  # read_file.go:218
    assert MAX_LIMIT_BYTES == 100_000  # engineering.py:630, not harness9


# ---- the line-number prefix, which ``edit`` has to strip ------------------


def test_the_line_number_prefix_is_six_columns_then_a_tab(tmp_path):
    """Plan 0029 trap 10. **The literal is the deliverable.**

    ``read_file.go:218`` renders ``%6d\\t%s``; ``edit``, a step away, has
    to recognise and remove exactly that when a model pastes a read line
    back as ``source_text``. Asserting on the shape — "starts with
    digits", "contains a tab" — would stay green through a change to
    ``%4d`` or to two spaces, and ``edit`` would then strip the wrong
    number of characters off every line.

    This project's own ``engineering.py`` uses ``f"{index}: {line}"``
    instead, which plan 0029 §6 replaces here deliberately: a tab is one
    separator to strip, while ``": "`` occurs inside real source lines.
    """
    (tmp_path / "a.py").write_text("import os\nx = 1\n")

    output = _read(_workspace(tmp_path), path="a.py", start_line=1)

    assert output == "     1\timport os\n     2\tx = 1\n"


def test_the_prefix_helper_widens_rather_than_truncating_past_six_digits():
    """A seven-digit line number must still be readable, in both languages.

    Go's ``%6d`` is a minimum width, and Python's ``{:6d}`` is the same
    minimum. Pinned because the obvious "fix" for a ragged column is a
    slice, and a truncated line number is worse than a wide one.
    """
    assert numbered_line(7, "x") == "     7\tx\n"
    assert numbered_line(1234567, "x") == "1234567\tx\n"


def test_the_description_warns_that_the_prefix_is_not_part_of_the_code():
    """Plan 0029 Q9. The warning is for a reader who never sees the plan.

    ``read_file.go`` states it twice — once in the tool description the
    model reads and once in a code comment the maintainer reads — and the
    duplication is deliberate, because the two tools ship separately.
    This asserts the model-facing copy, which is the one that has to
    survive a description rewrite.
    """
    description = read_tool().definition().description.lower()

    assert "source_text" in description
    assert "without the line number" in description
    assert "display only" in description


# ---- line mode -----------------------------------------------------------


def test_line_mode_is_one_based_and_includes_both_ends(tmp_path):
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\nfour\n")

    output = _read(_workspace(tmp_path), path="a.txt", start_line=2, end_line=3)

    assert output.startswith("     2\ttwo\n     3\tthree\n")


def test_line_mode_stops_at_five_hundred_lines_and_says_where_to_resume(
    tmp_path,
):
    """:data:`MAX_LINES`, re-verified rather than assumed.

    ``read_file.go:109`` records 200 being raised to 500 because paging a
    large source file cost a model turn each time. The number transfers;
    what does not transfer for free is the *suffix*, which is the half
    that makes the cap usable — a truncation the model cannot resume from
    is a file it cannot read.
    """
    body = "".join(f"line {index}\n" for index in range(1, 1201))
    (tmp_path / "big.txt").write_text(body)

    output = _read(_workspace(tmp_path), path="big.txt", start_line=1)

    assert output.count("\n") == MAX_LINES + 1
    assert f"{MAX_LINES:6d}\tline {MAX_LINES}\n" in output
    assert f"{MAX_LINES + 1:6d}" not in output
    assert f"start_line={MAX_LINES + 1}" in output


def test_an_end_line_beyond_the_cap_is_clamped_not_refused(tmp_path):
    """Asking for 10,000 lines is reasonable and is answered 500 at a time."""
    (tmp_path / "big.txt").write_text("x\n" * 900)

    output = _read(
        _workspace(tmp_path), path="big.txt", start_line=10, end_line=9000
    )

    assert "Read lines 10-509" in output
    assert "start_line=510" in output


def test_reading_to_the_end_of_a_short_file_adds_no_truncation_notice(
    tmp_path,
):
    """The positive twin of the two above: a complete read says nothing."""
    (tmp_path / "a.txt").write_text("one\ntwo\n")

    output = _read(_workspace(tmp_path), path="a.txt", start_line=1)

    assert output == "     1\tone\n     2\ttwo\n"
    assert "start_line=" not in output


def test_a_start_line_past_the_end_reports_the_total_instead_of_nothing(
    tmp_path,
):
    """``read_file.go:229-233``, re-judged for Python.

    The reference argues that an empty buffer can only mean "start_line
    ran off the end", since even a blank line writes its prefix. That
    argument does hold here — same prefix, same reason — but this
    implementation counts rendered lines instead of testing the buffer,
    so the message does not depend on :func:`numbered_line` staying
    non-empty. The blank-line case is asserted separately below, which is
    what makes the difference visible.
    """
    (tmp_path / "a.txt").write_text("one\ntwo\n")

    output = _read(_workspace(tmp_path), path="a.txt", start_line=7)

    assert output == "[start_line=7 is past the end of a.txt, which has 2 lines]"


def test_a_range_of_blank_lines_is_rendered_and_not_mistaken_for_an_overrun(
    tmp_path,
):
    """The case the reference calls structurally impossible, tested anyway.

    It is impossible *because of* the line-number prefix, which is a
    coupling worth knowing about: a future change that rendered bare
    content would turn three blank lines into "start_line is past the end
    of the file".
    """
    (tmp_path / "a.txt").write_text("head\n\n\n\ntail\n")

    output = _read(_workspace(tmp_path), path="a.txt", start_line=2, end_line=4)

    assert output.startswith("     2\t\n     3\t\n     4\t\n")
    assert "past the end" not in output


def test_windows_line_endings_come_back_as_single_lines(tmp_path):
    """Universal newlines are on, matching Go's ``ScanLines``.

    Both drop the ``\\r``. The consequence is a contract note for
    ``edit``: text read from a CRLF file will not match that file byte for
    byte, which is exactly why harness9's ``edit`` has a
    newline-normalising fallback level.
    """
    (tmp_path / "crlf.txt").write_bytes(b"one\r\ntwo\r\n")

    output = _read(_workspace(tmp_path), path="crlf.txt", start_line=1)

    assert output == "     1\tone\n     2\ttwo\n"


# ---- line mode, arguments the model got wrong ----------------------------


def test_end_line_below_start_line_names_the_argument_to_fix(tmp_path):
    """Kept from ``engineering.py:44``'s ``_validate_file_read_input``.

    harness9 has no such check: ``read_file.go:187-189`` leaves the
    inverted range alone, reads nothing, and reports "start_line is past
    the end of the file" — which sends the model to change ``start_line``,
    the argument that was fine. The old OmicsClaw tool is better here and
    the check is carried over.
    """
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\n")

    with pytest.raises(ToolArgumentError) as caught:
        _read(_workspace(tmp_path), path="a.txt", start_line=3, end_line=1)

    assert "input.end_line" in str(caught.value)
    assert "greater than or equal to" in str(caught.value)


def test_a_zero_start_line_is_refused_rather_than_silently_raised_to_one(
    tmp_path,
):
    """Python can tell an omitted integer from a zero; Go cannot.

    ``read_file.go:183-185`` clamps ``startLine < 1`` up to 1 because its
    JSON decoder gives ``0`` for both "absent" and "the model sent zero".
    Here absence is ``None``, so a ``0`` really was sent and really is a
    mistake, and saying so costs one turn instead of silently answering a
    different question.
    """
    (tmp_path / "a.txt").write_text("one\n")

    with pytest.raises(ToolArgumentError) as caught:
        _read(_workspace(tmp_path), path="a.txt", start_line=0)

    assert "1-based" in str(caught.value)


def test_end_line_without_start_line_is_refused_rather_than_ignored(tmp_path):
    """Silently falling back to byte mode would answer the wrong question.

    A model sending only ``end_line`` plainly wanted lines. Both reference
    implementations drop the argument on the floor and return a byte
    window, which reads as the tool working.
    """
    (tmp_path / "a.txt").write_text("one\ntwo\n")

    with pytest.raises(ToolArgumentError) as caught:
        _read(_workspace(tmp_path), path="a.txt", end_line=2)

    assert "start_line" in str(caught.value)


# ---- byte mode -----------------------------------------------------------


def test_byte_mode_defaults_to_eight_thousand_one_hundred_ninety_two_bytes(
    tmp_path,
):
    """:data:`MAX_READ_BYTES`, re-verified.

    ``read_file.go:30`` records 4,096 being raised to 8,192 because each
    page costs a model turn. Nothing in that trade is Go-specific, so the
    number carries; what is checked here is that it is the number the
    Python implementation actually applies, and that the notice names
    *bytes* rather than lines — the confusion ``read_file.go:169-173``
    exists to prevent.
    """
    (tmp_path / "big.txt").write_text("x" * 20000)

    output = _read(_workspace(tmp_path), path="big.txt")

    body, _, notice = output.partition("\n\n...[")
    assert len(body) == MAX_READ_BYTES
    assert "BYTES" in notice
    assert f"offset={MAX_READ_BYTES}" in notice
    assert "start_line" in notice


def test_byte_mode_reports_the_whole_file_when_it_fits(tmp_path):
    """The positive twin: below the cap, nothing is added."""
    (tmp_path / "a.txt").write_text("one\ntwo\n")

    assert _read(_workspace(tmp_path), path="a.txt") == "one\ntwo\n"


def test_a_limit_above_the_ceiling_is_clamped_to_this_projects_own_cap(
    tmp_path,
):
    """:data:`MAX_LIMIT_BYTES` is **not** harness9's; it is this repo's.

    ``engineering.py:630`` bounds ``max_chars`` at 100,000 and harness9
    has no ceiling at all, so honouring an unbounded ``limit`` would be a
    silent regression on the one axis this project cares about. Clamped
    rather than refused, because the truncation notice already tells the
    model how many bytes it really got.
    """
    (tmp_path / "big.txt").write_text("x" * (MAX_LIMIT_BYTES + 5000))

    output = _read(_workspace(tmp_path), path="big.txt", limit=10**9)

    body, _, notice = output.partition("\n\n...[")
    assert len(body) == MAX_LIMIT_BYTES
    assert f"{MAX_LIMIT_BYTES} bytes were read" in notice


def test_an_offset_past_the_end_says_so_instead_of_returning_emptiness(
    tmp_path,
):
    (tmp_path / "a.txt").write_text("hello")

    output = _read(_workspace(tmp_path), path="a.txt", offset=99)

    assert output == (
        "[offset=99 is past the end of a.txt, which is 5 bytes; "
        "nothing to read]"
    )


def test_a_window_that_ends_mid_character_degrades_instead_of_raising(
    tmp_path,
):
    """Plan 0029 Q3's UTF-8 warning, in its ``read`` form.

    Go needs a loop to trim a partial rune because its strings are bytes.
    Python's answer is ``errors="replace"`` at the decode, so the split
    character becomes one U+FFFD and the call succeeds. A translated
    trimming loop would be unreachable code.
    """
    (tmp_path / "u.txt").write_text("é" * 10, encoding="utf-8")

    output = _read(_workspace(tmp_path), path="u.txt", limit=3)

    assert output.startswith("é�")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"offset": -1}, "input.offset"),
        ({"limit": 0}, "input.limit"),
        ({"limit": -5}, "input.limit"),
    ],
)
def test_negative_paging_arguments_are_named_rather_than_coerced(
    tmp_path, kwargs, expected
):
    (tmp_path / "a.txt").write_text("hello")

    with pytest.raises(ToolArgumentError) as caught:
        _read(_workspace(tmp_path), path="a.txt", **kwargs)

    assert expected in str(caught.value)


# ---- plan 0029 trap 11: the long line -----------------------------------


def test_a_line_longer_than_the_cap_is_refused_with_the_mode_that_works(
    tmp_path,
):
    """Plan 0029 trap 11, **re-decided for Python rather than translated.**

    harness9 gets this for free: ``bufio.Scanner`` has a 512 KiB buffer
    and returns ``ErrTooLong`` past it. Python has no such limit —
    iterating a file will materialise a line of any size — so a faithful
    translation of the *code* would produce no guard at all, and the
    failure would be worse than the reference's: a multi-megabyte line
    read into memory and then into the model's context.

    So the message is what is pinned, and specifically that it names byte
    mode. A generic "could not read file" would send the model to retry
    line mode.
    """
    long_line = "x" * (MAX_LINE_CHARS + 1)
    (tmp_path / "gen.json").write_text(f"{long_line}\nshort\n")

    with pytest.raises(ToolArgumentError) as caught:
        _read(_workspace(tmp_path), path="gen.json", start_line=1)

    message = str(caught.value)
    assert "offset" in message and "limit" in message
    assert "byte mode" in message


def test_the_advice_the_long_line_refusal_gives_actually_works(tmp_path):
    """The positive twin, and the reason the pair matters.

    A refusal that names an alternative is only useful if the alternative
    reads the file. Byte mode has no line notion, so it does.
    """
    long_line = "x" * (MAX_LINE_CHARS + 1)
    (tmp_path / "gen.json").write_text(f"{long_line}\n")

    output = _read(_workspace(tmp_path), path="gen.json", offset=0, limit=64)

    assert output.startswith("x" * 64)


def test_a_line_just_inside_the_cap_still_renders(tmp_path):
    """The boundary in the other direction: 512 KiB exactly is fine."""
    (tmp_path / "wide.txt").write_text("y" * MAX_LINE_CHARS + "\n")

    output = _read(_workspace(tmp_path), path="wide.txt", start_line=1)

    assert output == numbered_line(1, "y" * MAX_LINE_CHARS)


# ---- plan 0029 trap 7: which failures are the model's to fix -------------


def test_a_file_that_is_not_there_is_an_error_the_model_can_correct(tmp_path):
    """Plan 0029 trap 7, first half. **The criterion is in the docstring.**

    Not "did something go wrong" but **what should the model change
    next**. The path is wrong and a different path fixes it, so this is
    ``is_error=True`` and the message names the argument. Its twin is the
    next test; read them together.
    """
    registry = ToolRegistry([read_tool(_workspace(tmp_path))])

    result = _run(
        registry.execute(
            ToolCall(id="c1", name=TOOL_NAME, arguments=_args(path="gone.txt"))
        )
    )

    assert result.is_error is True
    assert "gone.txt" in result.output
    assert "No such file" in result.output


def test_an_empty_file_is_not_an_error_because_there_is_nothing_to_fix(
    tmp_path,
):
    """Plan 0029 trap 7, second half.

    The file is there and it is empty. That is a fact about the world with
    no argument for the model to change, so it comes back as ordinary
    output — the same distinction that makes a non-zero exit from ``bash``
    ``is_error=False`` in the step that delivers it.
    """
    (tmp_path / "empty.txt").write_text("")
    registry = ToolRegistry([read_tool(_workspace(tmp_path))])

    result = _run(
        registry.execute(
            ToolCall(id="c1", name=TOOL_NAME, arguments=_args(path="empty.txt"))
        )
    )

    assert result.is_error is False
    assert result.output == ""


def test_a_name_too_long_for_the_filesystem_reads_as_a_correctable_sentence(
    tmp_path,
):
    """The gap the helper layer leaves open, closed here.

    ``Workspace.resolve`` accepts a 5,000-character name because
    :meth:`~pathlib.Path.resolve` never touches the filesystem, so the
    refusal arrives later as ``ENAMETOOLONG``. Reported raw that reads as
    a machine fault; what the model needs is a sentence naming the
    argument. Pinned so a later refactor cannot let the bare
    :exc:`OSError` through.
    """
    registry = ToolRegistry([read_tool(_workspace(tmp_path))])

    result = _run(
        registry.execute(
            ToolCall(
                id="c1", name=TOOL_NAME, arguments=_args(path="a" * 5000)
            )
        )
    )

    assert result.is_error is True
    assert "File name too long" in result.output
    assert "Send the path of an existing file" in result.output
    assert "Traceback" not in result.output


def test_a_directory_is_refused_by_name_rather_than_by_errno(tmp_path):
    (tmp_path / "sub").mkdir()

    with pytest.raises(ToolArgumentError) as caught:
        _read(_workspace(tmp_path), path="sub")

    assert "is a directory" in str(caught.value)


def test_an_empty_path_argument_is_refused(tmp_path):
    with pytest.raises(ToolArgumentError) as caught:
        _read(_workspace(tmp_path), path="   ")

    assert "input.path" in str(caught.value)


# ---- the boundary, each refusal beside a legitimate read -----------------


def test_a_relative_escape_is_refused_and_a_nested_path_is_not(tmp_path):
    """Plan 0029 §10-9: a refusal test alone is green under "refuse all"."""
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "ok.txt").write_text("fine\n")
    workspace = _workspace(tmp_path)

    assert _read(workspace, path="a/b/ok.txt") == "fine\n"

    with pytest.raises(PathEscapesWorkspace):
        _read(workspace, path="../../etc/passwd")


def test_an_absolute_path_inside_the_workspace_reads_and_one_outside_does_not(
    tmp_path,
):
    """Plan 0029 trap 2 as it reaches a tool.

    The Go implementation needs a branch here because
    ``filepath.Join(workDir, "/abs")`` doubles the path; Python's ``/``
    operator does not, so the branch is deliberately absent and only the
    behaviour is pinned.
    """
    (tmp_path / "ok.txt").write_text("fine\n")
    workspace = _workspace(tmp_path)

    assert _read(workspace, path=str(tmp_path / "ok.txt")) == "fine\n"

    with pytest.raises(PathEscapesWorkspace):
        _read(workspace, path="/etc/hostname")


def test_a_symlink_out_of_the_workspace_is_refused_and_one_inside_is_not(
    tmp_path,
):
    """Python's ``resolve`` follows links, which harness9's ``Abs`` does not.

    Plan 0029 Q10 calls that a net improvement and warns that the obvious
    way to "align with the reference" later would reopen the hole. The
    positive half keeps the improvement from being implemented as "refuse
    every symlink", which would break ordinary workspaces.
    """
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not yours\n")
    (tmp_path / "real.txt").write_text("yours\n")
    os.symlink(outside / "secret.txt", tmp_path / "escape.txt")
    os.symlink(tmp_path / "real.txt", tmp_path / "alias.txt")
    workspace = _workspace(tmp_path)

    assert _read(workspace, path="alias.txt") == "yours\n"

    with pytest.raises(PathEscapesWorkspace):
        _read(workspace, path="escape.txt")


def test_a_dotenv_is_refused_and_a_file_that_merely_starts_with_env_is_not(
    tmp_path,
):
    """The credential rule fires on names, so it has to be narrow."""
    (tmp_path / ".env").write_text("LLM_API_KEY=sk-real\n")
    (tmp_path / ".envelope-design.md").write_text("notes\n")
    workspace = _workspace(tmp_path)

    assert _read(workspace, path=".envelope-design.md") == "notes\n"

    with pytest.raises(PathIsSensitive):
        _read(workspace, path=".env")


def test_a_refused_path_keeps_the_class_that_says_which_rule_fired(tmp_path):
    """Both refusals reach the model as ``is_error``; they are not the same
    event for whoever is watching the machine, so neither is flattened into
    :exc:`~omicsclaw.tools.function_tool.ToolArgumentError`."""
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "id_rsa").write_text("key\n")
    registry = ToolRegistry([read_tool(_workspace(tmp_path))])

    result = _run(
        registry.execute(
            ToolCall(
                id="c1", name=TOOL_NAME, arguments=_args(path=".ssh/id_rsa")
            )
        )
    )

    assert result.is_error is True
    assert "PathIsSensitive" in result.output


# ---- where the workspace comes from --------------------------------------


def test_a_workspace_bound_to_the_session_is_used_when_none_was_given(
    tmp_path,
):
    """Plan 0029 §5's ``context_value`` row, which §1's constructor sketch
    does not replace: one registry serves many concurrent sessions, and a
    workspace frozen into a constructor would make them share one."""
    (tmp_path / "a.txt").write_text("bound\n")
    tool = read_tool()

    with use_tool_context(values={"workspace": str(tmp_path)}):
        assert _run(tool.execute(_args(path="a.txt"))) == "bound\n"


def test_the_constructor_wins_over_whatever_the_session_bound(tmp_path):
    """Precedence has to be one way round and testable."""
    other = tmp_path / "other"
    other.mkdir()
    (other / "a.txt").write_text("constructor\n")
    (tmp_path / "a.txt").write_text("context\n")
    tool = read_tool(Workspace(other))

    with use_tool_context(values={"workspace": str(tmp_path)}):
        assert _run(tool.execute(_args(path="a.txt"))) == "constructor\n"


def test_no_workspace_anywhere_is_not_reported_as_the_models_mistake():
    """A :exc:`RuntimeError`, not a
    :exc:`~omicsclaw.tools.function_tool.ToolArgumentError`.

    No argument the model can send binds a workspace to a session, so
    promising it a correction would send it round a loop it cannot leave.
    """
    tool = read_tool()

    with pytest.raises(RuntimeError) as caught:
        _run(tool.execute(_args(path="a.txt")))

    assert not isinstance(caught.value, ToolArgumentError)
    assert "workspace" in str(caught.value)


# ---- policy --------------------------------------------------------------


def test_the_policy_is_declared_rather_than_defaulted(tmp_path):
    """Plan 0029 Q2b.

    ``ToolPolicy()`` is ``HIGH`` + ``ASK``, and ``require_approval`` fails
    closed with no channel bound, so a ``read`` that forgot to declare
    could not read a line. ``read_only`` and ``concurrency_safe`` are
    checked too: they are claims rather than gates today, but they are the
    fields an assembly layer will filter on, and they are true here.
    """
    policy = read_tool(_workspace(tmp_path)).policy

    assert policy.approval_mode is ApprovalMode.AUTO
    assert policy.risk_level is RiskLevel.LOW
    assert policy.read_only is True
    assert policy.concurrency_safe is True
    assert policy.writes_workspace is False


def test_reading_needs_no_approval_channel_and_that_is_the_whole_point(
    tmp_path,
):
    """``AUTO`` is only real if it works with nobody listening.

    The counterpart in ``test_write.py`` asserts the opposite for the same
    machinery, which is what makes this one evidence rather than a
    tautology.
    """
    (tmp_path / "a.txt").write_text("fine\n")
    registry = ToolRegistry([read_tool(_workspace(tmp_path))])

    result = _run(
        registry.execute(
            ToolCall(id="c1", name=TOOL_NAME, arguments=_args(path="a.txt"))
        )
    )

    assert result.is_error is False
    assert result.output == "fine\n"


def test_it_is_a_tool_and_agrees_with_itself_about_its_name(tmp_path):
    tool = read_tool(_workspace(tmp_path))

    assert isinstance(tool, Tool)
    assert tool.name == tool.definition().name == TOOL_NAME


# ---- the environment seam (plan 0029 Q11) --------------------------------


class _RecordingEnvironment:
    """A fake that satisfies both file Protocols structurally.

    One object for both seams, which is the point of narrowing them: an
    assembly layer injects one environment into every tool, and the
    Protocols are the per-tool view of it rather than three things to
    implement.
    """

    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload
        self.reads: list[str] = []
        self.writes: list[tuple[str, bytes]] = []

    async def read_file(self, path: str) -> bytes:
        self.reads.append(path)
        return self.payload

    async def write_file(self, path: str, data: bytes) -> None:
        self.writes.append((path, data))


def test_an_injected_environment_really_replaces_the_local_filesystem(
    tmp_path,
):
    """Plan 0029 Q11, and plan 0029 trap 15 is why it is *used*.

    harness9 stores an environment on its file tools and never reads it
    (``read_file.go:35-37`` is a TODO) — dead state, which this project
    treats as a defect. So the fake below returns something the disk does
    not contain, and the assertion is that the disk's copy never appears.
    """
    (tmp_path / "a.txt").write_text("from disk\n")
    environment = _RecordingEnvironment(b"from the environment\n")
    tool = read_tool(_workspace(tmp_path), environment=environment)

    output = _run(tool.execute(_args(path="a.txt", start_line=1)))

    assert output == "     1\tfrom the environment\n"
    assert environment.reads == [str(tmp_path / "a.txt")]


def test_byte_mode_pages_through_an_injected_environment_too(tmp_path):
    (tmp_path / "a.txt").write_text("ignored\n")
    environment = _RecordingEnvironment(b"abcdefghij")
    tool = read_tool(_workspace(tmp_path), environment=environment)

    output = _run(tool.execute(_args(path="a.txt", offset=2, limit=3)))

    assert output.startswith("cde")
    assert "offset=5" in output


def test_an_environment_still_answers_to_the_workspace_boundary(tmp_path):
    """Injection does not widen the boundary; resolution happens first."""
    environment = _RecordingEnvironment(b"secrets")
    tool = read_tool(_workspace(tmp_path), environment=environment)

    with pytest.raises(PathEscapesWorkspace):
        _run(tool.execute(_args(path="/etc/hostname")))

    assert environment.reads == []


# ---- plan 0029 trap 5: cancellation is not an Observation ----------------


class _CancellingEnvironment:
    """An environment whose read is interrupted by the engine's deadline."""

    async def read_file(self, path: str) -> bytes:
        raise asyncio.CancelledError


def test_a_cancelled_read_stays_cancelled_and_is_not_turned_into_an_error(
    tmp_path,
):
    """Plan 0029 trap 5, fourth appearance in this rebuild.

    ``_fetch`` wraps its await in ``except OSError`` precisely so that
    this cannot happen; widening it to ``except Exception`` would not be
    enough to break this test, because :exc:`asyncio.CancelledError` is a
    :exc:`BaseException` — widening it to ``except BaseException`` would,
    and that is the mutation this test is aimed at. A cancelled turn
    reported to the model as "cannot read that file" sends it to fix a
    file that is fine.
    """
    (tmp_path / "a.txt").write_text("x\n")
    tool = read_tool(_workspace(tmp_path), environment=_CancellingEnvironment())

    async def main() -> str:
        try:
            await tool.execute(_args(path="a.txt"))
        except asyncio.CancelledError:
            return "cancelled"
        return "swallowed"

    assert asyncio.run(main()) == "cancelled"


def test_cancelling_a_read_that_is_waiting_for_a_lock_leaves_no_entry_behind(
    tmp_path,
):
    """The other half of trap 5, and it exercises task A's reference count.

    A read queued behind a writer is exactly where the engine's per-tool
    timeout lands, and an entry left in the table for a waiter that went
    away is the leak that count exists to prevent.
    """
    (tmp_path / "a.txt").write_text("x\n")
    target = (tmp_path / "a.txt").resolve()
    tool = read_tool(_workspace(tmp_path))

    async def main() -> str:
        async with write_lock(target):
            task = asyncio.create_task(tool.execute(_args(path="a.txt")))
            for _ in range(20):
                await asyncio.sleep(0)
            assert not task.done(), "the read should be queued behind us"
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                outcome = "cancelled"
            else:
                outcome = "completed"
        return outcome

    assert _run(main()) == "cancelled"
    assert PATH_LOCKS.reference_count(target) == 0
    assert PATH_LOCKS.tracked_paths() == frozenset()


# ---- reading really does take the shared lock ----------------------------


def test_two_reads_of_one_file_run_at_the_same_time(tmp_path):
    """A shared lock has to actually be shared, or ``read`` serialises the
    turn. Asserted through the table rather than by timing."""
    (tmp_path / "a.txt").write_text("x\n")
    target = (tmp_path / "a.txt").resolve()
    tool = read_tool(_workspace(tmp_path))

    async def main() -> None:
        async with PATH_LOCKS.read(target):
            assert PATH_LOCKS.reference_count(target) == 1
            output = await tool.execute(_args(path="a.txt"))
            assert output == "x\n"

    _run(main())
    assert PATH_LOCKS.tracked_paths() == frozenset()
