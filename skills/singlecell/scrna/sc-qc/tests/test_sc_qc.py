"""Tests for the sc-qc skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_qc.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_qc_out"


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figures" / "barcode_rank.png").exists()
    assert (tmp_output / "figures" / "qc_correlation_heatmap.png").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "qc_metrics_summary.csv").exists()
    assert (tmp_output / "tables" / "qc_metrics_per_cell.csv").exists()
    assert (tmp_output / "tables" / "barcode_rank_curve.csv").exists()
    assert (tmp_output / "tables" / "qc_metric_correlations.csv").exists()
    assert (tmp_output / "reproducibility" / "analysis_notebook.ipynb").exists()
    assert (tmp_output / "reproducibility" / "requirements.txt").exists()
    assert not (tmp_output / "reproducibility" / "environment.txt").exists()
    assert "sc-standardize-input" not in result.stderr


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "sc-qc"
    assert data["data"]["output_h5ad"] == "processed.h5ad"
    assert data["data"]["params"] == {"species": "human"}
    assert data["data"]["effective_params"]["species"] == "human"
    assert data["data"]["effective_params"]["calculate_ribo"] is True
    assert data["data"]["visualization"]["recipe_id"] == "standard-sc-qc-gallery"
    assert "qc_metrics_summary" in data["data"]["visualization"]["available_figure_data"]
    command_text = (tmp_output / "reproducibility" / "commands.sh").read_text()
    assert "--calculate-ribo" not in command_text


def test_prefers_counts_layer_and_gene_symbol_column(tmp_output, tmp_path):
    input_path = tmp_path / "layer_fallback.h5ad"
    norm_x = np.array(
        [
            [1.1, 0.4, 0.2, 0.1],
            [0.8, 0.2, 0.2, 0.0],
            [1.4, 0.3, 0.1, 0.0],
        ],
        dtype=np.float32,
    )
    counts = np.array(
        [
            [10, 4, 2, 1],
            [8, 2, 2, 0],
            [14, 3, 1, 0],
        ],
        dtype=np.int32,
    )
    adata = ad.AnnData(
        X=norm_x,
        obs=pd.DataFrame(index=["cell1", "cell2", "cell3"]),
        var=pd.DataFrame(
            {"gene_symbols": ["MT-CO1", "RPS3", "GENE3", "GENE4"]},
            index=["ENSG1", "ENSG2", "ENSG3", "ENSG4"],
        ),
    )
    adata.layers["counts"] = counts
    adata.write_h5ad(input_path)

    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--input", str(input_path), "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads((tmp_output / "result.json").read_text())
    prep = data["data"]["input_preparation"]
    assert prep["expression_source"] == "layers.counts"
    assert prep["gene_name_source"] == "var.gene_symbols"
    assert any("falling back to `layers.counts`" in warning for warning in prep["warnings"])

    qc_h5ad = ad.read_h5ad(tmp_output / "processed.h5ad")
    assert "pct_counts_mt" in qc_h5ad.obs.columns
    assert float(qc_h5ad.obs["pct_counts_mt"].max()) > 0
    np.testing.assert_allclose(np.asarray(qc_h5ad.X), counts)
    np.testing.assert_allclose(np.asarray(qc_h5ad.layers["counts"]), counts)
    assert qc_h5ad.raw is not None
    np.testing.assert_allclose(np.asarray(qc_h5ad.raw.X), counts)
    assert qc_h5ad.uns["omicsclaw_input_contract"]["standardized"] is True
    assert qc_h5ad.uns["omicsclaw_matrix_contract"]["X"] == "raw_counts"
    assert qc_h5ad.uns["omicsclaw_matrix_contract"]["raw"] == "raw_counts_snapshot"


def test_rejects_non_count_like_input_without_fallback(tmp_output, tmp_path):
    input_path = tmp_path / "normalized_only.h5ad"
    adata = ad.AnnData(
        X=np.array([[1.2, 0.5], [0.7, 0.3]], dtype=np.float32),
        obs=pd.DataFrame(index=["cell1", "cell2"]),
        var=pd.DataFrame(index=["GENE1", "GENE2"]),
    )
    adata.write_h5ad(input_path)

    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--input", str(input_path), "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )

    assert result.returncode != 0
    assert "expects a raw count-like matrix" in result.stderr
