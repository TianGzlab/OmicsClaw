"""Static method-contract tests for sc-in-silico-perturbation."""

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_in_silico_perturbation.py").read_text(encoding="utf-8")
SKILL_TEXT = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text(encoding="utf-8")


def test_sctenifoldknk_flags_are_exposed():
    assert "--ko-gene" in MODULE_TEXT
    assert "--n-net" in MODULE_TEXT
    assert "scTenifoldKnk" in SKILL_TEXT


def test_grn_ko_method_exposed():
    assert "grn_ko" in MODULE_TEXT
    assert "--method" in MODULE_TEXT
    assert "--n-top-genes" in MODULE_TEXT
    assert "--corr-threshold" in MODULE_TEXT


def test_input_contract_written():
    assert "ensure_input_contract" in MODULE_TEXT
    assert "omicsclaw_input_contract" in SKILL_TEXT or "omicsclaw_input_contract" in MODULE_TEXT


def test_matrix_contract_written():
    assert "propagate_singlecell_contracts" in MODULE_TEXT
    assert "omicsclaw_matrix_contract" in SKILL_TEXT or "omicsclaw_matrix_contract" in MODULE_TEXT


def test_processed_h5ad_output():
    assert "processed.h5ad" in MODULE_TEXT
    assert "save_h5ad" in MODULE_TEXT


def test_figures_manifest():
    assert "manifest.json" in MODULE_TEXT
    assert "_write_figures_manifest" in MODULE_TEXT


def test_figure_data_manifest():
    assert "figure_data" in MODULE_TEXT
    assert "_write_figure_data" in MODULE_TEXT


def test_degenerate_detection():
    assert "_check_degenerate" in MODULE_TEXT
    assert "suggested_actions" in MODULE_TEXT


def test_preflight_checks():
    assert "_preflight" in MODULE_TEXT
    assert "ko_gene" in MODULE_TEXT


def test_report_and_result():
    assert "report.md" in MODULE_TEXT
    assert "result.json" in MODULE_TEXT or "write_result_json" in MODULE_TEXT


def test_skill_md_has_method_table():
    assert "Method Selection Table" in SKILL_TEXT
    assert "grn_ko" in SKILL_TEXT
    assert "sctenifoldknk" in SKILL_TEXT


def test_skill_md_has_matrix_contract():
    assert "Matrix Contract" in SKILL_TEXT
    assert "raw_counts" in SKILL_TEXT


def test_skill_md_has_workflow():
    assert "Workflow" in SKILL_TEXT
    assert "Preflight" in SKILL_TEXT


def test_no_numba_disable_jit():
    assert "NUMBA_DISABLE_JIT" not in MODULE_TEXT
