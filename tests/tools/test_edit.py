"""Contract tests for ``omicsclaw.tools.builtin.edit``.

Plan 0029 §12's first inherited item. Two things make this tool's tests
different from ``test_write.py``'s, and both shape the file:

**A refusal has to be checked against the file, not the return value.**
The tool reads, decides, asks and only then writes, so every plausible
wrong implementation — asking after writing, matching twice, applying a
plan to changed bytes — returns something reasonable and leaves the wrong
file behind. So the assertions are about contents.

**The four match levels need a positive *and* a negative each.** A
cascade that always falls through to L4 passes every "this anchor was
found" test ever written, and one that stops at L1 passes every "an
ambiguous anchor is refused" test. Each level is pinned by a case that
only *it* can satisfy, and by the level it reports.

Plan 0029 §10-9's rule is kept throughout: every refusal is paired with a
legitimate edit, because a tool that refuses everything passes every
refusal test.

**The layering rule does not apply to this file**, for the reason
``test_read.py``, ``test_write.py`` and ``test_bash.py`` record: the guard
walks ``omicsclaw/tools/``, and a test may import
:class:`~omicsclaw.engine.config.EngineConfig` precisely so that the
coupling the production module cannot see is asserted somewhere.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.schema import ToolCall
from omicsclaw.tools import (
    ApprovalDecision,
    ApprovalDenied,
    ApprovalMode,
    ApprovalRequest,
    ApprovalUnavailable,
    EditTool,
    ProgressUpdate,
    RiskLevel,
    Tool,
    ToolPolicy,
    ToolRegistry,
)
from omicsclaw.tools._workspace import (
    PathEscapesWorkspace,
    PathIsSensitive,
    Workspace,
)
from omicsclaw.tools.builtin.edit import (
    CONTEXT_LINES,
    EDIT_SCHEMA,
    MATCH_EXACT,
    MATCH_LINE_BY_LINE,
    MATCH_NEWLINE,
    MATCH_TRIMMED,
    MAX_SUMMARY_LINES,
    TOOL_NAME,
    FileEditEnvironment,
    describe_change,
    plan_edit,
    replace_once,
    strip_line_numbers,
)
from omicsclaw.tools.builtin.read import numbered_line
from omicsclaw.tools.context import use_tool_context
from omicsclaw.tools.function_tool import ToolArgumentError

_T = TypeVar("_T")

_DEADLINE = 10.0


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; the suite drives this way."""
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


def _args(**kwargs: Any) -> str:
    return json.dumps(kwargs)


def _yes(seen: list[ApprovalRequest] | None = None):
    """An approval channel that agrees, and optionally keeps the receipts."""

    def channel(request: ApprovalRequest) -> ApprovalDecision:
        if seen is not None:
            seen.append(request)
        return ApprovalDecision(approved=True)

    return channel


def _no(reason: str = "not this time"):
    def channel(request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=False, reason=reason)

    return channel


def _edit(workspace: Workspace, *, approve=None, **kwargs: Any) -> str:
    tool = EditTool(workspace)
    with use_tool_context(approval=approve if approve is not None else _yes()):
        return _run(tool.execute(_args(**kwargs)))


def _seeded(tmp_path: Path, name: str, text: str) -> Path:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return target


# ---- the ordinary job ----------------------------------------------------


def test_an_exact_anchor_is_replaced_and_nothing_else_moves(tmp_path):
    """L1, the case the other three levels exist to avoid needing."""
    seeded = _seeded(
        tmp_path, "m.py", "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
    )

    message = _edit(
        Workspace(tmp_path),
        path="m.py",
        source_text="    return 1",
        target_text="    return 42",
    )

    assert seeded.read_text() == (
        "def a():\n    return 42\n\n\ndef b():\n    return 2\n"
    )
    assert "-     return 1" in message
    assert "+     return 42" in message
    assert "Exact match" in message


def test_the_summary_shows_three_lines_of_context_either_side(tmp_path):
    """:data:`CONTEXT_LINES`, and a diff is only useful if it is placed."""
    body = "".join(f"line{index}\n" for index in range(1, 12))
    _seeded(tmp_path, "m.txt", body)

    message = _edit(
        Workspace(tmp_path),
        path="m.txt",
        source_text="line6",
        target_text="CHANGED",
    )

    assert "  line3" in message and "  line9" in message
    assert "line2" not in message and "line10" not in message


def test_a_change_past_the_summary_ceiling_reports_counts_only(tmp_path):
    """:data:`MAX_SUMMARY_LINES`: a diff of a change the model just wrote
    is the least useful thing to spend its context on."""
    original = "".join(f"old{index}\n" for index in range(30))
    _seeded(tmp_path, "m.txt", original)
    replacement = "".join(f"new{index}\n" for index in range(30))

    message = _edit(
        Workspace(tmp_path),
        path="m.txt",
        source_text=original,
        target_text=replacement,
    )

    assert "30 lines removed, 30 added" in message
    assert "old0" not in message and "new0" not in message
    assert (tmp_path / "m.txt").read_text() == replacement


