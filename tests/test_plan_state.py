from __future__ import annotations

from omicsclaw.agents.plan_state import (
    PLAN_STATE_METADATA_KEY,
    PLAN_STATUS_APPROVED,
    PLAN_STATUS_PENDING_APPROVAL,
    build_plan_result_payload,
    load_plan_state_from_metadata,
    save_plan_state_to_metadata,
    sync_plan_state_metadata,
)
from omicsclaw.agents.pipeline_result import normalize_pipeline_result
from omicsclaw.agents.plan_validation import PLAN_VALIDATION_METADATA_KEY


def test_load_plan_state_from_legacy_metadata_reads_flat_shape():
    metadata = {
        "plan_status": PLAN_STATUS_APPROVED,
        "plan_approved_at": "2026-03-31T00:00:00+00:00",
        "plan_approved_by": "reviewer",
        "plan_approval_notes": "ship it",
        PLAN_VALIDATION_METADATA_KEY: {
            "path": "/tmp/plan.md",
            "size_bytes": 123,
            "mtime_ns": 456,
            "sha256": "abc123",
            "valid": True,
            "errors": [],
            "warnings": [],
            "detected_sections": ["analysis_stages"],
            "stage_count": 1,
        },
    }

    plan_state = load_plan_state_from_metadata(metadata)

    assert plan_state.status == PLAN_STATUS_APPROVED
    assert plan_state.approved_by == "reviewer"
    assert plan_state.approval_notes == "ship it"
    assert plan_state.validation is not None
    assert plan_state.validation.valid is True
    assert plan_state.validation.stage_count == 1


def test_save_plan_state_to_metadata_writes_nested_shape_and_cleans_legacy_keys():
    metadata = {
        "plan_status": PLAN_STATUS_PENDING_APPROVAL,
        PLAN_VALIDATION_METADATA_KEY: {
            "path": "/tmp/plan.md",
            "size_bytes": 123,
            "mtime_ns": 456,
            "sha256": "abc123",
            "valid": False,
            "errors": ["missing section"],
            "warnings": [],
            "detected_sections": [],
            "stage_count": 0,
        },
    }

    plan_state = load_plan_state_from_metadata(metadata)
    save_plan_state_to_metadata(metadata, plan_state)

    assert "plan_status" not in metadata
    assert PLAN_VALIDATION_METADATA_KEY not in metadata
    assert metadata[PLAN_STATE_METADATA_KEY]["status"] == PLAN_STATUS_PENDING_APPROVAL
    assert metadata[PLAN_STATE_METADATA_KEY]["validation"]["errors"] == ["missing section"]


def test_sync_plan_state_metadata_preserves_approval_and_refreshes_validation(tmp_path):
    metadata = {
        PLAN_STATE_METADATA_KEY: {
            "status": PLAN_STATUS_APPROVED,
            "approved_at": "2026-03-31T00:00:00+00:00",
            "approved_by": "reviewer",
            "approval_notes": "looks good",
        }
    }
    (tmp_path / "plan.md").write_text(
        """# Research Context & Scope

Test scope.

## Data Acquisition Strategy

Use the available dataset.

## Analysis Stages

### Stage 1
- Goal: establish a baseline
- OmicsClaw skill(s): spatial-preprocessing
- Parameters: min_genes=20, max_mt_pct=25
- Success signals: QC metrics are stable
- Expected artifacts: qc_report.csv, qc_plot.png
- Fallback: use data-driven thresholds if the first pass fails

## Dependencies

- scanpy

## Iteration Triggers

- Revisit parameters if QC fails

## Evaluation Protocol

- Compare against baseline and control metrics
""",
        encoding="utf-8",
    )

    plan_state = sync_plan_state_metadata(metadata, tmp_path)

    assert plan_state.status == PLAN_STATUS_APPROVED
    assert plan_state.approved_by == "reviewer"
    assert plan_state.validation is not None
    assert plan_state.validation.valid is True
    assert metadata[PLAN_STATE_METADATA_KEY]["validation"]["stage_count"] == 1


def test_build_plan_result_payload_exposes_nested_runtime_shape():
    metadata = {
        PLAN_STATE_METADATA_KEY: {
            "status": PLAN_STATUS_PENDING_APPROVAL,
            "validation": {
                "path": "/tmp/plan.md",
                "size_bytes": 123,
                "mtime_ns": 456,
                "sha256": "abc123",
                "valid": False,
                "errors": ["missing section"],
                "warnings": ["missing fallback"],
                "detected_sections": ["analysis_stages"],
                "stage_count": 1,
            },
        }
    }

    payload = build_plan_result_payload(
        load_plan_state_from_metadata(metadata),
        awaiting_approval=True,
    )

    assert payload["status"] == PLAN_STATUS_PENDING_APPROVAL
    assert payload["awaiting_approval"] is True
    assert payload["validation"]["valid"] is False
    assert payload["validation"]["errors"] == ["missing section"]
    assert payload["validation"]["warnings"] == ["missing fallback"]
    assert payload["validation"]["stage_count"] == 1


def test_normalize_pipeline_result_reads_legacy_plan_fields():
    result = normalize_pipeline_result(
        {
            "success": True,
            "workspace": "/tmp/workspace",
            "awaiting_plan_approval": True,
            "plan_status": PLAN_STATUS_PENDING_APPROVAL,
            "plan_validation_valid": False,
            "plan_validation_errors": ["missing section"],
            "plan_validation_warnings": ["missing fallback"],
        }
    )

    assert result.success is True
    assert result.workspace == "/tmp/workspace"
    assert result.plan.awaiting_approval is True
    assert result.plan.status == PLAN_STATUS_PENDING_APPROVAL
    assert result.plan.validation.valid is False
    assert result.plan.validation.errors == ["missing section"]


def test_normalize_pipeline_result_roundtrips_nested_plan_payload():
    normalized = normalize_pipeline_result(
        {
            "success": True,
            "workspace": "/tmp/workspace",
            "plan": {
                "status": PLAN_STATUS_APPROVED,
                "awaiting_approval": False,
                "approved_at": "2026-03-31T00:00:00+00:00",
                "approved_by": "reviewer",
                "approval_notes": "looks good",
                "validation": {
                    "available": True,
                    "valid": True,
                    "errors": [],
                    "warnings": [],
                    "detected_sections": ["analysis_stages"],
                    "stage_count": 1,
                },
            },
        }
    )

    serialized = normalized.to_dict()

    assert serialized["plan"]["status"] == PLAN_STATUS_APPROVED
    assert serialized["plan"]["validation"]["stage_count"] == 1
    assert serialized["plan_status"] == PLAN_STATUS_APPROVED
    assert serialized["awaiting_plan_approval"] is False


def test_normalize_pipeline_result_roundtrips_completion_payload():
    normalized = normalize_pipeline_result(
        {
            "success": True,
            "workspace": "/tmp/workspace",
            "manifest_path": "/tmp/workspace/manifest.json",
            "completion_report_path": "/tmp/workspace/completion_report.json",
            "completion": {
                "status": "complete",
                "completed": True,
                "report_path": "/tmp/workspace/completion_report.json",
                "manifest_path": "/tmp/workspace/manifest.json",
                "missing_required_artifacts": [],
                "warnings": [],
                "errors": [],
            },
        }
    )

    serialized = normalized.to_dict()

    assert normalized.completion.status == "complete"
    assert normalized.completion.completed is True
    assert serialized["completion"]["status"] == "complete"
    assert serialized["completion_completed"] is True
    assert serialized["manifest_path"] == "/tmp/workspace/manifest.json"
