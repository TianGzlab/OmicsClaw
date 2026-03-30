"""Spatial batch integration functions.

Provides three integration methods, each consuming a different data
representation from the preprocessed AnnData:

- **Harmony**: Operates on **PCA embeddings** (``adata.obsm["X_pca"]``).
  Iteratively adjusts principal components to remove batch effects.
  Ref: Korsunsky et al., *Nature Methods* 2019.

- **BBKNN**: Operates on **PCA embeddings** (``adata.obsm["X_pca"]``).
  Constructs a batch-balanced k-nearest-neighbor graph, replacing
  the standard neighbors graph.
  Ref: Polanski et al., *Bioinformatics* 2020.

- **Scanorama**: Uses Scanpy's wrapper around Scanorama on the PCA basis
  by default. The original Scanorama method stitches expression matrices
  via mutual nearest neighbours; ``sc.external.pp.scanorama_integrate``
  exposes core matching and smoothing controls on top of ``X_pca``.
  Ref: Hie et al., *Nature Biotechnology* 2019.

All three methods require upstream preprocessing: ``normalize_total`` →
``log1p`` → HVG selection → PCA. The batch labels must be present in
``adata.obs[batch_key]``.

Usage::

    from skills.spatial._lib.integration import (
        METHOD_PARAM_DEFAULTS,
        SUPPORTED_METHODS,
        run_integration,
    )
"""

from __future__ import annotations

import logging

import numpy as np

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs

ensure_runtime_cache_dirs()

import scanpy as sc

from .adata_utils import ensure_neighbors, ensure_pca
from .dependency_manager import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("harmony", "bbknn", "scanorama")

METHOD_PARAM_DEFAULTS = {
    "harmony": {
        "theta": 2.0,
        "lambda": 1.0,
        "max_iter_harmony": 10,
    },
    "bbknn": {
        "neighbors_within_batch": 3,
        "n_pcs": 50,
        "trim": None,
    },
    "scanorama": {
        "knn": 20,
        "sigma": 15.0,
        "alpha": 0.1,
        "batch_size": 5000,
    },
}


def _resolve_bbknn_n_pcs(adata, requested_n_pcs: int) -> int:
    """Clamp BBKNN n_pcs to the available PCA dimensionality."""
    n_available = int(adata.obsm["X_pca"].shape[1])
    if requested_n_pcs > n_available:
        logger.warning(
            "Requested BBKNN n_pcs=%d but only %d PCs are available in X_pca; "
            "using %d instead.",
            requested_n_pcs,
            n_available,
            n_available,
        )
        return n_available
    return requested_n_pcs


def _get_scanorama_batch_order(adata, batch_key: str) -> np.ndarray | None:
    """Return a stable sort order that makes batches contiguous if needed.

    Scanpy's Scanorama wrapper expects cells from the same batch to be stored
    contiguously in ``adata``. When the current ordering interleaves batches,
    OmicsClaw sorts a temporary copy by ``batch_key`` before integration and
    then restores the corrected embedding back to the original order.
    """
    batch_labels = np.asarray(adata.obs[batch_key].astype(str))
    if batch_labels.size <= 1:
        return None

    seen = {batch_labels[0]}
    prev = batch_labels[0]
    for label in batch_labels[1:]:
        if label == prev:
            continue
        if label in seen:
            return np.argsort(batch_labels, kind="stable")
        seen.add(label)
        prev = label
    return None


def integrate_harmony(
    adata,
    batch_key: str,
    *,
    theta: float = METHOD_PARAM_DEFAULTS["harmony"]["theta"],
    lamb: float = METHOD_PARAM_DEFAULTS["harmony"]["lambda"],
    max_iter_harmony: int = METHOD_PARAM_DEFAULTS["harmony"]["max_iter_harmony"],
) -> dict:
    """Run Harmony integration on PCA embeddings.

    Harmony adjusts **PCA embeddings** (``adata.obsm["X_pca"]``) to remove
    batch effects while preserving biological variation.  The upstream data
    must already be log-normalized with PCA computed.
    """
    require("harmonypy", feature="Harmony batch integration")
    import harmonypy

    ensure_pca(adata)
    logger.info(
        "Harmony: integrating on PCA embeddings (X_pca, %d components), "
        "batch_key='%s', theta=%s, lambda=%s, max_iter_harmony=%d",
        adata.obsm["X_pca"].shape[1], batch_key,
        theta, lamb, max_iter_harmony,
    )
    ho = harmonypy.run_harmony(
        adata.obsm["X_pca"],
        adata.obs,
        batch_key,
        theta=theta,
        lamb=lamb,
        max_iter_harmony=max_iter_harmony,
    )
    corrected = ho.Z_corr
    if corrected.shape[0] != adata.n_obs and corrected.shape[1] == adata.n_obs:
        corrected = corrected.T
    adata.obsm["X_pca_harmony"] = corrected
    sc.pp.neighbors(adata, use_rep="X_pca_harmony", n_neighbors=15)
    sc.tl.umap(adata)
    return {
        "method": "harmony",
        "embedding_key": "X_pca_harmony",
        "representation_type": "embedding",
        "effective_params": {
            "harmony_theta": theta,
            "harmony_lambda": lamb,
            "harmony_max_iter": max_iter_harmony,
        },
    }


