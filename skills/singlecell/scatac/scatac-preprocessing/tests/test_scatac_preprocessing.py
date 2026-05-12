"""Tests for the scatac-preprocessing skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "scatac_preprocessing.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "scatac_preprocess_out"


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert not (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "preprocess_summary.csv").exists()
    assert (tmp_output / "tables" / "cluster_summary.csv").exists()
    assert (tmp_output / "tables" / "peak_summary.csv").exists()
    assert (tmp_output / "tables" / "lsi_variance_ratio.csv").exists()
    assert (tmp_output / "tables" / "qc_metrics_per_cell.csv").exists()
    assert (tmp_output / "processed.h5ad").exists()
    assert not (tmp_output / "reproducibility" / "analysis_notebook.ipynb").exists()
    assert (tmp_output / "reproducibility" / "requirements.txt").exists()
    assert not (tmp_output / "reproducibility" / "environment.txt").exists()


def test_demo_report_content(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
        check=False,
    )
    report = (tmp_output / "report.md").read_text()
    assert "scATAC" in report or "ATAC" in report
    assert "Default Gallery" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
        check=False,
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "scatac-preprocessing"
    assert "summary" in data
    assert data["data"]["params"]["method"] == "tfidf_lsi"
    assert data["data"]["effective_params"]["method"] == "tfidf_lsi"
    assert data["data"]["effective_params"]["peak_selection_metric"] == "total_counts"
    assert data["data"]["effective_params"]["raw_available"] is True
    assert data["data"]["visualization"]["recipe_id"] == "standard-scatac-preprocessing-gallery"
    assert "peak_summary" in data["data"]["visualization"]["available_figure_data"]
    command_text = (tmp_output / "reproducibility" / "commands.sh").read_text()
    assert "--method tfidf_lsi" in command_text


def test_demo_mode_respects_custom_params(tmp_output):
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--demo",
            "--min-peaks",
            "150",
            "--n-lsi",
            "20",
            "--n-neighbors",
            "10",
            "--output",
            str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["data"]["params"]["min_peaks"] == 150
    assert payload["data"]["params"]["n_lsi"] == 20
    assert payload["data"]["params"]["n_neighbors"] == 10
