"""Tests for the spatial-de skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_de.py"


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
    return tmp_path / "de_out"


@pytest.fixture(scope="module")
def demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_de_demo")
    result = _run_skill(output_dir, "--demo")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


@pytest.fixture(scope="module")
def pydeseq2_demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_de_pydeseq2_demo")
    result = _run_skill(
        output_dir,
        "--demo",
        "--method",
        "pydeseq2",
        "--groupby",
        "leiden",
        "--group1",
        "0",
        "--group2",
        "1",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


def test_demo_mode(demo_output):
    """spatial-de --demo should run without error."""
    assert (demo_output / "report.md").exists()
    assert (demo_output / "result.json").exists()
    assert (demo_output / "processed.h5ad").exists()
    assert (demo_output / "tables" / "markers_top.csv").exists()
    assert (demo_output / "tables" / "de_full.csv").exists()
    assert (demo_output / "tables" / "de_significant.csv").exists()
    assert (demo_output / "reproducibility" / "commands.sh").exists()


def test_demo_outputs_gallery_contract(demo_output):
    """Demo mode should export gallery manifests, figure data, and the R helper."""
    assert (demo_output / "figures" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "markers_top.csv").exists()
    assert (demo_output / "figure_data" / "top_de_hits.csv").exists()
    assert (demo_output / "figure_data" / "de_full.csv").exists()
    assert (demo_output / "figure_data" / "de_plot_points.csv").exists()
    assert (demo_output / "figure_data" / "de_significant.csv").exists()
    assert (demo_output / "figure_data" / "group_de_metrics.csv").exists()
    assert (demo_output / "figure_data" / "de_run_summary.csv").exists()
    assert (demo_output / "figure_data" / "sample_counts_by_group.csv").exists()
    assert (demo_output / "figure_data" / "skipped_sample_groups.csv").exists()
    assert (demo_output / "figure_data" / "de_spatial_points.csv").exists()
    assert (demo_output / "figure_data" / "de_umap_points.csv").exists()
    assert (demo_output / "reproducibility" / "r_visualization.sh").exists()

    run_summary = (demo_output / "figure_data" / "de_run_summary.csv").read_text()
    assert "fdr_threshold" in run_summary
    assert "log2fc_threshold" in run_summary


def test_demo_gallery_manifests_have_roles(demo_output):
    """The standard DE gallery should emit figure and figure-data manifests."""
    figures_manifest = json.loads((demo_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((demo_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-de-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-de"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-de-gallery"


def test_demo_processed_h5ad_persists_gallery_annotations(demo_output):
    """Gallery-derived group burden columns should be written back into AnnData."""
    import scanpy as sc

    adata = sc.read_h5ad(demo_output / "processed.h5ad")
    assert "de_group_n_significant" in adata.obs.columns
    assert "de_group_n_effect_hits" in adata.obs.columns
    assert "de_group_n_marker_hits" in adata.obs.columns


def test_demo_report_content(demo_output):
    """Report should contain expected sections."""
    report = (demo_output / "report.md").read_text()
    assert "Spatial Differential Expression Report" in report
    assert "Interpretation Notes" in report
    assert "Visualization Outputs" in report
    assert "Disclaimer" in report


def test_demo_result_json(demo_output):
    """result.json should contain expected keys."""
    data = json.loads((demo_output / "result.json").read_text())
    assert data["skill"] == "spatial-de"
    assert "summary" in data
    assert data["summary"]["n_groups"] > 0
    assert data["summary"]["method"] == "wilcoxon"
    assert "visualization" in data["data"]
    assert data["data"]["visualization"]["group_effect_column"] == "de_group_n_effect_hits"


def test_pydeseq2_demo_exports_sample_support(pydeseq2_demo_output):
    """PyDESeq2 mode should export sample-support data and the shared gallery contract."""
    data = json.loads((pydeseq2_demo_output / "result.json").read_text())
    assert data["summary"]["method"] == "pydeseq2"
    assert (pydeseq2_demo_output / "figure_data" / "sample_counts_by_group.csv").exists()
    assert (pydeseq2_demo_output / "figure_data" / "de_plot_points.csv").exists()
    assert (pydeseq2_demo_output / "figure_data" / "de_run_summary.csv").exists()


def test_demo_accepts_richer_scanpy_flags(tmp_output):
    """CLI should accept method-specific Scanpy tuning flags."""
    result = _run_skill(
        tmp_output,
        "--demo",
        "--method",
        "wilcoxon",
        "--groupby",
        "leiden",
        "--n-top-genes",
        "12",
        "--fdr-threshold",
        "0.1",
        "--log2fc-threshold",
        "0.5",
        "--scanpy-corr-method",
        "bonferroni",
        "--scanpy-rankby-abs",
        "--scanpy-pts",
        "--scanpy-tie-correct",
        "--filter-markers",
        "--min-in-group-fraction",
        "0.2",
        "--min-fold-change",
        "0.5",
        "--max-out-group-fraction",
        "0.8",
        "--filter-compare-abs",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_demo_accepts_pydeseq2_flags(tmp_output):
    """CLI should accept the richer PyDESeq2 tuning flags."""
    result = _run_skill(
        tmp_output,
        "--demo",
        "--method",
        "pydeseq2",
        "--groupby",
        "leiden",
        "--group1",
        "0",
        "--group2",
        "1",
        "--sample-key",
        "sample_id",
        "--min-cells-per-sample",
        "5",
        "--min-counts-per-gene",
        "5",
        "--fdr-threshold",
        "0.1",
        "--log2fc-threshold",
        "0.5",
        "--pydeseq2-fit-type",
        "parametric",
        "--pydeseq2-size-factors-fit-type",
        "ratio",
        "--pydeseq2-alpha",
        "0.1",
        "--pydeseq2-n-cpus",
        "1",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
