"""Tests for the spatial-integrate skill."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_integrate.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SKILL_SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT.parent))


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "integrate_out"


def _make_multi_batch_adata(n_obs: int = 100, n_vars: int = 50):
    """Create a minimal preprocessed multi-batch AnnData for unit tests."""
    import anndata
    import pandas as pd
    import scanpy as sc

    rng = np.random.default_rng(42)
    counts = rng.poisson(5, size=(n_obs, n_vars)).astype(np.float32)
    adata = anndata.AnnData(X=counts.copy())
    adata.var_names = [f"Gene_{i}" for i in range(n_vars)]
    adata.obs_names = [f"Cell_{i}" for i in range(n_obs)]
    adata.obsm["spatial"] = rng.uniform(0, 1000, size=(n_obs, 2))

    # Assign batches
    adata.obs["batch"] = pd.Categorical(
        rng.choice(["batch_A", "batch_B"], size=n_obs)
    )

    # Log-normalize
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # PCA + neighbors
    sc.tl.pca(adata, n_comps=min(20, n_vars - 1, n_obs - 1))
    sc.pp.neighbors(adata, n_neighbors=min(10, n_obs - 1), n_pcs=min(10, 20))
    sc.tl.umap(adata)

    return adata


# -----------------------------------------------------------------------
# CLI integration tests (existing)
# -----------------------------------------------------------------------


def test_demo_mode(tmp_output):
    """spatial-integrate --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "processed.h5ad").exists()
    assert (tmp_output / "tables" / "integration_metrics.csv").exists()


def test_demo_outputs_gallery_contract(tmp_output):
    """Demo mode should export gallery manifests, figure data, and reproducibility helpers."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "figures" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "manifest.json").exists()
    assert (tmp_output / "figure_data" / "batch_sizes.csv").exists()
    assert (tmp_output / "figure_data" / "integration_metrics.csv").exists()
    assert (tmp_output / "figure_data" / "umap_before_points.csv").exists()
    assert (tmp_output / "figure_data" / "umap_after_points.csv").exists()
    assert (tmp_output / "tables" / "batch_sizes.csv").exists()
    assert (tmp_output / "tables" / "integration_observations.csv").exists()
    assert (tmp_output / "reproducibility" / "r_visualization.sh").exists()


def test_demo_gallery_manifests_have_roles(tmp_output):
    """The standard integration gallery should emit figure and figure-data manifests."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    figures_manifest = json.loads((tmp_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((tmp_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-integration-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-integrate"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-integration-gallery"


def test_demo_report_content(tmp_output):
    """Report should contain integration-related sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Integration" in report
    assert "Batch" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-integrate"
    assert "summary" in data
    assert data["summary"]["n_batches"] >= 2
    assert "batch_mixing_before" in data["summary"]
    assert "batch_mixing_after" in data["summary"]
    assert data["data"]["visualization"]["recipe_id"] == "standard-spatial-integration-gallery"
    assert data["data"]["visualization"]["embedding_key"] == data["summary"]["embedding_key"]


# -----------------------------------------------------------------------
# Unit tests for integration library
# -----------------------------------------------------------------------


def test_harmony_integration():
    """Harmony should produce corrected PCA embedding."""
    try:
        import harmonypy  # noqa: F401
    except ImportError:
        pytest.skip("harmonypy not installed")

    from skills.spatial._lib.integration import integrate_harmony

    adata = _make_multi_batch_adata()
    result = integrate_harmony(adata, batch_key="batch")

    assert result["method"] == "harmony"
    assert result["embedding_key"] == "X_pca_harmony"
    assert "X_pca_harmony" in adata.obsm
    assert adata.obsm["X_pca_harmony"].shape[0] == adata.n_obs


def test_batch_mixing_entropy():
    """Batch mixing entropy should return a value between 0 and 1."""
    from skills.spatial._lib.integration import compute_batch_mixing

    adata = _make_multi_batch_adata()
    mixing = compute_batch_mixing(adata, "batch")

    assert 0.0 <= mixing <= 1.0


def test_batch_mixing_single_batch():
    """Batch mixing with a single batch should return 0."""
    import pandas as pd
    from skills.spatial._lib.integration import compute_batch_mixing

    adata = _make_multi_batch_adata()
    adata.obs["batch"] = pd.Categorical(["batch_A"] * adata.n_obs)
    mixing = compute_batch_mixing(adata, "batch")

    assert mixing == 0.0


def test_run_integration_missing_batch_key():
    """Should raise ValueError if batch key doesn't exist."""
    from skills.spatial._lib.integration import run_integration

    adata = _make_multi_batch_adata()
    with pytest.raises(ValueError, match="Batch key.*not in adata.obs"):
        run_integration(adata, method="harmony", batch_key="nonexistent_key")


