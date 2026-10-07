"""Long-term memory files are private to their owner, and ``MEMORY.md`` is replaced atomically.

Long-term memory holds user preferences and project names. Before this
change ``memory.db``, its ``-wal`` and ``-shm`` files and ``MEMORY.md``
were created 0644, so any account on a shared machine could read them;
the WAL holds the same rows until a checkpoint, so tightening only the
main file is not enough. ``MEMORY.md`` was also written in place, so a
reader racing a regeneration could see a half-written file.
"""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

import pytest

from omicsclaw.memory import Database, LongTermStore, MemoryEntry, Precis
from omicsclaw.memory import precis as precis_module

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def loose_umask():
    """A umask that would leave new files group- and world-readable."""
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def test_a_new_database_and_its_wal_files_are_0600(tmp_path, loose_umask) -> None:
    target = tmp_path / "memory.db"
    db = Database(target)
    db.run(lambda c: c.execute(
        "INSERT INTO sessions (session_id, created_at, updated_at) VALUES ('s', 0, 0)"
    ))
    siblings = [Path(f"{target}{suffix}") for suffix in ("-wal", "-shm")]
    assert all(path.exists() for path in siblings), "WAL mode should leave -wal and -shm while open"
    assert _mode(target) == 0o600
    for path in siblings:
        assert _mode(path) == 0o600, path.name
    db.close()


def test_an_existing_database_keeps_its_mode(tmp_path, loose_umask) -> None:
    target = tmp_path / "memory.db"
    with Database(target):
        pass
    target.chmod(0o640)
    with Database(target):
        pass
    assert _mode(target) == 0o640


def test_memory_md_is_written_0600(tmp_path, loose_umask) -> None:
    db = Database()
    store = LongTermStore(db)
    asyncio.run(store.add(MemoryEntry(title="t", content="c")))
    target = tmp_path / "MEMORY.md"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o644)
    asyncio.run(Precis(store, target).regenerate())
    db.close()
    assert _mode(target) == 0o600
    assert "## t" in target.read_text(encoding="utf-8")


def test_a_failed_memory_md_write_leaves_the_old_file_and_no_temporary(tmp_path, monkeypatch) -> None:
    db = Database()
    store = LongTermStore(db)
    asyncio.run(store.add(MemoryEntry(title="t", content="c")))
    target = tmp_path / "MEMORY.md"
    target.write_text("old", encoding="utf-8")

    def refuse(src, dst):
        raise OSError("replace refused")

    monkeypatch.setattr(precis_module.os, "replace", refuse)
    with pytest.raises(OSError, match="replace refused"):
        asyncio.run(Precis(store, target).regenerate())
    db.close()
    assert target.read_text(encoding="utf-8") == "old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["MEMORY.md"]
