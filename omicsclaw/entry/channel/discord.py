"""
Discord channel implementation for OmicsClaw.

Uses ``discord.py`` to receive messages over the Discord Gateway. The
library runs its WebSocket on the event loop it is started from, so nothing
here crosses a thread boundary.

Start-up is two-phase. :meth:`DiscordChannel.prepare_control_binding` calls
``Client.login``, which is the point at which ``client.user`` becomes
readable — waiting for ``on_ready`` instead would put the binding after
``connect()`` and leave this bot's identity empty while the binding is being
built, and an empty identity makes **every** guild message fail closed.
:meth:`DiscordChannel.start` then opens the gateway.

Guild channels fail closed. A guild message is admitted only when this bot's
own id is among the ids the message @-mentioned, compared locally against the
identity read back at login.

Configuration via environment variables (read by ``omicsclaw/launch/``, never
here):
    DISCORD_BOT_TOKEN — Discord bot token

References:
    - https://discord.com/developers/docs/intro
    - https://discordpy.readthedocs.io/en/stable/
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from omicsclaw.entry.ingress import (
    SenderPolicy,
    VALUE_CHAT_TYPE,
    VALUE_MENTIONS,
)

from . import reply_target
from .base import Channel
from .binding import ChannelSurfaceBinding
from .capabilities import DISCORD as DISCORD_CAPS
from .config import BaseChannelConfig
from .discord_delivery import DiscordDeliveryAdapter
from .runtime import TurnAcceptanceStatus

logger = logging.getLogger("omicsclaw.channel.discord")

GATEWAY_PROBE_S = 1.0
"""How long a failing gateway is given to fail before start-up believes it.

