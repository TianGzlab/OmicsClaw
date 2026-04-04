"""Static method-contract tests for sc-pseudotime."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_pseudotime.py").read_text(encoding="utf-8")


def test_method_registry_includes_palantir():
    assert '"palantir": MethodConfig(' in MODULE_TEXT
    assert 'description="Palantir pseudotime with diffusion maps and waypoint sampling"' in MODULE_TEXT


def test_palantir_defaults_are_exposed():
    assert '"palantir_knn": 30' in MODULE_TEXT
    assert '"palantir_num_waypoints": 1200' in MODULE_TEXT
    assert '"palantir_max_iterations": 25' in MODULE_TEXT
    assert '"palantir_seed": 20' in MODULE_TEXT


def test_method_registry_includes_via():
    assert '"via": MethodConfig(' in MODULE_TEXT
    assert 'description="VIA pseudotime with automatic terminal-state inference"' in MODULE_TEXT


def test_via_defaults_are_exposed():
    assert '"via_knn": 30' in MODULE_TEXT
    assert '"via_seed": 20' in MODULE_TEXT


def test_method_registry_includes_cellrank():
    assert '"cellrank": MethodConfig(' in MODULE_TEXT
    assert 'description="CellRank fate mapping with GPCCA on pseudotime/connectivity kernels"' in MODULE_TEXT


def test_cellrank_defaults_are_exposed():
    assert '"cellrank_n_states": 3' in MODULE_TEXT
    assert '"cellrank_schur_components": 20' in MODULE_TEXT
    assert '"cellrank_frac_to_keep": 0.3' in MODULE_TEXT
    assert '"cellrank_use_velocity": False' in MODULE_TEXT
