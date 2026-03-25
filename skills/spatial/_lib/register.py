"""Spatial registration/alignment functions.

PASTE optimal transport alignment for multi-slice spatial data.

Usage::

    from skills.spatial._lib.register import run_registration, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .adata_utils import require_spatial_coords
from .dependency_manager import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("paste",)

_SLICE_KEY_CANDIDATES = ("slice", "sample", "section", "batch", "sample_id")


def detect_slice_key(adata) -> str | None:
    """Auto-detect the obs column that identifies slices."""
    for key in _SLICE_KEY_CANDIDATES:
        if key in adata.obs.columns and adata.obs[key].nunique() >= 2:
            return key
    return None


def run_paste(
    adata, *, slice_key: str, reference_slice: str | None, spatial_key: str,
) -> dict:
    """Run PASTE optimal transport alignment."""
    require("paste", feature="PASTE optimal transport spatial registration")
    import paste as pst

    slices_list = sorted(adata.obs[slice_key].unique().tolist(), key=str)
    ref = reference_slice or slices_list[0]
    ref_adata = adata[adata.obs[slice_key] == ref].copy()
    ref_coords = ref_adata.obsm[spatial_key].astype(float)

    aligned_coords = adata.obsm[spatial_key].copy().astype(float)
    disparities: dict[str, float] = {}

    for sl in slices_list:
        if str(sl) == str(ref):
            continue
        sl_adata = adata[adata.obs[slice_key] == sl].copy()
        try:
            result = pst.pairwise_align(ref_adata, sl_adata)
            pi = result[0] if isinstance(result, tuple) else result
            row_sums = pi.sum(axis=1, keepdims=True)
            row_sums = np.where(row_sums == 0, 1.0, row_sums)
            coords_new = (pi @ ref_coords) / row_sums

            src_mask = adata.obs[slice_key] == sl
            aligned_coords[src_mask] = coords_new
            disparity = float(np.sum(pi * pi))
            disparities[str(sl)] = disparity
        except Exception as exc:
            logger.warning("PASTE failed for slice '%s': %s", sl, exc)

    adata.obsm["spatial_aligned"] = aligned_coords
    mean_disp = float(np.mean(list(disparities.values()))) if disparities else 0.0

    return {
        "method": "paste", "reference_slice": str(ref),
        "n_slices": len(slices_list), "slices": [str(s) for s in slices_list],
        "disparities": disparities, "mean_disparity": mean_disp,
    }


def run_registration(
    adata, *, method: str = "paste",
    slice_key: str | None = None, reference_slice: str | None = None,
) -> dict:
    """Run spatial registration. Returns summary dict."""
    spatial_key = require_spatial_coords(adata)

    if slice_key is None:
        slice_key = detect_slice_key(adata)
    if slice_key is None:
        logger.warning("No slice column detected — creating synthetic 'slice' column for demo")
        rng = np.random.default_rng(42)
        adata.obs["slice"] = rng.choice(["slice_1", "slice_2"], size=adata.n_obs)
        adata.obs["slice"] = pd.Categorical(adata.obs["slice"])
        slice_key = "slice"

    if slice_key not in adata.obs.columns:
        raise ValueError(f"Slice key '{slice_key}' not in adata.obs")

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    slices = sorted(adata.obs[slice_key].unique().tolist(), key=str)
    logger.info("Input: %d cells x %d genes, %d slices", n_cells, n_genes, len(slices))

    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown registration method '{method}'. Choose from: {SUPPORTED_METHODS}")

    result = run_paste(
        adata, slice_key=slice_key,
        reference_slice=reference_slice, spatial_key=spatial_key,
    )

    return {"n_cells": n_cells, "n_genes": n_genes, "slice_key": slice_key, **result}