def test_the_borrowed_literals_are_the_reference_numbers():
    """Plan 0029 §10-8, pinned where the code cannot pin them.

    Both constants are used in arithmetic the other tests compare
    against, so changing one moves both sides of those assertions and the
    suite stays green. A borrowed number needs one test that names it.
    """
    assert CONTEXT_LINES == 3  # edit_file.go:143
    assert MAX_SUMMARY_LINES == 20  # edit_file.go:200


# ---- the four levels, one case each that only that level satisfies -------


def test_level_one_is_reported_as_exact_and_keeps_the_target_verbatim():
    content = "alpha\r\nbeta\r\ngamma\r\n"

    result, level = replace_once(content, "beta\r\n", "delta\r\n")

    assert level == MATCH_EXACT
    assert result == "alpha\r\ndelta\r\ngamma\r\n"


def test_level_two_matches_across_line_endings_and_restores_them():
    """``edit_file.go:280-288``. The level that exists because a model
    cannot see a ``\\r`` in a file it was shown."""
    content = "alpha\r\nbeta\r\ngamma\r\n"

    result, level = replace_once(content, "beta\ngamma", "beta\nGAMMA")

    assert level == MATCH_NEWLINE
    assert result == "alpha\r\nbeta\r\nGAMMA\r\n"
    assert "\n" not in result.replace("\r\n", "")


def test_level_three_tolerates_whitespace_around_the_anchor():
    content = "one\ntwo\nthree\n"

    result, level = replace_once(content, "  \n two \n ", "TWO")

    assert level == MATCH_TRIMMED
    assert result == "one\nTWO\nthree\n"


def test_an_all_whitespace_anchor_is_refused_before_it_can_eat_a_blank_line():
    """A gap in the reference, found by writing this test against it.

    ``edit_file.go:292`` skips L3 for an all-whitespace anchor and its
    comment gives the right reason — it would match a blank line by
    mistake — but the guard covers only L3. L4 splits ``strip("   ")``
    into ``[""]``, a window matching every blank line, so in a file with
    exactly one blank line the reference **replaces it**. This asserts
    both halves: the refusal happens, and it happens for a file where the
    unguarded cascade would have written something.
    """
    with pytest.raises(ToolArgumentError) as one_blank:
        plan_edit("one\n\ntwo\n", "     ", "X")
    with pytest.raises(ToolArgumentError) as many_blanks:
        plan_edit("one\n\ntwo\n\nthree\n", "\t\n ", "X")

    assert "nothing but whitespace" in str(one_blank.value)
    assert "nothing but whitespace" in str(many_blanks.value)
    # Not the empty-anchor wording: the two inputs fail for related but
    # distinct reasons and are owed distinct sentences.
    assert "names every position" not in str(one_blank.value)


def test_level_four_matches_regardless_of_indentation():
    content = "class C:\n    def m(self):\n        return 1\n"

    result, level = replace_once(
        content,
        "def m(self):\nreturn 1",
        "def m(self):\n    return 99",
    )

    assert level == MATCH_LINE_BY_LINE
    assert result == "class C:\n    def m(self):\n        return 99\n"


def test_level_four_reindents_the_replacement_to_the_files_own_level():
    """``edit_file.go:365-370``, the correction its comment calls out.

    L4 matched without regard to indentation, so the model's indentation
    of ``target_text`` carries no information. Writing it verbatim into a
    Python file turns a correct edit into an ``IndentationError``; the
    block's *relative* shape is kept and its base is realigned.
    """
    content = "def outer():\n    if x:\n        a = 1\n        b = 2\n"

    result, level = replace_once(
        content,
        "a = 1\nb = 2",
        "a = 1\nif y:\n    b = 3",
    )

    assert level == MATCH_LINE_BY_LINE
    assert result == (
        "def outer():\n    if x:\n        a = 1\n        if y:\n"
        "            b = 3\n"
    )


def test_level_four_leaves_blank_lines_blank_rather_than_indented():
    content = "def f():\n    x = 1\n    y = 2\n"

    result, _level = replace_once(content, "x = 1\ny = 2", "x = 1\n\ny = 2")

    assert result == "def f():\n    x = 1\n\n    y = 2\n"
    assert "    \n" not in result


# ---- the uniqueness guard, at every level that reports one --------------


def test_an_exactly_repeated_anchor_is_refused_rather_than_guessed(tmp_path):
    """``edit_file.go:269-271``. Nothing is written, and the message says
    what to do: send more context."""
    seeded = _seeded(tmp_path, "m.py", "x = 1\ny = 0\nx = 1\n")
    before = seeded.read_text()

    with pytest.raises(ToolArgumentError) as refusal:
        _edit(
            Workspace(tmp_path),
            path="m.py",
            source_text="x = 1",
            target_text="x = 2",
        )

    assert "occurs 2 times" in str(refusal.value)
    assert "unique" in str(refusal.value)
    assert seeded.read_text() == before


