"""``omicsclaw/planning`` — what a plan is, and where one session's lives.

Plan 0039 §3. Three types and nothing else: a status, an item, and the
store one session's items sit in. No rendering (:mod:`.render`), no
validation (:mod:`.rules`), no persistence (:mod:`.archive`) — this
module is the state, and the state is deliberately the smallest part.

**Standard library only.** Not even ``omicsclaw.schema``: a plan item is
not a message, and the moment this module can name a ``Message`` someone
will make :class:`PlanStore` produce one.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Sequence

__all__ = ["PlanItem", "PlanStatus", "PlanStore", "PlanWriteSink"]


class PlanStatus(StrEnum):
    """Where one plan item is in its life.

    A :class:`~enum.StrEnum`, so ``PlanStatus.PENDING == "pending"`` holds
    and an item round-trips through JSON without a converter.

    The transitions this vocabulary is meant to permit::

        pending ──► in_progress ──► completed
           │              │
           └──────────────┴──► cancelled

    Nothing in this module enforces that. :func:`omicsclaw.planning.rules.
    validate` is what refuses the two paths that matter, and it lives
    there rather than here because a store that silently rewrote what it
    was handed would make "what did the model actually ask for" an
    unanswerable question.
    """

    PENDING = "pending"
    """Not started. What a newly written item is."""

    IN_PROGRESS = "in_progress"
    """Being worked on now. The model marks an item this *before* the
    tool calls that carry it out, which is what makes the distinction
    between "claimed" and "finished" observable from outside."""

    COMPLETED = "completed"
    """Done, with something to show for it — a file written, a command
    run. :func:`~omicsclaw.planning.rules.validate` is what keeps a batch
    of these from being asserted at once."""

    CANCELLED = "cancelled"
    """Abandoned deliberately. Distinct from omission: dropping an item
    from a write trims it, cancelling it records that it was considered
    and dropped, and only the second survives
    :func:`~omicsclaw.planning.rules.merge`."""


@dataclass(frozen=True, slots=True)
class PlanItem:
    """One step: an identity, what it is, and where it has got to.

    Frozen, which is what lets :meth:`PlanStore.read` hand out its own
    tuple instead of a copy — see there.

    :param id: The model's own identifier for this step. It is the model's
        to assign, and the *only* thing tying a written item to its own
        history, so the anti-cheat rule and the merge both key on it. Two
        items sharing one id is the model contradicting itself within a
        single call; :func:`~omicsclaw.planning.rules.merge` keeps the
        first and says so.
    :param content: What the step is, as a concrete action. Unbounded
        here: the only thing asking for one action per item is the tool
        description, and plan 0039 §5 records that as a known cost rather
        than pretending a length cap would be an answer.
    :param status: Where it has got to. Defaults to :attr:`PlanStatus.
        PENDING`, so the ordinary act of writing down a new step needs no
        ceremony.
    """

    id: str
    content: str
    status: PlanStatus = PlanStatus.PENDING

    @property
    def is_active(self) -> bool:
        """Still outstanding — ``pending`` or ``in_progress``.

        The one predicate two very different consumers share: what gets
        re-injected every turn (:func:`~omicsclaw.planning.render.
        format_plan`) and what :meth:`PlanStore.active_count` counts.
        Writing it twice is how the injected block and the progress
        counter start disagreeing about whether a run is finished.
        """
        return self.status in (PlanStatus.PENDING, PlanStatus.IN_PROGRESS)


PlanWriteSink = Callable[[Sequence[PlanItem]], None]
"""Called with the new contents after every :meth:`PlanStore.write`.

The write-through seam: :class:`~omicsclaw.planning.book.PlanBook` binds
one that saves to an archive, which is how a plan survives a crash. The
reference harness instead checkpoints from its engine loop after a
successful ``plan_write`` (``loop_phases.go:310``); doing it here narrows
the crash window from "one turn" to "one file write", and costs the
engine no knowledge of planning at all.

