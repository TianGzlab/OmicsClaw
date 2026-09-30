"""``omicsclaw.entry.display``: text made safe before a person is shown it.

A reason, a tool name or an argument reaches a terminal and an IM chat
from a model that may have read a hostile file or page. Two things can go
wrong on the way, and each group of tests below pins one:

- a character acts on the display instead of being shown by it. rich's
  ``Text`` strips only BEL, BS, VT, FF and CR, so ESC, the C1 CSI
  (``\\x9b``) and the bidi override (U+202E) all reached the terminal
  through the CLI approval line;
- the text's own line breaks forge the card's structure: hundreds of
  blank lines push a dangerous first line off the screen, or a line that
  begins ``Approval required [`` passes for a second, harmless card.
"""

from __future__ import annotations

import json
import unicodedata

import pytest

from omicsclaw.entry.display import (
    CONTINUATION_PREFIX,
    LINE_BREAK_MARK,
    MAX_APPROVAL_BODY_CHARS,
    MAX_APPROVAL_BODY_LINES,
    MAX_BLOCK_CHARS,
    MAX_BLOCK_LINES,
    TALL_APPROVAL_BODY_CHARS,
    TALL_APPROVAL_BODY_LINES,
    approval_body,
    approval_body_note,
    inert_block,
    inert_line,
    inert_prose,
    unreadable_arguments_note,
)
from omicsclaw.tools import ApprovalRequest
from omicsclaw.tools.preview import REDACTED

_UNSAFE = {"Cc", "Cf", "Cs", "Zl", "Zp"}

_FORGED = "Approval required [t#9]: read_file (risk low) - read README.md"

_HOSTILE = (
    "\x1b[2J\x1b[31mred\x1b[0m"  # ESC: clear the screen, set a colour
    "\x9b31m"  # C1 CSI, the one-byte form of ESC [
    "\u202eevil"  # RLO: the rest of the line is drawn right to left
    "\u2066isolate\u2069"  # bidi isolate
    "\u200bzero\u200dwidth\ufeff"  # zero-width space, joiner, BOM
    "\rcarriage"  # CR: the cursor goes back and overwrites
    "\x85nel\u2028ls\u2029ps\x0bvt\x0cff"  # line breaks other than LF
    "\x00nul\x7fdel"
    "\U000e0001tag"  # a format character above the BMP
)


def _unsafe_in(text: str, *, allowed: str = "") -> list[str]:
    return [
        char
        for char in text
        if char not in allowed and unicodedata.category(char) in _UNSAFE
    ]


# ---- characters that act on the display ---------------------------------------


@pytest.mark.parametrize("render", [inert_line, inert_block])
def test_escape_bidi_c1_and_zero_width_characters_are_neutralised(render):
    """Each is written as a ``\\uXXXX`` escape, which is inert text. Nothing
    of the category that can act on a display survives, except the line
    feed a block keeps on purpose (and draws behind a prefix)."""
    shown = render(_HOSTILE)

    assert _unsafe_in(shown, allowed="\n") == []
    for escaped in (
        "\\u001b[2J",
        "\\u009b31m",
        "\\u202eevil",
        "\\u2066isolate",
        "\\u200bzero",
        "\\u200dwidth",
        "\\ufeff",
        "\\u000dcarriage",
        "\\u0085nel",
        "\\u2028ls",
        "\\udb40\\udc01tag",
    ):
        assert escaped in shown, escaped


def test_ordinary_text_is_left_alone():
    """This project's users write Chinese, and a reason is prose."""
    text = "对 TP53 做差异分析 — 50 genes, α=0.05"

    assert inert_line(text) == text
    assert inert_block(text) == text


def test_a_line_shows_where_its_line_breaks_were():
    """One-line displays used to fold a newline into a space, and ``echo
    a`` then ``rm -rf b`` on two lines read as one harmless command."""
    assert inert_line("echo a\nrm -rf b") == f"echo a{LINE_BREAK_MARK}rm -rf b"
    assert inert_line("echo a\r\nrm -rf b") == f"echo a{LINE_BREAK_MARK}rm -rf b"
    assert "\n" not in inert_line("a\n\n\nb")


