"""``omicsclaw/entry`` — conversations, their queues, and one Task each.

Plan 0031 Q4 and Q6. The engine below deliberately has no ``Session``
("a conversation goes in, a conversation comes out"; plan 0027 declined
to build half of one), so a conversation's history has to live
somewhere, and this is the somewhere. The reference harness keeps it in
SQLite from line one (``main.go:232-245``); this module keeps it behind
a :class:`SessionStore` Protocol with one in-memory implementation,
because **building half a persistence layer is a mistake this rebuild
has already paid for once**.

**Two things live on a session, not one.** ``history`` is the obvious
one. :attr:`Session.compaction` is the one that goes missing:
``context/compaction.py:214-220`` says outright that
:class:`~omicsclaw.context.CompactionState` is "carried between turns by
the caller; step 6 decides where it lives", and a deployment that drops
it re-summarizes from ``FIRST_TEMPLATE`` every single time — paying for
a summary it already has and losing the detail the last one chose to
keep.

**The registry is three guarantees and nothing else** (Q6):

1. *One Task per exchange.* ``contextvars`` isolate per Task, so two
   concurrent sessions are isolated only if each runs in its own —
   otherwise "the second ``set`` wins and one user's tool call is offered
   to the other user's approval prompt" (``tools/context.py`` Q4.5).
2. *Serial within a session, concurrent across sessions.* A second
   message to one conversation waits; a message to another does not.
3. *Queueing is a semantic, not a lock* (Q7). :meth:`SessionRegistry.
   submit` returns a handle **immediately**, publishes how many
   exchanges are ahead of it, refuses outright past
   ``max_queued_per_session``, and a queued exchange can be cancelled
   before it ever starts. A ``submit`` that awaited a lock would give a
   user who typed twice no handle, no feedback and no way out.

**Persistence happens here, not in the exchange's Task** (trap 3b).
Cancelling a Task injects :exc:`asyncio.CancelledError` at its next
``await``, so ``finally: await store.save(...)`` does not finish — and
an in-memory store whose ``save`` never actually suspends hides that
until the day it becomes SQLite. So the registry, which is the side that
*asks* for cancellation, reaps the Task first and saves afterwards. For
the same reason :meth:`InMemorySessionStore.save` suspends once on
purpose.

**What is not here.** No authentication, no rate limiting, no durable
log, no cross-process anything. A sender allowlist is
:class:`~omicsclaw.entry.ingress.SenderPolicy`'s, one layer out, and it
is out there because a registry that decided who may talk to it would be
a registry every surface had to configure identically.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from omicsclaw.context import CompactionState
from omicsclaw.schema import Message

from .assembly import AgentApp
from .events import Terminal
from .ingress import InboundMessage
from .memory import session_store
from .stream import TurnObservation
from .turn import TurnHandle, TurnRunner

__all__ = [
    "DEFAULT_ABANDON_GRACE_S",
    "InMemorySessionStore",
    "QueueFull",
    "RegistryClosed",
    "Session",
    "SessionRegistry",
    "SessionStore",
    "SubmissionRefused",
    "attach_sessions",
    "new_turn_id",
]

_log = logging.getLogger(__name__)

_EMPTY_VALUES: Mapping[str, object] = MappingProxyType({})

DEFAULT_ABANDON_GRACE_S = 30.0
"""Seconds an exchange keeps running after its last observer left.

