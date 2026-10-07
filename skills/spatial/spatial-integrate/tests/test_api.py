"""Public integration behavior on the recorded multi-batch fixture."""

import anndata as ad
import numpy as np
import pytest

from skills._sdk.notebook import load_demo, load_skill


@pytest.mark.parametrize("method,key", [("harmony", "X_pca_harmony"), ("bbknn", "X_pca"), ("scanorama", "X_scanorama")])
def test_integration_preserves_observation_order_and_returns_metrics(method, key):
    data = load_skill("spatial-preprocess").preprocess(
        load_demo("spatial_synthetic"), n_top_hvg=150, n_pcs=15)
    data.obs["batch"] = [f"batch_{i % 3}" for i in range(data.n_obs)]
    library = load_skill("spatial-integrate")
    names = data.obs_names.copy()
    original = data.X.copy()
    result = library.integrate(data, method=method)
    assert result is data
    assert data.obs_names.equals(names)
    np.testing.assert_array_equal(data.X, original)
    assert data.obsm[key].shape[0] == data.n_obs
    assert library.run_info(data)["method"] == method
    assert library.mixing_table(data).shape == (data.n_obs, 4)
    assert library.run_info(data, keep=False)
    assert library.run_info(data) == {}


def test_integration_rejects_unknown_method():
    with pytest.raises(ValueError, match="method"):
        load_skill("spatial-integrate").integrate(ad.AnnData(np.ones((4, 3))), method="unknown")
