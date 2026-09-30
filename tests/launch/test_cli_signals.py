"""``oc cli`` stopped by ``SIGTERM`` or by its terminal closing.

Both are driven against the real command in a pseudo-terminal, because
every property below is about a process: which exit code a supervisor
reads, and which processes are still alive once it has exited.

**Why the CLI has to handle these two signals at all.** A shell command
the model runs, and a ``!`` command the operator runs, start in a session
of their own so that a timeout or a ``Ctrl-C`` can kill the whole process
group. The price is that nothing sent to the terminal's process group
reaches them any more: not the ``SIGHUP`` of a closed terminal window, and
not the ``SIGTERM`` that ``kill``, ``timeout -s TERM`` or a supervisor
sends. Left to the default disposition, the CLI died where it stood, and
``sleep 30 | cat`` ran on with nothing left to enforce its timeout.
Measured before the handlers existed: the CLI ended by the signal itself
(``-15`` and ``-1``) and ``bash``, ``sleep`` and ``cat`` were all alive
afterwards, on both paths.

**Why the elapsed time is asserted.** A running exchange is not only
abandoned: it is cancelled. Left to the release instead, it would be
given :data:`~omicsclaw.entry.assembly.SHUTDOWN_GRACE_S` to finish on its
own, a command that never finishes would hold the process that long, and
a supervisor that follows ``SIGTERM`` with ``SIGKILL`` would kill it
first. Finishing well inside that grace is what shows the exchange was
cancelled rather than waited for.

**Why a closed terminal is its own case.** After a hang-up the terminal
is gone and a write to it fails with ``EIO``. The shutdown still writes —
``prompt_toolkit`` restores the screen, the held log is replayed, the
interpreter flushes standard output on its way out — and a shutdown that
stopped at the first failed write would skip the release, report ``1``
and leave the command running. ``129`` can only be reported once the
release has finished.
"""

from __future__ import annotations

import asyncio
import errno
import json
import os
import pathlib
import select
import shutil
import signal
import subprocess
import sys
import time

import pytest

from omicsclaw.entry.assembly import SHUTDOWN_GRACE_S

_SETSID = shutil.which("setsid")

pytestmark = pytest.mark.skipif(
    not os.path.isdir("/proc") or _SETSID is None or not hasattr(os, "openpty"),
    reason="needs /proc, a pseudo-terminal and util-linux setsid",
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_PROMPT = "❯".encode()

_CURSOR_QUERY = b"\x1b[6n"
_CURSOR_ANSWER = b"\x1b[1;1R"

_WAIT_S = 20.0

_ASKED = "the scripted backend asked for a command"
"""What the backend logs, at WARNING, when it asks for the command."""

_SITECUSTOMIZE = '''\
"""A backend that asks for one shell command, then answers."""
import logging
import sys

sys.path.insert(0, {root!r})

from omicsclaw.entry import assembly
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role, StreamChunk, StreamChunkType, ToolCall

ARGUMENTS = {arguments!r}
ASKED = {asked!r}


class Scripted:
    name = "scripted"

    def __init__(self):
        self.calls = 0

    async def generate(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            logging.getLogger("omicsclaw.test").warning(ASKED)
            call = ToolCall(id="call-0", name="bash", arguments=ARGUMENTS)
            return Completion(message=Message(role=Role.ASSISTANT, tool_calls=(call,)))
        return Completion(message=Message(role=Role.ASSISTANT, content="done"))

    async def _stream(self, messages, tools=None):
        completion = await self.generate(messages, tools)
        if completion.message.content:
            yield StreamChunk(
                type=StreamChunkType.TEXT_DELTA, delta=completion.message.content
            )
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)

    def generate_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    def bind(self, **overrides):
        return self


_ONE = Scripted()
assembly.provider_from_env = lambda *a, **k: _ONE
'''


def _group(pgid: int) -> dict[int, str]:
    """The live members of process group *pgid*, pid to command name.

    Read from ``/proc``: a killed member that has not been reaped yet is a
    zombie, and ``os.killpg(pgid, 0)`` answers for it as though it lived.
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


def _emptied(pgid: int, within: float = 2.0) -> bool:
    deadline = time.monotonic() + within
    while _group(pgid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


def _command_line(
    tmp_path: pathlib.Path, command: str
) -> tuple[list[str], dict[str, str]]:
    """``oc cli`` whose model asks for *command*, and the environment for it."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(
        _SITECUSTOMIZE.format(
            root=str(_REPO_ROOT),
            arguments=json.dumps({"command": command}),
            asked=_ASKED,
        ),
        encoding="utf-8",
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": os.pathsep.join((str(shim), str(_REPO_ROOT))),
        "HOME": str(tmp_path),
        "LANG": "C.UTF-8",
        "TERM": "xterm",
    }
    argv = [
        sys.executable,
        "-m",
        "omicsclaw.launch",
        "cli",
        "--workspace",
        str(workspace),
        "--permission-mode",
        "auto-approve",
    ]
    return argv, env


