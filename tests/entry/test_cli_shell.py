"""``!cmd`` — the operator's own shell, driven through the whole REPL.

Real ``bash`` child processes, a real workspace and the real scripted
backend, because every one of the five properties below is about a seam:
what the *screen* got versus what the *model* got, what ran versus what
was sent to the model, and what happens to a command that never returns.

No ``pytest-asyncio`` here, so every test drives :func:`asyncio.run`
itself and **bounds every await with :func:`asyncio.wait_for`** — which
in this file is not a formality: the timeout test's whole subject is a
command that would otherwise hang the session, and a hang with no
timeout plugin is a test run that never finishes.
"""

from __future__ import annotations

import asyncio
import os
import time

from omicsclaw.entry.cli import PROMPT
from omicsclaw.entry.cli._shell import CONTEXT_LIMIT, DISPLAY_LIMIT
from omicsclaw.schema import Message, Role
from tests.entry.test_cli_repl import (  # type: ignore[import-not-found]
    WAIT_S,
    answering,
    build,
    repl_over,
)
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
)


def _two_answers() -> Scripted:
    return Scripted(
        Message(role=Role.ASSISTANT, content="answer one"),
        Message(role=Role.ASSISTANT, content="answer two"),
    )


def test_a_shell_command_runs_here_and_never_reaches_the_model(tmp_path):
    """``!echo hi`` is a command, not a question about a command.

    ``calls == 0`` is the assertion that separates the two: a surface
    that did not intercept ``!`` would send the line to the model, which
    would answer it confidently and run nothing.
    """

    async def drive():
        provider = answering("should not be reached")
        app = build(tmp_path, provider)
        repl, _source, buffer = repl_over(app, ["!echo hi", "/exit"])
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return provider.calls, buffer.getvalue()

    calls, printed = asyncio.run(drive())

    assert calls == 0
    assert "$ echo hi" in printed
    assert "hi" in printed
    assert "✓ done" in printed


