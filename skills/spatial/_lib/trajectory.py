"""Spatial trajectory analysis functions.

Trajectory inference using DPT and CellRank.

Usage::

    from skills.spatial._lib.trajectory import run_trajectory, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import scanpy as sc

from .adata_utils import ensure_neighbors, ensure_pca

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("dpt", "cellrank", "palantir")


def run_dpt(
    adata, *, root_cell: str | None = None, n_dcs: int = 10,
) -> dict:
    """Run diffusion pseudotime using scanpy."""
    ensure_pca(adata)
    ensure_neighbors(adata)

    n_comps = min(n_dcs, adata.obsm["X_pca"].shape[1], adata.n_obs - 2)
    sc.tl.diffmap(adata, n_comps=max(n_comps, 2))

    if root_cell and root_cell in adata.obs_names:
        adata.uns["iroot"] = list(adata.obs_names).index(root_cell)
        logger.info("Using provided root cell: %s", root_cell)
    else:
        dc1 = adata.obsm["X_diffmap"][:, 0]
        adata.uns["iroot"] = int(np.argmax(dc1))
        root_cell = adata.obs_names[adata.uns["iroot"]]
        logger.info("Auto-selected root cell: %s (max DC1)", root_cell)

    sc.tl.dpt(adata)

    dpt_vals = adata.obs["dpt_pseudotime"].values
    finite_mask = np.isfinite(dpt_vals)

    cluster_key = "leiden" if "leiden" in adata.obs.columns else None
    per_cluster = {}
    if cluster_key:
        for cl in sorted(adata.obs[cluster_key].unique().tolist(), key=str):
            mask = (adata.obs[cluster_key] == cl) & finite_mask
            if np.sum(mask) > 0:
                per_cluster[str(cl)] = {
                    "mean_pseudotime": float(dpt_vals[mask].mean()),
                    "median_pseudotime": float(np.median(dpt_vals[mask])),
                    "n_cells": int(np.sum(mask)),
                }

    return {
        "method": "dpt",
        "root_cell": root_cell,
        "mean_pseudotime": float(dpt_vals[finite_mask].mean()) if np.any(finite_mask) else 0.0,
        "max_pseudotime": float(dpt_vals[finite_mask].max()) if np.any(finite_mask) else 0.0,
        "n_finite": int(np.sum(finite_mask)),
        "per_cluster": per_cluster,
    }


def run_cellrank(adata, *, n_states: int = 3) -> dict:
    """Run CellRank for directed trajectory analysis."""
    from .dependency_manager import require
    require("cellrank", feature="CellRank trajectory inference")
    import cellrank as cr

    kernel = cr.kernels.ConnectivityKernel(adata).compute_transition_matrix()
    estimator = cr.estimators.GPCCA(kernel)
    estimator.compute_schur(n_components=20)
    estimator.compute_macrostates(n_states=n_states)

    macro_key = None
    for candidate in ("macrostates_fwd", "macrostates", "term_states_fwd"):
        if candidate in adata.obs.columns:
            macro_key = candidate
            break

    n_macro = adata.obs[macro_key].nunique() if macro_key else 0

    return {
        "method": "cellrank",
        "n_macrostates": n_macro,
        "root_cell": None,
    }


def run_trajectory(
    adata, *, method: str = "dpt", root_cell: str | None = None, n_states: int = 3,
) -> dict:
    """Dispatch to the selected trajectory method."""
    n_cells = adata.n_obs
    n_genes = adata.n_vars
    logger.info("Input: %d cells x %d genes", n_cells, n_genes)

    if method == "cellrank":
        try:
            result = run_cellrank(adata, n_states=n_states)
        except Exception as exc:
            logger.warning("CellRank failed (%s), falling back to DPT", exc)
            result = run_dpt(adata, root_cell=root_cell)
    else:
        result = run_dpt(adata, root_cell=root_cell)

    return {"n_cells": n_cells, "n_genes": n_genes, **result}
