"""One plan per session, in a process that serves many of them.

Plan 0039 §2.4. The reference harness has no equivalent and does not
need one: its ``main.go`` builds a single ``PlanStore``, hands it to the
engine and to the tool, and the whole process is one conversation
(``cmd/harness9/main.go``). Here the Channel and Desktop surfaces run
many sessions through **one** :class:`~omicsclaw.tools.ToolRegistry`,
built once by :func:`~omicsclaw.entry.assembly.build_app` — so the tool
is shared and the plan cannot be. This is the indirection that reconciles
the two: the tool holds a book, and resolves the session at call time.
"""

from __future__ import annotations

import threading
from typing import Callable, Sequence

from .archive import PlanArchive, PlanArchiveError
from .plan import PlanItem, PlanStore, PlanWriteSink

__all__ = ["ArchiveErrorSink", "PlanBook"]


ArchiveErrorSink = Callable[[str, PlanArchiveError], None]
"""Called with ``(session_id, error)`` when storage lets the book down.

Binding one is what turns a storage failure from fatal into reported. It
is a parameter rather than a ``try``/``pass`` because this package may
not log: a swallowed :exc:`~omicsclaw.planning.archive.PlanArchiveError`
would make an unwritable plan directory completely invisible, and the
symptom — a plan that resets itself every restart — looks like a bug in
the model.

**No sink means the error propagates**, which is the right default for a
test and for a caller that has not thought about it.
:func:`~omicsclaw.entry.planning.build_plan_book` binds one that logs.
"""


class PlanBook:
    """``session_id`` → :class:`~omicsclaw.planning.plan.PlanStore`.

    :param archive: Where plans are kept between processes. ``None``
        keeps them in memory only, which is what a test wants and what a
        deployment gets if it turns persistence off.
    :param on_archive_error: See :data:`ArchiveErrorSink`.

    Locked with a :class:`threading.Lock` for the reason
    :class:`~omicsclaw.planning.plan.PlanStore` is: a tool may be running
    on a worker thread, and two sessions' first tool calls can arrive at
    once.
    """

    __slots__ = ("_archive", "_lock", "_on_error", "_stores")

    def __init__(
        self,
        archive: PlanArchive | None = None,
        *,
        on_archive_error: ArchiveErrorSink | None = None,
    ) -> None:
        self._archive = archive
        self._on_error = on_archive_error
        self._lock = threading.Lock()
        self._stores: dict[str, PlanStore] = {}

    def for_session(self, session_id: str) -> PlanStore:
        """The store for *session_id*, restored from the archive once.

        Creating it binds :meth:`~omicsclaw.planning.plan.PlanStore.write`
        to the archive, so every accepted plan write is on disk before the
        tool returns. That is stricter than the reference harness's
        write-time checkpoint (``loop_phases.go:310``), which persists
        after the turn's tools have all run.

        **The archive is read once per session, not once per exchange**,
        which the reference harness does the other way round: it reloads
        from its session store at the start of *every* interaction
        (``loop_phases.go:110``). Reading once is correct here and not
        merely cheaper, because in this arrangement the in-memory store
        is the *only* writer of the file — the archive cannot have moved
        underneath it. It stops being correct the moment a second process
        writes the same workspace's plans, and that is the condition to
        re-check before allowing one: the symptom would be two agents
        silently overwriting each other's plan with no error anywhere.

        **An empty *session_id* gets a store that is never persisted.**
        The anonymous path — :func:`~omicsclaw.entry.turn.run_turn`
        without a session — has no identity to resume under, so two
        unrelated runs would otherwise share one file and each would read
        the other's plan as its own history.

        The load happens outside the lock, so a slow filesystem does not
        stall another session's first call. The cost is stated rather
        than hidden: a second caller asking for the same new session in
        that window sees the store before it is seeded.
        :func:`~omicsclaw.entry.planning.build_injector` is called at the
        start of an exchange, before any tool of that exchange can run,
        which is what keeps the window shut in practice.
        """
        with self._lock:
            store = self._stores.get(session_id)
            if store is not None:
                return store
            store = PlanStore(on_write=self._sink(session_id))
            self._stores[session_id] = store
        if self._archive is not None and session_id:
            self._load(session_id, store)
        return store

    def sessions(self) -> tuple[str, ...]:
        """Every session this book has been asked about, in first-use order."""
        with self._lock:
            return tuple(self._stores)

    def forget(self, session_id: str) -> None:
        """Drop the in-memory store for *session_id*. Storage is untouched.

        For a surface evicting an idle session, in the way
        :meth:`~omicsclaw.entry.session.SessionRegistry._evict_sessions`
        does. Leaving the archive alone is the point: eviction is a
        memory decision, and the next :meth:`for_session` restores the
        plan rather than starting a resumed conversation with a blank one.
        """
        with self._lock:
            self._stores.pop(session_id, None)

    # ---- internals -------------------------------------------------------

    def _sink(self, session_id: str) -> PlanWriteSink | None:
        """The write-through callback for *session_id*, or ``None``."""
        archive = self._archive
        if archive is None or not session_id:
            return None

        def save(items: Sequence[PlanItem]) -> None:
            try:
                archive.save(session_id, items)
            except PlanArchiveError as error:
                if self._on_error is None:
                    raise
                self._on_error(session_id, error)

        return save

    def _load(self, session_id: str, store: PlanStore) -> None:
        """Seed *store* from the archive, reporting a bad file.

        Uses :meth:`~omicsclaw.planning.plan.PlanStore.restore` rather
        than ``write`` so that reading a plan does not write it back —
        see there. A failure leaves the store empty, which is the only
        safe degradation: the alternative is refusing to start an
        exchange because a file from a previous one cannot be parsed.
        """
        assert self._archive is not None
        try:
            store.restore(self._archive.load(session_id))
        except PlanArchiveError as error:
            if self._on_error is None:
                raise
            self._on_error(session_id, error)
