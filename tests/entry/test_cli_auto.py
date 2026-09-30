"""``/auto`` (plan 0050): switch now, save for the next start, keep the guards.

Each test runs a real REPL over a real app with a scripted backend and a
``.env`` under ``tmp_path``. None of them can reach the repository's own
``.env``: the path is always passed in, and
:func:`test_the_repository_dotenv_is_never_touched` checks that anyway.
"""

from __future__ import annotations

import asyncio
import hashlib
import pathlib

import pytest

from omicsclaw.entry.cli import CLI_PERMISSION_MODE_VARIABLE
from omicsclaw.permission import PermissionMode
from omicsclaw.schema import Message, Role
from tests.entry.test_cli_approval_scope import (  # type: ignore[import-not-found]
    Shell,
    _commands,
)
from tests.entry.test_cli_repl import (  # type: ignore[import-not-found]
    WAIT_S,
    build,
    repl_over,
)
from tests.entry.test_turn_runner import Scripted  # type: ignore[import-not-found]

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_EXISTING = "# a comment\nLLM_API_KEY=sk-keep-me\nUNKNOWN=leave-me\n"


def _run(tmp_path, commands, lines, *, dotenv=True, existing=_EXISTING, **kwargs):
    """A REPL reading *lines*; returns prompts, output, the tool, the app."""
    shell = Shell()
    path = tmp_path / ".env" if dotenv else None
    if path is not None and existing is not None:
        path.write_text(existing, encoding="utf-8")
    overrides = kwargs.pop("overrides", {})

    async def drive():
        app = build(tmp_path, _commands(*commands), tools=(shell,), **overrides)
        repl, source, buffer = repl_over(
            app, [*lines, "/exit"], dotenv_path=path, **kwargs
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        mode = app.permission.mode if app.permission is not None else None
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return source.prompts, buffer.getvalue(), mode

    prompts, printed, mode = asyncio.run(drive())
    asked = [one for one in prompts if one.startswith("approve shell [")]
    return asked, printed, shell, mode, path


# ---- now --------------------------------------------------------------


def test_auto_stops_the_questions_at_once(tmp_path):
    asked, printed, shell, mode, _ = _run(
        tmp_path, ["ls -la", "pwd"], ["/auto", "go"]
    )

    assert asked == []
    assert shell.ran == ["ls -la", "pwd"]
    assert mode is PermissionMode.AUTO_APPROVE
    assert "Auto-approve is on" in printed


def test_auto_off_brings_them_back(tmp_path):
    asked, _printed, shell, mode, _ = _run(
        tmp_path, ["ls -la"], ["/auto", "/auto off", "go", "y"]
    )

    assert len(asked) == 1
    assert shell.ran == ["ls -la"]
    assert mode is PermissionMode.DEFAULT


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/x",
        "echo OMICSCLAW_PERMISSION_MODE=bypass-all >> .env",
        "echo x > .omicsclaw/settings.json",
    ],
)
def test_what_is_always_asked_is_still_asked(tmp_path, command):
    """The whole of what makes ``/auto`` tolerable: the model cannot use it
    to switch the gate off for the next start, and a pattern still stops."""
    asked, _printed, shell, _mode, _ = _run(tmp_path, [command], ["/auto", "go", "n"])

    assert len(asked) == 1
    assert shell.ran == []


# ---- the next start ---------------------------------------------------


def test_the_setting_is_saved_for_the_cli_and_nothing_else_moves(tmp_path):
    _asked, _printed, _shell, _mode, path = _run(tmp_path, [], ["/auto"])

    text = path.read_text(encoding="utf-8")
    assert f"{CLI_PERMISSION_MODE_VARIABLE}=auto-approve" in text
    assert text.startswith(_EXISTING)
    assert "OMICSCLAW_PERMISSION_MODE=" not in text.replace(
        CLI_PERMISSION_MODE_VARIABLE, ""
    )


def test_off_writes_default_explicitly(tmp_path):
    """Deleting the key could let a second ``.env`` decide instead."""
    _asked, _printed, _shell, _mode, path = _run(
        tmp_path, [], ["/auto", "/auto off"]
    )

    assert f"{CLI_PERMISSION_MODE_VARIABLE}=default" in path.read_text("utf-8")


def test_switching_leaves_no_backups_behind(tmp_path):
    """Every backup is another copy of every key in the file."""
    _run(tmp_path, [], ["/auto", "/auto off", "/auto"])

    assert not list(tmp_path.glob(".env.backup-*"))
    assert not list(tmp_path.glob("*.partial"))


