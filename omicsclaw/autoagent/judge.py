"""Keep/Discard decision engine for autoagent optimization.

Implements AutoAgent's keep/discard rules (program.md lines 157-171):

1. If ``composite_score`` improved → **keep**.
2. If score is the same and the parameter change is simpler → **keep**
   (simplicity criterion).
3. Otherwise → **discard**.

Even discarded trials provide learning signal — the judge records *why*
a trial was discarded so the LLM meta-agent can reason about it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from omicsclaw.autoagent.constants import SCORE_DIFF_EPSILON
from omicsclaw.autoagent.experiment_ledger import ExperimentLedger, TrialRecord
from omicsclaw.autoagent.metrics_registry import MetricDef


@dataclass
class JudgmentResult:
    """Outcome of the keep/discard decision for one trial."""

    decision: str  # "keep" | "discard"
    reason: str
    new_best: bool
    learning_signal: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "new_best": self.new_best,
            "learning_signal": self.learning_signal,
        }


def judge(
    trial: TrialRecord,
    best: TrialRecord,
    ledger: ExperimentLedger,
    baseline_params: dict[str, Any] | None = None,
    metrics: dict[str, MetricDef] | None = None,
) -> JudgmentResult:
    """Apply AutoAgent keep/discard rules to a trial.

    Parameters
    ----------
    trial:
        The trial just completed.
    best:
        The current best trial (highest composite score so far).
    ledger:
        The full experiment ledger (for context in learning signal).
    baseline_params:
        Default parameter values from SearchSpace.  Used by the simplicity
        criterion to measure how far params deviate from defaults.
    """
    if trial.status == "crash":
        return JudgmentResult(
            decision="discard",
            reason="Trial crashed — skill execution failed.",
            new_best=False,
            learning_signal=_crash_learning_signal(trial),
        )

    trial_score = trial.composite_score
    best_score = best.composite_score

    # Handle -inf / NaN: any finite score beats a non-finite best
    trial_finite = math.isfinite(trial_score)
    best_finite = math.isfinite(best_score)

    if not trial_finite and not best_finite:
        # Both non-finite (e.g., both crashed) → discard
        return JudgmentResult(
            decision="discard",
            reason="Both trial and current best have non-finite scores.",
            new_best=False,
            learning_signal=_regression_signal(trial, best, metrics),
        )

    if trial_finite and not best_finite:
        # Trial has a real score, best doesn't → keep
        return JudgmentResult(
            decision="keep",
            reason=f"Trial achieved finite score ({trial_score:.4f}) "
            f"while previous best was non-finite.",
            new_best=True,
            learning_signal=_improvement_signal(trial, best, metrics),
        )

    if not trial_finite and best_finite:
        # Trial failed, best is real → discard
        return JudgmentResult(
            decision="discard",
            reason=f"Trial score is non-finite; best remains {best_score:.4f}.",
            new_best=False,
            learning_signal=_regression_signal(trial, best, metrics),
        )

    # Both finite from here
    score_diff = trial_score - best_score

    # Rule 1: Score improved → keep
    if score_diff > SCORE_DIFF_EPSILON:
        return JudgmentResult(
            decision="keep",
            reason=f"Score improved: {best_score:.4f} → {trial_score:.4f} "
            f"(+{score_diff:.4f})",
            new_best=True,
            learning_signal=_improvement_signal(trial, best, metrics),
        )

    # Rule 2: Same score, simpler change → keep (simplicity criterion)
    # "Simpler" = fewer parameter deviations from the default (baseline) values.
    if abs(score_diff) < SCORE_DIFF_EPSILON and baseline_params is not None:
        trial_changes = _param_deviation_count(trial.params, baseline_params)
        best_changes = _param_deviation_count(best.params, baseline_params)
        if trial_changes < best_changes:
            return JudgmentResult(
                decision="keep",
                reason=f"Same score ({trial_score:.4f}) but simpler: "
                f"{trial_changes} param change(s) vs {best_changes}.",
                new_best=True,
                learning_signal="Simpler configuration achieves same performance.",
            )

    # Rule 3: Otherwise → discard
    return JudgmentResult(
        decision="discard",
        reason=f"Score did not improve: best={best_score:.4f}, "
        f"trial={trial_score:.4f} ({score_diff:+.4f})",
        new_best=False,
        learning_signal=_regression_signal(trial, best, metrics),
    )


# ---------------------------------------------------------------------------
# Learning signal generators
# ---------------------------------------------------------------------------


def _improvement_signal(
    trial: TrialRecord,
    best: TrialRecord,
    metrics: dict[str, MetricDef] | None = None,
) -> str:
    """Describe what improved when a trial beats the current best."""
    lines: list[str] = []
    for metric_name in trial.raw_metrics:
        new_val = trial.raw_metrics.get(metric_name)
        old_val = best.raw_metrics.get(metric_name)
        if new_val is not None and old_val is not None:
            diff = new_val - old_val
            mdef = (metrics or {}).get(metric_name)
            if mdef and mdef.direction == "minimize":
                is_improved = diff < 0
            else:
                is_improved = diff > 0
            label = "improved" if is_improved else "regressed"
            lines.append(
                f"  {metric_name}: {old_val:.4f} → {new_val:.4f} "
                f"({label}, Δ={diff:+.4f})"
            )
    if not lines:
        return "Score improved but individual metric comparison unavailable."
    return "Metric changes:\n" + "\n".join(lines)


def _regression_signal(
    trial: TrialRecord,
    best: TrialRecord,
    metrics: dict[str, MetricDef] | None = None,
) -> str:
    """Describe what regressed when a trial is discarded."""
    improved: list[str] = []
    regressed: list[str] = []
    for metric_name in trial.raw_metrics:
        new_val = trial.raw_metrics.get(metric_name)
        old_val = best.raw_metrics.get(metric_name)
        if new_val is not None and old_val is not None:
            diff = new_val - old_val
            entry = f"{metric_name}: {old_val:.4f} → {new_val:.4f}"
            if abs(diff) > 1e-6:
                mdef = (metrics or {}).get(metric_name)
                if mdef and mdef.direction == "minimize":
                    # minimize: decrease is good
                    if diff < 0:
                        improved.append(entry)
                    else:
                        regressed.append(entry)
                else:
                    # maximize (default): increase is good
                    if diff > 0:
                        improved.append(entry)
                    else:
                        regressed.append(entry)

    parts: list[str] = []
    if improved:
        parts.append("Improved: " + "; ".join(improved))
    if regressed:
        parts.append("Regressed: " + "; ".join(regressed))
    if not parts:
        return "No significant metric differences detected."
    return "  |  ".join(parts)


def _crash_learning_signal(trial: TrialRecord) -> str:
    """Describe what can be learned from a crashed trial."""
    params_str = ", ".join(f"{k}={v}" for k, v in trial.params.items())
    return (
        f"Crashed with params: [{params_str}]. "
        f"These parameter values may be out of valid range."
    )


def _param_deviation_count(
    params: dict[str, Any],
    defaults: dict[str, Any],
) -> int:
    """Count how many parameters differ from the default (baseline) values."""
    count = 0
    for key, value in params.items():
        default_val = defaults.get(key)
        if default_val is not None and value != default_val:
            count += 1
    return count
