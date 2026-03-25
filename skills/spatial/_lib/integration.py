"""Spatial batch integration functions.

Harmony, BBKNN, and Scanorama batch integration with mixing metrics.

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
    """Run Harmony integration on PCA embeddings."""
    require("harmonypy", feature="Harmony batch integration")
    import harmonypy

    ensure_pca(adata)
    ho = harmonypy.run_harmony(adata.obsm["X_pca"], adata.obs, batch_key, max_iter_harmony=20)
    corrected = ho.Z_corr
    if corrected.shape[0] != adata.n_obs and corrected.shape[1] == adata.n_obs:
        corrected = corrected.T
    adata.obsm["X_pca_harmony"] = corrected
    sc.pp.neighbors(adata, use_rep="X_pca_harmony", n_neighbors=15)
    sc.tl.umap(adata)
    return {"method": "harmony", "embedding_key": "X_pca_harmony"}


def integrate_bbknn(adata, batch_key: str) -> dict:
    """Run BBKNN batch-balanced nearest neighbours."""
    require("bbknn", feature="BBKNN batch integration")
    import bbknn

    ensure_pca(adata)
    bbknn.bbknn(adata, batch_key=batch_key)
    sc.tl.umap(adata)
    return {"method": "bbknn", "embedding_key": "X_pca"}


def integrate_scanorama(adata, batch_key: str) -> dict:
    """Run Scanorama integration via Scanpy's external API."""
    require("scanorama", feature="Scanorama batch integration")
    ensure_pca(adata)
    sc.external.pp.scanorama_integrate(
        adata, key=batch_key, basis="X_pca", adjusted_basis="X_scanorama",
    )
    sc.pp.neighbors(adata, use_rep="X_scanorama")
    sc.tl.umap(adata)
    return {"method": "scanorama", "embedding_key": "X_scanorama"}


def compute_batch_mixing(adata, batch_key: str) -> float:
    """Compute batch mixing entropy from the neighbor graph."""
    try:
        from scipy import sparse
        if "connectivities" not in adata.obsp:
            return 0.0
        conn = adata.obsp["connectivities"]
        if sparse.issparse(conn):
            conn = conn.toarray()
        batch_labels = adata.obs[batch_key].values
        batches = np.unique(batch_labels)
        n_batches = len(batches)
        if n_batches < 2:
            return 0.0

        entropies = []
        for i in range(adata.n_obs):
            neighbors_idx = np.where(conn[i] > 0)[0]
            if len(neighbors_idx) == 0:
                continue
            neighbor_batches = batch_labels[neighbors_idx]
            counts = np.array([np.sum(neighbor_batches == b) for b in batches])
            probs = counts / counts.sum()
            probs = probs[probs > 0]
            entropy = -np.sum(probs * np.log(probs))
            entropies.append(entropy)

        max_entropy = np.log(n_batches)
        return float(np.mean(entropies) / max_entropy) if entropies else 0.0
    except Exception:
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
            "  python omicsclaw.py run spatial-preprocess --input data.h5ad --output results/"
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

    mixing_after = compute_batch_mixing(adata, batch_key)
    adata.obsm["X_umap_before_integration"] = umap_before

    if "leiden" not in adata.obs.columns:
        sc.tl.leiden(adata, resolution=1.0, flavor="igraph")

    return {
        "n_cells": adata.n_obs, "n_genes": adata.n_vars,
        "n_batches": n_batches, "batches": batches, "batch_sizes": batch_sizes,
        "method": result["method"], "embedding_key": result["embedding_key"],
        "batch_mixing_before": round(mixing_before, 4),
        "batch_mixing_after": round(mixing_after, 4),
    }
