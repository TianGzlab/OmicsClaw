"""The three surfaces, started the same way: read flags, call a factory.

Plan 0037 §5.1, and the file that makes its judgement 3 ("三个面对称")
true rather than aspirational. Every function here has the same shape ——
parse this surface's half of the command line, hand the deployment half
to :func:`~omicsclaw.entry.resolve_app_config` unparsed, assemble, run,
close —— so that no facade is a process while the other two are
libraries.

**Nothing below is imported privately.** Only public names of
``omicsclaw.entry`` and its three public subpackages are used, which is
plan 0037 §5.1's rule for this file and is pinned by
``tests/launch/test_launch_is_above_entry.py``. The reverse arrow ——
``entry`` importing ``launch`` —— is what that probe exists to refuse.

**The environment arrives as an argument.** ``env`` is a
:class:`~typing.Mapping` handed down from :func:`omicsclaw.launch.main`,
which is the only module in this package that names the live process
environment at all —— this one never does. That is what lets a test
describe a whole deployment, credentials included, without touching the
process it runs in —— and it is why the channel credentials are read
here rather than in :mod:`omicsclaw.entry.channel`: **which** variables
name a Telegram bot is a property of a deployment, and a deployment is
what a process shell owns (plan 0037 §2 problem 1).

**Optional dependencies stay inside the function that needs them.**
``uvicorn``, ``fastapi`` and the seven adapter modules this file can
build are imported in plainly visible ``import`` syntax inside a factory,
never at module scope, so ``import omicsclaw.launch`` costs none of them
and a dependency scanner can still see them (plan 0031 trap 13). The
*platform* SDKs are not named here at all: an adapter module owns
its own SDK import —— lazily, inside the method that first needs a
client —— and which adapter module to load is resolved by
:func:`~omicsclaw.entry.channel.get_channel_class` through
:func:`importlib.import_module`, in ``entry`` where the registry lives
and not in this shell. What this file must do is turn the resulting
:exc:`ImportError`, which surfaces during start-up rather than at
import, into :exc:`MissingSurfaceDependency` rather than a traceback.

**A signal is part of being a process, so it is handled here.** The
channel surface is the one long-lived process of the three, and
``SIGTERM`` is how a container asks it to stop. :class:`_stop_signals`
turns both ``SIGTERM`` and ``SIGINT`` into an orderly shutdown of the
same shape and reports which one arrived, because ``128 + signum`` is
the only thing a supervisor can read. The CLI uses the same class for
``SIGTERM`` and ``SIGHUP``, and :class:`_interrupts` for ``SIGINT``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import stat
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from omicsclaw.entry import (
    AppConfigError,
    attach_sessions,
    fields_set_by_argv,
    inert_prose,
    open_app,
    resolve_app_config,
)
from omicsclaw.entry.channel import (
    CHANNEL_REGISTRY,
    ChannelManager,
    compose_channel_runtime,
    get_channel_class,
)
from omicsclaw.entry.cli import (
    CLI_PERMISSION_MODE_VARIABLE,
    Repl,
    Screen,
    missing_credential_hint,
    open_prompt_source,
    run_configuration_wizard,
    run_once,
    terminal_owned_logging,
)
from omicsclaw.entry.desktop import DotenvSettings, create_desktop_app
from omicsclaw.permission import PermissionMode

from ._dotenv import LaunchEnvironment, dotenv_candidates, dotenv_target

__all__ = [
    "CHANNEL_FLAGS",
    "CHANNEL_USAGE",
    "CLI_FLAGS",
    "CLI_USAGE",
    "DESKTOP_FLAGS",
    "DESKTOP_USAGE",
    "EXIT_FAILED",
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_REFUSED",
    "EXIT_TERMINATED",
    "ChannelOptions",
    "DesktopOptions",
    "MissingSurfaceDependency",
    "ReplOptions",
    "start_channel",
    "start_cli",
    "start_desktop",
]

logger = logging.getLogger("omicsclaw.launch")

_HELP_FLAGS = ("--help", "-h")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
EXIT_INTERRUPTED = 130
EXIT_TERMINATED = 143
"""The exit codes, written once and read by both files in this package.

``130`` and ``143`` are ``128 + signum`` for ``SIGINT`` and ``SIGTERM``,
the convention every supervisor already reads. ``oc cli`` stopped by
``SIGHUP`` exits ``129`` by the same rule, computed by
:attr:`_stop_signals.exit_code` rather than named here. They are two numbers and
not one because "the operator stopped it" and "somebody pressed Ctrl-C
at a terminal" are different events, and a process that reports ``0``
for either —— which is what this shell did before plan 0037's review ——
tells its supervisor it finished the work.
"""


# ---- which half of the command line owns which flag -------------------


_HELP_ARITY: Mapping[str, int] = MappingProxyType(
    {flag: 0 for flag in _HELP_FLAGS}
)
"""``--help`` and ``-h``, in the shape the three flag tables want them.

Derived rather than retyped: this package already spells the help flags
twice (here and :data:`omicsclaw.launch._grammar.HELP_FLAGS`, which
``tests/launch/test_grammar.py`` imports by that name), and a third copy
is how the surfaces start disagreeing about what ``-h`` is.
"""


def _split_inline(token: str) -> tuple[str, str]:
    """``--session=run-7`` to its flag and its value, ``_from_argv``-style.

    An empty value —— ``--session=`` —— is *not* a value, which is the
    one subtlety :func:`flag_stride` turns on: the flag goes on to take
    the token after it.
    """
    flag, _separator, inline = token.partition("=")
    return flag, inline


def _refuse_a_value(flag: str, inline: str) -> None:
    """``--configure=yes`` is a mistake, and a silent one if unrefused."""
    if inline:
        raise AppConfigError(f"{flag} takes no value")


def flag_stride(tokens: Sequence[str], index: int) -> int:
    """Index of the next token in flag position, from a flag at *index*.

    The one walk over a deployment half, shared by
    :func:`_claim_surface_flags` here and
    :func:`~omicsclaw.launch._grammar._help_in_flag_position` there, so
    that the two cannot disagree about whether a token is a flag or the
    value of the flag in front of it.

    It mirrors ``omicsclaw/entry/config.py``'s ``_from_argv``: every
    deployment flag takes a value, carried inline after ``=`` or taken
    from the next token. **Inline means non-empty** —— ``--workspace=``
    goes on to eat the token after it, exactly as ``_from_argv``'s ``if
    inline:`` does. The grammar used to test ``"=" in token`` instead,
    which made ``oc cli --workspace= --help`` hoist a ``--help`` that
    ``resolve_app_config`` would have read as a workspace named
    ``--help``: two readers, two answers, one command line.

    The coupling to ``config.py`` is real and is the price of answering
    ``--help`` —— and now of claiming a surface flag —— without a second
    deployment parser. The day a deployment flag takes no value, this
    function and ``resolve_app_config`` disagree, and
    ``test_a_help_flag_that_is_a_value_is_not_hoisted`` is where it
    shows.
    """
    _flag, inline = _split_inline(tokens[index])
    return index + 1 if inline else index + 2


def _claim_surface_flags(
    deployment: Sequence[str], owned: Mapping[str, int]
) -> tuple[list[str], list[str]]:
    """Take this surface's own flags out of the deployment half.

    Returns ``(what is left for the deployment, what this surface
    claimed)``. ``oc cli --configure`` and ``oc cli -- --configure``
    therefore mean the same thing, without the cut in
    :func:`~omicsclaw.launch._grammar.split_command_line` acquiring an
    exception: a flag's owner is not a property of which side of ``--``
    it was typed on. The two flag families are disjoint —— pinned by
    ``test_the_surface_flags_and_the_deployment_flags_do_not_overlap``
    —— so claiming cannot take a flag ``resolve_app_config`` wanted, and
    plan 0031 Q8's one-reader rule survives intact.

    **Nothing here raises.** A claimed flag that is missing its value is
    claimed anyway and refused by this surface's own parser; an unknown
    deployment flag is left where it is and refused by ``_from_argv``.
    Both messages already exist, and a third refusal site would be a
    third wording of them.

    **A value is not a flag.** The walk is :func:`flag_stride`'s, so
    ``oc cli --workspace --configure /data`` claims nothing: that
    ``--configure`` is the workspace's value, however little sense it
    makes as one. The unknown-flag case strides the same way rather than
    refusing, which is the one deliberate difference from ``_from_argv``
    —— this function may not know the deployment's flag set (a surface
    that named one would be plan 0031 Q8's second reader) —— and it is
    what keeps ``oc cli --bogus --configure`` a refusal about
    ``--bogus``.

    **What ``--`` still buys.** A value that is spelled like a flag, and
    above all a value that *is* a deployment flag: ``oc cli --prompt
    --workspace /data`` claims ``--workspace`` as the prompt's text.
    That cannot be detected from here for the reason above, so the
    terminator remains the way to say it: ``oc cli -- --prompt
    --workspace``.
    """
    tokens = list(deployment)
    kept: list[str] = []
    claimed: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":  # only reachable when called directly
            kept.extend(tokens[index:])
            break
        flag, inline = _split_inline(token)
        arity = owned.get(flag)
        if arity is None:
            following = flag_stride(tokens, index)
            kept.extend(tokens[index:following])
            index = following
            continue
        if inline:
            claimed.extend((flag, inline))
            index += 1
        elif arity and index + 1 < len(tokens):
            claimed.extend((flag, tokens[index + 1]))
            index += 2
        else:
            claimed.append(token)
            index += 1
    return kept, claimed


CLI_USAGE = """\
usage: oc cli [deployment flags] [-- surface flags]

