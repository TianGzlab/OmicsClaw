"""``OMICSCLAW_CLI_PERMISSION_MODE``: the CLI's own key, and its place (plan 0050 §2).

Precedence for ``oc cli``, most deliberate first: the ``--permission-mode``
flag, ``OMICSCLAW_PERMISSION_MODE`` from anywhere, the CLI's own key, then
``default``. The other two surfaces never read the CLI's key —— that is the
whole reason it exists: ``/auto`` at a terminal must not make an unattended
Channel bot approve what it used to refuse.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from omicsclaw.entry import resolve_app_config
from omicsclaw.entry.cli import CLI_PERMISSION_MODE_VARIABLE
from omicsclaw.entry.config import AppConfigError
from omicsclaw.launch import main
from omicsclaw.launch._surfaces import (
    _permission_mode_source,
    _with_the_cli_permission_mode,
)
from omicsclaw.permission import PermissionMode

_GENERAL = "OMICSCLAW_PERMISSION_MODE"


def _mode(argv, env) -> PermissionMode:
    return resolve_app_config(argv, _with_the_cli_permission_mode(env)).permission_mode


def test_the_cli_key_alone_decides():
    env = {CLI_PERMISSION_MODE_VARIABLE: "auto-approve"}

    assert _mode([], env) is PermissionMode.AUTO_APPROVE
    assert _permission_mode_source([], env) == "cli-key"


def test_the_general_key_outranks_it():
    env = {CLI_PERMISSION_MODE_VARIABLE: "auto-approve", _GENERAL: "default"}

    assert _mode([], env) is PermissionMode.DEFAULT
    assert _permission_mode_source([], env) == "environment"


def test_the_flag_outranks_both():
    env = {CLI_PERMISSION_MODE_VARIABLE: "auto-approve"}
    argv = ["--permission-mode", "default"]

    assert _mode(argv, env) is PermissionMode.DEFAULT
    assert _permission_mode_source(argv, env) == "flag"


def test_nothing_set_is_the_default():
    assert _mode([], {}) is PermissionMode.DEFAULT
    assert _permission_mode_source([], {}) == ""


def test_a_bad_value_is_refused_under_its_own_name():
    with pytest.raises(AppConfigError, match=CLI_PERMISSION_MODE_VARIABLE):
        _with_the_cli_permission_mode({CLI_PERMISSION_MODE_VARIABLE: "yolo"})


def test_the_caller_s_mapping_is_not_mutated():
    env = {CLI_PERMISSION_MODE_VARIABLE: "auto-approve"}
    _with_the_cli_permission_mode(env)

    assert env == {CLI_PERMISSION_MODE_VARIABLE: "auto-approve"}


def _code(argv, env) -> int:
    quiet = io.StringIO()
    with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        return main(argv, env)


def test_only_the_cli_reads_it():
    """A value only the CLI would refuse: the Channel does not look at it."""
    env = {CLI_PERMISSION_MODE_VARIABLE: "yolo"}

    assert _code(["cli", "--help"], env) == 2
    assert _code(["channel", "--list"], env) == 0
    assert _code(["desktop", "--help"], env) == 0


def test_a_bad_value_is_refused_even_when_outranked():
    """A typo is loud whether or not it would have counted —— the rule every
    other deployment setting follows."""
    env = {CLI_PERMISSION_MODE_VARIABLE: "yolo", _GENERAL: "default"}

    with pytest.raises(AppConfigError, match=CLI_PERMISSION_MODE_VARIABLE):
        _with_the_cli_permission_mode(env)
