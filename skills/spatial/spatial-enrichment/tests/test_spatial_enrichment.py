"""Tests for the spatial-enrichment skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_enrichment.py"


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
    return tmp_path / "enrich_out"


@pytest.fixture(scope="module")
def demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_enrichment_demo")
    result = _run_skill(output_dir, "--demo")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


@pytest.fixture(scope="module")
def ssgsea_demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_enrichment_ssgsea_demo")
    result = _run_skill(
        output_dir,
        "--demo",
        "--method",
        "ssgsea",
        "--source",
        "omicsclaw_core",
        "--groupby",
        "leiden",
        "--ssgsea-sample-norm-method",
        "rank",
        "--ssgsea-correl-norm-type",
        "rank",
        "--ssgsea-min-size",
        "5",
        "--ssgsea-max-size",
        "200",
        "--ssgsea-weight",
        "0.25",
        "--ssgsea-threads",
        "1",
        "--ssgsea-seed",
        "13",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


def test_demo_mode(demo_output):
    """spatial-enrichment --demo should run without error."""
    assert (demo_output / "report.md").exists()
    assert (demo_output / "result.json").exists()
    assert (demo_output / "processed.h5ad").exists()
    assert (demo_output / "tables" / "enrichment_results.csv").exists()
    assert (demo_output / "reproducibility" / "commands.sh").exists()


def test_demo_outputs_gallery_contract(demo_output):
    """Demo mode should export gallery manifests, figure data, and the R helper."""
    assert (demo_output / "figures" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "enrichment_results.csv").exists()
    assert (demo_output / "figure_data" / "enrichment_significant.csv").exists()
    assert (demo_output / "figure_data" / "ranked_markers.csv").exists()
    assert (demo_output / "figure_data" / "top_enriched_terms.csv").exists()
    assert (demo_output / "figure_data" / "enrichment_group_metrics.csv").exists()
    assert (demo_output / "figure_data" / "enrichment_term_group_scores.csv").exists()
    assert (demo_output / "figure_data" / "enrichment_run_summary.csv").exists()
    assert (demo_output / "figure_data" / "enrichment_spatial_points.csv").exists()
    assert (demo_output / "figure_data" / "enrichment_umap_points.csv").exists()
    assert (demo_output / "reproducibility" / "r_visualization.sh").exists()

    run_summary = (demo_output / "figure_data" / "enrichment_run_summary.csv").read_text()
    assert "resolved_source" in run_summary
    assert "fdr_threshold" in run_summary


def test_demo_gallery_manifests_have_roles(demo_output):
    """The standard enrichment gallery should emit figure and figure-data manifests."""
    figures_manifest = json.loads((demo_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((demo_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-enrichment-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-enrichment"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-enrichment-gallery"


def test_demo_processed_h5ad_persists_gallery_annotations(demo_output):
    """Gallery-derived group burden columns should be written back into AnnData."""
    import scanpy as sc

    adata = sc.read_h5ad(demo_output / "processed.h5ad")
    assert "enrich_group_n_terms" in adata.obs.columns
    assert "enrich_group_n_significant" in adata.obs.columns
    assert "enrich_group_top_stat" in adata.obs.columns
    assert "enrich_group_top_abs_stat" in adata.obs.columns


def test_demo_report_content(demo_output):
    """Report should contain expected sections."""
    report = (demo_output / "report.md").read_text()
    assert "Spatial Pathway Enrichment Report" in report
    assert "Interpretation Notes" in report
    assert "Visualization Outputs" in report
    assert "Disclaimer" in report


def test_demo_result_json(demo_output):
    """result.json should contain expected keys."""
    data = json.loads((demo_output / "result.json").read_text())
    assert data["skill"] == "spatial-enrichment"
    assert "summary" in data
    assert data["summary"]["n_groups"] > 0
    assert data["summary"]["method"] == "enrichr"
    assert "visualization" in data["data"]
    assert data["data"]["visualization"]["group_top_stat_column"] == "enrich_group_top_stat"


def test_ssgsea_demo_exports_projected_scores(ssgsea_demo_output):
    """ssGSEA mode should export projected score columns through the shared gallery contract."""
    import scanpy as sc

    assert (ssgsea_demo_output / "figure_data" / "enrichment_spatial_points.csv").exists()
    assert (ssgsea_demo_output / "figure_data" / "enrichment_umap_points.csv").exists()

    data = json.loads((ssgsea_demo_output / "result.json").read_text())
    assert data["summary"]["method"] == "ssgsea"
    assert data["data"]["visualization"]["score_columns"]

    adata = sc.read_h5ad(ssgsea_demo_output / "processed.h5ad")
    ssgsea_cols = [column for column in adata.obs.columns if column.startswith("ssgsea_")]
    assert ssgsea_cols


def test_demo_accepts_gsea_flags(tmp_output):
    """CLI should accept the richer prerank GSEA parameter set."""
    result = _run_skill(
        tmp_output,
        "--demo",
        "--method",
        "gsea",
        "--source",
        "omicsclaw_core",
        "--groupby",
        "leiden",
        "--de-method",
        "wilcoxon",
        "--de-corr-method",
        "bonferroni",
        "--gsea-ranking-metric",
        "scores",
        "--gsea-min-size",
        "5",
        "--gsea-max-size",
        "200",
        "--gsea-permutation-num",
        "50",
        "--gsea-weight",
        "1.0",
        "--gsea-threads",
        "1",
        "--gsea-seed",
        "7",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_demo_accepts_ssgsea_flags(tmp_output):
    """CLI should accept the richer ssGSEA parameter set."""
    result = _run_skill(
        tmp_output,
        "--demo",
        "--method",
        "ssgsea",
        "--source",
        "omicsclaw_core",
        "--groupby",
        "leiden",
        "--ssgsea-sample-norm-method",
        "rank",
        "--ssgsea-correl-norm-type",
        "rank",
        "--ssgsea-min-size",
        "5",
        "--ssgsea-max-size",
        "200",
        "--ssgsea-weight",
        "0.25",
        "--ssgsea-threads",
        "1",
        "--ssgsea-seed",
        "13",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
