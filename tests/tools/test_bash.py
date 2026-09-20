"""Contract tests for ``omicsclaw.tools.builtin.bash`` (plan 0029 task C).

Three of these tests are here because the behaviour they pin is invisible
to every other test in the suite, which is the same thing as saying a
future "simplification" would pass:

* ``test_a_backgrounded_command_returns_in_milliseconds`` is the only
  thing standing between this tool and ``stdout=PIPE`` (plan 0029 Q5 /
  trap 13). Swapping the temporary file back for a pipe changes nothing
  any other test can see, and hangs the tool for the whole of its budget
  on ``cmd &``.
* ``test_every_literal_carried_over_is_the_one_the_reference_uses`` names
  16,000, 5,333, 10,667 and 45 outright. Task B found five false greens of
  the shape "``len(body) == MAX``" — a behaviour assertion written as an
  equation moves with the constant and survives its mutation — so the
  borrowed numbers get one test that cannot move with them.
* ``test_the_default_budget_leaves_room_inside_the_engines`` is the only
  enforcement of a coupling the production module is forbidden to see.
  ``omicsclaw/tools/`` may not import
  :class:`~omicsclaw.engine.config.EngineConfig`; a test file may, because
  the layering guard walks ``omicsclaw/tools/`` and nothing else.

**These tests really fork processes.** Every one of them either waits for
a short command or kills what it started, and the two that background
something record the child's pid and kill it in a ``finally``. A test that
leaves a subprocess behind does not fail — it fails something later.

**The layering rule does not apply to this file**, for the reason
``test_read.py`` and ``test_write.py`` record.
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import signal
import tempfile
import time
from pathlib import Path
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.executor import execute_tool_calls
from omicsclaw.schema import ToolCall, ToolResult
from omicsclaw.tools import (
    ApprovalDecision,
    ApprovalDenied,
    ApprovalMode,
    ApprovalRequest,
    ApprovalUnavailable,
    ProgressUpdate,
    RiskLevel,
    Tool,
    ToolPolicy,
    ToolRegistry,
)
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.builtin.bash import (
    BASH_SCHEMA,
    DEFAULT_TIMEOUT,
    ENGINE_TIMEOUT_MARGIN,
    HEAD_CHARS,
    MAX_OUTPUT_CHARS,
    TAIL_CHARS,
    TOOL_NAME,
    BashEnvironment,
    BashTool,
    CommandOutcome,
    _exit_status,
    _report,
)
from omicsclaw.tools.context import use_tool_context
from omicsclaw.tools.function_tool import ToolArgumentError

_T = TypeVar("_T")

_DEADLINE = 20.0
"""Outer deadline for one test's coroutine. Generous, because several of
these wait on a real process, and a wrong answer is worth more than a fast
one — but finite, because a hung subprocess must fail rather than stall
the suite."""


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; the suite drives this way."""
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


def _args(**kwargs: Any) -> str:
    return json.dumps(kwargs)


def _yes(seen: list[ApprovalRequest] | None = None):
    """An approval channel that agrees, and optionally keeps the receipts."""

    def channel(request: ApprovalRequest) -> ApprovalDecision:
        if seen is not None:
            seen.append(request)
        return ApprovalDecision(approved=True)

    return channel


def _no(reason: str = "not this time"):
    def channel(request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(approved=False, reason=reason)

    return channel


def _bash(
    workspace: Workspace,
    *,
    approve: Any = None,
    tool: BashTool | None = None,
    **kwargs: Any,
) -> str:
    target = tool if tool is not None else BashTool(workspace)
    with use_tool_context(approval=approve if approve is not None else _yes()):
        return _run(target.execute(_args(**kwargs)))


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path)


def _emit(tmp_path: Path, body: str) -> str:
    """A command whose output is exactly ``body``.

    Written to a file and ``cat``-ed rather than generated in the shell, so
    a truncation test asserts against bytes it chose rather than against
    whatever ``seq`` happened to print.
    """
    blob = tmp_path / "blob.txt"
    blob.write_text(body, encoding="utf-8")
    return f"cat {blob}"


def _halves(result: str) -> tuple[str, str]:
    """The kept head and kept tail either side of the elision marker."""
    head, marker, rest = result.partition("\n\n...[Output too long")
    assert marker, "the output was not truncated at all"
    _, closer, tail = rest.partition("]...\n\n")
    assert closer, "the elision marker was not closed"
    return head, tail


def _reap(pidfile: Path) -> None:
    """Kill whatever a test backgrounded, tolerating one already gone."""
    try:
        pid = int(pidfile.read_text().strip())
    except (OSError, ValueError):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


# ---- the ordinary job ----------------------------------------------------


def test_a_command_runs_and_its_output_comes_back(tmp_path):
    assert _bash(_workspace(tmp_path), command="echo hello") == "hello\n"


def test_stdout_and_stderr_arrive_merged_in_the_order_they_were_written(
    tmp_path,
):
    """``bash.go:91`` promises the merge, and a model debugging a build
    needs the interleaving: an error line belongs beside the step that
    produced it, not in a second block."""
    result = _bash(
        _workspace(tmp_path),
        command="echo out; echo err 1>&2; echo after",
    )

    assert result == "out\nerr\nafter\n"


def test_a_successful_command_with_no_output_says_so_in_words(tmp_path):
    """``bash.go:147-148, 193-194``. An empty Observation reads as a tool
    that did not run, and a model's next move after that is to run it
    again."""
    result = _bash(_workspace(tmp_path), command="true")

    assert result == "The command finished successfully with no terminal output."


def test_the_working_directory_is_the_workspace_root(tmp_path):
    workspace = _workspace(tmp_path)

    assert _bash(workspace, command="pwd").strip() == str(workspace.root)


