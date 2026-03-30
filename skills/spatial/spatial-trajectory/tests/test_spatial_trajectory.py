"""Tests for the spatial-trajectory skill."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_trajectory.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SKILL_SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT.parent))


def _load_skill_module():
    spec = importlib.util.spec_from_file_location("spatial_trajectory", SKILL_SCRIPT)
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
    return tmp_path / "traj_out"


@pytest.fixture(scope="module")
def demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_trajectory_demo")
    result = _run_skill(output_dir, "--demo")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


def test_demo_mode(demo_output):
    """spatial-trajectory --demo should run without error."""
    assert (demo_output / "report.md").exists()
    assert (demo_output / "result.json").exists()
    assert (demo_output / "processed.h5ad").exists()


def test_demo_outputs_gallery_contract(demo_output):
    """Demo mode should export gallery manifests, figure data, and the R helper."""
    assert (demo_output / "figures" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "trajectory_summary.csv").exists()
    assert (demo_output / "figure_data" / "trajectory_cluster_summary.csv").exists()
    assert (demo_output / "figure_data" / "trajectory_genes.csv").exists()
    assert (demo_output / "figure_data" / "trajectory_run_summary.csv").exists()
    assert (demo_output / "figure_data" / "trajectory_spatial_points.csv").exists()
    assert (demo_output / "figure_data" / "trajectory_umap_points.csv").exists()
    assert (demo_output / "figure_data" / "trajectory_diffmap_points.csv").exists()
    assert (demo_output / "reproducibility" / "r_visualization.sh").exists()
    assert (demo_output / "reproducibility" / "requirements.txt").exists()

    run_summary = (demo_output / "figure_data" / "trajectory_run_summary.csv").read_text()
    assert "pseudotime_key" in run_summary
    assert "cluster_mean_pt_column" in run_summary


def test_demo_gallery_manifests_have_roles(demo_output):
    """The standard trajectory gallery should emit figure and figure-data manifests."""
    figures_manifest = json.loads((demo_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((demo_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-trajectory-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-trajectory"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-trajectory-gallery"


def test_demo_processed_h5ad_persists_gallery_annotations(demo_output):
    """Gallery-derived cluster pseudotime columns should be written back into AnnData."""
    import scanpy as sc

    adata = sc.read_h5ad(demo_output / "processed.h5ad")
    assert "dpt_pseudotime" in adata.obs.columns
    assert "traj_cluster_mean_pt" in adata.obs.columns
    assert "traj_cluster_median_pt" in adata.obs.columns


def test_demo_report_content(demo_output):
    """Report should contain expected trajectory sections."""
    report = (demo_output / "report.md").read_text()
    assert "Spatial Trajectory Report" in report
    assert "Interpretation Notes" in report
    assert "Visualization Outputs" in report
    assert "Disclaimer" in report


def test_demo_result_json(demo_output):
    """result.json should contain expected keys."""
    data = json.loads((demo_output / "result.json").read_text())
    assert data["skill"] == "spatial-trajectory"
    assert "summary" in data
    assert data["summary"]["method"] == "dpt"
    assert data["summary"]["n_cells"] > 0
    assert "visualization" in data["data"]
    assert data["data"]["visualization"]["pseudotime_key"] == "dpt_pseudotime"
    assert data["data"]["visualization"]["cluster_mean_pt_column"] == "traj_cluster_mean_pt"


def test_collect_run_configuration_palantir():
    """Only Palantir parameters should enter a Palantir reproducibility config."""
    module = _load_skill_module()

    args = argparse.Namespace(
        method="palantir",
        cluster_key="leiden",
        root_cell=None,
        root_cell_type="progenitor",
        dpt_n_dcs=8,
        cellrank_n_states=4,
        cellrank_schur_components=12,
        cellrank_frac_to_keep=0.2,
        cellrank_use_velocity=True,
        palantir_n_components=12,
        palantir_knn=25,
        palantir_num_waypoints=500,
        palantir_max_iterations=30,
    )

    params, method_kwargs = module._collect_run_configuration(args)

    assert params == {
        "method": "palantir",
        "cluster_key": "leiden",
        "root_cell": None,
        "root_cell_type": "progenitor",
        "palantir_n_components": 12,
        "palantir_knn": 25,
        "palantir_num_waypoints": 500,
        "palantir_max_iterations": 30,
    }
    assert method_kwargs == {
        "palantir_n_components": 12,
        "palantir_knn": 25,
        "palantir_num_waypoints": 500,
        "palantir_max_iterations": 30,
    }


def test_write_report_records_effective_params(tmp_path):
    """Report, JSON, tables, and reproducibility outputs should keep method-specific params only."""
    module = _load_skill_module()

    summary = {
        "method": "cellrank",
        "n_cells": 100,
        "n_genes": 30,
        "cluster_key": "leiden",
        "root_cell": "cell_0",
        "root_cell_type": None,
        "pseudotime_key": "dpt_pseudotime",
        "mean_pseudotime": 0.4,
        "max_pseudotime": 1.0,
        "n_finite": 100,
        "per_cluster": {
            "0": {"mean_pseudotime": 0.2, "median_pseudotime": 0.2, "n_cells": 50},
            "1": {"mean_pseudotime": 0.6, "median_pseudotime": 0.6, "n_cells": 50},
        },
        "trajectory_genes": pd.DataFrame(
            {
                "gene": ["GeneA", "GeneB"],
                "correlation": [0.7, -0.6],
                "pvalue": [1e-5, 2e-4],
                "fdr": [1e-4, 3e-4],
                "direction": ["increasing", "decreasing"],
            }
        ),
        "n_trajectory_genes": 2,
        "kernel_mode": "pseudotime+connectivity",
        "macrostate_key": "macrostates_fwd",
        "lineage_key": "lineages_fwd",
        "n_macrostates": 3,
        "terminal_states": ["state_1", "state_2"],
        "driver_genes": {"state_1": ["GeneA", "GeneC"]},
        "effective_params": {
            "cluster_key": "leiden",
            "root_cell": "cell_0",
            "dpt_n_dcs": 8,
            "cellrank_n_states": 4,
            "cellrank_schur_components": 12,
            "cellrank_frac_to_keep": 0.2,
            "cellrank_use_velocity": False,
        },
    }
    params = {
        "method": "cellrank",
        "cluster_key": "leiden",
        "root_cell": "cell_0",
        "root_cell_type": None,
        "dpt_n_dcs": 8,
        "cellrank_n_states": 4,
        "cellrank_schur_components": 12,
        "cellrank_frac_to_keep": 0.2,
        "cellrank_use_velocity": False,
    }
    gallery_context = {
        "pseudotime_key": "dpt_pseudotime",
        "cluster_mean_pt_col": "traj_cluster_mean_pt",
        "cluster_median_pt_col": "traj_cluster_median_pt",
        "terminal_states_df": pd.DataFrame({"rank": [1, 2], "terminal_state": ["state_1", "state_2"]}),
        "driver_genes_df": pd.DataFrame(
            {"terminal_state": ["state_1", "state_1"], "rank": [1, 2], "gene": ["GeneA", "GeneC"]}
        ),
        "cluster_summary_df": pd.DataFrame(
            [
                {"cluster": "0", "mean_pseudotime": 0.2, "median_pseudotime": 0.2, "n_cells": 50},
                {"cluster": "1", "mean_pseudotime": 0.6, "median_pseudotime": 0.6, "n_cells": 50},
            ]
        ),
        "fate_prob_df": pd.DataFrame(),
        "entropy_key": None,
    }

    module.export_tables(tmp_path, summary, gallery_context=gallery_context)
    module.write_report(tmp_path, summary, None, params, gallery_context=gallery_context)
    module.write_reproducibility(tmp_path, summary, params, None, demo_mode=False)

    report = (tmp_path / "report.md").read_text()
    assert "Effective Method Parameters" in report
    assert "`cellrank_n_states`: 4" in report
    assert "CellRank Runtime Details" in report
    assert "Visualization Outputs" in report

    result = json.loads((tmp_path / "result.json").read_text())
    assert result["skill"] == "spatial-trajectory"
    assert result["data"]["effective_params"]["cellrank_frac_to_keep"] == 0.2
    assert result["data"]["visualization"]["cluster_mean_pt_column"] == "traj_cluster_mean_pt"

    commands = (tmp_path / "reproducibility" / "commands.sh").read_text()
    assert "--cellrank-n-states 4" in commands
    assert "--cellrank-schur-components 12" in commands
    assert "--palantir-knn" not in commands

    assert (tmp_path / "tables" / "trajectory_summary.csv").exists()
    assert (tmp_path / "tables" / "trajectory_cluster_summary.csv").exists()
    assert (tmp_path / "tables" / "trajectory_genes.csv").exists()
    assert (tmp_path / "tables" / "trajectory_terminal_states.csv").exists()
    assert (tmp_path / "tables" / "trajectory_driver_genes.csv").exists()
    assert (tmp_path / "tables" / "cellrank_terminal_states.csv").exists()
    assert (tmp_path / "tables" / "cellrank_driver_genes.csv").exists()
    assert (tmp_path / "reproducibility" / "r_visualization.sh").exists()


def test_run_trajectory_invalid_method():
    """Unknown trajectory methods should fail explicitly."""
    import anndata
    from skills.spatial._lib.trajectory import run_trajectory

    adata = anndata.AnnData(X=np.ones((10, 5), dtype=np.float32))
    adata.obsm["X_pca"] = np.ones((10, 3), dtype=np.float32)
    adata.uns["neighbors"] = {}

    with pytest.raises(ValueError, match="Unknown trajectory method"):
        run_trajectory(adata, method="unknown")
