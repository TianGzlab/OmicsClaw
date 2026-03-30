"""Tests for the spatial-annotate skill."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from anndata import AnnData

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_annotate.py"
_SPEC = importlib.util.spec_from_file_location("omicsclaw_spatial_annotate_test_module", SKILL_SCRIPT)
spatial_annotate_module = importlib.util.module_from_spec(_SPEC)
assert _SPEC is not None and _SPEC.loader is not None
_SPEC.loader.exec_module(spatial_annotate_module)


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "annotate_out"


def test_demo_mode(tmp_output):
    """spatial-annotate --demo should run without error."""
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


def test_demo_report_content(tmp_output):
    """Report should contain annotation sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Annotation" in report or "annotation" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-annotate"
    assert "summary" in data
    assert "n_clusters" in data["summary"]
    assert data["summary"]["n_clusters"] > 0
    assert data["data"]["visualization"]["recipe_id"] == "standard-spatial-annotation-gallery"
    assert data["data"]["visualization"]["cell_type_column"] == "cell_type"


def test_demo_outputs_tables_and_commands(tmp_output):
    """Demo mode should export tables and reproducibility commands."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "tables" / "annotation_summary.csv").exists()
    assert (tmp_output / "tables" / "cell_type_assignments.csv").exists()
    assert (tmp_output / "tables" / "cluster_annotations.csv").exists()
    assert (tmp_output / "tables" / "marker_overlap_scores.csv").exists()
    assert (tmp_output / "reproducibility" / "commands.sh").exists()
    assert (tmp_output / "reproducibility" / "r_visualization.sh").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "annotation_spatial_points.csv").exists()
    assert (tmp_output / "figure_data" / "annotation_umap_points.csv").exists()
    assert (tmp_output / "figure_data" / "annotation_cell_type_counts.csv").exists()


def test_demo_custom_marker_flags_are_recorded(tmp_output):
    """Custom marker-based flags should be accepted and written to commands.sh."""
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--demo",
            "--output",
            str(tmp_output),
            "--marker-rank-method",
            "t-test",
            "--marker-n-genes",
            "30",
            "--marker-overlap-method",
            "jaccard",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    commands = (tmp_output / "reproducibility" / "commands.sh").read_text()
    assert "--marker-rank-method t-test" in commands
    assert "--marker-n-genes 30" in commands
    assert "--marker-overlap-method jaccard" in commands


def test_demo_gallery_manifests_have_roles(tmp_output):
    """The standard gallery should emit figure and figure-data manifests."""
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

    assert figures_manifest["recipe_id"] == "standard-spatial-annotation-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-annotate"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-annotation-gallery"


def test_prepare_annotation_plot_state_recovers_labels_and_spatial_aliases():
    """Plot preparation should recover labels from probabilities and sync spatial aliases."""
    adata = AnnData(np.ones((3, 2), dtype=float))
    adata.obs_names = ["cell1", "cell2", "cell3"]
    adata.obsm["X_spatial"] = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    adata.obsm["tangram_ct_pred"] = pd.DataFrame(
        [[0.9, 0.1], [0.2, 0.8], [0.7, 0.3]],
        index=adata.obs_names,
        columns=["T cell", "B cell"],
    )
    adata.uns["tangram_cell_type_names"] = ["T cell", "B cell"]
    adata.uns["spatial"] = {"library": {}}

    spatial_annotate_module._prepare_annotation_plot_state(adata)

    assert "spatial" in adata.obsm
    assert "X_spatial" in adata.obsm
    assert "cell_type" in adata.obs.columns
    assert list(adata.obs["cell_type"].astype(str)) == ["T cell", "B cell", "T cell"]
