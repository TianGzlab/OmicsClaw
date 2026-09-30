"""Marker evidence for the K decision: compact for every K, full for the stable peaks.

The compact table (shares and three genes per domain) lets the model see
every K of the grid, not only the ones the stability curves favour; the full
block adds spatial coherence, centroids and fold changes where the model is
most likely to look. The nesting table says how a finer partition splits a
coarser one, which is how a model tells a real sub-region from a cut through
one.
"""

from __future__ import annotations

import gzip

import numpy as np
import pytest

anndata = pytest.importorskip("anndata")
pd = pytest.importorskip("pandas")
pytest.importorskip("scanpy")

from omicsclaw.ensemble.tuning.markers import compute, nesting  # noqa: E402


def _write(path, ids, labels):
    with gzip.open(path, "wt") as sink:
        pd.DataFrame({"obs_id": ids, "label": [str(x) for x in labels]}).to_csv(sink, index=False)
    return str(path)


def test_compact_full_and_nesting(tmp_path):
    rng = np.random.default_rng(0)
    n, genes = 300, 30
    region = np.repeat(np.arange(3), n // 3)
    x = rng.poisson(0.5, size=(n, genes)).astype(np.float32)
    for r in range(3):
        x[region == r, r * 5:(r + 1) * 5] += 5
    adata = anndata.AnnData(X=np.log1p(x))
    adata.obs_names = [f"s{i}" for i in range(n)]
    adata.var_names = [f"G{j}" for j in range(genes)]
    coords = np.column_stack([region * 10 + rng.uniform(0, 5, n), rng.uniform(0, 5, n)])
    adata.obsm["spatial"] = coords
    adata.write_h5ad(tmp_path / "in.h5ad")
    ids = list(adata.obs_names)
    fine = np.where((region == 2) & (coords[:, 1] > 2.5), 3, region)
    spec = {
        "input": str(tmp_path / "in.h5ad"),
        "partitions": [
            {"k": 3, "labels": _write(tmp_path / "k3.csv.gz", ids, region), "method": "m", "trial": "t1"},
            {"k": 4, "labels": _write(tmp_path / "k4.csv.gz", ids, fine), "method": "m", "trial": "t2"},
            {"k": 2, "labels": _write(tmp_path / "k2.csv.gz", ids, np.minimum(region, 1)), "method": "m", "trial": "t3"},
        ],
        "full": [3, 4],
    }
    document = compute(spec)
    assert set(document["compact"]) == {"2", "3", "4"}
    first = document["compact"]["3"]["domains"][0]
    assert first["domain"] == "0" and len(first["genes"]) == 3
    assert set(first["genes"]) <= {f"G{j}" for j in range(5)}
    assert set(document["full"]) == {"3", "4"}
    block = document["full"]["3"]["domains"][0]
    assert {"share", "same_label_neighbours", "centroid", "markers"} <= set(block)
    assert {"gene", "log2fc", "pct_in", "pct_out"} <= set(block["markers"][0])
    assert block["centroid"][0] < 0.3
    assert document["nesting"][0]["coarse"] == 3 and document["nesting"][0]["fine"] == 4
    three = next(row for row in document["nesting"][0]["rows"] if row["domain"] == "3")
    assert three["into"] == "2" and three["share"] == 1.0


def test_nesting_finds_the_majority_parent():
    fine = np.array(["a", "a", "a", "b", "b"])
    coarse = np.array(["x", "x", "y", "y", "y"])
    rows = nesting(fine, coarse)
    assert rows == [{"domain": "a", "into": "x", "share": pytest.approx(0.6667, abs=1e-4)},
                    {"domain": "b", "into": "y", "share": 1.0}]
