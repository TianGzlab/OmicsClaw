"""Tests for the spatial-velocity skill."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_velocity.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "velo_out"


def test_demo_mode(tmp_output):
    """spatial-velocity --demo should run without error."""
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
    assert "Velocity" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    import json

    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-velocity"
    assert "summary" in data
    summary = data["summary"]
    assert summary["n_cells"] > 0
    assert "mean_speed" in summary
    assert "median_speed" in summary


def test_demo_tables(tmp_output):
    """velocity_speed table should be written; confidence/pseudotime when available."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    tables_dir = tmp_output / "tables"
    assert tables_dir.exists()
    assert (tables_dir / "velocity_speed.csv").exists()


def test_demo_reproducibility(tmp_output):
    """Reproducibility artefacts should be present."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    repro_dir = tmp_output / "reproducibility"
    assert repro_dir.exists()
    assert (repro_dir / "commands.sh").exists()
    assert (repro_dir / "requirements.txt").exists()
    reqs = (repro_dir / "requirements.txt").read_text()
    assert "scvelo" in reqs
