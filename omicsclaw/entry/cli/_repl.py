"""The loop: read a line, run an exchange, print what it says.

Plan 0031 task D3. The reference harness's whole CLI is
``runCLI(ctx, eng, io.Reader, idx)`` with three exits — context done, EOF,
``exit``/``quit`` (``cli.go:36-79``) — and this is the same loop against
:class:`~omicsclaw.entry.session.SessionRegistry` instead of an engine,
which buys three things a direct ``engine.run`` could not have: the
exchange has an identity that survives the iterator, a second ``Ctrl-C``
has something to cancel, and an approval can be answered while the stream
is still being consumed.

**The input is an argument** (:class:`~omicsclaw.entry.cli._input.
PromptSource`). Nothing here reads :data:`sys.stdin`, so the loop under
test is the loop that ships — the one thing ``cli.go`` does that is worth
copying exactly.

**``Ctrl-C`` cancels the exchange, not the process.**
:meth:`Repl.interrupt` cancels the running handle; the registry publishes
``EXCHANGE_END(terminal="cancelled")``, this loop prints it and asks for
the next line. Two consequences are load-bearing and are tested:

- the conversation is **byte-identical** afterwards (plan 0031 trap 3).
  The engine's trajectory exists only on its ``DONE`` event, so a
  cancelled exchange has nothing partial to keep that would not be a
  guess, and this file does not invent one — it does not touch
  ``session.history`` at all;
- the loop continues. A REPL that died on the interrupt would make
  cancelling a runaway tool call cost the conversation.

**Approvals are answered from a separate Task** (trap 1). The harness
writes it as a consumer contract — "the UI must keep consuming events
while it shows the dialog" (``stream.go:51-58``) — and in Python it is
harder than that: awaiting a human inside the ``async for`` body stops the
iteration that would deliver the *second* tool's approval request, and two
concurrent tools then deadlock. So :meth:`Repl._ask` runs beside the pump
and the pump never waits for a person.

Two requests in flight are therefore two Tasks, but they share one
terminal, and queueing them on it belongs to the source
(:class:`~omicsclaw.entry.cli._input.PromptToolkitSource`) rather than
here — the pump must keep running either way. What this file owes in
return is that **a question that cannot be put is still answered**:
:meth:`Repl._ask` denies on any failure, because this surface sets no
approval deadline and an unsettled request is an exchange that never
ends.

**What this loop does not do.** Part of the ported catalogue (see
:data:`~omicsclaw.entry.cli._slash_command_support.REPL_SLASH_COMMAND_SPECS`),
because the skill runner, the research pipeline and the memory commands
are each a step of their own. A user who types one of those is told it
is not in this build rather than being left to wonder.

**Planning is visible here and not drivable.** ``/plan`` and ``/tasks``
read :attr:`~omicsclaw.entry.assembly.AgentApp.plans` and print it;
there is no ``/approve-plan`` and no "do the next task" because
:mod:`omicsclaw.planning`'s model is that the agent decides when a job
is worth planning, and a control panel bolted to the side of that would
be a second, contradictory answer to the same question. The three
commands are refused like any other unimplemented name, and the line
printed here is the whole of what this surface has to say about them.

**Visible is not the same as pull-only, though.** ``/plan`` alone made
the plan a thing a person had to *suspect had changed* before they could
see that it had, which is the one job a plan cannot do. So a successful
``plan_write`` also pushes the new snapshot into the transcript
(:meth:`Repl._show_plan`) — the reference harness appends its block on
the same trigger, ``toolName == "plan_write" && !result.IsError``
(``tui_update.go:641-646`` into ``updatePlanBlock``, ``:1637-1649``).

One departure: that append is unconditional, so a ``plan_write`` called
in *read* mode — which the tool supports and a model uses to re-read
what it was refused — leaves a second identical copy in the transcript.
Here the snapshot is compared with the last one printed and a plan that
did not move prints nothing. It stays read-only either way: this shows
what the tool already accepted and has no way to write one.

**And the silences are narrated.** Between ``TOOL_START`` and
``TOOL_RESULT`` — or between a question and the first token of its
answer — no frame arrives for as long as the work takes, and this loop
used to spend that time printing nothing at all. :class:`~omicsclaw.
entry.cli._activity.ActivityLine` runs beside the pump and says what is
outstanding and for how long. Who may own the cursor while it does, and
why a pipe gets appended lines instead of an animation, is that module's
docstring; what this file owes it is the state changes (a tool started,
a tool reported, a tool finished) and a :meth:`ActivityLine.hold` around
every stretch where something else is writing.

**A line starting with ``!`` never reaches the model.**
:meth:`Repl._dispatch` takes it before the command catalogue is
consulted and :mod:`~omicsclaw.entry.cli._shell` runs it; what it
printed is prefixed to the *next* question and then dropped. ``Ctrl-C``
while it runs kills it and gives the prompt back. That module
is where the reasoning about timeouts, ceilings and the absent approval
gate lives.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Sequence

from rich.cells import cell_len, set_cell_size
from rich.text import Text

from omicsclaw.context import CompactionRecord, is_summary_message
from omicsclaw.entry.assembly import AgentApp
from omicsclaw.entry.display import approval_body_note, inert_line, inert_prose
from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.render import TextRenderer
from omicsclaw.entry.session import Session, SubmissionRefused, new_turn_id
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.planning import PLAN_WRITE_TOOL_NAME, PlanItem, PlanStatus
from omicsclaw.schema import Message, Role
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest

from omicsclaw.permission import PermissionMode

from ._activity import HEARTBEAT_S, ActivityLine, drive_ticks
from ._auto import (
    AUTO_USAGE,
    CLI_PERMISSION_MODE_VARIABLE,
    auto_action,
    is_auto_answer,
    persist_cli_mode,
    saved_cli_mode,
)
from ._constants import WELCOME_SLOGANS
from ._input import ChoiceSource, PromptSource
from ._markdown import MarkdownStreamFormatter
from ._reasoning import ReasoningStreamWriter
from ._screen import Screen
from ._session_state import SessionState
from ._shell import (
    SHELL_RECORD_HEADER,
    SHELL_TIMEOUT_S,
    ShellResult,
    for_display,
    for_model,
    run_shell,
    shell_preamble,
    wants_a_terminal,
)
from ._transcript import ToolTranscript
from ._slash_command_support import (
    CLI_SLASH_COMMAND_SPECS,
    REPL_SLASH_COMMAND_SPECS,
    parse_slash_command,
    slash_command_help_rows,
    slash_token,
)

__all__ = ["PROMPT", "SESSION_LIST_LIMIT", "Repl", "run_once"]

_log = logging.getLogger(__name__)

PROMPT = "❯ "
"""What the user sees when it is their turn.

One string, used by the loop and asserted by the test that a cancelled
exchange comes back to the prompt rather than to a dead terminal. The
original was a ``prompt_toolkit`` ``HTML`` fragment
(``interactive.py:2110``); plain text because a
:class:`~omicsclaw.entry.cli._input.StreamSource` cannot render markup and
the two sources must ask the same question.
"""

_APPROVAL_PROMPT = "approve {name} [{card}]{size}? [y/N/a=always] "
"""Named **and numbered** so a person answering two requests knows which.

Two tools in one model message is the ordinary case, not the exotic one —
it is what makes trap 1 reachable at all — and the two are often the same
tool twice, ``web_fetch`` over two URLs being what the model does with
"read these pages". The terminal shows those cards one after the other
(:class:`~omicsclaw.entry.cli._input.PromptToolkitSource` holds one
reader at a time), so the name alone leaves two identical questions in a
row and no way to tell which is being answered.

