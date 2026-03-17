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
    GetChatRequest,
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

# Bot startup time (to filter old cached messages)
_BOT_START_TIME = time.time()

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
_FEISHU_MAX_TEXT_LEN = 4000  # Safe limit for Feishu text messages


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
# Rate limiting
# ---------------------------------------------------------------------------

RATE_LIMIT_PER_HOUR = int(os.environ.get("FEISHU_RATE_LIMIT_PER_HOUR", "60"))
_rate_buckets: dict[str, list[float]] = {}


def _check_rate_limit(sender_id: str) -> bool:
    """Return True if the sender is within rate limits."""
    if RATE_LIMIT_PER_HOUR <= 0:
        return True
    now = time.time()
    bucket = _rate_buckets.setdefault(sender_id, [])
    bucket[:] = [t for t in bucket if now - t < 3600]
    if len(bucket) >= RATE_LIMIT_PER_HOUR:
        return False
    bucket.append(now)
    return True


# ---------------------------------------------------------------------------
# Group member count cache
# ---------------------------------------------------------------------------

_group_member_count: dict[str, tuple[int, float]] = {}
_MEMBER_COUNT_TTL = 3600  # Cache for 1 hour


def _get_group_member_count(chat_id: str) -> int:
    """Get group member count with caching."""
    now = time.time()

    # Check cache
    if chat_id in _group_member_count:
        count, timestamp = _group_member_count[chat_id]
        if now - timestamp < _MEMBER_COUNT_TTL:
            return count

    # Fetch from API
    try:
        request = GetChatRequest.builder().chat_id(chat_id).build()
        response = _lark_client.im.v1.chat.get(request)

        if response.success() and response.data:
            # Get user_count and bot_count (both are strings)
            user_count = int(response.data.user_count or 0)
            bot_count = int(response.data.bot_count or 0)
            member_count = user_count + bot_count

            _group_member_count[chat_id] = (member_count, now)
            logger.info(f"Group {chat_id} has {member_count} members ({user_count} users + {bot_count} bots)")
            return member_count
    except Exception as e:
        logger.warning(f"Failed to get group member count: {e}")

    # Default to 3+ (assume normal group) if API fails
    return 3


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

def _send_text(chat_id: str, text: str, retries: int = 3) -> str | None:
    """Send a text message with retry for transient network errors. Returns message_id or None."""
    import requests as _requests

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
            response = _lark_client.im.v1.message.create(request)
            if not response.success():
                logger.error(f"Send text failed: {response.code} {response.msg}")
                return None
            return response.data.message_id if response.data else None
        except (_requests.exceptions.SSLError,
                _requests.exceptions.ConnectionError) as e:
            if attempt < retries:
                wait = attempt * 2
                logger.warning(f"Send text attempt {attempt}/{retries} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Send text failed after {retries} attempts: {e}")
                return None


def _update_text(message_id: str, text: str) -> bool:
    """Update an existing message. Returns True on success."""
    request = UpdateMessageRequest.builder() \
        .message_id(message_id) \
        .request_body(
            UpdateMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        ).build()
    try:
        response = _lark_client.im.v1.message.update(request)
        if not response.success():
            logger.warning(f"Update text failed: {response.code} {response.msg}")
            return False
        return True
    except Exception as e:
        logger.warning(f"Update text error: {e}")
        return False


def _delete_message(message_id: str):
    request = DeleteMessageRequest.builder() \
        .message_id(message_id) \
        .build()
    _lark_client.im.v1.message.delete(request)


