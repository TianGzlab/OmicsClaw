"""
Discord channel implementation for OmicsClaw.

Uses discord.py library for bot communication via Discord Gateway.
The bot listens for messages in channels/DMs and responds via the LLM core.

Prerequisites:
    pip install discord.py

Configuration via environment variables:
    DISCORD_BOT_TOKEN — Discord bot token

References:
    - https://discord.com/developers/docs/intro
    - https://discordpy.readthedocs.io/en/stable/
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from .base import Channel
from .capabilities import DISCORD as DISCORD_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger(__name__)


# ── Config ───────────────────────────────────────────────────────────


@dataclass
class DiscordConfig(BaseChannelConfig):
    """Discord channel configuration."""
    bot_token: str = ""
    text_chunk_limit: int = 2000  # Discord's message limit


# ── Channel ──────────────────────────────────────────────────────────


class DiscordChannel(Channel):
    """Discord channel using discord.py.

    Architecture:
    1. Connect via Discord Gateway using discord.py Client
    2. Listen for message events (DMs + channel mentions)
    3. Process through LLM core
    4. Reply in the same channel/DM

    Lifecycle:
        channel = DiscordChannel(config)
        await channel.start()   # connect to Discord
        await channel.run()     # blocks on event loop
        await channel.stop()    # disconnect
    """

    name = "discord"
    capabilities = DISCORD_CAPS

    def __init__(self, config: DiscordConfig):
        super().__init__(config)
        self._client = None
        self._ready = asyncio.Event()
        self._bot_user_id: str | None = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            import discord
        except ImportError:
            raise RuntimeError(
                "discord.py not installed. Run: pip install discord.py"
            )

        cfg: DiscordConfig = self.config
        if not cfg.bot_token:
            raise RuntimeError("DISCORD_BOT_TOKEN not set")

        # Detect proxy
        proxy = (
            cfg.proxy
            or os.environ.get("https_proxy")
            or os.environ.get("HTTPS_PROXY")
            or None
        )

        intents = discord.Intents.default()
        intents.message_content = True
        client_kwargs: dict[str, Any] = {"intents": intents}
        if proxy:
            client_kwargs["proxy"] = proxy

        self._client = discord.Client(**client_kwargs)

        @self._client.event
        async def on_ready():
            self._bot_user_id = str(self._client.user.id)
            logger.info(f"Discord bot ready: {self._client.user}")
            self._ready.set()

        @self._client.event
        async def on_message(message):
            await self._on_message(message)

        # Start the client in the background
        self._start_error: BaseException | None = None

        async def _guarded_start():
            try:
                await self._client.start(cfg.bot_token)
            except Exception as e:
                self._start_error = e
                self._ready.set()

        asyncio.create_task(_guarded_start())

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=60)
        except asyncio.TimeoutError:
            raise RuntimeError("Discord bot failed to connect within 60s")

        if self._start_error:
            raise RuntimeError(f"Discord bot failed: {self._start_error}")

        self._running = True
        logger.info("Discord channel started")

    async def stop(self) -> None:
        self._running = False
        if self._client:
            await self._client.close()
            self._client = None
        logger.info("Discord channel stopped")

    # ── Inbound ──────────────────────────────────────────────────────

    async def _on_message(self, message) -> None:
        """Handle incoming Discord message."""
        import discord

        # Skip own messages
        if message.author == self._client.user:
            return

        user_id = str(message.author.id)
        channel_id = str(message.channel.id)
        text = message.content or ""

        is_dm = isinstance(message.channel, discord.DMChannel)
        was_mentioned = is_dm or (self._client.user in message.mentions)

        # Skip group messages without @mention
        if not is_dm and not was_mentioned:
            return

        # Strip @mention from text
        if was_mentioned and not is_dm:
            text = text.replace(f"<@{self._bot_user_id}>", "").strip()
            text = text.replace(f"<@!{self._bot_user_id}>", "").strip()

        if not text:
            return

        # Dedup & rate limit
        msg_id = str(message.id)
        if self.is_duplicate(msg_id):
            return
        if not self.check_rate_limit(user_id):
            return

        logger.info(f"Discord message from {message.author}: {text[:80]}")
        asyncio.create_task(
            self._handle_message(channel_id, user_id, text, message)
        )

    async def _handle_message(
        self, channel_id: str, user_id: str, content: str, message,
    ) -> None:
        """Process message through core LLM and reply."""
        try:
            # Start typing
            await self.start_typing(channel_id)

            reply = await self.process_message(
                channel_id, user_id, content,
                platform="discord",
            )

            await self.stop_typing(channel_id)

            if reply:
                await self.send(channel_id, reply)
        except Exception as e:
            await self.stop_typing(channel_id)
            logger.error(f"Discord process error: {e}", exc_info=True)
            try:
                await self.send(channel_id, f"Sorry, an error occurred: {type(e).__name__}")
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
        """Send a text chunk to a Discord channel."""
        if not self._client:
            return
        ch = self._client.get_channel(int(chat_id))
        if not ch:
            logger.error(f"Discord channel {chat_id} not found")
            return
        await ch.send(raw_text)

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a file via Discord."""
        try:
            import discord
            if not self._client:
                return False
            ch = self._client.get_channel(int(chat_id))
            if not ch:
                return False
            f = discord.File(file_path)
            await ch.send(content=caption or None, file=f)
            return True
        except Exception as e:
            logger.error(f"Discord media send error: {e}")
            return False

    # ── Typing indicator ─────────────────────────────────────────────

    async def _send_typing(self, chat_id: str) -> None:
        """Send typing indicator to Discord channel."""
        if not self._client:
            return
        ch = self._client.get_channel(int(chat_id))
        if ch:
            try:
                await ch.trigger_typing()
            except Exception:
                pass

    # ── Backward-compatible entry point ──────────────────────────────

    def run_bot(self) -> None:
        """Blocking entry point for running the Discord channel standalone."""
        asyncio.run(self.run())
