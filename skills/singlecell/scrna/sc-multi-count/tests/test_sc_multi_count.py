"""Tests for the sc-multi-count skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_multi_count.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_multi_count_out"


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert not (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "standardized_input.h5ad").exists()
    assert (tmp_output / "figures" / "barcode_rank.png").exists()
    assert (tmp_output / "figures" / "count_distributions.png").exists()
    assert (tmp_output / "figures" / "count_complexity_scatter.png").exists()
    assert (tmp_output / "figures" / "sample_composition.png").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "tables" / "barcode_metrics.csv").exists()
    assert (tmp_output / "tables" / "per_sample_summary.csv").exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["skill"] == "sc-multi-count"
    assert payload["summary"]["n_samples"] == 2
    assert payload["summary"]["n_cells"] > 0
    assert payload["data"]["input_contract"]["standardized"] is True
    assert payload["data"]["output_h5ad"] == "processed.h5ad"
    assert payload["data"]["visualization"]["recipe_id"] == "standard-sc-multi-count-gallery"
    assert "count_diagnostics" in payload["data"]


def test_demo_h5ad_contract(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    import anndata as ad

    adata = ad.read_h5ad(tmp_output / "processed.h5ad")
    assert "counts" in adata.layers
    assert adata.raw is not None
    assert "sample_id" in adata.obs.columns
    assert set(adata.obs["sample_id"].unique()) == {"sample_A", "sample_B"}
    assert "omicsclaw_input_contract" in adata.uns
    assert "omicsclaw_matrix_contract" in adata.uns
    mc = adata.uns["omicsclaw_matrix_contract"]
    assert mc["X"] == "raw_counts"
    assert mc["layers"]["counts"] == "raw_counts"


def test_missing_input_error(tmp_output):
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--input", "/nonexistent/a.h5ad",
            "--input", "/nonexistent/b.h5ad",
            "--output", str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode != 0
    assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()


def test_single_input_error(tmp_output):
    result = subprocess.run(
        [
            sys.executable, str(SKILL_SCRIPT),
            "--input", "/some/file.h5ad",
            "--output", str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode != 0
    assert "at least two" in result.stderr.lower()
