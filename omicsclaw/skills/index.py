"""The loaded skill set: its prompt-facing index and its deferred bodies.

A :class:`SkillIndex` holds metadata only. Descriptions go into the
system prompt once per turn; bodies are read from disk when the model
asks for one by name.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .frontmatter import parse_frontmatter
from .skill import Skill

__all__ = [
    "SkillIndex",
    "SkillNotFound",
    "SkipReason",
    "SkippedSkill",
]


class SkipReason(StrEnum):
    """Why one ``SKILL.md`` was found but not indexed."""

    UNREADABLE = "unreadable"
    """The file, or a directory on the way to it, could not be read."""

    NO_FRONTMATTER = "no_frontmatter"
    """No ``---`` delimiters, so there is no metadata to index by."""

    MISSING_NAME = "missing_name"
    """Header present, ``name:`` absent or empty."""

    MISSING_DESCRIPTION = "missing_description"
    """Header present, ``description:`` absent or empty."""

    DUPLICATE_NAME = "duplicate_name"
    """Another skill already claimed the name; the first one keeps it."""


@dataclass(frozen=True, slots=True)
class SkippedSkill:
    """One ``SKILL.md`` that was found and not indexed."""

    path: Path
    reason: SkipReason
    detail: str = ""
    """Free text: the OS error, or the path that already holds the name."""


class SkillNotFound(LookupError):
    """No skill by that name.

    The message is written to be read by a model: the closest known
    names, and the size of the index the rest are listed in.
    """

    def __init__(self, name: str, suggestions: tuple[str, ...], total: int) -> None:
        self.name = name
        self.suggestions = suggestions
        self.total = total
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        super().__init__(
            f"no skill named {name!r}.{hint} "
            f"The skill index in the system prompt lists all {total}."
        )


@dataclass(frozen=True, slots=True)
class SkillIndex:
    """Every skill one scan indexed, plus what it refused and why.

    Immutable and constructible directly, so a test or a surface can
    build one from hand-made :class:`~omicsclaw.skills.skill.Skill`
    values without a filesystem;
    :func:`~omicsclaw.skills.loader.load_skills` is the ordinary way to
    get one.
    """

    skills: tuple[Skill, ...] = ()
    """Ordered by :attr:`~omicsclaw.skills.skill.Skill.relative_path`, so
    the rendered index is byte-identical across machines."""

    skipped: tuple[SkippedSkill, ...] = ()
    """What was found and not indexed. Empty is the healthy case."""

    root: Path = field(default_factory=Path)
    """The directory that was scanned."""

    encoding: str = "utf-8"
    """Used for the deferred body reads, matching the header read."""

    def __len__(self) -> int:
        return len(self.skills)

    @property
    def is_empty(self) -> bool:
        """Whether the index holds no skills."""
        return not self.skills

    def names(self) -> tuple[str, ...]:
        """Every loaded skill name, in index order."""
        return tuple(skill.name for skill in self.skills)

    def get(self, name: str) -> Skill | None:
        """Return the skill called *name*, or ``None`` if there is none."""
        for skill in self.skills:
            if skill.name == name:
                return skill
        return None

    def search(self, query: str) -> tuple[Skill, ...]:
        """Every skill whose name, domain, tags or triggers match *query*.

        Case-insensitive substring matching, in index order, with each
        skill answering at most once. A blank *query* matches everything,
        so ``/skills`` and ``/skills spatial`` share one code path.

        This is a *discovery* helper for a human at a prompt. The model
        routes from the descriptions in the system prompt, and a trigger
        keyword appearing in a turn does not load anything by itself.
        """
        wanted = query.strip().lower()
        if not wanted:
            return self.skills
        return tuple(
            skill for skill in self.skills if _matches(skill, wanted)
        )

    def by_domain(self) -> tuple[tuple[str, tuple[Skill, ...]], ...]:
        """Group the skills by :attr:`~omicsclaw.skills.skill.Skill.domain`.

        Domains come in first-appearance order and skills keep index
        order within each. Skills with no domain group under ``""``.
        """
        grouped: dict[str, list[Skill]] = {}
        for skill in self.skills:
            grouped.setdefault(skill.domain, []).append(skill)
        return tuple((key, tuple(value)) for key, value in grouped.items())

    def summary(self) -> str:
        """Render the index as one ``- name: description`` line per skill.

        Returns ``""`` for an empty index, which lets the caller drop the
        whole section instead of rendering a heading over nothing.

        Full descriptions: about 8.5k tokens over this repository's 96
        skills. See :meth:`domain_summary` for the cheaper rendering.
        """
        return "".join(f"- {s.name}: {s.description}\n" for s in self.skills)

    def domain_summary(self) -> str:
        """Render the index as one ``- domain (N skills): names`` line each.

        Drops the descriptions: about 600 tokens over this repository's
        96 skills, at the cost of routing on names alone.
        """
        lines = []
        for domain, skills in self.by_domain():
            label = domain or "(ungrouped)"
            names = ", ".join(skill.name for skill in skills)
            lines.append(f"- {label} ({len(skills)} skills): {names}\n")
        return "".join(lines)

    def prompt_body(self, *, compact: bool = False) -> str:
        """Render the skills block for a system prompt section.

        A sentence naming the ``use_skill`` tool followed by the index —
        :meth:`summary` by default, :meth:`domain_summary` when *compact*.
        Returns ``""`` for an empty index.

        The heading is not included, so the caller owns it::

            Section("skills", "## Available skills", index.prompt_body)

        Keyword-only after ``self``, so the bound method is usable
        directly as a zero-argument section source.
        """
        if self.is_empty:
            return ""
        index = self.domain_summary() if compact else self.summary()
        return (
            "Load a skill's full instructions with the `use_skill` tool "
            "when you need them.\n\n" + index
        )

    def get_full_content(self, name: str) -> str:
        """Read *name*'s instructions from disk and return them.

        The file is read fresh on every call, so a ``SKILL.md`` edited
        mid-run is picked up. Frontmatter is removed and surrounding
        whitespace stripped.

        :raises SkillNotFound: *name* is not in the index.
        :raises OSError: the file is in the index but cannot be read.
        :raises UnicodeDecodeError: it can be read but is no longer valid
            in :attr:`encoding`. Not an :exc:`OSError` — it is a
            :exc:`ValueError` — so a caller guarding the read has to name
            both, as :func:`~omicsclaw.skills.loader.load_skills` does.
        """
        skill = self.get(name)
        if skill is None:
            raise SkillNotFound(name, self.close_names(name), len(self.skills))
        text = skill.path.read_text(encoding=self.encoding)
        return parse_frontmatter(text).body.strip()

    def close_names(self, name: str) -> tuple[str, ...]:
        """Up to five indexed names spelled similarly to *name*.

        What :class:`SkillNotFound` offers the model as "did you mean".
        """
        return tuple(difflib.get_close_matches(name, self.names(), n=5, cutoff=0.5))


def _matches(skill: Skill, wanted: str) -> bool:
    """Whether *wanted* occurs in any of *skill*'s searchable fields."""
    haystacks = (skill.name, skill.domain, *skill.tags, *skill.triggers)
    return any(wanted in field.lower() for field in haystacks)
