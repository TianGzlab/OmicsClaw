"""The command table, and the one rule for cutting a command line.

Plan 0037 §5.2 and the landing form of its judgement 4 ("入口只有一族,
且这件事是可枚举的"): :data:`COMMANDS` is a three-entry constant whose
keys are exactly the three surfaces, and
``tests/launch/test_grammar.py::test_the_entry_points_are_exactly_three``
turns red before a fourth one can be born. Grepping a tree for module
guards can tell you how many process entry points it has; it cannot
make adding one cost anything.

**The command name is the subpackage name.** ``cli`` / ``desktop`` /
``channel`` map one-to-one onto ``omicsclaw/entry/{cli,desktop,channel}/``
and :attr:`Command.module` records that mapping so a test can check it
rather than a reader having to trust it.

**One cut, two owners.** ``oc <surface> [deployment] -- [surface]``
sends everything left of the terminator to
:func:`~omicsclaw.entry.resolve_app_config` unparsed and everything
right of it to that surface's own parser. Plan 0031 proved the rule on
one surface; this file applies it to three.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from ._surfaces import (
    CHANNEL_USAGE,
    CLI_USAGE,
    DESKTOP_USAGE,
    start_channel,
    start_cli,
    start_desktop,
)

__all__ = [
    "COMMANDS",
    "HELP_FLAGS",
    "TERMINATOR",
    "Command",
    "split_command_line",
    "usage",
]

TERMINATOR = "--"

HELP_FLAGS = frozenset({"--help", "-h"})
"""The only flags this shell reads for itself, and they are not config.

Neither is a field of :class:`~omicsclaw.entry.AppConfig`, so honouring
them here does not give plan 0031 Q8 a second parse point ——
``test_the_shell_names_no_deployment_flag`` derives the deployment flag
set from ``config.py`` itself and asserts this package names none of it.
"""

Starter = Callable[[Sequence[str], Sequence[str], Mapping[str, str]], int]


@dataclass(frozen=True)
class Command:
    """One process entry point: a name, the layer it starts, how to start it."""

    name: str
    module: str
    summary: str
    usage: str
    start: Starter


COMMANDS: Mapping[str, Command] = MappingProxyType(
    {
        "cli": Command(
            name="cli",
            module="omicsclaw.entry.cli",
            summary="terminal REPL, or one exchange with --prompt-file",
            usage=CLI_USAGE,
            start=start_cli,
        ),
        "desktop": Command(
            name="desktop",
            module="omicsclaw.entry.desktop",
            summary="HTTP backend for the OmicsClaw-App client",
            usage=DESKTOP_USAGE,
            start=start_desktop,
        ),
        "channel": Command(
            name="channel",
            module="omicsclaw.entry.channel",
            summary="instant-messaging adapters (Telegram, Feishu, ...)",
            usage=CHANNEL_USAGE,
            start=start_channel,
        ),
    }
)
"""The whole inventory of ways into this program.

Read-only on purpose: a :class:`~types.MappingProxyType` cannot be
mutated at import time by a plugin that would rather not edit this file,
which is how an enumerable set of entry points stops being enumerable.
"""


def split_command_line(tokens: Sequence[str]) -> tuple[list[str], list[str]]:
    """Cut at the first ``--``. A help flag on the left moves right.

    The deployment half is handed to ``resolve_app_config`` unchanged ——
    which would stop at the terminator anyway, and is given the shorter
    list only so that one function does not have to be trusted twice.

    **Why help is hoisted.** Once the command name is fixed there is
    exactly one thing ``--help`` could be asking about, so ``oc cli
    --help`` and ``oc cli -- --help`` mean the same thing and are
    answered by the same code. The alternative —— a second help path in
    this file —— would be a branch the surface parsers can no longer
    reach, and an unreachable branch is how the two answers drift apart.

    **A value is not a request.** The hoist used to lift *every* token
    spelled ``--help`` out of the deployment half, including one that
    was the value of the flag in front of it: ``oc cli --workspace
    --help /data`` became ``--workspace /data`` plus a help screen, so a
    malformed line silently started a differently-configured deployment.
    :func:`_help_in_flag_position` walks the half the way
    ``config.py``'s ``_from_argv`` does —— every deployment flag takes a
    value, inline after ``=`` or as the next token —— so only a token in
    flag position can be asking for help.
    """
    left = list(tokens)
    right: list[str] = []
    if TERMINATOR in left:
        cut = left.index(TERMINATOR)
        left, right = left[:cut], left[cut + 1 :]
    position = _help_in_flag_position(left)
    if position is not None:
        right = right + [left[position]]
        left = left[:position] + left[position + 1 :]
    return left, right


def _help_in_flag_position(deployment: Sequence[str]) -> int | None:
    """Index of the first help flag that is a flag and not somebody's value.

    Mirrors ``omicsclaw/entry/config.py``'s ``_from_argv`` stride: a
    token containing ``=`` carries its own value and advances one, and
    anything else takes the token after it. That coupling is real and is
    the price of answering ``--help`` without a second parser; the day a
    deployment flag takes no value, this stride and
    ``resolve_app_config`` disagree, and
    ``test_a_help_flag_that_is_a_value_is_not_hoisted`` is where it
    shows.
    """
    index = 0
    while index < len(deployment):
        token = deployment[index]
        if token in HELP_FLAGS:
            return index
        index += 1 if "=" in token else 2
    return None


def usage() -> str:
    """The top-level help: the three commands and the shape of a line."""
    lines = [
        "usage: oc <surface> [deployment flags] [-- surface flags]",
        "",
        "Surfaces:",
    ]
    lines.extend(
        f"  {command.name:9s} {command.summary}"
        for command in COMMANDS.values()
    )
    lines.extend(
        [
            "",
            "Deployment flags go before --, and are read by",
            "omicsclaw.entry.resolve_app_config. A surface's own flags go",
            "after it; run `oc <surface> --help` for that list.",
            "",
        ]
    )
    return "\n".join(lines)
