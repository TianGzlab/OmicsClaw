"""The three surface starters, and the branches nobody was standing over.

Plan 0037's review measured ``omicsclaw/launch/_surfaces.py`` at 297
statements with 83 never executed by any test, and made the point that
matters: the review then read those branches and found them **correct**. A
correct branch with no test is not a bug, it is a bug's future address —— the
next person who edits it gets no warning, and the file is the one that cuts
the command line for every deployment of this program.

This file stands over them. What is asserted here is deliberately the small
stuff —— a port bound, a channel name refused twice, a help flag answered ——
because that is what was uncovered; the process-level properties are in
``test_channel_command.py`` and ``test_cli_command.py``, where they need a
real process to mean anything.

**Every test here was run against the pre-fix code first.** A test that
cannot fail proves nothing, and plan 0037's own §8-4 is the cautionary tale:
a smoke that returned before the thing it smoked was started.
"""

from __future__ import annotations

import asyncio
import io
import logging
import signal
import sys

import pytest

from omicsclaw.entry.config import AppConfigError
from omicsclaw.launch import DOTENV_FILE, _adopt_dotenv, _surfaces, main
from omicsclaw.launch._surfaces import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_REFUSED,
    ChannelOptions,
    DesktopOptions,
    ReplOptions,
    _as_channel_names,
    _as_port,
    _refuse_an_open_unauthenticated_bind,
    _replay,
    _stop_signals,
)

# ---- the flag parsers -------------------------------------------------


@pytest.mark.parametrize(
    "argv, attribute, expected",
    [
        (["--host", "0.0.0.0"], "host", "0.0.0.0"),
        (["--port", "9000"], "port", 9000),
        ([], "host", _surfaces.DESKTOP_HOST),
        ([], "port", _surfaces.DESKTOP_PORT),
        (["--help"], "help", True),
        (["-h"], "help", True),
    ],
)
def test_each_desktop_flag_lands_where_it_says(argv, attribute, expected):
    assert getattr(DesktopOptions.parse(argv), attribute) == expected


@pytest.mark.parametrize("flag", ["--host", "--port"])
def test_a_desktop_flag_without_its_value_is_refused(flag):
    with pytest.raises(AppConfigError, match="needs a value"):
        DesktopOptions.parse([flag])


def test_an_unknown_desktop_flag_is_refused():
    with pytest.raises(AppConfigError, match="unknown surface option"):
        DesktopOptions.parse(["--tls"])


@pytest.mark.parametrize("raw", ["0", "65536", "-1", "http", "80.5", ""])
def test_a_port_outside_the_range_is_not_a_port(raw):
    """Both ends, because ``0`` and ``65536`` are the two off-by-ones.

    ``0`` is the one that matters in practice: a kernel reads it as
    "pick any free port", so a deployment that meant 8080 and typed 0
    would come up on an address nothing is configured to reach.
    """
    with pytest.raises(AppConfigError, match="not a port number"):
        _as_port(raw)


@pytest.mark.parametrize("raw, expected", [("1", 1), ("65535", 65535), ("8765", 8765)])
def test_a_port_inside_the_range_is_a_port(raw, expected):
    assert _as_port(raw) == expected


@pytest.mark.parametrize(
    "argv, attribute, expected",
    [
        (["--channels", "telegram,feishu"], "channels", ("telegram", "feishu")),
        (["--health-port", "8080"], "health_port", 8080),
        (["--verbose"], "verbose", True),
        (["--list"], "list", True),
        (["--help"], "help", True),
        ([], "health_port", 0),
        ([], "channels", ()),
    ],
)
def test_each_channel_flag_lands_where_it_says(argv, attribute, expected):
    assert getattr(ChannelOptions.parse(argv), attribute) == expected


@pytest.mark.parametrize("flag", ["--channels", "--health-port"])
def test_a_channel_flag_without_its_value_is_refused(flag):
    with pytest.raises(AppConfigError, match="needs a value"):
        ChannelOptions.parse([flag])


def test_an_unknown_channel_flag_is_refused():
    with pytest.raises(AppConfigError, match="unknown surface option"):
        ChannelOptions.parse(["--webhook"])


