"""Where a line of input comes from — which is a parameter, not a fact.

The reference harness's CLI is ``runCLI(ctx, eng, io.Reader, idx)``
(``cli.go:36``): the reader is an argument, so the loop can be driven by a
test without a terminal. This module is that argument. :class:`Repl
<omicsclaw.entry.cli._repl.Repl>` never touches :data:`sys.stdin` and
never imports ``prompt_toolkit``; it asks a :class:`PromptSource` for the
next line and is told when there are no more.

Three implementations, in the order a deployment prefers them:

:class:`PromptToolkitSource` — history, completion, a styled prompt. Built
by :func:`open_prompt_source` **only** when standard input is a terminal
and the package is installed.

:class:`StreamSource` — ``readline`` on any text stream. What a pipe gets,
and what ``oc cli < script.txt`` gets. The read
happens on a worker thread (:func:`asyncio.to_thread`) so that a blocking
``readline`` does not stop the event loop the session registry's lanes
live on.

:class:`ScriptedSource` — a fixed list, for tests and for
``--prompt-file``.

**A source is read from more than one task at a time.** :class:`Repl
<omicsclaw.entry.cli._repl.Repl>` answers each approval request from its
own Task so that the event pump never stops consuming, and one model
message may carry two calls to concurrency-safe tools that both ask —
``web_fetch`` and ``web_search`` are exactly that pair. Concurrent
:meth:`PromptSource.read` is therefore part of the contract, and a source
backed by **one** device has to queue its readers rather than let them
collide: ``prompt_toolkit`` asserts ``Application is already running`` on
the second overlapping prompt, and two ``readline`` threads on one stdin
hand the same typed line to whichever wakes first.

**Nothing here is imported at module scope that is not installed
everywhere** (plan 0031 trap 13). ``prompt_toolkit`` is imported inside
:func:`open_prompt_source` in plainly visible ``import`` syntax — not
through :func:`importlib.import_module`, which is the form plan 0028's
handover records as the one a static check cannot see — and the fallback
to :class:`StreamSource` is what makes the package usable without it.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Iterable, Protocol, Sequence, TextIO

from ._slash_command_support import (
    REPL_SLASH_COMMAND_SPECS,
    SlashCommandSpec,
    complete_run_skill_names,
    complete_slash_command_rows,
)

__all__ = [
    "PromptSource",
    "PromptToolkitSource",
    "ScriptedSource",
    "StreamSource",
    "open_prompt_source",
]


class PromptSource(Protocol):
    """One line of user input at a time, until there are none.

    May be read from several tasks at once. An implementation that owns a
    device only one reader can hold is required to serialize them itself
    — see this module's docstring for who calls it that way and why.
    """

    async def read(self, prompt: str) -> str:
        """The next line, without its newline.

        :raises EOFError: the input ended, or the source was closed while
            this read was queued behind another. A REPL treats this
            exactly as it treats ``/exit`` — the reference harness gives
            EOF and ``exit`` the same exit (``cli.go:36-79``).
        """
        ...

    def close(self) -> None:
        """Release whatever the source holds. Idempotent."""
        ...


class ScriptedSource:
    """A fixed sequence of lines, then :exc:`EOFError`.

    The double every test in ``tests/entry/test_cli_repl.py`` drives the
    loop with, and also what ``--prompt-file`` uses in production: one
    element, the whole file (see
    :func:`~omicsclaw.entry.cli.__main__.single_prompt`).
    """

    __slots__ = ("_lines", "prompts")

    def __init__(self, lines: Iterable[str]) -> None:
        self._lines = list(lines)
        self.prompts: list[str] = []
        """Every prompt string that was shown, in order. A test asserting
        that the loop came back to the prompt after a cancellation is
        asserting on this."""

    async def read(self, prompt: str) -> str:
        """The next line, **suspending once** on the way.

        The :func:`asyncio.sleep` is not decoration, and it is the same
        trade ``InMemorySessionStore.save`` documents: every real source
        suspends — a worker thread, a terminal, a socket — and one that
        never yields hides a defect rather than exposing it. A loop that
        stopped exiting on EOF would spin here without ever reaching the
        event loop, so the :func:`asyncio.wait_for` that every test in
        this repository wraps its awaits in would never get to fire and
        the run would hang instead of failing. Costing one loop iteration
        to keep a hang a *failure* is worth it on a machine with no
        timeout plugin installed.
        """
        await asyncio.sleep(0)
        self.prompts.append(prompt)
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)

    def close(self) -> None:
        self._lines.clear()


class StreamSource:
    """``readline`` on a text stream, off the event loop's thread.

    ``asyncio.to_thread`` rather than a direct call: the registry's lane
    pumps and any MCP connection live on the same loop, and a blocking
    ``readline`` on the loop's thread would freeze them for as long as the
    user is thinking. The worker thread cannot be cancelled while it is
    blocked in ``read(2)``; a source read from a pipe or a closed terminal
    unblocks at EOF, and this is written down rather than defended against
    because the alternative — a non-blocking reader per platform — is a
    platform layer this surface does not need.

    One reader at a time, because there is one stream: two ``readline``
    threads on one stdin both block in ``read(2)`` and the line the user
    typed goes to whichever the kernel wakes, so the question they
    answered is not necessarily the one their answer settles.
    """

    __slots__ = ("_closed", "_echo", "_reading", "_stream", "_write")

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        echo: TextIO | None = None,
    ) -> None:
        """*echo* receives the prompt string; ``None`` prints nothing.

        A piped run wants no prompt in its output, an interactive fallback
        wants one, and which it is is the caller's to know.
        """
        self._stream = stream if stream is not None else sys.stdin
        self._write = echo
        self._closed = False
        self._reading = asyncio.Lock()

    async def read(self, prompt: str) -> str:
        """The next line, waiting for any earlier reader to be answered.

        The closed check is repeated inside the lock: a source closed
        while this call was queued has no line left to give, and saying so
        with :exc:`EOFError` is what lets a caller fail closed instead of
        waiting on a stream nobody owns.
        """
        if self._closed:
            raise EOFError
        async with self._reading:
            if self._closed:
                raise EOFError
            if self._write is not None:
                self._write.write(prompt)
                self._write.flush()
            line = await asyncio.to_thread(self._stream.readline)
        if line == "":
            raise EOFError
        return line.rstrip("\n").rstrip("\r")

    def close(self) -> None:
        self._closed = True


class PromptToolkitSource:
    """A real terminal prompt: history, suggestions, completion.

    Constructed only by :func:`open_prompt_source`, which is also the only
    place that imports ``prompt_toolkit``. The session object is held
    opaquely (``Any``) so that this class's annotations cost no import
    either.

    **One question on the terminal at a time.** A ``PromptSession`` owns a
    single ``Application`` and re-entering it trips
    ``assert not self._is_running`` — an :exc:`AssertionError` raised in
    whichever task asked second. That is not a cosmetic failure: the task
    that dies is the one that would have answered an approval, and an
    approval nobody answers is an exchange that waits forever, because a
    terminal deployment sets no approval deadline on purpose. The lock
    turns two simultaneous cards into two cards in a row.
    """

    __slots__ = ("_reading", "_session")

    def __init__(self, session: Any) -> None:
        self._session = session
        self._reading = asyncio.Lock()

    async def read(self, prompt: str) -> str:
        """Show *prompt* once the terminal is free, and return the answer.

        :raises EOFError: the source was closed, including while this call
            was queued behind another question.
        """
        async with self._reading:
            session = self._session
            if session is None:
                raise EOFError
            return await session.prompt_async(prompt)

    def close(self) -> None:
        self._session = None


def _history_path() -> Any:
    """``~/.config/omicsclaw/history``, created if its directory is not.

    Ported from ``interactive.py``'s ``get_config_dir()`` usage (its lines
    2075-2077) minus two things: the SQLite store that function also
    served, and its ``XDG_CONFIG_HOME`` lookup. The lookup is dropped
    rather than moved because plan 0031 Q8 leaves **one** reader of the
    environment in this package and it is ``resolve_app_config``; a
    deployment that needs the history somewhere else should gain an
    ``AppConfig`` field, which is a decision with one home instead of two.
    """
    from pathlib import Path

    directory = Path.home() / ".config" / "omicsclaw"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "history"


def build_completer(
    skill_names: Sequence[str],
    *,
    specs: Sequence[SlashCommandSpec] = REPL_SLASH_COMMAND_SPECS,
) -> Any:
    """The slash / skill / path completer, over this deployment's skills.

    **Ported** from ``interactive.py``'s ``_make_completer`` (its lines
    286-342). One change: the skill names are an argument rather than a
    call to the deleted registry's ``list_registered_skill_names()``, so
    the completion offers exactly what
    :attr:`~omicsclaw.entry.assembly.AgentApp.skills` loaded — the list
    the model was shown, not a second scan that could disagree with it.

    Imports ``prompt_toolkit`` in the body, so naming this function costs
    nothing (trap 13).
    """
    from prompt_toolkit.completion import Completer, Completion, PathCompleter
    from prompt_toolkit.document import Document

    class _OmniCompleter(Completer):
        def __init__(self) -> None:
            self.path_completer = PathCompleter(expanduser=True)
            self._skills = list(skill_names)

        def get_completions(self, document: Document, complete_event: Any):
            text = document.text_before_cursor

            # 1. Slash commands
            if text.startswith("/") and " " not in text.strip():
                for cmd, desc in complete_slash_command_rows(text, specs):
                    if cmd.startswith(text):
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=f"{cmd:<20}",
                            display_meta=desc,
                        )
                return

            # 2. Skill completion for /run <skill>
            if text.startswith("/run "):
                skill_prefix = text[len("/run ") :].lstrip()
                for skill_name in complete_run_skill_names(text, self._skills):
                    yield Completion(
                        skill_name,
                        start_position=-len(skill_prefix),
                        display_meta="OmicsClaw Skill",
                    )

            # 3. File path completion
            words = text.split(" ")
            last_word = words[-1]
            if last_word.startswith(("./", "/", "~/")):
                path_doc = Document(
                    text=last_word, cursor_position=len(last_word)
                )
                try:
                    completions = self.path_completer.get_completions(
                        path_doc, complete_event
                    )
                    for comp in completions:
                        yield Completion(
                            comp.text,
                            start_position=-len(last_word),
                            display=comp.display,
                            display_meta="File Path",
                        )
                except Exception:
                    pass

    return _OmniCompleter()


def open_prompt_source(
    skill_names: Sequence[str] = (),
    *,
    stream: TextIO | None = None,
    interactive: bool | None = None,
) -> PromptSource:
    """The best source this process can have, degrading rather than failing.

    Three outcomes, decided in this order:

    1. *not a terminal* — :class:`StreamSource`. The harness makes the
       same test at ``main.go:453-468`` before choosing between its TUI
       and its line reader, and it is what makes
       ``oc cli < questions.txt`` work.
    2. *a terminal, ``prompt_toolkit`` installed* —
       :class:`PromptToolkitSource`.
    3. *a terminal, not installed* — :class:`StreamSource` echoing the
       prompt, which is the ``input()`` experience without ``input()``'s
       habit of holding the loop's thread.

    The import sits in branch 2's body on purpose. A module-level import
    would make ``prompt_toolkit`` a hard dependency of *importing* this
    package, and plan 0031 §9-4 asserts in a subprocess that it is not.
    """
    source = stream if stream is not None else sys.stdin
    if interactive is None:
        try:
            interactive = bool(source.isatty())
        except (AttributeError, ValueError):
            interactive = False
    if not interactive:
        return StreamSource(source)

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.shortcuts import CompleteStyle
        from prompt_toolkit.styles import Style
    except ImportError:
        return StreamSource(source, echo=sys.stdout)

    # Ported from interactive.py's _COMPLETION_STYLE (its lines 347-353).
    style = Style.from_dict(
        {
            "completion-menu": "bg:default noreverse",
            "completion-menu.completion": "bg:default #888888",
            "completion-menu.completion.current": "bg:default default bold",
            "completion-menu.meta.completion": "bg:default #666666",
            "completion-menu.meta.completion.current": "bg:default #aaaaaa bold",
        }
    )
    session = PromptSession(
        history=FileHistory(str(_history_path())),
        auto_suggest=AutoSuggestFromHistory(),
        completer=build_completer(skill_names),
        complete_style=CompleteStyle.COLUMN,
        complete_while_typing=True,
        style=style,
    )
    return PromptToolkitSource(session)
