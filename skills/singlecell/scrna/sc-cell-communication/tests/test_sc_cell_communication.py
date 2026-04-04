"""Static contract tests for the sc-cell-communication skill."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_cell_communication.py").read_text(encoding="utf-8")


def test_method_registry_includes_cellphonedb():
    assert '"cellphonedb": MethodConfig(' in MODULE_TEXT
    assert 'description="CellPhoneDB statistical analysis with official Python backend"' in MODULE_TEXT


def test_cellphonedb_defaults_are_exposed():
    assert '"cellphonedb_counts_data": "hgnc_symbol"' in MODULE_TEXT
    assert '"cellphonedb_iterations": 1000' in MODULE_TEXT
    assert '"cellphonedb_threshold": 0.1' in MODULE_TEXT
    assert '"cellphonedb_threads": 4' in MODULE_TEXT
    assert '"cellphonedb_pvalue": 0.05' in MODULE_TEXT


def test_nichenet_registry_and_cli_are_exposed():
    assert '"nichenet_r": MethodConfig(' in MODULE_TEXT
    assert '--condition-key' in MODULE_TEXT
    assert '--receiver' in MODULE_TEXT
    assert '--senders' in MODULE_TEXT
