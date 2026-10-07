"""Pseudotime chooses PCA and leaves process-wide JIT settings alone."""
import os
import anndata as ad
import numpy as np
import pandas as pd
from skills._sdk.notebook import load_skill


def test_dpt_defaults_to_pca_and_preserves_input(monkeypatch):
    rng = np.random.default_rng(3)
    adata = ad.AnnData(np.log1p(rng.gamma(2, 1, (40, 8))),
                      obs=pd.DataFrame({"cluster": pd.Categorical(["a", "b"] * 20)}))
    adata.obsm["X_pca"] = rng.normal(size=(40, 4))
    adata.obsm["X_umap"] = np.concatenate([np.zeros((20, 2)), np.ones((20, 2)) * 100])
    adata.uns["omicsclaw_matrix_contract"] = {"X": "normalized_expression"}
    monkeypatch.delenv("NUMBA_DISABLE_JIT", raising=False)
    api = load_skill("sc-pseudotime")
    assert "NUMBA_DISABLE_JIT" not in os.environ
    result = api.pseudotime(adata, cluster_key="cluster", root_cell=0, n_pcs=4, n_dcs=3, n_neighbors=15)
    assert result is not adata and "pseudotime" not in adata.obs
    assert api.run_info(result)["use_rep"] == "X_pca"
    assert np.isfinite(result.obs["pseudotime"]).all()
    assert result.obs["pseudotime"].iloc[0] == 0
    assert len(api.pseudotime_table(result)) == adata.n_obs
    assert "NUMBA_DISABLE_JIT" not in os.environ
