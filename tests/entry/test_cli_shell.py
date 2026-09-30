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
import contextlib
import os
import pathlib
import signal
import time
from asyncio import base_subprocess

import pytest

from omicsclaw.entry.cli import PROMPT
from omicsclaw.entry.cli import _shell
from omicsclaw.entry.cli._shell import CONTEXT_LIMIT, DISPLAY_LIMIT, run_shell
from omicsclaw.launch._surfaces import _interrupts
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


# ---- Ctrl-C while a command runs ----------------------------------------

needs_proc = pytest.mark.skipif(
    not os.path.isdir("/proc"), reason="reads process groups from /proc"
)


def _group(pgid: int) -> dict[int, str]:
    """The live members of process group *pgid*, pid to command name.

    Read from ``/proc`` rather than asked with ``os.killpg(pgid, 0)``,
    which a killed but not yet reaped member — a zombie — answers as
    though it were alive.
    """
    members: dict[int, str] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8", errors="replace") as f:
                stat = f.read()
        except OSError:
            continue
        name = stat[stat.find("(") + 1 : stat.rfind(")")]
        state, _parent, group = stat[stat.rfind(")") + 2 :].split()[:3]
        if int(group) == pgid and state != "Z":
            members[int(entry)] = name
    return members


async def _until(condition, what: str) -> None:
    """Wait for *condition* to hold, and fail by name if it never does."""
    deadline = time.monotonic() + WAIT_S
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"never happened: {what}")
        await asyncio.sleep(0.02)


def _leader(recorded: pathlib.Path) -> int | None:
    """The pid the command wrote into *recorded*, once it has."""
    try:
        text = recorded.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


async def _emptied(pgid: int) -> bool:
    """Whether the group empties within two seconds of a kill.

    Awaited on the loop that ran the command, so that the loop also sees
    the child exit and closes its transport before the test ends.
    """
    deadline = time.monotonic() + 2.0
    while _group(pgid):
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)
    return True


@needs_proc
def test_ctrl_c_during_a_shell_command_stops_the_command_and_not_the_repl(
    tmp_path,
):
    """``Ctrl-C`` while ``!sleep 20`` ran used to end ``oc cli`` with 130.

    The terminal's SIGINT lands in the entry point's handler, which asks
    :meth:`Repl.interrupt` whether there was anything to cancel and quits
    the loop when there was not. Only an exchange used to count, so a
    command a person typed was not "something running", and the key that
    means "stop this" meant "stop everything" — while the command itself,
    in a session of its own that the terminal's signal never reaches,
    went on running after the REPL had gone.

    Driven through that handler rather than through ``interrupt()``
    alone, because the handler's reading of the answer is where the
    process ended. Held here: the loop is not cancelled; the command's
    whole group is killed; the screen and the model's record both say
    it was interrupted; and the next line is read and answered.
    """
    recorded = tmp_path / "pgid"

    async def drive():
        provider = answering("noted")
        app = build(tmp_path, provider)
        repl, source, buffer = repl_over(
            app,
            [f"!echo $$ > {recorded}; sleep 20 | cat", "what was that?", "/exit"],
        )
        loop = asyncio.create_task(repl.run())
        await _until(lambda: _leader(recorded) is not None, "the command started")
        pgid = _leader(recorded)
        await _until(lambda: "sleep" in _group(pgid).values(), "sleep started")
        started = time.monotonic()
        _interrupts(repl, loop)._fire()
        await asyncio.wait({loop}, timeout=WAIT_S)
        elapsed = time.monotonic() - started
        ended_the_repl = loop.cancelled()
        emptied = await _emptied(pgid)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return (
            pgid,
            ended_the_repl,
            emptied,
            elapsed,
            source.prompts,
            buffer.getvalue(),
            provider.seen[0][-1].content if provider.seen else "",
        )

    pgid, ended_the_repl, emptied, elapsed, prompts, printed, sent = asyncio.run(
        drive()
    )

    assert not ended_the_repl, "Ctrl-C during a ! command ended the REPL"
    assert emptied, f"left running after Ctrl-C: {_group(pgid)}"
    assert elapsed < 5.0, f"the command was not stopped ({elapsed:.1f}s)"
    assert "✗ interrupted after" in printed
    assert prompts == [PROMPT, PROMPT, PROMPT], "the loop went back to the prompt"
    assert "noted" in printed, "the next line was answered"
    assert f"$ echo $$ > {recorded}; sleep 20 | cat (interrupted after " in sent
    assert sent.endswith("what was that?")


