from __future__ import annotations

from omicsclaw.agents.plan_validation import validate_plan_file, validate_plan_text


_VALID_PLAN_MD = """# Research Context & Scope

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
"""


def test_validate_plan_text_accepts_structurally_complete_plan():
    result = validate_plan_text(_VALID_PLAN_MD)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []
    assert result.stage_count == 1
    assert "analysis_stages" in result.detected_sections
    assert "evaluation_protocol" in result.detected_sections


def test_validate_plan_text_rejects_missing_required_sections():
    result = validate_plan_text(
        """# Research Context & Scope

Only the initial scope is described here.
"""
    )

    assert result.valid is False
    assert any("data acquisition strategy" in error.lower() for error in result.errors)
    assert any("analysis stages" in error.lower() for error in result.errors)
    assert any("evaluation protocol" in error.lower() for error in result.errors)


def test_validate_plan_text_rejects_missing_stage_details():
    result = validate_plan_text(
        """# Research Context & Scope

Test scope.

## Data Acquisition Strategy

Use the available dataset.

## Analysis Stages

### Stage 1
- Goal: preprocess data

## Dependencies

- scanpy

## Iteration Triggers

- Revisit parameters if QC fails

## Evaluation Protocol

- Compare outcomes across repeated runs
"""
    )

    assert result.valid is False
    assert "Missing stage detail: OmicsClaw skill selection." in result.errors
    assert "Missing stage detail: success signals." in result.errors
    assert "Missing stage detail: expected artifacts." in result.errors


def test_validate_plan_text_warns_when_qc_baseline_and_fallback_are_missing():
    result = validate_plan_text(
        """# Research Context & Scope

Test scope.

## Data Acquisition Strategy

Use the available dataset.

## Analysis Stages

### Stage 1
- Goal: preprocess data
- OmicsClaw skill(s): spatial-preprocessing
- Success signals: QC metrics are acceptable
- Expected artifacts: qc_report.csv

## Dependencies

- scanpy

## Iteration Triggers

- Repeat if outputs drift

## Evaluation Protocol

- Review outcomes qualitatively
"""
    )

    assert result.valid is True
    assert any("QC/parameter guidance" in warning for warning in result.warnings)
    assert any("baseline/control" in warning for warning in result.warnings)
    assert any("fallback strategy" in warning for warning in result.warnings)


def test_validate_plan_file_handles_missing_file(tmp_path):
    result = validate_plan_file(tmp_path / "missing-plan.md")

    assert result.valid is False
    assert result.errors == [
        f"plan.md not found: {tmp_path / 'missing-plan.md'}"
    ]
