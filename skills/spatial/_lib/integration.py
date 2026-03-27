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

- **Scanorama**: Operates on **preprocessed expression** (via scanpy wrapper
  using PCA basis by default).  The original Scanorama method stitches
  expression matrices via mutual nearest neighbors; the scanpy wrapper
  ``sc.external.pp.scanorama_integrate`` applies this to the PCA basis
  for efficiency.
  Ref: Hie et al., *Nature Biotechnology* 2019.

All three methods require upstream preprocessing: ``normalize_total`` →
``log1p`` → HVG selection → PCA.  The batch labels must be present in
``adata.obs[batch_key]``.

Usage::

    from skills.spatial._lib.integration import run_integration, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import scanpy as sc

from .adata_utils import ensure_neighbors, ensure_pca
from .dependency_manager import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("harmony", "bbknn", "scanorama")


def integrate_harmony(adata, batch_key: str) -> dict:
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
        "batch_key='%s'",
        adata.obsm["X_pca"].shape[1], batch_key,
    )
    ho = harmonypy.run_harmony(adata.obsm["X_pca"], adata.obs, batch_key, max_iter_harmony=20)
    corrected = ho.Z_corr
    if corrected.shape[0] != adata.n_obs and corrected.shape[1] == adata.n_obs:
        corrected = corrected.T
    adata.obsm["X_pca_harmony"] = corrected
    sc.pp.neighbors(adata, use_rep="X_pca_harmony", n_neighbors=15)
    sc.tl.umap(adata)
    return {"method": "harmony", "embedding_key": "X_pca_harmony"}


def integrate_bbknn(adata, batch_key: str) -> dict:
    """Run BBKNN batch-balanced nearest neighbours.

    BBKNN replaces the standard k-NN graph with a batch-balanced version
    built from **PCA embeddings** (``adata.obsm["X_pca"]``).  It modifies
    the neighbor graph in-place, then UMAP is recomputed on the corrected
    graph.
    """
    require("bbknn", feature="BBKNN batch integration")
    import bbknn

    ensure_pca(adata)
    logger.info(
        "BBKNN: constructing batch-balanced neighbor graph from PCA "
        "embeddings (X_pca, %d components), batch_key='%s'",
        adata.obsm["X_pca"].shape[1], batch_key,
    )
    bbknn.bbknn(adata, batch_key=batch_key)
    sc.tl.umap(adata)
    return {"method": "bbknn", "embedding_key": "X_pca"}


def integrate_scanorama(adata, batch_key: str) -> dict:
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
    logger.info(
        "Scanorama: integrating via scanpy wrapper on PCA basis "
        "(X_pca, %d components), batch_key='%s'. "
        "Note: original Scanorama works on expression matrices; "
        "scanpy wrapper uses PCA basis for efficiency.",
        adata.obsm["X_pca"].shape[1], batch_key,
    )
    sc.external.pp.scanorama_integrate(
        adata, key=batch_key, basis="X_pca", adjusted_basis="X_scanorama",
    )
    sc.pp.neighbors(adata, use_rep="X_scanorama")
    sc.tl.umap(adata)
    return {"method": "scanorama", "embedding_key": "X_scanorama"}


def compute_batch_mixing(adata, batch_key: str) -> float:
    """Compute batch mixing entropy from the spatial/neighbor connectivities graph.
    
    A higher entropy value relative to the number of batches indicates
    better physiological or technical mixing.
    """
    try:
        from scipy import sparse
        if "connectivities" not in adata.obsp:
            return 0.0

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
            return 0.0

        entropies = []
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
            entropies.append(entropy)

        max_entropy = np.log(n_batches)
        return float(np.mean(entropies) / max_entropy) if entropies else 0.0
    except Exception as e:
        logger.warning(f"Failed to compute batch mixing metric: {e}")
        return 0.0


def run_integration(adata, *, method: str = "harmony", batch_key: str = "batch") -> dict:
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
    mixing_before = compute_batch_mixing(adata, batch_key)

    if method == "harmony":
        result = integrate_harmony(adata, batch_key)
    elif method == "bbknn":
        result = integrate_bbknn(adata, batch_key)
    elif method == "scanorama":
        result = integrate_scanorama(adata, batch_key)
        
    # Prevent clustering collision overrides with existing labels
    if "leiden" not in adata.obs.columns:
        sc.tl.leiden(adata, resolution=1.0, flavor="igraph")

    mixing_after = compute_batch_mixing(adata, batch_key)
    adata.obsm["X_umap_before_integration"] = umap_before

    return {
        "n_cells": adata.n_obs, "n_genes": adata.n_vars,
        "n_batches": n_batches, "batches": batches, "batch_sizes": batch_sizes,
        "method": result["method"], "embedding_key": result["embedding_key"],
        "batch_mixing_before": round(mixing_before, 4),
        "batch_mixing_after": round(mixing_after, 4),
    }
