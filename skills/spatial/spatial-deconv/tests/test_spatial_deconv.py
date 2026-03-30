"""Tests for the spatial-deconv skill."""

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
from anndata import AnnData

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_deconv.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SKILL_SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT.parent))


def _load_skill_module():
    spec = importlib.util.spec_from_file_location("spatial_deconv", SKILL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_gallery_adata() -> AnnData:
    adata = AnnData(
        X=np.array(
            [
                [1.0, 0.5, 0.2],
                [0.8, 0.2, 0.1],
                [0.1, 0.9, 0.3],
                [0.2, 0.6, 0.7],
            ],
            dtype=float,
        )
    )
    adata.obs_names = [f"spot_{idx}" for idx in range(adata.n_obs)]
    adata.var_names = ["GeneA", "GeneB", "GeneC"]
    adata.obsm["spatial"] = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.2],
            [0.2, 1.0],
            [1.1, 1.1],
        ],
        dtype=float,
    )
    adata.obsm["X_umap"] = np.array(
        [
            [0.0, 0.0],
            [0.6, 0.1],
            [0.1, 0.7],
            [0.8, 0.9],
        ],
        dtype=float,
    )
    return adata


def _prepare_gallery_state(module, method: str = "cell2location"):
    adata = _make_gallery_adata()
    prop_df = pd.DataFrame(
        {
            "Tumor": [0.75, 0.65, 0.10, 0.15],
            "Stroma": [0.15, 0.20, 0.70, 0.25],
            "Immune": [0.10, 0.15, 0.20, 0.60],
        },
        index=adata.obs_names,
    )
    prop_key = f"deconvolution_{method}"
    adata.obsm[prop_key] = prop_df.to_numpy()
    adata.uns[f"{prop_key}_cell_types"] = list(prop_df.columns)
    summary = {
        "method": method,
        "reference": "ref.h5ad",
        "cell_type_key": "cell_type",
        "n_common_genes": 123,
        "device": "cpu",
        "effective_params": {"example_param": 1},
        "extra_tables": {},
    }
    gallery_context = module._prepare_deconv_gallery_context(adata, prop_df, summary)
    return adata, prop_df, summary, gallery_context


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "deconv_out"


def test_demo_mode(tmp_output):
    """spatial-deconv --demo should explain that a real reference is required."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 1
    assert "ERROR: --demo requires a real reference scRNA-seq dataset" in (result.stderr + result.stdout)


def test_collect_run_configuration_tangram():
    """Only the selected method's parameters should enter the reproducibility config."""
    module = _load_skill_module()

    args = argparse.Namespace(
        method="tangram",
        reference="ref.h5ad",
        cell_type_key="cell_type",
        no_gpu=False,
        flashdeconv_sketch_dim=512,
        flashdeconv_lambda_spatial=5000.0,
        flashdeconv_n_hvg=2000,
        flashdeconv_n_markers_per_type=50,
        cell2location_n_epochs=30000,
        cell2location_n_cells_per_spot=30,
        cell2location_detection_alpha=20.0,
        rctd_mode="full",
        destvi_n_epochs=2500,
        destvi_condscvi_epochs=300,
        destvi_n_hidden=128,
        destvi_n_latent=5,
        destvi_n_layers=2,
        destvi_dropout_rate=0.05,
        destvi_vamp_prior_p=15,
        stereoscope_rna_epochs=400,
        stereoscope_spatial_epochs=400,
        stereoscope_learning_rate=0.01,
        stereoscope_batch_size=128,
        tangram_n_epochs=1200,
        tangram_learning_rate=0.05,
        tangram_mode="clusters",
        spotlight_n_top=50,
        spotlight_weight_id="weight",
        spotlight_model="ns",
        spotlight_min_prop=0.01,
        spotlight_scale=True,
        card_sample_key=None,
        card_min_count_gene=100,
        card_min_count_spot=5,
        card_imputation=False,
        card_num_grids=2000,
        card_ineibor=10,
    )

    params, method_kwargs = module._collect_run_configuration(args)

    assert params["method"] == "tangram"
    assert params["tangram_mode"] == "clusters"
    assert "cell2location_n_cells_per_spot" not in params
    assert method_kwargs == {
        "reference_path": "ref.h5ad",
        "cell_type_key": "cell_type",
        "n_epochs": 1200,
        "learning_rate": 0.05,
        "mode": "clusters",
        "use_gpu": True,
    }


def test_build_aux_tables_exports_expected_contract():
    """Derived proportion summaries should produce stable auxiliary tables."""
    module = _load_skill_module()
    prop_df = pd.DataFrame(
        {
            "Tumor": [0.8, 0.2],
            "Stroma": [0.2, 0.8],
        },
        index=["spot_1", "spot_2"],
    )

    tables = module._build_aux_tables(prop_df)

    assert set(tables) == {
        "dominant_celltype.csv",
        "celltype_diversity.csv",
        "mean_proportions.csv",
    }
    dominant = tables["dominant_celltype.csv"]
    assert list(dominant["dominant_cell_type"]) == ["Tumor", "Stroma"]