@needs_proc
def test_cancelling_the_repl_during_a_shell_command_still_cancels_it(tmp_path):
    """An interrupted command is a cancelled *child*, not a cancelled REPL.

    The two arrive as the same exception at the same ``await``. Treating
    the REPL's own cancellation — shutdown, the second ``Ctrl-C`` at an
    idle prompt, a supervisor — as "the command was interrupted" would
    swallow it and go back to the prompt, so a REPL asked to stop would
    keep reading lines. It must stop, and the command must die with it.
    """
    recorded = tmp_path / "pgid"

    async def drive():
        app = build(tmp_path, answering("unused"))
        repl, source, buffer = repl_over(
            app, [f"!echo $$ > {recorded}; sleep 20", "/exit"]
        )
        loop = asyncio.create_task(repl.run())
        await _until(lambda: _leader(recorded) is not None, "the command started")
        pgid = _leader(recorded)
        await _until(lambda: "sleep" in _group(pgid).values(), "sleep started")
        loop.cancel()
        await asyncio.wait({loop}, timeout=WAIT_S)
        emptied = await _emptied(pgid)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return pgid, loop.cancelled(), emptied, source.prompts, buffer.getvalue()

    pgid, cancelled, emptied, prompts, printed = asyncio.run(drive())

    assert cancelled, "the REPL's own cancellation was swallowed"
    assert prompts == [PROMPT], "the loop asked for another line"
    assert "interrupted" not in printed
    assert emptied, f"left running after the REPL stopped: {_group(pgid)}"


@needs_proc
@pytest.mark.parametrize(
    "command",
    [
        "sleep 30 | cat",
        # The shell exits at once and is reaped; the background job keeps
        # the group — and the output pipe — alive without it.
        "sleep 30 & echo started",
    ],
)
def test_a_cancelled_command_takes_its_whole_process_group_with_it(
    tmp_path, command
):
    """Cancelling :func:`run_shell` kills the group, not only ``bash``.

    The command runs in a session of its own, so the terminal's SIGINT
    never reaches it, and cancelling the Task that awaits it only closes
    asyncio's transport — which kills ``bash`` and nothing else. Without
    an explicit kill on that path, ``sleep 30 | cat`` outlives the
    ``Ctrl-C`` that was meant to stop it.

    The second command is the case where ``bash`` is already gone: the
    group has to be addressed by the id it was created with, because
    asking the reaped leader for its group finds nothing.
    """
    recorded = tmp_path / "pgid"

    async def drive():
        running = asyncio.create_task(
            run_shell(f"echo $$ > {recorded}; {command}", cwd=tmp_path)
        )
        await _until(lambda: _leader(recorded) is not None, "the command started")
        pgid = _leader(recorded)
        await _until(lambda: "sleep" in _group(pgid).values(), "sleep started")
        running.cancel()
        await asyncio.wait({running}, timeout=WAIT_S)
        return pgid, running.cancelled(), await _emptied(pgid)

    pgid, cancelled, emptied = asyncio.run(drive())

    assert cancelled, "the cancellation was not passed on to the caller"
    assert emptied, f"outlived the cancellation: {_group(pgid)}"


def _hold_the_transport(monkeypatch) -> asyncio.Event:
    """Hold every subprocess transport before it connects, until released.

    The child has been exec-ed by then and runs on; only
    ``create_subprocess_exec`` is kept from returning.
    """
    release = asyncio.Event()
    connect = base_subprocess.BaseSubprocessTransport._connect_pipes

    async def held(self, waiter):
        await release.wait()
        return await connect(self, waiter)

    monkeypatch.setattr(
        base_subprocess.BaseSubprocessTransport, "_connect_pipes", held
    )
    return release


@needs_proc
def test_a_command_cancelled_while_its_shell_is_still_starting_loses_its_group(
    tmp_path, monkeypatch
):
    """The test above, with the cancellation landing inside the spawn.

    ``create_subprocess_exec`` returns only once the transport has
    connected its pipe, and ``bash`` has been running since before that.
    Cancelled in between, asyncio's own cleanup closes the transport, which
    SIGKILLs ``bash`` alone, and ``run_shell``'s handler never sees the
    exception, so ``sleep 30 | cat`` ran on — and, still holding the pipe,
    kept asyncio's cleanup waiting, so the cancellation itself did not
    return until ``sleep`` ended. This is what made the test above fail
    under load, two runs out of two at twice CPU oversubscription; here the
    transport is held so the window is certain.
    """
    release = _hold_the_transport(monkeypatch)
    recorded = tmp_path / "pgid"
    shell_left: list[bool] = []

    async def command() -> None:
        try:
            await run_shell(f"echo $$ > {recorded}; sleep 30 | cat", cwd=tmp_path)
        except asyncio.CancelledError:
            shell_left.append(os.path.exists(f"/proc/{_leader(recorded)}"))
            raise

    async def drive():
        running = asyncio.create_task(command())
        await _until(lambda: _leader(recorded) is not None, "the command started")
        pgid = _leader(recorded)
        await _until(lambda: "sleep" in _group(pgid).values(), "sleep started")
        running.cancel()
        await asyncio.sleep(0)  # the cancellation lands while the transport is held
        release.set()
        await asyncio.wait({running}, timeout=WAIT_S)
        return pgid, running.cancelled(), await _emptied(pgid)

    try:
        pgid, cancelled, emptied = asyncio.run(drive())

        assert emptied, f"outlived a cancellation during the spawn: {_group(pgid)}"
        assert cancelled, "the cancellation was not passed on to the caller"
        assert shell_left == [False], "bash was not reaped first"
    finally:
        if (pgid := _leader(recorded)) is not None and _group(pgid):
            with contextlib.suppress(OSError):
                os.killpg(pgid, signal.SIGKILL)