def test_a_line_shows_a_tab_as_a_space():
    """A tab is harmless but has no width a one-line display can count."""
    assert inert_line("a\tb") == "a b"


# ---- line structure ------------------------------------------------------------


def test_no_line_of_a_block_can_pass_for_a_card():
    """A reason cannot start a card line of its own: every line after the
    first carries the continuation prefix, so a forged header reads as
    part of the card it is in."""
    shown = inert_block(f"ls\n{_FORGED}\r\n{_FORGED}\n\n{_FORGED}")

    first, *rest = shown.split("\n")
    assert first == "ls"
    assert rest and all(line.startswith(CONTINUATION_PREFIX) for line in rest)
    assert not any(line.startswith("Approval required [") for line in rest)


def test_hundreds_of_blank_lines_cannot_push_the_first_line_off_the_screen():
    """The first line stays within :data:`MAX_BLOCK_LINES` rows of the card's
    header, and the header itself says the block was cut and by how much —
    so the person sees both the dangerous start and that something follows.

    Why 40 lines: the longest reason a tool writes by design is
    ``edit_file``'s diff — at most ``MAX_SUMMARY_LINES`` (20) changed lines
    plus three of context either side and a header, 27 lines — and it must
    fit whole. 40 leaves room for an ordinary multi-line command, and with
    the header, the legend and the prompt a card is still about one screen
    of a full-height terminal, where 500 blank lines would be ten screens.
    """
    shown = inert_block("rm -rf ~\n" + "\n" * 500 + "echo done")

    lines = shown.split("\n")
    assert MAX_BLOCK_LINES == 40
    assert len(lines) == MAX_BLOCK_LINES
    assert lines[0].startswith(f"[showing {MAX_BLOCK_LINES} of 502 lines, ")
    assert lines[0].endswith("] rm -rf ~")
    assert "echo done" not in shown
    assert all(line.startswith(CONTINUATION_PREFIX) for line in lines[1:])


def test_one_very_long_line_is_cut_too():
    """A single line wraps on screen, so 50,000 spaces after ``rm -rf ~``
    push it off the top as surely as blank lines do.

    Why 4,000 characters: 40 lines of 100 characters, the line bound's own
    size; on an 80-column terminal about fifty rows, one screen.
    """
    shown = inert_block("rm -rf ~;" + " " * 50_000 + "echo done")

    assert MAX_BLOCK_CHARS == 4000
    assert shown.startswith(
        f"[showing 1 of 1 lines, {MAX_BLOCK_CHARS} of 50018 characters] rm -rf ~;"
    )
    assert len(shown) < MAX_BLOCK_CHARS + 80
    assert "echo done" not in shown


def test_a_block_within_both_bounds_is_not_marked():
    text = "\n".join(f"line {n}" for n in range(MAX_BLOCK_LINES))

    shown = inert_block(text)

    assert not shown.startswith("[showing")
    assert shown.split("\n")[-1] == f"{CONTINUATION_PREFIX}line {MAX_BLOCK_LINES - 1}"


def test_the_bounds_are_parameters():
    assert inert_block("a\nb\nc", max_lines=2).startswith("[showing 2 of 3 lines")
    assert inert_block("abcdef", max_chars=3) == (
        "[showing 1 of 1 lines, 3 of 6 characters] abc"
    )


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_a_bound_that_is_not_a_positive_integer_is_refused(bad):
    with pytest.raises(ValueError, match="max_lines"):
        inert_block("x", max_lines=bad)
    with pytest.raises(ValueError, match="max_chars"):
        inert_block("x", max_chars=bad)


def test_a_block_keeps_tabs_and_indentation():
    """An edit diff of Go or a Makefile is indented with tabs; written as
    ``\\u0009`` it would be unreadable, and a tab cannot move the cursor
    back over anything."""
    assert inert_block("if x:\n\treturn 1") == f"if x:\n{CONTINUATION_PREFIX}\treturn 1"


# ---- prose: an answer or a thought, many lines, streamed ----------------------------


