"""One outbound message, one provider call, and what to believe afterwards.

Plan 0031 §5.3. The classification in this module is **not new work**: the
deleted control plane already had it, and the two shipped adapters
(:mod:`~omicsclaw.entry.channel.telegram_delivery`,
:mod:`~omicsclaw.entry.channel.feishu_delivery`) already return it. This file
is the vocabulary they were returning it in, moved across and connected to
:class:`~omicsclaw.entry.ingress.Acceptance`.

**Three states, and the third is the one that carries the engineering.**
``telegram_delivery.py:161-164`` says it in its own words — "The Pump must not
retry blindly". A send that timed out may or may not have arrived; resending it
produces a second visible reply that no control plane can see or account for.
So a transport failure is :attr:`DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN` and
never a softer rejection.

**Four adapter outcomes project onto three acceptances.** The adapters
distinguish *refused, permanently* from *refused, try again* because they can:
Telegram raises ``RetryAfter`` with a number on it and Feishu answers with a
rate-limit code. :class:`~omicsclaw.entry.ingress.Acceptance` has three members
and a ``retry_after``, which is where that fourth state lands —
:meth:`DeliveryAdapterResult.as_delivery_result` is the whole of the mapping
and the only place it is spelled. The adapter-level enum is kept rather than
collapsed at the source, so that a caller which needs to know *whether* a
retry is permitted can ask :attr:`DeliveryAdapterResult.retryable` instead of
inferring it from the presence of a hint the platform may simply not have sent.

**Retry policy lives here, the decision to retry does not.** :func:`deliver`
makes at most :data:`MAX_DELIVERY_ATTEMPTS` provider calls for one message and
stops on anything that is not provably retryable. It does not persist
anything: durable outbox ordering was the deleted control plane's and is not
this step's (plan 0031 §11).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Final, Mapping, Sequence

from omicsclaw.entry.ingress import Acceptance, DeliveryResult

__all__ = [
    "ATTEMPT_TIMEOUT_S",
    "DeliveryAdapter",
    "DeliveryAdapterResult",
    "DeliveryAttemptOutcome",
    "DeliveryAttemptRequest",
    "MAX_DELIVERY_ATTEMPTS",
    "RETRY_BASE_S",
    "RETRY_MAX_S",
    "deliver",
]

_log = logging.getLogger(__name__)

MAX_DELIVERY_ATTEMPTS: Final = 3
"""Provider calls one outbound message may cost.

``max_attempts=3`` from the deleted pump's constructor
(``git show HEAD:omicsclaw/control/delivery.py:61``), kept rather than rounded:
it was the number running against these same two platforms.
"""

RETRY_BASE_S: Final = 1.0
"""First backoff when the platform refused but did not say when to return.

``retry_base_ms=1_000`` from the same constructor, line 62, in seconds.
"""

RETRY_MAX_S: Final = 60.0
"""Ceiling on any wait, including one the platform asked for.

``retry_max_ms=60_000``, same source, line 63. A platform may ask for a week
(``_MAX_RETRY_AFTER_MS`` in both adapters bounds it there); honouring that
inside one exchange would pin a Task open for a week.
"""

ATTEMPT_TIMEOUT_S: Final = 30.0
"""Wall clock for one provider call before it is abandoned as unknown.

