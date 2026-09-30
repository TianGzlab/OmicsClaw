"""Stability curves: f (how often a K appears), c = 1 - rPAC (how consistent it is), a (cross-method agreement).

rPAC follows the MultiK source (Liu et al. 2021): ``PAC = F(0.9) - F(0.1)``
over the consensus values, divided by ``1 - prop_zeroes``. MultiK counts
zeroes over the whole matrix, this implementation over the pairs present
together at least once; the two differ by O(1/n). Agreement uses the
adjusted mutual information, which, unlike NMI, does not rise with the
number of labels by chance. The curves are evidence shown to the model, not a
filter; their bootstrap bands and peak frequencies say how much a single
subsample draw could have moved them.
"""

from __future__ import annotations

import gzip
import json
import math

import numpy as np
import pytest

anndata = pytest.importorskip("anndata")
pd = pytest.importorskip("pandas")
sklearn_metrics = pytest.importorskip("sklearn.metrics")

from omicsclaw.ensemble.tuning.stability import compute, pac_statistics, peaks, rpac_multik  # noqa: E402


def test_rpac_by_hand():
    """Pairs (0, 0.5, 1, 0, 0.2, 0.95): two zeroes, two values in (0.1, 0.9].
    PAC = 2/6, prop_zeroes = 2/6, rPAC = (1/3) / (2/3) = 0.5."""
    co = np.array([0, 1, 2, 0, 0.4, 1.9])
    both = np.array([2, 2, 2, 2, 2, 2.0])
    stats = pac_statistics(co, both)
    assert stats["pac"] == pytest.approx(1 / 3)
    assert stats["prop_zeroes"] == pytest.approx(1 / 3)
    assert stats["rpac"] == pytest.approx(0.5)
    assert stats["c"] == pytest.approx(0.5)


def test_upper_triangle_zeroes_differ_from_multik_only_by_order_one_over_n():
    rng = np.random.default_rng(0)
    n = 300
    blocks = rng.integers(0, 4, size=n)
    matrix = (blocks[:, None] == blocks[None, :]).astype(float)
    noise = rng.uniform(0, 1, size=(n, n))
    noise = (noise + noise.T) / 2
    matrix = np.where(noise < 0.1, 0.5, matrix)
    np.fill_diagonal(matrix, 1.0)
    upper = np.triu_indices(n, 1)
    ours = pac_statistics(matrix[upper], np.ones(upper[0].size))["rpac"]
    assert ours == pytest.approx(rpac_multik(matrix), abs=5 / n)


def test_pairs_never_together_are_left_out():
    stats = pac_statistics(np.array([0.0, 1.0, 0.0]), np.array([0.0, 1.0, 1.0]))
    assert stats["prop_zeroes"] == pytest.approx(0.5)


@pytest.mark.parametrize(
    "values, expected",
    [
        ({3: 0.1, 4: 0.5, 5: 0.2, 6: 0.3, 7: 0.1}, [4, 6]),
        ({3: 0.9, 4: 0.5, 5: 0.6}, [3, 5]),
        ({3: 0.5, 4: 0.5}, [3, 4]),
        ({3: 0.2, 5: 0.4, 9: 0.1}, [5]),
    ],
)
def test_peaks_compare_with_defined_neighbours(values, expected):
    assert peaks(values) == expected


# ---- the whole computation on a small synthetic input -----------------------------------------------


def _write_labels(path, ids, labels):
    with gzip.open(path, "wt") as sink:
        pd.DataFrame({"obs_id": ids, "label": [str(x) for x in labels]}).to_csv(sink, index=False)
    return str(path)


