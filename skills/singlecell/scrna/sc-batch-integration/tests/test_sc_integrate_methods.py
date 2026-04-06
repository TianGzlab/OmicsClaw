"""Static method-contract tests for sc-batch-integration."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_integrate.py").read_text(encoding="utf-8")


def test_method_specific_cli_args_are_exposed():
    assert '"--n-latent"' in MODULE_TEXT
    assert '"--labels-key"' in MODULE_TEXT
    assert '"--harmony-theta"' in MODULE_TEXT
    assert '"--bbknn-neighbors-within-batch"' in MODULE_TEXT
    assert '"--scanorama-knn"' in MODULE_TEXT
    assert '"--integration-features"' in MODULE_TEXT
    assert '"--integration-pcs"' in MODULE_TEXT
