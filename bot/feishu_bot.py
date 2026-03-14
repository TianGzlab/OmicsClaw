#!/usr/bin/env python3
"""
feishu_bot.py — OmicsClaw Feishu (Lark) Bot
============================================
Feishu frontend for OmicsClaw multi-omics skills.
Uses lark-oapi Python SDK with WebSocket long-connection (no public IP required).
Shares the core LLM engine with the Telegram bot via bot/core.py.

Prerequisites:
    pip install -r bot/requirements.txt

Usage:
    python bot/feishu_bot.py
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
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateImageRequest,
    CreateImageRequestBody,
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageResourceRequest,
    UpdateMessageRequest,
    UpdateMessageRequestBody,
    DeleteMessageRequest,
    CreateFileRequest,
    CreateFileRequestBody,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bot import core  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_dotenv_candidates = [_PROJECT_ROOT / ".env", Path.cwd() / ".env"]
for _p in _dotenv_candidates:
    if _p.exists():
        from dotenv import load_dotenv
        load_dotenv(str(_p))
        break

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "")
OMICSCLAW_MODEL = os.environ.get("OMICSCLAW_MODEL", os.environ.get("SPATIALCLAW_MODEL", ""))
THINKING_THRESHOLD_MS = int(os.environ.get("FEISHU_THINKING_THRESHOLD_MS", "2500"))
MAX_INBOUND_IMAGE_MB = int(os.environ.get("FEISHU_MAX_INBOUND_IMAGE_MB", "12"))
MAX_INBOUND_FILE_MB = int(os.environ.get("FEISHU_MAX_INBOUND_FILE_MB", "40"))
MAX_ATTACHMENTS = int(os.environ.get("FEISHU_MAX_ATTACHMENTS", "4"))
DEBUG = os.environ.get("FEISHU_BRIDGE_DEBUG", "") == "1"

if not FEISHU_APP_ID:
    print("Error: FEISHU_APP_ID not set. See bot/README.md for setup.")
    sys.exit(1)
if not FEISHU_APP_SECRET:
    print("Error: FEISHU_APP_SECRET not set. See bot/README.md for setup.")
    sys.exit(1)
if not LLM_API_KEY:
    print("Error: LLM_API_KEY not set. See bot/README.md for setup.")
    sys.exit(1)

core.init(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL or None,
    model=OMICSCLAW_MODEL,
    provider=LLM_PROVIDER,
)

logger = logging.getLogger("omicsclaw.bot.feishu")

# Feishu API client (for sending messages / uploading media)
_lark_client = lark.Client.builder() \
    .app_id(FEISHU_APP_ID) \
    .app_secret(FEISHU_APP_SECRET) \
    .log_level(lark.LogLevel.DEBUG if DEBUG else lark.LogLevel.INFO) \
    .build()

# ---------------------------------------------------------------------------
# Async event loop (runs in a background thread)
# ---------------------------------------------------------------------------

_loop = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_loop_thread.start()


def _run_async(coro, timeout=300):
    """Submit a coroutine to the background event loop and wait for result."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=timeout)


# ---------------------------------------------------------------------------
# Message dedup
# ---------------------------------------------------------------------------

_seen: dict[str, float] = {}
_SEEN_TTL = 600


def _is_duplicate(message_id: str) -> bool:
    now = time.time()
    expired = [k for k, ts in _seen.items() if now - ts > _SEEN_TTL]
    for k in expired:
        del _seen[k]
    if not message_id:
        return False
    if message_id in _seen:
        return True
    _seen[message_id] = now
    return False


# ---------------------------------------------------------------------------
# Feishu message parsing
# ---------------------------------------------------------------------------

