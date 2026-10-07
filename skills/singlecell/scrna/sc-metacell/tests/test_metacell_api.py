"""Metacell aggregation uses means and records an unavailable-method fallback."""

import anndata as ad
import numpy as np
import pandas as pd
import sys
from skills._sdk.notebook import load_skill


def test_metacells_preserve_cells_and_average_counts(monkeypatch):
    monkeypatch.setitem(sys.modules, "SEACells", None)
    counts = np.array([[2., 4.], [4., 6.], [20., 40.], [40., 60.]])
    adata = ad.AnnData(np.log1p(counts), obs=pd.DataFrame({"type": ["a", "a", "b", "b"]}, index=list("abcd")))
    adata.layers["counts"] = counts
    adata.obsm["X_pca"] = np.array([[0., 0.], [0.1, 0.], [9., 9.], [9.1, 9.]])
    original = adata.X.copy()
    api = load_skill("sc-metacell")
    result = api.metacells(adata, method="seacells", n_metacells=2, random_state=7)
    assert result.shape == (2, 2) and adata.n_obs == 4
    np.testing.assert_array_equal(adata.X, original)
    np.testing.assert_allclose(np.sort(result.X, axis=0), [[3., 5.], [30., 50.]])
    assert api.metacell_summary(result)["n_cells"].sum() == 4
    assert len(api.cell_to_metacell(adata)) == 4
    info = api.run_info(result)
    assert info["requested_method"] == "seacells" and info["executed_method"] == "kmeans"
    assert "SEACells" in info["fallback_reason"]