def test_generate_figures_exports_gallery_contract(tmp_path):
    """Synthetic deconvolution results should emit gallery manifests and figure-ready CSVs."""
    module = _load_skill_module()
    adata, _, summary, gallery_context = _prepare_gallery_state(module, method="cell2location")

    figures = module.generate_figures(
        adata,
        tmp_path,
        summary,
        gallery_context=gallery_context,
    )

    assert len(figures) >= 5
    assert (tmp_path / "figures" / "manifest.json").exists()
    assert (tmp_path / "figure_data" / "manifest.json").exists()
    assert (tmp_path / "figure_data" / "proportions.csv").exists()
    assert (tmp_path / "figure_data" / "deconv_spot_metrics.csv").exists()
    assert (tmp_path / "figure_data" / "dominant_celltype_counts.csv").exists()
    assert (tmp_path / "figure_data" / "deconv_run_summary.csv").exists()
    assert (tmp_path / "figure_data" / "deconv_spatial_points.csv").exists()
    assert (tmp_path / "figure_data" / "deconv_umap_points.csv").exists()

    figures_manifest = json.loads((tmp_path / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((tmp_path / "figure_data" / "manifest.json").read_text())
    assert figures_manifest["recipe_id"] == "standard-spatial-deconv-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-deconv"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-deconv-gallery"

    assert "deconv_cell2location_dominant_cell_type" in adata.obs.columns
    assert "deconv_cell2location_assignment_margin" in adata.obs.columns
    assert "deconv_cell2location_normalized_entropy" in adata.obs.columns


def test_export_tables_writes_standard_contract(tmp_path):
    """Table exports should include stable deconvolution summaries beyond the raw proportion matrix."""
    module = _load_skill_module()
    _, _, summary, gallery_context = _prepare_gallery_state(module, method="card")

    exported = module.export_tables(tmp_path, summary, gallery_context)

    assert any(path.endswith("tables/proportions.csv") for path in exported)
    assert (tmp_path / "tables" / "proportions.csv").exists()
    assert (tmp_path / "tables" / "dominant_celltype.csv").exists()
    assert (tmp_path / "tables" / "celltype_diversity.csv").exists()
    assert (tmp_path / "tables" / "mean_proportions.csv").exists()
    assert (tmp_path / "tables" / "deconv_spot_metrics.csv").exists()
    assert (tmp_path / "tables" / "dominant_celltype_counts.csv").exists()


def test_write_report_records_effective_params(tmp_path):
    """Report and result JSON should preserve only method-relevant settings."""
    module = _load_skill_module()

    summary = {
        "method": "card",
        "n_spots": 2,
        "n_cell_types": 2,
        "n_common_genes": 100,
        "device": "cpu",
        "dominant_types": {"Tumor": 1, "Stroma": 1},
        "effective_params": {
            "card_min_count_gene": 100,
            "card_min_count_spot": 5,
            "card_imputation": True,
        },
        "extra_tables": {
            "card_refined_proportions": pd.DataFrame(
                {"Tumor": [0.7], "Stroma": [0.3]},
                index=["grid_1"],
            )
        },
    }
    params = {
        "method": "card",
        "reference": "ref.h5ad",
        "cell_type_key": "cell_type",
        "card_min_count_gene": 100,
        "card_min_count_spot": 5,
        "card_imputation": True,
        "card_num_grids": 2000,
        "card_ineibor": 10,
    }
    gallery_context = {
        "prop_key": "deconvolution_card",
        "dominant_label_col": "deconv_card_dominant_cell_type",
        "dominant_proportion_col": "deconv_card_dominant_proportion",
        "normalized_entropy_col": "deconv_card_normalized_entropy",
        "assignment_margin_col": "deconv_card_assignment_margin",
    }

    module.write_report(tmp_path, summary, None, params, gallery_context=gallery_context)

    report = (tmp_path / "report.md").read_text()
    assert "Effective Method Parameters" in report
    assert "card_refined_proportions" in report
    assert "Visualization Outputs" in report

    result = json.loads((tmp_path / "result.json").read_text())
    assert result["skill"] == "spatial-deconv"
    assert result["data"]["effective_params"]["card_imputation"] is True
    assert result["data"]["visualization"]["recipe_id"] == "standard-spatial-deconv-gallery"
    assert result["data"]["visualization"]["assignment_margin_column"] == "deconv_card_assignment_margin"

    commands = (tmp_path / "reproducibility" / "commands.sh").read_text()
    assert "--card-imputation" in commands
    assert "--card-num-grids 2000" in commands
    assert "--tangram-mode" not in commands
    assert (tmp_path / "reproducibility" / "r_visualization.sh").exists()
