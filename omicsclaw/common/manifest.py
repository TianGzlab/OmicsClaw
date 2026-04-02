"""Pipeline manifest and workspace ledger helpers.

Each skill step produces a ``manifest.json`` in its output directory that
records what ran, with what parameters, and which upstream steps preceded it.
Phase 6 extends the same file into a lightweight workspace ledger so complex
flows can also persist workspace kind, required artifacts, and verification
state without breaking older skill manifests.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 2


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StepRecord:
    """Record of a single skill execution step."""

    skill: str
    version: str
    input_file: str = ""
    input_checksum: str = ""
    output_file: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    completed_at: str = ""

    def __post_init__(self):
        if not self.completed_at:
            self.completed_at = _utcnow_iso()


@dataclass
class WorkspaceRecord:
    """Metadata describing the workspace that produced this manifest."""

    kind: str = ""
    purpose: str = ""
    root: str = ""
    isolation_mode: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _utcnow_iso()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceRecord":
        return cls(
            kind=str(data.get("kind", "")).strip(),
            purpose=str(data.get("purpose", "")).strip(),
            root=str(data.get("root", "")).strip(),
            isolation_mode=str(data.get("isolation_mode", "")).strip(),
            created_at=str(data.get("created_at", "")).strip(),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ArtifactRecord:
    """Required or observed artifact contract for a workspace."""

    name: str
    path: str
    required: bool = True
    kind: str = "file"
    description: str = ""
    status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRecord":
        return cls(
            name=str(data.get("name", "")).strip(),
            path=str(data.get("path", "")).strip(),
            required=bool(data.get("required", True)),
            kind=str(data.get("kind", "file")).strip() or "file",
            description=str(data.get("description", "")).strip(),
            status=str(data.get("status", "")).strip(),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class VerificationRecord:
    """Serialized verification result for a workspace completion gate."""

    status: str = ""
    completed: bool = False
    report_path: str = ""
    verified_at: str = ""
    missing_required_artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.verified_at:
            self.verified_at = _utcnow_iso()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationRecord":
        return cls(
            status=str(data.get("status", "")).strip(),
            completed=bool(data.get("completed", False)),
            report_path=str(data.get("report_path", "")).strip(),
            verified_at=str(data.get("verified_at", "")).strip(),
            missing_required_artifacts=[
                str(item) for item in data.get("missing_required_artifacts", [])
            ],
            warnings=[str(item) for item in data.get("warnings", [])],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PipelineManifest:
    """Ordered execution history for a pipeline run."""

    steps: list[StepRecord] = field(default_factory=list)
    schema_version: int = MANIFEST_SCHEMA_VERSION
    workspace: WorkspaceRecord | None = None
    required_artifacts: list[ArtifactRecord] = field(default_factory=list)
    verification: VerificationRecord | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def append(self, record: StepRecord) -> None:
        """Add a new step to the execution history."""
        self.steps.append(record)

    def upstream_skills(self) -> list[str]:
        """Return the ordered list of skill names that have been executed."""
        return [s.skill for s in self.steps]

    def has_skill(self, skill_name: str) -> bool:
        """Check whether a specific skill appears in the execution history."""
        return any(s.skill == skill_name for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "steps": [asdict(s) for s in self.steps],
        }
        if self.workspace is not None:
            data["workspace"] = asdict(self.workspace)
        if self.required_artifacts:
            data["required_artifacts"] = [asdict(item) for item in self.required_artifacts]
        if self.verification is not None:
            data["verification"] = asdict(self.verification)
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineManifest:
        steps = [StepRecord(**s) for s in data.get("steps", [])]
        workspace_data = data.get("workspace")
        verification_data = data.get("verification")
        return cls(
            steps=steps,
            schema_version=int(data.get("schema_version", 1) or 1),
            workspace=(
                WorkspaceRecord.from_dict(workspace_data)
                if isinstance(workspace_data, dict)
                else None
            ),
            required_artifacts=[
                ArtifactRecord.from_dict(item)
                for item in data.get("required_artifacts", [])
                if isinstance(item, dict)
            ],
            verification=(
                VerificationRecord.from_dict(verification_data)
                if isinstance(verification_data, dict)
                else None
            ),
            metadata=dict(data.get("metadata", {})),
        )


def save_manifest(output_dir: str | Path, manifest: PipelineManifest) -> Path:
    """Persist a manifest instance to ``manifest.json``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / MANIFEST_FILENAME
    path.write_text(json.dumps(manifest.to_dict(), indent=2, default=str), encoding="utf-8")
    return path


def write_manifest(
    output_dir: str | Path,
    record: StepRecord,
    upstream: PipelineManifest | None = None,
    *,
    workspace: WorkspaceRecord | dict[str, Any] | None = None,
    required_artifacts: list[ArtifactRecord | dict[str, Any]] | None = None,
    verification: VerificationRecord | dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Write manifest.json to the output directory.

    If *upstream* is provided, the new record is appended to it.
    Otherwise a fresh manifest is created with just this step.
    """
    if upstream:
        manifest = PipelineManifest.from_dict(upstream.to_dict())
    else:
        manifest = PipelineManifest()
    manifest.append(record)
    if workspace is not None:
        manifest.workspace = (
            workspace
            if isinstance(workspace, WorkspaceRecord)
            else WorkspaceRecord.from_dict(dict(workspace))
        )
    if required_artifacts is not None:
        manifest.required_artifacts = [
            item if isinstance(item, ArtifactRecord) else ArtifactRecord.from_dict(dict(item))
            for item in required_artifacts
        ]
    if verification is not None:
        manifest.verification = (
            verification
            if isinstance(verification, VerificationRecord)
            else VerificationRecord.from_dict(dict(verification))
        )
    if metadata:
        manifest.metadata.update(dict(metadata))
    return save_manifest(output_dir, manifest)


def read_manifest(directory: str | Path) -> PipelineManifest | None:
    """Read manifest.json from a directory, returning None if absent."""
    path = Path(directory) / MANIFEST_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PipelineManifest.from_dict(data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
