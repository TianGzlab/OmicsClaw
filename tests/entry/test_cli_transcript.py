"""What a tool call leaves in the scrollback, asserted line by line.

:class:`~omicsclaw.entry.cli._transcript.ToolTranscript` is driven
directly here rather than through the REPL. The properties under test are
about *bytes on a line* — which number, how much of an argument, how many
lines of output — and a test that reached them through a real exchange
would be asserting on the loop's timing as well.

``tests/entry/test_cli_render.py`` and ``tests/entry/test_cli_logging.py``
own the other half: that the transcript really is wired into the pump,
and that showing a payload on the screen did not also start logging it.
"""

from __future__ import annotations

import json

from omicsclaw.engine import EngineEvent
from omicsclaw.entry.cli._transcript import (
    ARGUMENT_CHARS,
    OUTPUT_LINES,
    ToolTranscript,
)
from omicsclaw.entry.display import approval_body, unreadable_arguments_note
from omicsclaw.entry.events import TurnEvent
from omicsclaw.planning import PLAN_WRITE_TOOL_NAME
from omicsclaw.schema import ToolCall, ToolResult
from omicsclaw.tools import ApprovalRequest


def started(call_id: str, name: str, arguments: str = "{}") -> TurnEvent:
    call = ToolCall(id=call_id, name=name, arguments=arguments)
    return TurnEvent.from_engine(
        EngineEvent.tool_start(call), session_id="s1", turn_id="t1"
    )


def finished(
    call_id: str, name: str, output: str = "", *, failed: bool = False
) -> TurnEvent:
    result = ToolResult(
        tool_call_id=call_id, name=name, output=output, is_error=failed
    )
    return TurnEvent.from_engine(
        EngineEvent.tool_finished(result), session_id="s1", turn_id="t1"
    )


def text_of(lines) -> str:
    return "\n".join(line.plain for line in lines)


def test_a_result_is_paired_to_its_call_even_when_they_finish_out_of_order():
    """The property the legacy surface could not have.

    ``surfaces/cli/interactive.py`` matched a result to a call by popping
    a per-*name* FIFO, which is right only while calls to one tool finish
    in the order they started. Two ``web_fetch`` calls against two hosts
    are the ordinary case where that is false, and the ids make it a
    non-question: the pairing is looked up, not inferred.
    """
    transcript = ToolTranscript()
    head = "-> web_fetch"
    transcript.render(started("a", "web_fetch", '{"url": "https://one"}'), head)
    transcript.render(started("b", "web_fetch", '{"url": "https://two"}'), head)

    second = text_of(transcript.render(finished("b", "web_fetch"), "<- web_fetch ok"))
    first = text_of(transcript.render(finished("a", "web_fetch"), "<- web_fetch ok"))

    assert second.startswith("(2)"), second
    assert first.startswith("(1)"), first


def test_an_unknown_result_is_left_unnumbered_rather_than_mislabelled():
    """A number nobody can trust is worse than a blank column."""
    transcript = ToolTranscript()
    transcript.render(started("a", "bash", '{"command": "ls"}'), "-> bash")

    orphan = text_of(transcript.render(finished("zzz", "bash"), "<- bash ok"))

    assert "(" not in orphan, orphan
    assert orphan.strip().startswith("<- bash ok")


def test_the_call_line_shows_the_argument_it_was_given():
    transcript = ToolTranscript()

    line = text_of(
        transcript.render(started("a", "bash", '{"command": "wc -l x.csv"}'), "-> bash")
    )

    assert 'command="wc -l x.csv"' in line


def test_arguments_that_are_not_json_show_only_their_length():
    """As on the approval card, and for the card's reason.

    This line used to show the first 120 characters as they arrived, on
    the grounds that a malformed payload is the evidence. But arguments
    that do not decode are most often a call the model's output was cut
    off inside, ``max_tokens`` reached mid-string, and without a decoded
    object there is no key by which ``"api_key": "sk-live-…"`` could be
    found and hidden: the credential went into a scrollback that gets
    pasted into bug reports. The length still says that there was a
    payload and that it was malformed.
    """
    arguments = (
        '{"url": "https://x.example", "api_key": "sk-live-SECRET123", "body": "trunc'
    )
    transcript = ToolTranscript()

    line = text_of(
        transcript.render(started("a", "web_fetch", arguments), "-> web_fetch")
    )

    assert "SECRET123" not in line and "api_key" not in line
    assert line == (
        f"(1) -> web_fetch  (not shown: {len(arguments)} characters that could "
        "not be read as JSON)"
    )
    card, _cut = approval_body(
        ApprovalRequest(tool_name="web_fetch", reason="", arguments=arguments)
    )
    assert line.endswith(unreadable_arguments_note(arguments))
    assert card == f"arguments: {unreadable_arguments_note(arguments)}"