def test_an_anchor_ambiguous_only_once_indentation_is_ignored_is_refused():
    """The guard L4 carries itself, and it needs an anchor the three
    stricter levels all miss: two blocks with the same lines at different
    indentation, and an anchor that is a substring of neither."""
    content = (
        "if a:\n    run()\n    stop()\nif b:\n        run()\n        stop()\n"
    )

    with pytest.raises(ToolArgumentError) as refusal:
        replace_once(content, "run()\nstop()", "go()")

    assert "matches 2 places once indentation is ignored" in str(refusal.value)


def test_an_anchor_in_no_form_at_all_is_refused_with_one_wording():
    with pytest.raises(ToolArgumentError) as refusal:
        replace_once("alpha\nbeta\n", "gamma", "delta")

    message = str(refusal.value)
    assert "was not found" in message
    assert "line-number prefix" in message


def test_an_empty_anchor_is_named_rather_than_reported_as_a_multi_match():
    """A guard the reference does not have.

    ``"".count`` is ``len + 1`` in both languages, so without this the
    empty anchor reaches L1's multi-match branch and the model is told to
    add context to something that has none.
    """
    with pytest.raises(ToolArgumentError) as refusal:
        plan_edit("some file body\n", "", "x")

    message = str(refusal.value)
    assert "names every position" in message
    assert "occurs" not in message


# ---- idempotency: pi's archived no-op bug -------------------------------


def test_a_no_op_edit_succeeds_and_does_not_rewrite_the_file(tmp_path):
    """Plan 0029 appendix A, ``pi``'s second known bug: a no-op edit that
    errors breaks idempotency for a model re-sending work it already did.

    The file is not rewritten either, so a watcher does not rebuild and
    the modification time does not move.
    """
    seeded = _seeded(tmp_path, "m.py", "value = 1\n")
    before = seeded.stat().st_mtime_ns

    message = _edit(
        Workspace(tmp_path),
        path="m.py",
        source_text="value = 1",
        target_text="value = 1",
    )

    assert "already contains" in message
    assert seeded.read_text() == "value = 1\n"
    assert seeded.stat().st_mtime_ns == before


def test_a_no_op_still_requires_the_anchor_to_be_there(tmp_path):
    """The other half, and the reason the fix is not "skip the match".

    "Already done" and "never found" are different answers, and a model
    re-sending an edit whose anchor has since been renamed is owed the
    second one.
    """
    _seeded(tmp_path, "m.py", "value = 1\n")

    with pytest.raises(ToolArgumentError):
        _edit(
            Workspace(tmp_path),
            path="m.py",
            source_text="absent = 1",
            target_text="absent = 1",
        )


# ---- the line-number prefix contract (plan 0029 Q9) ---------------------


def test_the_prefix_this_strips_is_the_one_read_file_renders():
    """The contract's two halves, checked against each other.

    ``read_file`` produces the prefix and this tool has to invert it. The
    test composes the real producer rather than a hand-written
    ``"     1\\t"``, so a change to either side fails here instead of
    quietly leaving models unable to paste what they were shown.
    """
    shown = "".join(
        numbered_line(number, text)
        for number, text in ((7, "def f():"), (8, "    return 1"))
    )

    assert strip_line_numbers(shown.rstrip("\n")) == "def f():\n    return 1"


def test_an_anchor_pasted_with_line_numbers_still_finds_its_block(tmp_path):
    seeded = _seeded(tmp_path, "m.py", "def f():\n    return 1\n")
    pasted = "".join(
        numbered_line(number, text)
        for number, text in ((1, "def f():"), (2, "    return 1"))
    ).rstrip("\n")

    message = _edit(
        Workspace(tmp_path),
        path="m.py",
        source_text=pasted,
        target_text="def f():\n    return 2",
    )

    assert seeded.read_text() == "def f():\n    return 2\n"
    assert "after removing read_file's line numbers" in message


def test_a_stripped_anchor_is_never_reported_as_an_exact_match(tmp_path):
    """Stripping is the tool editing the model's argument, so the result
    must ask for a re-read rather than claim authority."""
    _seeded(tmp_path, "m.py", "a = 1\n")

    message = _edit(
        Workspace(tmp_path),
        path="m.py",
        source_text=numbered_line(1, "a = 1").rstrip("\n"),
        target_text=numbered_line(1, "a = 2").rstrip("\n"),
    )

    assert "Fuzzy match" in message
    assert "Exact match" not in message
    assert (tmp_path / "m.py").read_text() == "a = 2\n"


def test_a_tsv_whose_lines_start_with_a_number_is_not_stripped(tmp_path):
    """The risk the retry's ordering is what makes acceptable.

    In an omics repository ``1<TAB>gene_a`` is data, not a pasted
    ``read_file`` response. An anchor copied from such a file matches at
    L1, so the strip path is never reached — and the bytes written are the
    model's own.
    """
    seeded = _seeded(tmp_path, "genes.tsv", "     1\tgene_a\n     2\tgene_b\n")

    message = _edit(
        Workspace(tmp_path),
        path="genes.tsv",
        source_text="     2\tgene_b",
        target_text="     2\tgene_c",
    )

    assert seeded.read_text() == "     1\tgene_a\n     2\tgene_c\n"
    assert "Exact match" in message
    assert "line numbers" not in message


