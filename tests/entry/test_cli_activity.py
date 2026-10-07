"""Being told what is happening, without taking the screen to say it.

Two halves. The first drives :class:`~omicsclaw.entry.cli._activity.
ActivityLine` directly over an injected clock, because every property
worth pinning about it — that it erases before it repaints, that it
leaves nothing behind, that a pipe never sees an escape code — is a
statement about bytes and not about timing. The second drives the real
:class:`~omicsclaw.entry.cli.Repl` over a real
:class:`~omicsclaw.entry.assembly.AgentApp` and a tool that actually
takes time, because the claim "a long wait is now visible" is not true
of a class, it is true of a loop.

There is no ``pytest-asyncio`` on this machine, so every test drives
:func:`asyncio.run` itself and **every await is inside an
:func:`asyncio.wait_for`** — the convention ``test_cli_repl.py`` sets and
for its reason: a defect in this mechanism is a hang, and a hang with no
timeout plugin is a run that never finishes.

The integration half shortens the tick interval rather than sleeping for
the real one. A test that waited 0.12 s per frame would be pinning the
constant instead of the behaviour, and would be the first thing to go
flaky on a loaded machine.
"""

from __future__ import annotations

import asyncio
import io
import json
import pathlib

from rich.console import Console

from omicsclaw.entry.cli import Repl, Screen, ScriptedSource
from omicsclaw.entry.cli import _activity
from omicsclaw.entry.cli._activity import ActivityLine
from omicsclaw.entry.session import attach_sessions
from omicsclaw.planning import PlanItem
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
)
from omicsclaw.tools import (
    ApprovalMode,
    ToolPolicy,
    report_progress,
    require_approval,
)
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    calling,
    make_app,
)

WAIT_S = 10.0
"""Every await in this file is bounded by it."""

_ERASE = "\r\x1b[2K"
"""Spelled out here rather than imported, so that a change to the
sequence has to be made twice — once where it is written and once where
a test says what a terminal will receive."""

_FRAME_START = _ERASE + "\x1b[2m"
_FRAME_END = "\x1b[0m"


def frames(written: str) -> list[str]:
    """Only what the live line painted, with the ordinary output removed.

    Asserting on the whole buffer is the trap this function exists to
    close: the pump already prints a dim ``-> slowly`` for every tool
    call, so ``"slowly" in written`` is true of a build whose live line
    never names anything. A frame is the one thing that is only there if
    the line really painted it.
    """
    return [
        chunk.split(_FRAME_END, 1)[0]
        for chunk in written.split(_FRAME_START)[1:]
    ]


# ---- doubles -------------------------------------------------------------


