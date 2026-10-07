"""Known spatial partition through the notebook library."""
import numpy as np
import pandas as pd
from scipy import sparse
from anndata import AnnData
from skills._sdk.notebook import load_skill
import pytest


@pytest.fixture
def seeded_external_backends(monkeypatch):
    """Small external-package doubles expose the seed in returned labels."""
    import sys
    from types import SimpleNamespace
    import sklearn.mixture
    from skills._sdk.deps import _try_import

    class Mixture:
        def __init__(self, *, random_state, **kwargs):
            self.seed = random_state

        def fit_predict(self, values):
            return np.full(len(values), self.seed)

    class GraphST:
        def __init__(self, adata, *, random_seed, datatype, deconvolution=False, **kwargs):
            self.data = adata
            self.seed = random_seed

        def train(self):
            self.data.obsm["emb"] = self.data.X[:, :3].copy()
            self.data.obsm["emb"][:, 0] = self.seed
            return self.data

    class Cluster:
        def __init__(self, *, random_state, trainer_params, **kwargs):
            self.seed = random_state

        def fit(self, adata, **kwargs):
            pass

        def predict(self, adata, **kwargs):
            return np.full(adata.n_obs, self.seed)

    def train_stagate(adata, **kwargs):
        adata.obsm["STAGATE"] = np.ones((adata.n_obs, 3))
        return adata

    def graphst_clustering(adata, n_domains, **kwargs):
        adata.obs["domain"] = adata.obsm["emb"][:, 0].astype(int)

    monkeypatch.setattr(sklearn.mixture, "GaussianMixture", Mixture)
    modules = {
        "torch": SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False),
                                 device=lambda _: SimpleNamespace(type="cpu")),
        "STAGATE_pyG": SimpleNamespace(Cal_Spatial_Net=lambda *a, **k: None,
                                      train_STAGATE=train_stagate),
        "GraphST": SimpleNamespace(),
        "GraphST.GraphST": SimpleNamespace(GraphST=GraphST),
        "GraphST.utils": SimpleNamespace(clustering=graphst_clustering),
        "cellcharter": SimpleNamespace(tl=SimpleNamespace(Cluster=Cluster),
            gr=SimpleNamespace(remove_long_links=lambda *a: None,
                aggregate_neighbors=lambda adata, **kwargs: adata.obsm["X_pca"].copy())),
        "squidpy": SimpleNamespace(gr=SimpleNamespace(spatial_neighbors=lambda *a, **k: None)),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    _try_import.cache_clear()
    try:
        yield
    finally:
        _try_import.cache_clear()


@pytest.mark.parametrize("method", ["stagate", "graphst", "cellcharter"])
@pytest.mark.parametrize("seed, expected", [(None, 42), (0, 0), (13, 13)])
def test_method_default_seed_matches_cli_and_explicit_seed_wins(
        seeded_external_backends, method, seed, expected):
    api = load_skill("spatial-domains")
    data = AnnData(np.random.default_rng(5).normal(size=(8, 4)))
    data.obsm["X_pca"] = data.X[:, :3].copy()
    data.obsm["spatial"] = data.X[:, :2].copy()
    options = {} if seed is None else {"random_state": seed}
    api.identify(data, method=method, **options)
    assert data.obs["spatial_domain"].astype(str).unique().tolist() == [str(expected)]
    assert api.run_info(data)["random_state"] == expected


@pytest.mark.parametrize("seed, expected", [(None, 0), (13, 13)])
def test_automatic_pca_preserves_cli_seed_and_records_its_own_seed(
        seeded_external_backends, seed, expected):
    import scanpy as sc
    api = load_skill("spatial-domains")
    data = AnnData(np.random.default_rng(5).normal(size=(8, 4)))
    data.obsm["spatial"] = data.X[:, :2].copy()
    reference = data.copy()
    sc.pp.pca(reference, random_state=expected)
    api.identify(data, method="cellcharter", random_state=seed)
    np.testing.assert_allclose(data.obsm["X_pca"], reference.obsm["X_pca"])
    assert api.run_info(data)["pca_random_state"] == expected


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
    info = api.run_info(data, keep=False)
    assert info["n_domains"] == 2
    assert info["random_state"] == 0
    assert info["pca_random_state"] is None
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
