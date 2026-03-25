"""Spatial RNA velocity analysis functions.

scVelo (stochastic/deterministic/dynamical) and VELOVI.

Usage::

    from skills.spatial._lib.velocity import run_velocity, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .dependency_manager import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("stochastic", "deterministic", "dynamical", "velovi")


def validate_velocity_layers(adata) -> None:
    """Raise if required spliced/unspliced layers are missing."""
    missing = [k for k in ("spliced", "unspliced") if k not in adata.layers]
    if missing:
        raise ValueError(
            f"Required layers missing: {missing}.\n\n"
            "RNA velocity requires spliced and unspliced count layers.\n"
            "Generate them with velocyto or STARsolo during alignment:\n"
            "  velocyto run -b barcodes.tsv  BAM_FILE  GENOME.gtf\n"
            "  STAR --soloFeatures Gene Velocyto ..."
        )


def add_demo_velocity_layers(adata) -> None:
    """Add synthetic spliced/unspliced layers for demo/test purposes only."""
    from scipy import sparse

    X = adata.X
    if sparse.issparse(X):
        X = X.toarray()
    X = np.asarray(X, dtype=np.float32).clip(0)

    rng = np.random.default_rng(42)
    frac = rng.uniform(0.65, 0.85, size=X.shape)
    spliced = (X * frac).astype(np.float32)
    unspliced = (X * (1.0 - frac) + rng.exponential(0.05, size=X.shape)).astype(np.float32)

    adata.layers["spliced"] = spliced
    adata.layers["unspliced"] = unspliced
    logger.info("Added synthetic spliced/unspliced layers for demo (not biologically valid)")


def preprocess_for_velocity(
    adata, *, min_shared_counts: int = 30, n_top_genes: int = 2000,
    n_pcs: int = 30, n_neighbors: int = 30,
) -> None:
    import scanpy as sc
    scv = require("scvelo", feature="RNA velocity")
    scv.pp.filter_genes(adata, min_shared_counts=min_shared_counts)
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    try:
        sc.pp.highly_variable_genes(adata, n_top_genes=n_top_genes)
    except Exception as e:
        logger.warning(f"Could not compute highly variable genes: {e}")
    scv.pp.moments(adata, n_pcs=n_pcs, n_neighbors=n_neighbors)


def run_scvelo(adata, *, mode: str = "stochastic") -> dict:
    """Run scVelo RNA velocity."""
    scv = require("scvelo", feature="RNA velocity")

    if "Ms" not in adata.layers or "Mu" not in adata.layers:
        preprocess_for_velocity(adata)

    if mode == "dynamical":
        scv.tl.recover_dynamics(adata)
        scv.tl.velocity(adata, mode="dynamical")
        scv.tl.latent_time(adata)
    else:
        scv.tl.velocity(adata, mode=mode)

    scv.tl.velocity_graph(adata)

    speed: pd.Series | None = None
    if "velocity_length" in adata.obs.columns:
        speed = adata.obs["velocity_length"]
    elif "velocity" in adata.layers:
        vel = adata.layers["velocity"]
        if hasattr(vel, "toarray"):
            vel = vel.toarray()
        vals = np.sqrt((np.asarray(vel, dtype=np.float64) ** 2).sum(axis=1))
        adata.obs["velocity_speed"] = vals
        speed = pd.Series(vals, index=adata.obs_names)

    return {
        "method": f"scvelo_{mode}",
        "n_velocity_genes": int(np.sum(adata.var["velocity_genes"]))
        if "velocity_genes" in adata.var.columns else None,
        "mean_speed": float(speed.mean()) if speed is not None else 0.0,
        "median_speed": float(speed.median()) if speed is not None else 0.0,
    }


def run_velovi(adata) -> dict:
    """Run VELOVI — variational inference RNA velocity."""
    require("scvelo", feature="VELOVI preprocessing")
    require("scvi-tools", feature="VELOVI (VeloVI)")

    import scvelo as scv
    from scvi.external import VELOVI

    if "spliced" not in adata.layers or "unspliced" not in adata.layers:
        raise ValueError("VELOVI requires 'spliced' and 'unspliced' layers.")

    scv.pp.filter_and_normalize(adata, min_shared_counts=30, n_top_genes=2000, enforce=True)
    scv.pp.moments(adata, n_pcs=30, n_neighbors=30)

    VELOVI.setup_anndata(adata, spliced_layer="spliced", unspliced_layer="unspliced")
    model = VELOVI(adata)
    model.train(max_epochs=500)

    adata.layers["velocity"] = model.get_velocity()

    vel = np.asarray(adata.layers["velocity"], dtype=np.float64)
    speed = np.sqrt((vel ** 2).sum(axis=1))
    adata.obs["velocity_speed"] = speed

    return {
        "method": "velovi",
        "mean_speed": float(speed.mean()),
        "median_speed": float(np.median(speed)),
        "n_velocity_genes": adata.n_vars,
    }


def run_velocity(adata, *, method: str = "stochastic") -> dict:
    """Run RNA velocity. Returns summary dict."""
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")

    validate_velocity_layers(adata)

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    logger.info("Input: %d cells × %d genes, method=%s", n_cells, n_genes, method)

    if method == "velovi":
        result = run_velovi(adata)
    else:
        result = run_scvelo(adata, mode=method)

    return {"n_cells": n_cells, "n_genes": n_genes, **result}
