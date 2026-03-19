"""
QQ channel implementation for OmicsClaw using qq-botpy SDK.

Supports C2C (direct messages) and group messages via QQ Bot Gateway
(WebSocket, no public IP needed).

Prerequisites:
    pip install qq-botpy

Configuration via environment variables:
    QQ_APP_ID       — Bot AppID from QQ Open Platform
    QQ_APP_SECRET   — Bot AppSecret

References:
    - https://q.qq.com/doc/      (QQ Open Platform)
    - https://github.com/tencent-connect/botpy
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .base import Channel
from .capabilities import QQ as QQ_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger(__name__)


# ── Markdown → plain text helper ─────────────────────────────────────


def _strip_markdown(text: str) -> str:
    """Strip Markdown to plain text for QQ (which does not render Markdown)."""
    text = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip("`").strip(), text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1(\2)", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\-\*]\s+", "• ", text, flags=re.MULTILINE)
    return text


# ── Config ───────────────────────────────────────────────────────────


@dataclass
class QQConfig(BaseChannelConfig):
    """QQ Bot channel configuration."""
    app_id: str = ""
    app_secret: str = ""
    text_chunk_limit: int = 4096


# ── Channel ──────────────────────────────────────────────────────────


class QQChannel(Channel):
    """QQ channel using qq-botpy SDK.

    Connects via WebSocket to the QQ Bot Gateway — no public IP needed.
    Supports:
    - C2C (direct) messages
    - Group @mention messages
    - Image/video/audio media (URL-based; local files → text hint)

    Lifecycle:
        channel = QQChannel(QQConfig(app_id=..., app_secret=...))
        await channel.start()
        await channel.run()
        await channel.stop()
    """

    name = "qq"
    capabilities = QQ_CAPS

    # qq-botpy file_type constants: 1=image, 2=video, 3=audio
    _FILE_TYPE_MAP = {
        ".jpg": 1, ".jpeg": 1, ".png": 1, ".gif": 1,
        ".webp": 1, ".bmp": 1,
        ".mp4": 2, ".mov": 2, ".avi": 2,
        ".mp3": 3, ".ogg": 3, ".m4a": 3, ".wav": 3,
    }

    def __init__(self, config: QQConfig):
        super().__init__(config)
        self._client = None
        self._bot_task: asyncio.Task | None = None
        self._processed_ids: deque = deque(maxlen=1000)
        # msg_id → next msg_seq counter (QQ requires monotonically-increasing seq)
        self._msg_seq: dict[str, int] = {}
        self._msg_seq_order: deque = deque(maxlen=500)
        self._msg_seq_ids: set[str] = set()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            import botpy  # noqa: F401
        except ImportError:
            raise RuntimeError("qq-botpy not installed. Run: pip install qq-botpy")

        if not self.config.app_id or not self.config.app_secret:
            raise RuntimeError("QQ_APP_ID and QQ_APP_SECRET are required")

        BotClass = self._make_bot_class()
        self._client = BotClass()
        self._running = True
        self._bot_task = asyncio.create_task(self._run_bot())
        logger.info("QQ channel starting (Gateway WebSocket)...")

    async def stop(self) -> None:
        self._running = False
        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
        self._client = None
        logger.info("QQ channel stopped")

    async def _run_bot(self) -> None:
        try:
            await self._client.start(
                appid=self.config.app_id,
                secret=self.config.app_secret,
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"QQ bot error: {e}", exc_info=True)
            self._running = False

    def _make_bot_class(self) -> type:
        """Create a botpy.Client subclass bound to this channel instance."""
        import botpy

        channel = self

        intents = botpy.Intents(public_messages=True, direct_message=True)

        class _Bot(botpy.Client):
            def __init__(self):
                super().__init__(intents=intents)

            async def on_ready(self):
                logger.info(f"QQ bot connected: {self.robot.name}")

            async def on_c2c_message_create(self, message):
                await channel._on_msg(message, "c2c")

            async def on_group_at_message_create(self, message):
                await channel._on_msg(message, "group")

        return _Bot

    # ── Inbound ──────────────────────────────────────────────────────

    async def _on_msg(self, message, msg_type: str) -> None:
        """Handle incoming QQ message."""
        try:
            if message.id in self._processed_ids:
                return
            self._processed_ids.append(message.id)

            author = message.author
            content = (message.content or "").strip()
            # Strip @bot mention prefix injected by QQ in group messages
            content = re.sub(r"^@\S+\s*", "", content).strip()

            if msg_type == "c2c":
                sender_id = str(getattr(author, "user_openid", ""))
                chat_id = sender_id
            else:
                sender_id = str(getattr(author, "member_openid", ""))
                chat_id = str(getattr(message, "group_openid", ""))

            if not sender_id:
                return

            # Rate limit
            if not self.check_rate_limit(sender_id):
                return

            if not content:
                return

            logger.info(f"QQ {msg_type} from {sender_id}: {content[:80]}")
            asyncio.create_task(self._handle_llm(
                chat_id=chat_id,
                user_id=sender_id,
                content=content,
                metadata={"msg_type": msg_type, "event_id": message.id},
            ))
        except Exception:
            logger.exception("Error in QQ _on_msg")

    async def _handle_llm(
        self, chat_id: str, user_id: str, content: str, metadata: dict
    ) -> None:
        """Run LLM and send reply."""
        try:
            reply = await self.process_message(
                chat_id, user_id, content,
                platform="qq",
                metadata=metadata,
            )
            if reply:
                await self.send(chat_id, reply, metadata=metadata)
        except Exception as e:
            logger.error(f"QQ LLM error: {e}", exc_info=True)
            try:
                await self.send(chat_id, f"处理出错: {type(e).__name__}", metadata=metadata)
            except Exception:
                pass

    # ── Send ─────────────────────────────────────────────────────────

    def _next_msg_seq(self, msg_id: str) -> int:
        """Return and increment the msg_seq counter for the given msg_id."""
        seq = self._msg_seq.get(msg_id, 1)
        self._msg_seq[msg_id] = seq + 1
        if msg_id not in self._msg_seq_ids:
            self._msg_seq_order.append(msg_id)
            self._msg_seq_ids.add(msg_id)
            if len(self._msg_seq_order) > 500:
                oldest = self._msg_seq_order.popleft()
                self._msg_seq_ids.discard(oldest)
                self._msg_seq.pop(oldest, None)
        return seq

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        """Send a text chunk via QQ Bot API."""
        if not self._client:
            raise RuntimeError("QQ client not initialized")

        msg_type = (metadata or {}).get("msg_type", "c2c")
        msg_id = (metadata or {}).get("event_id", "")
        seq = self._next_msg_seq(msg_id)

        if msg_type == "group":
            await self._client.api.post_group_message(
                group_openid=chat_id,
                msg_type=0,
                content=raw_text,
                msg_id=msg_id,
                msg_seq=seq,
            )
        else:
            await self._client.api.post_c2c_message(
                openid=chat_id,
                msg_type=0,
                content=raw_text,
                msg_id=msg_id,
                msg_seq=seq,
            )

    def _format_chunk(self, text: str) -> str:
        """QQ uses plain text — strip Markdown."""
        return _strip_markdown(text)

    # ── Media send ───────────────────────────────────────────────────

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send media. QQ API only accepts URLs, not local paths."""
        if not self._client:
            return False

        from pathlib import Path
        meta = metadata or {}
        msg_type = meta.get("msg_type", "c2c")
        msg_id = meta.get("event_id", "")
        ext = Path(file_path).suffix.lower()
        file_type = self._FILE_TYPE_MAP.get(ext, 1)

        is_url = file_path.startswith("http://") or file_path.startswith("https://")
        if not is_url:
            # Fallback: send file name as text
            name = Path(file_path).name
            hint = f"[文件] {name}" + (f"\n{caption}" if caption else "")
            await self._send_chunk(chat_id, hint, hint, meta)
            return True

        try:
            seq = self._next_msg_seq(msg_id)
            if msg_type == "group":
                await self._client.api.post_group_file(
                    group_openid=chat_id,
                    file_type=file_type,
                    url=file_path,
                    srv_send_msg=True,
                )
            else:
                await self._client.api.post_c2c_file(
                    openid=chat_id,
                    file_type=file_type,
                    url=file_path,
                    srv_send_msg=True,
                )
        except Exception as e:
            logger.warning(f"QQ media send failed: {e}")
            return False

        if caption:
            await self.send(chat_id, caption, metadata=metadata)
        return True