Deployment flags are read by omicsclaw.entry.resolve_app_config; run it
with an unknown one to see the list it refuses. The system prompt's
front matter is a deployment flag and is called --system-prompt-file.

Surface flags, which may be written before or after --. Write them
after it when a value is spelled like a flag (oc cli -- --prompt
--model):
  --session <id>     REPL only: conversation to continue, a fresh one by
                     default. Refused together with --prompt, which is
                     one exchange and has no conversation to continue.
  --prompt <text>    answer once and exit, instead of starting the REPL
  --prompt-file <p>  the same, with the whole file as the one message
  --show-reasoning   print the model's reasoning above its answer. On by
                     default in the REPL, and for --prompt when stdout is
                     a terminal, so `> answer.txt` still holds only the
                     answer. This flag forces it on.
  --hide-reasoning   the answer only
  --configure        ask for a provider, a key, a model, an endpoint and
                     a workspace, and write them to the .env this shell
                     loads. Starts no agent, so it is refused together
                     with --session, --prompt and --prompt-file.
  --help             this text
"""

DESKTOP_USAGE = """\
usage: oc desktop [deployment flags] [-- surface flags]

Serves the OmicsClaw-App backend over HTTP: POST /chat/stream,
POST /chat/permission, POST /chat/abort,
POST /chat/session-permission-profile, GET and PUT /workspace,
GET /env/doctor, and GET /health, which publishes the wire contract;
and the management routes GET /skills, GET /skills/{domain}/{name},
GET /mcp/servers, GET and PUT /providers, POST /providers/test and
POST /chat/title. PUT /providers writes the .env this shell loads; a
saved provider takes effect at the next start. GET /files/tree and
GET /files/serve read files inside the workspace, except any path with a
segment that starts with a dot. One process serves one workspace; name it
with the --workspace deployment flag. Deployment flags are read by
omicsclaw.entry.resolve_app_config.

Surface flags, which may be written before or after --:
  --host <address>   interface to bind (default 127.0.0.1)
  --port <number>    port to bind (default 8765)
  --abandon-grace <seconds>
                     how long an exchange keeps running once this server
                     has noticed that nobody is watching it any more,
                     1 to 86400 (default 30). A client that reconnects
                     within it picks the stream up where it left off.
  --help             this text

For a server the desktop app reaches over SSH, start it as
  OMICSCLAW_SKILLS_DIR=<checkout>/skills \\
  oc desktop --workspace <dir> --delta-ring-size 65536 -- --host 127.0.0.1 --port 8765 --abandon-grace 600
Set OMICSCLAW_SKILLS_DIR when <dir> is not the checkout; otherwise
skills are read from <dir>/skills.
A long reply streams hundreds of events a second, so a few seconds
offline can push the point the app resumes from out of the default
2048-event replay ring; 600 seconds of grace covers a dropped Wi-Fi or a
closed lid before the exchange is cancelled.

The bearer token is read from OMICSCLAW_REMOTE_AUTH_TOKEN, not from a
flag: a secret on the command line is a secret in every process listing.
Binding any address but a loopback one without that variable set is
refused rather than served.
"""

CHANNEL_USAGE = """\
usage: oc channel [deployment flags] [-- surface flags]

Runs one or more instant-messaging adapters against one shared agent.
Deployment flags are read by omicsclaw.entry.resolve_app_config; the
per-platform credentials are read from the environment, which is loaded
from .env as well. `.env.example` section 11 is the full per-platform
variable list, and `--list` prints the adapters.

Prefer one platform per process unless you specifically want them to share
a session registry: every channel named here starts or none does, so one
mistyped credential stops the others too.

Surface flags, which may be written before or after --:
  --channels <list>  comma-separated adapters, e.g. telegram,slack
  --health-port <n>  serve a JSON health endpoint on this port
  --verbose          debug logging
  --list             print the adapter registry and exit
  --help             this text
"""

DESKTOP_HOST = "127.0.0.1"
"""Loopback, because :func:`create_desktop_app` defaults to no bearer token.

The Electron client connects to ``127.0.0.1:8765``. A default of
``0.0.0.0`` would put an unauthenticated agent on the network by typing
one word, which is the shape of mistake a default is supposed to prevent.
"""

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", ""})
"""Addresses that reach this machine only, and may therefore go unauthenticated.

``""`` is included because an empty ``--host`` is not a request to serve
the world; the other three are what a person actually types. Everything
else —— a LAN address, a public one, and ``0.0.0.0`` above all —— is
treated as off-machine and is gated on :data:`DESKTOP_TOKEN_VARIABLE`
by :func:`_refuse_an_open_unauthenticated_bind`.

The list is deliberately an allow-list. A deny-list of "dangerous"
addresses is the wrong shape for
:data:`~omicsclaw.entry.assembly.SAFETY_RULES` rule 1: the
question is not whether this spelling is known to be public, it is
whether it is known to be private.
"""

DESKTOP_PORT = 8765

DESKTOP_ABANDON_GRACE_RANGE_S = (1.0, 86_400.0)
"""The seconds ``--abandon-grace`` accepts, both ends included."""

DESKTOP_TOKEN_VARIABLE = "OMICSCLAW_REMOTE_AUTH_TOKEN"
"""Where the bearer token comes from, and why it is not a flag.

A remote deployment of the desktop backend has always been told to set
this variable, so the name is kept. It is read from the
environment and not from ``argv`` because a secret on the command line
is a secret in every process listing on the machine.
"""


class MissingSurfaceDependency(RuntimeError):
    """A surface was asked for and its optional dependency is not installed.

    Separate from :exc:`~omicsclaw.entry.AppConfigError` because the
    command was well formed: nothing the user can retype fixes it, and
    the message has to name the install rather than the usage.
    """


# ---- the CLI surface --------------------------------------------------


CLI_FLAGS: Mapping[str, int] = MappingProxyType(
    {
        **_HELP_ARITY,
        "--configure": 0,
        "--show-reasoning": 0,
        "--hide-reasoning": 0,
        "--session": 1,
        "--prompt": 1,
        "--prompt-file": 1,
    }
)
"""This surface's flags and how many tokens each takes.

