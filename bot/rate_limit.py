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


# ``_evict_lru_conversations`` was relocated to ``bot.session`` in slice #116
# (it manages session-storage limits, not rate-limit buckets).
