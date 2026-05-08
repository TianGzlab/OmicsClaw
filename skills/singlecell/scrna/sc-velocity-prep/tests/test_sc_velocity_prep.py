"""Tests for the sc-velocity-prep skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_velocity_prep.py"
DEMO_H5AD = Path(__file__).resolve().parents[5] / "data" / "pbmc3k_raw.h5ad"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_velocity_prep_out"


@pytest.fixture
def fake_cellranger_dir(tmp_path):
    outs = tmp_path / "sample_count" / "outs" / "filtered_feature_bc_matrix"
    outs.mkdir(parents=True)
    (tmp_path / "sample_count" / "outs" / "possorted_genome_bam.bam").write_bytes(b"")
    (outs / "barcodes.tsv").write_text("AAACCCAAGAAACACT-1\n", encoding="utf-8")
    return tmp_path / "sample_count"


def test_demo_mode(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert not (tmp_output / "README.md").exists()
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "velocity_input.h5ad").exists()
    assert (tmp_output / "figures" / "velocity_layer_summary.png").exists()
    assert (tmp_output / "figures" / "velocity_layer_fraction.png").exists()
    assert (tmp_output / "figures" / "velocity_gene_balance.png").exists()
    assert (tmp_output / "figures" / "velocity_top_genes_stacked.png").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()


def test_demo_result_json(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["skill"] == "sc-velocity-prep"
    assert payload["summary"]["spliced_layer_present"] is True
    assert payload["summary"]["unspliced_layer_present"] is True
    assert payload["data"]["output_h5ad"] == "processed.h5ad"
    assert payload["data"]["visualization"]["recipe_id"] == "standard-sc-velocity-prep-gallery"


def test_demo_mode_with_base_h5ad(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--base-h5ad", str(DEMO_H5AD), "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads((tmp_output / "result.json").read_text())
    assert payload["summary"]["used_base_h5ad"] is True


def test_velocyto_missing_gtf_message(tmp_output, fake_cellranger_dir):
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--input",
            str(fake_cellranger_dir),
            "--method",
            "velocyto",
            "--output",
            str(tmp_output),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode != 0
    stderr = result.stderr
    assert "resources/singlecell/references/gtf" in stderr
    assert "velocyto docs" in stderr
    assert "cp /path/to/refdata-gex" in stderr
