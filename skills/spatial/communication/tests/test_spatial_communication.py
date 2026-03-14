"""Tests for the spatial-communication skill."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_communication.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "comm_out"


def test_demo_mode(tmp_output):
    """spatial-communication --demo should run without error."""
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
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Cell-Cell Communication" in report
    assert "Disclaimer" in report
    assert "Method" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    import json

    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-communication"
    assert "summary" in data
    assert "n_interactions_tested" in data["summary"]
