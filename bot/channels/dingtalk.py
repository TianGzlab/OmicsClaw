"""
DingTalk (钉钉) channel implementation for OmicsClaw.

Uses the DingTalk Stream (WebSocket) protocol — no public IP required.
The bot connects via ``dingtalk-stream`` SDK or raw WebSocket to receive
messages and sends replies via the DingTalk Robot REST API.

Prerequisites:
    pip install httpx websockets

Configuration via environment variables:
    DINGTALK_CLIENT_ID       — Robot App Key
    DINGTALK_CLIENT_SECRET   — Robot App Secret

References:
    - https://open.dingtalk.com/document/isvapp/create-a-robot
    - https://open.dingtalk.com/document/orgapp/the-robot-sends-a-one-on-one-message
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from .base import Channel
from .capabilities import DINGTALK as DINGTALK_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger(__name__)

# ── DingTalk API endpoints ───────────────────────────────────────────

GATEWAY_URL = "https://api.dingtalk.com/v1.0/gateway/connections/open"
TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
SEND_URL = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
MEDIA_UPLOAD_URL = "https://oapi.dingtalk.com/media/upload"
FILE_DOWNLOAD_URL = "https://api.dingtalk.com/v1.0/robot/messageFiles/download"


# ── Config ───────────────────────────────────────────────────────────


@dataclass
class DingTalkConfig(BaseChannelConfig):
    """DingTalk channel configuration."""
    client_id: str = ""         # Robot App Key
    client_secret: str = ""     # Robot App Secret
    text_chunk_limit: int = 4096


# ── Channel ──────────────────────────────────────────────────────────


class DingTalkChannel(Channel):
    """DingTalk channel using Stream Mode (WebSocket).

    Architecture:
    1. Authenticate via OAuth to get access_token
    2. Open WebSocket gateway for inbound messages
    3. ACK each message, parse content, process through LLM
    4. Send replies via Robot oToMessages/batchSend REST API

    Lifecycle:
        channel = DingTalkChannel(config)
        await channel.start()   # auth + ws connect
        await channel.run()     # blocks on message loop
        await channel.stop()    # cleanup
    """

    name = "dingtalk"
    capabilities = DINGTALK_CAPS

    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

    def __init__(self, config: DingTalkConfig):
        super().__init__(config)
        self._http_client = None
        self._access_token: str | None = None
        self._token_expires: float = 0
        self._ws = None
        self._ws_task: asyncio.Task | None = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed. Run: pip install httpx")

        cfg: DingTalkConfig = self.config
        if not cfg.client_id or not cfg.client_secret:
            raise RuntimeError("DINGTALK_CLIENT_ID and DINGTALK_CLIENT_SECRET required")

        self._http_client = httpx.AsyncClient(timeout=15)
        await self._refresh_token()
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_loop())
        logger.info("DingTalk channel started (Stream Mode)")

    async def stop(self) -> None:
        self._running = False
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except (asyncio.CancelledError, Exception):
                pass
            self._ws_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._access_token = None
        logger.info("DingTalk channel stopped")

    # ── Token management ─────────────────────────────────────────────

    async def _refresh_token(self) -> None:
        """Fetch access_token from DingTalk OAuth2."""
        cfg: DingTalkConfig = self.config
        resp = await self._http_client.post(
            TOKEN_URL,
            json={"appKey": cfg.client_id, "appSecret": cfg.client_secret},
        )
        data = resp.json()
        token = data.get("accessToken")
        if not token:
            raise RuntimeError(f"DingTalk auth failed: {data}")
        self._access_token = token
        expires_in = int(data.get("expireIn", 7200))
        self._token_expires = time.monotonic() + expires_in - 300  # 5min early refresh
        logger.debug(f"DingTalk token refreshed, expires in {expires_in}s")

    async def _ensure_token(self) -> str:
        """Ensure the access token is valid, refreshing if expired."""
        if not self._access_token or time.monotonic() >= self._token_expires:
            await self._refresh_token()
        return self._access_token

    # ── WebSocket stream ─────────────────────────────────────────────

    async def _get_ws_url(self) -> str:
        """Get WebSocket URL from DingTalk gateway."""
        cfg: DingTalkConfig = self.config
        resp = await self._http_client.post(
            GATEWAY_URL,
            json={
                "clientId": cfg.client_id,
                "clientSecret": cfg.client_secret,
                "subscriptions": [
                    {"type": "CALLBACK", "topic": "/v1.0/im/bot/messages/get"}
                ],
                "ua": "omicsclaw-dingtalk/0.1",
            },
        )
        data = resp.json()
        endpoint, ticket = data.get("endpoint"), data.get("ticket")
        if not endpoint or not ticket:
            raise RuntimeError(f"DingTalk gateway failed: {data}")
        return f"{endpoint}?ticket={quote_plus(ticket)}"

    async def _ws_loop(self) -> None:
        """WebSocket message loop with automatic reconnection."""
        try:
            import websockets
        except ImportError:
            raise RuntimeError("websockets not installed. Run: pip install websockets")

        while self._running:
            try:
                ws_url = await self._get_ws_url()
                async with websockets.connect(ws_url) as ws:
                    self._ws = ws
                    logger.info("DingTalk WebSocket connected")
                    async for raw in ws:
                        try:
                            data = json.loads(raw) if isinstance(raw, str) else raw
                            await self._on_ws_message(data)
                        except json.JSONDecodeError:
                            logger.warning(f"DingTalk: non-JSON message: {raw[:100]}")
                        except Exception as e:
                            logger.error(f"DingTalk ws process error: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"DingTalk WS disconnected: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _ws_send_json(self, data: dict) -> None:
        """Send a JSON payload over the WebSocket."""
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def _on_ws_message(self, data: dict) -> None:
        """Handle a single WebSocket message from DingTalk Stream."""
        if not isinstance(data, dict):
            return

        headers = data.get("headers", {})
        msg_id = headers.get("messageId", "")

        # System ping — respond immediately
        if data.get("type") == "SYSTEM" and headers.get("topic") == "ping":
            await self._ws_send_json({
                "code": 200,
                "headers": headers,
                "message": "OK",
                "data": data.get("data", ""),
            })
            return

        # ACK the message
        await self._ws_send_json({
            "code": 200,
            "headers": {"contentType": "application/json", "messageId": msg_id},
            "message": "OK",
            "data": "{}",
        })

        if data.get("type") != "CALLBACK":
            return

        # Parse payload
        payload = data.get("data", "{}")
        if isinstance(payload, str):
            payload = json.loads(payload)

        text_obj = payload.get("text", {})
        content = (
            text_obj.get("content", "") if isinstance(text_obj, dict) else str(text_obj)
        ).strip()
        if not content:
            content = str(payload.get("content", "")).strip()
        if not content:
            return

        sender_id = payload.get("senderStaffId") or payload.get("senderId", "")
        is_group = payload.get("conversationType") == "2"
        chat_id = sender_id  # oToMessages API uses userIds (staffId)

        # Mention gating
        was_mentioned = not is_group
        if is_group and payload.get("isInAtList"):
            was_mentioned = True

        # Dedup & rate limit
        if self.is_duplicate(msg_id):
            return
        if not self._is_admin(sender_id) and not self.check_rate_limit(sender_id):
            logger.info(f"DingTalk: rate limited {sender_id}")
            return

        if not was_mentioned and is_group:
            return  # Skip group messages without @bot

        # Process through LLM
        logger.info(f"DingTalk message from {sender_id}: {content[:80]}")
        asyncio.create_task(self._handle_message(chat_id, sender_id, content))

    async def _handle_message(self, chat_id: str, sender_id: str, content: str) -> None:
        """Process message through core LLM and send reply."""
        try:
            reply = await self.process_message(
                chat_id, sender_id, content,
                platform="dingtalk",
            )
            if reply:
                await self.send(chat_id, reply)
        except Exception as e:
            logger.error(f"DingTalk process error: {e}", exc_info=True)
            try:
                await self.send(chat_id, f"Sorry, an error occurred: {type(e).__name__}")
            except Exception:
                pass

    # ── Send ─────────────────────────────────────────────────────────

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        """Send a single text chunk via DingTalk Robot API (Markdown)."""
        token = await self._ensure_token()
        cfg: DingTalkConfig = self.config
        await self._http_client.post(
            SEND_URL,
            json={
                "robotCode": cfg.client_id,
                "userIds": [chat_id],
                "msgKey": "sampleMarkdown",
                "msgParam": json.dumps({
                    "text": raw_text,
                    "title": "OmicsClaw",
                }),
            },
            headers={"x-acs-dingtalk-access-token": token},
        )

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a media file via DingTalk (images as native, files as markdown link)."""
        try:
            token = await self._ensure_token()
            cfg: DingTalkConfig = self.config
            ext = Path(file_path).suffix.lower()

            if ext in self._IMAGE_EXTS:
                media_id = await self._upload_media(token, file_path, "image")
                if media_id:
                    await self._http_client.post(
                        SEND_URL,
                        json={
                            "robotCode": cfg.client_id,
                            "userIds": [chat_id],
                            "msgKey": "sampleImageMsg",
                            "msgParam": json.dumps({"photoURL": media_id}),
                        },
                        headers={"x-acs-dingtalk-access-token": token},
                    )
                else:
                    # Fallback to markdown
                    text = f"![image]({file_path})"
                    await self.send(chat_id, text)
            else:
                name = Path(file_path).name
                text = f"[文件] {name}" + (f"\n{caption}" if caption else "")
                await self.send(chat_id, text)

            return True
        except Exception as e:
            logger.error(f"DingTalk media send error: {e}")
            return False

    async def _upload_media(
        self, token: str, file_path: str, media_type: str = "image",
    ) -> str | None:
        """Upload a file to DingTalk and return media_id."""
        try:
            url = f"{MEDIA_UPLOAD_URL}?access_token={token}&type={media_type}"
            with open(file_path, "rb") as f:
                resp = await self._http_client.post(
                    url,
                    files={"media": (Path(file_path).name, f)},
                )
            return resp.json().get("media_id")
        except Exception as e:
            logger.warning(f"DingTalk media upload failed: {e}")
            return None

    # ── Backward-compatible entry point ──────────────────────────────

    def run_stream(self) -> None:
        """Blocking entry point for running the DingTalk channel standalone."""
        asyncio.run(self.run())