def test_a_failing_command_shows_its_error_and_says_it_failed(tmp_path):
    """stderr is merged into stdout, so a message on it is still visible;
    without the status line an empty stdout and a failure read alike."""

    async def drive():
        app = build(tmp_path, answering("unused"))
        repl, _source, buffer = repl_over(
            app, ["!echo boom >&2; exit 3", "/exit"]
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "boom" in printed
    assert "non-zero exit" in printed


def test_a_bare_bang_does_nothing_and_says_nothing(tmp_path):
    """There is no command to complain about, and a complaint would be
    one more line between the person and their prompt."""

    async def drive():
        provider = answering("should not be reached")
        app = build(tmp_path, provider)
        repl, source, buffer = repl_over(app, ["!", "!   ", "/exit"])
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return provider.calls, source.prompts, buffer.getvalue()

    calls, prompts, printed = asyncio.run(drive())

    assert calls == 0
    assert "$" not in printed
    assert prompts == [PROMPT, PROMPT, PROMPT], "the prompt came straight back"


def test_the_screen_and_the_model_get_different_amounts_of_the_output(
    tmp_path,
):
    """Two ceilings, and the test reads both ends at once.

    A terminal's limit is attention and a prompt's is tokens, so one
    number cannot serve both — and a single truncation applied in one
    place would pass every assertion about *either* end on its own. The
    comparison between the two is the whole test.
    """

    async def drive():
        provider = answering("noted")
        app = build(tmp_path, provider)
        repl, _source, buffer = repl_over(
            app, ["!printf 'z%.0s' {1..6000}", "what was that?", "/exit"]
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue(), provider.seen[0][-1].content

    printed, sent = asyncio.run(drive())

    on_screen, to_model = printed.count("z"), sent.count("z")

    assert "…(truncated)" in printed, "the screen said it had cut something"
    assert "…(truncated)" in sent, "so did the copy the model was given"
    assert on_screen > to_model, (
        f"one ceiling served both ends: {on_screen} on screen, "
        f"{to_model} to the model"
    )
    assert to_model <= CONTEXT_LIMIT
    assert CONTEXT_LIMIT < on_screen <= DISPLAY_LIMIT


def test_the_record_reaches_the_next_question_and_only_that_one(tmp_path):
    """The mistake this feature is easiest to make.

    Injecting on every later prompt spends the budget again and, worse,
    reads to the model as the person having run the command again — so
    the second question's prompt is asserted to be *clean*, not merely to
    contain the new text.
    """

    async def drive():
        provider = _two_answers()
        app = build(tmp_path, provider)
        repl, _source, _buffer = repl_over(
            app, ["!echo marker-line", "first", "second", "/exit"]
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return provider.seen[0][-1].content, provider.seen[1][-1].content

    first, second = asyncio.run(drive())

    assert "$ echo marker-line" in first
    assert "marker-line" in first
    assert "first" in first
    assert second == "second"
    assert "marker-line" not in second


def test_a_command_that_never_returns_is_killed_and_the_prompt_comes_back(
    tmp_path,
):
    """The one hard safety property, and the reason the name list is only
    a courtesy.

    ``cat`` on a FIFO nobody writes to blocks in ``open(2)`` for ever and
    is **not** in :data:`~omicsclaw.entry.cli._shell.NEEDS_A_TERMINAL`, so
    what is under test is the timeout rather than the list. The cost of a
    miss has to be N seconds and a message; the alternative — a REPL
    waiting for a process that will not end — is the class of defect this
    surface was last repaired for.
    """
    waits = tmp_path / "waits"
    os.mkfifo(waits)

    async def drive():
        provider = answering("unused")
        app = build(tmp_path, provider)
        repl, source, buffer = repl_over(
            app, [f"!cat {waits}", "/exit"], shell_timeout_s=0.3
        )
        started = time.monotonic()
        await asyncio.wait_for(repl.run(), WAIT_S)
        elapsed = time.monotonic() - started
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return elapsed, source.prompts, buffer.getvalue()

    elapsed, prompts, printed = asyncio.run(drive())

    assert "killed after" in printed
    assert prompts == [PROMPT, PROMPT], "the loop went back to the prompt"
    assert elapsed < 3.0, f"the timeout did not bound the command ({elapsed:.1f}s)"


def test_nothing_the_command_started_outlives_the_kill(tmp_path):
    """The kill goes to the process **group**, not to ``bash`` alone.

    ``!`` runs a shell, and a shell's whole point is starting other
    programs. Killing only the direct child leaves everything behind it
    running, reparented and unreachable — the timeout would then report
    a bounded command while a background job carried on writing to the
    workspace.

    The command below backgrounds a subshell that creates *survivor*
    after the deadline has already passed, so the file is the observable:
    it exists only if something outlived the kill. Written as a file
    rather than as a liveness check on a pid because an orphan that is
    killed but not yet reaped is a zombie, and a zombie answers
    ``os.kill(pid, 0)`` as though it were alive.
    """
    survivor = tmp_path / "outlived-the-kill"

    async def drive():
        app = build(tmp_path, answering("unused"))
        repl, _source, buffer = repl_over(
            app,
            [f"!(sleep 1; touch {survivor}) & wait", "/exit"],
            shell_timeout_s=0.3,
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "killed after" in printed, "the command was supposed to time out"
    time.sleep(2.0)  # well past the moment the background job would fire
    assert not survivor.exists(), (
        "a process the command started survived the timeout; the kill "
        "reached bash but not the group it leads"
    )


def test_a_command_that_wants_a_terminal_is_turned_away_with_a_reason(
    tmp_path,
):
    """A courtesy, not a boundary: sixty seconds of nothing followed by
    "killed" is a worse answer than "open another window" when the answer
    is knowable up front."""

    async def drive():
        app = build(tmp_path, answering("unused"))
        repl, _source, buffer = repl_over(app, ["!vim notes.txt", "/exit"])
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "$ vim notes.txt" in printed
    assert "wants a terminal of its own" in printed
    assert "✓ done" not in printed, "it was reported as having run"


def test_the_shell_runs_in_the_workspace(tmp_path):
    """Where the agent works, which is what makes ``!ls`` about the data
    the conversation is about rather than about wherever ``oc`` started."""
    (tmp_path / "only-here.txt").write_text("x", encoding="utf-8")

    async def drive():
        app = build(tmp_path, answering("unused"))
        repl, _source, buffer = repl_over(app, ["!ls", "/exit"])
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    assert "only-here.txt" in asyncio.run(drive())