What :func:`_claim_surface_flags` reads, and the only place the arities
are written down. :class:`ReplOptions` stays a hand-written parser (see
its docstring), so the two are kept in step by a test rather than by
construction: ``test_the_flag_table_matches_the_parser`` probes every
flag in ``SHELL_FLAGS`` against the parser and compares what it finds
with this table.
"""


class ReplOptions:
    """The terminal surface's half of the command line.

    A hand-written parser and not :mod:`argparse` for one reason that is
    worth the thirty lines: ``argparse`` prints its own message and calls
    :func:`sys.exit`, so a surface flag typo and a deployment flag typo
    would be reported by two different mechanisms with two different
    exit codes. Raising :exc:`AppConfigError` puts both refusals through
    :func:`omicsclaw.launch.main`, which is the only place in the program
    that decides what an exit code is. The flag set is five long and a
    surface that needs more has a design problem before it has a parsing
    problem.
    """

    __slots__ = ("configure", "help", "prompt", "session_id", "show_reasoning")

    def __init__(self) -> None:
        self.session_id = ""
        self.prompt = ""
        self.show_reasoning: bool | None = None
        self.configure = False
        self.help = False

    def shows_reasoning(self, *, stdout_is_terminal: bool) -> bool:
        """Whether this run prints the model's reasoning.

        On unless asked otherwise —— with one exception that is not a
        preference but a promise: ``oc cli --prompt … > answer.txt``
        has always written only the answer to that file, and scripts
        read it. So a one-exchange run whose output is not a terminal
        prints the answer alone unless ``--show-reasoning`` says
        otherwise. The REPL is for a person, and shows it.
        """
        if self.show_reasoning is not None:
            return self.show_reasoning
        return stdout_is_terminal or not self.prompt

    @classmethod
    def parse(cls, argv: Sequence[str]) -> "ReplOptions":
        """Read the tail. Raises :exc:`AppConfigError` on anything unknown.

        The same exception type the deployment half raises, so the shell
        has one failure to report and the user sees one kind of message
        whichever side of ``--`` the typo was on.

        ``--session=run-7`` is read as well as ``--session run-7``,
        because a deployment flag has always accepted both and this half
        of the line is now reachable from the deployment side too: one
        spelling answered on one side of ``--`` and refused on the other
        would be a second inconsistency in the place the first was fixed.
        """
        options = cls()
        tokens = list(argv)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            flag, inline = _split_inline(token)
            if flag in _HELP_FLAGS:
                _refuse_a_value(flag, inline)
                options.help = True
                continue
            if flag in ("--show-reasoning", "--hide-reasoning"):
                _refuse_a_value(flag, inline)
                shown = flag == "--show-reasoning"
                if options.show_reasoning is (not shown):
                    raise AppConfigError(
                        "--show-reasoning and --hide-reasoning contradict "
                        "each other"
                    )
                options.show_reasoning = shown
                continue
            if flag == "--configure":
                _refuse_a_value(flag, inline)
                options.configure = True
                continue
            if flag in ("--session", "--prompt", "--prompt-file"):
                if inline:
                    value = inline
                elif index >= len(tokens):
                    raise AppConfigError(f"{flag} needs a value")
                else:
                    value = tokens[index]
                    index += 1
                if flag == "--session":
                    options.session_id = value
                elif flag == "--prompt":
                    options.prompt = value
                else:
                    options.prompt = _read_prompt_file(Path(value))
                continue
            raise AppConfigError(f"unknown surface option {token!r}")
        if options.session_id and options.prompt:
            raise AppConfigError(
                "--session names a conversation to continue and only the REPL "
                "has one; --prompt / --prompt-file is a single exchange"
            )
        if options.configure and (options.session_id or options.prompt):
            raise AppConfigError(
                "--configure writes the deployment's .env and starts no agent, "
                "so there is no session to continue and no exchange to run"
            )
        return options


def _stdout_is_a_terminal() -> bool:
    """Whether the answer is going to a person or into a file or pipe."""
    isatty = getattr(sys.stdout, "isatty", None)
    try:
        return bool(isatty()) if callable(isatty) else False
    except (OSError, ValueError):  # a closed or detached stream
        return False


def _read_prompt_file(path: Path) -> str:
    """The whole file, as one message (``cli.go:27-33``).

    An empty file is refused rather than sent: submitting an empty
    message costs a model call to be told nothing was asked.
    """
    try:
        text = path.expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        raise AppConfigError(f"--prompt-file {path}: {exc}") from exc
    if not text.strip():
        raise AppConfigError(f"--prompt-file {path} is empty")
    return text


def start_cli(
    deployment: Sequence[str],
    surface: Sequence[str],
    env: Mapping[str, str],
) -> int:
    """REPL, or one exchange when a prompt was supplied.

    ``main.go:453-468`` with one of its three branches removed: a prompt
    means the harness's ``RunOnce`` (its third branch, the ``else``), no
    prompt means the interactive one. What is missing here is its
    *middle* branch, ``case term.IsTerminal(...)``, which starts a Bubble
    Tea TUI (``tui.go:17``); this repository has no TUI at all yet (plan
    0031 §1.3), Textual or otherwise.

    The deployment half is resolved **before** ``--help`` is answered,
    for the reason plan 0037 §5.2 gives: everything left of ``--`` goes
    to :func:`~omicsclaw.entry.resolve_app_config`, always, or a typo
    there is silently discarded by whichever surface flag happened to
    return first. The user still sees the usage, because
    :func:`omicsclaw.launch.main` prints it alongside the refusal.

    ``--configure`` is answered next, before anything is assembled: it
    exists to fix a deployment that cannot start, so making it pay for a
    start-up first would make it useless in the one case it is for.

    **This surface's flags are claimed from either half** (plan 0048).
    ``oc cli --configure`` used to be a usage error whose usage listed
    ``--configure``, because the flag was read on one side of ``--`` and
    the line was parsed from the other. :func:`_claim_surface_flags`
    takes them from the deployment half first, so both spellings mean
    the same thing. What is claimed is parsed *before* the half after
    ``--``, so the more explicit spelling wins when a flag is given
    twice.

    This is not an exception to the cut in
    :func:`~omicsclaw.launch._grammar.split_command_line` —— which is
    unchanged —— but a statement about ownership: the surface and
    deployment flag families are disjoint, so nothing here can take a
    flag ``resolve_app_config`` wanted.

    **One ordering property is genuinely weaker than before.** The
    surface half can now carry tokens from the left of ``--``, so a
    refusal about them reaches the user before an unknown *deployment*
    flag would have: ``oc cli --bogus x --session`` now names the
    missing session value rather than ``--bogus``. Both are refusals
    with the same exit code; what plan 0037 §5.2 forbids —— a typo on
    the deployment side being discarded by a surface flag that returns
    ``0`` first —— is still refused, and
    ``test_a_claimed_flag_cannot_turn_a_refusal_into_a_start`` pins it.
    """
    deployment, claimed = _claim_surface_flags(deployment, CLI_FLAGS)
    options = ReplOptions.parse([*claimed, *surface])
    config = resolve_app_config(deployment, _with_the_cli_permission_mode(env))
    source = _permission_mode_source(deployment, env)
    if options.help:
        print(CLI_USAGE)
        return EXIT_OK
    if options.configure:
        run_configuration_wizard(
            dotenv_target(), workspace_default=str(config.workspace)
        )
        return EXIT_OK
    _report_a_missing_credential(env)

    records: Any = None
    try:
        with terminal_owned_logging() as records:
            try:
                code = asyncio.run(
                    _run_cli(
                        config,
                        options,
                        dotenv_path=dotenv_target(),
                        permission_mode_source=source,
                    )
                )
            except (KeyboardInterrupt, asyncio.CancelledError):
                code = EXIT_INTERRUPTED
    finally:
        _replay(records)
    return code


_PERMISSION_MODE_VARIABLE = "OMICSCLAW_PERMISSION_MODE"
"""The deployment-wide key. Named here only to be *deferred to*: this file
never parses it, it checks whether it is set so that the CLI-only key can
step aside —— ``resolve_app_config`` is still the one reader of its value."""


def _with_the_cli_permission_mode(env: Mapping[str, str]) -> Mapping[str, str]:
    """*env*, with the CLI-only key standing in for the general one.

    Precedence for ``oc cli``, most deliberate first: the
    ``--permission-mode`` flag, then ``OMICSCLAW_PERMISSION_MODE`` from
    anywhere, then ``OMICSCLAW_CLI_PERMISSION_MODE``, then ``default``. The
    general key outranks the specific one on purpose —— it is a deployment
    saying something about every surface, and ``/auto`` reports when it is
    being outranked rather than overriding it. The flag stays on top for
    free: ``resolve_app_config`` reads argv after env.

    A bad value is refused under the name the person wrote, not the name
    it was copied to —— and refused whether or not something outranks it,
    the rule every deployment setting follows: a typo is loud even when it
    would not have counted.
    """
    chosen = env.get(CLI_PERMISSION_MODE_VARIABLE, "")
    if not chosen:
        return env
    try:
        PermissionMode(chosen.strip().lower())
    except ValueError:
        modes = ", ".join(mode.value for mode in PermissionMode)
        raise AppConfigError(
            f"{CLI_PERMISSION_MODE_VARIABLE}: {chosen!r} is not a permission "
            f"mode ({modes})"
        ) from None
    if env.get(_PERMISSION_MODE_VARIABLE, ""):
        return env
    return {**env, _PERMISSION_MODE_VARIABLE: chosen}


def _permission_mode_source(
    deployment: Sequence[str], env: Mapping[str, str]
) -> str:
    """Which setting decided this run's permission mode, for ``/auto``.

    ``"flag"``, ``"environment"`` (the general key, exported or from a
    ``.env``: either way it outranks what ``/auto`` writes), ``"cli-key"``,
    or ``""`` for the default. Only facts that can be read exactly: whether
    the general key came from the shell or a file is not one of them, and
    does not need to be.
    """
    if "permission_mode" in fields_set_by_argv(deployment):
        return "flag"
    if env.get(_PERMISSION_MODE_VARIABLE, ""):
        return "environment"
    if env.get(CLI_PERMISSION_MODE_VARIABLE, ""):
        return "cli-key"
    return ""


def _report_a_missing_credential(env: Mapping[str, str]) -> int:
    """Name the setup command when nothing has configured a backend.

    To stderr, so that ``oc cli -- --prompt … > answer.txt`` still writes
    only the answer, and one line rather than a screen: the compensation
    for keeping ``--configure`` on the surface side of ``--`` is that
    nobody has to have read about it.

    Returns the number of lines printed so that a test can assert the
    silence as well as the line —— a hint that fires on a configured
    deployment is noise, and noise is how the next hint gets ignored.
    """
    hint = missing_credential_hint(env)
    if not hint:
        return 0
    print(hint, file=sys.stderr)
    return 1


async def _run_cli(
    config: Any,
    options: ReplOptions,
    *,
    dotenv_path: Path | None = None,
    permission_mode_source: str = "",
) -> int:
    """Assemble, run one of the two paths, release everything, report.

    Three properties that a plain ``try``/``finally`` did not have:

    *The prompt source is closed on every path.* ``source.close()`` used
    to be the statement after the REPL, so a ``Ctrl-C`` —— the ordinary
    way a REPL ends —— jumped over it and left ``prompt_toolkit``'s
    history file unflushed and its terminal state unrestored.

    *A second ``Ctrl-C`` cannot truncate the release.* See
    :func:`_release`.

    *The exit code is decided here*, where it is known whether the loop
    ended because the user asked it to or because the deployment could
    not be let go of. Reporting ``130`` over a half-finished shutdown is
    telling a supervisor a clean story about an unclean exit.

    ``SIGTERM`` and ``SIGHUP``, from start-up to the end of the release,
    stop the whole run rather than the work in front of the user, unless
    this process was started ignoring them: the Task running this is
    cancelled, which ends the REPL or the one exchange and a running
    ``!`` command with it, every exchange still running is cancelled, and
    the deployment is released. A signal that arrives before the run has
    ended makes the exit code ``128 + signum`` once the release has
    finished; one that arrives during the release leaves the run's own
    exit code. After ``SIGHUP``, see :func:`_leave_a_hung_up_terminal`.
    An exception raised by the run after the signal is logged rather than
    raised.
    """
    with _stop_signals(
        asyncio.current_task(),
        _CLI_STOP_SIGNALS,
        on_signal=_leave_a_hung_up_terminal,
    ) as stop:
        try:
            app = attach_sessions(await open_app(config))
        except asyncio.CancelledError:
            if not stop.signalled:
                raise
            return stop.exit_code
        screen = Screen()
        show_reasoning = options.shows_reasoning(
            stdout_is_terminal=_stdout_is_a_terminal()
        )
        code = EXIT_OK
        try:
            if options.prompt:
                handle = await run_once(
                    app,
                    options.prompt,
                    screen=screen,
                    show_reasoning=show_reasoning,
                )
                converged = handle is not None and handle.terminal == "converged"
                code = EXIT_OK if converged else EXIT_FAILED
            else:
                source = open_prompt_source()
                try:
                    repl = Repl(
                        app,
                        source=source,
                        screen=screen,
                        session_id=options.session_id,
                        show_reasoning=show_reasoning,
                        dotenv_path=dotenv_path,
                        permission_mode_source=permission_mode_source,
                    )
                    repl.welcome()
                    with _interrupts(repl, asyncio.current_task()):
                        await repl.run()
                finally:
                    source.close()
        except asyncio.CancelledError:
            code = EXIT_INTERRUPTED
        except Exception:
            if not stop.signalled:
                raise
            logger.warning(
                "the run failed while stopping for a signal", exc_info=True
            )
        finally:
            stopped_by_signal = stop.signalled
            if stopped_by_signal:
                _cancel_running_exchanges(app)
            released = await _release(app)
    if stopped_by_signal:
        code = stop.exit_code
    return code if released else EXIT_FAILED


_CLI_STOP_SIGNALS: tuple[int, ...] = tuple(
    number
    for number in (signal.SIGTERM, getattr(signal, "SIGHUP", None))
    if number is not None
)
"""Signals that end ``oc cli`` as a whole. ``SIGINT`` is not one of them:
:class:`_interrupts` handles it, as an interruption of the work in front
of the user."""


def _cancel_running_exchanges(app: Any) -> None:
    """Cancel every exchange *app*'s session registry is running, if it has one."""
    sessions = app.sessions
    if sessions is None:
        return
    for handle in sessions.running():
        handle.cancel()


