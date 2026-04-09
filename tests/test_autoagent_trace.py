"""Tests for omicsclaw.autoagent.trace — RunTrace and TraceCollector."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from omicsclaw.autoagent.trace import (
    DataShapeTrace,
    ExecutionTrace,
    MethodTrace,
    ParameterTrace,
    QualityTrace,
    RunTrace,
    TraceCollector,
    _extract_traceback,
    _extract_warnings,
    _param_diff,
    clear_result_json_cache,
)


# ---------------------------------------------------------------------------
# RunTrace dataclass tests
# ---------------------------------------------------------------------------


class TestRunTrace:
    def test_default_construction(self):
        trace = RunTrace(trial_id=1, skill_name="sc-preprocessing", method="scanpy")
        assert trace.trial_id == 1
        assert trace.skill_name == "sc-preprocessing"
        assert trace.method == "scanpy"
        assert trace.timestamp  # auto-populated
        assert trace.execution.exit_code == 0
        assert trace.data_shape.cell_retention_rate == 1.0
        assert trace.method_trace.fallback_used is False
        assert trace.parameters.effective_params == {}
        assert trace.quality.quality_metrics == {}

    def test_to_dict_roundtrip(self):
        trace = RunTrace(
            trial_id=42,
            skill_name="sc-batch-integration",
            method="harmony",
            execution=ExecutionTrace(exit_code=0, duration_seconds=12.5),
            data_shape=DataShapeTrace(
                n_obs_before=5000,
                n_obs_after=4800,
                cell_retention_rate=0.96,
                embedding_keys=["X_pca", "X_harmony"],
            ),
            method_trace=MethodTrace(
                requested_method="scanvi",
                executed_method="scvi",
                fallback_used=True,
                fallback_reason="no labels",
            ),
            parameters=ParameterTrace(
                user_params={"theta": 2.0},
                skill_defaults={"theta": 1.0},
                effective_params={"theta": 2.0},
            ),
            quality=QualityTrace(quality_metrics={"silhouette": 0.45}),
        )

        d = trace.to_dict()
        assert d["trial_id"] == 42
        assert d["execution"]["exit_code"] == 0
        assert d["data_shape"]["cell_retention_rate"] == 0.96
        assert d["method_trace"]["fallback_used"] is True
        assert d["parameters"]["user_params"]["theta"] == 2.0
        assert d["quality"]["quality_metrics"]["silhouette"] == 0.45

    def test_save_and_load(self, tmp_path):
        original = RunTrace(
            trial_id=7,
            skill_name="test-skill",
            method="test-method",
            execution=ExecutionTrace(exit_code=0, duration_seconds=5.0),
            data_shape=DataShapeTrace(
                n_obs_before=100, n_obs_after=90, cell_retention_rate=0.9,
            ),
        )
        saved_path = original.save(tmp_path)
        assert saved_path.exists()
        assert saved_path.name == "run_trace.json"

        loaded = RunTrace.load(saved_path)
        assert loaded.trial_id == 7
        assert loaded.skill_name == "test-skill"
        assert loaded.execution.duration_seconds == 5.0
        assert loaded.data_shape.n_obs_before == 100
        assert loaded.data_shape.cell_retention_rate == 0.9

    def test_diagnostic_summary_basic(self):
        trace = RunTrace(
            trial_id=1,
            skill_name="sc-preprocessing",
            method="scanpy",
            execution=ExecutionTrace(exit_code=0, duration_seconds=30.0),
            data_shape=DataShapeTrace(
                n_obs_before=5000,
                n_obs_after=4500,
                cell_retention_rate=0.9,
                embedding_keys=["X_pca"],
                n_clusters=8,
            ),
            quality=QualityTrace(quality_metrics={"silhouette": 0.35}),
        )
        summary = trace.to_diagnostic_summary()
        assert "Trial #1" in summary
        assert "sc-preprocessing" in summary
        assert "5000 cells" in summary
        assert "4500 cells" in summary
        assert "retention=90.0%" in summary
        assert "silhouette=0.3500" in summary

    def test_diagnostic_summary_with_fallback(self):
        trace = RunTrace(
            trial_id=2,
            skill_name="sc-batch-integration",
            method="scanvi",
            method_trace=MethodTrace(
                requested_method="scanvi",
                executed_method="scvi",
                fallback_used=True,
                fallback_reason="no labels",
            ),
        )
        summary = trace.to_diagnostic_summary()
        assert "FALLBACK" in summary
        assert "scanvi" in summary
        assert "scvi" in summary

    def test_diagnostic_summary_with_crash(self):
        trace = RunTrace(
            trial_id=3,
            skill_name="test",
            method="test",
            execution=ExecutionTrace(
                exit_code=1,
                stderr="File not found\nTraceback:\n  error line\nValueError: bad",
            ),
        )
        summary = trace.to_diagnostic_summary()
        assert "exit=1" in summary
        assert "Stderr" in summary

    def test_diagnostic_summary_param_diffs(self):
        trace = RunTrace(
            trial_id=1,
            skill_name="test",
            method="test",
            parameters=ParameterTrace(
                skill_defaults={"min_genes": 200, "n_pcs": 50},
                effective_params={"min_genes": 300, "n_pcs": 50},
            ),
        )
        summary = trace.to_diagnostic_summary()
        assert "min_genes: 200 -> 300" in summary


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_extract_traceback(self):
        stderr = (
            "some output\n"
            "Traceback (most recent call last):\n"
            '  File "test.py", line 1\n'
            "    func()\n"
            "ValueError: bad value\n"
            "more output"
        )
        tb = _extract_traceback(stderr)
        assert tb is not None
        assert "Traceback" in tb
        assert "ValueError" in tb

    def test_extract_traceback_none(self):
        assert _extract_traceback("") is None
        assert _extract_traceback("just normal output") is None

    def test_extract_warnings(self):
        stderr = (
            "Normal line\n"
            "/path/file.py:10: UserWarning: something deprecated\n"
            "  warnings.warn('something deprecated')\n"
            "/path/file.py:20: FutureWarning: will change\n"
            "Regular output\n"
            "WARNING: low memory\n"
        )
        warns = _extract_warnings(stderr)
        assert len(warns) == 3
        assert any("UserWarning" in w for w in warns)
        assert any("FutureWarning" in w for w in warns)
        assert any("WARNING" in w for w in warns)

    def test_extract_warnings_empty(self):
        assert _extract_warnings("") == []

    def test_param_diff(self):
        diffs = _param_diff(
            {"a": 1, "b": 2, "c": 3},
            {"a": 1, "b": 5, "c": 3},
        )
        assert len(diffs) == 1
        assert "b: 5 -> 2" in diffs[0]

    def test_param_diff_empty(self):
        assert _param_diff({"a": 1}, {"a": 1}) == []


# ---------------------------------------------------------------------------
# TraceCollector tests
# ---------------------------------------------------------------------------


@dataclass
class FakeExecution:
    """Minimal mock of TrialExecution for testing."""
    success: bool = True
    output_dir: str = ""
    duration_seconds: float = 10.0
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


class TestTraceCollector:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        clear_result_json_cache()
        yield
        clear_result_json_cache()

    def test_collect_with_empty_output(self, tmp_path):
        """Collect trace from an empty output directory."""
        execution = FakeExecution(output_dir=str(tmp_path))
        trace = TraceCollector.collect(
            trial_id=0,
            skill_name="sc-preprocessing",
            method="scanpy",
            execution=execution,
            output_dir=tmp_path,
            user_params={"min_genes": 200},
            skill_defaults={"min_genes": 200, "n_pcs": 50},
        )
        assert trace.trial_id == 0
        assert trace.skill_name == "sc-preprocessing"
        assert trace.execution.exit_code == 0
        assert trace.parameters.user_params == {"min_genes": 200}
        assert trace.parameters.skill_defaults["n_pcs"] == 50
        # Effective should be merged defaults + user
        assert trace.parameters.effective_params["min_genes"] == 200

    def test_collect_with_result_json(self, tmp_path):
        """Collect trace from a directory with result.json."""
        result = {
            "skill": "sc-preprocessing",
            "summary": {
                "n_cells_before": 5000,
                "n_genes_before": 20000,
                "n_cells": 4500,
                "n_genes": 18000,
                "n_clusters": 8,
                "silhouette": 0.42,
            },
            "data": {
                "effective_params": {
                    "method": "scanpy",
                    "min_genes": 300,
                    "n_pcs": 50,
                },
                "visualization": {
                    "embedding_key": "X_pca",
                },
            },
        }
        (tmp_path / "result.json").write_text(json.dumps(result))

        execution = FakeExecution(output_dir=str(tmp_path))
        trace = TraceCollector.collect(
            trial_id=1,
            skill_name="sc-preprocessing",
            method="scanpy",
            execution=execution,
            output_dir=tmp_path,
        )

        assert trace.data_shape.n_obs_before == 5000
        assert trace.data_shape.n_obs_after == 4500
        assert trace.data_shape.n_vars_before == 20000
        assert trace.data_shape.n_vars_after == 18000
        assert trace.data_shape.n_clusters == 8
        assert trace.data_shape.cell_retention_rate == 4500 / 5000
        assert trace.parameters.effective_params["min_genes"] == 300
        assert trace.quality.quality_metrics.get("silhouette") == 0.42

    def test_collect_with_sc_preprocessing_legacy_summary_aliases(self, tmp_path):
        """Collect trace from the real sc-preprocessing summary style."""
        result = {
            "skill": "sc-preprocessing",
            "summary": {
                "method": "scanpy",
                "n_cells": 4250,
                "n_genes": 18000,
                "n_hvg": 2000,
                "n_cells_before_filter": 5000,
                "n_genes_before_filter": 20000,
                "cells_retained_pct": 85.0,
            },
            "data": {
                "effective_params": {
                    "method": "scanpy",
                    "min_genes": 300,
                },
            },
        }
        (tmp_path / "result.json").write_text(json.dumps(result))

        execution = FakeExecution(output_dir=str(tmp_path))
        trace = TraceCollector.collect(
            trial_id=11,
            skill_name="sc-preprocessing",
            method="scanpy",
            execution=execution,
            output_dir=tmp_path,
        )

        assert trace.data_shape.n_obs_before == 5000
        assert trace.data_shape.n_obs_after == 4250
        assert trace.data_shape.n_vars_before == 20000
        assert trace.data_shape.n_vars_after == 18000
        assert trace.data_shape.cell_retention_rate == 0.85
        assert trace.parameters.effective_params["min_genes"] == 300
        assert trace.quality.quality_metrics.get("cells_retained_pct") == 85.0
        assert trace.quality.quality_metrics.get("cell_retention_rate") == 0.85

    def test_collect_with_method_fallback(self, tmp_path):
        """Collect trace when method fallback occurred."""
        result = {
            "skill": "sc-batch-integration",
            "summary": {
                "requested_method": "scanvi",
                "executed_method": "scvi",
                "fallback_used": True,
                "fallback_reason": "scanvi requires labels",
            },
            "data": {
                "effective_params": {"method": "scvi"},
            },
        }
        (tmp_path / "result.json").write_text(json.dumps(result))

        execution = FakeExecution(output_dir=str(tmp_path))
        trace = TraceCollector.collect(
            trial_id=2,
            skill_name="sc-batch-integration",
            method="scanvi",
            execution=execution,
            output_dir=tmp_path,
        )

        assert trace.method_trace.requested_method == "scanvi"
        assert trace.method_trace.executed_method == "scvi"
        assert trace.method_trace.fallback_used is True
        assert "labels" in trace.method_trace.fallback_reason

    def test_collect_crash(self, tmp_path):
        """Collect trace from a crashed trial."""
        execution = FakeExecution(
            success=False,
            output_dir=str(tmp_path),
            exit_code=1,
            stderr=(
                "Loading data...\n"
                "Traceback (most recent call last):\n"
                '  File "sc_preprocess.py", line 100\n'
                "ValueError: invalid literal\n"
            ),
        )
        trace = TraceCollector.collect(
            trial_id=3,
            skill_name="sc-preprocessing",
            method="scanpy",
            execution=execution,
            output_dir=tmp_path,
        )

        assert trace.execution.exit_code == 1
        assert trace.execution.traceback is not None
        assert "ValueError" in trace.execution.traceback

    def test_save_load_roundtrip(self, tmp_path):
        """Full roundtrip: collect -> save -> load."""
        result = {
            "skill": "test",
            "summary": {"n_cells": 100, "n_genes": 50},
            "data": {"effective_params": {"method": "scanpy"}},
        }
        output = tmp_path / "trial_0001"
        output.mkdir()
        (output / "result.json").write_text(json.dumps(result))

        execution = FakeExecution(output_dir=str(output), duration_seconds=5.5)
        trace = TraceCollector.collect(
            trial_id=1,
            skill_name="test",
            method="scanpy",
            execution=execution,
            output_dir=output,
        )

        saved = trace.save(output)
        loaded = RunTrace.load(saved)

        assert loaded.trial_id == trace.trial_id
        assert loaded.execution.duration_seconds == 5.5
        assert loaded.data_shape.n_obs_after == 100
