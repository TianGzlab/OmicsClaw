"""Tests for the spatial-statistics skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_statistics.py"

# Optional heavy dependencies — skip affected tests when not installed
try:
    import esda  # noqa: F401
    _ESDA_AVAILABLE = True
except ImportError:
    _ESDA_AVAILABLE = False


def _run_skill(output_dir: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    """Run the spatial-statistics CLI in demo mode."""
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--demo",
            "--output",
            str(output_dir),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return result


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "stats_out"


def test_default_neighborhood_enrichment_demo(tmp_output):
    """Default demo run should produce neighborhood-enrichment outputs."""
    _run_skill(tmp_output)

    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "analysis_summary.csv").exists()
    assert (tmp_output / "figure_data" / "pair_summary.csv").exists()
    assert (tmp_output / "figure_data" / "top_results.csv").exists()
    assert (tmp_output / "tables" / "neighborhood_zscore.csv").exists()
    assert (tmp_output / "tables" / "neighborhood_pairs.csv").exists()
    assert (tmp_output / "tables" / "analysis_summary.csv").exists()
    assert (tmp_output / "figures" / "neighborhood_enrichment_heatmap.png").exists()
    assert (tmp_output / "reproducibility" / "r_visualization.sh").exists()

    report = (tmp_output / "report.md").read_text()
    assert "Neighborhood Summary" in report
    assert "Interpretation Notes" in report
    assert "Visualization Outputs" in report

    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-statistics"
    assert data["summary"]["analysis_type"] == "neighborhood_enrichment"
    assert "graph_params" in data["summary"]
    assert data["data"]["visualization"]["recipe_id"] == "standard-spatial-statistics-gallery"

    figures_manifest = json.loads((tmp_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((tmp_output / "figure_data" / "manifest.json").read_text())
    assert figures_manifest["recipe_id"] == "standard-spatial-statistics-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["analysis_type"] == "neighborhood_enrichment"
    assert figure_data_manifest["available_files"]["analysis_summary"] == "analysis_summary.csv"

    import scanpy as sc

    adata = sc.read_h5ad(tmp_output / "processed.h5ad")
    assert "spatial_statistics_summary" in adata.uns
    assert "spatial_statistics_gallery" in adata.uns


def test_moran_custom_parameters_export_results(tmp_output):
    """Global Moran run should honor new method-aware parameters and exports."""
    out = tmp_output.parent / "stats_moran"
    _run_skill(
        out,
        "--analysis-type",
        "moran",
        "--genes",
        "Gene_000,Gene_001,Gene_002",
        "--stats-n-perms",
        "99",
        "--stats-corr-method",
        "fdr_bh",
        "--stats-n-neighs",
        "8",
    )

    assert (out / "tables" / "moran_results.csv").exists()
    assert (out / "figures" / "moran_ranking.png").exists()
    assert (out / "figures" / "moran_score_vs_significance.png").exists()
    assert (out / "figure_data" / "analysis_summary.csv").exists()
    assert (out / "figure_data" / "analysis_results.csv").exists()
    assert (out / "figure_data" / "top_results.csv").exists()
    assert (out / "figure_data" / "manifest.json").exists()
    result = json.loads((out / "result.json").read_text())
    assert result["summary"]["analysis_type"] == "moran"
    assert result["summary"]["n_genes"] == 3
    assert result["summary"]["graph_params"]["n_neighs"] == 8
    assert result["summary"]["corr_method"] == "fdr_bh"
    assert result["data"]["visualization"]["recipe_id"] == "standard-spatial-statistics-gallery"


@pytest.mark.skipif(not _ESDA_AVAILABLE, reason="esda not installed")
def test_getis_ord_exports_local_spot_tables(tmp_output):
    """Local Getis-Ord path should export per-gene and per-spot outputs."""
    out = tmp_output.parent / "stats_getis"
    _run_skill(
        out,
        "--analysis-type",
        "getis_ord",
        "--genes",
        "Gene_000",
        "--stats-n-perms",
        "99",
        "--no-getis-star",
    )

    assert (out / "tables" / "getis_ord_summary.csv").exists()
    assert (out / "tables" / "getis_ord_spots.csv").exists()
    assert (out / "figures" / "getis_ord_spatial.png").exists()
    assert (out / "figures" / "getis_ord_summary_barplot.png").exists()
    assert (out / "figure_data" / "spot_statistics.csv").exists()
    assert (out / "figure_data" / "analysis_summary.csv").exists()

    result = json.loads((out / "result.json").read_text())
    assert result["summary"]["analysis_type"] == "getis_ord"
    assert result["summary"]["getis_star"] is False
    assert result["data"]["visualization"]["recipe_id"] == "standard-spatial-statistics-gallery"


def test_spatial_centrality_uses_official_score_columns(tmp_output):
    """Spatial centrality should emit Squidpy-aligned score columns."""
    out = tmp_output.parent / "stats_centrality"
    _run_skill(
        out,
        "--analysis-type",
        "spatial_centrality",
        "--centrality-score",
        "degree_centrality,closeness_centrality",
    )

    table = out / "tables" / "centrality_scores.csv"
    assert table.exists()
    assert (out / "figures" / "manifest.json").exists()
    assert (out / "figure_data" / "analysis_results.csv").exists()
    assert (out / "figures" / "centrality_scores_barplot.png").exists()
    content = table.read_text()
    assert "degree_centrality" in content
    assert "closeness_centrality" in content
    assert "betweenness_centrality" not in content

    result = json.loads((out / "result.json").read_text())
    assert result["summary"]["analysis_type"] == "spatial_centrality"
    assert "degree_centrality" in result["summary"]["selected_scores"]
    assert result["data"]["visualization"]["recipe_id"] == "standard-spatial-statistics-gallery"
