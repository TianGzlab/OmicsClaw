"""
Slack channel implementation for OmicsClaw.

Uses the Slack SDK with Socket Mode — no public IP or webhook required.
The bot connects via the app-level token and receives events in real-time.

Prerequisites:
    pip install slack-sdk aiohttp

Configuration via environment variables:
    SLACK_BOT_TOKEN  — Bot User OAuth Token (xoxb-...)
    SLACK_APP_TOKEN  — App-Level Token (xapp-...) for Socket Mode

References:
    - https://api.slack.com/apis/connections/socket
    - https://slack.dev/python-slack-sdk/socket-mode/
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .base import Channel
from .capabilities import SLACK as SLACK_CAPS
from .config import BaseChannelConfig

logger = logging.getLogger(__name__)


# ── Config ───────────────────────────────────────────────────────────


@dataclass
class SlackConfig(BaseChannelConfig):
    """Slack channel configuration."""
    bot_token: str = ""   # xoxb-... (Bot User OAuth Token)
    app_token: str = ""   # xapp-... (App-Level Token for Socket Mode)
    text_chunk_limit: int = 4096


# ── Channel ──────────────────────────────────────────────────────────


class SlackChannel(Channel):
    """Slack channel using Socket Mode (no public endpoint needed).

    Architecture:
    1. Connect via Socket Mode using App-Level Token
    2. Listen for message/app_mention events
    3. Process through LLM core
    4. Reply via Web API (chat.postMessage)

    Lifecycle:
        channel = SlackChannel(config)
        await channel.start()   # authentication + socket connect
        await channel.run()     # blocks on event loop
        await channel.stop()    # disconnect
    """

    name = "slack"
    capabilities = SLACK_CAPS

    def __init__(self, config: SlackConfig):
        super().__init__(config)
        self._socket_client = None
        self._web_client = None
        self._bot_user_id: str | None = None
        self._typing_msg_ts: dict[str, str] = {}  # chat_id → ts of "..." message

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        cfg: SlackConfig = self.config
        if not cfg.bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN not set")
        if not cfg.app_token:
            raise RuntimeError(
                "SLACK_APP_TOKEN not set (must start with xapp- for Socket Mode)"
            )

        try:
            from slack_sdk.web.async_client import AsyncWebClient
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.socket_mode.request import SocketModeRequest
            from slack_sdk.socket_mode.response import SocketModeResponse
        except ImportError:
            raise RuntimeError(
                "slack-sdk or aiohttp not installed. "
                "Run: pip install slack-sdk aiohttp"
            )

        proxy = self.config.proxy
        self._web_client = AsyncWebClient(
            token=cfg.bot_token,
            proxy=proxy,
        )

        # Authenticate and get bot user id
        try:
            auth = await asyncio.wait_for(
                self._web_client.auth_test(), timeout=15,
            )
            self._bot_user_id = auth["user_id"]
            logger.info(f"Slack bot authenticated: {auth.get('user', 'unknown')}")
        except asyncio.TimeoutError:
            raise RuntimeError("Slack auth_test timed out — check token and network")
        except Exception as e:
            raise RuntimeError(f"Slack auth failed: {e}")

        # Set up Socket Mode client
        self._socket_client = SocketModeClient(
            app_token=cfg.app_token,
            web_client=self._web_client,
        )

        async def _event_handler(
            client: SocketModeClient,
            req: SocketModeRequest,
        ) -> None:
            # ACK immediately
            resp = SocketModeResponse(envelope_id=req.envelope_id)
            await client.send_socket_mode_response(resp)

            if req.type == "events_api":
                event = req.payload.get("event", {})
                event_type = event.get("type", "")
                if event_type == "message" and "subtype" not in event:
                    is_dm = event.get("channel_type") == "im"
                    await self._on_message(event, is_group=not is_dm, was_mentioned=is_dm)
                elif event_type == "app_mention":
                    await self._on_message(event, is_group=True, was_mentioned=True)

        self._socket_client.socket_mode_request_listeners.append(_event_handler)

        try:
            await asyncio.wait_for(self._socket_client.connect(), timeout=30)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Slack Socket Mode connection timed out — "
                "check app token and Socket Mode settings"
            )

        self._running = True
        logger.info("Slack channel started (Socket Mode)")

    async def stop(self) -> None:
        self._running = False
        if self._socket_client:
            try:
                await self._socket_client.close()
            except Exception:
                pass
            self._socket_client = None
        self._web_client = None
        logger.info("Slack channel stopped")

    # ── Inbound ──────────────────────────────────────────────────────

    async def _on_message(
        self,
        event: dict,
        *,
        is_group: bool = False,
        was_mentioned: bool = True,
    ) -> None:
        """Handle incoming Slack event."""
        user_id = event.get("user", "")

        # Skip own messages and bot messages
        if user_id == self._bot_user_id:
            return
        if event.get("bot_id"):
            return

        channel_id = event.get("channel", "")
        text = event.get("text", "")
        ts = event.get("ts", "")
        thread_ts = event.get("thread_ts") or ts

        # Strip @mention
        if was_mentioned and self._bot_user_id:
            text = text.replace(f"<@{self._bot_user_id}>", "").strip()

        if not text:
            return

        # Skip group messages without mention
        if is_group and not was_mentioned:
            return

        # Dedup & rate limit
        if self.is_duplicate(ts):
            return
        if not self.check_rate_limit(user_id):
            return

        logger.info(f"Slack message from {user_id}: {text[:80]}")
        asyncio.create_task(
            self._handle_message(channel_id, user_id, text, thread_ts)
        )

    async def _handle_message(
        self, channel_id: str, user_id: str, content: str, thread_ts: str,
    ) -> None:
        """Process message through core LLM and reply in thread."""
        try:
            await self.start_typing(channel_id)

            reply = await self.process_message(
                channel_id, user_id, content,
                platform="slack",
            )

            await self.stop_typing(channel_id)

            if reply:
                # Reply in thread
                await self._send_to_channel(channel_id, reply, thread_ts)
        except Exception as e:
            await self.stop_typing(channel_id)
            logger.error(f"Slack process error: {e}", exc_info=True)
            try:
                await self._send_to_channel(
                    channel_id,
                    f"Sorry, an error occurred: {type(e).__name__}",
                    thread_ts,
                )
            except Exception:
                pass

    async def _send_to_channel(
        self, channel_id: str, text: str, thread_ts: str = "",
    ) -> None:
        """Send a message to a Slack channel, optionally in a thread."""
        if not self._web_client:
            return
        kwargs: dict[str, Any] = {"channel": channel_id, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        await self._web_client.chat_postMessage(**kwargs)

    # ── Send (Channel ABC) ───────────────────────────────────────────

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        """Send a text chunk to a Slack channel."""
        thread_ts = metadata.get("thread_ts", "")
        await self._send_to_channel(chat_id, raw_text, thread_ts)

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Upload and send a file via Slack files_upload_v2."""
        try:
            if not self._web_client:
                return False
            await self._web_client.files_upload_v2(
                channel=chat_id,
                file=file_path,
                initial_comment=caption or None,
            )
            return True
        except Exception as e:
            logger.error(f"Slack media send error: {e}")
            return False

    # ── Typing indicator ─────────────────────────────────────────────

    async def _send_typing(self, chat_id: str) -> None:
        """Approximate typing indicator by posting a "…" message."""
        if not self._web_client:
            return
        try:
            resp = await self._web_client.chat_postMessage(
                channel=chat_id,
                text="…",
            )
            ts = resp.get("ts")
            if ts:
                self._typing_msg_ts[chat_id] = ts
        except Exception:
            pass

    async def stop_typing(self, chat_id: str) -> None:
        """Delete the typing placeholder message."""
        ts = self._typing_msg_ts.pop(chat_id, None)
        if ts and self._web_client:
            try:
                await self._web_client.chat_delete(channel=chat_id, ts=ts)
            except Exception:
                pass
        await super().stop_typing(chat_id)

    # ── Backward-compatible entry point ──────────────────────────────

    def run_bot(self) -> None:
        """Blocking entry point for running Slack channel standalone."""
        asyncio.run(self.run())
