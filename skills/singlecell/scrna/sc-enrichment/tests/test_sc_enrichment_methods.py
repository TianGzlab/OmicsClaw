"""Static method-contract tests for sc-enrichment."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_enrichment.py").read_text(encoding="utf-8")


def test_method_registry_includes_aucell():
    assert '"aucell_r": MethodConfig(' in MODULE_TEXT
    assert 'description="AUCell gene-set activity scoring using the official Bioconductor package"' in MODULE_TEXT


def test_aucell_defaults_are_exposed():
    assert '"groupby": "leiden"' in MODULE_TEXT
    assert '"top_pathways": 20' in MODULE_TEXT
    assert '"aucell_auc_max_rank": None' in MODULE_TEXT