def test_a_relative_path_in_a_command_lands_in_the_workspace(tmp_path):
    """The positive half of "the cwd is the workspace": a command that
    creates a file creates it *there*, not in the process's own cwd."""
    _bash(_workspace(tmp_path), command="echo saved > made-here.txt")

    assert (tmp_path / "made-here.txt").read_text() == "saved\n"


def test_a_command_reading_stdin_sees_end_of_file_rather_than_blocking(
    tmp_path,
):
    """A deliberate departure from ``bash.go:174-177``, which leaves stdin
    inherited. Inherited, ``cat`` blocks until the deadline — and on the
    CLI Surface the inherited descriptor is the user's terminal, so the
    subprocess would be competing with the human for their keystrokes.

    **A real pipe is installed on descriptor 0 for the duration**, and
    that is what makes this test able to tell the two apart. Under pytest
    the inherited descriptor is already closed or empty, so a plain
    ``cat`` finishes either way and removing ``stdin=DEVNULL`` survives the
    mutation — which is how this version came to exist. Holding the write
    end open gives the inherited case something to block on.
    """
    read_fd, write_fd = os.pipe()
    saved = os.dup(0)
    try:
        os.dup2(read_fd, 0)
        result = _bash(
            _workspace(tmp_path),
            tool=BashTool(_workspace(tmp_path), timeout=2.0),
            command="cat",
        )
    finally:
        os.dup2(saved, 0)
        for descriptor in (saved, read_fd, write_fd):
            os.close(descriptor)

    assert "[TIMEOUT" not in result
    assert result == "The command finished successfully with no terminal output."


# ---- the borrowed numbers ------------------------------------------------


def test_every_literal_carried_over_is_the_one_the_reference_uses():
    """Plan 0029 §10-8, pinned where it cannot follow the code.

    **This test exists because of the mutation class that survives without
    it.** The truncation tests below compare against ``HEAD_CHARS`` and
    ``TAIL_CHARS``, so changing ``MAX_OUTPUT_CHARS`` moves both sides of
    every one of those assertions and the suite stays green. A borrowed
    number needs one assertion that names it.
    """
    assert MAX_OUTPUT_CHARS == 16_000  # bash.go:23
    assert HEAD_CHARS == 5_333  # bash.go:216, maxOutputLen / 3
    assert TAIL_CHARS == 10_667  # bash.go:217, the remaining two thirds
    assert HEAD_CHARS + TAIL_CHARS == MAX_OUTPUT_CHARS
    assert TAIL_CHARS > HEAD_CHARS, "the tail is the half worth keeping"

    # Derived rather than borrowed: 120s is bash.go:29 and would be
    # unreachable under EngineConfig.tool_timeout. See DEFAULT_TIMEOUT.
    assert DEFAULT_TIMEOUT == 45.0
    assert ENGINE_TIMEOUT_MARGIN == 15.0


# ---- truncation (plan 0029 Q3, trap 14) ----------------------------------


def test_output_at_the_ceiling_is_returned_whole(tmp_path):
    """The positive control. A rule that truncates everything passes every
    truncation test ever written (plan 0029 §10-9)."""
    body = "x" * MAX_OUTPUT_CHARS

    result = _bash(_workspace(tmp_path), command=_emit(tmp_path, body))

    assert result == body


def test_an_over_long_output_keeps_the_summary_printed_at_its_end(tmp_path):
    """Plan 0029 trap 14, and the reason is ``bash.go:205-210``'s.

    A test runner prints progress first and its verdict last. The
    implementation the reference replaced kept only the head and cut off
    exactly the part worth reading, so this is the mutation to aim at:
    make :func:`_truncate` keep ``output[:MAX_OUTPUT_CHARS]`` and this
    test is the one that goes red.
    """
    body = "collecting ...\n" * 3_000 + "FAILED test_x.py::test_y\n=== 3 failed ===\n"
    assert len(body) > MAX_OUTPUT_CHARS

    result = _bash(_workspace(tmp_path), command=_emit(tmp_path, body))

    assert "=== 3 failed ===" in result
    assert "FAILED test_x.py::test_y" in result
    assert result.endswith("=== 3 failed ===\n")


def test_an_over_long_output_keeps_its_beginning_too(tmp_path):
    """The other half: a head-less implementation loses the command the
    build actually ran, which is where a wrong flag shows up."""
    body = "configure: --prefix=/opt\n" + ("step\n" * 5_000)
    assert len(body) > MAX_OUTPUT_CHARS

    result = _bash(_workspace(tmp_path), command=_emit(tmp_path, body))

    assert result.startswith("configure: --prefix=/opt\n")


def test_the_kept_halves_are_exactly_one_third_and_two_thirds(tmp_path):
    """The ratio itself, with the counts written down rather than derived.

    ``len(head) == HEAD_CHARS`` would be an equation both of whose sides
    move when the constant does — the false-green shape task B found five
    of — so the numbers here are literals.
    """
    body = "".join(f"line {index}\n" for index in range(6_000))
    assert len(body) > MAX_OUTPUT_CHARS

    result = _bash(_workspace(tmp_path), command=_emit(tmp_path, body))
    head, tail = _halves(result)

    assert len(head) == 5_333
    assert len(tail) == 10_667
    assert head == body[:5_333]
    assert tail == body[-10_667:]


def test_the_elision_marker_says_how_much_went_missing(tmp_path):
    body = "z" * 20_000

    result = _bash(_workspace(tmp_path), command=_emit(tmp_path, body))

    assert f"{20_000 - 16_000} characters from the middle were cut" in result


