"""Single-attempt Feishu Adapter for persistent Outbound Delivery.

The Delivery Pump owns ordering and retry policy (ADR 0060/0063).  This Adapter
performs one ``im.v1.message.create`` call and classifies only the outcome of
that call; it never dispatches conversational work, sleeps, retries, chunks
text, edits a placeholder, or sends media.

The legacy ``FeishuChannel._send_text_sync`` did the opposite -- it retried
three times internally on transport errors -- which is unsafe here: a retried
send whose first attempt actually reached Feishu produces a duplicate reply
that nothing upstream can see or account for.  Transport ambiguity must
surface as ``ACCEPTANCE_UNKNOWN`` and let the pump decide.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import math
import re
from typing import Any, Mapping

from . import reply_target
from .delivery import (
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from .reply_target import InvalidReplyTarget


_MAX_MESSAGE_ID_CHARS = 128
_MAX_RETRY_AFTER_MS = 7 * 24 * 60 * 60 * 1_000
# Feishu bounds the request-dedup `uuid` at 50 characters.
_MAX_UUID_CHARS = 50

# Feishu addresses a send by one of these identifier kinds.  A bare identifier
# string is not self-describing, so the immutable Reply Target must say which.
_RECEIVE_ID_TYPES = frozenset({"chat_id", "open_id", "user_id", "union_id", "email"})

# A structured Feishu response (one that carries a numeric `code`) means the
# HTTP call completed and the provider answered.  A non-zero code is therefore
# proof of NON-acceptance, not ambiguity -- only a transport failure is
# genuinely ambiguous.  So the default for an unrecognized code is
# `REJECTED_PERMANENT`: it records the failure without claiming an ambiguity
# that would block the Reply Target forever under the ADR 0063 barrier.
#
# Only codes that are both provably transient and provably non-accepted may be
# retried, because a wrong entry here duplicates a delivered reply. The set is
# deliberately small; adding to it requires evidence from Feishu's error table,
# and an omission is safe (it degrades to a recorded permanent failure).
_RETRYABLE_CODES = frozenset(
    {
        99991400,  # app request frequency limited
        230020,  # message send frequency limited
    }
)


class _InvalidFeishuDelivery(InvalidReplyTarget):
    """A target that is well formed in general but not addressable on Feishu.

    Feishu needs a ``destination_kind`` naming which identifier space the
    destination belongs to, and bounds the idempotency key it will accept.
    Neither is a common reply-target field, so both are checked here.
    """


def _bounded_message_id(value: object) -> str | None:
    if value is None:
        return None
    bounded = str(value)[:_MAX_MESSAGE_ID_CHARS]
    return bounded or None


def _retry_after_ms(response: object) -> int | None:
    """Read a provider-supplied wait hint, when one is present and sane."""

    for attribute in ("retry_after", "retry_after_ms"):
        value = getattr(response, attribute, None)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        seconds = float(value) if attribute == "retry_after" else float(value) / 1000.0
        if not math.isfinite(seconds) or seconds < 0:
            continue
        return min(_MAX_RETRY_AFTER_MS, int(math.ceil(seconds * 1_000)))
    return None


_WORD_JOINER = "\u2060"
_AT_ELEMENT = re.compile(r"<(?=\s*at)", re.IGNORECASE)


def _neutralise_at_elements(text: str) -> str:
    """*text* with a word joiner after every ``<`` that opens an ``<at`` element.

    Feishu reads ``<at user_id="…">`` in a ``text`` message as a mention, and
    ``user_id="all"`` as one for the whole chat. The joiner (U+2060) is
    invisible, so the text displays unchanged and names nobody. Matching
    ignores case and whitespace between ``<`` and ``at``; a ``<`` already
    followed by a joiner is left alone.

    Args:
        text: The text to send, as written.

    Returns:
        The text with each such ``<`` followed by U+2060.
    """
    return _AT_ELEMENT.sub("<" + _WORD_JOINER, text)


def _create_message_arguments(request: DeliveryAttemptRequest) -> dict[str, Any]:
    target = reply_target.read(request, adapter="feishu")
    destination_id = target["destination_id"]
    # Absent `destination_kind` means the Reply Target predates the Feishu
    # cutover; defaulting to chat_id keeps the historical shape addressable.
    receive_id_type = target.get("destination_kind") or "chat_id"
    if receive_id_type not in _RECEIVE_ID_TYPES:
        raise _InvalidFeishuDelivery("reply_target destination_kind is unsupported")
    item_id = request.item_id
    if not isinstance(item_id, str) or not item_id or len(item_id) > _MAX_UUID_CHARS:
        raise _InvalidFeishuDelivery("Delivery Item ID is unusable as a provider uuid")
    return {
        "receive_id_type": receive_id_type,
        "receive_id": destination_id,
        "msg_type": "text",
        "content": json.dumps(
            {"text": _neutralise_at_elements(request.text)}, ensure_ascii=False
        ),
        # ADR 0060 requires the opaque Delivery Item ID be supplied as the
        # provider idempotency key wherever the provider supports one. Feishu
        # deduplicates by `uuid` within an hour, so a retry of the SAME Item --
        # including one issued after an `acceptance_unknown` result -- cannot
        # produce a second visible message. The key is per-Item, not
        # per-Attempt, or retries would each get a fresh key and defeat it.
        "uuid": item_id,
    }


def _build_create_request(arguments: Mapping[str, Any]) -> Any:
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

    body = (
        CreateMessageRequestBody.builder()
        .receive_id(arguments["receive_id"])
        .msg_type(arguments["msg_type"])
        .content(arguments["content"])
    )
    # Older lark-oapi builds predate the dedup field. Losing idempotency is
    # recoverable; refusing to deliver at all is not, so degrade rather than
    # fail -- but never silently drop the key when the SDK does support it.
    if hasattr(body, "uuid"):
        body = body.uuid(arguments["uuid"])
    return (
        CreateMessageRequest.builder()
        .receive_id_type(arguments["receive_id_type"])
        .request_body(body.build())
        .build()
    )


class FeishuDeliveryAdapter:
    """Perform exactly one Feishu text Delivery Attempt.

    The text is sent with every ``<at`` element broken by a word joiner, so
    Feishu displays it as written and notifies nobody it names.
    """

    def __init__(self, client: Any, *, request_builder: Any = None) -> None:
        self._client = client
        self._request_builder = request_builder or _build_create_request

    async def __call__(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        return await self.attempt(request)

    async def attempt(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        try:
            arguments = _create_message_arguments(request)
            create_request = self._request_builder(arguments)
        except InvalidReplyTarget:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="feishu_invalid_delivery",
                provider_evidence=None,
                retry_after_ms=None,
            )
        except Exception:
            # A missing or incompatible SDK cannot have reached the provider.
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="feishu_client_unavailable",
                provider_evidence=None,
                retry_after_ms=None,
            )

        try:
            # Resolving the SDK method and handing it to the executor both
            # happen strictly BEFORE any socket work. A missing client attribute
            # or an already-shut-down executor therefore cannot have reached
            # Feishu, and must not be reported as ambiguous: `unknown` would
            # halt the ADR 0063 Reply Target barrier and block every later reply
            # to this destination over a purely local fault.
            send = self._client.im.v1.message.create
            loop = asyncio.get_running_loop()
            worker = loop.run_in_executor(None, send, create_request)
        except Exception:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="feishu_client_unavailable",
                provider_evidence=None,
                retry_after_ms=None,
            )

        # The lark SDK is synchronous, so it runs off the Pump's event loop.
        # Cancelling an executor future does not stop the blocking call. Keep
        # waiting through every cancellation so the Pump cannot release the
        # Reply Target barrier until the provider thread has really stopped.
        cancelled: asyncio.CancelledError | None = None
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError as error:
                cancelled = cancelled or error
            except Exception:
                break

        if cancelled is not None:
            if not worker.cancelled():
                with suppress(Exception):
                    worker.exception()
            raise cancelled

        try:
            response = worker.result()
        except Exception:
            # Timeouts, SSL and connection errors may have crossed the provider
            # acceptance seam.  The legacy path retried here; that is exactly
            # what produces invisible duplicate replies.
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
                error_code="feishu_acceptance_unknown",
                provider_evidence=None,
                retry_after_ms=None,
            )

        return self._classify(response)

    def _classify(self, response: object) -> DeliveryAdapterResult:
        succeeded = getattr(response, "success", None)
        if callable(succeeded) and succeeded():
            data = getattr(response, "data", None)
            message_id = _bounded_message_id(getattr(data, "message_id", None))
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.ACCEPTED,
                error_code=None,
                provider_evidence={"message_id": message_id} if message_id else None,
                retry_after_ms=None,
            )

        code = getattr(response, "code", None)
        if isinstance(code, bool) or not isinstance(code, int) or code == 0:
            # Either there is no readable code, or the response is internally
            # contradictory (`success()` false with the success code 0). Neither
            # proves the provider refused, so ambiguity is the honest answer.
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
                error_code="feishu_unclassified_response",
                provider_evidence=None,
                retry_after_ms=None,
            )
        if code in _RETRYABLE_CODES:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
                error_code="feishu_rate_limited",
                provider_evidence={"code": code},
                retry_after_ms=_retry_after_ms(response),
            )
        # Any other readable non-zero code: the provider answered and refused,
        # so this is proof of non-acceptance rather than ambiguity.  Recording
        # it as permanent keeps an audit trail and releases the Reply Target
        # barrier; classifying it `unknown` instead would stall every later
        # reply to this destination with no operator recourse.
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
            error_code="feishu_rejected",
            provider_evidence={"code": code},
            retry_after_ms=None,
        )


__all__ = ["FeishuDeliveryAdapter"]
