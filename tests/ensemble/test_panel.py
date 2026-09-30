"""Combining metric results into a panel score.

The score is a weighted mean of chance-corrected values clipped to [0, 1].
Clipping keeps one metric that is far below chance from outweighing the
others; renormalising over the metrics that could be computed keeps a single
failed metric (a missing optional dependency, say) from zeroing a trial
instead of being reported and dropped.
"""

from __future__ import annotations

import pytest

from omicsclaw.ensemble.metrics import PANELS, SPATIAL_DOMAINS, get_panel
from omicsclaw.ensemble.metrics.panel import MetricResult, clip01, combine, to_json


def test_the_spatial_panel_is_registered_with_its_weights():
    """Version 3 scores PAS and the raw silhouette equally.

    The DLPFC section of the panel-bias study found PAS the only member that
    correlated with ARI on its own, but PAS rewards spatial smoothing, and the
    silhouette pulls the other way on ``spatial_weight``; averaging the two is
    the point. CHAOS and the spatial-Leiden AMI drove the old panel towards
    over-splitting and are kept only as diagnostics.
    """
    assert get_panel("spatial_domains") is SPATIAL_DOMAINS
    assert SPATIAL_DOMAINS.weights == {"pas": 0.5, "silhouette_pca": 0.5}
    assert SPATIAL_DOMAINS.version == "spatial_domains/3"
    assert get_panel("batch_integration") is None
    assert set(PANELS) == {"spatial_domains"}


def test_diagnostics_are_never_scored():
    diagnostics = {m.name for m in SPATIAL_DOMAINS.metrics if m.weight == 0}
    assert diagnostics == {"chaos", "spatial_leiden_ami", "knn_agreement"}


def test_the_silhouette_is_the_one_member_scored_without_chance_correction():
    corrected = {m.name: m.chance_corrected for m in SPATIAL_DOMAINS.metrics}
    assert corrected == {
        "pas": True, "silhouette_pca": False, "chaos": True,
        "spatial_leiden_ami": True, "knn_agreement": True,
    }


def test_clipping():
    assert clip01(-0.3) == 0.0 and clip01(1.7) == 1.0 and clip01(0.25) == 0.25


def test_the_score_is_the_weighted_mean_of_clipped_adjusted_values():
    results = {
        "a": MetricResult(raw=1, expected=2, adjusted=0.5),
        "b": MetricResult(raw=1, expected=2, adjusted=1.5),
        "c": MetricResult(raw=1, expected=2, adjusted=-0.5),
    }
    combined = combine(results, {"a": 0.4, "b": 0.2, "c": 0.4})
    assert combined["score"] == pytest.approx(0.4 * 0.5 + 0.2 * 1.0 + 0.4 * 0.0)
    assert combined["clipped"] == {"a": 0.5, "b": 1.0, "c": 0.0}


def test_a_failed_metric_is_dropped_and_the_weights_renormalised():
    results = {
        "a": MetricResult(raw=1, expected=2, adjusted=0.5),
        "b": MetricResult(error="ModuleNotFoundError: igraph"),
        "c": MetricResult(raw=1, expected=2, adjusted=1.0),
    }
    combined = combine(results, {"a": 0.4, "b": 0.4, "c": 0.2})
    assert combined["weights_used"] == pytest.approx({"a": 2 / 3, "c": 1 / 3})
    assert combined["score"] == pytest.approx(2 / 3 * 0.5 + 1 / 3 * 1.0)
    assert combined["dropped"] == {"b": "ModuleNotFoundError: igraph"}


def test_a_degenerate_metric_is_dropped():
    results = {
        "a": MetricResult(raw=0, expected=0, degenerate=True),
        "c": MetricResult(raw=1, expected=2, adjusted=0.8),
    }
    combined = combine(results, {"a": 0.5, "c": 0.5})
    assert combined["score"] == pytest.approx(0.8)
    assert combined["dropped"] == {"a": "degenerate"}


def test_no_usable_metric_means_no_score():
    combined = combine({"a": MetricResult(error="x")}, {"a": 1.0})
    assert combined["score"] is None


def test_zero_weight_metrics_are_ignored_by_the_score():
    results = {"a": MetricResult(adjusted=0.2), "diag": MetricResult(adjusted=1.0)}
    assert combine(results, {"a": 1.0, "diag": 0.0})["score"] == pytest.approx(0.2)


def test_the_json_form_keeps_raw_expected_and_adjusted_apart():
    document = to_json(
        {
            "a": MetricResult(raw=1.0, expected=2.0, adjusted=0.5, extra={"k": 1}),
            "b": MetricResult(error="boom"),
            "c": MetricResult(raw=0.0, expected=0.0, degenerate=True),
        }
    )
    assert document["raw"] == {"a": 1.0, "b": None, "c": 0.0}
    assert document["expected"]["a"] == 2.0 and document["adjusted"]["a"] == 0.5
    assert document["errors"] == {"b": "boom"}
    assert document["degenerate_metrics"] == ["c"]
    assert document["diagnostics"] == {"a": {"k": 1}}