def test_only_a_wholly_prefixed_anchor_is_treated_as_pasted():
    """One prefixed line in five describes a data file, not a paste."""
    assert strip_line_numbers("     1\tone\nplain\n     3\tthree") is None
    assert strip_line_numbers("plain text") is None
    assert strip_line_numbers("") is None


def test_a_blank_line_inside_a_prefixed_paste_is_tolerated():
    """``numbered_line`` renders an empty source line as a number, a tab
    and nothing, and a model copying the block usually drops the trailing
    whitespace."""
    pasted = f"{numbered_line(1, 'a').rstrip(chr(10))}\n\n     3\tb"

    assert strip_line_numbers(pasted) == "a\n\nb"


def test_the_prefix_retry_does_not_rescue_an_ambiguous_anchor():
    """It fires on "not found" only. An anchor that is ambiguous is
    ambiguous whether or not it carries line numbers, and retrying a
    looser form could only turn a fixable refusal into a blind match."""
    content = "     1\tx\n     1\tx\n"

    with pytest.raises(ToolArgumentError) as refusal:
        plan_edit(content, "     1\tx", "     1\ty")

    assert "occurs 2 times" in str(refusal.value)


# ---- approval: the gate, and what it is shown ---------------------------


def test_a_denied_approval_leaves_the_file_exactly_as_it_was(tmp_path):
    seeded = _seeded(tmp_path, "m.py", "a = 1\n")

    with pytest.raises(ApprovalDenied):
        _edit(
            Workspace(tmp_path),
            approve=_no(),
            path="m.py",
            source_text="a = 1",
            target_text="a = 2",
        )

    assert seeded.read_text() == "a = 1\n"


def test_with_no_channel_bound_the_edit_fails_closed(tmp_path):
    """Plan 0029 Q2's accepted cost, asserted rather than assumed: the
    absence of an approval channel is not consent."""
    seeded = _seeded(tmp_path, "m.py", "a = 1\n")
    tool = EditTool(Workspace(tmp_path))

    with pytest.raises(ApprovalUnavailable):
        with use_tool_context():
            _run(tool.execute(_args(path="m.py", source_text="a = 1", target_text="b")))

    assert seeded.read_text() == "a = 1\n"


def test_the_prompt_carries_the_diff_the_resolved_path_and_the_level(tmp_path):
    """What a human is being asked is *what will change*, not *which tool
    is being called*."""
    _seeded(tmp_path, "sub/m.py", "keep\nold\nkeep2\n")
    seen: list[ApprovalRequest] = []

    _edit(
        Workspace(tmp_path),
        approve=_yes(seen),
        path="sub/m.py",
        source_text="old",
        target_text="new",
    )

    reason = seen[0].reason
    assert str((tmp_path / "sub" / "m.py").resolve()) in reason
    assert "- old" in reason and "+ new" in reason
    assert "an exact match" in reason
    assert seen[0].risk_level is RiskLevel.HIGH
    assert seen[0].approval_mode is ApprovalMode.ASK


def test_the_prompt_carries_the_bytes_the_model_sent_not_a_re_encoding(tmp_path):
    """Why this tool is hand-written rather than a ``FunctionTool``.

    Key order and spacing are what a person reviewing a destructive call
    is looking at, and a decode-then-re-encode loses both.
    """
    _seeded(tmp_path, "m.py", "a = 1\n")
    payload = '{"target_text":"a = 2",  "source_text":"a = 1", "path":"m.py"}'
    seen: list[ApprovalRequest] = []
    tool = EditTool(Workspace(tmp_path))

    with use_tool_context(approval=_yes(seen)):
        _run(tool.execute(payload))

    assert seen[0].arguments == payload


def test_a_file_that_moved_while_the_prompt_was_open_is_not_edited(tmp_path):
    """The second read, and the reason it is a refusal rather than a retry.

    What the human approved was a diff against particular bytes. Applying
    it to different bytes writes a change nobody saw; re-running the match
    could silently succeed at a different level against different content.
    """
    seeded = _seeded(tmp_path, "m.py", "a = 1\n")

    def meddling(request: ApprovalRequest) -> ApprovalDecision:
        seeded.write_text("a = 1\nb = 2\n")
        return ApprovalDecision(approved=True)

    with pytest.raises(ToolArgumentError) as refusal:
        _edit(
            Workspace(tmp_path),
            approve=meddling,
            path="m.py",
            source_text="a = 1",
            target_text="a = 9",
        )

    assert "changed while this edit was waiting" in str(refusal.value)
    assert seeded.read_text() == "a = 1\nb = 2\n"


