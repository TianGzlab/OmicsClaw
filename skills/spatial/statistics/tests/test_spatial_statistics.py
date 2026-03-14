"""Tests for the spatial-statistics skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_statistics.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "stats_out"


def test_demo_mode(tmp_output):
    """spatial-statistics --demo should run without error."""
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
    assert (tmp_output / "processed.h5ad").exists()


def test_demo_report_content(tmp_output):
    """Report should contain statistics sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Statistics" in report or "Enrichment" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-statistics"
    assert "summary" in data
    assert "n_clusters" in data["summary"] or "analysis_type" in data["summary"]


def test_ripley_analysis_type(tmp_output):
    """Running with --analysis-type ripley should also succeed."""
    ripley_out = tmp_output.parent / "stats_ripley"
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--demo", "--output", str(ripley_out),
            "--analysis-type", "ripley",
        ],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (ripley_out / "report.md").exists()
