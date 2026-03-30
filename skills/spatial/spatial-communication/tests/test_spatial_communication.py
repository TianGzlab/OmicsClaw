"""Tests for the spatial-communication skill."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_communication.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SKILL_SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT.parent))


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "comm_out"


def _make_comm_adata():
    import anndata

    adata = anndata.AnnData(
        X=np.array(
            [
                [1.0, 0.5, 0.0, 0.1],
                [0.9, 0.2, 0.2, 0.0],
                [0.1, 1.1, 0.4, 0.0],
                [0.0, 0.8, 0.9, 0.2],
            ],
            dtype=np.float32,
        )
    )
    adata.var_names = ["LIG1", "REC1", "LIG2", "REC2"]
    adata.obs_names = [f"spot_{i}" for i in range(adata.n_obs)]
    adata.obs["cell_type"] = pd.Categorical(["A", "A", "B", "B"])
    adata.obsm["spatial"] = np.array(
        [[0.0, 0.0], [1.0, 0.5], [5.0, 4.0], [5.5, 4.5]],
        dtype=np.float32,
    )
    return adata


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
    assert (tmp_output / "tables" / "lr_interactions.csv").exists()
    assert (tmp_output / "tables" / "signaling_roles.csv").exists()


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
    assert (tmp_output / "figure_data" / "lr_interactions.csv").exists()
    assert (tmp_output / "figure_data" / "top_interactions.csv").exists()
    assert (tmp_output / "figure_data" / "communication_summary.csv").exists()
    assert (tmp_output / "figure_data" / "signaling_roles.csv").exists()
    assert (tmp_output / "figure_data" / "communication_run_summary.csv").exists()
    assert (tmp_output / "figure_data" / "communication_spatial_points.csv").exists()
    assert (tmp_output / "figure_data" / "communication_umap_points.csv").exists()
    assert (tmp_output / "reproducibility" / "r_visualization.sh").exists()


def test_demo_gallery_manifests_have_roles(tmp_output):
    """The standard communication gallery should emit figure and figure-data manifests."""
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

    assert figures_manifest["recipe_id"] == "standard-spatial-communication-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-communication"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-communication-gallery"


def test_demo_report_content(tmp_output):
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Cell-Cell Communication" in report
    assert "Disclaimer" in report
    assert "Method" in report
    assert "Visualization Outputs" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-communication"
    assert "summary" in data
    assert "n_interactions_tested" in data["summary"]
    assert data["data"]["visualization"]["recipe_id"] == "standard-spatial-communication-gallery"
    assert data["data"]["visualization"]["cell_type_key"] == "leiden"


def test_collect_run_configuration_fastccc():
    """Only the selected method's parameters should enter the reproducibility config."""
    from spatial_communication import _collect_run_configuration

    args = argparse.Namespace(
        method="fastccc",
        cell_type_key="cell_type",
        species="human",
        liana_expr_prop=0.1,
        liana_min_cells=5,
        liana_n_perms=1000,
        liana_resource="auto",
        cellphonedb_iterations=1000,
        cellphonedb_threshold=0.1,
        fastccc_single_unit_summary="Mean",
        fastccc_complex_aggregation="Minimum",
        fastccc_lr_combination="Arithmetic",
        fastccc_min_percentile=0.2,
        cellchat_prob_type="triMean",
        cellchat_min_cells=10,
    )

    params, method_kwargs = _collect_run_configuration(args)

    assert params["method"] == "fastccc"
    assert "fastccc_min_percentile" in params
    assert "liana_expr_prop" not in params
    assert method_kwargs == {
        "single_unit_summary": "Mean",
        "complex_aggregation": "Minimum",
        "lr_combination": "Arithmetic",
        "min_percentile": 0.2,
    }


def test_run_communication_persists_standardized_results(monkeypatch):
    """run_communication should always write standardized result tables into adata.uns."""
    from skills.spatial._lib import communication as communication_lib

    adata = _make_comm_adata()
    fake_df = pd.DataFrame(
        [
            {
                "ligand": "LIG1",
                "receptor": "REC1",
                "source": "A",
                "target": "B",
                "score": 0.8,
                "pvalue": 0.01,
            },
            {
                "ligand": "LIG2",
                "receptor": "REC2",
                "source": "B",
                "target": "A",
                "score": 0.5,
                "pvalue": 0.03,
            },
        ]
    )

    def _fake_run_fastccc(*args, **kwargs):
        return fake_df, {
            "effective_params": {
                "fastccc_single_unit_summary": "Mean",
                "fastccc_min_percentile": 0.1,
            }
        }

    monkeypatch.setattr(communication_lib, "_run_fastccc", _fake_run_fastccc)
    summary = communication_lib.run_communication(
        adata,
        method="fastccc",
        cell_type_key="cell_type",
        species="human",
    )

    assert "ccc_results" in adata.uns
    assert "fastccc_results" in adata.uns
    assert "communication_summary" in adata.uns
    assert "communication_signaling_roles" in adata.uns
    assert summary["effective_params"]["fastccc_min_percentile"] == 0.1
    assert summary["n_significant"] == 2