def _until(condition, what: str, within: float = _WAIT_S) -> None:
    deadline = time.monotonic() + within
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"never happened: {what}")
        time.sleep(0.02)


class _Cli:
    """``python -m omicsclaw.launch cli`` with a pseudo-terminal as its terminal.

    The child leads a session of its own with the terminal as its
    controlling terminal, so closing the terminal's other end sends it
    ``SIGHUP`` exactly as closing a window does. ``setsid --ctty`` does
    that before ``exec``, so no Python runs in the forked child: this test
    process has threads, and forking one to run Python is what
    ``pty.fork`` warns can deadlock. Its output is read as it arrives, so
    it never blocks on a full terminal.
    """

    def __init__(
        self,
        tmp_path: pathlib.Path,
        command: str,
        *,
        stderr: pathlib.Path | None = None,
    ) -> None:
        """*stderr*, if given, is a file standard error goes to instead."""
        argv, env = _command_line(tmp_path, command)
        self.output = b""
        self.code: int | None = None
        self._terminal: int | None
        self._terminal, secondary = os.openpty()
        try:
            # Not a process-group leader, so setsid runs the command in
            # place: this pid is the CLI's own.
            errors = open(stderr, "wb") if stderr is not None else None
            try:
                self._process = subprocess.Popen(
                    [_SETSID, "--ctty", *argv],
                    stdin=secondary,
                    stdout=secondary,
                    stderr=errors if errors is not None else secondary,
                    env=env,
                )
            finally:
                if errors is not None:
                    errors.close()
        finally:
            os.close(secondary)
        self.pid = self._process.pid

    def read(self, seconds: float) -> None:
        """Collect output for *seconds*, answering any cursor-position query."""
        deadline = time.monotonic() + seconds
        while self._terminal is not None and time.monotonic() < deadline:
            ready, _, _ = select.select([self._terminal], [], [], 0.02)
            if not ready:
                continue
            try:
                chunk = os.read(self._terminal, 65536)
            except OSError:
                return
            if _CURSOR_QUERY in chunk:
                os.write(self._terminal, _CURSOR_ANSWER)
            self.output += chunk

    def until(self, condition, what: str) -> None:
        deadline = time.monotonic() + _WAIT_S
        while not condition():
            if time.monotonic() > deadline:
                raise AssertionError(f"never happened: {what}\n{self.text()}")
            self.read(0.02)

    def type(self, line: str) -> None:
        assert self._terminal is not None
        os.write(self._terminal, line.encode() + b"\r")

    def hang_up(self) -> None:
        """Close the terminal, as closing its window does."""
        assert self._terminal is not None
        os.close(self._terminal)
        self._terminal = None

    def wait(self) -> int:
        """The exit status, or ``-signum`` for a process the signal killed.

        Not folded into ``128 + signum``: a process that *exits* 143 has
        run its shutdown, and one the signal killed has run nothing.
        """
        deadline = time.monotonic() + _WAIT_S
        while True:
            code = self._process.poll()
            if code is not None:
                self.code = code
                return code
            if time.monotonic() > deadline:
                raise AssertionError(f"the CLI did not exit\n{self.text()}")
            if self._terminal is not None:
                self.read(0.02)
            else:
                time.sleep(0.02)

    def text(self) -> str:
        return self.output.decode("utf-8", errors="replace")

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
            self._process.wait()
        if self._terminal is not None:
            os.close(self._terminal)
            self._terminal = None


