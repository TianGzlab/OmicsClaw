"""Correlation inference respects the supplied TFs; mean scores are not AUCell."""

import anndata as ad
import numpy as np
import pandas as pd
import sys
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


def test_grn_backend_fallback_warns_and_records_the_actual_method(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "arboreto.algo", None)
    adata = ad.AnnData(np.array([[1., 2.], [2., 4.], [3., 6.], [4., 8.]]),
                      var=pd.DataFrame(index=["CUSTOM", "TARGET"]))
    api = load_skill("sc-grn")
    edges = api.infer_adjacencies(adata, tfs=["CUSTOM"], method="grnboost2")
    info = api.run_info(edges)
    assert info["requested_method"] == "grnboost2"
    assert info["executed_method"] == "correlation"
    assert "arboreto" in info["fallback_reason"]
    assert any(record.levelname == "WARNING" and "grnboost2" in record.message
               and "correlation" in record.message and "arboreto" in record.message
               for record in caplog.records)
    assert edges[["TF", "target"]].to_dict("records") == [{"TF": "CUSTOM", "target": "TARGET"}]


def test_run_info_can_be_read_independently_and_removed():
    adata = ad.AnnData(np.array([[1., 2.], [2., 4.], [3., 6.], [4., 8.]]),
                      var=pd.DataFrame(index=["CUSTOM", "TARGET"]))
    api = load_skill("sc-grn")
    edges = api.infer_adjacencies(adata, tfs=["CUSTOM"], method="correlation")
    info = api.run_info(edges, keep=True)
    info["tfs"].append("UNREQUESTED")
    assert api.run_info(edges)["tfs"] == ["CUSTOM"]
    removed = api.run_info(edges, keep=False)
    assert removed["executed_method"] == "correlation"
    assert api.run_info(edges) == {}
    assert "run_info" not in edges.attrs