def test_truncation_counts_characters_and_not_bytes(tmp_path):
    """Plan 0029 Q3 leaves the unit to this task; this is the decision.

    10,000 CJK characters are 30,000 bytes and 10,000 characters. Counted
    in bytes — the reference's unit, because a Go ``string`` is bytes —
    this would be cut; counted in characters it comes back whole.

    The unit is not a preference. Slicing bytes is what makes a character
    splittable, and repairing that is what ``bash.go:224-238``'s two
    rune-trimming helpers are for. Decoding once and slicing a
    :class:`str` makes both the defect and its repair unspellable, which
    is plan 0029 trap 15's requirement rather than an aesthetic.
    """
    body = "数" * 10_000
    assert len(body) == 10_000
    assert len(body.encode("utf-8")) == 30_000

    result = _bash(_workspace(tmp_path), command=_emit(tmp_path, body))

    assert result == body


def test_a_truncated_multibyte_output_never_loses_half_a_character(tmp_path):
    body = "数" * 20_000

    result = _bash(_workspace(tmp_path), command=_emit(tmp_path, body))
    head, tail = _halves(result)

    assert "�" not in result
    assert head == "数" * 5_333
    assert tail == "数" * 10_667


# ---- no pipe (plan 0029 Q5, trap 13) -------------------------------------


def test_a_backgrounded_command_returns_in_milliseconds(tmp_path):
    """Plan 0029 trap 13, and the whole reason the capture is a file.

    ``bash.go:153-165`` measured this: with a pipe, ``Wait()`` waits for
    every holder of the write end to close it, a backgrounded grandchild
    holds one, and the call blocks for the full budget. Measured in Go:
    20 s of hanging became ~5 ms. Re-measured here before this tool was
    written, with ``bash -c 'echo hi && sleep 30 &'`` — ``stdout=PIPE``
    plus ``communicate()`` was still blocked when a 6 s deadline gave up,
    and the same command with a temporary file returned in 0.003 s.

    **This is the only test that can tell the two apart.** Every other
    test in this file passes with a pipe, because none of them background
    anything. The tool's own budget is left at its 45 s default here on
    purpose: a fast return cannot be the timeout path in disguise.
    """
    pidfile = tmp_path / "pid"
    command = f"sleep 30 & echo $! > {pidfile}; echo backgrounded"
    try:
        started = time.monotonic()
        result = _bash(_workspace(tmp_path), command=command)
        elapsed = time.monotonic() - started

        assert result == "backgrounded\n"
        assert "[TIMEOUT" not in result
        assert elapsed < 2.0, (
            f"returned in {elapsed:.2f}s — a backgrounded child is holding "
            "the capture open, which is what happens with stdout=PIPE"
        )
        assert pidfile.read_text().strip().isdigit()
    finally:
        _reap(pidfile)


def test_a_backgrounded_child_is_still_running_when_the_call_returns(
    tmp_path,
):
    """The other half of the same measurement: the fix must not become
    "kill everything", which would return quickly and be useless."""
    pidfile = tmp_path / "pid"
    command = f"sleep 30 & echo $! > {pidfile}; echo backgrounded"
    try:
        _bash(_workspace(tmp_path), command=command)
        pid = int(pidfile.read_text().strip())

        os.kill(pid, 0)  # raises if the process is gone
    finally:
        _reap(pidfile)


def test_the_capture_file_is_gone_once_the_call_returns(tmp_path):
    """The stated cost of the temporary file, which is why
    :func:`_description` tells the model to redirect its own background
    output."""
    pattern = os.path.join(tempfile.gettempdir(), "omicsclaw-bash-*.log")
    before = set(glob.glob(pattern))

    _bash(_workspace(tmp_path), command="echo hi")

    assert set(glob.glob(pattern)) == before


# ---- exit status (plan 0029 Q6, traps 7 and 16) --------------------------


def test_the_shell_convention_is_used_for_a_signal(tmp_path):
    """Plan 0029 trap 16, at the unit that decides it."""
    assert _exit_status(0) == 0
    assert _exit_status(3) == 3
    assert _exit_status(-9) == 137  # SIGKILL
    assert _exit_status(-15) == 143  # SIGTERM


def test_asyncio_really_reports_a_signal_as_a_negative_number(tmp_path):
    """The premise :func:`_exit_status` is built on, pinned rather than
    assumed. ``pi``'s archived bug was the same predicate written against
    a runtime that reports ``null`` instead; if Python ever changed this,
    the normalisation above would be silently wrong."""

    async def scenario() -> int:
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            "kill -9 $$",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await process.wait()

    assert _run(scenario()) == -9


def test_a_command_killed_by_a_signal_is_not_reported_as_a_success(
    tmp_path,
):
    """Plan 0029 trap 16, end to end.

    ``pi`` tested ``exitCode !== 0 && exitCode !== null`` and a
    signal-terminated process reports ``null``, so everything ``SIGKILL``
    stopped came back as a success carrying partial output. The Python
    shape of the same bug is ``-9``: non-zero, but not a status any shell
    prints, and a model has nothing to match it against.
    """
    result = _bash(_workspace(tmp_path), command="echo working; kill -9 $$")

    assert "The command finished successfully" not in result
    assert "137" in result
    assert "working" in result


def test_a_negative_status_reaching_the_report_is_still_not_a_success():
    """Defence in depth, and it needed its own test to be defended.

    :func:`_exit_status` normalises before :func:`_report` ever sees a
    status, so the two together are safe and *neither half alone is
    pinned by an end-to-end test*: a mutation turning ``!= 0`` into
    ``> 0`` — pi's predicate exactly — survived the whole suite, because
    137 is greater than zero. It only bites once someone also drops the
    normalisation, at which point every signalled command reads as a
    success. Both halves are now named, so removing either goes red.
    """
    assert "successfully" not in _report(CommandOutcome(output="x\n", exit_code=-9))
    assert "successfully" not in _report(CommandOutcome(output="", exit_code=-9))


