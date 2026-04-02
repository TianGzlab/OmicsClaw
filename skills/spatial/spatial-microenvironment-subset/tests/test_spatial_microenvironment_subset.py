from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd

from skills.spatial._lib.microenvironment import (
    compute_radius_native,
    extract_microenvironment_subset,
    infer_microns_per_coordinate_unit,
)


SKILL_SCRIPT = (
    Path(__file__).resolve().parent.parent / "spatial_microenvironment_subset.py"
)


def _make_test_adata() -> ad.AnnData:
    obs = pd.DataFrame(
        {
            "cell_type": ["tumor", "stroma", "immune", "immune"],
        },
        index=["cell_0", "cell_1", "cell_2", "cell_3"],
    )
    var = pd.DataFrame(index=["GeneA", "GeneB"])
    adata = ad.AnnData(X=np.ones((4, 2), dtype=float), obs=obs, var=var)
    adata.obsm["spatial"] = np.array(
        [
            [0.0, 0.0],
            [30.0, 0.0],
            [80.0, 0.0],
            [150.0, 0.0],
        ]
    )
    return adata


def test_extract_microenvironment_subset_radius_native():
    adata = _make_test_adata()

    subset, summary = extract_microenvironment_subset(
        adata,
        center_key="cell_type",
        center_values=["tumor"],
        radius_native=50.0,
    )

    assert list(subset.obs_names) == ["cell_0", "cell_1"]
    assert summary["n_center_observations"] == 1
    assert summary["n_neighbor_observations"] == 1
    assert set(subset.obs["microenv_role"].astype(str)) == {"center", "neighbor"}


def test_extract_microenvironment_subset_target_filter():
    adata = _make_test_adata()

    subset, summary = extract_microenvironment_subset(
        adata,
        center_key="cell_type",
        center_values=["tumor"],
        target_key="cell_type",
        target_values=["immune"],
        radius_native=100.0,
    )

    assert list(subset.obs_names) == ["cell_0", "cell_2"]
    assert summary["target_key"] == "cell_type"
    assert summary["target_values"] == ["immune"]


def test_infer_visium_scale_from_spot_diameter_assumption():
    adata = _make_test_adata()
    adata.uns["spatial"] = {
        "library": {
            "scalefactors": {
                "spot_diameter_fullres": 110.0,
            }
        }
    }

    scale = infer_microns_per_coordinate_unit(adata, data_type="visium")
    radius_native, radius_um = compute_radius_native(
        radius_native=None,
        radius_microns=55.0,
        scale=scale,
    )

    assert scale.microns_per_coordinate_unit == 0.5
    assert radius_native == 110.0
    assert radius_um == 55.0


def test_cli_smoke(tmp_path: Path):
    adata = _make_test_adata()
    input_path = tmp_path / "input.h5ad"
    output_dir = tmp_path / "out"
    adata.write_h5ad(input_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_dir),
            "--center-key",
            "cell_type",
            "--center-values",
            "tumor",
            "--radius-native",
            "60",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "spatial_microenvironment_subset.h5ad").exists()
    assert (output_dir / "tables" / "selected_observations.csv").exists()
    assert (output_dir / "report.md").exists()