def test_an_output_preview_stops_at_a_bounded_number_of_lines():
    """A transcript that reprints the output is the output, not a log of it."""
    transcript = ToolTranscript()
    transcript.render(started("a", "bash", "{}"), "-> bash")
    body = "\n".join(f"row {index}" for index in range(OUTPUT_LINES + 5))

    lines = transcript.render(finished("a", "bash", body), "<- bash ok")

    assert len(lines) == OUTPUT_LINES + 2, text_of(lines)
    assert "more line(s)" in text_of(lines)
    assert f"row {OUTPUT_LINES + 4}" not in text_of(lines)


def test_a_plan_write_shows_no_payload_because_the_surface_prints_it():
    """Both halves, not just the result.

    ``plan_write``'s *arguments* are the plan and its *output* is the
    plan; ``Repl._show_plan`` prints the plan underneath in the shape a
    person reads. Previewing either would put it on screen twice.
    """
    transcript = ToolTranscript()
    payload = '{"steps": [{"content": "load the Visium slide"}]}'

    call = text_of(
        transcript.render(started("a", PLAN_WRITE_TOOL_NAME, payload), "-> x")
    )
    result = text_of(
        transcript.render(finished("a", PLAN_WRITE_TOOL_NAME, payload), "<- x ok")
    )

    assert "Visium" not in call, call
    assert "Visium" not in result, result


def test_detail_off_leaves_the_head_exactly_as_it_was():
    """The escape hatch a deployment that must not show payload uses."""
    transcript = ToolTranscript(detail=False)
    secret = '{"command": "cat PATIENT-7.vcf"}'
    transcript.render(started("a", "bash", secret), "-> bash")

    call = text_of(transcript.render(started("b", "bash", secret), "-> bash"))
    result = text_of(
        transcript.render(finished("b", "bash", "chr1 12345"), "<- bash ok")
    )

    assert "PATIENT-7" not in call, call
    assert "chr1" not in result, result
    assert call.strip() == "(2) -> bash", "the number still pairs, the payload is gone"


def styles_of(line) -> list[str]:
    """Every style actually applied to *line*, base attribute and spans.

    Reading ``Text.style`` alone is the trap this helper exists for: a
    style passed to ``Text(...)`` lands there, but one added by
    ``.append(text, style=...)`` lands in ``.spans`` and leaves
    ``.style`` at its default. An assertion on ``.style`` therefore says
    nothing at all about an appended head line, and passes or fails on
    whichever *other* line happened to be built the other way.
    """
    return [str(line.style)] + [str(span.style) for span in line.spans]


def test_a_failed_head_line_is_marked_even_when_there_is_no_output():
    """The head is where ``error`` is, so the head is what must be marked.

    An empty output is the case that pins it: with no preview lines
    underneath, the head is the only line there is, and a check that was
    really reading the preview's style has nothing left to read.
    """
    transcript = ToolTranscript()
    transcript.render(started("a", "bash", "{}"), "-> bash")

    lines = transcript.render(finished("a", "bash", "", failed=True), "<- bash error")

    assert len(lines) == 1, text_of(lines)
    assert any("red" in style for style in styles_of(lines[0])), styles_of(lines[0])


def test_a_successful_head_line_is_not_marked():
    """The other half: a mark every line carries marks nothing."""
    transcript = ToolTranscript()
    transcript.render(started("a", "bash", "{}"), "-> bash")

    lines = transcript.render(finished("a", "bash", "", failed=False), "<- bash ok")

    assert not any("red" in style for style in styles_of(lines[0]))