def _send_long_text(chat_id: str, text: str) -> str | None:
    """Send a text message, splitting into chunks if it exceeds Feishu limits."""
    if len(text) <= _FEISHU_MAX_TEXT_LEN:
        return _send_text(chat_id, text)

    first_mid = None
    while text:
        if len(text) <= _FEISHU_MAX_TEXT_LEN:
            chunk = text
            text = ""
        else:
            split_at = text.rfind("\n\n", 0, _FEISHU_MAX_TEXT_LEN)
            if split_at == -1:
                split_at = text.rfind("\n", 0, _FEISHU_MAX_TEXT_LEN)
            if split_at == -1:
                split_at = _FEISHU_MAX_TEXT_LEN
            chunk = text[:split_at]
            text = text[split_at:].lstrip("\n")
        if chunk.strip():
            mid = _send_text(chat_id, chunk.strip())
            if first_mid is None:
                first_mid = mid
    return first_mid


def _send_image_file(chat_id: str, filepath: str, caption: str | None = None):
    """Upload a local image file and send it to the chat."""
    import requests as _requests
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
    except (_requests.exceptions.SSLError, _requests.exceptions.ConnectionError):
        raise  # Let caller handle retries
    except Exception as e:
        logger.error(f"Send image failed: {e}")


def _send_document_file(chat_id: str, filepath: str, caption: str | None = None):
    """Upload and send a non-image file."""
    import requests as _requests
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
    except (_requests.exceptions.SSLError, _requests.exceptions.ConnectionError):
        raise  # Let caller handle retries
    except Exception as e:
        logger.error(f"Send file failed: {e}")


def _send_media_items(chat_id: str, items: list[dict]):
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
                _send_image_file(chat_id, fpath, caption=Path(fpath).stem.replace("_", " ").title())
                sent += 1
            elif item["type"] == "document":
                if fpath.endswith(".png"):
                    _send_image_file(chat_id, fpath)
                    sent += 1
                else:
                    _send_document_file(chat_id, fpath)
                    sent += 1
        except (_requests.exceptions.SSLError,
                _requests.exceptions.ConnectionError) as e:
            logger.warning(f"Network error sending media {fpath}, retrying: {e}")
            time.sleep(2)
            try:
                if item["type"] == "photo" or fpath.endswith(".png"):
                    _send_image_file(chat_id, fpath)
                else:
                    _send_document_file(chat_id, fpath)
                sent += 1
            except Exception as e2:
                logger.error(f"Retry failed for media {fpath}: {e2}")
        except Exception as e:
            logger.error(f"Failed to send media {fpath}: {e}")

    logger.info(f"Sent {sent}/{len(items)} media items to {chat_id}")


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------

