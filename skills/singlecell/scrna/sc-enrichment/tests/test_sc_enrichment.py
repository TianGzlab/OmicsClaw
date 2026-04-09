"""Tests for the sc-enrichment skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import anndata as ad
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "sc_enrichment.py"
MARKERS_SCRIPT = Path(__file__).resolve().parents[2] / "sc-markers" / "sc_markers.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "sc_enrichment_out"


def _write_test_gmt(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "PBMC_T\tna\tIL7R\tLTB\tIL32\tLDHB",
                "PBMC_NK\tna\tNKG7\tGNLY\tPRF1\tGZMB",
                "PBMC_B\tna\tMS4A1\tCD79A\tCD79B\tCD74",
                "PBMC_MONO\tna\tLST1\tFCER1G\tTYROBP\tS100A8",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_demo_ora_runs(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--method", "ora", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "tables" / "enrichment_results.csv").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()


def test_demo_gsea_runs(tmp_output):
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--method", "gsea", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "figures" / "gsea_running_scores.png").exists()
    assert (tmp_output / "tables" / "top_terms.csv").exists()


def test_processed_output_carries_contract_and_metadata(tmp_output):
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--method", "ora", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
        check=True,
    )
    adata = ad.read_h5ad(tmp_output / "processed.h5ad")
    assert "omicsclaw_matrix_contract" in adata.uns
    assert "omicsclaw_input_contract" in adata.uns
    assert "omicsclaw_sc-enrichment" in adata.uns


def test_markers_output_dir_input_runs(tmp_path):
    markers_out = tmp_path / "markers"
    enrich_out = tmp_path / "enrichment"
    gmt_path = _write_test_gmt(tmp_path / "custom_sets.gmt")

    markers_result = subprocess.run(
        [sys.executable, str(MARKERS_SCRIPT), "--demo", "--output", str(markers_out)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(MARKERS_SCRIPT.parent),
    )
    assert markers_result.returncode == 0, f"stderr: {markers_result.stderr}"

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--input",
            str(markers_out),
            "--method",
            "ora",
            "--gene-sets",
            str(gmt_path),
            "--output",
            str(enrich_out),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads((enrich_out / "result.json").read_text())
    assert data["skill"] == "sc-enrichment"
    assert data["summary"]["ranking_source"] in {"markers_table", "auto_cluster_ranking"}


def test_gene_set_from_markers_with_group_and_topn(tmp_path):
    markers_out = tmp_path / "markers_src"
    enrich_out = tmp_path / "enrichment_from_marker_sets"

    markers_result = subprocess.run(
        [sys.executable, str(MARKERS_SCRIPT), "--demo", "--output", str(markers_out)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(MARKERS_SCRIPT.parent),
    )
    assert markers_result.returncode == 0, f"stderr: {markers_result.stderr}"

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--input",
            str(markers_out),
            "--method",
            "ora",
            "--gene-set-from-markers",
            str(markers_out),
            "--marker-group",
            "CD4 T cells",
            "--marker-top-n",
            "3",
            "--output",
            str(enrich_out),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = json.loads((enrich_out / "result.json").read_text())
    assert data["data"]["params"]["gene_set_from_markers"] == str(markers_out)
    assert data["data"]["params"]["marker_group"] == "CD4 T cells"
    assert data["data"]["params"]["marker_top_n"] == "3"
