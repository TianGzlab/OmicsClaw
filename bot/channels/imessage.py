"""
iMessage channel implementation for OmicsClaw using imsg JSON-RPC.

Receives and sends iMessages via the `imsg` CLI tool over JSON-RPC (stdio).
macOS only — requires a signed-in Apple ID with Messages.app.

Prerequisites:
    macOS only
    brew install imsg      # or download from https://github.com/anthropics/imsg
    # Ensure Messages.app is open and signed in

Configuration via environment variables:
    IMESSAGE_CLI_PATH       — path to imsg binary (default: imsg)
    IMESSAGE_SERVICE        — imessage | sms | auto (default: auto)
    IMESSAGE_REGION         — phone number region (default: US)
    IMESSAGE_ALLOWED_SENDERS — comma-separated allowlist (empty = all)
                               formats: +1234567890, user@icloud.com,
                                        chat_id:123, chat_guid:iMessage;-;+1234567890
    IMESSAGE_DB_PATH        — optional custom iMessage database path

References:
    - https://github.com/anthropics/imsg
    - https://support.apple.com/guide/messages/
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Channel
from .capabilities import IMESSAGE as IMESSAGE_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger(__name__)


# ── Phone/email handle normalization ────────────────────────────────


_DIGITS_RE = re.compile(r"\D")


def _normalize_handle(handle: str) -> str:
    """Normalize a phone number or email for comparison."""
    h = handle.strip().lower()
    if "@" in h:
        return h  # email: compare as-is
    digits = _DIGITS_RE.sub("", h)
    if len(digits) >= 10:
        return "+" + digits.lstrip("0") if not digits.startswith("+") else digits
    return h


# ── Config ───────────────────────────────────────────────────────────


@dataclass
class IMessageConfig(BaseChannelConfig):
    """iMessage channel configuration."""
    cli_path: str = "imsg"
    db_path: str | None = None
    service: str = "auto"     # imessage | sms | auto
    region: str = "US"
    text_chunk_limit: int = 4096


# ── JSON-RPC client (stdio) ──────────────────────────────────────────


class _ImsgRpcClient:
    """Minimal JSON-RPC client communicating with imsg via stdio."""

    def __init__(
        self,
        cli_path: str,
        db_path: str | None,
        on_notification,
    ):
        self._cli_path = cli_path
        self._db_path = db_path
        self._on_notification = on_notification
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._id_counter = 0
        self._reader_task: asyncio.Task | None = None

    async def start(self) -> None:
        args = [self._cli_path]
        if self._db_path:
            args += ["--db", self._db_path]

        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.debug(f"imsg process started (pid={self._proc.pid})")

    async def stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None

    async def request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and await the response."""
        if not self._proc:
            raise RuntimeError("imsg not running")

        self._id_counter += 1
        req_id = self._id_counter
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        line = json.dumps(payload) + "\n"

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut

        self._proc.stdin.write(line.encode())
        await self._proc.stdin.drain()

        try:
            result = await asyncio.wait_for(fut, timeout=30)
            return result
        finally:
            self._pending.pop(req_id, None)

    async def _read_loop(self) -> None:
        """Read JSON-RPC messages from imsg stdout."""
        assert self._proc is not None
        while True:
            try:
                raw = await self._proc.stdout.readline()
                if not raw:
                    logger.warning("imsg stdout closed")
                    break
                self._dispatch(raw.decode().strip())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"imsg read error: {e}")

    def _dispatch(self, line: str) -> None:
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return

        # Response to a pending request
        if "id" in msg and msg["id"] in self._pending:
            fut = self._pending[msg["id"]]
            if "error" in msg:
                fut.set_exception(RuntimeError(str(msg["error"])))
            else:
                fut.set_result(msg.get("result", {}))
            return

        # Notification (no id or id=null)
        if "method" in msg:
            try:
                self._on_notification(msg["method"], msg.get("params"))
            except Exception:
                logger.exception("imsg notification handler error")


# ── Channel ──────────────────────────────────────────────────────────


