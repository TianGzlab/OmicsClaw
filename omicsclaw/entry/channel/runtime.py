"""The channel surface's composition root: bindings in, exchanges out.

Plan 0031 task D1. Every shipped adapter in this package was written against
one object — a runtime it is handed, submits normalised inbound messages to,
and never composes itself. That object used to be ``ControlRuntime``. This is
the half of it that belongs to :mod:`omicsclaw.entry` (plan 0031 Q23,
family ①): *who gets in*, *one exchange per message*, *the reply out*.

**What deliberately did not come across.** ``ControlRuntimePorts`` carried
twenty-two per-turn fields, six of them :data:`~typing.Any`. Here one exchange
is an :class:`~omicsclaw.entry.ingress.InboundMessage` and nothing else: the
model, the output style and the MCP list are deployment facts on
:class:`~omicsclaw.entry.config.AppConfig`, and the rest do not exist yet. The
durable half — outbox ordering, receipts, replay — is not in this step either
(plan 0031 §11); a reply here lives exactly as long as the process.

**Three obligations this file carries alone**, because nothing below it can:

1. *Refuse first.* :meth:`ChannelRuntime.submit` consults
   :class:`~omicsclaw.entry.ingress.SenderPolicy` **before** it touches
   :class:`~omicsclaw.entry.session.SessionRegistry`, so a message from
   outside the allowlist creates no exchange at all — not an exchange that
   answers "no". Authoritative ingress admits nobody else.
2. *Close the observation.* ``TurnStream.observer_count()`` does not decrease
   when an ``async for`` breaks, so the grace period that abandons an unwatched
   exchange can only start if this file calls ``aclose()``. Every observation
   opened here is opened with ``async with``.
3. *Hop to the loop.* Several vendor SDKs deliver callbacks on their own
   threads. ``ApprovalBroker.settle`` resolves an :class:`asyncio.Future` and
   is only safe on the loop's thread, so
   :meth:`ChannelRuntime.settle_approval_threadsafe` is the
   ``call_soon_threadsafe`` hop spelled out and is the only settle a callback
   should use (plan 0031 trap 10).
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Awaitable, Callable, Final, Mapping, Sequence

from omicsclaw.entry.assembly import AgentApp
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.ingress import Acceptance, InboundMessage
from omicsclaw.entry.render import TextRenderer
from omicsclaw.entry.session import QueueFull, RegistryClosed, SubmissionRefused
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.schema import Role
from omicsclaw.tools.context import ApprovalDecision

from .base import chunk_text
from .binding import ChannelSurfaceBinding
from .delivery import deliver

__all__ = [
    "CODE_EMPTY_TEXT",
    "CODE_NOT_STARTED",
    "CODE_OWNER_DENIED",
    "CODE_QUEUE_FULL",
    "CODE_UNKNOWN_ADAPTER",
    "ChannelRuntime",
    "ChannelSubmission",
    "DEFAULT_DELIVERED_TYPES",
    "SHUTDOWN_GRACE_S",
    "TurnAcceptanceResult",
    "TurnAcceptanceStatus",
    "VALUE_REPLY_TARGET",
    "compose_channel_runtime",
]

_log = logging.getLogger(__name__)

VALUE_REPLY_TARGET: Final = "reply_target"
"""Key under which an adapter puts *where the answer goes*.

:class:`~omicsclaw.entry.ingress.InboundMessage` has five frozen fields and a
``values`` mapping, and the reply target is the archetypal thing ``values``
exists for: the platform-shaped address the delivery adapter validates, which
this layer passes through and never interprets. Carrying it on the message
rather than as a second argument is what keeps it from being dropped on a
redelivery, which is the one path nobody exercises by hand.
"""

SHUTDOWN_GRACE_S: Final = 20.0
"""Seconds :meth:`ChannelRuntime.close` lets outstanding replies finish.

