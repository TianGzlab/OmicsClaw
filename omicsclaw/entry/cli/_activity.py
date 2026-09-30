"""What the agent is doing *right now*, on one line that costs no scrollback.

A REPL that only prints when something has finished is silent for exactly
the stretches a person most wants company: a model call that takes forty
seconds, a ``bash`` that takes four minutes. The frames are all there —
``TOOL_START``, ``PROGRESS``, ``TOOL_RESULT`` — but they arrive at the two
ends of the silence and say nothing during it. This module is the thing
that speaks during it.

**It is not a TUI** (plan 0041 ruling 1). Nothing here takes the screen,
draws a panel or owns a layout. The whole surface is *one line at the
bottom of the ordinary output*, written with ``\\r`` and an erase, so the
scrollback after an exchange is byte-for-byte what it was before this
module existed. That is the property :meth:`ActivityLine.close` exists to
guarantee and that ``tests/entry/test_cli_activity.py`` pins.

**The reference harness has no answer to copy here, and that is the
finding rather than an omission.** Its whole progress display lives in
the Bubbletea model — ``renderToolProgress`` (``tui_view.go:167-185``)
composed into ``View()`` at ``:529-537``, redrawn by a ``spinner.TickMsg``
loop that only runs while a *tool* is executing (``tui_update.go:405-416``
returns ``m, nil`` and lets the tick chain die otherwise). Its
line-oriented ``runCLI`` (``cli.go:36-79``) prints a banner, a prompt and
an error line and **nothing else for the whole run**: it calls the
blocking ``eng.Run``, so it has no streamed text either, and its only
trace of work in flight is the engine's ``log.Print`` on stderr at the
two *edges* of each tool call (``agent_loop.go:113-146``). Under ruling 1
the shape had to be designed rather than ported, and two deliberate
departures follow from that:

- the line runs **while a model call is outstanding too**, not only
  during tools. The reference can afford to skip that because its TUI is
  streaming tokens throughout; here the same gap is real — a model that
  answers with tool calls and no prose emits no ``TEXT_DELTA`` at all,
  and the wait before the first token of a long answer is exactly the
  silence this exists for;
- a pipe gets something. The reference's non-TTY mode is its *least*
  observable one; making the degraded case silent would have copied the
  wrong half.

Three things it has to share the terminal with, and the rule for each
(this is the hard part, not the animation):

*The streaming Markdown formatter.*
:class:`~omicsclaw.entry.cli._markdown.MarkdownStreamFormatter` prints
with ``end=""``, so while an answer is being written the cursor is
**mid-line** and column 0 does not belong to us. A ``\\r`` there would
overwrite the sentence the user is reading. The rule is therefore not
"erase more carefully" but *do not paint at all*: the REPL calls
:meth:`ActivityLine.hold` the moment text starts streaming and
:meth:`ActivityLine.release` when it stops. Nothing is lost by that —
while tokens are arriving the user already has the best possible progress
indicator, which is the answer itself.

*``prompt_toolkit`` during an approval.* A
:class:`~omicsclaw.entry.cli._input.PromptToolkitSource` builds a full
``Application`` around the prompt and redraws it on its own schedule; a
second writer emitting ``\\r`` under it produces a prompt with half a
spinner in it and, worse, a prompt whose cursor column
``prompt_toolkit`` no longer knows. So an outstanding approval holds the
line too — :meth:`hold` is counted, not boolean, because two tools in one
model message can both be waiting on a person.

*Everything the pump prints itself* (the dim ``-> bash`` lines, approval
cards, the plan snapshot). Those start at column 0, so the pump calls
:meth:`clear` before each one and the next tick repaints below it.

**A pipe gets no animation and no garbage.** ``\\r``-driven redrawing is
only meaningful to a terminal; written to a file it produces a line
containing every frame it ever drew. So the mode is chosen from
``Console.is_terminal`` — the same predicate rich itself uses to decide
whether to emit ANSI — and a non-terminal degrades to *appended plain
lines* rather than to silence or to escape codes. It degrades further
than that on purpose: a heartbeat line is only appended after
:data:`HEARTBEAT_S` of one uninterrupted activity, so a short
``oc cli --prompt ... > answer.txt`` emits **no** heartbeat at all and its
output is unchanged. Visibility is bought only where there would
otherwise have been a silence worth breaking.

**Token counts are deliberately absent.** Plan 0041 ruling 1 closed the
persistent token display ("``/usage`` 的按需打印就是 OmicsClaw 在这条上的
最终答案"), and a live line that grew a token counter would reopen it
through the back door. What this line carries is *what* and *how long* —
neither of which that ruling is about.
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from rich.text import Text

from omicsclaw.entry.display import inert_line

from ._screen import Screen

__all__ = [
    "HEARTBEAT_S",
    "QUIET_TICK_S",
    "TICK_S",
    "VERBS",
    "ActivityLine",
    "drive_ticks",
    "sanitize",
]

TICK_S = 0.12
"""Seconds between repaints on a terminal.