def test_run_integration_single_batch():
    """Should raise ValueError with only 1 batch."""
    import pandas as pd
    from skills.spatial._lib.integration import run_integration

    adata = _make_multi_batch_adata()
    adata.obs["batch"] = pd.Categorical(["batch_A"] * adata.n_obs)
    with pytest.raises(ValueError, match="Only 1 batch found"):
        run_integration(adata, method="harmony", batch_key="batch")


def test_run_integration_invalid_method():
    """Should raise ValueError for unknown method."""
    from skills.spatial._lib.integration import run_integration

    adata = _make_multi_batch_adata()
    with pytest.raises(ValueError, match="Unknown integration method"):
        run_integration(adata, method="nonexistent_method", batch_key="batch")


def test_supported_methods():
    """SUPPORTED_METHODS should list all three methods."""
    from skills.spatial._lib.integration import SUPPORTED_METHODS

    assert set(SUPPORTED_METHODS) == {"harmony", "bbknn", "scanorama"}


def test_run_integration_persists_visualization_snapshots(monkeypatch):
    """run_integration should persist explicit before/after UMAP snapshots to adata."""
    import scanpy as sc

    from skills.spatial._lib import integration as integration_lib

    adata = _make_multi_batch_adata()
    umap_before = adata.obsm["X_umap"].copy()

    def _fake_integrate_harmony(adata, batch_key, **kwargs):
        adata.obsm["X_pca_harmony"] = adata.obsm["X_pca"] + 0.01
        sc.pp.neighbors(adata, use_rep="X_pca_harmony", n_neighbors=10)
        sc.tl.umap(adata)
        return {
            "method": "harmony",
            "embedding_key": "X_pca_harmony",
            "representation_type": "embedding",
            "effective_params": {"harmony_theta": 2.0},
        }

    monkeypatch.setattr(integration_lib, "integrate_harmony", _fake_integrate_harmony)

    summary = integration_lib.run_integration(adata, method="harmony", batch_key="batch")

    assert "X_umap_before_integration" in adata.obsm
    assert "X_umap_after_integration" in adata.obsm
    assert np.allclose(adata.obsm["X_umap_before_integration"], umap_before)
    assert summary["method"] == "harmony"
    assert adata.uns["spatial_integration"]["method"] == "harmony"


def test_generate_figures_uses_persisted_after_umap_snapshot(tmp_path, monkeypatch):
    """generate_figures should use persisted snapshots rather than the mutable current X_umap."""
    import matplotlib.pyplot as plt

    from spatial_integrate import generate_figures

    adata = _make_multi_batch_adata()
    adata.obs["leiden"] = adata.obs["batch"].astype(str)
    before = adata.obsm["X_umap"].copy()
    after = before + 5.0
    tampered = np.zeros_like(before)
    adata.obsm["X_umap_before_integration"] = before
    adata.obsm["X_umap_after_integration"] = after
    adata.obsm["X_umap"] = tampered.copy()
    adata.obsm["X_pca_harmony"] = adata.obsm["X_pca"].copy()
    adata.obs["batch_entropy_before"] = np.linspace(0.1, 0.4, adata.n_obs)
    adata.obs["batch_entropy_after"] = np.linspace(0.3, 0.8, adata.n_obs)
    adata.obs["batch_entropy_delta"] = adata.obs["batch_entropy_after"] - adata.obs["batch_entropy_before"]

    seen = []

    def _fake_plot_integration(adata, params, subtype=None, batch_key=None, cluster_key=None):
        seen.append(("integration", subtype, np.asarray(adata.obsm["X_umap"]).copy()))
        return plt.figure()

    def _fake_plot_features(adata, params=None, feature=None, basis=None):
        seen.append(("feature", getattr(params, "feature", feature), np.asarray(adata.obsm["X_umap"]).copy()))
        return plt.figure()

    monkeypatch.setattr("spatial_integrate.plot_integration", _fake_plot_integration)
    monkeypatch.setattr("spatial_integrate.plot_features", _fake_plot_features)

    figures = generate_figures(
        adata,
        tmp_path,
        {
            "method": "harmony",
            "embedding_key": "X_pca_harmony",
            "representation_type": "embedding",
            "batch_mixing_before": 0.2,
            "batch_mixing_after": 0.7,
            "batch_mixing_gain": 0.5,
        },
        batch_key="batch",
    )

    assert len(figures) >= 6
    integration_calls = [item for item in seen if item[0] == "integration"]
    feature_calls = [item for item in seen if item[0] == "feature"]

    assert np.allclose(integration_calls[0][2], before)
    assert np.allclose(integration_calls[1][2], after)
    assert np.allclose(integration_calls[2][2], after)
    assert np.allclose(integration_calls[3][2], after)
    assert feature_calls
    assert np.allclose(feature_calls[0][2], after)
    assert np.allclose(adata.obsm["X_umap"], tampered)