``attempt_timeout_seconds=30.0``, same source, line 65. An adapter that never
returns is indistinguishable from one whose message arrived, so the timeout
resolves to ``ACCEPTANCE_UNKNOWN`` and not to a retry.
"""

_EMPTY_TARGET: Mapping[str, Any] = MappingProxyType({})


class DeliveryAttemptOutcome(StrEnum):
    """How one provider call ended, in the adapters' own vocabulary.

    Ported from ``HEAD:omicsclaw/control/models.py:151-155``, member for
    member, because both shipped adapters return these names today and
    renaming them would turn a two-line import change into a rewrite of every
    branch in both files (plan 0031 Q23).
    """

    ACCEPTED = "accepted"
    """The platform took the message. Never send it again."""

    NOT_ACCEPTED_RETRYABLE = "not_accepted_retryable"
    """The platform refused *and* the refusal is provably transient — a rate
    limit it named. Only refusals with that evidence belong here: a wrong
    entry duplicates a delivered reply."""

    REJECTED_PERMANENT = "rejected_permanent"
    """The platform answered and refused. Retrying changes nothing, and the
    answer itself is proof the message was not delivered."""

    ACCEPTANCE_UNKNOWN = "acceptance_unknown"
    """The call ended without an answer. It may have arrived."""


@dataclass(frozen=True, slots=True)
class DeliveryAttemptRequest:
    """The exact immutable provider-call request for one attempt.

    Flattened from ``HEAD:omicsclaw/control/models.py:667-689``, which read
    :attr:`item_id` and :attr:`reply_target` through a ``DeliveryCandidate``
    row. There is no durable outbox here, so the three fields the adapters
    actually read are the three fields there are.
    """

    item_id: str
    """Stable id for *this message*, not this attempt.

    Feishu's ``uuid`` deduplicates by it for an hour
    (``feishu_delivery.py:110-116``), so a retry of the same item cannot
    produce a second visible message — which is only true while the id stays
    the same across attempts. Bounded at 50 characters by that API.
    """

    text: str
    """What to send. Already chunked to the platform's limit by the caller;
    an adapter performs one call and never splits."""

    reply_target: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_TARGET)
    """Where to send it, in the shape the adapter validates — ``kind``,
    ``adapter``, ``destination_id``, and whatever else that platform needs
    (Telegram's ``thread_id``, Feishu's ``destination_kind``)."""

    attempt_no: int = 1
    """1-based, for logs. An adapter must not branch on it: "have I tried
    before" is the caller's state, not the provider call's."""


@dataclass(frozen=True, slots=True)
class DeliveryAdapterResult:
    """One adapter call's classified result.

    Ported from ``HEAD:omicsclaw/control/models.py:692-726`` minus the
    persistence validation, which guarded a database this step does not have.
    """

    outcome: DeliveryAttemptOutcome
    error_code: str | None = None
    """Short, bounded, and platform-specific — ``telegram_retry_after``,
    ``feishu_rejected``. For a log line, never for a branch."""

    provider_evidence: Mapping[str, Any] | None = None
    """What the platform said about the message it accepted, e.g. its own
    ``message_id``. Evidence that a send happened, kept small on purpose."""

    retry_after_ms: int | None = None
    """What the platform asked us to wait, when it said. ``None`` is *it did
    not say* and is not zero."""

    @property
    def retryable(self) -> bool:
        """Whether sending this message again is known to be safe and useful.

        True for exactly one outcome. ``ACCEPTANCE_UNKNOWN`` is deliberately
        excluded: a resend there may duplicate a reply a human already read.
        """
        return self.outcome is DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE

    def as_delivery_result(self) -> DeliveryResult:
        """Project onto the three-state vocabulary the whole layer shares.

        Both refusals become :attr:`~omicsclaw.entry.ingress.Acceptance
        .REJECTED`; the retryable one keeps its ``retry_after`` when the
        platform supplied one. That is a real narrowing — a retryable refusal
        with no hint is indistinguishable from a permanent one on the wire —
        and it is why :attr:`retryable` stays readable on this object for the
        caller that has to decide.
        """
        if self.outcome is DeliveryAttemptOutcome.ACCEPTED:
            return DeliveryResult(acceptance=Acceptance.ACCEPTED)
        if self.outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN:
            return DeliveryResult(acceptance=Acceptance.UNKNOWN)
        retry_after = None
        if self.retry_after_ms is not None:
            retry_after = self.retry_after_ms / 1000.0
        return DeliveryResult(acceptance=Acceptance.REJECTED, retry_after=retry_after)


DeliveryAdapter = Callable[[DeliveryAttemptRequest], Awaitable[DeliveryAdapterResult]]
"""One platform's single-attempt sender.

``TelegramDeliveryAdapter`` and ``FeishuDeliveryAdapter`` satisfy it through
``__call__``. Structural, not a base class: an adapter is a function that makes
one call and classifies it, and inheritance would suggest it has a lifecycle.
"""


