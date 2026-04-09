"""Tests for omicsclaw.autoagent.hard_gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omicsclaw.autoagent.hard_gates import (
    GateResult,
    HardGateVerdict,
    gate_artifacts_present,
    gate_cell_retention,
    gate_fallback_recorded,
    gate_no_crash,
    gate_no_empty_output,
    run_hard_gates,
)
from omicsclaw.autoagent.trace import (
    DataShapeTrace,
    ExecutionTrace,
    MethodTrace,
    RunTrace,
    TraceCollector,
)


def _make_trace(**kwargs) -> RunTrace:
    """Build a RunTrace with overrides."""
    return RunTrace(
        trial_id=kwargs.get("trial_id", 0),
        skill_name=kwargs.get("skill_name", "sc-preprocessing"),
        method=kwargs.get("method", "scanpy"),
        execution=kwargs.get("execution", ExecutionTrace()),
        data_shape=kwargs.get("data_shape", DataShapeTrace()),
        method_trace=kwargs.get("method_trace", MethodTrace()),
    )


# ---------------------------------------------------------------------------
# Individual gate tests
# ---------------------------------------------------------------------------


class TestGateNoCrash:
    def test_pass(self):
        trace = _make_trace(execution=ExecutionTrace(exit_code=0))
        result = gate_no_crash(trace)
        assert result.passed is True
        assert result.name == "no_crash"

    def test_fail(self):
        trace = _make_trace(execution=ExecutionTrace(exit_code=1))
        result = gate_no_crash(trace)
        assert result.passed is False
        assert "exit code 1" in result.message


class TestGateArtifactsPresent:
    def test_pass_default(self, tmp_path):
        (tmp_path / "result.json").write_text("{}")
        (tmp_path / "processed.h5ad").write_text("")
        trace = _make_trace(skill_name="sc-preprocessing")
        result = gate_artifacts_present(trace, tmp_path)
        assert result.passed is True

    def test_fail_missing_result_json(self, tmp_path):
        trace = _make_trace(skill_name="sc-preprocessing")
        result = gate_artifacts_present(trace, tmp_path)
        assert result.passed is False
        assert "result.json" in result.message

    def test_custom_required_files(self, tmp_path):
        (tmp_path / "output.csv").write_text("a,b\n1,2")
        trace = _make_trace(skill_name="bulkrna-de")
        result = gate_artifacts_present(
            trace, tmp_path, required_files=["output.csv"]
        )
        assert result.passed is True

    def test_non_adata_skill(self, tmp_path):
        """Skills not in _ADATA_SKILLS only need result.json."""
        (tmp_path / "result.json").write_text("{}")
        trace = _make_trace(skill_name="bulkrna-de")
        result = gate_artifacts_present(trace, tmp_path)
        assert result.passed is True


class TestGateCellRetention:
    def test_pass_high_retention(self):
        trace = _make_trace(
            data_shape=DataShapeTrace(
                n_obs_before=5000, n_obs_after=4800, cell_retention_rate=0.96,
            )
        )
        result = gate_cell_retention(trace)
        assert result.passed is True
        assert "4800/5000" in result.message

    def test_fail_low_retention(self):
        trace = _make_trace(
            data_shape=DataShapeTrace(
                n_obs_before=5000, n_obs_after=100, cell_retention_rate=0.02,
            )
        )
        result = gate_cell_retention(trace)
        assert result.passed is False
        assert "collapsed" in result.message

    def test_skip_no_before_count(self):
        trace = _make_trace(
            data_shape=DataShapeTrace(n_obs_before=0, n_obs_after=500)
        )
        result = gate_cell_retention(trace)
        assert result.passed is True
        assert "Skipped" in result.message

    def test_custom_threshold(self):
        trace = _make_trace(
            data_shape=DataShapeTrace(
                n_obs_before=1000, n_obs_after=80, cell_retention_rate=0.08,
            )
        )
        # 8% > 5% default → pass
        result = gate_cell_retention(trace, min_retention=0.05)
        assert result.passed is True
        # 8% < 10% custom → fail
        result = gate_cell_retention(trace, min_retention=0.10)
        assert result.passed is False

    def test_legacy_sc_preprocessing_summary_does_not_skip(self, tmp_path):
        result_payload = {
            "skill": "sc-preprocessing",
            "summary": {
                "n_cells": 4250,
                "n_genes": 18000,
                "n_hvg": 2000,
                "n_cells_before_filter": 5000,
                "n_genes_before_filter": 20000,
                "cells_retained_pct": 85.0,
            },
            "data": {"effective_params": {"method": "scanpy"}},
        }
        (tmp_path / "result.json").write_text(json.dumps(result_payload))

        trace = TraceCollector.collect(
            trial_id=1,
            skill_name="sc-preprocessing",
            method="scanpy",
            execution=ExecutionTrace(exit_code=0),
            output_dir=tmp_path,
        )
        result = gate_cell_retention(trace)

        assert result.passed is True
        assert "Skipped" not in result.message
        assert "4250/5000" in result.message


class TestGateNoEmptyOutput:
    def test_pass(self):
        trace = _make_trace(
            data_shape=DataShapeTrace(n_obs_after=100, n_vars_after=50)
        )
        result = gate_no_empty_output(trace)
        assert result.passed is True

    def test_fail_zero_cells(self):
        trace = _make_trace(
            execution=ExecutionTrace(exit_code=1),
            data_shape=DataShapeTrace(n_obs_after=0, n_vars_after=50),
        )
        result = gate_no_empty_output(trace)
        assert result.passed is False
        assert "Empty" in result.message

    def test_skip_unknown_shape(self):
        trace = _make_trace(
            data_shape=DataShapeTrace(n_obs_after=0, n_vars_after=0)
        )
        # exit_code=0 but no shape info → skip (don't fail)
        result = gate_no_empty_output(trace)
        assert result.passed is True
        assert "Skipped" in result.message


class TestGateFallbackRecorded:
    def test_pass_no_fallback(self):
        trace = _make_trace(method_trace=MethodTrace(fallback_used=False))
        result = gate_fallback_recorded(trace)
        assert result.passed is True

    def test_pass_with_reason(self):
        trace = _make_trace(
            method_trace=MethodTrace(
                requested_method="scanvi",
                executed_method="scvi",
                fallback_used=True,
                fallback_reason="no labels",
            )
        )
        result = gate_fallback_recorded(trace)
        assert result.passed is True
        assert "scanvi" in result.message

    def test_fail_silent_fallback(self):
        trace = _make_trace(
            method_trace=MethodTrace(
                requested_method="scanvi",
                executed_method="scvi",
                fallback_used=True,
                fallback_reason=None,
            )
        )
        result = gate_fallback_recorded(trace)
        assert result.passed is False
        assert "Silent" in result.message


# ---------------------------------------------------------------------------
# Aggregated gate runner
# ---------------------------------------------------------------------------


class TestRunHardGates:
    def test_all_pass(self, tmp_path):
        (tmp_path / "result.json").write_text("{}")
        (tmp_path / "processed.h5ad").write_text("")
        trace = _make_trace(
            execution=ExecutionTrace(exit_code=0),
            data_shape=DataShapeTrace(
                n_obs_before=1000,
                n_obs_after=900,
                n_vars_after=500,
                cell_retention_rate=0.9,
            ),
        )
        verdict = run_hard_gates(trace, tmp_path)
        assert verdict.all_passed is True
        assert len(verdict.results) == 5
        assert len(verdict.failed_gates) == 0
        assert "All 5 hard gates passed" in verdict.summary()

    def test_crash_fails(self, tmp_path):
        trace = _make_trace(execution=ExecutionTrace(exit_code=1))
        verdict = run_hard_gates(trace, tmp_path)
        assert verdict.all_passed is False
        assert any(g.name == "no_crash" and not g.passed for g in verdict.results)

    def test_subset_gates(self, tmp_path):
        trace = _make_trace(execution=ExecutionTrace(exit_code=0))
        verdict = run_hard_gates(
            trace, tmp_path, gates=["no_crash"]
        )
        assert len(verdict.results) == 1
        assert verdict.all_passed is True

    def test_diagnostic_output(self, tmp_path):
        trace = _make_trace(
            execution=ExecutionTrace(exit_code=1),
            data_shape=DataShapeTrace(
                n_obs_before=1000,
                n_obs_after=10,
                cell_retention_rate=0.01,
            ),
        )
        verdict = run_hard_gates(trace, tmp_path)
        diag = verdict.to_diagnostic()
        assert "[FAIL]" in diag
        assert "no_crash" in diag

    def test_to_dict(self, tmp_path):
        (tmp_path / "result.json").write_text("{}")
        trace = _make_trace(
            skill_name="bulkrna-de",
            execution=ExecutionTrace(exit_code=0),
        )
        verdict = run_hard_gates(trace, tmp_path)
        d = verdict.to_dict()
        assert "all_passed" in d
        assert isinstance(d["results"], list)
        assert all("name" in r for r in d["results"])
