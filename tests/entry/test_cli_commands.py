"""The commands plan 0041 reconnected: sessions, resume, compact, tasks.

Every test here builds a **real**
:class:`~omicsclaw.entry.assembly.AgentApp` — real registry, real SQLite
session store under ``tmp_path``, real plan book — over the scripted
provider ``test_turn_runner.py`` defines, and reads what the surface
printed out of a :class:`io.StringIO`. The point of that is the same as
in ``test_cli_repl.py``: the commands below are all *wiring*, and a
double in the middle of wiring proves only that the double was called.

There is no ``pytest-asyncio`` on this machine, so every test drives
:func:`asyncio.run` itself and **every await is inside an
:func:`asyncio.wait_for`** — a defect in this loop shows up as a hang,
and a hang with no timeout plugin is a test run that never finishes.
"""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import pathlib

import pytest

from omicsclaw.context import ContextBudget
from omicsclaw.engine import AgentEngine
from omicsclaw.entry.cli import Repl, ScriptedSource, Screen
from omicsclaw.entry.session import SessionRegistry, attach_sessions
from omicsclaw.memory import SqliteSessionStore, StoredSession
from omicsclaw.planning import PLAN_WRITE_TOOL_NAME
from omicsclaw.schema import Message, Role, ToolCall
from tests.entry.test_cli_repl import (  # type: ignore[import-not-found]
    WAIT_S,
    answering,
    build,
    repl_over,
)
from tests.entry.test_session import Canned  # type: ignore[import-not-found]
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    Sleeping,
    calling,
    make_app,
)


def run(coro):
    """One bounded await, driven without a timeout plugin."""
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


async def drive_repl(app, lines, **kwargs) -> str:
    """Run a whole REPL over *lines* and return everything it printed."""
    repl, _source, buffer = repl_over(app, lines, **kwargs)
    await asyncio.wait_for(repl.run(), WAIT_S)
    return buffer.getvalue()


# ---- /sessions --------------------------------------------------------


def test_sessions_tells_a_stored_deployment_from_an_unstored_one(tmp_path):
    """One test, both deployments, because one line used to cover both.

    ``/sessions`` printed "Sessions are in-memory only in this build"
    whatever the deployment was, and that sentence became false the day
    ``attach_sessions`` started defaulting to the app's own SQLite
    database. Asserting the two wordings *in the same test* is what makes
    the regression — one sentence standing in for two truths — impossible
    to reintroduce by editing one branch.
    """

    (tmp_path / "kept").mkdir()
    (tmp_path / "lost").mkdir()

    async def drive():
        stored = build(tmp_path / "kept", answering("unused"))
        kept = await drive_repl(stored, ["/sessions", "/exit"])
        await asyncio.wait_for(stored.aclose(), WAIT_S)

        forgetful = build(tmp_path / "lost", answering("unused"), memory=False)
        lost = await drive_repl(forgetful, ["/sessions", "/exit"])
        await asyncio.wait_for(forgetful.aclose(), WAIT_S)
        return kept, lost

    kept, lost = asyncio.run(drive())

    assert "in-memory only" not in kept
    assert "keeps them between runs" in kept
    assert "stores no conversations" in lost
    assert "keeps them between runs" not in lost


