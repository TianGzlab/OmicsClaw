"""Tests for the spatial-register skill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "spatial_register.py"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "register_out"


def _make_two_slice_adata(n_per_slice: int = 50, n_vars: int = 30):
    """Create a minimal two-slice AnnData for unit tests."""
    import anndata
    import pandas as pd

    rng = np.random.default_rng(42)
    n_obs = n_per_slice * 2
    counts = rng.poisson(5, size=(n_obs, n_vars)).astype(np.float32)
    adata = anndata.AnnData(X=counts)
    adata.var_names = [f"Gene_{i}" for i in range(n_vars)]
    adata.obs_names = [f"Cell_{i}" for i in range(n_obs)]

    # Spatial coords with offset for slice_2
    coords = rng.uniform(0, 1000, size=(n_obs, 2)).astype(np.float32)
    coords[n_per_slice:] += 200  # simulate misalignment
    adata.obsm["spatial"] = coords

    # Slice labels
    labels = ["slice_1"] * n_per_slice + ["slice_2"] * n_per_slice
    adata.obs["slice"] = pd.Categorical(labels)

    return adata


# -----------------------------------------------------------------------
# CLI integration tests (existing)
# -----------------------------------------------------------------------


def test_demo_mode(tmp_output):
    """spatial-register --demo should run without error."""
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


def test_demo_report_content(tmp_output):
    """Report should contain registration sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Registration" in report
    assert "Disclaimer" in report
    assert "disparity" in report.lower()


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "spatial-register"
    assert "summary" in data
    assert data["summary"]["n_slices"] >= 2
    assert data["summary"]["method"] == "paste"


def test_demo_aligned_coords(tmp_output):
    """processed.h5ad should contain spatial_aligned coords."""
    import anndata
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True, text=True, timeout=180, cwd=str(SKILL_SCRIPT.parent),
    )
    adata = anndata.read_h5ad(tmp_output / "processed.h5ad")
    assert "spatial_aligned" in adata.obsm


# -----------------------------------------------------------------------
# Unit tests for registration library
# -----------------------------------------------------------------------


def test_supported_methods():
    """SUPPORTED_METHODS should include both paste and stalign."""
    from skills.spatial._lib.register import SUPPORTED_METHODS

    assert "paste" in SUPPORTED_METHODS
    assert "stalign" in SUPPORTED_METHODS


def test_detect_slice_key():
    """Should auto-detect 'slice' column."""
    from skills.spatial._lib.register import detect_slice_key

    adata = _make_two_slice_adata()
    key = detect_slice_key(adata)
    assert key == "slice"


def test_detect_slice_key_missing():
    """Should return None when no slice column exists."""
    import anndata
    from skills.spatial._lib.register import detect_slice_key

    adata = anndata.AnnData(X=np.ones((10, 5)))
    assert detect_slice_key(adata) is None


def test_dispatch_invalid_method():
    """Should raise ValueError for unknown method."""
    from skills.spatial._lib.register import run_registration

    adata = _make_two_slice_adata()
    with pytest.raises(ValueError, match="Unknown registration method"):
        run_registration(adata, method="nonexistent", slice_key="slice")


def test_stalign_requires_two_slices():
    """STalign should raise ValueError if not exactly 2 slices."""
    import anndata
    import pandas as pd

    try:
        import STalign  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        pytest.skip("STalign or torch not installed")

    from skills.spatial._lib.register import run_stalign

    rng = np.random.default_rng(42)
    n = 90
    adata = anndata.AnnData(X=rng.poisson(5, (n, 20)).astype(np.float32))
    adata.obsm["spatial"] = rng.uniform(0, 1000, (n, 2)).astype(np.float32)
    adata.obs["slice"] = pd.Categorical(
        rng.choice(["s1", "s2", "s3"], size=n)
    )

    with pytest.raises(ValueError, match="pairwise registration"):
        run_stalign(adata, slice_key="slice", reference_slice=None, spatial_key="spatial")


def test_prepare_stalign_image():
    """Image preparation should produce normalized non-negative output."""
    try:
        import torch  # noqa: F401
    except ImportError:
        pytest.skip("torch not installed")

    from skills.spatial._lib.register import _prepare_stalign_image

    rng = np.random.default_rng(42)
    coords = rng.uniform(0, 1000, (100, 2)).astype(np.float32)
    intensity = rng.uniform(0, 1, 100).astype(np.float32)

    xgrid, image = _prepare_stalign_image(coords, intensity, (200, 200))

    assert len(xgrid) == 2
    assert image.shape == (200, 200)
    assert image.min() >= 0
    assert image.max() <= 1.0 + 1e-6
