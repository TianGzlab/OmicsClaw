"""
Telegram channel implementation for OmicsClaw.

Extracts the platform-specific logic from bot/telegram_bot.py into a
reusable Channel subclass. The original telegram_bot.py becomes a thin
launcher that creates a TelegramChannel and runs it.

This follows the EvoScientist Multi-Channel pattern where each platform
is a Channel subclass with start/stop/_send_chunk lifecycle.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import Channel
from .capabilities import TELEGRAM as TELEGRAM_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger("omicsclaw.channel.telegram")


@dataclass
class TelegramConfig(BaseChannelConfig):
    """Telegram-specific configuration."""
    bot_token: str = ""
    admin_chat_id: int = 0


class TelegramChannel(Channel):
    """Telegram channel using python-telegram-bot with long polling.

    Handles text messages, photos, documents, and bot commands.
    Bridges to core.llm_tool_loop() for LLM processing.
    """

    name = "telegram"
    capabilities = TELEGRAM_CAPS

    def __init__(self, config: TelegramConfig):
        super().__init__(config)
        self.tg_config = config
        self._app = None
        self._token_redact_filter = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self.tg_config.bot_token:
            raise RuntimeError("Telegram bot token is required")

        try:
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            raise RuntimeError(
                "python-telegram-bot not installed. "
                "Install with: pip install python-telegram-bot"
            )

        self._setup_token_redaction()

        self._app = Application.builder().token(self.tg_config.bot_token).build()

        # Register command handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("skills", self._cmd_skills))
        self._app.add_handler(CommandHandler("demo", self._cmd_demo))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("health", self._cmd_health))

        # Error handler
        self._app.add_error_handler(self._error_handler)

        # Message handlers
        self._app.add_handler(MessageHandler(
            filters.PHOTO | (filters.Document.IMAGE & ~filters.COMMAND),
            self._handle_photo,
        ))
        self._app.add_handler(MessageHandler(
            filters.Document.ALL & ~filters.Document.IMAGE & ~filters.COMMAND,
            self._handle_document,
        ))
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_message,
        ))

        # ── Start the polling loop ───────────────────────────────────
        # When launched via ChannelManager (python -m bot.run), only
        # start() is called. We must begin polling here, otherwise
        # the bot is connected but deaf — no messages are received.
        await self._app.initialize()
        await self._app.start()
        self._updater = self._app.updater
        await self._updater.start_polling(
            drop_pending_updates=True,
        )

        self._running = True
        logger.info("Telegram channel started (polling)")

    async def stop(self) -> None:
        self._running = False
        await self._typing_manager.stop_all()
        if self._app:
            try:
                if self._updater and self._updater.running:
                    await self._updater.stop()
                if self._app.running:
                    await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning(f"Telegram shutdown error (non-fatal): {e}")
            logger.info("Telegram channel stopped")

    def run_polling(self) -> None:
        """Synchronous entry point — run the Telegram bot with polling.

        This replaces the old ``app.run_polling()`` and is the primary
        way to start the Telegram bot (backward-compatible).
        Calls start() internally, then blocks until interrupted.
        """
        from bot import core
        logger.info(
            f"Starting OmicsClaw Telegram bot "
            f"(provider: {core.LLM_PROVIDER_NAME}, model: {core.OMICSCLAW_MODEL})"
        )
        logger.info(f"OmicsClaw directory: {core.OMICSCLAW_DIR}")
        if self.tg_config.admin_chat_id:
            logger.info(f"Admin chat ID: {self.tg_config.admin_chat_id}")
        logger.info(
            f"Rate limit: {self.config.rate_limit_per_hour} msgs/hour per user"
        )
        core.audit(
            "bot_start",
            platform="telegram",
            provider=core.LLM_PROVIDER_NAME,
            model=core.OMICSCLAW_MODEL,
            admin_chat=self.tg_config.admin_chat_id,
            rate_limit=self.config.rate_limit_per_hour,
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start())
        print("OmicsClaw Telegram bot is running. Press Ctrl+C to stop.")
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            loop.run_until_complete(self.stop())
            loop.close()

    # ── Core send implementation ─────────────────────────────────────

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        """Send a single text chunk via Telegram."""
        # strip_markup for plain-text safety in Telegram
        from bot import core
        text = core.strip_markup(formatted_text)
        if self._app:
            await self._app.bot.send_message(
                chat_id=int(chat_id),
                text=text,
            )

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a media file via Telegram."""
        if not self._app:
            return False
        try:
            path = Path(file_path)
            if not path.exists():
                return False
            ext = path.suffix.lower()
            cid = int(chat_id)
            if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                await self._app.bot.send_photo(
                    chat_id=cid,
                    photo=open(path, "rb"),
                    caption=caption or path.stem.replace("_", " ").title(),
                )
            else:
                await self._app.bot.send_document(
                    chat_id=cid,
                    document=open(path, "rb"),
                    filename=path.name,
                    caption=caption or None,
                )
            return True
        except Exception as e:
            logger.error(f"Telegram send_media error: {e}")
            return False

    # ── Typing indicator ─────────────────────────────────────────────

    async def _send_typing(self, chat_id: str) -> None:
        if self._app:
            await self._app.bot.send_chat_action(
                chat_id=int(chat_id),
                action="typing",
            )

    # ── Admin check ──────────────────────────────────────────────────

    def _is_admin(self, sender_id: str) -> bool:
        if not self.tg_config.admin_chat_id:
            return False
        try:
            return int(sender_id) == self.tg_config.admin_chat_id
        except (ValueError, TypeError):
            return False

    # ── Token redaction ──────────────────────────────────────────────

    def _setup_token_redaction(self) -> None:
        """Add a logging filter to redact the bot token from log output."""
        token = self.tg_config.bot_token
        if not token:
            return

        class _TokenRedactFilter(logging.Filter):
            def __init__(self, tok: str):
                super().__init__()
                self._token = tok

            def filter(self, record: logging.LogRecord) -> bool:
                if self._token and self._token in record.getMessage():
                    record.msg = str(record.msg).replace(self._token, "[REDACTED]")
                    if isinstance(record.args, tuple):
                        record.args = tuple(
                            str(a).replace(self._token, "[REDACTED]") for a in record.args
                        )
                return True

        redact = _TokenRedactFilter(token)
        for ln in ("httpx", "telegram", "httpcore"):
            logging.getLogger(ln).addFilter(redact)

    # ── Helpers ──────────────────────────────────────────────────────

    async def _send_long_message(self, update, text: str) -> None:
        """Send a potentially long text message, auto-chunking."""
        from bot import core
        text = core.strip_markup(text)
        limit = self.capabilities.max_text_length
        if len(text) <= limit:
            await update.message.reply_text(text)
            return
        from .base import chunk_text
        for chunk in chunk_text(text, limit):
            if chunk.strip():
                await update.message.reply_text(chunk)

    async def _drain_pending_media(self, update, context) -> None:
        """Send any pending media files queued by the LLM tool loop."""
        from bot import core
        chat_id = update.effective_chat.id
        items = core.pending_media.pop(chat_id, [])
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

    def _make_progress_fns(self, update):
        """Create progress callback functions for the LLM tool loop."""
        from bot import core

        async def _progress(msg: str):
            return await update.message.reply_text(core.strip_markup(msg))

        async def _progress_update(handle, msg: str):
            try:
                await handle.edit_text(core.strip_markup(msg))
            except Exception:
                pass

        return _progress, _progress_update

    # ── Command handlers ─────────────────────────────────────────────

    async def _cmd_start(self, update, context) -> None:
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

    async def _cmd_skills(self, update, context) -> None:
        try:
            from bot import core
            output = core.format_skills_table()
            await self._send_long_message(update, output or "No skills found.")
        except Exception as e:
            await update.message.reply_text(f"Error listing skills: {e}")

    async def _cmd_demo(self, update, context) -> None:
        if not self._check_rate(update):
            return
        from bot import core
        skill = context.args[0] if context.args else "preprocess"
        await update.message.reply_text(f"Running {skill} demo -- this may take a moment...")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        try:
            progress_fn, progress_update_fn = self._make_progress_fns(update)
            reply = await core.llm_tool_loop(
                update.effective_chat.id,
                f"Run the {skill} demo using the omicsclaw tool with mode='demo'.",
                user_id=str(update.effective_user.id),
                platform="telegram",
                progress_fn=progress_fn,
                progress_update_fn=progress_update_fn,
            )
            if core.pending_text:
                reply = "\n\n".join(core.pending_text)
                core.pending_text.clear()
            await self._send_long_message(update, reply)
            await self._drain_pending_media(update, context)
        except Exception as e:
            logger.error(f"Demo error: {e}", exc_info=True)
            await update.message.reply_text(f"Demo failed: {e}")

    async def _cmd_status(self, update, context) -> None:
        from bot import core
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
        await update.message.reply_text(status_msg)

    async def _cmd_health(self, update, context) -> None:
        from bot import core
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
            implemented = [
                d.name for d in sorted(skills_dir.iterdir())
                if d.is_dir() and (d / "SKILL.md").exists() and any(d.glob("*.py"))
            ]
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

    # ── Message handlers ─────────────────────────────────────────────

    def _check_rate(self, update) -> bool:
        """Check rate limit and send reply if exceeded. Returns True if OK."""
        uid = str(update.effective_user.id) if update.effective_user else str(update.effective_chat.id)
        if self._is_admin(uid):
            return True
        if not self.check_rate_limit(uid):
            from bot import core
            core.audit("rate_limited", user_id=uid)
            asyncio.create_task(update.message.reply_text(
                f"You've reached the limit of {self.config.rate_limit_per_hour} messages per hour. "
                "Please try again later."
            ))
            return False
        return True

    async def _handle_message(self, update, context) -> None:
        if not self._check_rate(update):
            return
        if not update.message or not update.message.text:
            return

        from bot import core
        user_text = update.message.text
        logger.info(f"Message from {update.effective_user.first_name}: {user_text[:100]}")
        core.audit(
            "message",
            user_id=update.effective_user.id if update.effective_user else None,
            text_preview=user_text[:200],
        )

        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            progress_fn, progress_update_fn = self._make_progress_fns(update)
            reply = await core.llm_tool_loop(
                update.effective_chat.id,
                user_text,
                user_id=str(update.effective_user.id),
                platform="telegram",
                progress_fn=progress_fn,
                progress_update_fn=progress_update_fn,
            )
            if core.pending_text:
                reply = "\n\n".join(core.pending_text)
                core.pending_text.clear()
            await self._send_long_message(update, reply)
            await self._drain_pending_media(update, context)
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await update.message.reply_text(
                f"Sorry, something went wrong -- {type(e).__name__}: {e}"
            )

    async def _handle_photo(self, update, context) -> None:
        if not self._check_rate(update):
            return
        if not update.message:
            return

        from bot import core
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

            progress_fn, progress_update_fn = self._make_progress_fns(update)
            reply = await core.llm_tool_loop(
                update.effective_chat.id,
                content_blocks,
                user_id=str(update.effective_user.id),
                platform="telegram",
                progress_fn=progress_fn,
                progress_update_fn=progress_update_fn,
            )
            if core.pending_text:
                reply = "\n\n".join(core.pending_text)
                core.pending_text.clear()
            await self._send_long_message(update, reply)

        except Exception as e:
            logger.error(f"Photo handling error: {e}", exc_info=True)
            await update.message.reply_text(
                f"Sorry, I couldn't process that image -- {type(e).__name__}: {e}"
            )

    async def _handle_document(self, update, context) -> None:
        if not self._check_rate(update):
            return
        if not update.message or not update.message.document:
            return

        doc = update.message.document
        mime = doc.mime_type or ""

        if mime.startswith("image/"):
            return

        from bot import core
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

            progress_fn, progress_update_fn = self._make_progress_fns(update)
            reply = await core.llm_tool_loop(
                update.effective_chat.id,
                "\n\n".join(parts),
                user_id=str(update.effective_user.id),
                platform="telegram",
                progress_fn=progress_fn,
                progress_update_fn=progress_update_fn,
            )
            if core.pending_text:
                reply = "\n\n".join(core.pending_text)
                core.pending_text.clear()
            await self._send_long_message(update, reply)
            await self._drain_pending_media(update, context)

        except Exception as e:
            logger.error(f"Document handling error: {e}", exc_info=True)
            await update.message.reply_text(
                f"Sorry, I couldn't process that document -- {type(e).__name__}: {e}"
            )

    # ── Error handler ────────────────────────────────────────────────

    async def _error_handler(self, update, context) -> None:
        from bot import core
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
