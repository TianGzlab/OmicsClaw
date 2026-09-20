"""Scanning a directory tree for ``SKILL.md`` files.

The walk is recursive, so skills may sit at any depth, and a directory
holding a ``SKILL.md`` may still hold skills of its own::

    skills/literature/SKILL.md
    skills/orchestrator/SKILL.md
    skills/orchestrator/omics-skill-builder/SKILL.md
    skills/spatial/spatial-de/SKILL.md
    skills/singlecell/scrna/sc-de/SKILL.md

A missing root is an empty index rather than an error, and one
unindexable skill costs only itself.
"""

from __future__ import annotations

import os
from pathlib import Path

from .frontmatter import parse_frontmatter
from .index import SkillIndex, SkipReason, SkippedSkill
from .skill import Skill

__all__ = ["SKILL_FILENAME", "SkillLoadError", "load_skills"]

SKILL_FILENAME = "SKILL.md"
"""The only filename this loader recognises."""

_IGNORED_PREFIXES = (".",)
_IGNORED_NAMES = frozenset({"__pycache__", "node_modules"})
"""Directory names never descended into."""


class SkillLoadError(RuntimeError):
    """The skills root exists but could not be scanned.

    Raised for a root that cannot be read or is not a directory. An
    absent root is not an error, and a failure below the root is recorded
    as a :class:`~omicsclaw.skills.index.SkippedSkill` instead.
    """


def load_skills(root: str | os.PathLike[str], *, encoding: str = "utf-8") -> SkillIndex:
    """Scan *root* for ``SKILL.md`` files and index the ones that parse.

    Only the headers are read; instructions stay on disk until
    :meth:`~omicsclaw.skills.index.SkillIndex.get_full_content` asks for
    them. *root* is used as spelled, so a relative root yields relative
    skill paths. *encoding* applies to the header reads and is carried on
    the index for the later body reads.

    Skills are ordered by their path relative to *root*, which makes the
    rendered index byte-stable across machines. When two skills declare
    the same name the first in that order wins and the other is recorded
    in :attr:`~omicsclaw.skills.index.SkillIndex.skipped`.

    Returns an empty index when *root* does not exist.

    :raises SkillLoadError: *root* exists and cannot be scanned.
    """
    base = Path(root)
    skipped: list[SkippedSkill] = []

    try:
        found = _scan(base, skipped)
    except FileNotFoundError:
        return SkillIndex(root=base, encoding=encoding)
    except OSError as exc:
        raise SkillLoadError(f"cannot scan the skills root {base}: {exc}") from exc

    found.sort(key=lambda path: path.relative_to(base).as_posix())

    skills: list[Skill] = []
    claimed: dict[str, Path] = {}
    for path in found:
        skill = _load_one(path, base, encoding, skipped)
        if skill is None:
            continue
        first = claimed.get(skill.name)
        if first is not None:
            skipped.append(
                SkippedSkill(
                    path,
                    SkipReason.DUPLICATE_NAME,
                    f"{skill.name!r} is already loaded from {first}",
                )
            )
            continue
        claimed[skill.name] = path
        skills.append(skill)

    return SkillIndex(
        skills=tuple(skills),
        skipped=tuple(skipped),
        root=base,
        encoding=encoding,
    )


def _scan(directory: Path, skipped: list[SkippedSkill]) -> list[Path]:
    """Collect every ``SKILL.md`` at or under *directory*.

    Descent continues past a ``SKILL.md``, because a skill directory may
    contain further skills. Appends to *skipped* for any subdirectory
    that cannot be listed and carries on; only an error on *directory*
    itself propagates. Symlinked directories are not followed.
    """
    with os.scandir(directory) as entries:
        children = sorted(entries, key=lambda entry: entry.name)

    found: list[Path] = []
    skill_file = directory / SKILL_FILENAME
    if skill_file.is_file():
        found.append(skill_file)

    for entry in children:
        if not entry.is_dir(follow_symlinks=False) or _ignored(entry.name):
            continue
        try:
            found.extend(_scan(Path(entry.path), skipped))
        except OSError as exc:
            skipped.append(
                SkippedSkill(Path(entry.path), SkipReason.UNREADABLE, str(exc))
            )
    return found


def _ignored(name: str) -> bool:
    """Whether a directory of this name should be skipped by the walk."""
    return name.startswith(_IGNORED_PREFIXES) or name in _IGNORED_NAMES


def _load_one(
    path: Path,
    root: Path,
    encoding: str,
    skipped: list[SkippedSkill],
) -> Skill | None:
    """Parse one ``SKILL.md`` into a skill.

    Returns ``None`` and appends to *skipped* when the file cannot be
    read or its header lacks a name or a description.
    """
    try:
        text = path.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError) as exc:
        skipped.append(SkippedSkill(path, SkipReason.UNREADABLE, str(exc)))
        return None

    header = parse_frontmatter(text)
    if not header.has_frontmatter:
        skipped.append(SkippedSkill(path, SkipReason.NO_FRONTMATTER))
        return None

    name = header.text("name").strip()
    if not name:
        skipped.append(SkippedSkill(path, SkipReason.MISSING_NAME))
        return None

    description = header.text("description").strip()
    if not description:
        skipped.append(SkippedSkill(path, SkipReason.MISSING_DESCRIPTION, name))
        return None

    return Skill(
        name=name,
        description=description,
        path=path,
        root=root,
        trigger=header.text("trigger").strip(),
        tags=header.items("tags"),
    )
