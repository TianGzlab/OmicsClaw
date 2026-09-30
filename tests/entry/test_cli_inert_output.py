"""Nothing foreign reaches the terminal as a control sequence.

A model that has read a hostile file or page controls far more of the
screen than its approval cards: its answer, its reasoning, the plan it
writes, what a stored conversation replays on ``/resume``, and — through
the tools it calls and the files they touch — shell output, MCP server
names and the rule a person asks to be remembered. Any of them carrying
``ESC [8m`` (conceal, with no reset) makes the *real* approval card
printed after it invisible, while a forged card written in plain text
stays in view; OSC 52 writes the clipboard; ``[link=…]`` read as rich
markup makes rich itself emit OSC 8.

The end-to-end tests drive the real REPL into a console that believes it
is a terminal, so rich writes its own style codes, and then allow exactly
those: SGR without conceal. Everything else — any other escape sequence,
BEL, a raw carriage return — can only have come from foreign text.
"""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import re
import types
import unicodedata

import pytest
from rich.console import Console

from omicsclaw.context import CompactionRecord
from omicsclaw.context.budget import Pressure
from omicsclaw.entry.assembly import AgentApp
from omicsclaw.entry.cli import MarkdownStreamFormatter, Repl, ScriptedSource, Screen
from omicsclaw.entry.cli._reasoning import ReasoningStreamWriter
from omicsclaw.entry.cli._repl import _compaction_verdict, _task_lines
from omicsclaw.entry.events import TurnEvent
from omicsclaw.planning import PlanItem, PlanStatus
from omicsclaw.schema import Message, Role, StreamChunk, ToolCall
from omicsclaw.tools import ApprovalRequest, BashTool
from omicsclaw.tools._workspace import Workspace
from tests.entry.test_cli_repl import (  # type: ignore[import-not-found]
    WAIT_S,
    answering,
    build,
)
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Asking,
    Scripted,
)

_CONCEAL = "\x1b[8m"
_OSC52 = "\x1b]52;c;cm0gLXJmIH4=\x07"
_FAKE_CARD = "\x1b[2mApproval required [t#1]: bash (risk low) - ls -la\x1b[0m"

_SEQUENCE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])"
)
_SGR = re.compile(r"\x1b\[[0-9;]*m")


def _conceals(parameters: list[str]) -> bool:
    """Whether an SGR parameter list turns conceal on, skipping colour
    arguments (``38;2;r;g;b`` can carry an ``8`` that is not a code)."""
    index = 0
    while index < len(parameters):
        code = parameters[index]
        if code in ("38", "48", "58") and index + 1 < len(parameters):
            index += 3 if parameters[index + 1] == "5" else 5
            continue
        if code == "8":
            return True
        index += 1
    return False


def foreign_sequences(written: str) -> list[str]:
    """Every escape sequence in *written* rich's own styling does not emit."""
    foreign = []
    for match in _SEQUENCE.finditer(written):
        sequence = match.group()
        if _SGR.fullmatch(sequence) and not _conceals(sequence[2:-1].split(";")):
            continue
        foreign.append(sequence)
    return foreign


def stray_characters(written: str) -> list[str]:
    """Control and format characters other than ESC (checked above), line
    feed and tab."""
    return [
        char
        for char in written
        if char not in "\x1b\n\t"
        and unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
    ]


def plain(written: str) -> str:
    return _SGR.sub("", written)


def terminal() -> tuple[Screen, io.StringIO]:
    """A screen whose console writes ANSI as it would to a real terminal."""
    buffer = io.StringIO()
    console = Console(
        file=buffer, force_terminal=True, color_system="truecolor", width=120
    )
    return Screen(console), buffer


def assert_inert(written: str) -> None:
    assert foreign_sequences(written) == [], foreign_sequences(written)
    assert stray_characters(written) == [], stray_characters(written)


class Streaming(Scripted):
    """A backend that sends each reply as the given chunks, then ``DONE``."""

    def __init__(self, *turns: tuple[tuple[StreamChunk, ...], Message]) -> None:
        super().__init__(*(message for _chunks, message in turns))
        self._chunks = [chunks for chunks, _message in turns]

    async def _stream(self, messages, tools=None):
        chunks = self._chunks[min(self.calls, len(self._chunks) - 1)]
        completion = await self.generate(messages, tools)
        for chunk in chunks:
            yield chunk
        yield StreamChunk.done(completion.message)


