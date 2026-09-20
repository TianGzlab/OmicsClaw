"""The bounded Markdown view and the truncation that bounds it."""

from __future__ import annotations

import asyncio

from omicsclaw.memory import (
    Category,
    Database,
    LongTermStore,
    MemoryEntry,
    Precis,
    render,
    truncate_utf8,
)


def run(coro):
    return asyncio.run(coro)


def test_truncation_leaves_short_text_alone() -> None:
    assert truncate_utf8("short", 100) == "short"


def test_truncation_keeps_utf8_intact() -> None:
    """A byte budget must not cut a character in half.

    Every character here is three UTF-8 bytes, so a budget that is not a
    multiple of three lands mid-character. Slicing the bytes and decoding
    strictly would raise; returning the broken bytes would poison
    whatever writes the file.
    """
    text = "空间转录组学分析流程" * 5
    for budget in range(20, 80):
        cut = truncate_utf8(text, budget)
        assert cut.encode("utf-8") == cut.encode("utf-8").decode(
            "utf-8"
        ).encode("utf-8")
        assert len(cut.encode("utf-8")) <= budget


def test_truncation_marks_what_it_dropped() -> None:
    cut = truncate_utf8("x" * 500, 100)
    assert cut.endswith("(truncated)")
    assert len(cut.encode("utf-8")) <= 100


def test_truncation_with_no_room_returns_nothing() -> None:
    assert truncate_utf8("x" * 500, 3) == ""


def test_render_of_nothing_is_empty() -> None:
    assert render([]) == ""


def test_render_writes_a_heading_per_entry() -> None:
    out = render(
        [
            MemoryEntry(title="Visium QC", content="min_counts=500",
                        category=Category.KNOWLEDGE),
            MemoryEntry(title="Palette", content="use viridis"),
        ]
    )
    assert "## Visium QC `knowledge`" in out
    assert "min_counts=500" in out
    assert "## Palette" in out
    assert "`" not in out.split("## Palette")[1].splitlines()[0]


def test_regenerate_writes_the_top_entries(tmp_path) -> None:
    db = Database()
    lt = LongTermStore(db)
    run(lt.add(MemoryEntry(title="high", content="a", importance=9)))
    run(lt.add(MemoryEntry(title="low", content="b", importance=1)))
    precis = Precis(lt, tmp_path / "MEMORY.md")
    written = run(precis.regenerate())
    db.close()
    assert written.index("## high") < written.index("## low")
    assert (tmp_path / "MEMORY.md").read_text(encoding="utf-8") == written


def test_regenerate_honours_the_entry_ceiling(tmp_path) -> None:
    db = Database()
    lt = LongTermStore(db)
    for i in range(10):
        run(lt.add(MemoryEntry(title=f"e{i}", content=f"body {i}",
                               importance=i)))
    precis = Precis(lt, tmp_path / "MEMORY.md", max_entries=3)
    written = run(precis.regenerate())
    db.close()
    assert written.count("## ") == 3


def test_regenerate_honours_the_byte_ceiling(tmp_path) -> None:
    db = Database()
    lt = LongTermStore(db)
    for i in range(30):
        run(lt.add(MemoryEntry(title=f"条目{i}", content="空间转录组" * 20,
                               importance=i)))
    precis = Precis(lt, tmp_path / "MEMORY.md", max_bytes=256)
    written = run(precis.regenerate())
    db.close()
    assert len(written.encode("utf-8")) <= 256


def test_regenerate_creates_the_parent_directory(tmp_path) -> None:
    db = Database()
    lt = LongTermStore(db)
    run(lt.add(MemoryEntry(title="t", content="c")))
    target = tmp_path / "nested" / "deeper" / "MEMORY.md"
    precis = Precis(lt, target)
    run(precis.regenerate())
    db.close()
    assert target.exists()


def test_read_before_any_write_is_empty(tmp_path) -> None:
    db = Database()
    precis = Precis(LongTermStore(db), tmp_path / "absent.md")
    db.close()
    assert precis.read() == ""


def test_read_returns_what_regenerate_wrote(tmp_path) -> None:
    db = Database()
    lt = LongTermStore(db)
    run(lt.add(MemoryEntry(title="t", content="内容")))
    precis = Precis(lt, tmp_path / "MEMORY.md")
    written = run(precis.regenerate())
    db.close()
    assert precis.read() == written


def test_soft_deleted_entries_leave_the_precis(tmp_path) -> None:
    db = Database()
    lt = LongTermStore(db)
    keep = run(lt.add(MemoryEntry(title="keep", content="a", importance=5)))
    drop = run(lt.add(MemoryEntry(title="drop", content="b", importance=9)))
    run(lt.soft_delete(drop))
    precis = Precis(lt, tmp_path / "MEMORY.md")
    written = run(precis.regenerate())
    db.close()
    assert keep and "## keep" in written
    assert "## drop" not in written
