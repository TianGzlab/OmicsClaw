"""
Channel manager that coordinates multiple chat channels.

Manages channel lifecycle (start/stop), wires each channel to the
message bus, routes outbound messages, and provides health monitoring.

This enables running multiple channels in one process::

    manager = ChannelManager()
    manager.register(telegram_channel)
    manager.register(feishu_channel)
    await manager.start_all()   # starts both concurrently
    await manager.run()         # blocks, routing messages
    await manager.stop_all()    # graceful shutdown

Adapted from EvoScientist's channel_manager.py, simplified for OmicsClaw.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .base import Channel
from .bus import InboundMessage, MessageBus, OutboundMessage
from .middleware import MiddlewarePipeline

logger = logging.getLogger(__name__)


# ── Per-channel health metrics ───────────────────────────────────────


@dataclass
class ChannelHealth:
    """Tracks message processing metrics per channel."""
    total_inbound: int = 0
    total_outbound: int = 0
    total_errors: int = 0
    consecutive_failures: int = 0
    last_error: str | None = None
    last_error_time: float | None = None
    started_at: float = 0.0

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self, error: str) -> None:
        self.total_errors += 1
        self.consecutive_failures += 1
        self.last_error = error
        self.last_error_time = time.monotonic()


# ── Channel Manager ──────────────────────────────────────────────────


class ChannelManager:
    """Manages multiple channels with unified lifecycle and routing.

    The manager:
    1. Registers channels and stores them by name
    2. Starts/stops channels concurrently
    3. Optionally uses a MessageBus for decoupled routing
    4. Provides a health check endpoint
    """

    def __init__(
        self,
        bus: MessageBus | None = None,
        middleware: MiddlewarePipeline | None = None,
    ):
        self._channels: dict[str, Channel] = {}
        self._health: dict[str, ChannelHealth] = {}
        self._bus = bus or MessageBus()
        self._middleware = middleware
        self._start_time: float = 0.0
        self._consumer_task: asyncio.Task | None = None
        self._dispatcher_task: asyncio.Task | None = None
        self._running = False

    # ── Properties ──────────────────────────────────────────────────

    @property
    def bus(self) -> MessageBus:
        return self._bus

    @property
    def channels(self) -> dict[str, Channel]:
        return dict(self._channels)

    @property
    def enabled_channels(self) -> list[str]:
        return list(self._channels.keys())

    def running_channels(self) -> list[str]:
        return [n for n, c in self._channels.items() if c._running]

    # ── Registration ────────────────────────────────────────────────

    def register(self, channel: Channel) -> None:
        """Register a channel for management."""
        if channel.name in self._channels:
            raise ValueError(f"Channel '{channel.name}' already registered")
        self._channels[channel.name] = channel
        self._health[channel.name] = ChannelHealth()
        logger.info(f"Registered channel: {channel.name}")

    def unregister(self, name: str) -> None:
        """Unregister a channel by name."""
        self._channels.pop(name, None)
        self._health.pop(name, None)
        logger.info(f"Unregistered channel: {name}")

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Start all registered channels concurrently."""
        self._start_time = time.monotonic()
        self._running = True

        tasks = []
        for name, channel in self._channels.items():
            tasks.append(self._start_one(name, channel))
        await asyncio.gather(*tasks, return_exceptions=True)

        # Start consumer (inbound processing) and dispatcher (outbound routing)
        self._consumer_task = asyncio.create_task(
            self._consumer_loop(),
            name="channel-consumer",
        )
        self._dispatcher_task = asyncio.create_task(
            self._bus.dispatch_outbound(),
            name="outbound-dispatcher",
        )

        logger.info(
            f"ChannelManager started ({len(self.running_channels())}"
            f"/{len(self._channels)} channels active)"
        )

    async def _start_one(self, name: str, channel: Channel) -> None:
        """Start a single channel with error handling."""
        health = self._health[name]
        try:
            await channel.start()
            health.started_at = time.monotonic()
            health.record_success()
            # Subscribe channel for outbound routing
            self._bus.subscribe_outbound(name, self._make_outbound_handler(channel))
            logger.info(f"Channel '{name}' started successfully")
        except Exception as e:
            health.record_failure(str(e))
            logger.error(f"Failed to start channel '{name}': {e}", exc_info=True)

    async def stop_all(self) -> None:
        """Stop all channels and background tasks."""
        self._running = False
        self._bus.stop()

        # Cancel background tasks
        for task in [self._consumer_task, self._dispatcher_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop all channels concurrently
        tasks = []
        for name, channel in self._channels.items():
            tasks.append(self._stop_one(name, channel))
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("ChannelManager stopped")

    async def _stop_one(self, name: str, channel: Channel) -> None:
        """Stop a single channel with error handling."""
        try:
            await channel.stop()
            logger.info(f"Channel '{name}' stopped")
        except Exception as e:
            logger.error(f"Error stopping channel '{name}': {e}")

    async def run(self) -> None:
        """Run until stopped or interrupted.

        Call after start_all(). Blocks until stop_all() is called or
        the process is interrupted.
        """
        try:
            while self._running:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop_all()

    # ── Inbound consumer ────────────────────────────────────────────

    async def _consumer_loop(self) -> None:
        """Process inbound messages from the bus through core.py."""
        from bot import core

        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self._bus.consume_inbound(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            health = self._health.get(msg.channel)
            if health:
                health.total_inbound += 1

            # Apply inbound middleware
            if self._middleware:
                processed = await self._middleware.process_inbound(msg)
                if processed is None:
                    continue
                msg = processed

            try:
                # Process through the LLM engine
                reply = await core.llm_tool_loop(
                    msg.chat_id,
                    msg.content,
                    user_id=msg.sender_id,
                    platform=msg.channel,
                )

                # Collect pending text
                if core.pending_text:
                    reply = "\n\n".join(core.pending_text)
                    core.pending_text.clear()

                # Publish response
                if reply:
                    outbound = OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=reply,
                        reply_to=msg.message_id,
                    )
                    # Apply outbound middleware
                    if self._middleware:
                        outbound = await self._middleware.process_outbound(outbound)
                    if outbound:
                        await self._bus.publish_outbound(outbound)

                if health:
                    health.record_success()

            except Exception as e:
                logger.error(
                    f"Error processing message from {msg.channel}: {e}",
                    exc_info=True,
                )
                if health:
                    health.record_failure(str(e))
                # Send error reply
                try:
                    err_msg = OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, an error occurred: {type(e).__name__}",
                    )
                    await self._bus.publish_outbound(err_msg)
                except Exception:
                    pass

    # ── Outbound handler factory ────────────────────────────────────

    def _make_outbound_handler(self, channel: Channel):
        """Create an outbound callback for a channel."""
        async def handler(msg: OutboundMessage) -> None:
            health = self._health.get(channel.name)
            try:
                success = await channel.send(
                    msg.chat_id,
                    msg.content,
                    metadata=msg.metadata,
                )
                if health:
                    if success:
                        health.total_outbound += 1
                        health.record_success()
                    else:
                        health.record_failure("send returned False")
                # Send media attachments
                for media_path in msg.media:
                    await channel.send_media(msg.chat_id, media_path)
            except Exception as e:
                if health:
                    health.record_failure(str(e))
                logger.error(f"Outbound send error on {channel.name}: {e}")
        return handler

    # ── Health check ────────────────────────────────────────────────

    def get_health(self) -> dict[str, Any]:
        """Get health status for all channels."""
        channels_health = {}
        for name, health in self._health.items():
            channels_health[name] = {
                "running": name in self.running_channels(),
                "total_inbound": health.total_inbound,
                "total_outbound": health.total_outbound,
                "total_errors": health.total_errors,
                "consecutive_failures": health.consecutive_failures,
                "last_error": health.last_error,
            }

        return {
            "status": "healthy" if self.running_channels() else "degraded",
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "channels": {
                "registered": self.enabled_channels,
                "running": self.running_channels(),
            },
            "queues": {
                "inbound_size": self._bus.inbound_size,
                "outbound_size": self._bus.outbound_size,
            },
            "channel_health": channels_health,
        }

    # ── Health check server ─────────────────────────────────────────

    async def start_health_server(self, port: int = 8080) -> None:
        """Start a minimal HTTP health-check endpoint.

        Responds to ``GET /healthz`` with JSON health payload.
        """
        async def handle(reader, writer):
            try:
                request_line = await asyncio.wait_for(
                    reader.readline(), timeout=5.0,
                )
                while True:
                    line = await reader.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break

                parts = request_line.decode("utf-8", errors="replace").split()
                if len(parts) >= 2 and parts[0] == "GET" and parts[1] == "/healthz":
                    body = json.dumps(self.get_health()).encode()
                    header = (
                        "HTTP/1.1 200 OK\r\n"
                        "Content-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\n"
                        "Connection: close\r\n\r\n"
                    )
                else:
                    body = b'{"error":"not found"}'
                    header = (
                        "HTTP/1.1 404 Not Found\r\n"
                        "Content-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\n"
                        "Connection: close\r\n\r\n"
                    )
                writer.write(header.encode() + body)
                await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        server = await asyncio.start_server(handle, "0.0.0.0", port)
        addrs = [s.getsockname() for s in server.sockets]
        logger.info(f"Health server listening on {addrs}")
