"""Editable surface — bounded regions the Meta-Agent may modify.

AutoAgent's success comes from constraining what the LLM can change.
OmicsClaw is a modular monorepo, so we define explicit levels:

Level 1 (lowest risk):  SKILL.md files
Level 2 (high value):   Skill wrappers + shared _lib
Level 3 (orchestration): Agent config, prompts, context layers
Level 4 (generative):   Auto-generated skill wrappers

Frozen infrastructure (never editable by Meta-Agent):
  runtime/*, routing/*, memory/*, autoagent/api.py, judge.py,
  tool_executor.py, context_assembler.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditLevel:
    """One level of the editable surface hierarchy."""

    level: int
    name: str
    description: str
    patterns: tuple[str, ...]  # glob patterns relative to project root

    def matches(self, rel_path: str) -> bool:
        """Check if a relative path matches this level's patterns."""
        from fnmatch import fnmatch

        return any(fnmatch(rel_path, pat) for pat in self.patterns)


@dataclass(frozen=True)
class SurfacePath:
    """Canonical representation of a project-contained path."""

    rel_path: str
    abs_path: Path


def resolve_path_within_root(
    project_root: Path,
    path: str | Path,
) -> SurfacePath:
    """Resolve a path and ensure it stays within ``project_root``."""
    root = Path(project_root).expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate

    resolved = candidate.resolve(strict=False)
    try:
        rel_path = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"Path {str(path)!r} escapes project root {root}"
        ) from exc

    return SurfacePath(rel_path=rel_path, abs_path=resolved)