def test_a_promise_in_the_file_is_not_overwritten(tmp_path):
    existing = f"{CLI_PERMISSION_MODE_VARIABLE}=read-only\n"
    _asked, printed, _shell, _mode, path = _run(
        tmp_path, [], ["/auto"], existing=existing
    )

    assert path.read_text("utf-8") == existing
    assert "Not saved" in printed


def test_with_nowhere_to_save_it_still_switches_and_says_so(tmp_path):
    _asked, printed, _shell, mode, _ = _run(tmp_path, [], ["/auto"], dotenv=False)

    assert mode is PermissionMode.AUTO_APPROVE
    assert "no .env to save to" in printed


def test_a_failed_save_keeps_the_switch(tmp_path):
    """The rule ``a`` follows: a save that failed does not undo consent."""
    shell = Shell()
    missing = tmp_path / "no-such-directory" / ".env"

    async def drive():
        app = build(tmp_path, _commands(), tools=(shell,))
        repl, _source, buffer = repl_over(app, ["/auto", "/exit"], dotenv_path=missing)
        await asyncio.wait_for(repl.run(), WAIT_S)
        mode = app.permission.mode
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue(), mode

    printed, mode = asyncio.run(drive())

    assert mode is PermissionMode.AUTO_APPROVE
    assert "Could not save" in printed


def test_being_outranked_at_the_next_start_is_reported(tmp_path):
    _asked, printed, _shell, _mode, _ = _run(
        tmp_path, [], ["/auto"], permission_mode_source="flag"
    )

    assert "--permission-mode flag" in printed


# ---- what it refuses --------------------------------------------------


@pytest.mark.parametrize(
    "started", [PermissionMode.READ_ONLY, PermissionMode.BYPASS_ALL]
)
@pytest.mark.parametrize("line", ["/auto", "/auto off"])
def test_a_deployment_promise_is_not_switched_or_saved(tmp_path, started, line):
    _asked, printed, _shell, mode, path = _run(
        tmp_path, [], [line], overrides={"permission_mode": started}
    )

    assert mode is started
    assert path.read_text("utf-8") == _EXISTING
    assert "restart with --permission-mode" in printed


@pytest.mark.parametrize("line", ["/auto of", "/auto yes", "/auto please"])
def test_an_argument_it_does_not_know_changes_nothing(tmp_path, line):
    """Fail closed: ``/auto of`` must not read as "on"."""
    _asked, printed, _shell, mode, path = _run(tmp_path, [], [line])

    assert mode is PermissionMode.DEFAULT
    assert path.read_text("utf-8") == _EXISTING
    assert "usage: /auto" in printed


# ---- at the approval prompt -------------------------------------------


def test_auto_typed_at_a_card_switches_and_allows_that_call(tmp_path):
    """What the legend promises, where the person reads it."""
    asked, printed, shell, mode, _ = _run(
        tmp_path, ["ls -la", "pwd"], ["go", "/auto"]
    )

    assert len(asked) == 1
    assert shell.ran == ["ls -la", "pwd"]
    assert mode is PermissionMode.AUTO_APPROVE
    assert "/auto stops these" in printed


def test_auto_typed_at_an_always_asked_card_asks_that_card_again(tmp_path):
    asked, _printed, shell, mode, _ = _run(
        tmp_path, ["rm -rf /tmp/x"], ["go", "/auto", "n"]
    )

    assert len(asked) == 2
    assert shell.ran == []
    assert mode is PermissionMode.AUTO_APPROVE


def test_another_command_at_a_card_denies_without_telling_the_model_it(tmp_path):
    asked, printed, shell, _mode, _ = _run(tmp_path, ["ls -la"], ["go", "/usage"])

    assert len(asked) == 1
    assert shell.ran == []
    assert "denied at the terminal" in printed
    assert ": /usage" not in printed


def test_the_legend_offers_auto_only_where_it_would_help(tmp_path):
    _asked, printed, _shell, _mode, _ = _run(
        tmp_path, ["rm -rf /tmp/x"], ["go", "n"]
    )

    assert "this call is always asked about" in printed
    assert "/auto stops these" not in printed


# ---- reporting --------------------------------------------------------


def test_current_reports_the_live_mode(tmp_path):
    _asked, printed, _shell, _mode, _ = _run(tmp_path, [], ["/auto", "/current"])

    assert "permissions: auto-approve" in printed


def test_status_reports_without_changing_anything(tmp_path):
    _asked, printed, _shell, mode, path = _run(tmp_path, [], ["/auto status"])

    assert mode is PermissionMode.DEFAULT
    assert path.read_text("utf-8") == _EXISTING
    assert "Permissions now: default" in printed


