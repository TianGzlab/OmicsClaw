"""Tests for the orchestrator skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_orchestrator.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "orch_out"


# ---------------------------------------------------------------------------
# Demo / list
# ---------------------------------------------------------------------------


def test_demo_mode(tmp_output):
    """orchestrator --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()


def test_list_skills():
    """--list-skills should print all skills and exit 0."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--list-skills"],
        capture_output=True, text=True, timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "preprocess" in result.stdout
    assert "communication" in result.stdout
    assert "standard" in result.stdout


# ---------------------------------------------------------------------------
# Query routing
# ---------------------------------------------------------------------------


def test_route_svg(tmp_output):
    """Query about spatially variable genes → genes skill."""
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--query", "find spatially variable genes",
            "--output", str(tmp_output),
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "genes" in result.stdout

    data = json.loads((tmp_output / "result.json").read_text())
    assert data["summary"]["routed_to"] == "genes"


def test_route_communication(tmp_output):
    """Query about ligand receptor → communication skill."""
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--query", "run ligand receptor interaction analysis",
            "--output", str(tmp_output),
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["summary"]["routed_to"] == "communication"


def test_route_trajectory(tmp_output):
    """Query about pseudotime → trajectory skill."""
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--query", "compute diffusion pseudotime",
            "--output", str(tmp_output),
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["summary"]["routed_to"] == "trajectory"


def test_route_integration(tmp_output):
    """Query about batch correction → integrate skill."""
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--query", "perform batch correction on multiple samples",
            "--output", str(tmp_output),
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["summary"]["routed_to"] == "integrate"


def test_route_cnv(tmp_output):
    """Query about copy number variation → cnv skill."""
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--query", "detect copy number variations in tumor",
            "--output", str(tmp_output),
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["summary"]["routed_to"] == "cnv"


def test_route_enrichment(tmp_output):
    """Query about GSEA → enrichment skill."""
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--query", "pathway enrichment using GSEA",
            "--output", str(tmp_output),
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["summary"]["routed_to"] == "enrichment"


# ---------------------------------------------------------------------------
# File-based routing
# ---------------------------------------------------------------------------


def test_route_h5ad_file(tmp_output, tmp_path):
    """h5ad file extension → preprocess skill."""
    fake_h5ad = tmp_path / "data.h5ad"
    fake_h5ad.write_bytes(b"fake")  # just needs to exist in name
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--input", str(fake_h5ad),
            "--output", str(tmp_output),
        ],
        capture_output=True, text=True, timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["summary"]["routed_to"] == "preprocess"


# ---------------------------------------------------------------------------
# Demo report content
# ---------------------------------------------------------------------------


def test_demo_report_content(tmp_output):
    """Demo report should contain all expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=60,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Orchestrator" in report
    assert "Routing" in report
    assert "Disclaimer" in report
    assert "standard" in report  # named pipeline


def test_demo_result_json(tmp_output):
    """result.json should contain routing stats."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=60,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "orchestrator"
    assert "summary" in data
    assert data["summary"]["total_skills"] > 0
    assert data["summary"]["total_keywords"] > 0
    assert "named_pipelines" in data["summary"]