def test_collect_run_configuration_harmony():
    """CLI parameter collection should keep Harmony-specific flags isolated."""
    from spatial_integrate import _collect_run_configuration

    args = argparse.Namespace(
        method="harmony",
        batch_key="sample_id",
        harmony_theta=3.5,
        harmony_lambda=-1.0,
        harmony_max_iter=15,
        bbknn_neighbors_within_batch=3,
        bbknn_n_pcs=50,
        bbknn_trim=None,
        scanorama_knn=20,
        scanorama_sigma=15.0,
        scanorama_alpha=0.1,
        scanorama_batch_size=5000,
    )

    params, method_kwargs = _collect_run_configuration(args)

    assert params == {
        "method": "harmony",
        "batch_key": "sample_id",
        "harmony_theta": 3.5,
        "harmony_lambda": -1.0,
        "harmony_max_iter": 15,
    }
    assert method_kwargs == {
        "theta": 3.5,
        "lamb": -1.0,
        "max_iter_harmony": 15,
    }


def test_write_report_repro_command_is_method_specific(tmp_path):
    """write_reproducibility should only serialize flags for the selected method."""
    from spatial_integrate import write_report, write_reproducibility

    output_dir = tmp_path / "report_out"
    output_dir.mkdir()
    summary = {
        "n_cells": 100,
        "n_genes": 50,
        "n_batches": 2,
        "batch_sizes": {"A": 40, "B": 60},
        "method": "bbknn",
        "embedding_key": "X_pca",
        "representation_type": "neighbor_graph",
        "batch_mixing_before": 0.21,
        "batch_mixing_after": 0.64,
        "effective_params": {
            "bbknn_neighbors_within_batch": 5,
            "bbknn_n_pcs": 30,
            "bbknn_trim": 60,
        },
    }
    params = {
        "method": "bbknn",
        "batch_key": "batch",
        "bbknn_neighbors_within_batch": 5,
        "bbknn_n_pcs": 30,
        "bbknn_trim": 60,
    }

    write_report(output_dir, summary, None, params)
    write_reproducibility(output_dir, params, None)

    cmd = (output_dir / "reproducibility" / "commands.sh").read_text()
    assert "skills/spatial/spatial-integrate/spatial_integrate.py" in cmd
    assert "--bbknn-neighbors-within-batch 5" in cmd
    assert "--bbknn-n-pcs 30" in cmd
    assert "--bbknn-trim 60" in cmd
    assert "--harmony-theta" not in cmd
    assert (output_dir / "reproducibility" / "r_visualization.sh").exists()


def test_scanorama_batch_order_helper_detects_interleaved_batches():
    """Interleaved batches should trigger a stable reorder for Scanorama."""
    import anndata
    import pandas as pd

    from skills.spatial._lib.integration import _get_scanorama_batch_order

    adata = anndata.AnnData(X=np.ones((6, 3), dtype=np.float32))
    adata.obs["batch"] = pd.Categorical(["A", "B", "A", "C", "B", "C"])

    order = _get_scanorama_batch_order(adata, "batch")

    assert order is not None
    sorted_labels = np.asarray(adata.obs["batch"].astype(str))[order]
    assert sorted_labels.tolist() == ["A", "A", "B", "B", "C", "C"]