def test_a_non_zero_exit_is_the_commands_own_result_not_a_tool_failure(
    tmp_path,
):
    """Plan 0029 Q6 and the first half of trap 7.

    **The criterion is what the model should change next.** A failing test
    suite gives it nothing to change about the call, so this is not an
    error: told ``is_error=True`` the model goes looking for a broken tool
    instead of a broken test. The other half of the pair is the test
    immediately below; the ``read`` half of plan 0029's trap 7 — a missing
    file *is* ``is_error=True`` — is in ``tests/tools/test_read.py``,
    because the two tools shipped in different tasks.
    """
    registry = ToolRegistry()
    registry.register(BashTool(_workspace(tmp_path)))
    call = ToolCall(id="1", name=TOOL_NAME, arguments=_args(command="exit 3"))

    with use_tool_context(approval=_yes()):
        result = _run(registry.execute(call))

    assert result.is_error is False
    assert "exit status 3" in result.output


def test_arguments_that_will_not_decode_are_the_models_own_mistake(tmp_path):
    """The second half of the pair above, under the same criterion: this
    one *is* fixed by sending different arguments, so it is raised and the
    registry marks it."""
    registry = ToolRegistry()
    registry.register(BashTool(_workspace(tmp_path)))
    call = ToolCall(id="1", name=TOOL_NAME, arguments='{"command": "ls"')

    with use_tool_context(approval=_yes()):
        result = _run(registry.execute(call))

    assert result.is_error is True
    assert "not valid JSON" in result.output


def test_a_failing_command_keeps_its_output(tmp_path):
    result = _bash(
        _workspace(tmp_path),
        command="echo before failing; exit 7",
    )

    assert result == "[exit status 7]\nbefore failing\n"


def test_a_failing_command_that_printed_nothing_still_says_what_happened(
    tmp_path,
):
    result = _bash(_workspace(tmp_path), command="exit 2")

    assert result == "[exit status 2] The command failed and printed nothing."


def test_a_failing_commands_exit_status_survives_truncation(tmp_path):
    """The status line is added after truncation for the same reason the
    timeout banner is (``bash.go:187``): the longest outputs are exactly
    the ones where it matters most."""
    body = "noise\n" * 5_000
    command = f"{_emit(tmp_path, body)}; exit 9"

    result = _bash(_workspace(tmp_path), command=command)

    assert result.startswith("[exit status 9]\n")


def test_an_empty_command_is_a_correctable_mistake_rather_than_a_result(
    tmp_path,
):
    """**A deliberate departure from** ``bash.go:119-121``, which returns
    the string ``"Error: 命令为空字符串"`` with ``err == nil``.

    That is a failure delivered as a success whose text happens to begin
    with "Error", and it is the exact shape of the legacy defect this
    layer exists to end — ``engineering.py`` returns ``"Error: file not
    found or outside allowed roots: …"`` as a tool *result*, so the run
    never sees ``is_error``, and both ``builtin/read.py`` and
    ``builtin/write.py`` document rejecting it. An empty command is also
    squarely on the correctable side of trap 7's criterion. The detection
    is the reference's; the reporting is this layer's.
    """
    with pytest.raises(ToolArgumentError) as raised:
        _bash(_workspace(tmp_path), command="   ")

    assert "input.command" in str(raised.value)


# ---- the timeout (plan 0029 Q4, trap 6) ----------------------------------


def test_the_default_budget_leaves_room_inside_the_engines(tmp_path):
    """Plan 0029 trap 6(b), and **no override on either side**.

    Trap 6(a) below proves the mechanism works for *some* pair of numbers,
    which is a different claim: it would stay green after someone dropped
    ``EngineConfig.tool_timeout`` to 30 s without touching ``bash.py``,
    because it picks its own convenient values. This one is a plain
    arithmetic assertion over two defaults, and it is the only thing
    holding a coupling ``omicsclaw/tools/`` is forbidden to see.

    Importing :class:`~omicsclaw.engine.config.EngineConfig` here is
    compliant: the layering guard walks ``omicsclaw/tools/``, not
    ``tests/``.
    """
    tool = BashTool(_workspace(tmp_path))

    assert tool.timeout + ENGINE_TIMEOUT_MARGIN <= EngineConfig().tool_timeout
    assert tool.max_timeout <= EngineConfig().tool_timeout


def test_the_timeout_the_model_reads_about_is_the_tools_and_not_the_engines(
    tmp_path,
):
    """Plan 0029 trap 6(a): the mechanism, down the real dispatch path.

    ``execute_tool_calls`` wraps every call in ``EngineConfig.tool_timeout``
    and reports an expiry as ``tool 'bash' timed out after Ns`` — a
    sentence that tells the model nothing about what to do next. The whole
    point of budgeting below the engine is that
    :func:`~omicsclaw.tools.builtin.bash._timeout_banner` gets there
    first.
    """
    registry = ToolRegistry()
    registry.register(BashTool(_workspace(tmp_path), timeout=0.4))
    config = EngineConfig(tool_timeout=8.0)
    call = ToolCall(id="1", name=TOOL_NAME, arguments=_args(command="sleep 30"))
    results: list[ToolResult | None] = []

    async def scenario() -> None:
        with use_tool_context(approval=_yes()):
            async for _ in execute_tool_calls(registry, [call], config, results):
                pass

    _run(scenario())
    answer = results[0]

    assert answer is not None
    assert answer.is_error is False
    assert "[TIMEOUT 0.4s" in answer.output
    assert "timed out after" not in answer.output


def test_a_timeout_returns_whatever_was_printed_before_it(tmp_path):
    result = _bash(
        _workspace(tmp_path),
        tool=BashTool(_workspace(tmp_path), timeout=0.4),
        command="echo got this far; sleep 30",
    )

    assert result.startswith("got this far\n")
    assert "[TIMEOUT 0.4s" in result


