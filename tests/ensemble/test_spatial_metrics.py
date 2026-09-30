"""The spatial panel's metrics against their literature definitions.

CHAOS and PAS are checked against hand-worked examples of the definitions in
SpatialPCA's ``fx_CHAOS``/``fx_PAS`` and SDMBench's ``_compute_CHAOS`` /
``_compute_PAS``. CHAOS is a nearest-neighbour distance within each label
(lower is better), not a fraction of same-label neighbours; a test pins that
compact labels score lower than shuffled ones. Three choices follow SDMBench and
are pinned here: labels with two or fewer members are skipped but their
observations stay in the denominator, the coordinates are standardised with the
population standard deviation, and PAS counts an observation as abnormal when
*more than* half of its ten neighbours carry another label (six or more).

The chance expectations are checked against Monte Carlo permutations. The PAS
check is sized so that the binomial approximation ``Bin(10, p_c)`` would fail
it; the exact hypergeometric expectation must pass.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from omicsclaw.ensemble.metrics.spatial import (
    chaos_metric,
    chaos_raw,
    compute_panel,
    encode,
    global_nn_distance,
    knn_agreement_expected,
    knn_agreement_raw,
    pas_expected,
    pas_raw,
    spatial_knn,
    standardise,
)

SQUARE = np.array([[-1.0, -1.0], [-1.0, 1.0], [1.0, -1.0], [1.0, 1.0]])
"""Already standardised: each axis has mean 0 and population std 1."""


def _codes(labels):
    return encode(labels)[0]


# ---- CHAOS ---------------------------------------------------------------------


def test_chaos_by_hand_with_a_single_point_label():
    # A = three corners: each one's nearest A neighbour is 2 away -> 6 / N=4.
    value, skipped = chaos_raw(_codes(["A", "A", "A", "B"]), standardise(SQUARE))
    assert value == pytest.approx(1.5)
    assert skipped == 1


def test_labels_with_two_members_are_skipped_but_counted_in_the_denominator():
    value, skipped = chaos_raw(_codes(["A", "A", "B", "B"]), standardise(SQUARE))
    assert (value, skipped) == (0.0, 4)
    coords = np.vstack([SQUARE, [[0.0, 0.0]]])
    value, skipped = chaos_raw(_codes(["A", "A", "A", "B", "B"]), standardise(coords))
    std = standardise(coords)
    by_hand = sum(
        min(np.linalg.norm(std[i] - std[j]) for j in (0, 1, 2) if j != i) for i in (0, 1, 2)
    ) / 5
    assert value == pytest.approx(by_hand)
    assert skipped == 2


def test_chaos_is_lower_for_compact_labels():
    rng = np.random.default_rng(0)
    coords = rng.uniform(0, 10, size=(400, 2))
    compact = _codes(coords[:, 0] > 5)
    shuffled = rng.permutation(compact)
    assert chaos_raw(compact, standardise(coords))[0] < chaos_raw(shuffled, standardise(coords))[0]


def test_standardisation_uses_the_population_standard_deviation():
    coords = np.array([[0.0, 0.0], [0.0, 4.0], [2.0, 0.0], [2.0, 4.0]])
    expected = (coords - coords.mean(axis=0)) / coords.std(axis=0, ddof=0)
    assert np.allclose(standardise(coords), expected)
    assert np.allclose(standardise(coords), SQUARE)


def test_chaos_matches_a_brute_force_transcription():
    rng = np.random.default_rng(3)
    coords = rng.normal(size=(120, 2)) * [5.0, 0.5]
    labels = rng.integers(0, 6, size=120)
    labels[:2] = 99  # a two-member label
    std = standardise(coords)
    total = 0.0
    for label in np.unique(labels):
        members = std[labels == label]
        if len(members) <= 2:
            continue
        distance = np.sqrt(((members[:, None, :] - members[None, :, :]) ** 2).sum(-1))
        np.fill_diagonal(distance, np.inf)
        total += distance.min(axis=1).sum()
    assert chaos_raw(_codes(labels), std)[0] == pytest.approx(total / 120)


def test_chaos_correction_is_one_at_the_lower_bound_and_zero_at_chance():
    rng = np.random.default_rng(1)
    coords = rng.uniform(0, 10, size=(600, 2))
    std = standardise(coords)
    nn = global_nn_distance(std)
    labels = _codes((coords[:, 0] // 2.5).astype(int))
    codes, sizes = encode(labels)
    good = chaos_metric(codes, sizes, std, nn)
    assert good.raw >= good.extra["lower_bound"]
    assert 0.3 < good.adjusted <= 1.0
    random = [
        chaos_metric(*encode(rng.permutation(labels)), std, nn).adjusted for _ in range(10)
    ]
    assert abs(float(np.mean(random))) < 0.1


def test_a_single_label_is_degenerate_for_chaos():
    coords = np.random.default_rng(0).uniform(size=(30, 2))
    std = standardise(coords)
    codes, sizes = encode(["A"] * 30)
    result = chaos_metric(codes, sizes, std, global_nn_distance(std))
    assert result.degenerate and result.adjusted is None


# ---- PAS ---------------------------------------------------------------------------


def _wheel(n_b_on_rim: int) -> tuple[np.ndarray, np.ndarray]:
    """A centre and ten rim points: every point's ten neighbours are the other ten."""
    angles = np.linspace(0, 2 * math.pi, 10, endpoint=False)
    coords = np.vstack([[0.0, 0.0], np.c_[np.cos(angles), np.sin(angles)] * 0.5])
    labels = ["A"] + ["A"] * (10 - n_b_on_rim) + ["B"] * n_b_on_rim
    return coords, _codes(labels)


