"""RNA velocity visualization for SpatialClaw.

Sub-types:
- ``stream``       — velocity embedding stream plot (default)
- ``phase``        — spliced/unspliced phase portrait
- ``proportions``  — pie chart of spliced/unspliced ratios
- ``heatmap``      — genes ordered by pseudotime
- ``paga``         — PAGA with velocity arrows

Requires ``scvelo``.  The ``paga`` sub-type only requires ``scanpy``.

Adapted from ChatSpatial visualization/velocity.py — removed async/ToolContext.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import matplotlib.pyplot as plt
import scanpy as sc

from .core import VizParams, get_categorical_columns, infer_basis, resolve_figure_size

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_velocity(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    subtype: Optional[str] = None,
    cluster_key: Optional[str] = None,
) -> plt.Figure:
    """RNA velocity visualization.

    Args:
        adata: AnnData object with computed velocity (``velocity_graph`` in uns).
        params: :class:`~omicsclaw.spatial.viz.params.VizParams`.
        subtype: ``"stream"`` (default), ``"phase"``, ``"proportions"``,
                 ``"heatmap"``, or ``"paga"``.
        cluster_key: obs column for cluster labels / colouring.

    Returns:
        :class:`matplotlib.figure.Figure`

    Raises:
        ImportError: If ``scvelo`` is not installed (except ``paga`` subtype).
        ValueError: If required data (e.g., velocity graph, layers) is absent.
    """
    if params is None:
        params = VizParams()
    if subtype:
        params.subtype = subtype
    if cluster_key:
        params.cluster_key = cluster_key

    st = params.subtype or "stream"
    logger.info("Creating RNA velocity visualization: %s", st)

    dispatch = {
        "stream": _plot_stream,
        "phase": _plot_phase,
        "proportions": _plot_proportions,
        "heatmap": _plot_heatmap,
        "paga": _plot_paga,
    }
    if st not in dispatch:
        raise ValueError(
            f"Unknown velocity subtype '{st}'. "
            "Choose: 'stream', 'phase', 'proportions', 'heatmap', 'paga'."
        )
    return dispatch[st](adata, params)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_scvelo():
    try:
        import scvelo as scv
        return scv
    except ImportError:
        raise ImportError(
            "scvelo is required for RNA velocity visualization. "
            "Install with: pip install scvelo"
        )


def _auto_cluster_key(adata: Any, params: VizParams) -> Optional[str]:
    if params.cluster_key and params.cluster_key in adata.obs.columns:
        return params.cluster_key
    cats = get_categorical_columns(adata)
    return cats[0] if cats else None


# ---------------------------------------------------------------------------
# Stream plot
# ---------------------------------------------------------------------------


def _plot_stream(adata: Any, params: VizParams) -> plt.Figure:
    """Velocity embedding stream plot."""
    scv = _require_scvelo()

    if "velocity_graph" not in adata.uns:
        raise ValueError(
            "velocity_graph not found. Run scv.tl.velocity_graph(adata) first."
        )

    basis = infer_basis(adata, preferred=params.basis) or "umap"
    feature = _auto_cluster_key(adata, params)

    figsize = params.figure_size or (10, 8)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    scv.pl.velocity_embedding_stream(
        adata, basis=basis, color=feature,
        ax=ax, show=False, alpha=params.alpha,
        legend_loc="right margin" if feature else None,
        frameon=params.show_axes, title="",
    )
    ax.set_title(
        params.title or f"RNA Velocity Stream ({basis})", fontsize=14
    )
    if basis == "spatial":
        ax.invert_yaxis()

    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Phase portrait
# ---------------------------------------------------------------------------


def _plot_phase(adata: Any, params: VizParams) -> plt.Figure:
    """Spliced/unspliced phase portrait for key genes."""
    scv = _require_scvelo()

    for layer in ("velocity", "Ms", "Mu"):
        if layer not in adata.layers:
            raise ValueError(
                f"Layer '{layer}' missing. Run scv.tl.velocity(adata) first."
            )

    feat = params.feature
    if feat:
        var_names = [feat] if isinstance(feat, str) else list(feat)
    else:
        if "velocity_genes" in adata.var.columns:
            var_names = list(adata.var_names[adata.var["velocity_genes"]][:4])
        else:
            var_names = list(adata.var_names[:4])

    valid = [g for g in var_names if g in adata.var_names]
    if not valid:
        raise ValueError(f"None of the requested genes found: {var_names}")

    basis = infer_basis(adata, preferred=params.basis, priority=["umap", "spatial"]) or "umap"
    figsize = resolve_figure_size(params, n_panels=len(valid), panel_width=4, panel_height=4)

    scv.pl.velocity(
        adata, var_names=valid, basis=basis,
        color=params.cluster_key or None,
        figsize=figsize, dpi=params.dpi, show=False,
        ncols=len(valid),
    )
    fig = plt.gcf()
    if params.title:
        fig.suptitle(params.title, fontsize=14, y=1.02)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Proportions pie chart
# ---------------------------------------------------------------------------


def _plot_proportions(adata: Any, params: VizParams) -> plt.Figure:
    """Spliced/unspliced proportion pie charts grouped by cluster."""
    scv = _require_scvelo()

    for layer in ("spliced", "unspliced"):
        if layer not in adata.layers:
            raise ValueError(
                f"Layer '{layer}' missing. "
                "Ensure the input AnnData was created with loom/STARsolo and "
                "contains spliced/unspliced counts."
            )

    cluster_key = _auto_cluster_key(adata, params)
    if not cluster_key:
        raise ValueError(
            "cluster_key required for proportions plot. "
            f"Available obs columns: {list(adata.obs.columns)[:10]}"
        )

    figsize = resolve_figure_size(params, "violin")
    scv.pl.proportions(
        adata, groupby=cluster_key,
        figsize=figsize, dpi=params.dpi, show=False,
    )
    fig = plt.gcf()
    if params.title:
        fig.suptitle(params.title, fontsize=14, y=1.02)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Velocity heatmap
# ---------------------------------------------------------------------------


def _plot_heatmap(adata: Any, params: VizParams) -> plt.Figure:
    """Gene expression heatmap ordered by pseudotime."""
    scv = _require_scvelo()

    time_cols = ["latent_time", "velocity_pseudotime", "dpt_pseudotime"]
    sortby = next((c for c in time_cols if c in adata.obs.columns), None)

    if sortby is None:
        if "velocity_graph" in adata.uns:
            logger.info("Computing velocity_pseudotime for heatmap ordering")
            scv.tl.velocity_pseudotime(adata)
            sortby = "velocity_pseudotime"
        else:
            raise ValueError(
                "No time ordering column found. Need one of: "
                f"{time_cols}. Run velocity or trajectory analysis first."
            )

    feat = params.feature
    if feat:
        var_names = [feat] if isinstance(feat, str) else list(feat)
        valid = [g for g in var_names if g in adata.var_names]
        if not valid:
            raise ValueError(f"None of the requested genes found: {var_names}")
    else:
        if "velocity_genes" in adata.var.columns:
            valid = list(adata.var_names[adata.var["velocity_genes"]][:50])
        elif "highly_variable" in adata.var.columns:
            valid = list(adata.var_names[adata.var["highly_variable"]][:50])
        else:
            valid = list(adata.var_names[:50])

    figsize = resolve_figure_size(params, "heatmap")
    scv.pl.heatmap(
        adata, var_names=valid, sortby=sortby,
        col_color=params.cluster_key,
        n_convolve=30, show=False, figsize=figsize,
    )
    fig = plt.gcf()
    fig.set_dpi(params.dpi)
    if params.title:
        fig.suptitle(params.title, fontsize=14, y=1.02)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# PAGA plot (only scanpy required)
# ---------------------------------------------------------------------------


def _plot_paga(adata: Any, params: VizParams) -> plt.Figure:
    """PAGA connectivity graph — requires only scanpy."""
    cluster_key = _auto_cluster_key(adata, params)
    if not cluster_key:
        raise ValueError(
            "cluster_key required for PAGA. "
            f"Available obs columns: {list(adata.obs.columns)[:10]}"
        )

    if (
        "paga" not in adata.uns
        or adata.uns.get("paga", {}).get("groups") != cluster_key
    ):
        logger.info("Computing PAGA for cluster_key='%s'", cluster_key)
        sc.tl.paga(adata, groups=cluster_key)

    figsize = params.figure_size or (10, 8)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)
    sc.pl.paga(
        adata, color=cluster_key,
        edge_width_scale=0.5, ax=ax, show=False,
        frameon=params.show_axes,
    )
    ax.set_title(params.title or f"PAGA — {cluster_key}", fontsize=14)
    plt.tight_layout()
    return fig
