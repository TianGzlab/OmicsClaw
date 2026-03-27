"""Spatial RNA velocity analysis functions.

All methods require **spliced + unspliced count layers** as their
fundamental input.  The layers are typically produced by velocyto or
STARsolo during alignment.

Method-specific data flow:

- **stochastic / deterministic**: ``layers["spliced"]`` and
  ``layers["unspliced"]`` → ``filter_and_normalize`` → ``moments`` (→
  ``Ms``, ``Mu`` in layers) → ``scv.tl.velocity(mode=...)`` →
  ``velocity_graph`` → ``velocity_confidence`` → ``velocity_pseudotime``.

- **dynamical**: Same as above, but additionally runs
  ``scv.tl.recover_dynamics()`` before velocity estimation to fit full
  kinetic parameters, and computes ``latent_time``.

- **velovi**: Runs ``filter_and_normalize`` + ``moments`` + ``preprocess_data``
  (initial velocity priors), trains VELOVI model, then extracts velocity
  with posterior sampling (``n_samples=25``), latent time, kinetic rates
  (alpha/beta/gamma), and velocity scaling — following the official
  scvi-tools VELOVI tutorial exactly.

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


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def preprocess_for_velocity(
    adata, *, min_shared_counts: int = 30, n_top_genes: int = 2000,
    n_pcs: int = 30, n_neighbors: int = 30,
) -> None:
    """Filter, normalize, and compute moments for RNA velocity.

    scvelo ≥0.3 removed ``n_top_genes``/``log``/``enforce`` from
    ``filter_and_normalize``; HVG selection, log-transform, PCA, and
    neighbor graph are handled separately as recommended by scvelo ≥0.4
    deprecation notices:

    1. ``scv.pp.filter_and_normalize`` — filters genes and normalizes
       ``X``, ``spliced``, and ``unspliced`` layers simultaneously.
    2. ``sc.pp.log1p`` — log-transforms ``X``.
    3. ``sc.pp.highly_variable_genes`` — selects top HVGs.
    4. ``sc.pp.pca`` + ``sc.pp.neighbors`` — pre-computes neighbor graph
       (avoids scvelo DeprecationWarning about automatic neighbor calculation).
    5. ``scv.pp.moments`` — neighbor-smoothed first-order moments (Ms, Mu).
    """
    import scanpy as sc
    scv = require("scvelo", feature="RNA velocity")
    scv.pp.filter_and_normalize(adata, min_shared_counts=min_shared_counts)
    sc.pp.log1p(adata)
    try:
        sc.pp.highly_variable_genes(adata, n_top_genes=n_top_genes)
    except Exception as e:
        logger.warning("Could not select highly variable genes: %s", e)
    sc.pp.pca(adata, n_comps=n_pcs)
    sc.pp.neighbors(adata, n_pcs=n_pcs, n_neighbors=n_neighbors)
    scv.pp.moments(adata, n_pcs=n_pcs, n_neighbors=n_neighbors)


# ---------------------------------------------------------------------------
# Speed helper (shared by scVelo and VELOVI)
# ---------------------------------------------------------------------------

def _compute_speed(adata) -> pd.Series:
    """Compute per-cell velocity speed from ``adata.layers['velocity']``.

    Prefers ``velocity_length`` written by ``scv.tl.velocity_confidence``
    when available; otherwise computes the L2 norm of the velocity vector.
    Stores the result in ``adata.obs['velocity_speed']`` and returns it.
    """
    if "velocity_length" in adata.obs.columns:
        speed = adata.obs["velocity_length"].copy()
        adata.obs["velocity_speed"] = speed.values
        return speed

    if "velocity" not in adata.layers:
        return pd.Series(dtype=float)

    vel = adata.layers["velocity"]
    if hasattr(vel, "toarray"):
        vel = vel.toarray()
    vals = np.sqrt((np.asarray(vel, dtype=np.float64) ** 2).sum(axis=1))
    adata.obs["velocity_speed"] = vals
    return pd.Series(vals, index=adata.obs_names)


# ---------------------------------------------------------------------------
# scVelo (stochastic / deterministic / dynamical)
# ---------------------------------------------------------------------------

def run_scvelo(adata, *, mode: str = "stochastic") -> dict:
    """Run scVelo RNA velocity.

    Standard workflow (scVelo docs):
      1. filter_and_normalize + moments (if not pre-computed)
      2. velocity estimation (+ recover_dynamics for dynamical mode)
      3. velocity_graph (cosine-similarity transition matrix)
      4. velocity_confidence → velocity_length, velocity_confidence per cell
      5. velocity_pseudotime (cell ordering along velocity field)
      6. latent_time (dynamical mode only)
    """
    scv = require("scvelo", feature="RNA velocity")

    if "Ms" not in adata.layers or "Mu" not in adata.layers:
        logger.info("scVelo %s: computing moments from spliced/unspliced layers", mode)
        preprocess_for_velocity(adata)
    else:
        logger.info("scVelo %s: using pre-computed moments (Ms, Mu)", mode)

    if mode == "dynamical":
        logger.info("Running recover_dynamics (full kinetic model) ...")
        scv.tl.recover_dynamics(adata)
        scv.tl.velocity(adata, mode="dynamical")
        scv.tl.latent_time(adata)
    else:
        scv.tl.velocity(adata, mode=mode)

    scv.tl.velocity_graph(adata)

    # Compute per-cell confidence scores (velocity_length + velocity_confidence)
    try:
        scv.tl.velocity_confidence(adata)
        logger.info("Computed velocity_length and velocity_confidence per cell")
    except Exception as exc:
        logger.warning("velocity_confidence failed (non-fatal): %s", exc)

    # Compute pseudotime ordering along the velocity field
    try:
        scv.tl.velocity_pseudotime(adata)
        logger.info("Computed velocity_pseudotime")
    except Exception as exc:
        logger.warning("velocity_pseudotime failed (non-fatal): %s", exc)

    speed = _compute_speed(adata)

    result: dict = {
        "method": f"scvelo_{mode}",
        "n_velocity_genes": int(np.sum(adata.var["velocity_genes"]))
        if "velocity_genes" in adata.var.columns else None,
        "mean_speed": float(speed.mean()) if not speed.empty else 0.0,
        "median_speed": float(speed.median()) if not speed.empty else 0.0,
    }

    if "velocity_confidence" in adata.obs.columns:
        conf = adata.obs["velocity_confidence"].dropna()
        result["mean_confidence"] = float(conf.mean()) if not conf.empty else None

    return result


# ---------------------------------------------------------------------------
# VELOVI (variational inference)
# ---------------------------------------------------------------------------

def run_velovi(adata) -> dict:
    """Run VELOVI — variational inference RNA velocity.

    Follows the official scvi-tools VELOVI tutorial exactly:
      1. filter_and_normalize + moments → Ms / Mu
      2. preprocess_data(adata) → initial deterministic velocity priors
      3. VELOVI.setup_anndata(spliced_layer="Ms", unspliced_layer="Mu")
      4. model.train(max_epochs=500, early stopping)
      5. get_velocity(n_samples=25, velo_statistic="mean") + velocity scaling
      6. get_latent_time(n_samples=25) → latent_time_velovi layer
      7. Store kinetic rates (alpha, beta, gamma) in adata.var
      8. velocity_graph for downstream embedding / trajectory use
    """
    require("scvelo", feature="VELOVI preprocessing")
    require("scvi-tools", feature="VELOVI (VeloVI)")

    import torch
    import scvelo as scv
    from scvi.external import VELOVI

    try:
        from velovi import preprocess_data as velovi_preprocess_data
        _has_velovi_preprocess = True
    except ImportError:
        _has_velovi_preprocess = False

    if "spliced" not in adata.layers or "unspliced" not in adata.layers:
        raise ValueError("VELOVI requires 'spliced' and 'unspliced' layers.")

    import scanpy as sc
    logger.info("VELOVI: preprocessing spliced/unspliced counts → moments (Ms, Mu)")
    scv.pp.filter_and_normalize(adata, min_shared_counts=30)
    sc.pp.log1p(adata)
    try:
        sc.pp.highly_variable_genes(adata, n_top_genes=2000)
    except Exception as e:
        logger.warning("VELOVI: Could not select highly variable genes: %s", e)
    sc.pp.pca(adata, n_comps=30)
    sc.pp.neighbors(adata, n_pcs=30, n_neighbors=30)
    scv.pp.moments(adata, n_pcs=30, n_neighbors=30)

    # Compute initial deterministic velocity priors (used as model regularisation)
    if _has_velovi_preprocess:
        logger.info("VELOVI: computing initial velocity priors via preprocess_data()")
        velovi_preprocess_data(adata)
    else:
        logger.info("VELOVI: velovi.preprocess_data not available, skipping priors")

    logger.info("VELOVI: setting up model with moments (Ms, Mu) as input")
    VELOVI.setup_anndata(adata, spliced_layer="Ms", unspliced_layer="Mu")
    model = VELOVI(adata)
    model.train(max_epochs=500)

    # Posterior velocity with sampling (official recommendation: n_samples=25)
    latent_time = model.get_latent_time(n_samples=25)
    velocities = model.get_velocity(n_samples=25, velo_statistic="mean")

    # Scale velocity to a biologically interpretable range (official tutorial)
    scaling = 20.0 / latent_time.max(0)
    adata.layers["velocity"] = velocities / scaling
    adata.layers["latent_time_velovi"] = latent_time

    # Store kinetic rates for downstream interpretation
    rates = model.get_rates()
    adata.var["fit_alpha"] = rates["alpha"] / scaling
    adata.var["fit_beta"] = rates["beta"] / scaling
    adata.var["fit_gamma"] = rates["gamma"] / scaling
    try:
        adata.var["fit_t_"] = (
            torch.nn.functional.softplus(model.module.switch_time_unconstr)
            .detach().cpu().numpy()
        ) * scaling
    except AttributeError:
        pass
    adata.layers["fit_t"] = latent_time.values * scaling[np.newaxis, :]
    adata.var["fit_scaling"] = 1.0

    # Build velocity graph so downstream tools (scv.pl, CellRank) work
    scv.tl.velocity_graph(adata)

    speed = _compute_speed(adata)

    return {
        "method": "velovi",
        "mean_speed": float(speed.mean()) if not speed.empty else 0.0,
        "median_speed": float(speed.median()) if not speed.empty else 0.0,
        "n_velocity_genes": adata.n_vars,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_velocity(adata, *, method: str = "stochastic") -> dict:
    """Run RNA velocity analysis and return a summary dict.

    All methods require ``adata.layers["spliced"]`` and
    ``adata.layers["unspliced"]`` as their fundamental input source.

    Parameters
    ----------
    adata:
        AnnData object with ``spliced`` and ``unspliced`` count layers.
    method:
        One of ``SUPPORTED_METHODS``.

    Returns
    -------
    dict
        Summary containing ``n_cells``, ``n_genes``, ``method``,
        ``mean_speed``, ``median_speed``, and method-specific extras.
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")

    validate_velocity_layers(adata)

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    logger.info(
        "Input: %d cells × %d genes, method=%s; "
        "spliced shape=%s, unspliced shape=%s",
        n_cells, n_genes, method,
        adata.layers["spliced"].shape, adata.layers["unspliced"].shape,
    )

    result = run_velovi(adata) if method == "velovi" else run_scvelo(adata, mode=method)
    return {"n_cells": n_cells, "n_genes": n_genes, **result}
