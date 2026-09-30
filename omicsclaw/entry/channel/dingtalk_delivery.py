"""Single-attempt DingTalk Adapter for outbound Delivery.

The pump owns ordering and retry policy. This Adapter performs one
``robot/oToMessages/batchSend`` call and classifies only the outcome of that
call; it never dispatches conversational work, sleeps, retries, chunks text,
or sends media.

**The response is read.** The path this replaces posted and returned, which
made every outcome — a revoked token, an unknown user, a rate limit, a
gateway timeout — look identical to a delivered message. A send nobody looks
at is not a send that succeeded; it is one whose failure is invisible.

DingTalk answers a rate limit either with HTTP 429 or with a body code whose
name says so, and both carry the evidence that nothing was delivered. Any
other answered 4xx is a refusal. A timeout, a 5xx and an exception may have
crossed the acceptance seam and are reported as unknown, because a resend
there shows a second copy of an answer somebody may already have read.
"""

from __future__ import annotations

import json
import math
from typing import Any

from . import reply_target
from .delivery import (
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from .reply_target import InvalidReplyTarget

__all__ = ["SEND_URL", "DingTalkDeliveryAdapter"]

SEND_URL = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"

_MAX_MESSAGE_ID_CHARS = 128
_MAX_RETRY_AFTER_MS = 7 * 24 * 60 * 60 * 1_000

RETRYABLE_CODES = frozenset({"requestLimit", "tooManyRequests", "rateLimit"})
"""Body codes that mean *come back later*, and nothing else does.

Deliberately a small allow-list. An omission costs one reply reported as
unknown, which the pump already handles safely; a wrong entry would declare
a delivered message undelivered and send it again.
"""


def _retry_after_ms(response: object) -> int | None:
    """The wait DingTalk asked for. ``None`` is *it did not say*, not zero."""

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


def _send_arguments(request: DeliveryAttemptRequest) -> dict[str, Any]:
    target = reply_target.read(request, adapter="dingtalk")
    robot_code = target.get("robot_code")
    if not isinstance(robot_code, str) or not robot_code:
        # ``batchSend`` names the robot that speaks; without it DingTalk has
        # no sender to attribute the message to and refuses the call.
        raise InvalidReplyTarget("reply_target has no robot_code")
    return {
        "robotCode": robot_code,
        "userIds": [target["destination_id"]],
        "msgKey": "sampleMarkdown",
        "msgParam": json.dumps(
            {"text": request.text, "title": "OmicsClaw"}, ensure_ascii=False
        ),
    }


def _body(response: object) -> dict[str, Any]:
    reader = getattr(response, "json", None)
    if not callable(reader):
        return {}
    try:
        payload = reader()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _evidence(body: dict[str, Any]) -> dict[str, Any] | None:
    ids = body.get("processQueryKey") or body.get("requestId")
    if ids is None:
        return None
    bounded = str(ids)[:_MAX_MESSAGE_ID_CHARS]
    return {"message_id": bounded} if bounded else None


class DingTalkDeliveryAdapter:
    """Perform exactly one DingTalk text Delivery Attempt.

    *token_provider* is awaited per attempt rather than a token being held,
    because the access token expires every two hours and the adapter must
    not be the reason a deployment stops answering after one of them.
    """

    def __init__(self, http_client: Any, token_provider: Any) -> None:
        self._http = http_client
        self._token_provider = token_provider

    async def __call__(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        return await self.attempt(request)

    async def attempt(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        try:
            arguments = _send_arguments(request)
        except InvalidReplyTarget:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="dingtalk_invalid_delivery",
            )

        try:
            token = await self._token_provider()
        except Exception:
            # Refreshing the token happens strictly before any send, so a
            # failure here cannot have reached DingTalk.
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="dingtalk_token_unavailable",
            )

        try:
            response = await self._http.post(
                SEND_URL,
                json=arguments,
                headers={"x-acs-dingtalk-access-token": token},
            )
        except Exception:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
                error_code="dingtalk_acceptance_unknown",
            )

        return self._classify(response)

    def _classify(self, response: object) -> DeliveryAdapterResult:
        """What one answered call is allowed to mean."""

        status = getattr(response, "status_code", None)
        body = _body(response)
        code = body.get("code")

        if status == 429 or (isinstance(code, str) and code in RETRYABLE_CODES):
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
                error_code="dingtalk_rate_limited",
                provider_evidence={"code": str(code)} if code else None,
                retry_after_ms=_retry_after_ms(response),
            )
        if isinstance(status, int) and 200 <= status < 300 and not code:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.ACCEPTED,
                provider_evidence=_evidence(body),
            )
        if isinstance(status, int) and 400 <= status < 500:
            # DingTalk answered and refused. The answer itself is proof the
            # message was not delivered, so there is nothing ambiguous here.
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="dingtalk_rejected",
                provider_evidence={"code": str(code)} if code else None,
            )
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
            error_code="dingtalk_acceptance_unknown",
            provider_evidence={"code": str(code)} if code else None,
        )