**A judgement, and the one number in this module that is neither derived
nor taken from the plan** — plan 0031 trap 9 fixes the *condition* ("the
last observer leaves", never "an iterator broke") and leaves the period
open. It is sized against the two events it must not mistake for
abandonment: a browser reload re-opening an SSE stream, and an IM
delivery being retried after a transport error. Both are seconds, not
tens of seconds. Whoever measures a real reconnect on the desktop client
should replace this with that measurement plus its variance.

Raising it costs a cancelled exchange's remaining work when a user
really did close the tab; lowering it risks killing an exchange that a
reconnect was about to resume, which is the more expensive mistake — the
exchange may be eight minutes into a deconvolution.
"""


def new_turn_id() -> str:
    """A fresh exchange id, unique within this process and beyond it.

    Random rather than a counter: a ``turn_id`` appears in a Desktop
    client's resume URL and in an IM callback's payload, both of which
    can outlive the process that issued them, and two processes that each
    started counting at one would hand out the same id for different
    exchanges.
    """
    return uuid.uuid4().hex


@dataclass(slots=True)
class Session:
    """One conversation: what was said, and what was summarized away.

    Mutable, unlike almost everything else in this rebuild, because it is
    the one thing that genuinely accumulates. The registry replaces
    :attr:`history` and :attr:`compaction` wholesale after a successful
    exchange; a cancelled or failed exchange leaves both untouched.
    """

    session_id: str

    history: tuple[Message, ...] = ()
    """The conversation **without** a system message (plan 0031 Q3).

    :func:`~omicsclaw.entry.turn.compose` adds a fresh one every turn, so
    storing one would stack a stale persona beside the current one — and
    would put a slowly drifting block inside the byte-exact prefix the
    provider caches on.
    """

    compaction: CompactionState = field(default_factory=CompactionState)
    """Summary and anchors carried between exchanges.

    Losing this is not fatal and not free: the next compaction starts
    from ``FIRST_TEMPLATE`` with a blank page, pays for a summary of
    material it has already summarized, and cannot recover the detail the
    previous pass chose to keep.
    """

    created_at: float = field(default_factory=time.time)
    """Wall clock at creation, for a surface that lists sessions."""

    values: Mapping[str, object] = field(default_factory=lambda: _EMPTY_VALUES)
    """Session-level facts for the tools — a chat id, a surface name.

    Merged under the exchange's own facts by
    :meth:`~omicsclaw.entry.turn.TurnRunner.turn_values`, so a
    ``turn_id`` left here by accident cannot shadow the running one.
    """


class SessionStore(Protocol):
    """Where conversations are kept between exchanges.

    A Protocol, so the persistent memory layer of a later step satisfies
    it **structurally** and never imports :mod:`omicsclaw.entry` — the
    same relationship ``ToolExecutor`` has with
    :class:`~omicsclaw.tools.ToolRegistry`, and the reason the dependency
    arrow stays pointing one way.

    Every method is ``async`` including the ones the in-memory
    implementation could answer instantly. A synchronous signature here
    would be a decision that the store is local, taken in the one place
    that has no business taking it.
    """

    async def load(self, session_id: str) -> Session | None:
        """The stored session, or ``None`` if there is not one yet."""

    async def save(self, session: Session) -> None:
        """Persist *session* as it now stands."""

    async def list(self, limit: int = 50) -> Sequence[Session]:
        """The most recently created sessions, newest first."""


class InMemorySessionStore:
    """A :class:`SessionStore` that forgets everything on exit.

    What a deployment with its memory database switched off falls back
    to; :class:`~omicsclaw.memory.SqliteSessionStore` is what
    :func:`attach_sessions` picks when there is one. Restarting loses
    every conversation, which is honest: a store that wrote files
    without a schema, a migration story or a retention rule would be the
    half persistence layer this plan refuses to build twice.
    """

    __slots__ = ("_sessions",)

    def __init__(self) -> None:
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    async def load(self, session_id: str) -> Session | None:
        await asyncio.sleep(0)
        return self._sessions.get(session_id)

    async def save(self, session: Session) -> None:
        """Store *session*, suspending once on the way.

        **The :func:`asyncio.sleep` is not decoration.** Every real store
        suspends — a file write, a SQLite call on a thread, an HTTP
        request — and a save that never yields cannot demonstrate the
        failure trap 3b is about: a ``save`` awaited inside a cancelled
        Task never completes, and an implementation that made that
        mistake would be green against a store that never gives the
        cancellation anywhere to land. Costing one loop iteration to keep
        a test honest is the same trade plan 0029's finding #6 named.
        """
        await asyncio.sleep(0)
        self._sessions[session.session_id] = session
        self._sessions.move_to_end(session.session_id)

    async def list(self, limit: int = 50) -> Sequence[Session]:
        await asyncio.sleep(0)
        if limit <= 0:
            return ()
        return tuple(reversed(self._sessions.values()))[:limit]


class SubmissionRefused(RuntimeError):
    """A message this registry declined to turn into an exchange.

    One base for the two refusals so a surface can catch the category
    when it only wants to tell a user "not now", and the subclasses when
    it wants to distinguish *retry later* from *this process is going
    away*.
    """


class QueueFull(SubmissionRefused):
    """This session already has as many exchanges waiting as it may.

    Retryable, once something finishes. Plan 0031 Q7: an unbounded queue
    is not politeness, it is a place for a user hammering enter to
    accumulate work nobody will read the answers to.
    """


class RegistryClosed(SubmissionRefused):
    """Shutdown has begun; this process is not taking new exchanges."""


@dataclass(slots=True)
class _Lane:
    """One session's serialization: what runs, what waits, and the pump.

    A lane exists per ``session_id`` and is the whole of "serial within a
    session, concurrent across sessions". It holds no history — that is
    :class:`Session`'s — so a lane can be created before the session it
    belongs to has been loaded, which is what lets :meth:`SessionRegistry.
    submit` return without awaiting anything.
    """

    session_id: str
    waiting: deque[TurnHandle] = field(default_factory=deque)
    running: TurnHandle | None = None
    pump: asyncio.Task[None] | None = None

    def busy(self) -> bool:
        return self.running is not None or bool(self.waiting)

    def queued_depth(self) -> int:
        """Exchanges waiting behind the one that runs next.

        The head of :attr:`waiting` is not counted while nothing is
        running, because it *is* what runs next — it is only sitting in
        the queue because :meth:`SessionRegistry.submit` returns without
        awaiting and its pump has not been scheduled yet. Counting it
        would make the admitted depth depend on whether the caller
        happened to yield between two submissions, which is the kind of
        rule a user experiences as random.
        """
        if self.running is not None:
            return len(self.waiting)
        return max(0, len(self.waiting) - 1)


class SessionRegistry:
    """Sessions, their queues, and one Task per running exchange.

    The object :attr:`~omicsclaw.entry.assembly.AgentApp.sessions` holds,
    and the only mutable thing in an assembled deployment.

    Built over an app rather than by :func:`~omicsclaw.entry.build_app`,
    which still leaves ``sessions=None``: the registry needs the app and
    the app names the registry, and :func:`attach_sessions` is the one
    line that ties that knot without either object having to be built
    twice.
    """

    __slots__ = (
        "_app",
        "_by_request",
        "_closed",
        "_grace_s",
        "_handles",
        "_lanes",
        "_sessions",
        "_store",
    )

    def __init__(
        self,
        app: AgentApp,
        *,
        store: SessionStore | None = None,
        abandon_grace_s: float | None = DEFAULT_ABANDON_GRACE_S,
    ) -> None:
        """``abandon_grace_s=None`` disables cancelling unwatched exchanges.

        Which is what a surface that submits and awaits — a CLI, a
        scripted run — wants, because it never observes at all. The
        default is on, since the two surfaces that reconnect are the two
        that can otherwise leave an exchange running for nobody.
        """
        self._app = app
        self._store: SessionStore = (
            store if store is not None else InMemorySessionStore()
        )
        self._grace_s = abandon_grace_s
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lanes: dict[str, _Lane] = {}
        self._handles: OrderedDict[str, TurnHandle] = OrderedDict()
        self._by_request: dict[tuple[str, str], TurnHandle] = {}
        self._closed = False

    # ---- submission ------------------------------------------------------

    async def submit(
        self,
        session_id: str,
        text: str,
        *,
        values: Mapping[str, object] | None = None,
        source_request_id: str = "",
    ) -> TurnHandle:
        """Accept one message and hand back a handle to it, immediately.

        **Nothing is awaited before the handle exists**, which is the
        whole of Q7: the session is loaded by the lane's pump when this
        exchange's turn comes, not here, so a user who sent two messages
        gets two handles and can cancel the second. ``async`` is kept in
        the signature because loading, admission control and persistence
        are the sort of thing that acquires an ``await`` later, and a
        surface should not have to change when it does.

        A ``source_request_id`` that has been seen before **on this
        session** resolves to the same handle rather than starting a
        second exchange — the idempotency the desktop client's published
        contract declares (``durable_ingress_idempotency``, plan 0031
        Q24). Passing ``""`` opts out, and a surface that opts out and
        then retries gets two answers to one question.

        **The key is scoped to the session, not global.** A surface is
        free to mint request ids per conversation — a message sequence
        number, a client-side counter — and a global index would resolve
        one conversation's id to *another conversation's handle*, which
        is not a duplicate submission but a caller being handed somebody
        else's event stream, tool arguments and outputs included.

        :raises QueueFull: this session already has
            ``max_queued_per_session`` exchanges waiting.
        :raises RegistryClosed: :meth:`shutdown` has begun.
        """
        return self._enqueue(
            session_id,
            text,
            values=values,
            source_request_id=source_request_id,
            compaction_only=False,
        )

    async def compact(self, session_id: str) -> TurnHandle:
        """Queue a compaction of *session_id*'s history, and return its handle.

        Runs in the session's lane like any exchange, so it never overlaps
        one: it compacts the history as the exchanges ahead of it left it.
        The history is summarized as a FULL compaction whatever its
        pressure; it is replaced only when the compaction is written back,
        so a failed summary leaves it as it was. The outcome's
        ``compaction`` says what happened.

        :raises QueueFull: this session already has
            ``max_queued_per_session`` exchanges waiting.
        :raises RegistryClosed: :meth:`shutdown` has begun.
        """
        return self._enqueue(
            session_id, "", values=None, source_request_id="", compaction_only=True
        )

    def _enqueue(
        self,
        session_id: str,
        text: str,
        *,
        values: Mapping[str, object] | None,
        source_request_id: str,
        compaction_only: bool,
    ) -> TurnHandle:
        if self._closed:
            raise RegistryClosed("this registry is shutting down")
        if source_request_id:
            seen = self._by_request.get((session_id, source_request_id))
            if seen is not None:
                _log.info(
                    "redelivery of %s resolved to turn %s",
                    source_request_id,
                    seen.turn_id,
                )
                return seen

        lane = self._lanes.setdefault(session_id, _Lane(session_id))
        limit = self._app.config.max_queued_per_session
        depth = lane.queued_depth()
        if depth >= limit:
            raise QueueFull(
                f"session {session_id!r} already has {depth} exchange(s) "
                f"waiting, which is its limit of {limit}"
            )

        handle = TurnHandle(
            session_id=session_id,
            turn_id=new_turn_id(),
            text=text,
            values=values,
            ring_size=self._app.config.delta_ring_size,
            approval_timeout_s=self._app.config.approval_timeout_s,
            abandon_grace_s=self._grace_s,
            compaction_only=compaction_only,
        )
        ahead = (1 if lane.running is not None else 0) + len(lane.waiting)
        lane.waiting.append(handle)
        self._remember(handle, source_request_id)
        if ahead:
            handle._publish_queued(ahead)
            _log.info(
                "turn %s queued behind %d on session %s",
                handle.turn_id,
                ahead,
                session_id,
            )
        if lane.pump is None:
            lane.pump = asyncio.create_task(
                self._pump(lane), name=f"omicsclaw-lane-{session_id}"
            )
        return handle

    async def deliver(self, message: InboundMessage) -> TurnHandle:
        """Submit an :class:`~omicsclaw.entry.ingress.InboundMessage`.

        The form the three surfaces use, because the message already
        carries the four things :meth:`submit` needs and carrying them
        separately is four chances to drop the idempotency key. Admission
        — whether this sender may drive the agent at all — is
        :class:`~omicsclaw.entry.ingress.SenderPolicy`'s and has already
        happened by the time a message reaches here.
        """
        return await self.submit(
            message.session_id,
            message.text,
            values=message.values,
            source_request_id=message.source_request_id,
        )

    # ---- observation -----------------------------------------------------

    def observe(self, turn_id: str, *, after_seq: int = 0) -> TurnObservation:
        """Open a cursor over an exchange named by id.

        The reconnect path: a Desktop client that lost its SSE stream
        knows the ``turn_id`` and the last ``seq`` it processed, and has
        no reference to the handle the original request was holding.

        :raises KeyError: no exchange by that id is still retained. The
            retention window is one exchange per live session; see
            :meth:`_remember`.
        """
        return self.handle(turn_id).observe(after_seq=after_seq)

    def handle(self, turn_id: str) -> TurnHandle:
        """The handle for *turn_id*.

        :raises KeyError: it was never issued here, or it has aged out.
        """
        handle = self._handles.get(turn_id)
        if handle is None:
            raise KeyError(f"no retained exchange {turn_id!r}")
        return handle

    def session(self, session_id: str) -> Session | None:
        """The in-memory session, or ``None`` if none has been loaded."""
        return self._sessions.get(session_id)

    async def load_session(self, session_id: str) -> Session | None:
        """The conversation named *session_id*, from memory or the store.

        Reads without adopting: the session is not added to this
        registry and no lane is created for it, so asking whether a
        conversation exists cannot bring one into being. ``None`` means
        no exchange has ever been saved under that id.
        """
        known = self._sessions.get(session_id)
        if known is not None:
            return known
        return await self._store.load(session_id)

    async def list_sessions(self, limit: int = 10) -> Sequence[Session]:
        """The most recently created conversations, newest first.

        The scope is the store this registry was attached over, and the
        store's own scope is its backing file — see
        :meth:`omicsclaw.memory.SqliteSessionStore.list`. A session this
        process started but has not yet run an exchange in is absent,
        because the registry saves a session after it runs one.
        """
        return await self._store.list(limit)

    @property
    def persistent(self) -> bool:
        """Whether a conversation here outlives the process.

        Answered from the store's type, which is the only thing that
        knows: :class:`SessionStore` declares nothing about durability,
        so a third implementation that also forgets would be reported as
        persistent until it is named here.
        """
        return not isinstance(self._store, InMemorySessionStore)

    def running(self) -> tuple[TurnHandle, ...]:
        """Handles of the exchanges executing right now."""
        return tuple(
            lane.running for lane in self._lanes.values() if lane.running is not None
        )

    # ---- shutdown --------------------------------------------------------

    async def shutdown(self, grace_s: float) -> None:
        """Stop admitting, let what is running finish, then cancel and reap.

        Plan 0031 Q17. Three phases, in this order:

        1. refuse new submissions;
        2. wait up to *grace_s* for every lane to drain — the exchange
           running and whatever was already accepted behind it. Work that
           was admitted is finished if it can be; "graceful" is not a
           synonym for "abandon the queue";
        3. cancel what is left, running and queued alike, then wait once
           more for the pumps to persist what they can, and finally
           cancel and **reap** them.

        The worst case is therefore about ``2 × grace_s``: the grace the
        accepted work gets, and the same allowance again for the drain of
        what was cancelled — that second window is not the work, it is
        the ``await store.save`` that trap 3b insists happens out here.

        Reaping is not tidiness: an un-awaited cancelled Task prints
        "Task exception was never retrieved" at interpreter shutdown,
        into a log nobody is reading by then.

        :meth:`_close_out` runs from a ``finally`` and therefore on every
        exit, including the two early returns. It used to run only on the
        path that cancelled something, which meant a pump that had
        already died of its own exception left its handle unsettled and
        unrescued — the one case where the backstop was needed was the
        one case it was skipped.
        """
        self._closed = True
        try:
            pumps = [
                lane.pump for lane in self._lanes.values() if lane.pump is not None
            ]
            if not pumps:
                return

            _done, pending = await asyncio.wait(pumps, timeout=max(grace_s, 0.0))
            if not pending:
                return

            _log.warning("shutdown grace expired; cancelling %d lane(s)", len(pending))
            for lane in self._lanes.values():
                for handle in tuple(lane.waiting):
                    handle.cancel()
                if lane.running is not None:
                    lane.running.cancel()
            _done, pending = await asyncio.wait(pending, timeout=max(grace_s, 0.0))
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            self._close_out()

    def _close_out(self) -> None:
        """Settle whatever a cancelled pump left in the air.

        A pump cancelled in the middle of its own ``await store.save``
        never reaches :meth:`TurnHandle._settle`, which would leave a
        surface iterating a stream that has no ending and a caller
        awaiting a :meth:`TurnHandle.wait` that never returns. The
        terminal frame is owed however the process is going down;
        publishing on an already-sealed stream is ignored, so this is a
        backstop and not a second emitter.

        Retained handles are the source rather than the lanes': a pump's
        own ``finally`` clears ``lane.running`` on its way out, so by the
        time this runs the lane has forgotten what it was carrying.
        Nothing runs after shutdown, so an exchange that has not reached
        a terminal state by now never will.
        """
        for handle in tuple(self._handles.values()):
            if handle.done:
                continue
            handle._publish_terminal("cancelled")
            handle._settle("cancelled")

    # ---- the lane pump ---------------------------------------------------

    async def _pump(self, lane: _Lane) -> None:
        """Run one lane's exchanges, one at a time, until the queue drains.

        Lives for as long as there is work and is replaced by the next
        :meth:`submit` afterwards. It — not the exchange's own Task — is
        what persists, because it is the side that is still running when
        the exchange it cancelled is not.

        **One bad exchange does not close the lane.** :meth:`_run`
        already settles whatever it could not finish, so the guard below
        is for a defect in that guard: without it, one exception here
        leaves every exchange queued behind it in :attr:`_Lane.waiting`
        with no pump to consume them and no terminal frame to end them,
        which is a conversation that has stopped answering rather than a
        turn that failed.
        """
        try:
            while lane.waiting:
                handle = lane.waiting.popleft()
                lane.running = handle
                try:
                    await self._run(handle)
                except Exception:  # noqa: BLE001 - see the docstring
                    _log.exception(
                        "lane %s survived a failed turn %s",
                        lane.session_id,
                        handle.turn_id,
                    )
                    self._end_in_the_air(handle, "failed")
                finally:
                    lane.running = None
        finally:
            lane.pump = None
            # Reached with work still queued only when this pump was
            # cancelled. Those exchanges will never run, and a handle
            # nobody will ever settle is a ``wait()`` that never returns.
            for stranded in tuple(lane.waiting):
                self._end_in_the_air(stranded, "cancelled")
            lane.waiting.clear()

    @staticmethod
    def _end_in_the_air(
        handle: TurnHandle,
        terminal: Terminal,
        error: BaseException | None = None,
    ) -> None:
        """Close an exchange whose own bookkeeping never got to it.

        Publishing on a sealed stream is ignored, so this emits the
        terminal frame only where none was emitted, and settles the
        handle either way. Settling is the half that matters: the frame
        ends a stream, and :meth:`TurnHandle.wait` is what a CLI and a
        channel pump are both blocked on.
        """
        if handle.done:
            return
        handle._publish_terminal(terminal)
        handle._settle(terminal, error)

    async def _run(self, handle: TurnHandle) -> None:
        """One exchange: its own Task, then reap, then persist.

        Guarded as a whole, because two of the awaits inside call an
        implementation this module does not own. ``load`` and ``save``
        belong to :class:`SessionStore`, whose only shipped
        implementation never raises — so a store that does (a locked
        SQLite file, a full disk, an HTTP 500) leaves the exchange with
        no terminal frame and no settled handle. That is not a failed
        turn: it is a stream that never ends and a
        :meth:`TurnHandle.wait` that never returns, which is trap 1b's
        failure wearing a persistence layer's clothes.

        **A ``save`` that raises is reported as ``failed`` even though
        the stream already sealed on ``converged``.** The frame is gone
        the moment it is published and cannot be retracted; the handle is
        this registry's own verdict, and an exchange whose history did
        not reach the store did not finish. The two therefore disagree on
        that one path, deliberately — a surface that needs the answer
        reads the stream, and a surface that needs to know it was kept
        reads :attr:`TurnHandle.terminal`.

        **Three clauses, because a guard that caught everything and
        re-raised nothing would be worse than none.** The exchange is
        owed its frame however it ended, so every clause settles; only an
        ordinary :exc:`Exception` is also *absorbed*. A cancellation and
        a :exc:`BaseException` are settled and then re-raised, because
        both mean something outside this exchange has decided to stop —
        ``shutdown`` waiting out a second grace window for a pump that
        already quit, or a :exc:`KeyboardInterrupt` this layer has no
        business overruling.
        """
        try:
            await self._attempt(handle)
        except asyncio.CancelledError:
            self._end_in_the_air(handle, "cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 - see the docstring
            _log.exception("turn %s ended outside its own task", handle.turn_id)
            self._end_in_the_air(handle, "failed", exc)
        except BaseException as exc:  # noqa: BLE001 - see the docstring
            _log.exception("turn %s ended on %s", handle.turn_id, type(exc).__name__)
            self._end_in_the_air(handle, "failed", exc)
            raise

    async def _attempt(self, handle: TurnHandle) -> None:
        """The exchange itself, with nothing between it and its failures."""
        if handle.terminal == "cancelled":
            # Cancelled while queued. It never had a runner, so nothing
            # else would ever emit its terminal frame.
            handle._end_unstarted()
            return

        session = await self._session(handle.session_id)
        if handle.terminal == "cancelled":
            # Cancelled *during* that load. Until ``_start`` adopts a
            # Task, :meth:`TurnHandle.cancel` has nowhere to deliver the
            # request but this flag, so a second look is the only thing
            # standing between a Ctrl-C typed right after submit and an
            # exchange that runs anyway, calls the model, rewrites the
            # history and overwrites its own ``cancelled`` with
            # ``converged``.
            handle._end_unstarted()
            return

        runner = TurnRunner(
            self._app,
            handle.stream,
            session_id=handle.session_id,
            turn_id=handle.turn_id,
            history=session.history,
            compaction=session.compaction,
            user_text=handle.text,
            values={**session.values, **handle.values},
            approval=handle.approvals,
            force_compaction=handle.compaction_only,
        )
        task = asyncio.create_task(
            runner.run(), name=f"omicsclaw-turn-{handle.turn_id}"
        )
        handle._start(task)

        # ``wait`` rather than ``await task``: a cancelled exchange must
        # not cancel the pump that has to save afterwards, and an
        # exception must not escape before the verdict is recorded.
        try:
            await asyncio.wait({task})
        finally:
            # Cancelling an ``asyncio.wait`` does **not** cancel what it
            # was waiting on, so a pump cancelled here would leave a turn
            # running against a registry that is shutting down.
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        _reap(task)

        terminal = runner.terminal
        error, outcome = runner.error, runner.outcome
        if not handle.stream.sealed:
            # The Task was cancelled before ``run`` executed a single
            # statement, so its ``finally`` never ran and nothing emitted
            # the terminal frame an observer is waiting for.
            terminal, error, outcome = "cancelled", None, None
            handle._publish_terminal("cancelled")

        if terminal == "converged" and outcome is not None:
            session.history = outcome.history
            session.compaction = outcome.state
        # Cancelled and failed exchanges leave the history byte-identical
        # (trap 3): the engine's trajectory exists only on its DONE event,
        # so there is nothing partial to keep that would not be a guess.
        await self._store.save(session)
        handle._settle(terminal, error, outcome)

    # ---- internals -------------------------------------------------------

    async def _session(self, session_id: str) -> Session:
        """The live session, loading or creating it on first use."""
        known = self._sessions.get(session_id)
        if known is not None:
            self._sessions.move_to_end(session_id)
            return known
        loaded = await self._store.load(session_id)
        session = loaded if loaded is not None else Session(session_id=session_id)
        self._sessions[session_id] = session
        self._evict_sessions()
        return session

    def _evict_sessions(self) -> None:
        """Drop the least recently used **idle** sessions past the cap.

        A session with an exchange running or queued is never a victim
        however old it is (Q6): evicting it would drop the history the
        running exchange is about to be saved into, which is a data loss
        wearing a cache policy's clothes. If every session is busy,
        nothing is evicted and the cap is exceeded — the honest outcome,
        since the alternative is to break one of them.
        """
        cap = self._app.config.max_sessions
        for session_id in tuple(self._sessions):
            if len(self._sessions) <= cap:
                return
            lane = self._lanes.get(session_id)
            if lane is not None and lane.busy():
                continue
            del self._sessions[session_id]
            self._lanes.pop(session_id, None)
            _log.info("evicted idle session %s", session_id)

    def _remember(self, handle: TurnHandle, source_request_id: str) -> None:
        """Retain a handle so it can be reopened by id, within a bound.

        The bound is ``max_sessions``, which makes it exactly "one
        resumable exchange per live session" — derived rather than a new
        number to keep, and the smallest window in which every live
        conversation's current exchange is still addressable. Only
        terminal exchanges are evicted; a running one stays reachable
        whatever the pressure.
        """
        self._handles[handle.turn_id] = handle
        if source_request_id:
            self._by_request[(handle.session_id, source_request_id)] = handle
        cap = self._app.config.max_sessions
        for turn_id, retained in tuple(self._handles.items()):
            if len(self._handles) <= cap:
                break
            if not retained.done:
                continue
            del self._handles[turn_id]
            for key, held in tuple(self._by_request.items()):
                if held is retained:
                    del self._by_request[key]


def _reap(task: asyncio.Task[object]) -> BaseException | None:
    """Consume a finished Task's exception and return it.

    Calling :meth:`asyncio.Task.exception` is what marks it retrieved;
    the return value is for a caller that wants to log. A cancelled Task
    is asked nothing, because asking raises.
    """
    if task.cancelled():
        return None
    return task.exception()


def attach_sessions(
    app: AgentApp,
    *,
    store: SessionStore | None = None,
    abandon_grace_s: float | None = DEFAULT_ABANDON_GRACE_S,
) -> AgentApp:
    """Give *app* a session registry, and the registry the finished app.

    :func:`~omicsclaw.entry.build_app` leaves
    :attr:`~omicsclaw.entry.assembly.AgentApp.sessions` as ``None``
    because the two reference each other; this resolves that in one
    place::

        app = attach_sessions(await open_app(resolve_app_config(argv, env)))
        handle = await app.sessions.submit("s1", "分析这份 Visium 数据")

    The registry ends up holding the *attached* app rather than the one
    it was constructed over, so ``app.sessions._app is app`` — one object
    graph, not two views of one deployment.

    **``store=None`` means "this app's own", not "in memory".** An app
    with a memory database open resumes its conversations out of it, so
    a surface gets persistence by calling this the short way rather than
    by knowing to ask for it; an app without one — memory switched off,
    or an app assembled by hand — falls back to
    :class:`InMemorySessionStore` and forgets on exit. Passing a store
    overrides both.
    """
    if store is None:
        store = session_store(app.memory)
    registry = SessionRegistry(app, store=store, abandon_grace_s=abandon_grace_s)
    attached = dataclasses.replace(app, sessions=registry)
    registry._app = attached
    return attached