def _leave_a_hung_up_terminal(
    number: int, descriptors: Sequence[int] = (1, 2)
) -> None:
    """On ``SIGHUP``, point each of *descriptors* whose terminal is gone at ``/dev/null``.

    A descriptor is redirected when it is a character device that no
    longer answers as a terminal, which is what a terminal becomes when it
    hangs up; every later write to it, the interpreter's flush at exit
    included, then succeeds instead of failing with ``EIO``. A file, a
    pipe and a terminal still in use are left as they are. Does nothing
    for any other signal, and nothing when ``/dev/null`` cannot be opened.

    :param number: The signal that arrived.
    :param descriptors: The descriptors to check; standard output and
        standard error by default.
    """
    if number != getattr(signal, "SIGHUP", None):
        return
    try:
        sink = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        return
    try:
        for descriptor in descriptors:
            try:
                gone = stat.S_ISCHR(os.fstat(descriptor).st_mode) and not os.isatty(
                    descriptor
                )
                if gone:
                    os.dup2(sink, descriptor)
            except OSError:
                continue
    finally:
        os.close(sink)


async def _release(app: Any) -> bool:
    """Close the deployment, absorbing one further interrupt. Did it finish?

    ``Ctrl-C`` at a REPL cancels this coroutine, and the cancellation
    lands wherever it is —— including inside
    :meth:`~omicsclaw.entry.assembly.AgentApp.aclose`, which is draining
    sessions, stopping MCP child processes and removing a sandbox
    container. A second ``Ctrl-C`` from somebody who thinks nothing is
    happening used to cut that in half and still be reported as ``130``:
    an orphaned container, and an exit code saying the shutdown was
    clean.

    :func:`asyncio.shield` is what makes the close survive it: the
    cancellation arrives at the ``await`` here rather than inside the
    close, and the close is waited for again. Exactly one extra
    interrupt is absorbed —— a bound and not a loop, because a shell
    that cannot be stopped is its own failure. If the second one does
    not let it finish either, the caller is told, and says so.
    """
    closing = asyncio.ensure_future(app.aclose())
    for _ in range(2):
        try:
            await asyncio.shield(closing)
            return True
        except asyncio.CancelledError:
            if closing.done():
                return True
            logger.warning("shutdown interrupted; still releasing the deployment")
    closing.cancel()
    try:  # reaped, or the loop complains about it at interpreter shutdown
        await closing
    except BaseException:  # noqa: BLE001 - it was cancelled on purpose
        pass
    return False