def test_pas_counts_six_different_neighbours_but_not_five():
    # 6 A, 5 B: an A sees 5 A + 5 B (5 different, normal); a B sees 6 A (abnormal).
    coords, codes = _wheel(5)
    assert pas_raw(codes, spatial_knn(coords, 10)) == pytest.approx(5 / 11)
    # 5 A, 6 B: an A sees 6 B (abnormal); a B sees 5 A + 5 B (normal).
    coords, codes = _wheel(6)
    assert pas_raw(codes, spatial_knn(coords, 10)) == pytest.approx(5 / 11)


def test_pas_uses_raw_coordinates():
    rng = np.random.default_rng(0)
    coords = rng.uniform(size=(200, 2)) * [100.0, 1.0]
    codes = _codes(coords[:, 1] > 0.5)
    raw = pas_raw(codes, spatial_knn(coords, 10))
    standardised = pas_raw(codes, spatial_knn(standardise(coords), 10))
    assert raw != standardised


def test_the_hypergeometric_expectation_matches_permutations_and_the_binomial_does_not():
    from scipy.stats import binom

    rng = np.random.default_rng(7)
    coords = rng.uniform(size=(40, 2))
    codes = _codes([0] * 20 + [1] * 12 + [2] * 8)
    sizes = np.bincount(codes)
    knn = spatial_knn(coords, 10)
    draws = np.array([pas_raw(rng.permutation(codes), knn) for _ in range(20000)])
    mc, se = draws.mean(), draws.std(ddof=1) / math.sqrt(draws.size)
    exact = pas_expected(sizes, 10)
    binomial = sum((s / 40) * binom(10, s / 40).cdf(4) for s in sizes)
    assert abs(mc - exact) < 4 * se
    assert abs(mc - binomial) > 4 * se