def test_runs_of_whitespace_collapse_to_one_space():
    """So the budget is spent on content rather than on indentation.

    Indented text leaves long runs of spaces once it is on one line;
    without folding, the cut would land before the part worth reading.
    Each line break stays visible as ``↵`` rather than being folded away
    with the spaces, because a command that is two lines is a different
    command from the same words on one. Driven through a string value,
    which reaches the line as the model wrote it.
    """
    transcript = ToolTranscript()
    arguments = json.dumps({"command": "broken   \n\n  command"})

    line = text_of(transcript.render(started("a", "bash", arguments), "-> bash"))

    assert 'command="broken ↵ ↵ command"' in line, repr(line)


def test_a_long_argument_is_cut_and_the_cut_is_marked():
    """The other numeric bound this module introduced.

    An unmarked truncation reads as the whole argument and sends a person
    looking for a bug in a command that was never run that way.
    """
    transcript = ToolTranscript()
    long_command = "echo " + "x" * (ARGUMENT_CHARS * 2)

    line = text_of(
        transcript.render(
            started("a", "bash", json.dumps({"command": long_command})), "-> bash"
        )
    )

    assert len(line) < len(long_command), line
    assert "…" in line


def test_control_characters_never_reach_the_terminal():
    """A terminal executes an escape sequence rather than printing it.

    ``\x1b[2J\x1b[H`` clears the screen and homes the cursor — on the
    very transcript being written — and a tool's output is not this
    program's text. Newlines matter for a second reason: one of them in
    an argument would turn a call line into two.
    """
    transcript = ToolTranscript()
    evil = "\x1b[31mRED\x1b[0m\x1b[2J\x1b[H"

    call = transcript.render(started("a", "bash", json.dumps({"c": evil})), "-> bash")
    result = transcript.render(finished("a", "bash", f"one\ttwo{evil}"), "<- bash ok")

    for line in (*call, *result):
        rendered = line.plain
        assert "\x1b" not in rendered, repr(rendered)
        assert "\n" not in rendered, repr(rendered)
        assert "\t" not in rendered, repr(rendered)
    assert "RED" in text_of(call), "the readable part is kept, not the escape"


def test_an_event_that_is_not_a_tool_call_is_one_dim_line():
    """Everything else keeps exactly the shape the shared renderer gave it."""
    transcript = ToolTranscript()
    event = TurnEvent.exchange_end("converged", session_id="s1", turn_id="t1")

    lines = transcript.render(event, "Done.")

    assert len(lines) == 1
    assert lines[0].plain == "Done."


def test_a_credential_in_the_arguments_is_hidden_on_the_call_line():
    """The call line is scrollback, and scrollback is pasted into bug
    reports: a value under a credential-named key is hidden by the rule
    the approval card and the MCP preview use, at any depth."""
    transcript = ToolTranscript()
    arguments = json.dumps(
        {
            "url": "https://api.example/v1",
            "api_key": "sk-live-123",
            "headers": {"Authorization": "Bearer abc"},
        }
    )

    line = text_of(
        transcript.render(started("a", "web_fetch", arguments), "-> web_fetch")
    )

    assert "sk-live-123" not in line and "Bearer abc" not in line
    assert 'api_key="[redacted]"' in line
    assert '"Authorization": "[redacted]"' in line
    assert 'url="https://api.example/v1"' in line


def test_a_credential_in_a_list_of_arguments_is_hidden_too():
    transcript = ToolTranscript()

    line = text_of(
        transcript.render(started("a", "x", '[{"token": "t0k3n"}]'), "-> x")
    )

    assert "t0k3n" not in line and "[redacted]" in line


def test_the_head_is_made_inert_here_as_well():
    """The shared renderer already escapes the head; the transcript does it
    again because it is the last step before the terminal, and it cannot
    know every caller went through the renderer."""
    transcript = ToolTranscript()
    head = "-> x\x1b[8m‮"

    call = transcript.render(started("a", "x"), head)
    result = transcript.render(finished("a", "x"), f"<- x ok{chr(27)}[8m")
    other = transcript.render(
        TurnEvent.exchange_end("cancelled", session_id="s1", turn_id="t1"),
        "a\x1b[8m\nb",
    )

    for line in (*call, *result, *other):
        assert "\x1b" not in line.plain and "‮" not in line.plain, repr(line.plain)
    assert other[0].plain == "a\\u001b[8m\nb", "a multi-line head keeps its lines"
