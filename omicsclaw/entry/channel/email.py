"""
Email channel implementation for OmicsClaw using standard IMAP + SMTP.

Polls an IMAP mailbox for unseen messages and replies over SMTP. Works with
Gmail (app password), Outlook and any standard server, using only the
standard library. Both protocols are blocking, so every call is awaited back
onto the loop through an executor — there is no callback thread here and
nothing hops between loops.

**There are no groups and no mentions, so this bot has no identity.**
:attr:`~omicsclaw.entry.ingress.SenderPolicy.bot_identity` is left empty on
purpose: should a message ever arrive labelled as a group message, an empty
identity makes :meth:`~omicsclaw.entry.ingress.SenderPolicy.admits` refuse it
rather than answer it to whoever wrote it.

**Inbound attachments are not stored.** The path this replaces wrote every
attachment to ``/tmp`` under a filename taken straight from the mail's
``Content-Disposition`` header, and then nothing ever read the result: the
whole feature was a write. A header is attacker-controlled input, so a
``filename`` containing ``../`` wrote outside the directory it named. Both
problems end the same way — there is nowhere for an attachment to go in this
layer, so it is not fetched.

**Idempotency does not survive a restart, and that is known rather than
fixed.** Inbound de-duplication is the IMAP ``\\Seen`` flag plus the
runtime's own record of accepted ``Message-ID`` values, and that record lives
in this process. A crash between fetching a message and flagging it means the
message is answered again after a restart. Durable ingress is deferred for
the whole layer, not for this adapter.

Configuration via environment variables (read by ``omicsclaw/launch/``, never
here):
    EMAIL_IMAP_HOST / PORT / USERNAME / PASSWORD / MAILBOX / USE_SSL
    EMAIL_SMTP_HOST / PORT / USERNAME / PASSWORD / STARTTLS
    EMAIL_FROM_ADDRESS, EMAIL_POLL_INTERVAL, EMAIL_MARK_SEEN
    EMAIL_ALLOWED_SENDERS

References:
    - https://docs.python.org/3/library/imaplib.html
    - https://docs.python.org/3/library/smtplib.html
"""

from __future__ import annotations

import asyncio
import email as email_lib
import html
import imaplib
import logging
import re
import ssl
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.utils import parseaddr
from typing import Any

from omicsclaw.entry.ingress import (
    SenderPolicy,
    VALUE_CHAT_TYPE,
    VALUE_MENTIONS,
)

from . import reply_target
from .base import Channel
from .binding import ChannelSurfaceBinding
from .capabilities import EMAIL as EMAIL_CAPS
from .config import BaseChannelConfig
from .email_delivery import EmailDeliveryAdapter, SmtpSettings
from .runtime import TurnAcceptanceStatus

logger = logging.getLogger("omicsclaw.channel.email")

MAX_MESSAGES_PER_POLL = 20

EMAIL_TEXT_CHUNK_LIMIT = 100_000
"""Characters per outbound mail when the deployment does not say.

A real number and not the capability profile's ``0``. That zero means "no
practical limit" to a reader and *a per-chunk budget of zero* to
:func:`~omicsclaw.entry.channel.base.chunk_text`, which is one of its two
non-terminating inputs. 100,000 is a generous bound on a single mail body
and is a number the chunker can act on.
"""


# ─ Helpers ────────────────────────


def decode_header_value(raw: str) -> str:
    """Decode an RFC 2047 header value, falling back to what was sent."""
    try:
        return str(make_header(decode_header(raw))) if raw else ""
    except Exception:
        return raw or ""


