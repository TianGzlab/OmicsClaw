"""Single-attempt Slack Adapter for outbound Delivery.

The pump owns ordering and retry policy. This Adapter performs one
``chat.postMessage`` call and classifies only the outcome of that call; it
never dispatches conversational work, sleeps, retries, chunks text, or sends
media.

Slack answers a rate limit with HTTP 429 and a ``Retry-After`` header, which
is the only refusal here with evidence that the message was *not* delivered.
Everything without such an answer — a timeout, a dropped socket, an error
nobody anticipated — may have crossed the acceptance seam and is reported as
unknown, because a resend there puts a second copy of an answer in front of
somebody who has already read the first and nothing upstream can see it
happen.
"""

from __future__ import annotations

from functools import lru_cache
import math
from typing import Any

from . import reply_target
from .delivery import (
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from .reply_target import InvalidReplyTarget

__all__ = ["SlackDeliveryAdapter"]

_MAX_MESSAGE_ID_CHARS = 128
_MAX_RETRY_AFTER_MS = 7 * 24 * 60 * 60 * 1_000

PERMANENT_ERRORS = frozenset(
    {
        "invalid_auth",
        "not_authed",
        "account_inactive",
        "token_revoked",
        "channel_not_found",
        "is_archived",
        "msg_too_long",
        "no_text",
        "restricted_action",
    }
)
"""Slack error codes that mean *this will never work*, so stop.

Deliberately a small allow-list of refusals rather than "any 4xx". An
omission costs one reply reported as unknown, which the pump already handles
safely; a wrong entry would declare a delivered message undelivered.
"""


@lru_cache(maxsize=1)
def _slack_api_error() -> type[BaseException] | None:
    """Load the optional Slack SDK only when an attempt has already raised."""

    try:
        from slack_sdk.errors import SlackApiError
    except ImportError:
        return None
    return SlackApiError


def _is_api_error(error: BaseException) -> bool:
    """Whether *error* is Slack's own, by type or — with no SDK — by name."""

    error_type = _slack_api_error()
    return (error_type is not None and isinstance(error, error_type)) or type(
        error
    ).__name__ == "SlackApiError"


def _response_field(response: object, key: str) -> Any:
    """One field of a Slack response, whether it behaves as a mapping or not."""

    getter = getattr(response, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None
    return getattr(response, key, None)


def _retry_after_ms(response: object) -> int | None:
    """The wait Slack asked for, in the header it sends it in.

    ``None`` is *Slack did not say*, which is not zero: reading a missing
    hint as "retry now" turns one rate limit into a tighter loop against the
    thing that just imposed it.
    """
    headers = getattr(response, "headers", None)
    raw = None
    if headers is not None:
        getter = getattr(headers, "get", None)
        if callable(getter):
            raw = getter("Retry-After") or getter("retry-after")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(_MAX_RETRY_AFTER_MS, int(math.ceil(seconds * 1_000)))


_MRKDWN_ESCAPES = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;"})


def _escape_mrkdwn(text: str) -> str:
    """*text* with ``&``, ``<`` and ``>`` written as Slack's entities.

    These are the three characters Slack's formatting rules say to escape.
    Every mention, channel reference and link in ``mrkdwn`` is written
    between ``<`` and ``>``, so none survives; nothing else changes.

    Args:
        text: The text to send, as written.

    Returns:
        The text Slack displays as *text*.
    """
    return text.translate(_MRKDWN_ESCAPES)


def _post_message_arguments(request: DeliveryAttemptRequest) -> dict[str, Any]:
    target = reply_target.read(request, adapter="slack")
    arguments: dict[str, Any] = {
        "channel": target["destination_id"],
        "text": _escape_mrkdwn(request.text),
    }
    thread_ts = target.get("thread_ts")
    if thread_ts:
        # Keeps an answer in the thread the question was asked in; without it
        # a busy channel interleaves several conversations at top level.
        arguments["thread_ts"] = str(thread_ts)
    return arguments


def _message_evidence(response: object) -> dict[str, Any] | None:
    ts = _response_field(response, "ts")
    if ts is None:
        return None
    bounded = str(ts)[:_MAX_MESSAGE_ID_CHARS]
    return {"message_id": bounded} if bounded else None


class SlackDeliveryAdapter:
    """Perform exactly one Slack text Delivery Attempt.

    The text is sent with ``&``, ``<`` and ``>`` escaped, so Slack displays
    it as written and resolves no mention, channel reference or link in it.
    """

    def __init__(self, web_client: Any) -> None:
        self._web_client = web_client

    async def __call__(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        return await self.attempt(request)

    async def attempt(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        try:
            arguments = _post_message_arguments(request)
        except InvalidReplyTarget:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="slack_invalid_delivery",
            )

        try:
            response = await self._web_client.chat_postMessage(**arguments)
        except Exception as error:
            return self._classify_error(error)

        if _response_field(response, "ok") is False:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="slack_rejected",
                provider_evidence={"error": str(_response_field(response, "error"))},
            )
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTED,
            provider_evidence=_message_evidence(response),
        )

    def _classify_error(self, error: BaseException) -> DeliveryAdapterResult:
        """What one raised call is allowed to mean.

        Only a 429 with Slack's own answer behind it is provably a refusal;
        everything else, this adapter does not know.
        """
        if not _is_api_error(error):
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
                error_code="slack_acceptance_unknown",
            )
        response = getattr(error, "response", None)
        if getattr(response, "status_code", None) == 429:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
                error_code="slack_rate_limited",
                retry_after_ms=_retry_after_ms(response),
            )
        code = _response_field(response, "error")
        if isinstance(code, str) and code in PERMANENT_ERRORS:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="slack_rejected",
                provider_evidence={"error": code},
            )
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
            error_code="slack_acceptance_unknown",
        )