def test_prose_keeps_line_breaks_and_tabs_and_escapes_everything_else():
    """An answer is read as paragraphs, so its line breaks stay line breaks;
    every other character that can act on a display is written as an
    escape, exactly as in a line or a block."""
    shown = inert_prose(_HOSTILE)

    assert _unsafe_in(shown, allowed="\n\t") == []
    for escaped in ("\\u001b[2J", "\\u009b31m", "\\u202eevil", "\\u000dcarriage"):
        assert escaped in shown, escaped
    assert inert_prose("a\n\tb") == "a\n\tb"


def test_prose_reads_crlf_as_one_line_break():
    assert inert_prose("one\r\ntwo\r\n") == "one\ntwo\n"


def test_prose_has_no_prefix_and_is_never_cut():
    """Unlike a block, prose is the model's own answer on its own lines: it
    is not inside a card whose structure it could forge, and cutting it
    would lose the answer the person asked for."""
    text = "\n".join(f"line {n}" for n in range(1000)) + "x" * 50_000

    assert inert_prose(text) == text
    assert inert_prose("") == ""


def test_prose_neutralises_the_sequences_that_hide_a_later_card():
    """SGR 8 (conceal) with no reset hides whatever the terminal prints
    next, which is the real approval card; OSC 52 writes the clipboard."""
    shown = inert_prose("\x1b[8m\x1b]52;c;cm0gLXJmIH4=\x07\x1b\\")

    assert "\x1b" not in shown and "\x07" not in shown
    assert shown == "\\u001b[8m\\u001b]52;c;cm0gLXJmIH4=\\u0007\\u001b\\"


# ---- the approval card's body --------------------------------------------------


def _request(reason: str = "", arguments: str = "{}", *, shows_call: bool = False):
    return ApprovalRequest(
        tool_name="bash",
        arguments=arguments,
        reason=reason,
        reason_shows_call=shows_call,
    )


def _body_lines(body: str) -> list[str]:
    first, *rest = body.split("\n")
    assert all(line.startswith(CONTINUATION_PREFIX) for line in rest), rest
    return [first, *(line[len(CONTINUATION_PREFIX) :] for line in rest)]


def test_the_body_is_the_reason_then_the_arguments_as_the_card_showed_them():
    """Short bodies read exactly as the card did before the body had a
    function of its own: reason, then ``arguments:`` and indented JSON."""
    body, cut = approval_body(_request("look it up", '{"q": 1}'))

    assert cut is False
    assert body == (
        "look it up\n"
        f"{CONTINUATION_PREFIX}arguments: {{\n"
        f'{CONTINUATION_PREFIX}  "q": 1\n'
        f"{CONTINUATION_PREFIX}}}"
    )


def test_a_reason_that_shows_the_call_is_not_followed_by_the_arguments():
    body, cut = approval_body(
        _request("run: ls", '{"command": "ls"}', shows_call=True)
    )

    assert (body, cut) == ("run: ls", False)


def test_arguments_alone_make_the_body_and_nothing_makes_none():
    assert approval_body(_request("", '{"q": 1}'))[0].startswith("arguments: {")
    assert approval_body(_request("", "{}")) == ("", False)
    assert approval_body(_request("", '{"q": 1}', shows_call=True)) == ("", False)


def test_arguments_are_shown_as_indented_json_with_sorted_keys():
    """Two payloads that decode alike show alike, whatever order the model
    wrote their keys in."""
    body, _cut = approval_body(_request("", '{"z": 1, "command": "rm -rf ./build"}'))

    assert body == (
        "arguments: {\n"
        f'{CONTINUATION_PREFIX}  "command": "rm -rf ./build",\n'
        f'{CONTINUATION_PREFIX}  "z": 1\n'
        f"{CONTINUATION_PREFIX}}}"
    )


def test_a_line_break_inside_an_argument_cannot_start_a_card_line():
    """JSON writes it as ``\\n``, so a string value never adds a line."""
    payload = json.dumps({"command": f"ls\n{_FORGED}\x1b[2J\u202e"})

    body, _cut = approval_body(_request("", payload))

    assert len(body.split("\n")) == 3
    assert "\\n" + _FORGED in body
    assert _unsafe_in(body, allowed="\n") == []


