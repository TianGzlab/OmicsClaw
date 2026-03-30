"""Tests for the spatial-velocity skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_velocity.py"


def _run_skill(output_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), *args, "--output", str(output_dir)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "velocity_out"


@pytest.fixture(scope="module")
def demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_velocity_demo")
    result = _run_skill(output_dir, "--demo")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


def test_demo_mode(demo_output):
    """spatial-velocity --demo should run without error."""
    assert (demo_output / "report.md").exists()
    assert (demo_output / "result.json").exists()
    assert (demo_output / "processed.h5ad").exists()
    assert (demo_output / "tables" / "cell_velocity_metrics.csv").exists()
    assert (demo_output / "tables" / "gene_velocity_summary.csv").exists()
    assert (demo_output / "tables" / "velocity_gene_hits.csv").exists()


def test_demo_outputs_gallery_contract(demo_output):
    """Demo mode should export gallery manifests, figure data, and the R helper."""
    assert (demo_output / "figures" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "velocity_summary.csv").exists()
    assert (demo_output / "figure_data" / "velocity_cell_metrics.csv").exists()
    assert (demo_output / "figure_data" / "velocity_gene_summary.csv").exists()
    assert (demo_output / "figure_data" / "velocity_gene_hits.csv").exists()
    assert (demo_output / "figure_data" / "velocity_cluster_summary.csv").exists()
    assert (demo_output / "figure_data" / "velocity_top_cells.csv").exists()
    assert (demo_output / "figure_data" / "velocity_top_genes.csv").exists()
    assert (demo_output / "figure_data" / "velocity_run_summary.csv").exists()
    assert (demo_output / "figure_data" / "velocity_spatial_points.csv").exists()
    assert (demo_output / "figure_data" / "velocity_umap_points.csv").exists()
    assert (demo_output / "reproducibility" / "r_visualization.sh").exists()
    assert (demo_output / "reproducibility" / "requirements.txt").exists()
    assert (demo_output / "reproducibility" / "environment.txt").exists()

    run_summary = (demo_output / "figure_data" / "velocity_run_summary.csv").read_text()
    assert "pseudotime_key" in run_summary
    assert "cluster_mean_speed_column" in run_summary


def test_demo_gallery_manifests_have_roles(demo_output):
    """The standard velocity gallery should emit figure and figure-data manifests."""
    figures_manifest = json.loads((demo_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((demo_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-velocity-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-velocity"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-velocity-gallery"


def test_demo_processed_h5ad_persists_gallery_annotations(demo_output):
    """Gallery-derived cluster metrics should be written back into AnnData."""
    import scanpy as sc

    adata = sc.read_h5ad(demo_output / "processed.h5ad")
    assert "velocity_speed" in adata.obs.columns
    assert "velocity_cluster_mean_speed" in adata.obs.columns
    assert "velocity_cluster_mean_confidence" in adata.obs.columns
    assert "velocity_cluster_mean_pseudotime" in adata.obs.columns


def test_demo_report_content(demo_output):
    """Report should contain expected sections."""
    report = (demo_output / "report.md").read_text()
    assert "Spatial RNA Velocity Report" in report
    assert "Cluster Velocity Summary" in report
    assert "Visualization Outputs" in report
    assert "Disclaimer" in report


def test_demo_result_json(demo_output):
    """result.json should contain expected keys."""
    data = json.loads((demo_output / "result.json").read_text())
    assert data["skill"] == "spatial-velocity"
    assert data["summary"]["method"] == "stochastic"
    assert data["summary"]["engine"] == "scvelo"
    assert data["summary"]["n_cells"] > 0
    assert data["summary"]["has_velocity_pseudotime"] is True
    assert "visualization" in data["data"]
    assert data["data"]["visualization"]["pseudotime_key"] == "velocity_pseudotime"
    assert data["data"]["visualization"]["cluster_mean_speed_column"] == "velocity_cluster_mean_speed"


def test_deterministic_custom_flags_are_recorded(tmp_output):
    """Deterministic runs should honor and report the new scVelo controls."""
    out = tmp_output.parent / "velocity_deterministic"
    result = _run_skill(
        out,
        "--demo",
        "--method",
        "deterministic",
        "--velocity-fit-offset",
        "--velocity-min-r2",
        "0.02",
        "--velocity-min-likelihood",
        "0.005",
        "--velocity-graph-n-neighbors",
        "12",
        "--no-velocity-graph-approx",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    data = json.loads((out / "result.json").read_text())
    summary = data["summary"]
    params = data["data"]["params"]
    assert summary["method"] == "deterministic"
    assert summary["engine"] == "scvelo"
    assert summary["graph_params"]["n_neighbors"] == 12
    assert summary["model_params"]["fit_offset"] is True
    assert summary["model_params"]["min_r2"] == pytest.approx(0.02)
    assert summary["model_params"]["min_likelihood"] == pytest.approx(0.005)
    assert params["velocity_graph_approx"] is False
    assert data["data"]["visualization"]["cluster_mean_speed_column"] == "velocity_cluster_mean_speed"

    commands = (out / "reproducibility" / "commands.sh").read_text()
    assert "--velocity-fit-offset" in commands
    assert "--velocity-min-r2 0.02" in commands
    assert "--no-velocity-graph-approx" in commands


def test_dynamical_lightweight_demo_exports_latent_time(tmp_output):
    """Lightweight dynamical runs should complete and expose latent-time metadata."""
    out = tmp_output.parent / "velocity_dynamical"
    result = _run_skill(
        out,
        "--demo",
        "--method",
        "dynamical",
        "--dynamical-n-top-genes",
        "20",
        "--dynamical-max-iter",
        "2",
        "--dynamical-n-jobs",
        "1",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    data = json.loads((out / "result.json").read_text())
    summary = data["summary"]
    assert summary["method"] == "dynamical"
    assert summary["engine"] == "scvelo"
    assert summary["has_latent_time"] is True
    assert summary["model_params"]["dynamical_n_top_genes"] == 20
    assert summary["model_params"]["dynamical_max_iter"] == 2
    assert summary["model_params"]["dynamical_n_jobs"] == 1
    assert data["data"]["visualization"]["latent_time_key"] == "latent_time"

    cell_table = (out / "tables" / "cell_velocity_metrics.csv").read_text()
    assert "latent_time" in cell_table
    run_summary = (out / "figure_data" / "velocity_run_summary.csv").read_text()
    assert "latent_time_key" in run_summary