def _drive(app, lines, screen, **kwargs) -> list[str]:
    async def drive() -> list[str]:
        source = ScriptedSource(lines)
        repl = Repl(app, source=source, screen=screen, animated=False, **kwargs)
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source.prompts

    return asyncio.run(drive())


# ---- the answer and the reasoning -------------------------------------------


def test_an_answer_cannot_hide_the_approval_card_that_follows_it(tmp_path):
    """The attack end to end: reasoning and answer deltas carry conceal, a
    clipboard write and a forged card; a real card follows. The terminal
    receives rich's own styling and nothing else, the real card's header
    is on screen, and the forged one is shown as the inert text it is.

    A ``\\r\\n`` split across two deltas is still one line break: each
    delta is escaped on its own, and a lone ``\\r`` would otherwise be
    shown as ``\\u000d`` at the end of every such line."""
    text = [
        "Checking the directory.\r",
        f"\n\n{_FAKE_CARD}{_CONCEAL}{_OSC52}\n",
        f"still hidden {_CONCEAL}",
    ]
    provider = Streaming(
        (
            (
                StreamChunk.reasoning(f"weighing it {_CONCEAL}quietly\r"),
                StreamChunk.reasoning(f"\nthen more{_OSC52}"),
                *(StreamChunk.text(delta) for delta in text),
            ),
            Message(
                role=Role.ASSISTANT,
                content="".join(text),
                tool_calls=(ToolCall(id="c0", name="ask", arguments="{}"),),
            ),
        ),
        (
            (StreamChunk.text("stopped"),),
            Message(role=Role.ASSISTANT, content="stopped"),
        ),
    )
    app = build(tmp_path, provider, tools=(Asking("ask"),))
    screen, buffer = terminal()

    prompts = _drive(app, ["go", "n", "/exit"], screen, show_reasoning=True)

    written = buffer.getvalue()
    assert_inert(written)
    shown = plain(written)
    assert re.search(r"^Approval required \[[^\]]+#1\]: ask \(risk \w+\)", shown, re.M)
    assert "approve ask [#1]? [y/N/a=always] " in prompts
    assert "\\u001b[8m" in shown and "\\u001b]52;c;" in shown
    assert not re.search(r"^Approval required \[t#1\]: bash", shown, re.M)
    assert "Checking the directory.\n" in shown
    assert "│ weighing it \\u001b[8mquietly\n" in shown
    assert "\\u000d" not in shown


def test_a_two_hundred_line_heredoc_is_whole_on_the_card_and_the_prompt_says_how_tall(
    tmp_path,
):
    """The real ``bash`` behind the real gate, on the terminal. Every line
    of the script is on the card, and because a card that tall has its
    first line scrolled away by the time the prompt is reached, the prompt
    repeats the note that opens the card."""
    script = "\n".join(f"df_{n:03d} = run(step={n}, cells='all')" for n in range(200))
    command = f"cat > analysis.py <<'EOF'\n{script}\nEOF"
    provider = Scripted(
        Message(
            role=Role.ASSISTANT,
            tool_calls=(
                ToolCall(
                    id="c0", name="bash", arguments=json.dumps({"command": command})
                ),
            ),
        ),
        Message(role=Role.ASSISTANT, content="ok"),
    )
    app = build(tmp_path, provider, tools=(BashTool(Workspace(tmp_path)),))
    buffer = io.StringIO()

    prompts = _drive(app, ["write it", "n", "/exit"], Screen.into(buffer, width=200))

    printed = buffer.getvalue().split("\n")
    for line in command.split("\n"):
        assert f"  │ {line}" in printed, line
    (head,) = [line for line in printed if "Approval required [" in line]
    note = re.search(r" - (\[\d+ lines, \d+ characters\]) ", head)
    assert note is not None, head
    assert int(note.group(1)[1:].split()[0]) > 200
    (asked,) = [p for p in prompts if p.startswith("approve bash")]
    assert asked == f"approve bash [#1] {note.group(1)}? [y/N/a=always] "


