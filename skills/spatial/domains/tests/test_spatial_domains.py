"""Tests for the spatial-domains skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_domains.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "domains_out"


def test_demo_mode(tmp_output):
    """spatial-domains --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
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
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Spatial Domain Identification Report" in report
    assert "Disclaimer" in report
    assert "Domain" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-domains"
    assert "summary" in data
    assert data["summary"]["n_domains"] > 0


def test_demo_figures(tmp_output):
    """Demo mode should produce spatial domain figures."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    figures_dir = tmp_output / "figures"
    assert figures_dir.exists()
    assert (figures_dir / "spatial_domains.png").exists()
    assert (figures_dir / "umap_domains.png").exists()


def test_demo_tables(tmp_output):
    """Demo mode should produce domain summary table."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert (tmp_output / "tables" / "domain_summary.csv").exists()