@pytest.mark.parametrize("arguments", ["", "  ", "{}", "{ }"])
def test_no_arguments_add_no_arguments_line(arguments):
    assert approval_body(_request("", arguments)) == ("", False)
    assert approval_body(_request("why", arguments)) == ("why", False)


def test_arguments_that_are_not_json_show_only_their_length_on_the_body():
    """Without a decoded object there are no keys to hide values by."""
    arguments = '{"token": "s3cr3t", oops'

    body, _cut = approval_body(_request("why", arguments))

    assert "s3cr3t" not in body and "token" not in body
    assert unreadable_arguments_note(arguments) == (
        f"(not shown: {len(arguments)} characters that could not be read as JSON)"
    )
    assert body.endswith(f"arguments: {unreadable_arguments_note(arguments)}")


def test_arguments_nested_too_deeply_to_render_show_only_their_length():
    arguments = "[" * 100_000 + "]" * 100_000

    body, _cut = approval_body(_request("why", arguments))

    assert body.endswith(f"arguments: {unreadable_arguments_note(arguments)}")


def test_credentials_in_the_arguments_are_hidden_at_any_depth():
    """The rule is :func:`~omicsclaw.tools.preview.redact_credentials`'s,
    the same one the MCP preview uses, not a second copy."""
    payload = {
        "query": "TP53",
        "api_key": "sk-live-123",
        "nested": [{"Authorization": "Bearer abc"}, {"password": "hunter2"}],
    }

    body, _cut = approval_body(_request("why", json.dumps(payload)))

    for secret in ("sk-live-123", "Bearer abc", "hunter2"):
        assert secret not in body
    assert body.count(REDACTED) == 3
    assert f'"api_key": "{REDACTED}"' in body
    assert '"query": "TP53"' in body


def test_nothing_on_the_body_can_act_on_the_display_or_pass_for_a_header():
    body, _cut = approval_body(
        _request(f"{_HOSTILE}\n{_FORGED}", json.dumps({"c": _HOSTILE}))
    )

    assert _unsafe_in(body, allowed="\n\t") == []
    lines = body.split("\n")
    assert all(line.startswith(CONTINUATION_PREFIX) for line in lines[1:])
    assert not any(line.startswith("Approval required [") for line in lines)


def test_a_body_of_a_few_lines_carries_no_note():
    reason = "\n".join(f"step {n}" for n in range(TALL_APPROVAL_BODY_LINES))

    body, cut = approval_body(_request(reason, shows_call=True))

    assert cut is False
    assert body.startswith("step 0")
    assert approval_body_note(_request(reason, shows_call=True)) == ""


def test_a_tall_body_says_how_many_lines_it_has_on_its_first_line():
    """A card taller than a screen has its first line, which is where the
    command starts, scrolled away while the person reads the end; the note
    on that first line, repeated at the prompt, says how tall it is."""
    lines = TALL_APPROVAL_BODY_LINES + 1
    reason = "\n".join(f"step {n}" for n in range(lines))

    body, cut = approval_body(_request(reason, shows_call=True))

    assert cut is False
    assert body.startswith(f"[{lines} lines, {len(reason)} characters] step 0")
    assert _body_lines(body)[-1] == f"step {lines - 1}"


def test_one_long_line_is_tall_too():
    """Wrapped, 11,000 characters are a hundred rows on an 80-column
    terminal: as tall as a hundred lines, and noted like them, although
    the body has only three."""
    reason = "rm -rf ~\n" + " " * 11_000 + "x\necho harmless"

    body, cut = approval_body(_request(reason, shows_call=True))

    assert cut is False
    assert len(reason) > TALL_APPROVAL_BODY_CHARS
    assert body.startswith(f"[3 lines, {len(reason)} characters] rm -rf ~")


def test_runs_of_blank_lines_show_as_one_and_the_note_gives_the_true_count():
    """Blank lines are the cheapest way to push the dangerous first line off
    the screen and leave a harmless last one in view. Folded, the body is
    three lines, and the note still gives the 502 the reason really had."""
    reason = "rm -rf ~\n" + "\n" * 500 + "echo done"

    body, cut = approval_body(_request(reason, shows_call=True))

    assert cut is False
    assert _body_lines(body) == [
        f"[502 lines, {len(reason)} characters; 499 blank lines folded] rm -rf ~",
        "",
        "echo done",
    ]


