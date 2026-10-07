"""Marker annotation at the public function boundary."""
import numpy as np
import pandas as pd
import pytest
from anndata import AnnData
from skills._sdk.notebook import load_skill


def test_marker_annotation_recovers_known_t_and_b_cells():
    api = load_skill("spatial-annotate")
    data = AnnData(np.log1p(np.array([[10, 9, 0, 0], [11, 10, 0, 1], [9, 8, 1, 0],
                                     [0, 0, 10, 9], [1, 0, 11, 10], [0, 1, 9, 8]], dtype=float)),
                   obs=pd.DataFrame({"leiden": pd.Categorical(["a"] * 3 + ["b"] * 3)}, index=list("abcdef")),
                   var=pd.DataFrame(index=["CD3D", "CD3E", "CD79A", "MS4A1"]))
    assert api.annotate(data, n_marker_genes=2) is data
    assert data.obs["cell_type"].astype(str).tolist() == ["T cells"] * 3 + ["B cells"] * 3
    assert api.run_info(data, keep=False)["n_cell_types"] == 2
    assert api.run_info(data) == {}


def test_reference_method_requires_reference_data():
    with pytest.raises(ValueError, match="reference"):
        load_skill("spatial-annotate").annotate(AnnData(), method="tangram")


def test_count_models_reject_log_normalized_counts_before_training():
    data = AnnData(np.array([[0.1, 0.5], [0.2, 0.4]]))
    data.layers["counts"] = data.X.copy()
    with pytest.raises(ValueError, match="integer raw counts"):
        load_skill("spatial-annotate").annotate(data, method="cellassign")