def _stop(cli: _Cli, how: str) -> None:
    if how == "SIGTERM":
        os.kill(cli.pid, signal.SIGTERM)
    else:
        cli.hang_up()


_CODES = {"SIGTERM": 143, "hang-up": 129}


@pytest.mark.parametrize("how", sorted(_CODES))
@pytest.mark.parametrize("path", ["bash tool", "! command"])
def test_a_stop_signal_kills_the_running_command_and_reports_itself(
    tmp_path, path, how
):
    """The command dies with the CLI, which exits ``128 + signum``."""
    recorded = tmp_path / "pgid"
    command = f"echo $$ > {recorded}; sleep 30 | cat"
    cli = _Cli(tmp_path, command)
    pgid = None
    try:
        cli.until(lambda: _PROMPT in cli.output, "the prompt")
        cli.type("run it" if path == "bash tool" else f"!{command}")
        cli.until(
            lambda: recorded.exists() and recorded.read_text().strip(),
            "the command started",
        )
        pgid = int(recorded.read_text())
        cli.until(lambda: "sleep" in _group(pgid).values(), "sleep started")

        started = time.monotonic()
        _stop(cli, how)
        code = cli.wait()
        elapsed = time.monotonic() - started

        assert _emptied(pgid), f"outlived the CLI: {_group(pgid)}"
        assert code == _CODES[how], cli.text()
        assert elapsed < SHUTDOWN_GRACE_S - 1, (
            f"took {elapsed:.1f}s: the command was waited for, not cancelled"
        )
        assert "Traceback" not in cli.text()
    finally:
        cli.close()
        if pgid is not None and _group(pgid):
            os.killpg(pgid, signal.SIGKILL)


@pytest.mark.parametrize("how", sorted(_CODES))
def test_a_stop_signal_at_an_idle_prompt_ends_the_repl(tmp_path, how):
    """Nothing to cancel, and the REPL still stops: this signal is not
    ``Ctrl-C``, which only ends the loop when there was nothing to
    interrupt. The prompt that is waiting for a line is abandoned."""
    cli = _Cli(tmp_path, "true")
    try:
        cli.until(lambda: _PROMPT in cli.output, "the prompt")

        _stop(cli, how)

        assert cli.wait() == _CODES[how], cli.text()
        assert "Traceback" not in cli.text()
    finally:
        cli.close()


def test_after_a_hang_up_the_held_log_reaches_a_standard_error_that_survived(
    tmp_path,
):
    """What went wrong on the way out is logged, held while the REPL owns
    the terminal, and replayed after it. A hung-up terminal can show none
    of it, and is pointed at ``/dev/null`` so that writing it does not
    fail; ``oc cli 2>> cli.log`` is how the record is kept, and that file
    must neither be redirected nor miss the replay."""
    recorded = tmp_path / "pgid"
    errors = tmp_path / "stderr.log"
    command = f"echo $$ > {recorded}; sleep 30 | cat"
    cli = _Cli(tmp_path, command, stderr=errors)
    pgid = None
    try:
        cli.until(lambda: _PROMPT in cli.output, "the prompt")
        cli.type("run it")
        cli.until(
            lambda: recorded.exists() and recorded.read_text().strip(),
            "the command started",
        )
        pgid = int(recorded.read_text())

        cli.hang_up()

        assert cli.wait() == 129
        assert _emptied(pgid), f"outlived the CLI: {_group(pgid)}"
        assert _ASKED in errors.read_text(errors="replace")
    finally:
        cli.close()
        if pgid is not None and _group(pgid):
            os.killpg(pgid, signal.SIGKILL)


