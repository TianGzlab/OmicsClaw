"""Bootstrap helpers — seed the ``__shared__`` namespace at startup.

``seed_knowhows`` walks every ``KnowHowInjector`` entry and writes it
through ``MemoryEngine.seed_shared``. Idempotency comes from
``seed_shared`` itself (same content → no write); this module just
handles enumeration, error containment, and stat reporting.

Bootstrap failures are intentionally non-fatal: a missing
``knowledge_base/`` directory or a write error must downgrade to a
warning log, not block the surface from coming up.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .engine import MemoryEngine


async def seed_knowhows(
    engine: "MemoryEngine",
    *,
    injector: Optional[Any] = None,
) -> dict[str, int]:
    """Seed every loaded KH document into ``__shared__``.

    Returns ``{"seeded": N, "skipped": N, "failed": N}``:
      - ``seeded`` — entries whose content was written (new or changed).
      - ``skipped`` — entries whose active content already matched.
      - ``failed`` — entries where the write raised; reasons are logged.

    Passing ``injector`` is intended for tests; production callers omit
    it and the function uses the global ``KnowHowInjector`` singleton.
    """
    if injector is None:
        from omicsclaw.knowledge.knowhow import get_knowhow_injector

        injector = get_knowhow_injector()

    stats = {"seeded": 0, "skipped": 0, "failed": 0}

    try:
        entries = list(injector.iter_entries())
    except Exception as exc:
        logger.warning(
            "KH bootstrap: enumerate failed (%s); skipping seed", exc
        )
        return stats

    for uri, content in entries:
        try:
            _, written = await engine.seed_shared(uri, content)
            if written:
                stats["seeded"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:
            stats["failed"] += 1
            logger.warning(
                "KH bootstrap: seed %s failed (%s)", uri, exc
            )

    if stats["seeded"] or stats["failed"]:
        logger.info(
            "KH bootstrap: %d seeded, %d unchanged, %d failed",
            stats["seeded"],
            stats["skipped"],
            stats["failed"],
        )
    return stats
