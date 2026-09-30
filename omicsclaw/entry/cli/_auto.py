"""``/auto``: the terminal's switch between asking and not asking (plan 0050).

Two halves, because the owner's requirement was "the same as editing
``.env``" and editing ``.env`` alone takes a restart:

- *now*: :meth:`~omicsclaw.entry.AgentApp.set_permission_mode` moves the one
  permission gate this process has, so the next tool call already runs under
  the new mode;
- *next start*: :data:`CLI_PERMISSION_MODE_VARIABLE` is written to the
  ``.env`` the shell reads.

The key is the CLI's own and not ``OMICSCLAW_PERMISSION_MODE``, because all
three surfaces read ``.env``, and a switch typed at a terminal must not make
an unattended Channel bot start approving what it used to refuse on a
timeout. This module owns the name; :mod:`omicsclaw.launch` imports it,
since that is the direction the two layers may depend on each other in.

What stays asked in ``auto-approve`` is the gate's business, not this
module's: dangerous commands, explicit ``ask`` rules, and any change to
``.omicsclaw/`` or a ``.env`` —— including the one this module writes.
"""

from __future__ import annotations

from pathlib import Path

from omicsclaw.permission import PermissionMode

from ._configure import read_dotenv, write_dotenv

__all__ = [
    "AUTO_USAGE",
    "CLI_PERMISSION_MODE_VARIABLE",
    "auto_action",
    "is_auto_answer",
    "persist_cli_mode",
    "saved_cli_mode",
]

CLI_PERMISSION_MODE_VARIABLE = "OMICSCLAW_CLI_PERMISSION_MODE"
"""The permission mode for ``oc cli`` only, below the flag and below
``OMICSCLAW_PERMISSION_MODE`` in precedence (see
``omicsclaw/launch/_surfaces.py``)."""

AUTO_USAGE = "usage: /auto [on|off|status]"

_ACTIONS = {"": "on", "on": "on", "off": "off", "status": "status"}

_PROMISES = frozenset({PermissionMode.READ_ONLY, PermissionMode.BYPASS_ALL})
"""Modes a person wrote down as a deployment promise, not a convenience.

``/auto`` refuses to overwrite either in the file, for the same reason
:meth:`~omicsclaw.entry.AgentApp.set_permission_mode` refuses to leave either
at run time."""


def auto_action(argument: str) -> str | None:
    """``"on"``, ``"off"``, ``"status"``, or ``None`` for anything else.

    Fails closed: a typo is refused rather than read as "on". ``/auto of``
    turning auto-approve *on* would be the worst available reading of a
    command whose only other meaning is the opposite.
    """
    return _ACTIONS.get(argument.strip().casefold())


def is_auto_answer(answer: str) -> bool:
    """Whether an approval prompt was answered with ``/auto``."""
    return answer.strip().casefold() in {"/auto", "/auto on"}


def saved_cli_mode(path: Path | None) -> str:
    """What the ``.env`` says for the CLI, or ``""`` when nothing does."""
    if path is None:
        return ""
    return read_dotenv(path).get(CLI_PERMISSION_MODE_VARIABLE, "").strip()


def persist_cli_mode(path: Path, mode: PermissionMode) -> str:
    """Write *mode* for the CLI to *path*. Returns what to tell the person.

    ``off`` writes ``default`` explicitly rather than deleting the key: the
    shell reads up to two ``.env`` files and the first one to set a key
    wins, so a deletion here can let a value in the other file through.

    Raises :exc:`OSError` or :exc:`ValueError` when the file cannot be read
    or written; the caller reports it and keeps the switch it already made.
    """
    current = saved_cli_mode(path)
    if current:
        try:
            promised = PermissionMode(current.lower())
        except ValueError:
            promised = None
        if promised in _PROMISES:
            return (
                f"Not saved: {path} sets {CLI_PERMISSION_MODE_VARIABLE}="
                f"{current}, a setting somebody chose deliberately. Edit the "
                "file to change it."
            )
    write_dotenv(path, {CLI_PERMISSION_MODE_VARIABLE: mode.value}, backup=False)
    return f"Saved {CLI_PERMISSION_MODE_VARIABLE}={mode.value} to {path}."
