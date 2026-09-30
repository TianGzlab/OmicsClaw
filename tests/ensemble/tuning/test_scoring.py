"""The fixed-K score: normalise PAS and the silhouette by the probe's range at K, then average.

Their scales differ by an order of magnitude and they pull in opposite
directions on ``spatial_weight`` (PAS rewards smoothing, the silhouette
penalises it), so they are averaged only after each is mapped to the range
the probe trials span at the same K. The range is fixed after the probe:
letting tuning trials widen it would change the scores of trials already
judged. A score therefore depends on the other methods' probe trials and is
comparable only within one reference.
"""

from __future__ import annotations

import math

import pytest

from omicsclaw.ensemble.tuning.scoring import KReference, build_references, member_values, score_trial


def _metrics(pas_adj, sil, *, pas_se=0.01, sil_sd=0.2, m=100):
    return {
        "adjusted": {"pas": pas_adj, "silhouette_pca": sil},
        "raw": {"pas": 0.1, "silhouette_pca": sil},
        "diagnostics": {
            "pas": {"se_adjusted": pas_se, "n": 1000},
            "silhouette_pca": {"sd": sil_sd, "sample_size": m, "se": sil_sd / math.sqrt(m)},
        },
    }


def test_members_are_corrected_pas_and_raw_silhouette():
    values = member_values(_metrics(0.8, -0.1))
    assert values["pas"] == (0.8, 0.01)
    assert values["silhouette_pca"][0] == -0.1
    assert values["silhouette_pca"][1] == pytest.approx(0.02)


def test_references_are_per_k_ranges_over_ok_probe_trials():
    trials = [
        {"n_labels": 5, "metrics": _metrics(0.6, 0.10)},
        {"n_labels": 5, "metrics": _metrics(0.9, 0.05)},
        {"n_labels": 5, "metrics": _metrics(0.7, 0.20)},
        {"n_labels": 6, "metrics": _metrics(0.7, 0.20)},
    ]
    refs = build_references(trials)
    assert refs[5].ranges == {"pas": (0.6, 0.9), "silhouette_pca": (0.05, 0.20)}
    assert refs[5].n_trials == 3
    assert refs[6].ranges == {} and set(refs[6].degenerate) == {"pas", "silhouette_pca"}
    assert not refs[6].usable
    assert KReference.from_json(refs[5].to_json()) == refs[5]


def test_the_score_is_the_unclipped_mean_of_range_normalised_members():
    ref = KReference(k=5, n_trials=3, ranges={"pas": (0.6, 0.9), "silhouette_pca": (0.05, 0.20)})
    scored = score_trial(_metrics(0.75, 0.125), ref)
    assert scored.score == pytest.approx(0.5)
    below = score_trial(_metrics(0.3, 0.0), ref)
    assert below.score < 0
    above = score_trial(_metrics(1.2, 0.5), ref)
    assert above.score > 1


def test_the_standard_error_propagates_through_the_normalisation():
    ref = KReference(k=5, n_trials=3, ranges={"pas": (0.6, 0.9), "silhouette_pca": (0.05, 0.20)})
    scored = score_trial(_metrics(0.75, 0.125, pas_se=0.03, sil_sd=0.3, m=100), ref)
    expected = math.sqrt((0.03 / 0.3) ** 2 + (0.03 / 0.15) ** 2) / 2
    assert scored.se == pytest.approx(expected)


def test_a_degenerate_member_leaves_the_mean():
    ref = KReference(k=5, n_trials=2, ranges={"pas": (0.6, 0.9)}, degenerate=("silhouette_pca",))
    scored = score_trial(_metrics(0.9, 0.9, pas_se=0.03), ref)
    assert scored.score == pytest.approx(1.0) and scored.members_used == ("pas",)
    assert scored.se == pytest.approx(0.1)


def test_no_reference_means_no_score():
    assert score_trial(_metrics(0.9, 0.1), None).score is None
    assert score_trial(_metrics(0.9, 0.1), KReference(k=3, n_trials=1)).score is None


def test_the_score_is_absolute_not_a_rank():
    """A rank would change every earlier trial's score whenever a new trial
    arrives; the score of one trial must not depend on which others ran."""
    ref = KReference(k=5, n_trials=3, ranges={"pas": (0.6, 0.9), "silhouette_pca": (0.05, 0.20)})
    one = score_trial(_metrics(0.8, 0.1), ref).score
    assert score_trial(_metrics(0.8, 0.1), ref).score == one
