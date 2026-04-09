"""Tests for omicsclaw.autoagent.judge — keep/discard decision engine."""

from __future__ import annotations

import math

import pytest

from omicsclaw.autoagent.experiment_ledger import ExperimentLedger, TrialRecord
from omicsclaw.autoagent.judge import judge, _param_deviation_count
from omicsclaw.autoagent.metrics_registry import MetricDef


def _make_trial(
    trial_id: int = 1,
    params: dict | None = None,
    composite_score: float = 0.5,
    status: str = "pending",
    raw_metrics: dict | None = None,
) -> TrialRecord:
    return TrialRecord(
        trial_id=trial_id,
        params=params or {},
        composite_score=composite_score,
        status=status,
        reasoning="test",
        output_dir="/tmp/trial",
        raw_metrics=raw_metrics or {},
    )


def _empty_ledger() -> ExperimentLedger:
    return ExperimentLedger.__new__(ExperimentLedger)


class TestJudgeKeepDiscard:
    """Core keep/discard rules."""

    def test_higher_score_keeps(self):
        best = _make_trial(trial_id=0, composite_score=0.5)
        trial = _make_trial(trial_id=1, composite_score=0.7)
        result = judge(trial, best, _empty_ledger())
        assert result.decision == "keep"
        assert result.new_best is True

    def test_lower_score_discards(self):
        best = _make_trial(trial_id=0, composite_score=0.7)
        trial = _make_trial(trial_id=1, composite_score=0.3)
        result = judge(trial, best, _empty_ledger())
        assert result.decision == "discard"
        assert result.new_best is False

    def test_equal_score_no_baseline_discards(self):
        best = _make_trial(trial_id=0, composite_score=0.5)
        trial = _make_trial(trial_id=1, composite_score=0.5)
        result = judge(trial, best, _empty_ledger(), baseline_params=None)
        assert result.decision == "discard"

    def test_crashed_trial_discards(self):
        best = _make_trial(trial_id=0, composite_score=0.5)
        trial = _make_trial(trial_id=1, composite_score=float("-inf"), status="crash")
        result = judge(trial, best, _empty_ledger())
        assert result.decision == "discard"
        assert "crash" in result.reason.lower()

    def test_finite_beats_non_finite_best(self):
        best = _make_trial(trial_id=0, composite_score=float("-inf"))
        trial = _make_trial(trial_id=1, composite_score=0.1)
        result = judge(trial, best, _empty_ledger())
        assert result.decision == "keep"
        assert result.new_best is True

    def test_non_finite_trial_against_finite_best(self):
        best = _make_trial(trial_id=0, composite_score=0.5)
        trial = _make_trial(trial_id=1, composite_score=float("nan"))
        result = judge(trial, best, _empty_ledger())
        assert result.decision == "discard"

    def test_both_non_finite_discards(self):
        best = _make_trial(trial_id=0, composite_score=float("-inf"))
        trial = _make_trial(trial_id=1, composite_score=float("nan"))
        result = judge(trial, best, _empty_ledger())
        assert result.decision == "discard"


class TestSimplicityCriterion:
    """Simplicity criterion: same score + fewer changes = keep."""

    def test_simpler_params_keeps(self):
        defaults = {"theta": 2.0, "k": 15, "pcs": 30}
        best = _make_trial(
            trial_id=0,
            composite_score=0.5,
            params={"theta": 3.0, "k": 20, "pcs": 50},  # 3 changes
        )
        trial = _make_trial(
            trial_id=1,
            composite_score=0.5,
            params={"theta": 2.0, "k": 15, "pcs": 50},  # 1 change
        )
        result = judge(trial, best, _empty_ledger(), baseline_params=defaults)
        assert result.decision == "keep"
        assert result.new_best is True

    def test_more_complex_params_discards(self):
        defaults = {"theta": 2.0, "k": 15}
        best = _make_trial(
            trial_id=0,
            composite_score=0.5,
            params={"theta": 2.0, "k": 15},  # 0 changes
        )
        trial = _make_trial(
            trial_id=1,
            composite_score=0.5,
            params={"theta": 3.0, "k": 20},  # 2 changes
        )
        result = judge(trial, best, _empty_ledger(), baseline_params=defaults)
        assert result.decision == "discard"

    def test_same_complexity_discards(self):
        defaults = {"theta": 2.0}
        best = _make_trial(trial_id=0, composite_score=0.5, params={"theta": 3.0})
        trial = _make_trial(trial_id=1, composite_score=0.5, params={"theta": 4.0})
        result = judge(trial, best, _empty_ledger(), baseline_params=defaults)
        assert result.decision == "discard"


