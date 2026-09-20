"""The long-term memory entry: its category, fingerprint and expiry."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import StrEnum

_SECONDS_PER_DAY = 86400.0


class Category(StrEnum):
    """What kind of thing an entry records."""

    KNOWLEDGE = "knowledge"
    PREFERENCE = "preference"
    TASK = "task"
    SKILL = "skill"


def normalize(content: str) -> str:
    """Fold *content* to the form fingerprints are taken over.

    Lowercases, collapses every run of whitespace to one space and strips
    the ends, so two entries that differ only in layout share a
    fingerprint.

    :param content: Raw entry body.
    :returns: The normalised form.
    """
    return " ".join(content.lower().split())


def signature(content: str) -> str:
    """The deduplication fingerprint of *content*.

    :param content: Raw entry body.
    :returns: Hex SHA-256 of :func:`normalize`'s output.
    """
    return hashlib.sha256(normalize(content).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class MemoryEntry:
    """One thing worth remembering across sessions.

    :param id: Identifier assigned by the store on first write.
    :param title: Short label shown in the précis.
    :param content: The body of the memory.
    :param category: What kind of thing this records.
    :param importance: 0-10; orders the précis and drives staleness.
    :param ttl_days: Days after the last update before the entry expires;
        ``0`` or less never expires.
    """

    id: str = ""
    title: str = ""
    content: str = ""
    category: Category | str = ""
    importance: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_used_at: float | None = None
    use_count: int = 0
    ttl_days: int = 0
    disabled: bool = False
    tags: tuple[str, ...] = ()

    @property
    def signature(self) -> str:
        """The deduplication fingerprint of this entry's content."""
        return signature(self.content)

    def expired(self, now: float | None = None) -> bool:
        """Whether the entry has outlived its TTL.

        The clock runs from ``updated_at``, so rewriting an entry defers
        its expiry. Reading one does not: reaching for a memory is no
        evidence that it is still true.

        :param now: Epoch seconds to judge against; defaults to the
            current time.
        :returns: ``True`` when the entry has expired.
        """
        if self.ttl_days <= 0:
            return False
        deadline = self.updated_at + self.ttl_days * _SECONDS_PER_DAY
        return deadline < (time.time() if now is None else now)
