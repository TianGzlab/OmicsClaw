"""Single-attempt Telegram Adapter for outbound Delivery.

The pump owns ordering and retry policy.  This Adapter performs one
``send_message`` call and classifies only the outcome of that call; it never
dispatches conversational work, sleeps, retries, chunks text, or sends media.

Ported for plan 0031 task D1 with the import block as the only change: the
three names it needs moved from the deleted control plane into
:mod:`omicsclaw.entry.channel.delivery`, member for member. Line 161 below is
why plan 0031 §5.3 says this file is ported rather than rebuilt — the
three-state acceptance the plan set out to design was already here.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
import math
from typing import Any, Mapping

from .delivery import (
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)


_MAX_MESSAGE_ID_CHARS = 128
_MAX_RETRY_AFTER_MS = 7 * 24 * 60 * 60 * 1_000


class _InvalidTelegramDelivery(ValueError):
    pass


@lru_cache(maxsize=1)
def _telegram_error_types() -> Mapping[str, type[BaseException]]:
    """Load the optional Telegram SDK only when an attempt raises."""

    try:
        from telegram.error import BadRequest, Forbidden, RetryAfter
    except ImportError:
        return {}
    return {
        "BadRequest": BadRequest,
        "Forbidden": Forbidden,
        "RetryAfter": RetryAfter,
    }


def _is_error(error: BaseException, class_name: str) -> bool:
    error_type = _telegram_error_types().get(class_name)
    return (error_type is not None and isinstance(error, error_type)) or type(
        error
    ).__name__ == class_name


def _retry_after_ms(error: BaseException) -> int | None:
    value = getattr(error, "retry_after", None)
    if isinstance(value, timedelta):
        seconds = value.total_seconds()
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
    else:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(_MAX_RETRY_AFTER_MS, int(math.ceil(seconds * 1_000)))


def _telegram_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise _InvalidTelegramDelivery(f"{field_name} must be a Telegram integer")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise _InvalidTelegramDelivery(
            f"{field_name} must be a Telegram integer"
        ) from exc


def _send_message_arguments(request: DeliveryAttemptRequest) -> dict[str, Any]:
    target = request.reply_target
    if not isinstance(target, Mapping):
        raise _InvalidTelegramDelivery("reply_target must be a mapping")
    if target.get("kind", "channel") != "channel":
        raise _InvalidTelegramDelivery("reply_target kind must be channel")
    if target.get("adapter", "telegram") != "telegram":
        raise _InvalidTelegramDelivery("reply_target adapter must be telegram")
    destination_id = target.get("destination_id")
    if destination_id is None:
        raise _InvalidTelegramDelivery("reply_target has no destination_id")
    if not isinstance(request.text, str) or not request.text:
        raise _InvalidTelegramDelivery("Delivery Item text must be non-empty")

    arguments: dict[str, Any] = {
        "chat_id": _telegram_integer(destination_id, "destination_id"),
        "text": request.text,
    }
    thread_id = target.get("thread_id")
    if thread_id is not None:
        arguments["message_thread_id"] = _telegram_integer(thread_id, "thread_id")
    return arguments


def _message_evidence(message: object) -> Mapping[str, Any] | None:
    message_id = getattr(message, "message_id", None)
    if isinstance(message_id, int) and not isinstance(message_id, bool):
        return {"message_id": message_id}
    if message_id is None:
        return None
    bounded = str(message_id)[:_MAX_MESSAGE_ID_CHARS]
    return {"message_id": bounded} if bounded else None


class TelegramDeliveryAdapter:
    """Perform exactly one Telegram text Delivery Attempt."""

    def __init__(self, bot: Any) -> None:
        self._bot = bot

    async def __call__(
        self,
        request: DeliveryAttemptRequest,
    ) -> DeliveryAdapterResult:
        return await self.attempt(request)

    async def attempt(
        self,
        request: DeliveryAttemptRequest,
    ) -> DeliveryAdapterResult:
        try:
            arguments = _send_message_arguments(request)
        except _InvalidTelegramDelivery:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="telegram_invalid_delivery",
                provider_evidence=None,
                retry_after_ms=None,
            )

        try:
            message = await self._bot.send_message(**arguments)
        except Exception as error:
            if _is_error(error, "RetryAfter"):
                return DeliveryAdapterResult(
                    outcome=DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
                    error_code="telegram_retry_after",
                    provider_evidence=None,
                    retry_after_ms=_retry_after_ms(error),
                )
            if _is_error(error, "BadRequest"):
                return DeliveryAdapterResult(
                    outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                    error_code="telegram_bad_request",
                    provider_evidence=None,
                    retry_after_ms=None,
                )
            if _is_error(error, "Forbidden"):
                return DeliveryAdapterResult(
                    outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                    error_code="telegram_forbidden",
                    provider_evidence=None,
                    retry_after_ms=None,
                )
            # Timeouts, NetworkError and every other exception may have crossed
            # the provider acceptance seam.  The Pump must not retry blindly.
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
                error_code="telegram_acceptance_unknown",
                provider_evidence=None,
                retry_after_ms=None,
            )

        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTED,
            error_code=None,
            provider_evidence=_message_evidence(message),
            retry_after_ms=None,
        )


__all__ = ["TelegramDeliveryAdapter"]
