"""
WeChat (企业微信 / 微信公众号) channel implementation for OmicsClaw.

Supports two backends:
1. **wecom** (企业微信应用) — Corporate WeChat API
   - Receives messages via HTTP webhook callback (XML)
   - Sends replies via REST API
   - Supports text, markdown, image, file messages
   - Token auto-refresh with 2-hour TTL

2. **wechatmp** (微信公众号) — Official Account API
   - Receives messages via HTTP webhook callback (XML)
   - Sends replies via customer service API
   - Supports text, image messages

Prerequisites:
    pip install httpx aiohttp

Configuration via environment variables:
    # WeCom backend
    WECOM_CORP_ID            — Corp ID
    WECOM_AGENT_ID           — Agent ID
    WECOM_SECRET             — App Secret
    WECOM_TOKEN              — Callback token (optional, for signature verify)
    WECOM_ENCODING_AES_KEY   — Callback AES key (optional, for encrypted mode)
    WECOM_WEBHOOK_PORT       — Webhook listen port (default: 9001)

    # WeChat MP backend
    WECHAT_APP_ID            — App ID
    WECHAT_APP_SECRET        — App Secret
    WECHAT_TOKEN             — Callback token
    WECHAT_ENCODING_AES_KEY  — AES key (optional)
    WECHAT_WEBHOOK_PORT      — Webhook listen port (default: 9001)

References:
    - https://developer.work.weixin.qq.com/document/
    - https://developers.weixin.qq.com/doc/offiaccount/
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Channel
from .capabilities import WECHAT as WECHAT_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger(__name__)


# ── Markdown → plain text helper ─────────────────────────────────────


def _strip_markdown(text: str) -> str:
    """Strip Markdown for plain-text WeChat messages."""
    text = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip("`").strip(), text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1(\2)", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\-\*]\s+", "• ", text, flags=re.MULTILINE)
    return text


def _parse_xml(xml_str: str) -> dict[str, str]:
    """Parse WeChat XML message into a flat dict."""
    result: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_str)
        for child in root:
            result[child.tag] = child.text or ""
    except ET.ParseError:
        logger.warning("Failed to parse WeChat XML")
    return result


# ── Config ───────────────────────────────────────────────────────────


@dataclass
class WeComConfig(BaseChannelConfig):
    """WeCom (企业微信) configuration."""
    corp_id: str = ""
    agent_id: str = ""
    secret: str = ""
    token: str = ""                # Optional: callback verification
    encoding_aes_key: str = ""     # Optional: encrypted mode
    webhook_port: int = 9001
    text_chunk_limit: int = 4096


@dataclass
class WeChatMPConfig(BaseChannelConfig):
    """WeChat Official Account (公众号) configuration."""
    app_id: str = ""
    app_secret: str = ""
    token: str = ""
    encoding_aes_key: str = ""
    webhook_port: int = 9001
    text_chunk_limit: int = 4096


# ── Channel ──────────────────────────────────────────────────────────


class WeChatChannel(Channel):
    """Unified WeChat channel supporting WeCom and Official Account backends.

    Architecture follows the same pattern as FeishuChannel:
    - HTTP webhook server (aiohttp) for inbound messages
    - REST API calls (httpx) for outbound messages
    - Token auto-refresh with 5-minute safety margin

    Lifecycle:
        channel = WeChatChannel(config, backend="wecom")
        await channel.start()   # auth + start webhook
        await channel.run()     # blocks
        await channel.stop()    # cleanup
    """

    name = "wechat"
    capabilities = WECHAT_CAPS

    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}

    def __init__(
        self,
        config: WeComConfig | WeChatMPConfig,
        backend: str = "wecom",
    ):
        super().__init__(config)
        self._backend = backend
        self._access_token: str | None = None
        self._token_expires: float = 0
        self._http_client = None
        self._runner = None
        self._site = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            import httpx  # noqa: F401
            from aiohttp import web  # noqa: F401
        except ImportError:
            raise RuntimeError("httpx and aiohttp required. Run: pip install httpx aiohttp")

        self._validate_config()

        import httpx
        self._http_client = httpx.AsyncClient(timeout=15)

        # Get initial token
        await self._refresh_token()

        # Start webhook server
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/wechat/callback", self._handle_verify)
        app.router.add_post("/wechat/callback", self._handle_message)

        port = self.config.webhook_port if hasattr(self.config, "webhook_port") else 9001
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", port)
        await self._site.start()

        self._running = True
        logger.info(
            f"WeChat channel started (backend={self._backend}, "
            f"webhook on port {port})"
        )

    async def stop(self) -> None:
        self._running = False
        if self._site:
            await self._site.stop()
            self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._access_token = None
        logger.info("WeChat channel stopped")

    def _validate_config(self) -> None:
        """Validate required config fields."""
        if self._backend == "wecom":
            cfg = self.config
            if not getattr(cfg, "corp_id", None):
                raise RuntimeError("WECOM_CORP_ID is required")
            if not getattr(cfg, "secret", None):
                raise RuntimeError("WECOM_SECRET is required")
            if not getattr(cfg, "agent_id", None):
                raise RuntimeError("WECOM_AGENT_ID is required")
        elif self._backend == "wechatmp":
            cfg = self.config
            if not getattr(cfg, "app_id", None):
                raise RuntimeError("WECHAT_APP_ID is required")
            if not getattr(cfg, "app_secret", None):
                raise RuntimeError("WECHAT_APP_SECRET is required")

    # ── Token management ─────────────────────────────────────────────

    async def _refresh_token(self) -> None:
        """Fetch or refresh the access_token."""
        if self._backend == "wecom":
            cfg = self.config
            url = (
                f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
                f"?corpid={cfg.corp_id}&corpsecret={cfg.secret}"
            )
        else:
            cfg = self.config
            url = (
                f"https://api.weixin.qq.com/cgi-bin/token"
                f"?grant_type=client_credential"
                f"&appid={cfg.app_id}&secret={cfg.app_secret}"
            )

        resp = await self._http_client.get(url)
        data = resp.json()

        if data.get("errcode", 0) != 0:
            raise RuntimeError(
                f"WeChat auth error ({data.get('errcode')}): "
                f"{data.get('errmsg', 'unknown')}"
            )

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 7200)
        self._token_expires = time.monotonic() + expires_in - 300
        logger.debug(f"WeChat token refreshed, expires in {expires_in}s")

    async def _ensure_token(self) -> str:
        """Return a valid access token."""
        if not self._access_token or time.monotonic() >= self._token_expires:
            await self._refresh_token()
        return self._access_token

    # ── Webhook: URL verification (GET) ──────────────────────────────

    async def _handle_verify(self, request) -> Any:
        """Handle GET /wechat/callback for URL verification."""
        from aiohttp import web

        signature = request.query.get("signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")
        echostr = request.query.get("echostr", "")

        if not echostr:
            return web.Response(status=400, text="missing echostr")

        # Plain-mode signature verification
        token = getattr(self.config, "token", "")
        if token:
            parts = sorted([token, timestamp, nonce])
            expected = hashlib.sha1("".join(parts).encode()).hexdigest()
            if expected != signature:
                logger.warning("WeChat verify: signature mismatch")
                return web.Response(status=403)

        return web.Response(text=echostr)

    # ── Webhook: inbound messages (POST) ─────────────────────────────

    async def _handle_message(self, request) -> Any:
        """Handle POST /wechat/callback for incoming messages."""
        from aiohttp import web

        try:
            body = await request.text()
        except Exception:
            return web.Response(status=400)

        xml_data = _parse_xml(body)

        # Process asynchronously (WeChat requires response within 5s)
        asyncio.create_task(self._safe_process(xml_data))
        return web.Response(text="success")

    async def _safe_process(self, xml_data: dict[str, str]) -> None:
        """Wrapper to catch exceptions in fire-and-forget tasks."""
        try:
            await self._process_message(xml_data)
        except Exception:
            logger.exception("Error processing WeChat message")

    async def _process_message(self, xml_data: dict[str, str]) -> None:
        """Parse XML message and route to LLM."""
        msg_type = xml_data.get("MsgType", "")
        from_user = xml_data.get("FromUserName", "")
        msg_id = xml_data.get("MsgId", "")
        content = xml_data.get("Content", "")

        if not from_user:
            return

        # Build text from different message types
        text = ""
        if msg_type == "text":
            text = content
        elif msg_type == "image":
            text = "[图片消息]"
        elif msg_type == "voice":
            recognition = xml_data.get("Recognition", "")
            text = f"[语音识别] {recognition}" if recognition else "[语音消息]"
        elif msg_type == "location":
            label = xml_data.get("Label", "")
            lat = xml_data.get("Location_X", "")
            lon = xml_data.get("Location_Y", "")
            text = f"[位置] {label} ({lat}, {lon})"
        elif msg_type == "link":
            title = xml_data.get("Title", "")
            url = xml_data.get("Url", "")
            text = f"[链接] {title}\n{url}"
        elif msg_type == "event":
            event = xml_data.get("Event", "")
            if event == "subscribe":
                text = "[用户关注]"
            elif event == "unsubscribe":
                return
            else:
                return
        else:
            text = f"[{msg_type} 消息]"

        if not text:
            return

        chat_id = from_user

        # Dedup & rate limit
        if msg_id and self.is_duplicate(msg_id):
            return
        if not self.check_rate_limit(from_user):
            return

        logger.info(f"WeChat message from {from_user}: {text[:80]}")
        asyncio.create_task(self._handle_llm(chat_id, from_user, text))

    async def _handle_llm(self, chat_id: str, user_id: str, content: str) -> None:
        """Process through core LLM and send reply."""
        try:
            reply = await self.process_message(
                chat_id, user_id, content,
                platform=f"wechat-{self._backend}",
            )
            if reply:
                await self.send(chat_id, reply)
        except Exception as e:
            logger.error(f"WeChat process error: {e}", exc_info=True)
            try:
                await self.send(chat_id, f"抱歉，处理出错: {type(e).__name__}")
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
        """Send a text message via WeChat/WeCom REST API."""
        token = await self._ensure_token()

        if self._backend == "wecom":
            # Try markdown first, then fallback to plain text
            try:
                await self._wecom_send_markdown(token, chat_id, raw_text)
                return
            except Exception:
                pass
            await self._wecom_send_text(token, chat_id, raw_text)
        else:
            await self._mp_send_text(token, chat_id, raw_text)

    def _format_chunk(self, text: str) -> str:
        """WeCom uses markdown; MP uses plain text."""
        if self._backend == "wecom":
            return text  # WeCom supports a subset of Markdown
        return _strip_markdown(text)

    # ── WeCom send helpers ───────────────────────────────────────────

    async def _wecom_send_text(self, token: str, user_id: str, text: str) -> None:
        """Send plain text via WeCom API."""
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        body = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": int(self.config.agent_id),
            "text": {"content": _strip_markdown(text)},
        }
        resp = await self._http_client.post(url, json=body)
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"WeCom send error: {data.get('errmsg')}")

    async def _wecom_send_markdown(self, token: str, user_id: str, text: str) -> None:
        """Send markdown via WeCom API."""
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        body = {
            "touser": user_id,
            "msgtype": "markdown",
            "agentid": int(self.config.agent_id),
            "markdown": {"content": text},
        }
        resp = await self._http_client.post(url, json=body)
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"WeCom markdown send error: {data.get('errmsg')}")

    # ── MP send helpers ──────────────────────────────────────────────

    async def _mp_send_text(self, token: str, openid: str, text: str) -> None:
        """Send text via WeChat MP customer service API."""
        url = (
            f"https://api.weixin.qq.com/cgi-bin/message/custom/send"
            f"?access_token={token}"
        )
        body = {
            "touser": openid,
            "msgtype": "text",
            "text": {"content": _strip_markdown(text)},
        }
        resp = await self._http_client.post(url, json=body)
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"MP send error: {data.get('errmsg')}")

    # ── Media send ───────────────────────────────────────────────────

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Upload and send a media file via WeChat/WeCom."""
        try:
            token = await self._ensure_token()
            media_id = await self._upload_media(token, file_path)
            if not media_id:
                return False

            ext = Path(file_path).suffix.lower()
            is_image = ext in self._IMAGE_EXTS
            msg_type = "image" if is_image else "file"

            if self._backend == "wecom":
                url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
                body = {
                    "touser": chat_id,
                    "msgtype": msg_type,
                    "agentid": int(self.config.agent_id),
                    msg_type: {"media_id": media_id},
                }
                await self._http_client.post(url, json=body)
            else:
                if not is_image:
                    # MP doesn't support file; send as text
                    name = Path(file_path).name
                    await self._mp_send_text(
                        token, chat_id, f"[文件] {name}\n{caption}" if caption else f"[文件] {name}"
                    )
                    return True
                url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={token}"
                body = {
                    "touser": chat_id,
                    "msgtype": "image",
                    "image": {"media_id": media_id},
                }
                await self._http_client.post(url, json=body)

            # Send caption separately if provided
            if caption:
                await self.send(chat_id, caption)

            return True
        except Exception as e:
            logger.error(f"WeChat media send error: {e}")
            return False

    async def _upload_media(self, token: str, file_path: str) -> str | None:
        """Upload media to WeChat/WeCom and return media_id."""
        ext = Path(file_path).suffix.lower()
        is_image = ext in self._IMAGE_EXTS
        media_type = "image" if is_image else "file"

        if self._backend == "wecom":
            url = (
                f"https://qyapi.weixin.qq.com/cgi-bin/media/upload"
                f"?access_token={token}&type={media_type}"
            )
        else:
            url = (
                f"https://api.weixin.qq.com/cgi-bin/media/upload"
                f"?access_token={token}&type={media_type}"
            )

        try:
            with open(file_path, "rb") as f:
                resp = await self._http_client.post(
                    url,
                    files={"media": (Path(file_path).name, f)},
                )
            data = resp.json()
            if data.get("errcode", 0) != 0 and "media_id" not in data:
                logger.error(f"WeChat media upload failed: {data.get('errmsg')}")
                return None
            return data.get("media_id")
        except Exception as e:
            logger.error(f"WeChat media upload error: {e}")
            return None

    # ── Backward-compatible entry point ──────────────────────────────

    def run_server(self) -> None:
        """Blocking entry point for running the WeChat channel standalone."""
        asyncio.run(self.run())