@pytest.mark.parametrize(
    "raw, message",
    [
        ("", "at least one channel name"),
        (" , ,", "at least one channel name"),
        ("telegran", "unknown channel"),
        ("telegram,telegram", "more than once"),
    ],
)
def test_a_channel_list_is_refused_for_the_reason_it_is_wrong(raw, message):
    """Three refusals, and the third is the one nothing else would catch.

    ``ChannelManager.register`` is keyed by name, so ``telegram,telegram``
    would register one adapter, drop the other without a word and run a
    deployment that is not the one that was asked for.
    """
    with pytest.raises(AppConfigError, match=message):
        _as_channel_names(raw)


def test_a_channel_list_tolerates_the_spaces_a_person_types():
    assert _as_channel_names(" telegram , feishu ") == ("telegram", "feishu")


# ---- CLAUDE.md safety rule 1 ------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", ""])
def test_a_loopback_bind_needs_no_token(host):
    assert _refuse_an_open_unauthenticated_bind(host, "") is None


@pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.5", "::", "example.internal"])
def test_an_off_machine_bind_without_a_token_is_refused(host):
    """Plan 0037 R2, and the owner's ruling on it.

    ``create_desktop_app(app, bearer_token="")`` authorises every
    request, which is the right default for a socket only this machine
    can reach and is an unauthenticated agent with a shell tool for any
    other address. The message has to name the variable, because a
    refusal whose remedy the reader has to go and look up is a refusal
    they will work around.
    """
    with pytest.raises(AppConfigError, match="OMICSCLAW_REMOTE_AUTH_TOKEN"):
        _refuse_an_open_unauthenticated_bind(host, "")


@pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.5"])
def test_an_off_machine_bind_with_a_token_is_allowed(host):
    assert _refuse_an_open_unauthenticated_bind(host, "s3cret") is None


def test_the_desktop_command_refuses_an_open_bind_before_it_needs_uvicorn(capsys):
    """The whole command, not the helper: ordering is the property.

    ``uvicorn`` is not installed here, so a check placed after the
    dependency probe would be unreachable on this machine and the
    refusal a user actually got would be about a missing package. The
    security refusal has to come first, and the only way to see that it
    does is to run the command where both conditions hold.
    """
    code = main(["desktop", "--", "--host", "0.0.0.0"], {})
    captured = capsys.readouterr()

    assert code == EXIT_REFUSED
    assert "OMICSCLAW_REMOTE_AUTH_TOKEN" in captured.err
    assert "uvicorn" not in captured.err


def test_the_token_comes_from_the_environment_the_shell_was_handed(capsys):
    """With the variable set, the same command reaches the dependency check.

    This is the other half of the test above and the reason it is not
    vacuous: the refusal is conditional on the environment, so both
    branches have to be shown from the outside. Both exit ``2``, so the
    *message* is what distinguishes them.
    """
    code = main(
        ["desktop", "--", "--host", "0.0.0.0"],
        {"OMICSCLAW_REMOTE_AUTH_TOKEN": "s3cret"},
    )
    captured = capsys.readouterr()

    assert code == EXIT_REFUSED
    assert "uvicorn and fastapi" in captured.err
    assert "OMICSCLAW_REMOTE_AUTH_TOKEN" not in captured.err


# ---- plan 0037 §5.2: the deployment half is always read ---------------


@pytest.mark.parametrize(
    "argv",
    [
        ["channel", "--bogus", "--", "--list"],
        ["channel", "--bogus", "--", "--help"],
        ["cli", "--bogus", "--", "--help"],
        ["desktop", "--bogus", "--", "--help"],
    ],
    ids=lambda argv: " ".join(argv),
)
def test_an_unknown_deployment_flag_is_never_discarded_by_a_surface(argv, capsys):
    """Plan 0037 R1 and §5.2: ``--``'s left half goes to one reader, always.

    Every one of these exited ``0`` before the fix. ``--list`` and
    ``--help`` returned before ``resolve_app_config`` was ever called,
    so a mistyped deployment flag was silently dropped and the
    deployment that ran —— or the help that printed —— was not the one
    that was asked for. ``oc cli --bogus`` with no terminator was
    refused correctly all along, which is what made the gap look like it
    was not there.
    """
    code = main(argv, {})
    captured = capsys.readouterr()

    assert code == EXIT_REFUSED
    assert "--bogus" in captured.err