def test_lines_of_only_spaces_and_tabs_are_blank_lines_too():
    reason = "a\n \n\t\n  \nb"

    body, _cut = approval_body(_request(reason, shows_call=True))

    assert _body_lines(body) == [
        f"[5 lines, {len(reason)} characters; 2 blank lines folded] a",
        "",
        "b",
    ]


_OTHER_SPACES = (
    "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009"
    "\u200a\u202f\u205f\u3000"
)
"""Every space separator but U+0020: the characters ``str.strip`` removes
that :func:`~omicsclaw.tools.preview.escape_unsafe` leaves as they are."""


@pytest.mark.parametrize("space", list(_OTHER_SPACES), ids=lambda c: f"U+{ord(c):04X}")
def test_a_line_of_any_other_space_is_a_line_of_the_command(space):
    """bash splits a command into words at space, tab and newline only;
    NBSP, U+3000 and the rest of the space separators are ordinary
    characters to it, so a line of them is a command word — the name of a
    function or alias the same script defined, run on that line. Folded as
    blank, that line vanished from the card while bash still ran it, so
    only spaces and tabs make a line blank."""
    assert unicodedata.category(space) == "Zs" and not space.strip()
    reason = f"echo start\n{space}\n{space}\n{space}\necho end"

    body, cut = approval_body(_request(reason, shows_call=True))

    assert cut is False
    assert _body_lines(body) == ["echo start", space, space, space, "echo end"]
    assert approval_body_note(_request(reason, shows_call=True)) == ""


def test_two_blank_lines_are_already_a_run():
    """The fold starts at two: one blank line is a paragraph break, and two
    are the shortest run that adds rows to the card without adding anything
    to read."""
    reason = "a\n\n\nb"

    body, cut = approval_body(_request(reason, shows_call=True))

    assert cut is False
    assert _body_lines(body) == [
        f"[4 lines, {len(reason)} characters; 1 blank line folded] a",
        "",
        "b",
    ]


def test_one_blank_line_is_left_alone_and_carries_no_note():
    """A paragraph break is not a way to hide anything."""
    assert approval_body(_request("a\n\nb", shows_call=True)) == (
        f"a\n{CONTINUATION_PREFIX}\n{CONTINUATION_PREFIX}b",
        False,
    )


def test_the_line_bound_is_on_reason_and_arguments_together():
    """Each part alone fits; the card they make together does not, and a
    card a screen cannot hold is cut once, not per part."""
    half = MAX_APPROVAL_BODY_LINES * 3 // 4
    reason = "\n".join(f"r{n}" for n in range(half))
    arguments = json.dumps({f"k{n:04d}": n for n in range(half)})

    assert approval_body(_request(reason, shows_call=True))[1] is False
    assert approval_body(_request("", arguments))[1] is False
    body, cut = approval_body(_request(reason, arguments))

    assert cut is True
    assert len(body.split("\n")) == MAX_APPROVAL_BODY_LINES
    total = half + half + 2  # the arguments' braces
    assert body.startswith(f"[showing {MAX_APPROVAL_BODY_LINES} of {total} lines, ")


def test_the_character_bound_is_on_reason_and_arguments_together():
    third = MAX_APPROVAL_BODY_CHARS * 2 // 3
    reason = "r" * third
    arguments = json.dumps({"content": "x" * third})

    assert approval_body(_request(reason, shows_call=True))[1] is False
    assert approval_body(_request("", arguments))[1] is False
    body, cut = approval_body(_request(reason, arguments))

    assert cut is True
    assert f", {MAX_APPROVAL_BODY_CHARS} of " in body.split("\n")[0]


def test_a_cut_body_says_what_it_shows_of_how_much():
    reason = "\n".join(f"line {n}" for n in range(1000))

    body, cut = approval_body(_request(reason, shows_call=True), max_lines=10)

    assert cut is True
    assert body.startswith(
        f"[showing 10 of 1000 lines, {len(chr(10).join(reason.split(chr(10))[:10]))}"
        f" of {len(reason)} characters] line 0"
    )
    assert "line 10" not in body


