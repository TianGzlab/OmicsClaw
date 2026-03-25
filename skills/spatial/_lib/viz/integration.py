"""Batch integration quality visualization for SpatialClaw.

Sub-types:
- ``batch``     — UMAP coloured by batch (assess mixing)
- ``cluster``   — UMAP coloured by cluster (assess bio-structure preservation)
- ``highlight`` — per-batch highlight panels (detailed distribution)

Adapted from ChatSpatial visualization/integration.py — removed async/ToolContext.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np

from .core import VizParams, get_categorical_cmap

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_integration(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    subtype: Optional[str] = None,
    batch_key: Optional[str] = None,
    cluster_key: Optional[str] = None,
) -> plt.Figure:
    """Visualise batch integration quality.

    Args:
        adata: AnnData object with UMAP embedding (``adata.obsm['X_umap']``).
        params: :class:`~skills.spatial._lib.viz.params.VizParams`.
        subtype: ``"batch"`` (default), ``"cluster"``, or ``"highlight"``.
        batch_key: obs column for batch labels.
        cluster_key: obs column for cluster labels.

    Returns:
        :class:`matplotlib.figure.Figure`
    """
    if params is None:
        params = VizParams()
    if subtype:
        params.subtype = subtype
    if batch_key:
        params.batch_key = batch_key
    if cluster_key:
        params.cluster_key = cluster_key

    if "X_umap" not in adata.obsm:
        raise ValueError(
            "UMAP coordinates not found in adata.obsm['X_umap']. "
            "Run sc.tl.umap first."
        )

    st = params.subtype or "batch"
    dispatch = {
        "batch": _plot_by_batch,
        "cluster": _plot_by_cluster,
        "highlight": _plot_batch_highlight,
    }
    if st not in dispatch:
        raise ValueError(
            f"Unknown integration subtype '{st}'. Choose: 'batch', 'cluster', 'highlight'."
        )
    return dispatch[st](adata, params)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_batch_key(adata: Any, params: VizParams) -> str:
    key = params.batch_key
    if not key:
        for candidate in ("batch", "sample", "library_id", "slide"):
            if candidate in adata.obs.columns:
                logger.info("Auto-detected batch key: %s", candidate)
                return candidate
        raise ValueError(
            "No batch_key provided and none auto-detected. "
            "Set params.batch_key or batch_key=."
        )
    if key not in adata.obs.columns:
        raise ValueError(f"batch_key '{key}' not found in adata.obs")
    return key


def _get_cluster_key(adata: Any, params: VizParams) -> str:
    key = params.cluster_key
    if not key:
        for candidate in ("leiden", "louvain", "cluster", "cell_type", "celltype"):
            if candidate in adata.obs.columns:
                logger.info("Auto-detected cluster key: %s", candidate)
                return candidate
        raise ValueError(
            "No cluster_key provided and none auto-detected. "
            "Set params.cluster_key or cluster_key=."
        )
    if key not in adata.obs.columns:
        raise ValueError(f"cluster_key '{key}' not found in adata.obs")
    return key


def _category_colors(series: Any, n: int) -> list[Any]:
    cmap_name = get_categorical_cmap(n)
    cmap = plt.cm.get_cmap(cmap_name)
    return [cmap(i / max(1, n - 1)) for i in range(n)]


# ---------------------------------------------------------------------------
# Subtype: batch
# ---------------------------------------------------------------------------


def _plot_by_batch(adata: Any, params: VizParams) -> plt.Figure:
    """UMAP coloured by batch label — good integration shows mixed colours."""
    batch_key = _get_batch_key(adata, params)
    umap = np.asarray(adata.obsm["X_umap"])
    batch_vals = adata.obs[batch_key]
    batches = (
        batch_vals.cat.categories
        if hasattr(batch_vals, "cat")
        else np.unique(batch_vals)
    )
    n = len(batches)
    colors = _category_colors(batch_vals, n)

    figsize = params.figure_size or (8, 6)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    for i, batch in enumerate(batches):
        mask = batch_vals == batch
        ax.scatter(
            umap[mask, 0], umap[mask, 1],
            c=[colors[i]], label=str(batch),
            s=params.spot_size or 10, alpha=params.alpha, rasterized=True,
        )

    ax.set_xlabel("UMAP 1", fontsize=12)
    ax.set_ylabel("UMAP 2", fontsize=12)
    ax.set_title(
        params.title or "UMAP by Batch\n(good integration → mixed colours)",
        fontsize=14,
    )
    if params.show_legend:
        ax.legend(
            title="Batch", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False
        )
    ax.set_aspect("equal", adjustable="datalim")
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Subtype: cluster
# ---------------------------------------------------------------------------


def _plot_by_cluster(adata: Any, params: VizParams) -> plt.Figure:
    """UMAP coloured by cluster — good integration preserves bio structure."""
    cluster_key = _get_cluster_key(adata, params)
    umap = np.asarray(adata.obsm["X_umap"])
    cluster_vals = adata.obs[cluster_key]
    clusters = (
        cluster_vals.cat.categories
        if hasattr(cluster_vals, "cat")
        else np.unique(cluster_vals)
    )
    n = len(clusters)
    colors = _category_colors(cluster_vals, n)

    figsize = params.figure_size or (8, 6)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    for i, cl in enumerate(clusters):
        mask = cluster_vals == cl
        ax.scatter(
            umap[mask, 0], umap[mask, 1],
            c=[colors[i]], label=str(cl),
            s=params.spot_size or 10, alpha=params.alpha, rasterized=True,
        )

    ax.set_xlabel("UMAP 1", fontsize=12)
    ax.set_ylabel("UMAP 2", fontsize=12)
    ax.set_title(
        params.title or f"UMAP by {cluster_key}\n(good integration → preserved clusters)",
        fontsize=14,
    )
    if params.show_legend:
        ncol = 2 if n > 10 else 1
        ax.legend(
            title=cluster_key, bbox_to_anchor=(1.02, 1), loc="upper left",
            frameon=False, ncol=ncol,
        )
    ax.set_aspect("equal", adjustable="datalim")
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Subtype: highlight
# ---------------------------------------------------------------------------


def _plot_batch_highlight(adata: Any, params: VizParams) -> plt.Figure:
    """Multi-panel UMAP: each batch highlighted against a grey background."""
    batch_key = _get_batch_key(adata, params)
    umap = np.asarray(adata.obsm["X_umap"])
    batch_vals = adata.obs[batch_key]
    batches = (
        batch_vals.cat.categories
        if hasattr(batch_vals, "cat")
        else np.unique(batch_vals)
    )
    n = len(batches)
    colors = _category_colors(batch_vals, n)

    n_cols = min(4, n)
    n_rows = (n + n_cols - 1) // n_cols
    figsize = params.figure_size or (4 * n_cols, 3.5 * n_rows)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=figsize, dpi=params.dpi)
    axes = np.atleast_2d(axes).flatten()

    for i, batch in enumerate(batches):
        ax = axes[i]
        mask = batch_vals == batch

        # Grey background
        ax.scatter(
            umap[~mask, 0], umap[~mask, 1],
            c="lightgray", s=3, alpha=0.3, rasterized=True,
        )
        # Coloured foreground
        ax.scatter(
            umap[mask, 0], umap[mask, 1],
            c=[colors[i]], s=params.spot_size or 8,
            alpha=params.alpha, rasterized=True,
        )
        n_cells = int(mask.sum())
        ax.set_title(f"{batch}\n(n={n_cells:,})", fontsize=11)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal", adjustable="datalim")

    for i in range(n, len(axes)):
        axes[i].axis("off")

    fig.suptitle(
        params.title or "Per-Batch Distribution",
        fontsize=14, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    return fig
