"""Tests for the spatial-cnv skill."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_cnv.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "cnv_out"


def test_demo_mode(tmp_output):
    """spatial-cnv --demo should run without error."""
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
    assert (tmp_output / "tables" / "cnv_scores.csv").exists()
    assert (tmp_output / "tables" / "cnv_run_summary.csv").exists()
    assert (tmp_output / "reproducibility" / "commands.sh").exists()


def test_demo_outputs_gallery_contract(tmp_output):
    """Demo mode should export gallery manifests, figure data, and the R helper."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "cnv_scores.csv").exists()
    assert (tmp_output / "figure_data" / "cnv_run_summary.csv").exists()
    assert (tmp_output / "figure_data" / "cnv_spatial_points.csv").exists()
    assert (tmp_output / "figure_data" / "cnv_umap_points.csv").exists()
    assert (tmp_output / "figure_data" / "cnv_bin_summary.csv").exists()
    assert (tmp_output / "tables" / "cnv_bin_summary.csv").exists()
    assert (tmp_output / "reproducibility" / "r_visualization.sh").exists()


def test_demo_gallery_manifests_have_roles(tmp_output):
    """The standard CNV gallery should emit figure and figure-data manifests."""
    import json

    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    figures_manifest = json.loads((tmp_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((tmp_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-cnv-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-cnv"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-cnv-gallery"


def test_demo_report_content(tmp_output):
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "CNV" in report
    assert "Visualization Outputs" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    import json

    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-cnv"
    assert "summary" in data
    assert data["summary"]["n_cells"] > 0


def test_demo_accepts_infercnv_flags(tmp_output):
    """CLI should accept the method-specific inferCNVpy flags exposed in SKILL.md."""
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--demo",
            "--infercnv-lfc-clip",
            "2.5",
            "--infercnv-dynamic-threshold",
            "1.2",
            "--infercnv-exclude-chromosomes",
            "chrX",
            "chrY",
            "--infercnv-chunksize",
            "2000",
            "--infercnv-n-jobs",
            "1",
            "--output",
            str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
