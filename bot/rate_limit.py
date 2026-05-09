"""Per-user rate limiter + LRU eviction helper for transcripts.

Carved out of ``bot/core.py`` per ADR 0001. ``check_rate_limit`` is pure;
``_evict_lru_conversations`` reaches into transcript / tool-result stores
that ``bot.core`` owns, so it late-imports them on each call.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("omicsclaw.bot.rate_limit")

RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "10"))
_rate_buckets: dict[str, list[float]] = {}


def check_rate_limit(user_id: str, admin_id: str = "") -> bool:
    """Check per-user rate limit. Returns True if allowed."""
    if RATE_LIMIT_PER_HOUR <= 0 or (admin_id and user_id == admin_id):
        return True
    now = time.time()
    bucket = _rate_buckets.setdefault(user_id, [])
    bucket[:] = [t for t in bucket if now - t < 3600]
    if len(bucket) >= RATE_LIMIT_PER_HOUR:
        return False
    bucket.append(now)
    return True


def _evict_lru_conversations():
    """Evict least-recently-used conversations when limit exceeded.

    Late-imports ``transcript_store`` / ``tool_result_store`` /
    ``MAX_CONVERSATIONS`` from ``bot.core`` so the module loads without a
    circular dependency at import time.
    """
    from bot.core import MAX_CONVERSATIONS, tool_result_store, transcript_store

    transcript_store.max_conversations = MAX_CONVERSATIONS
    evicted = transcript_store.evict_lru_conversations()
    for chat_id in evicted:
        tool_result_store.clear(chat_id)
    if evicted:
        logger.debug(f"Evicted {len(evicted)} stale conversation(s)")