def test_the_timeout_banner_is_appended_after_truncation(tmp_path):
    """``bash.go:187``: truncate, *then* warn.

    **A finding about the reference, recorded because it changes what this
    test can honestly claim.** That comment says the order exists so the
    warning is not truncated away — but keeping the *tail* already
    guarantees that: a banner appended before truncation lands in the last
    10,667 characters and survives anyway. The ordering was load-bearing
    against the head-only implementation ``bash.go:205-210`` says it
    replaced, and it is not load-bearing beside the head-plus-tail one
    that replaced it. It is still correct and free, so it is kept.

    What the order *does* still decide is observable and is what is
    asserted: the banner is not counted as part of the command's output,
    so the elided character count is over the output alone. Appending
    first inflates it by the length of the banner.
    """
    body = "noise\n" * 5_000
    assert len(body) == 30_000
    command = f"{_emit(tmp_path, body)}; sleep 30"

    result = _bash(
        _workspace(tmp_path),
        tool=BashTool(_workspace(tmp_path), timeout=1.0),
        command=command,
    )

    assert "...[Output too long" in result
    assert result.rstrip().endswith("]")
    assert "[TIMEOUT 1s" in result.rsplit("\n\n", 1)[-1]
    assert "14000 characters from the middle were cut" in result


def test_the_banner_tells_the_model_this_was_not_its_codes_fault(tmp_path):
    """``bash.go:199-203``. Without the distinction a model reads a
    truncated output with no verdict, concludes the code is broken, and
    edits something that was fine."""
    result = _bash(
        _workspace(tmp_path),
        tool=BashTool(_workspace(tmp_path), timeout=0.3),
        command="sleep 30",
    )

    assert "not an error in your code" in result
    assert "run a single test" in result
    assert "only shorten this limit" in result


def test_timeout_secs_can_shorten_the_limit(tmp_path):
    """The one thing plan 0029 Q4 keeps the argument for: a probe the
    model wants to give up on quickly."""
    result = _bash(
        _workspace(tmp_path),
        tool=BashTool(_workspace(tmp_path), timeout=30.0),
        command="sleep 30",
        timeout_secs=1,
    )

    assert "[TIMEOUT 1s" in result


def test_timeout_secs_cannot_lengthen_it(tmp_path):
    """``bash.go:75-77`` clamps; so does this, and the cap is the
    operator's own budget rather than a second constant. Asking for 600
    seconds gets the 0.5 the deployment configured."""
    result = _bash(
        _workspace(tmp_path),
        tool=BashTool(_workspace(tmp_path), timeout=0.5),
        command="sleep 30",
        timeout_secs=600,
    )

    assert "[TIMEOUT 0.5s" in result


def test_a_zero_timeout_secs_is_named_rather_than_read_as_absent(tmp_path):
    """``bash.go:72-84`` has to read ``0`` as "not given", because Go's
    decoder cannot tell an omitted integer from a zero. Python can, so a
    ``0`` that was really sent is really a mistake and saying so costs one
    corrected call instead of a silent 45 seconds."""
    with pytest.raises(ToolArgumentError) as raised:
        _bash(_workspace(tmp_path), command="true", timeout_secs=0)

    assert "input.timeout_secs" in str(raised.value)


def test_the_constructor_refuses_a_budget_that_could_never_run_anything(
    tmp_path,
):
    with pytest.raises(ValueError):
        BashTool(_workspace(tmp_path), timeout=0)


def test_max_timeout_follows_the_operators_budget(tmp_path):
    """Plan 0029 Q4 spells the ceiling as a constant that happens to equal
    the default. Derived instead: two numbers whose equality *is* the
    invariant can drift apart in one edit, and a deployment that raises
    ``timeout`` gets a ceiling that follows rather than a cap it forgot
    about."""
    workspace = _workspace(tmp_path)

    assert BashTool(workspace).max_timeout == DEFAULT_TIMEOUT
    assert BashTool(workspace, timeout=120.0).max_timeout == 120.0


# ---- cancellation (plan 0029 trap 5) -------------------------------------


def _cancel_midway(tool: BashTool, command: str, after: float) -> str:
    """Start a command, cancel the turn part-way, report what came back."""

    async def scenario() -> str:
        with use_tool_context(approval=_yes()):
            task = asyncio.ensure_future(tool.execute(_args(command=command)))
            await asyncio.sleep(after)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return "cancelled"
        return "not cancelled"

    return _run(scenario())


def test_a_cancelled_command_stays_cancelled(tmp_path):
    """Plan 0029 trap 5, fourth time in this rebuild and the easiest place
    to get wrong: an ``except Exception`` around ``process.wait()`` would
    turn the engine's own cancellation into an Observation telling the
    model to fix a command that was fine."""
    tool = BashTool(_workspace(tmp_path), timeout=30.0)

    assert _cancel_midway(tool, "sleep 20", after=0.3) == "cancelled"


def test_a_cancelled_turn_does_not_leave_its_subprocess_running(tmp_path):
    """The ``except CancelledError`` clause names the exception in order to
    kill the child and re-raise. Naming it is not handling it — but the
    child would outlive the turn otherwise, so the marker below is what
    says which of the two happened."""
    marker = tmp_path / "ran-anyway"
    tool = BashTool(_workspace(tmp_path), timeout=30.0)
    command = f"sleep 0.5; touch {marker}"

    assert _cancel_midway(tool, command, after=0.1) == "cancelled"
    time.sleep(1.5)

    assert not marker.exists()


def test_the_same_command_does_touch_the_marker_when_nothing_cancels_it(
    tmp_path,
):
    """The positive control for the test above, without which it would
    pass against a tool that never ran anything at all."""
    marker = tmp_path / "ran-anyway"

    _bash(_workspace(tmp_path), command=f"sleep 0.2; touch {marker}")

    assert marker.exists()


def test_a_cancelled_turn_leaves_no_capture_file_behind(tmp_path):
    pattern = os.path.join(tempfile.gettempdir(), "omicsclaw-bash-*.log")
    before = set(glob.glob(pattern))
    tool = BashTool(_workspace(tmp_path), timeout=30.0)

    _cancel_midway(tool, "sleep 20", after=0.3)

    assert set(glob.glob(pattern)) == before


