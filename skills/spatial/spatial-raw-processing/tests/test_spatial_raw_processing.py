"""Tests for the spatial-raw-processing skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_raw_processing.py"


def _run_skill(output_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), *args, "--output", str(output_dir)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )


@pytest.fixture(scope="module")
def demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_raw_demo")
    result = _run_skill(output_dir, "--demo")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


def test_demo_mode_writes_expected_outputs(demo_output):
    assert (demo_output / "report.md").exists()
    assert (demo_output / "result.json").exists()
    assert (demo_output / "raw_counts.h5ad").exists()
    assert (demo_output / "figures" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "manifest.json").exists()
    assert (demo_output / "tables" / "run_summary.csv").exists()
    assert (demo_output / "tables" / "stage_summary.csv").exists()
    assert (demo_output / "tables" / "spot_qc.csv").exists()
    assert (demo_output / "tables" / "gene_qc.csv").exists()
    assert (demo_output / "tables" / "top_genes.csv").exists()
    assert (demo_output / "upstream" / "st_pipeline" / "omicsclaw_stpipeline_run.json").exists()
    assert (demo_output / "reproducibility" / "commands.sh").exists()
    assert (demo_output / "reproducibility" / "r_visualization.sh").exists()


def test_demo_result_json_contains_next_step_contract(demo_output):
    result = json.loads((demo_output / "result.json").read_text())
    assert result["skill"] == "spatial-raw-processing"
    assert result["summary"]["method"] == "st_pipeline"
    assert result["summary"]["next_skill"] == "spatial-preprocess"
    assert result["data"]["visualization"]["recipe_id"] == "standard-spatial-raw-processing-gallery"
    assert result["data"]["recommended_next_step"]["skill"] == "spatial-preprocess"


def test_demo_h5ad_preserves_raw_contract(demo_output):
    adata = ad.read_h5ad(demo_output / "raw_counts.h5ad")
    assert "counts" in adata.layers
    assert adata.raw is not None
    assert "spatial" in adata.obsm
    assert "total_counts" in adata.obs.columns
    assert "n_genes_by_counts" in adata.obs.columns
    assert adata.uns["omicsclaw"]["next_skill"] == "spatial-preprocess"


def test_demo_report_mentions_next_step(demo_output):
    report = (demo_output / "report.md").read_text()
    assert "Spatial Raw Processing Report" in report
    assert "Recommended Next Step" in report
    assert "spatial-preprocess" in report


def test_matrix_level_input_is_rejected_with_handoff_guidance(tmp_path):
    adata = ad.AnnData(
        X=np.array([[1.0, 2.0], [0.0, 3.0]], dtype=float),
        obs=pd.DataFrame(index=["spot1", "spot2"]),
        var=pd.DataFrame(index=["GeneA", "GeneB"]),
    )
    adata.obsm["spatial"] = np.array([[0.0, 0.0], [1.0, 1.0]])
    input_path = tmp_path / "matrix_input.h5ad"
    adata.write_h5ad(input_path)

    result = _run_skill(tmp_path / "out", "--input", str(input_path))
    assert result.returncode != 0
    assert "spatial-preprocess" in (result.stderr or result.stdout)