def strip_html(text: str) -> str:
    """Reduce a basic HTML body to the text it is made of."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


# ─ Config ─────────────────────────


@dataclass
class EmailConfig(BaseChannelConfig):
    """Email channel configuration."""

    # IMAP (inbound)
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    # SMTP (outbound)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True  # True=STARTTLS (587), False=implicit SSL (465)
    from_address: str = ""
    # Behaviour
    poll_interval: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    text_chunk_limit: int = EMAIL_TEXT_CHUNK_LIMIT


# ─ Channel ────────────────────────


class EmailChannel(Channel):
    """Email channel using IMAP polling and SMTP sending.

    Owner mail enters the authoritative
    :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`; answers leave
    only through its delivery pump, which is what classifies whether they
    were accepted. Attachments, in both directions, are fail-closed.
    """

    name = "email"
    capabilities = EMAIL_CAPS
    authoritative_ingress = True

    def __init__(self, config: EmailConfig):
        super().__init__(config)
        self.email_config = config
        self._imap: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._account_namespace = ""

    # ─ Lifecycle ──────────────────────

    def _owner_subjects(self) -> frozenset[str]:
        """The allowlist, folded to lower case.

        An address is the identity on this channel, and the case of one is
        not part of it: a mail from ``Owner@Example.com`` is from the person
        configured as ``owner@example.com``.
        """
        return frozenset(
            str(value).strip().lower()
            for value in (self.config.allowed_senders or set())
            if str(value).strip()
        )

    def _is_owner(self, subject: str | None) -> bool:
        """Compare an address the same way the allowlist was folded."""

        return super()._is_owner(str(subject or "").lower())

    async def prepare_control_binding(self) -> ChannelSurfaceBinding:
        """Describe this mailbox's control binding before polling starts."""

        owners = self._owner_subjects()
        if not owners:
            raise RuntimeError(
                "Email authoritative ingress requires EMAIL_ALLOWED_SENDERS"
            )
        cfg = self.email_config
        if not cfg.imap_host or not cfg.imap_username:
            raise RuntimeError("EMAIL_IMAP_HOST and EMAIL_IMAP_USERNAME are required")
        if not cfg.smtp_host or not cfg.smtp_username:
            raise RuntimeError("EMAIL_SMTP_HOST and EMAIL_SMTP_USERNAME are required")

        from_address = (cfg.from_address or cfg.smtp_username).strip()
        if not from_address:
            raise RuntimeError("Email sender address is unavailable")
        self._account_namespace = from_address

        return ChannelSurfaceBinding(
            adapter="email",
            account_namespace=from_address,
            # No identity: there are no groups here, and an empty identity is
            # what makes a message labelled as one fail closed.
            sender_policy=SenderPolicy(allowed_senders=owners, bot_identity=""),
            delivery_adapter=EmailDeliveryAdapter(
                SmtpSettings(
                    host=cfg.smtp_host,
                    port=cfg.smtp_port,
                    username=cfg.smtp_username,
                    password=cfg.smtp_password,
                    from_address=from_address,
                    starttls=cfg.smtp_starttls,
                    subject_prefix=cfg.subject_prefix,
                )
            ),
            # The capability profile's ``max_text_length`` is 0 here, which
            # the chunker cannot act on; see EMAIL_TEXT_CHUNK_LIMIT.
            text_chunk_limit=cfg.text_chunk_limit or EMAIL_TEXT_CHUNK_LIMIT,
            attachment_input_enabled=False,
        )

    async def start(self) -> None:
        """Phase 2: connect IMAP and begin polling once the runtime is bound."""

        if self._control_runtime is None:
            raise RuntimeError(
                "Email requires the shared ChannelRuntime to be bound before start()"
            )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connect_imap)
        self._running = True
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="omicsclaw-email"
        )
        logger.info(
            "Email channel started (IMAP %s, poll every %ds)",
            self.email_config.imap_host,
            self.email_config.poll_interval,
        )

    async def stop(self) -> None:
        self.deactivate_ingress()
        self._running = False
        task = self._poll_task
        self._poll_task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._imap is not None:
            try:
                self._imap.close()
                self._imap.logout()
            except Exception as error:
                logger.warning("IMAP shutdown failed (%s)", type(error).__name__)
            self._imap = None
        # The shared runtime is owned and closed by the runner, not by any one
        # channel: several channels share one agent.
        self._control_runtime = None
        self._control_loop = None
        logger.info("Email channel stopped")

    # ─ IMAP connection ────────────────────

    def _connect_imap(self) -> None:
        cfg = self.email_config
        try:
            if cfg.imap_use_ssl:
                self._imap = imaplib.IMAP4_SSL(
                    cfg.imap_host,
                    cfg.imap_port,
                    ssl_context=ssl.create_default_context(),
                )
            else:
                self._imap = imaplib.IMAP4(cfg.imap_host, cfg.imap_port)
            self._imap.login(cfg.imap_username, cfg.imap_password)
            self._imap.select(cfg.imap_mailbox)
        except Exception as error:
            raise RuntimeError(
                f"IMAP connection failed ({type(error).__name__})"
            ) from None

    def _reconnect_imap(self) -> None:
        """Reconnect only when the existing connection has actually gone."""
        try:
            if self._imap is not None:
                self._imap.noop()
                return
        except Exception:
            pass
        self._connect_imap()

    # ─ Polling loop ─────────────────────

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as error:
                logger.error("Email poll failed (%s)", type(error).__name__)
            await asyncio.sleep(self.email_config.poll_interval)

    async def _poll_once(self) -> None:
        """Fetch what is unseen and hand each one to the runtime."""
        loop = asyncio.get_running_loop()
        for message in await loop.run_in_executor(None, self._fetch_unseen):
            await self._on_message(message)

    def _fetch_unseen(self) -> list[dict]:
        """Read unseen mail. Blocking, so it runs on a worker thread.

        Attachments are neither decoded nor written; see the module
        docstring. What comes back is a text body and the headers a reply
        needs, which is everything this layer can carry.
        """
        self._reconnect_imap()
        results: list[dict] = []
        try:
            status, data = self._imap.search(None, "UNSEEN")
            if status != "OK":
                return []
            for uid in data[0].split()[-MAX_MESSAGES_PER_POLL:]:
                status, payload = self._imap.fetch(uid, "(RFC822)")
                if status != "OK" or not payload or not payload[0]:
                    continue
                message = email_lib.message_from_bytes(payload[0][1])
                _name, from_address = parseaddr(message.get("From", ""))
                body = self._extract_body(message)
                if len(body) > self.email_config.max_body_chars:
                    body = body[: self.email_config.max_body_chars] + "\n[truncated]"
                if self.email_config.mark_seen:
                    self._imap.store(uid, "+FLAGS", "\\Seen")
                results.append(
                    {
                        "from_addr": from_address,
                        "subject": decode_header_value(message.get("Subject", "")),
                        "body": body,
                        "message_id": message.get("Message-ID", ""),
                        "references": message.get("References", ""),
                    }
                )
        except Exception as error:
            logger.error("IMAP fetch failed (%s)", type(error).__name__)
        return results

    def _extract_body(self, message) -> str:
        """The plain text of a mail, preferring the part that already is text."""
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain":
                    return self._decode_payload(part)
            for part in message.walk():
                if part.get_content_type() == "text/html":
                    return strip_html(self._decode_payload(part))
            return ""
        text = self._decode_payload(message)
        return (
            strip_html(text) if message.get_content_type() == "text/html" else text
        )

    @staticmethod
    def _decode_payload(part) -> str:
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    # ─ Inbound ───────────────────────

    def _reply_target(self, mail: dict) -> dict[str, Any]:
        """Where a reply goes, and what makes a mail client thread it."""

        return reply_target.build(
            "email",
            self._account_namespace,
            mail["from_addr"],
            subject=mail.get("subject") or None,
            original_message_id=mail.get("message_id") or None,
            references=mail.get("references") or None,
        )

    async def _on_message(self, mail: dict) -> None:
        """Normalise one mail into the authoritative runtime.

        Performs no model work and sends no reply: the answer is delivered by
        the runtime's pump once the exchange has run.
        """

        if not self.ingress_active:
            return
        from_address = str(mail.get("from_addr") or "").strip()
        message_id = str(mail.get("message_id") or "").strip()
        if not from_address or not message_id:
            return

        # A second, redundant allowlist check. ``SenderPolicy`` at ingress is
        # the authority and applies to every adapter; this one stops the work
        # earlier. Both deny by default, so the redundancy only tightens.
        if from_address.lower() not in self._owner_subjects():
            logger.warning("Ignored a mail from an address outside the allowlist")
            return

        subject = str(mail.get("subject") or "")
        body = str(mail.get("body") or "")
        text = f"Subject: {subject}\n\n{body}" if subject else body
        if not text.strip():
            return

        if self.seen_before(message_id):
            return

        target = self._reply_target(mail)
        if body.strip().startswith("/") and await self.answer_slash_command(
            target, from_address, from_address, body.strip()
        ):
            return

        if not self.check_rate_limit(from_address):
            logger.warning("Email sender exceeded the configured rate limit")
            return

        # Length only: a mail body is the likeliest place in this repository
        # for a subject identifier to appear, and a log is the most widely
        # shared destination there is.
        logger.info("Email accepted (%d chars)", len(text))
        await self._submit_control_inbound(
            from_address=from_address,
            text=text,
            message_id=message_id,
            target=target,
        )

    async def _submit_control_inbound(
        self,
        *,
        from_address: str,
        text: str,
        message_id: str,
        target: dict[str, Any],
    ):
        """Submit one normalised mail as one exchange."""

        if self._control_runtime is None:
            raise RuntimeError("Email ChannelRuntime is not bound")
        inbound = self.inbound(
            from_address,
            from_address,
            text,
            # RFC 5322 makes Message-ID globally unique and it survives a
            # redelivery, so it is the natural idempotency key.
            source_request_id=message_id,
            reply_target=target,
            values={VALUE_CHAT_TYPE: "private", VALUE_MENTIONS: ()},
        )
        result = await self._control_runtime.submit(inbound)
        if result.acceptance.status is TurnAcceptanceStatus.REJECTED:
            # Refusals cannot answer through the pump, because no exchange was
            # accepted. The local cache is deliberately NOT updated, so a
            # redelivery of a transiently rejected mail can still land.
            logger.warning(
                "Email ingress rejected: %s", result.acceptance.code or "unspecified"
            )
            return result
        self.remember_message(message_id)
        return result