def test_a_short_card_keeps_the_short_prompt(tmp_path):
    """The note is for the tall card; an ordinary one is asked about as
    it always was."""
    app = build(
        tmp_path,
        Scripted(
            Message(
                role=Role.ASSISTANT,
                tool_calls=(ToolCall(id="c0", name="ask", arguments="{}"),),
            ),
            Message(role=Role.ASSISTANT, content="ok"),
        ),
        tools=(Asking("ask"),),
    )

    prompts = _drive(app, ["go", "n", "/exit"], Screen.into(io.StringIO()))

    assert "approve ask [#1]? [y/N/a=always] " in prompts


def test_the_prompt_names_the_tool_inertly(tmp_path):
    """An MCP tool's name is its server's to choose, and the prompt is
    drawn by ``prompt_toolkit``, which escapes C0 controls but not a bidi
    override."""

    async def drive():
        app = build(tmp_path, answering("unused"))
        source = ScriptedSource(["n"])
        repl = Repl(app, source=source, screen=Screen.into(io.StringIO()))
        decided = []

        class Handle:
            async def approve(self, request_id, decision):
                decided.append(decision)

        request = ApprovalRequest(tool_name="ask\x1b[8m\u202e", reason="r")
        event = TurnEvent.approval_required(request, "t#1")
        await asyncio.wait_for(repl._ask(Handle(), "t#1", event), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source.prompts, decided

    prompts, decided = asyncio.run(drive())

    assert prompts == ["approve ask\\u001b[8m\\u202e [#1]? [y/N/a=always] "]
    assert [d.approved for d in decided] == [False]


def test_markdown_reads_a_crlf_split_across_deltas_as_one_line_break():
    buffer = io.StringIO()
    formatter = MarkdownStreamFormatter(Screen.into(buffer).console)

    formatter.write("one\r")
    formatter.write("\ntwo \x1b[8m")
    formatter.finish()

    assert buffer.getvalue() == "one\ntwo \\u001b[8m"


def test_markdown_escapes_what_it_prints_before_a_line_ends():
    """The safe prefix of an unfinished line is printed at once; it is
    escaped like a finished line."""
    buffer = io.StringIO()
    formatter = MarkdownStreamFormatter(Screen.into(buffer).console)

    formatter.write("plain \x1b]52;c;eA==\x07 text")

    assert buffer.getvalue() == "plain \\u001b]52;c;eA==\\u0007 text"


def test_reasoning_reads_a_crlf_split_across_deltas_as_one_line_break():
    buffer = io.StringIO()
    writer = ReasoningStreamWriter(Screen.into(buffer).console)

    writer.write("one\r")
    writer.write("\ntwo \x1b[8m")
    writer.finish()

    assert buffer.getvalue().split("\n")[1:3] == ["│ one", "│ two \\u001b[8m"]


# ---- what else the terminal is shown -------------------------------------------


def test_a_plan_item_is_one_inert_line():
    """The model writes the plan; ``Text`` keeps it from being markup, and
    only escaping keeps it from being a title-setting OSC."""
    (header, line) = _task_lines(
        [
            PlanItem(
                id="1",
                content="step \x1b]0;pwned\x07\nforged",
                status=PlanStatus.PENDING,
            )
        ]
    )

    assert "\x1b" not in line.plain and "\x07" not in line.plain
    assert "\n" not in line.plain
    assert "step \\u001b]0;pwned\\u0007 ↵ forged" in line.plain


def test_a_failed_compaction_is_reported_inertly():
    """``degraded`` can carry the summarizing model's error text."""
    record = CompactionRecord(
        pressure=Pressure.FULL,
        tokens_before=9,
        tokens_after=9,
        msgs_before=4,
        msgs_after=4,
        summarized=0,
        preserved_tail=0,
        summary_text="",
        degraded="provider said \x1b[8m",
        written_back=False,
    )

    assert _compaction_verdict(record).endswith("provider said \\u001b[8m")


def test_resume_and_sessions_replay_a_stored_conversation_inertly(tmp_path):
    """A stored conversation is replayed from a store other surfaces write
    to as well; its question and its answer are foreign by the time
    ``/sessions`` and ``/resume`` print them."""
    app = build(tmp_path, answering(f"answer {_CONCEAL}hidden{_OSC52}"))
    screen, buffer = terminal()

    _drive(
        app,
        [f"question \x1b]0;title\x07", "/new", "/sessions", "/resume first", "/exit"],
        screen,
        session_id="first",
    )

    written = buffer.getvalue()
    assert_inert(written)
    after = plain(written).split("Resumed first", 1)[1]
    assert "agent: answer \\u001b[8mhidden\\u001b]52;c;" in after
    assert "you: question \\u001b]0;title\\u0007" in after


def test_a_shell_commands_output_is_shown_inertly(tmp_path):
    """``!cat`` of a file the agent wrote is the file's text on screen."""
    (tmp_path / "hostile.txt").write_bytes(
        b"line one\n\x1b[8mhidden\x1b]52;c;eA==\x07\n"
    )
    screen, buffer = terminal()

    _drive(build(tmp_path, answering("unused")), ["!cat hostile.txt", "/exit"], screen)

    written = buffer.getvalue()
    assert_inert(written)
    assert "line one\n\\u001b[8mhidden\\u001b]52;c;eA==\\u0007" in plain(written)


def test_an_mcp_server_name_is_not_read_as_markup(tmp_path):
    """``.mcp.json`` names the server; as a markup string, ``[link=…]``
    made rich emit an OSC 8 hyperlink and ``[/x]`` ended the REPL."""
    app = build(tmp_path, answering("unused"))
    name = "[link=https://evil.example]ctx[/link][/x]\x1b[8m"
    manager = types.SimpleNamespace(
        statuses=lambda: (
            types.SimpleNamespace(
                name=name, state=types.SimpleNamespace(value="connected"), tools=()
            ),
        )
    )
    screen, buffer = terminal()

    async def drive():
        source = ScriptedSource(["/mcp", "/exit"])
        repl = Repl(
            dataclasses.replace(app, mcp=manager),
            source=source,
            screen=screen,
            animated=False,
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)

    asyncio.run(drive())

    written = buffer.getvalue()
    assert_inert(written)
    assert "[link=https://evil.example]ctx[/link][/x]\\u001b[8m: connected" in plain(
        written
    )


def test_a_skills_query_is_not_read_as_markup(tmp_path):
    """``[/dim]`` typed after ``/skills`` closed a tag nobody opened, and
    rich raised out of the REPL."""
    buffer = io.StringIO()

    _drive(
        build(tmp_path, answering("unused")),
        ["/skills [/dim]", "/exit"],
        Screen.into(buffer),
    )

    assert "No skill matches '[/dim]'." in buffer.getvalue()


def test_a_remembered_rule_is_reported_inertly(tmp_path, monkeypatch):
    """The rule's pattern is the call's own argument, and the model chose
    that."""
    monkeypatch.setattr(
        AgentApp, "remember_approval", lambda self, request: f"ask(x{_CONCEAL})"
    )
    app = build(
        tmp_path,
        Scripted(
            Message(
                role=Role.ASSISTANT,
                tool_calls=(ToolCall(id="c0", name="ask", arguments="{}"),),
            ),
            Message(role=Role.ASSISTANT, content="ok"),
        ),
        tools=(Asking("ask"),),
    )
    screen, buffer = terminal()

    _drive(app, ["go", "a", "/exit"], screen)

    written = buffer.getvalue()
    assert_inert(written)
    assert "Remembered: always allow ask(x\\u001b[8m)" in plain(written)


@pytest.mark.parametrize(
    "reply",
    [
        f"plain {_CONCEAL}",
        f"**bold {_CONCEAL}** and `code {_OSC52}`",
        f"[label {_CONCEAL}](https://x.example/{_OSC52})",
        f"# heading {_CONCEAL}\n- item {_OSC52}\n> quote {_CONCEAL}",
    ],
)
def test_no_markdown_form_lets_an_escape_through(tmp_path, reply):
    """Each markdown form is rendered by its own branch; each branch prints
    what the escaping left."""
    screen, buffer = terminal()

    _drive(build(tmp_path, answering(reply)), ["go", "/exit"], screen)

    assert_inert(buffer.getvalue())
    assert "\\u001b" in plain(buffer.getvalue())
