"""
Email channel implementation for OmicsClaw using standard IMAP + SMTP.

Polls an IMAP mailbox for new messages and replies via SMTP.
Supports Gmail (App Password), Outlook, and any IMAP/SMTP server.
All processing uses stdlib (imaplib, smtplib, email) — no extra deps.

Configuration via environment variables:
    EMAIL_IMAP_HOST         — IMAP server (e.g. imap.gmail.com)
    EMAIL_IMAP_PORT         — IMAP port (default: 993)
    EMAIL_IMAP_USERNAME     — IMAP login username / email address
    EMAIL_IMAP_PASSWORD     — IMAP password or App Password
    EMAIL_IMAP_MAILBOX      — Mailbox to monitor (default: INBOX)
    EMAIL_IMAP_USE_SSL      — Use SSL (default: 1)
    EMAIL_SMTP_HOST         — SMTP server (e.g. smtp.gmail.com)
    EMAIL_SMTP_PORT         — SMTP port (default: 587)
    EMAIL_SMTP_USERNAME     — SMTP login username
    EMAIL_SMTP_PASSWORD     — SMTP password or App Password
    EMAIL_SMTP_STARTTLS     — Use STARTTLS (default: 1, port 587)
    EMAIL_FROM_ADDRESS      — Sender display address (defaults to smtp_username)
    EMAIL_POLL_INTERVAL     — Seconds between IMAP polls (default: 30)
    EMAIL_MARK_SEEN         — Mark emails as read after processing (default: 1)
    EMAIL_ALLOWED_SENDERS   — Comma-separated email addresses (empty = all)

References:
    - https://docs.python.org/3/library/imaplib.html
    - https://docs.python.org/3/library/smtplib.html
"""

from __future__ import annotations

import asyncio
import contextlib
import email as email_lib
import email.utils
import html
import imaplib
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email import encoders
from email.header import decode_header, make_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from .base import Channel
from .capabilities import EMAIL as EMAIL_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger(__name__)

_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20 MB


# ── Helpers ──────────────────────────────────────────────────────────


def _decode_hdr(raw: str) -> str:
    """Decode a RFC2047-encoded email header value."""
    try:
        return str(make_header(decode_header(raw))) if raw else ""
    except Exception:
        return raw or ""


