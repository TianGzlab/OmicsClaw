"""Bridge between QueryEngineCallbacks.on_context_compacted and the SSE queue.

Lives in its own module so the wiring is unit-testable without importing
the rest of ``server.py`` (which carries fastapi / httpx imports).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from omicsclaw.runtime.context_compaction import (
    CompactionEvent,
    build_compaction_status_payload,
)

logger = logging.getLogger(__name__)


def make_compaction_event_handler(queue: Any) -> Callable[[CompactionEvent], None]:
    """Return a handler that serialises a CompactionEvent and pushes it
    onto the desktop server's SSE queue as a 'status' frame.

    The queue is duck-typed: anything with a ``put_nowait(item)`` method
    works (asyncio.Queue, but also test doubles).
    """

    def handle(event: CompactionEvent) -> None:
        try:
            payload = build_compaction_status_payload(event)
            queue.put_nowait(
                {"type": "status", "data": json.dumps(payload)}
            )
        except Exception:
            logger.warning(
                "Failed to push compaction event to SSE queue; ignoring.",
                exc_info=True,
            )

    return handle


__all__ = ["make_compaction_event_handler"]