@pytest.mark.parametrize("surface", ["cli", "desktop", "channel"])
def test_a_well_formed_help_request_is_still_answered(surface, capsys):
    """The other side of the rule, so it cannot pass by refusing everything."""
    assert main([surface, "--help"], {}) == EXIT_OK

    assert f"usage: oc {surface}" in capsys.readouterr().out


def test_the_registry_listing_still_works_and_reads_the_gate(capsys):
    assert main(["channel", "--", "--list"], {}) == EXIT_OK
    printed = capsys.readouterr().out

    assert "telegram" in printed and "authoritative" in printed
    assert "disabled pending cutover" in printed


def test_a_channel_run_with_no_channels_says_which_flag_is_missing(capsys):
    assert main(["channel"], {}) == EXIT_REFUSED

    assert "--channels is required" in capsys.readouterr().err


# ---- plan 0037 B3: main() raises nothing ------------------------------


def _table_that_raises(exception: BaseException) -> dict:
    """The real command table with one starter replaced.

    Driven through :func:`main` rather than by calling the clause
    directly, because "raises nothing" is a property of that function
    and of no smaller thing.
    """
    import dataclasses

    from omicsclaw.launch import COMMANDS

    def explode(_deployment, _surface, _env):
        raise exception

    return dict(COMMANDS, channel=dataclasses.replace(
        COMMANDS["channel"], start=explode
    ))


@pytest.mark.parametrize(
    "exception, expected",
    [
        (ValueError("a failure nobody wrote a clause for"), EXIT_FAILED),
        (RuntimeError("python-telegram-bot not installed"), EXIT_FAILED),
        (SystemExit(3), 3),
        (SystemExit("argparse said so"), EXIT_FAILED),
    ],
    ids=["value-error", "runtime-error", "sys-exit-code", "sys-exit-message"],
)
def test_an_unanticipated_failure_is_an_exit_code_and_not_a_traceback(
    monkeypatch, capsys, exception, expected
):
    """``main``'s docstring promises an exit code and no exception.

    Until plan 0037's review it caught three exception types and let
    every other one out, which is how ``oc channel -- --channels
    telegram`` answered a missing platform SDK with a traceback full of
    this machine's absolute paths and exit code 1 out of the interpreter
    rather than out of this function. The failure is still *reported* ——
    the type and the message —— because a backstop that swallows the
    reason is worse than the traceback it replaced.

    :exc:`SystemExit` has its own clause because a library that calls
    :func:`sys.exit` has already chosen a code, and overwriting it would
    lose the only thing it said.
    """
    import omicsclaw.launch as launch

    monkeypatch.setattr(launch, "COMMANDS", _table_that_raises(exception))

    code = main(["channel", "--", "--list"], {})
    captured = capsys.readouterr()

    assert code == expected
    assert "Traceback" not in captured.err


def test_the_backstop_names_the_failure_it_caught(monkeypatch, capsys):
    """Reporting nothing would satisfy "no traceback" and help nobody."""
    import omicsclaw.launch as launch

    monkeypatch.setattr(
        launch, "COMMANDS", _table_that_raises(ValueError("the actual reason"))
    )

    assert main(["channel", "--", "--list"], {}) == EXIT_FAILED
    assert "ValueError: the actual reason" in capsys.readouterr().err


def test_a_surface_dependency_that_is_absent_is_a_refusal_not_a_crash(
    monkeypatch, capsys
):
    """An ``ImportError`` out of a running adapter becomes exit code 2.

    Both shipped adapters translate their own missing SDK into a
    ``RuntimeError`` with an install line, so this clause is reached by
    the *untranslated* imports —— ``feishu.py`` has two —— and by any
    adapter added later. Exit code 2 and not 1, because nothing the user
    retypes fixes an uninstalled package.
    """

    async def missing(_config, _options, _env):
        raise ModuleNotFoundError("No module named 'lark_oapi'", name="lark_oapi")

    monkeypatch.setattr(_surfaces, "_serve_channels", missing)
    code = main(
        ["channel", "--", "--channels", "feishu"],
        {
            "FEISHU_APP_ID": "a",
            "FEISHU_APP_SECRET": "s",
            "FEISHU_ALLOWED_SENDERS": "ou_owner",
            "FEISHU_BOT_OPEN_ID": "ou_bot",
        },
    )
    captured = capsys.readouterr()

    assert code == EXIT_REFUSED
    assert "lark_oapi is not installed" in captured.err
    assert "Traceback" not in captured.err