def _fixture(tmp_path, n=120):
    rng = np.random.default_rng(1)
    ids = [f"o{i}" for i in range(n)]
    adata = anndata.AnnData(X=np.zeros((n, 2), dtype=np.float32))
    adata.obs_names = ids
    adata.write_h5ad(tmp_path / "input.h5ad")
    truth = np.repeat(np.arange(4), n // 4)
    sub, full, exact = [], [], []
    for b in range(1, 5):
        keep = np.sort(rng.choice(n, size=int(0.8 * n), replace=False))
        for r, k in enumerate((3, 4, 4, 5)):
            labels = truth.copy()
            if k == 3:
                labels = np.minimum(labels, 2)
            if k == 5:
                labels = np.where((labels == 0) & (np.arange(n) % 2 == 0), 4, labels)
            if r == 2:
                flip = rng.choice(n, size=10, replace=False)
                labels[flip] = (labels[flip] + 1) % 4
            path = _write_labels(tmp_path / f"s{b}_{r}.csv.gz", [ids[i] for i in keep], labels[keep])
            sub.append({"b": b, "method": "leiden", "resolution": 0.5 + r, "labels": path})
    for method, shift in (("leiden", 0), ("louvain", 7)):
        labels = truth.copy()
        noisy = np.random.default_rng(shift).choice(n, size=15, replace=False)
        labels[noisy] = (labels[noisy] + 1) % 4
        full.append({"method": method, "resolution": 1.0,
                     "labels": _write_labels(tmp_path / f"full_{method}.csv.gz", ids, labels)})
    for method in ("spagcn",):
        exact.append({"method": method, "requested_k": 4,
                      "labels": _write_labels(tmp_path / f"exact_{method}.csv.gz", ids, truth)})
    spec = {
        "input": str(tmp_path / "input.h5ad"), "grid": [3, 4, 5, 6], "n_sub": 4,
        "sub": sub, "full": full, "exact": exact, "min_f": 0.025,
        "boot_fc": 50, "boot_a": 20, "seed_fc": 5800, "seed_a": 5801,
        "consensus_subset": 5000, "consensus_seed": 5700,
    }
    return spec, truth, full, exact


def test_the_curves_on_a_small_example(tmp_path):
    spec, truth, full, exact = _fixture(tmp_path)
    document = compute(spec, processes=1)
    rows = document["per_k"]
    assert rows["4"]["f"] == pytest.approx(0.5) and rows["3"]["f"] == pytest.approx(0.25)
    assert rows["6"]["f"] == 0 and rows["6"]["c"] is None and rows["6"]["a"] is None
    assert rows["3"]["c"] == pytest.approx(1.0)
    assert rows["4"]["c"] < 1.0
    ids = [f"o{i}" for i in range(len(truth))]
    parts = []
    for item in exact + full:
        table = pd.read_csv(item["labels"], dtype=str)
        parts.append(table.set_index("obs_id").loc[ids, "label"].to_numpy())
    expected = np.mean([
        sklearn_metrics.adjusted_mutual_info_score(parts[i], parts[j]) for i, j in ((0, 1), (0, 2), (1, 2))
    ])
    assert rows["4"]["a"] == pytest.approx(expected, abs=1e-6)
    assert rows["4"]["a_members"] == ["spagcn", "leiden", "louvain"]
    assert rows["4"]["a"] != pytest.approx(np.mean([
        sklearn_metrics.normalized_mutual_info_score(parts[i], parts[j]) for i, j in ((0, 1), (0, 2), (1, 2))
    ]), abs=1e-6)
    assert rows["4"]["f_lo"] <= rows["4"]["f"] <= rows["4"]["f_hi"]
    assert set(rows["4"]["peak_frequency"]) == {"f", "c", "a"}
    assert document["consensus_subset"] is None


def test_bands_and_peak_frequencies_are_reproducible(tmp_path):
    spec, *_ = _fixture(tmp_path)
    first = compute(spec, processes=1)
    second = compute(spec, processes=2)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_a_consensus_subset_is_used_above_the_limit(tmp_path):
    spec, *_ = _fixture(tmp_path)
    spec["consensus_subset"] = 60
    document = compute(spec, processes=1)
    assert document["consensus_subset"] == 60
    assert document["per_k"]["4"]["c"] is not None


def test_agreement_needs_three_partitions(tmp_path):
    spec, *_ = _fixture(tmp_path)
    spec["exact"] = []
    document = compute(spec, processes=1)
    assert document["per_k"]["4"]["a"] is None
    assert document["per_k"]["4"]["peak_frequency"]["a"] == 0


def test_pac_counts_the_upper_endpoint_and_not_the_lower():
    """MultiK's ``Fn(0.9) - Fn(0.1)`` is the share in (0.1, 0.9]: a consensus of exactly
    0.1 is outside, exactly 0.9 inside."""
    stats = pac_statistics(np.array([0.1, 0.9, 0.5, 1.0]), np.ones(4))
    assert stats["pac"] == pytest.approx(2 / 4)
    lower_only = pac_statistics(np.array([0.1, 1.0]), np.ones(2))
    assert lower_only["pac"] == 0


def test_the_bootstrap_uses_the_same_pac_interval_as_the_full_curve(tmp_path):
    """Two identical subsamples make every resample equal to the full data, so the
    band must collapse onto the full value; with consensus values of exactly 0.1
    and 0.9 present, a different endpoint in the bootstrap path would move it."""
    rng = np.random.default_rng(4)
    n = 40
    ids = [f"o{i}" for i in range(n)]
    adata = anndata.AnnData(X=np.zeros((n, 2), dtype=np.float32))
    adata.obs_names = ids
    adata.write_h5ad(tmp_path / "input.h5ad")
    runs = [rng.integers(0, 4, size=n) for _ in range(10)]
    for labels in runs:
        labels[:4] = [0, 1, 2, 3]
    sub = []
    for b in (1, 2):
        for r, labels in enumerate(runs):
            path = _write_labels(tmp_path / f"b{b}_{r}.csv.gz", ids, labels)
            sub.append({"b": b, "method": "leiden", "resolution": 0.5, "labels": path})
    spec = {"input": str(tmp_path / "input.h5ad"), "grid": [4], "n_sub": 2, "sub": sub, "full": [], "exact": [],
            "min_f": 0.025, "boot_fc": 20, "boot_a": 2, "seed_fc": 1, "seed_a": 1,
            "consensus_subset": 5000, "consensus_seed": 5700}
    row = compute(spec, processes=1)["per_k"]["4"]
    assert row["c_lo"] == pytest.approx(row["c"]) and row["c_hi"] == pytest.approx(row["c"])
