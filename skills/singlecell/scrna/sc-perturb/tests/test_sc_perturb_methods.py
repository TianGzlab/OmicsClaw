"""Static method-contract tests for sc-perturb."""

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_perturb.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")


def test_mixscape_is_exposed():
    assert 'choices=["mixscape"]' in MODULE_TEXT
    assert '`mixscape`' in SKILL_TEXT
    assert "--pert-key" in SKILL_TEXT


def test_output_is_processed_h5ad():
    """Output must use canonical name processed.h5ad."""
    assert 'output_dir / "processed.h5ad"' in MODULE_TEXT


def test_contract_metadata_written():
    """Must write omicsclaw_input_contract and omicsclaw_matrix_contract."""
    assert "omicsclaw_input_contract" in MODULE_TEXT
    assert "omicsclaw_matrix_contract" in MODULE_TEXT


def test_degenerate_detection_exists():
    """Must detect degenerate output (all NP)."""
    assert "_detect_degenerate_output" in MODULE_TEXT
    assert "all_non_perturbed" in MODULE_TEXT
    assert "suggested_actions" in MODULE_TEXT


def test_figure_data_dir():
    """Must create figure_data directory."""
    assert "figure_data" in MODULE_TEXT


def test_reproducibility():
    """Must write reproducibility/commands.sh."""
    assert "commands.sh" in MODULE_TEXT


def test_skill_md_matrix_expectations():
    """SKILL.md must declare matrix expectations."""
    assert "normalized expression" in SKILL_TEXT.lower() or "raw counts" in SKILL_TEXT.lower()
    assert "Upstream Step" in SKILL_TEXT or "upstream" in SKILL_TEXT.lower()
    assert "Workflow" in SKILL_TEXT