# ---- approval (plan 0029 Q2) ---------------------------------------------


def test_nothing_runs_when_no_approval_channel_is_bound(tmp_path):
    """``require_approval`` fails closed, and the assertion that matters
    is the filesystem's rather than the exception's: an implementation
    that asked *after* running would satisfy the first reading."""
    marker = tmp_path / "ran"
    tool = BashTool(_workspace(tmp_path))

    with pytest.raises(ApprovalUnavailable):
        _run(tool.execute(_args(command=f"touch {marker}")))

    assert not marker.exists()


def test_nothing_runs_when_the_human_says_no(tmp_path):
    marker = tmp_path / "ran"

    with pytest.raises(ApprovalDenied):
        _bash(
            _workspace(tmp_path),
            approve=_no("that command deletes things"),
            command=f"touch {marker}",
        )

    assert not marker.exists()


def test_the_approval_prompt_carries_the_exact_bytes_the_model_sent(
    tmp_path,
):
    """Plan 0029 §5: this is why the tool is hand-written rather than a
    :class:`~omicsclaw.tools.function_tool.FunctionTool`. A prompt showing
    re-encoded arguments is showing something other than what will run —
    key order, spacing and any field the schema did not mention are all
    gone by then."""
    seen: list[ApprovalRequest] = []
    payload = '{"command":   "echo hi",  "timeout_secs": 5}'
    tool = BashTool(_workspace(tmp_path))

    with use_tool_context(approval=_yes(seen)):
        _run(tool.execute(payload))

    assert len(seen) == 1
    assert seen[0].arguments == payload
    assert seen[0].tool_name == TOOL_NAME


def test_the_approval_reason_shows_the_whole_command_and_where_it_runs(
    tmp_path,
):
    """Never an excerpt. A summary is where ``; rm -rf ~`` hides, and the
    person clicking is the only boundary this tool has."""
    seen: list[ApprovalRequest] = []
    workspace = _workspace(tmp_path)
    command = "make build && ./deploy.sh --force ; rm -rf ./cache"

    with use_tool_context(approval=_yes(seen)):
        _run(BashTool(workspace).execute(_args(command=command)))

    reason = seen[0].reason
    assert command in reason
    assert str(workspace.root) in reason
    assert "no OS isolation" in reason
    assert seen[0].risk_level is RiskLevel.HIGH
    assert seen[0].approval_mode is ApprovalMode.ASK


def test_the_approval_reason_names_the_limit_being_granted(tmp_path):
    seen: list[ApprovalRequest] = []
    tool = BashTool(_workspace(tmp_path), timeout=12.0)

    with use_tool_context(approval=_yes(seen)):
        _run(tool.execute(_args(command="true")))

    assert "12s limit" in seen[0].reason


def test_the_policy_is_declared_and_says_more_than_the_default_would(
    tmp_path,
):
    """Plan 0029 Q2. Leaving ``policy`` off lands on ``HIGH`` + ``ASK`` by
    accident, and that is the reason to write them down: a guarded default
    nobody chose and a guarded default somebody chose are identical at the
    call site and completely different the day someone relaxes the
    default."""
    policy = BashTool(_workspace(tmp_path)).policy

    assert policy.risk_level is RiskLevel.HIGH
    assert policy.approval_mode is ApprovalMode.ASK
    assert policy.concurrency_safe is False
    assert policy.read_only is False
    assert policy.allowed_in_background is False
    assert policy.writes_workspace is True
    assert "shell" in policy.tags


def test_a_deployment_can_relax_it_through_the_registry(tmp_path):
    """``register(policy=)`` is the override plan 0028 Q5 made
    authoritative, and the only one — there is deliberately no ``policy``
    constructor argument, because a constructor can only set the fallback
    and would be silently dead wherever a deployment named a policy at
    registration."""
    registry = ToolRegistry()
    registry.register(
        BashTool(_workspace(tmp_path)),
        ToolPolicy(risk_level=RiskLevel.LOW, approval_mode=ApprovalMode.AUTO),
    )
    call = ToolCall(id="1", name=TOOL_NAME, arguments=_args(command="echo ok"))

    result = _run(registry.execute(call))  # no approval channel bound

    assert result.is_error is False
    assert result.output == "ok\n"


def test_progress_is_reported_but_a_missing_audience_is_not_a_failure(
    tmp_path,
):
    seen: list[ProgressUpdate] = []
    workspace = _workspace(tmp_path)

    with use_tool_context(approval=_yes(), progress=seen.append):
        _run(BashTool(workspace).execute(_args(command="echo hi")))

    assert [update.tool_name for update in seen] == [TOOL_NAME]
    assert "echo hi" in seen[0].message
    assert _bash(workspace, command="echo hi") == "hi\n"  # no sink bound


def test_a_multi_line_command_is_reported_as_one_line_of_progress(tmp_path):
    """Display only — a status line stays a line. The approval prompt is
    where the whole command is guaranteed to appear, and
    :meth:`BashTool._reason` says why it is never abbreviated there."""
    seen: list[ProgressUpdate] = []

    with use_tool_context(approval=_yes(), progress=seen.append):
        _run(BashTool(_workspace(tmp_path)).execute(_args(command="echo a\necho b")))

    assert "\n" not in seen[0].message
    assert seen[0].message.endswith("echo a …")


# ---- the injected environment (plan 0029 Q11, trap 15) -------------------


class _RecordingEnvironment:
    """A fake :class:`BashEnvironment`, structural and importing nothing."""

    def __init__(self, output: str = "from the environment\n", exit_code: int = 0):
        self.calls: list[tuple[str, str, float]] = []
        self._output = output
        self._exit_code = exit_code

    async def run_bash(
        self,
        command: str,
        cwd: str,
        timeout: float,
    ) -> CommandOutcome:
        self.calls.append((command, cwd, timeout))
        return CommandOutcome(output=self._output, exit_code=self._exit_code)