*card* is the request id's within-exchange suffix, the ``#1`` of the
``[<turn id>#1]`` the approval card was printed with, so the prompt and
the card that explains it carry the same label. The turn id itself is
dropped: every outstanding request belongs to the exchange that is
running, and a 32-character prefix in a prompt wraps the line on a narrow
terminal, which costs more than it tells.

*size* is ``""``, or a space and the note the card's body opens with
(:func:`~omicsclaw.entry.display.approval_body_note`) when the body has
one: its line and character counts, and what was folded or cut."""

_INTERRUPTED_REASON = "interrupted at the terminal"
"""The reason a card is settled with when Ctrl-C is pressed at it."""

_NO_OPERATOR_REASON = "no operator at the terminal"
"""The reason a card is settled with when the input ended or the Task
reading it was cancelled."""

_YES = frozenset({"y", "yes", "ok", "allow"})
"""Everything counted as consent. Anything else denies, including the
empty line, because plan 0031 Q12 rules that approval fails closed and a
person who pressed enter to get their prompt back has not agreed to
anything."""

_ALWAYS = frozenset({"a", "always"})
"""Consent, plus a request to write an ``allow`` rule for this exact call.

Exact on purpose, and not widened by plan 0049: a rule outranks the
dangerous-command patterns, so ``bash(git *)`` would let ``git status;
rm -rf /`` through without the pattern ever being read. For "stop asking
about ``bash``" the answer is ``s``, or ``--permission-mode auto-approve``.

A subset of consent rather than a fourth outcome: an answer here both
approves and persists, and an answer that persisted without approving
would be a rule nobody acted on. The rule written covers only the call
that was shown — see
:meth:`~omicsclaw.entry.assembly.AgentApp.remember_approval`."""

_FOR_THIS_SESSION = frozenset({"s", "session"})
"""Consent, plus "stop asking me about this *tool* in this conversation".

Per tool since plan 0049; it used to be per exact call, which for ``bash``
made it a ``y`` with a longer name. Questions the gate marks
``ask_every_time`` —— a dangerous-command pattern, an explicit ``ask``
rule, a change to ``.omicsclaw/``, the rule file or a ``.env``, a tool
declared ``DENY_UNLESS_TRUSTED`` —— are still asked every time, and
answering ``s`` to one of those allows that call only.

The middle of the three grants, and the one a person reaches for most:
``y`` costs a prompt per call and ``a`` writes a rule that outlives the
reason for it. This one is remembered in :attr:`Repl._granted` and
nowhere else, so it dies with the conversation and with the process, and
:meth:`~omicsclaw.permission.PermissionGate.remember` is never called —
which is the observable difference between the two, and what a person
choosing between them is choosing."""

_APPROVAL_LEGEND = (
    "  y = allow once · s = allow this tool for the rest of the conversation"
    " · a = always, and write a rule · anything else denies"
)
"""The three grants spelled out, printed above each approval card.

``[y/N/a=always]`` in the prompt itself is the short form and stays that
way — it is the string the approval tests name and it is already as wide
as a narrow terminal wants — so the middle grant would otherwise be a
key nobody could discover. The reference harness has the same problem
and solves it the same way: its dialog lists all of its options
(``tui_view.go:467-491``) rather than compressing them into the prompt.
"""

_ALWAYS_ASKED_LEGEND = (
    "  this call is always asked about: y or s = allow it once · "
    "a = always, and write a rule · anything else denies"
)
"""The legend for a card :attr:`ApprovalRequest.ask_every_time` marks.

A different legend rather than the same one with a footnote, because on
this card ``s`` does not do what the ordinary legend says it does, and a
person who reads "allow this tool for the rest of the conversation" and
then gets asked again has been told something untrue."""

_PROTECTED_LEGEND = (
    "  this call is always asked about, and no rule can change that: "
    "y = allow it once · anything else denies"
)
"""The legend for a card no grant can answer —— not ``s``, not ``a``.

A change to the rule file, ``.omicsclaw/`` or a ``.env`` is decided before
the gate reads any rule, so the ``allow`` rule ``a`` would write is never
consulted. Offering it would print "Remembered" over a grant that does
nothing, and ask the identical question again next time."""

SESSION_LIST_LIMIT = 10
"""Conversations ``/sessions`` and ``/resume`` show.

The reference harness's number (``tui_update.go:1409-1421``) and its
reason: a resume list is read by eye, and a list longer than a screen is
one a person scrolls rather than reads. ``/resume <id>`` reaches a
conversation that has fallen off the end; the list is a convenience, not
the index.
"""

_PICKER_MESSAGE = "Resume a conversation (↑/↓ move · Enter resume · Esc cancel)"

_PICKER_CHROME = 8
"""Columns the ``/resume`` picker spends on each row before the text:
its left padding, cursor symbol, row number and right padding."""

_LISTING_CHROME = 5
"""Columns ``/sessions`` spends on each row's number, ``"  3. "``."""

_NOT_STORED = (
    "This deployment stores no conversations: they are held in memory and "
    "lost when the process exits."
)

_TASK_ICONS = {
    PlanStatus.IN_PROGRESS: "▶",
    PlanStatus.COMPLETED: "✔",
    PlanStatus.CANCELLED: "⊘",
    PlanStatus.PENDING: "○",
}
"""One glyph per status, from the reference harness's task panel
(``tui_view.go:117-135``). The status word is printed beside it rather
than replaced by it: a glyph is read at a glance and a word is read by
somebody who has not learned the glyphs yet, and only one of the two
survives being copied into a bug report.
"""

_TASK_STYLES = {
    PlanStatus.IN_PROGRESS: "yellow",
    PlanStatus.COMPLETED: "green",
    PlanStatus.CANCELLED: "dim",
    PlanStatus.PENDING: "",
}


def _card(request_id: str) -> str:
    """The label the approval card was printed with, short enough to prompt on.

    :param request_id: the exchange-scoped id, ``<turn id>#<n>``.
    :returns: ``#<n>``, or the whole id when it carries no ``#`` — an id
        shaped by something other than the turn runner is still better
        shown than replaced with a number that means nothing.
    """
    _turn, hash_mark, index = request_id.rpartition("#")
    return f"#{index}" if hash_mark else request_id


def _task_lines(items: Sequence[PlanItem]) -> list[Text]:
    """One header and one line per plan item, ready to print.

    :class:`~rich.text.Text` and not markup, and each item's content made
    one inert line by :func:`~omicsclaw.entry.display.inert_line`.
    """
    done = sum(1 for item in items if item.status is PlanStatus.COMPLETED)
    active = sum(1 for item in items if item.status is PlanStatus.IN_PROGRESS)
    header = Text("Tasks", style="bold")
    header.append(f"  ·  {done}/{len(items)} done", style="dim")
    if active:
        header.append(f"  ·  {active} active", style="yellow")
    lines = [header]
    for index, item in enumerate(items, start=1):
        line = Text(f"{index:>3}. ", style="dim")
        line.append(f"{_TASK_ICONS[item.status]}  ", style=_TASK_STYLES[item.status])
        line.append(inert_line(item.content), style=_TASK_STYLES[item.status])
        line.append(f"  [{item.status.value}]", style="dim")
        lines.append(line)
    return lines


def _fit(text: str, width: int) -> str:
    """*text* cut to *width* terminal cells, with ``…`` when it was cut.

    Measured in cells, not characters, so a CJK character counts as two.
    """
    if width <= 0:
        return ""
    if cell_len(text) <= width:
        return text
    return set_cell_size(text, width - 1).rstrip() + "…"


def _said(message: Message) -> str:
    """What a person reads *message* as saying, on one inert line.

    A block of ``!`` command records in front of a question is dropped,
    keeping what follows the last blank line: the question itself. Runs of
    whitespace become one space, and the result is made inert by
    :func:`~omicsclaw.entry.display.inert_line`.
    """
    content = message.content or ""
    if content.startswith(SHELL_RECORD_HEADER):
        content = content.rpartition("\n\n")[2]
    return inert_line(" ".join(content.split()))


def _questions(history: Sequence[Message]) -> list[str]:
    """The person's messages, in order, without compaction summaries."""
    return [
        said
        for message in history
        if message.role is Role.USER and not is_summary_message(message)
        for said in (_said(message),)
        if said
    ]


def _session_summary(session: Session, *, current: bool, width: int) -> str:
    """One conversation on one line of at most *width* cells.

    Id, whether it is the current one, when it was last active, its size,
    then as much of its first question as fits. Only the question is cut.
    """
    when = datetime.fromtimestamp(session.updated_at).strftime("%Y-%m-%d %H:%M")
    marker = "  (current)" if current else ""
    head = (
        f"{inert_line(session.session_id)}{marker}  {when}  "
        f"{len(session.history)} message(s)"
    )
    questions = _questions(session.history)
    preview = questions[0] if questions else "(no messages)"
    room = width - cell_len(head) - 2
    if room < 8:
        return head
    return f"{head}  {_fit(preview, room)}"


def _recap(history: Sequence[Message], *, width: int) -> list[Text]:
    """The last question and the last answer, a line each, dim."""
    lines: list[Text] = []
    questions = _questions(history)
    if questions:
        lines.append(Text(_fit(f"  you: {questions[-1]}", width), style="dim"))
    answers = [
        said
        for message in history
        if message.role is Role.ASSISTANT
        for said in (_said(message),)
        if said
    ]
    if answers:
        lines.append(Text(_fit(f"  agent: {answers[-1]}", width), style="dim"))
    return lines


def _shell_status(result: ShellResult) -> str:
    """The line under a ``!`` command's output saying how it ended."""
    if result.interrupted:
        return f"  ✗ interrupted after {result.duration_s:.1f}s"
    if result.timed_out:
        return (
            f"  ✗ killed after {result.duration_s:.1f}s — it was still "
            "running, and this prompt will not wait longer"
        )
    if result.failed:
        return f"  ✗ non-zero exit — {result.duration_s:.2f}s"
    return f"  ✓ done — {result.duration_s:.2f}s"


def _shell_style(result: ShellResult) -> str:
    return "red" if result.failed else "green"


def _compaction_verdict(record: CompactionRecord | None) -> str:
    """What ``/compact`` achieved, in one line.

    Printed whatever happened, including when nothing did: the
    ``COMPACTION`` frame the pump renders is only published when a
    compaction changed something, so on a short conversation it is this
    line or silence, and silence reads as a command that did not run.
    """
    if record is None:
        return "Compaction did not finish."
    if not record.written_back:
        if record.degraded:
            return (
                "Compaction failed and the conversation was left as it "
                f"was: {inert_line(record.degraded)}"
            )
        return "Nothing to compact: this conversation is already short."
    return (
        f"Compacted: {record.tokens_before} -> {record.tokens_after} tokens "
        f"({1 - record.compression_ratio:.0%} smaller), "
        f"{record.msgs_before} -> {record.msgs_after} messages."
    )


class Repl:
    """One terminal, one conversation, one exchange at a time.

    Holds no history: :class:`~omicsclaw.entry.session.SessionRegistry`
    does, keyed by :attr:`session_id`. What this object owns is the
    screen, the input source, and the handle of whatever is running — the
    third being the whole of why ``Ctrl-C`` has an address to send a
    cancellation to.
    """

    __slots__ = (
        "_activity",
        "_animated",
        "_app",
        "_asking",
        "_dotenv_path",
        "_granted",
        "_heartbeat_s",
        "_permission_mode_source",
        "_plan_shown",
        "_running",
        "_screen",
        "_shell_records",
        "_shell_running",
        "_shell_timeout_s",
        "_show_reasoning",
        "_source",
        "_usage",
        "state",
    )

    def __init__(
        self,
        app: AgentApp,
        *,
        source: PromptSource,
        screen: Screen | None = None,
        session_id: str = "",
        show_reasoning: bool = False,
        shell_timeout_s: float = SHELL_TIMEOUT_S,
        animated: bool | None = None,
        heartbeat_s: float = HEARTBEAT_S,
        dotenv_path: Path | None = None,
        permission_mode_source: str = "",
    ) -> None:
        """*dotenv_path* is where ``/auto`` saves its setting —— the file the
        process shell reads, which only that shell can name —— and ``None``
        means this run has nowhere to save it. *permission_mode_source* is
        which setting decided the mode this run started in (``"flag"``,
        ``"environment"``, ``"cli-key"`` or ``""``), so that ``/auto`` can say
        when what it saves will be outranked at the next start."""
        if app.sessions is None:
            raise ValueError(
                "this app has no session registry — build it with "
                "attach_sessions(build_app(config))"
            )
        self._app = app
        self._source = source
        self._screen = screen if screen is not None else Screen()
        self._show_reasoning = show_reasoning
        self._dotenv_path = dotenv_path
        self._permission_mode_source = permission_mode_source
        self._shell_timeout_s = shell_timeout_s
        self._running: TurnHandle | None = None
        self._asking: set[asyncio.Task[None]] = set()
        self._granted: set[tuple[str, str]] = set()
        """``(session id, tool name)`` a person said "for this
        conversation" about. Keyed by the *tool*, so it grants more than
        the rule ``a`` writes, which covers one exact call —— and is safe
        to only because it never answers a question the gate marked
        :attr:`~omicsclaw.tools.ApprovalRequest.ask_every_time` (plan
        0049). Shared with the sub-agents this conversation delegates to:
        they are the same model's work, in the same trust domain."""
        self._shell_records: list[str] = []
        self._shell_running: asyncio.Task[ShellResult] | None = None
        """The ``!`` command running in the foreground, for
        :meth:`interrupt` to cancel. ``None`` when there is none."""
        self._usage = [0, 0]
        self._animated = animated
        self._heartbeat_s = heartbeat_s
        self._activity: ActivityLine | None = None
        """The live line of whatever exchange is running, so that an
        approval answered from its own Task can stop it painting over a
        prompt. ``None`` between exchanges."""
        self._plan_shown: tuple[tuple[str, str], ...] = ()
        """The last plan snapshot this conversation printed, so that a
        ``plan_write`` that read the plan back without changing it does
        not print it again. Cleared when the conversation changes."""
        self.state = SessionState(
            session_id=session_id or new_turn_id()[:8],
            workspace_dir=str(app.config.workspace),
            ui_backend="cli",
        )

    # ---- the loop --------------------------------------------------------

    async def run(self) -> None:
        """Read, run, print, repeat — until EOF or ``/exit``.

        Does **not** close the app. The process's entry point owns that,
        because a REPL is one of several things that can share one
        deployment and the one that finishes first does not get to shut
        the others down.
        """
        while self.state.running:
            try:
                line = await self._source.read(PROMPT)
            except EOFError:
                self._screen.print("[dim]Goodbye![/dim]")
                break
            text = line.strip()
            if not text:
                continue
            if not await self._dispatch(text):
                break
        self.state.stop()

    async def _dispatch(self, text: str) -> bool:
        """Handle one line. ``False`` means the loop should end.

        ``!`` is taken **before** the catalogue is consulted, because it
        is not a slash command and putting it in that table would make
        every shell command a name somebody has to have registered.

        A slash command is matched against the **whole** catalogue, not
        against the implemented subset, so that ``/research`` gets an
        answer instead of being sent to the model as a question about
        itself.

        A ``/name`` the catalogue does not claim is **reported**, not
        asked: sending it to the model spends a round trip to have a typo
        answered as prose. A line whose first token is a path is not a
        name — see
        :func:`~omicsclaw.entry.cli._slash_command_support.slash_token` —
        so a pasted ``/data/run7/matrix.h5ad`` still reaches the model.
        """
        if text.startswith("!"):
            await self._shell(text[1:].strip())
            return True
        command = parse_slash_command(text, CLI_SLASH_COMMAND_SPECS)
        if command is None:
            if self._unknown_slash(text):
                return True
            await self.ask(text)
            return True
        if command.name == "/exit":
            self._screen.print("[dim]Goodbye! See you next time.[/dim]")
            return False
        implemented = {spec.name for spec in REPL_SLASH_COMMAND_SPECS}
        if command.name not in implemented:
            self._screen.print(
                f"[yellow]{command.name} is not available in this build.[/yellow]"
            )
            self._screen.print(
                "[dim]The skill runner, the research pipeline and the memory "
                "commands each land in a step of their own; the agent drives "
                "its own plan. /help lists what runs today.[/dim]"
            )
            return True
        await self._command(command.name, command.arg)
        return True

    async def _command(self, name: str, arg: str) -> None:
        """The commands this surface answers, each from the assembled app."""
        if name == "/help":
            self._help()
            return
        if name == "/skills":
            self._skills(arg)
            return
        if name == "/mcp":
            self._mcp()
            return
        if name == "/usage":
            self._screen.print(
                f"[dim]Session total: {self._usage[0]} in / "
                f"{self._usage[1]} out[/dim]"
            )
            return
        if name == "/current":
            # ``Text``: a workspace path is not this file's to trust, and
            # ``/data/cohort[batch1]`` would lose its bracket to rich, or
            # ``[/tmp]`` raise and end the REPL.
            self._screen.print(
                Text(
                    f"Session {inert_line(self.state.session_id)} in "
                    f"{self.state.workspace_dir} · permissions: "
                    f"{self._live_mode_name()}",
                    style="dim",
                )
            )
            return
        if name == "/auto":
            self._auto(arg)
            return
        if name == "/sessions":
            await self._sessions()
            return
        if name == "/resume":
            await self._resume(arg)
            return
        if name == "/compact":
            await self._compact()
            return
        if name in ("/plan", "/tasks"):
            self._tasks()
            return
        if name in ("/new", "/clear"):
            self._new_session(fresh_id=name == "/new")
            return

    def _help(self) -> None:
        """The menu, as :class:`~rich.text.Text`.

        Not a markup string: a description carries ``[workspace]`` and
        ``[id|number]``, and rich would read either as a style tag and
        fail to find a style by that name.
        """
        for command, description in slash_command_help_rows(
            REPL_SLASH_COMMAND_SPECS
        ):
            line = Text("  ")
            line.append(command, style="bold yellow")
            line.append("  ")
            line.append(description)
            self._screen.print(line)

    def _unknown_slash(self, text: str) -> bool:
        """Report a ``/name`` no command answers. ``False`` if it named none.

        A name that is a skill's gets one more line: skills are not
        commands here, the agent picks one from what the task says.
        """
        token = slash_token(text)
        if token is None:
            return False
        token = inert_line(token)
        self._screen.print(Text(f"No command named /{token}.", style="yellow"))
        if self._names_a_skill(token):
            self._screen.print(
                Text(
                    "Skills are picked by the agent: describe the task "
                    f'(e.g. "use {token} to ..."); /skills lists them.',
                    style="dim",
                )
            )
        self._screen.print("[dim]/help lists the commands.[/dim]")
        return True

    def _names_a_skill(self, token: str) -> bool:
        """Whether *token* is an indexed skill's name, ignoring case."""
        lowered = token.lower()
        return any(skill.name.lower() == lowered for skill in self._app.skills.skills)

    def _skills(self, query: str) -> None:
        """List the indexed skills, grouped by domain, filtered by *query*.

        The filter is
        :meth:`~omicsclaw.skills.index.SkillIndex.search`, so it reaches
        a skill's domain, tags and trigger keywords and not only its
        name: ``/skills DE`` finds ``spatial-de`` and ``bulkrna-de``
        together with the ones whose triggers say "differential
        expression".
        """
        found = self._app.skills.search(query)
        if not found:
            if query.strip():
                self._screen.print(
                    Text(
                        f"No skill matches {inert_line(repr(query.strip()))}.",
                        style="dim",
                    )
                )
            else:
                self._screen.print("[dim]No skills indexed for this workspace.[/dim]")
            return

        self._screen.print(
            f"[dim]{len(found)} skill(s) — mention one in your request, or "
            "just describe the task:[/dim]"
        )
        grouped: dict[str, list[str]] = {}
        for skill in found:
            grouped.setdefault(skill.domain, []).append(skill.name)
        for domain, names in grouped.items():
            self._screen.print(Text(inert_line(domain or "(ungrouped)"), style="dim"))
            for name in names:
                self._screen.print(Text(f"  {inert_line(name)}"))

    def _mcp(self) -> None:
        """What ``.mcp.json`` produced, read off the live manager.

        Not the ported ``_mcp.py``: that module manages a **second**
        configuration file (``~/.config/omicsclaw/mcp.yaml``) and speaks to
        servers through ``langchain_mcp_adapters``, while this deployment
        already connects its servers in
        :func:`~omicsclaw.entry.assembly.open_app` from ``.mcp.json``
        through :mod:`omicsclaw.mcp`. Two managers over two files is worse
        than no management UI; see this package's docstring.
        """
        manager = self._app.mcp
        if manager is None:
            self._screen.print("[dim]No MCP servers configured.[/dim]")
            return
        for status in manager.statuses():
            self._screen.print(
                Text(
                    f"  {inert_line(status.name)}: {status.state.value} "
                    f"({len(status.tools)} tool(s))"
                )
            )

    async def _sessions(self) -> None:
        """List the recent conversations, and say where they are kept.

        The conversation being had is named whether or not it is in the
        list: it is absent until it has run an exchange, and a listing
        that simply left it out reads as though it were missing.
        """
        registry = self._app.sessions
        assert registry is not None  # guarded in __init__
        known = await registry.list_sessions(SESSION_LIST_LIMIT)
        if registry.persistent:
            self._screen.print(
                f"[dim]{len(known)} saved conversation(s); this workspace "
                "keeps them between runs.[/dim]"
            )
        else:
            self._screen.print(f"[dim]{_NOT_STORED}[/dim]")
        width = self._screen.console.width - _LISTING_CHROME
        for index, session in enumerate(known, start=1):
            current = session.session_id == self.state.session_id
            row = _session_summary(session, current=current, width=width)
            line = Text(f"{index:>3}. ", style="dim")
            line.append(row, style="bold" if current else "")
            self._screen.print(line)
        if not any(s.session_id == self.state.session_id for s in known):
            self._screen.print(
                Text(
                    f"  ❯ {inert_line(self.state.session_id)} is the conversation "
                    "you are in; nothing has been saved under it yet.",
                    style="dim",
                )
            )

    async def _resume(self, arg: str) -> None:
        """Continue an earlier conversation: picked, or by id or number.

        With no argument the person picks from the recent list. With one,
        the id is tried first and the number only if no conversation goes
        by that id, so a session actually called ``2`` can still be
        reached by name.
        """
        registry = self._app.sessions
        assert registry is not None  # guarded in __init__
        wanted = arg.strip()
        if not wanted:
            await self._pick_session()
            return
        session = await registry.load_session(wanted)
        if session is None:
            session = await self._numbered(wanted)
        if session is None:
            self._screen.print(
                Text(
                    f"No conversation {inert_line(wanted)}. /sessions lists what "
                    "is here.",
                    style="yellow",
                )
            )
            return
        self._switch_to(session)

    async def _pick_session(self) -> None:
        """Let the person pick a conversation to resume, or list them.

        The picker needs a source that is a :class:`ChoiceSource`. Any
        other source — a pipe, a script, a terminal without
        ``prompt_toolkit`` — gets the list and the ``/resume <number>``
        hint, so that a piped script's next line is never read as a
        choice. A picker that cannot be shown falls back to the same list.
        """
        registry = self._app.sessions
        assert registry is not None  # guarded in __init__
        known = await registry.list_sessions(SESSION_LIST_LIMIT)
        current = self.state.session_id
        others = [i for i, s in enumerate(known) if s.session_id != current]
        if not known:
            self._screen.print("[dim]No saved conversations to resume.[/dim]")
            if not registry.persistent:
                self._screen.print(f"[dim]{_NOT_STORED}[/dim]")
            return
        if not others:
            self._screen.print("[dim]No other conversation to resume.[/dim]")
            return
        if isinstance(self._source, ChoiceSource):
            width = self._screen.console.width - _PICKER_CHROME
            options = [
                _session_summary(s, current=s.session_id == current, width=width)
                for s in known
            ]
            try:
                picked = await self._source.choose(
                    _PICKER_MESSAGE, options, default=others[0]
                )
            except EOFError:
                picked = None
            except NotImplementedError:
                _log.debug("no /resume picker in this prompt_toolkit; listing")
                await self._list_for_resume()
                return
            except Exception:  # noqa: BLE001 - the REPL outlives its picker
                _log.exception("the /resume picker failed; listing instead")
                await self._list_for_resume()
                return
            if picked is None or not 0 <= picked < len(known):
                self._screen.print("[dim]Resume cancelled.[/dim]")
                return
            session = known[picked]
            if session.session_id == current:
                self._screen.print(
                    Text(f"Already in {inert_line(session.session_id)}.", style="dim")
                )
                return
            self._switch_to(session)
            return
        await self._list_for_resume()

    async def _list_for_resume(self) -> None:
        await self._sessions()
        self._screen.print(
            "[dim]Type /resume <id> or /resume <number> to continue one.[/dim]"
        )

    def _switch_to(self, session: Session) -> None:
        """Make *session* the conversation this terminal is in, and recap it."""
        self.state.session_id = session.session_id
        self.state.messages.clear()
        self._plan_shown = ()
        self._screen.print(
            Text(
                f"Resumed {inert_line(session.session_id)}: "
                f"{len(session.history)} message(s).",
                style="dim",
            )
        )
        for line in _recap(session.history, width=self._screen.console.width):
            self._screen.print(line)

    async def _numbered(self, wanted: str) -> Session | None:
        """The conversation ``/sessions`` printed as *wanted*, if any."""
        if not wanted.isdigit():
            return None
        registry = self._app.sessions
        assert registry is not None  # guarded in __init__
        known = await registry.list_sessions(SESSION_LIST_LIMIT)
        index = int(wanted)
        if 1 <= index <= len(known):
            return known[index - 1]
        return None

    async def _compact(self) -> None:
        """Summarize this conversation now, and report what that saved.

        Refused while an exchange is running in this conversation. A
        compaction queued behind one would rewrite a history the exchange
        is still adding to, and the person who typed ``/compact`` would
        be reading a report about a conversation that has moved on.
        """
        registry = self._app.sessions
        assert registry is not None  # guarded in __init__
        session_id = self.state.session_id
        if any(handle.session_id == session_id for handle in registry.running()):
            self._screen.print(
                "[yellow]This conversation is busy; /compact would have to "
                "wait for the exchange that is running. Try again when it "
                "has finished.[/yellow]"
            )
            return
        try:
            handle = await registry.compact(session_id)
        except SubmissionRefused as refused:
            self._screen.print(
                Text(f"Cannot compact now: {inert_line(str(refused))}", style="yellow")
            )
            return
        await self._drive(handle)
        outcome = handle.outcome
        record = outcome.compaction if outcome is not None else None
        self._screen.print(Text(_compaction_verdict(record), style="dim"))

    def _tasks(self) -> None:
        """Show this conversation's plan. Reads it and nothing else.

        There is no command here that writes one: ``plan_write`` refuses
        a batch of steps that claims work nobody did, and a surface that
        could set a status directly would be a way around that check
        rather than a second opinion about it.
        """
        book = self._app.plans
        if book is None:
            self._screen.print(
                "[dim]Planning is not enabled in this deployment.[/dim]"
            )
            return
        items = book.for_session(self.state.session_id).read()
        if not items:
            self._screen.print(
                "[dim]No tasks yet: nothing has been planned in this "
                "conversation.[/dim]"
            )
            return
        for line in _task_lines(items):
            self._screen.print(line)

    def _new_session(self, *, fresh_id: bool) -> None:
        """Start a conversation with no history.

        ``/new`` and ``/clear`` do the same thing here, and *fresh_id*
        only changes what the user is told. The original pair meant
        "another conversation" and "forget this one"; both are a session
        id the registry has never seen, and the one being left is still
        in the store under its own id for ``/resume`` to find.

        Implemented by **abandoning** the session rather than by editing
        one. The registry's :class:`~omicsclaw.entry.session.Session` is
        the object a lane pump saves into, and reaching into it to empty a
        tuple is how a surface races an exchange it forgot was running.
        """
        self.state.session_id = new_turn_id()[:8]
        self.state.messages.clear()
        self._plan_shown = ()
        label = "New session" if fresh_id else "Cleared; new session"
        self._screen.print(f"[dim]{label}: {self.state.session_id}[/dim]")

    # ---- the operator's own shell ---------------------------------------

    async def _shell(self, command: str) -> None:
        """Run one ``!`` command and keep the record for the next question.

        An empty command — a bare ``!`` — does nothing and says nothing:
        there is no shell command to complain about, and a complaint
        would be one more line between the person and their prompt.

        The command runs in a child Task held in :attr:`_shell_running`
        while it lasts. When :meth:`interrupt` cancels that Task, the
        command is reported and recorded as interrupted and this returns
        normally.

        :raises asyncio.CancelledError: the Task running this method was
            cancelled; the command has been killed.
        """
        if not command:
            return
        self._screen.print(Text(f"$ {inert_line(command)}", style="bold cyan"))
        if wants_a_terminal(command):
            self._screen.print(
                Text(
                    "  This one wants a terminal of its own; run it in "
                    "another window.",
                    style="yellow",
                )
            )
            return
        started = time.monotonic()
        running = asyncio.create_task(
            run_shell(
                command,
                cwd=self._app.config.workspace,
                timeout_s=self._shell_timeout_s,
            ),
            name="omicsclaw-cli-shell",
        )
        self._shell_running = running
        try:
            result = await running
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            result = ShellResult(
                command=command,
                output="",
                failed=True,
                duration_s=time.monotonic() - started,
                timed_out=False,
                interrupted=True,
            )
        finally:
            self._shell_running = None
        shown = inert_prose(for_display(result.output))
        if shown:
            self._screen.print(Text(shown, style="dim"))
        self._screen.print(Text(_shell_status(result), style=_shell_style(result)))
        self._shell_records.append(for_model(result))

    def _with_shell_records(self, text: str) -> str:
        """*text* with the commands run since the last question in front.

        Cleared as it is read, so one command is reported to the model
        once. Re-injecting it on every later question would spend the
        budget again and, worse, read as the person having run it again.
        """
        preamble = shell_preamble(self._shell_records)
        self._shell_records.clear()
        return preamble + text

    # ---- one exchange ----------------------------------------------------

    async def ask(self, text: str) -> TurnHandle | None:
        """Submit one message and print the answer as it arrives.

        Returns the handle so a caller that wants the verdict — the
        single-shot path, a test — can read :attr:`TurnHandle.terminal`
        without watching the stream a second time. ``None`` means the
        registry refused the submission.
        """
        registry = self._app.sessions
        assert registry is not None  # guarded in __init__
        try:
            handle = await registry.submit(
                self.state.session_id, self._with_shell_records(text)
            )
        except SubmissionRefused as refused:
            self._screen.print(Text(inert_line(str(refused)), style="yellow"))
            return None
        return await self._drive(handle)

    async def _drive(self, handle: TurnHandle) -> TurnHandle:
        """Put one exchange on the screen and wait for its verdict.

        Shared by :meth:`ask` and :meth:`_compact`, which differ only in
        what they submit: everything from the first frame onwards —
        rendering, approvals, reaping the questions the exchange outlived
        — is the same for a compaction as for a question.
        """
        self._running = handle
        try:
            await self._pump(handle)
            # The terminal *frame* says the exchange ended; the registry
            # records the verdict after it, once it has persisted. Waiting
            # here is what makes ``handle.terminal`` readable by the caller
            # and stops the next prompt racing a save.
            await handle.wait()
        finally:
            self._running = None
            await self._reap_asking()
        return handle

    async def _pump(self, handle: TurnHandle) -> None:
        """Consume one exchange's frames and put them on the screen.

        ``async with`` rather than a bare ``async for``: breaking out of
        an iteration does not detach the observation — ``TurnStream``
        counts attachments and an object with ``__anext__`` has no
        ``break`` hook — and a ``Ctrl-C`` is exactly a break. Without the
        context manager the abandonment grace period would never start
        and the last thing a session did would be kept alive by a cursor
        nobody holds.

        The ticker is a Task rather than a timeout on ``__anext__``
        because the two questions are different: a timeout would ask "has
        a frame arrived yet", and what the live line needs to know is
        "how long has it been" — which nothing in the iteration can
        answer while the iteration is what is waiting.
        """
        renderer = TextRenderer(batched=False)
        markdown = MarkdownStreamFormatter(self._screen.console)
        thinking = ReasoningStreamWriter(self._screen.console)
        transcript = ToolTranscript()
        activity = ActivityLine(
            self._screen,
            animated=self._animated,
            heartbeat_s=self._heartbeat_s,
        )
        self._activity = activity
        ticker = asyncio.create_task(
            drive_ticks(activity), name="omicsclaw-cli-activity"
        )
        streaming = False
        answering = False
        wrote_lines = False
        try:
            async with handle.observe() as observation:
                async for event in observation:
                    if event.type is TurnEventType.REASONING_DELTA:
                        # Not through ``renderer``: it can only mark
                        # reasoning with a text prefix, and a terminal
                        # can set it apart properly (``_reasoning``).
                        delta = self._reasoning_delta(event)
                        if delta:
                            if not streaming:
                                # From here the cursor belongs to the
                                # stream; see ``_activity``'s docstring.
                                activity.hold()
                                streaming = True
                                if wrote_lines and not thinking.is_open:
                                    # Thinking resumed after a tool line:
                                    # a gap, so the block reads as one.
                                    self._screen.print()
                            if answering:
                                # The answer paused for more thought.
                                markdown.finish()
                                self._screen.print()
                                answering = False
                            thinking.write(delta)
                        continue
                    text = renderer.feed(event)
                    if event.type is TurnEventType.TEXT_DELTA:
                        if text:
                            if not streaming:
                                activity.hold()
                                streaming = True
                            if thinking.finish():
                                # One blank line between the working
                                # and the answer it led to.
                                self._screen.print()
                            markdown.write(text)
                            answering = True
                        continue
                    if streaming:
                        thinking.finish()
                        markdown.finish()
                        self._screen.print()
                        streaming = False
                        answering = False
                        activity.release()
                    # Whatever is printed below starts at column 0.
                    activity.clear()
                    self._note_activity(event, activity)
                    if event.type is TurnEventType.APPROVAL_REQUIRED:
                        self._ask_human(handle, event)
                    if event.type is TurnEventType.TURN_END:
                        self._count(event)
                    if event.type is TurnEventType.EXCHANGE_END:
                        if event.terminal == "converged":
                            # "Done." under every answer is noise. A
                            # cancelled or failed exchange *is* printed:
                            # silence there is indistinguishable from an
                            # answer still being written.
                            continue
                    if text:
                        # ``Text`` and not a markup string: a rendered
                        # line carries an approval's ``[request_id]`` and
                        # a tool's own name, and rich would read the
                        # brackets as a style tag and delete them. Markup
                        # is for text this file wrote, never for text it
                        # was handed. ``transcript`` decides how many
                        # lines that becomes; everything but a tool call
                        # comes back as the one line it was.
                        for line in transcript.render(event, text):
                            self._screen.print(line)
                        wrote_lines = True
                    if event.type is TurnEventType.TOOL_RESULT:
                        self._show_plan(event)
        finally:
            ticker.cancel()
            try:
                await ticker
            except asyncio.CancelledError:
                # This task's cancellation, not ours. Re-raising would
                # report the exchange as interrupted whenever it ended.
                pass
            activity.close()
            self._activity = None
        if streaming:
            thinking.finish()
            markdown.finish()
        tail = renderer.flush()
        if tail:
            markdown.write(tail)
            markdown.finish()
        self._screen.print()

    def _reasoning_delta(self, event: TurnEvent) -> str:
        """The reasoning this frame carries, or ``""`` if it is not shown."""
        if not self._show_reasoning or event.engine is None:
            return ""
        return event.engine.delta or ""

    def _note_activity(self, event: TurnEvent, activity: ActivityLine) -> None:
        """Tell the live line what this frame changed about the wait.

        A tool result puts the line back to "waiting for the model"
        rather than leaving the finished tool's name up: the next thing
        to take time is the model call that reads the result, and a line
        still naming ``bash`` while the model thinks is worse than no
        line, because it is wrong rather than merely absent.

        ``TOOL_START`` goes to :meth:`ActivityLine.started` rather than
        to ``begin``; see there for why the two frames can arrive in
        either order.
        """
        kind = event.type
        if kind is TurnEventType.TOOL_START:
            call = event.engine.tool_call if event.engine is not None else None
            activity.started(call.name if call is not None else "a tool")
            return
        if kind is TurnEventType.PROGRESS:
            update = event.progress
            if update is not None:
                activity.detail(update.message, tool=update.tool_name)
            return
        if kind in (
            TurnEventType.TOOL_RESULT,
            TurnEventType.EXCHANGE_START,
            TurnEventType.TURN_END,
            TurnEventType.COMPACTION,
        ):
            activity.begin()

    def _show_plan(self, event: TurnEvent) -> None:
        """Print the plan after a ``plan_write`` that changed it.

        Reads the book rather than the tool's own output: the tool
        answers with what it accepted, and what a person needs to see is
        the whole list including the items this call did not mention
        (``plan_write`` takes partial updates). Silent when nothing moved,
        which is what a read-mode call and a refused write both are.
        """
        result = event.engine.tool_result if event.engine is not None else None
        if result is None or result.is_error or result.name != PLAN_WRITE_TOOL_NAME:
            return
        book = self._app.plans
        if book is None:
            return
        items = tuple(book.for_session(self.state.session_id).read())
        snapshot = tuple((item.content, item.status.value) for item in items)
        if not items or snapshot == self._plan_shown:
            return
        self._plan_shown = snapshot
        for line in _task_lines(items):
            self._screen.print(line)

    def _count(self, event: TurnEvent) -> None:
        """Accumulate what ``/usage`` reports, when the backend said.

        ``TURN_END.usage`` is ``None`` on a streamed run whose backend
        reported nothing, and a zero :class:`~omicsclaw.schema.Usage`
        means "free **or** unreported" (plan 0031 trap 7). Adding zero for
        both would make the two indistinguishable in the total, so the
        ``None`` case is skipped and the zero case is added — which is
        also why the per-turn line comes from
        :class:`~omicsclaw.entry.render.TextRenderer`, the one place that
        has a distinct string for each.
        """
        usage = event.engine.usage if event.engine is not None else None
        if usage is None:
            return
        self._usage[0] += usage.input_tokens
        self._usage[1] += usage.output_tokens

    # ---- interruption ----------------------------------------------------

    def interrupt(self) -> bool:
        """Cancel what runs in the foreground. ``Ctrl-C``'s whole effect.

        That is the running exchange if there is one, otherwise the
        running ``!`` command. Returns whether there was either, so a
        caller can tell interrupted work from an interrupted prompt — the
        process's entry point uses the answer to decide whether ``Ctrl-C``
        at an idle prompt should quit.

        **Must be called on the event loop's thread.** The entry point's
        ``SIGINT`` handler, installed with :func:`signal.signal`, does not
        call this itself: it schedules the call on the loop with
        :meth:`~asyncio.loop.call_soon_threadsafe`.
        """
        handle = self._running
        if handle is not None:
            _log.info("cancelling turn %s on user interrupt", handle.turn_id)
            handle.cancel()
            return True
        shell = self._shell_running
        if shell is not None:
            _log.info("cancelling a shell command on user interrupt")
            shell.cancel()
            return True
        return False

    # ---- approvals -------------------------------------------------------

    def _ask_human(self, handle: TurnHandle, event: TurnEvent) -> None:
        """Start asking, and return to the pump immediately (trap 1).

        The hold is taken **here** rather than inside :meth:`_ask`, so
        that it is in force before the new Task has had a chance to run:
        a tick landing between ``create_task`` and the prompt would paint
        a spinner that ``prompt_toolkit`` is about to draw over.
        """
        activity = self._activity
        if activity is not None:
            activity.hold()
        task = asyncio.create_task(
            self._answer(handle, event.request_id, event, activity),
            name=f"omicsclaw-cli-approval-{event.request_id}",
        )
        self._asking.add(task)
        task.add_done_callback(self._forget_asking)

    async def _answer(
        self,
        handle: TurnHandle,
        request_id: str,
        event: TurnEvent,
        activity: ActivityLine | None,
    ) -> None:
        """Ask, and give the live line back however the question ends.

        A wrapper rather than a ``finally`` inside :meth:`_ask` so that
        the pair is balanced even on the path where ``_ask`` itself
        raises — which is the path :meth:`_forget_asking` exists for. An
        unbalanced hold is an exchange that runs with nothing on screen,
        which is the defect this mechanism exists to remove.
        """
        try:
            await self._ask(handle, request_id, event)
        finally:
            if activity is not None:
                activity.release()

    def _forget_asking(self, task: "asyncio.Task[None]") -> None:
        """Drop a finished question, and never drop its failure with it.

        The exception has to be *retrieved*, not only discarded: an
        unretrieved one is reported by the event loop at garbage
        collection, which here means inside a log sink the REPL is holding
        until it gives the terminal back. :meth:`_ask` answers on every
        path it can reach, so arriving here with an exception means it
        could not — and the exchange that was waiting for that answer is
        the thing the line explains.
        """
        self._asking.discard(task)
        if task.cancelled():
            return
        failure = task.exception()
        if failure is not None:
            _log.error("approval task failed: %r", failure)

    async def _read_card(
        self,
        prompt: str,
        *,
        subject: str,
        settled_as: str,
        refuse: Callable[[str], Awaitable[object]],
    ) -> str | None:
        """Read the answer to a card, and settle the card when there is none.

        Every path that ends without a line awaits ``refuse(reason)``
        exactly once:

        - Ctrl-C at the card (:exc:`KeyboardInterrupt` from the source):
          reason :data:`_INTERRUPTED_REASON`, then :meth:`interrupt`
          cancels the running exchange, also when *refuse* raises;
        - the source ended (:exc:`EOFError`) or the Task reading was
          cancelled: reason :data:`_NO_OPERATOR_REASON`;
        - any other exception from the source: it is logged, the line
          ``Could not ask about <subject>: <error>. <settled_as>.`` is
          printed, and the reason is ``the terminal could not ask:
          <error>``.

        :param prompt: the card's prompt line.
        :param subject: what the card asks about, for the printed line.
        :param settled_as: what *refuse* makes of the card, ending the
            printed line (``"Denied"``).
        :param refuse: settles this card as unanswered with the given
            reason.
        :returns: the line typed, or ``None``, by which point the card is
            settled.
        :raises Exception: whatever *refuse* raises.
        """
        try:
            return await self._source.read(prompt)
        except KeyboardInterrupt:
            try:
                await refuse(_INTERRUPTED_REASON)
            finally:
                self.interrupt()
        except (EOFError, asyncio.CancelledError):
            await refuse(_NO_OPERATOR_REASON)
        except Exception as exc:  # noqa: BLE001 - every failure settles the card
            _log.exception("could not ask about %s", subject)
            # ``Text`` and not markup: *subject* and the error message are
            # strings this file was handed, and rich would read a bracket
            # in either as a style tag.
            self._screen.print(
                Text(
                    f"Could not ask about {subject}: {inert_line(str(exc))}. "
                    f"{settled_as}.",
                    style="yellow",
                )
            )
            await refuse(f"the terminal could not ask: {exc}")
        return None

    async def _ask(
        self, handle: TurnHandle, request_id: str, event: TurnEvent
    ) -> None:
        """Put one question to the person and send back what they said.

        The prompt names the tool and nothing else. What the request is
        *about* — its risk tier and the tool's own reason, which may carry
        the command, a diff, a URL or a bounded argument preview — was
        already printed by the pump from
        :class:`~omicsclaw.entry.render.TextRenderer`. The raw
        ``event.approval.arguments`` are never printed here.

        A card that gets no answer — Ctrl-C at it, the input ending, the
        Task being cancelled, the source failing — denies the request (see
        :meth:`_read_card`); Ctrl-C also cancels the exchange.
        """
        request = event.approval
        name = inert_line(request.tool_name) if request is not None else "a tool"
        if request is not None and self._already_granted(request):
            self._screen.print(
                Text(f"{name}: allowed for this conversation.", style="dim")
            )
            await handle.approve(request_id, ApprovalDecision(True, ""))
            return
        note = approval_body_note(request) if request is not None else ""
        prompt = _APPROVAL_PROMPT.format(
            name=name,
            card=inert_line(_card(request_id)),
            size=f" {note}" if note else "",
        )
        always_asked = request is not None and request.ask_every_time
        rememberable = request is None or self._app.can_remember_approval(request)
        while True:
            legend = self._approval_legend(always_asked, rememberable)
            self._screen.print(Text(legend, style="dim"))
            answer = await self._read_card(
                prompt,
                subject=name,
                settled_as="Denied",
                refuse=lambda reason: handle.approve(
                    request_id, ApprovalDecision(False, reason)
                ),
            )
            if answer is None:
                return
            if not is_auto_answer(answer):
                break
            # ``/auto`` typed at the card is what a person means when the
            # legend has just told them it exists (plan 0050 §3.5): switch,
            # then settle this card the way the new mode would have. A card
            # the gate always asks about is asked again, because
            # auto-approve would have asked it too.
            try:
                self._auto("on")
            except Exception as exc:  # noqa: BLE001 - see below
                # ``_ask`` settles its request on every path (see
                # ``_forget_asking``); a failure while switching is reported
                # and the card is asked again, never left open.
                _log.exception("/auto at an approval card failed")
                self._screen.print(
                    Text(f"/auto failed: {inert_line(str(exc))}", style="yellow")
                )
                continue
            if not always_asked and self._live_mode() is PermissionMode.AUTO_APPROVE:
                await handle.approve(request_id, ApprovalDecision(True, ""))
                return
        verdict = answer.strip().lower()
        always = verdict in _ALWAYS
        for_session = verdict in _FOR_THIS_SESSION
        approved = always or for_session or verdict in _YES
        if always and request is not None:
            if rememberable:
                self._remember(request)
            else:
                self._screen.print(
                    Text(
                        "Allowed this call only: no rule can allow changes to "
                        "the files that decide what is asked about.",
                        style="dim",
                    )
                )
        if for_session and request is not None:
            if always_asked:
                self._screen.print(
                    Text(
                        f"Allowed this call only: {name} calls "
                        "like it are always asked about.",
                        style="dim",
                    )
                )
            else:
                self._granted.add(self._grant_key(request))
                self._screen.print(
                    Text(
                        f"Will not ask about {name} again in this "
                        "conversation, except for calls that are always asked "
                        "about. Nothing was written to disk.",
                        style="dim",
                    )
                )
        reason = answer.strip()
        if reason.startswith("/"):
            # A command typed at the wrong prompt is not a message for the
            # model; sending "/usage" as the reason a call was refused would
            # be a refusal it cannot act on.
            reason = "denied at the terminal"
        await handle.approve(
            request_id,
            ApprovalDecision(approved, "" if approved else reason),
        )

    def _approval_legend(self, always_asked: bool, rememberable: bool = True) -> str:
        """The grants, and ``/auto`` where it would stop cards like this one.

        Only in ``default``: in ``read-only`` the command is refused, and in
        ``auto-approve`` a card like this one would not have been shown. Not
        on a card the gate always asks about, which ``/auto`` cannot stop.
        """
        if not rememberable:
            return _PROTECTED_LEGEND
        if always_asked:
            return _ALWAYS_ASKED_LEGEND
        if self._live_mode() is PermissionMode.DEFAULT:
            return f"{_APPROVAL_LEGEND} · /auto stops these"
        return _APPROVAL_LEGEND

    # ---- /auto ----------------------------------------------------------

    def _live_mode(self) -> PermissionMode | None:
        """The gate's mode now —— not ``config.permission_mode``, which is
        the start-up value and goes stale at the first ``/auto``."""
        gate = self._app.permission
        return gate.mode if gate is not None else None

    def _live_mode_name(self) -> str:
        mode = self._live_mode()
        return mode.value if mode is not None else "ungated"

    def _auto(self, argument: str) -> None:
        """Switch between asking and not asking, now and for the next start.

        The two halves are decided separately (plan 0050 §3.2): the switch by
        the gate's mode, the save by what the file says. A switch the app
        refuses saves nothing —— the refusal means this session is under a
        promise, and writing the opposite into the file would be making a
        new one behind the person's back.
        """
        action = auto_action(argument)
        if action is None:
            self._screen.print(Text(AUTO_USAGE, style="yellow"))
            return
        if action == "status":
            self._auto_status()
            return
        target = (
            PermissionMode.AUTO_APPROVE if action == "on" else PermissionMode.DEFAULT
        )
        try:
            previous = self._app.set_permission_mode(target)
        except ValueError as exc:
            self._screen.print(Text(inert_line(str(exc)), style="yellow"))
            return
        if previous is None:
            self._screen.print(
                Text("This app has no permission gate; nothing to switch.", style="yellow")
            )
            return
        if previous is target:
            self._screen.print(Text(f"Already {target.value}.", style="dim"))
        elif target is PermissionMode.AUTO_APPROVE:
            self._screen.print(Text(self._auto_on_notice(), style="dim"))
        else:
            self._screen.print(
                Text("Back to default: tool calls are asked about again.", style="dim")
            )
        self._save_mode(target)

    def _auto_on_notice(self) -> str:
        """What auto-approve means, said every time it is turned on."""
        return (
            "Auto-approve is on for this whole process (it survives /new "
            "and /resume, unlike s). Ordinary tool calls run without asking. Still "
            "asked every time: dangerous commands, explicit ask rules, and "
            "changes to .omicsclaw/ or .env; deny rules still deny. The "
            f"dangerous-command patterns are a deny-list, not a boundary: "
            f"{self._sandbox_state()} Applies to oc cli only."
        )

    def _sandbox_state(self) -> str:
        """Where ``bash`` actually runs —— read from the live binding, not
        from the configuration, which says what was asked for."""
        binding = self._app.sandbox
        if binding is not None and binding.active:
            return "bash runs in the sandbox container."
        if binding is not None and binding.degraded:
            why = f" ({inert_line(binding.unavailable)})" if binding.unavailable else ""
            return (
                f"a sandbox was requested but is not in use{why}, so bash "
                "runs on this machine."
            )
        return (
            "bash runs directly on this machine; OMICSCLAW_SANDBOX=docker "
            "puts it in a container."
        )

    def _save_mode(self, mode: PermissionMode) -> None:
        """Write the CLI's mode to ``.env``, and say whether it will count.

        A save that fails does not undo the switch: the person asked for
        both, the switch happened, and the report says which half did not
        —— the rule :meth:`_remember` follows for ``a``.
        """
        if self._dotenv_path is None:
            self._screen.print(
                Text(
                    "This run has no .env to save to; the next start will not "
                    "remember this.",
                    style="dim",
                )
            )
            return
        try:
            report = persist_cli_mode(self._dotenv_path, mode)
        except (OSError, ValueError, RuntimeError) as exc:
            # RuntimeError: a symlink loop, on the Python versions where
            # ``Path.resolve`` raises that rather than an OSError.
            self._screen.print(
                Text(
                    f"Could not save to {self._dotenv_path}: {inert_line(str(exc))}",
                    style="yellow",
                )
            )
            return
        self._screen.print(Text(inert_line(report), style="dim"))
        outranked = self._outranked_by()
        if outranked:
            self._screen.print(
                Text(
                    f"At the next start {outranked} will decide instead.",
                    style="yellow",
                )
            )

    def _outranked_by(self) -> str:
        """What will beat the saved setting at the next start, if anything."""
        if self._permission_mode_source == "flag":
            return (
                "the --permission-mode flag, if it is passed again as it was "
                "this time,"
            )
        if self._permission_mode_source == "environment":
            return (
                "OMICSCLAW_PERMISSION_MODE (set in the environment or .env, "
                "and ahead of the CLI's own key)"
            )
        return ""

    def _auto_status(self) -> None:
        try:
            saved = inert_line(saved_cli_mode(self._dotenv_path) or "not set")
        except (OSError, ValueError) as exc:
            saved = f"unreadable ({inert_line(str(exc))})"
        where = str(self._dotenv_path) if self._dotenv_path else "no .env"
        started = {
            "flag": "the --permission-mode flag",
            "environment": "OMICSCLAW_PERMISSION_MODE",
            "cli-key": CLI_PERMISSION_MODE_VARIABLE,
        }.get(self._permission_mode_source, "the default")
        self._screen.print(
            Text(
                f"Permissions now: {self._live_mode_name()} · started from "
                f"{started} · {CLI_PERMISSION_MODE_VARIABLE} in {where}: "
                f"{saved} · {self._sandbox_state()}",
                style="dim",
            )
        )

    def _grant_key(self, request: ApprovalRequest) -> tuple[str, str]:
        """What :attr:`_granted` remembers one approved call as.

        The conversation is part of the key rather than something
        ``/new`` has to remember to clear: a grant made in one
        conversation does not apply in the next, and resuming the first
        one brings its grants back with it.
        """
        return (self.state.session_id, request.tool_name)

    def _already_granted(self, request: ApprovalRequest) -> bool:
        """Whether this conversation said ``s`` to this tool, and may use it.

        Never for a question the gate marked ``ask_every_time``: the grant
        was given for the tool's ordinary calls, and this one is not one.
        """
        if request.ask_every_time:
            return False
        return self._grant_key(request) in self._granted

    def _remember(self, request: ApprovalRequest) -> None:
        """Write an ``allow`` rule for this call, and say what happened.

        Reports the outcome on screen either way: a person who asked not to
        be asked again and is asked again anyway stops trusting the prompt,
        so "this run cannot remember that" has to be visible rather than
        silent. Never raises — a rule file that cannot be written must not
        turn a granted approval into a failed tool call.
        """
        try:
            pattern = self._app.remember_approval(request)
        except OSError as exc:
            self._screen.print(
                Text(f"Could not save the rule: {inert_line(str(exc))}", style="dim")
            )
            return
        if pattern is None:
            self._screen.print("[dim]This run has nowhere to remember that.[/dim]")
            return
        # ``Text``: a pattern is a string this file was handed, and rich
        # would read the brackets ``literal_pattern`` escapes with as tags.
        note = f"Remembered: always allow {inert_line(pattern)}"
        if "(" in pattern:
            # Without an argument the rule is the whole tool; with one it
            # is this call and no other, which is not what a person who
            # pressed "always" on ``bash`` usually expects.
            note += (
                f" (this exact call only; s stops asking about "
                f"{inert_line(request.tool_name)} for this conversation)"
            )
        self._screen.print(Text(note, style="dim"))

    async def _reap_asking(self) -> None:
        """Cancel and await whatever question the exchange outlived.

        An exchange can end — converged, cancelled, timed out — while a
        person is still looking at an approval prompt. The Task waiting
        for them has nothing left to answer, and an un-awaited cancelled
        Task prints "Task exception was never retrieved" into a terminal
        the user is still reading.
        """
        if not self._asking:
            return
        pending = tuple(self._asking)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        self._asking.clear()

    # ---- presentation ----------------------------------------------------

    def welcome(self, *, slogan: str = "") -> None:
        """Logo, deployment facts and one line of greeting.

        The ported banner picked its slogan with :func:`random.choice`;
        this one takes the first unless told otherwise. A surface whose
        output changes between two runs of the same command cannot be
        compared, and a greeting is not worth a seeded RNG — a deployment
        that wants variety passes one.

        The model name is :class:`~omicsclaw.entry.config.AppConfig`'s
        and there is no provider fallback:
        :class:`~omicsclaw.provider.LLMProvider` does not publish one, so
        reading ``provider.model`` here crashed this command on its first
        line. An unnamed model prints no ``Model:`` field, which is
        honest — the provider layer has not detected one yet.
        """
        self._screen.banner(
            session_id=self.state.session_id,
            workspace=self._app.config.workspace,
            model=self._app.config.model,
            provider=self._app.provider.name,
        )
        chosen = slogan or WELCOME_SLOGANS[0]
        self._screen.print(f"[dim italic]  {chosen}[/dim italic]")
        self._screen.rule()


async def run_once(
    app: AgentApp,
    text: str,
    *,
    screen: Screen | None = None,
    source: PromptSource | None = None,
    show_reasoning: bool = False,
) -> TurnHandle | None:
    """One prompt, one answer, no loop — the harness's ``RunOnce``.

    ``cli.go:27-33`` passes the **whole** file as one ``userPrompt`` and
    says why in a comment: unlike the line-oriented REPL, this avoids a
    multi-line task instruction being split into several independent
    turns. The same reasoning is why *text* here is one string and not a
    sequence of lines.

    *source* is only consulted if a tool asks for approval. Passing
    ``None`` means nobody is at the terminal and every request is denied —
    fail closed, which is also what a deadline expiring does.
    """
    from ._input import ScriptedSource

    repl = Repl(
        app,
        source=source if source is not None else ScriptedSource(()),
        screen=screen,
        show_reasoning=show_reasoning,
    )
    return await repl.ask(text)