async def _process_message_async(
    chat_id: str,
    pure_chat_id: str,  # Pure chat_id without platform prefix
    text: str,
    attachments: list[dict],
    user_id: str = None,
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
        # Use session_key for received_files (needs platform prefix)
        session_key = f"feishu:{pure_chat_id}"
        local_path_match = re.search(r"\[local path\]\s*(\S+)", text)
        if local_path_match:
            fpath = local_path_match.group(1)
            if Path(fpath).exists():
                fname = Path(fpath).name
                core.received_files[session_key] = {"path": fpath, "filename": fname}

        user_content = text

    # Create progress callbacks to notify user about long-running tasks
    async def _progress(msg: str):
        """Send progress message, return message_id as handle."""
        return _send_text(chat_id, core.strip_markup(msg))

    async def _progress_update(handle, msg: str):
        """Update a previously sent progress message."""
        if handle:
            _update_text(handle, core.strip_markup(msg))

    reply = await core.llm_tool_loop(
        pure_chat_id,  # Pass pure chat_id, llm_tool_loop will construct session_id
        user_content,
        user_id=user_id,
        platform="feishu",
        progress_fn=_progress,
        progress_update_fn=_progress_update,
    )

    if core.pending_text:
        reply = "\n\n".join(core.pending_text)
        core.pending_text.clear()

    # Don't pop pending_media here - let the outer handler do it
    # This prevents race conditions when timeout occurs
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

        # Ignore messages sent before bot startup (cached messages)
        if hasattr(message, 'create_time') and message.create_time:
            # create_time is in milliseconds
            msg_time = int(message.create_time) / 1000.0
            if msg_time < _BOT_START_TIME:
                logger.info(f"Ignoring cached message from before bot startup: {message_id}")
                return

        # Rate limiting (after dedup to avoid counting retries)
        if not _check_rate_limit(sender_id):
            _send_text(chat_id, f"Rate limit reached ({RATE_LIMIT_PER_HOUR} messages/hour). Please try again later.")
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

            # Check if it's a 2-person group (1 user + 1 bot)
            member_count = _get_group_member_count(chat_id)
            is_two_person_group = member_count == 2

            # In 2-person groups, always respond (no need to @)
            if is_two_person_group:
                text = cleaned
            else:
                # Normal group (3+ members): only respond when @mentioned
                if not mentioned:
                    return
                text = cleaned

        session_key = f"feishu:{sender_id if chat_type == 'p2p' else chat_id}"

        logger.info(f"Feishu message: chat_type={chat_type} text={text[:100]}")
        core.audit("message", platform="feishu", chat_id=chat_id,
                    text_preview=text[:200])

        # Thinking placeholder (thread-safe)
        placeholder_id = ""
        placeholder_lock = threading.Lock()
        done_event = threading.Event()

        def _send_thinking():
            nonlocal placeholder_id
            if done_event.is_set():
                return
            mid = _send_text(chat_id, "正在分析…")
            if mid:
                with placeholder_lock:
                    placeholder_id = mid

        timer = None
        if THINKING_THRESHOLD_MS > 0:
            timer = threading.Timer(THINKING_THRESHOLD_MS / 1000, _send_thinking)
            timer.start()

        try:
            # Pass pure chat_id (not session_key) to llm_tool_loop
            # llm_tool_loop will construct session_id internally as f"{platform}:{user_id}:{chat_id}"
            # No timeout — wait until analysis completes
            reply = _run_async(
                _process_message_async(chat_id, sender_id if chat_type == 'p2p' else chat_id, text, attachments, sender_id),
                timeout=None,
            )
        except Exception as e:
            logger.error(f"Message processing error: {e}", exc_info=True)
            reply = f"抱歉，处理消息时出错了。错误已记录，请稍后重试。"
        finally:
            done_event.set()
            if timer:
                timer.cancel()

        # Always try to retrieve media items, even after timeout/error
        # This must be done AFTER the async call completes or times out
        pure_chat_id = sender_id if chat_type == 'p2p' else chat_id
        if sender_id:
            session_id = f"feishu:{sender_id}:{pure_chat_id}"
        else:
            session_id = f"feishu::{pure_chat_id}"

        media_items = core.pending_media.pop(session_id, [])
        if media_items:
            logger.info(f"Captured {len(media_items)} pending media items: "
                         f"{[item.get('path', '?') for item in media_items]}")

        reply_text = core.strip_markup(reply or "")

        if not reply_text.strip():
            with placeholder_lock:
                if placeholder_id:
                    try:
                        _delete_message(placeholder_id)
                    except Exception:
                        pass
            return

        # Add Feishu emoji to reply
        reply_text = reply_text.strip() + " [看]"

        # Send media items first (captured atomically from _process_message_async)
        if media_items:
            with placeholder_lock:
                if placeholder_id:
                    try:
                        # Update placeholder instead of deleting it
                        _update_text(placeholder_id, "✓ 分析完成，正在发送结果…")
                    except Exception:
                        pass
                    placeholder_id = ""
            _send_media_items(chat_id, media_items)
            if reply_text.strip():
                _send_long_text(chat_id, reply_text)
            return

        # Text-only reply
        with placeholder_lock:
            pid = placeholder_id
        if pid:
            if not _update_text(pid, reply_text):
                # Update failed, send as new message instead
                _send_long_text(chat_id, reply_text)
            return

        _send_long_text(chat_id, reply_text)

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
