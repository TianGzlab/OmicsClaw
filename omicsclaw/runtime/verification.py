"""Workspace verification and completion gate primitives."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from omicsclaw.common.manifest import (
    ArtifactRecord,
    PipelineManifest,
    StepRecord,
    VerificationRecord,
    WorkspaceRecord,
    read_manifest,
    save_manifest,
)
from .events import EVENT_VERIFICATION_COMPLETED
from .hook_payloads import VerificationHookPayload
from .hooks import LifecycleHookRuntime

WORKSPACE_KIND_CONVERSATION = "conversation"
WORKSPACE_KIND_ANALYSIS_RUN = "analysis_run"

COMPLETION_STATUS_COMPLETE = "complete"
COMPLETION_STATUS_INCOMPLETE = "incomplete"
COMPLETION_STATUS_FAILED = "failed"
COMPLETION_STATUS_AWAITING_APPROVAL = "awaiting_approval"
COMPLETION_STATUS_PARTIAL = "partial"

ARTIFACT_KIND_FILE = "file"
ARTIFACT_KIND_DIR = "dir"

COMPLETION_REPORT_FILENAME = "completion_report.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ArtifactRequirement:
    """Required artifact contract for a workspace."""

    name: str
    path: str
    kind: str = ARTIFACT_KIND_FILE
    required: bool = True
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_manifest_record(self, *, status: str = "") -> ArtifactRecord:
        return ArtifactRecord(
            name=self.name,
            path=self.path,
            required=self.required,
            kind=self.kind,
            description=self.description,
            status=status,
            metadata=dict(self.metadata),
        )


@dataclass(slots=True)
class ArtifactVerification:
    """Observed verification result for one artifact contract."""

    name: str
    path: str
    kind: str
    required: bool
    present: bool
    resolved_path: str = ""
    description: str = ""
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "required": self.required,
            "present": self.present,
            "resolved_path": self.resolved_path,
            "description": self.description,
            "detail": self.detail,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class CompletionReport:
    """Structured completion report for an isolated workspace run."""

    workspace_kind: str
    workspace_purpose: str
    workspace_root: str
    status: str
    completed: bool
    artifacts: list[ArtifactVerification] = field(default_factory=list)
    generated_at: str = field(default_factory=_utcnow_iso)
    manifest_path: str = ""
    report_path: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def missing_required_artifacts(self) -> list[str]:
        return [
            artifact.path
            for artifact in self.artifacts
            if artifact.required and not artifact.present
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_kind": self.workspace_kind,
            "workspace_purpose": self.workspace_purpose,
            "workspace_root": self.workspace_root,
            "status": self.status,
            "completed": self.completed,
            "generated_at": self.generated_at,
            "manifest_path": self.manifest_path,
            "report_path": self.report_path,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "missing_required_artifacts": self.missing_required_artifacts(),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }

    def to_verification_record(self) -> VerificationRecord:
        return VerificationRecord(
            status=self.status,
            completed=self.completed,
            report_path=self.report_path,
            missing_required_artifacts=self.missing_required_artifacts(),
            warnings=list(self.warnings),
            metadata={
                "workspace_kind": self.workspace_kind,
                "workspace_purpose": self.workspace_purpose,
                "errors": list(self.errors),
                "artifact_checks": [artifact.to_dict() for artifact in self.artifacts],
                **dict(self.metadata),
            },
        )


def verify_workspace_artifacts(
    workspace: str | Path,
    requirements: Iterable[ArtifactRequirement],
) -> list[ArtifactVerification]:
    """Check artifact presence inside a workspace."""
    root = Path(workspace)
    results: list[ArtifactVerification] = []
    for requirement in requirements:
        target = root / requirement.path
        if requirement.kind == ARTIFACT_KIND_DIR:
            present = target.exists() and target.is_dir()
        else:
            present = target.exists() and target.is_file()
        results.append(
            ArtifactVerification(
                name=requirement.name,
                path=requirement.path,
                kind=requirement.kind,
                required=requirement.required,
                present=present,
                resolved_path=str(target) if present else "",
                description=requirement.description,
                detail="" if present else "artifact missing",
                metadata=dict(requirement.metadata),
            )
        )
    return results


def build_completion_report(
    workspace: str | Path,
    *,
    workspace_kind: str,
    workspace_purpose: str,
    requirements: Iterable[ArtifactRequirement],
    status: str = "",
    warnings: Iterable[str] | None = None,
    errors: Iterable[str] | None = None,
    manifest_path: str = "",
    metadata: Mapping[str, Any] | None = None,
    completed: bool | None = None,
) -> CompletionReport:
    """Build a structured completion report from workspace artifact checks."""
    root = Path(workspace)
    artifact_checks = verify_workspace_artifacts(root, requirements)
    warning_list = [str(item) for item in (warnings or []) if str(item).strip()]
    error_list = [str(item) for item in (errors or []) if str(item).strip()]
    missing_required = [
        artifact.path for artifact in artifact_checks if artifact.required and not artifact.present
    ]

    if not status:
        if error_list:
            status = COMPLETION_STATUS_FAILED
        elif missing_required:
            status = COMPLETION_STATUS_INCOMPLETE
        else:
            status = COMPLETION_STATUS_COMPLETE

    if completed is None:
        completed = status == COMPLETION_STATUS_COMPLETE and not missing_required and not error_list

    return CompletionReport(
        workspace_kind=workspace_kind,
        workspace_purpose=workspace_purpose,
        workspace_root=str(root),
        status=status,
        completed=bool(completed),
        artifacts=artifact_checks,
        manifest_path=manifest_path,
        warnings=warning_list,
        errors=error_list,
        metadata=dict(metadata or {}),
    )


def write_completion_report(
    workspace: str | Path,
    report: CompletionReport,
    *,
    filename: str = COMPLETION_REPORT_FILENAME,
    hook_runtime: LifecycleHookRuntime | None = None,
    hook_context: Mapping[str, Any] | None = None,
) -> Path:
    """Persist ``CompletionReport`` as JSON inside the workspace."""
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)
    path = root / filename
    report.report_path = str(path)
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    if hook_runtime is not None:
        hook_runtime.emit(
            EVENT_VERIFICATION_COMPLETED,
            VerificationHookPayload(
                workspace=report.workspace_root,
                workspace_kind=report.workspace_kind,
                workspace_purpose=report.workspace_purpose,
                status=report.status,
                completed=report.completed,
                missing_required_artifacts=tuple(report.missing_required_artifacts()),
                warnings=tuple(report.warnings),
                errors=tuple(report.errors),
                report_path=report.report_path,
                manifest_path=report.manifest_path,
            ),
            context=dict(hook_context or {}),
        )
    return path


def update_workspace_manifest(
    workspace: str | Path,
    *,
    workspace_kind: str,
    workspace_purpose: str,
    requirements: Iterable[ArtifactRequirement],
    completion_report: CompletionReport | None = None,
    step: StepRecord | None = None,
    isolation_mode: str = "",
    metadata: Mapping[str, Any] | None = None,
    append_step: bool = True,
) -> Path:
    """Create or update the workspace manifest with verification contract data."""
    root = Path(workspace)
    manifest = read_manifest(root) or PipelineManifest()
    if step is not None and (append_step or not manifest.steps):
        manifest.append(step)

    manifest.workspace = WorkspaceRecord(
        kind=workspace_kind,
        purpose=workspace_purpose,
        root=str(root),
        isolation_mode=isolation_mode,
        metadata=dict(metadata or {}),
    )
    manifest.required_artifacts = [
        requirement.to_manifest_record(
            status="present"
            if (root / requirement.path).exists()
            else "missing"
        )
        for requirement in requirements
    ]
    if metadata:
        manifest.metadata.update(dict(metadata))
    if completion_report is not None:
        manifest.verification = completion_report.to_verification_record()
    return save_manifest(root, manifest)


def format_completion_summary(report: CompletionReport) -> str:
    """Human-readable summary for chat/tool surfaces."""
    lines = [
        f"Status: {report.status}",
        f"Completed: {report.completed}",
    ]
    missing = report.missing_required_artifacts()
    if missing:
        lines.append("Missing required artifacts:")
        lines.extend(f"- {item}" for item in missing)
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in report.warnings)
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"- {item}" for item in report.errors)
    return "\n".join(lines)


def format_completion_mapping_summary(
    payload: Mapping[str, Any] | None,
) -> str:
    """Human-readable summary for completion payload mappings."""
    if not payload:
        return ""

    status = str(payload.get("status", "") or "").strip()
    completed_raw = payload.get("completed", None)
    missing = [
        str(item).strip()
        for item in payload.get("missing_required_artifacts", []) or []
        if str(item).strip()
    ]
    warnings = [
        str(item).strip()
        for item in payload.get("warnings", []) or []
        if str(item).strip()
    ]
    errors = [
        str(item).strip()
        for item in payload.get("errors", []) or []
        if str(item).strip()
    ]

    lines: list[str] = []
    if status:
        lines.append(f"Status: {status}")
    if completed_raw is not None:
        lines.append(f"Completed: {bool(completed_raw)}")
    if missing:
        lines.append("Missing required artifacts:")
        lines.extend(f"- {item}" for item in missing)
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in warnings)
    if errors:
        lines.append("Errors:")
        lines.extend(f"- {item}" for item in errors)
    return "\n".join(lines)


@contextmanager
def isolated_workspace(
    staging_root: str | Path,
    *,
    prefix: str,
    keep_on_error: bool = False,
) -> Iterator[Path]:
    """Create an isolated temporary workspace below a stable staging root."""
    base = Path(staging_root)
    base.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"{prefix}-", dir=base))
    try:
        yield temp_dir
    except Exception:
        if keep_on_error:
            raise
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    else:
        shutil.rmtree(temp_dir, ignore_errors=True)


__all__ = [
    "ARTIFACT_KIND_DIR",
    "ARTIFACT_KIND_FILE",
    "COMPLETION_REPORT_FILENAME",
    "COMPLETION_STATUS_AWAITING_APPROVAL",
    "COMPLETION_STATUS_COMPLETE",
    "COMPLETION_STATUS_FAILED",
    "COMPLETION_STATUS_INCOMPLETE",
    "COMPLETION_STATUS_PARTIAL",
    "WORKSPACE_KIND_ANALYSIS_RUN",
    "WORKSPACE_KIND_CONVERSATION",
    "ArtifactRequirement",
    "ArtifactVerification",
    "CompletionReport",
    "build_completion_report",
    "format_completion_mapping_summary",
    "format_completion_summary",
    "isolated_workspace",
    "update_workspace_manifest",
    "verify_workspace_artifacts",
    "write_completion_report",
]
