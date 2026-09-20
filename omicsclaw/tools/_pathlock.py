"""One lock per file, held on the event loop rather than on a thread.

Plan 0029 §4 Q7. Two coroutines writing the same file is not a race this
layer might one day have — it is a race it has **today**, and the lost
update is real.

Part of it is now stopped upstream. ``engine/executor.py`` reads
:attr:`~omicsclaw.tools.base.ToolPolicy.concurrency_safe` through
:meth:`~omicsclaw.tools.registry.ToolRegistry.is_concurrency_safe` and
runs a call that has not claimed it as a **barrier**, alone, so two
``write`` calls the model emits in one assistant turn are ordered by the
scheduler — plan 0028 §11 debt #1, closed.

What remains is everything that is not one turn, and this module is the
only defence there is for it:

* **Overlapping turns.** The barrier orders the calls of the turn it is
  scheduling and knows nothing about a second one. Two Channel
  conversations, a sub-agent, a background run — each drives its own
  ``execute_tool_calls`` on the same event loop and the same files.
* **A tool that declared itself safe and is not.** ``concurrency_safe``
  is the author's claim, and the scheduler has no way to check it.
* **Concurrency inside one call.** A tool that fans out its own writes is
  one call to the barrier.

Which is why it ships with the first tool that can write rather than with
the optimisation pass it looks like.

**asyncio primitives, and the reason is not taste.** The reference
implementation (``harness9/internal/tools/path_locker.go``) uses
``sync.RWMutex`` because a goroutine can be preempted between any two
instructions, so a real mutual-exclusion primitive is the only thing that
makes a section atomic. (Not because goroutines are OS threads — they are
multiplexed onto them, and a blocked one yields its thread to the
runtime.) Ours are Tasks on one event loop, preempted only at an
``await``, and a :class:`threading.Lock` there is wrong in both
directions at once:

* ``with threading.Lock():`` around an ``await`` does not make the
  section atomic. The lock is released only when the block exits, but the
  coroutine *yields* at every ``await`` inside it, so a second coroutine
  runs in the middle of a "protected" read-modify-write. It looks like a
  lock and is not one.
* And when the second coroutine reaches ``lock.acquire()``, it blocks the
  **thread** — which is the event loop — so nothing can ever release it.
  A single-threaded deadlock, from a lock that appeared to be working
  moments earlier.

:class:`asyncio.Condition` has neither failure: a waiter suspends the
Task and returns control to the loop.
``test_the_event_loop_keeps_running_while_a_task_waits_for_a_lock``
pins the second half, because it is the half that turns into a hang
rather than into a wrong answer.

**The key is the resolved path, never the string the model sent.**
``./results/a.csv``, ``results/../results/a.csv`` and
``/work/run-7/results/a.csv`` are one file with three names, and locking
the names takes three different locks — a lock that is held, that costs
something, and that protects nothing. :func:`_key` resolves before
looking anything up, so aliases collapse. Note that harness9 keys on
``filepath.Clean`` (``path_locker.go:40``), which normalises ``.`` and
``..`` but does **not** make a path absolute; it is safe there only
because its three callers — ``read_file.go:124``, ``write_file.go:104``
and ``edit_file.go:110`` — all happen to pass ``safePath`` output. Doing the
normalisation inside the table rather than trusting callers is the one
place this deliberately does not copy the reference.

**Reference counting, straight from the reference, for the reason given
there** (``path_locker.go:12-16``): an entry is created on first use and
**deleted when the last holder leaves**, so a long-running agent that
touches a million paths does not accumulate a million locks. The count is
incremented *before* acquiring and decremented *after* releasing —
crucially covering the waiting period, because an entry evicted while
somebody is queued on it would be recreated by the next arrival, and two
lock objects for one path is the aliasing bug wearing different clothes.

The same counting buys something Go had no need of: because a table entry
never outlives its last holder, an :class:`asyncio.Condition` created on
one event loop is never found by a later one. Repeated
:func:`asyncio.run` calls — which is what this project's test suite is,
:mod:`pytest-asyncio` not being installed — would otherwise hit
``RuntimeError: ... is bound to a different event loop`` on the second
run.

**The table itself takes no mutex, where the Go version takes one.**
``pathLocksMu`` guards against two OS threads mutating the map at once.
Here, ``_claim`` and ``_release`` contain no ``await``, and a coroutine
cannot be preempted except at an ``await``, so each is already atomic
with respect to every other Task on the loop. The assumption that buys
this is **one event loop per process**, which is what every surface in
this repository does (one uvicorn loop for Desktop, one loop for the
Channel runner). A deployment that ran two loops in one process would get
a loud ``RuntimeError`` out of asyncio's own loop binding rather than a
silently unsynchronised lock — the better of the two failures, and the
reason a :class:`threading.Lock` is not added "just in case": guarding
the dict while leaving the condition variable loop-bound would hide the
loud failure without fixing anything.

**Writer preference, matching ``sync.RWMutex``.** A reader that arrives
while a writer is queued waits. Without that, a tool loop doing many
reads and one write can starve the write indefinitely, and Go's RWMutex
blocks new readers once a writer is waiting for exactly this reason.

**Not re-entrant.** Taking a read lock and then a write lock on the same
path from one Task deadlocks — there is no owner tracking, and there
should not be, because the operation that needs both is a single
read-modify-write that should hold **one** write lock for its whole
length. That is a note for ``edit`` (plan 0029 §12), which is the first
tool shaped that way.

**Leaf.** The standard library, and nothing else.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path


def _key(path: str | Path) -> Path:
    """The canonical identity of a file, which is what gets locked.

    :meth:`Path.resolve` follows symlinks too, so a path and a link to it
    are one key — the same reasoning as
    :meth:`omicsclaw.tools._workspace.Workspace.resolve`, and the reason
    a tool may pass that method's output here unchanged.

    A relative path is resolved against the process working directory,
    which is correct only while nothing calls :func:`os.chdir`. Tools in
    this layer pass an already-absolute path because the workspace
    boundary hands them one; the fallback exists so a script is not
    forced to care.
    """
    return Path(path).resolve()


class _PathLock:
    """A readers-writer lock for one path, plus its reference count.

    Private because the table is the interface: a caller holding one of
    these could acquire without claiming a reference, and the entry would
    be evicted from under it.

    :class:`asyncio.Condition` rather than hand-rolled futures. The
    alternative — a queue of futures, each resolved by whoever releases —
    has to *grant* the lock to a waiter that may already have been
    cancelled, and handing the grant back correctly is the classic place
    this kind of code goes wrong. Here all state is mutated only while
    holding the condition's own mutex and only after
    :meth:`asyncio.Condition.wait_for` has returned, so a cancelled
    waiter simply never took the lock and there is nothing to hand back.

    The cost of that choice, stated: the *release* path also awaits the
    condition's mutex, so it is not strictly non-suspending. The mutex is
    never held across an ``await`` by anyone, so acquiring it almost
    always completes without suspending; the trade is a small
    cancellation window in release against a whole class of handoff bugs
    in acquire.
    """

    __slots__ = (
        "_condition",
        "_readers",
        "_waiting_writers",
        "_writing",
        "references",
    )

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._readers = 0
        self._writing = False
        self._waiting_writers = 0
        # Holders plus waiters for this entry. Owned by the table, which
        # is the only thing that may change it: the count decides when
        # the entry is evicted, and an entry evicted while somebody is
        # queued on it is the whole bug it exists to prevent.
        self.references = 0

    @property
    def readers(self) -> int:
        """Concurrent readers inside the critical section, for tests."""
        return self._readers

    @property
    def writing(self) -> bool:
        """Whether a writer is inside the critical section, for tests."""
        return self._writing

    async def acquire_read(self) -> None:
        """Wait until reading is safe, then count this reader in.

        ``_waiting_writers == 0`` is the writer-preference half: a reader
        arriving while a writer is queued joins the queue behind it
        instead of extending the current read burst.
        """
        async with self._condition:
            await self._condition.wait_for(
                lambda: not self._writing and self._waiting_writers == 0
            )
            self._readers += 1

    async def release_read(self) -> None:
        """Drop this reader and wake a waiting writer when it was the last."""
        async with self._condition:
            self._readers -= 1
            if self._readers == 0:
                self._condition.notify_all()

    async def acquire_write(self) -> None:
        """Wait for exclusive access, announcing the wait while waiting.

        The counter is raised *before* waiting and lowered in a
        ``finally`` so that a cancelled writer does not leave readers
        deferring to a writer that has gone away — which would be a
        permanent stall of every reader on that path. Dropping to zero
        wakes them; on the ordinary path that wake-up is spurious, and
        :meth:`asyncio.Condition.wait_for` re-checks its predicate, so
        the readers see the write that is about to start and wait again.
        """
        async with self._condition:
            self._waiting_writers += 1
            try:
                await self._condition.wait_for(
                    lambda: not self._writing and self._readers == 0
                )
            finally:
                self._waiting_writers -= 1
                if self._waiting_writers == 0:
                    self._condition.notify_all()
            self._writing = True

    async def release_write(self) -> None:
        """Release exclusive access and wake everyone waiting on it."""
        async with self._condition:
            self._writing = False
            self._condition.notify_all()


class PathLockTable:
    """Every path currently locked, and nothing else.

    Instantiable so a test can have its own, but correctness needs
    exactly one per process: two tables are two locks per path, which is
    no lock at all. :data:`PATH_LOCKS` is that one, and
    :func:`read_lock` / :func:`write_lock` are how tools reach it.
    """

    __slots__ = ("_locks",)

    def __init__(self) -> None:
        self._locks: dict[Path, _PathLock] = {}

    def _claim(self, key: Path) -> _PathLock:
        """The entry for ``key``, created if absent, with a reference held.

        No ``await`` anywhere in here, which is what makes it atomic
        against every other Task on this loop — see the module docstring.
        """
        lock = self._locks.get(key)
        if lock is None:
            lock = _PathLock()
            self._locks[key] = lock
        lock.references += 1
        return lock

    def _release(self, key: Path, lock: _PathLock) -> None:
        """Drop a reference, and forget the path when it was the last.

        Deleting at zero is what keeps the table the size of the work in
        flight rather than the size of everything ever touched.
        """
        lock.references -= 1
        if lock.references <= 0:
            self._locks.pop(key, None)

    def reference_count(self, path: str | Path) -> int:
        """Holders plus waiters for ``path``; ``0`` when it is not tracked."""
        lock = self._locks.get(_key(path))
        return lock.references if lock is not None else 0

    def tracked_paths(self) -> frozenset[Path]:
        """Every path with a live entry. Empty when the table is idle."""
        return frozenset(self._locks)

    @asynccontextmanager
    async def read(self, path: str | Path) -> AsyncIterator[Path]:
        """Hold a shared lock on ``path`` for the block.

        Several readers hold it at once; a writer waits for all of them.
        Yields the resolved path that was actually locked, so a caller
        can see which file its alias became.
        """
        key = _key(path)
        lock = self._claim(key)
        try:
            await lock.acquire_read()
            try:
                yield key
            finally:
                await lock.release_read()
        finally:
            self._release(key, lock)

    @asynccontextmanager
    async def write(self, path: str | Path) -> AsyncIterator[Path]:
        """Hold an exclusive lock on ``path`` for the block.

        The reference is dropped in the outer ``finally``, so a writer
        cancelled **while still queued** — the engine's per-tool timeout
        firing during a wait — leaves no entry behind. That is the leak
        the reference count exists to prevent, and it is the path that
        does not get exercised by ordinary use.
        """
        key = _key(path)
        lock = self._claim(key)
        try:
            await lock.acquire_write()
            try:
                yield key
            finally:
                await lock.release_write()
        finally:
            self._release(key, lock)


PATH_LOCKS = PathLockTable()
"""The process-wide table. One, for the reason :class:`PathLockTable` says."""


def read_lock(path: str | Path) -> AbstractAsyncContextManager[Path]:
    """Shared lock on ``path`` in the process-wide table.

    ``async with read_lock(p):`` — a module-level function rather than
    ``PATH_LOCKS.read`` at each call site so that no tool has to know
    which table is the real one, which is the shape harness9 exposes
    (``RLockPath``) for the same reason.
    """
    return PATH_LOCKS.read(path)


def write_lock(path: str | Path) -> AbstractAsyncContextManager[Path]:
    """Exclusive lock on ``path`` in the process-wide table.

    ``async with write_lock(p):`` — what ``write`` and, later, ``edit``
    wrap their whole read-modify-write in.
    """
    return PATH_LOCKS.write(path)


__all__ = [
    "PATH_LOCKS",
    "PathLockTable",
    "read_lock",
    "write_lock",
]
