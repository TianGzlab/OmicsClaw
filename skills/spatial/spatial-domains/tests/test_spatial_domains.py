"""Tests for the spatial-domains skill."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

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


def test_dispatch_graphst_maps_data_type_to_datatype(monkeypatch):
    """GraphST dispatch should forward data_type into the wrapper's datatype arg."""
    from skills.spatial._lib import domains as domains_mod

    adata = _make_synthetic_adata()
    captured: dict[str, object] = {}

    def fake_graphst(input_adata, *, n_domains=7, epochs=None, datatype=None, **kwargs):
        captured["adata"] = input_adata
        captured["n_domains"] = n_domains
        captured["epochs"] = epochs
        captured["datatype"] = datatype
        captured.update(kwargs)
        return {"method": "graphst", "n_domains": 2, "domain_counts": {}}

    monkeypatch.setattr(domains_mod, "identify_domains_graphst", fake_graphst)

    result = domains_mod.dispatch_method(
        "graphst",
        adata,
        n_domains=7,
        epochs=1,
        data_type="slide_seq",
    )

    assert result["method"] == "graphst"
    assert captured["adata"] is adata
    assert captured["n_domains"] == 7
    assert captured["epochs"] == 1
    assert captured["datatype"] == "slide_seq"


def test_graphst_datatype_infers_slide_from_input_filename():
    """Slide-seqV2 filenames should route GraphST away from dense 10X graph construction."""
    spec = importlib.util.spec_from_file_location("spatial_domains_script", SKILL_SCRIPT)
    assert spec is not None and spec.loader is not None
    spatial_domains_script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(spatial_domains_script)

    adata = _make_synthetic_adata()

    assert (
        spatial_domains_script._infer_graphst_data_type(
            adata,
            "/data/slideseqv2_mouse_hippocampus.h5ad",
            explicit_data_type=None,
        )
        == "slide_seq"
    )


def test_graphst_large_slide_graph_preparation_uses_sparse_adjacency(monkeypatch):
    """GraphST Slide/Stereo preparation must avoid dense n_spot x n_spot arrays."""
    from skills.spatial._lib import domains as domains_mod

    adata = _make_synthetic_adata(n_obs=20, n_vars=30)
    adata_work = adata.copy()

    domains_mod._prepare_graphst_sparse_slide_graph(adata_work, n_neighbors=3)

    assert sp.issparse(adata_work.obsm["adj"])
    assert sp.issparse(adata_work.obsm["graph_neigh"])
    assert adata_work.obsm["adj"].shape == (adata_work.n_obs, adata_work.n_obs)
    assert adata_work.obsm["graph_neigh"].nnz <= adata_work.n_obs * 3


def test_graphst_sparse_init_patch_keeps_readout_mask_sparse():
    """GraphST's constructor must not densify Slide/Stereo readout masks."""
    import importlib
    import torch

    pytest.importorskip("GraphST")
    from skills.spatial._lib import domains as domains_mod

    graphst_module = importlib.import_module("GraphST.GraphST")
    adata = _make_synthetic_adata(n_obs=20, n_vars=30)
    adata_work = adata.copy()

    domains_mod._prepare_graphst_sparse_slide_graph(adata_work, n_neighbors=3)
    domains_mod._patch_graphst_sparse_readout()
    domains_mod._patch_graphst_sparse_init()

    model = graphst_module.GraphST(
        adata_work,
        device=torch.device("cpu"),
        datatype="Slide",
        epochs=1,
    )

    assert model.adj.is_sparse
    assert model.graph_neigh.is_sparse


def test_graphst_large_embedding_clustering_uses_minibatch_kmeans():
    """Large GraphST runs should avoid slow repeated Leiden resolution searches."""
    import anndata
    from skills.spatial._lib import domains as domains_mod

    rng = np.random.default_rng(42)
    clusters = [
        np.full((8, 6), fill_value=i, dtype=np.float32)
        + rng.normal(0, 0.01, size=(8, 6)).astype(np.float32)
        for i in range(4)
    ]
    adata = anndata.AnnData(X=np.ones((32, 10), dtype=np.float32))
    adata.obsm["emb"] = np.vstack(clusters)

    labels, clustering_name = domains_mod._cluster_graphst_embedding(
        adata,
        n_domains=4,
        random_seed=42,
        large_threshold=10,
    )

    assert clustering_name == "minibatch_kmeans"
    assert len(labels) == adata.n_obs
    assert len(set(np.asarray(labels).astype(str))) == 4


def test_large_gallery_does_not_compute_missing_umap(monkeypatch):
    """Large outputs should not spend extra time computing UMAP for the gallery."""
    spec = importlib.util.spec_from_file_location("spatial_domains_script", SKILL_SCRIPT)
    assert spec is not None and spec.loader is not None
    spatial_domains_script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(spatial_domains_script)

    adata = _make_synthetic_adata(n_obs=30, n_vars=30)
    adata.obsm.pop("X_umap", None)

    def fail_umap(*_args, **_kwargs):
        raise AssertionError("UMAP should not be computed for large gallery outputs")

    monkeypatch.setattr(spatial_domains_script.sc.tl, "umap", fail_umap)

    spatial_domains_script._ensure_umap_for_gallery(adata, max_auto_obs=10)

    assert "X_umap" not in adata.obsm


def test_cli_accepts_epochs_and_data_type_flags(tmp_output):
    """CLI surface should expose the GraphST-relevant routing flags."""
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--help",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(SKILL_SCRIPT.parent),
    )

    assert result.returncode == 0
    assert "--epochs" in result.stdout
    assert "--data-type" in result.stdout


def test_refine_spatial_domains():
    """Spatial refinement should produce labels for all cells."""
    from skills.spatial._lib.domains import identify_domains_leiden, refine_spatial_domains

    adata = _make_synthetic_adata()
    identify_domains_leiden(adata, resolution=0.5)
    refined = refine_spatial_domains(adata, threshold=0.5, k=5)

    assert len(refined) == adata.n_obs
    assert refined.index.equals(adata.obs.index)