def integrate_bbknn(
    adata,
    batch_key: str,
    *,
    neighbors_within_batch: int = METHOD_PARAM_DEFAULTS["bbknn"]["neighbors_within_batch"],
    n_pcs: int = METHOD_PARAM_DEFAULTS["bbknn"]["n_pcs"],
    trim: int | None = METHOD_PARAM_DEFAULTS["bbknn"]["trim"],
) -> dict:
    """Run BBKNN batch-balanced nearest neighbours.

    BBKNN replaces the standard k-NN graph with a batch-balanced version
    built from **PCA embeddings** (``adata.obsm["X_pca"]``).  It modifies
    the neighbor graph in-place, then UMAP is recomputed on the corrected
    graph.
    """
    require("bbknn", feature="BBKNN batch integration")
    import bbknn

    ensure_pca(adata)
    effective_n_pcs = _resolve_bbknn_n_pcs(adata, n_pcs)
    logger.info(
        "BBKNN: constructing batch-balanced neighbor graph from PCA "
        "embeddings (X_pca, %d components), batch_key='%s', "
        "neighbors_within_batch=%d, n_pcs=%d, trim=%s",
        adata.obsm["X_pca"].shape[1], batch_key,
        neighbors_within_batch, effective_n_pcs, trim,
    )
    bbknn.bbknn(
        adata,
        batch_key=batch_key,
        neighbors_within_batch=neighbors_within_batch,
        n_pcs=effective_n_pcs,
        trim=trim,
    )
    sc.tl.umap(adata)
    return {
        "method": "bbknn",
        "embedding_key": "X_pca",
        "representation_type": "neighbor_graph",
        "effective_params": {
            "bbknn_neighbors_within_batch": neighbors_within_batch,
            "bbknn_n_pcs": effective_n_pcs,
            "bbknn_trim": trim,
        },
    }


def integrate_scanorama(
    adata,
    batch_key: str,
    *,
    knn: int = METHOD_PARAM_DEFAULTS["scanorama"]["knn"],
    sigma: float = METHOD_PARAM_DEFAULTS["scanorama"]["sigma"],
    alpha: float = METHOD_PARAM_DEFAULTS["scanorama"]["alpha"],
    batch_size: int = METHOD_PARAM_DEFAULTS["scanorama"]["batch_size"],
) -> dict:
    """Run Scanorama integration via Scanpy's external API.

    The original Scanorama algorithm stitches **preprocessed expression
    matrices** via mutual nearest neighbors (Hie et al., 2019).  The
    scanpy wrapper ``sc.external.pp.scanorama_integrate`` applies this
    to the PCA basis for computational efficiency, producing a corrected
    embedding in ``X_scanorama``.

    For expression-level integration (closer to the original paper), users
    can call ``scanorama.integrate()`` directly on per-batch HVG matrices.
    """
    require("scanorama", feature="Scanorama batch integration")
    ensure_pca(adata)
    reorder = _get_scanorama_batch_order(adata, batch_key)
    adata_work = adata
    if reorder is not None:
        logger.info(
            "Scanorama requires batches to be stored contiguously; "
            "temporarily sorting cells by '%s' before integration.",
            batch_key,
        )
        adata_work = adata[reorder].copy()
    logger.info(
        "Scanorama: integrating via scanpy wrapper on PCA basis "
        "(X_pca, %d components), batch_key='%s', knn=%d, sigma=%s, alpha=%s, batch_size=%d. "
        "Note: original Scanorama works on expression matrices; "
        "scanpy wrapper uses PCA basis for efficiency.",
        adata.obsm["X_pca"].shape[1], batch_key,
        knn, sigma, alpha, batch_size,
    )
    sc.external.pp.scanorama_integrate(
        adata_work,
        key=batch_key,
        basis="X_pca",
        adjusted_basis="X_scanorama",
        knn=knn,
        sigma=sigma,
        alpha=alpha,
        batch_size=batch_size,
    )
    corrected = adata_work.obsm["X_scanorama"]
    if reorder is not None:
        restored = np.empty_like(corrected)
        restored[reorder] = corrected
        adata.obsm["X_scanorama"] = restored
    else:
        adata.obsm["X_scanorama"] = corrected
    sc.pp.neighbors(adata, use_rep="X_scanorama")
    sc.tl.umap(adata)
    return {
        "method": "scanorama",
        "embedding_key": "X_scanorama",
        "representation_type": "embedding",
        "effective_params": {
            "scanorama_knn": knn,
            "scanorama_sigma": sigma,
            "scanorama_alpha": alpha,
            "scanorama_batch_size": batch_size,
        },
    }


def compute_batch_mixing(adata, batch_key: str) -> float:
    """Compute mean batch-mixing entropy from the connectivities graph."""
    profile = compute_batch_mixing_profile(adata, batch_key)
    return float(profile.mean()) if profile.size else 0.0


