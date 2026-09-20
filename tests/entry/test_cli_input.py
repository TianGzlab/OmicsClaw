"""The prompt sources, read the way the REPL really reads them.

:class:`~omicsclaw.entry.cli._repl.Repl` answers every approval request
from its own Task, so a model message carrying two calls to
concurrency-safe ASK tools — ``web_fetch`` and ``web_search`` are the two
the registry mounts — puts two :meth:`PromptSource.read` calls in flight
at once. ``tests/entry/test_cli_repl.py`` drives that case through
:class:`~omicsclaw.entry.cli.ScriptedSource`, which is a list and happily
serves both; a terminal is not a list, and these tests are about the
difference.

There is no ``pytest-asyncio`` here, so every test drives
:func:`asyncio.run` itself and bounds every await with
:func:`asyncio.wait_for` — an unserialized source shows up as a hang, and
a hang with no timeout plugin is a test run that never finishes.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from omicsclaw.entry.cli._input import PromptToolkitSource, StreamSource

WAIT_S = 10.0


class OneAtATime:
    """A ``PromptSession`` double with ``prompt_toolkit``'s own guard.

    ``Application.run_async`` opens with ``assert not self._is_running,
    "Application is already running."`` (prompt_toolkit 3.0.52), so a
    second overlapping prompt raises rather than queues. Reproducing the
    assertion rather than mocking it out is the point: a double that
    tolerates re-entry is exactly the double that reported this defect as
    working code.
    """

    def __init__(self, answers: list[str]) -> None:
        self._answers = answers
        self._running = False
        self.prompts: list[str] = []

    async def prompt_async(self, prompt: str) -> str:
        assert not self._running, "Application is already running."
        self._running = True
        try:
            self.prompts.append(prompt)
            await asyncio.sleep(0)  # a real prompt suspends; this must too
            return self._answers.pop(0)
        finally:
            self._running = False


def test_the_terminal_source_serializes_two_concurrent_readers():
    """Two cards at once become two cards in a row, not an AssertionError.

    Before the lock this raised ``Application is already running`` inside
    whichever approval Task asked second. That Task then never settled its
    request, and with no approval deadline at this surface the exchange
    waited for an answer that could no longer be given — the CLI froze
    with nothing on screen to say why.
    """

    async def drive():
        session = OneAtATime(["y", "n"])
        source = PromptToolkitSource(session)
        answers = await asyncio.wait_for(
            asyncio.gather(
                source.read("approve web_fetch? "),
                source.read("approve web_search? "),
            ),
            WAIT_S,
        )
        return answers, session.prompts

    answers, prompts = asyncio.run(drive())

    assert sorted(answers) == ["n", "y"]
    assert sorted(prompts) == [
        "approve web_fetch? ",
        "approve web_search? ",
    ]


class Held:
    """A ``PromptSession`` double the test decides when to answer.

    :attr:`asked` fires once a prompt is on screen and :attr:`release`
    lets it return, so a second reader can be put on the lock at a moment
    the test knows it is queued rather than at one it hopes it is.
    """

    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.asked = asyncio.Event()
        self.release = asyncio.Event()

    async def prompt_async(self, prompt: str) -> str:
        self.asked.set()
        await self.release.wait()
        return self._answer


def test_the_terminal_source_refuses_a_reader_queued_when_it_closes():
    """A question waiting for a terminal that has gone is refused, not left.

    :meth:`PromptToolkitSource.close` drops the session while a second
    read may still be queued behind the first — which is what ``Ctrl-C``
    at an approval card does. ``EOFError`` is what the REPL already treats
    as "nobody is there", so the queued approval denies instead of waiting
    on a terminal this process no longer owns.
    """

    async def drive():
        session = Held("y")
        source = PromptToolkitSource(session)
        first = asyncio.ensure_future(source.read("approve web_fetch? "))
        await asyncio.wait_for(session.asked.wait(), WAIT_S)
        second = asyncio.ensure_future(source.read("approve web_search? "))
        await asyncio.sleep(0)  # the second reader is now on the lock
        source.close()
        session.release.set()
        assert await asyncio.wait_for(first, WAIT_S) == "y"
        with pytest.raises(EOFError):
            await asyncio.wait_for(second, WAIT_S)

    asyncio.run(drive())


class OverlapWatchingStream:
    """A stream that reports whether two ``readline`` calls were ever live.

    The sleep is what makes the answer meaningful: two worker threads
    started back to back would both be inside ``readline`` for the same
    50 ms, which is the overlap a real stdin resolves by handing one typed
    line to whichever thread the kernel happens to wake. Asserting on the
    returned lines alone cannot see that — with a
    :class:`io.StringIO` the two reads usually come out in order anyway.
    """

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self._guard = threading.Lock()
        self._live = 0
        self.overlapped = False

    def readline(self) -> str:
        with self._guard:
            self._live += 1
            self.overlapped = self.overlapped or self._live > 1
        time.sleep(0.05)
        with self._guard:
            self._live -= 1
            return self._lines.pop(0) if self._lines else ""


def test_the_stream_source_serializes_two_concurrent_readers():
    """One stdin, one ``readline`` at a time — answers in the order asked.

    Two ``asyncio.to_thread(readline)`` calls on one stream both block in
    ``read(2)``, and the line the person typed goes to whichever thread
    the kernel wakes: the question they answered is not necessarily the
    one their answer settles. Serialized, the first question gets the
    first line.
    """

    async def drive():
        stream = OverlapWatchingStream(["first\n", "second\n"])
        source = StreamSource(stream)
        first = asyncio.ensure_future(source.read("q1"))
        await asyncio.sleep(0)  # let the first reader take the lock
        second = asyncio.ensure_future(source.read("q2"))
        lines = await asyncio.wait_for(asyncio.gather(first, second), WAIT_S)
        return lines, stream.overlapped

    lines, overlapped = asyncio.run(drive())

    assert lines == ["first", "second"]
    assert not overlapped, "two readline threads were live on one stream"


class HeldStream:
    """A stream whose ``readline`` blocks on a real thread until released.

    ``StreamSource`` reads through :func:`asyncio.to_thread`, so the
    holding has to be a :class:`threading.Event` — an asyncio one would
    never be set by a loop that is waiting for this thread.
    """

    def __init__(self, line: str) -> None:
        self._line = line
        self.asked = threading.Event()
        self.release = threading.Event()

    def readline(self) -> str:
        self.asked.set()
        self.release.wait(WAIT_S)
        return self._line


def test_the_stream_source_refuses_a_reader_queued_when_it_closes():
    """The closed check is re-made inside the lock, not only before it.

    A reader that passed the check before queueing would otherwise go on
    to ``readline`` a stream the source has already been told to let go.
    """

    async def drive():
        stream = HeldStream("first\n")
        source = StreamSource(stream)
        first = asyncio.ensure_future(source.read("q1"))
        while not stream.asked.is_set():
            await asyncio.sleep(0.01)
        second = asyncio.ensure_future(source.read("q2"))
        await asyncio.sleep(0)  # the second reader is now on the lock
        source.close()
        stream.release.set()
        assert await asyncio.wait_for(first, WAIT_S) == "first"
        with pytest.raises(EOFError):
            await asyncio.wait_for(second, WAIT_S)

    asyncio.run(drive())
