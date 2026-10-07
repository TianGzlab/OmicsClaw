"""Spatial statistics via the public library."""
import numpy as np
import pandas as pd
import pytest
from anndata import AnnData
from scipy import sparse
from skills._sdk.notebook import load_skill


def test_network_properties_report_known_triangle():
    api = load_skill("spatial-statistics")
    data = AnnData(np.ones((3, 2)), obs=pd.DataFrame({"leiden": ["a", "a", "b"]}, index=list("abc")))
    data.obsm["spatial"] = np.array([[0, 0], [1, 0], [0, 1]])
    data.obsp["spatial_connectivities"] = sparse.csr_matrix(np.ones((3, 3)) - np.eye(3))
    assert api.analyze(data, analysis_type="network_properties") is data
    result = api.results_table(data, name="results_df")
    assert result.loc[0, "n_edges"] == 3
    assert result.loc[0, "mean_degree"] == 2
    assert api.run_info(data, keep=False)["analysis_family"] == "network"
    assert api.run_info(data) == {}


def test_unknown_analysis_rejected():
    with pytest.raises(ValueError, match="analysis_type"):
        load_skill("spatial-statistics").analyze(AnnData(), analysis_type="made_up")


def test_unknown_parameter_is_not_silently_ignored():
    with pytest.raises(TypeError, match="unexpected keyword"):
        load_skill("spatial-statistics").analyze(AnnData(), typo_permutations=10)


def test_getis_ord_accepts_float32_spatial_graph():
    data = AnnData(np.arange(1, 9, dtype=float).reshape(8, 1), var=pd.DataFrame(index=["marker"]))
    data.obsm["spatial"] = np.column_stack([np.arange(8), np.zeros(8)])
    data.obsp["spatial_connectivities"] = sparse.diags(
        [np.ones(7, dtype=np.float32), np.ones(7, dtype=np.float32)], [-1, 1], shape=(8, 8), format="csr")
    api = load_skill("spatial-statistics")
    api.analyze(data, analysis_type="getis_ord", genes=["marker"], n_perms=9, getis_star=False)
    assert np.isfinite(data.obs["getis_ord_marker"]).all()
    assert data.obs["getis_ord_pval_marker"].between(0, 1).all()


def test_bivariate_moran_discloses_unsupported_seed():
    rng = np.random.default_rng(0)
    data = AnnData(rng.normal(size=(40, 2)), var=pd.DataFrame(index=["a", "b"]))
    data.obsm["spatial"] = rng.uniform(size=(40, 2))
    api = load_skill("spatial-statistics")
    with pytest.warns(RuntimeWarning, match="results vary between runs"):
        api.analyze(data, analysis_type="bivariate_moran", genes=["a", "b"], n_perms=9, random_state=7)
    info = api.run_info(data)
    assert info["requested_random_state"] == 7
    assert info["effective_random_state"] is None
    assert info["seed_supported"] is False
    assert "Moran_BV" in info["reproducibility_note"]
