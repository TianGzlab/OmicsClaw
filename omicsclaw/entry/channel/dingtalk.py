"""
DingTalk (钉钉) channel implementation for OmicsClaw.

Uses the DingTalk Stream (WebSocket) protocol — no public IP required. The
socket is driven by ``websockets`` on the running event loop, so nothing
here crosses a thread boundary. Replies leave through the Robot REST API.

**Attribution here is weaker than on Telegram or Feishu, and the difference
is worth stating.** DingTalk does not report a list of mentioned identities
that this bot's own id could be looked up in. What it reports is a boolean,
``isInAtList``, which is the platform asserting "this message @-mentioned
you". This adapter translates that assertion into the vocabulary
:class:`~omicsclaw.entry.ingress.SenderPolicy` reads — it puts the
configured robot identity into the mention list **only when the boolean is
true**. So what is verified is *DingTalk says this was aimed at us*, not *we
found ourselves in the mention list*. Putting the identity there
unconditionally would make the group gate always open, which is the same as
having no gate.

**Replies are one-to-one even for a group message.** ``oToMessages/batchSend``
addresses people, not conversations, so an answer to something said in a
group arrives in the sender's direct chat. That is what this API does and
what the reply target therefore names.

Configuration via environment variables (read by ``omicsclaw/launch/``, never
here):
    DINGTALK_CLIENT_ID       — Robot App Key
    DINGTALK_CLIENT_SECRET   — Robot App Secret

References:
    - https://open.dingtalk.com/document/isvapp/create-a-robot
    - https://open.dingtalk.com/document/orgapp/the-robot-sends-a-one-on-one-message
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

from omicsclaw.entry.ingress import (
    SenderPolicy,
    VALUE_CHAT_TYPE,
    VALUE_MENTIONS,
)

from . import reply_target
from .base import Channel
from .binding import ChannelSurfaceBinding
from .capabilities import DINGTALK as DINGTALK_CAPS
from .config import BaseChannelConfig
from .dingtalk_delivery import DingTalkDeliveryAdapter
from .runtime import TurnAcceptanceStatus

logger = logging.getLogger("omicsclaw.channel.dingtalk")

# ─ DingTalk API endpoints ───────────────────

GATEWAY_URL = "https://api.dingtalk.com/v1.0/gateway/connections/open"
TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"

GROUP_CONVERSATION_TYPE = "2"
"""``conversationType`` for a group chat; ``"1"`` is one-to-one."""

RECONNECT_DELAY_S = 5.0


# ─ Config ─────────────────────────


@dataclass
class DingTalkConfig(BaseChannelConfig):
    """DingTalk channel configuration."""

    client_id: str = ""  # Robot App Key
    client_secret: str = ""  # Robot App Secret
    text_chunk_limit: int = 4096


# ─ Channel ────────────────────────


class DingTalkChannel(Channel):
    """DingTalk channel using Stream Mode (WebSocket).

    Owner text enters the authoritative
    :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`; answers leave
    only through its delivery pump, which is what classifies whether they
    were accepted. Inbound attachments and outbound media are fail-closed.
    """

    name = "dingtalk"
    capabilities = DINGTALK_CAPS
    authoritative_ingress = True

    def __init__(self, config: DingTalkConfig):
        super().__init__(config)
        self.dingtalk_config = config
        self._http_client = None
        self._access_token: str | None = None
        self._token_expires: float = 0.0
        self._ws = None
        self._ws_task: asyncio.Task[None] | None = None
        self._account_namespace = ""
        self.bot_identity = ""
        """The robot's App Key, which is what a proven mention resolves to.

        Empty until :meth:`prepare_control_binding` has run, which is exactly
        when a group message cannot be attributed and therefore fails closed.
        """

    # ─ Lifecycle ──────────────────────

    async def prepare_control_binding(self) -> ChannelSurfaceBinding:
        """Authenticate far enough to describe this robot's control binding."""

        owners = self._owner_subjects()
        if not owners:
            raise RuntimeError(
                "DingTalk authoritative ingress requires DINGTALK_ALLOWED_SENDERS"
            )
        client_id = self.dingtalk_config.client_id.strip()
        if not client_id or not self.dingtalk_config.client_secret.strip():
            raise RuntimeError(
                "DINGTALK_CLIENT_ID and DINGTALK_CLIENT_SECRET are required"
            )
        if self._http_client is None:
            self._http_client = self._build_http_client()
        await self._refresh_token()

        self._account_namespace = f"robot-{client_id}"
        self.bot_identity = client_id

        return ChannelSurfaceBinding(
            adapter="dingtalk",
            account_namespace=self._account_namespace,
            sender_policy=SenderPolicy(
                allowed_senders=owners,
                bot_identity=self.bot_identity,
            ),
            delivery_adapter=DingTalkDeliveryAdapter(
                self._http_client, self._ensure_token
            ),
            text_chunk_limit=(
                self.config.text_chunk_limit or self.capabilities.max_text_length
            ),
            attachment_input_enabled=False,
        )

    def _build_http_client(self) -> Any:
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed. Run: pip install httpx") from None
        return httpx.AsyncClient(timeout=15)

    async def start(self) -> None:
        """Phase 2: open the stream once the shared runtime is bound."""

        if self._control_runtime is None:
            raise RuntimeError(
                "DingTalk requires the shared ChannelRuntime to be bound "
                "before start()"
            )
        if self._http_client is None:  # pragma: no cover - prepare runs first
            raise RuntimeError("DingTalk was not prepared")
        self._running = True
        self._ws_task = asyncio.create_task(
            self._ws_loop(), name="omicsclaw-dingtalk"
        )
        logger.info("DingTalk channel started (Stream Mode)")

    async def stop(self) -> None:
        self.deactivate_ingress()
        self._running = False
        task = self._ws_task
        self._ws_task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as error:
                logger.warning(
                    "DingTalk socket shutdown failed (%s)", type(error).__name__
                )
            self._ws = None
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception as error:
                logger.warning(
                    "DingTalk HTTP shutdown failed (%s)", type(error).__name__
                )
            self._http_client = None
        self._access_token = None
        # The shared runtime is owned and closed by the runner, not by any one
        # channel: several channels share one agent.
        self._control_runtime = None
        self._control_loop = None
        logger.info("DingTalk channel stopped")

    def run_stream(self) -> None:
        """Refuse the legacy standalone entry point.

        The robot cannot own the agent it speaks for: every channel in the
        process shares one
        :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`, composed by
        the runner from every channel's binding.
        """

        raise RuntimeError(
            "DingTalkChannel.run_stream() is retired; start the robot through "
            "the runner that owns the shared ChannelRuntime: compose one with "
            "compose_channel_runtime(app, channels) and start them through "
            "ChannelManager"
        )

    # ─ Token management ────────────────────

    async def _refresh_token(self) -> None:
        """Fetch an access token from DingTalk OAuth2."""
        response = await self._http_client.post(
            TOKEN_URL,
            json={
                "appKey": self.dingtalk_config.client_id,
                "appSecret": self.dingtalk_config.client_secret,
            },
        )
        data = response.json()
        token = data.get("accessToken")
        if not token:
            raise RuntimeError(
                f"DingTalk auth failed (code {data.get('code', 'unknown')})"
            )
        self._access_token = token
        expires_in = int(data.get("expireIn", 7200))
        # Five minutes early, so a token never expires between the check and
        # the call it was fetched for.
        self._token_expires = time.monotonic() + expires_in - 300

    async def _ensure_token(self) -> str:
        """A token that is valid now, refreshing it if it is not."""
        if not self._access_token or time.monotonic() >= self._token_expires:
            await self._refresh_token()
        return self._access_token or ""

    # ─ WebSocket stream ────────────────────

    async def _get_ws_url(self) -> str:
        """Open a gateway connection and return the socket URL it names."""
        response = await self._http_client.post(
            GATEWAY_URL,
            json={
                "clientId": self.dingtalk_config.client_id,
                "clientSecret": self.dingtalk_config.client_secret,
                "subscriptions": [
                    {"type": "CALLBACK", "topic": "/v1.0/im/bot/messages/get"}
                ],
                "ua": "omicsclaw-dingtalk/0.1",
            },
        )
        data = response.json()
        endpoint, ticket = data.get("endpoint"), data.get("ticket")
        if not endpoint or not ticket:
            raise RuntimeError("DingTalk gateway returned no endpoint")
        return f"{endpoint}?ticket={quote_plus(ticket)}"

    async def _ws_loop(self) -> None:
        """Receive events until stopped, reconnecting when the socket drops."""
        try:
            import websockets
        except ImportError:
            raise RuntimeError(
                "websockets not installed. Run: pip install websockets"
            ) from None

        while self._running:
            try:
                async with websockets.connect(await self._get_ws_url()) as socket:
                    self._ws = socket
                    logger.info("DingTalk WebSocket connected")
                    async for raw in socket:
                        await self._on_raw(raw)
            except asyncio.CancelledError:
                break
            except Exception as error:
                logger.warning(
                    "DingTalk socket dropped (%s); reconnecting",
                    type(error).__name__,
                )
                await asyncio.sleep(RECONNECT_DELAY_S)

    async def _on_raw(self, raw: Any) -> None:
        """Decode one frame, never letting a bad one end the loop."""
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except json.JSONDecodeError:
            logger.warning("DingTalk sent a frame that is not JSON")
            return
        try:
            await self._on_ws_message(data)
        except Exception as error:
            # Type only, and no traceback: a provider exception can embed the
            # payload, which on this path is what somebody wrote.
            logger.error("DingTalk event handler error (%s)", type(error).__name__)

    async def _ws_send_json(self, data: dict) -> None:
        if self._ws is not None:
            await self._ws.send(json.dumps(data))

    async def _on_ws_message(self, data: Any) -> None:
        """Normalise one Stream frame into the authoritative runtime.

        Performs no model work and sends no reply: the answer is delivered by
        the runtime's pump once the exchange has run.
        """

        if not isinstance(data, dict):
            return
        headers = data.get("headers", {}) or {}
        message_id = str(headers.get("messageId", "") or "")

        if data.get("type") == "SYSTEM" and headers.get("topic") == "ping":
            await self._ws_send_json(
                {
                    "code": 200,
                    "headers": headers,
                    "message": "OK",
                    "data": data.get("data", ""),
                }
            )
            return

        # Acknowledge first. DingTalk resends anything it has not heard back
        # about, and an exchange takes far longer than it waits; the
        # idempotency key on the submission is what makes a resend we did not
        # prevent resolve to the same exchange.
        await self._ws_send_json(
            {
                "code": 200,
                "headers": {
                    "contentType": "application/json",
                    "messageId": message_id,
                },
                "message": "OK",
                "data": "{}",
            }
        )

        if data.get("type") != "CALLBACK" or not self.ingress_active:
            return

        payload = data.get("data", "{}")
        if isinstance(payload, (str, bytes)):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            return
        await self._on_payload(message_id, payload)

    async def _on_payload(self, message_id: str, payload: dict) -> None:
        """Handle one decoded callback payload."""

        text_field = payload.get("text", {})
        content = (
            text_field.get("content", "")
            if isinstance(text_field, dict)
            else str(text_field)
        ).strip()
        if not content:
            content = str(payload.get("content", "") or "").strip()
        if not content:
            return

        sender_id = str(
            payload.get("senderStaffId") or payload.get("senderId") or ""
        )
        if not sender_id or not message_id:
            return

        is_group = payload.get("conversationType") == GROUP_CONVERSATION_TYPE
        mentions = self._proven_mentions(payload, is_group=is_group)
        if is_group and not mentions:
            # The same rule SenderPolicy applies at ingress, applied here too
            # so that group chatter costs nothing. Ingress remains the
            # authority; this only stops the work early.
            return

        if self.seen_before(message_id):
            return

        if content.startswith("/") and await self.answer_slash_command(
            self._reply_target(sender_id), sender_id, sender_id, content
        ):
            return

        if not self._is_admin(sender_id) and not self.check_rate_limit(sender_id):
            logger.warning("DingTalk sender exceeded the configured rate limit")
            return

        # Length and chat kind only: a chat message is the likeliest place in
        # this repository for a subject identifier to appear, and a log is the
        # most widely shared destination there is.
        logger.info(
            "DingTalk message accepted (group=%s, %d chars)", is_group, len(content)
        )
        await self._submit_control_inbound(
            sender_id=sender_id,
            text=content,
            message_id=message_id,
            chat_type="group" if is_group else "private",
            mentions=mentions,
        )

    def _proven_mentions(self, payload: dict, *, is_group: bool) -> tuple[str, ...]:
        """This robot's identity, but only when DingTalk says it was mentioned.

        The boolean is the whole of the attribution DingTalk offers, so it is
        translated rather than trusted blindly: an unconditional identity
        here would make :meth:`~omicsclaw.entry.ingress.SenderPolicy.admits`
        return true for every group message, which is a gate that is always
        open.
        """
        if not is_group:
            return ()
        if not self.bot_identity or not payload.get("isInAtList"):
            return ()
        return (self.bot_identity,)

    def _reply_target(self, staff_id: str) -> dict[str, Any]:
        """Where a reply goes: to a person, because that is what this API does.

        ``robot_code`` travels with it because ``batchSend`` names the robot
        that speaks, and the delivery adapter has no other way to know it.
        """

        return reply_target.build(
            "dingtalk",
            self._account_namespace,
            staff_id,
            robot_code=self.dingtalk_config.client_id.strip(),
        )

    async def _submit_control_inbound(
        self,
        *,
        sender_id: str,
        text: str,
        message_id: str,
        chat_type: str,
        mentions: tuple[str, ...],
    ):
        """Submit one normalised DingTalk message as one exchange."""

        if self._control_runtime is None:
            raise RuntimeError("DingTalk ChannelRuntime is not bound")
        inbound = self.inbound(
            sender_id,
            sender_id,
            text,
            # The Stream header's messageId is stable across DingTalk's own
            # redelivery, so it is the natural idempotency key.
            source_request_id=message_id,
            reply_target=self._reply_target(sender_id),
            values={VALUE_CHAT_TYPE: chat_type, VALUE_MENTIONS: mentions},
        )
        result = await self._control_runtime.submit(inbound)
        if result.acceptance.status is TurnAcceptanceStatus.REJECTED:
            # Refusals cannot answer through the pump, because no exchange was
            # accepted. The local cache is deliberately NOT updated, so a
            # DingTalk resend of a transiently rejected message can still land.
            logger.warning(
                "DingTalk ingress rejected: %s",
                result.acceptance.code or "unspecified",
            )
            return result
        self.remember_message(message_id)
        return result
