"""Fingerprints, categories and expiry, without touching a database."""

from __future__ import annotations

from omicsclaw.memory import Category, MemoryEntry, normalize, signature

DAY = 86400.0


def test_normalize_folds_case_and_whitespace() -> None:
    assert normalize("  Min_Counts   =\n500  ") == "min_counts = 500"


def test_layout_differences_share_a_fingerprint() -> None:
    assert signature("min_counts=500 min_genes=200") == signature(
        "MIN_COUNTS=500\n\n   min_genes=200  "
    )


def test_different_content_gets_a_different_fingerprint() -> None:
    assert signature("min_counts=500") != signature("min_counts=1000")


def test_entry_exposes_its_own_fingerprint() -> None:
    entry = MemoryEntry(content="spatial domains use leiden")
    assert entry.signature == signature("spatial domains use leiden")


def test_zero_ttl_never_expires() -> None:
    entry = MemoryEntry(content="x", ttl_days=0, updated_at=0.0)
    assert entry.expired(now=1e12) is False


def test_negative_ttl_never_expires() -> None:
    entry = MemoryEntry(content="x", ttl_days=-5, updated_at=0.0)
    assert entry.expired(now=1e12) is False


def test_entry_inside_its_ttl_is_live() -> None:
    entry = MemoryEntry(content="x", ttl_days=7, updated_at=0.0)
    assert entry.expired(now=6 * DAY) is False


def test_entry_past_its_ttl_is_expired() -> None:
    entry = MemoryEntry(content="x", ttl_days=7, updated_at=0.0)
    assert entry.expired(now=8 * DAY) is True


def test_expiry_runs_from_the_update_not_the_creation() -> None:
    """The TTL clock restarts when an entry is rewritten.

    An entry created long ago but updated yesterday is current, not
    stale. Judging from ``created_at`` would throw away exactly the
    memories that are being kept up to date.
    """
    entry = MemoryEntry(
        content="x", ttl_days=7, created_at=0.0, updated_at=100 * DAY
    )
    assert entry.expired(now=101 * DAY) is False
    assert entry.expired(now=108 * DAY) is True


def test_categories_are_plain_strings() -> None:
    assert Category.KNOWLEDGE == "knowledge"
    assert set(Category) == {
        Category.KNOWLEDGE,
        Category.PREFERENCE,
        Category.TASK,
        Category.SKILL,
    }