class Clock:
    """A monotonic clock a test advances by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def terminal_screen(width: int = 100) -> tuple[Screen, io.StringIO]:
    """A screen that claims to be a terminal but emits no colour of its own.

    ``color_system=None`` is what makes the assertions readable: every
    escape sequence in the buffer afterwards was written by
    :mod:`~omicsclaw.entry.cli._activity` rather than by rich styling a
    dim line.
    """
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        width=width,
        force_terminal=True,
        color_system=None,
        highlight=False,
        soft_wrap=True,
        emoji=False,
        _environ={"TERM": "xterm"},
    )
    return Screen(console), buffer


class Slow:
    """A tool that takes measurable time, so a wait has something to show."""

    policy = ToolPolicy(approval_mode=ApprovalMode.AUTO, concurrency_safe=True)

    def __init__(self, name: str = "slowly", delay_s: float = 0.25) -> None:
        self._name = name
        self._delay_s = delay_s

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description="Takes a while.",
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: str) -> str:
        await asyncio.sleep(self._delay_s)
        return "finished eventually"


class Announcing:
    """A tool that reports what it is doing, then does it — like ``bash``.

    ``report_progress`` before the first ``await`` is what puts a
    ``PROGRESS`` frame on the stream ahead of the ``TOOL_START`` that
    announces the same call; this double is that ordering, kept as a test
    rather than as a paragraph.
    """

    policy = ToolPolicy(approval_mode=ApprovalMode.AUTO, concurrency_safe=True)

    def __init__(self, name: str = "slowly", delay_s: float = 0.25) -> None:
        self._name = name
        self._delay_s = delay_s

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description="Says what it is doing.",
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: str) -> str:
        await report_progress(
            "running in /tmp/ocdemo: sleep 20", tool_name=self._name
        )
        await asyncio.sleep(self._delay_s)
        return "finished eventually"


class SlowAsking:
    """A tool that asks a human and *then* takes time.

    Both halves matter: the first makes a window in which the live line
    must be silent, the second makes a window in which it must speak
    again. A tool that only asked could not tell a hold that is released
    from one that leaks.
    """

    policy = ToolPolicy(approval_mode=ApprovalMode.ASK, concurrency_safe=True)

    def __init__(self, name: str = "ask", delay_s: float = 0.25) -> None:
        self._name = name
        self._delay_s = delay_s

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description="Asks, then works.",
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: str) -> str:
        await require_approval(self._name, arguments)
        await asyncio.sleep(self._delay_s)
        return f"{self._name} ran"


class Dozing(Scripted):
    """A backend whose *second* reply takes measurable time to begin.

    The window after a tool result and before the next token — the one
    that is silent in every build where the live line only runs during
    tools.
    """

    def __init__(self, *replies: Message, pause_s: float = 0.25) -> None:
        super().__init__(*replies)
        self._pause_s = pause_s

    async def generate(self, messages, tools=None):
        if self.calls:
            await asyncio.sleep(self._pause_s)
        return await super().generate(messages, tools)


class SlowStream(Scripted):
    """A backend that pauses *between* two text deltas of one answer.

    The arrangement that makes the streaming rule testable: while the
    pause lasts the cursor is mid-line, and anything the live line paints
    lands between the two halves of a sentence.
    """

    def __init__(self, first: str, second: str, *, pause_s: float = 0.25) -> None:
        super().__init__(Message(role=Role.ASSISTANT, content=first + second))
        self._halves = (first, second)
        self._pause_s = pause_s

    async def _stream(self, messages, tools=None):
        completion = await self.generate(messages, tools)
        first, second = self._halves
        yield StreamChunk(type=StreamChunkType.TEXT_DELTA, delta=first)
        await asyncio.sleep(self._pause_s)
        yield StreamChunk(type=StreamChunkType.TEXT_DELTA, delta=second)
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)


class Dawdling:
    """A prompt source that takes its time answering, and watches the screen.

    Records what was written to *buffer* between the moment a prompt was
    put and the moment it was answered — which is exactly the window in
    which a live line must not paint, because on a real terminal
    ``prompt_toolkit`` owns those columns.
    """

    def __init__(self, buffer: io.StringIO, lines, *, verdict: str = "y",
                 pause_s: float = 0.25) -> None:
        self._buffer = buffer
        self._lines = list(lines)
        self._verdict = verdict
        self._pause_s = pause_s
        self.prompts: list[str] = []
        self.during: list[str] = []
        self.answered_at = 0
        """Where the buffer stood when the last question was answered, so
        a test can ask what happened *after* the hold should have been
        given back."""

    async def read(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not prompt.startswith("approve "):
            await asyncio.sleep(0)
            if not self._lines:
                raise EOFError
            return self._lines.pop(0)
        mark = len(self._buffer.getvalue())
        await asyncio.sleep(self._pause_s)
        self.during.append(self._buffer.getvalue()[mark:])
        self.answered_at = len(self._buffer.getvalue())
        return self._verdict

    def close(self) -> None:
        self._lines.clear()


def planning_call(*steps: tuple[str, str]) -> Message:
    """One assistant message writing *steps* through the real tool."""
    payload = {
        "steps": [
            {"id": f"s{index}", "content": content, "status": status}
            for index, (content, status) in enumerate(steps, start=1)
        ]
    }
    return Message(
        role=Role.ASSISTANT,
        tool_calls=(
            ToolCall(id="c0", name="plan_write", arguments=json.dumps(payload)),
        ),
    )


def build(tmp_path: pathlib.Path, provider, *, tools=None, **overrides):
    """A real app with a registry, defaulting to the **foundation** tools.

    ``tools=None`` rather than ``()``: an explicit sequence replaces the
    whole registry, which would leave ``plan_write`` unmounted and
    ``AgentApp.plans`` set to ``None`` (``assembly.py:1080-1088``) — and
    every plan test here would then be asserting about a deployment that
    does not plan.
    """
    return attach_sessions(make_app(tmp_path, provider, tools=tools, **overrides))


# ---- half one: the line itself -------------------------------------------


def test_a_terminal_line_erases_itself_before_every_repaint():
    """The property that keeps the scrollback free of frames.

    Three erases for two paints: one ahead of each repaint and one from
    :meth:`~omicsclaw.entry.cli._activity.ActivityLine.close`. A paint
    that forgot its erase would leave both frames on the line and every
    earlier frame in the transcript.
    """
    clock = Clock()
    screen, buffer = terminal_screen()
    line = ActivityLine(screen, animated=True, clock=clock)

    line.begin("slowly", "reading the counts matrix")
    line.tick()
    clock.advance(4.0)
    line.tick()
    line.close()

    written = buffer.getvalue()
    assert written.count(_ERASE) == 3, repr(written)
    assert "slowly" in written
    assert "reading the counts matrix" in written
    assert "4s" in written
    assert written.endswith(_ERASE), "something was left on the line"


def test_a_held_line_paints_nothing_until_it_is_released():
    """Who owns the cursor is a question this class must answer ``no`` to.

    While an answer streams or an approval prompt is up, the columns
    belong to somebody else — so a tick in that window must produce no
    bytes at all, not merely tidier bytes.
    """
    clock = Clock()
    screen, buffer = terminal_screen()
    line = ActivityLine(screen, animated=True, clock=clock)
    line.begin("slowly")

    line.hold()
    for _ in range(3):
        clock.advance(1.0)
        line.tick()
    held = buffer.getvalue()

    line.release()
    line.tick()

    assert held == "", f"painted while held: {held!r}"
    assert "slowly" in buffer.getvalue()


def test_two_holders_need_two_releases():
    """Counted, because two tools in one message can both be asking.

    A boolean hold would let the first answered approval hand the cursor
    back while the second question is still on screen.
    """
    clock = Clock()
    screen, buffer = terminal_screen()
    line = ActivityLine(screen, animated=True, clock=clock)
    line.begin("slowly")

    line.hold()
    line.hold()
    line.release()
    line.tick()
    after_one = buffer.getvalue()

    line.release()
    line.tick()

    assert after_one == "", f"painted with one holder left: {after_one!r}"
    assert "slowly" in buffer.getvalue()


def test_a_pipe_never_receives_an_escape_sequence():
    """The rule a redirected run depends on, asserted over the bytes.

    Driven well past the heartbeat so that the non-terminal path really
    does write something — a test that only proved silence would also
    pass against a line that had been deleted.
    """
    clock = Clock()
    buffer = io.StringIO()
    line = ActivityLine(
        Screen.into(buffer), clock=clock, heartbeat_s=10.0
    )
    line.begin("slowly", "reading the counts matrix")

    for _ in range(40):
        clock.advance(1.0)
        line.tick()
    line.close()

    written = buffer.getvalue()
    assert not line.animated
    assert "\x1b" not in written, repr(written)
    assert "\r" not in written, repr(written)
    assert "still slowly" in written


def test_a_dumb_terminal_is_not_asked_to_erase_a_line():
    """``TERM=dumb`` is a tty and still cannot do ``\\x1b[2K``.

    ``is_terminal`` alone would say yes to it — the two are separate
    questions and rich answers both — and the visible cost of getting it
    wrong is a column of ``[2K`` down the side of the session.
    """
    clock = Clock()
    buffer = io.StringIO()
    console = Console(
        file=buffer, width=100, force_terminal=True, _environ={"TERM": "dumb"}
    )
    line = ActivityLine(Screen(console), clock=clock, heartbeat_s=10.0)
    line.begin("slowly")

    assert console.is_terminal and console.is_dumb_terminal
    assert not line.animated

    for _ in range(15):
        clock.advance(1.0)
        line.tick()

    assert "\x1b" not in buffer.getvalue(), repr(buffer.getvalue())
    assert "still slowly" in buffer.getvalue()


def test_a_short_wait_adds_nothing_to_a_piped_transcript():
    """``oc cli --prompt ... > answer.txt`` keeps the output it had.

    The whole reason the heartbeat has a threshold: visibility is bought
    only where there would otherwise have been a silence long enough to
    read as a dead process.
    """
    clock = Clock()
    buffer = io.StringIO()
    line = ActivityLine(Screen.into(buffer), clock=clock, heartbeat_s=30.0)
    line.begin("slowly")

    for _ in range(9):
        clock.advance(1.0)
        line.tick()

    assert buffer.getvalue() == "", repr(buffer.getvalue())


def test_a_long_wait_adds_one_line_per_heartbeat():
    """One line per interval, not one per tick.

    A heartbeat that fired on every poll would turn a four-minute
    ``bash`` into two hundred identical lines, which is a different way
    of telling somebody nothing.
    """
    clock = Clock()
    buffer = io.StringIO()
    line = ActivityLine(Screen.into(buffer), clock=clock, heartbeat_s=10.0)
    line.begin("slowly")

    for _ in range(35):
        clock.advance(1.0)
        line.tick()

    written = buffer.getvalue()
    assert written.count("still slowly") == 3, repr(written)
    assert "10s" in written and "20s" in written and "30s" in written


def test_a_new_detail_does_not_restart_the_elapsed_clock():
    """The number that answers "is it stuck?" must keep counting.

    A tool reporting progress twice is one activity with two things to
    say; resetting the clock on the second would make a wedged tool that
    still chats look permanently young.
    """
    clock = Clock()
    screen, buffer = terminal_screen()
    line = ActivityLine(screen, animated=True, clock=clock)

    line.begin("slowly", "starting")
    clock.advance(12.0)
    line.detail("still going")
    line.tick()

    assert "12s" in buffer.getvalue(), repr(buffer.getvalue())
    assert "still going" in buffer.getvalue()


def test_a_starting_tool_keeps_only_its_own_message():
    """``started`` restarts the clock; whose message it keeps is the test.

    Keeping unconditionally would put the last tool's command under the
    next tool's name — a line that is confidently wrong, which is the
    one thing worse than a line that says nothing.
    """
    clock = Clock()
    screen, buffer = terminal_screen()
    line = ActivityLine(screen, animated=True, clock=clock)

    line.detail("running in /tmp: sleep 20", tool="bash")
    clock.advance(7.0)
    line.started("bash")
    line.tick()
    same = buffer.getvalue()

    line.started("read_file")
    line.tick()
    other = buffer.getvalue()[len(same) :]

    assert "bash(running in /tmp: sleep 20)" in same, repr(same)
    assert "  0s" in same, "the clock did not restart with the call"
    assert "read_file" in other
    assert "sleep 20" not in other, f"inherited another tool's message: {other!r}"


def test_a_tool_that_reports_a_newline_cannot_break_the_line():
    """A progress message is a string this module was handed.

    A newline in one would end the row the next ``\\r`` was going to
    rewind, and an escape sequence in one would set a colour nothing
    resets — so the newline is drawn as a mark and the escape is written
    out as text before the line is composed.
    """
    clock = Clock()
    screen, buffer = terminal_screen()
    line = ActivityLine(screen, animated=True, clock=clock)

    line.begin("slowly", "line one\nline two\x1b[31m")
    line.tick()

    painted = buffer.getvalue()
    assert "\n" not in painted, repr(painted)
    assert "\x1b[31m" not in painted, repr(painted)
    assert "line one ↵ line two\\u001b[31m" in painted


def test_c1_controls_and_format_characters_never_reach_the_terminal():
    """The animated path writes past rich, so nothing else filters it.

    Replacing only C0 and DEL left the one-byte CSI ``\\x9b`` (a C1
    control, the same as ``ESC [`` to a terminal honouring C1), the bidi
    override U+202E and zero-width characters to be written as they were.
    Every one is now an escape, by the same rule every surface uses.
    """
    clock = Clock()
    screen, buffer = terminal_screen()
    line = ActivityLine(screen, animated=True, clock=clock)

    line.begin("bash\u200b", "\x9b2J\x85\u202etxt.exe\u2066\ufeff")
    line.tick()

    painted = buffer.getvalue()
    assert not {"\x9b", "\x85", "\u202e", "\u2066", "\ufeff", "\u200b"} & set(painted)
    assert "bash\\u200b(\\u009b2J\\u0085\\u202etxt.exe\\u2066\\ufeff)" in painted
    assert _activity.sanitize("\x9b\u202e") == "\\u009b\\u202e"


def test_a_closed_line_stays_closed():
    """The pump's ``finally`` runs before the next prompt is printed."""
    clock = Clock()
    screen, buffer = terminal_screen()
    line = ActivityLine(screen, animated=True, clock=clock)
    line.begin("slowly")
    line.close()

    before = buffer.getvalue()
    clock.advance(5.0)
    line.tick()

    assert buffer.getvalue() == before


# ---- half two: the loop --------------------------------------------------


def test_a_terminal_is_told_which_tool_it_is_waiting_for(tmp_path, monkeypatch):
    """The whole point, over a real exchange and a tool that really waits.

    ``Slow`` sleeps long enough for the ticker Task to run many times
    while the event pump is suspended inside ``__anext__`` — which is the
    arrangement the ticker exists for and the one a timeout on the
    iteration could not have produced.
    """
    monkeypatch.setattr(_activity, "TICK_S", 0.01)

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                calling("slowly"),
                Message(role=Role.ASSISTANT, content="all done"),
            ),
            tools=(Slow(delay_s=0.25),),
        )
        screen, buffer = terminal_screen()
        repl = Repl(app, source=ScriptedSource(()), screen=screen, animated=True)
        await asyncio.wait_for(repl.ask("take your time"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())
    painted = frames(printed)

    assert painted, "nothing was ever painted"
    named = [frame for frame in painted if "slowly" in frame]
    assert named, f"the live line never named the running tool: {painted}"
    assert any("ctrl-c to interrupt" in frame for frame in named)
    assert any(verb in frame for frame in named for verb in _activity.VERBS)
    assert "all done" in printed
    # Nothing is ever written on top of a painted frame: whatever comes
    # after one begins with the erase that takes the row back.
    for after in printed.split(_FRAME_END)[1:]:
        assert after == "" or after.startswith("\r"), (
            f"output landed on a painted line: {after[:60]!r}"
        )


def test_the_line_stops_naming_a_tool_that_has_finished(tmp_path, monkeypatch):
    """The wait after a tool result belongs to the model, not to the tool.

    ``Dozing`` makes the second model call take measurable time, so the
    last frames painted in this exchange are from that wait. A line still
    reading ``slowly`` there is not merely stale — it is naming something
    that is no longer running, which is worse than painting nothing.
    """
    monkeypatch.setattr(_activity, "TICK_S", 0.01)

    async def drive():
        app = build(
            tmp_path,
            Dozing(
                calling("slowly"),
                Message(role=Role.ASSISTANT, content="all done"),
                pause_s=0.25,
            ),
            tools=(Slow(delay_s=0.1),),
        )
        screen, buffer = terminal_screen()
        repl = Repl(app, source=ScriptedSource(()), screen=screen, animated=True)
        await asyncio.wait_for(repl.ask("take your time"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    painted = frames(asyncio.run(drive()))

    assert any("slowly" in frame for frame in painted), "the tool was never shown"
    assert "slowly" not in painted[-1], f"stale tool name left up: {painted[-1]!r}"


def test_a_piped_exchange_carries_no_animation(tmp_path, monkeypatch):
    """``oc cli --prompt ... | cat`` gets its answer and no control bytes.

    The same exchange as the test above, differing only in whether the
    console claims to be a terminal — so a mode decision that ignored
    that claim would turn this red while leaving the other green.
    """
    monkeypatch.setattr(_activity, "TICK_S", 0.01)

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                calling("slowly"),
                Message(role=Role.ASSISTANT, content="all done"),
            ),
            tools=(Slow(delay_s=0.25),),
        )
        buffer = io.StringIO()
        repl = Repl(app, source=ScriptedSource(()), screen=Screen.into(buffer))
        await asyncio.wait_for(repl.ask("take your time"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "\x1b" not in printed, repr(printed)
    assert "\r" not in printed, repr(printed)
    assert "all done" in printed
    assert "still" not in printed, "a short exchange earned no heartbeat"


def test_nothing_is_painted_into_a_streaming_answer(tmp_path, monkeypatch):
    """The conflict with the streaming Markdown formatter, as bytes.

    The formatter prints with ``end=""``, so between the two halves of
    this answer the cursor is mid-sentence. A tick landing there without
    the hold splices ``\\r`` and an erase into the middle of the word the
    user is reading — and this test can see it, because the two halves
    would no longer be adjacent.
    """
    monkeypatch.setattr(_activity, "TICK_S", 0.01)

    async def drive():
        app = build(
            tmp_path, SlowStream("Moran's I measures ", "spatial autocorrelation")
        )
        screen, buffer = terminal_screen()
        repl = Repl(app, source=ScriptedSource(()), screen=screen, animated=True)
        await asyncio.wait_for(repl.ask("what is Moran's I?"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "Moran's I measures spatial autocorrelation" in printed, repr(printed)


def test_nothing_is_painted_while_an_approval_is_outstanding(tmp_path, monkeypatch):
    """The conflict with ``prompt_toolkit``, measured over the right window.

    ``Dawdling`` records the screen between putting the question and
    answering it. On a real terminal that window belongs to the prompt's
    own ``Application``, which redraws on its own schedule and does not
    expect a second writer to move the cursor to column 0.

    The second assertion is the one that keeps the first honest: the
    tool goes on working after consent, so the line has to come back. A
    hold that is taken and never given back would satisfy "silent under
    the prompt" by being silent for the rest of the exchange.
    """
    monkeypatch.setattr(_activity, "TICK_S", 0.01)

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                calling("ask"),
                Message(role=Role.ASSISTANT, content="settled"),
            ),
            tools=(SlowAsking("ask", delay_s=0.25),),
        )
        screen, buffer = terminal_screen()
        source = Dawdling(buffer, [], pause_s=0.25)
        repl = Repl(app, source=source, screen=screen, animated=True)
        await asyncio.wait_for(repl.ask("please ask"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source, buffer.getvalue()

    source, printed = asyncio.run(drive())

    assert source.during, "the approval prompt was never put"
    for window in source.during:
        assert "\x1b" not in window, f"painted under the prompt: {window!r}"
    assert frames(printed[source.answered_at :]), (
        "the line never came back after the question was answered"
    )
    assert "settled" in printed


def test_the_live_line_is_gone_before_the_next_prompt(tmp_path, monkeypatch):
    """A cancelled exchange must not leave half a spinner above the prompt.

    ``Ctrl-C`` is the ordinary way a long exchange ends, and it ends it
    from outside the pump — so the erase has to be in a ``finally``
    rather than on the path that reaches ``EXCHANGE_END``.
    """
    monkeypatch.setattr(_activity, "TICK_S", 0.01)

    async def drive():
        tool = Slow(delay_s=30.0)
        app = build(tmp_path, Scripted(calling("slowly")), tools=(tool,))
        screen, buffer = terminal_screen()
        repl = Repl(app, source=ScriptedSource(()), screen=screen, animated=True)
        asking = asyncio.create_task(repl.ask("take forever"))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if _ERASE in buffer.getvalue():
                break
        assert repl.interrupt(), "nothing was running to cancel"
        await asyncio.wait_for(asking, WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert _ERASE in printed, "the live line never ran"
    assert "Cancelled." in printed
    tail = printed[printed.rindex("Cancelled.") :]
    assert "\x1b" not in tail, f"residue after the last line: {tail!r}"


def test_what_a_tool_says_survives_its_own_tool_start(tmp_path, monkeypatch):
    """The ordering bug a real run found, as a test.

    ``bash`` names its command and its directory through
    ``report_progress`` before it awaits anything, so that frame reaches
    the stream ahead of the ``TOOL_START`` for the same call. A
    ``TOOL_START`` handler that started a clean activity therefore
    deleted the one useful thing on the line and left ``bash`` alone —
    which is what the first pty run of this feature actually showed.
    """
    monkeypatch.setattr(_activity, "TICK_S", 0.01)

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                calling("slowly"),
                Message(role=Role.ASSISTANT, content="all done"),
            ),
            tools=(Announcing(delay_s=0.25),),
        )
        screen, buffer = terminal_screen()
        repl = Repl(app, source=ScriptedSource(()), screen=screen, animated=True)
        await asyncio.wait_for(repl.ask("take your time"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    painted = frames(asyncio.run(drive()))

    assert painted, "nothing was ever painted"
    assert any("slowly(running in /tmp/ocdemo: sleep 20)" in f for f in painted), (
        f"the tool's own description was dropped: {painted}"
    )


def test_an_aborted_pump_still_erases_the_line(tmp_path, monkeypatch):
    """The erase has to be in ``finally``, not on the path to the end.

    Cancelling the Task running the exchange — which is what a
    ``Ctrl-C`` at the shell, a closed Desktop connection or a supervisor
    shutdown all become — lands inside ``__anext__`` with the line
    painted and **no terminal frame ever delivered to this consumer**. An
    erase that only happened while handling ``EXCHANGE_END`` would leave
    a frozen spinner as the last thing on the terminal.
    """
    monkeypatch.setattr(_activity, "TICK_S", 0.01)

    async def drive():
        app = build(
            tmp_path, Scripted(calling("slowly")), tools=(Slow(delay_s=30.0),)
        )
        screen, buffer = terminal_screen()
        repl = Repl(app, source=ScriptedSource(()), screen=screen, animated=True)
        asking = asyncio.create_task(repl.ask("take forever"))
        for _ in range(400):
            await asyncio.sleep(0.01)
            if frames(buffer.getvalue()):
                break
        asking.cancel()
        await asyncio.wait_for(
            asyncio.gather(asking, return_exceptions=True), WAIT_S
        )
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert frames(printed), "the live line never painted"
    assert printed.endswith(_ERASE), f"a frame was left up: {printed[-80:]!r}"


# ---- the plan, pushed rather than pulled ---------------------------------


def test_a_plan_write_puts_the_new_plan_in_the_transcript(tmp_path):
    """A plan nobody is shown is a plan nobody is following.

    ``/tasks`` alone required a person to suspect the plan had changed
    before they could see that it had. This is the push half, on the
    reference harness's trigger: a ``plan_write`` that was not an error.
    """

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                planning_call(
                    ("load the Visium slide", "in_progress"),
                    ("call spatial domains", "pending"),
                ),
                Message(role=Role.ASSISTANT, content="starting now"),
            ),
        )
        buffer = io.StringIO()
        repl = Repl(app, source=ScriptedSource(()), screen=Screen.into(buffer))
        await asyncio.wait_for(repl.ask("analyse this slide"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "load the Visium slide" in printed, repr(printed)
    assert "call spatial domains" in printed
    assert "0/2 done" in printed
    assert "1 active" in printed
    assert "starting now" in printed


def test_a_plan_that_did_not_move_is_not_printed_again(tmp_path):
    """Read mode is a real mode of ``plan_write`` and prints nothing.

    The reference appends unconditionally (``tui_update.go:1641-1648``),
    so a model re-reading its plan leaves a duplicate block behind. Here
    the snapshot is compared with the last one shown.
    """

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                planning_call(("load the Visium slide", "pending")),
                Message(
                    role=Role.ASSISTANT,
                    tool_calls=(
                        ToolCall(id="c1", name="plan_write", arguments="{}"),
                    ),
                ),
                Message(role=Role.ASSISTANT, content="done"),
            ),
        )
        buffer = io.StringIO()
        repl = Repl(app, source=ScriptedSource(()), screen=Screen.into(buffer))
        await asyncio.wait_for(repl.ask("analyse this slide"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert printed.count("load the Visium slide") == 1, repr(printed)
    assert printed.count("0/1 done") == 1


def test_a_plan_that_moved_is_printed_again(tmp_path):
    """The other half of the same rule, or the first one proves nothing.

    A deduplication that simply printed once per exchange would pass the
    test above and hide exactly the update a person is waiting for.
    """

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                planning_call(("load the Visium slide", "in_progress")),
                planning_call(("load the Visium slide", "completed")),
                Message(role=Role.ASSISTANT, content="loaded"),
            ),
        )
        buffer = io.StringIO()
        repl = Repl(app, source=ScriptedSource(()), screen=Screen.into(buffer))
        await asyncio.wait_for(repl.ask("analyse this slide"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert printed.count("load the Visium slide") == 2, repr(printed)
    assert "0/1 done" in printed
    assert "1/1 done" in printed


def test_a_tool_that_is_not_plan_write_prints_no_plan(tmp_path):
    """The trigger is the tool's name, not "a tool finished".

    A resumed conversation is what makes the difference visible: its plan
    is already in the book before this REPL has shown anything, so a
    build that reacted to every successful tool result would answer a
    ``read_file`` by printing a plan the exchange never touched. The
    deduplication cannot stand in for the name check here — there is no
    earlier snapshot for it to compare against.
    """

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                Message(
                    role=Role.ASSISTANT,
                    tool_calls=(
                        ToolCall(
                            id="c0",
                            name="read_file",
                            arguments=json.dumps({"path": "OMICSCLAW.md"}),
                        ),
                    ),
                ),
                Message(role=Role.ASSISTANT, content="read it"),
            ),
        )
        assert app.plans is not None
        app.plans.for_session("resumed").restore(
            (PlanItem(id="s1", content="load the Visium slide"),)
        )
        buffer = io.StringIO()
        repl = Repl(
            app,
            source=ScriptedSource(()),
            screen=Screen.into(buffer),
            session_id="resumed",
        )
        await asyncio.wait_for(repl.ask("what does OMICSCLAW.md say?"), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "<- read_file ok" in printed, repr(printed)
    assert "load the Visium slide" not in printed, repr(printed)


def test_a_new_conversation_forgets_what_it_had_shown(tmp_path):
    """``/new`` moves to a session whose plan has never been printed here.

    Without the reset the snapshot from the previous conversation would
    suppress the first plan of the next one — the two are different
    plans that happen to read the same.
    """

    async def drive():
        app = build(
            tmp_path,
            Scripted(
                planning_call(("load the Visium slide", "pending")),
                Message(role=Role.ASSISTANT, content="first"),
                planning_call(("load the Visium slide", "pending")),
                Message(role=Role.ASSISTANT, content="second"),
            ),
        )
        buffer = io.StringIO()
        source = ScriptedSource(["one", "/new", "two", "/exit"])
        repl = Repl(app, source=source, screen=Screen.into(buffer))
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert printed.count("load the Visium slide") == 2, repr(printed)


def test_a_resumed_conversation_forgets_what_it_had_shown(tmp_path):
    """``/resume`` resets the snapshot the same way ``/new`` does."""

    async def drive():
        earlier = build(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="x")))
        repl = Repl(
            earlier,
            source=ScriptedSource(["hello", "/exit"]),
            screen=Screen.into(io.StringIO()),
            session_id="s-other",
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(earlier.aclose(), WAIT_S)

        app = build(
            tmp_path,
            Scripted(
                planning_call(("load the Visium slide", "pending")),
                Message(role=Role.ASSISTANT, content="first"),
                planning_call(("load the Visium slide", "pending")),
                Message(role=Role.ASSISTANT, content="second"),
            ),
        )
        buffer = io.StringIO()
        source = ScriptedSource(["one", "/resume s-other", "two", "/exit"])
        repl = Repl(app, source=source, screen=Screen.into(buffer))
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "Resumed s-other" in printed
    assert printed.count("load the Visium slide") == 2, repr(printed)
