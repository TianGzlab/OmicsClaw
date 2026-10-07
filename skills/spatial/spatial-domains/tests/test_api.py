"""Known spatial partition through the notebook library."""
import numpy as np
import pandas as pd
from scipy import sparse
from anndata import AnnData
from skills._sdk.notebook import load_skill
import pytest


def test_disconnected_expression_graph_yields_two_domains():
    api = load_skill("spatial-domains")
    data = AnnData(np.ones((8, 3)))
    data.obsm["X_pca"] = np.ones((8, 2))
    data.obsp["connectivities"] = sparse.block_diag([np.ones((4, 4)) - np.eye(4)] * 2).tocsr()
    data.uns["neighbors"] = {"connectivities_key": "connectivities"}
    result = api.identify(data, spatial_weight=0)
    assert result is data
    labels = data.obs["spatial_domain"].astype(str)
    assert labels.iloc[:4].nunique() == 1
    assert labels.iloc[4:].nunique() == 1
    assert labels.iloc[0] != labels.iloc[4]
    assert api.domain_counts(data)["n_cells"].tolist() == [4, 4]
    assert api.run_info(data, keep=False)["n_domains"] == 2
    assert api.run_info(data) == {}


def test_missing_spatial_backend_records_expression_fallback(monkeypatch):
    import builtins
    original = builtins.__import__
    def without_squidpy(name, *args, **kwargs):
        if name == "squidpy":
            raise ImportError("squidpy deliberately unavailable")
        return original(name, *args, **kwargs)
    data = AnnData(np.ones((8, 3)))
    data.obsm["X_pca"] = np.ones((8, 2))
    data.obsm["spatial"] = np.column_stack([np.arange(8), np.zeros(8)])
    data.obsp["connectivities"] = sparse.block_diag([np.ones((4, 4)) - np.eye(4)] * 2).tocsr()
    data.uns["neighbors"] = {"connectivities_key": "connectivities"}
    api = load_skill("spatial-domains")
    monkeypatch.setattr(builtins, "__import__", without_squidpy)
    with pytest.warns(RuntimeWarning, match="expression-only"):
        api.identify(data)
    info = api.run_info(data)
    assert info["requested_method"] == "spatial_leiden"
    assert info["executed_method"] == "expression_leiden"
    assert "squidpy" in info["fallback_reason"]
