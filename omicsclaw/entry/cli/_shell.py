"""``!cmd`` — the operator's own shell, run where the agent works.

A line beginning with ``!`` is intercepted before the slash-command
catalogue is consulted and handed to ``bash -c`` in the workspace, and
the model is not called. The reference harness does the same at
``tui_update.go:359-363`` → ``dispatchShellCommand`` (``:1612-1635``),
and four of its decisions are copied for the reasons it gives:
``bash -c`` so that pipes, redirection and ``&&`` work; combined stdout
and stderr so an error is visible; two different output ceilings, one
for the screen and a smaller one for the model; and the record of what
ran prefixed to the *next* question, so the model knows what the person
just did.

**Nothing here passes a permission gate, deliberately.** The person
typing ``!rm -rf build`` already has a shell on this machine — they are
sitting at one — so a confirmation prompt in front of their own command
is theatre. What the gate exists for is a command the *model* proposed,
and no command reaches this module from the model.

**The timeout is short and is its own number.**
:data:`~omicsclaw.entry.config.AppConfig.bash_timeout` is minutes long
because it covers a deconvolution or a STAR alignment that the agent
kicked off and nobody is watching. This one covers a command a person
typed and is now staring at a cursor waiting for, which is a different
question with a different answer, so it is a separate constant rather
than a share of that one. Whoever wants ten minutes of ``!`` can open
a second terminal, which is also the honest answer for anything
interactive.

**The command list is a courtesy; the timeout is the guarantee.**
:func:`wants_a_terminal` looks at the first word only — as the reference
harness does (``tui_update.go:1578-1582``) — so ``echo hi && vim``,
``bash -c vim`` and ``git commit`` (which opens ``$EDITOR``) all walk
straight past it. **Do not treat filling the list in as the fix.** The
cost of a miss has to be bounded by something that cannot be talked
around, and that is :data:`SHELL_TIMEOUT_S` plus a process group that is
killed as a group: a program that sits waiting for a terminal is killed
after N seconds and the REPL prints why. A REPL that hung instead would
be reviving exactly the class of defect this surface was last repaired
for.

Two more things the child does not get. Its standard input is
``/dev/null``, so it cannot race the REPL for the keyboard — the
reference harness gets this from Go's default and this module has to ask
for it. And it runs in a session of its own, so killing it after the
timeout kills whatever it started rather than orphaning a subtree that
holds the pipe open.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from omicsclaw.memory import truncate_utf8

__all__ = [
    "CONTEXT_LIMIT",
    "DISPLAY_LIMIT",
    "NEEDS_A_TERMINAL",
    "SHELL_RECORD_HEADER",
    "SHELL_TIMEOUT_S",
    "ShellResult",
    "for_display",
    "for_model",
    "run_shell",
    "shell_preamble",
    "wants_a_terminal",
]

SHELL_TIMEOUT_S = 60.0
"""Seconds a ``!`` command may run before it is killed.

Unrelated to every other timeout in this deployment, and that is the
point — see this module's docstring. A minute is long enough for the
commands ``!`` is for (``ls``, ``git status``, ``head``, a quick
``grep``) and short enough that a person who typed one that will never
finish gets their prompt back while they are still looking at it.
"""

DISPLAY_LIMIT = 4096
"""Bytes of output a ``!`` command may put on the screen.

Matches ``read_file``'s ceiling in the reference harness so that a person
meets one number rather than two, and a scrollback full of one command's
output is a scrollback the answer above it has left.
"""

CONTEXT_LIMIT = 2048
"""Bytes of output that reach the model.

Half the screen's, because these records accumulate: several commands
between two questions are all prefixed to the same prompt, and the
budget they share is the conversation's. The two ceilings are separate
values and not one because they answer to different limits — a terminal's
is attention and a prompt's is tokens.
"""

SHELL_RECORD_HEADER = "[Shell commands run by the operator at the terminal]"
"""First line of the block prefixed to the next question.

Says who ran them, which is the part the model cannot infer: without it
a transcript of commands arriving inside a user message reads as an
instruction to run them.
"""

NEEDS_A_TERMINAL = frozenset(
    {
        "emacs",
        "htop",
        "less",
        "man",
        "more",
        "nano",
        "screen",
        "ssh",
        "tmux",
        "top",
        "vi",
        "vim",
        "watch",
    }
)
"""Programs known to want a terminal this REPL will not give them.