class TestParamDeviationCount:
    """Tests for _param_deviation_count helper."""

    def test_no_deviations(self):
        assert _param_deviation_count({"a": 1, "b": 2}, {"a": 1, "b": 2}) == 0

    def test_all_deviated(self):
        assert _param_deviation_count({"a": 10, "b": 20}, {"a": 1, "b": 2}) == 2

    def test_extra_params_not_in_defaults(self):
        # Params not in defaults are not counted
        assert _param_deviation_count({"a": 1, "c": 99}, {"a": 1}) == 0

    def test_empty_params(self):
        assert _param_deviation_count({}, {"a": 1, "b": 2}) == 0


class TestLearningSignals:
    """Judge produces useful learning signals."""

    def test_improvement_signal_has_metrics(self):
        best = _make_trial(trial_id=0, composite_score=0.5, raw_metrics={"asw": 0.3})
        trial = _make_trial(trial_id=1, composite_score=0.7, raw_metrics={"asw": 0.5})
        result = judge(trial, best, _empty_ledger())
        assert "asw" in result.learning_signal

    def test_crash_signal_has_params(self):
        best = _make_trial(trial_id=0, composite_score=0.5)
        trial = _make_trial(
            trial_id=1,
            composite_score=float("-inf"),
            status="crash",
            params={"theta": 99.0},
        )
        result = judge(trial, best, _empty_ledger())
        assert "theta" in result.learning_signal


class TestDirectionAwareLearningSignals:
    """Learning signals respect MetricDef.direction."""

    def test_minimize_metric_decrease_reported_as_improved(self):
        metrics = {
            "batch_asw": MetricDef(
                source="result.json:summary.batch_asw",
                direction="minimize",
                weight=1.0,
                range_min=-1.0,
                range_max=1.0,
            ),
        }
        best = _make_trial(trial_id=0, composite_score=0.5, raw_metrics={"batch_asw": 0.5})
        trial = _make_trial(trial_id=1, composite_score=0.7, raw_metrics={"batch_asw": 0.2})
        result = judge(trial, best, _empty_ledger(), metrics=metrics)
        assert "improved" in result.learning_signal.lower()

    def test_minimize_metric_increase_reported_as_regressed(self):
        metrics = {
            "batch_asw": MetricDef(
                source="result.json:summary.batch_asw",
                direction="minimize",
                weight=1.0,
                range_min=-1.0,
                range_max=1.0,
            ),
        }
        best = _make_trial(trial_id=0, composite_score=0.7, raw_metrics={"batch_asw": 0.2})
        trial = _make_trial(trial_id=1, composite_score=0.3, raw_metrics={"batch_asw": 0.5})
        result = judge(trial, best, _empty_ledger(), metrics=metrics)
        assert "regressed" in result.learning_signal.lower()

    def test_maximize_metric_increase_reported_as_improved(self):
        metrics = {
            "mean_ilisi": MetricDef(
                source="result.json:summary.mean_ilisi",
                direction="maximize",
                weight=1.0,
                range_min=1.0,
                range_max=5.0,
            ),
        }
        best = _make_trial(trial_id=0, composite_score=0.5, raw_metrics={"mean_ilisi": 2.0})
        trial = _make_trial(trial_id=1, composite_score=0.7, raw_metrics={"mean_ilisi": 3.5})
        result = judge(trial, best, _empty_ledger(), metrics=metrics)
        assert "improved" in result.learning_signal.lower()

    def test_without_metrics_falls_back_to_raw_comparison(self):
        """Backward compat: no metrics param → old numeric-direction behavior."""
        best = _make_trial(trial_id=0, composite_score=0.5, raw_metrics={"asw": 0.3})
        trial = _make_trial(trial_id=1, composite_score=0.7, raw_metrics={"asw": 0.5})
        result = judge(trial, best, _empty_ledger())
        assert "asw" in result.learning_signal
