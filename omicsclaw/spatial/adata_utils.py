"""AnnData helper utilities shared across SpatialClaw skills."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import scanpy as sc

from omicsclaw.spatial.exceptions import DataError, PreprocessingRequiredError

logger = logging.getLogger(__name__)


def get_spatial_key(adata) -> str | None:
    """Return the obsm key holding spatial coordinates, or None."""
    for key in ("spatial", "X_spatial"):
        if key in adata.obsm:
            return key
    return None


def require_spatial_coords(adata) -> str:
    """Return the spatial obsm key; raise if not found."""
    key = get_spatial_key(adata)
    if key is None:
        raise DataError(
            "No spatial coordinates found in adata.obsm. "
            "Expected 'spatial' or 'X_spatial'."
        )
    return key


def require_preprocessed(adata) -> None:
    """Raise if the data has not been preprocessed (no PCA)."""
    if "X_pca" not in adata.obsm:
        raise PreprocessingRequiredError(
            "Data has not been preprocessed. Run spatial-preprocess first."
        )


def ensure_pca(adata, *, n_comps: int = 50) -> None:
    """Compute PCA if not already present."""
    if "X_pca" not in adata.obsm:
        logger.info("Computing PCA with %d components", n_comps)
        sc.tl.pca(adata, n_comps=min(n_comps, adata.n_vars - 1))


def ensure_neighbors(adata, *, n_neighbors: int = 15, n_pcs: int = 50) -> None:
    """Compute neighbors graph if not already present."""
    if "neighbors" not in adata.uns:
        ensure_pca(adata, n_comps=n_pcs)
        logger.info("Computing neighbors graph (k=%d)", n_neighbors)
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs)


def store_analysis_metadata(
    adata,
    skill_name: str,
    method: str,
    params: dict[str, Any] | None = None,
) -> None:
    """Store analysis metadata in adata.uns for provenance tracking."""
    key = f"spatialclaw_{skill_name}"
    adata.uns[key] = {
        "method": method,
        "params": params or {},
    }