def test_two_concurrent_edits_to_one_path_do_not_lose_one_another(tmp_path):
    """Plan 0028 §11 debt #1 in the one place this layer can answer it.

    ``engine/executor.py`` fires an ``ensure_future`` per call with
    ``max_concurrent_tools`` defaulting to unlimited, so two edits to one
    path in one turn really do run together. The write lock plus the
    changed-file check turn a lost update into one success and one
    correctable refusal.
    """
    seeded = _seeded(tmp_path, "m.py", "a = 1\nb = 1\n")

    async def main() -> list[object]:
        arrived = asyncio.Event()
        count = 0

        async def gate(request: ApprovalRequest) -> ApprovalDecision:
            nonlocal count
            count += 1
            if count == 2:
                arrived.set()
            await arrived.wait()
            return ApprovalDecision(approved=True)

        tool = EditTool(Workspace(tmp_path))
        first = _args(path="m.py", source_text="a = 1", target_text="a = 2")
        second = _args(path="m.py", source_text="b = 1", target_text="b = 2")
        with use_tool_context(approval=gate):
            return await asyncio.gather(
                tool.execute(first),
                tool.execute(second),
                return_exceptions=True,
            )

    outcomes = _run(main())

    failures = [one for one in outcomes if isinstance(one, BaseException)]
    assert len(failures) == 1
    assert isinstance(failures[0], ToolArgumentError)
    assert seeded.read_text() in ("a = 2\nb = 1\n", "a = 1\nb = 2\n")


def test_progress_is_reported_and_a_missing_sink_is_not_a_failure(tmp_path):
    _seeded(tmp_path, "m.py", "a = 1\n")
    updates: list[ProgressUpdate] = []
    tool = EditTool(Workspace(tmp_path))

    with use_tool_context(approval=_yes(), progress=updates.append):
        _run(tool.execute(_args(path="m.py", source_text="a = 1", target_text="a = 2")))

    assert any(update.tool_name == TOOL_NAME for update in updates)
    # And again with nothing listening, which is the ordinary case.
    _seeded(tmp_path, "n.py", "a = 1\n")
    assert _edit(
        Workspace(tmp_path), path="n.py", source_text="a = 1", target_text="a = 2"
    )


def test_a_cancelled_turn_is_not_reported_to_the_model_as_a_failure(tmp_path):
    """Plan 0029 trap 5, the fourth time this layer has had to say it.

    Every ``except`` in the module names :exc:`OSError` or
    :exc:`UnicodeDecodeError`. An ``except Exception`` around the approval
    would turn the engine's deadline into an Observation.
    """
    _seeded(tmp_path, "m.py", "a = 1\n")
    tool = EditTool(Workspace(tmp_path))

    async def cancelling(request: ApprovalRequest) -> ApprovalDecision:
        raise asyncio.CancelledError

    async def main() -> None:
        with use_tool_context(approval=cancelling):
            await tool.execute(
                _args(path="m.py", source_text="a = 1", target_text="a = 2")
            )

    with pytest.raises(asyncio.CancelledError):
        _run(main())

    assert (tmp_path / "m.py").read_text() == "a = 1\n"


# ---- the workspace boundary still comes first ---------------------------


def test_a_path_outside_the_workspace_is_refused(tmp_path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("secret = 1\n")
    inside = tmp_path / "ws"
    inside.mkdir()
    _seeded(inside, "ok.py", "a = 1\n")

    with pytest.raises(PathEscapesWorkspace):
        _edit(
            Workspace(inside),
            path="../outside.py",
            source_text="secret = 1",
            target_text="secret = 2",
        )

    assert outside.read_text() == "secret = 1\n"
    # The paired positive control: a legitimate path in the same workspace
    # must still work, or "refuses everything" would pass the test above.
    assert _edit(
        Workspace(inside), path="ok.py", source_text="a = 1", target_text="a = 2"
    )


def test_a_symlink_out_of_the_workspace_is_refused_before_anything_lands(tmp_path):
    """Plan 0029 Q10 and trap 3. ``Path.resolve`` follows links, so this
    layer is stricter than ``safe_path.go``'s prefix comparison — and the
    assertion is that the external file is untouched, not that an error
    came back."""
    external = tmp_path / "external"
    external.mkdir()
    victim = external / "victim.py"
    victim.write_text("original\n")
    inside = tmp_path / "ws"
    inside.mkdir()
    os.symlink(external, inside / "link")

    with pytest.raises(PathEscapesWorkspace):
        _edit(
            Workspace(inside),
            path="link/victim.py",
            source_text="original",
            target_text="tampered",
        )

    assert victim.read_text() == "original\n"


def test_a_sensitive_path_is_refused_by_its_own_class(tmp_path, monkeypatch):
    """Plan 0029 Q8: the credential list is checked after resolution, so a
    workspace-internal link to ``~/.ssh`` does not get through."""
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "id_rsa").write_text("KEY\n")
    monkeypatch.setenv("HOME", str(home))
    inside = tmp_path / "ws"
    inside.mkdir()
    os.symlink(home / ".ssh", inside / "keys")

    with pytest.raises(PathIsSensitive):
        _edit(
            Workspace(inside),
            path="keys/id_rsa",
            source_text="KEY",
            target_text="STOLEN",
        )

    assert (home / ".ssh" / "id_rsa").read_text() == "KEY\n"


# ---- what the file itself can be wrong about ----------------------------


def test_a_missing_file_says_which_tool_to_use_instead(tmp_path):
    """The case a model reaches by picking this tool when it wanted
    ``write_file``; "No such file or directory" does not say that."""
    with pytest.raises(ToolArgumentError) as refusal:
        _edit(
            Workspace(tmp_path),
            path="absent.py",
            source_text="a",
            target_text="b",
        )

    assert "does not exist" in str(refusal.value)
    assert "write_file" in str(refusal.value)


