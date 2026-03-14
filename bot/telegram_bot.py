#!/usr/bin/env python3
"""
telegram_bot.py — OmicsClaw Telegram Bot
========================================
Telegram frontend for OmicsClaw multi-omics skills.
Uses the shared core engine (bot/core.py) for LLM reasoning and skill execution.

Prerequisites:
    pip install -r bot/requirements.txt

Usage:
    python bot/telegram_bot.py
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Ensure the project root is on sys.path so ``import bot.core`` works when
# this script is executed directly (``python bot/telegram_bot.py``).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bot import core  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_dotenv_candidates = [
    _PROJECT_ROOT / ".env",
    Path.cwd() / ".env",
]
for _p in _dotenv_candidates:
    if _p.exists():
        from dotenv import load_dotenv
        load_dotenv(str(_p))
        break

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0") or "0")
LLM_API_KEY = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "")
OMICSCLAW_MODEL = os.environ.get("OMICSCLAW_MODEL", os.environ.get("SPATIALCLAW_MODEL", ""))
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "10"))

if not TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN not set. See bot/README.md for setup.")
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

logger = logging.getLogger("omicsclaw.bot.telegram")


# ---------------------------------------------------------------------------
# Redact bot token from log output
# ---------------------------------------------------------------------------

class _TokenRedactFilter(logging.Filter):
    def __init__(self, token: str):
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        if self._token and self._token in record.getMessage():
            record.msg = str(record.msg).replace(self._token, "[REDACTED]")
            if isinstance(record.args, tuple):
                record.args = tuple(
                    str(a).replace(self._token, "[REDACTED]") for a in record.args
                )
        return True


if TELEGRAM_BOT_TOKEN:
    _redact = _TokenRedactFilter(TELEGRAM_BOT_TOKEN)
    for _ln in ("httpx", "telegram", "httpcore"):
        logging.getLogger(_ln).addFilter(_redact)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_admin(update: Update) -> bool:
    return bool(ADMIN_CHAT_ID) and update.effective_chat.id == ADMIN_CHAT_ID


_rate_buckets: dict[int, list[float]] = {}


def _check_rate_limit(update: Update) -> bool:
    if RATE_LIMIT_PER_HOUR <= 0 or is_admin(update):
        return True
    uid = update.effective_user.id if update.effective_user else update.effective_chat.id
    now = time.time()
    bucket = _rate_buckets.setdefault(uid, [])
    bucket[:] = [t for t in bucket if now - t < 3600]
    if len(bucket) >= RATE_LIMIT_PER_HOUR:
        return False
    bucket.append(now)
    return True


async def _rate_limit_reply(update: Update) -> None:
    core.audit("rate_limited", user_id=update.effective_user.id if update.effective_user else None)
    await update.message.reply_text(
        f"You've reached the limit of {RATE_LIMIT_PER_HOUR} messages per hour. "
        "Please try again later."
    )


async def send_long_message(update: Update, text: str):
    text = core.strip_markup(text)
    MAX_LEN = 4096
    if len(text) <= MAX_LEN:
        await update.message.reply_text(text)
        return
    chunks = []
    while text:
        if len(text) <= MAX_LEN:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, MAX_LEN)
        if split_at == -1:
            split_at = text.rfind("\n", 0, MAX_LEN)
        if split_at == -1:
            split_at = MAX_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    for chunk in chunks:
        if chunk.strip():
            await update.message.reply_text(chunk)


async def _drain_pending_media(update: Update, context) -> None:
    items = core.pending_media.pop(0, [])
    if not items:
        return
    chat_id = update.effective_chat.id
    for item in items:
        try:
            path = Path(item["path"])
            if not path.exists():
                continue
            if item["type"] == "document":
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=open(path, "rb"),
                    filename=path.name,
                )
            elif item["type"] == "photo":
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=open(path, "rb"),
                    caption=path.stem.replace("_", " ").title(),
                )
        except Exception as e:
            logger.warning(f"Failed to send media {item['path']}: {e}")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to OmicsClaw -- multi-omics analysis at your fingertips!\n\n"
        "I can analyze spatial, single-cell, genomics, proteomics, and metabolomics data "
        "through a unified skill system.\n\n"
        "Commands:\n"
        "  /skills  -- list available analysis skills\n"
        "  /demo <skill>  -- run a demo (preprocess, domains, de, genes, statistics, ...)\n"
        "  /status  -- bot info\n"
        "  /health  -- system health check\n\n"
        "Or just chat -- ask any multi-omics analysis question.\n"
        "Upload data files for personalized analysis.\n"
        "Send an image when you need tissue/platform identification.\n\n"
        "OmicsClaw is a research tool, not a medical device. "
        "Consult a domain expert before making decisions based on these results."
    )


async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(core.OMICSCLAW_PY), "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(core.OMICSCLAW_DIR),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode(errors="replace").strip()
        await send_long_message(update, output or "No skills found.")
    except Exception as e:
        await update.message.reply_text(f"Error listing skills: {e}")


async def cmd_demo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_rate_limit(update):
        await _rate_limit_reply(update)
        return
    skill = context.args[0] if context.args else "preprocess"
    await update.message.reply_text(f"Running {skill} demo -- this may take a moment...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        reply = await core.llm_tool_loop(
            update.effective_chat.id,
            f"Run the {skill} demo using the omicsclaw tool with mode='demo'."
        )
        if core.pending_text:
            reply = "\n\n".join(core.pending_text)
            core.pending_text.clear()
        await send_long_message(update, reply)
        await _drain_pending_media(update, context)
    except Exception as e:
        logger.error(f"Demo error: {e}", exc_info=True)
        await update.message.reply_text(f"Demo failed: {e}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime_secs = int(time.time() - core.BOT_START_TIME)
    hours, remainder = divmod(uptime_secs, 3600)
    minutes, secs = divmod(remainder, 60)

    skills_dir = core.OMICSCLAW_DIR / "skills"
    skill_count = sum(
        1 for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    ) if skills_dir.exists() else 0

    provider_label = core.LLM_PROVIDER_NAME or "auto"
    status_msg = (
        f"OmicsClaw Bot Status\n"
        f"====================\n"
        f"Bot uptime: {hours}h {minutes}m {secs}s\n"
        f"LLM provider: {provider_label}\n"
        f"LLM model: {core.OMICSCLAW_MODEL}\n"
        f"Skills available: {skill_count}\n"
        f"OmicsClaw dir: {core.OMICSCLAW_DIR}\n"
    )
    if LLM_BASE_URL:
        status_msg += f"LLM endpoint: {LLM_BASE_URL}\n"
    await update.message.reply_text(status_msg)


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    checks = []
    if core.OMICSCLAW_PY.exists():
        checks.append("OmicsClaw CLI: OK")
    else:
        checks.append("OmicsClaw CLI: MISSING")

    if core.SOUL_MD.exists():
        checks.append("SOUL.md: OK")
    else:
        checks.append("SOUL.md: MISSING (using fallback)")

    skills_dir = core.OMICSCLAW_DIR / "skills"
    if skills_dir.exists():
        implemented = [d.name for d in sorted(skills_dir.iterdir())
                       if d.is_dir() and (d / "SKILL.md").exists() and any(d.glob("*.py"))]
        checks.append(f"Skills (implemented): {len(implemented)}")
    else:
        checks.append("Skills directory: MISSING")

    if core.OUTPUT_DIR.exists():
        output_count = sum(1 for _ in core.OUTPUT_DIR.iterdir())
        checks.append(f"Output runs: {output_count}")
    else:
        checks.append("Output directory: not yet created")

    await update.message.reply_text(
        "OmicsClaw Health Check\n"
        "======================\n" + "\n".join(checks)
    )


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_rate_limit(update):
        await _rate_limit_reply(update)
        return
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    logger.info(f"Message from {update.effective_user.first_name}: {user_text[:100]}")
    core.audit("message", user_id=update.effective_user.id if update.effective_user else None,
               text_preview=user_text[:200])

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        reply = await core.llm_tool_loop(update.effective_chat.id, user_text)
        if core.pending_text:
            reply = "\n\n".join(core.pending_text)
            core.pending_text.clear()
        await send_long_message(update, reply)
        await _drain_pending_media(update, context)
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await update.message.reply_text(f"Sorry, something went wrong -- {type(e).__name__}: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_rate_limit(update):
        await _rate_limit_reply(update)
        return
    if not update.message:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        photo = update.message.photo[-1] if update.message.photo else None
        doc = update.message.document if not photo else None

        if not photo and not doc:
            return

        if doc:
            mime = doc.mime_type or ""
            if not mime.startswith("image/"):
                return
            file = await doc.get_file()
            media_type = mime
            filename = doc.file_name or "image.jpg"
        else:
            file = await photo.get_file()
            media_type = "image/jpeg"
            filename = "photo.jpg"

        img_bytes = await file.download_as_bytearray()

        if len(img_bytes) > core.MAX_PHOTO_BYTES:
            await update.message.reply_text(
                f"Photo too large ({len(img_bytes) / (1024*1024):.1f} MB). "
                f"Maximum: {core.MAX_PHOTO_BYTES / (1024*1024):.0f} MB."
            )
            return

        img_b64 = base64.standard_b64encode(bytes(img_bytes)).decode("ascii")
        logger.info(f"Photo received: {len(img_bytes)} bytes, type={media_type}")
        core.audit("photo", size_bytes=len(img_bytes), media_type=media_type)

        filename = core.sanitize_filename(filename)
        tmp_path = Path(tempfile.gettempdir()) / f"spatialclaw_{filename}"
        tmp_path.write_bytes(bytes(img_bytes))
        core.received_files[update.effective_chat.id] = {
            "path": str(tmp_path), "filename": filename,
        }

        caption = update.message.caption or ""
        content_blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": img_b64,
                },
            },
        ]
        if caption:
            content_blocks.append({"type": "text", "text": caption})
        else:
            content_blocks.append({
                "type": "text",
                "text": (
                    "[Image sent without caption. Look at this image. "
                    "If it shows a tissue section (H&E stain, fluorescence, IF, "
                    "spatial barcode array, Visium capture area, or other histology): "
                    "identify the tissue type, staining method, and likely spatial "
                    "transcriptomics platform. Then suggest which OmicsClaw analysis "
                    "skills would be appropriate (e.g. preprocess, domains, annotate). "
                    "If the image is not a tissue section, describe what you see and "
                    "ask if anything specific is needed.]"
                ),
            })

        reply = await core.llm_tool_loop(update.effective_chat.id, content_blocks)
        if core.pending_text:
            reply = "\n\n".join(core.pending_text)
            core.pending_text.clear()
        await send_long_message(update, reply)

    except Exception as e:
        logger.error(f"Photo handling error: {e}", exc_info=True)
        await update.message.reply_text(
            f"Sorry, I couldn't process that image -- {type(e).__name__}: {e}"
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _check_rate_limit(update):
        await _rate_limit_reply(update)
        return
    if not update.message or not update.message.document:
        return

    doc = update.message.document
    mime = doc.mime_type or ""

    if mime.startswith("image/"):
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        file = await doc.get_file()
        filename = core.sanitize_filename(doc.file_name or "document")
        file_size = doc.file_size or 0

        if file_size > core.MAX_UPLOAD_BYTES:
            await update.message.reply_text(
                f"File too large ({file_size / (1024*1024):.1f} MB). "
                f"Maximum: {core.MAX_UPLOAD_BYTES / (1024*1024):.0f} MB."
            )
            return

        tmp_path = Path(tempfile.gettempdir()) / f"spatialclaw_{filename}"
        await file.download_to_drive(str(tmp_path))
        logger.info(f"Document received: {filename} ({file_size} bytes, {mime})")
        core.audit("document", filename=filename, size_bytes=file_size, mime=mime)

        core.received_files[update.effective_chat.id] = {
            "path": str(tmp_path), "filename": filename,
        }

        # Auto-create a spatial session
        session_path = None
        try:
            upload_proc = await asyncio.create_subprocess_exec(
                sys.executable, str(core.OMICSCLAW_PY), "upload",
                "--input", str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            up_stdout, _ = await asyncio.wait_for(upload_proc.communicate(), timeout=30)
            up_out = up_stdout.decode(errors="replace")
            for line in up_out.splitlines():
                if "session" in line.lower() and ("/" in line or "\\" in line):
                    for token in line.split():
                        if token.endswith(".json"):
                            session_path = token
                            break
            if session_path:
                core.received_files[update.effective_chat.id]["session_path"] = session_path
                logger.info(f"Auto-created session: {session_path}")
        except Exception as prof_err:
            logger.warning(f"Auto-session creation failed (non-fatal): {prof_err}")

        caption = update.message.caption or ""
        parts = [f"[Document received: {filename} ({mime}, {file_size} bytes)]"]
        if session_path:
            parts.append(f"[Spatial session auto-created: {session_path}]")
        if caption:
            parts.append(caption)
        else:
            ext = Path(filename).suffix.lower()
            file_routing = {
                ".h5ad": "preprocess",
                ".h5": "preprocess",
                ".loom": "velocity",
            }
            suggested = file_routing.get(ext, "auto")
            parts.append(
                f"The user sent this spatial data file. Detect the file type and "
                f"run the appropriate OmicsClaw skill using mode='file'. "
                f"Suggested skill based on extension '{ext}': {suggested}. "
                f"If unsure, use skill='auto'."
            )

        reply = await core.llm_tool_loop(update.effective_chat.id, "\n\n".join(parts))
        if core.pending_text:
            reply = "\n\n".join(core.pending_text)
            core.pending_text.clear()
        await send_long_message(update, reply)
        await _drain_pending_media(update, context)

    except Exception as e:
        logger.error(f"Document handling error: {e}", exc_info=True)
        await update.message.reply_text(
            f"Sorry, I couldn't process that document -- {type(e).__name__}: {e}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info(f"Starting OmicsClaw Telegram bot (provider: {core.LLM_PROVIDER_NAME}, model: {core.OMICSCLAW_MODEL})")
    logger.info(f"OmicsClaw directory: {core.OMICSCLAW_DIR}")
    if LLM_BASE_URL:
        logger.info(f"LLM base URL: {LLM_BASE_URL}")
    logger.info(f"Admin chat ID: {ADMIN_CHAT_ID or 'not set (public mode)'}")
    logger.info(f"Rate limit: {RATE_LIMIT_PER_HOUR} msgs/hour per user")
    core.audit("bot_start", platform="telegram", provider=core.LLM_PROVIDER_NAME,
               model=core.OMICSCLAW_MODEL, admin_chat=ADMIN_CHAT_ID,
               rate_limit=RATE_LIMIT_PER_HOUR)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("skills", cmd_skills))
    app.add_handler(CommandHandler("demo", cmd_demo))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("health", cmd_health))

    async def _error_handler(update, context):
        err = context.error
        if err is None:
            return
        err_name = type(err).__name__
        if "Forbidden" in err_name or "forbidden" in str(err).lower():
            logger.info(f"User blocked bot: {err}")
            return
        if err_name in ("TimedOut", "NetworkError", "RetryAfter"):
            logger.warning(f"Transient error: {err}")
            return
        logger.error(f"Unhandled error: {err}", exc_info=context.error)
        core.audit("error", severity="HIGH", error_type=err_name, detail=str(err)[:300])

    app.add_error_handler(_error_handler)

    app.add_handler(MessageHandler(
        filters.PHOTO | (filters.Document.IMAGE & ~filters.COMMAND),
        handle_photo,
    ))
    app.add_handler(MessageHandler(
        filters.Document.ALL & ~filters.Document.IMAGE & ~filters.COMMAND,
        handle_document,
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message,
    ))

    print("OmicsClaw Telegram bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