def test_prepare_communication_gallery_context_maps_roles_to_observations():
    """Gallery context should project signaling-role summaries back onto observations."""
    from spatial_communication import _prepare_communication_gallery_context

    adata = _make_comm_adata()
    lr_df = pd.DataFrame(
        [
            {
                "ligand": "LIG1",
                "receptor": "REC1",
                "source": "A",
                "target": "B",
                "score": 0.8,
                "pvalue": 0.01,
            }
        ]
    )
    summary = {
        "cell_type_key": "cell_type",
        "lr_df": lr_df,
        "top_df": lr_df,
        "pathway_df": pd.DataFrame(),
        "signaling_roles_df": pd.DataFrame(
            [
                {
                    "cell_type": "A",
                    "sender_score": 0.8,
                    "receiver_score": 0.1,
                    "hub_score": 0.9,
                    "dominant_role": "sender",
                    "n_outgoing": 1,
                    "n_incoming": 0,
                },
                {
                    "cell_type": "B",
                    "sender_score": 0.1,
                    "receiver_score": 0.8,
                    "hub_score": 0.9,
                    "dominant_role": "receiver",
                    "n_outgoing": 0,
                    "n_incoming": 1,
                },
            ]
        ),
    }

    context = _prepare_communication_gallery_context(adata, summary)

    assert context["role_col"] == "communication_role"
    assert context["hub_score_col"] == "communication_hub_score"
    assert "communication_role" in adata.obs.columns
    assert "communication_hub_score" in adata.obs.columns
    assert set(adata.obs["communication_role"].astype(str)) == {"sender", "receiver"}


def test_write_report_exports_method_specific_tables(tmp_path):
    """The explicit export helpers should emit standardized and CellChat-specific tables."""
    from spatial_communication import export_tables, write_report, write_reproducibility

    lr_df = pd.DataFrame(
        [
            {
                "ligand": "CXCL12",
                "receptor": "CXCR4",
                "source": "Stroma",
                "target": "Tumor",
                "score": 0.9,
                "pvalue": 0.01,
                "pathway": "CXCL",
            }
        ]
    )
    summary = {
        "n_cells": 10,
        "n_genes": 100,
        "n_cell_types": 2,
        "method": "cellchat_r",
        "species": "human",
        "cell_type_key": "cell_type",
        "n_interactions_tested": 1,
        "n_significant": 1,
        "lr_df": lr_df,
        "top_df": lr_df,
        "pathway_df": pd.DataFrame(
            [
                {
                    "source": "Stroma",
                    "target": "Tumor",
                    "pathway": "CXCL",
                    "n_interactions": 1,
                    "mean_score": 0.9,
                    "top_ligand": "CXCL12",
                    "top_receptor": "CXCR4",
                }
            ]
        ),
        "signaling_roles_df": pd.DataFrame(
            [
                {
                    "cell_type": "Stroma",
                    "sender_score": 0.9,
                    "receiver_score": 0.0,
                    "hub_score": 0.9,
                    "dominant_role": "sender",
                    "n_outgoing": 1,
                    "n_incoming": 0,
                }
            ]
        ),
        "effective_params": {
            "cellchat_prob_type": "triMean",
            "cellchat_min_cells": 10,
        },
        "extra_tables": {
            "cellchat_pathways_df": pd.DataFrame([{"pathway_name": "CXCL"}]),
            "cellchat_centrality_df": pd.DataFrame([{"cell_type": "Stroma"}]),
        },
    }
    params = {
        "method": "cellchat_r",
        "cell_type_key": "cell_type",
        "species": "human",
        "cellchat_prob_type": "triMean",
        "cellchat_min_cells": 10,
    }

    write_report(tmp_path, summary, None, params)
    export_tables(tmp_path, summary)
    write_reproducibility(tmp_path, params, None)

    assert (tmp_path / "tables" / "lr_interactions.csv").exists()
    assert (tmp_path / "tables" / "top_interactions.csv").exists()
    assert (tmp_path / "tables" / "communication_summary.csv").exists()
    assert (tmp_path / "tables" / "signaling_roles.csv").exists()
    assert (tmp_path / "tables" / "cellchat_pathways.csv").exists()
    assert (tmp_path / "reproducibility" / "r_visualization.sh").exists()
    commands = (tmp_path / "reproducibility" / "commands.sh").read_text()
    assert "--cellchat-prob-type triMean" in commands
    assert "--liana-expr-prop" not in commands
