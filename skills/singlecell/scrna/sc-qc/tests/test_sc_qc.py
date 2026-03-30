"""Tests for the sc-qc skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_qc.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_qc_out"


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "qc_metrics_summary.csv").exists()
    assert (tmp_output / "tables" / "qc_metrics_per_cell.csv").exists()
    assert (tmp_output / "reproducibility" / "analysis_notebook.ipynb").exists()
    assert (tmp_output / "reproducibility" / "requirements.txt").exists()
    assert not (tmp_output / "reproducibility" / "environment.txt").exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "sc-qc"
    assert data["data"]["params"] == {"species": "human"}
    assert data["data"]["effective_params"]["species"] == "human"
    assert data["data"]["effective_params"]["calculate_ribo"] is True
    assert data["data"]["visualization"]["recipe_id"] == "standard-sc-qc-gallery"
    assert "qc_metrics_summary" in data["data"]["visualization"]["available_figure_data"]
    command_text = (tmp_output / "reproducibility" / "commands.sh").read_text()
    assert "--calculate-ribo" not in command_text
