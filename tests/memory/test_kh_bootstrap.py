"""Tests for the KH bootstrap that seeds ``__shared__`` after init_db.

Phase 1.3 of the KH-to-graph migration. The bootstrap function pulls
every ``(uri, content)`` from ``KnowHowInjector.iter_entries`` and
writes it via ``MemoryEngine.seed_shared``. Re-running on a populated
database is a no-op (idempotency comes from ``seed_shared`` itself).

Bootstrap failures must NEVER prevent a surface from starting — a
missing knowledge_base/ directory or a write error must downgrade
to a log line, not an exception.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from omicsclaw.memory.bootstrap import seed_knowhows
from omicsclaw.memory.database import DatabaseManager
from omicsclaw.memory.engine import MemoryEngine
from omicsclaw.memory.models import SHARED_NAMESPACE
from omicsclaw.memory.search import SearchIndexer
from omicsclaw.knowledge.knowhow import KnowHowInjector


def _write_kh(kh_dir: Path, filename: str, body: str) -> None:
    kh_dir.mkdir(parents=True, exist_ok=True)
    (kh_dir / filename).write_text(body, encoding="utf-8")


@pytest_asyncio.fixture
async def engine(tmp_path):
    db = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    search = SearchIndexer(db)
    yield MemoryEngine(db, search)
    await db.close()


@pytest_asyncio.fixture
def kh_injector(tmp_path):
    kh_dir = tmp_path / "kh"
    _write_kh(kh_dir, "KH-a.md", "---\ndoc_id: rule-a\n---\n\nBody A\n")
    _write_kh(kh_dir, "KH-b.md", "---\ndoc_id: rule-b\n---\n\nBody B\n")
    return KnowHowInjector(knowhows_dir=kh_dir)


@pytest.mark.asyncio
async def test_seed_knowhows_writes_each_entry_to_shared(engine, kh_injector):
    stats = await seed_knowhows(engine, injector=kh_injector)

    assert stats == {"seeded": 2, "skipped": 0, "failed": 0}

    record_a = await engine.recall(
        "core://kh/rule-a", namespace=SHARED_NAMESPACE
    )
    record_b = await engine.recall(
        "core://kh/rule-b", namespace=SHARED_NAMESPACE
    )
    assert record_a is not None and "Body A" in record_a.content
    assert record_b is not None and "Body B" in record_b.content


@pytest.mark.asyncio
async def test_seed_knowhows_is_idempotent_on_unchanged_corpus(
    engine, kh_injector
):
    first = await seed_knowhows(engine, injector=kh_injector)
    second = await seed_knowhows(engine, injector=kh_injector)

    assert first == {"seeded": 2, "skipped": 0, "failed": 0}
    assert second == {"seeded": 0, "skipped": 2, "failed": 0}


@pytest.mark.asyncio
async def test_seed_knowhows_detects_changed_content(tmp_path, engine):
    kh_dir = tmp_path / "kh"
    _write_kh(kh_dir, "KH-c.md", "---\ndoc_id: rule-c\n---\n\nBody v1\n")
    injector = KnowHowInjector(knowhows_dir=kh_dir)
    await seed_knowhows(engine, injector=injector)

    # Simulate an updated KH on disk — fresh injector to bypass _cache.
    _write_kh(kh_dir, "KH-c.md", "---\ndoc_id: rule-c\n---\n\nBody v2\n")
    fresh = KnowHowInjector(knowhows_dir=kh_dir)
    stats = await seed_knowhows(engine, injector=fresh)

    assert stats["seeded"] == 1
    assert stats["skipped"] == 0
    record = await engine.recall(
        "core://kh/rule-c", namespace=SHARED_NAMESPACE
    )
    assert record is not None and "Body v2" in record.content


@pytest.mark.asyncio
async def test_seed_knowhows_swallows_iter_errors(engine):
    class _BrokenInjector:
        def iter_entries(self):
            raise RuntimeError("knowledge_base unreadable")

    stats = await seed_knowhows(engine, injector=_BrokenInjector())

    assert stats == {"seeded": 0, "skipped": 0, "failed": 0}


@pytest.mark.asyncio
async def test_compat_memory_store_seeds_kh_on_initialize(tmp_path):
    """Wiring check: bot startup (CompatMemoryStore.initialize) must seed
    KH guards into __shared__ so the bot's first message has graph access
    to them. Catches a future regression that drops the bootstrap call.
    """
    import sqlalchemy as sa

    from omicsclaw.memory.compat import CompatMemoryStore
    from omicsclaw.memory.models import Path

    store = CompatMemoryStore(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/wired.db"
    )
    try:
        await store.initialize()
        async with store._db.session() as s:
            rows = (
                await s.execute(
                    sa.select(Path).where(
                        Path.namespace == SHARED_NAMESPACE,
                        Path.domain == "core",
                        Path.path.like("kh/%"),
                    )
                )
            ).scalars().all()
        assert len(rows) > 0, (
            "CompatMemoryStore.initialize() did not seed any core://kh/* "
            "rows — bootstrap wiring is broken."
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_seed_knowhows_swallows_per_entry_errors(engine, kh_injector):
    """One bad URI must not stop the rest of the corpus from seeding."""

    class _PartialInjector:
        def __init__(self, real):
            self._real = real

        def iter_entries(self):
            yield "core://kh/good", "Good body"
            yield "://malformed", "Malformed URI"
            for uri, content in self._real.iter_entries():
                yield uri, content

    stats = await seed_knowhows(
        engine, injector=_PartialInjector(kh_injector)
    )

    assert stats["seeded"] >= 1
    assert stats["failed"] >= 1
    # Good entry and the two real-injector entries land in __shared__.
    record = await engine.recall(
        "core://kh/good", namespace=SHARED_NAMESPACE
    )
    assert record is not None

    # Entries iterated AFTER the malformed one must still be written —
    # one bad URI mustn't poison the rest of the corpus.
    record_a = await engine.recall(
        "core://kh/rule-a", namespace=SHARED_NAMESPACE
    )
    record_b = await engine.recall(
        "core://kh/rule-b", namespace=SHARED_NAMESPACE
    )
    assert record_a is not None
    assert record_b is not None