Fast enough that the spinner reads as motion rather than as a stutter,
slow enough that a minute of waiting costs 500 writes rather than 60,000.
"""

QUIET_TICK_S = 1.0
"""Seconds between clock checks when there is nothing to animate.

A non-terminal never repaints, so this only decides how precisely a
heartbeat lands on :data:`HEARTBEAT_S`. One second is well under the
resolution anybody reads a log at.
"""

HEARTBEAT_S = 30.0
"""How long one activity must run before a non-terminal says so.

The number that keeps a piped run's output unchanged for the ordinary
case. Every short exchange finishes inside it and appends nothing; only
a wait long enough that a reader would wonder whether the process died
earns a line.
"""

VERBS = ("thinking", "analysing", "working", "reasoning", "weighing")
"""The rotating word, in the reference harness's position and for its
reason.

``spinnerVerbs`` (``cmd/harness9/tui.go:142-144``) is six Chinese verbs
rotated every 30 spinner ticks ≈ 3 s (``tui_update.go:405-416``). A
changing word distinguishes "still working" from "frozen at the same
pixel" in a way a spinning glyph does not — the glyph could be a stuck
animation, and a screenshot of one says nothing at all.

It rotates **whether or not a tool is running**, which is also what the
reference does: its line is ``⠼ 思考中...  bash(...)  [1.2s]`` — verb and
tool together, one proving liveness and the other saying what.
"""

_VERB_S = 3.0
"""Seconds one verb stays up. The reference harness's 30 ticks at
10 FPS, kept because the judgement is the same: long enough to read,
short enough to change inside the attention span it holds."""

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
"""Braille spinner frames, one code point each so the line's width is
its character count."""

_ERASE = "\r\x1b[2K"
"""Return to column 0 and clear the line. Emitted before every repaint
and once more by :meth:`ActivityLine.close`, which is what makes the
scrollback identical to a run without this module."""

_DIM = "\x1b[2m"
_RESET = "\x1b[0m"

_HINT = "  ·  ctrl-c to interrupt"
"""True on this surface: ``Ctrl-C`` cancels the exchange and returns to
the prompt (:meth:`~omicsclaw.entry.cli._repl.Repl.interrupt`)."""


def sanitize(value: str) -> str:
    """*value* as one line that cannot act on the terminal.

    :func:`~omicsclaw.entry.display.inert_line`: a line break is drawn as
    a mark and every control or format character is escaped. Applied to
    what the animated path writes past rich, and to the plain path too so
    both show the same string.
    """
    return inert_line(value)


class ActivityLine:
    """One redrawable line saying what is happening and for how long.

    :param screen: where the line is written; its console decides the
        mode and supplies the width.
    :param animated: overrides the ``Console.is_terminal`` test. Only a
        test should pass it — a deployment that guesses wrong writes
        escape codes into a pipe.
    :param clock: monotonic seconds, injectable so a test can age an
        activity without sleeping.
    """

    __slots__ = (
        "_animated",
        "_clock",
        "_console",
        "_detail",
        "_heartbeat_s",
        "_closed",
        "_held",
        "_last_note",
        "_painted",
        "_screen",
        "_since",
        "_tool",
    )

    def __init__(
        self,
        screen: Screen,
        *,
        animated: bool | None = None,
        clock: Callable[[], float] = time.monotonic,
        heartbeat_s: float = HEARTBEAT_S,
    ) -> None:
        self._screen = screen
        self._console = screen.console
        if animated is None:
            # ``getattr`` rather than an attribute: a console that cannot
            # say whether it is a terminal is not one, and guessing "yes"
            # is the guess that writes escape codes into a file.
            #
            # ``is_dumb_terminal`` is a separate question from
            # ``is_terminal`` and rich answers both: ``TERM=dumb`` is a
            # tty that cannot be asked to erase a line, so it gets the
            # appended form rather than a row of ``[2K``.
            animated = (
                bool(getattr(self._console, "is_terminal", False))
                and not getattr(self._console, "is_dumb_terminal", False)
                and not getattr(self._console, "legacy_windows", False)
            )
        self._animated = animated
        self._clock = clock
        self._heartbeat_s = heartbeat_s
        self._tool = ""
        self._detail = ""
        self._held = 0
        self._painted = False
        self._closed = False
        self._since = clock()
        self._last_note = self._since

    @property
    def animated(self) -> bool:
        """Whether this line redraws in place rather than appending."""
        return self._animated

    @property
    def interval_s(self) -> float:
        """Seconds a driver should wait between :meth:`tick` calls."""
        return TICK_S if self._animated else QUIET_TICK_S

    # ---- what is happening ----------------------------------------------

    def begin(self, tool: str = "", detail: str = "") -> None:
        """Start a new activity and restart its clock.

        An empty *tool* means "waiting for the model", which is the state
        between every tool result and the next tool call.
        """
        self.clear()
        self._tool = sanitize(tool)
        self._detail = sanitize(detail)
        self._since = self._clock()
        self._last_note = self._since

    def started(self, tool: str) -> None:
        """A tool call began: restart the clock, keep what it already said.

        ``TOOL_START`` is not reliably the first frame of a tool call. The
        engine yields it through the loop's generator while
        :func:`~omicsclaw.tools.report_progress` publishes straight onto
        the stream, so a tool that reports before its first ``await``
        — ``bash`` does, naming the command and the directory — overtakes
        the frame announcing it. A plain :meth:`begin` here therefore
        threw away the only description of the work and left the line
        reading ``bash`` with nothing after it. Observed on a real run,
        not reasoned about.
        """
        keep = self._detail if self._tool == sanitize(tool) else ""
        self.begin(tool, keep)

    def detail(self, detail: str, *, tool: str = "") -> None:
        """Replace the current activity's detail without restarting it.

        A tool that reports progress twice is one activity with two
        things to say, not two activities: restarting the clock here
        would reset the elapsed figure that answers "is it stuck?".
        """
        self._detail = sanitize(detail)
        if tool:
            self._tool = sanitize(tool)

    # ---- who owns the cursor --------------------------------------------

    def hold(self) -> None:
        """Stop painting: something else owns the line. Counted."""
        self._held += 1
        self.clear()

    def release(self) -> None:
        """Undo one :meth:`hold`. Painting resumes at the last one."""
        if self._held:
            self._held -= 1

    @property
    def held(self) -> bool:
        """Whether anything is currently holding the line."""
        return self._held > 0

    # ---- drawing ---------------------------------------------------------

    def tick(self) -> None:
        """Repaint, or append a heartbeat, or do nothing. One decision."""
        if self._closed or self._held:
            return
        now = self._clock()
        if self._animated:
            self._paint(now)
            return
        if now - self._last_note < self._heartbeat_s:
            return
        self._last_note = now
        self._screen.print(Text(self._plain_line(now), style="dim"))

    def clear(self) -> None:
        """Erase the painted line, if there is one. Idempotent."""
        if not self._painted:
            return
        self._painted = False
        self._write(_ERASE)

    def close(self) -> None:
        """Erase for the last time and refuse to paint again.

        Called from the pump's ``finally``, so an exchange that was
        cancelled or that raised leaves no half-drawn line above the next
        prompt.
        """
        self.clear()
        self._closed = True

    # ---- internals -------------------------------------------------------

    def _paint(self, now: float) -> None:
        line = self._animated_line(now)
        self._write(f"{_ERASE}{_DIM}{line}{_RESET}")
        self._painted = True

    def _write(self, payload: str) -> None:
        """Write straight to the console's file, bypassing rich.

        Rich wraps, justifies and style-parses what it is given, and all
        three are wrong for a control sequence: ``\\r`` is not a word
        boundary and ``\\x1b[2K`` is not markup. The console is still the
        object asked for the file and the width, so a test pointing a
        :class:`~omicsclaw.entry.cli._screen.Screen` at a buffer sees
        these bytes with everything else in order.
        """
        file = self._console.file
        file.write(payload)
        file.flush()

    def _width(self) -> int:
        try:
            return max(20, int(self._console.size.width))
        except Exception:  # pragma: no cover - a console with no size
            return 80

    def _verb(self, now: float) -> str:
        return VERBS[int((now - self._since) / _VERB_S) % len(VERBS)]

    def _frame(self, now: float) -> str:
        return _FRAMES[int(now / TICK_S) % len(_FRAMES)]

    def _animated_line(self, now: float) -> str:
        """The terminal form: spinner, verb, tool, elapsed, hint.

        The tool's detail is the only part that is cut, and it is cut
        rather than wrapped: a line longer than the terminal wraps onto a
        second row that the next ``\\r`` cannot reach, which is how an
        in-place indicator turns into a column of litter.
        """
        head = f"{self._frame(now)} {self._verb(now)}…"
        tail = f"  {int(now - self._since)}s{_HINT}"
        if self._tool:
            budget = self._width() - 1 - len(head) - len(tail) - len(self._tool) - 4
            if self._detail and budget > 8:
                head += f"  {self._tool}({self._detail[:budget]})"
            else:
                head += f"  {self._tool}"
        return (head + tail)[: self._width() - 1]

    def _plain_line(self, now: float) -> str:
        """The pipe form: one appended sentence, no control characters."""
        what = self._tool or "waiting for the model"
        line = f"... still {what} — {int(now - self._since)}s"
        if self._detail:
            line += f": {self._detail}"
        return line


async def drive_ticks(line: ActivityLine) -> None:
    """Call :meth:`ActivityLine.tick` forever, on the line's own cadence.

    Runs as its own Task beside the event pump, because the pump spends a
    long exchange suspended inside ``__anext__`` and a coroutine that is
    waiting for a frame cannot also be counting the seconds it waited.
    The caller cancels it; there is no exit condition here.
    """
    while True:
        await asyncio.sleep(line.interval_s)
        line.tick()