def test_the_cut_flag_is_exact_at_the_bounds():
    """A Channel refuses to send a card that was cut, so a flag that is
    wrong in either direction either sends half a command or refuses a
    whole one."""
    three = "a\nb\nc"

    assert approval_body(_request(three, shows_call=True), max_lines=3)[1] is False
    assert approval_body(_request(three, shows_call=True), max_lines=2)[1] is True
    assert approval_body(_request(three, shows_call=True), max_chars=5)[1] is False
    assert approval_body(_request(three, shows_call=True), max_chars=4)[1] is True
    folded = "a\n\n\n\nb"
    assert approval_body(_request(folded, shows_call=True), max_lines=3)[1] is False


def test_a_cut_just_past_a_line_does_not_count_the_next_line_as_shown():
    """With the character bound falling just after ``aaaaa``'s line break,
    the note used to read "showing 2 of 2 lines" over an empty second line:
    ``rm -rf ~`` was not on the card, and the note said every line was."""
    reason = "aaaaa\nrm -rf ~"

    for max_chars in (5, 6):
        body, cut = approval_body(_request(reason, shows_call=True), max_chars=max_chars)

        assert cut is True
        assert body == f"[showing 1 of 2 lines, 5 of {len(reason)} characters] aaaaa"


def test_a_line_cut_short_ends_with_a_mark():
    """Unmarked, ``rm -rf ./build`` cut after ``rm -rf .`` reads as a whole
    command that deletes the working directory: the last line of a cut body
    must not pass for a complete one."""
    reason = "echo ok\nrm -rf ./build"

    body, cut = approval_body(_request(reason, shows_call=True), max_chars=16)

    assert cut is True
    assert _body_lines(body) == [
        f"[showing 2 of 2 lines, 16 of {len(reason)} characters] echo ok",
        "rm -rf .…",
    ]


def test_a_cut_line_that_ends_on_a_line_bound_is_whole_and_unmarked():
    reason = "\n".join(f"line {n}" for n in range(5))

    body, _cut = approval_body(_request(reason, shows_call=True), max_lines=2)

    assert _body_lines(body)[-1] == "line 1"


def test_the_note_counts_characters_as_written_not_as_escaped():
    """Five hundred ESC characters take 3,000 on screen, so the card is tall
    and noted; the note gives the size of what is being approved, not of
    the escapes it is drawn with. A CRLF line break is written as two
    characters and is one line break."""
    escaped = "x\n" + "\x1b" * 500
    crlf = "\r\n".join(f"step {n}" for n in range(TALL_APPROVAL_BODY_LINES + 1))
    first_whole = "\x1b" * 10 + "\nrm -rf ~"

    assert approval_body_note(_request(escaped, shows_call=True)) == (
        f"[2 lines, {len(escaped)} characters]"
    )
    assert approval_body_note(_request(first_whole, shows_call=True), max_lines=1) == (
        f"[showing 1 of 2 lines, 10 of {len(first_whole)} characters]"
    )
    assert approval_body_note(_request(crlf, shows_call=True)) == (
        f"[{TALL_APPROVAL_BODY_LINES + 1} lines, {len(crlf)} characters]"
    )


def test_a_cut_never_splits_an_escape_and_counts_what_it_shows_as_written():
    """The cut is made on what the screen shows, so 2,000 ESC characters,
    12,000 on screen, reach the bound; it stops at the last whole escape,
    since ``\\u00`` shows no character at all, and the note counts the ESC
    characters shown, not their escapes."""
    reason = "run:\n" + "\x1b" * 2000 + "\nrm -rf ~"

    body, cut = approval_body(_request(reason, shows_call=True))

    assert cut is True
    first, second = _body_lines(body)
    assert first == f"[showing 2 of 3 lines, 2004 of {len(reason)} characters] run:"
    assert second == "\\u001b" * 1999 + "…"
    assert "rm -rf" not in body


