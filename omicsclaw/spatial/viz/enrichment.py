"""Pathway enrichment visualization for SpatialClaw.

Sub-types:
- ``barplot``  — horizontal bar chart of top enriched pathways (default)
- ``dotplot``  — bubble plot (size = gene count, colour = p-value)
- ``spatial``  — spatial map of ssGSEA enrichment scores
- ``violin``   — violin plots of enrichment scores per cluster

Requires ``gseapy`` for barplot/dotplot sub-types.
``spatial`` requires pre-computed enrichment scores stored in ``adata.obs``.

Adapted from ChatSpatial visualization/enrichment.py — removed async/ToolContext.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .core import (
    VizParams,
    _require_spatial_coords,
    auto_spot_size,
    get_categorical_columns,
    safe_tight_layout,
    setup_multi_panel_figure,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_enrichment(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    subtype: Optional[str] = None,
    cluster_key: Optional[str] = None,
    top_n: int = 20,
) -> plt.Figure:
    """Pathway enrichment visualization.

    Args:
        adata: AnnData object.  For ``barplot``/``dotplot`` sub-types, enrichment
               results must be in ``adata.uns['enrichment_results']`` or as a
               ``gseapy`` result object.  For ``spatial``/``violin``, enrichment
               scores must be stored as columns in ``adata.obs``.
        params: :class:`~omicsclaw.spatial.viz.params.VizParams`.
        subtype: ``"barplot"`` (default), ``"dotplot"``, ``"spatial"``,
                 or ``"violin"``.
        cluster_key: obs column for grouping (``"violin"`` sub-type).
        top_n: Number of top pathways to display.

    Returns:
        :class:`matplotlib.figure.Figure`
    """
    if params is None:
        params = VizParams()
    if subtype:
        params.subtype = subtype
    if cluster_key:
        params.cluster_key = cluster_key

    st = params.subtype or "barplot"
    logger.info("Creating enrichment visualization: %s", st)

    dispatch = {
        "barplot": _plot_barplot,
        "dotplot": _plot_dotplot,
        "spatial": _plot_spatial,
        "violin": _plot_violin,
    }
    if st not in dispatch:
        raise ValueError(
            f"Unknown enrichment subtype '{st}'. "
            "Choose: 'barplot', 'dotplot', 'spatial', 'violin'."
        )
    return dispatch[st](adata, params, top_n=top_n)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _find_enrichment_results(adata: Any) -> pd.DataFrame:
    """Return enrichment results DataFrame from adata.uns."""
    candidates = [
        "enrichment_results", "gsea_results", "enrichr_results",
        "pathway_enrichment", "ora_results",
    ]
    for key in candidates:
        if key in adata.uns:
            val = adata.uns[key]
            if isinstance(val, pd.DataFrame) and len(val) > 0:
                return val
    raise ValueError(
        "No enrichment results found. Run spatial-enrichment first.\n"
        f"Expected one of: {candidates} in adata.uns."
    )


def _find_score_columns(adata: Any) -> list[str]:
    """Detect enrichment score columns in adata.obs."""
    candidates = [
        c for c in adata.obs.columns
        if any(tok in c.lower() for tok in ("score", "enrichment", "gsva", "ssgsea"))
        and pd.api.types.is_numeric_dtype(adata.obs[c])
    ]
    if not candidates and "enrichment_score_columns" in adata.uns:
        candidates = list(adata.uns["enrichment_score_columns"])
    return candidates


# ---------------------------------------------------------------------------
# Barplot
# ---------------------------------------------------------------------------


def _plot_barplot(adata: Any, params: VizParams, *, top_n: int) -> plt.Figure:
    """Horizontal bar chart of top enriched pathways."""
    df = _find_enrichment_results(adata)

    # Detect key columns
    term_col = next((c for c in ("Term", "Pathway", "pathway", "term") if c in df.columns), df.columns[0])
    pval_col = next(
        (c for c in ("Adjusted P-value", "FDR q-val", "p_adj", "pvalue", "P-value")
         if c in df.columns), None,
    )
    score_col = next(
        (c for c in ("Combined Score", "NES", "Enrichment Score", "ES", "score")
         if c in df.columns), None,
    )

    df = df.copy().head(top_n)
    if pval_col:
        df["_neg_log_p"] = -np.log10(
            np.clip(pd.to_numeric(df[pval_col], errors="coerce").fillna(1.0), 1e-300, 1.0)
        )
    else:
        df["_neg_log_p"] = np.arange(len(df), 0, -1, dtype=float)

    figsize = params.figure_size or (9, max(4, len(df) * 0.38))
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    cmap = plt.cm.get_cmap(params.colormap or "viridis")
    norm = plt.Normalize(df["_neg_log_p"].min(), df["_neg_log_p"].max())
    colors = [cmap(norm(v)) for v in df["_neg_log_p"].values]

    y_pos = np.arange(len(df))
    bar_vals = (
        pd.to_numeric(df[score_col], errors="coerce").fillna(0).values
        if score_col else df["_neg_log_p"].values
    )
    ax.barh(y_pos, bar_vals, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(df[term_col].values, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel(score_col or "-log10(p-value)", fontsize=11)
    ax.set_title(params.title or "Top Enriched Pathways", fontsize=13, fontweight="bold")

    if params.show_colorbar:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        plt.colorbar(sm, ax=ax, label="-log10(adj. p-value)", pad=0.02)

    safe_tight_layout(fig)
    return fig


# ---------------------------------------------------------------------------
# Dotplot
# ---------------------------------------------------------------------------


def _plot_dotplot(adata: Any, params: VizParams, *, top_n: int) -> plt.Figure:
    """Bubble plot: x = NES / score, y = term, size = gene count, colour = p-value."""
    df = _find_enrichment_results(adata)

    term_col = next((c for c in ("Term", "Pathway", "pathway", "term") if c in df.columns), df.columns[0])
    score_col = next(
        (c for c in ("NES", "Combined Score", "Enrichment Score", "ES", "score")
         if c in df.columns), None,
    )
    pval_col = next(
        (c for c in ("Adjusted P-value", "FDR q-val", "p_adj", "pvalue", "P-value")
         if c in df.columns), None,
    )
    n_genes_col = next(
        (c for c in ("Overlap", "n_genes", "Gene_count", "gene_count") if c in df.columns), None
    )

    df = df.copy().head(top_n)
    x_vals = pd.to_numeric(df[score_col], errors="coerce").fillna(0).values if score_col else np.arange(len(df), 0, -1, dtype=float)
    pvals = pd.to_numeric(df[pval_col], errors="coerce").fillna(1.0).values if pval_col else np.ones(len(df))
    neg_log_p = -np.log10(np.clip(pvals, 1e-300, 1.0))

    if n_genes_col:
        def _parse_overlap(v: Any) -> float:
            try:
                if isinstance(v, str) and "/" in v:
                    return float(v.split("/")[0])
                return float(v)
            except Exception:
                return 10.0
        sizes = np.array([_parse_overlap(v) for v in df[n_genes_col]])
        sizes = np.clip(sizes, 5, 100) * 5
    else:
        sizes = 80.0

    figsize = params.figure_size or (8, max(4, len(df) * 0.38))
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    cmap = plt.cm.get_cmap(params.colormap or "RdBu_r")
    norm = plt.Normalize(neg_log_p.min(), neg_log_p.max())
    colors = [cmap(norm(v)) for v in neg_log_p]

    y_pos = np.arange(len(df))
    ax.scatter(x_vals, y_pos, c=colors, s=sizes, alpha=0.85, edgecolors="white", linewidths=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(df[term_col].values, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color="grey", lw=0.8, ls="--", alpha=0.5)
    ax.set_xlabel(score_col or "Score", fontsize=11)
    ax.set_title(params.title or "Pathway Enrichment Dotplot", fontsize=13, fontweight="bold")

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, label="-log10(adj. p-value)", pad=0.02)
    safe_tight_layout(fig)
    return fig


# ---------------------------------------------------------------------------
# Spatial enrichment score map
# ---------------------------------------------------------------------------


def _plot_spatial(adata: Any, params: VizParams, *, top_n: int) -> plt.Figure:
    """Spatial maps of per-spot enrichment scores."""
    score_cols = _find_score_columns(adata)
    if not score_cols:
        raise ValueError(
            "No enrichment score columns found in adata.obs. "
            "Run ssGSEA or AUCell first, then visualise."
        )

    n_show = min(len(score_cols), top_n, 12)
    cols_to_show = score_cols[:n_show]
    coords = _require_spatial_coords(adata)
    spot_size = auto_spot_size(adata, params.spot_size, basis="spatial")

    fig, axes = setup_multi_panel_figure(
        n_panels=n_show,
        params=params,
        default_title="Pathway Enrichment Scores (Spatial)",
    )

    for i, col in enumerate(cols_to_show):
        ax = axes[i]
        values = adata.obs[col].values.astype(float)
        sc = ax.scatter(
            coords[:, 0], coords[:, 1],
            c=values, cmap=params.colormap or "RdBu_r",
            s=spot_size, alpha=params.alpha,
        )
        if params.show_colorbar:
            plt.colorbar(sc, ax=ax)
        label = col if len(col) <= 25 else col[:22] + "..."
        ax.set_title(label, fontsize=9)
        ax.set_aspect("equal")
        ax.invert_yaxis()
        ax.axis("off")

    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Violin plots of enrichment scores per cluster
# ---------------------------------------------------------------------------


def _plot_violin(adata: Any, params: VizParams, *, top_n: int) -> plt.Figure:
    """Violin plots of enrichment scores grouped by cluster."""
    import seaborn as sns

    score_cols = _find_score_columns(adata)
    if not score_cols:
        raise ValueError(
            "No enrichment score columns found in adata.obs. "
            "Run ssGSEA or AUCell first."
        )

    cluster_key = params.cluster_key
    if not cluster_key:
        for cand in ("leiden", "louvain", "cluster", "cell_type", "celltype"):
            if cand in adata.obs.columns:
                cluster_key = cand
                break
    if not cluster_key or cluster_key not in adata.obs.columns:
        raise ValueError(
            "cluster_key required for violin plots. "
            "Set params.cluster_key or cluster_key=."
        )

    n_show = min(len(score_cols), top_n, 6)
    cols_to_show = score_cols[:n_show]

    fig, axes = setup_multi_panel_figure(
        n_panels=n_show,
        params=params,
        default_title="Pathway Enrichment Scores by Cluster",
        use_tight_layout=True,
    )

    for i, col in enumerate(cols_to_show):
        ax = axes[i]
        plot_data = adata.obs[[cluster_key, col]].copy()
        plot_data.columns = ["Cluster", "Score"]
        sns.violinplot(
            data=plot_data, x="Cluster", y="Score", ax=ax,
            inner="box", linewidth=0.8,
        )
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
        label = col if len(col) <= 30 else col[:27] + "..."
        ax.set_title(label, fontsize=9)
        ax.set_xlabel("")
        ax.set_ylabel("Score", fontsize=9)

    safe_tight_layout(fig)
    return fig
