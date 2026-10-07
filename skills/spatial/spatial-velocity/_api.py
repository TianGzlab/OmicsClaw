"""Spatial RNA velocity from measured spliced and unspliced layers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from skills.spatial._lib.velocity import run_velocity, validate_velocity_layers
from skills.spatial._lib.inference_result import read_info, store_info

__all__ = ["velocity", "run_info", "cell_metrics", "gene_metrics", "velocity_figure"]
_RUN_KEY = "omicsclaw_spatial_velocity_run"


def velocity(adata, *, method: str = "stochastic", cluster_key: str = "leiden",
             method_params: dict | None = None, random_state: int = 0):
    """Estimate velocity in place from spliced/unspliced count layers.

    Preprocessing filters genes, normalizes X and count layers, and builds
    PCA/neighbors/moments. Optional confidence, pseudotime and latent-time
    failures are reported in run_info warnings. VELOVI GPU results can vary
    between runs even with a fixed seed. scVelo velocity pseudotime uses an
    eigensolver without a seed argument; its results vary between runs.

    :param adata: AnnData containing measured spliced and unspliced layers.
    :param method: stochastic (CLI default), deterministic, dynamical or velovi.
    :param cluster_key: Annotation used in output summaries; default leiden.
    :param method_params: CLI options with underscores; None keeps defaults,
        including velocity_min_shared_counts=30 and velocity_n_pcs=30.
        See references/parameters.md for method-specific controls.
    :param random_state: PCA/neighbor and VELOVI training seed, default 0.
    :returns: The same AnnData with velocity layers, graph and JSON diagnostics.
    :raises ValueError: Missing layers or invalid method.
    :raises ImportError: A backend is unavailable; use install_skill_deps.
    """
    validate_velocity_layers(adata)
    options = dict(method_params or {})
    if options.get("velocity_n_pcs", 30) < 2:
        raise ValueError("velocity_n_pcs must be >= 2")
    try:
        summary = run_velocity(adata, method=method, cluster_key=cluster_key,
                               random_state=random_state, **options)
    except ImportError as exc:
        raise ImportError(f"{method} backend unavailable: {exc}; use install_skill_deps") from exc
    summary["random_state"] = random_state
    store_info(adata, _RUN_KEY, summary)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the last velocity method's diagnostics and metric tables.

    :param adata: AnnData returned by velocity.
    :param keep: True retains diagnostics; False removes them for CLI serialization.
    :returns: A dictionary with effective method controls and warnings, or empty dict.
    """
    return read_info(adata, _RUN_KEY, keep=keep)


def cell_metrics(adata) -> pd.DataFrame:
    """Return velocity speed, confidence and pseudotime for each spot.

    :param adata: AnnData returned by velocity.
    :returns: The last run's barcode-indexed cell table, or an empty table.
    """
    return run_info(adata).get("cell_df", pd.DataFrame()).copy()


def gene_metrics(adata) -> pd.DataFrame:
    """Return fitted velocity gene parameters and fit quality.

    :param adata: AnnData returned by velocity.
    :returns: The last run's gene-indexed table, or an empty table.
    """
    return run_info(adata).get("gene_df", pd.DataFrame()).copy()


def velocity_figure(adata, *, color: str = "velocity_speed", basis: str = "spatial"):
    """Plot a numeric velocity metric at spot coordinates without saving.

    :param adata: AnnData after velocity inference.
    :param color: Numeric observation metric; velocity_speed by default.
    :param basis: Coordinate key, spatial by default; X_umap is also supported.
    :returns: A matplotlib Figure owned by the caller.
    :raises KeyError: Missing coordinates or metric.
    """
    import matplotlib.pyplot as plt

    coords = np.asarray(adata.obsm[basis])
    fig, ax = plt.subplots(figsize=(6, 5))
    points = ax.scatter(coords[:, 0], coords[:, 1], c=adata.obs[color], s=16)
    fig.colorbar(points, ax=ax, label=color)
    fig.tight_layout()
    return fig
