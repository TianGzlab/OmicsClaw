"""Doublet annotations through the library and its scientific backends."""

import sys
from types import SimpleNamespace

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from skills._sdk.notebook import load_skill


def test_scrublet_receives_counts_and_seed_without_dropping_cells(monkeypatch):
    observed = {}

    class Scrublet:
        def __init__(self, matrix, *, expected_doublet_rate, random_state):
            observed.update(matrix=matrix.copy(), rate=expected_doublet_rate, seed=random_state)

        def scrub_doublets(self, **kwargs):
            return np.array([0.1, 0.8, 0.3]), np.array([False, True, False])

    monkeypatch.setitem(sys.modules, "scrublet", SimpleNamespace(Scrublet=Scrublet))
    counts = np.array([[3, 1], [10, 3], [2, 4]])
    adata = ad.AnnData(np.log1p(counts))
    adata.layers["counts"] = counts.copy()
    api = load_skill("sc-doublet-detection")
    result = api.detect_doublets(adata, random_state=37, threshold=0.2)
    assert result is adata and adata.n_obs == 3
    np.testing.assert_array_equal(observed["matrix"], counts)
    np.testing.assert_allclose(adata.X, np.log1p(counts))
    assert observed["seed"] == 37
    assert adata.obs["predicted_doublet"].tolist() == [False, True, True]
    assert api.run_info(adata)["expression_source"] == "layers.counts"
    assert api.doublet_calls_table(adata)["cell_id"].tolist() == ["0", "1", "2"]
    assert api.doublet_summary(adata)["n_cells"].tolist() == [1, 2]


def test_matrix_exchange_preserves_expression_orientation_and_metadata(tmp_path):
    from scipy.io import mmread
    from skills.singlecell._lib.r_exchange import write_matrix_exchange

    expression = np.array([[1.2, 0.], [3.4, 5.6], [0., 7.8]])
    adata = ad.AnnData(expression, obs=pd.DataFrame({"group": ["B", "A", "B"], "unused": [1, 2, 3]},
                                                  index=["c2", "c1", "c3"]),
                        var=pd.DataFrame(index=["g2", "g1"]))
    folder = write_matrix_exchange(adata, tmp_path / "exchange", obs_columns=["group"])
    np.testing.assert_allclose(mmread(folder / "matrix.mtx").toarray(), expression.T)
    assert (folder / "barcodes.tsv").read_text().splitlines() == ["c2", "c1", "c3"]
    assert (folder / "features.tsv").read_text().splitlines()[0].split("\t")[0] == "g2"
    frame = pd.read_csv(folder / "obs.csv", index_col=0)
    assert frame.index.tolist() == ["c2", "c1", "c3"] and list(frame) == ["group"]
    assert frame["group"].tolist() == ["B", "A", "B"]
