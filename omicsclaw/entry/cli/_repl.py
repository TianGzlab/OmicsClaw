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
printed is prefixed to the *next* question and then dropped. That module
is where the reasoning about timeouts, ceilings and the absent approval
gate lives.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Sequence

from rich.text import Text

from omicsclaw.context import CompactionRecord
from omicsclaw.entry.assembly import AgentApp
from omicsclaw.entry.events import TurnEvent, TurnEventType
from omicsclaw.entry.render import TextRenderer
from omicsclaw.entry.session import Session, SubmissionRefused, new_turn_id
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.planning import PLAN_WRITE_TOOL_NAME, PlanItem, PlanStatus
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest

from ._activity import HEARTBEAT_S, ActivityLine, drive_ticks
from ._constants import WELCOME_SLOGANS
from ._input import PromptSource
from ._markdown import MarkdownStreamFormatter
from ._screen import Screen
from ._session_state import SessionState
from ._shell import (
    SHELL_TIMEOUT_S,
    ShellResult,
    for_display,
    for_model,
    run_shell,
    shell_preamble,
    wants_a_terminal,
)
from ._slash_command_support import (
    CLI_SLASH_COMMAND_SPECS,
    REPL_SLASH_COMMAND_SPECS,
    parse_slash_command,
    slash_command_help_rows,
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

_APPROVAL_PROMPT = "approve {name} [{card}]? [y/N/a=always] "
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
terminal, which costs more than it tells."""

_YES = frozenset({"y", "yes", "ok", "allow"})
"""Everything counted as consent. Anything else denies, including the
empty line, because plan 0031 Q12 rules that approval fails closed and a
person who pressed enter to get their prompt back has not agreed to
anything."""

_ALWAYS = frozenset({"a", "always"})
"""Consent, plus a request to write an ``allow`` rule for this exact call.

A subset of consent rather than a fourth outcome: an answer here both
approves and persists, and an answer that persisted without approving
would be a rule nobody acted on. The rule written covers only the call
that was shown — see
:meth:`~omicsclaw.entry.assembly.AgentApp.remember_approval`."""

_FOR_THIS_SESSION = frozenset({"s", "session"})
"""Consent, plus "stop asking me about this call in this conversation".

The middle of the three grants, and the one a person reaches for most:
``y`` costs a prompt per call and ``a`` writes a rule that outlives the
reason for it. This one is remembered in :attr:`Repl._granted` and
nowhere else, so it dies with the conversation and with the process, and
:meth:`~omicsclaw.permission.PermissionGate.remember` is never called —
which is the observable difference between the two, and what a person
choosing between them is choosing."""

_APPROVAL_LEGEND = (
    "  y = allow once · s = allow for this conversation · "
    "a = always, and write a rule · anything else denies"
)
"""The three grants spelled out, printed above each approval card.

``[y/N/a=always]`` in the prompt itself is the short form and stays that
way — it is the string the approval tests name and it is already as wide
as a narrow terminal wants — so the middle grant would otherwise be a
key nobody could discover. The reference harness has the same problem
and solves it the same way: its dialog lists all of its options
(``tui_view.go:467-491``) rather than compressing them into the prompt.
"""

SESSION_LIST_LIMIT = 10
"""Conversations ``/sessions`` and ``/resume`` show.

The reference harness's number (``tui_update.go:1409-1421``) and its
reason: a resume list is read by eye, and a list longer than a screen is
one a person scrolls rather than reads. ``/resume <id>`` reaches a
conversation that has fallen off the end; the list is a convenience, not
the index.
"""

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

    :class:`~rich.text.Text` and not markup: the content is whatever the
    model wrote, and ``[read the matrix]`` would be swallowed as a style
    tag.
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
        line.append(item.content, style=_TASK_STYLES[item.status])
        line.append(f"  [{item.status.value}]", style="dim")
        lines.append(line)
    return lines


def _session_line(session: Session, *, index: int, current: bool) -> Text:
    """One row of ``/sessions``: which conversation, how big, how old."""
    when = datetime.fromtimestamp(session.created_at).strftime("%Y-%m-%d %H:%M")
    line = Text(f"{index:>3}. ", style="dim")
    line.append("❯ " if current else "  ", style="bold" if current else "dim")
    line.append(session.session_id, style="bold" if current else "")
    line.append(f"  {len(session.history)} message(s)  {when}", style="dim")
    return line


def _shell_status(result: ShellResult) -> str:
    """The line under a ``!`` command's output saying how it ended."""
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
                f"was: {record.degraded}"
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
        "_granted",
        "_heartbeat_s",
        "_plan_shown",
        "_running",
        "_screen",
        "_shell_records",
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
    ) -> None:
        if app.sessions is None:
            raise ValueError(
                "this app has no session registry — build it with "
                "attach_sessions(build_app(config))"
            )
        self._app = app
        self._source = source
        self._screen = screen if screen is not None else Screen()
        self._show_reasoning = show_reasoning
        self._shell_timeout_s = shell_timeout_s
        self._running: TurnHandle | None = None
        self._asking: set[asyncio.Task[None]] = set()
        self._granted: set[tuple[str, str, str]] = set()
        """``(session id, tool name, arguments)`` a person said "for this
        conversation" about. Keyed by the arguments as they were sent, so
        it grants less than the rule ``a`` writes and never more; this is
        a surface's shortcut and not a second implementation of what
        :mod:`omicsclaw.permission` decides a call is."""
        self._shell_records: list[str] = []
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
        """
        if text.startswith("!"):
            await self._shell(text[1:].strip())
            return True
        command = parse_slash_command(text, CLI_SLASH_COMMAND_SPECS)
        if command is None:
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
            self._screen.print(
                f"[dim]Session {self.state.session_id} in "
                f"{self.state.workspace_dir}[/dim]"
            )
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

    def _skills(self, domain: str) -> None:
        names = self._app.skills.names()
        wanted = domain.strip().lower()
        if wanted:
            names = tuple(name for name in names if wanted in name.lower())
        if not names:
            self._screen.print("[dim]No skills indexed for this workspace.[/dim]")
            return
        self._screen.print(f"[dim]{len(names)} skill(s):[/dim]")
        for name in names:
            self._screen.print(f"  {name}")

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
                f"  {status.name}: {status.state.value} "
                f"({len(status.tools)} tool(s))"
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
            self._screen.print(
                "[dim]This deployment stores no conversations: they are "
                "held in memory and lost when the process exits.[/dim]"
            )
        for index, session in enumerate(known, start=1):
            self._screen.print(
                _session_line(
                    session,
                    index=index,
                    current=session.session_id == self.state.session_id,
                )
            )
        if not any(s.session_id == self.state.session_id for s in known):
            self._screen.print(
                Text(
                    f"  ❯ {self.state.session_id} is the conversation you are "
                    "in; nothing has been saved under it yet.",
                    style="dim",
                )
            )

    async def _resume(self, arg: str) -> None:
        """Continue an earlier conversation, by id or by listed number.

        The id is tried first and the number only if no conversation goes
        by that id, so a session actually called ``2`` can still be
        reached by name — a resolution order the other way round would
        make some ids unreachable and give no sign of it.
        """
        registry = self._app.sessions
        assert registry is not None  # guarded in __init__
        wanted = arg.strip()
        if not wanted:
            await self._sessions()
            self._screen.print(
                "[dim]Type /resume <id> or /resume <number> to continue "
                "one.[/dim]"
            )
            return
        session = await registry.load_session(wanted)
        if session is None:
            session = await self._numbered(wanted)
        if session is None:
            self._screen.print(
                Text(
                    f"No conversation {wanted}. /sessions lists what is here.",
                    style="yellow",
                )
            )
            return
        self.state.session_id = session.session_id
        self.state.messages.clear()
        self._plan_shown = ()
        self._screen.print(
            Text(
                f"Resumed {session.session_id}: "
                f"{len(session.history)} message(s).",
                style="dim",
            )
        )

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
            self._screen.print(Text(f"Cannot compact now: {refused}", style="yellow"))
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
        """
        if not command:
            return
        self._screen.print(Text(f"$ {command}", style="bold cyan"))
        if wants_a_terminal(command):
            self._screen.print(
                Text(
                    "  This one wants a terminal of its own; run it in "
                    "another window.",
                    style="yellow",
                )
            )
            return
        result = await run_shell(
            command,
            cwd=self._app.config.workspace,
            timeout_s=self._shell_timeout_s,
        )
        shown = for_display(result.output)
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
            self._screen.print(f"[yellow]{refused}[/yellow]")
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
        renderer = TextRenderer(
            batched=False, show_reasoning=self._show_reasoning
        )
        markdown = MarkdownStreamFormatter(self._screen.console)
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
        try:
            async with handle.observe() as observation:
                async for event in observation:
                    text = renderer.feed(event)
                    if event.type in (
                        TurnEventType.TEXT_DELTA,
                        TurnEventType.REASONING_DELTA,
                    ):
                        if text:
                            if not streaming:
                                # From here the cursor belongs to the
                                # answer; see ``_activity``'s docstring.
                                activity.hold()
                                streaming = True
                            markdown.write(text)
                        continue
                    if streaming:
                        markdown.finish()
                        self._screen.print()
                        streaming = False
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
                        # was handed.
                        self._screen.print(Text(text, style="dim"))
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
            markdown.finish()
        tail = renderer.flush()
        if tail:
            markdown.write(tail)
            markdown.finish()
        self._screen.print()

    def _note_activity(self, event: TurnEvent, activity: ActivityLine) -> None:
        """Tell the live line what this frame changed about the wait.

        A tool result puts the line back to "waiting for the model"
        rather than leaving the finished tool's name up: the next thing
        to take time is the model call that reads the result, and a line
        still naming ``bash`` while the model thinks is worse than no
        line, because it is wrong rather than merely absent.
        """
        kind = event.type
        if kind is TurnEventType.TOOL_START:
            call = event.engine.tool_call if event.engine is not None else None
            activity.begin(call.name if call is not None else "a tool")
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
        """Cancel the exchange that is running. ``Ctrl-C``'s whole effect.

        Returns whether there was one, so a caller can tell an interrupted
        exchange from an interrupted prompt — the process's entry point
        uses the answer to decide whether ``Ctrl-C`` at an idle prompt
        should quit.

        **Must be called on the event loop's thread.** Cancelling a Task
        and resolving the futures behind it is only safe there, and
        :func:`signal.signal` handlers run between bytecodes on the main
        thread, which is not the same statement. The entry point therefore
        installs this through :meth:`asyncio.loop.add_signal_handler`
        (plan 0031 trap 10).
        """
        handle = self._running
        if handle is None:
            return False
        _log.info("cancelling turn %s on user interrupt", handle.turn_id)
        handle.cancel()
        return True

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

    async def _ask(
        self, handle: TurnHandle, request_id: str, event: TurnEvent
    ) -> None:
        """Put one question to the person and send back what they said.

        The prompt names the tool and nothing else. What the request is
        *about* — its risk tier and the tool's own reason — was already
        printed by the pump from
        :class:`~omicsclaw.entry.render.TextRenderer`, which is also the
        one place that decides what an approval card may show. It shows no
        arguments: they are the payload plan 0031 Q22 rule 1 keeps out of
        a log, and a terminal is a log with a scrollback buffer. A surface
        that has decided it may show them reads
        ``event.approval.arguments`` itself, having taken that decision
        explicitly.
        """
        request = event.approval
        name = request.tool_name if request is not None else "a tool"
        if request is not None and self._already_granted(request):
            self._screen.print(
                Text(f"{name}: allowed for this conversation.", style="dim")
            )
            await handle.approve(request_id, ApprovalDecision(True, ""))
            return
        prompt = _APPROVAL_PROMPT.format(name=name, card=_card(request_id))
        self._screen.print(f"[dim]{_APPROVAL_LEGEND}[/dim]")
        try:
            answer = await self._source.read(prompt)
        except (EOFError, asyncio.CancelledError):
            # Nobody is there to say yes. Fail closed, exactly as an
            # expired deadline does (plan 0031 Q12).
            await handle.approve(
                request_id, ApprovalDecision(False, "no operator at the terminal")
            )
            return
        except Exception as exc:  # noqa: BLE001 - see below
            # The question could not be put. Denying is the only safe
            # answer, and it has to be *an* answer: a terminal deployment
            # sets no approval deadline, so returning without settling the
            # request stops the exchange for good — which is what a broken
            # prompt used to do, silently and with the log held back until
            # the process exited.
            _log.exception("could not ask about %s", name)
            # ``Text`` and not markup: both the tool's name and the
            # exception's message are strings this file was handed, and
            # rich would read a bracket in either as a style tag.
            self._screen.print(
                Text(f"Could not ask about {name}: {exc}. Denied.", style="yellow")
            )
            await handle.approve(
                request_id,
                ApprovalDecision(False, f"the terminal could not ask: {exc}"),
            )
            return
        verdict = answer.strip().lower()
        always = verdict in _ALWAYS
        for_session = verdict in _FOR_THIS_SESSION
        approved = always or for_session or verdict in _YES
        if always and request is not None:
            self._remember(request)
        if for_session and request is not None:
            self._granted.add(self._grant_key(request))
            self._screen.print(
                Text(
                    f"Will not ask about {request.tool_name} again in this "
                    "conversation. Nothing was written to disk.",
                    style="dim",
                )
            )
        await handle.approve(
            request_id,
            ApprovalDecision(approved, "" if approved else answer.strip()),
        )

    def _grant_key(self, request: ApprovalRequest) -> tuple[str, str, str]:
        """What :attr:`_granted` remembers one approved call as.

        The conversation is part of the key rather than something
        ``/new`` has to remember to clear: a grant made in one
        conversation does not apply in the next, and resuming the first
        one brings its grants back with it.
        """
        return (self.state.session_id, request.tool_name, request.arguments)

    def _already_granted(self, request: ApprovalRequest) -> bool:
        """Whether this conversation has said yes to this exact call before."""
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
            self._screen.print(f"[dim]Could not save the rule: {exc}[/dim]")
            return
        if pattern is None:
            self._screen.print("[dim]This run has nowhere to remember that.[/dim]")
            return
        self._screen.print(f"[dim]Remembered: always allow {pattern}[/dim]")

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