@pytest.mark.skipif(shutil.which("nohup") is None, reason="needs nohup")
def test_a_hang_up_nohup_told_it_to_ignore_stays_ignored(tmp_path):
    """``nohup oc cli --prompt-file task.md &`` is how a long analysis is
    left running past the end of an ssh session: ``nohup`` sets ``SIGHUP``
    to ignored and the process inherits that. A handler installed over it
    undid the one thing ``nohup`` is for, and the analysis was stopped at
    the moment the connection dropped — measured with the handler in
    place: exit 129, command killed; before it existed: exit 0, command
    finished. What the parent chose to ignore is ignored, ``SIGTERM``
    included."""
    recorded = tmp_path / "pgid"
    finished = tmp_path / "finished"
    argv, env = _command_line(
        tmp_path, f"echo $$ > {recorded}; sleep 1; touch {finished}"
    )
    with open(tmp_path / "output.txt", "wb") as sink:
        process = subprocess.Popen(
            [shutil.which("nohup"), *argv, "--prompt", "run it"],
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.STDOUT,
            env=env,
        )
    try:
        _until(
            lambda: recorded.exists() and recorded.read_text().strip(),
            "the command started",
        )
        os.kill(process.pid, signal.SIGHUP)

        code = process.wait(_WAIT_S)

        assert code == 0, (tmp_path / "output.txt").read_text(errors="replace")
        assert finished.exists(), "the command was stopped by the hang-up"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_sigterm_while_reading_an_open_pipe_ends_the_process(tmp_path):
    """``docker run -i``, a systemd unit with piped input, a producer that
    stays attached: standard input is a pipe that does not close. The
    REPL waits for its next line on a thread blocked in ``readline``, and
    that thread used to belong to the loop's default executor, which
    ``asyncio.run`` waits for as it shuts down — so the release finished
    and the process then waited for a line that was never coming, until
    the supervisor's ``SIGKILL``."""
    argv, env = _command_line(tmp_path, "true")
    output = tmp_path / "output.txt"
    with open(output, "wb") as sink:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=sink,
            stderr=subprocess.STDOUT,
            env=env,
        )
    try:
        assert process.stdin is not None
        process.stdin.write(b"!echo ready\n")
        process.stdin.flush()
        _until(lambda: b"done" in output.read_bytes(), "the first line answered")
        time.sleep(0.3)  # the REPL is back to waiting for its next line

        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        try:
            code = process.wait(SHUTDOWN_GRACE_S)
        except subprocess.TimeoutExpired:
            code = None
        elapsed = time.monotonic() - started

        assert code == 143, f"after {elapsed:.1f}s: {output.read_text(errors='replace')}"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stdin is not None:
            process.stdin.close()


# ---- the same shutdown, with the REPL and the app stood in for ----------


class _Handle:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def cancel(self) -> None:
        self._log.append("exchange cancelled")


class _Sessions:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    def running(self) -> tuple[_Handle, ...]:
        return (_Handle(self._log),)


class _App:
    """Records what the shutdown did to it, and can be signalled mid-release."""

    def __init__(self, *, terminated_while_releasing: bool = False) -> None:
        self.log: list[str] = []
        self.sessions = _Sessions(self.log)
        self._terminated_while_releasing = terminated_while_releasing

    async def aclose(self) -> None:
        if self._terminated_while_releasing:
            os.kill(os.getpid(), signal.SIGTERM)
            await asyncio.sleep(0.2)
        self.log.append("released")


class _Source:
    def close(self) -> None:
        pass