def test_the_fake_environment_satisfies_the_protocol_structurally():
    assert isinstance(_RecordingEnvironment(), BashEnvironment)


def test_an_injected_environment_takes_the_command_instead_of_this_machine(
    tmp_path,
):
    """Plan 0029 trap 15: the parameter has to be **live**. harness9 holds
    an environment on its file tools and never reads it
    (``read_file.go:35-37`` is a TODO), which is dead state rather than a
    seam. The marker is what proves no local process ran."""
    marker = tmp_path / "ran-locally"
    environment = _RecordingEnvironment()
    workspace = _workspace(tmp_path)
    tool = BashTool(workspace, environment=environment)

    with use_tool_context(approval=_yes()):
        result = _run(tool.execute(_args(command=f"touch {marker}")))

    assert result == "from the environment\n"
    assert not marker.exists()
    assert environment.calls[0][0] == f"touch {marker}"


def test_an_environment_is_given_the_workspace_root_and_the_budget(tmp_path):
    """Both are obligations the tool cannot check afterwards: an
    implementation ignoring ``cwd`` silently relocates every relative path
    the model writes, and one ignoring ``timeout`` has no way to stop
    cleanly."""
    environment = _RecordingEnvironment()
    workspace = _workspace(tmp_path)
    tool = BashTool(workspace, environment=environment, timeout=9.0)

    with use_tool_context(approval=_yes()):
        _run(tool.execute(_args(command="ls")))

    command, cwd, timeout = environment.calls[0]
    assert command == "ls"
    assert cwd == str(workspace.root)
    assert timeout == 9.0


def test_a_shorter_timeout_secs_reaches_the_environment_too(tmp_path):
    environment = _RecordingEnvironment()
    tool = BashTool(_workspace(tmp_path), environment=environment, timeout=30.0)

    with use_tool_context(approval=_yes()):
        _run(tool.execute(_args(command="ls", timeout_secs=2)))

    assert environment.calls[0][2] == 2.0


def test_an_environments_negative_exit_code_is_normalised_at_the_seam(
    tmp_path,
):
    """Plan 0029 trap 16 arriving through the seam. An environment written
    the obvious way — on :mod:`asyncio.subprocess` — hands back ``-9``, so
    normalising here is cheaper than trusting every future implementation
    to have read the trap."""
    environment = _RecordingEnvironment(output="partial\n", exit_code=-9)
    tool = BashTool(_workspace(tmp_path), environment=environment)

    with use_tool_context(approval=_yes()):
        result = _run(tool.execute(_args(command="ls")))

    assert result == "[exit status 137]\npartial\n"


def test_an_environments_output_is_truncated_like_any_other(tmp_path):
    environment = _RecordingEnvironment(output="q" * 20_000)
    tool = BashTool(_workspace(tmp_path), environment=environment)

    with use_tool_context(approval=_yes()):
        result = _run(tool.execute(_args(command="ls")))

    head, tail = _halves(result)
    assert len(head) == 5_333
    assert len(tail) == 10_667


class _SlowEnvironment:
    async def run_bash(self, command: str, cwd: str, timeout: float):
        await asyncio.sleep(30)
        raise AssertionError("the budget should have fired first")


def test_an_environment_that_overruns_gets_the_tools_own_banner(tmp_path):
    """The budget is imposed as well as passed: a ``run_bash`` that ignores
    its argument must not be able to spend the engine's budget too."""
    tool = BashTool(
        _workspace(tmp_path), environment=_SlowEnvironment(), timeout=0.4
    )

    with use_tool_context(approval=_yes()):
        result = _run(tool.execute(_args(command="ls")))

    assert result.startswith("[TIMEOUT 0.4s")


class _ImpatientEnvironment:
    """An environment whose own client gave up, not ours."""

    async def run_bash(self, command: str, cwd: str, timeout: float):
        raise TimeoutError("docker host unreachable after 2s")


def test_an_environments_own_timeout_is_not_claimed_as_ours(tmp_path):
    """The same reasoning as ``engine/executor.py::_execute``: on 3.11+ a
    third party's expired deadline raises the very class ours does, and
    reported as ours the model is told to narrow a command when the truth
    is that a container host is unreachable."""
    tool = BashTool(
        _workspace(tmp_path), environment=_ImpatientEnvironment(), timeout=30.0
    )
    registry = ToolRegistry()
    registry.register(tool)
    call = ToolCall(id="1", name=TOOL_NAME, arguments=_args(command="ls"))

    with use_tool_context(approval=_yes()):
        result = _run(registry.execute(call))

    assert result.is_error is True
    assert "docker host unreachable" in result.output
    assert "[TIMEOUT" not in result.output


class _CancellingEnvironment:
    async def run_bash(self, command: str, cwd: str, timeout: float):
        raise asyncio.CancelledError()


def test_a_cancelled_environment_call_stays_cancelled(tmp_path):
    """Plan 0029 trap 5 on the routed path as well. ``except OSError`` is
    what keeps this true, and it has to come *after* ``except
    TimeoutError`` because on 3.11+ the builtin ``TimeoutError`` is an
    ``OSError``."""
    tool = BashTool(_workspace(tmp_path), environment=_CancellingEnvironment())

    async def scenario() -> str:
        with use_tool_context(approval=_yes()):
            try:
                await tool.execute(_args(command="ls"))
            except asyncio.CancelledError:
                return "cancelled"
        return "not cancelled"

    assert _run(scenario()) == "cancelled"


# ---- being a tool at all -------------------------------------------------


