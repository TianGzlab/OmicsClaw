"""Static method-contract tests for sc-pseudotime."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_pseudotime.py").read_text(encoding="utf-8")


def test_method_registry_includes_all_public_methods():
    for method in ("dpt", "palantir", "via", "cellrank", "slingshot_r"):
        assert f'"{method}": MethodConfig(' in MODULE_TEXT


def test_shared_selector_params_are_exposed():
    assert '"use_rep"' in MODULE_TEXT
    assert '"root_cluster"' in MODULE_TEXT
    assert '"root_cell"' in MODULE_TEXT
    assert '"corr_method"' in MODULE_TEXT


def test_palantir_defaults_are_exposed():
    assert '"palantir_knn": 30' in MODULE_TEXT
    assert '"palantir_n_components": 10' in MODULE_TEXT
    assert '"palantir_num_waypoints": 1200' in MODULE_TEXT
    assert '"palantir_max_iterations": 25' in MODULE_TEXT


def test_via_defaults_are_exposed():
    assert '"via_knn": 30' in MODULE_TEXT
    assert '"via_seed": 20' in MODULE_TEXT


def test_cellrank_defaults_are_exposed():
    assert '"cellrank_n_states": 3' in MODULE_TEXT
    assert '"cellrank_schur_components": 20' in MODULE_TEXT
    assert '"cellrank_frac_to_keep": 0.3' in MODULE_TEXT
    assert '"cellrank_use_velocity": False' in MODULE_TEXT


def test_slingshot_parameters_are_exposed():
    assert '"end_clusters"' in MODULE_TEXT
    assert 'description="Slingshot lineage inference through the R bridge"' in MODULE_TEXT
