"""Public function-library behavior on raw spatial counts."""

import numpy as np
import pytest

from skills._sdk.notebook import load_skill


def test_load_exposes_the_spatial_preprocessing_library():
    library = load_skill("spatial-preprocess")
    assert callable(library.preprocess)
    assert callable(library.run_info)


@pytest.mark.slow
def test_preprocess_returns_a_copy_with_counts_and_seeded_embeddings(monkeypatch):
    from scripts.generate_demo_data import generate_demo_visium

    monkeypatch.delenv("NUMBA_DISABLE_JIT", raising=False)
    library = load_skill("spatial-preprocess")
    source = generate_demo_visium()
    original = source.copy()
    first = library.preprocess(source, n_top_hvg=50, n_pcs=15, random_state=7)
    second = library.preprocess(source, n_top_hvg=50, n_pcs=15, random_state=7)
    assert first is not source
    np.testing.assert_array_equal(source.X, original.X)
    assert source.obs.equals(original.obs) and source.var.equals(original.var)
    assert set(source.obsm) == {"spatial"}
    assert not source.uns and not source.layers and source.raw is None
    np.testing.assert_array_equal(first.layers["counts"], original[first.obs_names, first.var_names].X)
    np.testing.assert_array_equal(first.raw.X, first.layers["counts"])
    np.testing.assert_allclose(first.X, np.log1p(first.layers["counts"] / first.layers["counts"].sum(axis=1)[:, None] * 1e4), rtol=1e-6)
    np.testing.assert_array_equal(first.obsm["X_umap"], second.obsm["X_umap"])
    assert first.obs["leiden"].equals(second.obs["leiden"])
    assert library.run_info(first)["random_state"] == 7
    assert library.run_info(first, keep=False)["n_cells_raw"] == original.n_obs
    assert library.run_info(first) == {}


def test_tables_and_spatial_figure_describe_the_returned_data():
    import anndata as ad
    import matplotlib.pyplot as plt
    import pandas as pd

    library = load_skill("spatial-preprocess")
    data = ad.AnnData(np.ones((3, 4)))
    data.obs["leiden"] = pd.Categorical(["1", "0", "0"])
    data.obs["total_counts"] = [4, 5, 6]
    data.obsm["spatial"] = np.array([[1., 2.], [2., 3.], [3., 4.]])
    data.uns["pca"] = {"variance_ratio": np.array([.6, .2]), "variance": np.array([3., 1.])}
    summary = library.cluster_summary(data)
    assert summary.to_dict("list") == {"cluster": ["0", "1"], "n_cells": [2, 1]}
    qc = library.qc_metrics_table(data)
    assert qc["observation"].tolist() == data.obs_names.tolist()
    assert qc["total_counts"].tolist() == [4, 5, 6]
    variance = library.pca_variance_table(data)
    np.testing.assert_allclose(variance["cumulative_variance_ratio"], [.6, .8])
    fig = library.spatial_figure(data, color="leiden")
    np.testing.assert_array_equal(fig.axes[0].collections[0].get_offsets(), data.obsm["spatial"])
    plt.close(fig)


@pytest.mark.parametrize("module", ["skmisc.loess", "igraph", "umap"])
def test_missing_backend_names_the_approved_installer(module, monkeypatch):
    import sys
    from scripts.generate_demo_data import generate_demo_visium

    library = load_skill("spatial-preprocess")
    monkeypatch.setitem(sys.modules, module, None)
    with pytest.raises(ImportError, match="install_skill_deps"):
        library.preprocess(generate_demo_visium())


@pytest.mark.parametrize("kwargs", [
    {"min_genes": -1}, {"min_cells": -1}, {"max_genes": -1},
    {"max_mt_pct": 101}, {"max_mt_pct": float("nan")},
    {"n_pcs": 0}, {"n_top_hvg": 0}, {"n_neighbors": 0},
    {"leiden_resolution": float("nan")}, {"resolutions": [0]},
    {"tissue": "unknown"},
])
def test_invalid_parameters_are_rejected_without_mutating_input(kwargs):
    import anndata as ad

    library = load_skill("spatial-preprocess")
    data = ad.AnnData(np.ones((4, 5)))
    with pytest.raises(ValueError, match=next(iter(kwargs))):
        library.preprocess(data, **kwargs)
    assert data.obs.empty and data.var.empty and not data.layers
