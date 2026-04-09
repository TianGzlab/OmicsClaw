"""Unit tests for autoagent Stage 1 modules.

Covers: metrics_registry, search_space, experiment_ledger, evaluator, judge.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# metrics_registry
# ---------------------------------------------------------------------------
from omicsclaw.autoagent.metrics_registry import (
    INTEGRATION_METRICS,
    MetricDef,
    SC_PREPROCESSING_METRICS,
    get_metrics_for_skill,
    list_optimizable_skills,
)


class TestMetricDef:
    def test_valid_directions(self):
        m = MetricDef(source="result.json:summary.x", direction="maximize")
        assert m.direction == "maximize"
        m2 = MetricDef(source="result.json:summary.x", direction="minimize")
        assert m2.direction == "minimize"

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="direction"):
            MetricDef(source="x", direction="up")

    def test_invalid_weight_raises(self):
        with pytest.raises(ValueError, match="weight"):
            MetricDef(source="x", direction="maximize", weight=0)
        with pytest.raises(ValueError, match="weight"):
            MetricDef(source="x", direction="maximize", weight=-1)


class TestGetMetrics:
    def test_exact_match(self):
        m = get_metrics_for_skill("sc-batch-integration", "*")
        assert m is not None
        assert "mean_ilisi" in m

    def test_wildcard_fallback(self):
        m = get_metrics_for_skill("sc-batch-integration", "harmony")
        assert m is not None
        assert "mean_ilisi" in m

    def test_unknown_skill_returns_none(self):
        assert get_metrics_for_skill("nonexistent-skill") is None

    def test_alias_coverage(self):
        m1 = get_metrics_for_skill("sc-integrate")
        m2 = get_metrics_for_skill("sc-batch-integration")
        assert m1 is not None
        assert m2 is not None
        assert set(m1.keys()) == set(m2.keys())

    def test_annotation_metrics(self):
        m = get_metrics_for_skill("sc-cell-annotation")
        assert m is not None
        assert "n_cell_types" in m
        assert "mean_confidence" in m


class TestListOptimizable:
    def test_returns_nonempty(self):
        skills = list_optimizable_skills()
        assert len(skills) > 0
        assert all("skill" in s for s in skills)

    def test_excludes_aliases_and_skills_without_param_hints(self):
        skills = list_optimizable_skills()
        names = {item["skill"] for item in skills}
        assert "sc-batch-integration" in names
        assert "sc-integrate" not in names
        assert "spatial-integrate" in names
        assert "spatial-integration" not in names
        assert "sc-clustering" not in names
        assert "sc-cell-annotation" not in names


# ---------------------------------------------------------------------------
# search_space
# ---------------------------------------------------------------------------
from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace, build_method_surface


class TestSearchSpace:
    SAMPLE_HINTS = {
        "params": ["batch_key", "harmony_theta", "integration_pcs"],
        "defaults": {"batch_key": "batch", "harmony_theta": 2.0, "integration_pcs": 50},
        "tips": [
            "--harmony-theta: diversity penalty; raise to encourage stronger mixing.",
            "--integration-pcs: number of PCs for integration.",
        ],
    }

    def test_from_param_hints_basic(self):
        ss = SearchSpace.from_param_hints(
            "sc-batch-integration",
            "harmony",
            self.SAMPLE_HINTS,
            fixed_params={"batch_key": "sample_id"},
        )
        assert ss.skill_name == "sc-batch-integration"
        assert ss.method == "harmony"
        assert ss.fixed == {"batch_key": "sample_id"}
        # batch_key is fixed, so only 2 tunable
        assert len(ss.tunable) == 2
        names = {p.name for p in ss.tunable}
        assert "harmony_theta" in names
        assert "integration_pcs" in names
        assert "batch_key" not in names

    def test_parameter_types_inferred(self):
        ss = SearchSpace.from_param_hints(
            "test", "m", self.SAMPLE_HINTS
        )
        theta = next(p for p in ss.tunable if p.name == "harmony_theta")
        pcs = next(p for p in ss.tunable if p.name == "integration_pcs")
        assert theta.param_type == "float"
        assert pcs.param_type == "int"

    def test_ranges_inferred(self):
        ss = SearchSpace.from_param_hints(
            "test", "m", self.SAMPLE_HINTS
        )
        theta = next(p for p in ss.tunable if p.name == "harmony_theta")
        assert theta.low is not None and theta.low < 2.0
        assert theta.high is not None and theta.high > 2.0

    def test_cli_flags(self):
        ss = SearchSpace.from_param_hints(
            "test", "m", self.SAMPLE_HINTS
        )
        theta = next(p for p in ss.tunable if p.name == "harmony_theta")
        assert theta.cli_flag == "--harmony-theta"

    def test_tips_parsed(self):
        ss = SearchSpace.from_param_hints(
            "test", "m", self.SAMPLE_HINTS
        )
        theta = next(p for p in ss.tunable if p.name == "harmony_theta")
        assert "diversity penalty" in theta.tip

    def test_bool_parameters_get_explicit_true_false_choices(self):
        ss = SearchSpace.from_param_hints(
            "test", "m", {
                "params": ["use_gpu"],
                "defaults": {"use_gpu": True},
                "tips": [],
            },
        )
        use_gpu = next(p for p in ss.tunable if p.name == "use_gpu")
        assert use_gpu.param_type == "bool"
        assert use_gpu.choices == [True, False]
        assert use_gpu.low is None
        assert use_gpu.high is None

    def test_categorical_parameters_are_excluded_from_tunable_space(self):
        ss = SearchSpace.from_param_hints(
            "test", "m", {
                "params": ["batch_key", "harmony_theta"],
                "defaults": {"batch_key": "batch", "harmony_theta": 2.0},
                "tips": [],
            },
        )
        names = {p.name for p in ss.tunable}
        assert "batch_key" not in names
        assert "harmony_theta" in names

    def test_build_method_surface_separates_tunable_and_fixed_inputs(self):
        surface = build_method_surface(
            "test",
            "m",
            {
                "params": ["batch_key", "labels_key", "harmony_theta"],
                "defaults": {"batch_key": "batch", "harmony_theta": 2.0},
                "tips": [
                    "--batch-key: batch column in adata.obs.",
                    "--labels-key: label column in adata.obs.",
                    "--harmony-theta: diversity penalty.",
                ],
            },
        )

        assert [param.name for param in surface.tunable] == ["harmony_theta"]
        assert [param.name for param in surface.fixed] == ["batch_key", "labels_key"]
        assert surface.fixed[0].required is False
        assert surface.fixed[0].default == "batch"
        assert surface.fixed[1].required is True

    def test_defaults_dict(self):
        ss = SearchSpace.from_param_hints(
            "test", "m", self.SAMPLE_HINTS,
            fixed_params={"batch_key": "b"},
        )
        defaults = ss.defaults_dict()
        assert "harmony_theta" in defaults
        assert defaults["harmony_theta"] == 2.0
        assert "batch_key" not in defaults

    def test_to_summary(self):
        ss = SearchSpace.from_param_hints(
            "test", "m", self.SAMPLE_HINTS,
            fixed_params={"batch_key": "b"},
        )
        summary = ss.to_summary()
        assert "harmony_theta" in summary
        assert "batch_key" in summary


# ---------------------------------------------------------------------------
# experiment_ledger
# ---------------------------------------------------------------------------
from omicsclaw.autoagent.directive import build_directive
from omicsclaw.autoagent.experiment_ledger import ExperimentLedger, TrialRecord


class TestTrialRecord:
    def test_roundtrip(self):
        r = TrialRecord(
            trial_id=0,
            params={"theta": 2.0},
            composite_score=0.75,
            raw_metrics={"ilisi": 1.8},
            status="baseline",
            evaluation_success=False,
            missing_metrics=["clisi", "batch_asw"],
        )
        d = r.to_dict()
        r2 = TrialRecord.from_dict(d)
        assert r2.trial_id == 0
        assert r2.params == {"theta": 2.0}
        assert r2.composite_score == 0.75
        assert r2.evaluation_success is False
        assert r2.missing_metrics == ["clisi", "batch_asw"]


class TestExperimentLedger:
    def test_append_and_read(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ExperimentLedger(path)
        assert len(ledger) == 0

        r = TrialRecord(trial_id=0, params={"a": 1}, composite_score=0.5, status="baseline")
        ledger.append(r)
        assert len(ledger) == 1
        assert ledger.best_trial().trial_id == 0

    def test_persistence(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger1 = ExperimentLedger(path)
        ledger1.append(TrialRecord(trial_id=0, params={}, composite_score=0.5, status="baseline"))
        ledger1.append(TrialRecord(trial_id=1, params={}, composite_score=0.8, status="keep"))

        # Re-open from disk
        ledger2 = ExperimentLedger(path)
        assert len(ledger2) == 2
        assert ledger2.best_trial().trial_id == 1

    def test_best_trial_ignores_discard(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ExperimentLedger(path)
        ledger.append(TrialRecord(trial_id=0, params={}, composite_score=0.5, status="baseline"))
        ledger.append(TrialRecord(trial_id=1, params={}, composite_score=0.9, status="discard"))
        assert ledger.best_trial().trial_id == 0


class TestDirective:
    def test_metrics_section_describes_metric_values_without_false_normalization(self, tmp_path):
        ledger = ExperimentLedger(tmp_path / "ledger.jsonl")
        search_space = SearchSpace.from_param_hints(
            "sc-batch-integration",
            "harmony",
            TestSearchSpace.SAMPLE_HINTS,
        )

        directive = build_directive(
            "sc-batch-integration",
            "harmony",
            search_space,
            INTEGRATION_METRICS,
            ledger,
            max_trials=5,
        )

        assert "weighted sum of **normalized** metric values" in directive

    def test_format_table(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ExperimentLedger(path)
        ledger.append(TrialRecord(
            trial_id=0, params={"theta": 2.0}, composite_score=0.5,
            raw_metrics={"ilisi": 1.8}, status="baseline",
        ))
        table = ledger.format_table()
        assert "theta" in table
        assert "baseline" in table

    def test_to_history_text(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ExperimentLedger(path)
        ledger.append(TrialRecord(
            trial_id=0, params={"theta": 2.0}, composite_score=0.5,
            raw_metrics={"ilisi": 1.8}, status="baseline",
            reasoning="Initial baseline run",
            missing_metrics=["clisi"],
        ))
        text = ledger.to_history_text()
        assert "Trial #0" in text
        assert "baseline" in text or "=" in text
        assert "Missing metrics: clisi" in text


# ---------------------------------------------------------------------------
# evaluator
# ---------------------------------------------------------------------------
from omicsclaw.autoagent.evaluator import Evaluator, _resolve_dot_path


class TestResolveDotPath:
    def test_simple(self):
        assert _resolve_dot_path({"a": {"b": 1.5}}, "a.b") == 1.5

    def test_missing(self):
        assert _resolve_dot_path({"a": {}}, "a.b") is None

    def test_deep(self):
        d = {"summary": {"metrics": {"ilisi": 2.3}}}
        assert _resolve_dot_path(d, "summary.metrics.ilisi") == 2.3


class TestEvaluator:
    def _make_output_dir(self, tmp_path, result_json: dict) -> Path:
        out = tmp_path / "trial_0000"
        out.mkdir()
        (out / "result.json").write_text(json.dumps(result_json))
        return out

    def test_evaluate_from_result_json(self, tmp_path):
        out = self._make_output_dir(tmp_path, {
            "summary": {"mean_ilisi": 2.0, "mean_clisi": 1.1}
        })
        ev = Evaluator(INTEGRATION_METRICS)
        result = ev.evaluate(out)
        assert result.success
        assert "mean_ilisi" in result.raw_metrics
        assert result.raw_metrics["mean_ilisi"] == 2.0
        assert result.composite_score != 0.0

    def test_missing_metric(self, tmp_path):
        out = self._make_output_dir(tmp_path, {
            "summary": {"mean_ilisi": 2.0}
            # missing mean_clisi, batch_asw, celltype_asw
        })
        ev = Evaluator(INTEGRATION_METRICS)
        result = ev.evaluate(out)
        assert result.success  # partial success
        assert len(result.missing_metrics) > 0

    def test_no_result_json(self, tmp_path):
        out = tmp_path / "empty_trial"
        out.mkdir()
        ev = Evaluator(INTEGRATION_METRICS)
        result = ev.evaluate(out)
        assert not result.success
        assert result.composite_score == float("-inf")

    def test_direction_normalization(self, tmp_path):
        """Minimize metrics should be flipped so higher composite is better."""
        # Two trials: one with high clisi (bad), one with low clisi (good)
        metrics = {
            "clisi": MetricDef(
                source="result.json:summary.clisi",
                direction="minimize",
                weight=1.0,
                range_min=0.0,
                range_max=10.0,
            ),
        }
        ev = Evaluator(metrics)

        out_bad = self._make_output_dir(tmp_path, {"summary": {"clisi": 5.0}})
        out_good = tmp_path / "trial_good"
        out_good.mkdir()
        (out_good / "result.json").write_text(json.dumps({"summary": {"clisi": 1.0}}))

        score_bad = ev.evaluate(out_bad).composite_score
        score_good = ev.evaluate(out_good).composite_score
        assert score_good > score_bad  # lower clisi → higher score

    def test_csv_reading(self, tmp_path):
        out = tmp_path / "trial_csv"
        out.mkdir()
        tables = out / "tables"
        tables.mkdir()
        (tables / "metrics.csv").write_text("metric,value\nmean_ilisi,2.5\n")

        metrics = {
            "ilisi_csv": MetricDef(
                source="tables/metrics.csv",
                column="value",
                direction="maximize",
                weight=1.0,
            ),
        }
        ev = Evaluator(metrics)
        result = ev.evaluate(out)
        assert result.success
        assert result.raw_metrics["ilisi_csv"] == 2.5

    def test_adata_path_filters_extra_metrics_and_uses_metricdefs(self, tmp_path, monkeypatch):
        out = tmp_path / "trial_adata"
        out.mkdir()
        (out / "processed.h5ad").write_text("stub", encoding="utf-8")

        monkeypatch.setattr(
            "omicsclaw.autoagent.metrics_compute.compute_metrics_from_adata",
            lambda *args, **kwargs: {
                "n_batches": 2.0,
                "mean_ilisi": 2.0,
                "mean_clisi": 1.0,
                "batch_asw": 0.2,
                "celltype_asw": 0.8,
            },
        )

        ev = Evaluator(
            INTEGRATION_METRICS,
            skill_name="sc-batch-integration",
            method="harmony",
        )
        result = ev.evaluate(out)

        assert result.success
        assert set(result.raw_metrics) == {
            "mean_ilisi",
            "mean_clisi",
            "batch_asw",
            "celltype_asw",
        }
        assert "n_batches" not in result.raw_metrics
        # After range normalization:
        # mean_ilisi=2.0 → (2-1)/(5-1)=0.25 (max) → 0.25
        # mean_clisi=1.0 → (1-1)/(5-1)=0.0 (min→flip) → 1.0
        # batch_asw=0.2 → (0.2+1)/(1+1)=0.6 (min→flip) → 0.4
        # celltype_asw=0.8 → (0.8+1)/(1+1)=0.9 (max) → 0.9
        # composite = (0.25*0.4 + 1.0*0.3 + 0.4*0.15 + 0.9*0.15) / 1.0 = 0.595
        assert abs(result.composite_score - 0.595) < 0.001

    def test_sc_preprocessing_result_json_aliases_are_normalized(self, tmp_path):
        out = self._make_output_dir(tmp_path, {
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
                "effective_params": {"method": "scanpy"},
            },
        })
        ev = Evaluator(
            SC_PREPROCESSING_METRICS,
            skill_name="sc-preprocessing",
            method="scanpy",
        )
        result = ev.evaluate(out)

        assert result.success
        assert result.raw_metrics["cell_retention"] == 0.85
        assert result.raw_metrics["n_hvgs"] == 2000
        assert result.raw_metrics["n_genes_after"] == 18000
        assert result.missing_metrics == []


# ---------------------------------------------------------------------------
# judge
# ---------------------------------------------------------------------------
from omicsclaw.autoagent.judge import judge, JudgmentResult


class TestJudge:
    def _make_ledger(self, tmp_path) -> ExperimentLedger:
        return ExperimentLedger(tmp_path / "ledger.jsonl")

    def test_improvement_keeps(self, tmp_path):
        ledger = self._make_ledger(tmp_path)
        best = TrialRecord(trial_id=0, params={"theta": 2.0}, composite_score=0.5,
                           raw_metrics={"ilisi": 1.8}, status="baseline")
        trial = TrialRecord(trial_id=1, params={"theta": 4.0}, composite_score=0.7,
                            raw_metrics={"ilisi": 2.3}, status="pending")
        result = judge(trial, best, ledger)
        assert result.decision == "keep"
        assert result.new_best

    def test_regression_discards(self, tmp_path):
        ledger = self._make_ledger(tmp_path)
        best = TrialRecord(trial_id=0, params={"theta": 2.0}, composite_score=0.7,
                           raw_metrics={}, status="baseline")
        trial = TrialRecord(trial_id=1, params={"theta": 8.0}, composite_score=0.5,
                            raw_metrics={}, status="pending")
        result = judge(trial, best, ledger)
        assert result.decision == "discard"
        assert not result.new_best

    def test_crash_discards(self, tmp_path):
        ledger = self._make_ledger(tmp_path)
        best = TrialRecord(trial_id=0, params={}, composite_score=0.5, status="baseline")
        trial = TrialRecord(trial_id=1, params={"theta": 100.0},
                            composite_score=float("-inf"), status="crash")
        result = judge(trial, best, ledger)
        assert result.decision == "discard"
        assert "crash" in result.reason.lower()

    def test_same_score_simpler_keeps(self, tmp_path):
        """Simplicity criterion: same score but fewer deviations from defaults → keep."""
        ledger = self._make_ledger(tmp_path)
        defaults = {"theta": 2.0, "pcs": 50}
        best = TrialRecord(trial_id=0, params={"theta": 3.0, "pcs": 40},
                           composite_score=0.7, status="baseline")
        # Trial with same score but closer to defaults (only theta changed)
        trial = TrialRecord(trial_id=1, params={"theta": 3.0, "pcs": 50},
                            composite_score=0.7, status="pending")
        result = judge(trial, best, ledger, baseline_params=defaults)
        # trial: 1 deviation (theta), best: 2 deviations (theta+pcs) → keep
        assert result.decision == "keep"
        assert result.new_best

    def test_same_score_same_complexity_discards(self, tmp_path):
        """Same score and same complexity → discard."""
        ledger = self._make_ledger(tmp_path)
        defaults = {"theta": 2.0, "pcs": 50}
        best = TrialRecord(trial_id=0, params={"theta": 3.0, "pcs": 40},
                           composite_score=0.7, status="baseline")
        trial = TrialRecord(trial_id=1, params={"theta": 4.0, "pcs": 40},
                            composite_score=0.7, status="pending")
        result = judge(trial, best, ledger, baseline_params=defaults)
        # Both have 2 deviations → not simpler → discard
        assert result.decision == "discard"

    def test_both_inf_discards(self, tmp_path):
        """Both -inf scores → discard (no useful comparison)."""
        ledger = self._make_ledger(tmp_path)
        best = TrialRecord(trial_id=0, params={}, composite_score=float("-inf"), status="baseline")
        trial = TrialRecord(trial_id=1, params={}, composite_score=float("-inf"), status="pending")
        result = judge(trial, best, ledger)
        assert result.decision == "discard"

    def test_finite_beats_inf(self, tmp_path):
        """Any finite score beats -inf → keep."""
        ledger = self._make_ledger(tmp_path)
        best = TrialRecord(trial_id=0, params={}, composite_score=float("-inf"), status="baseline")
        trial = TrialRecord(trial_id=1, params={"theta": 2.0}, composite_score=0.1, status="pending")
        result = judge(trial, best, ledger)
        assert result.decision == "keep"
        assert result.new_best

    def test_inf_trial_loses_to_finite_best(self, tmp_path):
        """-inf trial score vs finite best → discard."""
        ledger = self._make_ledger(tmp_path)
        best = TrialRecord(trial_id=0, params={}, composite_score=0.5, status="baseline")
        trial = TrialRecord(trial_id=1, params={}, composite_score=float("-inf"), status="pending")
        result = judge(trial, best, ledger)
        assert result.decision == "discard"
