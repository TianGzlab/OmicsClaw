"""The record for one loaded skill."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

__all__ = ["Skill"]


@dataclass(frozen=True, slots=True)
class Skill:
    """One ``SKILL.md`` found on disk, with its body still unread.

    Metadata is parsed once when the tree is scanned; the body is read
    only when :meth:`~omicsclaw.skills.index.SkillIndex.get_full_content`
    asks for it.

    :attr:`path` is always written by the loader and never assembled from
    caller input, so a lookup by name cannot be turned into a traversal.
    """

    name: str
    """From ``name:``. Unique within an index, and the identifier
    ``use_skill`` is called with."""

    description: str
    """From ``description:``, folded continuation lines included."""

    path: Path
    """The ``SKILL.md`` itself, spelled the way the scanned root was:
    relative under a relative root, absolute under an absolute one."""

    root: Path
    """The directory that was scanned to find this skill."""

    trigger: str = ""
    """From ``trigger:``, as one display string; empty when undeclared.

    A header may spell it as a comma-separated scalar or as a block
    sequence; the loader joins a sequence with ``", "`` so this attribute
    reads the same either way. :attr:`triggers` is the parsed form.
    """

    tags: tuple[str, ...] = ()
    """From ``tags:``. Carried as metadata; nothing here filters on it."""

    @property
    def triggers(self) -> tuple[str, ...]:
        """:attr:`trigger` split on commas, trimmed, empties dropped.

        These are discovery keywords, not an automatic dispatch rule:
        nothing in this package fires a skill because a turn contained
        one. They widen :meth:`~omicsclaw.skills.index.SkillIndex.search`
        so that a user hunting for "DE" finds ``spatial-de`` under a name
        that does not contain the word.
        """
        return tuple(part.strip() for part in self.trigger.split(",") if part.strip())

    @property
    def directory(self) -> Path:
        """The skill's own directory — where its scripts and data sit."""
        return self.path.parent

    @property
    def relative_path(self) -> PurePosixPath:
        """:attr:`path` relative to :attr:`root`, with forward slashes.

        POSIX-spelled so it is a stable sort key across platforms.
        """
        return PurePosixPath(self.path.relative_to(self.root).as_posix())

    @property
    def domain(self) -> str:
        """The first directory under the root, or ``""`` at the root itself.

        ``spatial/spatial-de/SKILL.md`` and ``literature/SKILL.md`` both
        answer with their leading directory.
        """
        parts = self.relative_path.parts
        return parts[0] if len(parts) > 1 else ""