# ---- the telegram builder ---------------------------------------------


def test_telegram_needs_a_token():
    with pytest.raises(AppConfigError, match="TELEGRAM_BOT_TOKEN"):
        _surfaces.build_channel("telegram", {})


def test_telegram_needs_an_allowlist_the_way_feishu_does():
    """Plan 0037 B3's third clause: one class of mistake, one experience.

    Left to the adapter, this arrived as a ``RuntimeError`` out of a
    started ``Application`` —— exit code 1 and no usage —— while the
    same omission on Feishu was an ``AppConfigError`` with exit code 2.
    """
    with pytest.raises(AppConfigError, match="TELEGRAM_ALLOWED_SENDERS"):
        _surfaces.build_channel("telegram", {"TELEGRAM_BOT_TOKEN": "t"})


@pytest.mark.parametrize(
    "env",
    [
        {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "42"},
        {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_ALLOWED_SENDERS": "owner"},
    ],
    ids=["chat-id", "allowlist"],
)
def test_telegram_is_built_from_either_half_of_its_gate(env):
    """Both spellings of "who may talk to this bot" are accepted.

    Constructing the adapter costs no SDK —— ``telegram`` is imported
    lazily, when a client is first needed —— so this runs here.
    """
    channel = _surfaces.build_channel("telegram", env)

    assert channel.config.bot_token == "t"


def test_an_adapter_with_no_launch_configuration_says_so():
    with pytest.raises(AppConfigError, match="no launch configuration yet"):
        _surfaces.build_channel("slack", {})


@pytest.mark.parametrize("raw", ["x", "1.5", "seven"])
def test_a_whole_number_variable_that_is_not_one_is_refused(raw):
    with pytest.raises(AppConfigError, match="not a whole number"):
        _surfaces._as_int({"TELEGRAM_CHAT_ID": raw}, "TELEGRAM_CHAT_ID", 0)


# ---- the log the CLI holds while it owns the terminal -----------------


def test_the_held_log_is_printed_even_when_the_run_fails(monkeypatch, capsys):
    """Plan 0037 R6: the run that most needs its log used to lose it whole.

    ``_replay`` sat after the ``with`` block and the only ``except``
    around the run caught interrupts, so any other exception carried the
    buffer out of scope unread —— on exactly the runs somebody would be
    trying to diagnose.
    """

    def explode(coroutine, *_args, **_kwargs):
        coroutine.close()  # or the interpreter warns about it at collection
        logging.getLogger("omicsclaw.test").error("the last thing that happened")
        raise RuntimeError("and then this")

    monkeypatch.setattr(_surfaces.asyncio, "run", explode)

    with pytest.raises(RuntimeError, match="and then this"):
        _surfaces.start_cli([], [], {})

    assert "the last thing that happened" in capsys.readouterr().err


def test_an_empty_log_prints_nothing(capsys):
    _replay(io.StringIO())

    assert capsys.readouterr().err == ""


def test_only_the_tail_of_a_long_log_is_printed(capsys):
    _replay(io.StringIO("x" * (_surfaces._LOG_TAIL_CHARS + 500)))

    assert len(capsys.readouterr().err) == _surfaces._LOG_TAIL_CHARS


def test_replaying_something_with_no_records_is_not_an_error(capsys):
    """``start_cli``'s ``finally`` can be reached before the buffer exists."""
    _replay(None)

    assert capsys.readouterr().err == ""


# ---- the CLI's two exits: end of input, and Ctrl-C --------------------


class _Source:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _App:
    """Barely an app: what ``_run_cli`` touches and nothing else."""

    def __init__(self) -> None:
        self.closed = 0
        self.skills = type("Skills", (), {"names": staticmethod(lambda: ())})()

    async def aclose(self) -> None:
        self.closed += 1


def _cli_doubles(monkeypatch, repl_class) -> tuple[_App, _Source]:
    app, source = _App(), _Source()

    async def open_app(_config):
        return app

    monkeypatch.setattr(_surfaces, "open_app", open_app)
    monkeypatch.setattr(_surfaces, "attach_sessions", lambda given: given)
    monkeypatch.setattr(_surfaces, "open_prompt_source", lambda _names: source)
    monkeypatch.setattr(_surfaces, "Screen", lambda *a, **k: None)
    monkeypatch.setattr(_surfaces, "Repl", repl_class)
    return app, source


def test_the_prompt_source_is_closed_when_the_repl_is_interrupted(monkeypatch):
    """Plan 0037 G5. ``Ctrl-C`` is how a REPL ordinarily ends.

    ``source.close()`` was the statement *after* ``await repl.run()``,
    so the ordinary ending jumped over it: ``prompt_toolkit``'s history
    file unflushed and its terminal state unrestored, on the path most
    sessions take.
    """

    class Interrupted:
        def __init__(self, *_a, **_k) -> None:
            pass

        def welcome(self) -> None:
            pass

        async def run(self) -> None:
            raise asyncio.CancelledError

    app, source = _cli_doubles(monkeypatch, Interrupted)
    code = asyncio.run(_surfaces._run_cli(object(), _surfaces.ReplOptions()))

    assert code == 130
    assert source.closed == 1
    assert app.closed == 1


def test_the_prompt_source_is_closed_on_the_ordinary_ending_too(monkeypatch):
    """Or the fix above could have been "close it in the except"."""

    class Finished:
        def __init__(self, *_a, **_k) -> None:
            pass

        def welcome(self) -> None:
            pass

        async def run(self) -> None:
            return None

    app, source = _cli_doubles(monkeypatch, Finished)

    assert asyncio.run(_surfaces._run_cli(object(), _surfaces.ReplOptions())) == EXIT_OK
    assert source.closed == 1
    assert app.closed == 1


class _SlowToClose:
    """An app whose release has three observable steps."""

    def __init__(self) -> None:
        self.steps: list[str] = []

    async def aclose(self) -> None:
        self.steps.append("sessions")
        await asyncio.sleep(0.02)
        self.steps.append("mcp")
        await asyncio.sleep(0.02)
        self.steps.append("sandbox")


def test_a_second_interrupt_does_not_cut_the_release_in_half():
    """Plan 0037 G4: an orphaned container reported as a clean ``130``.

    The first ``Ctrl-C`` ends the loop and the release begins; a second
    one from somebody who thinks nothing is happening used to land
    *inside* ``AgentApp.aclose`` —— between stopping the MCP children
    and removing the sandbox container —— and the shell still reported
    130. :func:`asyncio.shield` moves the cancellation to the caller's
    ``await``, so the close runs to its end.
    """

    async def scenario():
        app = _SlowToClose()
        task = asyncio.current_task()
        asyncio.get_running_loop().call_later(0.01, task.cancel)
        released = await _surfaces._release(app)
        return released, app.steps

    released, steps = asyncio.run(scenario())

    assert released is True
    assert steps == ["sessions", "mcp", "sandbox"]


def test_a_release_that_cannot_finish_is_reported_rather_than_claimed():
    """Exactly one extra interrupt is absorbed; the bound is deliberate.

    A shell that cannot be stopped is its own failure, so the third
    ``Ctrl-C`` wins —— and then the exit code must not say the shutdown
    was clean, which is the half of G4 that is about honesty rather than
    about containers.
    """

    async def scenario():
        app = _SlowToClose()
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        loop.call_later(0.005, task.cancel)
        loop.call_later(0.010, task.cancel)
        loop.call_later(0.015, task.cancel)
        return await _surfaces._release(app), app.steps

    released, steps = asyncio.run(scenario())

    assert released is False
    assert steps != ["sessions", "mcp", "sandbox"]


def test_a_truncated_release_is_not_reported_as_a_clean_interrupt(monkeypatch):
    """``_run_cli`` turns that ``False`` into an exit code that is not 130."""

    class Interrupted:
        def __init__(self, *_a, **_k) -> None:
            pass

        def welcome(self) -> None:
            pass

        async def run(self) -> None:
            raise asyncio.CancelledError

    _cli_doubles(monkeypatch, Interrupted)

    async def refuse_to_finish(_app):
        return False

    monkeypatch.setattr(_surfaces, "_release", refuse_to_finish)

    assert asyncio.run(_surfaces._run_cli(object(), _surfaces.ReplOptions())) == (
        EXIT_FAILED
    )


# ---- plan 0037 G6: two flags that cannot both mean anything -----------


@pytest.mark.parametrize("flag", ["--prompt", "--prompt-file"])
def test_a_session_to_continue_and_a_single_exchange_are_refused_together(
    flag, tmp_path
):
    """Silently ignoring one of two flags is the worst of the three options.

    ``run_once`` takes no session, so ``--session`` did nothing at all
    next to ``--prompt`` —— and ``CLI_USAGE`` did not say so, which made
    "it was ignored" indistinguishable from "it was honoured" from the
    outside.
    """
    brief = tmp_path / "brief.md"
    brief.write_text("do the thing\n", encoding="utf-8")
    value = "hi" if flag == "--prompt" else str(brief)

    with pytest.raises(AppConfigError, match="only the REPL"):
        ReplOptions.parse(["--session", "run-7", flag, value])


def test_the_cli_usage_says_which_flag_is_repl_only():
    """A refusal a reader could have avoided by reading the usage."""
    assert "REPL only" in _surfaces.CLI_USAGE


@pytest.mark.parametrize(
    "argv",
    [["--session", "run-7"], ["--prompt", "hi"]],
    ids=["session-alone", "prompt-alone"],
)
def test_either_flag_alone_is_still_accepted(argv):
    assert ReplOptions.parse(argv) is not None


# ---- the REPL's Ctrl-C handler ----------------------------------------


class _Repl:
    """Enough of a REPL for :class:`_interrupts` to talk to."""

    def __init__(self, interruptible: bool) -> None:
        self.interruptible = interruptible
        self.stopped = False
        self.interrupted = 0
        self.state = self

    def interrupt(self) -> bool:
        self.interrupted += 1
        return self.interruptible

    def stop(self) -> None:
        self.stopped = True


def test_a_ctrl_c_during_an_exchange_cancels_only_the_exchange():
    repl = _Repl(interruptible=True)
    task = _NeverCancelled()

    _surfaces._interrupts(repl, task)._fire()  # type: ignore[arg-type]

    assert repl.interrupted == 1
    assert repl.stopped is False
    assert task.cancelled == 0


def test_a_ctrl_c_with_nothing_running_ends_the_loop():
    repl = _Repl(interruptible=False)
    task = _NeverCancelled()

    _surfaces._interrupts(repl, task)._fire()  # type: ignore[arg-type]

    assert repl.stopped is True
    assert task.cancelled == 1


class _NeverCancelled:
    def __init__(self) -> None:
        self.cancelled = 0

    def cancel(self) -> None:
        self.cancelled += 1


def test_removing_a_handler_that_was_never_installed_is_a_no_op():
    """``__exit__`` runs on Windows too, where ``__enter__`` did nothing."""
    guard = _surfaces._interrupts(_Repl(True), None)  # type: ignore[arg-type]

    guard.__exit__()  # no running loop, and nothing was installed


# ---- the signal guard, without a process ------------------------------


def test_a_signal_guard_reports_128_plus_the_first_signal():
    """A second Ctrl-C from an impatient operator must not change the code.

    The task is ``None`` here on purpose: cancelling the task this
    coroutine *is* would end the test rather than exercise the guard.
    Cancellation against a real run loop is asserted in
    ``test_channel_command.py``, on a real process.
    """

    async def scenario() -> tuple[int, bool]:
        with _stop_signals(None) as signals:
            before = signals.exit_code
            signals._fire(signal.SIGTERM)
            signals._fire(signal.SIGINT)
        return signals.exit_code, before == EXIT_OK

    code, was_clean = asyncio.run(scenario())

    assert was_clean
    assert code == 143


def test_a_signal_guard_with_no_signal_reports_success():
    async def scenario() -> int:
        with _stop_signals(None) as signals:
            pass
        return signals.exit_code

    assert asyncio.run(scenario()) == EXIT_OK


def test_the_handlers_are_removed_again():
    """A loop left holding a callback into a finished run is plan 0031 Q22."""

    async def scenario() -> list[int]:
        loop = asyncio.get_running_loop()
        installed: list[int] = []
        original = loop.add_signal_handler
        removed: list[int] = []

        def record(number, callback, *args):
            installed.append(number)
            return original(number, callback, *args)

        loop.add_signal_handler = record  # type: ignore[assignment]
        original_remove = loop.remove_signal_handler

        def record_removal(number):
            removed.append(number)
            return original_remove(number)

        loop.remove_signal_handler = record_removal  # type: ignore[assignment]
        with _stop_signals(None):
            pass
        assert installed == [signal.SIGTERM, signal.SIGINT]
        return removed

    assert asyncio.run(scenario()) == [signal.SIGTERM, signal.SIGINT]


# ---- plan 0037 R3: .env is loaded, and by this layer -------------------


@pytest.fixture
def pristine_environment():
    """Put the process environment back, including keys ``.env`` added.

    ``monkeypatch.setenv`` restores what it set; it cannot restore what
    the code under test set, and adopting a ``.env`` is precisely code
    that sets variables. Without this, one of these tests leaks a
    credential-shaped variable into every test that runs after it.
    """
    import os

    before = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def test_a_dotenv_file_reaches_the_surface(
    tmp_path, monkeypatch, capsys, pristine_environment
):
    """``CLAUDE.md`` teaches ``.env``; until now nothing read it.

    ``entry/config.py`` records the job as this package's and
    ``launch/`` had zero hits for the name, so the documented way to
    configure a channel did nothing at all. Probed through the Feishu
    builder because each missing variable has its own refusal: if the
    file were ignored the message would be the *first* one, and it is
    the second.
    """
    (tmp_path / DOTENV_FILE).write_text(
        "FEISHU_APP_ID=from-the-file\nFEISHU_APP_SECRET=s\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_ALLOWED_SENDERS", raising=False)
    monkeypatch.setattr(sys, "argv", ["oc", "channel", "--", "--channels", "feishu"])

    code = main()
    captured = capsys.readouterr()

    assert code == EXIT_REFUSED
    assert "FEISHU_ALLOWED_SENDERS" in captured.err
    assert "FEISHU_APP_ID and FEISHU_APP_SECRET" not in captured.err


def test_an_exported_variable_beats_the_file(
    tmp_path, monkeypatch, pristine_environment
):
    """``override=False``, like the runner this replaces and like godotenv.

    A file in a developer's checkout must not be able to replace what an
    operator put in a systemd unit —— that is a credential changing
    hands without anybody editing the deployment.

    **Both roots are pinned.** This test used to pin ``root`` only, and
    was red on any checkout that has a real ``.env`` —— the second
    candidate is the working directory, which under pytest is the
    repository itself. A test whose result depends on whether the person
    running it has configured the program is not testing the program.
    """
    (tmp_path / DOTENV_FILE).write_text("OC_PROBE=from-the-file\n", encoding="utf-8")
    monkeypatch.setenv("OC_PROBE", "from-the-operator")

    read = _adopt_dotenv(root=tmp_path, cwd=tmp_path / "nowhere")

    import os

    assert read == (tmp_path / DOTENV_FILE,)
    assert os.environ["OC_PROBE"] == "from-the-operator"


def test_a_missing_dotenv_is_not_an_error(tmp_path):
    """Neither candidate exists, and start-up is not affected."""
    assert _adopt_dotenv(root=tmp_path / "nowhere", cwd=tmp_path / "nowhere") == ()


def test_an_explicit_environment_means_the_file_is_not_read(tmp_path, monkeypatch):
    """``main(argv, env)`` describes a whole deployment, so nothing is added.

    This is what keeps every other test in ``tests/launch/`` hermetic: a
    ``.env`` in the checkout must not be able to change what they see.
    """
    (tmp_path / DOTENV_FILE).write_text("OC_PROBE_TWO=leaked\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["channel", "--", "--list"], {}) == EXIT_OK

    import os

    assert "OC_PROBE_TWO" not in os.environ
