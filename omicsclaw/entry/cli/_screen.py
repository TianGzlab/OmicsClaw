"""Who owns the terminal, and what it may print while it does.

Two jobs that are one job. The banner and the separators are **ported**
from ``omicsclaw/surfaces/cli/interactive.py`` — ``print_banner`` at its
lines 238-277 and ``_print_separator`` at 369-371.
:func:`terminal_owned_logging` is **not** a port: it answers plan 0031
Q22 rule 2, which the original had no counterpart for, and the only
thing it took from ``_configure_cli_loggers`` (``:211-231``) is the idea
of a quiet list — see :data:`_QUIETED_LOGGERS`, every name of which had
to be rewritten because the packages the original named no longer exist.

**Q22 rule 2 — a REPL owning the terminal reroutes logging.** The
reference harness redirects the log sink before starting its full-screen
UI and restores it with a ``defer`` (``tui.go:365-367``). The reason
survives the translation to a line-oriented REPL: a ``WARNING`` from an
MCP server landing in the middle of a streamed sentence corrupts the one
thing the user is reading, and the record is not lost — it goes to
*destination* instead, which a deployment can point at a file.

**Q22 rule 1 — no tool argument and no tool output is ever logged.** This
module cannot enforce that for other files, but it is the file that
decides where log records go, so it is where the rule is written down:
``write_file``'s content, ``bash``'s command and ``web_fetch``'s full URL
can each carry a subject identifier, and
:data:`~omicsclaw.entry.assembly.SAFETY_RULES` rule 1 ("genetic data never
leaves this machine") is a rule a log file can break.
Nothing in :mod:`omicsclaw.entry.cli` passes either to a logger, and
``tests/entry/test_cli_logging.py`` drives a real tool call and asserts
the arguments never reach a record.

**Why ``rich`` and not ``print``.** It is already a hard dependency of the
package this code came from, it is installed here, and the ported
Markdown renderer emits :class:`rich.text.Text`. A :class:`Screen` wraps
one :class:`rich.console.Console` so that everything written by this
surface goes through one object a test can point at a buffer — the change
that made the ported formatter testable at all.
"""

from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path
from typing import Iterator, TextIO

from rich.console import Console
from rich.text import Text

from ._constants import LOGO_GRADIENT, LOGO_LINES

__all__ = ["Screen", "terminal_owned_logging"]

_QUIETED_LOGGERS = (
    "omicsclaw.entry",
    "omicsclaw.tools",
    "omicsclaw.mcp",
    "httpx",
    "httpcore",
    "openai",
    "anthropic",
)
"""Loggers a chat session does not want interleaved with its answer.

Rewritten rather than ported: the original list named ``omicsclaw.bot``,
``omicsclaw.core``, ``omicsclaw.memory`` and ``omicsclaw.runtime``, none
of which exists after the rebuild. These are the packages that log today.

The original also read ``OMICSCLAW_LOG_LEVEL`` to choose how quiet to be.
That variable is gone rather than moved: plan 0031 Q8 leaves one reader
of the environment in this package, and
:func:`terminal_owned_logging` takes the level as an argument instead. A
deployment that wants it back from the environment gives ``AppConfig`` a
field, which is the one place allowed to look.
"""

DEFAULT_QUIET_LEVEL = logging.ERROR
"""How quiet the noisy loggers are made while a REPL owns the screen.

``ERROR`` is the level the ported ``_configure_cli_loggers`` defaulted to,
kept because the judgement behind it has not changed: a chat session shows
what the user asked for, and anything below an error competing with a
streamed sentence costs more than it tells.
"""


class Screen:
    """Everything this surface prints, through one console.

    A thin wrapper and deliberately not thinner: the console is the seam
    that makes the REPL testable without a terminal, so it is worth a name
    and worth being the only way to write.
    """

    __slots__ = ("console",)

    def __init__(self, console: Console | None = None) -> None:
        self.console = console if console is not None else Console()

    @classmethod
    def into(cls, sink: TextIO, *, width: int = 80) -> "Screen":
        """A screen that writes to *sink* with colour and wrapping off.

        The form a test uses: ``force_terminal=False`` keeps ANSI escapes
        out of the captured text, and a fixed *width* keeps the separator
        the same length on every machine.
        """
        return cls(
            Console(
                file=sink,
                width=width,
                force_terminal=False,
                highlight=False,
                soft_wrap=True,
                emoji=False,
            )
        )

    def print(self, *args: object, **kwargs: object) -> None:
        self.console.print(*args, **kwargs)

    def rule(self) -> None:
        """A full-width separator between exchanges."""
        self.console.print(Text("─" * self.console.size.width, style="dim"))

    def banner(
        self,
        *,
        session_id: str,
        workspace: Path | str,
        model: str = "",
        provider: str = "",
        ui_backend: str = "cli",
        mode: str | None = None,
    ) -> None:
        """Print the logo and one line of deployment facts.

        Ported whole. ``session_id`` is still a parameter although the
        ported body never printed it — the original did not either, and
        removing an argument that three call sites pass is a change to
        make deliberately rather than while moving a file.
        """
        for line, color in zip(LOGO_LINES, LOGO_GRADIENT):
            self.console.print(Text(line, style=f"{color} bold"))

        info = Text()
        info.append("  ", style="dim")
        parts: list[tuple[str, str]] = []
        if model:
            parts.append(("Model: ", model))
        if provider:
            parts.append(("Provider: ", provider))
        if mode:
            parts.append(("Mode: ", mode))
        parts.append(("UI: ", ui_backend))

        for i, (label, value) in enumerate(parts):
            if i > 0:
                info.append("  ", style="dim")
            info.append(label, style="dim")
            info.append(value, style="magenta")

        home = str(Path.home())
        ws = str(workspace)
        dir_display = ws.replace(home, "~", 1) if ws.startswith(home) else ws
        info.append("\n  ", style="dim")
        info.append("Workspace: ", style="dim")
        info.append(dir_display, style="magenta")

        info.append("\n  Type ", style="#ffe082")
        info.append("/", style="#ffe082 bold")
        info.append(" for commands, ", style="#ffe082")
        info.append("/help", style="#ffe082 bold")
        info.append(" for full list", style="#ffe082")
        self.console.print(info)


@contextlib.contextmanager
def terminal_owned_logging(
    destination: TextIO | None = None,
    *,
    quiet_level: int = DEFAULT_QUIET_LEVEL,
) -> Iterator[TextIO]:
    """Send log records somewhere other than the screen, then put it back.

    Yields whatever records are being written to, so a caller that passed
    ``None`` can still read them — the default is an in-memory buffer
    rather than ``/dev/null`` because a record that is discarded cannot be
    shown to a user who asks what went wrong, and discarding by default is
    how a surface ends up being the reason a diagnosis is impossible.

    Restoring in ``finally`` is the whole point (``tui.go:365-367``): a
    REPL that raised on its way out and left the root logger pointing at a
    closed buffer would take the next thing in the process down with it.
    """
    sink: TextIO = io.StringIO() if destination is None else destination
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    previous_levels = {name: logging.getLogger(name).level for name in _QUIETED_LOGGERS}

    handler = logging.StreamHandler(sink)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.handlers = [handler]
    for name in _QUIETED_LOGGERS:
        logging.getLogger(name).setLevel(quiet_level)
    try:
        yield sink
    finally:
        root.handlers = previous_handlers
        root.setLevel(previous_level)
        for name, level in previous_levels.items():
            logging.getLogger(name).setLevel(level)
        handler.close()
