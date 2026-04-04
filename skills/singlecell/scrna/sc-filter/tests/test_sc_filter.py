"""Tests for the sc-filter skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_filter.py"


def test_demo_mode(tmp_path):
    output_dir = tmp_path / "sc_filter_demo"
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(output_dir)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, result.stderr
    assert (output_dir / "processed.h5ad").exists()
    assert (output_dir / "figures" / "filter_comparison.png").exists()
    assert (output_dir / "figures" / "filter_summary.png").exists()
    assert (output_dir / "figures").exists()
    assert (output_dir / "figure_data" / "manifest.json").exists()
    assert (output_dir / "tables" / "filter_stats.csv").exists()
    assert (output_dir / "tables" / "filter_summary.csv").exists()
    assert (output_dir / "tables" / "retention_summary.csv").exists()


def test_demo_processed_contract(tmp_path):
    output_dir = tmp_path / "sc_filter_contract"
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(output_dir)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, result.stderr
    adata = ad.read_h5ad(output_dir / "processed.h5ad")
    assert adata.uns["omicsclaw_matrix_contract"]["X"] == "raw_counts"
    assert adata.uns["omicsclaw_matrix_contract"]["layers"]["counts"] == "raw_counts"
    assert adata.uns["omicsclaw_input_contract"]["domain"] == "singlecell"


def test_filter_reuses_existing_qc_metrics_on_normalized_input(tmp_path):
    input_path = tmp_path / "normalized_with_qc.h5ad"
    output_dir = tmp_path / "sc_filter_reuse"
    x = np.array([[1.2, 0.2, 0.0], [0.4, 1.3, 0.1], [0.3, 0.1, 1.4]], dtype=float)
    adata = ad.AnnData(
        X=x,
        obs=pd.DataFrame(
            {
                "n_genes_by_counts": [2, 2, 2],
                "total_counts": [100, 120, 140],
                "pct_counts_mt": [1.0, 2.0, 3.0],
            },
            index=["c1", "c2", "c3"],
        ),
        var=pd.DataFrame(index=["MT-CO1", "RPLP0", "GAPDH"]),
    )
    adata.uns["omicsclaw_matrix_contract"] = {
        "X": "normalized_expression",
        "raw": None,
        "layers": {},
        "producer_skill": "external",
    }
    adata.write_h5ad(input_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_dir),
            "--min-genes",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((output_dir / "result.json").read_text())
    assert payload["summary"]["qc_metrics_reused"] is True
    assert payload["data"]["matrix_contract"]["X"] == "normalized_expression"
