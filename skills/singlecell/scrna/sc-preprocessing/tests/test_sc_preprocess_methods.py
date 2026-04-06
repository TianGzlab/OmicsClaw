"""Static method-contract tests for sc-preprocessing."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_preprocess.py").read_text(encoding="utf-8")


def test_method_registry_includes_pearson_residuals():
    assert '"pearson_residuals": MethodConfig(' in MODULE_TEXT
    assert 'description="Scanpy Pearson residual workflow"' in MODULE_TEXT


def test_pearson_defaults_are_exposed():
    assert '"pearson_residuals": {' in MODULE_TEXT
    assert '"pearson_hvg_flavor": "seurat_v3"' in MODULE_TEXT
    assert '"pearson_theta": 100.0' in MODULE_TEXT


def test_method_specific_cli_args_are_exposed():
    assert '"--normalization-target-sum"' in MODULE_TEXT
    assert '"--scanpy-hvg-flavor"' in MODULE_TEXT
    assert '"--pearson-theta"' in MODULE_TEXT
    assert '"--seurat-normalize-method"' in MODULE_TEXT
    assert '"--seurat-scale-factor"' in MODULE_TEXT
    assert '"--seurat-hvg-method"' in MODULE_TEXT
    assert '"--sctransform-regress-mt"' in MODULE_TEXT