def _run_cli_with(
    monkeypatch,
    app: _App,
    *,
    repl: type | None = None,
    answer: str | None = None,
    terminated_while_opening: bool = False,
) -> int:
    """``_run_cli`` over doubles: the REPL *repl*, or one exchange ending *answer*.

    A double that wants a signal sends SIGTERM to this process. An outer
    handler is installed first, so that code which does not handle the
    signal fails the test instead of killing the test run.
    """
    import types

    from omicsclaw.launch import _surfaces

    async def open_app(_config):
        if terminated_while_opening:
            os.kill(os.getpid(), signal.SIGTERM)
            await asyncio.sleep(2.0)
        return app

    async def run_once(_app, _prompt, **_kwargs):
        return types.SimpleNamespace(terminal=answer)

    monkeypatch.setattr(_surfaces, "open_app", open_app)
    monkeypatch.setattr(_surfaces, "attach_sessions", lambda given: given)
    monkeypatch.setattr(_surfaces, "open_prompt_source", _Source)
    monkeypatch.setattr(_surfaces, "Screen", lambda *a, **k: None)
    monkeypatch.setattr(_surfaces, "run_once", run_once)
    if repl is not None:
        monkeypatch.setattr(_surfaces, "Repl", repl)
    options = _surfaces.ReplOptions()
    if answer is not None:
        options.prompt = "run it"
    original = signal.signal(signal.SIGTERM, lambda *_: None)
    try:
        return asyncio.run(_surfaces._run_cli(object(), options))
    finally:
        signal.signal(signal.SIGTERM, original)


class _TerminatedRepl:
    """Sends SIGTERM to its own process, then waits to be stopped."""

    def __init__(self, *_a, **_k) -> None:
        pass

    def welcome(self) -> None:
        pass

    async def run(self) -> None:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(2.0)


def test_sigterm_cancels_the_running_exchange_before_the_release(monkeypatch):
    """Cancelled, not drained: the release gives what still runs
    ``SHUTDOWN_GRACE_S`` to finish by itself, which a command that never
    finishes spends in full."""
    app = _App()

    code = _run_cli_with(monkeypatch, app, repl=_TerminatedRepl)

    assert code == 143
    assert app.log == ["exchange cancelled", "released"]


class _TerminalGoneRepl(_TerminatedRepl):
    """Stopped by the signal, then fails to write to a terminal that is gone."""

    async def run(self) -> None:
        try:
            await super().run()
        except asyncio.CancelledError:
            raise OSError(errno.EIO, "Input/output error") from None


def test_a_failed_write_after_the_signal_costs_neither_the_release_nor_the_code(
    monkeypatch,
):
    """The signal is why the process is ending, and a write that fails on
    the way out is its consequence, not a second failure to report."""
    app = _App()

    code = _run_cli_with(monkeypatch, app, repl=_TerminalGoneRepl)

    assert code == 143
    assert app.log[-1] == "released"


class _BrokenRepl(_TerminatedRepl):
    """Fails on its own, with no signal anywhere."""

    async def run(self) -> None:
        raise RuntimeError("a failure no signal caused")


def test_without_a_signal_a_failure_is_raised_as_it_was(monkeypatch):
    """Only a failure that follows a stop signal is its consequence. Any
    other is the failure the command reports, so it still leaves
    ``_run_cli`` — after the release, which runs on every path."""
    app = _App()

    with pytest.raises(RuntimeError, match="no signal caused"):
        _run_cli_with(monkeypatch, app, repl=_BrokenRepl)

    assert app.log == ["released"]


def test_sigterm_during_start_up_is_reported_as_itself(monkeypatch):
    """Start-up is when a deployment is most likely to be stopped, because
    it is when somebody is watching it. The cancellation used to leave
    ``_run_cli`` as a bare ``CancelledError``, which the command reports
    as ``130``: an interrupt at a terminal, not the operator's stop."""
    app = _App()

    code = _run_cli_with(
        monkeypatch, app, repl=_TerminatedRepl, terminated_while_opening=True
    )

    assert code == 143
    assert app.log == [], "there was no deployment yet to release"


