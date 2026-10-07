"""Public pseudotime parameters, independent of the CLI's argument registry."""

import inspect

import anndata as ad
import numpy as np
import pytest

from skills._sdk.notebook import load_skill


def _parameters():
    return inspect.signature(load_skill("sc-pseudotime").pseudotime).parameters


def test_all_public_methods_are_recognized_before_input_validation():
    api = load_skill("sc-pseudotime")
    cells = ad.AnnData(np.ones((2, 2)))
    for method in ("dpt", "palantir", "via", "cellrank", "slingshot_r", "monocle3_r"):
        with pytest.raises(ValueError, match="missing from obs"):
            api.pseudotime(cells, method=method)
    with pytest.raises(ValueError, match="Unsupported pseudotime method"):
        api.pseudotime(cells, method="unknown")


def test_shared_selector_params_are_exposed():
    parameters = _parameters()
    assert {"use_rep", "root_cluster", "root_cell"} <= parameters.keys()
    assert inspect.signature(load_skill("sc-pseudotime").trajectory_genes).parameters["method"].default == "pearson"


def test_palantir_defaults_are_exposed():
    parameters = _parameters()
    expected = {"palantir_knn": 30, "palantir_n_components": 10,
                "palantir_num_waypoints": 1200, "palantir_max_iterations": 25}
    assert {key: parameters[key].default for key in expected} == expected


def test_via_defaults_are_exposed():
    parameters = _parameters()
    assert parameters["via_knn"].default == 30
    assert parameters["via_seed"].default is None
    assert parameters["random_state"].default == 20


def test_cellrank_defaults_are_exposed():
    parameters = _parameters()
    expected = {"cellrank_n_states": 3, "cellrank_schur_components": 20,
                "cellrank_frac_to_keep": 0.3, "cellrank_use_velocity": False}
    assert {key: parameters[key].default for key in expected} == expected


def test_slingshot_parameters_are_exposed():
    assert _parameters()["end_clusters"].default is None
