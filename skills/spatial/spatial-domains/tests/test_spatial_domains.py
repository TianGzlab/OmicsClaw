"""Tests for the spatial-domains skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_domains.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Ensure project root is importable
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "domains_out"


def _make_synthetic_adata(n_obs: int = 50, n_vars: int = 30):
    """Create a minimal preprocessed AnnData for unit tests."""
    import anndata
    import scanpy as sc
    import scipy.sparse as sp

    rng = np.random.default_rng(42)
    counts = rng.poisson(5, size=(n_obs, n_vars)).astype(np.float32)
    adata = anndata.AnnData(X=counts.copy())
    adata.var_names = [f"Gene_{i}" for i in range(n_vars)]
    adata.obs_names = [f"Cell_{i}" for i in range(n_obs)]
    adata.obsm["spatial"] = rng.uniform(0, 1000, size=(n_obs, 2))

    # Preserve raw counts in layers and raw
    adata.layers["counts"] = counts.copy()
    adata.raw = adata.copy()

    # Log-normalize
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # HVG + PCA + neighbors
    sc.pp.highly_variable_genes(adata, n_top_genes=min(20, n_vars - 1))
    sc.tl.pca(adata, n_comps=min(15, n_vars - 1, n_obs - 1))
    sc.pp.neighbors(adata, n_neighbors=min(10, n_obs - 1), n_pcs=min(10, 15))

    return adata


# -----------------------------------------------------------------------
# CLI integration tests (existing)
# -----------------------------------------------------------------------


def test_demo_mode(tmp_output):
    """spatial-domains --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "processed.h5ad").exists()


def test_demo_report_content(tmp_output):
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Spatial Domain Identification Report" in report
    assert "Disclaimer" in report
    assert "Domain" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-domains"
    assert "summary" in data
    assert data["summary"]["n_domains"] > 0
    assert data["data"]["visualization"]["recipe_id"] == "standard-spatial-domain-gallery"
    assert data["data"]["visualization"]["domain_column"] == "spatial_domain"


def test_demo_figures(tmp_output):
    """Demo mode should produce spatial domain figures."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    figures_dir = tmp_output / "figures"
    assert figures_dir.exists()
    assert (figures_dir / "spatial_domains.png").exists()
    assert (figures_dir / "umap_domains.png").exists()


def test_demo_tables_and_gallery_contract(tmp_output):
    """Demo mode should produce tables, manifests, and reproducibility helpers."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "tables" / "domain_summary.csv").exists()
    assert (tmp_output / "tables" / "domain_assignments.csv").exists()
    assert (tmp_output / "tables" / "domain_neighbor_mixing.csv").exists()
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "domain_counts.csv").exists()
    assert (tmp_output / "figure_data" / "domain_spatial_points.csv").exists()
    assert (tmp_output / "figure_data" / "domain_umap_points.csv").exists()
    assert (tmp_output / "figure_data" / "domain_neighbor_mixing.csv").exists()
    assert (tmp_output / "reproducibility" / "commands.sh").exists()
    assert (tmp_output / "reproducibility" / "r_visualization.sh").exists()


def test_demo_gallery_manifests_have_roles(tmp_output):
    """The standard domain gallery should emit figure and figure-data manifests."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    figures_manifest = json.loads((tmp_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((tmp_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-domain-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-domains"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-domain-gallery"


# -----------------------------------------------------------------------
# Unit tests for domain identification library (method-specific)
# -----------------------------------------------------------------------


def test_leiden_uses_prebuilt_graph():
    """Leiden should cluster using the pre-built neighbor graph."""
    from skills.spatial._lib.domains import identify_domains_leiden

    adata = _make_synthetic_adata()
    summary = identify_domains_leiden(adata, resolution=0.5)

    assert summary["method"] == "leiden"
    assert summary["n_domains"] > 0
    assert "spatial_domain" in adata.obs.columns


def test_louvain_uses_prebuilt_graph():
    """Louvain should cluster using the pre-built neighbor graph."""
    pytest.skip("louvain segfaults on small synthetic data; tested via CLI demo only")


def test_dispatch_invalid_method():
    """dispatch_method should raise ValueError for unknown methods."""
    from skills.spatial._lib.domains import dispatch_method

    adata = _make_synthetic_adata()
    with pytest.raises(ValueError, match="Unknown method"):
        dispatch_method("nonexistent_method", adata)


def test_dispatch_supported_methods():
    """SUPPORTED_METHODS should list all registered domain methods."""
    from skills.spatial._lib.domains import SUPPORTED_METHODS

    assert set(SUPPORTED_METHODS) == {
        "leiden",
        "louvain",
        "spagcn",
        "stagate",
        "graphst",
        "banksy",
        "cellcharter",
    }


def test_refine_spatial_domains():
    """Spatial refinement should produce labels for all cells."""
    from skills.spatial._lib.domains import identify_domains_leiden, refine_spatial_domains

    adata = _make_synthetic_adata()
    identify_domains_leiden(adata, resolution=0.5)
    refined = refine_spatial_domains(adata, threshold=0.5, k=5)

    assert len(refined) == adata.n_obs
    assert refined.index.equals(adata.obs.index)
