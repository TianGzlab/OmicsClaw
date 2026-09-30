"""Skipping stage 2 and choosing trials, without a model.

The panel correlates only weakly with ground truth, so more trials mostly
make the best panel score the maximum of panel noise. Two rules guard
against that, both using the score's standard error: stage 2 (a local
refinement) runs only when stage 1 beat the default by more than one SE, and
the final choice is the simplest trial within one SE of the best. The SE is
a single-partition measurement error, not the cross-validation SE of the
classical one-standard-error rule; the rule is borrowed as a heuristic.
"""

from __future__ import annotations

import pytest

from omicsclaw.ensemble.tuning.judge import Evaluated, choose_final, choose_method, eligible, skip_stage2


def _item(trial, score, *, se=0.02, params=None, n_labels=7, status="ok", seq=None, default=False, method="spagcn"):
    return Evaluated(
        method=method, run_id="r", trial=trial, seq=seq if seq is not None else int(trial[1:]),
        params=params or {"n_domains": 7, "spagcn_p": 0.5, "epochs": 100},
        status=status, n_labels=n_labels, score=score, se=se, is_default=default,
    )


def test_eligibility_needs_ok_k_labels_and_a_score():
    assert eligible(_item("t1", 0.5), 7)
    assert not eligible(_item("t1", 0.5, n_labels=6), 7)
    assert not eligible(_item("t1", None), 7)
    assert not eligible(_item("t1", 0.5, status="failed"), 7)


def test_stage2_is_skipped_unless_stage1_beats_default_plus_se():
    default = _item("t1", 0.50, se=0.03, default=True)
    within = [_item("t2", 0.52), _item("t3", 0.53)]
    skip, why = skip_stage2(default, within, 7)
    assert skip and why["bar"] == pytest.approx(0.53)
    beyond = [_item("t2", 0.52), _item("t3", 0.5301)]
    skip, why = skip_stage2(default, beyond, 7)
    assert not skip and why["stage1_best_trial"] == "t3"


def test_stage2_runs_when_the_default_is_not_at_k():
    default = _item("t1", None, n_labels=6, default=True)
    skip, why = skip_stage2(default, [_item("t2", 0.1)], 7)
    assert not skip


def test_stage2_is_skipped_when_nothing_in_stage1_is_eligible():
    skip, _ = skip_stage2(_item("t1", 0.5, default=True), [_item("t2", None, status="failed")], 7)
    assert skip


def test_within_one_se_the_simplest_trial_wins_not_the_best():
    default = _item("t1", 0.60, default=True)
    better = _item("t2", 0.61, params={"n_domains": 7, "spagcn_p": 0.9, "epochs": 100})
    choice = choose_method([default, better], 7, _spagcn(), ignore=("n_domains",))
    assert choice.status == "ok" and choice.chosen.trial == "t1"
    assert choice.within_se == ["t1", "t2"]


def test_outside_the_band_the_best_wins():
    default = _item("t1", 0.50, default=True)
    better = _item("t2", 0.60, params={"n_domains": 7, "spagcn_p": 0.9, "epochs": 100})
    choice = choose_method([default, better], 7, _spagcn(), ignore=("n_domains",))
    assert choice.chosen.trial == "t2" and choice.within_se == ["t2"]


def test_the_tie_chain_is_count_then_distance_then_order():
    near = _item("t3", 0.60, params={"n_domains": 7, "spagcn_p": 0.6, "epochs": 100})
    far = _item("t2", 0.61, params={"n_domains": 7, "spagcn_p": 0.9, "epochs": 100})
    two = _item("t4", 0.62, params={"n_domains": 7, "spagcn_p": 0.6, "epochs": 120})
    choice = choose_method([far, near, two], 7, _spagcn(), ignore=("n_domains",))
    assert [r["trial"] for r in choice.ranking] == ["t3", "t2", "t4"]
    twin = _item("t5", 0.60, params={"n_domains": 7, "spagcn_p": 0.6, "epochs": 100})
    choice = choose_method([twin, near], 7, _spagcn(), ignore=("n_domains",))
    assert choice.chosen.trial == "t3"


def test_no_trial_at_k_falls_back_to_the_default():
    default = _item("t1", None, n_labels=5, default=True)
    other = _item("t2", None, n_labels=6)
    choice = choose_method([default, other], 7, _spagcn())
    assert choice.status == "fallback_default" and choice.chosen.trial == "t1"
    assert choose_method([], 7, _spagcn()).status == "failed"
    broken = _item("t1", None, status="failed", default=True)
    assert choose_method([broken], 7, _spagcn()).status == "failed"


def test_the_final_answer_is_the_best_method_at_k():
    from omicsclaw.ensemble.tuning.judge import MethodChoice

    a = MethodChoice("a", "ok", _item("t1", 0.4, method="a"))
    b = MethodChoice("b", "ok", _item("t1", 0.7, method="b"))
    c = MethodChoice("c", "fallback_default", _item("t1", 0.9, n_labels=5, method="c"))
    assert choose_final({"a": a, "b": b, "c": c}, 7).method == "b"
    assert choose_final({"c": c}, 7) is None


def _spagcn():
    from pathlib import Path

    from omicsclaw.ensemble.space import TuningCatalog
    from omicsclaw.skills import load_skills

    root = Path(__file__).resolve().parents[3] / "skills"
    return TuningCatalog.from_skills(load_skills(root)).get("spatial-domains").method("spagcn")


def test_the_band_is_one_standard_error_not_two():
    """A simpler trial 1.5 SE below the best is outside the band: with a 2-SE
    band it would be chosen instead of the best."""
    best = _item("t2", 0.63, se=0.02, params={"n_domains": 7, "spagcn_p": 0.9, "epochs": 100})
    simple = _item("t1", 0.60, se=0.02, default=True)
    choice = choose_method([simple, best], 7, _spagcn(), ignore=("n_domains",))
    assert choice.chosen.trial == "t2" and choice.within_se == ["t2"]
