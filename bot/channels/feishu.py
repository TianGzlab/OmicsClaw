"""
Feishu (Lark) channel implementation for OmicsClaw.

Extracts the platform-specific logic into a reusable Channel subclass.

Uses lark-oapi Python SDK with WebSocket long-connection (no public IP required).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import Channel, chunk_text
from .capabilities import FEISHU as FEISHU_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger("omicsclaw.channel.feishu")


@dataclass
class FeishuConfig(BaseChannelConfig):
    """Feishu-specific configuration."""
    app_id: str = ""
    app_secret: str = ""
    thinking_threshold_ms: int = 2500
    max_inbound_image_mb: int = 12
    max_inbound_file_mb: int = 40
    max_attachments: int = 4
    debug: bool = False


class FeishuChannel(Channel):
    """Feishu channel using lark-oapi with WebSocket long-connection.

    The Feishu SDK uses a synchronous event handler, so this channel
    uses a background asyncio event loop for integrating with core.py's
    async LLM tool loop.
    """

    name = "feishu"
    capabilities = FEISHU_CAPS

    # Request verbs to detect intent in group chats
    _REQUEST_VERBS = [
        "帮", "麻烦", "请", "能否", "可以", "解释", "看看", "排查",
        "分析", "总结", "写", "改", "修", "查", "对比", "翻译",
        "preprocess", "analyze", "run", "demo",
    ]

    def __init__(self, config: FeishuConfig):
        super().__init__(config)
        self.feishu_config = config
        self._lark_client = None
        self._ws_client = None
        self._loop = None
        self._loop_thread = None
        self._bot_start_time = time.time()
        self._seen: dict[str, float] = {}
        self._seen_ttl = 600
        self._group_member_count: dict[str, tuple[int, float]] = {}
        self._member_count_ttl = 3600

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self.feishu_config.app_id:
            raise RuntimeError("FEISHU_APP_ID is required")
        if not self.feishu_config.app_secret:
            raise RuntimeError("FEISHU_APP_SECRET is required")

        try:
            import lark_oapi as lark
        except ImportError:
            raise RuntimeError(
                "lark-oapi not installed. "
                "Install with: pip install lark-oapi"
            )

        self._lark_client = lark.Client.builder() \
            .app_id(self.feishu_config.app_id) \
            .app_secret(self.feishu_config.app_secret) \
            .log_level(
                lark.LogLevel.DEBUG if self.feishu_config.debug
                else lark.LogLevel.INFO
            ) \
            .build()

        # Background async event loop for LLM calls
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True,
        )
        self._loop_thread.start()

        # ── Start WebSocket event listener in a separate thread ────────
        # CRITICAL: lark_oapi.ws.client has a MODULE-LEVEL variable:
        #     loop = asyncio.get_event_loop()  (line 26 of client.py)
        # All internal methods (start, _connect, _receive_message_loop)
        # use this cached `loop`. When imported from an async context
        # (ChannelManager's asyncio.run), it captures the RUNNING main
        # loop, causing "This event loop is already running" errors.
        #
        # Fix: create a fresh loop in the thread and PATCH the module-
        # level `loop` variable so lark_oapi uses it.
        def _ws_thread_target():
            import lark_oapi.ws.client as _ws_mod

            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)
            # Monkey-patch the module-level loop variable
            _ws_mod.loop = ws_loop

            try:
                event_handler = lark.EventDispatcherHandler.builder("", "") \
                    .register_p2_im_message_receive_v1(self._handle_event) \
                    .build()

                self._ws_client = lark.ws.Client(
                    self.feishu_config.app_id,
                    self.feishu_config.app_secret,
                    event_handler=event_handler,
                    log_level=(
                        lark.LogLevel.DEBUG if self.feishu_config.debug
                        else lark.LogLevel.INFO
                    ),
                )
                self._ws_client.start()
            except Exception as e:
                logger.error(f"Feishu WebSocket thread error: {e}", exc_info=True)
            finally:
                ws_loop.close()

        self._ws_thread = threading.Thread(
            target=_ws_thread_target, daemon=True,
        )
        self._ws_thread.start()

        self._running = True
        logger.info("Feishu channel initialized")

    async def stop(self) -> None:
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        await self._typing_manager.stop_all()
        logger.info("Feishu channel stopped")

    def run_sync(self) -> None:
        """Synchronous entry point — start the Feishu bot with WebSocket.

        This is the primary way to start the Feishu bot (backward-compatible).
        Calls start() internally which sets up the WebSocket listener in a
        daemon thread, then blocks until interrupted.
        """
        from bot import core

        logger.info(
            f"Starting OmicsClaw Feishu bot "
            f"(provider: {core.LLM_PROVIDER_NAME}, model: {core.OMICSCLAW_MODEL})"
        )
        logger.info(f"OmicsClaw directory: {core.OMICSCLAW_DIR}")
        logger.info(f"Feishu App ID: {self.feishu_config.app_id}")
        core.audit(
            "bot_start",
            platform="feishu",
            provider=core.LLM_PROVIDER_NAME,
            model=core.OMICSCLAW_MODEL,
            feishu_app_id=self.feishu_config.app_id,
        )

        # start() creates the WebSocket listener in a daemon thread.
        # Use new_event_loop() to avoid DeprecationWarning on Python 3.10+.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start())

        print("OmicsClaw Feishu bot is running. Press Ctrl+C to stop.")

        # Block the main thread — the WS listener runs in _ws_thread
        try:
            self._ws_thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            loop.close()

    # ── Core send implementation ─────────────────────────────────────

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        """Send a single text chunk via Feishu."""
        self._send_text_sync(chat_id, formatted_text)

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a media file via Feishu."""
        try:
            path = Path(file_path)
            if not path.exists():
                return False
            ext = path.suffix.lower()
            if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                self._send_image_file(chat_id, file_path, caption)
            else:
                self._send_document_file(chat_id, file_path, caption)
            return True
        except Exception as e:
            logger.error(f"Feishu send_media error: {e}")
            return False

    # ── Dedup ────────────────────────────────────────────────────────

    def _is_duplicate_feishu(self, message_id: str) -> bool:
        """Feishu-specific dedup with TTL cleanup."""
        now = time.time()
        expired = [k for k, ts in self._seen.items() if now - ts > self._seen_ttl]
        for k in expired:
            del self._seen[k]
        if not message_id:
            return False
        if message_id in self._seen:
            return True
        self._seen[message_id] = now
        return False

    # ── Group member count ───────────────────────────────────────────

    def _get_group_member_count(self, chat_id: str) -> int:
        now = time.time()
        if chat_id in self._group_member_count:
            count, timestamp = self._group_member_count[chat_id]
            if now - timestamp < self._member_count_ttl:
                return count
        try:
            from lark_oapi.api.im.v1 import GetChatRequest
            request = GetChatRequest.builder().chat_id(chat_id).build()
            response = self._lark_client.im.v1.chat.get(request)
            if response.success() and response.data:
                user_count = int(response.data.user_count or 0)
                bot_count = int(response.data.bot_count or 0)
                member_count = user_count + bot_count
                self._group_member_count[chat_id] = (member_count, now)
                return member_count
        except Exception as e:
            logger.warning(f"Failed to get group member count: {e}")
        return 3  # Default: assume normal group

    # ── Text parsing ─────────────────────────────────────────────────

    @staticmethod
    def _normalize_text(raw: str) -> str:
        t = str(raw or "")
        t = re.sub(r"<\s*br\s*/?>", "\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<\s*/p\s*>\s*<\s*p\s*>", "\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<[^>]+>", "", t)
        t = t.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
        t = t.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    def _extract_post_text(self, post_json: dict) -> tuple[str, list[str]]:
        """Extract text and image_keys from a Feishu post (rich text) message."""
        lines: list[str] = []
        image_keys: list[str] = []

        def inline(node) -> str:
            if not node:
                return ""
            if isinstance(node, list):
                return "".join(inline(n) for n in node)
            if not isinstance(node, dict):
                return ""
            tag = node.get("tag", "")
            if tag == "text":
                return str(node.get("text", ""))
            if tag == "a":
                return str(node.get("text", node.get("href", "")))
            if tag == "at":
                return f"@{node.get('user_name', '')}" if node.get("user_name") else "@"
            if tag == "img":
                if node.get("image_key"):
                    image_keys.append(str(node["image_key"]))
                return "[image]"
            if tag == "code_block":
                lang = str(node.get("language", "")).strip()
                code = str(node.get("text", ""))
                return f"\n```{lang}\n{code}\n```\n"
            acc = ""
            for v in node.values():
                if isinstance(v, (dict, list)):
                    acc += inline(v)
            return acc

        title = post_json.get("title", "")
        if title:
            lines.append(self._normalize_text(title))

        content = post_json.get("content")
        if isinstance(content, list):
            for para in content:
                if isinstance(para, list):
                    joined = "".join(inline(n) for n in para)
                else:
                    joined = inline(para)
                normalized = self._normalize_text(joined)
                if normalized:
                    lines.append(normalized)
        elif content:
            normalized = self._normalize_text(inline(content))
            if normalized:
                lines.append(normalized)

        return "\n".join(lines).strip(), list(set(image_keys))

    def _download_image_as_b64(self, message_id: str, image_key: str) -> str | None:
        """Download a Feishu image and return as base64 data URL."""
        try:
            from lark_oapi.api.im.v1 import GetMessageResourceRequest
            request = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(image_key) \
                .type("image") \
                .build()
            response = self._lark_client.im.v1.message_resource.get(request)
            if not response.success():
                logger.warning(f"Image download failed: {response.code} {response.msg}")
                return None

            tmp = Path(tempfile.gettempdir()) / f"feishu_recv_{time.time_ns()}.png"
            tmp.write_bytes(response.file.read())

            size = tmp.stat().st_size
            max_bytes = self.feishu_config.max_inbound_image_mb * 1024 * 1024
            if size > max_bytes:
                logger.warning(f"Image too large: {size} bytes > {max_bytes}")
                tmp.unlink(missing_ok=True)
                return None

            b64 = base64.standard_b64encode(tmp.read_bytes()).decode("ascii")
            tmp.unlink(missing_ok=True)
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            logger.error(f"Image download error: {e}")
            return None

    def _download_file_to_tmp(self, message_id: str, file_key: str, filename: str = "file.bin") -> str | None:
        """Download a Feishu file to a temp path and return the path."""
        try:
            from lark_oapi.api.im.v1 import GetMessageResourceRequest
            request = GetMessageResourceRequest.builder() \
                .message_id(message_id) \
                .file_key(file_key) \
                .type("file") \
                .build()
            response = self._lark_client.im.v1.message_resource.get(request)
            if not response.success():
                logger.warning(f"File download failed: {response.code} {response.msg}")
                return None

            ext = Path(filename).suffix or ".bin"
            tmp = Path(tempfile.gettempdir()) / f"feishu_recv_{time.time_ns()}{ext}"
            tmp.write_bytes(response.file.read())

            size = tmp.stat().st_size
            max_bytes = self.feishu_config.max_inbound_file_mb * 1024 * 1024
            if size > max_bytes:
                logger.warning(f"File too large: {size} bytes > {max_bytes}")
                tmp.unlink(missing_ok=True)
                return None
            return str(tmp)
        except Exception as e:
            logger.error(f"File download error: {e}")
            return None

    def _parse_message(self, message: dict) -> tuple[str, list[dict]]:
        """Parse a Feishu message into (text, attachments)."""
        message_id = message.get("message_id", "")
        message_type = message.get("message_type", "")
        raw_content = message.get("content", "")
        text = ""
        attachments: list[dict] = []

        if not message_type or not raw_content:
            return text, attachments

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            return self._normalize_text(raw_content), attachments

        if message_type == "text":
            text = self._normalize_text(parsed.get("text", ""))
        elif message_type == "post":
            post_text, image_keys = self._extract_post_text(parsed)
            text = post_text
            for k in image_keys[:self.feishu_config.max_attachments]:
                data_url = self._download_image_as_b64(message_id, k)
                if data_url:
                    attachments.append({"type": "image", "content": data_url})
        elif message_type == "image":
            image_key = parsed.get("image_key", "")
            if image_key and message_id:
                data_url = self._download_image_as_b64(message_id, image_key)
                if data_url:
                    attachments.append({"type": "image", "content": data_url})
            text = "[image]"
        elif message_type == "file":
            file_key = parsed.get("file_key", "")
            fname = parsed.get("file_name", "file.bin")
            text = f"[file] {fname}"
            if file_key and message_id:
                fp = self._download_file_to_tmp(message_id, file_key, fname)
                if fp:
                    text += f"\n\n[local path] {fp}"
        elif message_type == "audio":
            file_key = parsed.get("file_key", "")
            fname = parsed.get("file_name", "audio.opus")
            text = f"[audio] {fname}"
            if file_key and message_id:
                fp = self._download_file_to_tmp(message_id, file_key, fname)
                if fp:
                    text += f"\n\n[local path] {fp}"
        elif message_type == "media":
            file_key = parsed.get("file_key", "")
            fname = parsed.get("file_name", "video.bin")
            text = f"[video] {fname}"
            if file_key and message_id:
                fp = self._download_file_to_tmp(message_id, file_key, fname)
                if fp:
                    text += f"\n\n[local path] {fp}"

        if not text and attachments:
            text = "[attachment]"
        if not text:
            text = f"[{message_type} message]"

        return text, attachments

    # ── Group intent filter ──────────────────────────────────────────

    def _should_respond_in_group(self, text: str, mentions: list) -> bool:
        if mentions:
            return True
        if re.search(r"[？?]$", text):
            return True
        if re.search(r"\b(why|how|what|when|where|who|help)\b", text, re.IGNORECASE):
            return True
        if any(v in text for v in self._REQUEST_VERBS):
            return True
        if re.match(r"^(omicsclaw|spatialclaw|bot|助手|智能体)[\s,:，：]", text, re.IGNORECASE):
            return True
        return False

    # ── Feishu send helpers ──────────────────────────────────────────

    def _send_text_sync(self, chat_id: str, text: str, retries: int = 3) -> str | None:
        """Send a text message with retry. Returns message_id or None."""
        import requests as _requests
        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}))
                .build()
            ).build()

        for attempt in range(1, retries + 1):
            try:
                response = self._lark_client.im.v1.message.create(request)
                if not response.success():
                    logger.error(f"Send text failed: {response.code} {response.msg}")
                    return None
                return response.data.message_id if response.data else None
            except (_requests.exceptions.SSLError,
                    _requests.exceptions.ConnectionError) as e:
                if attempt < retries:
                    wait = attempt * 2
                    logger.warning(
                        f"Send text attempt {attempt}/{retries} failed ({e}), "
                        f"retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"Send text failed after {retries} attempts: {e}")
                    return None

    def _update_text(self, message_id: str, text: str) -> bool:
        """Update an existing message. Returns True on success."""
        from lark_oapi.api.im.v1 import (
            UpdateMessageRequest,
            UpdateMessageRequestBody,
        )
        request = UpdateMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(
                UpdateMessageRequestBody.builder()
                .msg_type("text")
                .content(json.dumps({"text": text}))
                .build()
            ).build()
        try:
            response = self._lark_client.im.v1.message.update(request)
            if not response.success():
                logger.warning(f"Update text failed: {response.code} {response.msg}")
                return False
            return True
        except Exception as e:
            logger.warning(f"Update text error: {e}")
            return False

    def _delete_message(self, message_id: str) -> None:
        from lark_oapi.api.im.v1 import DeleteMessageRequest
        request = DeleteMessageRequest.builder() \
            .message_id(message_id) \
            .build()
        try:
            self._lark_client.im.v1.message.delete(request)
        except Exception:
            pass

    def _send_long_text(self, chat_id: str, text: str) -> str | None:
        """Send a text message, splitting into chunks if too long."""
        limit = self.capabilities.max_text_length
        if len(text) <= limit:
            return self._send_text_sync(chat_id, text)

        first_mid = None
        for chunk in chunk_text(text, limit):
            if chunk.strip():
                mid = self._send_text_sync(chat_id, chunk.strip())
                if first_mid is None:
                    first_mid = mid
        return first_mid

    def _send_image_file(self, chat_id: str, filepath: str, caption: str | None = None) -> None:
        """Upload a local image file and send it to the chat."""
        import requests as _requests
        from lark_oapi.api.im.v1 import (
            CreateImageRequest,
            CreateImageRequestBody,
            CreateMessageRequest,
            CreateMessageRequestBody,
        )
        try:
            with open(filepath, "rb") as f:
                upload_req = CreateImageRequest.builder() \
                    .request_body(
                        CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(f)
                        .build()
                    ).build()
                upload_resp = self._lark_client.im.v1.image.create(upload_req)

            if not upload_resp.success():
                logger.error(f"Image upload failed: {upload_resp.code} {upload_resp.msg}")
                return

            image_key = upload_resp.data.image_key
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("image")
                    .content(json.dumps({"image_key": image_key}))
                    .build()
                ).build()
            self._lark_client.im.v1.message.create(request)

            if caption and caption.strip():
                self._send_text_sync(chat_id, caption.strip())
        except (_requests.exceptions.SSLError, _requests.exceptions.ConnectionError):
            raise
        except Exception as e:
            logger.error(f"Send image failed: {e}")

    def _send_document_file(self, chat_id: str, filepath: str, caption: str | None = None) -> None:
        """Upload and send a non-image file."""
        import requests as _requests
        from lark_oapi.api.im.v1 import (
            CreateFileRequest,
            CreateFileRequestBody,
            CreateMessageRequest,
            CreateMessageRequestBody,
        )
        try:
            fname = Path(filepath).name
            with open(filepath, "rb") as f:
                upload_req = CreateFileRequest.builder() \
                    .request_body(
                        CreateFileRequestBody.builder()
                        .file_type("stream")
                        .file_name(fname)
                        .file(f)
                        .build()
                    ).build()
                upload_resp = self._lark_client.im.v1.file.create(upload_req)

            if not upload_resp.success():
                logger.error(f"File upload failed: {upload_resp.code} {upload_resp.msg}")
                return

            file_key = upload_resp.data.file_key
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("file")
                    .content(json.dumps({"file_key": file_key}))
                    .build()
                ).build()
            self._lark_client.im.v1.message.create(request)

            if caption and caption.strip():
                self._send_text_sync(chat_id, caption.strip())
        except (_requests.exceptions.SSLError, _requests.exceptions.ConnectionError):
            raise
        except Exception as e:
            logger.error(f"Send file failed: {e}")

    def _send_media_items(self, chat_id: str, items: list[dict]) -> None:
        """Send media items (figures, reports) to the Feishu chat."""
        import requests as _requests
        sent = 0
        for item in items:
            fpath = item.get("path", "")
            if not fpath or not Path(fpath).exists():
                logger.warning(f"Media file not found, skipping: {fpath}")
                continue
            try:
                if item["type"] == "photo":
                    self._send_image_file(
                        chat_id, fpath,
                        caption=Path(fpath).stem.replace("_", " ").title(),
                    )
                    sent += 1
                elif item["type"] == "document":
                    if fpath.endswith(".png"):
                        self._send_image_file(chat_id, fpath)
                    else:
                        self._send_document_file(chat_id, fpath)
                    sent += 1
            except (_requests.exceptions.SSLError,
                    _requests.exceptions.ConnectionError) as e:
                logger.warning(f"Network error sending media {fpath}, retrying: {e}")
                time.sleep(2)
                try:
                    if item["type"] == "photo" or fpath.endswith(".png"):
                        self._send_image_file(chat_id, fpath)
                    else:
                        self._send_document_file(chat_id, fpath)
                    sent += 1
                except Exception as e2:
                    logger.error(f"Retry failed for media {fpath}: {e2}")
            except Exception as e:
                logger.error(f"Failed to send media {fpath}: {e}")
        logger.info(f"Sent {sent}/{len(items)} media items to {chat_id}")

    # ── Async helper ─────────────────────────────────────────────────

    def _run_async(self, coro, timeout=None):
        """Submit a coroutine to the background event loop and wait."""
        if not self._loop:
            raise RuntimeError("Feishu channel not started")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ── Process message ──────────────────────────────────────────────

    async def _process_message_async(
        self,
        chat_id: str,
        pure_chat_id: str,
        text: str,
        attachments: list[dict],
        user_id: str | None = None,
    ) -> str:
        """Process a single message through the LLM tool loop."""
        from bot import core

        if attachments:
            content_blocks: list[dict] = []
            for att in attachments:
                if att["type"] == "image":
                    data_url = att["content"]
                    match = re.match(r"data:([^;]+);base64,(.*)", data_url, re.DOTALL)
                    if match:
                        content_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": match.group(1),
                                "data": match.group(2),
                            },
                        })
            if text:
                content_blocks.append({"type": "text", "text": text})
            elif not content_blocks:
                content_blocks.append({"type": "text", "text": "[attachment]"})
            else:
                content_blocks.append({
                    "type": "text",
                    "text": (
                        "[Image sent. If it shows a tissue section (H&E stain, fluorescence, "
                        "spatial barcode array, Visium capture area, or other histology): "
                        "identify the tissue type, staining method, and likely spatial "
                        "transcriptomics platform. Then suggest which OmicsClaw skills "
                        "would be appropriate. If not a tissue section, describe what you see.]"
                    ),
                })
            user_content = content_blocks
        else:
            session_key = f"feishu:{pure_chat_id}"
            local_path_match = re.search(r"\[local path\]\s*(\S+)", text)
            if local_path_match:
                fpath = local_path_match.group(1)
                if Path(fpath).exists():
                    fname = Path(fpath).name
                    core.received_files[session_key] = {"path": fpath, "filename": fname}
            user_content = text

        async def _progress(msg: str):
            return self._send_text_sync(chat_id, core.strip_markup(msg))

        async def _progress_update(handle, msg: str):
            if handle:
                self._update_text(handle, core.strip_markup(msg))

        reply = await core.llm_tool_loop(
            pure_chat_id,
            user_content,
            user_id=user_id,
            platform="feishu",
            progress_fn=_progress,
            progress_update_fn=_progress_update,
        )

        if core.pending_text:
            reply = "\n\n".join(core.pending_text)
            core.pending_text.clear()

        return reply

    # ── Event handler ────────────────────────────────────────────────

    def _handle_event(self, data) -> None:
        """Synchronous handler called by lark-oapi event dispatcher."""
        from bot import core
        try:
            event = data.event
            message = event.message
            sender = event.sender

            chat_id = message.chat_id
            message_id = message.message_id
            chat_type = message.chat_type
            sender_id = sender.sender_id.open_id if sender and sender.sender_id else ""

            if not chat_id or not message_id:
                return
            if self._is_duplicate_feishu(message_id):
                return
            if not message.content:
                return

            # Ignore messages sent before bot startup
            if hasattr(message, 'create_time') and message.create_time:
                msg_time = int(message.create_time) / 1000.0
                if msg_time < self._bot_start_time:
                    logger.info(f"Ignoring cached message from before bot startup: {message_id}")
                    return

            # Rate limiting
            if not self.check_rate_limit(sender_id):
                self._send_text_sync(
                    chat_id,
                    f"Rate limit reached ({self.config.rate_limit_per_hour} messages/hour). "
                    "Please try again later.",
                )
                return

            msg_dict = {
                "message_id": message_id,
                "message_type": message.message_type,
                "content": message.content,
            }
            text, attachments = self._parse_message(msg_dict)

            # Group chat: respond only when appropriate
            if chat_type == "group":
                mentions = message.mentions or []
                cleaned = re.sub(r"@_user_\d+\s*", "", text).strip()

                mentioned = len(mentions) > 0
                member_count = self._get_group_member_count(chat_id)
                is_two_person_group = member_count == 2

                if is_two_person_group:
                    text = cleaned
                else:
                    if not mentioned:
                        return
                    text = cleaned

            logger.info(f"Feishu message: chat_type={chat_type} text={text[:100]}")
            core.audit(
                "message",
                platform="feishu",
                chat_id=chat_id,
                text_preview=text[:200],
            )

            # Thinking placeholder
            placeholder_id = ""
            placeholder_lock = threading.Lock()
            done_event = threading.Event()

            def _send_thinking():
                nonlocal placeholder_id
                if done_event.is_set():
                    return
                mid = self._send_text_sync(chat_id, "正在分析…")
                if mid:
                    with placeholder_lock:
                        placeholder_id = mid

            timer = None
            if self.feishu_config.thinking_threshold_ms > 0:
                timer = threading.Timer(
                    self.feishu_config.thinking_threshold_ms / 1000,
                    _send_thinking,
                )
                timer.start()

            try:
                pure_chat_id = sender_id if chat_type == 'p2p' else chat_id
                reply = self._run_async(
                    self._process_message_async(
                        chat_id, pure_chat_id, text, attachments, sender_id,
                    ),
                    timeout=None,
                )
            except Exception as e:
                logger.error(f"Message processing error: {e}", exc_info=True)
                reply = "抱歉，处理消息时出错了。错误已记录，请稍后重试。"
            finally:
                done_event.set()
                if timer:
                    timer.cancel()

            # Retrieve media items
            pure_chat_id = sender_id if chat_type == 'p2p' else chat_id
            if sender_id:
                session_id = f"feishu:{sender_id}:{pure_chat_id}"
            else:
                session_id = f"feishu::{pure_chat_id}"

            media_items = core.pending_media.pop(session_id, [])
            if media_items:
                logger.info(
                    f"Captured {len(media_items)} pending media items: "
                    f"{[item.get('path', '?') for item in media_items]}"
                )

            reply_text = core.strip_markup(reply or "")

            if not reply_text.strip():
                with placeholder_lock:
                    if placeholder_id:
                        try:
                            self._delete_message(placeholder_id)
                        except Exception:
                            pass
                return

            # Add Feishu emoji
            reply_text = reply_text.strip() + " [看]"

            # Send media items first
            if media_items:
                with placeholder_lock:
                    if placeholder_id:
                        try:
                            self._update_text(placeholder_id, "✓ 分析完成，正在发送结果…")
                        except Exception:
                            pass
                        placeholder_id = ""
                self._send_media_items(chat_id, media_items)
                if reply_text.strip():
                    self._send_long_text(chat_id, reply_text)
                return

            # Text-only reply
            with placeholder_lock:
                pid = placeholder_id
            if pid:
                if not self._update_text(pid, reply_text):
                    self._send_long_text(chat_id, reply_text)
                return

            self._send_long_text(chat_id, reply_text)

        except Exception as e:
            logger.error(f"Feishu message handler error: {e}", exc_info=True)
