"""Tests for the spatial-integrate skill."""

from __future__ import annotations

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
