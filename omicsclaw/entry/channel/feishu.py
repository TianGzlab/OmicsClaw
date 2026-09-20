"""
Feishu (Lark) channel implementation for OmicsClaw.

Extracts the platform-specific logic into a reusable Channel subclass.

Uses lark-oapi Python SDK with WebSocket long-connection (no public IP
required).

Ported from ``omicsclaw/surfaces/channels/feishu.py`` for plan 0031 task D1.
The file imported one symbol from the deleted control plane
(``feishu.py:21``); four things changed and nothing else:

- ``ChannelSurfaceBinding`` comes from
  :mod:`omicsclaw.entry.channel.binding`, and the owner identity scope it
  carried is a :class:`~omicsclaw.entry.ingress.SenderPolicy`;
- submission builds an :class:`~omicsclaw.entry.ingress.InboundMessage`
  instead of ``RawInboundV1`` plus ``ControlRuntimePorts``;
- the audit call into the deleted ``agent.state`` module is gone;
- the chat kind and the mention list now travel on the message, so the
  allowlist gate is applied once more at ingress — by the object that owns
  it — and not only here.

**The two fail-closed rules ``CLAUDE.md`` states are unchanged and are the
reason this file was worth porting.** ``FEISHU_ALLOWED_SENDERS`` is required
and admits nobody else (``_handle_event``, and again in ``SenderPolicy``);
``FEISHU_BOT_OPEN_ID`` is what proves a group @-mention targets this bot, and
without it group chats fail closed (:meth:`FeishuChannel
._group_message_mentions_this_bot`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from omicsclaw.entry.ingress import (
    SenderPolicy,
    VALUE_CHAT_TYPE,
    VALUE_MENTIONS,
)

from .base import Channel
from .binding import ChannelSurfaceBinding
from .capabilities import FEISHU as FEISHU_CAPS
from .config import BaseChannelConfig
from .runtime import TurnAcceptanceStatus

logger = logging.getLogger("omicsclaw.channel.feishu")


@dataclass
class FeishuConfig(BaseChannelConfig):
    """Feishu-specific configuration."""

    app_id: str = ""
    app_secret: str = ""
    # Open ID of this Bot. Group messages are admitted only when they mention
    # THIS Bot; without the ID a group @-mention cannot be distinguished from
    # the Owner mentioning another human, so group chats fail closed.
    bot_open_id: str = ""
    # Bound the initial authenticated connection and the async disconnect plus
    # listener-thread join. Readiness is signalled by the SDK's `_connect` seam.
    ws_start_probe_seconds: float = 5.0
    ws_join_seconds: float = 10.0
    thinking_threshold_ms: int = 2500
    max_inbound_image_mb: int = 12
    max_inbound_file_mb: int = 40
    max_attachments: int = 4
    debug: bool = False


class FeishuChannel(Channel):
    """Feishu channel using lark-oapi with WebSocket long-connection.

    The Feishu SDK delivers events on its **own thread**, which is the single
    fact that shapes this file: every hand-off to the agent goes through
    :meth:`_run_async`, which submits to the loop the runtime lives on rather
    than to any channel-local one. An ``asyncio`` primitive belongs to the
    loop that created it, and calling into one from this thread corrupts that
    loop's bookkeeping instead of failing loudly (plan 0031 trap 10).
    """

    name = "feishu"
    capabilities = FEISHU_CAPS
    # Text-only cutover: Owner text and group @-mentions enter the
    # authoritative ChannelRuntime, and terminal replies leave only through
    # its delivery pump.  Inbound attachments, outbound media, rich
    # post/cards and placeholder editing remain fail-closed.
    authoritative_ingress = True

    # Request verbs to detect intent in group chats
    _REQUEST_VERBS = [
        "帮",
        "麻烦",
        "请",
        "能否",
        "可以",
        "解释",
        "看看",
        "排查",
        "分析",
        "总结",
        "写",
        "改",
        "修",
        "查",
        "对比",
        "翻译",
        "preprocess",
        "analyze",
        "run",
        "demo",
    ]

    def __init__(self, config: FeishuConfig):
        super().__init__(config)
        self.feishu_config = config
        self._lark_client = None
        self._ws_client = None
        self._ws_loop = None
        self._ws_thread = None
        self._ws_ready = threading.Event()
        self._ws_exit = threading.Event()
        self._ws_stopping = threading.Event()
        self._ws_error: BaseException | None = None
        self._bot_start_time = time.time()
        self._seen: dict[str, float] = {}
        self._seen_ttl = 600
        self._group_member_count: dict[str, tuple[int, float]] = {}
        self._member_count_ttl = 3600
        self._control_runtime = None

    # ─ Lifecycle ──────────────────────

    def _require_authoritative_identity(self) -> set[str]:
        owners = self._owner_subjects()
        if not owners:
            raise RuntimeError(
                "Feishu authoritative ingress requires FEISHU_ALLOWED_SENDERS "
                "(Owner open_id values)"
            )
        if not self.feishu_config.bot_open_id.strip():
            raise RuntimeError(
                "Feishu authoritative ingress requires FEISHU_BOT_OPEN_ID "
                "to prove group mentions target this Bot"
            )
        return owners

    def _build_lark_client(self):
        if not self.feishu_config.app_id:
            raise RuntimeError("FEISHU_APP_ID is required")
        if not self.feishu_config.app_secret:
            raise RuntimeError("FEISHU_APP_SECRET is required")

        try:
            import lark_oapi as lark
        except ImportError:
            raise RuntimeError(
                "lark-oapi not installed. " "Install with: pip install lark-oapi"
            )

        return (
            lark.Client.builder()
            .app_id(self.feishu_config.app_id)
            .app_secret(self.feishu_config.app_secret)
            .log_level(
                lark.LogLevel.DEBUG if self.feishu_config.debug else lark.LogLevel.INFO
            )
            .build()
        )

    async def prepare_control_binding(self) -> ChannelSurfaceBinding:
        """Authenticate far enough to describe this Bot's control binding."""

        owners = self._require_authoritative_identity()
        # The Feishu App ID is the account namespace: it is the stable identity
        # of the Bot whose token sends the reply, so one Backend serving two
        # Apps can never claim the other's Delivery target sequence.
        account_namespace = self.feishu_config.app_id.strip()
        if not account_namespace:
            raise RuntimeError("Feishu account namespace is unavailable")
        if self._lark_client is None:
            self._lark_client = self._build_lark_client()

        from .feishu_delivery import FeishuDeliveryAdapter

        return ChannelSurfaceBinding(
            adapter="feishu",
            account_namespace=account_namespace,
            # Both halves of the CLAUDE.md rule in one object: the owner
            # allowlist, and the Bot open_id that proves a group @-mention
            # was aimed here.  `_require_authoritative_identity` has already
            # refused to start without either.
            sender_policy=SenderPolicy(
                allowed_senders=frozenset(owners),
                bot_identity=self.feishu_config.bot_open_id.strip(),
            ),
            delivery_adapter=FeishuDeliveryAdapter(self._lark_client),
            text_chunk_limit=(
                self.config.text_chunk_limit or self.capabilities.max_text_length
            ),
            # Inbound attachments have no Feishu Attachment Store cutover.
            attachment_input_enabled=False,
        )

    async def start(self) -> None:
        if self._control_runtime is None:
            raise RuntimeError(
                "Feishu requires the shared ChannelRuntime to be bound "
                "before start()"
            )
        self._require_authoritative_identity()
        if self._lark_client is None:
            self._lark_client = self._build_lark_client()

        import lark_oapi as lark

        # ─ Start WebSocket event listener in a separate thread ───────
        # CRITICAL: lark_oapi.ws.client has a MODULE-LEVEL variable:
        #     loop = asyncio.get_event_loop()  (line 26 of client.py)
        # All internal methods (start, _connect, _receive_message_loop)
        # use this cached `loop`. When imported from an async context
        # (ChannelManager's asyncio.run), it captures the RUNNING main
        # loop, causing "This event loop is already running" errors.
        #
        # Fix: create a fresh loop in the thread and PATCH the module-
        # level `loop` variable so lark_oapi uses it.
        self._ws_ready.clear()
        self._ws_exit.clear()
        self._ws_stopping.clear()
        self._ws_error = None

        def _ws_thread_target():
            import lark_oapi.ws.client as _ws_mod

            ws_loop = asyncio.new_event_loop()
            self._ws_loop = ws_loop
            asyncio.set_event_loop(ws_loop)
            # Monkey-patch the module-level loop variable
            _ws_mod.loop = ws_loop

            try:
                event_handler = (
                    lark.EventDispatcherHandler.builder("", "")
                    .register_p2_im_message_receive_v1(self._handle_event)
                    .build()
                )

                client = lark.ws.Client(
                    self.feishu_config.app_id,
                    self.feishu_config.app_secret,
                    event_handler=event_handler,
                    log_level=(
                        lark.LogLevel.DEBUG
                        if self.feishu_config.debug
                        else lark.LogLevel.INFO
                    ),
                )
                self._ws_client = client
                connect = getattr(client, "_connect", None)
                disconnect = getattr(client, "_disconnect", None)
                if not callable(connect) or not callable(disconnect):
                    raise RuntimeError(
                        "Feishu SDK lacks the required WebSocket lifecycle seams"
                    )

                async def _connect_and_signal():
                    if self._ws_stopping.is_set():
                        raise asyncio.CancelledError
                    await connect()
                    if self._ws_stopping.is_set():
                        await disconnect()
                        raise asyncio.CancelledError
                    if getattr(client, "_conn", None) is None:
                        raise RuntimeError(
                            "Feishu WebSocket connection was not established"
                        )
                    self._ws_ready.set()

                client._connect = _connect_and_signal
                client.start()
            except BaseException as e:  # noqa: BLE001 - reported to start()
                if not self._ws_stopping.is_set():
                    self._ws_error = e
                    logger.error(
                        "Feishu WebSocket thread failed (%s)",
                        type(e).__name__,
                    )
            finally:
                pending = asyncio.all_tasks(ws_loop)
                for task in pending:
                    task.cancel()
                if pending and not ws_loop.is_closed():
                    with suppress(Exception):
                        ws_loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                with suppress(Exception):
                    ws_loop.close()
                self._ws_exit.set()

        self._ws_thread = threading.Thread(
            target=_ws_thread_target,
            daemon=True,
            name="feishu-ws",
        )
        self._ws_thread.start()

        try:
            outcome = await asyncio.to_thread(
                self._wait_for_websocket_start,
                max(0.0, float(self.feishu_config.ws_start_probe_seconds)),
            )
        except asyncio.CancelledError:
            await self._rollback_cancelled_start()
            raise
        if outcome != "ready":
            with suppress(Exception):
                await self._shutdown_websocket()
            raise RuntimeError(
                "Feishu WebSocket failed to become ready; verify the App "
                "credentials, permissions, and lark-oapi compatibility"
            ) from None

        self._running = True
        logger.info("Feishu channel initialized")

    def _wait_for_websocket_start(self, timeout: float) -> str:
        """Wait for one truthful initial outcome without owning the SDK loop."""

        deadline = time.monotonic() + timeout
        while True:
            if self._ws_exit.is_set():
                return "exit"
            if self._ws_ready.is_set():
                return "ready"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "timeout"
            self._ws_ready.wait(min(0.01, remaining))

    async def _rollback_cancelled_start(self) -> None:
        """Finish bounded WS rollback despite repeated caller cancellation."""

        shutdown_task = asyncio.create_task(self._shutdown_websocket())
        while not shutdown_task.done():
            try:
                await asyncio.shield(shutdown_task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            shutdown_task.result()
        except Exception as error:
            raise RuntimeError(
                "Feishu WebSocket shutdown failed during startup cancellation "
                f"({type(error).__name__})"
            ) from None

    def _owner_subjects(self) -> frozenset[str]:
        """Configured Feishu Owner open_id values."""

        return frozenset(
            str(value).strip()
            for value in (self.config.allowed_senders or set())
            if str(value).strip()
        )

    async def stop(self) -> None:
        self.deactivate_ingress()
        failures: list[str] = []
        try:
            await self._shutdown_websocket()
        except Exception as error:
            failures.append(type(error).__name__)
        try:
            await self._typing_manager.stop_all()
        except Exception as error:
            failures.append(type(error).__name__)
        if failures:
            raise RuntimeError(
                "Feishu channel shutdown failed (" + ", ".join(failures) + ")"
            ) from None

        # The shared ChannelRuntime is owned and closed by the runner, not
        # by any one Channel: several Channels share one agent.
        self._control_runtime = None
        self._control_loop = None
        self._running = False
        logger.info("Feishu channel stopped")

    async def _shutdown_websocket(self) -> None:
        """Stop the lark listener and prove it is no longer dispatching events.

        Returning from stop() while the WebSocket thread still holds its socket
        would let a late Feishu event submit an exchange into the shared
        ChannelRuntime the runner is about to close.
        """

        client = self._ws_client
        ws_loop = self._ws_loop
        thread = self._ws_thread
        timeout = max(0.0, float(self.feishu_config.ws_join_seconds))

        if thread is not None and thread.is_alive() and self._ws_exit.is_set():
            await asyncio.to_thread(thread.join, timeout)
            if thread.is_alive():
                raise RuntimeError("Feishu WebSocket listener did not stop")
        elif thread is not None and thread.is_alive():
            disconnect = getattr(client, "_disconnect", None)
            if not callable(disconnect) or ws_loop is None:
                raise RuntimeError(
                    "Feishu WebSocket listener has no usable shutdown seam"
                )

            self._ws_stopping.set()

            async def _disconnect_on_owner_loop():
                await disconnect()

            coroutine = _disconnect_on_owner_loop()
            try:
                disconnect_future = asyncio.run_coroutine_threadsafe(
                    coroutine,
                    ws_loop,
                )
            except Exception as error:
                coroutine.close()
                raise RuntimeError(
                    "Feishu WebSocket disconnect could not be scheduled"
                ) from error

            try:
                await asyncio.wait_for(
                    asyncio.wrap_future(disconnect_future),
                    timeout=timeout,
                )
            except Exception as error:
                raise RuntimeError(
                    "Feishu WebSocket disconnect did not complete"
                ) from error

            with suppress(RuntimeError):
                ws_loop.call_soon_threadsafe(ws_loop.stop)
            await asyncio.to_thread(thread.join, timeout)
            if thread.is_alive():
                raise RuntimeError("Feishu WebSocket listener did not stop")

        self._ws_client = None
        self._ws_loop = None
        self._ws_thread = None
        self._ws_ready.clear()
        self._ws_stopping.clear()

    def run_sync(self) -> None:
        """Refuse the legacy standalone entry point.

        The Bot cannot own the agent it speaks for: every Channel in the
        process shares one
        :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime`, and that is
        composed by the runner from every Channel's binding. Starting here
        would either fail on an unbound runtime or build a second one, which
        would be a second set of conversations for the same person.
        """

        raise RuntimeError(
            "FeishuChannel.run_sync() is retired; start the Bot through the "
            "runner that owns the shared ChannelRuntime: compose one with "
            "compose_channel_runtime(app, channels) and start them through "
            "ChannelManager"
        )

    # ─ Core send implementation ─────────────────

    async def process_message(self, *args, **kwargs) -> str:
        raise RuntimeError(
            "Feishu messages must enter through the authoritative ChannelRuntime"
        )

    async def send(
        self,
        chat_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        raise RuntimeError(
            "Feishu replies must leave through the ChannelRuntime delivery "
            "pump, which classifies whether they were accepted"
        )

    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        raise RuntimeError(
            "Feishu text chunks must leave through the ChannelRuntime "
            "delivery pump, which classifies whether they were accepted"
        )

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        raise RuntimeError(
            "Feishu outbound media is disabled: this layer has no content "
            "parts to carry it (plan 0031 §5.3)"
        )

    # ─ Dedup ────────────────────────

    def _is_duplicate_feishu(self, message_id: str) -> bool:
        """Read-only local redelivery check with TTL cleanup.

        An optimization only. The authority is the registry's own
        ``source_request_id`` idempotency, which resolves a repeat to the
        exchange it already started; this just avoids building the message
        again for an obvious one.

        It must NOT mark a message as seen before that acceptance, and does
        not: a failed submission plus a Feishu redelivery inside the TTL
        would otherwise lose the message silently.
        """

        now = time.time()
        expired = [k for k, ts in self._seen.items() if now - ts > self._seen_ttl]
        for k in expired:
            del self._seen[k]
        return bool(message_id) and message_id in self._seen

    def _remember_feishu_message(self, message_id: str) -> None:
        """Record a message only once the runtime has accepted it."""

        if message_id:
            self._seen[message_id] = time.time()

    # ─ Group member count ───────────────────

    def _get_group_member_count(self, chat_id: str) -> int:
        now = time.time()
        if chat_id in self._group_member_count:
            count, timestamp = self._group_member_count[chat_id]
            if now - timestamp < self._member_count_ttl:
                return count
        try:
            from lark_oapi.api.im.v1 import GetChatRequest

            request = GetChatRequest.builder().chat_id(chat_id).build()
            response = self._lark_client.im.v1.chat.get(request)
            if response.success() and response.data:
                user_count = int(response.data.user_count or 0)
                bot_count = int(response.data.bot_count or 0)
                member_count = user_count + bot_count
                self._group_member_count[chat_id] = (member_count, now)
                return member_count
        except Exception as e:
            logger.warning(f"Failed to get group member count: {e}")
        return 3  # Default: assume normal group

    # ─ Text parsing ─────────────────────

    @staticmethod
    def _normalize_text(raw: str) -> str:
        t = str(raw or "")
        t = re.sub(r"<\s*br\s*/?>", "\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<\s*/p\s*>\s*<\s*p\s*>", "\n", t, flags=re.IGNORECASE)
        t = re.sub(r"<[^>]+>", "", t)
        t = t.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
        t = t.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    def _run_async(self, coro, timeout=None):
        """Submit a coroutine to the loop that owns the shared ChannelRuntime.

        Feishu events arrive on the lark WebSocket thread. The runtime's
        asyncio primitives belong to the runner's loop, so submissions must go
        THERE rather than to any Channel-local loop.
        """

        loop = self._control_loop
        if loop is None:
            raise RuntimeError("Feishu channel has no control event loop")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    # ─ Process message ────────────────────

    def _handle_event(self, data) -> None:
        """Normalize one Feishu message into the authoritative ChannelRuntime.

        This handler performs no LLM work, sends no placeholder, and produces
        no reply: the answer is delivered by the runtime's pump once the
        exchange has run. That separation is ADR 0060/0063's and it survives
        the port, with one honest difference — the pump here holds the reply
        in memory rather than in a durable outbox, so a process that dies
        mid-delivery loses it (plan 0031 §11).
        """

        if not self.ingress_active:
            return

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
            if not sender_id:
                logger.warning("Ignored Feishu message without a sender open_id")
                return
            if sender_id not in self._owner_subjects():
                logger.warning("Ignored Feishu message from a non-Owner")
                return
            if chat_type not in {"p2p", "group"}:
                logger.warning("Ignored Feishu message with an unsupported chat_type")
                return
            if not message.content:
                return

            # Feishu redelivers events at least once. The registry's
            # source_request_id idempotency is the authority; this cheap local
            # check just avoids rebuilding an obvious repeat.
            if self._is_duplicate_feishu(message_id):
                return

            if getattr(message, "create_time", None):
                msg_time = int(message.create_time) / 1000.0
                if msg_time < self._bot_start_time:
                    logger.info(
                        f"Ignoring cached message from before bot startup: {message_id}"
                    )
                    return

            # Gate on the provider message type BEFORE parsing. The legacy
            # parser downloaded images and files as a side effect and, for
            # non-text types, synthesized placeholder text such as "[image]" or
            # embedded "[local path] /tmp/...". Admitting either would be worse
            # than rejecting: the Owner would receive an answer about a
            # placeholder they never wrote, and a local path would be back in
            # the conversation history as a side channel.
            if message.message_type != "text":
                logger.warning(
                    "Feishu %s messages remain fail-closed in the text-only slice",
                    message.message_type,
                )
                return

            text = self._extract_owner_text(message.content)
            if text is None:
                return

            if chat_type == "group":
                if not self._group_message_mentions_this_bot(message):
                    return
                text = re.sub(r"@_user_\d+\s*", "", text).strip()

            if not text.strip():
                return

            # Consume rate-limit budget only for a message that is actually
            # about to become a Turn. Charging it before the type and mention
            # gates would let images, or group chatter that never mentions this
            # Bot, exhaust the Owner's budget and starve their real requests.
            if not self.check_rate_limit(sender_id):
                logger.warning("Feishu Owner exceeded the configured rate limit")
                return

            # Length and chat kind only.  The old line logged 100 characters
            # of what the Owner wrote and audited 200 more; plan 0031 Q22
            # keeps message content off every shared channel.
            logger.info(
                "Feishu message accepted (chat_type=%s, %d chars)",
                chat_type,
                len(text),
            )

            self._run_async(
                self._submit_control_inbound(
                    chat_id=chat_id,
                    message_id=message_id,
                    sender_open_id=sender_id,
                    text=text,
                    chat_type=chat_type,
                    mentions=self._mentioned_identities(message),
                ),
                timeout=None,
            )
        except Exception as error:
            # Type only, and no traceback. A provider exception can embed the
            # request payload, which on this path is what somebody wrote
            # (plan 0031 Q22) — the same rule the Telegram error handler
            # already followed.
            logger.error("Feishu message handler error (%s)", type(error).__name__)

    def _group_message_mentions_this_bot(self, message: Any) -> bool:
        """Admit a group message only when it @-mentions THIS Bot.

        A non-empty ``mentions`` list is not enough: the Owner mentioning
        another human in a shared group would otherwise create a Turn and an
        unsolicited reply. Without a configured Bot open ID the mention cannot
        be attributed at all, so group chats fail closed rather than guessing
        from member counts.
        """

        bot_open_id = self.feishu_config.bot_open_id.strip()
        if not bot_open_id:
            logger.warning(
                "Feishu group messages are fail-closed until FEISHU_BOT_OPEN_ID "
                "is configured"
            )
            return False
        for mention in getattr(message, "mentions", None) or ():
            identity = getattr(mention, "id", None)
            if getattr(identity, "open_id", None) == bot_open_id:
                return True
        return False

    def _extract_owner_text(self, raw_content: str) -> str | None:
        """Read the plain text of a Feishu ``text`` message, or ``None``.

        Deliberately narrow: it reads one field and never downloads, writes a
        temporary file, or substitutes a placeholder for absent content.
        """

        try:
            parsed = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(parsed, dict):
            return None
        raw_text = parsed.get("text")
        if not isinstance(raw_text, str):
            return None
        text = self._normalize_text(raw_text)
        return text if text.strip() else None

    def _mentioned_identities(self, message: Any) -> tuple[str, ...]:
        """Every ``open_id`` this message @-mentioned, for the ingress gate.

        The same list :meth:`_group_message_mentions_this_bot` reads, handed
        on so that :class:`~omicsclaw.entry.ingress.SenderPolicy` can apply
        the group rule itself.  Two checks of one rule, on purpose: this one
        stops the work early, and the one at ingress is the one that holds
        for every adapter in the package, including any written later.
        """

        found: list[str] = []
        for mention in getattr(message, "mentions", None) or ():
            identity = getattr(mention, "id", None)
            open_id = getattr(identity, "open_id", None)
            if isinstance(open_id, str) and open_id:
                found.append(open_id)
        return tuple(found)

    async def _submit_control_inbound(
        self,
        *,
        chat_id: str,
        message_id: str,
        sender_open_id: str,
        text: str,
        chat_type: str = "",
        mentions: tuple[str, ...] = (),
    ):
        """Submit one normalized Feishu message as one exchange.

        Runs on the runtime's loop, not on the WebSocket thread: the caller
        got here through :meth:`_run_async`.
        """

        if not self.ingress_active:
            return None

        if self._control_runtime is None:
            raise RuntimeError("Feishu ChannelRuntime is not bound")
        account_namespace = self.feishu_config.app_id.strip()
        inbound = self.inbound(
            chat_id,
            sender_open_id,
            text,
            # The Feishu message_id is globally unique and stable across
            # event redelivery, so it is the natural idempotency key.
            source_request_id=message_id,
            reply_target={
                "schema_version": 1,
                "kind": "channel",
                "adapter": "feishu",
                "account_namespace": account_namespace,
                "destination_id": chat_id,
                "destination_kind": "chat_id",
            },
            values={
                VALUE_CHAT_TYPE: chat_type,
                VALUE_MENTIONS: mentions,
            },
        )
        # `submit`, not `submit_and_wait`: waiting here would serialize every
        # Feishu event -- including other conversations -- behind one
        # analysis, because the WebSocket thread blocks on this call.
        # Returning at admission still applies backpressure, and the reply is
        # delivered by the runtime's pump rather than by this thread.
        result = await self._control_runtime.submit(inbound)
        if result.acceptance.status is TurnAcceptanceStatus.REJECTED:
            # Refusals cannot answer through the pump, because no exchange was
            # accepted; log rather than open a second, unaccounted send path.
            # The local redelivery cache is deliberately NOT updated, so a
            # Feishu retry of a transiently rejected message can still land.
            logger.warning(
                "Feishu ingress rejected: %s", result.acceptance.code or "unspecified"
            )
            return result
        self._remember_feishu_message(message_id)
        return result
