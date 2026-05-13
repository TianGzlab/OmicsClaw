"""
Abstract base class for OmicsClaw communication channels.

Defines the Channel interface that all messaging channels (Telegram, Feishu,
DingTalk, Discord, etc.) must implement. Provides common functionality:
- Smart text chunking (code-fence-aware)
- Auto-formatting based on channel capabilities
- Rate limiting
- Message deduplication
- Typing indicator management

Channels call ``core.llm_tool_loop()`` directly from their platform
handlers; cross-cutting concerns (rate limit, dedup, audit) live in
``bot.core`` / ``bot.rate_limit`` rather than a separate pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .capabilities import ChannelCapabilities
from .config import BaseChannelConfig

_logger = logging.getLogger(__name__)


# ── Text chunking ────────────────────────────────────────────────────


def chunk_text(text: str, limit: int) -> list[str]:
    """Split text into chunks that respect logical boundaries and code fences.

    If a code block is split across chunks, each chunk is automatically
    wrapped in its own fences (``\u0060\u0060\u0060...\u0060\u0060\u0060``) to maintain formatting.

    Args:
        text: The text to split.
        limit: Maximum characters per chunk.

    Returns:
        List of text chunks, each <= limit characters.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    in_code_block = False
    code_block_lang = ""

    while remaining:
        # Reserve space for fences if we're inside a code block
        effective_limit = limit - (20 if in_code_block else 0)

        if len(remaining) <= effective_limit:
            segment = remaining
            best = len(remaining)
        else:
            segment = remaining[:effective_limit]
            best = -1

            if not in_code_block:
                # Paragraph boundary
                pos = segment.rfind("\n\n")
                if pos > 0:
                    best = pos
                # Line boundary
                if best == -1:
                    pos = segment.rfind("\n")
                    if pos > 0:
                        best = pos
                # Word boundary
                if best == -1:
                    pos = segment.rfind(" ")
                    if pos > 0:
                        best = pos
            else:
                # Inside code block: only split at newlines
                pos = segment.rfind("\n")
                if pos > 0:
                    best = pos

            if best == -1:
                best = effective_limit

        chunk_raw = remaining[:best].rstrip()

        # Track code fence state transitions
        starts_in_code = in_code_block
        current_lang = code_block_lang

        fences = list(re.finditer(r"```(\w*)", chunk_raw))
        for f in fences:
            if not in_code_block:
                in_code_block = True
                code_block_lang = f.group(1) or ""
            else:
                in_code_block = False
                code_block_lang = ""

        ends_in_code = in_code_block

        # Add fences if split mid-code-block
        prefix = f"```{current_lang}\n" if starts_in_code else ""
        suffix = "\n```" if ends_in_code else ""

        final_chunk = prefix + chunk_raw + suffix
        if final_chunk.strip():
            chunks.append(final_chunk)

        remaining = remaining[best:].lstrip("\n")

    return chunks


# ── Dedup cache ──────────────────────────────────────────────────────


class DedupCache:
    """Bounded ordered cache with TTL for detecting duplicate message IDs."""

    def __init__(
        self,
        max_size: int = 1000,
        trim_to: int = 500,
        ttl_seconds: float = 3600.0,
    ) -> None:
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._max = max_size
        self._trim = trim_to
        self._ttl = ttl_seconds

    def is_duplicate(self, msg_id: str) -> bool:
        """Return True if msg_id has been seen before.

        First-time IDs are recorded and False is returned.
        Empty IDs are never considered duplicates.
        """
        if not msg_id:
            return False
        self._prune()
        if msg_id in self._seen:
            self._seen.move_to_end(msg_id)
            self._seen[msg_id] = time.monotonic()
            return True
        self._seen[msg_id] = time.monotonic()
        if len(self._seen) > self._max:
            while len(self._seen) > self._trim:
                self._seen.popitem(last=False)
        return False

    def _prune(self) -> None:
        cutoff = time.monotonic() - self._ttl
        while self._seen:
            key, ts = next(iter(self._seen.items()))
            if ts > cutoff:
                break
            self._seen.popitem(last=False)


# ── Rate limiter ─────────────────────────────────────────────────────


class RateLimiter:
    """Per-sender sliding-window rate limiter."""

    def __init__(self, max_per_hour: int = 0):
        self.max_per_hour = max_per_hour
        self._buckets: dict[str, list[float]] = {}

    def check(self, sender_id: str) -> bool:
        """Return True if sender is within rate limits."""
        if self.max_per_hour <= 0:
            return True
        now = time.time()
        bucket = self._buckets.setdefault(sender_id, [])
        bucket[:] = [t for t in bucket if now - t < 3600]
        if len(bucket) >= self.max_per_hour:
            return False
        bucket.append(now)
        return True


# ── Typing indicator manager ─────────────────────────────────────────