def test_sessions_lists_the_conversations_earlier_runs_left(tmp_path):
    """Not just the one being had — that is what it used to report.

    Two processes leave two conversations in one workspace database; a
    third has to be able to see both of them, or ``/resume`` has nothing
    to resume and no way to find out what there is.
    """

    async def drive():
        first = build(tmp_path, answering("one"))
        await drive_repl(first, ["hello", "/exit"], session_id="s-alpha")
        await asyncio.wait_for(first.aclose(), WAIT_S)

        second = build(tmp_path, answering("two"))
        await drive_repl(second, ["hello again", "/exit"], session_id="s-beta")
        await asyncio.wait_for(second.aclose(), WAIT_S)

        third = build(tmp_path, answering("three"))
        printed = await drive_repl(
            third, ["/sessions", "/exit"], session_id="s-gamma"
        )
        await asyncio.wait_for(third.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert "s-alpha" in printed
    assert "s-beta" in printed
    assert "2 message(s)" in printed
    assert "nothing has been saved under it yet" in printed, (
        "the conversation being had is named too, or the list reads as "
        "though the current one were missing"
    )


# ---- /resume ----------------------------------------------------------


def test_resume_continues_a_stored_conversation_rather_than_starting_one(
    tmp_path,
):
    """The whole point of ``/resume``, asserted against the database.

    The history is read back through a **third** app, so what is compared
    is what reached SQLite rather than what one registry happened to be
    holding in memory.
    """

    async def drive():
        first = build(tmp_path, answering("first answer"))
        await drive_repl(first, ["first question", "/exit"], session_id="s-old")
        await asyncio.wait_for(first.aclose(), WAIT_S)

        second = build(tmp_path, answering("second answer"))
        printed = await drive_repl(
            second, ["/resume s-old", "second question", "/exit"]
        )
        await asyncio.wait_for(second.aclose(), WAIT_S)

        reader = build(tmp_path, answering("unused"))
        stored = await asyncio.wait_for(
            reader.sessions.load_session("s-old"), WAIT_S
        )
        await asyncio.wait_for(reader.aclose(), WAIT_S)
        return printed, [message.content for message in stored.history]

    printed, history = asyncio.run(drive())

    assert "Resumed s-old: 2 message(s)." in printed
    assert history == [
        "first question",
        "first answer",
        "second question",
        "second answer",
    ]


def test_resume_takes_the_number_the_listing_printed(tmp_path):
    """The other half of "by number or by id" the prompt advertises."""

    async def drive():
        first = build(tmp_path, answering("one"))
        await drive_repl(first, ["hello", "/exit"], session_id="s-only")
        await asyncio.wait_for(first.aclose(), WAIT_S)

        second = build(tmp_path, answering("two"))
        printed = await drive_repl(second, ["/resume 1", "/current", "/exit"])
        await asyncio.wait_for(second.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert "Resumed s-only: 2 message(s)." in printed
    assert "Session s-only in" in printed


def test_resume_refuses_an_id_nothing_was_saved_under(tmp_path):
    """Switching to it anyway would silently discard the conversation.

    The person would go on talking, believing they had returned to an
    earlier thread, and the messages would land in a session that has
    never existed under a name they chose by mistake.
    """

    async def drive():
        app = build(tmp_path, answering("unused"))
        repl, _source, buffer = repl_over(app, ["/resume s-nope", "/exit"])
        before = repl.state.session_id
        await asyncio.wait_for(repl.run(), WAIT_S)
        after = repl.state.session_id
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue(), before, after

    printed, before, after = asyncio.run(drive())

    assert "No conversation s-nope." in printed
    assert before == after, "the refused resume changed the session anyway"


def test_bare_resume_lists_what_there_is_to_resume(tmp_path):
    """A picker with no argument has to show the choices."""

    async def drive():
        first = build(tmp_path, answering("one"))
        await drive_repl(first, ["hello", "/exit"], session_id="s-listed")
        await asyncio.wait_for(first.aclose(), WAIT_S)

        second = build(tmp_path, answering("two"))
        printed = await drive_repl(second, ["/resume", "/exit"])
        await asyncio.wait_for(second.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert "s-listed" in printed
    assert "/resume <id> or /resume <number>" in printed


class Choosing(ScriptedSource):
    """A scripted source that can also pick, the way the terminal source does.

    *picks* are answered in order; an exception class or instance in it is
    raised instead, which is how a picker that cannot be shown is played.
    """

    def __init__(self, lines, picks) -> None:
        super().__init__(lines)
        self.picks = list(picks)
        self.asked: list[tuple[str, list[str], int]] = []

    async def choose(self, message, options, *, default=0):
        await asyncio.sleep(0)
        self.asked.append((message, list(options), default))
        pick = self.picks.pop(0)
        if isinstance(pick, BaseException) or (
            isinstance(pick, type) and issubclass(pick, BaseException)
        ):
            raise pick
        return pick


async def _two_conversations(tmp_path) -> None:
    """``s-a`` then ``s-b``, each with one exchange, in the workspace store."""
    first = build(tmp_path, answering("answer a"))
    await drive_repl(first, ["question a", "/exit"], session_id="s-a")
    await asyncio.wait_for(first.aclose(), WAIT_S)
    second = build(tmp_path, answering("answer b"))
    await drive_repl(second, ["question b", "/exit"], session_id="s-b")
    await asyncio.wait_for(second.aclose(), WAIT_S)


def _picking(tmp_path, lines, picks, *, session_id="s-b", provider=None):
    """Drive a REPL whose source picks; return printed text, source, final id."""

    async def drive():
        await _two_conversations(tmp_path)
        app = build(tmp_path, provider or answering("answer again"))
        buffer = io.StringIO()
        source = Choosing(lines, picks)
        repl = Repl(
            app, source=source, screen=Screen.into(buffer), session_id=session_id
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        final = repl.state.session_id
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue(), source, final

    return asyncio.run(drive())


def test_bare_resume_opens_the_picker_on_the_first_other_conversation(tmp_path):
    """The current conversation is listed, so numbers match ``/sessions``,
    but the cursor starts on the one a person most likely wants."""
    printed, source, final = _picking(tmp_path, ["/resume", "/exit"], [None])

    (message, options, default), = source.asked
    assert "Esc" in message
    assert options[0].startswith("s-b  (current)")
    assert options[1].startswith("s-a  ")
    assert "question a" in options[1]
    assert default == 1
    assert "Resume cancelled." in printed
    assert final == "s-b"


def test_picking_a_conversation_resumes_it_like_resume_by_id(tmp_path):
    """Asserted against what reached SQLite, as the by-id test is."""

    async def drive():
        await _two_conversations(tmp_path)
        app = build(tmp_path, answering("answer again"))
        buffer = io.StringIO()
        source = Choosing(["/resume", "follow-up", "/exit"], [1])
        repl = Repl(app, source=source, screen=Screen.into(buffer), session_id="s-b")
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)

        reader = build(tmp_path, answering("unused"))
        stored = await asyncio.wait_for(reader.sessions.load_session("s-a"), WAIT_S)
        await asyncio.wait_for(reader.aclose(), WAIT_S)
        return buffer.getvalue(), [m.content for m in stored.history]

    printed, history = asyncio.run(drive())

    assert "Resumed s-a: 2 message(s)." in printed
    assert "you: question a" in printed
    assert "agent: answer a" in printed
    assert history == ["question a", "answer a", "follow-up", "answer again"]


def test_picking_the_current_conversation_changes_nothing(tmp_path):
    printed, _source, final = _picking(tmp_path, ["/resume", "/exit"], [0])

    assert "Already in s-b." in printed
    assert "Resumed" not in printed
    assert final == "s-b"


def test_a_closed_picker_counts_as_declining_and_the_loop_goes_on(tmp_path):
    printed, _source, final = _picking(
        tmp_path, ["/resume", "/current", "/exit"], [EOFError]
    )

    assert "Resume cancelled." in printed
    assert "Session s-b in" in printed
    assert final == "s-b"


@pytest.mark.parametrize(
    "failure", [NotImplementedError, RuntimeError("the terminal went away")]
)
def test_a_picker_that_cannot_be_shown_falls_back_to_the_list(
    tmp_path, failure, caplog
):
    """An old ``prompt_toolkit`` is expected, so it is not logged as an error;
    anything else is. Either way the REPL lists and keeps going."""
    with caplog.at_level("DEBUG", logger="omicsclaw.entry.cli._repl"):
        printed, _source, final = _picking(
            tmp_path, ["/resume", "/current", "/exit"], [failure]
        )

    assert "/resume <id> or /resume <number>" in printed
    assert "s-a" in printed
    assert "Session s-b in" in printed
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    if failure is NotImplementedError:
        assert errors == []
    else:
        assert errors, "an unexpected picker failure was not logged"


def test_the_picker_is_not_shown_when_there_is_nothing_else_to_resume(tmp_path):
    async def drive():
        empty = build(tmp_path / "empty", answering("unused"))
        buffer = io.StringIO()
        nothing = Choosing(["/resume", "/exit"], [])
        repl = Repl(empty, source=nothing, screen=Screen.into(buffer))
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(empty.aclose(), WAIT_S)

        alone = build(tmp_path / "alone", answering("unused"))
        only = Choosing(["hello", "/resume", "/exit"], [])
        repl = Repl(alone, source=only, screen=Screen.into(buffer), session_id="solo")
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(alone.aclose(), WAIT_S)
        return buffer.getvalue(), nothing.asked, only.asked

    (tmp_path / "empty").mkdir()
    (tmp_path / "alone").mkdir()
    printed, asked_empty, asked_alone = asyncio.run(drive())

    assert asked_empty == [] and asked_alone == []
    assert "No saved conversations to resume." in printed
    assert "No other conversation to resume." in printed


def test_a_source_that_cannot_pick_never_reads_the_next_line_as_a_choice(
    tmp_path,
):
    """``oc cli < script.txt``: the line after ``/resume`` is a question."""
    provider = answering("answered")

    async def drive():
        await _two_conversations(tmp_path)
        app = build(tmp_path, provider)
        printed = await drive_repl(app, ["/resume", "hello", "/exit"])
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert provider.seen[-1][-1].content == "hello"
    assert "/resume <id> or /resume <number>" in printed


def test_sessions_lists_the_conversation_used_last_first(tmp_path):
    """Created first, spoken in last: it leads the list, not the newest."""

    async def drive():
        await _two_conversations(tmp_path)
        again = build(tmp_path, answering("answer a2"))
        await drive_repl(again, ["question a2", "/exit"], session_id="s-a")
        await asyncio.wait_for(again.aclose(), WAIT_S)
        reader = build(tmp_path, answering("unused"))
        printed = await drive_repl(reader, ["/sessions", "/exit"])
        await asyncio.wait_for(reader.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert "1. s-a" in printed
    assert "2. s-b" in printed


# ---- one conversation on one line -----------------------------------------


def _session(*history, session_id="s-1"):
    from omicsclaw.entry.session import Session

    return Session(session_id=session_id, history=tuple(history), updated_at=0.0)


def test_the_preview_skips_the_summary_a_compaction_left_first():
    from omicsclaw.context import Anchors, build_compaction_message
    from omicsclaw.entry.cli._repl import _session_summary

    summary = build_compaction_message(Anchors(user_intent="ship it"), "long talk")
    row = _session_summary(
        _session(summary, Message.user("which clusters are immune?")),
        current=False,
        width=120,
    )

    assert "[Context Compaction]" not in row
    assert row.endswith("which clusters are immune?")


def test_the_preview_drops_shell_records_even_when_their_output_has_blank_lines():
    from omicsclaw.entry.cli._repl import _session_summary
    from omicsclaw.entry.cli._shell import shell_preamble

    asked = shell_preamble(["$ ls\nline one\n\nline three"]) + "what now?"
    row = _session_summary(_session(Message.user(asked)), current=False, width=120)

    assert row.endswith("what now?")
    assert "line" not in row


def test_a_wide_preview_is_cut_by_terminal_cells_not_characters():
    from rich.cells import cell_len

    from omicsclaw.entry.cli._repl import _session_summary

    question = "比较肿瘤与间质区域的差异表达基因" * 5
    row = _session_summary(_session(Message.user(question)), current=False, width=60)

    assert cell_len(row) <= 60
    assert row.endswith("…")


def test_a_narrow_terminal_cuts_the_preview_and_never_the_marker():
    from omicsclaw.entry.cli._repl import _session_summary

    row = _session_summary(
        _session(Message.user("a long question " * 10)), current=True, width=30
    )

    assert row.startswith("s-1  (current)")
    assert "question" not in row


def test_a_conversation_with_nothing_said_says_so():
    from omicsclaw.entry.cli._repl import _session_summary

    assert _session_summary(_session(), current=False, width=120).endswith(
        "(no messages)"
    )


def test_the_recap_is_the_last_exchange_and_its_text_is_not_markup():
    from omicsclaw.entry.cli._repl import _recap

    history = (
        Message.user("first"),
        Message(role=Role.ASSISTANT, content="early answer"),
        Message.user("show [red]this[/red]"),
        Message(role=Role.ASSISTANT, content="done:\n  [bold]x[/bold]"),
    )
    buffer = io.StringIO()
    screen = Screen.into(buffer)
    for line in _recap(history, width=80):
        screen.print(line)
    printed = buffer.getvalue()

    assert "you: show [red]this[/red]" in printed
    assert "agent: done: [bold]x[/bold]" in printed
    assert "first" not in printed


# ---- /compact ---------------------------------------------------------


def _bulk() -> tuple[Message, ...]:
    """A conversation big enough that compacting it plainly changes it."""
    messages: list[Message] = []
    for index in range(20):
        messages.append(Message(role=Role.USER, content=f"q{index} " + "q" * 300))
        messages.append(
            Message(role=Role.ASSISTANT, content=f"a{index} " + "a" * 300)
        )
    return tuple(messages)


def _compactable(tmp_path: pathlib.Path, provider):
    """An app whose window is small enough for a forced compaction to hold."""
    app = make_app(tmp_path, provider, tools=())
    app = dataclasses.replace(
        app,
        budget=ContextBudget(
            context_tokens=200_000,
            reserve_output_tokens=0,
            reserve_tool_tokens=0,
            safety_ratio=0.0,
        ),
        summarizer=Canned(),
    )
    app = dataclasses.replace(
        app, engine=AgentEngine(provider, app.registry, app.config.engine_config())
    )
    return attach_sessions(app)


def test_compact_asks_the_registry_to_compact_and_reports_what_it_saved(
    tmp_path, monkeypatch
):
    """``/compact`` is a compaction, not a question about compaction.

    A surface that sent the word to the model would produce a confident
    paragraph about summarizing and change nothing, and the history is
    the only place that difference shows — so the spy records *which*
    entry point was used and the assertions read the conversation
    afterwards.
    """
    seen: list[str] = []
    real_compact = SessionRegistry.compact
    real_submit = SessionRegistry.submit

    async def spy_compact(self, session_id):
        seen.append("compact")
        return await real_compact(self, session_id)

    async def spy_submit(self, session_id, text, **kwargs):
        seen.append("submit")
        return await real_submit(self, session_id, text, **kwargs)

    monkeypatch.setattr(SessionRegistry, "compact", spy_compact)
    monkeypatch.setattr(SessionRegistry, "submit", spy_submit)

    async def drive():
        app = _compactable(tmp_path, answering("unused"))
        store = SqliteSessionStore(app.memory.database)
        await asyncio.wait_for(
            store.save(StoredSession(session_id="s-big", history=_bulk())), WAIT_S
        )
        printed = await drive_repl(app, ["/compact", "/exit"], session_id="s-big")
        left = app.sessions.session("s-big").history
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return seen, printed, left

    calls, printed, left = asyncio.run(drive())

    assert calls == ["compact"], "the command went somewhere other than compact"
    assert "Compacted:" in printed
    assert "tokens" in printed and "smaller)" in printed
    assert len(left) < len(_bulk()), "the conversation was not actually compacted"


def test_compact_says_so_when_there_is_nothing_to_compact(tmp_path):
    """Silence after a command is indistinguishable from a command that
    did not run, and a short conversation is the ordinary case."""

    async def drive():
        app = build(tmp_path, answering("hi"))
        printed = await drive_repl(app, ["hello", "/compact", "/exit"])
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert "Nothing to compact" in printed


def test_compact_is_refused_while_this_conversation_is_busy(tmp_path):
    """The reference harness refuses ``/compact`` while a turn runs
    (``tui_update.go:330-349``) and the reason survives: a compaction
    queued behind an exchange rewrites a history that exchange is still
    adding to, and the report describes a conversation that moved on."""

    async def drive():
        sleeping = Sleeping()
        app = build(
            tmp_path,
            Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
            tools=(sleeping,),
        )
        buffer = io.StringIO()
        repl = Repl(
            app,
            source=ScriptedSource(()),
            screen=Screen.into(buffer),
        )
        asking = asyncio.create_task(repl.ask("hang please"))
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)

        await asyncio.wait_for(repl._dispatch("/compact"), WAIT_S)
        refusal = buffer.getvalue()

        repl.interrupt()
        await asyncio.wait_for(asking, WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return refusal

    printed = asyncio.run(drive())

    assert "This conversation is busy" in printed
    assert "Compacted:" not in printed
    assert "Nothing to compact" not in printed


# ---- /plan and /tasks -------------------------------------------------


def _three_tasks() -> Message:
    """One ``plan_write`` call writing three steps, one of them started."""
    return Message(
        role=Role.ASSISTANT,
        content="",
        tool_calls=(
            ToolCall(
                id="c1",
                name=PLAN_WRITE_TOOL_NAME,
                arguments=json.dumps(
                    {
                        "steps": [
                            {
                                "id": "1",
                                "content": "load the matrix",
                                "status": "completed",
                            },
                            {
                                "id": "2",
                                "content": "cluster the spots",
                                "status": "in_progress",
                            },
                            {
                                "id": "3",
                                "content": "call the markers",
                                "status": "pending",
                            },
                        ]
                    }
                ),
            ),
        ),
    )


def test_tasks_shows_the_plan_the_model_wrote_in_its_own_shape(tmp_path):
    """The plan was invisible here: ``plan_write`` rendered as ``<-
    plan_write ok`` like any other tool call, and nothing could show what
    it had written. ``/tasks`` reads the book — and prints a task list
    rather than the tool's JSON, which is the difference between a
    person being able to read it and a person being handed the wire
    format."""

    async def drive():
        app = attach_sessions(
            make_app(
                tmp_path,
                Scripted(
                    _three_tasks(), Message(role=Role.ASSISTANT, content="planned")
                ),
            )
        )
        printed = await drive_repl(app, ["plan this", "/tasks", "/exit"])
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert "Tasks" in printed and "1/3 done" in printed and "1 active" in printed
    for content in ("load the matrix", "cluster the spots", "call the markers"):
        assert content in printed
    for status in ("completed", "in_progress", "pending"):
        assert f"[{status}]" in printed
    assert '"status": "in_progress"' not in printed, (
        "this is the tool's JSON, not a task list"
    )


def test_plan_shows_the_same_thing_tasks_does(tmp_path):
    """Two names for one read-only view; a ``/plan`` that showed
    something else would be a second, disagreeing answer."""

    async def drive():
        app = attach_sessions(
            make_app(
                tmp_path,
                Scripted(
                    _three_tasks(), Message(role=Role.ASSISTANT, content="planned")
                ),
            )
        )
        printed = await drive_repl(app, ["plan this", "/plan", "/exit"])
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert "cluster the spots" in printed
    assert "[in_progress]" in printed


def test_tasks_on_a_session_with_no_plan_says_so(tmp_path):
    """An empty state, not an exception and not a blank line."""

    async def drive():
        app = attach_sessions(make_app(tmp_path, answering("unused")))
        printed = await drive_repl(app, ["/tasks", "/exit"])
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return printed

    printed = asyncio.run(drive())

    assert "No tasks yet" in printed


def test_the_three_plan_control_commands_are_still_refused(tmp_path):
    """Read-only is the decision, not a stage on the way to a control panel.

    ``/approve-plan``, ``/resume-task`` and ``/do-current-task`` are in
    the catalogue and stay unimplemented: the agent decides when to plan
    and when to move on, and a person driving that from the side would be
    a second answer to the same question. Naming them here is what makes
    a later "while we are in there" addition a red test rather than a
    quiet expansion of scope.
    """

    async def drive():
        provider = answering("unused")
        app = attach_sessions(make_app(tmp_path, provider, tools=()))
        printed = await drive_repl(
            app,
            ["/approve-plan", "/resume-task 2", "/do-current-task", "/exit"],
        )
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return provider.calls, printed

    calls, printed = asyncio.run(drive())

    assert calls == 0
    for name in ("/approve-plan", "/resume-task", "/do-current-task"):
        assert f"{name} is not available in this build." in printed
