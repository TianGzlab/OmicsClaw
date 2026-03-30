"""Spatial registration/alignment functions.

Provides two registration methods for multi-slice spatial data:

- **PASTE**: Optimal transport alignment — aligns N slices to a reference
  using gene-expression-aware probabilistic transport maps.
  Ref: Zeira et al., *Nature Methods* 2022.

- **STalign**: Diffeomorphic mapping via LDDMM — pairwise registration
  that rasterizes point-cloud coordinates into images and computes a
  smooth deformation field to warp the source onto the target.
  Ref: Clifton et al., *Nature Communications* 2023.

Usage::

    from skills.spatial._lib.register import run_registration, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .adata_utils import require_spatial_coords
from .dependency_manager import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("paste", "stalign")
VALID_PASTE_DISSIMILARITIES = ("kl", "euclidean", "Euclidean")

_SLICE_KEY_CANDIDATES = ("slice", "sample", "section", "batch", "sample_id")

METHOD_PARAM_DEFAULTS = {
    "paste": {
        "alpha": 0.1,
        "dissimilarity": "kl",
        "use_gpu": False,
    },
    "stalign": {
        "image_size": 400,
        "niter": 2000,
        "a": 500.0,
        "use_expression": False,
    },
}


def _prefixed_params(prefix: str, **values) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        result[f"{prefix}_{key}"] = value
    return result


def detect_slice_key(adata) -> str | None:
    """Auto-detect the obs column that identifies slices."""
    for key in _SLICE_KEY_CANDIDATES:
        if key in adata.obs.columns and adata.obs[key].nunique() >= 2:
            return key
    return None


def _find_common_genes(adata_list: list) -> list[str]:
    """Return sorted intersection of gene names across AnnData objects."""
    if not adata_list:
        return []
    common = set(adata_list[0].var_names)
    for ad in adata_list[1:]:
        common &= set(ad.var_names)
    return sorted(common)


def _prepare_paste_slice(adata_slice, common_genes: list[str], spatial_key: str):
    """Prepare a single slice for PASTE: subset to common genes, normalize.

    PASTE computes an optimal-transport cost that combines **expression
    dissimilarity** and **spatial distance**.  The official tutorial
    (paste-bio.readthedocs.io) normalises each slice with
    ``normalize_total`` + ``log1p`` before calling ``pairwise_align`` so
    that expression scales are comparable across slices.

    Additionally, PASTE internally accesses ``adata.obsm["spatial"]``, so
    if the actual spatial key differs we copy it there.
    """
    import scanpy as sc

    s = adata_slice[:, common_genes].copy()
    # Guarantee PASTE finds obsm["spatial"]
    if spatial_key != "spatial":
        s.obsm["spatial"] = s.obsm[spatial_key]
    sc.pp.normalize_total(s, target_sum=1e4)
    sc.pp.log1p(s)
    return s


def run_paste(
    adata,
    *,
    slice_key: str,
    reference_slice: str | None,
    spatial_key: str,
    alpha: float = METHOD_PARAM_DEFAULTS["paste"]["alpha"],
    dissimilarity: str = METHOD_PARAM_DEFAULTS["paste"]["dissimilarity"],
    use_gpu: bool = METHOD_PARAM_DEFAULTS["paste"]["use_gpu"],
) -> dict:
    """Run PASTE optimal transport alignment.

    PASTE requires **expression matrix + spatial coordinates** for each
    slice.  The transport plan is computed from a cost that combines gene-
    expression dissimilarity and spatial distance, so both inputs are
    essential.  Per the official tutorial, slices are first subset to
    common genes and normalised (``normalize_total`` + ``log1p``) before
    alignment.
    """
    require("paste", feature="PASTE optimal transport spatial registration")
    if use_gpu:
        require("torch", feature="PASTE GPU backend")
    import paste as pst
    import ot.backend as ot_backend

    slices_list = sorted(adata.obs[slice_key].unique().tolist(), key=str)
    ref = reference_slice or slices_list[0]

    # --- Prepare per-slice AnnData objects --------------------------------
    raw_slices = {
        str(sl): adata[adata.obs[slice_key] == sl].copy()
        for sl in slices_list
    }
    common_genes = _find_common_genes(list(raw_slices.values()))
    n_common = len(common_genes)
    if n_common == 0:
        raise ValueError(
            "No common genes found across slices. PASTE requires a shared "
            "gene space; check that all slices use the same gene naming."
        )
    logger.info(
        "PASTE: using expression matrix (%d common genes) + spatial "
        "coordinates for optimal-transport alignment", n_common,
    )

    # Normalize + subset each slice (following paste-bio tutorial)
    prepared = {
        sl: _prepare_paste_slice(ad, common_genes, spatial_key)
        for sl, ad in raw_slices.items()
    }

    ref_prepared = prepared[str(ref)]
    ref_coords = raw_slices[str(ref)].obsm[spatial_key].astype(float)

    aligned_coords = adata.obsm[spatial_key].copy().astype(float)
    disparities: dict[str, float] = {}

    for sl in slices_list:
        if str(sl) == str(ref):
            continue
        sl_prepared = prepared[str(sl)]
        try:
            backend = ot_backend.TorchBackend() if use_gpu else ot_backend.NumpyBackend()
            result = pst.pairwise_align(
                ref_prepared,
                sl_prepared,
                alpha=alpha,
                dissimilarity=dissimilarity,
                backend=backend,
                use_gpu=use_gpu,
            )
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
        "n_common_genes": n_common,
        "disparities": disparities, "mean_disparity": mean_disp,
        "effective_params": _prefixed_params(
            "paste",
            alpha=alpha,
            dissimilarity=dissimilarity,
            use_gpu=use_gpu,
        ),
    }


# ---------------------------------------------------------------------------
# STalign helpers
# ---------------------------------------------------------------------------


def _prepare_stalign_image(
    coords: np.ndarray,
    intensity: np.ndarray,
    image_size: tuple[int, int],
    padding: float = 0.1,
) -> tuple:
    """Convert a point cloud to a rasterized image for STalign.

    Each point is placed on a regular grid and smoothed with a Gaussian
    kernel so that STalign's LDDMM can compute image gradients.

    Parameters
    ----------
    coords : ndarray, shape (N, 2)
        Spatial (x, y) coordinates of spots/cells.
    intensity : ndarray, shape (N,)
        Per-point intensity (e.g. total expression or ones).
    image_size : tuple[int, int]
        (height, width) of the output raster.
    padding : float
        Fractional margin around the point cloud (default 0.1).

    Returns
    -------
    xgrid : list[Tensor]
        Grid axis tensors expected by ``STalign.LDDMM``.
    image : Tensor
        2-D float32 image tensor.
    """
    import torch
    from scipy.ndimage import gaussian_filter

    coords = np.asarray(coords, dtype=np.float32)
    intensity = np.asarray(intensity, dtype=np.float32)

    def _to_indices(values: np.ndarray, size: int) -> np.ndarray:
        vmin, vmax = values.min(), values.max()
        vrange = vmax - vmin
        if vrange > 0:
            lo = padding * size
            hi = (1 - padding) * size
            values = ((values - vmin) / vrange) * (hi - lo) + lo
        return np.clip(values.astype(np.int32), 0, size - 1)

    xgrid = [
        torch.linspace(0, image_size[0], image_size[0], dtype=torch.float32),
        torch.linspace(0, image_size[1], image_size[1], dtype=torch.float32),
    ]

    x_idx = _to_indices(coords[:, 1], image_size[0])
    y_idx = _to_indices(coords[:, 0], image_size[1])

    image = np.zeros(image_size, dtype=np.float32)
    np.add.at(image, (x_idx, y_idx), intensity)
    image = gaussian_filter(image, sigma=1.0)

    if image.max() > 0:
        image /= image.max()

    return xgrid, torch.tensor(image, dtype=torch.float32)


def _compute_stalign_signal(
    ref_adata, src_adata, common_genes: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Compute per-spot expression signal for STalign rasterization.

    STalign's official API accepts coordinates + a **signal matrix**
    (gene expression or general feature matrix) which it rasterizes into
    images.  For the LDDMM image-based path we reduce the signal to a
    single intensity per spot using PCA-PC1, which preserves the dominant
    axis of transcriptomic variation and produces a far more informative
    image than a naive total-count sum.

    Falls back to total-count sum if PCA fails (e.g. too few genes).
    """
    import scipy.sparse as sp

    def _to_dense(X):
        return np.asarray(X.toarray() if sp.issparse(X) else X, dtype=np.float32)

    ref_X = _to_dense(ref_adata[:, common_genes].X)
    src_X = _to_dense(src_adata[:, common_genes].X)

    try:
        from sklearn.decomposition import PCA
        # Fit PCA on the reference, transform both
        pca = PCA(n_components=1, random_state=42)
        ref_pc1 = pca.fit_transform(ref_X).flatten()
        src_pc1 = pca.transform(src_X).flatten()
        # Shift to non-negative (image intensities must be >= 0)
        global_min = min(ref_pc1.min(), src_pc1.min())
        ref_signal = (ref_pc1 - global_min).astype(np.float32)
        src_signal = (src_pc1 - global_min).astype(np.float32)
        logger.info(
            "STalign signal: PC1 from %d common genes "
            "(explains %.1f%% variance)",
            len(common_genes), pca.explained_variance_ratio_[0] * 100,
        )
    except Exception as exc:
        logger.warning("PCA failed (%s), falling back to total-count signal", exc)
        ref_signal = ref_X.sum(axis=1).astype(np.float32)
        src_signal = src_X.sum(axis=1).astype(np.float32)

    return ref_signal, src_signal


