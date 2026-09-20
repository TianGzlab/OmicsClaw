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
``uvicorn``, ``fastapi`` and the two adapter modules this file can build
are imported in plainly visible ``import`` syntax inside a factory,
never at module scope, so ``import omicsclaw.launch`` costs none of them
and a dependency scanner can still see them (plan 0031 trap 13). The
nine *platform* SDKs are not named here at all: an adapter module owns
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
the only thing a supervisor can read.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from omicsclaw.entry import (
    AppConfigError,
    attach_sessions,
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
    Repl,
    Screen,
    missing_credential_hint,
    open_prompt_source,
    run_configuration_wizard,
    run_once,
    terminal_owned_logging,
)
from omicsclaw.entry.desktop import create_desktop_app

from ._dotenv import dotenv_target

__all__ = [
    "CHANNEL_USAGE",
    "CLI_USAGE",
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
the convention every supervisor already reads. They are two numbers and
not one because "the operator stopped it" and "somebody pressed Ctrl-C
at a terminal" are different events, and a process that reports ``0``
for either —— which is what this shell did before plan 0037's review ——
tells its supervisor it finished the work.
"""

CLI_USAGE = """\
usage: oc cli [deployment flags] [-- surface flags]

Deployment flags are read by omicsclaw.entry.resolve_app_config; run it
with an unknown one to see the list it refuses. The system prompt's
front matter is a deployment flag and is called --system-prompt-file.

Surface flags (after --):
  --session <id>     REPL only: conversation to continue, a fresh one by
                     default. Refused together with --prompt, which is
                     one exchange and has no conversation to continue.
  --prompt <text>    answer once and exit, instead of starting the REPL
  --prompt-file <p>  the same, with the whole file as the one message
  --show-reasoning   print the model's reasoning as well as its answer
  --configure        ask for a provider, a key, a model, an endpoint and
                     a workspace, and write them to the .env this shell
                     loads. Starts no agent, so it is refused together
                     with --session, --prompt and --prompt-file.
  --help             this text
"""

DESKTOP_USAGE = """\
usage: oc desktop [deployment flags] [-- surface flags]

Serves POST /chat/stream and GET /health for the OmicsClaw-App client.
Deployment flags are read by omicsclaw.entry.resolve_app_config.

Surface flags (after --):
  --host <address>   interface to bind (default 127.0.0.1)
  --port <number>    port to bind (default 8765)
  --help             this text

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
from .env as well (see CLAUDE.md, or omicsclaw/surfaces/channels/README.md
for the full per-platform variable list).

Surface flags (after --):
  --channels <list>  comma-separated adapters, e.g. telegram,feishu
  --health-port <n>  serve a JSON health endpoint on this port
  --verbose          debug logging
  --list             print the adapter registry and exit
  --help             this text
"""

DESKTOP_HOST = "127.0.0.1"
"""Loopback, because :func:`create_desktop_app` defaults to no bearer token.

``CLAUDE.md`` publishes ``oc desktop-server --host 127.0.0.1 --port 8765``
and the Electron client connects to exactly that. A default of
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
addresses is the wrong shape for ``CLAUDE.md`` safety rule 1: the
question is not whether this spelling is known to be public, it is
whether it is known to be private.
"""

DESKTOP_PORT = 8765

DESKTOP_TOKEN_VARIABLE = "OMICSCLAW_REMOTE_AUTH_TOKEN"
"""Where the bearer token comes from, and why it is not a flag.

``omicsclaw/remote/auth.py:30`` already publishes this name, so the
shell reuses it rather than minting a second one. It is read from the
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
        self.show_reasoning = False
        self.configure = False
        self.help = False

    @classmethod
    def parse(cls, argv: Sequence[str]) -> "ReplOptions":
        """Read the tail. Raises :exc:`AppConfigError` on anything unknown.

        The same exception type the deployment half raises, so the shell
        has one failure to report and the user sees one kind of message
        whichever side of ``--`` the typo was on.
        """
        options = cls()
        tokens = list(argv)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if token in _HELP_FLAGS:
                options.help = True
                continue
            if token == "--show-reasoning":
                options.show_reasoning = True
                continue
            if token == "--configure":
                options.configure = True
                continue
            if token in ("--session", "--prompt", "--prompt-file"):
                if index >= len(tokens):
                    raise AppConfigError(f"{token} needs a value")
                value = tokens[index]
                index += 1
                if token == "--session":
                    options.session_id = value
                elif token == "--prompt":
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
    start-up first would make it useless in the one case it is for. It
    is a surface flag and goes after ``--`` like every other one —— the
    hoist in :func:`~omicsclaw.launch._grammar.split_command_line` is for
    ``--help`` alone, and every exception to that rule weakens it.
    """
    options = ReplOptions.parse(surface)
    config = resolve_app_config(deployment, env)
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
                code = asyncio.run(_run_cli(config, options))
            except (KeyboardInterrupt, asyncio.CancelledError):
                code = EXIT_INTERRUPTED
    finally:
        _replay(records)
    return code


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


async def _run_cli(config: Any, options: ReplOptions) -> int:
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
    """
    app = attach_sessions(await open_app(config))
    screen = Screen()
    code = EXIT_OK
    try:
        if options.prompt:
            handle = await run_once(
                app,
                options.prompt,
                screen=screen,
                show_reasoning=options.show_reasoning,
            )
            converged = handle is not None and handle.terminal == "converged"
            code = EXIT_OK if converged else EXIT_FAILED
        else:
            source = open_prompt_source(app.skills.names())
            try:
                repl = Repl(
                    app,
                    source=source,
                    screen=screen,
                    session_id=options.session_id,
                    show_reasoning=options.show_reasoning,
                )
                repl.welcome()
                with _interrupts(repl, asyncio.current_task()):
                    await repl.run()
            finally:
                source.close()
    except asyncio.CancelledError:
        code = EXIT_INTERRUPTED
    finally:
        released = await _release(app)
    return code if released else EXIT_FAILED


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

    A context manager because the handler must be removed again: a loop
    left holding a callback into a finished REPL is the shutdown-time
    version of the "log sink never restored" mistake plan 0031 Q22 rule
    2 is about. :exc:`NotImplementedError` is caught because
    :meth:`~asyncio.loop.add_signal_handler` does not exist on Windows,
    where the fallback is Python's default —— ``KeyboardInterrupt`` out
    of the loop, which ends the process rather than the exchange.

    Installed through the loop rather than :func:`signal.signal` because
    the handler cancels a Task and that is only safe on the loop's own
    thread (plan 0031 trap 10).
    """

    def __init__(self, repl: Repl, task: "asyncio.Task[int] | None") -> None:
        self._repl = repl
        self._task = task
        self._installed = False

    def __enter__(self) -> "_interrupts":
        try:
            asyncio.get_running_loop().add_signal_handler(
                signal.SIGINT, self._fire
            )
            self._installed = True
        except (NotImplementedError, RuntimeError, ValueError):
            self._installed = False
        return self

    def __exit__(self, *_exc: object) -> None:
        if not self._installed:
            return
        try:
            asyncio.get_running_loop().remove_signal_handler(signal.SIGINT)
        except (NotImplementedError, RuntimeError, ValueError):
            pass

    def _fire(self) -> None:
        """Cancel the exchange, or the loop when there is not one."""
        if self._repl.interrupt():
            return
        self._repl.state.stop()
        if self._task is not None:
            self._task.cancel()


_LOG_TAIL_CHARS = 4000
"""How much of the redirected log is shown once the terminal is free.

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
    """
    text = getattr(records, "getvalue", lambda: "")()
    if not text:
        return
    print(text[-_LOG_TAIL_CHARS:], file=sys.stderr, end="")


# ---- the Desktop surface ----------------------------------------------


class DesktopOptions:
    """The Desktop backend's half of the command line.

    Three flags and no token among them —— see
    :data:`DESKTOP_TOKEN_VARIABLE`.
    """

    __slots__ = ("help", "host", "port")

    def __init__(self) -> None:
        self.host = DESKTOP_HOST
        self.port = DESKTOP_PORT
        self.help = False

    @classmethod
    def parse(cls, argv: Sequence[str]) -> "DesktopOptions":
        options = cls()
        tokens = list(argv)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if token in _HELP_FLAGS:
                options.help = True
                continue
            if token in ("--host", "--port"):
                if index >= len(tokens):
                    raise AppConfigError(f"{token} needs a value")
                value = tokens[index]
                index += 1
                if token == "--host":
                    options.host = value
                else:
                    options.port = _as_port(value)
                continue
            raise AppConfigError(f"unknown surface option {token!r}")
        return options


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
    """Serve ``POST /chat/stream`` and ``GET /health`` over HTTP.

    The routes and their eight schema versions belong to the external
    Electron client and are not this shell's to change (plan 0031 Q24);
    all that happens here is binding an ASGI server to the application
    :func:`~omicsclaw.entry.desktop.create_desktop_app` returns.

    Four things happen in a fixed order and each ordering is a decision:
    the surface flags are read, the deployment half is resolved (plan
    0037 §5.2 —— *always*, so an unknown deployment flag cannot be
    discarded by an early return), an off-machine bind without a token
    is refused, and only then is the optional dependency checked ——
    still before anything is assembled, which is the property
    ``test_the_desktop_command_checks_the_dependency_before_assembling``
    pins.
    """
    options = DesktopOptions.parse(surface)
    config = resolve_app_config(deployment, env)
    if options.help:
        print(DESKTOP_USAGE)
        return EXIT_OK
    token = env.get(DESKTOP_TOKEN_VARIABLE, "").strip()
    _refuse_an_open_unauthenticated_bind(options.host, token)
    server_module = _asgi_server_module()
    return asyncio.run(_serve_desktop(config, options, token, server_module))


def _refuse_an_open_unauthenticated_bind(host: str, token: str) -> None:
    """``CLAUDE.md`` safety rule 1, enforced where the address is chosen.

    ``create_desktop_app(app, bearer_token="")`` authorises every
    request —— ``server.py:303`` is ``if not bearer_token: return True``
    —— which is the right default for a loopback socket the Electron
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
    module and not a remedy; this deployment's remedy is a published
    extra, so it is what the message says.
    """
    try:
        import fastapi  # noqa: F401  (checked here, imported for real below)
        import uvicorn
    except ImportError as exc:
        raise MissingSurfaceDependency(
            "the desktop surface needs uvicorn and fastapi "
            "(pip install -e '.[desktop]')"
        ) from exc
    return uvicorn


async def _serve_desktop(
    config: Any, options: DesktopOptions, token: str, uvicorn: Any
) -> int:
    app = attach_sessions(await open_app(config))
    try:
        api = create_desktop_app(app, bearer_token=token)
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
            if token in _HELP_FLAGS:
                options.help = True
                continue
            if token == "--list":
                options.list = True
                continue
            if token == "--verbose":
                options.verbose = True
                continue
            if token in ("--channels", "--health-port"):
                if index >= len(tokens):
                    raise AppConfigError(f"{token} needs a value")
                value = tokens[index]
                index += 1
                if token == "--channels":
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
    options = ChannelOptions.parse(surface)
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
    """Name, class and cutover status for all nine adapters.

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

    __slots__ = ("_installed", "_signal", "_task")

    def __init__(self, task: "asyncio.Task[Any] | None") -> None:
        self._task = task
        self._signal: int = 0
        self._installed: list[int] = []

    def __enter__(self) -> "_stop_signals":
        loop = asyncio.get_running_loop()
        for number in (signal.SIGTERM, signal.SIGINT):
            try:
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
        """First signal stops the loop; a second is left to the default.

        Only the first is recorded, so a second ``Ctrl-C`` from somebody
        who thinks nothing is happening does not change the exit code of
        a shutdown that is already under way.
        """
        if self._signal:
            return
        self._signal = number
        logger.info("Received signal %s; stopping channels", number)
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

    Only Telegram and Feishu have a builder: plan 0031 §5.3 accepts
    those two and the other seven are gated at start-up by
    :meth:`~omicsclaw.entry.channel.base.Channel.require_authoritative_ingress`
    anyway. Writing seven builders for adapters that cannot start would
    be writing seven things no test can exercise.
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


_CHANNEL_BUILDERS = {
    "telegram": _build_telegram,
    "feishu": _build_feishu,
}
"""The two adapters plan 0031 §5.3 accepts, and no placeholder for the rest.

``CHANNEL_REGISTRY`` has nine names and this table has two. The gap is
deliberate and is reported as a refusal by :func:`build_channel` rather
than hidden behind a builder that would construct an adapter
``require_authoritative_ingress`` then refuses to start.
"""
