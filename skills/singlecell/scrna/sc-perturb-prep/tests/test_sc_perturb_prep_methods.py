"""Static method-contract tests for sc-perturb-prep."""

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_perturb_prep.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")


def test_mapping_tsv_flags_are_exposed():
    assert "--mapping-file" in MODULE_TEXT
    assert "--control-patterns" in MODULE_TEXT
    assert "`mapping_tsv`" in SKILL_TEXT


def test_output_is_processed_h5ad():
    """Output must use canonical name processed.h5ad."""
    assert 'output_dir / "processed.h5ad"' in MODULE_TEXT


def test_contract_metadata_via_canonicalize():
    """Must write contract metadata via canonicalize_singlecell_adata."""
    assert "canonicalize_singlecell_adata" in MODULE_TEXT
    assert "omicsclaw_matrix_contract" in MODULE_TEXT


def test_degenerate_detection_exists():
    """Must detect degenerate output (zero assigned, all control, single perturbation)."""
    assert "zero_assigned" in MODULE_TEXT
    assert "all_control" in MODULE_TEXT
    assert "single_perturbation" in MODULE_TEXT
    assert "suggested_actions" in MODULE_TEXT


def test_figure_data_dir():
    """Must create figure_data directory."""
    assert "figure_data" in MODULE_TEXT


def test_reproducibility():
    """Must write reproducibility/commands.sh."""
    assert "commands.sh" in MODULE_TEXT


def test_skill_md_matrix_expectations():
    """SKILL.md must declare matrix expectations and workflow."""
    assert "raw counts" in SKILL_TEXT.lower() or "raw_counts" in SKILL_TEXT
    assert "Upstream Step" in SKILL_TEXT or "upstream" in SKILL_TEXT.lower()
    assert "Workflow" in SKILL_TEXT
    assert "Downstream Step" in SKILL_TEXT or "downstream" in SKILL_TEXT.lower()