**A judgement, and the one number in this module that is not derived from
anything.** It is deliberately *shorter* than one attempt's own ceiling
(:data:`~omicsclaw.entry.channel.delivery.ATTEMPT_TIMEOUT_S`, 30 s): waiting a
hung provider call out would cost that per reply in flight, and a call
cancelled mid-flight is exactly the
:attr:`~omicsclaw.entry.ingress.Acceptance.UNKNOWN` the pump already models
and already refuses to retry. So the trade is "a reply that was probably
already sent may be reported as unknown" against "a container's ``SIGTERM``
takes half a minute per conversation".

Whoever measures a real Telegram or Feishu send should replace this with that
measurement plus its variance. Raising it delays shutdown; lowering it turns
more delivered replies into unknown ones.
"""

CODE_OWNER_DENIED: Final = "owner_denied"
"""Refusal code kept verbatim from the deleted control plane.

``surfaces/channels/telegram.py:471`` branched on this exact string to log
"ignored a message from a non-Owner" without answering it, and the ported
adapter still does. It is the one refusal that must never
turn into a reply: answering tells an unknown sender that the bot is here and
that their id is not on the list.
"""

CODE_QUEUE_FULL: Final = "queue_full"
"""This session already has as many exchanges waiting as it may.

Renamed from the old ``delivery_backpressure``, which named the outbox this
step does not have. The user-facing sentence is the same — come back later —
but a code that describes a component nobody can find is worse than a new one.
"""

CODE_NOT_STARTED: Final = "not_started"
"""The runtime is not accepting: never started, or already shutting down.

Renamed from ``control_not_ready`` for :data:`CODE_QUEUE_FULL`'s reason.
"""

CODE_UNKNOWN_ADAPTER: Final = "unknown_adapter"
"""No binding was composed for this message's
:attr:`~omicsclaw.entry.ingress.InboundMessage.surface`. A configuration
fault, refused rather than guessed: guessing would send one bot's reply
through another's token."""

CODE_EMPTY_TEXT: Final = "empty_text"
"""Nothing to run. An exchange over an empty prompt costs a model call to
produce a reply to nothing."""

DEFAULT_DELIVERED_TYPES: Final[frozenset[TurnEventType]] = frozenset(
    {
        TurnEventType.QUEUED,
        TurnEventType.APPROVAL_REQUIRED,
        TurnEventType.APPROVAL_SETTLED,
        TurnEventType.EXCHANGE_END,
    }
)
"""Frames worth interrupting a chat for **while an exchange is running**.

Anything the person has to act on, and anything that changes what they should
believe about what they are seeing. The answer itself is not here, and that is
the decision this constant exists to record:

*The answer is delivered once, from the trajectory, after the exchange ends.*
Three reasons, and the second is a property of this layer rather than a
preference:

1. Every platform here rate-limits sends and edits. A message per token stops
   a bot inside its first sentence.
2. **Delta frames are droppable by contract** (plan 0031 Q14): an observation
   buffers 64 frames, and a backend that yields a hundred chunks without
   awaiting fills that buffer before this pump is ever scheduled. The dropped
   deltas are announced by a ``GAP``, which is honest and is *still a
   truncated answer*. The exchange's own trajectory has no gaps.
3. It is what the adapters did **before** the port —
   ``surfaces/channels/feishu.py:558-560`` reads word for word: this handler
   "performs no LLM work, sends no placeholder, and produces no reply: the
   terminal reply is committed with the Turn and delivered by the persistent
   Delivery Pump". ``entry/channel/feishu.py:605-608`` says the same thing
   in its own words, and adds the one difference — this pump holds the reply
   in memory rather than in a durable outbox.

``TOOL_START``, ``TOOL_RESULT``, ``PROGRESS``, ``TURN_END``, ``CONTEXT`` and
``COMPACTION`` are absent for the first reason alone. ``GAP`` is absent
because, with the answer taken from the trajectory, a gap is a fact about a
buffer and no longer a fact about what the person is reading.

This is surface policy, not a renderer limitation: a deployment that wants the
tool trace, or a live token stream, passes its own set —
:meth:`ChannelRuntime._pump_reply` batches deltas and suppresses the
after-the-fact answer when it has already streamed one. ``REASONING_DELTA``
would still do nothing: :class:`~omicsclaw.entry.render.TextRenderer`
suppresses it unless ``show_reasoning`` is set.
"""