class _interrupts:
    """``Ctrl-C`` to :meth:`Repl.interrupt` while this block is entered.

    A context manager because the previous handler is put back on exit.

    Installed with :func:`signal.signal`, not
    :meth:`~asyncio.loop.add_signal_handler`: every ``prompt_toolkit``
    prompt adds its own loop-level SIGINT handler and removes it when the
    prompt returns, which would delete this one after the first line read.
    A Python-level handler is saved and restored around each prompt. The
    handler only schedules :meth:`_fire` on the loop, because cancelling a
    Task is only safe on the loop's own thread.

    Outside the main thread :func:`signal.signal` raises
    :exc:`ValueError`; nothing is installed then, and ``Ctrl-C`` keeps
    Python's default behaviour.
    """

    def __init__(self, repl: Repl, task: "asyncio.Task[int] | None") -> None:
        self._repl = repl
        self._task = task
        self._installed = False
        self._previous: Any = None

    def __enter__(self) -> "_interrupts":
        try:
            loop = asyncio.get_running_loop()
            previous = signal.getsignal(signal.SIGINT)
            signal.signal(
                signal.SIGINT,
                lambda *_: loop.call_soon_threadsafe(self._fire),
            )
        except (RuntimeError, ValueError):
            self._installed = False
            return self
        self._previous = previous
        self._installed = True
        return self

    def __exit__(self, *_exc: object) -> None:
        if not self._installed:
            return
        self._installed = False
        try:
            signal.signal(
                signal.SIGINT,
                self._previous
                if self._previous is not None
                else signal.default_int_handler,
            )
        except (RuntimeError, ValueError):
            pass

    def _fire(self) -> None:
        """Handle one ``Ctrl-C``, on the event loop's thread.

        :meth:`Repl.interrupt` cancels the running exchange, or else the
        running ``!`` command. When there is neither, the REPL is stopped
        and the task running it, if one was given, is cancelled.
        """
        if self._repl.interrupt():
            return
        self._repl.state.stop()
        if self._task is not None:
            self._task.cancel()


_LOG_TAIL_CHARS = 4000
"""How much of the redirected log is shown once the terminal is free,
counted in characters as printed, after escaping.

Bounded because the buffer is in memory for the life of the session and
a chatty MCP server should not be able to grow it without limit; the
tail rather than the head because the last thing that went wrong is the
one being asked about.

Whoever wants the whole thing cannot get it by pre-installing a handler:
``terminal_owned_logging`` *replaces* the root handler list for the
session rather than adding to it, so an already-installed file handler
receives nothing until the REPL gives the terminal back. The way to keep
everything today is to raise this bound; a ``--log-file`` deployment
flag is the honest fix and is recorded as debt in plan 0037 appendix A.
"""


def _replay(records: "object") -> None:
    """Print what was logged, now that the REPL has let go of the screen.

    Plan 0031 Q22 rule 2 says a REPL owning the terminal reroutes
    logging; it does not say the records are thrown away. Discarding
    them is how a surface becomes the reason a failure cannot be
    diagnosed, so they are held and shown afterwards, to stderr, where a
    pipe can separate them from the answer the user asked for.

    Called from a ``finally`` and not after the block, because the run
    that most needs its log is the one that raised something nobody
    expected —— and until plan 0037's review that was the one run whose
    log was dropped whole.

    What is printed is :func:`_inert_tail` of the log, at most
    :data:`_LOG_TAIL_CHARS` characters in which no character can act on
    the terminal. When standard error cannot be written, the log is
    dropped and nothing is raised.
    """
    text = getattr(records, "getvalue", lambda: "")()
    if not text:
        return
    try:
        print(_inert_tail(text, _LOG_TAIL_CHARS), file=sys.stderr, end="")
    except OSError:
        pass


def _inert_tail(text: str, limit: int) -> str:
    """The end of *text* made inert by :func:`inert_prose`, in at most *limit* characters.

    The cut falls between characters of *text*, so no escape is split, and
    as many of its last characters are kept as fit in *limit* once made
    inert.

    :param text: The text to show the end of.
    :param limit: The most characters to return.
    :returns: The inert tail; ``""`` for ``""``.
    """
    start = len(text)
    size = 0
    while start > 0:
        size += len(inert_prose(text[start - 1]))
        if size > limit:
            break
        start -= 1
    return inert_prose(text[start:])


# ---- the Desktop surface ----------------------------------------------


DESKTOP_FLAGS: Mapping[str, int] = MappingProxyType(
    {**_HELP_ARITY, "--host": 1, "--port": 1, "--abandon-grace": 1}
)
"""This surface's flags and their arities —— see :data:`CLI_FLAGS`."""


class DesktopOptions:
    """The Desktop backend's half of the command line.

    Four flags and no token among them —— see
    :data:`DESKTOP_TOKEN_VARIABLE`. ``abandon_grace_s`` is ``None`` unless
    ``--abandon-grace`` was given, which leaves the session registry's
    own default in force.
    """

    __slots__ = ("abandon_grace_s", "help", "host", "port")

    def __init__(self) -> None:
        self.host = DESKTOP_HOST
        self.port = DESKTOP_PORT
        self.abandon_grace_s: float | None = None
        self.help = False

    @classmethod
    def parse(cls, argv: Sequence[str]) -> "DesktopOptions":
        options = cls()
        tokens = list(argv)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            flag, inline = _split_inline(token)
            if flag in _HELP_FLAGS:
                _refuse_a_value(flag, inline)
                options.help = True
                continue
            if flag in ("--host", "--port", "--abandon-grace"):
                if inline:
                    value = inline
                elif index >= len(tokens):
                    raise AppConfigError(f"{flag} needs a value")
                else:
                    value = tokens[index]
                    index += 1
                if flag == "--host":
                    options.host = value
                elif flag == "--port":
                    options.port = _as_port(value)
                else:
                    options.abandon_grace_s = _as_grace_seconds(value)
                continue
            raise AppConfigError(f"unknown surface option {token!r}")
        return options


def _as_grace_seconds(raw: str) -> float:
    """``--abandon-grace``'s value as seconds, refusing anything outside
    :data:`DESKTOP_ABANDON_GRACE_RANGE_S`, ``nan`` and ``inf`` included."""
    low, high = DESKTOP_ABANDON_GRACE_RANGE_S
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise AppConfigError(
            f"--abandon-grace takes a number of seconds, not {raw!r}"
        ) from exc
    if not low <= seconds <= high:
        raise AppConfigError(
            f"--abandon-grace takes {low:g} to {high:g} seconds, not {raw!r}"
        )
    return seconds


def _as_port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError as exc:
        raise AppConfigError(f"{raw!r} is not a port number") from exc
    if not 0 < port < 65536:
        raise AppConfigError(f"{port} is not a port number")
    return port


def start_desktop(
    deployment: Sequence[str],
    surface: Sequence[str],
    env: Mapping[str, str],
) -> int:
    """Serve the Desktop routes over HTTP.

    The routes and their wire contract are defined by
    :mod:`omicsclaw.entry.desktop`; all that happens here is binding an
    ASGI server to the application
    :func:`~omicsclaw.entry.desktop.create_desktop_app` returns.

    Four things happen in a fixed order and each ordering is a decision:
    the surface flags are read, the deployment half is resolved
    (*always*, so an unknown deployment flag cannot be discarded by an
    early return), an off-machine bind without a token is refused, and
    only then is the optional dependency checked ——
    still before anything is assembled, which is the property
    ``test_the_desktop_command_checks_the_dependency_before_assembling``
    pins.
    """
    deployment, claimed = _claim_surface_flags(deployment, DESKTOP_FLAGS)
    options = DesktopOptions.parse([*claimed, *surface])
    config = resolve_app_config(deployment, env)
    if options.help:
        print(DESKTOP_USAGE)
        return EXIT_OK
    token = env.get(DESKTOP_TOKEN_VARIABLE, "").strip()
    _refuse_an_open_unauthenticated_bind(options.host, token)
    server_module = _asgi_server_module()
    settings = _desktop_settings(env)
    return asyncio.run(_serve_desktop(config, options, token, server_module, settings))


def _desktop_settings(
    env: Mapping[str, str], *, root: Path | None = None, cwd: Path | None = None
) -> DotenvSettings:
    """The ``.env`` settings the Desktop routes read and write.

    The target and the candidates are the ones ``_adopt_dotenv`` uses.
    From a :class:`~omicsclaw.launch._dotenv.LaunchEnvironment` the
    exported variables are the names set before ``.env`` was read and the
    start-up environment is its snapshot; any other *env* is the whole
    deployment, so all of it is both.
    """
    if isinstance(env, LaunchEnvironment):
        names = env.exported_names
        startup: Mapping[str, str] = env.startup
    else:
        names = frozenset(env)
        startup = dict(env)
    exported = {name: startup[name] for name in names if name in startup}
    return DotenvSettings(
        dotenv_target(root, cwd),
        candidates=dotenv_candidates(root, cwd),
        exported=exported,
        startup=startup,
    )