@dataclass
class EditSurface:
    """The bounded editable surface for a harness evolution session.

    Constructed with a maximum level (1-4) and an optional explicit
    file list.  Files outside the surface are rejected before patch
    application.
    """

    max_level: int
    project_root: Path
    explicit_files: list[str] = field(default_factory=list)
    _resolved_levels: list[EditLevel] = field(
        default_factory=list, repr=False
    )
    _explicit_file_set: frozenset[str] = field(
        default_factory=frozenset, repr=False
    )

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root).expanduser().resolve()
        self._resolved_levels = [
            lv for lv in ALL_LEVELS if lv.level <= self.max_level
        ]
        self.explicit_files = self._normalize_explicit_files(self.explicit_files)
        self._explicit_file_set = frozenset(self.explicit_files)

    @property
    def active_levels(self) -> list[EditLevel]:
        return list(self._resolved_levels)

    def _normalize_explicit_files(self, files: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for file_path in files:
            surface_path = resolve_path_within_root(self.project_root, file_path)
            if _is_frozen(surface_path.rel_path):
                raise ValueError(
                    f"Explicit file {surface_path.rel_path!r} is frozen and "
                    "cannot be edited."
                )
            if surface_path.rel_path not in seen:
                normalized.append(surface_path.rel_path)
                seen.add(surface_path.rel_path)

        return normalized

    def _is_rel_path_editable(self, rel_path: str) -> bool:
        if _is_frozen(rel_path):
            return False

        if self._explicit_file_set:
            return rel_path in self._explicit_file_set

        return any(lv.matches(rel_path) for lv in self._resolved_levels)

    def resolve_path(self, path: str | Path) -> SurfacePath:
        """Resolve a path against the project root."""
        return resolve_path_within_root(self.project_root, path)

    def resolve_editable_path(self, path: str | Path) -> SurfacePath:
        """Resolve a path and enforce the editable surface boundary."""
        surface_path = self.resolve_path(path)
        rel_path = surface_path.rel_path

        if _is_frozen(rel_path):
            raise PermissionError(
                f"File {rel_path!r} is frozen and cannot be edited."
            )

        if self._explicit_file_set and rel_path not in self._explicit_file_set:
            raise PermissionError(
                f"File {rel_path!r} is outside the explicit editable file list."
            )

        if not self._explicit_file_set and not any(
            lv.matches(rel_path) for lv in self._resolved_levels
        ):
            raise PermissionError(
                f"File {rel_path!r} is outside the editable surface "
                f"(max_level={self.max_level})."
            )

        return surface_path

    def is_editable(self, rel_path: str | Path) -> bool:
        """Check if a file is within the editable surface.

        Parameters
        ----------
        rel_path:
            Path relative to the project root.
        """
        try:
            surface_path = self.resolve_path(rel_path)
        except ValueError:
            return False

        return self._is_rel_path_editable(surface_path.rel_path)

    def is_frozen(self, rel_path: str | Path) -> bool:
        """Check if a file is in the frozen infrastructure list."""
        try:
            surface_path = self.resolve_path(rel_path)
        except ValueError:
            return False
        return _is_frozen(surface_path.rel_path)

    def validate_file_list(self, files: list[str]) -> tuple[list[str], list[str]]:
        """Split a file list into editable and rejected files.

        Returns
        -------
        (editable, rejected)
        """
        editable = []
        rejected = []
        for f in files:
            try:
                editable.append(self.resolve_editable_path(f).rel_path)
            except (PermissionError, ValueError):
                rejected.append(f)
        return editable, rejected

    def file_exists(self, rel_path: str | Path) -> bool:
        """Check if a file exists on disk."""
        try:
            return self.resolve_path(rel_path).abs_path.exists()
        except ValueError:
            return False

    def read_file(self, rel_path: str | Path) -> str:
        """Read a file within the editable surface."""
        path = self.resolve_editable_path(rel_path).abs_path
        return path.read_text(encoding="utf-8")

    def clone_for_project_root(self, project_root: str | Path) -> EditSurface:
        """Clone this surface against another project root."""
        return EditSurface(
            max_level=self.max_level,
            project_root=Path(project_root),
            explicit_files=list(self.explicit_files),
        )

    def describe(self) -> str:
        """Human-readable description of the editable surface."""
        lines = [f"Editable surface (max level {self.max_level}):"]

        if self.explicit_files:
            lines.append("  Explicit file list:")
            for f in self.explicit_files:
                lines.append(f"    - {f}")
        else:
            for lv in self._resolved_levels:
                lines.append(f"  Level {lv.level} ({lv.name}): {lv.description}")
                for pat in lv.patterns:
                    lines.append(f"    - {pat}")

        lines.append("")
        lines.append("  Frozen (never editable):")
        for pat in FROZEN_PATTERNS:
            lines.append(f"    - {pat}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_level": self.max_level,
            "explicit_files": self.explicit_files,
            "active_levels": [
                {"level": lv.level, "name": lv.name, "patterns": list(lv.patterns)}
                for lv in self._resolved_levels
            ],
            "frozen_patterns": list(FROZEN_PATTERNS),
        }


# ---------------------------------------------------------------------------
# Level definitions
# ---------------------------------------------------------------------------

LEVEL_1 = EditLevel(
    level=1,
    name="skill_docs",
    description="SKILL.md files — descriptions, param hints, defaults",
    patterns=(
        "skills/**/SKILL.md",
    ),
)

LEVEL_2 = EditLevel(
    level=2,
    name="skill_code",
    description="Skill wrappers and shared _lib modules",
    patterns=(
        "skills/**/*.py",
        "skills/**/_lib/*.py",
    ),
)

LEVEL_3 = EditLevel(
    level=3,
    name="orchestration",
    description="Agent config, prompts, and context layers",
    patterns=(
        "omicsclaw/agents/config.yaml",
        "omicsclaw/agents/prompts.py",
    ),
)

LEVEL_4 = EditLevel(
    level=4,
    name="generated",
    description="Auto-generated skill wrappers and extensions",
    patterns=(
        "skills/generated/**/*.py",
        "skills/generated/**/SKILL.md",
        "extensions/generated_skills/**/*.py",
        "extensions/generated_skills/**/SKILL.md",
    ),
)

ALL_LEVELS = [LEVEL_1, LEVEL_2, LEVEL_3, LEVEL_4]


# ---------------------------------------------------------------------------
# Frozen patterns — infrastructure that must never be modified
# ---------------------------------------------------------------------------

FROZEN_PATTERNS = (
    "omicsclaw/runtime/*",
    "omicsclaw/routing/*",
    "omicsclaw/memory/*",
    "omicsclaw/autoagent/api.py",
    "omicsclaw/autoagent/judge.py",
    "omicsclaw/autoagent/hard_gates.py",
    "omicsclaw/autoagent/trace.py",
    "omicsclaw/autoagent/evaluator.py",
    "omicsclaw/autoagent/experiment_ledger.py",
    "omicsclaw/autoagent/constants.py",
    "omicsclaw/core/registry.py",
    "omicsclaw/core/skill_protocol.py",
    "omicsclaw/execution/*",
    "omicsclaw/__init__.py",
    "omicsclaw.py",
    "CLAUDE.md",
)


def _is_frozen(rel_path: str) -> bool:
    """Check if a relative path matches any frozen pattern."""
    from fnmatch import fnmatch

    return any(fnmatch(rel_path, pat) for pat in FROZEN_PATTERNS)


# ---------------------------------------------------------------------------
# Factory for MVP
# ---------------------------------------------------------------------------


def build_sc_preprocessing_surface(project_root: Path) -> EditSurface:
    """Build the MVP editable surface for sc-preprocessing evolution.

    Only allows editing the three files identified in the plan:
    - skills/singlecell/scrna/sc-preprocessing/SKILL.md
    - skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py
    - skills/singlecell/_lib/qc.py
    """
    return EditSurface(
        max_level=2,
        project_root=Path(project_root),
        explicit_files=[
            "skills/singlecell/scrna/sc-preprocessing/SKILL.md",
            "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py",
            "skills/singlecell/_lib/qc.py",
        ],
    )


def build_spatial_domains_surface(
    project_root: Path,
    *,
    method: str = "",
) -> EditSurface:
    """Build the bounded surface for spatial-domains evolution.

    ``spatial-domains`` routes most algorithm logic through the shared
    ``skills/spatial/_lib/domains.py`` module rather than a per-method folder.
    Exposing these canonical files prevents the Meta-Agent from hallucinating
    non-existent paths like ``skills/spatial-domains/cellcharter/...``.
    """
    _ = method.strip().lower()
    return EditSurface(
        max_level=2,
        project_root=Path(project_root),
        explicit_files=[
            "skills/spatial/spatial-domains/SKILL.md",
            "skills/spatial/spatial-domains/spatial_domains.py",
            "skills/spatial/_lib/domains.py",
        ],
    )