@pytest.mark.parametrize("answer, expected", [("converged", 0), ("failed", 1)])
def test_a_signal_after_the_run_has_ended_keeps_the_runs_own_code(
    monkeypatch, answer, expected
):
    """``--prompt`` answered, and then the signal arrived while the
    deployment was being released. Reported as ``143``, a batch system
    reruns a task that had finished, and a ``1`` saying the exchange
    failed is lost. The exit code reports the run, and the signal only
    when it stopped the run."""
    app = _App(terminated_while_releasing=True)

    code = _run_cli_with(monkeypatch, app, answer=answer)

    assert code == expected
    assert app.log == ["released"], "nothing was running to cancel"


# ---- what the handlers leave alone --------------------------------------


@pytest.mark.parametrize("ignored", [signal.SIGHUP, signal.SIGTERM])
def test_a_signal_the_parent_ignores_is_left_ignored(ignored):
    """``nohup`` ignores ``SIGHUP`` for the process it starts, and a shell
    without job control ignores ``SIGINT`` for a job put in the
    background: the parent's decision, made for this process. A handler
    installed over it reverses that decision, and removing the handler
    afterwards sets the default, which is not what was inherited either."""
    from omicsclaw.launch._surfaces import _stop_signals

    async def scenario() -> tuple[object, object]:
        with _stop_signals(None, (signal.SIGTERM, signal.SIGHUP)):
            inside = signal.getsignal(ignored)
        return inside, signal.getsignal(ignored)

    original = signal.signal(ignored, signal.SIG_IGN)
    try:
        inside, after = asyncio.run(scenario())
    finally:
        signal.signal(ignored, original)

    assert inside == signal.SIG_IGN
    assert after == signal.SIG_IGN


def _file(descriptor: int) -> tuple[int, int, int]:
    """What *descriptor* refers to: device, inode, and the device it is."""
    status = os.fstat(descriptor)
    return status.st_dev, status.st_ino, status.st_rdev


def test_a_terminal_that_has_hung_up_is_pointed_at_dev_null():
    """Every write to a hung-up terminal fails with ``EIO``, the
    interpreter's own flush at exit included, which turns a clean ``129``
    into ``120``. After this one, writes go nowhere and succeed."""
    from omicsclaw.launch._surfaces import _leave_a_hung_up_terminal

    primary, secondary = os.openpty()
    os.close(primary)  # the terminal hangs up
    try:
        _leave_a_hung_up_terminal(signal.SIGHUP, (secondary,))

        assert os.fstat(secondary).st_rdev == os.stat(os.devnull).st_rdev
        assert os.write(secondary, b"after the hang-up") > 0
    finally:
        os.close(secondary)


def test_a_terminal_still_in_use_is_left_alone():
    """``kill -HUP`` with the window still open: the person is still
    looking at it, and the log replayed on the way out is for them."""
    from omicsclaw.launch._surfaces import _leave_a_hung_up_terminal

    primary, secondary = os.openpty()
    try:
        before = _file(secondary)

        _leave_a_hung_up_terminal(signal.SIGHUP, (secondary,))

        assert _file(secondary) == before
    finally:
        os.close(primary)
        os.close(secondary)


def test_a_pipe_and_a_file_are_left_alone(tmp_path):
    """``oc cli 2> err.log`` keeps its log when the terminal closes: only
    a terminal hangs up, and only a hung-up terminal is redirected."""
    from omicsclaw.launch._surfaces import _leave_a_hung_up_terminal

    reading, writing = os.pipe()
    logged = os.open(tmp_path / "err.log", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        before = [_file(writing), _file(logged)]

        _leave_a_hung_up_terminal(signal.SIGHUP, (writing, logged))

        assert [_file(writing), _file(logged)] == before
    finally:
        for descriptor in (reading, writing, logged):
            os.close(descriptor)
