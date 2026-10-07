"""Trajectory behavior through the function library loaded by notebook steps."""

import numpy as np
import pytest

from skills._sdk.notebook import load_demo, load_skill


def test_dpt_returns_same_object_and_roots_pseudotime_at_requested_spot():
    import scanpy as sc

    data = load_demo("spatial_synthetic")
    sc.pp.normalize_total(data, target_sum=10000)
    sc.pp.log1p(data)
    sc.pp.pca(data, n_comps=15, random_state=0)
    sc.pp.neighbors(data, random_state=0)
    library = load_skill("spatial-trajectory")
    result = library.trajectory(data, root_cell=str(data.obs_names[0]))
    assert result is data
    assert data.obs["dpt_pseudotime"].iloc[0] == pytest.approx(0)
    assert np.isfinite(data.obs["dpt_pseudotime"]).any()
    info = library.run_info(data)
    assert info["root_cell"] == data.obs_names[0]
    assert info["random_state"] == 0
    assert library.pseudotime_table(data).shape[0] == data.n_obs
    assert library.run_info(data, keep=False)["method"] == "dpt"
    assert library.run_info(data) == {}


def test_missing_preprocessing_is_explicit():
    library = load_skill("spatial-trajectory")
    with pytest.raises(ValueError, match="PCA"):
        library.trajectory(load_demo("spatial_synthetic"))


def test_plot_missing_coordinates_is_explicit():
    data = load_demo("spatial_synthetic")
    data.obs["dpt_pseudotime"] = np.linspace(0, 1, data.n_obs)
    library = load_skill("spatial-trajectory")
    with pytest.raises(KeyError):
        library.pseudotime_figure(data, basis="missing")
