"""A prior sc-filter result can bypass all preprocessing filters."""

import anndata as ad
import numpy as np
import pandas as pd
import pytest

from skills._sdk.notebook import load_skill


def test_apply_filters_false_preserves_cells_genes_and_doublets():
    api = load_skill("sc-preprocessing")
    counts = np.random.default_rng(42).poisson(4, (12, 20)).astype(float)
    counts[:, -1] = 0
    counts[0, -1] = 1
    adata = ad.AnnData(
        counts,
        obs=pd.DataFrame({"n_genes_by_counts": [20] * 12,
                          "total_counts": counts.sum(axis=1),
                          "pct_counts_mt": [30.] + [1.] * 11,
                          "predicted_doublet": [False, True] + [False] * 10},
                         index=[f"c{i}" for i in range(12)]),
        var=pd.DataFrame(index=[f"G{i}" for i in range(20)]),
    )
    result = api.preprocess(adata, min_genes=1, min_cells=3, apply_filters=False,
                            n_pcs=2, n_top_hvg=10)
    assert result.obs_names.equals(adata.obs_names)
    assert result.var_names.equals(adata.var_names)
    assert result.obsm["X_pca"].shape == (12, 2)
    assert api.run_info(result)["filter_summary"]["filters_applied"] is False
    filtered = api.preprocess(adata, min_genes=1, min_cells=3, n_pcs=2, n_top_hvg=10)
    assert filtered.shape == (10, 19)


@pytest.mark.parametrize("method", ["seurat", "sctransform"])
def test_apply_filters_false_also_disables_r_gene_filtering(monkeypatch, method):
    api = load_skill("sc-preprocessing")
    adata = ad.AnnData(
        np.array([[2, 0, 0], [1, 3, 0], [2, 1, 0]], dtype=float),
        obs=pd.DataFrame({"n_genes_by_counts": [1, 2, 2], "total_counts": [2, 4, 3],
                          "pct_counts_mt": [0., 0., 0.]}, index=["a", "b", "c"]),
        var=pd.DataFrame(index=["G1", "G2", "undetected"]),
    )

    def seurat_create_object(working, **options):
        detected = np.count_nonzero(working.layers["counts"], axis=0)
        return working[:, detected >= options["min_cells"]].copy()

    monkeypatch.setitem(api.preprocess.__wrapped__.__globals__, "_run_seurat_preprocessing", seurat_create_object)
    result = api.preprocess(adata, method=method, apply_filters=False)
    assert result.var_names.equals(adata.var_names)
