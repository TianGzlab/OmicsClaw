"""Radius selection through the notebook library."""
import numpy as np
import pandas as pd
import pytest
from anndata import AnnData
from skills._sdk.notebook import load_skill


def test_radius_selects_neighbors_and_preserves_input():
    library = load_skill("spatial-microenvironment-subset")
    data = AnnData(np.ones((4, 2)), obs=pd.DataFrame({"cell_type": ["A", "B", "B", "B"]}, index=list("abcd")))
    data.obsm["spatial"] = np.array([[0, 0], [1, 0], [2, 0], [4, 0]])
    result = library.subset(data, center_values=["A"], radius_native=1.5)
    assert list(result.obs_names) == ["a", "b"]
    assert data.n_obs == 4
    assert "microenv_role" not in data.obs
    assert library.run_info(result)["n_neighbor_observations"] == 1
    assert library.selection_table(result)["microenv_distance_native"].tolist() == [0, 1]


def test_invalid_radius_is_rejected():
    library = load_skill("spatial-microenvironment-subset")
    with pytest.raises(ValueError, match="radius"):
        library.subset(AnnData(np.ones((2, 2))), center_values=["A"], radius_native=-1)
