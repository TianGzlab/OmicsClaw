"""Tests for the spatial-preprocess skill."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_preprocess.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _load_skill_module():
    spec = importlib.util.spec_from_file_location("spatial_preprocess", SKILL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    return tmp_path / "preprocess_out"


@pytest.fixture(scope="module")
def demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_preprocess_demo")
    result = _run_skill(output_dir, "--demo")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


def test_demo_mode(demo_output):
    """spatial-preprocess --demo should run without error."""
    assert (demo_output / "report.md").exists()
    assert (demo_output / "result.json").exists()
    assert (demo_output / "processed.h5ad").exists()
    assert (demo_output / "figures").exists()
    assert (demo_output / "tables" / "cluster_summary.csv").exists()
    assert (demo_output / "tables" / "qc_summary.csv").exists()
    assert (demo_output / "tables" / "pca_variance_ratio.csv").exists()
    assert (demo_output / "reproducibility" / "commands.sh").exists()


def test_demo_outputs_gallery_contract(demo_output):
    """Demo mode should export gallery manifests, figure data, and the R helper."""
    assert (demo_output / "figures" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "cluster_summary.csv").exists()
    assert (demo_output / "figure_data" / "qc_metric_distributions.csv").exists()
    assert (demo_output / "figure_data" / "preprocess_run_summary.csv").exists()
    assert (demo_output / "figure_data" / "pca_variance_ratio.csv").exists()
    assert (demo_output / "figure_data" / "preprocess_spatial_points.csv").exists()
    assert (demo_output / "figure_data" / "preprocess_umap_points.csv").exists()
    assert (demo_output / "reproducibility" / "r_visualization.sh").exists()

    run_summary = (demo_output / "figure_data" / "preprocess_run_summary.csv").read_text()
    assert "n_pcs_used" in run_summary
    assert "leiden_resolution" in run_summary


def test_demo_gallery_manifests_have_roles(demo_output):
    """The standard preprocess gallery should emit figure and figure-data manifests."""
    figures_manifest = json.loads((demo_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((demo_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-preprocess-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-preprocess"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-preprocess-gallery"


def test_demo_processed_h5ad_persists_preprocess_state(demo_output):
    """Processed AnnData should keep the stable preprocessing objects used by the gallery."""
    import scanpy as sc

    adata = sc.read_h5ad(demo_output / "processed.h5ad")
    assert "counts" in adata.layers
    assert adata.raw is not None
    assert "X_pca" in adata.obsm
    assert "X_umap" in adata.obsm
    assert "leiden" in adata.obs.columns
    assert "highly_variable" in adata.var.columns


def test_demo_report_content(demo_output):
    """Report should contain the upgraded visualization contract sections."""
    report = (demo_output / "report.md").read_text()
    assert "Spatial Preprocessing Report" in report
    assert "Interpretation Notes" in report
    assert "Visualization Outputs" in report
    assert "Disclaimer" in report


def test_demo_result_json(demo_output):
    """result.json should contain visualization metadata for downstream tools."""
    data = json.loads((demo_output / "result.json").read_text())
    assert data["skill"] == "spatial-preprocess"
    assert "summary" in data
    assert data["summary"]["n_clusters"] > 0
    assert "visualization" in data["data"]
    assert data["data"]["visualization"]["recipe_id"] == "standard-spatial-preprocess-gallery"
    assert data["data"]["visualization"]["cluster_column"] == "leiden"
    assert data["data"]["visualization"]["counts_layer"] == "counts"


def test_collect_run_configuration_with_resolutions():
    """Preprocess config collection should keep the current single-workflow contract explicit."""
    module = _load_skill_module()

    args = argparse.Namespace(
        data_type="visium",
        species="human",
        min_genes=200,
        min_cells=3,
        max_mt_pct=15.0,
        max_genes=5000,
        tissue="brain",
        n_top_hvg=3000,
        n_pcs=30,
        n_neighbors=20,
        leiden_resolution=0.6,
        resolutions="0.4,0.8,1.0",
    )

    params, resolutions = module._collect_run_configuration(args)

    assert params["data_type"] == "visium"
    assert params["tissue"] == "brain"
    assert params["resolutions"] == "0.4,0.8,1.0"
    assert resolutions == [0.4, 0.8, 1.0]


def test_write_report_records_effective_params(tmp_path):
    """Reports, tables, and reproducibility outputs should use the upgraded contract."""
    module = _load_skill_module()

    summary = {
        "method": "scanpy_standard",
        "n_cells_raw": 100,
        "n_genes_raw": 5000,
        "n_cells_filtered": 80,
        "n_genes_filtered": 4000,
        "n_hvg": 2000,
        "n_clusters": 5,
        "has_spatial": True,
        "cluster_sizes": {"0": 30, "1": 20, "2": 15, "3": 10, "4": 5},
        "n_pcs_computed": 30,
        "n_pcs_used": 30,
        "n_pcs_suggested": 22,
        "tissue_preset": "brain",
        "multi_resolution": {"0.4": 4, "0.8": 7},
        "effective_params": {
            "species": "human",
            "tissue_preset": "brain",
            "min_genes": 200,
            "min_cells": 0,
            "max_mt_pct": 10,
            "max_genes": 6000,
            "n_top_hvg": 2000,
            "n_hvg_selected": 2000,
            "n_pcs_requested": 30,
            "n_pcs_computed": 30,
            "n_pcs_used": 30,
            "n_pcs_suggested": 22,
            "n_neighbors": 15,
            "leiden_resolution": 0.5,
            "normalize_target_sum": 10000.0,
            "hvg_flavor": "seurat_v3",
            "leiden_flavor": "igraph",
            "resolutions": [0.4, 0.8],
        },
    }
    params = {
        "data_type": "visium",
        "species": "human",
        "min_genes": 0,
        "min_cells": 0,
        "max_mt_pct": 20.0,
        "max_genes": 0,
        "n_top_hvg": 2000,
        "n_pcs": 30,
        "n_neighbors": 15,
        "leiden_resolution": 0.5,
        "tissue": "brain",
        "resolutions": "0.4,0.8",
    }
    gallery_context = {
        "cluster_col": "leiden",
        "spatial_key": "spatial",
        "multi_resolution_columns": ["leiden_res_0.4", "leiden_res_0.8"],
        "qc_metric_cols": ["n_genes_by_counts", "total_counts", "pct_counts_mt"],
        "obsm_keys": {"X_umap", "spatial"},
        "layer_keys": {"counts"},
        "var_keys": {"highly_variable"},
        "cluster_summary_df": module._build_cluster_summary_table(summary),
        "multi_resolution_df": module._build_multi_resolution_table(summary),
        "pca_variance_df": module.pd.DataFrame(
            {
                "pc": [1, 2, 3],
                "variance_ratio": [0.2, 0.15, 0.1],
                "cumulative_variance_ratio": [0.2, 0.35, 0.45],
                "variance": [2.0, 1.5, 1.0],
            }
        ),
    }

    module.export_tables(tmp_path, summary, gallery_context=gallery_context)
    module.write_report(tmp_path, summary, None, params, gallery_context=gallery_context)
    module.write_reproducibility(tmp_path, params, summary, input_file=None, demo_mode=False)

    report = (tmp_path / "report.md").read_text()
    assert "Effective Method Parameters" in report
    assert "Visualization Outputs" in report
    assert "`max_mt_pct`: 10" in report

    result = json.loads((tmp_path / "result.json").read_text())
    assert result["skill"] == "spatial-preprocess"
    assert result["data"]["visualization"]["recipe_id"] == "standard-spatial-preprocess-gallery"
    assert result["data"]["visualization"]["counts_layer"] == "counts"

    commands = (tmp_path / "reproducibility" / "commands.sh").read_text()
    assert "--max-mt-pct 10" in commands
    assert "--tissue brain" in commands
    assert "--resolutions 0.4,0.8" in commands

    assert (tmp_path / "tables" / "qc_summary.csv").exists()
    assert (tmp_path / "tables" / "multi_resolution_summary.csv").exists()
    assert (tmp_path / "reproducibility" / "r_visualization.sh").exists()