def test_a_directory_is_refused_as_a_directory(tmp_path):
    (tmp_path / "adir").mkdir()

    with pytest.raises(ToolArgumentError) as refusal:
        _edit(Workspace(tmp_path), path="adir", source_text="a", target_text="b")

    assert "is a directory" in str(refusal.value)


def test_a_binary_file_is_refused_rather_than_edited_through_replacements(tmp_path):
    """Decoding is strict here and lenient in ``read_file``'s byte mode,
    and the asymmetry is the point: this tool writes the bytes back."""
    blob = tmp_path / "data.bin"
    blob.write_bytes(b"\x00\x01\xff\xfe binary")

    with pytest.raises(ToolArgumentError) as refusal:
        _edit(Workspace(tmp_path), path="data.bin", source_text="a", target_text="b")

    assert "not valid UTF-8" in str(refusal.value)
    assert blob.read_bytes() == b"\x00\x01\xff\xfe binary"


def test_an_empty_path_is_refused_with_the_reason(tmp_path):
    with pytest.raises(ToolArgumentError) as refusal:
        _edit(Workspace(tmp_path), path="   ", source_text="a", target_text="b")

    assert "must name a file" in str(refusal.value)


def test_a_payload_that_is_not_this_tools_shape_is_correctable(tmp_path):
    tool = EditTool(Workspace(tmp_path))

    with use_tool_context(approval=_yes()):
        with pytest.raises(ToolArgumentError) as missing:
            _run(tool.execute(_args(path="m.py", source_text="a")))
        with pytest.raises(ToolArgumentError) as extra:
            _run(
                tool.execute(
                    _args(path="m.py", source_text="a", target_text="b", mode="x")
                )
            )

    assert "target_text" in str(missing.value)
    assert "mode" in str(extra.value)


# ---- the Environment seam (plan 0029 Q11) -------------------------------


class _FakeEnvironment:
    """A two-method environment, and a record of what crossed the seam."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.reads: list[str] = []
        self.writes: list[tuple[str, bytes]] = []

    async def read_file(self, path: str) -> bytes:
        self.reads.append(path)
        try:
            return self.files[path]
        except KeyError as exc:
            raise FileNotFoundError(2, "No such file or directory", path) from exc

    async def write_file(self, path: str, data: bytes) -> None:
        self.writes.append((path, data))
        self.files[path] = data


def test_the_environment_is_a_structural_protocol():
    assert isinstance(_FakeEnvironment({}), FileEditEnvironment)


def test_an_injected_environment_carries_both_halves_of_the_edit(tmp_path):
    """Q11's requirement that the parameter be *live*, and this tool's
    own: an edit routed through a container for its read and to the host
    for its write would corrupt the file rather than merely leak it."""
    resolved = str((tmp_path / "m.py").resolve())
    environment = _FakeEnvironment({resolved: b"a = 1\n"})
    tool = EditTool(Workspace(tmp_path), environment=environment)

    with use_tool_context(approval=_yes()):
        _run(tool.execute(_args(path="m.py", source_text="a = 1", target_text="a = 2")))

    assert environment.reads == [resolved, resolved]
    assert environment.writes == [(resolved, b"a = 2\n")]
    assert not (tmp_path / "m.py").exists(), "the host filesystem was not touched"


def test_the_workspace_boundary_applies_before_the_environment(tmp_path):
    """An environment does not widen the sandbox: the path is refused
    before anything crosses the seam."""
    environment = _FakeEnvironment({})
    tool = EditTool(Workspace(tmp_path), environment=environment)

    with pytest.raises(PathEscapesWorkspace):
        with use_tool_context(approval=_yes()):
            _run(
                tool.execute(
                    _args(path="/etc/passwd", source_text="root", target_text="x")
                )
            )

    assert environment.reads == [] and environment.writes == []


# ---- the registry's view, and trap 7's criterion -----------------------


def test_a_missing_file_is_an_error_and_a_no_op_edit_is_not(tmp_path):
    """Plan 0029 trap 7, as a pair in one test, with the criterion named.

    **The criterion is what the model should change next.** A missing file
    is answered by sending a different path, so it is ``is_error=True``. A
    no-op edit is answered by moving on, because the world is already in
    the requested state, so it is not. The other half of the pair lives in
    ``test_bash.py`` — a non-zero exit is not an error, a bad payload is.
    """
    _seeded(tmp_path, "m.py", "a = 1\n")
    registry = ToolRegistry()
    registry.register(
        EditTool(Workspace(tmp_path)),
        ToolPolicy(approval_mode=ApprovalMode.AUTO),
    )

    async def main() -> tuple[Any, Any]:
        absent = await registry.execute(
            ToolCall(
                id="1",
                name=TOOL_NAME,
                arguments=_args(path="nope.py", source_text="a", target_text="b"),
            )
        )
        noop = await registry.execute(
            ToolCall(
                id="2",
                name=TOOL_NAME,
                arguments=_args(
                    path="m.py", source_text="a = 1", target_text="a = 1"
                ),
            )
        )
        return absent, noop

    absent, noop = _run(main())

    assert absent.is_error is True
    assert noop.is_error is False


def test_the_registry_resolves_the_tightening_direction(tmp_path):
    """Plan 0028's lesson: a loosening test passing proves nothing.

    The tool's own policy is already ``ASK``; what has to be checked is
    that a deployment *registering* it as ``ASK`` over an ``AUTO`` author
    default would be honoured. So the tool is registered with ``AUTO`` and
    the run succeeds, then with the default and it fails closed.
    """
    _seeded(tmp_path, "m.py", "a = 1\n")
    loose = ToolRegistry()
    loose.register(
        EditTool(Workspace(tmp_path)), ToolPolicy(approval_mode=ApprovalMode.AUTO)
    )
    strict = ToolRegistry()
    strict.register(EditTool(Workspace(tmp_path)))

    call = ToolCall(
        id="1",
        name=TOOL_NAME,
        arguments=_args(path="m.py", source_text="a = 1", target_text="a = 2"),
    )

    # The strict registry runs first, so its refusal cannot be mistaken
    # for the anchor having already been consumed by the loose one.
    refused = _run(strict.execute(call))
    assert refused.is_error is True
    assert "approval" in refused.output
    assert (tmp_path / "m.py").read_text() == "a = 1\n"

    assert _run(loose.execute(call)).is_error is False
    assert (tmp_path / "m.py").read_text() == "a = 2\n"


# ---- the definition a model is shown ------------------------------------


def test_the_tool_satisfies_the_protocol_and_agrees_with_its_own_name():
    tool = EditTool()

    assert isinstance(tool, Tool)
    assert tool.name == TOOL_NAME == tool.definition().name == "edit_file"


def test_the_definition_is_stable_and_not_shared_between_instances():
    """Plan 0028's prompt-prefix-caching reason: the tool list has to be
    byte-identical from turn to turn, and two registries must not be able
    to mutate one another's schema."""
    first, second = EditTool(), EditTool()

    assert first.definition() is first.definition()
    first.definition().input_schema["properties"].pop("path")
    assert "path" in second.definition().input_schema["properties"]
    assert "path" in EDIT_SCHEMA["properties"]