def _normalize_text(raw: str) -> str:
    t = str(raw or "")
    t = re.sub(r"<\s*br\s*/?>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<\s*/p\s*>\s*<\s*p\s*>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    t = t.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _extract_post_text(post_json: dict) -> tuple[str, list[str]]:
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
        # Fallback: recurse into values
        acc = ""
        for v in node.values():
            if isinstance(v, (dict, list)):
                acc += inline(v)
        return acc

    title = post_json.get("title", "")
    if title:
        lines.append(_normalize_text(title))

    content = post_json.get("content")
    if isinstance(content, list):
        for para in content:
            if isinstance(para, list):
                joined = "".join(inline(n) for n in para)
            else:
                joined = inline(para)
            normalized = _normalize_text(joined)
            if normalized:
                lines.append(normalized)
    elif content:
        normalized = _normalize_text(inline(content))
        if normalized:
            lines.append(normalized)

    return "\n".join(lines).strip(), list(set(image_keys))


def _download_image_as_b64(message_id: str, image_key: str) -> str | None:
    """Download a Feishu image and return as base64 data URL."""
    try:
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(image_key) \
            .type("image") \
            .build()

        response = _lark_client.im.v1.message_resource.get(request)
        if not response.success():
            logger.warning(f"Image download failed: {response.code} {response.msg}")
            return None

        tmp = Path(tempfile.gettempdir()) / f"feishu_recv_{time.time_ns()}.png"
        tmp.write_bytes(response.file.read())

        size = tmp.stat().st_size
        max_bytes = MAX_INBOUND_IMAGE_MB * 1024 * 1024
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


def _download_file_to_tmp(message_id: str, file_key: str, filename: str = "file.bin") -> str | None:
    """Download a Feishu file to a temp path and return the path."""
    try:
        request = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(file_key) \
            .type("file") \
            .build()

        response = _lark_client.im.v1.message_resource.get(request)
        if not response.success():
            logger.warning(f"File download failed: {response.code} {response.msg}")
            return None

        ext = Path(filename).suffix or ".bin"
        tmp = Path(tempfile.gettempdir()) / f"feishu_recv_{time.time_ns()}{ext}"
        tmp.write_bytes(response.file.read())

        size = tmp.stat().st_size
        max_bytes = MAX_INBOUND_FILE_MB * 1024 * 1024
        if size > max_bytes:
            logger.warning(f"File too large: {size} bytes > {max_bytes}")
            tmp.unlink(missing_ok=True)
            return None

        return str(tmp)
    except Exception as e:
        logger.error(f"File download error: {e}")
        return None


def _parse_feishu_message(message: dict) -> tuple[str, list[dict]]:
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
        return _normalize_text(raw_content), attachments

    if message_type == "text":
        text = _normalize_text(parsed.get("text", ""))

    elif message_type == "post":
        post_text, image_keys = _extract_post_text(parsed)
        text = post_text
        for k in image_keys[:MAX_ATTACHMENTS]:
            data_url = _download_image_as_b64(message_id, k)
            if data_url:
                attachments.append({"type": "image", "content": data_url})

    elif message_type == "image":
        image_key = parsed.get("image_key", "")
        if image_key and message_id:
            data_url = _download_image_as_b64(message_id, image_key)
            if data_url:
                attachments.append({"type": "image", "content": data_url})
        text = "[image]"

    elif message_type == "file":
        file_key = parsed.get("file_key", "")
        fname = parsed.get("file_name", "file.bin")
        text = f"[file] {fname}"
        if file_key and message_id:
            fp = _download_file_to_tmp(message_id, file_key, fname)
            if fp:
                text += f"\n\n[local path] {fp}"

    elif message_type == "audio":
        file_key = parsed.get("file_key", "")
        fname = parsed.get("file_name", "audio.opus")
        text = f"[audio] {fname}"
        if file_key and message_id:
            fp = _download_file_to_tmp(message_id, file_key, fname)
            if fp:
                text += f"\n\n[local path] {fp}"

    elif message_type == "media":
        file_key = parsed.get("file_key", "")
        fname = parsed.get("file_name", "video.bin")
        text = f"[video] {fname}"
        if file_key and message_id:
            fp = _download_file_to_tmp(message_id, file_key, fname)
            if fp:
                text += f"\n\n[local path] {fp}"

    if not text and attachments:
        text = "[attachment]"
    if not text:
        text = f"[{message_type} message]"

    return text, attachments


# ---------------------------------------------------------------------------
# Group chat intent filter
# ---------------------------------------------------------------------------

_REQUEST_VERBS = [
    "帮", "麻烦", "请", "能否", "可以", "解释", "看看", "排查",
    "分析", "总结", "写", "改", "修", "查", "对比", "翻译",
    "preprocess", "analyze", "run", "demo",
]


def _should_respond_in_group(text: str, mentions: list) -> bool:
    if mentions:
        return True
    if re.search(r"[？?]$", text):
        return True
    if re.search(r"\b(why|how|what|when|where|who|help)\b", text, re.IGNORECASE):
        return True
    if any(v in text for v in _REQUEST_VERBS):
        return True
    if re.match(r"^(omicsclaw|spatialclaw|bot|助手|智能体)[\s,:，：]", text, re.IGNORECASE):
        return True
    return False


# ---------------------------------------------------------------------------
# Feishu sending
# ---------------------------------------------------------------------------

def _send_text(chat_id: str, text: str) -> str | None:
    """Send a text message. Returns message_id or None."""
    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        ).build()

    response = _lark_client.im.v1.message.create(request)
    if not response.success():
        logger.error(f"Send text failed: {response.code} {response.msg}")
        return None
    return response.data.message_id if response.data else None


