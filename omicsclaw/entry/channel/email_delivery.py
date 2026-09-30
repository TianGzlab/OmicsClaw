"""Single-attempt SMTP Adapter for outbound Delivery.

The pump owns ordering and retry policy. This Adapter builds one message,
performs one ``sendmail`` and classifies only the outcome of that call; it
never dispatches conversational work, sleeps, retries, chunks text, or sends
attachments.

**Nothing here is ever retryable, and that is a property of SMTP rather than
a precaution.** The pump retries only an outcome that carries evidence of
*when* to come back, and SMTP has no such thing: a server that is busy says
so with a 4xx and names no interval. So a refusal the server spelled out is
permanent, and everything ambiguous — a dropped connection, a timeout, a
4xx that may have been raised after the message was already queued — is
reported as unknown and left alone. Resending an unknown would put a second
copy of an answer in somebody's inbox, where it stays.

**The classification is by exception type, not by string.** The path this
replaces searched the exception's *message* for ``"550"`` and ``"auth"``,
which made a server that words its errors differently look like a transport
failure, and a transport failure whose message happened to contain "auth"
look permanent.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Callable

from . import reply_target
from .delivery import (
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from .reply_target import InvalidReplyTarget

__all__ = ["EmailDeliveryAdapter", "SmtpSettings", "build_reply"]


@dataclass(frozen=True, slots=True)
class SmtpSettings:
    """Everything one SMTP send needs, and nothing about receiving mail."""

    host: str
    port: int
    username: str
    password: str
    from_address: str
    starttls: bool = True
    subject_prefix: str = "Re: "
    timeout_s: float = 30.0


PERMANENT_ERRORS: tuple[type[BaseException], ...] = (
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPNotSupportedError,
)
"""Failures the server named. Retrying changes nothing, and the answer
itself is proof the message was not accepted."""


def _subject(prefix: str, original: object) -> str:
    text = str(original or "").strip()
    if not text:
        return "OmicsClaw Reply"
    return text if text.lower().startswith("re:") else f"{prefix}{text}"


def build_reply(
    settings: SmtpSettings,
    request: DeliveryAttemptRequest,
) -> tuple[str, EmailMessage]:
    """The recipient and the message to send them.

    Plain text only. This layer performs no Markdown-to-HTML conversion, so
    an HTML alternative would carry the same characters into a context that
    collapses their line breaks — worse than the text it was made from.

    ``In-Reply-To`` and ``References`` are set when the target names the
    message being answered, which is what makes a mail client thread the
    conversation rather than start a new one per reply.
    """
    target = reply_target.read(request, adapter="email")
    to_address = target["destination_id"]
    message = EmailMessage()
    message["Subject"] = _subject(settings.subject_prefix, target.get("subject"))
    message["From"] = settings.from_address
    message["To"] = to_address
    original_id = target.get("original_message_id")
    if isinstance(original_id, str) and original_id:
        message["In-Reply-To"] = original_id
        references = str(target.get("references") or "").strip()
        message["References"] = f"{references} {original_id}".strip()
    message.set_content(request.text)
    return to_address, message


def _send(settings: SmtpSettings, to_address: str, message: EmailMessage) -> None:
    """One blocking SMTP conversation. Called on a worker thread."""

    server: smtplib.SMTP | None = None
    try:
        if settings.starttls:
            server = smtplib.SMTP(
                settings.host, settings.port, timeout=settings.timeout_s
            )
            server.starttls(context=ssl.create_default_context())
        else:
            server = smtplib.SMTP_SSL(
                settings.host,
                settings.port,
                context=ssl.create_default_context(),
                timeout=settings.timeout_s,
            )
        server.login(settings.username, settings.password)
        server.sendmail(settings.from_address, [to_address], message.as_string())
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                # Quitting after the message was handed over changes nothing
                # about whether it was accepted.
                pass


class EmailDeliveryAdapter:
    """Perform exactly one SMTP Delivery Attempt.

    *send* is injected so a test can describe a refusing server without one;
    production uses the module's own blocking sender, run on a worker thread
    because ``smtplib`` has no asynchronous form.
    """

    def __init__(
        self,
        settings: SmtpSettings,
        send: Callable[[SmtpSettings, str, EmailMessage], None] | None = None,
    ) -> None:
        self._settings = settings
        self._send = send or _send

    async def __call__(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        return await self.attempt(request)

    async def attempt(
        self, request: DeliveryAttemptRequest
    ) -> DeliveryAdapterResult:
        try:
            to_address, message = build_reply(self._settings, request)
        except InvalidReplyTarget:
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="email_invalid_delivery",
            )

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, self._send, self._settings, to_address, message
            )
        except Exception as error:
            return self._classify(error)

        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTED,
            provider_evidence=_evidence(message),
        )

    def _classify(self, error: BaseException) -> DeliveryAdapterResult:
        """What one failed conversation is allowed to mean. Never retryable."""

        if isinstance(error, PERMANENT_ERRORS):
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                error_code="email_rejected",
                provider_evidence={"error": type(error).__name__},
            )
        if isinstance(error, smtplib.SMTPResponseException):
            code = getattr(error, "smtp_code", 0)
            if isinstance(code, int) and 500 <= code < 600:
                return DeliveryAdapterResult(
                    outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
                    error_code="email_rejected",
                    provider_evidence={"code": code},
                )
            # A 4xx may have been raised after the server took the message,
            # so it is ambiguous rather than a refusal — and SMTP names no
            # interval, so it is not retryable either.
            return DeliveryAdapterResult(
                outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
                error_code="email_acceptance_unknown",
                provider_evidence={"code": code} if code else None,
            )
        return DeliveryAdapterResult(
            outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
            error_code="email_acceptance_unknown",
        )


def _evidence(message: EmailMessage) -> dict[str, Any] | None:
    message_id = message.get("Message-ID")
    return {"message_id": str(message_id)} if message_id else None
