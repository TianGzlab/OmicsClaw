"""
Slack channel implementation for OmicsClaw.

Uses the Slack SDK with Socket Mode — no public IP or webhook required. The
bot connects with an app-level token and receives events over a WebSocket
that ``slack_sdk`` drives on the running event loop, so nothing here crosses
a thread boundary.

Start-up is two-phase, as it is for every adapter in this package:
:meth:`SlackChannel.prepare_control_binding` authenticates and describes the
account, the runner composes one shared runtime over every channel's binding,
and only then does :meth:`SlackChannel.start` open the socket.

Group channels fail closed. A channel message is admitted only when this
bot's own ``<@U…>`` handle appears among the identities the message
@-mentioned — read out of the message text rather than inferred from the
event name, so that an ``app_mention`` Slack delivered for some other reason
still has to prove it was aimed here.

Configuration via environment variables (read by ``omicsclaw/launch/``, never
here):
    SLACK_BOT_TOKEN  — Bot User OAuth Token (xoxb-...)
    SLACK_APP_TOKEN  — App-Level Token (xapp-...) for Socket Mode

References:
    - https://api.slack.com/apis/connections/socket
    - https://slack.dev/python-slack-sdk/socket-mode/
"""

from __future__ import annotations

import asyncio
import logging
import re
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
from .capabilities import SLACK as SLACK_CAPS
from .config import BaseChannelConfig
from .runtime import TurnAcceptanceStatus
from .slack_delivery import SlackDeliveryAdapter

logger = logging.getLogger("omicsclaw.channel.slack")

_MENTION = re.compile(r"<@([A-Z0-9]+)>")

AUTH_TIMEOUT_S = 15.0
CONNECT_TIMEOUT_S = 30.0


# ─ Config ─────────────────────────


@dataclass
class SlackConfig(BaseChannelConfig):
    """Slack channel configuration."""

    bot_token: str = ""  # xoxb-... (Bot User OAuth Token)
    app_token: str = ""  # xapp-... (App-Level Token for Socket Mode)
    text_chunk_limit: int = 4096


def slack_mentions(text: str) -> tuple[str, ...]:
    """Every identity *text* @-mentioned, in the spelling Slack writes.

    Slack puts a mention in the message body as ``<@U123>`` and reports no
    separate entity list, so the body is where the attribution lives.
    Returns an empty tuple when nobody was mentioned, which in a channel is
    what makes the message fail closed.
    """
    return tuple(f"<@{found}>" for found in _MENTION.findall(text or ""))


# ─ Channel ────────────────────────