def _update_text(message_id: str, text: str):
    request = UpdateMessageRequest.builder() \
        .message_id(message_id) \
        .request_body(
            UpdateMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        ).build()
    _lark_client.im.v1.message.update(request)


def _delete_message(message_id: str):
    request = DeleteMessageRequest.builder() \
        .message_id(message_id) \
        .build()
    _lark_client.im.v1.message.delete(request)


def _send_image_file(chat_id: str, filepath: str, caption: str | None = None):
    """Upload a local image file and send it to the chat."""
    try:
        with open(filepath, "rb") as f:
            upload_req = CreateImageRequest.builder() \
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(f)
                    .build()
                ).build()
            upload_resp = _lark_client.im.v1.image.create(upload_req)

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
        _lark_client.im.v1.message.create(request)

        if caption and caption.strip():
            _send_text(chat_id, caption.strip())
    except Exception as e:
        logger.error(f"Send image failed: {e}")


def _send_document_file(chat_id: str, filepath: str, caption: str | None = None):
    """Upload and send a non-image file."""
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
            upload_resp = _lark_client.im.v1.file.create(upload_req)

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
        _lark_client.im.v1.message.create(request)

        if caption and caption.strip():
            _send_text(chat_id, caption.strip())
    except Exception as e:
        logger.error(f"Send file failed: {e}")


def _send_pending_media(chat_id: str):
    """Send any queued media items to the Feishu chat."""
    items = core.pending_media.pop(0, [])
    for item in items:
        try:
            fpath = item.get("path", "")
            if not fpath or not Path(fpath).exists():
                continue
            if item["type"] == "photo":
                _send_image_file(chat_id, fpath, caption=Path(fpath).stem.replace("_", " ").title())
            elif item["type"] == "document":
                if fpath.endswith(".png"):
                    _send_image_file(chat_id, fpath)
                else:
                    _send_document_file(chat_id, fpath)
        except Exception as e:
            logger.warning(f"Failed to send media {item.get('path')}: {e}")


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------

async def _process_message_async(
    chat_id: str,
    session_key: str,
    text: str,
    attachments: list[dict],
):
    """Process a single message through the LLM tool loop."""
    # Build content blocks
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
        # Check if message contains a file path -> register as received file
        local_path_match = re.search(r"\[local path\]\s*(\S+)", text)
        if local_path_match:
            fpath = local_path_match.group(1)
            if Path(fpath).exists():
                fname = Path(fpath).name
                core.received_files[session_key] = {"path": fpath, "filename": fname}

        user_content = text

    reply = await core.llm_tool_loop(session_key, user_content)

    if core.pending_text:
        reply = "\n\n".join(core.pending_text)
        core.pending_text.clear()

    return reply


