"""Tests for the spatial-genes skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_genes.py"


def _run_skill(output_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), *args, "--output", str(output_dir)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "genes_out"


@pytest.fixture(scope="module")
def demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_genes_demo")
    result = _run_skill(output_dir, "--demo")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


def test_demo_mode(demo_output):
    """spatial-genes --demo should run without error."""
    assert (demo_output / "report.md").exists()
    assert (demo_output / "result.json").exists()
    assert (demo_output / "processed.h5ad").exists()
    assert (demo_output / "tables" / "svg_results.csv").exists()
    assert (demo_output / "tables" / "top_svg_scores.csv").exists()
    assert (demo_output / "tables" / "significant_svgs.csv").exists()
    assert (demo_output / "tables" / "svg_observation_metrics.csv").exists()
    assert (demo_output / "reproducibility" / "commands.sh").exists()
    assert (demo_output / "reproducibility" / "requirements.txt").exists()


def test_demo_outputs_gallery_contract(demo_output):
    """Demo mode should export gallery manifests, figure data, and the R helper."""
    assert (demo_output / "figures" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "svg_results.csv").exists()
    assert (demo_output / "figure_data" / "top_svg_scores.csv").exists()
    assert (demo_output / "figure_data" / "significant_svgs.csv").exists()
    assert (demo_output / "figure_data" / "svg_run_summary.csv").exists()
    assert (demo_output / "figure_data" / "svg_observation_metrics.csv").exists()
    assert (demo_output / "figure_data" / "top_svg_spatial_points.csv").exists()
    assert (demo_output / "figure_data" / "top_svg_umap_points.csv").exists()
    assert (demo_output / "reproducibility" / "r_visualization.sh").exists()

    run_summary = (demo_output / "figure_data" / "svg_run_summary.csv").read_text()
    assert "metric,value" in run_summary
    assert "fdr_threshold" in run_summary
    assert "n_genes_tested" in run_summary


def test_demo_gallery_manifests_have_roles(demo_output):
    """The standard gallery should emit figure and figure-data manifests."""
    figures_manifest = json.loads((demo_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((demo_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-svg-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-genes"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-svg-gallery"
    assert figure_data_manifest["available_files"]["svg_results"] == "svg_results.csv"
    assert figure_data_manifest["available_files"]["significant_svgs"] == "significant_svgs.csv"
    assert figure_data_manifest["available_files"]["observation_metrics"] == "svg_observation_metrics.csv"
    assert "mean_expression_col" in figure_data_manifest["metric_columns"]


def test_demo_processed_h5ad_persists_gallery_annotations(demo_output):
    """Gallery-derived observation metrics should be written back into AnnData."""
    import scanpy as sc

    adata = sc.read_h5ad(demo_output / "processed.h5ad")
    assert "svg_top_gene_mean_expression" in adata.obs.columns
    assert "svg_top_gene_max_expression" in adata.obs.columns
    assert "svg_top_gene_detected_count" in adata.obs.columns
    assert "svg_top_gene_dominant" in adata.obs.columns
    assert "spatial_genes_gallery" in adata.uns
    assert "gallery_genes" in adata.uns["spatial_genes_gallery"]


def test_demo_report_content(demo_output):
    """Report should contain the standardized SVG sections."""
    report = (demo_output / "report.md").read_text()
    assert "Spatially Variable Genes Report" in report
    assert "Top Spatially Variable Genes" in report
    assert "Interpretation Notes" in report
    assert "Visualization Outputs" in report
    assert "Disclaimer" in report


def test_demo_result_json(demo_output):
    """result.json should contain standardized summary and visualization keys."""
    data = json.loads((demo_output / "result.json").read_text())
    assert data["skill"] == "spatial-genes"
    assert "summary" in data
    assert data["summary"]["n_genes_tested"] > 0
    assert data["summary"]["method"] == "morans"
    assert "visualization" in data["data"]
    assert data["data"]["visualization"]["recipe_id"] == "standard-spatial-svg-gallery"
    assert data["data"]["visualization"]["mean_expression_col"] == "svg_top_gene_mean_expression"
    assert data["data"]["visualization"]["dominant_gene_col"] == "svg_top_gene_dominant"


def test_demo_accepts_richer_morans_flags(tmp_output):
    """CLI should accept the richer Moran's I tuning flags."""
    result = _run_skill(
        tmp_output,
        "--demo",
        "--method",
        "morans",
        "--n-top-genes",
        "12",
        "--fdr-threshold",
        "0.1",
        "--morans-coord-type",
        "generic",
        "--morans-n-neighs",
        "8",
        "--morans-n-perms",
        "0",
        "--morans-corr-method",
        "bonferroni",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