_CONVERGED: Final = "converged"


class TurnAcceptanceStatus(StrEnum):
    """Whether one inbound message became an exchange.

    Ported from ``HEAD:omicsclaw/control/models.py:95-99`` (plan 0031 Q23
    names it as a family ① symbol). ``CONFLICT`` is dropped with its cause: it
    meant one idempotency key had arrived twice with *different* content,
    which only a durable ingress record can notice.
    """

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    """A redelivery of a message already accepted. Resolves to the original
    exchange and starts no second one, which is the whole of idempotency
    here."""

    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TurnAcceptanceResult:
    """Admission outcome, and the exchange it resolved to if there is one."""

    status: TurnAcceptanceStatus
    turn_id: str = ""
    code: str = ""
    """Empty on acceptance. One of the ``CODE_*`` constants otherwise."""


@dataclass(frozen=True, slots=True)
class ChannelSubmission:
    """What :meth:`ChannelRuntime.submit` gives back.

    ``result.acceptance.status`` and ``result.acceptance.code`` are the shape
    both production adapters already branch on, so the reconnection is a
    changed import rather than a rewritten handler.
    """

    acceptance: TurnAcceptanceResult
    handle: TurnHandle | None = None
    """``None`` exactly when the message was refused."""


class ChannelRuntime:
    """One agent, several channel accounts, one exchange per message.

    Composed once per process by the runner — never by a channel — because
    the adapters share one :class:`~omicsclaw.entry.session.SessionRegistry`
    and two registries would be two sets of conversations for one person.
    """

    __slots__ = (
        "_accepted",
        "_app",
        "_bindings",
        "_delivered_types",
        "_loop",
        "_replies",
        "_sleep",
        "_started",
    )

    def __init__(
        self,
        app: AgentApp,
        bindings: Sequence[ChannelSurfaceBinding],
        *,
        delivered_types: frozenset[TurnEventType] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Refuse a deployment that cannot answer safely, at composition.

        Two of the three checks are plan 0031 Q12 and §9-9 respectively, and
        both fail here rather than at the first message:

        - ``sessions`` is ``None`` until
          :func:`~omicsclaw.entry.session.attach_sessions` has run, and a
          runtime over an app with no registry would accept messages it can
          never run.
        - ``approval_timeout_s`` **must** be a number on this surface. A
          channel asks a person who may have closed the app; ``None`` there
          means a tool waits for consent until the exchange itself is
          abandoned, holding the session's queue behind it. Expiry denies.
        """
        if app.sessions is None:
            raise ValueError(
                "ChannelRuntime needs an app with a session registry; call "
                "attach_sessions(build_app(config)) first"
            )
        if app.config.approval_timeout_s is None:
            raise ValueError(
                "a channel surface must set AppConfig.approval_timeout_s: an "
                "approval nobody answers would hold the session open, and an "
                "approval that expired into consent would be no control at all"
            )
        if not bindings:
            raise ValueError("ChannelRuntime needs at least one channel binding")
        indexed: dict[str, ChannelSurfaceBinding] = {}
        for binding in bindings:
            if binding.adapter in indexed:
                raise ValueError(
                    f"two bindings claim the adapter {binding.adapter!r}; an "
                    "inbound message names its surface by adapter alone, so "
                    "two accounts of one platform need two processes"
                )
            indexed[binding.adapter] = binding
        self._app = app
        self._bindings = indexed
        self._delivered_types = (
            DEFAULT_DELIVERED_TYPES if delivered_types is None else delivered_types
        )
        self._sleep = sleep
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = False
        self._replies: dict[str, asyncio.Task[None]] = {}
        self._accepted: OrderedDict[tuple[str, str], str] = OrderedDict()

    @classmethod
    def for_channel_surfaces(
        cls,
        app: AgentApp,
        *,
        bindings: Sequence[ChannelSurfaceBinding],
        **kwargs: Any,
    ) -> ChannelRuntime:
        """Name kept from ``ControlRuntime.for_channel_surfaces``.

        ``__main__.py:432`` called it during composition and this package's
        runner does the same thing in the same order, so the name is worth
        more than the symmetry of a plain constructor (plan 0031 Q23).
        """
        return cls(app, bindings, **kwargs)

    # ---- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        """Bind to the running loop and open for submissions.

        The loop is captured here rather than in ``__init__`` because a
        runner composes the runtime and runs it in the same coroutine but a
        test may not, and the loop this records is the one every cross-thread
        hop will target.
        """
        self._loop = asyncio.get_running_loop()
        self._started = True
        _log.info(
            "channel runtime started for %s", ", ".join(sorted(self._bindings))
        )

    async def close(self, grace_s: float = SHUTDOWN_GRACE_S) -> None:
        """Stop accepting, let the replies in flight land, then reap.

        Replies are waited for rather than cancelled first: the exchange has
        already run and the person is owed its answer. What is *not* waited
        for is a retry — the grace expires and the task is cancelled, because
        a shutdown that honours a sixty-second rate-limit hint is a shutdown
        that does not happen.

        Reaping is not tidiness: an un-awaited cancelled Task prints "Task
        exception was never retrieved" at interpreter shutdown.
        """
        self._started = False
        tasks = tuple(self._replies.values())
        if not tasks:
            return
        _done, pending = await asyncio.wait(tasks, timeout=max(grace_s, 0.0))
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._replies.clear()

    @property
    def app(self) -> AgentApp:
        """The deployment these channels speak for."""
        return self._app

    @property
    def started(self) -> bool:
        return self._started

    def binding(self, adapter: str) -> ChannelSurfaceBinding | None:
        """The binding for *adapter*, or ``None`` if none was composed."""
        return self._bindings.get(adapter)

    # ---- ingress ---------------------------------------------------------

    async def submit(self, message: InboundMessage) -> ChannelSubmission:
        """Admit one message and start the exchange it earns, immediately.

        Returns as soon as the exchange has a handle — it may still be queued
        behind another on the same conversation (plan 0031 Q7) — so a vendor
        SDK's callback thread is never blocked behind an analysis.

        **Every accepted message gets a reply pump**, and there is no way to
        ask for one without. The alternative used to exist for adapters that
        sent the answer themselves, and a second outbound path is exactly
        what nothing upstream can account for.

        **Order matters and is the security control.** The allowlist is
        consulted before the registry, so a refused sender leaves no trace in
        the session store, costs no model call, and gets no answer.
        """
        if not self._started:
            return _refused(CODE_NOT_STARTED)
        binding = self._bindings.get(message.surface)
        if binding is None:
            _log.warning("no binding for surface %r", message.surface)
            return _refused(CODE_UNKNOWN_ADAPTER)
        if not binding.sender_policy.admits(message):
            # Deliberately no reply: answering an unknown sender confirms both
            # that this bot exists and that their identity was checked.
            _log.warning(
                "ignored a %s message from a sender outside the allowlist",
                binding.adapter,
            )
            return _refused(CODE_OWNER_DENIED)
        if not message.text.strip():
            return _refused(CODE_EMPTY_TEXT)

        known = self._accepted.get(
            (message.session_id, message.source_request_id)
        )
        registry = self._app.sessions
        assert registry is not None  # guarded in __init__
        try:
            handle = await registry.deliver(message)
        except QueueFull:
            return _refused(CODE_QUEUE_FULL)
        except RegistryClosed:
            return _refused(CODE_NOT_STARTED)
        except SubmissionRefused:  # pragma: no cover - a future refusal
            return _refused(CODE_NOT_STARTED)

        if known == handle.turn_id or handle.turn_id in self._replies:
            _log.info("redelivery resolved to exchange %s", handle.turn_id)
            return ChannelSubmission(
                acceptance=TurnAcceptanceResult(
                    status=TurnAcceptanceStatus.DUPLICATE,
                    turn_id=handle.turn_id,
                ),
                handle=handle,
            )
        self._remember(
            message.session_id, message.source_request_id, handle.turn_id
        )
        self._start_reply(binding, handle, message)
        return ChannelSubmission(
            acceptance=TurnAcceptanceResult(
                status=TurnAcceptanceStatus.ACCEPTED,
                turn_id=handle.turn_id,
            ),
            handle=handle,
        )

    async def submit_and_wait(self, message: InboundMessage) -> ChannelSubmission:
        """:meth:`submit`, then wait for the exchange to reach a verdict.

        For an adapter whose callback can afford to wait — Telegram's, which
        runs on the loop. Feishu's cannot: its handler occupies the SDK's one
        WebSocket thread, so waiting there would serialise every conversation
        behind one analysis.
        """
        submission = await self.submit(message)
        if submission.handle is not None:
            await submission.handle.wait()
        return submission

    def handle(self, turn_id: str) -> TurnHandle | None:
        """The exchange named by *turn_id*, while the registry retains it."""
        registry = self._app.sessions
        if registry is None:  # pragma: no cover - guarded in __init__
            return None
        try:
            return registry.handle(turn_id)
        except KeyError:
            return None

    # ---- approvals -------------------------------------------------------

    async def settle_approval(
        self,
        turn_id: str,
        request_id: str,
        decision: ApprovalDecision,
    ) -> bool:
        """Answer one outstanding question from the loop's own thread.

        Returns whether it took effect. ``False`` is ordinary, not an error:
        a person can click a card twice, or click one their client
        re-rendered after the deadline (plan 0031 Q18).
        """
        handle = self.handle(turn_id)
        if handle is None:
            return False
        return handle.approvals.settle(request_id, decision)

    def settle_approval_threadsafe(
        self,
        turn_id: str,
        request_id: str,
        decision: ApprovalDecision,
    ) -> None:
        """Answer one question **from a thread that is not the loop's**.

        This is the hop, and it is not optional. ``ApprovalBroker.settle``
        resolves an :class:`asyncio.Future`, which is only safe from the
        thread running the loop that created it; calling it from a vendor
        SDK's callback thread corrupts the loop's bookkeeping instead of
        failing loudly (plan 0031 trap 10). Several adapters here deliver
        their callbacks exactly that way.

        Asynchronous by construction — it returns once the answer is
        scheduled, not once it has been applied — so it cannot report whether
        the request was still outstanding. A caller that needs the verdict is
        already on the loop and should await :meth:`settle_approval`.
        """
        loop = self._loop
        if loop is None:
            raise RuntimeError(
                "ChannelRuntime is not started, so it has no loop to settle on"
            )
        loop.call_soon_threadsafe(self._settle_now, turn_id, request_id, decision)

    def _settle_now(
        self,
        turn_id: str,
        request_id: str,
        decision: ApprovalDecision,
    ) -> None:
        """Run on the loop thread by :meth:`settle_approval_threadsafe`.

        Swallows nothing and raises nothing: an exception here would surface
        in the loop's exception handler, detached from the callback that
        caused it, so an unknown exchange is logged and dropped.
        """
        handle = self.handle(turn_id)
        if handle is None or not handle.approvals.settle(request_id, decision):
            _log.debug("approval %s on %s had nothing to settle", request_id, turn_id)

    # ---- the reply pump --------------------------------------------------

    def _start_reply(
        self,
        binding: ChannelSurfaceBinding,
        handle: TurnHandle,
        message: InboundMessage,
    ) -> None:
        """One Task per exchange, and never two exchanges in one Task.

        ``contextvars`` isolate per Task, so two conversations sharing one
        Task would offer one person's tool call to the other person's
        approval prompt (plan 0031 Q6). A channel is the surface where two
        conversations are the normal case.
        """
        target = message.values.get(VALUE_REPLY_TARGET)
        reply_target: Mapping[str, Any] = target if isinstance(target, Mapping) else {}
        if not reply_target:
            _log.warning(
                "exchange %s has no reply target; running it with no way back",
                handle.turn_id,
            )
        task = asyncio.create_task(
            self._pump_reply(binding, handle, reply_target),
            name=f"omicsclaw-reply-{handle.turn_id}",
        )
        self._replies[handle.turn_id] = task
        task.add_done_callback(self._reply_finished)

    def _reply_finished(self, task: asyncio.Task[None]) -> None:
        """Forget the task and consume whatever it ended with."""
        for turn_id, known in tuple(self._replies.items()):
            if known is task:
                del self._replies[turn_id]
                break
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:  # pragma: no cover - the pump catches its own
            _log.error("reply pump failed (%s)", type(error).__name__)

    async def _pump_reply(
        self,
        binding: ChannelSurfaceBinding,
        handle: TurnHandle,
        reply_target: Mapping[str, Any],
    ) -> None:
        """Watch one exchange and put what it says in front of the person.

        Two deliveries, with different sources and different guarantees:

        *While it runs*, the frames in :data:`DEFAULT_DELIVERED_TYPES` are
        rendered and sent as they happen — the queue notice, the approval
        card, a terminal frame that is not a success. These are control
        frames and the stream never drops one.

        *When it ends*, the answer, taken from the exchange's trajectory
        rather than from the deltas (see :meth:`_answer`). A deployment that
        puts ``TEXT_DELTA`` in its own delivered set gets a live stream
        instead, batched by :class:`~omicsclaw.entry.render.TextRenderer` so
        that a token is not a message; ``streamed`` is then what stops the
        answer being sent a second time.

        ``async with`` rather than a bare ``async for``: breaking out of an
        iteration does **not** detach the observation
        (``TurnStream.observer_count`` counts attachments, and an object with
        ``__anext__`` has no ``break`` hook), so without this the grace period
        that abandons an unwatched exchange would never start and the Task
        running it would leak. This is the one place that obligation lands.
        """
        renderer = TextRenderer(batched=True, batch_chars=binding.text_chunk_limit)
        sent = 0
        streamed = False
        async with handle.observe() as observation:
            async for event in observation:
                if event.type not in self._delivered_types:
                    continue
                if event.type is TurnEventType.EXCHANGE_END:
                    if event.terminal == _CONVERGED:
                        # "Done." is noise in a chat window. A cancelled or
                        # failed exchange *is* fed, because silence there is
                        # indistinguishable from an answer still being
                        # written.
                        continue
                text = renderer.feed(event)
                if not text:
                    continue
                streamed = streamed or event.type is TurnEventType.TEXT_DELTA
                landed = await self._send(binding, reply_target, text, handle, sent)
                sent += 1
                if not landed:
                    return
        tail = renderer.flush()
        if tail:
            landed = await self._send(binding, reply_target, tail, handle, sent)
            sent += 1
            if not landed:
                return
        if streamed:
            # A deployment that asked for a live token stream has already been
            # given the answer, gaps and all; sending it again from the
            # trajectory would deliver it twice.
            return
        answer = await self._answer(handle)
        if answer:
            await self._send(binding, reply_target, answer, handle, sent)

    async def _answer(self, handle: TurnHandle) -> str:
        """The exchange's own final words, waited for and read from the record.

        **Not accumulated from the event stream.** Delta frames are droppable
        under buffer pressure (plan 0031 Q14) and an answer assembled from
        them can be silently short; the trajectory the engine returns is the
        only gap-free copy. See :data:`DEFAULT_DELIVERED_TYPES`.

        Waits, because the verdict is recorded by the registry *after* the
        terminal frame is published — the frame says the exchange ended, and
        :meth:`~omicsclaw.entry.turn.TurnHandle.wait` says what it ended
        with. Returns ``""`` for anything that did not converge: a cancelled
        or failed exchange has already been reported by its terminal frame,
        and a half-written answer is not one.
        """
        outcome = await handle.wait()
        if outcome is None or handle.terminal != _CONVERGED:
            return ""
        for message in reversed(outcome.result.messages):
            if message.role is Role.ASSISTANT and message.content:
                return message.content
        return ""

    async def _send(
        self,
        binding: ChannelSurfaceBinding,
        reply_target: Mapping[str, Any],
        text: str,
        handle: TurnHandle,
        ordinal: int,
    ) -> bool:
        """Chunk one rendered message out, and say whether it landed.

        ``False`` stops the pump. Pushing the rest of an answer at a
        transport that just refused, or that may have taken a copy already,
        turns one undelivered paragraph into an unreadable conversation.
        """
        if not reply_target:
            return False
        chunks = chunk_text(text, binding.text_chunk_limit)
        result = await deliver(
            binding.delivery_adapter,
            chunks,
            # Stable per message and per attempt, because Feishu deduplicates
            # by it for an hour — regenerating it per attempt would defeat the
            # one thing that makes a retry safe there.
            item_prefix=f"{handle.turn_id}-{ordinal}",
            reply_target=reply_target,
            sleep=self._sleep,
        )
        if result.acceptance is Acceptance.ACCEPTED:
            return True
        _log.warning(
            "reply for %s ended %s; not sending the rest of it",
            handle.turn_id,
            result.acceptance.value,
        )
        return False

    # ---- internals -------------------------------------------------------

    def _remember(
        self, session_id: str, source_request_id: str, turn_id: str
    ) -> None:
        """Retain one idempotency key, within the registry's own window.

        The bound is :attr:`~omicsclaw.entry.config.AppConfig.max_sessions`
        because that is how many exchanges the registry itself keeps
        addressable; remembering a key whose exchange has already aged out of
        the registry would resolve a redelivery to a handle nobody can reach.

        Keyed by conversation as well, matching
        :class:`~omicsclaw.entry.session.SessionRegistry`: two chats whose
        platform numbers its callbacks independently would otherwise share
        one key space, and the second chat's first message would be reported
        as a duplicate of the first chat's.
        """
        if not source_request_id:
            return
        key = (session_id, source_request_id)
        self._accepted[key] = turn_id
        self._accepted.move_to_end(key)
        while len(self._accepted) > self._app.config.max_sessions:
            self._accepted.popitem(last=False)


def _refused(code: str) -> ChannelSubmission:
    return ChannelSubmission(
        acceptance=TurnAcceptanceResult(status=TurnAcceptanceStatus.REJECTED, code=code)
    )


async def compose_channel_runtime(
    app: AgentApp,
    channels: Sequence[Any],
    **kwargs: Any,
) -> ChannelRuntime:
    """Phase 1 of start-up: collect every binding, then build one runtime.

    The ordering is the whole function and it is not arbitrary — it is
    ``__main__.py:401-450``'s, which this replaces:

    1. **every** channel authenticates and returns a binding before anything
       is composed, so a channel that cannot reach its platform fails the
       start rather than leaving half a deployment answering messages;
    2. the runtime is started **before** it is bound into the channels, so no
       channel can submit into a runtime that is not accepting;
    3. a failure at any point releases every channel that got as far as
       authenticating.

    The loop is captured by :meth:`ChannelRuntime.start` and handed to each
    channel here, because a channel whose SDK delivers events on its own
    thread has to submit to *that* loop and cannot discover it itself.

    Ingress stays closed afterwards: opening it is
    :meth:`~omicsclaw.entry.channel.manager.ChannelManager.start_all`'s
    barrier, which opens every channel's at once.
    """
    prepared: list[Any] = []
    bindings: list[ChannelSurfaceBinding] = []
    try:
        for channel in channels:
            prepared.append(channel)
            binding = await channel.prepare_control_binding()
            if binding is None:
                raise RuntimeError(
                    f"Channel {channel.name!r} produced no binding; a cut-over "
                    "channel must describe its adapter, account and owners"
                )
            bindings.append(binding)
        runtime = ChannelRuntime.for_channel_surfaces(
            app, bindings=tuple(bindings), **kwargs
        )
        await runtime.start()
        loop = asyncio.get_running_loop()
        for channel in prepared:
            channel.bind_control_runtime(runtime, loop=loop)
    except BaseException:
        for channel in prepared:
            try:
                await channel.stop()
            except Exception as error:  # pragma: no cover - reported, not raised
                _log.error(
                    "releasing %s after a failed composition (%s)",
                    getattr(channel, "name", "?"),
                    type(error).__name__,
                )
        raise
    return runtime
