"""Static method-contract tests for sc-preprocessing."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_preprocess.py").read_text(encoding="utf-8")


def test_method_registry_includes_pearson_residuals():
    assert '"pearson_residuals": MethodConfig(' in MODULE_TEXT
    assert 'description="Scanpy Pearson residual workflow"' in MODULE_TEXT


def test_pearson_defaults_are_exposed():
    assert '"pearson_residuals": {' in MODULE_TEXT
    assert '"hvg_flavor": "seurat_v3"' in MODULE_TEXT
    assert '"pearson_theta": 100.0' in MODULE_TEXT
