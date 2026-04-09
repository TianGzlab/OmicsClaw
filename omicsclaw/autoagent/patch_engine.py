"""Patch engine — parse, apply, and revert code patches.

The Meta-Agent outputs structured JSON with ``old_code``/``new_code``
hunks.  The patch engine validates these against the editable surface,
applies them with backup, and can revert on failure.

Patch lifecycle:
1. Parse LLM JSON response → PatchPlan
2. Validate all target files are within editable surface
3. Backup target files
4. Apply hunks via exact string replacement
5. If trial passes → keep changes
6. If trial fails → revert from backup
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omicsclaw.autoagent.edit_surface import EditSurface, resolve_path_within_root

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Hunk:
    """A single code replacement within one file."""

    old_code: str
    new_code: str


@dataclass
class FileDiff:
    """All hunks for one file."""

    file: str  # relative path
    hunks: list[Hunk] = field(default_factory=list)


@dataclass
class PatchPlan:
    """Complete patch output from the Meta-Agent."""

    target_files: list[str] = field(default_factory=list)
    description: str = ""
    expected_improvements: list[str] = field(default_factory=list)
    rollback_conditions: list[str] = field(default_factory=list)
    diffs: list[FileDiff] = field(default_factory=list)
    reasoning: str = ""
    converged: bool = False

    @property
    def n_hunks(self) -> int:
        return sum(len(d.hunks) for d in self.diffs)

    @property
    def diff_summary(self) -> str:
        """One-line summary of the patch size."""
        files = len(self.diffs)
        hunks = self.n_hunks
        return f"{files} file(s), {hunks} hunk(s)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_files": self.target_files,
            "description": self.description,
            "expected_improvements": self.expected_improvements,
            "rollback_conditions": self.rollback_conditions,
            "diffs": [
                {
                    "file": d.file,
                    "hunks": [{"old_code": h.old_code, "new_code": h.new_code}
                              for h in d.hunks],
                }
                for d in self.diffs
            ],
            "reasoning": self.reasoning,
            "converged": self.converged,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_patch_response(text: str) -> PatchPlan:
    """Parse the Meta-Agent's JSON response into a PatchPlan.

    Handles markdown code fences and extracts the outermost JSON object.
    """
    text = text.strip()

    # Strip markdown fences
    fence_match = re.search(
        r"```(?:json|JSON)?\s*\n(.*?)```", text, re.DOTALL
    )
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse
    data = _parse_json(text)
    if data is None:
        raise ValueError(f"Could not parse LLM response as JSON: {text[:200]}")

    # Check for convergence signal
    if data.get("converged"):
        return PatchPlan(
            converged=True,
            reasoning=data.get("reasoning", "LLM indicated convergence"),
        )

    # Parse patch plan
    plan_data = data.get("patch_plan", {})
    diffs_data = data.get("diffs", [])

    diffs: list[FileDiff] = []
    for diff_entry in diffs_data:
        file_path = diff_entry.get("file", "")
        hunks: list[Hunk] = []
        for hunk_data in diff_entry.get("hunks", []):
            old_code = hunk_data.get("old_code", "")
            new_code = hunk_data.get("new_code", "")
            if old_code and old_code != new_code:
                hunks.append(Hunk(old_code=old_code, new_code=new_code))
        if hunks:
            diffs.append(FileDiff(file=file_path, hunks=hunks))

    return PatchPlan(
        target_files=plan_data.get("target_files", []),
        description=plan_data.get("description", ""),
        expected_improvements=plan_data.get("expected_improvements", []),
        rollback_conditions=plan_data.get("rollback_conditions", []),
        diffs=diffs,
        reasoning=data.get("reasoning", ""),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of validating a patch against the editable surface."""

    valid: bool
    errors: list[str] = field(default_factory=list)

    @property
    def error_summary(self) -> str:
        return "; ".join(self.errors) if self.errors else "OK"