The reference harness's thirteen names (``tui_update.go:1567-1577``),
kept for the message they buy: "open another terminal" is more useful
than sixty seconds of nothing. It is not a safety boundary — see this
module's docstring.
"""

_TIMED_OUT = "timed out"


@dataclass(frozen=True, slots=True)
class ShellResult:
    """What one ``!`` command did."""

    command: str
    output: str
    """stdout and stderr, interleaved as the terminal would have shown
    them, decoded with replacement so a binary byte cannot raise."""

    failed: bool
    """True on a non-zero exit **and** on a kill, as the reference
    harness's ``isErr`` is: both mean the command did not do what was
    asked, and a person who sees only the output cannot tell."""

    duration_s: float
    timed_out: bool


def wants_a_terminal(command: str) -> bool:
    """Whether *command*'s first word is a program known to need a TTY.

    Only the first word, and only its final path segment, so
    ``/usr/bin/vim`` is caught and ``echo hi && vim`` is not. See this
    module's docstring: a miss costs :data:`SHELL_TIMEOUT_S`, not a
    wedged session.
    """
    words = command.split()
    if not words:
        return False
    return os.path.basename(words[0]) in NEEDS_A_TERMINAL


async def run_shell(
    command: str,
    *,
    cwd: Path | str,
    timeout_s: float = SHELL_TIMEOUT_S,
) -> ShellResult:
    """Run *command* through ``bash -c`` in *cwd* and collect its output.

    Never raises for the command's own sake: a non-zero exit, a kill and
    a shell that could not even be started all come back as a
    :class:`ShellResult` with ``failed`` set, because the caller's job is
    to put the answer on a screen and a traceback is not one.

    :param command: Shell text, exactly as typed after the ``!``.
    :param cwd: Directory to run in.
    :param timeout_s: Seconds before the command and everything it
        started are killed.
    """
    started = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            command,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as error:
        return ShellResult(
            command=command,
            output=f"could not start a shell: {error}",
            failed=True,
            duration_s=time.monotonic() - started,
            timed_out=False,
        )

    try:
        raw, _ = await asyncio.wait_for(process.communicate(), timeout_s)
    except TimeoutError:
        _kill_the_group(process)
        raw = await _drain(process)
        return ShellResult(
            command=command,
            output=_decode(raw),
            failed=True,
            duration_s=time.monotonic() - started,
            timed_out=True,
        )
    return ShellResult(
        command=command,
        output=_decode(raw),
        failed=process.returncode != 0,
        duration_s=time.monotonic() - started,
        timed_out=False,
    )


def for_display(output: str) -> str:
    """*output* cut to :data:`DISPLAY_LIMIT` bytes, marked where it was cut."""
    return truncate_utf8(output, DISPLAY_LIMIT)


def for_model(result: ShellResult) -> str:
    """One record of *result*, cut to :data:`CONTEXT_LIMIT` bytes.

    Shaped like a terminal transcript — the command on a ``$`` line, its
    output under it — because that is the shape a model has seen a
    million of and needs no explaining.
    """
    body = truncate_utf8(result.output, CONTEXT_LIMIT)
    note = f" ({_TIMED_OUT} after {result.duration_s:.0f}s)" if result.timed_out else ""
    return f"$ {result.command}{note}\n{body}"


def shell_preamble(records: Sequence[str]) -> str:
    """The block to prefix to the next question, or ``""`` for no records.

    Empty for an empty sequence rather than a header with nothing under
    it: a caller is expected to test the result, and a prompt that opened
    by announcing commands and then listed none would be a puzzle the
    model tries to solve.
    """
    if not records:
        return ""
    return SHELL_RECORD_HEADER + "\n" + "\n---\n".join(records) + "\n\n"


def _kill_the_group(process: "asyncio.subprocess.Process") -> None:
    """Kill the command and everything it started.

    The process group and not the process: ``bash -c 'sleep 60 | cat'``
    leaves two children, and killing only the shell leaves the pipe held
    open by a process nobody is waiting for.
    """
    with contextlib.suppress(OSError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        return
    with contextlib.suppress(OSError):
        process.kill()


async def _drain(process: "asyncio.subprocess.Process") -> bytes:
    """Whatever a killed command had already written, or nothing.

    The first :meth:`communicate` was cancelled by the timeout, so the
    pipe may still hold bytes; a second call collects them now that the
    writer is gone. It is allowed to fail — this runs on the path where
    something has already gone wrong, and losing the tail of a killed
    command's output is not worth a second failure.
    """
    try:
        raw, _ = await process.communicate()
    except Exception:  # noqa: BLE001 - see the docstring
        return b""
    return raw or b""


def _decode(raw: bytes | None) -> str:
    """Bytes from a command as text, with undecodable ones replaced."""
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")