async def deliver(
    adapter: DeliveryAdapter,
    chunks: Sequence[str],
    *,
    item_prefix: str,
    reply_target: Mapping[str, Any],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> DeliveryResult:
    """Send *chunks* in order, stopping at the first one that does not land.

    Returns the result of the **last attempt made**, so a caller sees the
    reason the reply is incomplete rather than a summary that hides it.

    Three rules, each of which is a failure mode rather than a preference:

    - *Stop on the first failure.* Continuing would deliver paragraph three of
      an answer whose paragraph two never arrived, which reads as a different
      answer.
    - *Never retry an unknown.* The message may be in front of the human
      already; a second copy is worse than a missing one, and unlike a missing
      one it cannot be noticed by the process that caused it.
    - *One item id per chunk, stable across attempts.* It is the platform's
      idempotency key where there is one, so it must not be regenerated per
      attempt.

    *sleep* is injected so a test can assert the backoff without waiting it
    out; production passes :func:`asyncio.sleep`.
    """
    outcome = DeliveryResult(acceptance=Acceptance.ACCEPTED)
    for index, chunk in enumerate(chunks):
        if not chunk:
            continue
        outcome = await _deliver_one(
            adapter,
            chunk,
            item_id=f"{item_prefix}-{index}",
            reply_target=reply_target,
            sleep=sleep,
        )
        if outcome.acceptance is not Acceptance.ACCEPTED:
            return outcome
    return outcome


async def _deliver_one(
    adapter: DeliveryAdapter,
    text: str,
    *,
    item_id: str,
    reply_target: Mapping[str, Any],
    sleep: Callable[[float], Awaitable[None]],
) -> DeliveryResult:
    """One chunk, up to :data:`MAX_DELIVERY_ATTEMPTS` provider calls."""
    result = DeliveryAdapterResult(
        outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        error_code="no_attempt_made",
    )
    for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
        request = DeliveryAttemptRequest(
            item_id=item_id,
            text=text,
            reply_target=reply_target,
            attempt_no=attempt,
        )
        result = await _attempt(adapter, request)
        if result.outcome is DeliveryAttemptOutcome.ACCEPTED:
            return result.as_delivery_result()
        _log.warning(
            "delivery attempt %d/%d for %s ended %s (%s)",
            attempt,
            MAX_DELIVERY_ATTEMPTS,
            item_id,
            result.outcome.value,
            result.error_code or "unspecified",
        )
        if not result.retryable or attempt == MAX_DELIVERY_ATTEMPTS:
            return result.as_delivery_result()
        await sleep(_backoff(attempt, result.retry_after_ms))
    return result.as_delivery_result()  # pragma: no cover - loop always returns


async def _attempt(
    adapter: DeliveryAdapter,
    request: DeliveryAttemptRequest,
) -> DeliveryAdapterResult:
    """Call the adapter once, bounded, and never let it raise into the pump.

    An adapter that raises has told us nothing about whether the message
    arrived, which is exactly ``ACCEPTANCE_UNKNOWN``. Letting the exception
    out instead would abort the reply of an exchange that has already run.
    """
    try:
        async with asyncio.timeout(ATTEMPT_TIMEOUT_S):
            result = await adapter(request)
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
            error_code="attempt_timeout",
        )
    except Exception as error:
        _log.warning("delivery adapter raised (%s)", type(error).__name__)
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
            error_code="adapter_raised",
        )
    if not isinstance(result, DeliveryAdapterResult):
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
            error_code="adapter_result_unusable",
        )
    return result


def _backoff(attempt: int, retry_after_ms: int | None) -> float:
    """Seconds to wait before the next attempt, bounded by :data:`RETRY_MAX_S`.

    A platform-supplied hint wins over the exponential default, because it is
    the only figure that knows when the rate limit actually lifts.
    """
    if retry_after_ms is not None:
        return min(RETRY_MAX_S, max(0.0, retry_after_ms / 1000.0))
    return min(RETRY_MAX_S, RETRY_BASE_S * (2 ** (attempt - 1)))
