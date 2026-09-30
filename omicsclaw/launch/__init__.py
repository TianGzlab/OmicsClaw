"""``omicsclaw.launch`` —— the process shell, and nothing else.

Plan 0037 §5, scheme C. Everything about *being a process* lives here:
the command line, the environment, the exit code. Everything about
*being an agent* lives one layer down in :mod:`omicsclaw.entry`, which
after this package exists is three libraries and no processes.

**Why a layer rather than three ``__main__`` files.** A process entry
point is naturally a member of the layer it starts, and that membership
is what forced ``omicsclaw/entry/`` to read ``argv`` for itself and
forced its one-parse-point rule to carry an exemption (plan 0031 Q8,
recorded as open in ``docs/FRAMEWORK-REBUILD.md`` step 6). Three
surfaces would have meant three exemptions, and a growing exemption list
is the only way that rule degrades. Lifting the process out removes both
of the exemptions it had instead of adding two more.

**This file is the only reader of two globals in this package.**
``sys.argv`` and ``os.environ`` are named here —— at the two defaults of
:func:`main`, and in :func:`_adopt_dotenv`, which is the one place that
*writes* the process environment —— and nowhere else under
``omicsclaw/launch/``: every function below takes them as arguments.

**The rest of the rebuilt stack is not env-free, and saying so was
wrong.** Plan 0037 §3-1 claimed ``os.environ`` was read by
``resolve_app_config`` alone "plus the one declared exception
``provider_from_env``". It is not, and the claim passed review only
because the other readers live in packages the scan did not cover. The
real list is four entries long, each with a reason, and it is enumerated
and pinned by
``tests/launch/test_the_environment_is_read_in_known_places.py`` —— an
inaccurate rule that nothing enforces is worse than a wider rule that
something does.

**The grammar is three commands, one per surface**::

    oc cli                                 REPL
    oc cli --prompt-file brief.md          one exchange, then exit
    oc desktop --port 8765                 HTTP backend
    oc channel --channels telegram,feishu  IM adapters

``oc run <skill>`` is deliberately absent (owner ruling, 2026-09-20):
deterministic skill execution is what the agent does in a session and
what an in-surface command asks for, not a fourth way into the program.

**Exit codes.** ``0`` converged, ``1`` the surface ran and did not
converge —— or failed in a way nothing here anticipated —— ``2`` the
command line or the deployment was refused, which includes an optional
dependency that is not installed because nothing the user retypes fixes
that either, ``129`` hung up (``SIGHUP``, the terminal closed),
``130`` interrupted (``SIGINT``) and ``143`` terminated (``SIGTERM``).
The last three are ``128 + signum``, the convention a supervisor
already reads.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

from omicsclaw.entry import AppConfigError

from ._dotenv import DOTENV_FILE, LaunchEnvironment, dotenv_candidates, dotenv_target
from ._grammar import COMMANDS, Command, split_command_line, usage
from ._surfaces import (
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_TERMINATED,
    MissingSurfaceDependency,
)

__all__ = [
    "COMMANDS",
    "DOTENV_FILE",
    "EXIT_FAILED",
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_REFUSED",
    "EXIT_TERMINATED",
    "Command",
    "dotenv_candidates",
    "dotenv_target",
    "main",
    "usage",
]


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Run one command. Returns a process exit code and raises nothing.

    *argv* is the arguments **after** the program name and *env* is the
    environment; both default to this process's own. Passing them is how
    a test drives a whole deployment without touching the process it
    runs in, and —— since plan 0037 §5.4 —— it is also how the shipped
    code reaches :func:`~omicsclaw.entry.resolve_app_config`, whose two
    parameters are no longer optional. An injection point used only by
    tests is a design that has not finished; this one is now on the
    production path.

    **Raises nothing, and that is now true of every exception and not
    of three.** Until plan 0037's review this function caught
    :exc:`~omicsclaw.entry.AppConfigError`,
    :exc:`~omicsclaw.launch._surfaces.MissingSurfaceDependency` and
    :exc:`KeyboardInterrupt`, and everything else reached the user as a
    traceback with this machine's absolute paths in it —— which is what
    ``oc channel -- --channels telegram`` did on a host without the
    Telegram SDK. The last clause below is the backstop that makes the
    sentence above a property rather than a hope.

    *env* given explicitly means "this mapping is the whole deployment":
    ``.env`` is not read and the process environment is not touched, so
    a test describes exactly what it means to describe. ``env=None``
    means this shell owns the process, and then :func:`_adopt_dotenv`
    runs and the surface receives a
    :class:`~omicsclaw.launch._dotenv.LaunchEnvironment`: the live
    environment, the names that were set before ``.env`` was read, and a
    snapshot taken right after.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if env is None:
        environment: Mapping[str, str] = os.environ
        exported = frozenset(environment)
        _adopt_dotenv()
        environment = LaunchEnvironment(environment, exported)
    else:
        environment = env

    if not arguments:
        print(usage(), file=sys.stderr)
        return EXIT_REFUSED

    name, rest = arguments[0], arguments[1:]
    command = COMMANDS.get(name)
    if command is None:
        if name in ("help", "--help", "-h"):
            print(usage())
            return EXIT_OK
        print(
            f"omicsclaw: unknown command {name!r}\n\n{usage()}", file=sys.stderr
        )
        return EXIT_REFUSED

    deployment, surface = split_command_line(rest)
    try:
        return command.start(deployment, surface, environment)
    except AppConfigError as exc:
        print(f"omicsclaw: {exc}\n\n{command.usage}", file=sys.stderr)
        return EXIT_REFUSED
    except MissingSurfaceDependency as exc:
        print(f"omicsclaw: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except SystemExit as exc:  # a surface's library called sys.exit
        code = exc.code
        return code if isinstance(code, int) else EXIT_FAILED
    except BaseException as exc:  # noqa: BLE001 - the promise above
        print(f"omicsclaw: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_FAILED


def _adopt_dotenv(
    root: Path | None = None, cwd: Path | None = None
) -> tuple[Path, ...]:
    """Overlay ``.env`` onto the process environment, without overriding it.

    Returns the files that were read, for the test that has to prove
    this happened at all.

    **Why the live environment and not the mapping handed down.**
    :func:`omicsclaw.provider.provider_from_env` is plan 0031 Q8's one
    declared exception and reads ``LLM_API_KEY`` from the process
    directly; a ``.env`` merged only into the mapping this function
    returns would configure the workspace and leave the agent without a
    key —— which is the failure ``.env.example``'s instructions would
    produce. ``omicsclaw/entry/config.py`` says the same thing from the
    other side: a resolver that returns a value cannot make that
    function see a variable. Owning the process environment is what a
    process shell is for.

    **An exported variable always wins.** ``override=False``, matching
    the runner this replaces and ``godotenv`` in the reference harness.
    A file checked into a developer's tree must not be able to silently
    replace what an operator put in a systemd unit.

    Two locations, project root first —— which of them, and in which
    order, is :func:`omicsclaw.launch._dotenv.dotenv_candidates`'s answer
    and not a second copy of the search: ``oc cli --configure`` writes to
    the file this function reads, and the two agreeing by construction
    is cheaper than the two agreeing by review. Both roots are arguments
    so that a test can name them; a missing file is not an error, because
    most deployments export variables the ordinary way.
    """
    from omicsclaw.common.runtime_env import load_env_file

    read: list[Path] = []
    for candidate in dotenv_candidates(root, cwd):
        try:
            if load_env_file(candidate, override=False):
                read.append(candidate)
        except OSError:  # unreadable .env is not a reason not to start
            continue
    return tuple(read)