A gateway that refuses a token or cannot reach Discord does so on its first
frame; anything slower is a slow network, which is not a start-up fault and
must not be reported as one."""


# ─ Config ─────────────────────────


@dataclass
class DiscordConfig(BaseChannelConfig):
    """Discord channel configuration."""

    bot_token: str = ""
    text_chunk_limit: int = 2000  # Discord's message limit


# ─ Channel ────────────────────────


class DiscordChannel(Channel):
    """Discord channel using ``discord.py``.

    Owner text enters the authoritative
    :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`; answers leave
    only through its delivery pump, which is what classifies whether they
    were accepted. Inbound attachments and outbound media are fail-closed.
    """

    name = "discord"
    capabilities = DISCORD_CAPS
    authoritative_ingress = True

    def __init__(self, config: DiscordConfig):
        super().__init__(config)
        self.discord_config = config
        self._client = None
        self._gateway: asyncio.Task[None] | None = None
        self._account_namespace = ""
        self.bot_identity = ""
        """This bot's own user id as text, read back from Discord at login.

        Empty until :meth:`prepare_control_binding` has run, which is exactly
        when a guild mention cannot be attributed and therefore fails closed.
        """

    # ─ Lifecycle ──────────────────────

    async def prepare_control_binding(self) -> ChannelSurfaceBinding:
        """Log in far enough to describe this bot's control binding.

        ``login`` and not ``connect``: it performs the token exchange that
        populates ``client.user`` and opens no gateway, so the runner can
        compose a runtime over every channel's binding before any of them
        starts receiving events.
        """

        owners = self._owner_subjects()
        if not owners:
            raise RuntimeError(
                "Discord authoritative ingress requires DISCORD_ALLOWED_SENDERS"
            )
        if not self.discord_config.bot_token:
            raise RuntimeError("DISCORD_BOT_TOKEN is required")
        if self._client is None:
            self._client = self._build_client()

        await self._client.login(self.discord_config.bot_token)
        user = getattr(self._client, "user", None)
        user_id = getattr(user, "id", None)
        if user_id is None:
            await self.stop()
            raise RuntimeError("Discord bot identity is unavailable")
        self._account_namespace = f"bot-{user_id}"
        self.bot_identity = str(user_id)
        logger.info("Discord bot authenticated for %s", self._account_namespace)

        return ChannelSurfaceBinding(
            adapter="discord",
            account_namespace=self._account_namespace,
            sender_policy=SenderPolicy(
                allowed_senders=owners,
                bot_identity=self.bot_identity,
            ),
            delivery_adapter=DiscordDeliveryAdapter(self._client),
            text_chunk_limit=(
                self.config.text_chunk_limit or self.capabilities.max_text_length
            ),
            attachment_input_enabled=False,
        )

    def _build_client(self) -> Any:
        try:
            import discord
        except ImportError:
            raise RuntimeError(
                "discord.py not installed. Run: pip install discord.py"
            ) from None

        intents = discord.Intents.default()
        intents.message_content = True
        kwargs: dict[str, Any] = {"intents": intents}
        # Configured, not sniffed: one function in this process is allowed to
        # read the environment, and it is not this one.
        if self.config.proxy:
            kwargs["proxy"] = self.config.proxy
        client = discord.Client(**kwargs)

        @client.event
        async def on_message(message):
            await self._on_message(message)

        return client

    async def start(self) -> None:
        """Phase 2: open the gateway once the shared runtime is bound."""

        if self._control_runtime is None:
            raise RuntimeError(
                "Discord requires the shared ChannelRuntime to be bound "
                "before start()"
            )
        if self._client is None:  # pragma: no cover - prepare runs first
            raise RuntimeError("Discord client was not prepared")

        async def _run_gateway() -> None:
            await self._client.connect(reconnect=True)

        self._gateway = asyncio.create_task(_run_gateway(), name="omicsclaw-discord")
        done, _pending = await asyncio.wait(
            {self._gateway},
            timeout=GATEWAY_PROBE_S,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if done:
            # Roll the whole channel back rather than report a start that
            # will never receive an event: `start_all` is all-or-nothing on
            # purpose, so half a deployment never answers messages.
            error = self._gateway.exception() if not self._gateway.cancelled() else None
            await self.stop()
            raise RuntimeError(
                "Discord gateway stopped before it began serving"
                + (f" ({type(error).__name__})" if error is not None else "")
            ) from None

        self._running = True
        logger.info("Discord channel started (gateway)")

    async def stop(self) -> None:
        self.deactivate_ingress()
        gateway = self._gateway
        self._gateway = None
        if gateway is not None and not gateway.done():
            gateway.cancel()
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as error:
                logger.warning(
                    "Discord shutdown failed (%s)", type(error).__name__
                )
            self._client = None
        if gateway is not None:
            await asyncio.gather(gateway, return_exceptions=True)
        # The shared runtime is owned and closed by the runner, not by any one
        # channel: several channels share one agent.
        self._control_runtime = None
        self._control_loop = None
        self._running = False
        logger.info("Discord channel stopped")

    def run_bot(self) -> None:
        """Refuse the legacy standalone entry point.

        The bot cannot own the agent it speaks for: every channel in the
        process shares one
        :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`, composed by
        the runner from every channel's binding.
        """

        raise RuntimeError(
            "DiscordChannel.run_bot() is retired; start the bot through the "
            "runner that owns the shared ChannelRuntime: compose one with "
            "compose_channel_runtime(app, channels) and start them through "
            "ChannelManager"
        )

    # ─ Inbound ───────────────────────

    def _reply_target(self, channel_id: str) -> dict[str, Any]:
        """Where a reply goes. A Discord channel id addresses it completely."""

        return reply_target.build("discord", self._account_namespace, channel_id)

    async def _on_message(self, message: Any) -> None:
        """Normalise one Discord message into the authoritative runtime.

        Performs no model work and sends no reply: the answer is delivered by
        the runtime's pump once the exchange has run.
        """

        if not self.ingress_active:
            return
        author = getattr(message, "author", None)
        user_id = str(getattr(author, "id", "") or "")
        channel = getattr(message, "channel", None)
        channel_id = str(getattr(channel, "id", "") or "")
        message_id = str(getattr(message, "id", "") or "")
        if not user_id or not channel_id or not message_id:
            return
        if user_id == self.bot_identity:
            return

        mentions = tuple(
            str(getattr(user, "id", ""))
            for user in getattr(message, "mentions", ()) or ()
        )
        is_dm = self._is_direct_message(channel)
        addressed = bool(self.bot_identity) and self.bot_identity in mentions
        if not is_dm and not addressed:
            # The same rule SenderPolicy applies at ingress, applied here too
            # so that guild chatter costs nothing. Ingress remains the
            # authority; this only stops the work early.
            return

        text = str(getattr(message, "content", "") or "")
        if self.bot_identity:
            # Discord writes the same mention two ways depending on the
            # client that produced it; both have to come off or the model
            # reads a snowflake as part of the question.
            for spelling in (f"<@{self.bot_identity}>", f"<@!{self.bot_identity}>"):
                text = text.replace(spelling, "")
        text = text.strip()
        if not text:
            return

        if self.seen_before(message_id):
            return

        if text.startswith("/") and await self.answer_slash_command(
            self._reply_target(channel_id), channel_id, user_id, text
        ):
            return

        if not self.check_rate_limit(user_id):
            logger.warning("Discord sender exceeded the configured rate limit")
            return

        # Length and chat kind only: a chat message is the likeliest place in
        # this repository for a subject identifier to appear, and a log is the
        # most widely shared destination there is.
        logger.info("Discord message accepted (dm=%s, %d chars)", is_dm, len(text))
        await self._submit_control_inbound(
            channel_id=channel_id,
            user_id=user_id,
            text=text,
            message_id=message_id,
            chat_type="private" if is_dm else "group",
            mentions=mentions,
        )

    @staticmethod
    def _is_direct_message(channel: Any) -> bool:
        """Whether *channel* is a DM, without needing the SDK to be installed.

        ``discord.DMChannel`` when there is a discord.py to import, and the
        class name otherwise — the same fallback the delivery adapter uses to
        classify errors, for the same reason.
        """
        try:
            import discord
        except ImportError:
            return type(channel).__name__ in ("DMChannel", "GroupChannel")
        return isinstance(channel, (discord.DMChannel, discord.GroupChannel))

    async def _submit_control_inbound(
        self,
        *,
        channel_id: str,
        user_id: str,
        text: str,
        message_id: str,
        chat_type: str,
        mentions: tuple[str, ...],
    ):
        """Submit one normalised Discord message as one exchange."""

        if self._control_runtime is None:
            raise RuntimeError("Discord ChannelRuntime is not bound")
        inbound = self.inbound(
            channel_id,
            user_id,
            text,
            # The Discord snowflake is globally unique and stable across the
            # gateway's own redelivery, so it is the natural idempotency key.
            source_request_id=message_id,
            reply_target=self._reply_target(channel_id),
            values={VALUE_CHAT_TYPE: chat_type, VALUE_MENTIONS: mentions},
        )
        result = await self._control_runtime.submit(inbound)
        if result.acceptance.status is TurnAcceptanceStatus.REJECTED:
            # Refusals cannot answer through the pump, because no exchange was
            # accepted. The local cache is deliberately NOT updated, so a
            # gateway resend of a transiently rejected message can still land.
            logger.warning(
                "Discord ingress rejected: %s",
                result.acceptance.code or "unspecified",
            )
            return result
        self.remember_message(message_id)
        return result
