"""Trajectory / pseudotime visualization for SpatialClaw.

Sub-types:
- ``pseudotime``  — pseudotime on embedding ± velocity stream (default)
- ``circular``    — CellRank circular fate-probability projection
- ``fate_map``    — CellRank aggregated fate probabilities (bar mode)
- ``gene_trends`` — CellRank GAM gene trends along lineages
- ``fate_heatmap``— CellRank smoothed heatmap ordered by pseudotime

Requires ``cellrank`` for everything except ``pseudotime``.
``pseudotime`` + velocity stream panel requires ``scvelo`` if velocity is present.

Adapted from ChatSpatial visualization/trajectory.py — removed async/ToolContext.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import matplotlib
import matplotlib.pyplot as plt
import scanpy as sc

from .core import VizParams, get_categorical_columns, infer_basis, resolve_figure_size

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_trajectory(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    subtype: Optional[str] = None,
    cluster_key: Optional[str] = None,
) -> plt.Figure:
    """Trajectory / pseudotime visualization.

    Args:
        adata: AnnData object with trajectory/pseudotime results.
        params: :class:`~omicsclaw.spatial.viz.params.VizParams`.
        subtype: ``"pseudotime"`` (default), ``"circular"``, ``"fate_map"``,
                 ``"gene_trends"``, or ``"fate_heatmap"``.
        cluster_key: obs column for cluster labels.

    Returns:
        :class:`matplotlib.figure.Figure`
    """
    if params is None:
        params = VizParams()
    if subtype:
        params.subtype = subtype
    if cluster_key:
        params.cluster_key = cluster_key

    st = params.subtype or "pseudotime"
    logger.info("Creating trajectory visualization: %s", st)

    dispatch = {
        "pseudotime": _plot_pseudotime,
        "circular": _plot_circular,
        "fate_map": _plot_fate_map,
        "gene_trends": _plot_gene_trends,
        "fate_heatmap": _plot_fate_heatmap,
    }
    if st not in dispatch:
        raise ValueError(
            f"Unknown trajectory subtype '{st}'. "
            "Choose: 'pseudotime', 'circular', 'fate_map', 'gene_trends', 'fate_heatmap'."
        )
    return dispatch[st](adata, params)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_cellrank():
    try:
        import cellrank as cr
        return cr
    except ImportError:
        raise ImportError(
            "cellrank is required for this trajectory sub-type. "
            "Install with: pip install cellrank"
        )


def _find_pseudotime_key(adata: Any, params: VizParams) -> str:
    feat = params.feature
    if feat:
        key = feat[0] if isinstance(feat, list) else feat
        if key in adata.obs.columns:
            return key
    candidates = [k for k in adata.obs.columns if "pseudotime" in k.lower()]
    if candidates:
        return candidates[0]
    raise ValueError(
        "No pseudotime column found. Run trajectory analysis first or "
        "set params.feature='<pseudotime_column_name>'."
    )


def _auto_cluster_key(adata: Any, params: VizParams) -> Optional[str]:
    if params.cluster_key and params.cluster_key in adata.obs.columns:
        return params.cluster_key
    cats = get_categorical_columns(adata)
    return cats[0] if cats else None


# ---------------------------------------------------------------------------
# Pseudotime embedding
# ---------------------------------------------------------------------------


def _plot_pseudotime(adata: Any, params: VizParams) -> plt.Figure:
    """Pseudotime coloured embedding with optional velocity stream panel."""
    pseudotime_key = _find_pseudotime_key(adata, params)
    # For pseudotime embedding, prefer UMAP/tSNE over spatial coordinates.
    # infer_basis default priority is spatial-first, which is wrong here.
    basis = infer_basis(
        adata,
        preferred=params.basis,
        priority=["umap", "tsne", "pca", "spatial"],
    ) or "umap"
    has_velocity = "velocity_graph" in adata.uns

    n_panels = 2 if has_velocity else 1
    figsize = resolve_figure_size(params, n_panels=n_panels, panel_width=6, panel_height=5)
    fig, axes = plt.subplots(1, n_panels, figsize=figsize, dpi=params.dpi)
    axes_list = [axes] if n_panels == 1 else list(axes)

    from matplotlib import colormaps
    from mpl_toolkits.axes_grid1 import make_axes_locatable

    cmap = colormaps.get_cmap(params.colormap)

    ax1 = axes_list[0]
    sc.pl.embedding(
        adata, basis=basis, color=pseudotime_key,
        cmap=params.colormap, ax=ax1, show=False,
        frameon=params.show_axes, alpha=params.alpha,
        colorbar_loc=None,
        title=f"Pseudotime ({pseudotime_key})",
    )
    if basis == "spatial":
        ax1.invert_yaxis()
    if params.show_colorbar:
        divider = make_axes_locatable(ax1)
        cax = divider.append_axes("right", size="4%", pad=0.05)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
        sm.set_array([])
        fig.colorbar(sm, cax=cax)

    if has_velocity and n_panels > 1:
        try:
            import scvelo as scv
        except ImportError:
            logger.warning("scvelo not available; skipping velocity stream panel")
        else:
            ax2 = axes_list[1]
            scv.pl.velocity_embedding_stream(
                adata, basis=basis, color=pseudotime_key,
                color_map=params.colormap,
                ax=ax2, show=False, alpha=params.alpha,
                frameon=params.show_axes,
                title="RNA Velocity Stream", colorbar=False,
            )
            if basis == "spatial":
                ax2.invert_yaxis()
            if params.show_colorbar:
                divider2 = make_axes_locatable(ax2)
                cax2 = divider2.append_axes("right", size="4%", pad=0.05)
                sm2 = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
                sm2.set_array([])
                fig.colorbar(sm2, cax=cax2)

    if params.title:
        fig.suptitle(params.title, fontsize=14, y=1.02)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# CellRank circular projection
# ---------------------------------------------------------------------------


def _plot_circular(adata: Any, params: VizParams) -> plt.Figure:
    """CellRank circular fate-probability projection."""
    cr = _require_cellrank()

    fate_key = next(
        (k for k in ("lineages_fwd", "to_terminal_states") if k in adata.obsm),
        None,
    )
    if not fate_key:
        raise ValueError(
            "CellRank fate probabilities not found. Run trajectory analysis first."
        )

    keys = None
    if params.cluster_key and params.cluster_key in adata.obs.columns:
        keys = [params.cluster_key]
    else:
        cats = get_categorical_columns(adata, limit=3)
        if cats:
            keys = cats

    figsize = resolve_figure_size(params, "trajectory")

    prev_backend = matplotlib.get_backend()
    matplotlib.use("Agg")
    try:
        cr.pl.circular_projection(adata, keys=keys, figsize=figsize, dpi=params.dpi)
        fig = plt.gcf()
    finally:
        matplotlib.use(prev_backend)

    if params.title:
        fig.suptitle(params.title, fontsize=14, y=1.02)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# CellRank fate map
# ---------------------------------------------------------------------------


def _plot_fate_map(adata: Any, params: VizParams) -> plt.Figure:
    """CellRank aggregated fate probabilities (bar mode)."""
    cr = _require_cellrank()

    fate_key = next(
        (k for k in ("lineages_fwd", "to_terminal_states") if k in adata.obsm),
        None,
    )
    if not fate_key:
        raise ValueError(
            "CellRank fate probabilities not found. Run trajectory analysis first."
        )

    cluster_key = _auto_cluster_key(adata, params)
    if not cluster_key:
        raise ValueError("cluster_key required for fate map.")

    figsize = resolve_figure_size(params, "violin")

    prev_backend = matplotlib.get_backend()
    matplotlib.use("Agg")
    try:
        cr.pl.aggregate_fate_probabilities(
            adata, cluster_key=cluster_key, mode="bar",
            figsize=figsize, dpi=params.dpi,
        )
        fig = plt.gcf()
    finally:
        matplotlib.use(prev_backend)

    if params.title:
        fig.suptitle(params.title, fontsize=14, y=1.02)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# CellRank gene trends
# ---------------------------------------------------------------------------


def _plot_gene_trends(adata: Any, params: VizParams) -> plt.Figure:
    """CellRank GAM gene expression trends along lineages."""
    cr = _require_cellrank()

    feat = params.feature
    if feat:
        genes = [feat] if isinstance(feat, str) else list(feat)
    else:
        if "highly_variable" in adata.var.columns:
            genes = list(adata.var_names[adata.var["highly_variable"]][:5])
        else:
            genes = list(adata.var_names[:5])

    valid = [g for g in genes if g in adata.var_names]
    if not valid:
        raise ValueError(f"None of the requested genes found: {genes}")

    time_key = next(
        (c for c in ("pseudotime", "latent_time", "velocity_pseudotime", "dpt_pseudotime")
         if c in adata.obs.columns),
        None,
    )
    if not time_key:
        raise ValueError("No pseudotime column found for gene trends.")

    try:
        from cellrank.models import GAM
        model = GAM(adata)
    except Exception as exc:
        raise ValueError(f"Could not initialise CellRank GAM model: {exc}")

    prev_backend = matplotlib.get_backend()
    matplotlib.use("Agg")
    try:
        cr.pl.gene_trends(adata, model=model, genes=valid, time_key=time_key)
        fig = plt.gcf()
    finally:
        matplotlib.use(prev_backend)

    if params.title:
        fig.suptitle(params.title, fontsize=14, y=1.02)
    return fig


# ---------------------------------------------------------------------------
# CellRank fate heatmap
# ---------------------------------------------------------------------------


def _plot_fate_heatmap(adata: Any, params: VizParams) -> plt.Figure:
    """CellRank smoothed expression heatmap by pseudotime."""
    cr = _require_cellrank()

    feat = params.feature
    if feat:
        genes = [feat] if isinstance(feat, str) else list(feat)
    else:
        if "highly_variable" in adata.var.columns:
            genes = list(adata.var_names[adata.var["highly_variable"]][:20])
        else:
            genes = list(adata.var_names[:20])

    valid = [g for g in genes if g in adata.var_names]
    if not valid:
        raise ValueError(f"None of the requested genes found: {genes}")

    time_key = next(
        (c for c in ("pseudotime", "latent_time", "velocity_pseudotime", "dpt_pseudotime")
         if c in adata.obs.columns),
        None,
    )
    if not time_key:
        raise ValueError("No pseudotime column found for fate heatmap.")

    try:
        from cellrank.models import GAM
        model = GAM(adata)
    except Exception as exc:
        raise ValueError(f"Could not initialise CellRank GAM model: {exc}")

    prev_backend = matplotlib.get_backend()
    matplotlib.use("Agg")
    try:
        cr.pl.heatmap(adata, model=model, genes=valid, time_key=time_key)
        fig = plt.gcf()
    finally:
        matplotlib.use(prev_backend)

    if params.title:
        fig.suptitle(params.title, fontsize=14, y=1.02)
    return fig