def test_auto_is_on_the_menu(tmp_path):
    _asked, printed, _shell, _mode, _ = _run(tmp_path, [], ["/help"])

    assert "/auto" in printed


# ---- the guard this whole file runs under -----------------------------


def test_the_repository_dotenv_is_never_touched(tmp_path):
    live = _REPO_ROOT / ".env"
    before = hashlib.md5(live.read_bytes()).hexdigest() if live.exists() else None

    _run(tmp_path, [], ["/auto", "/auto off", "/auto status"])

    after = hashlib.md5(live.read_bytes()).hexdigest() if live.exists() else None
    assert after == before


# ---- the app enforces the transitions, not only the REPL --------------


def test_the_app_refuses_what_the_repl_would_refuse(tmp_path):
    app = build(tmp_path, Scripted(Message(role=Role.ASSISTANT, content="x")))
    try:
        with pytest.raises(ValueError):
            app.set_permission_mode(PermissionMode.READ_ONLY)
        assert app.set_permission_mode(PermissionMode.AUTO_APPROVE) is (
            PermissionMode.DEFAULT
        )
        assert app.permission.mode is PermissionMode.AUTO_APPROVE
    finally:
        asyncio.run(asyncio.wait_for(app.aclose(), WAIT_S))



# ---- review of the implementation (2026-09-23) --------------------------


def test_always_is_not_offered_where_no_rule_can_reach(tmp_path):
    """A change to ``.omicsclaw/`` is decided before any rule is read, so an
    ``allow`` rule written for it would say "Remembered" and do nothing."""
    command = "echo x > .omicsclaw/notes.txt"
    asked, printed, shell, _mode, _ = _run(
        tmp_path, [command, command], ["go", "a", "n"]
    )

    assert len(asked) == 2
    assert shell.ran == [command]
    assert "no rule can change that" in printed
    assert "Remembered" not in printed
    settings = tmp_path / ".omicsclaw" / "settings.json"
    assert not settings.exists() or "allow" not in settings.read_text("utf-8")


def test_a_failure_while_switching_at_a_card_still_settles_it(tmp_path, monkeypatch):
    """``_ask`` answers on every path; a broken switch asks the card again."""
    from omicsclaw.entry.assembly import AgentApp

    def boom(self, mode):
        raise RuntimeError("symlink loop")

    monkeypatch.setattr(AgentApp, "set_permission_mode", boom)

    asked, printed, shell, _mode, _ = _run(tmp_path, ["ls -la"], ["go", "/auto", "y"])

    assert len(asked) == 2
    assert shell.ran == ["ls -la"]
    assert "/auto failed" in printed


def test_status_survives_a_file_it_cannot_decode(tmp_path):
    shell = Shell()
    path = tmp_path / ".env"
    path.write_bytes(b"LLM_API_KEY=\xff\xfe\n")

    async def drive():
        app = build(tmp_path, _commands(), tools=(shell,))
        repl, _source, buffer = repl_over(
            app, ["/auto status", "/exit"], dotenv_path=path
        )
        await asyncio.wait_for(repl.run(), WAIT_S)
        await asyncio.wait_for(app.aclose(), WAIT_S)
        return buffer.getvalue()

    printed = asyncio.run(drive())

    assert "unreadable" in printed
    assert "Goodbye" in printed


def test_the_legend_offers_auto_only_in_default(tmp_path):
    for started, offered in (
        (PermissionMode.DEFAULT, True),
        (PermissionMode.AUTO_APPROVE, False),
    ):
        app = build(
            tmp_path,
            Scripted(Message(role=Role.ASSISTANT, content="x")),
            permission_mode=started,
        )
        repl, _source, _buffer = repl_over(app, [])
        try:
            assert ("/auto stops these" in repl._approval_legend(False)) is offered
        finally:
            asyncio.run(asyncio.wait_for(app.aclose(), WAIT_S))


def test_being_outranked_by_the_general_key_is_reported(tmp_path):
    _asked, printed, _shell, _mode, _ = _run(
        tmp_path, [], ["/auto"], permission_mode_source="environment"
    )

    assert "OMICSCLAW_PERMISSION_MODE (set in the environment or .env" in printed


def test_a_promise_is_recognised_in_any_letter_case(tmp_path):
    existing = f"{CLI_PERMISSION_MODE_VARIABLE}=READ-ONLY\n"
    _asked, printed, _shell, _mode, path = _run(
        tmp_path, [], ["/auto"], existing=existing
    )

    assert path.read_text("utf-8") == existing
    assert "Not saved" in printed
