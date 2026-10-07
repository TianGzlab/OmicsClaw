"""Deconvolution through the notebook function library."""
import numpy as np
import pandas as pd
import pytest
from anndata import AnnData
from skills._sdk.notebook import load_demo, load_skill


def test_flashdeconv_returns_aligned_proportions_without_mutating_reference():
    api = load_skill("spatial-deconv")
    data = load_demo("spatial_synthetic")
    reference = data.copy()
    reference.obs["cell_type"] = reference.obs["domain_ground_truth"]
    before = reference.X.copy()
    assert api.deconvolve(data, reference=reference, method="flashdeconv", sketch_dim=32, n_hvg=150) is data
    table = api.proportions(data)
    assert table.index.equals(data.obs_names)
    assert set(table.columns) == {"domain_0", "domain_1", "domain_2"}
    np.testing.assert_allclose(table.sum(axis=1), 1, atol=1e-5)
    np.testing.assert_array_equal(reference.X, before)
    assert "deconvolution_flashdeconv" not in reference.obsm
    assert api.run_info(data, keep=False)["n_cell_types"] == 3
    assert api.run_info(data) == {}


def test_count_model_rejects_normalized_values_before_loading_backend():
    data = AnnData(np.full((4, 60), 0.25))
    reference = data.copy()
    reference.obs["cell_type"] = pd.Categorical(["A", "A", "B", "B"])
    with pytest.raises(ValueError, match="integer counts"):
        load_skill("spatial-deconv").deconvolve(data, reference=reference)