class TypingManager:
    """Manages background typing-indicator loops per chat_id."""

    def __init__(
        self,
        send_action,
        interval: float = 5.0,
    ) -> None:
        self._send_action = send_action
        self._interval = interval
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, chat_id: str) -> None:
        await self.stop(chat_id)

        async def _loop() -> None:
            while True:
                try:
                    await self._send_action(chat_id)
                except Exception:
                    pass
                await asyncio.sleep(self._interval)

        self._tasks[chat_id] = asyncio.create_task(_loop())

    async def stop(self, chat_id: str) -> None:
        task = self._tasks.pop(chat_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def stop_all(self) -> None:
        for cid in list(self._tasks):
            await self.stop(cid)


# ── Channel ABC ──────────────────────────────────────────────────────


class Channel(ABC):
    """Abstract base class for OmicsClaw messaging channels.

    Subclasses must implement:
    - start()       — initialize the channel
    - stop()        — clean shutdown
    - _send_chunk() — send a single text chunk (platform-specific)

    Subclasses may optionally override:
    - send_media()        — send files/images
    - _send_typing()      — send typing indicator
    - _format_chunk()     — convert markdown to channel format
    - _strip_markup()     — remove markup for fallback
    - _is_admin()         — check admin status

    Subclasses should set ``name`` to a unique identifier (e.g. "telegram").
    """

    name: str = "base"
    capabilities: ChannelCapabilities = ChannelCapabilities()

    def __init__(self, config: BaseChannelConfig | None = None):
        self.config = config or BaseChannelConfig()
        self._running = False
        self._dedup = DedupCache()
        self._rate_limiter = RateLimiter(
            max_per_hour=self.config.rate_limit_per_hour,
        )
        # Typing indicator manager (channels override _send_typing)
        self._typing_manager = TypingManager(
            self._send_typing,
            interval=5.0,
        )

    # ── Lifecycle ────────────────────────────────────────────────────

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start the channel (connect, authenticate, etc.)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        ...

    async def run(self) -> None:
        """Start the channel and run until stopped."""
        await self.start()
        self._running = True
        try:
            while self._running:
                await asyncio.sleep(0.5)
        finally:
            await self.stop()

    # ── Sending ──────────────────────────────────────────────────────

    async def send(
        self,
        chat_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a message with auto-chunking based on capabilities.

        Returns True if all chunks sent successfully.
        """
        if not content:
            return True
        try:
            limit = self.config.text_chunk_limit or self.capabilities.max_text_length
            chunks = chunk_text(content, limit)
            for chunk in chunks:
                formatted = self._format_chunk(chunk)
                await self._send_chunk(chat_id, formatted, chunk, metadata or {})
            return True
        except Exception as e:
            _logger.error(f"{self.name} send error: {e}")
            return False

    @abstractmethod
    async def _send_chunk(
        self,
        chat_id: str,
        formatted_text: str,
        raw_text: str,
        metadata: dict[str, Any],
    ) -> None:
        """Send a single text chunk. Platform-specific implementation.

        Args:
            chat_id: Target chat identifier.
            formatted_text: Text formatted for the channel (HTML/Markdown/plain).
            raw_text: Original unformatted text (fallback).
            metadata: Channel-specific metadata.
        """
        ...

    async def send_media(
        self,
        chat_id: str,
        file_path: str,
        caption: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a media file. Override in subclasses with media_send capability."""
        return False

    # ── Formatting ──────────────────────────────────────────────────

    def _format_chunk(self, text: str) -> str:
        """Convert text to channel's preferred format.

        Default: return as-is. Override for HTML/Markdown conversion.
        """
        return text

    @staticmethod
    def strip_markup(text: str) -> str:
        """Remove common markup for plain-text fallback."""
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        text = re.sub(r"_(.*?)_", r"\1", text)
        text = re.sub(r"`(.*?)`", r"\1", text)
        return text

    # ── Typing indicator ─────────────────────────────────────────────

    async def _send_typing(self, chat_id: str) -> None:
        """Send a single typing indicator. Override in sub-classes."""
        pass

    async def start_typing(self, chat_id: str) -> None:
        """Start a background typing indicator loop."""
        if self.capabilities.typing:
            await self._typing_manager.start(chat_id)

    async def stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        await self._typing_manager.stop(chat_id)

    # ── Dedup and rate limiting ──────────────────────────────────────

    def is_duplicate(self, message_id: str) -> bool:
        """Check if a message ID is a duplicate."""
        return self._dedup.is_duplicate(message_id)

    def check_rate_limit(self, sender_id: str) -> bool:
        """Check if sender is within rate limits."""
        return self._rate_limiter.check(sender_id)

    def _is_admin(self, sender_id: str) -> bool:
        """Check if sender is an admin (bypasses rate limits). Override as needed."""
        return False

    # ── Process message (bridge to core.py) ──────────────────────────

    async def process_message(
        self,
        chat_id: str,
        user_id: str,
        content: str | list,
        *,
        platform: str = "",
        progress_fn=None,
        progress_update_fn=None,
    ) -> str:
        """Process an inbound message through the OmicsClaw LLM tool loop.

        This bridges the Channel abstraction to bot/core.py's LLM engine.
        """
        from bot import core

        return await core.llm_tool_loop(
            int(chat_id) if chat_id.isdigit() else chat_id,
            content,
            user_id=user_id,
            platform=platform or self.name,
            progress_fn=progress_fn,
            progress_update_fn=progress_update_fn,
        )
