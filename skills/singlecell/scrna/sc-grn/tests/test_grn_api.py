"""Correlation inference respects the supplied TFs; mean scores are not AUCell."""

import anndata as ad
import numpy as np
import pandas as pd
from skills._sdk.notebook import load_skill


def test_correlation_uses_user_tfs_and_mean_scoring_is_explicit():
    values = np.array([[1., 4., 2., 7.], [2., 3., 4., 1.], [3., 2., 6., 8.], [4., 1., 8., 2.]])
    adata = ad.AnnData(values, var=pd.DataFrame(index=["CUSTOM", "OTHER", "TARGET", "NOISE"]))
    api = load_skill("sc-grn")
    adjacency = api.infer_adjacencies(adata, tfs=["CUSTOM"], method="correlation", n_top=2)
    assert set(adjacency["TF"]) == {"CUSTOM"}
    assert adjacency.iloc[0]["target"] == "OTHER"
    regulons = api.regulons_from_adjacencies(adjacency, n_top=2)
    scores = api.score_regulons(adata, regulons, method="mean")
    np.testing.assert_allclose(scores["CUSTOM"], values[:, [1, 2]].mean(axis=1))
    assert scores.attrs["scoring_method"] == "mean"
    assert scores.attrs["is_aucell"] is False
    assert not any(name.startswith("regulon_") for name in adata.obs)