@needs_proc
def test_a_timed_out_command_whose_shell_has_exited_is_still_killed(tmp_path):
    """The timeout's kill reaches a group whose leader is already reaped.

    ``bash -c 'sleep 30 & echo started'`` exits at once and the
    background ``sleep`` keeps the output pipe open. Looking the group up
    through the reaped shell's pid found nothing, so the kill fell back
    to the shell alone, and collecting the output afterwards waited the
    full thirty seconds for a process that was supposed to be dead: the
    one bound this module promises did not hold.
    """
    recorded = tmp_path / "pgid"

    async def drive():
        started = time.monotonic()
        result = await asyncio.wait_for(
            run_shell(
                f"echo $$ > {recorded}; sleep 30 & echo started",
                cwd=tmp_path,
                timeout_s=0.3,
            ),
            WAIT_S,
        )
        elapsed = time.monotonic() - started
        return result, elapsed, await _emptied(_leader(recorded))

    result, elapsed, emptied = asyncio.run(drive())

    assert result.timed_out
    assert elapsed < 3.0, f"the timeout did not bound the command ({elapsed:.1f}s)"
    assert emptied, "the background job survived the timeout"


def test_a_timed_out_command_keeps_what_it_printed_before_the_kill(tmp_path):
    """A command killed at the deadline has usually printed the very lines
    that say why it hung; a result with empty output after sixty seconds
    of waiting leaves the person nothing to go on. The output used to be
    collected by ``communicate()``, whose buffer the timeout cancelled and
    dropped, so only bytes still in the pipe after the kill survived."""

    async def drive():
        return await asyncio.wait_for(
            run_shell(
                "echo before-the-deadline; sleep 30", cwd=tmp_path, timeout_s=0.5
            ),
            WAIT_S,
        )

    result = asyncio.run(drive())

    assert result.timed_out and result.failed
    assert result.output == "before-the-deadline\n"


def test_what_was_still_in_the_pipe_at_the_kill_is_read_after_it(
    tmp_path, monkeypatch
):
    """Bytes the reader had not reached when the deadline fired.

    The loop stalls — a slow synchronous callback, a starved CPU — and
    during the stall the command writes and the deadline passes. When the
    loop resumes, the timeout cancels the reader before the new bytes have
    been handed to it, so they are still waiting when the command is
    killed, and only the drain after the kill reads them. Without it the
    result is empty, and the line that says why the command hung is lost.

    The stall is made by blocking the loop from this test, and only once
    the reader is running, so the deadline cannot pass before the command
    has written. The spy on ``_collect`` only records when reading began.
    """
    go = tmp_path / "go"
    written = tmp_path / "written"
    reading: list[float] = []
    collect = _shell._collect

    async def spy(process, into):
        reading.append(time.monotonic())
        return await collect(process, into)

    monkeypatch.setattr(_shell, "_collect", spy)
    timeout_s = 0.3

    async def drive():
        running = asyncio.create_task(
            run_shell(
                f"until [ -e {go} ]; do sleep 0.01; done; "
                f"printf left-in-the-pipe; touch {written}; exec sleep 30",
                cwd=tmp_path,
                timeout_s=timeout_s,
            )
        )
        await _until(lambda: bool(reading), "the output is being read")
        go.touch()
        give_up = time.monotonic() + WAIT_S
        while not written.exists() or time.monotonic() < reading[0] + timeout_s + 0.1:
            if time.monotonic() > give_up:
                raise AssertionError("never happened: the command wrote")
            time.sleep(0.01)  # blocks the loop: nothing reads the pipe meanwhile
        return await asyncio.wait_for(running, WAIT_S)

    result = asyncio.run(drive())

    assert result.timed_out
    assert result.output == "left-in-the-pipe"


def test_the_screen_and_the_model_see_the_partial_output_of_a_killed_command(
    tmp_path,
):
    async def drive():
        provider = _two_answers()
        app = build(tmp_path, provider)
        repl, _source, buffer = repl_over(
            app,
            ["!echo partial-line; sleep 30", "what happened?", "/exit"],
            shell_timeout_s=0.3,
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return provider.seen, buffer.getvalue()

    seen, printed = asyncio.run(drive())

    assert "partial-line" in printed and "killed after" in printed
    question = seen[0][-1].content
    assert "partial-line" in question and "timed out" in question