def test_the_description_warns_about_the_line_number_prefix():
    """Plan 0029 Q9 requires the warning on *both* sides of the contract.
    ``read_file`` tells the model the prefix is display-only; this tool is
    where the model is holding the prefixed text."""
    description = EditTool().definition().description

    assert "line-number prefix" in description
    assert "EXACTLY ONCE" in description


def test_the_policy_is_declared_rather_than_defaulted():
    """Plan 0029 Q2. The values coincide with ``ToolPolicy()``'s
    defaults, which is exactly why they are written down: a guarded
    default nobody chose and one somebody chose are indistinguishable at
    the call site and different when the next person relaxes the default.
    """
    policy = EditTool.policy

    assert policy.risk_level is RiskLevel.HIGH
    assert policy.approval_mode is ApprovalMode.ASK
    assert policy.writes_workspace is True
    assert policy.read_only is False
    assert policy.concurrency_safe is False
    assert policy.allowed_in_background is False


def test_no_policy_field_name_reaches_the_prompt():
    """Plan 0028: a model shown its own approval rules is a model invited
    to argue with them."""
    definition = EditTool().definition()
    rendered = json.dumps(
        {"description": definition.description, "schema": definition.input_schema}
    )

    for field in ("risk_level", "approval_mode", "writes_workspace", "read_only"):
        assert field not in rendered


# ---- the diff builder, on its own ---------------------------------------


def test_a_pure_insertion_reports_zero_removals():
    change = describe_change("a\nb\n", "a\nNEW\nb\n")

    assert (change.removed, change.added) == (0, 1)
    assert change.diff is not None and "+ NEW" in change.diff


def test_a_pure_deletion_reports_zero_additions():
    change = describe_change("a\ngone\nb\n", "a\nb\n")

    assert (change.removed, change.added) == (1, 0)
    assert change.diff is not None and "- gone" in change.diff


def test_a_meaningful_trailing_blank_line_is_not_reported_as_deleted():
    """``edit_file.go:166-171``: dropping exactly one empty element undoes
    :meth:`str.split`'s artefact, while ``rstrip("\\n")`` would eat real
    blank lines at the end of a file."""
    unchanged = describe_change("a\n\n", "a\n\n")
    removed = describe_change("a\n\n", "a\n")

    assert (unchanged.removed, unchanged.added) == (0, 0)
    assert (removed.removed, removed.added) == (1, 0)


def test_a_crlf_file_does_not_report_every_line_as_changed():
    change = describe_change("a\r\nb\r\n", "a\r\nB\r\n")

    assert (change.removed, change.added) == (1, 1)


# ---- repairs from the independent audit ---------------------------------


