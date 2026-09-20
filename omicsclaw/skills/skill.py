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
    """From ``trigger:``; empty when the header does not declare one."""

    tags: tuple[str, ...] = ()
    """From ``tags:``. Carried as metadata; nothing here filters on it."""

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