**A sink must not raise**, and a sink that does costs the tool call that
triggered it. That contract is stated rather than defended with a
``try``: this package may not log, so swallowing an exception here would
make an unwritable plan file completely silent. Whoever binds a sink is
in a layer that *can* log, and that is where the decision to carry on
belongs.
"""


class PlanStore:
    """One session's plan. Atomically replaced, never patched.

    **Full replacement is the write model**, following the reference
    harness (``plan.go:47-49``) and for its reason: a model emits the
    whole plan it now believes in, so an API shaped like that emission
    has no incremental-update state to keep consistent. What the model
    omits is decided by :func:`~omicsclaw.planning.rules.merge` *before*
    the items get here — this class stores exactly what it is given.

    **Locked with a :class:`threading.Lock`, not an
    :class:`asyncio.Lock`.** Two reasons, both concrete. ``read`` is
    called before every model call through
    :class:`~omicsclaw.planning.injector.PlanInjector`, and an async lock
    would turn a tuple read into an ``await`` point on the loop's hot
    path. And a tool is free to run under :func:`asyncio.to_thread` — the
    bash tool does — where an ``asyncio.Lock`` protects nothing at all.
    The critical sections here are a tuple assignment and a scan; they do
    not block.
    """

    __slots__ = ("_items", "_lock", "_on_write")

    def __init__(self, *, on_write: PlanWriteSink | None = None) -> None:
        self._lock = threading.Lock()
        self._items: tuple[PlanItem, ...] = ()
        self._on_write = on_write

    def read(self) -> tuple[PlanItem, ...]:
        """The plan as it now stands.

        **No defensive copy, deliberately.** The reference harness copies
        twice on every write and once on every read (``plan.go:69-81``)
        because a Go slice is a view onto shared memory and a caller that
        keeps one can mutate the store through it. A tuple of frozen
        items is not a view: the caller cannot append to it, cannot
        replace an element, and cannot reach into an item. Copying it
        would buy nothing and cost a proportional allocation on the
        engine's per-call path.
        """
        with self._lock:
            return self._items

    def write(self, items: Sequence[PlanItem]) -> tuple[PlanItem, ...]:
        """Replace the plan with *items*, then tell the sink.

        :returns: The new contents, which is what the caller should report
            — reading back with :meth:`read` could observe a later write.

        The sink is called **outside the lock**: it does file I/O, and
        holding a lock across a disk write would make every injection on
        every concurrent session wait for it. The consequence is honest
        rather than hidden — two writes racing can reach the sink in the
        opposite order to which they were stored, so a sink that persists
        must be able to say which contents it was handed. It is, because
        it is handed them.
        """
        new = tuple(items)
        with self._lock:
            self._items = new
        if self._on_write is not None:
            self._on_write(new)
        return new

    def restore(self, items: Sequence[PlanItem]) -> None:
        """Seed the plan from storage without calling the sink.

        What :class:`~omicsclaw.planning.book.PlanBook` uses when a
        session is resumed. Separate from :meth:`write` for one reason
        that is not style: a restore that fired the sink would write the
        archive back out with exactly what was just read from it, turning
        every resumed session into a needless disk write and — if the
        archive is mid-migration or hand-edited — silently normalising a
        file the operator is still looking at.
        """
        with self._lock:
            self._items = tuple(items)

    def active_count(self) -> tuple[int, int]:
        """``(active, total)`` — outstanding items, and all of them.

        The reference harness uses this to decide whether its TUI should
        keep the agent running (``plan.go:135``). **Nothing in this
        repository consumes it yet**, and that is said here rather than
        discovered later: the TUI was not ported (plan 0031 §11), so this
        is a seam for a surface that wants to show progress, and plan
        0038 §8.2's lesson — a capability with no caller is dead code
        however well tested — applies until one does.
        """
        with self._lock:
            items = self._items
        return sum(1 for item in items if item.is_active), len(items)

    @property
    def is_empty(self) -> bool:
        """No items at all — never written, or written empty.

        Read by the planning gate: a session with a plan does not need to
        be told to make one.
        """
        with self._lock:
            return not self._items
