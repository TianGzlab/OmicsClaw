"""Static method-contract tests for sc-pathway-scoring."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_pathway_scoring.py").read_text(encoding="utf-8")


def test_method_registry_includes_aucell():
    assert '"aucell_r": MethodConfig(' in MODULE_TEXT
    assert 'description="AUCell gene-set activity scoring using the official Bioconductor package"' in MODULE_TEXT


def test_method_registry_includes_score_genes():
    assert '"score_genes_py": MethodConfig(' in MODULE_TEXT
    assert 'description="Scanpy/Seurat-style module scoring on normalized expression"' in MODULE_TEXT


def test_defaults_are_exposed():
    assert '"groupby": None' in MODULE_TEXT
    assert '"top_pathways": 20' in MODULE_TEXT
    assert '"aucell_auc_max_rank": None' in MODULE_TEXT
    assert '"score_genes_ctrl_size": 50' in MODULE_TEXT
    assert '"score_genes_n_bins": 25' in MODULE_TEXT


def test_gene_set_db_support_is_exposed():
    assert 'parser.add_argument("--gene-set-db"' in MODULE_TEXT
    assert 'parser.add_argument("--species", default="human")' in MODULE_TEXT
    assert "GENE_SET_DB_ALIASES" in MODULE_TEXT