def test_a_folded_and_cut_body_counts_both_sides_of_the_note_in_the_same_lines():
    """The note used to put the rows on screen over the lines written,
    ``showing 15 of 70 lines ... 49 blank lines folded``, and no reading
    of those three numbers adds up. Both sides now count lines as written,
    a folded run as all the lines it stands for; the folded count is of
    the lines shown, so the rows on screen are shown less folded."""
    reason = "\n".join(["a"] * 10 + [""] * 50 + ["b"] * 10)

    body, cut = approval_body(_request(reason, shows_call=True), max_lines=15)

    assert cut is True
    lines = _body_lines(body)
    assert lines[0] == (
        f"[showing 64 of 70 lines, 77 of {len(reason)} characters; "
        "49 blank lines folded] a"
    )
    assert lines[1:] == ["a"] * 9 + [""] + ["b"] * 4
    assert len(lines) == 64 - 49


def test_a_run_past_the_cut_is_not_counted_as_folded():
    """Lines the card does not reach are not shown, folded or otherwise."""
    reason = "\n".join(["a"] * 3 + [""] * 5 + ["b"] + [""] * 5 + ["c"])

    body, _cut = approval_body(_request(reason, shows_call=True), max_lines=5)

    assert _body_lines(body) == [
        f"[showing 9 of 15 lines, 12 of {len(reason)} characters; "
        "4 blank lines folded] a",
        "a",
        "a",
        "",
        "b",
    ]


@pytest.mark.parametrize(
    ("reason", "bounds", "note"),
    [
        pytest.param(
            "\n".join(f"step {n}" for n in range(21)),
            {},
            "[21 lines, 157 characters]",
            id="tall",
        ),
        pytest.param(
            "rm -rf ~\n" + "\n" * 500 + "echo done",
            {},
            "[502 lines, 518 characters; 499 blank lines folded]",
            id="folded",
        ),
        pytest.param(
            "\n".join(f"line {n}" for n in range(1000)),
            {"max_lines": 10},
            "[showing 10 of 1000 lines, 69 of 8889 characters]",
            id="cut",
        ),
        pytest.param(
            "\n".join(["a"] * 10 + [""] * 50 + ["b"] * 10),
            {"max_lines": 15},
            "[showing 64 of 70 lines, 77 of 89 characters; 49 blank lines folded]",
            id="folded-and-cut",
        ),
    ],
)
def test_the_note_is_repeatable_elsewhere(reason, bounds, note):
    """The prompt under a tall card repeats this, without parsing the body,
    so it must be the very note the body opens with."""
    request = _request(reason, shows_call=True)

    assert approval_body_note(request, **bounds) == note
    assert approval_body(request, **bounds)[0].startswith(f"{note} ")


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_a_body_bound_that_is_not_a_positive_integer_is_refused(bad):
    with pytest.raises(ValueError, match="max_lines"):
        approval_body(_request("x"), max_lines=bad)
    with pytest.raises(ValueError, match="max_chars"):
        approval_body(_request("x"), max_chars=bad)


def test_the_body_bounds_hold_an_ordinary_script_whole():
    """Why 400 lines and 12,000 characters: a heredoc that writes an
    analysis script is the longest command a person routinely approves,
    and a card that cuts it asks them to approve what they cannot read.
    Two hundred lines of forty characters fit with room to spare."""
    assert MAX_APPROVAL_BODY_LINES == 400
    assert MAX_APPROVAL_BODY_CHARS == 12_000
    script = "\n".join(f"print('row {n:03d}', {'x' * 20!r})" for n in range(200))
    reason = f"run:\ncat > a.py <<'EOF'\n{script}\nEOF"

    body, cut = approval_body(_request(reason, shows_call=True))

    assert cut is False
    for n in range(200):
        assert f"print('row {n:03d}'" in body


def test_a_count_of_one_takes_the_singular():
    """A note is read by a person deciding whether to approve; "1 lines" reads
    as a slip and invites doubt about the numbers beside it."""
    reason = "x" * 30

    body, cut = approval_body(_request(reason, shows_call=True), max_chars=10)

    assert cut is True
    assert _body_lines(body)[0].startswith("[showing 1 of 1 line, ")
