"""
Async message bus that decouples chat channels from the LLM core.

Channels push messages to the inbound queue; the consumer reads from
inbound, processes through core.llm_tool_loop(), and pushes responses
to the outbound queue. A background dispatcher routes outbound messages
to the correct channel via subscriber callbacks.

Adapted from EvoScientist's message bus, simplified for OmicsClaw's
lightweight architecture.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


# ── Message types ────────────────────────────────────────────────────


@dataclass
class InboundMessage:
    """Message received from a chat channel.

    Carries enough context for the bus to route and for the LLM engine
    to build a session: which channel, who sent it, which chat.
    """

    channel: str
    sender_id: str
    chat_id: str
    content: str | list
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = ""
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_group: bool = False
    was_mentioned: bool = True

    @property
    def session_key(self) -> str:
        """Unique key for session identification: channel:chat_id."""
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""

    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Outbound callback type ──────────────────────────────────────────

OutboundCallback = Callable[[OutboundMessage], Awaitable[None]]


# ── Message Bus ──────────────────────────────────────────────────────


class MessageBus:
    """Async message bus that decouples chat channels from the LLM core.

    Inbound flow:  Channel → MessageBus.inbound → Consumer → core.py
    Outbound flow: core.py → MessageBus.outbound → Dispatcher → Channel

    Usage::

        bus = MessageBus()
        # Channel publishes a message
        await bus.publish_inbound(InboundMessage(...))
        # Consumer reads messages
        msg = await bus.consume_inbound()
        # After processing, publish response
        await bus.publish_outbound(OutboundMessage(...))
    """

    def __init__(self, max_inbound: int = 1000, max_outbound: int = 1000):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(
            maxsize=max_inbound,
        )
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(
            maxsize=max_outbound,
        )
        self._outbound_subscribers: dict[str, list[OutboundCallback]] = {}
        self._running = False
        self._start_time = time.monotonic()

    # ── Inbound (channel → consumer) ────────────────────────────────

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the consumer."""
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    # ── Outbound (consumer → channel) ───────────────────────────────

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the consumer to channels."""
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    # ── Subscriber-based routing ────────────────────────────────────

    def subscribe_outbound(
        self,
        channel: str,
        callback: OutboundCallback,
    ) -> None:
        """Register a callback for outbound messages targeting *channel*."""
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)

    async def dispatch_outbound(self) -> None:
        """Route outbound messages to subscribed channels.

        Run as a background task — loops until stop() is called.
        """
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.outbound.get(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue
            subscribers = self._outbound_subscribers.get(msg.channel, [])
            if not subscribers:
                logger.warning(f"No subscriber for channel: {msg.channel}")
                continue
            for callback in subscribers:
                try:
                    await callback(msg)
                except Exception as e:
                    logger.error(f"Error dispatching to {msg.channel}: {e}")

    def stop(self) -> None:
        """Stop the dispatcher loop."""
        self._running = False

    # ── Observability ────────────────────────────────────────────────

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()

    @property
    def uptime_seconds(self) -> float:
        """Bus uptime in seconds."""
        return time.monotonic() - self._start_time