def test_a_failed_write_leaves_the_original_file_intact(tmp_path, monkeypatch):
    """The claim ``_unwritable`` makes has to be true when it is made.

    A plain ``O_TRUNC`` open empties the file before the first byte is
    written, so an ENOSPC part-way through left a **zero-byte file** while
    the model was told "The file is unchanged". The write goes to a
    sibling temporary file and is moved into place, so a failure at any
    point leaves the original untouched.
    """
    seeded = _seeded(tmp_path, "m.py", "ORIGINAL ONE\nORIGINAL TWO\n")
    original = seeded.read_text()

    def full_disk(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fdopen", full_disk)

    with pytest.raises(ToolArgumentError) as refusal:
        _edit(
            Workspace(tmp_path),
            path="m.py",
            source_text="ORIGINAL ONE",
            target_text="EDITED ONE",
        )

    assert "could not write it back" in str(refusal.value)
    assert "file is unchanged" in str(refusal.value)
    assert seeded.read_text() == original, "the claim in that message is false"


def test_a_failed_write_leaves_no_temporary_file_behind(tmp_path, monkeypatch):
    """The other half: an atomic write that litters is its own problem."""
    _seeded(tmp_path, "m.py", "a = 1\n")

    def refuse(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(ToolArgumentError):
        _edit(
            Workspace(tmp_path), path="m.py", source_text="a = 1", target_text="a = 2"
        )

    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["m.py"]


def test_the_edited_file_keeps_the_permissions_it_had(tmp_path):
    """:func:`os.replace` installs a new inode, so the mode has to be
    carried over — an edit must not quietly make a script unreadable."""
    seeded = _seeded(tmp_path, "run.sh", "echo one\n")
    os.chmod(seeded, 0o750)

    _edit(
        Workspace(tmp_path),
        path="run.sh",
        source_text="echo one",
        target_text="echo two",
    )

    assert seeded.stat().st_mode & 0o777 == 0o750
    assert seeded.read_text() == "echo two\n"


def test_two_concurrent_edits_through_an_environment_do_not_lose_one(tmp_path):
    """The lost update the local path cannot show.

    With no environment, ``_get`` resolves without ever yielding to the
    loop, so the two tasks never interleave and **removing both path locks
    leaves the whole suite green**. Any real ``Environment`` — a container
    round-trip, an object store — awaits, and then the locks are the only
    thing standing between two edits and a silently discarded one.
    """
    resolved = str((tmp_path / "m.py").resolve())

    class _Slow:
        def __init__(self) -> None:
            self.files = {resolved: b"a = 1\nb = 1\n"}

        async def read_file(self, path: str) -> bytes:
            await asyncio.sleep(0)
            return self.files[path]

        async def write_file(self, path: str, data: bytes) -> None:
            await asyncio.sleep(0)
            self.files[path] = data

    environment = _Slow()

    async def main() -> list[object]:
        tool = EditTool(Workspace(tmp_path), environment=environment)
        first = _args(path="m.py", source_text="a = 1", target_text="a = 2")
        second = _args(path="m.py", source_text="b = 1", target_text="b = 2")
        with use_tool_context(approval=_yes()):
            return await asyncio.gather(
                tool.execute(first), tool.execute(second), return_exceptions=True
            )

    outcomes = _run(main())

    succeeded = [one for one in outcomes if not isinstance(one, BaseException)]
    assert len(succeeded) == 1, "both edits reported success; one was lost"
    assert environment.files[resolved] in (b"a = 2\nb = 1\n", b"a = 1\nb = 2\n")


def test_an_anchor_longer_than_the_file_is_simply_not_found(tmp_path):
    """The case ``edit_file.go``'s window guard exists for. It is handled
    by the scan itself — ``range`` of a negative length is empty — so the
    guard was unreachable code in the shape of a safeguard."""
    with pytest.raises(ToolArgumentError) as refusal:
        plan_edit("one line\n", "one line\ntwo\nthree\nfour\n", "x")

    assert "was not found" in str(refusal.value)


def test_level_four_strips_the_blocks_own_base_indent_before_re_hanging_it():
    """The half of the re-indentation every other L4 test leaves untested.

    Those all send a ``target_text`` whose non-blank lines already share an
    empty prefix, so the common-prefix computation is exercised only where
    it is a no-op. A model that sends its replacement indented — the
    natural thing after reading the file — would get **double** indentation
    without this, which in Python is an ``IndentationError``.
    """
    content = "class C:\n    def m(self):\n        a = 1\n        b = 2\n"

    result, level = replace_once(
        content,
        "a = 1\nb = 2",
        "    a = 1\n    b = 9",
    )

    assert level == MATCH_LINE_BY_LINE
    assert result == (
        "class C:\n    def m(self):\n        a = 1\n        b = 9\n"
    )


def test_level_four_keeps_relative_indentation_while_re_hanging_the_block():
    """A two-line anchor, so that L1 cannot match it verbatim and the
    re-indentation is really what produces the result."""
    content = "def f():\n    x = 1\n    y = 2\n"

    result, level = replace_once(
        content,
        "x = 1\ny = 2",
        "        if y:\n            z = 1",
    )

    assert level == MATCH_LINE_BY_LINE
    assert result == "def f():\n    if y:\n        z = 1\n"