def test_it_is_a_tool_and_agrees_with_itself_about_its_name(tmp_path):
    tool = BashTool(_workspace(tmp_path))

    assert isinstance(tool, Tool)
    assert tool.name == TOOL_NAME == tool.definition().name == "bash"


def test_two_instances_do_not_share_one_schema_mapping(tmp_path):
    workspace = _workspace(tmp_path)
    first = BashTool(workspace).definition().input_schema
    second = BashTool(workspace).definition().input_schema

    first["properties"]["command"]["description"] = "edited"

    assert second["properties"]["command"]["description"] != "edited"
    assert BASH_SCHEMA["properties"]["command"]["description"] != "edited"


def test_the_definition_is_the_same_object_every_turn(tmp_path):
    """The tool segment sits inside the region every vendor's prompt-prefix
    cache keys on, so a definition rebuilt per turn would move the cache
    breakpoint."""
    tool = BashTool(_workspace(tmp_path))

    assert tool.definition() is tool.definition()


def test_the_description_states_the_limits_this_instance_really_has(
    tmp_path,
):
    """``bash.go:101`` formats its own limits into the schema, and the
    reason is that a deployment which raised ``timeout`` and left the
    sentence at 45 would be lying to the model with nothing to catch it."""
    workspace = _workspace(tmp_path)
    default = BashTool(workspace).definition()
    raised = BashTool(workspace, timeout=300.0).definition()

    assert "killed after 45 seconds" in default.description
    assert "killed after 300 seconds" in raised.description
    assert "at most 45" in _timeout_field(default)
    assert "at most 300" in _timeout_field(raised)


def _timeout_field(definition) -> str:
    return definition.input_schema["properties"]["timeout_secs"]["description"]


def test_the_description_tells_the_model_what_a_non_zero_exit_means(
    tmp_path,
):
    """Plan 0029 Q6 is only half done in the return value: the model has to
    be told, or it reads ``[exit status 1]`` and starts debugging the
    tool."""
    description = BashTool(_workspace(tmp_path)).definition().description

    assert "NON-ZERO EXIT STATUS" in description
    assert "not as a failure of this tool" in description


def test_the_description_carries_the_cost_that_came_with_the_fix(tmp_path):
    """Plan 0029 Q5 says the trade has to reach the model: the capture is
    deleted when the call returns, so a backgrounded command that relied on
    the inherited descriptor loses everything it wrote."""
    description = BashTool(_workspace(tmp_path)).definition().description

    assert "nohup cmd > out.log 2>&1 &" in description
    assert "deleted the moment this call returns" in description


def test_the_description_warns_that_long_output_loses_its_middle(tmp_path):
    description = BashTool(_workspace(tmp_path)).definition().description

    assert "16000 characters" in description
    assert "END" in description


def test_an_unknown_argument_is_a_schema_complaint_not_a_type_error(
    tmp_path,
):
    with pytest.raises(ToolArgumentError) as raised:
        _bash(_workspace(tmp_path), command="true", shell="zsh")

    assert "input.shell" in str(raised.value)


def test_a_missing_command_field_is_named_rather_than_defaulted(tmp_path):
    with pytest.raises(ToolArgumentError) as raised:
        _bash(_workspace(tmp_path), timeout_secs=5)

    assert "input.command" in str(raised.value)


# ---- the workspace it runs in --------------------------------------------


def test_a_workspace_that_is_no_longer_there_is_not_the_models_mistake(
    tmp_path,
):
    """Covers the ``except OSError`` in ``_start``, which would otherwise
    be reachable-but-unexercised — the state plan 0029 trap 15 asks an
    assessor to report. A :exc:`RuntimeError` rather than a
    :exc:`~omicsclaw.tools.function_tool.ToolArgumentError`: no command
    the model can send makes a deleted directory exist again."""
    missing = tmp_path / "gone"
    assert not missing.exists(), (
        "Workspace resolves without touching the filesystem, so this root "
        "is accepted and only the spawn below can notice it is not there"
    )
    tool = BashTool(_workspace(missing))

    with pytest.raises(RuntimeError) as raised:
        with use_tool_context(approval=_yes()):
            _run(tool.execute(_args(command="pwd")))

    assert not isinstance(raised.value, ToolArgumentError)
    assert "could not start a shell" in str(raised.value)


class _BrokenEnvironment:
    async def run_bash(self, command: str, cwd: str, timeout: float):
        raise OSError("the container socket is gone")


def test_an_environment_that_cannot_run_anything_says_so(tmp_path):
    """The other reachable ``except OSError``, on the routed path."""
    tool = BashTool(_workspace(tmp_path), environment=_BrokenEnvironment())

    with pytest.raises(RuntimeError) as raised:
        with use_tool_context(approval=_yes()):
            _run(tool.execute(_args(command="ls")))

    assert "container socket is gone" in str(raised.value)


def test_a_workspace_bound_to_the_session_is_used_when_none_was_given(
    tmp_path,
):
    """One registry serves many concurrent sessions — the Channel Surface
    has conversations interleaving on one event loop — so a workspace
    frozen into the constructor would make one of them run in another's
    directory."""
    tool = BashTool()

    with use_tool_context(approval=_yes(), values={"workspace": str(tmp_path)}):
        result = _run(tool.execute(_args(command="pwd")))

    assert result.strip() == str(Path(tmp_path).resolve())


def test_no_workspace_anywhere_is_not_reported_as_the_models_mistake():
    """A :exc:`RuntimeError` rather than a
    :exc:`~omicsclaw.tools.function_tool.ToolArgumentError`: no argument
    the model can send binds a workspace to a session, so promising it a
    correction would send it round a loop it cannot leave."""
    tool = BashTool()

    with pytest.raises(RuntimeError) as raised:
        with use_tool_context(approval=_yes()):
            _run(tool.execute(_args(command="pwd")))

    assert not isinstance(raised.value, ToolArgumentError)
    assert "workspace" in str(raised.value)
