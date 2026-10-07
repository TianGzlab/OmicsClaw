"""Marker discovery leaves the expression object unchanged."""

from copy import deepcopy

import anndata as ad
import numpy as np
import pandas as pd
import pytest
import scanpy as sc

from skills._sdk.notebook import load_skill


def _expression():
    return ad.AnnData(
        np.log1p(np.array([[9, 0, 2], [8, 0, 3], [7, 1, 2],
                          [0, 9, 2], [1, 8, 3], [0, 7, 2]], dtype=float)),
        obs=pd.DataFrame({"group": pd.Categorical(["a"] * 3 + ["b"] * 3)},
                         index=[f"c{i}" for i in range(6)]),
        var=pd.DataFrame(index=["A", "B", "shared"]),
        uns={"kept": {"value": 7}},
    )


def test_marker_ranking_is_pure_and_records_empty_filter_fallback():
    api = load_skill("sc-markers")
    adata = _expression()
    original_x, original_obs, original_uns = adata.X.copy(), adata.obs.copy(), deepcopy(adata.uns)
    table = api.find_markers(adata, groupby="group", min_in_group_fraction=1.0)
    np.testing.assert_array_equal(adata.X, original_x)
    pd.testing.assert_frame_equal(adata.obs, original_obs)
    assert adata.uns == original_uns
    assert len(table) == 6
    assert api.run_info(table)["filter_fallback"] is True
    assert api.run_info(table)["fallback_reason"]
    assert api.top_markers(table, n_top=1).set_index("group")["names"].to_dict() == {"a": "A", "b": "B"}


def test_filter_error_is_recorded(monkeypatch):
    api = load_skill("sc-markers")

    def fail(*args, **kwargs):
        raise RuntimeError("filter failed for fixture")

    monkeypatch.setattr(sc.tl, "filter_rank_genes_groups", fail)
    table = api.find_markers(_expression(), groupby="group")
    assert len(table) == 6
    assert "filter failed for fixture" in api.run_info(table)["fallback_reason"]


def test_cosg_has_no_p_values_and_top_markers_use_scores():
    api = load_skill("sc-markers")
    table = api.find_markers(_expression(), groupby="group", method="cosg", n_genes=3)
    assert table[["pvals", "pvals_adj"]].isna().all().all()
    table.loc[table["names"] == "shared", "logfoldchanges"] = 1000
    top = api.top_markers(table, n_top=1)
    assert top.set_index("group")["names"].to_dict() == {"a": "A", "b": "B"}
    assert set(api.cluster_summary(table)["effect_metric"]) == {"scores"}
    assert api.run_info(table, keep=False)["method"] == "cosg"
    assert api.run_info(table) == {}


@pytest.mark.parametrize("method", ["t-test", "logreg"])
def test_other_scanpy_methods_return_rankings(method):
    api = load_skill("sc-markers")
    adata = _expression()
    third = adata[:3].copy()
    third.obs["group"] = "c"
    third.obs_names = ["c6", "c7", "c8"]
    third.X = np.log1p(np.array([[1, 0, 9], [0, 1, 8], [1, 1, 7]], dtype=float))
    adata = ad.concat([adata, third])
    table = api.find_markers(adata, groupby="group", method=method)
    assert not table.empty
    assert {"group", "names", "scores"} <= set(table)


def test_marker_dotplot_returns_a_figure_without_files(tmp_path, monkeypatch):
    api = load_skill("sc-markers")
    adata = _expression()
    table = api.find_markers(adata, groupby="group")
    monkeypatch.chdir(tmp_path)
    figure = api.marker_dotplot_figure(adata, table, groupby="group", n_top=1)
    assert figure.axes
    assert list(tmp_path.iterdir()) == []
