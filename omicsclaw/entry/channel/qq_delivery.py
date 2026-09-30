"""Single-attempt QQ Adapter for outbound Delivery.

The pump owns ordering and retry policy. This Adapter performs one
``post_group_message`` or ``post_c2c_message`` call and classifies only the
outcome of that call; it never dispatches conversational work, sleeps,
retries, chunks text, or sends media.

**Two duties live here that look like they belong elsewhere.**

*The sequence number.* QQ only accepts a passive reply addressed to the
inbound message's ``msg_id``, numbered by a ``msg_seq`` that increases
within it. The number therefore has to be a property of **the message being
sent**, not of the attempt: :func:`~omicsclaw.entry.channel.delivery.deliver`
may call this adapter up to three times for one chunk, and a counter would
hand each retry a fresh number. QQ would read that as a new message and the
person would see the same answer twice — which is precisely the duplicate
that ``ACCEPTANCE_UNKNOWN`` exists to prevent. :class:`MessageSequence` keys
the number by the delivery item id, which is stable across attempts.

*The formatting.* QQ renders no Markdown, so an answer written in it arrives
full of asterisks and backticks. Reducing it is part of "how this platform
takes a message", the same layer as validating the address — and putting it
in the pump instead would make the pump know seven Markdown dialects.
"""

from __future__ import annotations

from collections import OrderedDict
import math
import re
from typing import Any, Final

from . import reply_target
from .delivery import (
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from .reply_target import InvalidReplyTarget

__all__ = ["MessageSequence", "QQDeliveryAdapter", "strip_markdown"]

_MAX_MESSAGE_ID_CHARS = 128
_MAX_RETRY_AFTER_MS = 7 * 24 * 60 * 60 * 1_000

PERMANENT_ERRORS: Final = frozenset(
    {
        "AuthenticationFailedError",
        "UnauthorizedError",
        "ForbiddenError",
        "NotFoundError",
        "MethodNotAllowedError",
        "SequenceNumberError",
    }
)
"""botpy exception names that mean *this will never work*, so stop."""


def strip_markdown(text: str) -> str:
    """Reduce Markdown to text QQ can display, which is plain text.

    QQ renders none of it, so an unreduced answer reaches the person with
    the punctuation still in it — ``**bold**`` rather than bold. Nothing
    upstream can see that happen: the platform accepts asterisks as happily
    as words, so the acceptance classification stays green throughout.
    """
    text = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip("`").strip(), text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1(\2)", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\-\*]\s+", "• ", text, flags=re.MULTILINE)
    return text


class MessageSequence:
    """``msg_seq`` per inbound message, keyed by what is being sent.

    Keyed by delivery item id and **not** by a counter. The item id is
    stable across the attempts one message may cost, so a retry reuses its
    own number and QQ recognises the resend as the same message rather than
    posting a second one; a new chunk gets the next number, which is what QQ
    requires of consecutive replies.

    Bounded, because a long-lived process would otherwise accumulate one
    entry per conversation it has ever answered.
    """

    def __init__(self, max_targets: int = 500) -> None:
        self._by_target: OrderedDict[str, dict[str, int]] = OrderedDict()
        self._max = max(1, max_targets)

    def of(self, msg_id: str, item_id: str) -> int:
        numbers = self._by_target.get(msg_id)
        if numbers is None:
            numbers = {}
            self._by_target[msg_id] = numbers
            while len(self._by_target) > self._max:
                self._by_target.popitem(last=False)
        self._by_target.move_to_end(msg_id)
        if item_id not in numbers:
            numbers[item_id] = len(numbers) + 1
        return numbers[item_id]


def _retry_after_ms(error: BaseException) -> int | None:
    """The wait QQ asked for, when it said. ``None`` is *it did not*."""

    for holder in (error, getattr(error, "response", None)):
        headers = getattr(holder, "headers", None)
        getter = getattr(headers, "get", None)
        if not callable(getter):
            continue
        raw = getter("Retry-After") or getter("retry-after")
        if raw is None:
            continue
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(seconds) or seconds < 0:
            continue
        return min(_MAX_RETRY_AFTER_MS, int(math.ceil(seconds * 1_000)))
    return None


def _http_status(error: BaseException) -> int | None:
    """The HTTP status behind a botpy error, wherever it put it."""

    for holder in (error, getattr(error, "response", None)):
        if holder is None:
            continue
        for attribute in ("status", "status_code", "code"):
            value = getattr(holder, attribute, None)
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 100 <= value < 600
            ):
                return value
    return None


def _evidence(result: object) -> dict[str, Any] | None:
    reader = getattr(result, "get", None)
    message_id = reader("id") if callable(reader) else getattr(result, "id", None)
    if message_id is None:
        return None
    bounded = str(message_id)[:_MAX_MESSAGE_ID_CHARS]
    return {"message_id": bounded} if bounded else None


class QQDeliveryAdapter:
    """Perform exactly one QQ text Delivery Attempt."""

    def __init__(self, client: Any, sequence: MessageSequence | None = None) -> None:
        self._client = client
        self._sequence = sequence or MessageSequence()

    async def __call__(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        return await self.attempt(request)

    async def attempt(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        try:
            target = reply_target.read(request, adapter="qq")
            msg_id = target.get("msg_id")
            if not isinstance(msg_id, str) or not msg_id:
                # QQ only accepts a reply that names the message it answers.
                raise InvalidReplyTarget("reply_target has no msg_id")
        except InvalidReplyTarget:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="qq_invalid_delivery",
            )

        api = getattr(self._client, "api", None)
        is_group = target.get("msg_type") == "group"
        method = "post_group_message" if is_group else "post_c2c_message"
        send = getattr(api, method, None)
        if not callable(send):
            # Resolving the method happens strictly before any socket work, so
            # a missing client cannot have reached QQ.
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="qq_client_unavailable",
            )

        arguments: dict[str, Any] = {
            "msg_type": 0,
            "content": strip_markdown(request.text),
            "msg_id": msg_id,
            "msg_seq": self._sequence.of(msg_id, request.item_id),
        }
        if is_group:
            arguments["group_openid"] = target["destination_id"]
        else:
            arguments["openid"] = target["destination_id"]

        try:
            result = await send(**arguments)
        except Exception as error:
            return self._classify_error(error)

        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTED,
            provider_evidence=_evidence(result),
        )

    def _classify_error(self, error: BaseException) -> DeliveryAdapterResult:
        """What one raised send is allowed to mean.

        Only a 429 is provably a refusal that may be repeated. A 5xx, a
        timeout and anything unnamed may have crossed the acceptance seam,
        and repeating one of those is how a person reads the same answer
        twice without anything upstream noticing.
        """
        status = _http_status(error)
        if status == 429:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
                error_code="qq_rate_limited",
                retry_after_ms=_retry_after_ms(error),
            )
        if type(error).__name__ in PERMANENT_ERRORS or (
            status is not None and 400 <= status < 500
        ):
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="qq_rejected",
                provider_evidence={"error": type(error).__name__},
            )
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
            error_code="qq_acceptance_unknown",
        )