def run_stalign(
    adata,
    *,
    slice_key: str,
    reference_slice: str | None,
    spatial_key: str,
    image_size: tuple[int, int] = (
        METHOD_PARAM_DEFAULTS["stalign"]["image_size"],
        METHOD_PARAM_DEFAULTS["stalign"]["image_size"],
    ),
    niter: int = METHOD_PARAM_DEFAULTS["stalign"]["niter"],
    a: float = METHOD_PARAM_DEFAULTS["stalign"]["a"],
    use_expression: bool = METHOD_PARAM_DEFAULTS["stalign"]["use_expression"],
) -> dict:
    """Run STalign diffeomorphic registration (pairwise only).

    STalign performs **LDDMM** (Large Deformation Diffeomorphic Metric
    Mapping) between two tissue slices.  The method requires
    **coordinates + a signal/expression matrix** for each slice.  The
    signal is rasterized into a 2-D image, and LDDMM computes a smooth
    deformation field to warp the source image onto the target.  The
    learned diffeomorphism is then applied to the source coordinates.

    When ``use_expression=True``, the signal is derived from the first
    principal component (PC1) of the shared gene expression matrix,
    which preserves the dominant transcriptomic variation and produces
    a more informative raster than a simple total-count sum.

    Parameters
    ----------
    adata : AnnData
        Combined multi-slice data with ``obs[slice_key]`` identifying slices.
    slice_key : str
        Column in ``adata.obs`` labelling slices.
    reference_slice : str or None
        Label of the target (fixed) slice.  If *None*, the first slice is used.
    spatial_key : str
        Key in ``adata.obsm`` holding 2-D coordinates.
    image_size : tuple[int, int]
        Raster resolution for LDDMM (default 400x400).
    niter : int
        Number of LDDMM iterations (default 2000).
    a : float
        LDDMM kernel bandwidth — controls deformation smoothness.
        Larger values produce smoother warps (default 500).
    use_expression : bool
        If *True*, expression-derived signal (PC1 of common genes) is used
        as intensity for image rasterization.  If *False*, uniform weights.

    Returns
    -------
    dict
        Summary with method, slices, and alignment status.
    """
    require("STalign", feature="STalign diffeomorphic spatial registration")
    require("torch", feature="STalign (PyTorch backend)")

    import STalign.STalign as ST
    import torch

    slices_list = sorted(adata.obs[slice_key].unique().tolist(), key=str)
    if len(slices_list) != 2:
        raise ValueError(
            f"STalign only supports pairwise registration (2 slices), "
            f"but found {len(slices_list)} slices in '{slice_key}'. "
            f"Use --method paste for multi-slice alignment."
        )

    ref = reference_slice or slices_list[0]
    other = [s for s in slices_list if str(s) != str(ref)][0]

    logger.info(
        "STalign: pairwise registration '%s' -> '%s' "
        "(image_size=%s, niter=%d, a=%.1f, use_expression=%s)",
        other, ref, image_size, niter, a, use_expression,
    )

    ref_adata = adata[adata.obs[slice_key] == ref].copy()
    src_adata = adata[adata.obs[slice_key] == other].copy()

    ref_coords = np.asarray(ref_adata.obsm[spatial_key], dtype=np.float32)
    src_coords = np.asarray(src_adata.obsm[spatial_key], dtype=np.float32)

    # --- Signal: expression-based (PC1) or uniform ------------------------
    n_common_genes = 0
    if use_expression:
        common_genes = _find_common_genes([ref_adata, src_adata])
        n_common_genes = len(common_genes)
        if n_common_genes < 10:
            logger.warning(
                "Only %d common genes — falling back to uniform signal",
                n_common_genes,
            )
            ref_intensity = np.ones(len(ref_coords), dtype=np.float32)
            src_intensity = np.ones(len(src_coords), dtype=np.float32)
        else:
            ref_intensity, src_intensity = _compute_stalign_signal(
                ref_adata, src_adata, common_genes,
            )
    else:
        ref_intensity = np.ones(len(ref_coords), dtype=np.float32)
        src_intensity = np.ones(len(src_coords), dtype=np.float32)

    # --- Rasterize to images for LDDMM -----------------------------------
    ref_grid, ref_image = _prepare_stalign_image(ref_coords, ref_intensity, image_size)
    src_grid, src_image = _prepare_stalign_image(src_coords, src_intensity, image_size)

    # --- STalign LDDMM ---------------------------------------------------
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("STalign device: %s", device)

    stalign_params = {
        "a": a,
        "p": 2.0,
        "expand": 2.0,
        "nt": 3,
        "niter": niter,
        "diffeo_start": 0,
        "epL": 2e-08,
        "epT": 0.2,
        "epV": 2000.0,
        "sigmaM": 1.0,
        "sigmaB": 2.0,
        "sigmaA": 5.0,
        "sigmaR": 500000.0,
        "sigmaP": 20.0,
        "device": device,
        "dtype": torch.float32,
    }

    try:
        result = ST.LDDMM(
            xI=src_grid, I=src_image,
            xJ=ref_grid, J=ref_image,
            **stalign_params,
        )

        A = result.get("A")
        v = result.get("v")
        xv = result.get("xv")

        if A is None or v is None or xv is None:
            raise RuntimeError("STalign LDDMM did not return valid transformation (A, v, xv)")

        # Transform source coordinates to target space
        src_points = torch.tensor(src_coords, dtype=torch.float32)
        transformed = ST.transform_points_source_to_target(xv, v, A, src_points)

        # Safely convert to numpy
        if isinstance(transformed, torch.Tensor):
            transformed = transformed.detach().cpu().numpy()
        transformed = np.asarray(transformed, dtype=np.float32)

    except Exception as exc:
        raise RuntimeError(
            f"STalign registration failed: {exc}. "
            f"Consider using --method paste instead."
        ) from exc

    # --- Store aligned coordinates ----------------------------------------
    aligned_coords = adata.obsm[spatial_key].copy().astype(float)
    src_mask = adata.obs[slice_key] == other
    aligned_coords[src_mask] = transformed
    adata.obsm["spatial_aligned"] = aligned_coords

    logger.info("STalign registration complete: '%s' warped onto '%s'", other, ref)

    return {
        "method": "stalign",
        "reference_slice": str(ref),
        "n_slices": 2,
        "slices": [str(s) for s in slices_list],
        "disparities": {},
        "mean_disparity": 0.0,
        "n_common_genes": n_common_genes if use_expression else 0,
        "stalign_params": {
            "image_size": list(image_size),
            "niter": niter,
            "a": a,
            "use_expression": use_expression,
            "signal_type": "PC1" if use_expression and n_common_genes >= 10 else "uniform",
            "device": str(device),
        },
        "effective_params": _prefixed_params(
            "stalign",
            image_size=image_size[0] if image_size[0] == image_size[1] else list(image_size),
            niter=niter,
            a=a,
            use_expression=use_expression,
        ),
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def run_registration(
    adata, *, method: str = "paste",
    slice_key: str | None = None, reference_slice: str | None = None,
    **kwargs,
) -> dict:
    """Run spatial registration. Returns summary dict.

    Parameters
    ----------
    method : str
        ``"paste"`` (multi-slice OT) or ``"stalign"`` (pairwise LDDMM).
    slice_key : str or None
        Column in ``adata.obs`` labelling slices.  Auto-detected if None.
    reference_slice : str or None
        Label of the reference (fixed) slice.
    **kwargs
        Extra parameters forwarded to the chosen method function
        (e.g. ``image_size``, ``niter``, ``a``, ``use_expression`` for STalign).
    """
    spatial_key = require_spatial_coords(adata)

    if slice_key is None:
        slice_key = detect_slice_key(adata)
    if slice_key is None:
        raise ValueError(
            "Could not detect a slice label column automatically. "
            "Provide --slice-key or add one of the common columns: "
            f"{', '.join(_SLICE_KEY_CANDIDATES)}."
        )

    if slice_key not in adata.obs.columns:
        raise ValueError(f"Slice key '{slice_key}' not in adata.obs")

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    slices = sorted(adata.obs[slice_key].unique().tolist(), key=str)
    logger.info("Input: %d cells x %d genes, %d slices", n_cells, n_genes, len(slices))

    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown registration method '{method}'. Choose from: {SUPPORTED_METHODS}")

    if method == "paste":
        paste_keys = {"alpha", "dissimilarity", "use_gpu"}
        paste_kwargs = {k: v for k, v in kwargs.items() if k in paste_keys}
        result = run_paste(
            adata, slice_key=slice_key,
            reference_slice=reference_slice, spatial_key=spatial_key,
            **paste_kwargs,
        )
    elif method == "stalign":
        # Filter kwargs to STalign-specific parameters
        stalign_keys = {"image_size", "niter", "a", "use_expression"}
        stalign_kwargs = {k: v for k, v in kwargs.items() if k in stalign_keys}
        result = run_stalign(
            adata, slice_key=slice_key,
            reference_slice=reference_slice, spatial_key=spatial_key,
            **stalign_kwargs,
        )

    return {
        "n_cells": n_cells,
        "n_genes": n_genes,
        "slice_key": slice_key,
        **result,
    }
