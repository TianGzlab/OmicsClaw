"""
Channel manager that coordinates multiple chat channels.

Manages channel lifecycle (start/stop) and per-channel health monitoring. The
manager starts only Adapters that declare a verified authoritative ingress
cutover; it does not compose or own the shared ChannelRuntime.

Ported from ``omicsclaw/surfaces/channels/manager.py`` for plan 0031 task D1,
unchanged apart from one wrapped line and this paragraph. The composition root
lives above it: build the runtime, bind it into every Channel, and only then
call :meth:`ChannelManager.start_all`, which opens every Channel's ingress
together::

    runtime = ChannelRuntime.for_channel_surfaces(app, bindings=bindings)
    await runtime.start()
    for channel in manager.channels.values():
        channel.bind_control_runtime(runtime, loop=asyncio.get_running_loop())
    await manager.start_all()

The barrier matters: ingress opens for **all** Channels or none, so a message
arriving during start-up cannot reach a runtime that is not yet accepting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from .base import Channel

logger = logging.getLogger(__name__)


# ─ Per-channel health metrics ──────────────────


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


# ─ Channel Manager ──────────────────────


class ChannelManager:
    """Manages multiple channels with unified lifecycle.

    The manager:
    1. Registers channels and stores them by name
    2. Starts/stops channels concurrently
    3. Provides a health check endpoint

    Cut-over Channels handle their own RawInbound Adapter boundary; the manager
    only owns lifecycle, the authoritative-cutover gate and health.
    """

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}
        self._health: dict[str, ChannelHealth] = {}
        self._start_time: float = 0.0
        self._running = False
        self._health_server: asyncio.Server | None = None
        self._health_lifecycle_lock = asyncio.Lock()

    # ─ Properties ──────────────────────

    @property
    def channels(self) -> dict[str, Channel]:
        return dict(self._channels)

    @property
    def enabled_channels(self) -> list[str]:
        return list(self._channels.keys())

    def running_channels(self) -> list[str]:
        return [n for n, c in self._channels.items() if c._running]

    # ─ Registration ─────────────────────

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

    # ─ Lifecycle ──────────────────────

    async def start_all(self) -> None:
        """Start every transport, then open ingress as one process-local unit."""
        self._start_time = time.monotonic()
        self._running = True

        tasks = []
        for name, channel in self._channels.items():
            tasks.append(self._start_one(name, channel))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            await self.stop_all()
            failed_names = [
                name
                for (name, _channel), result in zip(self._channels.items(), results)
                if isinstance(result, BaseException)
            ]
            raise RuntimeError(
                "Channel startup failed for: " + ", ".join(failed_names)
            ) from None

        not_running = [
            name for name, channel in self._channels.items() if not channel._running
        ]
        if not_running:
            await self.stop_all()
            raise RuntimeError(
                "Channel startup failed for: " + ", ".join(not_running)
            ) from None

        for channel in self._channels.values():
            channel.activate_ingress()

        logger.info(
            f"ChannelManager started ({len(self.running_channels())}"
            f"/{len(self._channels)} channels active)"
        )

    async def _start_one(self, name: str, channel: Channel) -> None:
        """Start a single channel with error handling."""
        health = self._health[name]
        try:
            channel.require_authoritative_ingress()
            await channel.start()
            health.started_at = time.monotonic()
            health.record_success()
            logger.info(f"Channel '{name}' started successfully")
        except Exception as error:
            error_type = type(error).__name__
            health.record_failure(error_type)
            logger.error("Failed to start channel '%s' (%s)", name, error_type)
            raise RuntimeError(
                f"Channel '{name}' failed to start ({error_type})"
            ) from None

    async def start_channel(self, name: str) -> None:
        """Start a single already-registered channel.

        Safe to call while the manager is running — the consumer/dispatcher
        loops will pick up the new channel automatically.
        """
        channel = self._channels.get(name)
        if channel is None:
            raise ValueError(f"Channel '{name}' is not registered")
        if channel._running:
            return  # already running
        await self._start_one(name, channel)
        channel.activate_ingress()

    async def stop_channel(self, name: str) -> None:
        """Stop and unregister a single channel.

        If no channels remain, the manager keeps running (caller decides
        whether to tear it down).
        """
        channel = self._channels.get(name)
        if channel is None:
            return
        await self._stop_one(name, channel)
        self.unregister(name)

    async def stop_all(self) -> None:
        """Close ingress, stop all transports, and aggregate sanitized failures."""
        self._running = False

        for channel in self._channels.values():
            channel.deactivate_ingress()

        tasks = []
        for name, channel in self._channels.items():
            tasks.append(self._stop_one(name, channel))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failed = [
            f"{name} ({self._health[name].last_error or 'Exception'})"
            for (name, _channel), result in zip(self._channels.items(), results)
            if isinstance(result, BaseException)
        ]
        failures = []
        if failed:
            failures.append("Channel shutdown failed for: " + ", ".join(failed))

        async with self._health_lifecycle_lock:
            health_server = self._health_server
            if health_server is not None:
                health_error_type: str | None = None
                try:
                    health_server.close()
                except BaseException as error:
                    health_error_type = type(error).__name__
                    logger.error(
                        "Error closing Health server (%s)",
                        health_error_type,
                    )
                try:
                    await health_server.wait_closed()
                except BaseException as error:
                    health_error_type = health_error_type or type(error).__name__
                    logger.error(
                        "Error waiting for Health server shutdown (%s)",
                        type(error).__name__,
                    )
                if health_error_type is None:
                    self._health_server = None
                else:
                    failures.append(
                        f"Health server shutdown failed ({health_error_type})"
                    )

        if failures:
            raise RuntimeError("; ".join(failures)) from None

        logger.info("ChannelManager stopped")

    async def _stop_one(self, name: str, channel: Channel) -> None:
        """Stop a single channel with error handling."""
        channel.deactivate_ingress()
        try:
            await channel.stop()
            logger.info(f"Channel '{name}' stopped")
        except Exception as error:
            error_type = type(error).__name__
            self._health[name].record_failure(error_type)
            logger.error(
                "Error stopping channel '%s' (%s)",
                name,
                error_type,
            )
            raise RuntimeError(
                f"Channel '{name}' failed to stop ({error_type})"
            ) from None

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

    # ─ Health check ─────────────────────

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
            "channel_health": channels_health,
        }

    # ─ Health check server ───────────────────

    async def start_health_server(self, port: int = 8080) -> None:
        """Start a minimal HTTP health-check endpoint.

        Responds to ``GET /healthz`` with JSON health payload.
        """

        async def handle(reader, writer):
            try:
                request_line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=5.0,
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

        async with self._health_lifecycle_lock:
            if self._health_server is not None:
                raise RuntimeError("Health server already started")
            server = await asyncio.start_server(handle, "0.0.0.0", port)
            self._health_server = server
        addrs = [s.getsockname() for s in server.sockets]
        logger.info(f"Health server listening on {addrs}")
