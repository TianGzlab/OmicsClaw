"""
QQ channel implementation for OmicsClaw using the qq-botpy SDK.

Supports C2C (direct) and group messages over the QQ Bot Gateway
(WebSocket, no public IP needed). botpy runs its socket on the event loop it
is started from, so nothing here crosses a thread boundary.

**Attribution here is weaker than on Telegram or Feishu, and the difference
is worth stating.** QQ reports no list of mentioned identities. What it does
instead is pre-filter: ``on_group_at_message_create`` fires *only* for group
messages that @-mentioned this bot. That callback name is therefore the
platform asserting "this was aimed at you", and this adapter translates the
assertion into the vocabulary
:class:`~omicsclaw.entry.ingress.SenderPolicy` reads — it puts the
configured app id into the mention list **only** on that callback. So what
is verified is *QQ says this was aimed at us*, not *we found ourselves in the
mention list*. Doing it unconditionally would make the group gate always
open, which is the same as having no gate.

Configuration via environment variables (read by ``omicsclaw/launch/``, never
here):
    QQ_APP_ID       — Bot AppID from the QQ Open Platform
    QQ_APP_SECRET   — Bot AppSecret

References:
    - https://q.qq.com/doc/      (QQ Open Platform)
    - https://github.com/tencent-connect/botpy
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
from .capabilities import QQ as QQ_CAPS
from .config import BaseChannelConfig
from .qq_delivery import MessageSequence, QQDeliveryAdapter
from .runtime import TurnAcceptanceStatus

logger = logging.getLogger("omicsclaw.channel.qq")

GATEWAY_PROBE_S = 1.0
"""How long a failing gateway is given to fail before start-up believes it.