def test_the_pas_correction():
    rng = np.random.default_rng(2)
    coords = rng.uniform(0, 10, size=(500, 2))
    codes = _codes((coords[:, 0] // 2).astype(int))
    sizes = np.bincount(codes)
    from omicsclaw.ensemble.metrics.spatial import pas_metric

    result = pas_metric(codes, sizes, spatial_knn(coords, 10))
    assert result.adjusted == pytest.approx((result.expected - result.raw) / result.expected)
    assert result.adjusted > 0.5


# ---- kNN agreement -------------------------------------------------------------------


def test_knn_agreement_expectation():
    sizes = np.array([30, 10])
    assert knn_agreement_expected(sizes) == pytest.approx(0.75 * 29 / 39 + 0.25 * 9 / 39)
    rng = np.random.default_rng(5)
    coords = rng.uniform(size=(40, 2))
    codes = _codes([0] * 30 + [1] * 10)
    knn = spatial_knn(coords, 10)
    draws = [knn_agreement_raw(rng.permutation(codes), knn) for _ in range(5000)]
    assert np.mean(draws) == pytest.approx(knn_agreement_expected(sizes), abs=0.005)


def test_spatial_knn_excludes_self_even_with_duplicate_coordinates():
    coords = np.array([[0.0, 0.0]] * 3 + [[1.0, 1.0], [2.0, 2.0]])
    knn = spatial_knn(coords, 2)
    for row in range(5):
        assert row not in knn[row]


# ---- the whole panel -------------------------------------------------------------------


def _synthetic(n=900, seed=0):
    rng = np.random.default_rng(seed)
    coords = rng.uniform(0, 30, size=(n, 2))
    labels = (coords[:, 0] // 10).astype(int).astype(str)
    expression = rng.normal(size=(n, 5)) + labels.astype(int)[:, None]
    return coords, labels, expression


def test_the_panel_reports_raw_expected_and_adjusted_for_every_metric():
    pytest.importorskip("igraph")
    coords, labels, expression = _synthetic()
    document = compute_panel(labels, {"coords": coords, "expression": expression})
    for name in ("chaos", "pas", "spatial_leiden_ami", "knn_agreement"):
        assert document["raw"][name] is not None
        assert document["expected"][name] is not None
        assert document["adjusted"][name] is not None
    assert document["errors"] == {}
    assert 0 < document["score"] <= 1
    assert document["panel_version"] == "spatial_domains/3"
    ami = document["diagnostics"]["spatial_leiden_ami"]
    assert len(ami["reference_n_clusters"]) == 3


def test_spatial_leiden_ami_of_a_reference_partition_is_one():
    pytest.importorskip("igraph")
    from omicsclaw.ensemble.metrics.spatial import reference_partitions, spatial_leiden_ami_metric

    coords, _, _ = _synthetic()
    partitions = reference_partitions(coords)
    result = spatial_leiden_ami_metric(_codes(partitions[0]), partitions)
    assert result.raw == pytest.approx(1.0)


def test_a_failed_metric_is_dropped_not_fatal(monkeypatch):
    from omicsclaw.ensemble.metrics import spatial

    def broken(*args, **kwargs):
        raise ModuleNotFoundError("No module named 'igraph'")

    monkeypatch.setattr(spatial, "reference_partitions", broken)
    coords, labels, expression = _synthetic()
    document = compute_panel(labels, {"coords": coords, "expression": expression})
    assert "igraph" in document["errors"]["spatial_leiden_ami"]
    assert set(document["weights_used"]) == {"pas", "silhouette_pca"}
    assert document["score"] is not None


def test_one_label_is_degenerate_with_score_zero():
    coords, _, _ = _synthetic(n=50)
    document = compute_panel(["x"] * 50, {"coords": coords})
    assert document["degenerate"] is True and document["score"] == 0.0


def test_the_diagnostics_are_reported():
    coords, labels, expression = _synthetic()
    document = compute_panel(labels, {"coords": coords, "expression": expression})
    assert document["n_labels"] == 3
    assert 0 < document["largest_label_frac"] < 1
    assert document["adjusted"]["silhouette_pca"] == document["raw"]["silhouette_pca"]
    assert document["chaos_skipped_spots"] == 0
    assert document["diagnostics"]["chaos"]["permutations"] == 10


# ---- version 3: the scored members and their standard errors ----------------------------


def test_the_silhouette_is_scored_raw_so_a_random_labelling_sits_near_zero():
    """``(s + 1) / 2`` would put the random level at 0.5 and hide a negative
    silhouette; the fixed-K score normalises members by their observed range,
    which only makes sense on the raw value."""
    from omicsclaw.ensemble.metrics.spatial import silhouette_metric

    rng = np.random.default_rng(3)
    expression = rng.normal(size=(600, 5))
    random_codes = rng.integers(0, 4, size=600)
    result = silhouette_metric(random_codes, expression)
    assert result.adjusted == result.raw
    assert abs(result.raw) < 0.05


def test_the_silhouette_matches_sklearn_and_reports_its_spread():
    from sklearn.metrics import silhouette_score

    from omicsclaw.ensemble.metrics.spatial import SILHOUETTE_SEED, silhouette_metric

    coords, labels, expression = _synthetic(n=700)
    codes = _codes(labels)
    result = silhouette_metric(codes, expression)
    expected = silhouette_score(expression, codes, sample_size=700, random_state=SILHOUETTE_SEED)
    assert result.raw == pytest.approx(expected)
    assert result.extra["sample_size"] == 700
    assert result.extra["sd"] > 0
    assert result.extra["se"] == pytest.approx(result.extra["sd"] / np.sqrt(700))


def test_pas_reports_the_standard_error_of_its_corrected_value():
    from omicsclaw.ensemble.metrics.spatial import pas_metric, spatial_knn

    coords, labels, _ = _synthetic(n=400)
    codes = _codes(labels)
    sizes = np.bincount(codes)
    result = pas_metric(codes, sizes, spatial_knn(coords, 10))
    pas, expected = result.raw, result.expected
    assert result.extra["n"] == 400
    assert result.extra["se_adjusted"] == pytest.approx(np.sqrt(pas * (1 - pas) / 400) / expected)


def test_the_panel_score_is_the_mean_of_clipped_pas_and_silhouette():
    coords, labels, expression = _synthetic()
    document = compute_panel(labels, {"coords": coords, "expression": expression})
    pas = min(1.0, max(0.0, document["adjusted"]["pas"]))
    sil = min(1.0, max(0.0, document["raw"]["silhouette_pca"]))
    assert document["score"] == pytest.approx(0.5 * pas + 0.5 * sil)
