"""Tests for the sc-de skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import anndata as ad
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_de.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_de_out"


def test_demo_mode(tmp_output):
    """sc-de --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()


def test_demo_report_content(tmp_output):
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Differential" in report or "Expression" in report or "DE" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "sc-de"
    assert "summary" in data


def test_logreg_demo_runs(tmp_output):
    """Logistic-regression DE should run in demo mode."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--method", "logreg", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    report = (tmp_output / "report.md").read_text()
    assert "logreg" in report


def test_processed_output_carries_contract_and_analysis(tmp_output):
    """processed.h5ad should persist matrix contract and DE analysis metadata."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    adata = ad.read_h5ad(tmp_output / "processed.h5ad")
    assert "omicsclaw_matrix_contract" in adata.uns
    assert "omicsclaw_input_contract" in adata.uns
    assert "omicsclaw_sc-de" in adata.uns