class IMessageChannel(Channel):
    """iMessage channel using imsg JSON-RPC (macOS only).

    Uses `imsg` CLI for real-time message streaming instead of polling.
    Supports iMessage and SMS dual channel (service='auto').

    ⚠️  macOS only. Requires:
        1. brew install imsg
        2. Messages.app open + Apple ID signed in
        3. Terminal app granted Full Disk Access in System Settings

    Lifecycle:
        channel = IMessageChannel(IMessageConfig())
        await channel.start()
        await channel.run()
        await channel.stop()
    """

    name = "imessage"
    capabilities = IMESSAGE_CAPS

    def __init__(self, config: IMessageConfig):
        super().__init__(config)
        self._client: _ImsgRpcClient | None = None
        self._subscription_id: int | None = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("iMessage channel requires macOS")

        cli = self.config.cli_path
        if not shutil.which(cli):
            raise RuntimeError(
                f"imsg CLI not found at '{cli}'. Install via: brew install imsg"
            )

        self._client = _ImsgRpcClient(
            cli_path=cli,
            db_path=self.config.db_path,
            on_notification=self._on_notification,
        )
        await self._client.start()

        # Subscribe to message events
        try:
            result = await self._client.request(
                "watch.subscribe",
                {"attachments": True},
            )
            self._subscription_id = result.get("subscription")
        except Exception as e:
            await self._client.stop()
            raise RuntimeError(f"imsg subscribe failed: {e}") from e

        self._running = True
        logger.info("iMessage channel started")

    async def stop(self) -> None:
        self._running = False
        if self._client and self._subscription_id is not None:
            try:
                await self._client.request(
                    "watch.unsubscribe",
                    {"subscription": self._subscription_id},
                )
            except Exception:
                pass
        if self._client:
            await self._client.stop()
            self._client = None
        logger.info("iMessage channel stopped")

    # ── Notifications ─────────────────────────────────────────────────

    def _on_notification(self, method: str, params: dict | None) -> None:
        if method == "message":
            asyncio.create_task(self._handle_message(params or {}))
        elif method == "error":
            logger.error(f"imsg error notification: {params}")

    async def _handle_message(self, params: dict) -> None:
        """Process an incoming iMessage notification."""
        message = params.get("message", {})
        if not message:
            return
        if message.get("is_from_me"):
            return

        sender = message.get("sender", "").strip()
        if not sender:
            return

        # Allow-list check
        if not self._is_sender_allowed(
            sender,
            chat_id=message.get("chat_id"),
            chat_guid=message.get("chat_guid"),
        ):
            return

        if not self.check_rate_limit(sender):
            return

        text = message.get("text", "").strip()

        # Attachments
        annotations: list[str] = []
        media_paths: list[str] = []
        _VOICE_EXTS = {".caf", ".m4a", ".aac", ".ogg", ".opus", ".mp3", ".amr"}
        for att in (message.get("attachments") or []):
            file_path = att if isinstance(att, str) else att.get("path", "")
            if not file_path:
                annotations.append("[附件: 路径缺失]")
                continue
            att_path = Path(file_path)
            is_voice = att_path.suffix.lower() in _VOICE_EXTS
            label = "语音" if is_voice else "附件"
            if att_path.exists():
                try:
                    dst = Path(f"/tmp/imsg_{att_path.name}")
                    shutil.copy2(str(att_path), str(dst))
                    media_paths.append(str(dst))
                    annotations.append(f"[{label}: {dst.name}]")
                except Exception as e:
                    annotations.append(f"[{label}: {att_path.name} (复制失败)]")
            else:
                annotations.append(f"[{label}: {file_path} (文件不存在)]")

        if not text and not annotations:
            return

        full_text = text
        if annotations:
            full_text = (text + "\n" + "\n".join(annotations)).strip()

        is_group = message.get("is_group", False)
        chat_id = str(message.get("chat_id", sender))

        meta = {
            "chat_id": message.get("chat_id"),
            "chat_guid": message.get("chat_guid"),
            "is_group": is_group,
            "chat_name": message.get("chat_name"),
        }

        try:
            ts_raw = message.get("created_at")
            ts = datetime.fromisoformat(ts_raw) if ts_raw else datetime.now()
        except Exception:
            ts = datetime.now()

        logger.info(f"iMessage from {sender}: {full_text[:80]}")
        asyncio.create_task(self._handle_llm(chat_id, sender, full_text, meta))

    async def _handle_llm(
        self, chat_id: str, user_id: str, content: str, metadata: dict
    ) -> None:
        try:
            reply = await self.process_message(
                chat_id, user_id, content,
                platform="imessage",
                metadata=metadata,
            )
            if reply:
                await self.send(chat_id, reply, metadata=metadata)
        except Exception as e:
            logger.error(f"iMessage LLM error: {e}", exc_info=True)

    # ── Allow-list ────────────────────────────────────────────────────

    def _is_sender_allowed(
        self,
        sender: str,
        chat_id: int | None = None,
        chat_guid: str | None = None,
    ) -> bool:
        """Check sender against the allow-list.

        Supports:
        - Empty list → allow all
        - ``*`` → allow all
        - ``chat_id:123`` → match by integer chat ID
        - ``chat_guid:iMessage;-;+1234567890`` → match by chat GUID
        - Phone number (normalized, e.g. +16505551234)
        - Email address (user@icloud.com)
        """
        allowed = self.config.allowed_senders
        if not allowed:
            return True
        if "*" in allowed:
            return True

        sender_norm = _normalize_handle(sender)
        for entry in allowed:
            entry = entry.strip()
            if not entry:
                continue
            lower = entry.lower()
            if lower.startswith("chat_id:") and chat_id is not None:
                try:
                    if int(entry.split(":", 1)[1].strip()) == chat_id:
                        return True
                except ValueError:
                    pass
                continue
            if lower.startswith("chat_guid:") and chat_guid:
                if entry.split(":", 1)[1].strip() == chat_guid:
                    return True
                continue
            if _normalize_handle(entry) == sender_norm:
                return True
        return False

    # ── Send ─────────────────────────────────────────────────────────

    def _resolve_target(self, chat_id: str, metadata: dict | None) -> dict:
        """Build the send target params from metadata or chat_id string."""
        meta = metadata or {}
        for key in ("chat_id", "chat_guid", "chat_identifier"):
            if meta.get(key):
                return {key: meta[key]}
        return {"to": chat_id}

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        if not self._client:
            raise RuntimeError("iMessage client not running")
        params: dict[str, Any] = {
            "text": raw_text,  # plain text only
            "service": self.config.service,
            "region": self.config.region,
        }
        params.update(self._resolve_target(chat_id, metadata))
        await self._client.request("send", params)

    def _format_chunk(self, text: str) -> str:
        """iMessage is plain-text only."""
        return text

    # ── Media send ───────────────────────────────────────────────────

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not self._client:
            return False
        try:
            params: dict[str, Any] = {
                "file": file_path,
                "service": self.config.service,
                "region": self.config.region,
            }
            if caption:
                params["text"] = caption
            params.update(self._resolve_target(chat_id, metadata))
            await self._client.request("send", params)
            return True
        except Exception as e:
            logger.error(f"iMessage media send error: {e}")
            return False
