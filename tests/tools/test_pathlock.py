"""Contract tests for ``omicsclaw.tools._pathlock`` (plan 0029, task A).

Plan 0029 §8 trap 4 lives here, and so does the claim that makes this
module necessary at all: **two writes to one path really do run at the
same time.** That is not asserted from the module's own side, where it
would be a tautology, but through
:func:`~omicsclaw.engine.executor.execute_tool_calls`.

*Where* they overlap has changed, and the three engine-driven tests at
the bottom are the current answer. Inside one turn the scheduler now runs
a call that has not claimed ``concurrency_safe`` as a barrier, so plan
0028 §11 debt #1 is closed and two writes in one assistant turn are
ordered by the engine. Across **overlapping turns** it is not: each turn
schedules its own calls and knows nothing of the other, which is the
Channel Surface's ordinary shape. That is the concurrency this lock
exists for, and the three tests are the hazard, the same hazard with the
lock, and the barrier that covers the other case.

**Every wait in this file has a deadline.** A read-write lock that is
broken in the interesting direction does not return a wrong answer — it
hangs, and a hanging test is a test that gets killed by CI and reported
as flaky rather than as the defect it is. :func:`_run` therefore wraps
everything in :func:`asyncio.wait_for`. That guard is also what makes
:func:`test_the_event_loop_keeps_running_while_a_task_waits_for_a_lock`
work at all: swap the :class:`asyncio.Condition` for a
:class:`threading.Lock` and the whole loop stops, which is a timeout
rather than an assertion failure.

**Ordering is forced with :func:`_settle`, never with a wall-clock
sleep.** ``await asyncio.sleep(0.05)`` in a concurrency test is a guess
about scheduling that passes on a fast machine and fails on a loaded one.
Yielding to the loop until nothing is runnable is the same intent stated
exactly.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.executor import execute_tool_calls
from omicsclaw.schema import ToolCall, ToolDefinition, ToolResult
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools._pathlock import PATH_LOCKS, read_lock, write_lock

_T = TypeVar("_T")

_DEADLINE = 5.0
"""A hang guard, not a measurement: a lock that never releases deadlocks."""


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


async def _settle(rounds: int = 25) -> None:
    """Let every runnable task reach its next suspension point.

    ``asyncio.sleep(0)`` yields once. Several rounds are needed because
    a task queueing for a lock passes through more than one await —
    acquiring the condition's mutex, then waiting on the condition — and
    a test that only yielded once would be testing its own guess about
    how many.
    """
    for _ in range(rounds):
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def table_is_idle():
    """The process-wide table must start and end every test empty.

    This is plan 0029's "reference count reaching zero deletes the
    entry", asserted once for every test in the file rather than only in
    the test named for it. A leak shows up as the *next* test failing,
    which is exactly the confusing symptom the reference implementation's
    comment (``path_locker.go:12-16``) is warning about — so it is caught
    at the boundary of the test that caused it instead.
    """
    assert PATH_LOCKS.tracked_paths() == frozenset()
    yield
    assert PATH_LOCKS.tracked_paths() == frozenset(), (
        "a lock entry outlived the test that took it"
    )


@pytest.fixture
def target(tmp_path: pathlib.Path) -> pathlib.Path:
    """One file for contention, starting empty so a lost update shows."""
    path = tmp_path / "log.txt"
    path.write_text("", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Shared reads, exclusive writes.
# --------------------------------------------------------------------------


def test_two_readers_hold_one_path_at_the_same_time(target: pathlib.Path):
    """Shared means shared: the second reader does not wait for the first.

    Written as a rendezvous rather than as a count, because a count
    proves only that two readers ran, not that they overlapped. Each
    reader refuses to leave until both are inside, so an exclusive
    implementation deadlocks and the deadline fires.
    """
    async def main() -> None:
        inside = 0
        both = asyncio.Event()

        async def reader() -> None:
            nonlocal inside
            async with read_lock(target):
                inside += 1
                if inside == 2:
                    both.set()
                await both.wait()

        await asyncio.gather(reader(), reader())

    _run(main())


def test_a_writer_waits_for_every_reader_to_leave(target: pathlib.Path):
    """A read in flight blocks a write, and the order proves which way."""

    async def main() -> list[str]:
        order: list[str] = []
        release = asyncio.Event()

        async def reader() -> None:
            async with read_lock(target):
                order.append("read-in")
                await release.wait()
                order.append("read-out")

        async def writer() -> None:
            async with write_lock(target):
                order.append("write")

        reading = asyncio.create_task(reader())
        await _settle()
        writing = asyncio.create_task(writer())
        await _settle()

        assert not writing.done(), "the writer ran while a reader held the path"
        release.set()
        await asyncio.gather(reading, writing)
        return order

    assert _run(main()) == ["read-in", "read-out", "write"]


def test_a_reader_waits_for_a_writer_to_leave(target: pathlib.Path):
    """And the mirror image, so neither half is exclusive by accident."""

    async def main() -> list[str]:
        order: list[str] = []
        release = asyncio.Event()

        async def writer() -> None:
            async with write_lock(target):
                order.append("write-in")
                await release.wait()
                order.append("write-out")

        async def reader() -> None:
            async with read_lock(target):
                order.append("read")

        writing = asyncio.create_task(writer())
        await _settle()
        reading = asyncio.create_task(reader())
        await _settle()

        assert not reading.done(), "a read ran while a write held the path"
        release.set()
        await asyncio.gather(writing, reading)
        return order

    assert _run(main()) == ["write-in", "write-out", "read"]


def test_a_waiting_writer_is_not_starved_by_a_stream_of_readers(
    target: pathlib.Path,
):
    """A reader arriving after a queued writer waits behind it.

    Go's ``sync.RWMutex`` blocks new readers once a writer is waiting,
    and this reproduces that rather than inventing a policy: an agent
    loop that reads a file far more often than it writes one would
    otherwise defer the write for as long as the reads keep coming.

    Mutation: drop ``self._waiting_writers == 0`` from
    :meth:`_PathLock.acquire_read`'s predicate and the order becomes
    ``["read-1", "read-2", "write"]``.
    """

    async def main() -> list[str]:
        order: list[str] = []
        release = asyncio.Event()

        async def first_reader() -> None:
            async with read_lock(target):
                order.append("read-1")
                await release.wait()

        async def writer() -> None:
            async with write_lock(target):
                order.append("write")

        async def late_reader() -> None:
            async with read_lock(target):
                order.append("read-2")

        first = asyncio.create_task(first_reader())
        await _settle()
        writing = asyncio.create_task(writer())
        await _settle()
        late = asyncio.create_task(late_reader())
        await _settle()

        release.set()
        await asyncio.gather(first, writing, late)
        return order

    assert _run(main()) == ["read-1", "write", "read-2"]


def test_two_different_paths_do_not_wait_for_each_other(
    tmp_path: pathlib.Path,
):
    """The positive control for every exclusion test above.

    A single global mutex would pass all of them and fail this one by
    deadlocking, which is the whole reason the lock is per path. Holding
    both at once from one task is the sharpest form: it cannot complete
    unless the two locks are genuinely independent.
    """

    async def main() -> int:
        async with write_lock(tmp_path / "a.txt"):
            async with write_lock(tmp_path / "b.txt"):
                return len(PATH_LOCKS.tracked_paths())

    assert _run(main()) == 2


# --------------------------------------------------------------------------
# The reason this module exists: concurrent writes to one path.
# --------------------------------------------------------------------------


async def _append(path: pathlib.Path, mark: str, *, locked: bool) -> None:
    """Read, yield, write — the shape every read-modify-write tool has.

    The ``await`` in the middle is not artificial. Any real ``write``
    tool awaits something between reading and writing (approval, a
    progress report, the write itself), and that is the window in which
    the other coroutine runs.
    """
    if locked:
        async with write_lock(path):
            await _append_unlocked(path, mark)
        return
    await _append_unlocked(path, mark)


async def _append_unlocked(path: pathlib.Path, mark: str) -> None:
    text = path.read_text(encoding="utf-8")
    await asyncio.sleep(0)
    path.write_text(text + mark, encoding="utf-8")


def test_two_unlocked_writers_lose_an_update(target: pathlib.Path):
    """The hazard, demonstrated, so the next test is not a tautology.

    Both coroutines read the empty file before either writes, so one
    append is silently discarded. If this ever stops being true the lock
    below is protecting nothing and the reason to keep it has changed.
    """
    async def main() -> None:
        await asyncio.gather(
            _append(target, "A", locked=False),
            _append(target, "B", locked=False),
        )

    _run(main())

    assert len(target.read_text(encoding="utf-8")) == 1


def test_two_concurrent_writers_to_one_path_are_serialised(
    target: pathlib.Path,
):
    """The same two coroutines, taking the lock. Both updates survive.

    Run through real :func:`asyncio.gather` concurrency rather than one
    after the other — sequential calls would pass against a lock that
    does nothing at all.
    """
    async def main() -> None:
        await asyncio.gather(
            _append(target, "A", locked=True),
            _append(target, "B", locked=True),
        )

    _run(main())

    assert sorted(target.read_text(encoding="utf-8")) == ["A", "B"]


# --------------------------------------------------------------------------
# Trap 4 — the key is the resolved path, not the string the model sent.
# --------------------------------------------------------------------------


def test_two_names_for_one_file_take_the_same_lock(
    target: pathlib.Path, tmp_path: pathlib.Path
):
    """Plan 0029 trap 4, stated as identity rather than as timing.

    ``sub/../log.txt`` and a symlink to ``log.txt`` are the same file. If
    the table keyed on the string it was handed, each would get its own
    entry — three locks, no exclusion, and every test above still green
    because they all use one spelling.

    Mutation: make ``_key`` return ``Path(path)`` unresolved and both
    reference counts drop to zero while ``tracked_paths`` grows to three.
    """
    (tmp_path / "sub").mkdir()
    dotted = tmp_path / "sub" / ".." / "log.txt"
    linked = tmp_path / "latest.txt"
    linked.symlink_to(target)

    async def main() -> tuple[int, int, int]:
        async with write_lock(target):
            return (
                PATH_LOCKS.reference_count(dotted),
                PATH_LOCKS.reference_count(linked),
                len(PATH_LOCKS.tracked_paths()),
            )

    assert _run(main()) == (1, 1, 1)


def test_two_aliases_writing_at_once_are_still_serialised(
    target: pathlib.Path, tmp_path: pathlib.Path
):
    """And the consequence of the above, as a lost update that is not lost.

    This is the test the aliasing bug actually breaks in production: two
    ``write`` calls in one turn naming one file two ways, which is
    exactly what a model that has been shown both an absolute and a
    relative path will emit.
    """
    (tmp_path / "sub").mkdir()
    dotted = tmp_path / "sub" / ".." / "log.txt"

    async def main() -> None:
        await asyncio.gather(
            _append(target, "A", locked=True),
            _append(dotted, "B", locked=True),
        )

    _run(main())

    assert sorted(target.read_text(encoding="utf-8")) == ["A", "B"]


# --------------------------------------------------------------------------
# Reference counting, including the paths ordinary use never exercises.
# --------------------------------------------------------------------------


def test_the_table_forgets_a_path_when_the_last_holder_leaves(
    target: pathlib.Path,
):
    """Counted up while held, down on release, deleted at zero.

    The shape of harness9's ``TestPathLocker_RefCounting``, which takes
    three read locks and releases two before checking. Three nested read
    locks are legal for the same reason two readers are concurrent.
    """

    async def main() -> list[int]:
        counts = []
        async with read_lock(target):
            async with read_lock(target):
                async with read_lock(target):
                    counts.append(PATH_LOCKS.reference_count(target))
                counts.append(PATH_LOCKS.reference_count(target))
            counts.append(PATH_LOCKS.reference_count(target))
        counts.append(PATH_LOCKS.reference_count(target))
        counts.append(len(PATH_LOCKS.tracked_paths()))
        return counts

    assert _run(main()) == [3, 2, 1, 0, 0]


def test_a_reference_is_released_when_the_body_raises(target: pathlib.Path):
    """A tool that fails mid-write must not leave the file locked forever.

    The ``finally`` that does this is invisible in ordinary use, which is
    why it gets a test rather than a comment.
    """

    async def main() -> int:
        with pytest.raises(RuntimeError):
            async with write_lock(target):
                raise RuntimeError("the tool blew up")
        return len(PATH_LOCKS.tracked_paths())

    assert _run(main()) == 0


def test_a_writer_cancelled_while_still_queued_leaves_nothing_behind(
    target: pathlib.Path,
):
    """The engine's per-tool timeout, firing during a wait.

    ``engine/executor.py`` wraps each call in
    :func:`asyncio.timeout`, so a tool queued behind a slow write is
    cancelled *before* it ever holds the lock. The reference is claimed
    before acquiring — deliberately, so an entry is not evicted from
    under a waiter — which makes this the one path where the count could
    be left high and the table could grow without bound.

    Both halves: the count comes back down, and the reader that was
    blocked behind the cancelled writer still gets through, so the
    ``_waiting_writers`` bookkeeping is not left permanently raised.
    """

    async def waiting_writer() -> None:
        async with write_lock(target):
            pass

    async def main() -> list[int]:
        counts = []
        async with write_lock(target):
            queued = asyncio.create_task(waiting_writer())
            await _settle()
            counts.append(PATH_LOCKS.reference_count(target))
            queued.cancel()
            outcome = await asyncio.gather(queued, return_exceptions=True)
            assert isinstance(outcome[0], asyncio.CancelledError)
            await _settle()
            counts.append(PATH_LOCKS.reference_count(target))

        async with read_lock(target):
            counts.append(PATH_LOCKS.reference_count(target))
        return counts

    assert _run(main()) == [2, 1, 1]


# --------------------------------------------------------------------------
# asyncio, not threading.
# --------------------------------------------------------------------------


def test_the_event_loop_keeps_running_while_a_task_waits_for_a_lock(
    target: pathlib.Path,
):
    """Plan 0029 §4 Q7, the half that decides which primitive is legal.

    A :class:`threading.Lock` used here would block the **thread** that
    is the event loop, so the ticks below would never resume and this
    test would die on its deadline rather than fail an assertion. With an
    asyncio primitive the waiter merely suspends and everything else
    keeps running — including, in production, the other tools in the same
    turn and the surface streaming to the user.
    """

    async def waiting_writer() -> None:
        async with write_lock(target):
            pass

    async def main() -> int:
        ticks = 0
        async with write_lock(target):
            queued = asyncio.create_task(waiting_writer())
            for _ in range(5):
                await asyncio.sleep(0)
                ticks += 1
            assert not queued.done(), "the writer did not wait"
        await queued
        return ticks

    assert _run(main()) == 5


# --------------------------------------------------------------------------
# The same thing again, through the engine that will actually schedule it.
# --------------------------------------------------------------------------


class _Appender:
    """A minimal write tool, with and without the lock.

    Hand-written and structurally typed, importing nothing from
    ``omicsclaw.tools.base``: what is under test is the scheduler's
    behaviour, so the tool is kept as close to nothing as the Protocol
    allows.
    """

    def __init__(self, path: pathlib.Path, *, locked: bool) -> None:
        self._path = path
        self._locked = locked

    @property
    def name(self) -> str:
        return "append_locked" if self._locked else "append_raw"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description="Append one character to a file.",
            input_schema={
                "type": "object",
                "properties": {"mark": {"type": "string"}},
            },
        )

    async def execute(self, arguments: str) -> str:
        mark = json.loads(arguments)["mark"]
        await _append(self._path, mark, locked=self._locked)
        return f"appended {mark}"


async def _one_turn(registry: ToolRegistry, name: str) -> None:
    """Two calls to one tool in one turn, through the engine's scheduler.

    ``EngineConfig()`` leaves ``max_concurrent_tools`` at ``0`` — no
    ceiling — and ``serialize_unsafe_tools`` at ``True``. ``_Appender``
    declares no policy, so it resolves to ``ToolPolicy()`` and its
    ``concurrency_safe=False`` makes each of these calls a barrier.
    """
    calls = [
        ToolCall(id="c0", name=name, arguments='{"mark": "A"}'),
        ToolCall(id="c1", name=name, arguments='{"mark": "B"}'),
    ]
    await _run_calls(registry, calls)


async def _two_turns(registry: ToolRegistry, name: str) -> None:
    """The same two calls, one per turn, with the turns overlapping.

    What the Channel Surface has by construction: two conversations
    interleaving on one event loop. The barrier orders the calls *within*
    one turn and knows nothing about a second turn, so this is the
    concurrency it does not cover.
    """
    await asyncio.gather(
        _run_calls(registry, [ToolCall(id="c0", name=name, arguments='{"mark": "A"}')]),
        _run_calls(registry, [ToolCall(id="c1", name=name, arguments='{"mark": "B"}')]),
    )


async def _run_calls(registry: ToolRegistry, calls: list[ToolCall]) -> None:
    results: list[ToolResult | None] = []
    async for _ in execute_tool_calls(registry, calls, EngineConfig(), results):
        pass
    for result in results:
        assert result is not None and not result.is_error, result


def test_the_engine_runs_two_unsafe_writes_in_one_turn_one_at_a_time(
    target: pathlib.Path,
):
    """Plan 0028 §11 debt #1, from the side that was missing the barrier.

    This file used to pin the opposite: the scheduler started every call
    in a turn unconditionally, ``ToolPolicy.concurrency_safe`` had no
    consumer, and one assistant turn emitting two writes to one path lost
    one of them. The engine now reads the flag and runs a call that has
    not claimed concurrency safety alone, so both updates survive **with
    no lock in the tool at all**.
    """
    registry = ToolRegistry([_Appender(target, locked=False)])

    _run(_one_turn(registry, "append_raw"))

    assert sorted(target.read_text(encoding="utf-8")) == ["A", "B"]


def test_two_overlapping_turns_are_not_covered_by_the_barrier(
    target: pathlib.Path,
):
    """Why this module survives the barrier rather than being replaced by it.

    ``execute_tool_calls`` orders the calls of **one** turn. Two turns
    driven concurrently — two chats, a sub-agent, a background run — each
    schedule their own, and neither knows the other exists. The lost
    update is back, which is what makes the next test a real test.
    """
    registry = ToolRegistry([_Appender(target, locked=False)])

    _run(_two_turns(registry, "append_raw"))

    assert len(target.read_text(encoding="utf-8")) == 1


def test_the_lock_serialises_two_writes_the_barrier_does_not_cover(
    target: pathlib.Path,
):
    """The same two turns, one line different in the tool."""
    registry = ToolRegistry([_Appender(target, locked=True)])

    _run(_two_turns(registry, "append_locked"))

    assert sorted(target.read_text(encoding="utf-8")) == ["A", "B"]
