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

import ast
from copy import deepcopy
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
    prompt_views: dict[str, str] = field(default_factory=dict, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)
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
        self.prompt_views = self._normalize_prompt_views(self.prompt_views)
        self.metadata = deepcopy(self.metadata)
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

    def _normalize_prompt_views(self, views: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for file_path, content in views.items():
            if not content:
                continue
            surface_path = resolve_path_within_root(self.project_root, file_path)
            normalized[surface_path.rel_path] = str(content)
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

    def has_prompt_view(self, rel_path: str | Path) -> bool:
        try:
            surface_path = self.resolve_editable_path(rel_path)
        except (PermissionError, ValueError):
            return False
        return surface_path.rel_path in self.prompt_views

    def read_prompt_file(self, rel_path: str | Path) -> str:
        """Read a method-focused prompt view when available."""
        surface_path = self.resolve_editable_path(rel_path)
        prompt_view = self.prompt_views.get(surface_path.rel_path)
        if prompt_view is not None:
            return prompt_view
        return surface_path.abs_path.read_text(encoding="utf-8")

    def clone_for_project_root(self, project_root: str | Path) -> EditSurface:
        """Clone this surface against another project root."""
        return EditSurface(
            max_level=self.max_level,
            project_root=Path(project_root),
            explicit_files=list(self.explicit_files),
            prompt_views=dict(self.prompt_views),
            metadata=deepcopy(self.metadata),
        )

    def describe(self) -> str:
        """Human-readable description of the editable surface."""
        lines = [f"Editable surface (max level {self.max_level}):"]
        method_focus = self.metadata.get("method_focus")
        if isinstance(method_focus, dict):
            focus_method = str(method_focus.get("method", "") or "").strip()
            if focus_method:
                lines.append(f"  Method focus: {focus_method}")
                lines.append(
                    "  Shared multi-method files must stay scoped to the target method."
                )
                lines.append("")

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


_SPATIAL_DOMAINS_METHOD_DISPLAY = {
    "leiden": "Leiden",
    "louvain": "Louvain",
    "spagcn": "SpaGCN",
    "stagate": "STAGATE",
    "graphst": "GraphST",
    "banksy": "BANKSY",
    "cellcharter": "CellCharter",
}

_SPATIAL_DOMAINS_METHOD_FUNCTIONS = {
    "leiden": ["identify_domains_leiden"],
    "louvain": ["identify_domains_louvain"],
    "spagcn": ["identify_domains_spagcn"],
    "stagate": ["identify_domains_stagate"],
    "graphst": ["identify_domains_graphst"],
    "banksy": ["identify_domains_banksy"],
    "cellcharter": [
        "identify_domains_cellcharter",
        "_cluster_fixed_k",
        "_cluster_auto_k",
    ],
}

_SPATIAL_DOMAINS_WRAPPER_PATTERNS = {
    "leiden": [
        'parser.add_argument("--method"',
        'parser.add_argument("--resolution"',
        'parser.add_argument("--spatial-weight"',
        '"leiden":',
        'if args.method in ["leiden", "louvain"]',
        "summary = dispatch_method(",
    ],
    "louvain": [
        'parser.add_argument("--method"',
        'parser.add_argument("--resolution"',
        'parser.add_argument("--spatial-weight"',
        '"louvain":',
        'if args.method in ["leiden", "louvain"]',
        "summary = dispatch_method(",
    ],
    "spagcn": [
        'parser.add_argument("--method"',
        'parser.add_argument("--n-domains"',
        'parser.add_argument("--epochs"',
        "# SpaGCN",
        '"spagcn":',
        'if args.method == "spagcn"',
        "summary = dispatch_method(",
    ],
    "stagate": [
        'parser.add_argument("--method"',
        'parser.add_argument("--n-domains"',
        'parser.add_argument("--epochs"',
        "# STAGATE network params",
        '"stagate":',
        'if args.method == "stagate"',
        "summary = dispatch_method(",
    ],
    "graphst": [
        'parser.add_argument("--method"',
        'parser.add_argument("--n-domains"',
        'parser.add_argument("--epochs"',
        "# GraphST",
        '"graphst":',
        'if args.method == "graphst"',
        "summary = dispatch_method(",
    ],
    "banksy": [
        'parser.add_argument("--method"',
        'parser.add_argument("--resolution"',
        'parser.add_argument("--n-domains"',
        "# BANKSY param",
        '"banksy":',
        'if args.method == "banksy"',
        "summary = dispatch_method(",
    ],
    "cellcharter": [
        'parser.add_argument("--method"',
        'parser.add_argument("--n-domains"',
        "# CellCharter params",
        'parser.add_argument("--auto-k"',
        'parser.add_argument("--auto-k-min"',
        'parser.add_argument("--auto-k-max"',
        'parser.add_argument("--n-layers"',
        'parser.add_argument("--use-rep"',
        '"cellcharter":',
        'if args.method == "cellcharter"',
        "summary = dispatch_method(",
    ],
}


def _extract_python_functions(path: Path, function_names: list[str]) -> str:
    if not path.exists():
        return ""

    source = path.read_text(encoding="utf-8")
    try:
        module = ast.parse(source)
    except SyntaxError:
        return ""

    lines = source.splitlines()
    by_name = {
        node.name: node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    blocks: list[str] = []
    for name in function_names:
        node = by_name.get(name)
        if node is None or node.end_lineno is None:
            continue
        block = "\n".join(lines[node.lineno - 1 : node.end_lineno]).rstrip()
        if block:
            blocks.append(block)
    return "\n\n\n".join(blocks)


def _extract_context_windows(
    path: Path,
    patterns: list[str],
    *,
    before: int = 1,
    after: int = 10,
) -> str:
    if not path.exists():
        return ""

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return ""

    ranges: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        if any(pattern in line for pattern in patterns):
            ranges.append((max(0, index - before), min(len(lines), index + after + 1)))

    if not ranges:
        return ""

    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    separator = (
        "\n# ... omitted unrelated sections ...\n\n"
        if path.suffix == ".py"
        else "\n...\n\n"
    )
    excerpts = [
        "\n".join(lines[start:end]).rstrip()
        for start, end in merged
    ]
    return separator.join(excerpt for excerpt in excerpts if excerpt)


def _extract_markdown_section(path: Path, heading: str) -> str:
    if not path.exists():
        return ""

    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index
            break

    if start is None:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("### "):
            end = index
            break
    return "\n".join(lines[start:end]).rstrip()


def _join_nonempty_excerpts(excerpts: list[str], *, python_like: bool = False) -> str:
    items = [excerpt for excerpt in excerpts if excerpt]
    if not items:
        return ""
    separator = (
        "\n# ... omitted unrelated sections ...\n\n"
        if python_like
        else "\n...\n\n"
    )
    return separator.join(items)


def _build_spatial_domains_skill_view(path: Path, method: str) -> str:
    display_name = _SPATIAL_DOMAINS_METHOD_DISPLAY[method]
    return _join_nonempty_excerpts([
        _extract_context_windows(
            path,
            [f"{method}:"],
            before=1,
            after=6,
        ),
        _extract_context_windows(
            path,
            [f"--method {method}"],
            before=1,
            after=2,
        ),
        _extract_markdown_section(path, f"### {display_name}"),
    ])


def _build_spatial_domains_wrapper_view(path: Path, method: str) -> str:
    excerpts: list[str]
    if method == "cellcharter":
        excerpts = [
            _extract_context_windows(path, ["# CellCharter params"], before=0, after=5),
            _extract_context_windows(path, ['"cellcharter":'], before=0, after=1),
            _extract_context_windows(
                path,
                ['if args.method == "cellcharter"'],
                before=0,
                after=8,
            ),
        ]
    elif method == "leiden":
        excerpts = [
            _extract_context_windows(path, ['parser.add_argument("--resolution"'], before=0, after=0),
            _extract_context_windows(path, ['parser.add_argument("--spatial-weight"'], before=0, after=0),
            _extract_context_windows(path, ['"leiden":'], before=0, after=0),
            _extract_context_windows(
                path,
                ['if args.method in ["leiden", "louvain"]'],
                before=0,
                after=1,
            ),
        ]
    else:
        excerpts = [
            _extract_context_windows(
                path,
                _SPATIAL_DOMAINS_WRAPPER_PATTERNS[method],
                before=0,
                after=6,
            ),
        ]
    return _join_nonempty_excerpts(excerpts, python_like=True)


def _build_spatial_domains_prompt_views(
    project_root: Path,
    method: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    normalized_method = str(method or "").strip().lower()
    if normalized_method not in _SPATIAL_DOMAINS_METHOD_FUNCTIONS:
        return {}, {}

    skill_doc = Path(project_root) / "skills" / "spatial" / "spatial-domains" / "SKILL.md"
    wrapper = (
        Path(project_root)
        / "skills"
        / "spatial"
        / "spatial-domains"
        / "spatial_domains.py"
    )
    shared = Path(project_root) / "skills" / "spatial" / "_lib" / "domains.py"

    display_name = _SPATIAL_DOMAINS_METHOD_DISPLAY[normalized_method]
    prompt_views = {
        "skills/spatial/spatial-domains/SKILL.md": _build_spatial_domains_skill_view(
            skill_doc,
            normalized_method,
        ),
        "skills/spatial/spatial-domains/spatial_domains.py": _build_spatial_domains_wrapper_view(
            wrapper,
            normalized_method,
        ),
        "skills/spatial/_lib/domains.py": _extract_python_functions(
            shared,
            _SPATIAL_DOMAINS_METHOD_FUNCTIONS[normalized_method],
        ),
    }

    blocked_methods = [
        method_name
        for method_name in _SPATIAL_DOMAINS_METHOD_FUNCTIONS
        if method_name != normalized_method
    ]
    metadata = {
        "method_focus": {
            "skill_name": "spatial-domains",
            "method": normalized_method,
            "focus_targets": {
                "skills/spatial/spatial-domains/SKILL.md": [
                    f"{display_name} method documentation and usage examples",
                ],
                "skills/spatial/spatial-domains/spatial_domains.py": [
                    "main() method-specific CLI branches and dispatch call",
                ],
                "skills/spatial/_lib/domains.py": list(_SPATIAL_DOMAINS_METHOD_FUNCTIONS[normalized_method]),
            },
            "blocked_functions": {
                "skills/spatial/_lib/domains.py": [
                    f"identify_domains_{method_name}"
                    for method_name in blocked_methods
                ],
            },
        }
    }
    return prompt_views, metadata


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
    prompt_views, metadata = _build_spatial_domains_prompt_views(
        Path(project_root),
        method,
    )
    return EditSurface(
        max_level=2,
        project_root=Path(project_root),
        explicit_files=[
            "skills/spatial/spatial-domains/SKILL.md",
            "skills/spatial/spatial-domains/spatial_domains.py",
            "skills/spatial/_lib/domains.py",
        ],
        prompt_views=prompt_views,
        metadata=metadata,
    )