def _refuse_an_open_unauthenticated_bind(host: str, token: str) -> None:
    """``SAFETY_RULES`` rule 1, enforced where the address is chosen.

    ``create_desktop_app(app, bearer_token="")`` authorises every
    request, which is the right default for a loopback socket the Electron
    client owns and is an unauthenticated agent with a shell tool on the
    network for any other address. Nothing downstream can tell the two
    apart, because by the time a request arrives the host is a uvicorn
    detail; the only place that knows both facts is this one.

    Refused rather than defaulted: silently falling back to loopback
    would serve something other than what was asked for, and silently
    minting a token would leave the client unable to connect. The
    message names the variable so that the remedy is one line long.
    """
    if host in LOOPBACK_HOSTS or token:
        return
    raise AppConfigError(
        f"--host {host} serves beyond this machine and "
        f"{DESKTOP_TOKEN_VARIABLE} is empty, which leaves every route "
        f"unauthenticated; set {DESKTOP_TOKEN_VARIABLE} or bind "
        f"{DESKTOP_HOST}"
    )


def _asgi_server_module() -> Any:
    """``uvicorn`` and ``fastapi``, checked before anything is assembled.

    Both are imported here, in plainly visible syntax, and both are
    checked **before** :func:`open_app` —— assembling an agent, starting
    its MCP servers and then discovering there is no web framework to
    serve it with wastes the start-up and reports the wrong failure
    last. A bare :exc:`ImportError` out of a process shell names a
    module and not a remedy. Both packages are conda-managed
    (``environment.yml``), so the remedy the message names is the conda
    environment rather than a pip extra.
    """
    try:
        import fastapi  # noqa: F401  (checked here, imported for real below)
        import uvicorn
    except ImportError as exc:
        raise MissingSurfaceDependency(
            "the desktop surface needs uvicorn and fastapi, which the "
            "OmicsClaw conda environment provides; update it with "
            "`mamba env update -f environment.yml`, or install them into "
            "this interpreter's environment with "
            "`mamba install -c conda-forge fastapi uvicorn`"
        ) from exc
    return uvicorn


async def _serve_desktop(
    config: Any,
    options: DesktopOptions,
    token: str,
    uvicorn: Any,
    settings: DotenvSettings | None = None,
) -> int:
    opened = await open_app(config)
    if options.abandon_grace_s is None:
        app = attach_sessions(opened)
    else:
        app = attach_sessions(opened, abandon_grace_s=options.abandon_grace_s)
    try:
        api = create_desktop_app(app, bearer_token=token, settings=settings)
        server = uvicorn.Server(
            uvicorn.Config(
                api, host=options.host, port=options.port, log_level="info"
            )
        )
        await server.serve()
        return 0
    finally:
        await app.aclose()


# ---- the Channel surface ----------------------------------------------


CHANNEL_FLAGS: Mapping[str, int] = MappingProxyType(
    {
        **_HELP_ARITY,
        "--list": 0,
        "--verbose": 0,
        "--channels": 1,
        "--health-port": 1,
    }
)
"""This surface's flags and their arities —— see :data:`CLI_FLAGS`."""


class ChannelOptions:
    """The instant-messaging surface's half of the command line."""

    __slots__ = ("channels", "health_port", "help", "list", "verbose")

    def __init__(self) -> None:
        self.channels: tuple[str, ...] = ()
        self.health_port = 0
        self.list = False
        self.verbose = False
        self.help = False

    @classmethod
    def parse(cls, argv: Sequence[str]) -> "ChannelOptions":
        options = cls()
        tokens = list(argv)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            flag, inline = _split_inline(token)
            if flag in _HELP_FLAGS:
                _refuse_a_value(flag, inline)
                options.help = True
                continue
            if flag == "--list":
                _refuse_a_value(flag, inline)
                options.list = True
                continue
            if flag == "--verbose":
                _refuse_a_value(flag, inline)
                options.verbose = True
                continue
            if flag in ("--channels", "--health-port"):
                if inline:
                    value = inline
                elif index >= len(tokens):
                    raise AppConfigError(f"{flag} needs a value")
                else:
                    value = tokens[index]
                    index += 1
                if flag == "--channels":
                    options.channels = _as_channel_names(value)
                else:
                    options.health_port = _as_port(value)
                continue
            raise AppConfigError(f"unknown surface option {token!r}")
        return options


def _as_channel_names(raw: str) -> tuple[str, ...]:
    """``telegram,feishu`` to two names, refusing a repeat.

    A name given twice would register one channel and silently drop the
    other, because :meth:`ChannelManager.register` is keyed by name ——
    the legacy runner refused it for the same reason
    (``surfaces/channels/__main__.py:365``).
    """
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not names:
        raise AppConfigError("--channels needs at least one channel name")
    unknown = sorted(set(names) - set(CHANNEL_REGISTRY))
    if unknown:
        available = ", ".join(sorted(CHANNEL_REGISTRY))
        raise AppConfigError(f"unknown channel {unknown}; available: {available}")
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise AppConfigError(f"channel requested more than once: {repeated}")
    return names