def _handle_feishu_event(data: lark.im.v1.P2ImMessageReceiveV1):
    """Synchronous handler called by lark-oapi event dispatcher."""
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
        if _is_duplicate(message_id):
            return
        if not message.content:
            return

        msg_dict = {
            "message_id": message_id,
            "message_type": message.message_type,
            "content": message.content,
        }
        text, attachments = _parse_feishu_message(msg_dict)

        # Group chat: respond only when appropriate
        if chat_type == "group":
            mentions = message.mentions or []
            cleaned = re.sub(r"@_user_\d+\s*", "", text).strip()

            has_attachment = len(attachments) > 0
            mentioned = len(mentions) > 0

            if has_attachment and not mentioned and cleaned in ("[image]", "[attachment]", ""):
                return
            if not has_attachment and not _should_respond_in_group(cleaned, mentions):
                return
            text = cleaned

        session_key = f"feishu:{sender_id if chat_type == 'p2p' else chat_id}"

        logger.info(f"Feishu message: chat_type={chat_type} text={text[:100]}")
        core.audit("message", platform="feishu", chat_id=chat_id,
                    text_preview=text[:200])

        # Thinking placeholder
        placeholder_id = ""
        done = False

        def _send_thinking():
            nonlocal placeholder_id
            if done:
                return
            mid = _send_text(chat_id, "正在分析…")
            if mid:
                placeholder_id = mid

        timer = None
        if THINKING_THRESHOLD_MS > 0:
            timer = threading.Timer(THINKING_THRESHOLD_MS / 1000, _send_thinking)
            timer.start()

        try:
            reply = _run_async(
                _process_message_async(chat_id, session_key, text, attachments),
                timeout=300,
            )
        except Exception as e:
            reply = f"(system error) {e}"
        finally:
            done = True
            if timer:
                timer.cancel()

        reply_text = core.strip_markup(reply or "")

        if not reply_text.strip():
            if placeholder_id:
                try:
                    _delete_message(placeholder_id)
                except Exception:
                    pass
            return

        # Send pending media first
        media_items = core.pending_media.get(0, [])
        if media_items:
            if placeholder_id:
                try:
                    _delete_message(placeholder_id)
                except Exception:
                    pass
                placeholder_id = ""
            _send_pending_media(chat_id)
            if reply_text.strip():
                _send_text(chat_id, reply_text)
            return

        # Text-only reply
        if placeholder_id:
            try:
                _update_text(placeholder_id, reply_text)
                return
            except Exception:
                pass

        _send_text(chat_id, reply_text)

    except Exception as e:
        logger.error(f"Feishu message handler error: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info(f"Starting OmicsClaw Feishu bot (provider: {core.LLM_PROVIDER_NAME}, model: {core.OMICSCLAW_MODEL})")
    logger.info(f"OmicsClaw directory: {core.OMICSCLAW_DIR}")
    logger.info(f"Feishu App ID: {FEISHU_APP_ID}")
    if LLM_BASE_URL:
        logger.info(f"LLM base URL: {LLM_BASE_URL}")
    core.audit("bot_start", platform="feishu", provider=core.LLM_PROVIDER_NAME,
               model=core.OMICSCLAW_MODEL, feishu_app_id=FEISHU_APP_ID)

    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(_handle_feishu_event) \
        .build()

    ws_client = lark.ws.Client(
        FEISHU_APP_ID,
        FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG if DEBUG else lark.LogLevel.INFO,
    )

    print("OmicsClaw Feishu bot is running. Press Ctrl+C to stop.")
    ws_client.start()


if __name__ == "__main__":
    main()
