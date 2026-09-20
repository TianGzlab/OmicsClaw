"""``omicsclaw/entry`` — turning "ask a human" into a frame and a future.

Plan 0031 trap 1. A tool that needs consent calls
:func:`omicsclaw.tools.require_approval`, which awaits the
:data:`~omicsclaw.tools.ApprovalChannel` bound for its Task. That
``await`` happens **inside** the tool, inside
``AgentEngine.run_stream``'s ``__anext__``. The generator that would have
to announce the question is the same generator that is suspended waiting
for its answer, so no arrangement of a single consumer loop can both show
the prompt and produce the decision:

- a consumer that *polls* between engine events never sees the request,
  because the request is issued after it went back to waiting;
- a consumer that stops iterating to show a dialog stops the engine, and
  with two concurrent tools the second request never even happens.

The way out this layer takes is the first of the two
``omicsclaw/tools/context.py:136-141`` names: the engine runs in **its
own Task**, and this broker is the seam between it and whoever answers.
The request becomes an ``APPROVAL_REQUIRED`` frame on the exchange's
:class:`~omicsclaw.entry.stream.TurnStream` — which any number of
observers can be reading — plus an :class:`asyncio.Future` that a
*different* Task resolves through :meth:`ApprovalBroker.settle`.

**This channel is asynchronous**, and that is a decision rather than an
accommodation. ``ApprovalChannel`` is typed ``Callable[[ApprovalRequest],
Any]`` and ``require_approval`` awaits the result only when it is
awaitable, so a synchronous channel is legal; a synchronous broker is
not, because the whole of its job is to suspend one Task until another
one answers, and there is no synchronous spelling of that which does not
block the event loop the answer has to arrive on. :meth:`settle` is the
synchronous half, and it is synchronous for the mirror-image reason: it
is called from a click handler, an HTTP route or an IM callback, and
none of those should have to await anything to deliver one boolean.

**The deadline denies** (plan 0031 Q12). ``timeout_s=None`` waits for as
long as the exchange lives, which is what a CLI with a person in front of
it wants. A channel surface must set a number, and when that number
expires the answer is *no*: an approval that expired into consent would
be a security control that a silent user disables.

**Never logs an argument.** ``omicsclaw.entry``'s logging rule (Q22) is
at its sharpest here — an :class:`~omicsclaw.tools.ApprovalRequest`
carries the raw argument payload of the call about to run, which is
exactly the ``bash`` command line or ``write_file`` body that may name a
subject. Only the tool name, the request id and the outcome are logged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from omicsclaw.entry.events import TurnEvent
from omicsclaw.entry.stream import TurnStream
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest

__all__ = [
    "ABANDONED_REASON",
    "ApprovalBroker",
    "TIMEOUT_REASON",
]

_log = logging.getLogger(__name__)

TIMEOUT_REASON: Final = "no answer before the approval deadline"
"""Denial reason when :attr:`AppConfig.approval_timeout_s` expires.

Reaches the model through ``ApprovalDenied``, so it is written for a
reader that has to decide what to do next: "nobody answered" is a
different instruction from "the user said no", and a model told only
"denied" will retry the same call.
"""

ABANDONED_REASON: Final = "the exchange ended before this was answered"
"""Denial reason when the exchange ends with a question outstanding.