def start_channel(
    deployment: Sequence[str],
    surface: Sequence[str],
    env: Mapping[str, str],
) -> int:
    """Run one or more IM adapters against one shared agent.

    One runtime per process, because two registries would be two sets of
    conversations for one person, and ingress opens last and for
    everyone at once —— both properties belong to
    :func:`~omicsclaw.entry.channel.compose_channel_runtime` and
    :meth:`~omicsclaw.entry.channel.ChannelManager.start_all`, and this
    function's only job is to call them in that order.

    The deployment half is resolved before ``--list`` and ``--help`` are
    answered. It used to be resolved after them, which broke plan 0037
    §5.2 twice over: ``oc channel --bogus-flag -- --list`` exited ``0``
    with the typo discarded, and ``oc channel --bogus-flag`` blamed the
    missing ``--channels`` instead of naming the flag it could not read.
    """
    deployment, claimed = _claim_surface_flags(deployment, CHANNEL_FLAGS)
    options = ChannelOptions.parse([*claimed, *surface])
    config = resolve_app_config(deployment, env)
    if options.help:
        print(CHANNEL_USAGE)
        return EXIT_OK
    if options.list:
        _print_channel_registry()
        return EXIT_OK
    if not options.channels:
        raise AppConfigError("--channels is required (e.g. --channels telegram)")

    logging.basicConfig(
        level=logging.DEBUG if options.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        return asyncio.run(_serve_channels(config, options, env))
    except ImportError as exc:
        raise MissingSurfaceDependency(
            f"{exc.name} is not installed and starting "
            f"{', '.join(options.channels)} needs it (pip install {exc.name})"
        ) from exc
    except KeyboardInterrupt:  # pragma: no cover - the loop handles SIGINT
        return EXIT_INTERRUPTED
    except asyncio.CancelledError:  # pragma: no cover - same
        return EXIT_INTERRUPTED


def _print_channel_registry() -> None:
    """Name, class and cutover status for every registered adapter.

    The status is read from the class rather than from a second list
    kept here: ``Channel.authoritative_ingress`` is what
    :meth:`~omicsclaw.entry.channel.base.Channel.require_authoritative_ingress`
    actually gates on at start-up, and a printed list that disagreed
    with the gate would be worse than no list.
    """
    print("Available channels:")
    for name in sorted(CHANNEL_REGISTRY):
        _module, class_name = CHANNEL_REGISTRY[name]
        try:
            authoritative = bool(get_channel_class(name).authoritative_ingress)
            status = "authoritative" if authoritative else "disabled pending cutover"
        except ImportError as exc:  # pragma: no cover - needs a broken adapter
            status = f"unavailable ({exc})"
        print(f"  {name:12s} -> {class_name} [{status}]")


class _stop_signals:
    """``SIGTERM`` and ``SIGINT`` end the run loop; the block records which.

    Those two by default; the CLI passes ``SIGTERM`` and ``SIGHUP``
    instead, and a hook to run before the Task is cancelled.

    This is the whole of plan 0037's B1 and B2. Before it, ``SIGTERM``
    —— the signal a container, a systemd unit and ``kill`` all send by
    default —— had no handler at all, so the default disposition applied
    and the process died where it stood: no turn drained, no MCP child
    reaped, no sandbox container removed, even though
    :meth:`~omicsclaw.entry.assembly.AgentApp.aclose` documents a channel
    runner closing it on exactly that signal. ``SIGINT`` did run the
    cleanup, through :class:`asyncio.Runner`'s own handling, but
    :meth:`ChannelManager.run` absorbs the resulting
    :exc:`~asyncio.CancelledError` —— correctly, because "stopped" is not
    an error for a library —— so the coroutine returned normally and the
    shell reported ``0``. A supervisor reading ``0`` cannot tell "the
    operator stopped it" from "it finished".

    Handled here and not in :meth:`ChannelManager.run` deliberately. An
    exit code is a property of a process and this package is the process
    (plan 0037 §2 problem 1); a manager that re-raised would be encoding
    a shell's convention in a library that three other callers use, and
    it still could not report *which* signal arrived, which is the one
    fact ``128 + signum`` is made of.

    Installed through the loop rather than :func:`signal.signal` for the
    reason :class:`_interrupts` gives: the handler cancels a Task, and
    that is only safe on the loop's own thread (plan 0031 trap 10).

    Entered **before** the first adapter is built and not around the run
    loop alone, because the window between them is not theoretical: the
    first version of this class installed its handlers after
    :meth:`ChannelManager.start_all`, and the test that signals the
    process the moment it reports a channel serving killed it outright,
    every time. A start-up is exactly when a deployment is most likely
    to be stopped —— it is when somebody is watching it.
    """

    __slots__ = ("_installed", "_numbers", "_on_signal", "_signal", "_task")

    def __init__(
        self,
        task: "asyncio.Task[Any] | None",
        numbers: Sequence[int] = (signal.SIGTERM, signal.SIGINT),
        on_signal: Callable[[int], None] | None = None,
    ) -> None:
        """Handle *numbers* while entered; the first to arrive cancels *task*.

        :param task: The Task the first signal cancels, or ``None``.
        :param numbers: The signals handled while the block is entered.
        :param on_signal: Called with the first signal's number, on the
            loop's thread, before *task* is cancelled.
        """
        self._task = task
        self._numbers = tuple(numbers)
        self._on_signal = on_signal
        self._signal: int = 0
        self._installed: list[int] = []

    def __enter__(self) -> "_stop_signals":
        """Install a handler for each signal whose disposition is not ``SIG_IGN``.

        A signal this process was started ignoring, as ``nohup`` starts it
        ignoring ``SIGHUP``, stays ignored and is neither handled nor
        restored by :meth:`__exit__`.
        """
        loop = asyncio.get_running_loop()
        for number in self._numbers:
            try:
                if signal.getsignal(number) == signal.SIG_IGN:
                    continue
                loop.add_signal_handler(number, self._fire, number)
            except (NotImplementedError, RuntimeError, ValueError):
                continue
            self._installed.append(number)
        return self

    def __exit__(self, *_exc: object) -> None:
        loop = asyncio.get_running_loop()
        for number in self._installed:
            try:
                loop.remove_signal_handler(number)
            except (NotImplementedError, RuntimeError, ValueError):
                pass
        self._installed.clear()

    def _fire(self, number: int) -> None:
        """Record the first signal, call the hook and cancel the Task.

        Every later signal handled by this block, of either kind, is
        ignored while the block is entered: it neither changes the
        recorded signal nor cancels the Task again.
        """
        if self._signal:
            return
        self._signal = number
        logger.info("Received signal %s; stopping", number)
        if self._on_signal is not None:
            self._on_signal(number)
        if self._task is not None:
            self._task.cancel()

    @property
    def signalled(self) -> bool:
        """Whether this block is the reason the run loop stopped."""
        return bool(self._signal)

    @property
    def exit_code(self) -> int:
        """``0`` if no signal arrived, otherwise ``128 + signum``."""
        return (128 + self._signal) if self._signal else EXIT_OK


async def _serve_channels(
    config: Any, options: ChannelOptions, env: Mapping[str, str]
) -> int:
    """Build the adapters, assemble once, run until a signal says stop.

    The adapters are built **before** the agent is assembled: a missing
    credential is the most common way this command fails and paying for
    an MCP start-up first only delays the message.

    The whole of it runs inside :class:`_stop_signals`, start-up
    included. The cancellation it delivers lands wherever the coroutine
    happens to be; if that is inside :meth:`ChannelManager.run` it is
    absorbed there and every ``finally`` below still runs, which is the
    orderly shutdown. If it lands earlier —— during assembly, say —— the
    cleanup is whatever has been entered so far, which is still more
    than the nothing that used to happen.
    """
    with _stop_signals(asyncio.current_task()) as signals:
        try:
            channels = [build_channel(name, env) for name in options.channels]
            app = attach_sessions(await open_app(config))
            try:
                manager = ChannelManager()
                for channel in channels:
                    manager.register(channel)
                runtime = await compose_channel_runtime(
                    app, tuple(manager.channels.values())
                )
                try:
                    await manager.start_all()
                    if options.health_port:
                        await manager.start_health_server(options.health_port)
                    await manager.run()
                finally:
                    await runtime.close()
            finally:
                await app.aclose()
        except asyncio.CancelledError:
            if not signals.signalled:
                raise
    return signals.exit_code


def build_channel(name: str, env: Mapping[str, str]) -> Any:
    """One adapter, configured from *env*.

    A registry name with no builder here is refused rather than guessed at.
    It is an adapter that has not been through the cut-over and that
    :meth:`~omicsclaw.entry.channel.base.Channel.require_authoritative_ingress`
    would refuse to start anyway; saying so before an agent is assembled
    costs nothing and names the real reason.
    """
    builder = _CHANNEL_BUILDERS.get(name)
    if builder is None:
        raise AppConfigError(
            f"channel {name!r} has no launch configuration yet; it is also "
            "disabled until its ChannelRuntime and delivery cutover lands"
        )
    return builder(env)


def _allowed_senders(env: Mapping[str, str], variable: str) -> set[str]:
    return {
        value.strip() for value in env.get(variable, "").split(",") if value.strip()
    }


def _as_int(env: Mapping[str, str], variable: str, default: int) -> int:
    raw = env.get(variable, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise AppConfigError(f"{variable}: {raw!r} is not a whole number") from exc


def _required(env: Mapping[str, str], variable: str, why: str) -> str:
    """One credential, or a refusal that names the variable and the reason.

    The reason is not decoration: an adapter's own ``RuntimeError`` surfaces
    to this shell as an unanticipated failure, whereas "this deployment is
    not configured" has to read as the configuration mistake it is.
    """
    value = env.get(variable, "").strip()
    if not value:
        raise AppConfigError(f"{variable} is required: {why}")
    return value


def _as_bool(env: Mapping[str, str], variable: str, default: bool) -> bool:
    """A yes/no setting in the spellings a ``.env`` actually uses.

    An unrecognised value is refused rather than read as false: a
    ``STARTTLS=maybe`` that silently became "no" would downgrade a
    connection that was meant to be encrypted.
    """
    raw = env.get(variable, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise AppConfigError(f"{variable}: {raw!r} is not a yes/no value")


def _build_telegram(env: Mapping[str, str]) -> Any:
    """Telegram, with both halves of its gate checked before anything starts.

    The allowlist check is here and not only in
    :meth:`TelegramChannel.prepare_control_binding` for symmetry with
    :func:`_build_feishu`: both refusals are "this deployment is not
    configured", so both have to be the same kind of event. Left to the
    adapter it arrived as a :exc:`RuntimeError` out of a started
    ``Application``, which this shell could only report as an
    unanticipated failure —— two experiences for one class of mistake,
    on two surfaces of the same command.
    """
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise AppConfigError("TELEGRAM_BOT_TOKEN is required for --channels telegram")
    from omicsclaw.entry.channel.telegram import TelegramChannel, TelegramConfig

    allowed = _allowed_senders(env, "TELEGRAM_ALLOWED_SENDERS")
    if not allowed and not _as_int(env, "TELEGRAM_CHAT_ID", 0):
        raise AppConfigError(
            "TELEGRAM_ALLOWED_SENDERS or TELEGRAM_CHAT_ID is required: "
            "authoritative Telegram ingress admits only configured Owners"
        )
    return TelegramChannel(
        TelegramConfig(
            bot_token=token,
            admin_chat_id=_as_int(env, "TELEGRAM_CHAT_ID", 0),
            account_namespace=env.get("TELEGRAM_ACCOUNT_NAMESPACE", "").strip(),
            allowed_senders=allowed or None,
        )
    )


def _build_feishu(env: Mapping[str, str]) -> Any:
    app_id = env.get("FEISHU_APP_ID", "").strip()
    app_secret = env.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise AppConfigError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")
    allowed = _allowed_senders(env, "FEISHU_ALLOWED_SENDERS")
    if not allowed:
        raise AppConfigError(
            "FEISHU_ALLOWED_SENDERS is required: authoritative Feishu ingress "
            "admits only configured Owner open_id values"
        )
    bot_open_id = env.get("FEISHU_BOT_OPEN_ID", "").strip()
    if not bot_open_id:
        raise AppConfigError(
            "FEISHU_BOT_OPEN_ID is required: authoritative Feishu ingress must "
            "prove a group mention targets this Bot"
        )
    from omicsclaw.entry.channel.feishu import FeishuChannel, FeishuConfig

    return FeishuChannel(
        FeishuConfig(
            allowed_senders=allowed,
            bot_open_id=bot_open_id,
            app_id=app_id,
            app_secret=app_secret,
            thinking_threshold_ms=_as_int(
                env, "FEISHU_THINKING_THRESHOLD_MS", 2500
            ),
            max_inbound_image_mb=_as_int(env, "FEISHU_MAX_INBOUND_IMAGE_MB", 12),
            max_inbound_file_mb=_as_int(env, "FEISHU_MAX_INBOUND_FILE_MB", 40),
            max_attachments=_as_int(env, "FEISHU_MAX_ATTACHMENTS", 4),
            rate_limit_per_hour=_as_int(env, "FEISHU_RATE_LIMIT_PER_HOUR", 60),
            debug=env.get("FEISHU_BRIDGE_DEBUG", "") == "1",
        )
    )


def _build_slack(env: Mapping[str, str]) -> Any:
    from omicsclaw.entry.channel.slack import SlackChannel, SlackConfig

    allowed = _allowed_senders(env, "SLACK_ALLOWED_SENDERS")
    if not allowed:
        raise AppConfigError(
            "SLACK_ALLOWED_SENDERS is required: authoritative Slack ingress "
            "admits only configured owner user ids"
        )
    return SlackChannel(
        SlackConfig(
            bot_token=_required(
                env, "SLACK_BOT_TOKEN", "the bot posts and authenticates with it"
            ),
            app_token=_required(
                env, "SLACK_APP_TOKEN", "Socket Mode opens its socket with it"
            ),
            allowed_senders=allowed,
            rate_limit_per_hour=_as_int(env, "SLACK_RATE_LIMIT_PER_HOUR", 0),
            proxy=env.get("SLACK_PROXY", "").strip() or None,
        )
    )


def _build_discord(env: Mapping[str, str]) -> Any:
    from omicsclaw.entry.channel.discord import DiscordChannel, DiscordConfig

    allowed = _allowed_senders(env, "DISCORD_ALLOWED_SENDERS")
    if not allowed:
        raise AppConfigError(
            "DISCORD_ALLOWED_SENDERS is required: authoritative Discord "
            "ingress admits only configured owner user ids"
        )
    return DiscordChannel(
        DiscordConfig(
            bot_token=_required(
                env, "DISCORD_BOT_TOKEN", "the gateway authenticates with it"
            ),
            allowed_senders=allowed,
            rate_limit_per_hour=_as_int(env, "DISCORD_RATE_LIMIT_PER_HOUR", 0),
            proxy=env.get("DISCORD_PROXY", "").strip() or None,
        )
    )


def _build_dingtalk(env: Mapping[str, str]) -> Any:
    from omicsclaw.entry.channel.dingtalk import DingTalkChannel, DingTalkConfig

    allowed = _allowed_senders(env, "DINGTALK_ALLOWED_SENDERS")
    if not allowed:
        raise AppConfigError(
            "DINGTALK_ALLOWED_SENDERS is required: authoritative DingTalk "
            "ingress admits only configured owner staff ids"
        )
    return DingTalkChannel(
        DingTalkConfig(
            client_id=_required(
                env, "DINGTALK_CLIENT_ID", "it is the robot this bot speaks as"
            ),
            client_secret=_required(
                env, "DINGTALK_CLIENT_SECRET", "the access token is fetched with it"
            ),
            allowed_senders=allowed,
            rate_limit_per_hour=_as_int(env, "DINGTALK_RATE_LIMIT_PER_HOUR", 0),
        )
    )


def _build_qq(env: Mapping[str, str]) -> Any:
    from omicsclaw.entry.channel.qq import QQChannel, QQConfig

    allowed = _allowed_senders(env, "QQ_ALLOWED_SENDERS")
    if not allowed:
        raise AppConfigError(
            "QQ_ALLOWED_SENDERS is required: authoritative QQ ingress admits "
            "only configured owner openid values"
        )
    return QQChannel(
        QQConfig(
            app_id=_required(env, "QQ_APP_ID", "it is the bot this process is"),
            app_secret=_required(
                env, "QQ_APP_SECRET", "the gateway authenticates with it"
            ),
            allowed_senders=allowed,
            rate_limit_per_hour=_as_int(env, "QQ_RATE_LIMIT_PER_HOUR", 0),
        )
    )


def _build_email(env: Mapping[str, str]) -> Any:
    """Email, whose four mandatory credentials span two protocols.

    IMAP and SMTP are separate servers with separate logins, and a
    deployment that configured one of them would come up and then fail at
    the first message in one direction only. Both halves are therefore
    required here rather than where they are first used.
    """
    from omicsclaw.entry.channel.email import EmailChannel, EmailConfig

    allowed = _allowed_senders(env, "EMAIL_ALLOWED_SENDERS")
    if not allowed:
        raise AppConfigError(
            "EMAIL_ALLOWED_SENDERS is required: authoritative Email ingress "
            "admits only configured owner addresses"
        )
    return EmailChannel(
        EmailConfig(
            imap_host=_required(env, "EMAIL_IMAP_HOST", "inbound mail is polled"),
            imap_port=_as_int(env, "EMAIL_IMAP_PORT", 993),
            imap_username=_required(
                env, "EMAIL_IMAP_USERNAME", "the mailbox is opened with it"
            ),
            imap_password=env.get("EMAIL_IMAP_PASSWORD", ""),
            imap_mailbox=env.get("EMAIL_IMAP_MAILBOX", "").strip() or "INBOX",
            imap_use_ssl=_as_bool(env, "EMAIL_IMAP_USE_SSL", True),
            smtp_host=_required(env, "EMAIL_SMTP_HOST", "replies are sent through it"),
            smtp_port=_as_int(env, "EMAIL_SMTP_PORT", 587),
            smtp_username=_required(
                env, "EMAIL_SMTP_USERNAME", "the reply is sent as it"
            ),
            smtp_password=env.get("EMAIL_SMTP_PASSWORD", ""),
            smtp_starttls=_as_bool(env, "EMAIL_SMTP_STARTTLS", True),
            from_address=env.get("EMAIL_FROM_ADDRESS", "").strip(),
            poll_interval=_as_int(env, "EMAIL_POLL_INTERVAL", 30),
            mark_seen=_as_bool(env, "EMAIL_MARK_SEEN", True),
            allowed_senders=allowed,
            rate_limit_per_hour=_as_int(env, "EMAIL_RATE_LIMIT_PER_HOUR", 0),
        )
    )


_CHANNEL_BUILDERS = {
    "telegram": _build_telegram,
    "feishu": _build_feishu,
    "slack": _build_slack,
    "discord": _build_discord,
    "dingtalk": _build_dingtalk,
    "qq": _build_qq,
    "email": _build_email,
}
"""One builder per adapter that can be started, and no placeholder.

Seven functions rather than one generic builder over a declarative table.
The table would have to express "email's four mandatory credentials across
two protocols", which is a small language nobody asked for; **which** variables name a deployment is exactly
the knowledge this package exists to hold, and it reads better as an ``if``
than as a schema.

Each one refuses an empty allowlist here rather than leaving it to the
adapter, because both are "this deployment is not configured" and have to
arrive as the same kind of event — an adapter's ``RuntimeError`` reaches
this shell as an unanticipated failure instead.

``CHANNEL_REGISTRY`` may still hold a name this table does not;
:func:`build_channel` reports that as a refusal rather than hiding it behind
a builder for an adapter that would then refuse to start.
"""
