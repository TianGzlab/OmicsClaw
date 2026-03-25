"""Gene expression aggregate visualizations for SpatialClaw.

Sub-types:
- ``heatmap``    — scanpy heatmap grouped by cluster
- ``violin``     — scanpy violin plot grouped by cluster
- ``dotplot``    — scanpy dotplot (expression + fraction)
- ``correlation``— seaborn clustermap of gene-gene correlations

Adapted from ChatSpatial visualization/expression.py — removed async/ToolContext.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc
import seaborn as sns

from .core import VizParams, validate_features

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_expression(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    subtype: Optional[str] = None,
    genes: Optional[list[str]] = None,
    cluster_key: Optional[str] = None,
) -> plt.Figure:
    """Aggregated gene expression visualisation.

    Args:
        adata: AnnData object.
        params: :class:`~skills.spatial._lib.viz.params.VizParams`.
        subtype: ``"heatmap"`` (default), ``"violin"``, ``"dotplot"``,
                 or ``"correlation"``.
        genes: List of gene names (overrides ``params.feature``).
        cluster_key: obs column for grouping (overrides ``params.cluster_key``).

    Returns:
        :class:`matplotlib.figure.Figure`
    """
    if params is None:
        params = VizParams()
    if subtype:
        params.subtype = subtype
    if genes:
        params.feature = genes
    if cluster_key:
        params.cluster_key = cluster_key

    st = params.subtype or "heatmap"
    logger.info("Creating expression visualization: %s", st)

    dispatch = {
        "heatmap": _plot_heatmap,
        "violin": _plot_violin,
        "dotplot": _plot_dotplot,
        "correlation": _plot_correlation,
    }
    if st not in dispatch:
        raise ValueError(
            f"Unknown expression subtype '{st}'. "
            "Choose: 'heatmap', 'violin', 'dotplot', 'correlation'."
        )
    return dispatch[st](adata, params)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_cluster_key(adata: Any, params: VizParams) -> str:
    """Return cluster_key or auto-detect a suitable column."""
    if params.cluster_key and params.cluster_key in adata.obs.columns:
        return params.cluster_key
    for candidate in ("leiden", "louvain", "cluster", "cell_type", "celltype"):
        if candidate in adata.obs.columns:
            logger.info("Auto-detected cluster key: %s", candidate)
            return candidate
    raise ValueError(
        "No cluster_key provided and no default clustering column found. "
        "Run spatial-domains or set cluster_key."
    )


def _get_genes(adata: Any, params: VizParams, max_genes: int = 30) -> list[str]:
    """Validate and return a list of genes from params."""
    if params.feature is None:
        raise ValueError("No genes provided. Set params.feature or pass genes=.")
    feat_list = params.feature if isinstance(params.feature, list) else [params.feature]
    validated = validate_features(adata, feat_list, max_features=max_genes, genes_only=True)
    if not validated:
        raise ValueError(f"None of the requested genes exist in the data: {feat_list}")
    return validated


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------


def _plot_heatmap(adata: Any, params: VizParams) -> plt.Figure:
    """Scanpy heatmap of mean expression per cluster."""
    groupby = _resolve_cluster_key(adata, params)
    genes = _get_genes(adata, params)
    logger.info("Heatmap: %d genes × %s", len(genes), groupby)

    sc.pl.heatmap(
        adata,
        var_names=genes,
        groupby=groupby,
        cmap=params.colormap,
        show=False,
        dendrogram=params.dotplot_dendrogram,
        swap_axes=params.dotplot_swap_axes,
        standard_scale=params.dotplot_standard_scale,
    )
    return plt.gcf()


# ---------------------------------------------------------------------------
# Violin
# ---------------------------------------------------------------------------


def _plot_violin(adata: Any, params: VizParams) -> plt.Figure:
    """Scanpy violin plot grouped by cluster."""
    groupby = _resolve_cluster_key(adata, params)
    genes = _get_genes(adata, params)
    logger.info("Violin: %d genes × %s", len(genes), groupby)

    sc.pl.violin(
        adata,
        keys=genes,
        groupby=groupby,
        show=False,
    )
    return plt.gcf()


# ---------------------------------------------------------------------------
# Dotplot
# ---------------------------------------------------------------------------


def _plot_dotplot(adata: Any, params: VizParams) -> plt.Figure:
    """Scanpy dotplot showing expression magnitude and cell fraction."""
    groupby = _resolve_cluster_key(adata, params)
    genes = _get_genes(adata, params)
    logger.info("Dotplot: %d genes × %s", len(genes), groupby)

    dotplot_kwargs: dict[str, Any] = {
        "adata": adata,
        "var_names": genes,
        "groupby": groupby,
        "cmap": params.colormap,
        "show": False,
    }
    if params.dotplot_dendrogram:
        dotplot_kwargs["dendrogram"] = True
    if params.dotplot_swap_axes:
        dotplot_kwargs["swap_axes"] = True
    if params.dotplot_standard_scale:
        dotplot_kwargs["standard_scale"] = params.dotplot_standard_scale
    if params.dotplot_dot_min is not None:
        dotplot_kwargs["dot_min"] = params.dotplot_dot_min
    if params.dotplot_dot_max is not None:
        dotplot_kwargs["dot_max"] = params.dotplot_dot_max
    if params.dotplot_smallest_dot is not None:
        dotplot_kwargs["smallest_dot"] = params.dotplot_smallest_dot

    sc.pl.dotplot(**dotplot_kwargs)
    return plt.gcf()


# ---------------------------------------------------------------------------
# Correlation clustermap
# ---------------------------------------------------------------------------


def _plot_correlation(adata: Any, params: VizParams) -> plt.Figure:
    """Seaborn clustermap of gene-gene Pearson/Spearman correlations."""
    genes = _get_genes(adata, params, max_genes=20)
    logger.info("Correlation: %d genes, method=%s", len(genes), params.correlation_method)

    # Build expression matrix
    import scipy.sparse as sp

    gene_idx = [adata.var_names.get_loc(g) for g in genes]
    X = adata.X[:, gene_idx]
    if sp.issparse(X):
        X = X.toarray()
    X = np.asarray(X, dtype=float)

    if params.color_scale == "log":
        X = np.log1p(X)
    elif params.color_scale == "sqrt":
        X = np.sqrt(X)

    expr_df = pd.DataFrame(X, columns=genes)
    corr_df = expr_df.corr(method=params.correlation_method)

    n = len(genes)
    figsize = params.figure_size or (max(8, n), max(8, n))

    g = sns.clustermap(
        corr_df,
        cmap=params.colormap,
        center=0,
        annot=True,
        fmt=".2f",
        square=True,
        figsize=figsize,
        dendrogram_ratio=0.15,
        cbar_pos=(0.02, 0.8, 0.03, 0.15),
    )
    title = params.title or f"Gene Correlation ({params.correlation_method.title()})"
    g.fig.suptitle(title, y=1.02, fontsize=14)
    return g.fig