def compute_batch_mixing_profile(adata, batch_key: str) -> np.ndarray:
    """Return per-cell normalized batch-mixing entropy from the connectivities graph.

    Higher values indicate stronger local mixing across batches. The returned
    vector is scaled to ``[0, 1]`` by dividing by the maximum entropy implied
    by the number of batches.
    """
    try:
        from scipy import sparse
        if "connectivities" not in adata.obsp:
            return np.zeros(adata.n_obs, dtype=float)

        conn = adata.obsp["connectivities"]
        # CRITICAL: Never run .toarray() on an N x N matrix unless you want a massive RAM explosion.
        # Force Cast to Compressed Sparse Row (CSR) format to safely navigate rows
        if not sparse.issparse(conn):
            conn = sparse.csr_matrix(conn)
        else:
            conn = conn.tocsr()
            
        # Standardize strings to prevent dtype/category mixing errors
        batch_labels = np.asarray(adata.obs[batch_key].astype(str))
        batches = np.unique(batch_labels)
        n_batches = len(batches)
        if n_batches < 2:
            return np.zeros(adata.n_obs, dtype=float)

        entropies = np.zeros(adata.n_obs, dtype=float)
        # Vectorized sparse traversal
        for i in range(adata.n_obs):
            start, end = conn.indptr[i], conn.indptr[i+1]
            if start == end:
                continue
            neighbors_idx = conn.indices[start:end]
            neighbor_batches = batch_labels[neighbors_idx]
            
            # Fast vectorized counting instead of N looping operations
            _, counts = np.unique(neighbor_batches, return_counts=True)
            probs = counts / counts.sum()
            entropy = -np.sum(probs * np.log(probs))
            entropies[i] = float(entropy)

        max_entropy = np.log(n_batches)
        return entropies / max_entropy if max_entropy > 0 else np.zeros(adata.n_obs, dtype=float)
    except Exception as e:
        logger.warning(f"Failed to compute batch mixing metric: {e}")
        return np.zeros(adata.n_obs, dtype=float)


def run_integration(
    adata,
    *,
    method: str = "harmony",
    batch_key: str = "batch",
    **method_kwargs,
) -> dict:
    """Run multi-sample integration. Returns summary dict."""
    if batch_key not in adata.obs.columns:
        raise ValueError(f"Batch key '{batch_key}' not in adata.obs. Available: {list(adata.obs.columns)}")

    batches = sorted(adata.obs[batch_key].unique().tolist(), key=str)
    n_batches = len(batches)
    batch_sizes = {str(b): int((adata.obs[batch_key] == b).sum()) for b in batches}

    logger.info("Input: %d cells x %d genes, %d batches", adata.n_obs, adata.n_vars, n_batches)

    if n_batches < 2:
        raise ValueError(
            f"Only 1 batch found in '{batch_key}'. "
            "Multi-sample integration requires at least 2 batches."
        )
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown integration method '{method}'. Choose from: {SUPPORTED_METHODS}")

    if "X_pca" not in adata.obsm:
        raise ValueError(
            "X_pca not found. Run spatial-preprocess before integration:\n"
            "  oc run spatial-preprocess --input data.h5ad --output results/"
        )
    if "X_umap" not in adata.obsm:
        ensure_neighbors(adata)
        sc.tl.umap(adata)
        
    umap_before = adata.obsm["X_umap"].copy()
    mixing_profile_before = compute_batch_mixing_profile(adata, batch_key)
    mixing_before = float(mixing_profile_before.mean()) if mixing_profile_before.size else 0.0

    if method == "harmony":
        result = integrate_harmony(adata, batch_key, **method_kwargs)
    elif method == "bbknn":
        result = integrate_bbknn(adata, batch_key, **method_kwargs)
    elif method == "scanorama":
        result = integrate_scanorama(adata, batch_key, **method_kwargs)

    # Prevent clustering collision overrides with existing labels
    if "leiden" not in adata.obs.columns:
        sc.tl.leiden(adata, resolution=1.0, flavor="igraph")

    mixing_profile_after = compute_batch_mixing_profile(adata, batch_key)
    mixing_after = float(mixing_profile_after.mean()) if mixing_profile_after.size else 0.0
    adata.obsm["X_umap_before_integration"] = umap_before
    adata.obsm["X_umap_after_integration"] = adata.obsm["X_umap"].copy()
    adata.obs["batch_entropy_before"] = mixing_profile_before
    adata.obs["batch_entropy_after"] = mixing_profile_after
    adata.obs["batch_entropy_delta"] = mixing_profile_after - mixing_profile_before

    summary = {
        "n_cells": adata.n_obs, "n_genes": adata.n_vars,
        "n_batches": n_batches, "batches": batches, "batch_sizes": batch_sizes,
        "method": result["method"], "embedding_key": result["embedding_key"],
        "representation_type": result.get("representation_type", "embedding"),
        "batch_mixing_before": round(mixing_before, 4),
        "batch_mixing_after": round(mixing_after, 4),
        "batch_mixing_gain": round(mixing_after - mixing_before, 4),
        "effective_params": result.get("effective_params", {}),
    }
    adata.uns["spatial_integration"] = summary.copy()
    return summary
