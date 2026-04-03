"""Tests for the sc-fastq-qc skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_fastq_qc.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_fastq_qc_out"


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
    assert (tmp_output / "figures" / "fastq_q30_summary.png").exists()
    assert (tmp_output / "figures" / "per_base_quality.png").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "fastq_per_sample_summary.csv").exists()
    assert (tmp_output / "reproducibility" / "analysis_notebook.ipynb").exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["skill"] == "sc-fastq-qc"
    assert payload["summary"]["method"] == "fastqc"
    assert payload["summary"]["n_samples"] == 1
    assert "fastq_per_sample_summary" in payload["data"]["visualization"]["available_figure_data"]