def validate_patch(
    patch: PatchPlan,
    surface: EditSurface,
) -> ValidationResult:
    """Validate that a patch only touches editable files and hunks match."""
    errors: list[str] = []

    if not patch.diffs:
        errors.append("Patch contains no diffs.")
        return ValidationResult(valid=False, errors=errors)

    for diff in patch.diffs:
        try:
            surface_path = surface.resolve_editable_path(diff.file)
        except (PermissionError, ValueError) as exc:
            errors.append(str(exc))
            continue

        if not surface_path.abs_path.exists():
            errors.append(
                f"File {surface_path.rel_path!r} does not exist on disk."
            )
            continue

        try:
            content = surface_path.abs_path.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"Cannot read {surface_path.rel_path!r}: {exc}")
            continue

        for i, hunk in enumerate(diff.hunks):
            if hunk.old_code not in content:
                # Try with normalized whitespace
                normalized_content = _normalize_ws(content)
                normalized_old = _normalize_ws(hunk.old_code)
                if normalized_old not in normalized_content:
                    errors.append(
                        f"{surface_path.rel_path} hunk #{i}: "
                        "old_code not found in file "
                        f"(first 80 chars: {hunk.old_code[:80]!r})"
                    )

    return ValidationResult(valid=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


def apply_patch(
    patch: PatchPlan,
    surface: EditSurface,
) -> list[str]:
    """Apply a validated patch to files on disk.

    Returns a list of files that were modified.

    Raises
    ------
    PermissionError
        If a patch targets a file outside the editable surface.
    ValueError
        If a path escapes the project root or a hunk cannot be found.
    """
    modified: list[str] = []

    for diff in patch.diffs:
        surface_path = surface.resolve_editable_path(diff.file)
        file_path = surface_path.abs_path
        content = file_path.read_text(encoding="utf-8")
        original = content

        for hunk in diff.hunks:
            if hunk.old_code in content:
                occurrence_count = content.count(hunk.old_code)
                if occurrence_count > 1:
                    raise ValueError(
                        f"Ambiguous hunk: old_code appears {occurrence_count} "
                        f"times in {surface_path.rel_path}. Provide more "
                        f"surrounding context in old_code to disambiguate. "
                        f"(first 80 chars: {hunk.old_code[:80]!r})"
                    )
                content = content.replace(hunk.old_code, hunk.new_code, 1)
            else:
                # Try whitespace-normalized matching
                match_pos = _find_normalized(content, hunk.old_code)
                if match_pos is not None:
                    start, end = match_pos
                    content = content[:start] + hunk.new_code + content[end:]
                else:
                    raise ValueError(
                        f"Hunk old_code not found in {surface_path.rel_path}: "
                        f"{hunk.old_code[:80]!r}"
                    )

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            modified.append(surface_path.rel_path)

    return modified


def revert_files(
    files: list[str],
    project_root: Path,
    backup_dir: Path,
) -> None:
    """Revert files from backup copies."""
    for rel_path in files:
        resolved = resolve_path_within_root(project_root, rel_path)
        backup = resolve_path_within_root(backup_dir, resolved.rel_path).abs_path
        target = resolved.abs_path
        if backup.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(backup), str(target))
            logger.info("Reverted %s from backup", resolved.rel_path)
        else:
            logger.warning("No backup found for %s", resolved.rel_path)


def backup_files(
    files: list[str],
    project_root: Path,
    backup_dir: Path,
) -> None:
    """Create backup copies of files before patching."""
    for rel_path in files:
        resolved = resolve_path_within_root(project_root, rel_path)
        src = resolved.abs_path
        dst = resolve_path_within_root(backup_dir, resolved.rel_path).abs_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(str(src), str(dst))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_json(text: str) -> dict[str, Any] | None:
    """Parse JSON, handling edge cases.

    Delegates to the shared :func:`~omicsclaw.autoagent.llm_client.parse_json_from_llm`
    implementation.
    """
    from omicsclaw.autoagent.llm_client import parse_json_from_llm

    return parse_json_from_llm(text)


def _normalize_ws(s: str) -> str:
    """Normalize whitespace for fuzzy matching."""
    return " ".join(s.split())


def _find_normalized(content: str, old_code: str) -> tuple[int, int] | None:
    """Find old_code in content using whitespace-normalized matching.

    Returns (start, end) positions in the original content, or None.
    """
    # Build a mapping from normalized positions to original positions
    normalized_old = _normalize_ws(old_code)
    if not normalized_old:
        return None

    lines = content.splitlines(keepends=True)
    # Try line-by-line normalized matching
    old_lines = old_code.strip().splitlines()
    if not old_lines:
        return None

    first_norm = _normalize_ws(old_lines[0])
    for i, line in enumerate(lines):
        if first_norm in _normalize_ws(line):
            # Try matching subsequent lines
            end_line = i + len(old_lines)
            if end_line > len(lines):
                continue
            candidate = "".join(lines[i:end_line])
            if _normalize_ws(candidate) == _normalize_ws(old_code):
                start_pos = sum(len(l) for l in lines[:i])
                end_pos = start_pos + len(candidate)
                return start_pos, end_pos

    return None