A gateway that refuses credentials does so on its first frame; anything
slower is a slow network, which is not a start-up fault.
"""

_LEADING_MENTION = re.compile(r"^@\S+\s*")


# ─ Config ─────────────────────────


@dataclass
class QQConfig(BaseChannelConfig):
    """QQ Bot channel configuration."""

    app_id: str = ""
    app_secret: str = ""
    text_chunk_limit: int = 4096


# ─ Channel ────────────────────────


class QQChannel(Channel):
    """QQ channel using the qq-botpy SDK.

    Owner text enters the authoritative
    :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`; answers leave
    only through its delivery pump, which is what classifies whether they
    were accepted. Inbound attachments and outbound media are fail-closed.
    """

    name = "qq"
    capabilities = QQ_CAPS
    authoritative_ingress = True

    def __init__(self, config: QQConfig):
        super().__init__(config)
        self.qq_config = config
        self._client = None
        self._gateway: asyncio.Task[None] | None = None
        self._sequence = MessageSequence()
        self._account_namespace = ""
        self.bot_identity = ""
        """The bot's App ID, which is what a proven mention resolves to.

        Empty until :meth:`prepare_control_binding` has run, which is exactly
        when a group message cannot be attributed and therefore fails closed.
        """

    # ─ Lifecycle ──────────────────────

    async def prepare_control_binding(self) -> ChannelSurfaceBinding:
        """Describe this bot's control binding before the gateway opens.

        QQ offers no cheap identity call: botpy authenticates as part of
        opening the socket, and the App ID is the identity the platform
        issued. So the namespace here is configured rather than read back —
        which is why a mismatched App ID shows up as a gateway that refuses
        to connect rather than as a binding that names the wrong account.
        """

        owners = self._owner_subjects()
        if not owners:
            raise RuntimeError("QQ authoritative ingress requires QQ_ALLOWED_SENDERS")
        app_id = self.qq_config.app_id.strip()
        if not app_id or not self.qq_config.app_secret.strip():
            raise RuntimeError("QQ_APP_ID and QQ_APP_SECRET are required")
        if self._client is None:
            self._client = self._build_client()

        self._account_namespace = f"app-{app_id}"
        self.bot_identity = app_id

        return ChannelSurfaceBinding(
            adapter="qq",
            account_namespace=self._account_namespace,
            sender_policy=SenderPolicy(
                allowed_senders=owners,
                bot_identity=self.bot_identity,
            ),
            delivery_adapter=QQDeliveryAdapter(self._client, self._sequence),
            text_chunk_limit=(
                self.config.text_chunk_limit or self.capabilities.max_text_length
            ),
            attachment_input_enabled=False,
        )

    def _build_client(self) -> Any:
        try:
            import botpy
        except ImportError:
            raise RuntimeError(
                "qq-botpy not installed. Run: pip install qq-botpy"
            ) from None

        channel = self
        intents = botpy.Intents(public_messages=True, direct_message=True)

        class _Bot(botpy.Client):
            def __init__(self) -> None:
                super().__init__(intents=intents)

            async def on_ready(self) -> None:
                logger.info("QQ bot connected")

            async def on_c2c_message_create(self, message) -> None:
                await channel._on_message(message, is_group=False)

            async def on_group_at_message_create(self, message) -> None:
                # This callback exists only for group messages that mentioned
                # this bot, which is the whole of QQ's attribution.
                await channel._on_message(message, is_group=True)

        return _Bot()

    async def start(self) -> None:
        """Phase 2: open the gateway once the shared runtime is bound."""

        if self._control_runtime is None:
            raise RuntimeError(
                "QQ requires the shared ChannelRuntime to be bound before start()"
            )
        if self._client is None:  # pragma: no cover - prepare runs first
            raise RuntimeError("QQ client was not prepared")

        async def _run_gateway() -> None:
            await self._client.start(
                appid=self.qq_config.app_id,
                secret=self.qq_config.app_secret,
            )

        self._gateway = asyncio.create_task(_run_gateway(), name="omicsclaw-qq")
        done, _pending = await asyncio.wait(
            {self._gateway},
            timeout=GATEWAY_PROBE_S,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if done:
            # Roll the whole channel back rather than report a start that will
            # never receive an event: `start_all` is all-or-nothing on purpose,
            # so half a deployment never answers messages.
            error = self._gateway.exception() if not self._gateway.cancelled() else None
            await self.stop()
            raise RuntimeError(
                "QQ gateway stopped before it began serving"
                + (f" ({type(error).__name__})" if error is not None else "")
            ) from None

        self._running = True
        logger.info("QQ channel started (gateway)")

    async def stop(self) -> None:
        self.deactivate_ingress()
        gateway = self._gateway
        self._gateway = None
        if gateway is not None and not gateway.done():
            gateway.cancel()
        if gateway is not None:
            await asyncio.gather(gateway, return_exceptions=True)
        self._client = None
        # The shared runtime is owned and closed by the runner, not by any one
        # channel: several channels share one agent.
        self._control_runtime = None
        self._control_loop = None
        self._running = False
        logger.info("QQ channel stopped")

    def run_bot(self) -> None:
        """Refuse the legacy standalone entry point.

        The bot cannot own the agent it speaks for: every channel in the
        process shares one
        :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`, composed by
        the runner from every channel's binding.
        """

        raise RuntimeError(
            "QQChannel.run_bot() is retired; start the bot through the runner "
            "that owns the shared ChannelRuntime: compose one with "
            "compose_channel_runtime(app, channels) and start them through "
            "ChannelManager"
        )

    # ─ Inbound ───────────────────────

    def _reply_target(
        self, destination_id: str, msg_id: str, *, is_group: bool
    ) -> dict[str, Any]:
        """Where a reply goes, and which inbound message it answers.

        ``msg_id`` is not decoration: QQ accepts a bot's message only as a
        passive reply to one it can name, so the id of the message being
        answered has to reach the delivery adapter.
        """

        return reply_target.build(
            "qq",
            self._account_namespace,
            destination_id,
            msg_id=msg_id,
            msg_type="group" if is_group else "c2c",
        )

    async def _on_message(self, message: Any, *, is_group: bool) -> None:
        """Normalise one QQ message into the authoritative runtime.

        Performs no model work and sends no reply: the answer is delivered by
        the runtime's pump once the exchange has run.
        """

        if not self.ingress_active:
            return
        message_id = str(getattr(message, "id", "") or "")
        author = getattr(message, "author", None)
        if is_group:
            sender_id = str(getattr(author, "member_openid", "") or "")
            destination_id = str(getattr(message, "group_openid", "") or "")
        else:
            sender_id = str(getattr(author, "user_openid", "") or "")
            destination_id = sender_id
        if not message_id or not sender_id or not destination_id:
            return

        # QQ writes the mention it filtered on into the body as a prefix.
        text = _LEADING_MENTION.sub(
            "", str(getattr(message, "content", "") or "").strip()
        ).strip()
        if not text:
            return

        if self.seen_before(message_id):
            return

        target = self._reply_target(destination_id, message_id, is_group=is_group)
        if text.startswith("/") and await self.answer_slash_command(
            target, destination_id, sender_id, text
        ):
            return

        if not self.check_rate_limit(sender_id):
            logger.warning("QQ sender exceeded the configured rate limit")
            return

        # Length and chat kind only: a chat message is the likeliest place in
        # this repository for a subject identifier to appear, and a log is the
        # most widely shared destination there is.
        logger.info("QQ message accepted (group=%s, %d chars)", is_group, len(text))
        await self._submit_control_inbound(
            destination_id=destination_id,
            sender_id=sender_id,
            text=text,
            message_id=message_id,
            is_group=is_group,
        )

    async def _submit_control_inbound(
        self,
        *,
        destination_id: str,
        sender_id: str,
        text: str,
        message_id: str,
        is_group: bool,
    ):
        """Submit one normalised QQ message as one exchange."""

        if self._control_runtime is None:
            raise RuntimeError("QQ ChannelRuntime is not bound")
        inbound = self.inbound(
            destination_id,
            sender_id,
            text,
            # The QQ message id is stable across the gateway's own
            # redelivery, so it is the natural idempotency key.
            source_request_id=message_id,
            reply_target=self._reply_target(
                destination_id, message_id, is_group=is_group
            ),
            values={
                VALUE_CHAT_TYPE: "group" if is_group else "private",
                # Only the group callback carries QQ's assertion that this bot
                # was addressed, so only it may name this bot as mentioned.
                VALUE_MENTIONS: (self.bot_identity,) if is_group else (),
            },
        )
        result = await self._control_runtime.submit(inbound)
        if result.acceptance.status is TurnAcceptanceStatus.REJECTED:
            # Refusals cannot answer through the pump, because no exchange was
            # accepted. The local cache is deliberately NOT updated, so a QQ
            # resend of a transiently rejected message can still land.
            logger.warning(
                "QQ ingress rejected: %s", result.acceptance.code or "unspecified"
            )
            return result
        self.remember_message(message_id)
        return result
