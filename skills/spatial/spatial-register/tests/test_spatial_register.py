"""Tests for the spatial-register skill."""

from __future__ import annotations

import argparse
import importlib.util
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
if str(SKILL_SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT.parent))


def _load_skill_module():
    spec = importlib.util.spec_from_file_location("spatial_register", SKILL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_skill(output_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), *args, "--output", str(output_dir)],
        capture_output=True,
        text=True,
        timeout=240,
        cwd=str(SKILL_SCRIPT.parent),
    )


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "register_out"


@pytest.fixture(scope="module")
def demo_output(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("spatial_register_demo")
    result = _run_skill(output_dir, "--demo")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return output_dir


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

    coords = rng.uniform(0, 1000, size=(n_obs, 2)).astype(np.float32)
    coords[n_per_slice:] += 200
    adata.obsm["spatial"] = coords

    labels = ["slice_1"] * n_per_slice + ["slice_2"] * n_per_slice
    adata.obs["slice"] = pd.Categorical(labels)

    return adata


# -----------------------------------------------------------------------
# CLI integration tests
# -----------------------------------------------------------------------


def test_demo_mode(demo_output):
    """spatial-register --demo should run without error."""
    assert (demo_output / "report.md").exists()
    assert (demo_output / "result.json").exists()
    assert (demo_output / "processed.h5ad").exists()
    assert (demo_output / "tables" / "registration_summary.csv").exists()
    assert (demo_output / "tables" / "registration_metrics.csv").exists()
    assert (demo_output / "reproducibility" / "commands.sh").exists()


def test_demo_outputs_gallery_contract(demo_output):
    """Demo mode should export gallery manifests, figure data, and the R helper."""
    assert (demo_output / "figures" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "manifest.json").exists()
    assert (demo_output / "figure_data" / "registration_points.csv").exists()
    assert (demo_output / "figure_data" / "registration_shift_by_slice.csv").exists()
    assert (demo_output / "figure_data" / "registration_run_summary.csv").exists()
    assert (demo_output / "reproducibility" / "r_visualization.sh").exists()

    run_summary = (demo_output / "figure_data" / "registration_run_summary.csv").read_text()
    assert "mean_disparity" in run_summary
    assert "shift_distance_column" in run_summary


def test_demo_gallery_manifests_have_roles(demo_output):
    """The standard registration gallery should emit figure and figure-data manifests."""
    figures_manifest = json.loads((demo_output / "figures" / "manifest.json").read_text())
    figure_data_manifest = json.loads((demo_output / "figure_data" / "manifest.json").read_text())

    assert figures_manifest["recipe_id"] == "standard-spatial-register-gallery"
    assert any(plot["role"] == "overview" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "diagnostic" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "supporting" for plot in figures_manifest["plots"])
    assert any(plot["role"] == "uncertainty" for plot in figures_manifest["plots"])
    assert figure_data_manifest["skill"] == "spatial-register"
    assert figure_data_manifest["recipe_id"] == "standard-spatial-register-gallery"


def test_demo_aligned_coords_and_shift_annotations(demo_output):
    """processed.h5ad should contain aligned coordinates and gallery-derived shift annotations."""
    import anndata

    adata = anndata.read_h5ad(demo_output / "processed.h5ad")
    assert "spatial_aligned" in adata.obsm
    assert "registration_shift_distance" in adata.obs.columns
    assert "registration_is_reference_slice" in adata.obs.columns


def test_demo_report_content(demo_output):
    """Report should contain registration interpretation and visualization sections."""
    report = (demo_output / "report.md").read_text()
    assert "Spatial Registration Report" in report
    assert "Interpretation Notes" in report
    assert "Visualization Outputs" in report
    assert "Disclaimer" in report


def test_demo_result_json(demo_output):
    """result.json should contain visualization metadata for downstream tools."""
    data = json.loads((demo_output / "result.json").read_text())
    assert data["skill"] == "spatial-register"
    assert "summary" in data
    assert data["summary"]["n_slices"] >= 2
    assert data["summary"]["method"] == "paste"
    assert "visualization" in data["data"]
    assert data["data"]["visualization"]["recipe_id"] == "standard-spatial-register-gallery"
    assert data["data"]["visualization"]["aligned_coordinate_key"] == "spatial_aligned"
    assert data["data"]["visualization"]["shift_distance_column"] == "registration_shift_distance"


def test_collect_run_configuration_paste():
    """Only PASTE parameters should be emitted for a PASTE run."""
    module = _load_skill_module()

    args = argparse.Namespace(
        method="paste",
        slice_key="sample",
        reference_slice="slice_1",
        paste_alpha=0.25,
        paste_dissimilarity="euclidean",
        paste_use_gpu=True,
        stalign_niter=3000,
        stalign_image_size=600,
        stalign_a=800.0,
        use_expression=True,
    )

    params, method_kwargs = module._collect_run_configuration(args)

    assert params == {
        "method": "paste",
        "slice_key": "sample",
        "reference_slice": "slice_1",
        "paste_alpha": 0.25,
        "paste_dissimilarity": "euclidean",
        "paste_use_gpu": True,
    }
    assert method_kwargs == {
        "alpha": 0.25,
        "dissimilarity": "euclidean",
        "use_gpu": True,
    }


def test_write_report_records_effective_params(tmp_path):
    """Report and reproducibility output should keep method-specific params and visualization metadata."""
    module = _load_skill_module()

    summary = {
        "method": "paste",
        "n_cells": 100,
        "n_genes": 30,
        "slice_key": "slice",
        "reference_slice": "slice_1",
        "n_slices": 2,
        "slices": ["slice_1", "slice_2"],
        "mean_disparity": 0.123456,
        "n_common_genes": 20,
        "disparities": {"slice_2": 0.123456},
        "effective_params": {
            "paste_alpha": 0.2,
            "paste_dissimilarity": "kl",
            "paste_use_gpu": False,
        },
    }
    params = {
        "method": "paste",
        "slice_key": "slice",
        "reference_slice": "slice_1",
        "paste_alpha": 0.2,
        "paste_dissimilarity": "kl",
        "paste_use_gpu": False,
    }
    gallery_context = {
        "spatial_key": "spatial",
        "has_aligned": True,
        "shift_distance_col": "registration_shift_distance",
        "reference_slice_col": "registration_is_reference_slice",
        "shift_summary_df": module.pd.DataFrame(
            {
                "slice": ["slice_1", "slice_2"],
                "n_observations": [50, 50],
                "mean_shift": [0.0, 12.5],
                "median_shift": [0.0, 11.8],
                "max_shift": [0.0, 22.1],
                "is_reference": [True, False],
            }
        ),
        "disparity_df": module.pd.DataFrame(
            {
                "slice": ["slice_2"],
                "disparity": [0.123456],
            }
        ),
        "metrics_df": module.pd.DataFrame(
            {
                "slice": ["slice_1", "slice_2"],
                "n_observations": [50, 50],
                "mean_shift": [0.0, 12.5],
                "median_shift": [0.0, 11.8],
                "max_shift": [0.0, 22.1],
                "is_reference": [True, False],
                "disparity": [module.np.nan, 0.123456],
            }
        ),
        "points_df": module.pd.DataFrame(
            {
                "observation": ["obs1", "obs2"],
                "slice": ["slice_1", "slice_2"],
                "original_x": [0.0, 1.0],
                "original_y": [0.0, 1.0],
                "aligned_x": [0.0, 2.0],
                "aligned_y": [0.0, 2.0],
                "delta_x": [0.0, 1.0],
                "delta_y": [0.0, 1.0],
                "shift_distance": [0.0, 1.414],
                "is_reference_slice": [True, False],
            }
        ),
    }

    module.export_tables(tmp_path, summary, gallery_context=gallery_context)
    module.write_report(tmp_path, summary, None, params, gallery_context=gallery_context)
    module.write_reproducibility(tmp_path, params, summary, input_file=None, demo_mode=False)

    report = (tmp_path / "report.md").read_text()
    assert "Effective Method Parameters" in report
    assert "Visualization Outputs" in report
    assert "`paste_alpha`: 0.2" in report

    result = json.loads((tmp_path / "result.json").read_text())
    assert result["skill"] == "spatial-register"
    assert result["data"]["effective_params"]["paste_dissimilarity"] == "kl"
    assert result["data"]["visualization"]["recipe_id"] == "standard-spatial-register-gallery"
    assert result["data"]["visualization"]["shift_distance_column"] == "registration_shift_distance"

    commands = (tmp_path / "reproducibility" / "commands.sh").read_text()
    assert "--paste-alpha 0.2" in commands
    assert "--paste-dissimilarity kl" in commands
    assert "--stalign-a" not in commands

    assert (tmp_path / "tables" / "registration_summary.csv").exists()
    assert (tmp_path / "tables" / "registration_metrics.csv").exists()
    assert (tmp_path / "reproducibility" / "r_visualization.sh").exists()


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


def test_run_registration_requires_real_slice_key():
    """Registration should fail fast instead of fabricating slice labels."""
    import anndata
    from skills.spatial._lib.register import run_registration

    adata = anndata.AnnData(X=np.ones((10, 5), dtype=np.float32))
    adata.obsm["spatial"] = np.ones((10, 2), dtype=np.float32)

    with pytest.raises(ValueError, match="Could not detect a slice label column automatically"):
        run_registration(adata, method="paste")


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
