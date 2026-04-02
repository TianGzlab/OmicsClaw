"""Lightweight structural validation for research pipeline plan.md files."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omicsclaw.common.checksums import sha256_file


PLAN_VALIDATION_METADATA_KEY = "plan_validation"


@dataclass(slots=True)
class PlanValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected_sections: list[str] = field(default_factory=list)
    stage_count: int = 0


@dataclass(slots=True)
class PlanValidationSnapshot:
    path: str
    size_bytes: int
    mtime_ns: int
    sha256: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected_sections: list[str] = field(default_factory=list)
    stage_count: int = 0

    def to_result(self) -> PlanValidationResult:
        return PlanValidationResult(
            valid=self.valid,
            errors=list(self.errors),
            warnings=list(self.warnings),
            detected_sections=list(self.detected_sections),
            stage_count=self.stage_count,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "detected_sections": list(self.detected_sections),
            "stage_count": self.stage_count,
        }

    def matches_file(self, path: str | Path) -> bool:
        plan_path = Path(path).expanduser().resolve()
        if not plan_path.exists():
            return False
        stat = plan_path.stat()
        return (
            self.path == str(plan_path)
            and self.size_bytes == stat.st_size
            and self.mtime_ns == stat.st_mtime_ns
        )

    @classmethod
    def from_result(
        cls,
        path: str | Path,
        result: PlanValidationResult,
    ) -> "PlanValidationSnapshot":
        plan_path = Path(path).expanduser().resolve()
        stat = plan_path.stat()
        return cls(
            path=str(plan_path),
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            sha256=sha256_file(plan_path),
            valid=result.valid,
            errors=list(result.errors),
            warnings=list(result.warnings),
            detected_sections=list(result.detected_sections),
            stage_count=result.stage_count,
        )

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
    ) -> "PlanValidationSnapshot | None":
        if not isinstance(data, Mapping):
            return None
        path = str(data.get("path", "")).strip()
        if not path:
            return None
        try:
            return cls(
                path=path,
                size_bytes=int(data.get("size_bytes", 0)),
                mtime_ns=int(data.get("mtime_ns", 0)),
                sha256=str(data.get("sha256", "")).strip(),
                valid=bool(data.get("valid", False)),
                errors=[str(item) for item in data.get("errors", [])],
                warnings=[str(item) for item in data.get("warnings", [])],
                detected_sections=[
                    str(item) for item in data.get("detected_sections", [])
                ],
                stage_count=int(data.get("stage_count", 0)),
            )
        except (TypeError, ValueError):
            return None


_SECTION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "research_context_scope",
        (
            "research context",
            "context & scope",
            "context and scope",
            "scope",
        ),
    ),
    (
        "data_acquisition_strategy",
        (
            "data acquisition strategy",
            "data acquisition",
            "dataset acquisition",
            "data strategy",
        ),
    ),
    (
        "analysis_stages",
        (
            "analysis stages",
            "experimental stages",
            "analysis plan",
        ),
    ),
    (
        "dependencies",
        (
            "dependencies",
            "packages",
            "compute requirements",
            "resource dependencies",
        ),
    ),
    (
        "iteration_triggers",
        (
            "iteration triggers",
            "iteration criteria",
            "when to iterate",
        ),
    ),
    (
        "evaluation_protocol",
        (
            "evaluation protocol",
            "evaluation plan",
            "metrics, baselines, controls",
            "metrics and baselines",
        ),
    ),
)

_STAGE_PATTERN = re.compile(
    r"(?im)^(?:#{1,6}\s*stage\s+\d+|\s*\d+[\.\)]\s*stage\b|\s*[-*]\s*stage\s+\d+)"
)


def _contains_any(text: str, options: tuple[str, ...]) -> bool:
    return any(option in text for option in options)


def _has_explicit_qc_guidance(text: str) -> bool:
    return any(
        re.search(pattern, text)
        for pattern in (
            r"(?im)^\s*[-*]?\s*parameters?\s*[:\-]",
            r"(?im)^\s*[-*]?\s*(?:qc|filter(?:ing)?)\s*(?:parameters?|thresholds?|strategy)?\s*[:\-]",
            r"(?im)\b(min_genes|min_cells|max_mt_pct|max_pct_mt|min_counts|max_counts|n_top_hvg|mad|thresholds?)\b",
        )
    )


def validate_plan_text(text: str) -> PlanValidationResult:
    content = text.strip()
    if not content:
        return PlanValidationResult(valid=False, errors=["plan.md is empty."])

    lowered = content.lower()
    detected_sections: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    for section_name, options in _SECTION_RULES:
        if _contains_any(lowered, options):
            detected_sections.append(section_name)
        else:
            errors.append(
                f"Missing required section: {section_name.replace('_', ' ')}."
            )

    stage_count = len(_STAGE_PATTERN.findall(content))
    if stage_count == 0:
        goal_count = len(re.findall(r"(?im)^\s*[-*]?\s*goal\s*[:\-]", content))
        stage_count = goal_count

    if stage_count == 0:
        errors.append("No analysis stages were detected.")

    for label, patterns in (
        ("goal", (r"(?im)\bgoal\b",)),
        ("OmicsClaw skill selection", (r"(?im)\bskills?\b", r"(?im)\bomicsclaw\b")),
        ("success signals", (r"(?im)\bsuccess signals?\b",)),
        ("expected artifacts", (r"(?im)\bexpected artifacts?\b", r"(?im)\bartifacts?\b")),
    ):
        if not any(re.search(pattern, content) for pattern in patterns):
            errors.append(f"Missing stage detail: {label}.")

    if not _has_explicit_qc_guidance(content):
        warnings.append(
            "No explicit QC/parameter guidance detected; review thresholds before approval."
        )

    if not re.search(r"(?im)\b(baseline|control|comparison)\b", content):
        warnings.append(
            "No baseline/control language detected; evaluation protocol may be underspecified."
        )

    if not re.search(r"(?im)\b(fallback|alternative|if .* fails)\b", content):
        warnings.append(
            "No fallback strategy detected for failed stages."
        )

    return PlanValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        detected_sections=detected_sections,
        stage_count=stage_count,
    )


def validate_plan_file(path: str | Path) -> PlanValidationResult:
    plan_path = Path(path)
    if not plan_path.exists():
        return PlanValidationResult(
            valid=False,
            errors=[f"plan.md not found: {plan_path}"],
        )
    return validate_plan_text(plan_path.read_text(encoding="utf-8"))


def capture_plan_validation_snapshot(
    path: str | Path,
) -> PlanValidationSnapshot | None:
    plan_path = Path(path).expanduser().resolve()
    if not plan_path.exists():
        return None
    result = validate_plan_file(plan_path)
    return PlanValidationSnapshot.from_result(plan_path, result)


def load_plan_validation_snapshot(
    data: PlanValidationSnapshot | Mapping[str, Any] | None,
) -> PlanValidationSnapshot | None:
    if isinstance(data, PlanValidationSnapshot):
        return data
    if data is None:
        return None
    return PlanValidationSnapshot.from_dict(data)


def resolve_plan_validation_snapshot(
    path: str | Path,
    cached_snapshot: PlanValidationSnapshot | Mapping[str, Any] | None = None,
) -> PlanValidationSnapshot | None:
    snapshot = load_plan_validation_snapshot(cached_snapshot)
    if snapshot is not None and snapshot.matches_file(path):
        return snapshot
    return capture_plan_validation_snapshot(path)


def resolve_plan_validation_result(
    path: str | Path,
    cached_snapshot: PlanValidationSnapshot | Mapping[str, Any] | None = None,
) -> PlanValidationResult:
    snapshot = resolve_plan_validation_snapshot(path, cached_snapshot)
    if snapshot is not None:
        return snapshot.to_result()
    return validate_plan_file(path)
