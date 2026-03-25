"""AnnData utilities for single-cell analysis."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import scanpy as sc

if TYPE_CHECKING:
    from anndata import AnnData

from .exceptions import PreprocessingRequiredError

logger = logging.getLogger(__name__)


def require_preprocessed(adata: AnnData) -> None:
    """Require PCA to be computed."""
    if "X_pca" not in adata.obsm:
        raise PreprocessingRequiredError(
            "PCA not found. Run sc-preprocess first:\n"
            "  python omicsclaw.py run sc-preprocess --input data.h5ad --output results/"
        )


def ensure_pca(adata: AnnData, n_comps: int = 50) -> None:
    """Compute PCA if missing."""
    if "X_pca" not in adata.obsm:
        logger.info("Computing PCA (%d components)", n_comps)
        sc.tl.pca(adata, n_comps=min(n_comps, adata.n_vars - 1))


def ensure_neighbors(adata: AnnData, n_neighbors: int = 15, n_pcs: int = 50) -> None:
    """Compute neighbors if missing."""
    if "neighbors" not in adata.uns:
        ensure_pca(adata, n_comps=n_pcs)
        logger.info("Computing neighbors (n=%d, pcs=%d)", n_neighbors, n_pcs)
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=min(n_pcs, adata.obsm["X_pca"].shape[1]))


def store_analysis_metadata(adata: AnnData, skill_name: str, method: str, params: dict) -> None:
    """Store analysis metadata in adata.uns."""
    if "omicsclaw_analyses" not in adata.uns:
        adata.uns["omicsclaw_analyses"] = []
    adata.uns["omicsclaw_analyses"].append({
        "skill": skill_name,
        "method": method,
        "params": params,
    })
