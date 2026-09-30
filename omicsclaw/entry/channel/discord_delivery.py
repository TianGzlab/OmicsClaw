"""Single-attempt Discord Adapter for outbound Delivery.

The pump owns ordering and retry policy. This Adapter resolves one channel,
performs one ``channel.send`` call and classifies only the outcome of that
call; it never dispatches conversational work, sleeps, retries, chunks text,
or sends media.

Discord answers a rate limit with HTTP 429 and a ``retry_after`` on the
exception, which is the only refusal here with evidence that nothing was
delivered. A ``Forbidden`` or ``NotFound`` is an answer too — the platform
replied, and its reply is proof of non-delivery. Everything else, including
a timeout and a dropped gateway, may have crossed the acceptance seam and is
reported as unknown: resending there shows a second copy of an answer that
somebody may already have read.
"""

from __future__ import annotations

from functools import lru_cache
import math
from typing import Any, Mapping

from . import reply_target
from .delivery import (
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from .reply_target import InvalidReplyTarget

__all__ = ["DiscordDeliveryAdapter"]

_MAX_MESSAGE_ID_CHARS = 128
_MAX_RETRY_AFTER_MS = 7 * 24 * 60 * 60 * 1_000


@lru_cache(maxsize=1)
def _discord_error_types() -> Mapping[str, type[BaseException]]:
    """Load the optional Discord SDK only when an attempt has already raised."""

    try:
        from discord.errors import Forbidden, HTTPException, NotFound
    except ImportError:
        return {}
    return {
        "Forbidden": Forbidden,
        "HTTPException": HTTPException,
        "NotFound": NotFound,
    }


def _is_error(error: BaseException, class_name: str) -> bool:
    """Whether *error* is that Discord error, by type or — with no SDK — by name.

    The name comparison is exact and load-bearing: without ``discord.py``
    installed it is the only thing that tells a rate limit from a refusal.
    """
    error_type = _discord_error_types().get(class_name)
    return (error_type is not None and isinstance(error, error_type)) or type(
        error
    ).__name__ == class_name


def _retry_after_ms(error: BaseException) -> int | None:
    """The wait Discord asked for, when it said. ``None`` is *it did not*."""

    value = getattr(error, "retry_after", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(_MAX_RETRY_AFTER_MS, int(math.ceil(seconds * 1_000)))


def _channel_id(request: DeliveryAttemptRequest) -> int:
    target = reply_target.read(request, adapter="discord")
    try:
        return int(str(target["destination_id"]).strip())
    except (TypeError, ValueError) as exc:
        raise InvalidReplyTarget("destination_id must be a Discord snowflake") from exc


def _no_mentions() -> Any | None:
    """``discord.AllowedMentions.none()``, or ``None`` without ``discord.py``."""

    try:
        from discord import AllowedMentions
    except ImportError:
        return None
    return AllowedMentions.none()


def _message_evidence(message: object) -> dict[str, Any] | None:
    message_id = getattr(message, "id", None)
    if message_id is None:
        return None
    bounded = str(message_id)[:_MAX_MESSAGE_ID_CHARS]
    return {"message_id": bounded} if bounded else None


class DiscordDeliveryAdapter:
    """Perform exactly one Discord text Delivery Attempt.

    Every send carries ``allowed_mentions`` set to notify nobody, so the text
    is displayed as written and no mention in it pings anyone.
    """

    def __init__(self, client: Any, *, allowed_mentions: Any = None) -> None:
        """Wrap *client* for single-attempt sends.

        Args:
            client: The ``discord.py`` client whose channel cache resolves a
                destination.
            allowed_mentions: What every send passes as ``allowed_mentions``.
                ``None`` loads ``discord.AllowedMentions.none()`` at each
                attempt; an attempt with no ``discord.py`` to load it from
                is refused rather than sent without it.
        """
        self._client = client
        self._allowed_mentions = allowed_mentions

    async def __call__(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        return await self.attempt(request)

    async def attempt(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        try:
            channel_id = _channel_id(request)
        except InvalidReplyTarget:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="discord_invalid_delivery",
            )

        allowed_mentions = self._allowed_mentions
        if allowed_mentions is None:
            allowed_mentions = _no_mentions()
        if allowed_mentions is None:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="discord_client_unavailable",
            )

        # Resolving the channel happens strictly before any socket work, so a
        # miss here cannot have reached Discord and must not be reported as
        # ambiguous.
        channel = self._client.get_channel(channel_id)
        if channel is None:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="discord_channel_not_found",
            )

        try:
            message = await channel.send(
                request.text, allowed_mentions=allowed_mentions
            )
        except Exception as error:
            return self._classify_error(error)

        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTED,
            provider_evidence=_message_evidence(message),
        )

    def _classify_error(self, error: BaseException) -> DeliveryAdapterResult:
        """What one raised send is allowed to mean.

        ``Forbidden`` and ``NotFound`` are checked before the generic
        ``HTTPException`` they both subclass, or a permanent refusal carrying
        no status would fall through the 429 branch untouched.
        """
        if _is_error(error, "Forbidden"):
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="discord_forbidden",
            )
        if _is_error(error, "NotFound"):
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="discord_not_found",
            )
        if _is_error(error, "HTTPException") and getattr(error, "status", None) == 429:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
                error_code="discord_rate_limited",
                retry_after_ms=_retry_after_ms(error),
            )
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
            error_code="discord_acceptance_unknown",
        )
