"""
Telegram channel implementation for OmicsClaw.

Extracts the platform-specific logic into a reusable Channel subclass.

Ported from ``omicsclaw/surfaces/channels/telegram.py`` for plan 0031 task D1.
Every change is on one seam: the file imported one symbol from the deleted
control plane (``telegram.py:20``) and built one object out of it. What
changed, and nothing else:

- ``ChannelSurfaceBinding`` now comes from
  :mod:`omicsclaw.entry.channel.binding`, and the owner allowlist it carried
  as an identity-scope table is a :class:`~omicsclaw.entry.ingress
  .SenderPolicy`;
- inbound submission builds an :class:`~omicsclaw.entry.ingress
  .InboundMessage` instead of a ``RawInboundV1`` plus a twenty-two-field
  ``ControlRuntimePorts``;
- the seven places that read the deleted ``agent.state`` module's globals
  read the assembled app instead, or say less: the two ``audit`` calls are
  gone with the sink they wrote to, and the surviving log lines report a
  length rather than what somebody wrote (plan 0031 Q22);
- **the photo path is gone.** Plan 0031 §5.3 discards it: this layer's
  :class:`~omicsclaw.schema.Message` carries ``content: str`` and no
  content parts (``omicsclaw/schema/message.py:178-179``), so
  an accepted photo would have been dropped between here and the model.
  Photos are refused with a sentence, the way documents already were.

Group chats fail closed. A Telegram group message is admitted only when it
@-mentions this bot, proved against the authenticated identity — the same
rule ``CLAUDE.md`` states for Feishu, applied here because the reason for it
is the platform's, not Feishu's: without it, an owner mentioning a colleague
in a shared group makes this agent answer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from omicsclaw.entry.ingress import (
    SenderPolicy,
    VALUE_CHAT_TYPE,
    VALUE_MENTIONS,
)

from .base import Channel
from .binding import ChannelSurfaceBinding
from .capabilities import TELEGRAM as TELEGRAM_CAPS
from .commands import SlashCommandContext, dispatch
from .config import BaseChannelConfig
from .runtime import (
    CODE_EMPTY_TEXT,
    CODE_NOT_STARTED,
    CODE_OWNER_DENIED,
    CODE_QUEUE_FULL,
    TurnAcceptanceStatus,
)
from .telegram_delivery import TelegramDeliveryAdapter

logger = logging.getLogger("omicsclaw.channel.telegram")

_PHOTO_UNSUPPORTED_NOTICE = (
    "OmicsClaw cannot read images yet, so this photo was not accepted. "
    "Describe what it shows, or send a path to a data file."
)
_DOCUMENT_UNSUPPORTED_NOTICE = (
    "Telegram documents are not supported on the authoritative path yet."
)


def telegram_bot_identity(bot: Any) -> str:
    """This bot's identity in the spelling a group mention uses.

    Telegram writes a mention of a bot as ``@username`` in the message text
    and reports it as a ``mention`` entity; there is no id in that form. So
    the username is the identity when there is one, and the numeric id is the
    fallback for the bots that have none — which can then only be addressed
    by a ``text_mention``.
    """
    username = getattr(bot, "username", None)
    if isinstance(username, str) and username:
        return f"@{username}"
    bot_id = getattr(bot, "id", None)
    if isinstance(bot_id, int) and not isinstance(bot_id, bool):
        return str(bot_id)
    return ""


def telegram_mentions(message: Any) -> tuple[str, ...]:
    """Every identity *message* @-mentioned, in both spellings Telegram uses.

    ``mention`` entities carry the ``@handle`` as a slice of the text;
    ``text_mention`` entities carry a user object instead, for accounts with
    no public username. Both are returned so that
    :meth:`~omicsclaw.entry.ingress.SenderPolicy.admits` can match whichever
    form :func:`telegram_bot_identity` produced.

    Returns an empty tuple when the message mentions nobody — which in a
    group is what makes it fail closed.
    """
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    found: list[str] = []
    for entity in getattr(message, "entities", None) or ():
        kind = getattr(entity, "type", "")
        if kind == "mention":
            offset = getattr(entity, "offset", None)
            length = getattr(entity, "length", None)
            if isinstance(offset, int) and isinstance(length, int):
                found.append(text[offset : offset + length])
        elif kind == "text_mention":
            user = getattr(entity, "user", None)
            user_id = getattr(user, "id", None)
            if user_id is not None:
                found.append(str(user_id))
    return tuple(found)


@dataclass
class TelegramConfig(BaseChannelConfig):
    """Telegram-specific configuration."""

    bot_token: str = ""
    admin_chat_id: int = 0
    account_namespace: str = ""


class TelegramChannel(Channel):
    """Telegram channel using python-telegram-bot with long polling.

    Owner text enters the authoritative
    :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`; replies leave
    only through its delivery pump. Photos, albums, documents and outbound
    media are all fail-closed.
    """

    name = "telegram"
    capabilities = TELEGRAM_CAPS
    authoritative_ingress = True

    def __init__(self, config: TelegramConfig):
        super().__init__(config)
        self.tg_config = config
        self._app = None
        self._updater = None
        self._control_runtime = None
        self._token_redact_filter = None
        self.bot_identity = ""
        """This bot's own ``@handle``, read back from Telegram during phase 1.

        Empty until :meth:`prepare_control_binding` has authenticated, which
        is exactly when group messages cannot be attributed and therefore
        fail closed."""

    # ─ Lifecycle ──────────────────────

    async def prepare_control_binding(self) -> ChannelSurfaceBinding:
        """Authenticate far enough to describe this Bot's control binding.

        The shared ChannelRuntime is composed by the runner, so this method
        must bring the Application up to the point where the authenticated Bot
        identity is readable and a Delivery Adapter can be built over its bot.
        """

        owners = self._owner_subjects()
        if not owners:
            raise RuntimeError(
                "Telegram authoritative ingress requires TELEGRAM_CHAT_ID "
                "or TELEGRAM_ALLOWED_SENDERS"
            )
        if self._app is None:
            self._build_application()
        try:
            await self._app.initialize()
            await self._app.start()
            bot_identity = await self._app.bot.get_me()
        except BaseException:
            await self.stop()
            raise
        bot_id = getattr(bot_identity, "id", None)
        if isinstance(bot_id, bool) or not isinstance(bot_id, int):
            await self.stop()
            raise RuntimeError("Telegram Bot identity is unavailable")
        account_namespace = f"bot-{bot_id}"
        configured_namespace = self.tg_config.account_namespace.strip()
        if configured_namespace and configured_namespace != account_namespace:
            await self.stop()
            raise RuntimeError(
                "TELEGRAM_ACCOUNT_NAMESPACE must equal the authenticated Bot identity"
            )
        self.tg_config.account_namespace = account_namespace
        self.bot_identity = telegram_bot_identity(bot_identity)
        return ChannelSurfaceBinding(
            adapter="telegram",
            account_namespace=account_namespace,
            # The owner set and this bot's own handle, in one object: the
            # second is what proves a group @-mention was aimed here, and
            # without it every group message fails closed.
            sender_policy=SenderPolicy(
                allowed_senders=owners,
                bot_identity=self.bot_identity,
            ),
            delivery_adapter=TelegramDeliveryAdapter(self._app.bot),
            text_chunk_limit=(
                self.config.text_chunk_limit or self.capabilities.max_text_length
            ),
            # Photos are refused at the handler; see the module docstring.
            attachment_input_enabled=False,
        )

    def _build_application(self) -> None:
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
        self._app.add_handler(
            MessageHandler(
                filters.PHOTO | (filters.Document.IMAGE & ~filters.COMMAND),
                self._handle_photo,
            )
        )
        self._app.add_handler(
            MessageHandler(
                filters.Document.ALL & ~filters.Document.IMAGE & ~filters.COMMAND,
                self._handle_document,
            )
        )
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_message,
            )
        )

    async def start(self) -> None:
        """Phase 2: begin polling once the shared ChannelRuntime is bound."""

        if self._control_runtime is None:
            raise RuntimeError(
                "Telegram requires the shared ChannelRuntime to be bound "
                "before start()"
            )
        if self._app is None:  # pragma: no cover - prepare runs first
            raise RuntimeError("Telegram Application was not prepared")
        await self._activate_application()
        self._running = True
        logger.info("Telegram channel started (polling)")

    async def _activate_application(self) -> None:
        """Begin polling, rolling the whole Channel back on failure."""

        try:
            self._updater = self._app.updater
            await self._updater.start_polling(
                drop_pending_updates=False,
            )
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        self.deactivate_ingress()
        failures: list[str] = []
        try:
            await self._typing_manager.stop_all()
        except Exception as error:
            error_type = type(error).__name__
            failures.append(error_type)
            logger.warning("Telegram typing shutdown failed (%s)", error_type)
        if self._updater and self._updater.running:
            try:
                await self._updater.stop()
            except Exception as error:
                error_type = type(error).__name__
                failures.append(error_type)
                logger.warning(
                    "Telegram polling shutdown failed (%s)", error_type
                )
        if self._app:
            if self._app.running:
                try:
                    await self._app.stop()
                except Exception as error:
                    error_type = type(error).__name__
                    failures.append(error_type)
                    logger.warning(
                        "Telegram Application stop failed (%s)",
                        error_type,
                    )
            try:
                await self._app.shutdown()
            except Exception as error:
                error_type = type(error).__name__
                failures.append(error_type)
                logger.warning(
                    "Telegram Application shutdown failed (%s)",
                    error_type,
                )
        if failures:
            raise RuntimeError(
                "Telegram channel shutdown failed (" + ", ".join(failures) + ")"
            ) from None

        # Detach only after every provider callback source has stopped. The
        # runner owns the shared runtime and closes it after all Channels stop.
        self._control_runtime = None
        self._control_loop = None
        self._updater = None
        self._app = None
        self._running = False
        logger.info("Telegram channel stopped")


    def run_polling(self) -> None:
        """Refuse the legacy standalone entry point.

        The Bot cannot own the agent it speaks for: every Channel in the
        process shares one
        :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`, and that is
        composed by the runner from every Channel's binding. Starting here
        would either fail on an unbound runtime or build a second one, which
        would be a second set of conversations for the same person.
        """

        raise RuntimeError(
            "TelegramChannel.run_polling() is retired; start the Bot through "
            "the runner that owns the shared ChannelRuntime: compose one with "
            "compose_channel_runtime(app, channels) and start them through "
            "ChannelManager"
        )

    # ─ Core send implementation ─────────────────

    async def process_message(self, *args, **kwargs) -> str:
        raise RuntimeError(
            "Telegram messages must enter through the authoritative ChannelRuntime"
        )

    async def send(
        self,
        chat_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        raise RuntimeError(
            "Telegram replies must leave through the ChannelRuntime delivery pump, "
            "which classifies whether they were accepted"
        )

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        raise RuntimeError(
            "Telegram text chunks must leave through the ChannelRuntime delivery "
            "pump, which classifies whether they were accepted"
        )

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        raise RuntimeError(
            "Telegram media Delivery is disabled until durable artifact references land"
        )

    # ─ Typing indicator ────────────────────

    async def _send_typing(self, chat_id: str) -> None:
        if self._app:
            await self._app.bot.send_chat_action(
                chat_id=int(chat_id),
                action="typing",
            )

    # ─ Admin check ──────────────────────

    def _is_admin(self, sender_id: str) -> bool:
        if not self.tg_config.admin_chat_id:
            return False
        try:
            return int(sender_id) == self.tg_config.admin_chat_id
        except (ValueError, TypeError):
            return False

    def _owner_subjects(self) -> frozenset[str]:
        configured = {
            str(value).strip()
            for value in (self.config.allowed_senders or set())
            if str(value).strip()
        }
        if self.tg_config.admin_chat_id:
            configured.add(str(self.tg_config.admin_chat_id))
        return frozenset(configured)

    def _owner_update_allowed(self, update) -> bool:
        user = getattr(update, "effective_user", None)
        if user is None or str(user.id) not in self._owner_subjects():
            logger.warning("Ignored Telegram update from a non-Owner")
            return False
        return True

    # ─ Token redaction ────────────────────

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
                    record.msg = record.getMessage().replace(
                        self._token,
                        "[REDACTED]",
                    )
                    record.args = ()
                return True

        redact = _TokenRedactFilter(token)
        self._token_redact_filter = redact
        protected_loggers = [
            value
            for name, value in logging.Logger.manager.loggerDict.items()
            if isinstance(value, logging.Logger)
            and name.startswith(("httpx", "telegram", "httpcore"))
        ]
        protected_loggers.extend(
            logging.getLogger(name) for name in ("httpx", "telegram", "httpcore")
        )
        for protected_logger in protected_loggers:
            protected_logger.addFilter(redact)
            for handler in protected_logger.handlers:
                handler.addFilter(redact)
        # Descendant records are filtered by ancestor handlers, not ancestor
        # Logger filters. Root handler coverage closes that propagation gap.
        for handler in logging.getLogger().handlers:
            handler.addFilter(redact)

    # ─ Helpers ───────────────────────

    async def _send_long_message(self, update, text: str) -> None:
        """Send a potentially long text message, auto-chunking.

        Only command output travels this way — an answer from the model
        leaves through the delivery pump, which is the path that classifies
        acceptance. This one is a direct provider call and reports nothing,
        which is tolerable for a listing and is not for an answer.
        """
        text = self.strip_markup(text)
        limit = self.capabilities.max_text_length
        if len(text) <= limit:
            await update.message.reply_text(text)
            return
        from .base import chunk_text

        for chunk in chunk_text(text, limit):
            if chunk.strip():
                await update.message.reply_text(chunk)

    async def _submit_control_inbound(self, update, text: str):
        """Normalize one Telegram message and submit it as one exchange.

        Returns the :class:`~omicsclaw.entry.channel.runtime.ChannelSubmission`
        so a caller can see the verdict, and ``None`` when there was nothing
        to submit. Refusals answer the person only when saying so is safe: a
        sender outside the allowlist is told nothing at all, because a reply
        confirms both that this bot is here and that their id was checked.
        """

        if not self.ingress_active:
            return None
        if self._control_runtime is None:
            raise RuntimeError("Telegram ChannelRuntime is not bound")
        message = update.message
        user = update.effective_user
        chat = update.effective_chat
        if message is None or user is None or chat is None:
            return None
        account_namespace = self.tg_config.account_namespace.strip()
        reply_target: dict[str, Any] = {
            "schema_version": 1,
            "kind": "channel",
            "adapter": "telegram",
            "account_namespace": account_namespace,
            "destination_id": str(chat.id),
        }
        thread_id = getattr(message, "message_thread_id", None)
        if thread_id is not None:
            reply_target["thread_id"] = str(thread_id)
        inbound = self.inbound(
            str(chat.id),
            str(user.id),
            text,
            # Chat plus message id: stable across Telegram's own redelivery,
            # unique within this account, and short. The registry resolves a
            # repeat of it to the exchange it already started.
            source_request_id=f"{chat.id}:{message.message_id}",
            reply_target=reply_target,
            values={
                VALUE_CHAT_TYPE: str(getattr(chat, "type", "") or ""),
                VALUE_MENTIONS: telegram_mentions(message),
            },
        )
        result = await self._control_runtime.submit(inbound)
        if result.acceptance.status is TurnAcceptanceStatus.REJECTED:
            await self._notify_refusal(message, result.acceptance.code)
        return result

    async def _notify_refusal(self, message, code: str) -> None:
        """Tell the person why, unless telling them is itself the leak."""

        if code == CODE_OWNER_DENIED:
            logger.warning("Ignored Telegram message from a non-Owner")
            return
        notices = {
            CODE_QUEUE_FULL: (
                "OmicsClaw is still working on your earlier messages. "
                "Please retry later."
            ),
            CODE_NOT_STARTED: "OmicsClaw is still starting. Please retry.",
            CODE_EMPTY_TEXT: "There was no text in that message to work on.",
        }
        await message.reply_text(
            notices.get(code, "This Telegram request was not accepted.")
        )

    async def _submit_control_text(self, update, text: str):
        """Submit a text-only Telegram message through the shared helper."""

        return await self._submit_control_inbound(update, text)

    # ─ Command handlers ────────────────────

    async def _cmd_start(self, update, context) -> None:
        if not self._owner_update_allowed(update):
            return
        await update.message.reply_text(
            "Welcome to OmicsClaw -- multi-omics analysis at your "
            "fingertips!\n\n"
            "I can analyze spatial, single-cell, genomics, proteomics and "
            "metabolomics data through a unified skill system.\n\n"
            "Commands:\n"
            "  /skills  -- list available analysis skills\n"
            "  /demo <skill>  -- run a demo (preprocess, domains, de, ...)\n"
            "  /status  -- bot info\n"
            "  /health  -- system health check\n\n"
            "Or just chat -- ask any multi-omics analysis question. Photos, "
            "albums and documents are not supported; send a path to a data "
            "file instead.\n\n"
            "OmicsClaw is a research tool, not a medical device. "
            "Consult a domain expert before making decisions based on these results."
        )

    def _command_context(self, update, text: str) -> SlashCommandContext:
        """The request-scoped half of a slash command, assembled once.

        The deployment-scoped half — skills, tools, provider, workspace — is
        the app the runtime holds, which is where those handlers used to read
        module globals from.
        """

        chat = update.effective_chat
        user = update.effective_user
        app = self._control_runtime.app if self._control_runtime else None
        chat_id = str(getattr(chat, "id", "")) if chat is not None else ""
        return SlashCommandContext(
            chat_id=chat_id,
            user_id=str(getattr(user, "id", "")) if user is not None else None,
            platform=self.name,
            user_text=text,
            workspace=str(app.config.workspace) if app is not None else "",
            app=app,
            session_id=self.session_id(chat_id),
        )

    async def _run_command(self, update, text: str) -> None:
        """Dispatch one built-in command and send whatever it answered."""

        # The verb, not the command line: ``/analyse P12345.h5ad`` puts a
        # subject identifier in the argument, and a traceback is written
        # wherever an operator points this logger.
        verb = text.split(maxsplit=1)[0] if text.strip() else ""
        try:
            reply = await dispatch(self._command_context(update, text))
        except Exception:
            logger.exception("Telegram command %s failed", verb)
            await update.message.reply_text("That command failed.")
            return
        await self._send_long_message(update, reply or "Nothing to show.")

    async def _cmd_skills(self, update, context) -> None:
        if not self._owner_update_allowed(update):
            return
        await self._run_command(update, "/skills")

    async def _cmd_demo(self, update, context) -> None:
        if not self._owner_update_allowed(update):
            return
        skill = context.args[0] if context.args else "preprocess"
        await update.message.reply_text(
            f"Running {skill} demo -- this may take a moment..."
        )
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
        try:
            await self._submit_control_text(
                update,
                f"Run the {skill} demo using the omicsclaw tool with mode='demo'.",
            )
        except Exception:
            logger.exception("Telegram demo submission failed")

    async def _cmd_status(self, update, context) -> None:
        if not self._owner_update_allowed(update):
            return
        await self._run_command(update, "/status")

    async def _cmd_health(self, update, context) -> None:
        """A start-up check against the assembled app, not the filesystem.

        The old version stat-ed four paths that the deleted ``agent.state``
        module had resolved at import. Every one of them is now a fact the
        composition root already established — the prompt either rendered or
        the app would not exist, the skills either scanned or the index is
        empty — so this reports what was assembled rather than guessing from
        a directory listing.
        """

        if not self._owner_update_allowed(update):
            return
        runtime = self._control_runtime
        if runtime is None:
            await update.message.reply_text("OmicsClaw is not bound to a runtime.")
            return
        app = runtime.app
        checks = [
            f"Provider: {app.provider.name}",
            f"Model: {app.config.model or 'provider default'}",
            f"Tools mounted: {len(app.tools_snapshot)}",
            f"Skills indexed: {len(app.skills)}",
            f"Skills skipped: {len(app.skills.skipped)}",
            f"Context window: {app.budget.context_tokens} tokens",
            f"Workspace: {app.config.workspace}",
            f"Accepting: {'yes' if runtime.started else 'no'}",
        ]
        await update.message.reply_text(
            "OmicsClaw Health Check\n" "======================\n" + "\n".join(checks)
        )

    # ─ Message handlers ────────────────────

    async def _handle_message(self, update, context) -> None:
        if not self._owner_update_allowed(update):
            return
        if not update.message or not update.message.text:
            return

        user_text = update.message.text
        # Length only. The old line logged the sender's first name and 100
        # characters of what they wrote; plan 0031 Q22 keeps message content
        # off every shared channel, and a log is the most shared one there is.
        logger.info("Telegram message accepted (%d chars)", len(user_text))

        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action="typing"
            )
            await self._submit_control_text(update, user_text)
        except Exception:
            # The Turn may already be durably accepted. A direct fallback reply
            # could then duplicate or overtake its canonical Outbox Delivery.
            logger.exception("Telegram text submission failed")

    async def _handle_photo(self, update, context) -> None:
        """Refuse a photo, in one sentence, having fetched nothing.

        Plan 0031 §5.3 discards the photo path: an inbound image has nowhere
        to go once this layer's ``Message`` carries no content parts, so the
        old handler's careful descriptor validation and byte capability would
        have produced an attachment the model never sees. Refusing is not a
        regression against that — it is the same outcome, said out loud and
        without downloading anything.
        """

        if not self._owner_update_allowed(update):
            return
        if not update.message:
            return
        message = update.message
        # The broad registration filter also routes image documents here.
        if getattr(message, "document", None) is not None:
            await message.reply_text(_DOCUMENT_UNSUPPORTED_NOTICE)
            return
        await message.reply_text(_PHOTO_UNSUPPORTED_NOTICE)

    async def _handle_document(self, update, context) -> None:
        if not self._owner_update_allowed(update):
            return
        if not update.message or not update.message.document:
            return

        await update.message.reply_text(_DOCUMENT_UNSUPPORTED_NOTICE)

    # ─ Error handler ─────────────────────

    async def _error_handler(self, update, context) -> None:
        err = context.error
        if err is None:
            return
        err_name = type(err).__name__
        if "Forbidden" in err_name or "forbidden" in str(err).lower():
            logger.info("Telegram provider rejected access (%s)", err_name)
            return
        if err_name in ("TimedOut", "NetworkError", "RetryAfter"):
            logger.warning("Transient Telegram provider error (%s)", err_name)
            return
        # Provider errors may embed credentials, request URLs or payloads. Keep
        # the evidence to the bounded exception classification. The audit sink
        # the old line also wrote to lived in the deleted state module; plan
        # 0031 has no audit log yet, and inventing one here would be a second
        # unowned place that writes about users.
        logger.error("Unhandled Telegram provider error (%s)", err_name)