def _strip_html(text: str) -> str:
    """Convert basic HTML to plain text."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


# ── Config ───────────────────────────────────────────────────────────


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
    smtp_starttls: bool = True   # True=STARTTLS (587), False=implicit SSL (465)
    from_address: str = ""
    # Behavior
    poll_interval: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    text_chunk_limit: int = 4096


# ── Channel ──────────────────────────────────────────────────────────


class EmailChannel(Channel):
    """Email channel using IMAP polling + SMTP sending.

    Works with Gmail (App Password), Outlook, and any standard IMAP/SMTP server.
    No extra Python dependencies — uses only stdlib.

    Lifecycle:
        channel = EmailChannel(config)
        await channel.start()    # connect IMAP, start polling task
        await channel.run()      # blocks
        await channel.stop()     # cleanup
    """

    name = "email"
    capabilities = EMAIL_CAPS

    def __init__(self, config: EmailConfig):
        super().__init__(config)
        self._imap: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None
        self._poll_task: asyncio.Task | None = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        cfg = self.config
        if not cfg.imap_host or not cfg.imap_username:
            raise RuntimeError("EMAIL_IMAP_HOST and EMAIL_IMAP_USERNAME are required")
        if not cfg.smtp_host or not cfg.smtp_username:
            raise RuntimeError("EMAIL_SMTP_HOST and EMAIL_SMTP_USERNAME are required")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connect_imap)
        self._running = True

        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"Email channel started "
            f"(IMAP: {cfg.imap_host}, poll every {cfg.poll_interval}s)"
        )

    async def stop(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._imap:
            try:
                self._imap.close()
                self._imap.logout()
            except Exception:
                pass
            self._imap = None
        logger.info("Email channel stopped")

    # ── IMAP connection ──────────────────────────────────────────────

    def _connect_imap(self) -> None:
        cfg = self.config
        try:
            if cfg.imap_use_ssl:
                self._imap = imaplib.IMAP4_SSL(
                    cfg.imap_host, cfg.imap_port,
                    ssl_context=ssl.create_default_context(),
                )
            else:
                self._imap = imaplib.IMAP4(cfg.imap_host, cfg.imap_port)
            self._imap.login(cfg.imap_username, cfg.imap_password)
            self._imap.select(cfg.imap_mailbox)
            logger.debug(f"IMAP connected: {cfg.imap_host}:{cfg.imap_port}")
        except Exception as e:
            raise RuntimeError(f"IMAP connection failed: {e}") from e

    def _reconnect_imap(self) -> None:
        """Reconnect IMAP if the connection was dropped."""
        try:
            if self._imap:
                self._imap.noop()
                return
        except Exception:
            pass
        self._connect_imap()

    # ── Polling loop ─────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Repeatedly poll for new emails at configured interval."""
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Email poll error: {e}", exc_info=True)
            await asyncio.sleep(self.config.poll_interval)

    async def _poll_once(self) -> None:
        """Fetch and process unseen emails."""
        loop = asyncio.get_running_loop()
        messages = await loop.run_in_executor(None, self._fetch_unseen)
        for m in messages:
            await self._process_email(m)

    def _fetch_unseen(self) -> list[dict]:
        """Fetch up to 20 UNSEEN emails from the IMAP server."""
        self._reconnect_imap()
        results = []
        try:
            status, data = self._imap.search(None, "UNSEEN")
            if status != "OK":
                return []

            for mid in data[0].split()[-20:]:   # Process at most 20 per cycle
                status, msg_data = self._imap.fetch(mid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue

                msg = email_lib.message_from_bytes(msg_data[0][1])
                from_name, from_addr = parseaddr(msg.get("From", ""))

                body = self._extract_body(msg)
                if len(body) > self.config.max_body_chars:
                    body = body[: self.config.max_body_chars] + "\n[...截断]"

                # Collect attachments
                attachments: list[dict] = []
                if msg.is_multipart():
                    for part in msg.walk():
                        content_disp = part.get("Content-Disposition") or ""
                        content_type = part.get_content_type() or ""
                        is_attach = "attachment" in content_disp.lower()
                        is_inline_img = (
                            "inline" in content_disp.lower()
                            and content_type.startswith("image/")
                        )
                        if is_attach or is_inline_img:
                            filename = _decode_hdr(part.get_filename() or "attachment")
                            payload = part.get_payload(decode=True)
                            if payload:
                                if len(payload) > _MAX_ATTACHMENT_BYTES:
                                    attachments.append({
                                        "annotation": f"[附件: {filename} (过大, {len(payload)} bytes)]"
                                    })
                                else:
                                    tmp_path = Path(f"/tmp/email_{mid.decode()}_{filename}")
                                    tmp_path.write_bytes(payload)
                                    lbl = "inline-image" if is_inline_img else "附件"
                                    attachments.append({
                                        "path": str(tmp_path),
                                        "annotation": f"[{lbl}: {tmp_path.name}]",
                                    })

                if self.config.mark_seen:
                    self._imap.store(mid, "+FLAGS", "\\Seen")

                results.append({
                    "from_addr": from_addr,
                    "from_name": _decode_hdr(from_name),
                    "subject": _decode_hdr(msg.get("Subject", "")),
                    "body": body,
                    "message_id": msg.get("Message-ID", ""),
                    "date": msg.get("Date", ""),
                    "references": msg.get("References", ""),
                    "attachments": attachments,
                })
        except Exception as e:
            logger.error(f"IMAP fetch error: {e}", exc_info=True)
        return results

    def _extract_body(self, msg) -> str:
        """Extract plain-text body from an email message."""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return self._decode_payload(part)
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    return _strip_html(self._decode_payload(part))
            return "[无文本正文]"
        text = self._decode_payload(msg)
        return _strip_html(text) if msg.get_content_type() == "text/html" else text

    @staticmethod
    def _decode_payload(part) -> str:
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    # ── Message processing ───────────────────────────────────────────

    async def _process_email(self, m: dict) -> None:
        """Send an email through the LLM pipeline."""
        # Allowlist check
        allowed = self.config.allowed_senders
        if allowed and m["from_addr"] not in allowed:
            logger.debug(f"Email ignored (not in allowlist): {m['from_addr']}")
            return

        if not self.check_rate_limit(m["from_addr"]):
            return

        subject = m["subject"]
        text = f"[邮件] 主题: {subject}\n\n{m['body']}" if subject else m["body"]

        try:
            ts = email.utils.parsedate_to_datetime(m["date"])
        except Exception:
            ts = datetime.now()

        meta = {
            "chat_id": m["from_addr"],
            "subject": subject,
            "original_message_id": m["message_id"],
            "references": m["references"],
            "backend": "email",
        }

        logger.info(f"Email from {m['from_addr']}: {subject[:60]}")
        asyncio.create_task(self._handle_llm(m["from_addr"], text, meta))

    async def _handle_llm(self, from_addr: str, content: str, metadata: dict) -> None:
        """Process the email through LLM and reply."""
        try:
            reply = await self.process_message(
                from_addr, from_addr, content,
                platform="email",
                metadata=metadata,
            )
            if reply:
                await self.send(from_addr, reply, metadata=metadata)
        except Exception as e:
            logger.error(f"Email LLM error: {e}", exc_info=True)

    # ── Send ─────────────────────────────────────────────────────────

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        """Send an email reply via SMTP (HTML + plain text dual-format)."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, self._smtp_send_html, chat_id, formatted_text, raw_text, metadata or {}
            )
        except Exception as e:
            err = str(e).lower()
            if any(c in err for c in ("550", "553", "554", "auth", "rejected")):
                raise
            logger.warning(f"HTML email failed ({e}), falling back to plain text")
            await loop.run_in_executor(
                None, self._smtp_send_plain, chat_id, raw_text, metadata or {}
            )

    @contextlib.contextmanager
    def _smtp_connect(self):
        """Open an SMTP connection (STARTTLS or implicit SSL)."""
        cfg = self.config
        srv = None
        try:
            if cfg.smtp_starttls:
                srv = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30)
                srv.starttls()
            else:
                srv = smtplib.SMTP_SSL(
                    cfg.smtp_host, cfg.smtp_port,
                    context=ssl.create_default_context(),
                    timeout=30,
                )
            srv.login(cfg.smtp_username, cfg.smtp_password)
            yield srv
        finally:
            if srv is not None:
                with contextlib.suppress(Exception):
                    srv.quit()

    def _build_subject(self, orig_subject: str) -> str:
        cfg = self.config
        if orig_subject and not orig_subject.lower().startswith("re:"):
            return f"{cfg.subject_prefix}{orig_subject}"
        return orig_subject or "OmicsClaw Reply"

    def _set_reply_headers(self, msg, meta: dict) -> None:
        orig_id = meta.get("original_message_id", "")
        if orig_id:
            msg["In-Reply-To"] = orig_id
            msg["References"] = f"{meta.get('references', '')} {orig_id}".strip()

    def _smtp_send_plain(self, to: str, content: str, meta: dict) -> None:
        from email.message import EmailMessage
        cfg = self.config
        from_addr = cfg.from_address or cfg.smtp_username
        msg = EmailMessage()
        msg["Subject"] = self._build_subject(meta.get("subject", ""))
        msg["From"] = from_addr
        msg["To"] = to
        self._set_reply_headers(msg, meta)
        msg.set_content(content)
        with self._smtp_connect() as srv:
            srv.sendmail(from_addr, [to], msg.as_string())

    def _smtp_send_html(
        self, to: str, html_content: str, plain_content: str, meta: dict
    ) -> None:
        """Send HTML + plain text multipart email."""
        cfg = self.config
        from_addr = cfg.from_address or cfg.smtp_username
        msg = MIMEMultipart("alternative")
        msg["Subject"] = self._build_subject(meta.get("subject", ""))
        msg["From"] = from_addr
        msg["To"] = to
        self._set_reply_headers(msg, meta)
        msg.attach(MIMEText(plain_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))
        with self._smtp_connect() as srv:
            srv.sendmail(from_addr, [to], msg.as_string())

    # ── Media (attachment) ───────────────────────────────────────────

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a result file as an email attachment."""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._smtp_send_attachment,
                chat_id, file_path, caption, metadata or {}
            )
            return True
        except Exception as e:
            logger.error(f"Email attachment send error: {e}")
            return False

    def _smtp_send_attachment(
        self, to: str, file_path: str, caption: str, meta: dict
    ) -> None:
        cfg = self.config
        from_addr = cfg.from_address or cfg.smtp_username
        path = Path(file_path)

        msg = MIMEMultipart()
        msg["Subject"] = self._build_subject(meta.get("subject", ""))
        msg["From"] = from_addr
        msg["To"] = to
        self._set_reply_headers(msg, meta)

        if caption:
            msg.attach(MIMEText(caption, "plain", "utf-8"))

        part = MIMEBase("application", "octet-stream")
        part.set_payload(path.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={path.name}")
        msg.attach(part)

        with self._smtp_connect() as srv:
            srv.sendmail(from_addr, [to], msg.as_string())
