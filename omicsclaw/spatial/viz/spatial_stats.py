"""Spatial statistics visualization for SpatialClaw.

Sub-types:
- ``moran``        — horizontal bar plot of top spatially variable genes (Moran's I)
- ``neighborhood`` — neighbourhood enrichment heatmap (squidpy)
- ``co_occurrence``— co-occurrence rate curves (squidpy)
- ``ripley``       — Ripley's L function (squidpy)
- ``centrality``   — graph centrality scores (squidpy)

Adapted from ChatSpatial visualization/spatial_stats.py — removed async/ToolContext.
``moran`` is the only sub-type that requires no extra dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np

from .core import VizParams, get_categorical_columns, safe_tight_layout

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_spatial_stats(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    subtype: Optional[str] = None,
    cluster_key: Optional[str] = None,
) -> plt.Figure:
    """Spatial statistics visualization.

    Args:
        adata: AnnData object with pre-computed spatial statistics.
        params: :class:`~omicsclaw.spatial.viz.params.VizParams`.
        subtype: ``"moran"`` (default), ``"neighborhood"``, ``"co_occurrence"``,
                 ``"ripley"``, or ``"centrality"``.
        cluster_key: obs column for cluster labels (required by most subtypes).

    Returns:
        :class:`matplotlib.figure.Figure`
    """
    if params is None:
        params = VizParams()
    if subtype:
        params.subtype = subtype
    if cluster_key:
        params.cluster_key = cluster_key

    st = params.subtype or "moran"
    logger.info("Creating spatial stats visualization: %s", st)

    dispatch = {
        "moran": _plot_moran,
        "neighborhood": _plot_neighborhood,
        "co_occurrence": _plot_co_occurrence,
        "ripley": _plot_ripley,
        "centrality": _plot_centrality,
    }
    if st not in dispatch:
        raise ValueError(
            f"Unknown spatial stats subtype '{st}'. "
            "Choose: 'moran', 'neighborhood', 'co_occurrence', 'ripley', 'centrality'."
        )
    return dispatch[st](adata, params)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_cluster_key(adata: Any, params: VizParams) -> str:
    key = params.cluster_key
    if not key:
        for candidate in ("leiden", "louvain", "cluster", "cell_type", "celltype"):
            if candidate in adata.obs.columns:
                logger.info("Auto-detected cluster key: %s", candidate)
                return candidate
        avail = get_categorical_columns(adata, limit=10)
        raise ValueError(
            "cluster_key required. "
            f"Available categorical columns: {avail}"
        )
    if key not in adata.obs.columns:
        raise ValueError(f"cluster_key '{key}' not found in adata.obs")
    return key


# ---------------------------------------------------------------------------
# Moran's I barplot (no external deps — pure matplotlib)
# ---------------------------------------------------------------------------


def _plot_moran(adata: Any, params: VizParams) -> plt.Figure:
    """Top spatially variable genes ranked by Moran's I.

    Expects ``adata.uns['moranI']`` with columns ``I`` and ``pval_norm``.
    """
    if "moranI" not in adata.uns:
        raise ValueError(
            "Moran's I results not found in adata.uns['moranI']. "
            "Run sq.gr.spatial_autocorr first."
        )

    moran_data = adata.uns["moranI"].copy()
    moran_data["gene"] = moran_data.index

    pvals = moran_data["pval_norm"].values
    min_pval = max(1e-50, np.min(pvals[pvals > 0]) if np.any(pvals > 0) else 1e-50)
    pvals_safe = np.clip(pvals, min_pval, 1.0)
    moran_data["neg_log_pval"] = -np.log10(pvals_safe)
    moran_data["significant"] = pvals < 0.05

    n_top = min(20, len(moran_data))
    top_genes = moran_data.nlargest(n_top, "I")
    n_actual = len(top_genes)

    figsize = params.figure_size or (8, max(n_actual * 0.4 + 1.5, 3))
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    norm = plt.Normalize(
        vmin=top_genes["neg_log_pval"].min(),
        vmax=top_genes["neg_log_pval"].max(),
    )
    cmap = plt.colormaps.get_cmap(params.colormap or "viridis")
    colors = [cmap(norm(v)) for v in top_genes["neg_log_pval"].values]

    y_pos = np.arange(n_actual)
    ax.barh(
        y_pos, top_genes["I"].values,
        color=colors, alpha=params.alpha,
        edgecolor="black", linewidth=0.5,
    )
    ax.set_yticks(y_pos)
    ax.set_yticklabels(top_genes["gene"].values)
    ax.invert_yaxis()

    for i, (_, row) in enumerate(top_genes.iterrows()):
        if row["significant"]:
            ax.text(
                row["I"] + 0.01, i, "*",
                va="center", ha="left", fontsize=12, fontweight="bold",
            )

    ax.set_title(
        params.title or "Top Spatially Variable Genes (Moran's I)",
        fontsize=14, fontweight="bold",
    )
    ax.set_xlabel("Moran's I (spatial autocorrelation)", fontsize=12)
    ax.set_ylabel("Gene", fontsize=12)
    ax.axvline(x=0, color="gray", linestyle="--", alpha=0.5, linewidth=1)

    if params.show_colorbar:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax, pad=0.02)
        cbar.set_label("-log10(p-value)", fontsize=10)

    n_sig = int(top_genes["significant"].sum())
    ax.text(
        0.98, 0.02,
        f"* p < 0.05 ({n_sig}/{n_actual} significant)",
        transform=ax.transAxes, ha="right", va="bottom",
        fontsize=9, style="italic", color="gray",
    )

    safe_tight_layout(fig)
    return fig


# ---------------------------------------------------------------------------
# squidpy-based subtypes
# ---------------------------------------------------------------------------


def _plot_neighborhood(adata: Any, params: VizParams) -> plt.Figure:
    """Neighbourhood enrichment heatmap (requires squidpy)."""
    try:
        import squidpy as sq
    except ImportError:
        raise ImportError(
            "squidpy is required for neighbourhood enrichment plots. "
            "Install with: pip install squidpy"
        )

    cluster_key = _resolve_cluster_key(adata, params)
    enrichment_key = f"{cluster_key}_nhood_enrichment"
    if enrichment_key not in adata.uns:
        raise ValueError(
            f"Neighbourhood enrichment not found. "
            f"Run sq.gr.nhood_enrichment(adata, cluster_key='{cluster_key}') first."
        )

    figsize = params.figure_size or (10, 8)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)
    sq.pl.nhood_enrichment(
        adata, cluster_key=cluster_key,
        cmap=params.colormap or "coolwarm", ax=ax,
        title=params.title or f"Neighbourhood Enrichment ({cluster_key})",
    )
    safe_tight_layout(fig)
    return fig


def _plot_co_occurrence(adata: Any, params: VizParams) -> plt.Figure:
    """Co-occurrence rate curves (requires squidpy)."""
    try:
        import squidpy as sq
    except ImportError:
        raise ImportError(
            "squidpy is required for co-occurrence plots. "
            "Install with: pip install squidpy"
        )

    cluster_key = _resolve_cluster_key(adata, params)
    co_key = f"{cluster_key}_co_occurrence"
    if co_key not in adata.uns:
        raise ValueError(
            f"Co-occurrence results not found. "
            f"Run sq.gr.co_occurrence(adata, cluster_key='{cluster_key}') first."
        )

    cats = list(adata.obs[cluster_key].cat.categories)
    clusters_to_show = cats[: min(4, len(cats))]
    figsize = params.figure_size  # let squidpy auto-size unless overridden

    sq.pl.co_occurrence(
        adata, cluster_key=cluster_key,
        clusters=clusters_to_show,
        figsize=figsize, dpi=params.dpi,
    )
    fig = plt.gcf()
    if params.title:
        fig.suptitle(params.title, y=1.02)
    return fig


def _plot_ripley(adata: Any, params: VizParams) -> plt.Figure:
    """Ripley's L function curves (requires squidpy)."""
    try:
        import squidpy as sq
    except ImportError:
        raise ImportError(
            "squidpy is required for Ripley plots. "
            "Install with: pip install squidpy"
        )

    cluster_key = _resolve_cluster_key(adata, params)
    ripley_key = f"{cluster_key}_ripley_L"
    if ripley_key not in adata.uns:
        raise ValueError(
            f"Ripley results not found. "
            f"Run sq.gr.ripley(adata, cluster_key='{cluster_key}', mode='L') first."
        )

    figsize = params.figure_size or (10, 8)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)
    sq.pl.ripley(adata, cluster_key=cluster_key, mode="L", plot_sims=True, ax=ax)
    if params.title:
        ax.set_title(params.title)
    safe_tight_layout(fig)
    return fig


def _plot_centrality(adata: Any, params: VizParams) -> plt.Figure:
    """Graph centrality scores (requires squidpy)."""
    try:
        import squidpy as sq
    except ImportError:
        raise ImportError(
            "squidpy is required for centrality plots. "
            "Install with: pip install squidpy"
        )

    cluster_key = _resolve_cluster_key(adata, params)
    centrality_key = f"{cluster_key}_centrality_scores"
    if centrality_key not in adata.uns:
        raise ValueError(
            f"Centrality scores not found. "
            f"Run sq.gr.centrality_scores(adata, cluster_key='{cluster_key}') first."
        )

    figsize = params.figure_size or (12, 5)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)
    sq.pl.centrality_scores(adata, cluster_key=cluster_key, ax=ax)
    if params.title:
        ax.set_title(params.title)
    safe_tight_layout(fig)
    return fig
