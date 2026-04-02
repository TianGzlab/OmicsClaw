"""Normalized runtime result contract for research pipeline runs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlanValidationRuntimeResult:
    available: bool = False
    valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detected_sections: list[str] = field(default_factory=list)
    stage_count: int = 0

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
    ) -> "PlanValidationRuntimeResult":
        if not isinstance(data, Mapping):
            return cls()
        return cls(
            available=bool(data.get("available", True)),
            valid=bool(data.get("valid", False)),
            errors=[str(item) for item in data.get("errors", [])],
            warnings=[str(item) for item in data.get("warnings", [])],
            detected_sections=[str(item) for item in data.get("detected_sections", [])],
            stage_count=int(data.get("stage_count", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "detected_sections": list(self.detected_sections),
            "stage_count": self.stage_count,
        }


@dataclass(slots=True)
class PlanRunResult:
    status: str = ""
    awaiting_approval: bool = False
    approved_at: str = ""
    approved_by: str = ""
    approval_notes: str = ""
    validation: PlanValidationRuntimeResult = field(
        default_factory=PlanValidationRuntimeResult
    )

    @classmethod
    def from_payload(
        cls,
        data: Mapping[str, Any] | None,
    ) -> "PlanRunResult":
        if not isinstance(data, Mapping):
            return cls()
        return cls(
            status=str(data.get("status", "")).strip(),
            awaiting_approval=bool(data.get("awaiting_approval", False)),
            approved_at=str(data.get("approved_at", "")).strip(),
            approved_by=str(data.get("approved_by", "")).strip(),
            approval_notes=str(data.get("approval_notes", "")).strip(),
            validation=PlanValidationRuntimeResult.from_mapping(data.get("validation")),
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PlanRunResult":
        nested = data.get("plan")
        if isinstance(nested, Mapping):
            return cls.from_payload(nested)
        has_legacy_validation = any(
            key in data
            for key in (
                "plan_validation_valid",
                "plan_validation_errors",
                "plan_validation_warnings",
            )
        )
        return cls(
            status=str(data.get("plan_status", "")).strip(),
            awaiting_approval=bool(data.get("awaiting_plan_approval", False)),
            validation=PlanValidationRuntimeResult(
                available=has_legacy_validation,
                valid=bool(data.get("plan_validation_valid", False)),
                errors=[str(item) for item in data.get("plan_validation_errors", [])],
                warnings=[
                    str(item) for item in data.get("plan_validation_warnings", [])
                ],
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "awaiting_approval": self.awaiting_approval,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "approval_notes": self.approval_notes,
            "validation": self.validation.to_dict(),
        }

    def to_legacy_fields(self) -> dict[str, Any]:
        return {
            "awaiting_plan_approval": self.awaiting_approval,
            "plan_status": self.status,
            "plan_validation_valid": self.validation.valid,
            "plan_validation_errors": list(self.validation.errors),
            "plan_validation_warnings": list(self.validation.warnings),
        }


@dataclass(slots=True)
class CompletionRunResult:
    status: str = ""
    completed: bool = False
    report_path: str = ""
    manifest_path: str = ""
    missing_required_artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None,
    ) -> "CompletionRunResult":
        if not isinstance(data, Mapping):
            return cls()
        nested = data.get("completion")
        if isinstance(nested, Mapping):
            return cls(
                status=str(nested.get("status", "")).strip(),
                completed=bool(nested.get("completed", False)),
                report_path=str(nested.get("report_path", "")).strip(),
                manifest_path=str(nested.get("manifest_path", "")).strip(),
                missing_required_artifacts=[
                    str(item) for item in nested.get("missing_required_artifacts", [])
                ],
                warnings=[str(item) for item in nested.get("warnings", [])],
                errors=[str(item) for item in nested.get("errors", [])],
            )
        return cls(
            status=str(data.get("completion_status", "")).strip(),
            completed=bool(data.get("completion_completed", False)),
            report_path=str(data.get("completion_report_path", "")).strip(),
            manifest_path=str(data.get("manifest_path", "")).strip(),
            missing_required_artifacts=[
                str(item) for item in data.get("missing_required_artifacts", [])
            ],
            warnings=[str(item) for item in data.get("completion_warnings", [])],
            errors=[str(item) for item in data.get("completion_errors", [])],
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "completed": self.completed,
            "report_path": self.report_path,
            "manifest_path": self.manifest_path,
            "missing_required_artifacts": list(self.missing_required_artifacts),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass(slots=True)
class PipelineRunResult:
    success: bool
    report_path: str = ""
    review_path: str = ""
    notebook_path: str = ""
    workspace: str = ""
    manifest_path: str = ""
    completion_report_path: str = ""
    intake: dict[str, Any] = field(default_factory=dict)
    completed_stages: list[str] = field(default_factory=list)
    review_iterations: int = 0
    review_cap_reached: bool = False
    plan: PlanRunResult = field(default_factory=PlanRunResult)
    completion: CompletionRunResult = field(default_factory=CompletionRunResult)
    warnings: list[str] = field(default_factory=list)
    final_output: str = ""
    error: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PipelineRunResult":
        return cls(
            success=bool(data.get("success", False)),
            report_path=str(data.get("report_path", "")).strip(),
            review_path=str(data.get("review_path", "")).strip(),
            notebook_path=str(data.get("notebook_path", "")).strip(),
            workspace=str(data.get("workspace", "")).strip(),
            manifest_path=str(data.get("manifest_path", "")).strip(),
            completion_report_path=str(data.get("completion_report_path", "")).strip(),
            intake=dict(data.get("intake", {})),
            completed_stages=[str(item) for item in data.get("completed_stages", [])],
            review_iterations=int(data.get("review_iterations", 0)),
            review_cap_reached=bool(data.get("review_cap_reached", False)),
            plan=PlanRunResult.from_mapping(data),
            completion=CompletionRunResult.from_mapping(data),
            warnings=[str(item) for item in data.get("warnings", [])],
            final_output=str(data.get("final_output", "")),
            error=str(data.get("error", "")),
        )

    def to_dict(self, *, include_legacy_plan_fields: bool = True) -> dict[str, Any]:
        data = {
            "success": self.success,
            "report_path": self.report_path,
            "review_path": self.review_path,
            "notebook_path": self.notebook_path,
            "workspace": self.workspace,
            "manifest_path": self.manifest_path,
            "completion_report_path": self.completion_report_path,
            "intake": dict(self.intake),
            "completed_stages": list(self.completed_stages),
            "review_iterations": self.review_iterations,
            "review_cap_reached": self.review_cap_reached,
            "plan": self.plan.to_payload(),
            "completion": self.completion.to_payload(),
            "warnings": list(self.warnings),
            "final_output": self.final_output,
            "error": self.error,
        }
        if include_legacy_plan_fields:
            data.update(self.plan.to_legacy_fields())
        data.update(
            {
                "completion_status": self.completion.status,
                "completion_completed": self.completion.completed,
                "missing_required_artifacts": list(self.completion.missing_required_artifacts),
                "completion_warnings": list(self.completion.warnings),
                "completion_errors": list(self.completion.errors),
            }
        )
        return data


def normalize_pipeline_result(data: Mapping[str, Any]) -> PipelineRunResult:
    return PipelineRunResult.from_mapping(data)