Also a denial, for :data:`TIMEOUT_REASON`'s reason: an unanswered
question is not consent, whatever ended it.
"""


class ApprovalBroker:
    """One exchange's outstanding questions, addressable by id.

    Created per exchange, alongside its :class:`TurnStream`. The broker
    **is** the :data:`~omicsclaw.tools.ApprovalChannel`: pass the
    instance itself to
    :func:`~omicsclaw.tools.use_tool_context`. Two roles, deliberately on
    one object, because they are two ends of one correlation:
    :meth:`__call__` runs on the exchange's Task and suspends, while
    :meth:`settle` runs on whatever Task the answer arrived on.

    Not thread-safe: :meth:`settle` resolves an :class:`asyncio.Future`,
    which is only safe from the loop's own thread. A surface whose SDK
    delivers callbacks on its own thread hops with
    ``loop.call_soon_threadsafe``, the same hop
    :meth:`TurnStream.publish_threadsafe` spells out.
    """

    __slots__ = ("_issued", "_pending", "_stream", "_timeout_s")

    def __init__(
        self,
        stream: TurnStream,
        *,
        timeout_s: float | None = None,
    ) -> None:
        """``timeout_s=None`` waits for as long as the exchange runs.

        A non-positive deadline is refused rather than treated as "deny
        immediately": a surface that computed one from arithmetic that
        went wrong would otherwise silently deny every tool that asks,
        which reads as "the agent cannot use tools" and not as a
        misconfiguration.
        """
        if timeout_s is not None and timeout_s <= 0:
            raise ValueError("approval timeout must be positive, or None to wait")
        self._stream = stream
        self._timeout_s = timeout_s
        self._pending: dict[str, asyncio.Future[ApprovalDecision]] = {}
        self._issued = 0

    async def __call__(self, request: ApprovalRequest) -> ApprovalDecision:
        """Publish the question, then wait for somebody to answer it.

        The :data:`~omicsclaw.tools.ApprovalChannel` implementation.
        Returns a decision — approved or denied — and never raises on the
        denial paths; ``require_approval`` is what turns a denial into
        ``ApprovalDenied`` for the tool.

        :raises asyncio.CancelledError: the exchange was cancelled while
            this question was outstanding. The pending entry is dropped
            first, so a decision that arrives afterwards is the no-op
            :meth:`settle` documents rather than an
            :exc:`~asyncio.InvalidStateError`.
        """
        loop = asyncio.get_running_loop()
        self._issued += 1
        request_id = f"{self._stream.turn_id}#{self._issued}"
        future: asyncio.Future[ApprovalDecision] = loop.create_future()
        self._pending[request_id] = future

        self._stream.publish(
            TurnEvent.approval_required(
                request,
                request_id,
                session_id=self._stream.session_id,
                turn_id=self._stream.turn_id,
            )
        )
        _log.info(
            "approval requested: tool=%s request=%s risk=%s",
            request.tool_name,
            request_id,
            request.risk_level,
        )

        try:
            decision = await self._decide(future)
        except asyncio.CancelledError:
            self._pending.pop(request_id, None)
            raise

        # Absent means :meth:`abandon` already resolved and announced it;
        # publishing a second APPROVAL_SETTLED for one request_id would
        # make a consumer's correlation table ambiguous.
        if self._pending.pop(request_id, None) is None:
            return decision

        self._stream.publish(
            TurnEvent.approval_settled(
                request_id,
                decision,
                session_id=self._stream.session_id,
                turn_id=self._stream.turn_id,
            )
        )
        _log.info(
            "approval settled: request=%s approved=%s",
            request_id,
            decision.approved,
        )
        return decision

    def settle(self, request_id: str, decision: ApprovalDecision) -> bool:
        """Answer one outstanding question. Unknown ids are a no-op.

        Returns whether the answer took effect, so a caller that wants to
        tell a person "that card has expired" can. **Returning ``False``
        is the normal case, not an error** (plan 0031 Q18): a decision
        comes from a human, and a human clicking twice, clicking after
        the deadline, or clicking on a card their client re-rendered
        after a reconnect are all ordinary inputs. Raising on them would
        turn a double-click into a traceback in a surface's callback.
        """
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(decision)
        return True

    def abandon(self, reason: str = ABANDONED_REASON) -> None:
        """Deny everything still outstanding, and say so on the stream.

        Called from the exchange's ``finally`` so that a question which
        outlived its exchange fails closed. Synchronous on purpose: that
        ``finally`` may be running inside a Task that has already been
        cancelled, where the next ``await`` re-raises immediately and a
        coroutine would not finish (plan 0031 trap 3b).

        Resolving the futures matters even when the waiter is about to be
        cancelled anyway: on the *timeout* and *failure* paths it is not,
        and a tool left awaiting a future nobody will ever complete is a
        Task that never finishes.
        """
        if not self._pending:
            return
        decision = ApprovalDecision(approved=False, reason=reason)
        for request_id, future in tuple(self._pending.items()):
            del self._pending[request_id]
            if not future.done():
                future.set_result(decision)
            self._stream.publish(
                TurnEvent.approval_settled(
                    request_id,
                    decision,
                    session_id=self._stream.session_id,
                    turn_id=self._stream.turn_id,
                )
            )
            _log.info("approval abandoned: request=%s", request_id)

    def pending(self) -> tuple[str, ...]:
        """Ids of the questions waiting for an answer, oldest first."""
        return tuple(self._pending)

    async def _decide(
        self,
        future: asyncio.Future[ApprovalDecision],
    ) -> ApprovalDecision:
        """Wait for the future, applying the deadline if there is one.

        The expiry is caught here and turned into a denial rather than
        allowed to propagate: a :exc:`TimeoutError` escaping the channel
        would surface to the model as a tool that crashed, when what
        happened is that a person did not answer.
        """
        if self._timeout_s is None:
            return await future
        try:
            async with asyncio.timeout(self._timeout_s):
                return await future
        except TimeoutError:
            _log.info("approval deadline expired after %.1fs", self._timeout_s)
            return ApprovalDecision(approved=False, reason=TIMEOUT_REASON)
