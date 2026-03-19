"""
Composable message processing middleware.

Each middleware is a standalone class that can be composed into a pipeline.
They extract logic that was previously baked into individual bot scripts,
making it reusable across all channels.

Adapted from EvoScientist's middleware.py, simplified for OmicsClaw.

Available middleware:
- DedupMiddleware:        Message deduplication
- RateLimitMiddleware:    Per-sender rate limiting
- AllowListMiddleware:    Sender/channel filtering
- MentionGatingMiddleware: Group chat mention filtering
- GroupHistoryMiddleware:  Accumulate group context for @mentions
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Callable

from .bus import InboundMessage, OutboundMessage

_logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Base middleware classes
# ═══════════════════════════════════════════════════════════════════════


class InboundMiddleware:
    """Base class for inbound message processing middleware.

    Override ``process()`` to implement filtering or transformation.
    Return ``None`` to drop a message from the pipeline.
    """

    async def process(
        self,
        msg: InboundMessage,
        context: dict[str, Any] | None = None,
    ) -> InboundMessage | None:
        return msg


class OutboundMiddleware:
    """Base class for outbound message processing middleware."""

    async def process(
        self,
        msg: OutboundMessage,
        context: dict[str, Any] | None = None,
    ) -> OutboundMessage | None:
        return msg


# ═══════════════════════════════════════════════════════════════════════
# Pipeline runner
# ═══════════════════════════════════════════════════════════════════════


class MiddlewarePipeline:
    """Runs messages through a chain of middleware in order.

    Usage::

        pipeline = MiddlewarePipeline([
            DedupMiddleware(),
            RateLimitMiddleware(max_per_hour=10),
            AllowListMiddleware(allowed_senders={"admin_123"}),
        ])
        result = await pipeline.process_inbound(msg)
        if result is None:
            # message was filtered out
            pass
    """

    def __init__(
        self,
        inbound: list[InboundMiddleware] | None = None,
        outbound: list[OutboundMiddleware] | None = None,
    ):
        self._inbound = inbound or []
        self._outbound = outbound or []

    def add_inbound(self, mw: InboundMiddleware) -> None:
        """Append an inbound middleware to the pipeline."""
        self._inbound.append(mw)

    def add_outbound(self, mw: OutboundMiddleware) -> None:
        """Append an outbound middleware to the pipeline."""
        self._outbound.append(mw)

    async def process_inbound(
        self,
        msg: InboundMessage,
        context: dict[str, Any] | None = None,
    ) -> InboundMessage | None:
        """Run an inbound message through all inbound middleware."""
        ctx = context or {}
        current: InboundMessage | None = msg
        for mw in self._inbound:
            if current is None:
                return None
            current = await mw.process(current, ctx)
        return current

    async def process_outbound(
        self,
        msg: OutboundMessage,
        context: dict[str, Any] | None = None,
    ) -> OutboundMessage | None:
        """Run an outbound message through all outbound middleware."""
        ctx = context or {}
        current: OutboundMessage | None = msg
        for mw in self._outbound:
            if current is None:
                return None
            current = await mw.process(current, ctx)
        return current


# ═══════════════════════════════════════════════════════════════════════
# Inbound middleware implementations
# ═══════════════════════════════════════════════════════════════════════


class DedupMiddleware(InboundMiddleware):
    """Message deduplication using a bounded TTL cache.

    Drops messages whose ``message_id`` has been seen within the TTL window.
    """

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

    async def process(
        self,
        msg: InboundMessage,
        context: dict[str, Any] | None = None,
    ) -> InboundMessage | None:
        if not msg.message_id:
            return msg
        self._prune()
        if msg.message_id in self._seen:
            self._seen.move_to_end(msg.message_id)
            self._seen[msg.message_id] = time.monotonic()
            _logger.debug(f"Dedup: dropping duplicate {msg.message_id}")
            return None
        self._seen[msg.message_id] = time.monotonic()
        if len(self._seen) > self._max:
            while len(self._seen) > self._trim:
                self._seen.popitem(last=False)
        return msg

    def _prune(self) -> None:
        cutoff = time.monotonic() - self._ttl
        while self._seen:
            key, ts = next(iter(self._seen.items()))
            if ts > cutoff:
                break
            self._seen.popitem(last=False)

    @property
    def cache_size(self) -> int:
        return len(self._seen)


class RateLimitMiddleware(InboundMiddleware):
    """Per-sender sliding-window rate limiter.

    Drops messages from senders who exceed the hourly limit.
    Admin senders (identified via ``admin_ids``) bypass limits.
    """

    def __init__(
        self,
        max_per_hour: int = 60,
        admin_ids: set[str] | None = None,
        on_limited: Callable[[InboundMessage], Any] | None = None,
    ) -> None:
        self.max_per_hour = max_per_hour
        self.admin_ids = admin_ids or set()
        self.on_limited = on_limited
        self._buckets: dict[str, list[float]] = {}

    async def process(
        self,
        msg: InboundMessage,
        context: dict[str, Any] | None = None,
    ) -> InboundMessage | None:
        if self.max_per_hour <= 0:
            return msg
        if msg.sender_id in self.admin_ids:
            return msg

        now = time.time()
        bucket = self._buckets.setdefault(msg.sender_id, [])
        bucket[:] = [t for t in bucket if now - t < 3600]
        if len(bucket) >= self.max_per_hour:
            _logger.debug(
                f"Rate limit: dropping message from {msg.sender_id} "
                f"({len(bucket)}/{self.max_per_hour} in last hour)"
            )
            if self.on_limited:
                try:
                    result = self.on_limited(msg)
                    if hasattr(result, '__await__'):
                        await result
                except Exception:
                    pass
            return None
        bucket.append(now)
        return msg


class AllowListMiddleware(InboundMiddleware):
    """Sender and channel allow-list enforcement.

    Drops messages from senders or channels not in the allow lists.
    If an allow list is None, that dimension is unrestricted.
    """

    def __init__(
        self,
        allowed_senders: set[str] | None = None,
        allowed_channels: set[str] | None = None,
    ) -> None:
        self.allowed_senders = allowed_senders
        self.allowed_channels = allowed_channels

    async def process(
        self,
        msg: InboundMessage,
        context: dict[str, Any] | None = None,
    ) -> InboundMessage | None:
        # Channel allow-list
        if self.allowed_channels and msg.chat_id not in self.allowed_channels:
            _logger.debug(f"AllowList: dropping message from non-allowed chat {msg.chat_id}")
            return None

        # Sender allow-list
        if self.allowed_senders and msg.sender_id not in self.allowed_senders:
            _logger.debug(f"AllowList: dropping message from non-allowed sender {msg.sender_id}")
            return None

        return msg


class MentionGatingMiddleware(InboundMiddleware):
    """Filter messages based on mention policy in group chats.

    Policy values:
    - ``"always"``: require mention in all chats
    - ``"group"``: require mention only in groups (default)
    - ``"off"``: never require mention (respond to everything)
    """

    def __init__(
        self,
        require_mention: str = "group",
        strip_mention_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.require_mention = require_mention
        self._strip_fn = strip_mention_fn

    async def process(
        self,
        msg: InboundMessage,
        context: dict[str, Any] | None = None,
    ) -> InboundMessage | None:
        if not self._should_process(msg):
            return None
        # Strip @mention text from group messages
        if msg.is_group and self._strip_fn and isinstance(msg.content, str):
            msg = dataclasses.replace(msg, content=self._strip_fn(msg.content))
        return msg

    def _should_process(self, msg: InboundMessage) -> bool:
        if self.require_mention == "off":
            return True
        if self.require_mention == "always":
            return msg.was_mentioned
        # "group" — require mention only in groups
        if not msg.is_group:
            return True
        return msg.was_mentioned


# ── Group history context ────────────────────────────────────────────


@dataclass
class _HistoryEntry:
    sender_id: str
    text: str
    timestamp: float
    message_id: str = ""


class GroupHistoryMiddleware(InboundMiddleware):
    """Buffer non-mentioned group messages, inject as context when mentioned.

    When the bot is mentioned in a group, all buffered messages since the
    last mention are prepended as context to help the LLM understand the
    conversation flow.
    """

    def __init__(
        self,
        max_per_chat: int = 50,
        max_age_seconds: int = 3600,
    ) -> None:
        self._buffers: dict[str, deque[_HistoryEntry]] = {}
        self._max = max_per_chat
        self._max_age = max_age_seconds

    async def process(
        self,
        msg: InboundMessage,
        context: dict[str, Any] | None = None,
    ) -> InboundMessage | None:
        if not msg.is_group:
            return msg

        ts = time.monotonic()
        content_text = msg.content if isinstance(msg.content, str) else str(msg.content)

        if not msg.was_mentioned:
            # Buffer the message for context
            if msg.chat_id not in self._buffers:
                self._buffers[msg.chat_id] = deque(maxlen=self._max)
            self._buffers[msg.chat_id].append(
                _HistoryEntry(
                    sender_id=msg.sender_id,
                    text=content_text,
                    timestamp=ts,
                    message_id=msg.message_id,
                )
            )
            return msg  # Let MentionGatingMiddleware handle the drop

        # Mentioned: inject history context
        buf = self._buffers.get(msg.chat_id)
        if buf:
            cutoff = time.monotonic() - self._max_age
            recent = [e for e in buf if e.timestamp > cutoff]
            if recent:
                lines = ["[Chat messages since your last reply - for context]"]
                for e in recent[-20:]:
                    lines.append(f"[from: {e.sender_id}] {e.text}")
                lines.append("[/Chat context]")
                context_block = "\n".join(lines)
                new_content = (
                    context_block
                    + "\n\n[Current message - respond to this]\n"
                    + content_text
                )
                msg = dataclasses.replace(msg, content=new_content)
            self._buffers.pop(msg.chat_id, None)

        return msg


# ═══════════════════════════════════════════════════════════════════════
# Outbound middleware implementations
# ═══════════════════════════════════════════════════════════════════════


class TextLimitMiddleware(OutboundMiddleware):
    """Truncate outbound messages that exceed a maximum length.

    Instead of splitting (which is handled by Channel.send()), this
    middleware truncates with a warning suffix for safety.
    """

    def __init__(self, max_length: int = 50000) -> None:
        self.max_length = max_length
        self._suffix = "\n\n[Message truncated due to length]"

    async def process(
        self,
        msg: OutboundMessage,
        context: dict[str, Any] | None = None,
    ) -> OutboundMessage | None:
        if len(msg.content) > self.max_length:
            truncated = msg.content[:self.max_length - len(self._suffix)] + self._suffix
            return dataclasses.replace(msg, content=truncated)
        return msg


class AuditMiddleware(OutboundMiddleware):
    """Log outbound messages for audit purposes."""

    def __init__(self, audit_fn: Callable[..., Any] | None = None) -> None:
        self._audit_fn = audit_fn

    async def process(
        self,
        msg: OutboundMessage,
        context: dict[str, Any] | None = None,
    ) -> OutboundMessage | None:
        if self._audit_fn:
            try:
                self._audit_fn(
                    "outbound",
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content_length=len(msg.content),
                )
            except Exception:
                pass
        return msg