class SlackChannel(Channel):
    """Slack channel using Socket Mode (no public endpoint needed).

    Owner text enters the authoritative
    :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`; answers leave
    only through its delivery pump, which is what classifies whether they
    were accepted. Inbound files and outbound media are fail-closed.
    """

    name = "slack"
    capabilities = SLACK_CAPS
    authoritative_ingress = True

    def __init__(self, config: SlackConfig):
        super().__init__(config)
        self.slack_config = config
        self._socket_client = None
        self._web_client = None
        self._account_namespace = ""
        self.bot_identity = ""
        """This bot's own ``<@U…>`` handle, read back from Slack.

        Empty until :meth:`prepare_control_binding` has authenticated, which
        is exactly when a channel mention cannot be attributed and therefore
        fails closed."""
        self._typing_msg_ts: dict[str, str] = {}

    # ─ Lifecycle ──────────────────────

    async def prepare_control_binding(self) -> ChannelSurfaceBinding:
        """Authenticate far enough to describe this bot's control binding.

        ``auth_test`` is what makes the account namespace and the bot handle
        *authenticated* rather than configured: one process serving two Slack
        apps cannot then deliver one app's reply through the other's token.
        """

        owners = self._owner_subjects()
        if not owners:
            raise RuntimeError(
                "Slack authoritative ingress requires SLACK_ALLOWED_SENDERS"
            )
        if not self.slack_config.bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN is required")
        if not self.slack_config.app_token:
            raise RuntimeError(
                "SLACK_APP_TOKEN is required (xapp-... for Socket Mode)"
            )
        if self._web_client is None:
            self._web_client = self._build_web_client()

        try:
            auth = await asyncio.wait_for(
                self._web_client.auth_test(), timeout=AUTH_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Slack auth_test timed out; check the bot token and the network"
            ) from None
        team_id = str(auth["team_id"] or "").strip()
        user_id = str(auth["user_id"] or "").strip()
        if not team_id or not user_id:
            raise RuntimeError("Slack identity is unavailable")
        self._account_namespace = f"team-{team_id}"
        self.bot_identity = f"<@{user_id}>"
        logger.info("Slack bot authenticated for %s", self._account_namespace)

        return ChannelSurfaceBinding(
            adapter="slack",
            account_namespace=self._account_namespace,
            sender_policy=SenderPolicy(
                allowed_senders=owners,
                bot_identity=self.bot_identity,
            ),
            delivery_adapter=SlackDeliveryAdapter(self._web_client),
            text_chunk_limit=(
                self.config.text_chunk_limit or self.capabilities.max_text_length
            ),
            attachment_input_enabled=False,
        )

    def _build_web_client(self) -> Any:
        try:
            from slack_sdk.web.async_client import AsyncWebClient
        except ImportError:
            raise RuntimeError(
                "slack-sdk not installed. Run: pip install slack-sdk aiohttp"
            ) from None
        return AsyncWebClient(
            token=self.slack_config.bot_token, proxy=self.config.proxy
        )

    async def start(self) -> None:
        """Phase 2: open the socket once the shared runtime is bound."""

        if self._control_runtime is None:
            raise RuntimeError(
                "Slack requires the shared ChannelRuntime to be bound before start()"
            )
        if self._web_client is None:  # pragma: no cover - prepare runs first
            raise RuntimeError("Slack was not prepared")

        try:
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.socket_mode.response import SocketModeResponse
        except ImportError:
            raise RuntimeError(
                "slack-sdk or aiohttp not installed. "
                "Run: pip install slack-sdk aiohttp"
            ) from None

        self._socket_client = SocketModeClient(
            app_token=self.slack_config.app_token,
            web_client=self._web_client,
        )

        async def _event_handler(client, request) -> None:
            # Acknowledge first: Slack resends anything it has not heard back
            # about within three seconds, and an exchange takes longer than
            # that. The idempotency key on the submission is what makes a
            # resend we did not prevent resolve to the same exchange.
            await client.send_socket_mode_response(
                SocketModeResponse(envelope_id=request.envelope_id)
            )
            if request.type != "events_api":
                return
            event = request.payload.get("event", {})
            kind = event.get("type", "")
            if kind == "message" and "subtype" not in event:
                await self._on_message(
                    event, is_group=event.get("channel_type") != "im"
                )
            elif kind == "app_mention":
                await self._on_message(event, is_group=True)

        self._socket_client.socket_mode_request_listeners.append(_event_handler)

        try:
            await asyncio.wait_for(
                self._socket_client.connect(), timeout=CONNECT_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            await self.stop()
            raise RuntimeError(
                "Slack Socket Mode connection timed out; check the app token "
                "and that Socket Mode is enabled"
            ) from None

        self._running = True
        logger.info("Slack channel started (Socket Mode)")

    async def stop(self) -> None:
        self.deactivate_ingress()
        if self._socket_client:
            try:
                await self._socket_client.close()
            except Exception as error:
                logger.warning(
                    "Slack socket shutdown failed (%s)", type(error).__name__
                )
            self._socket_client = None
        self._web_client = None
        # The shared runtime is owned and closed by the runner, not by any one
        # channel: several channels share one agent.
        self._control_runtime = None
        self._control_loop = None
        self._running = False
        logger.info("Slack channel stopped")

    def run_bot(self) -> None:
        """Refuse the legacy standalone entry point.

        The bot cannot own the agent it speaks for: every channel in the
        process shares one
        :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`, composed by
        the runner from every channel's binding.
        """

        raise RuntimeError(
            "SlackChannel.run_bot() is retired; start the bot through the "
            "runner that owns the shared ChannelRuntime: compose one with "
            "compose_channel_runtime(app, channels) and start them through "
            "ChannelManager"
        )

    # ─ Inbound ───────────────────────

    def _reply_target(self, channel_id: str, thread_ts: str) -> dict[str, Any]:
        """Where a reply to this message goes — in its thread where there is one."""

        return reply_target.build(
            "slack",
            self._account_namespace,
            channel_id,
            thread_ts=thread_ts or None,
        )

    async def _on_message(self, event: dict, *, is_group: bool) -> None:
        """Normalise one Slack event into the authoritative runtime.

        Performs no model work and sends no reply: the answer is delivered by
        the runtime's pump once the exchange has run.
        """

        if not self.ingress_active:
            return
        user_id = str(event.get("user", "") or "")
        channel_id = str(event.get("channel", "") or "")
        message_ts = str(event.get("ts", "") or "")
        if not user_id or not channel_id or not message_ts:
            return
        if event.get("bot_id") or (
            self.bot_identity and self.bot_identity == f"<@{user_id}>"
        ):
            return

        raw_text = str(event.get("text", "") or "")
        mentions = slack_mentions(raw_text)
        addressed = bool(self.bot_identity) and self.bot_identity in mentions
        if is_group and not addressed:
            # The same rule SenderPolicy applies at ingress, applied here too
            # so that channel chatter costs nothing. Ingress remains the
            # authority; this only stops the work early.
            return

        text = raw_text.replace(self.bot_identity, "").strip()
        if not text:
            return

        key = f"{channel_id}:{message_ts}"
        if self.seen_before(key):
            return

        thread_ts = str(event.get("thread_ts") or message_ts)
        if text.startswith("/") and await self.answer_slash_command(
            self._reply_target(channel_id, thread_ts), channel_id, user_id, text
        ):
            return

        if not self.check_rate_limit(user_id):
            logger.warning("Slack sender exceeded the configured rate limit")
            return

        # Length and chat kind only: a chat message is the likeliest place in
        # this repository for a subject identifier to appear, and a log is the
        # most widely shared destination there is.
        logger.info(
            "Slack message accepted (group=%s, %d chars)", is_group, len(text)
        )
        await self._submit_control_inbound(
            channel_id=channel_id,
            user_id=user_id,
            text=text,
            key=key,
            thread_ts=thread_ts,
            chat_type="group" if is_group else "private",
            mentions=mentions,
        )

    async def _submit_control_inbound(
        self,
        *,
        channel_id: str,
        user_id: str,
        text: str,
        key: str,
        thread_ts: str,
        chat_type: str,
        mentions: tuple[str, ...],
    ):
        """Submit one normalised Slack message as one exchange."""

        if self._control_runtime is None:
            raise RuntimeError("Slack ChannelRuntime is not bound")
        inbound = self.inbound(
            channel_id,
            user_id,
            text,
            # Channel plus message timestamp: Slack's own identity for the
            # message, stable across the resends an unacknowledged event
            # causes, so a repeat resolves to the exchange already running.
            source_request_id=key,
            reply_target=self._reply_target(channel_id, thread_ts),
            values={VALUE_CHAT_TYPE: chat_type, VALUE_MENTIONS: mentions},
        )
        result = await self._control_runtime.submit(inbound)
        if result.acceptance.status is TurnAcceptanceStatus.REJECTED:
            # Refusals cannot answer through the pump, because no exchange was
            # accepted. The local cache is deliberately NOT updated, so a
            # Slack resend of a transiently rejected message can still land.
            logger.warning(
                "Slack ingress rejected: %s", result.acceptance.code or "unspecified"
            )
            return result
        self.remember_message(key)
        return result

    # ─ Typing indicator ────────────────────

    async def _send_typing(self, chat_id: str) -> None:
        """Approximate a typing indicator by posting a "…" and deleting it.

        A direct provider call that reports nothing. It is tolerable for a
        hint — if it goes missing the person sees one fewer ellipsis — and it
        is exactly why an answer may not travel this way.
        """
        if not self._web_client:
            return
        try:
            response = await self._web_client.chat_postMessage(
                channel=chat_id, text="…"
            )
            ts = response.get("ts")
            if ts:
                self._typing_msg_ts[chat_id] = ts
        except Exception as error:
            logger.debug("Slack typing hint failed (%s)", type(error).__name__)

    async def stop_typing(self, chat_id: str) -> None:
        """Delete the typing placeholder, if one was posted."""
        ts = self._typing_msg_ts.pop(chat_id, None)
        if ts and self._web_client:
            try:
                await self._web_client.chat_delete(channel=chat_id, ts=ts)
            except Exception as error:
                logger.debug(
                    "Slack typing cleanup failed (%s)", type(error).__name__
                )
        await super().stop_typing(chat_id)
