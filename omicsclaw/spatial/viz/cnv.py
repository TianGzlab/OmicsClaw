"""Copy number variation (CNV) visualization for SpatialClaw.

Sub-types:
- ``heatmap`` — chromosome CNV heatmap (default, requires infercnvpy)
- ``spatial`` — spatial map of CNV score on tissue

Adapted from ChatSpatial visualization/cnv.py — removed async/ToolContext.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np

from .core import (
    VizParams,
    _require_spatial_coords,
    auto_spot_size,
    plot_spatial_feature,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_cnv(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    subtype: Optional[str] = None,
    cluster_key: Optional[str] = None,
) -> plt.Figure:
    """CNV visualization.

    Args:
        adata: AnnData object with CNV results.  For ``heatmap``, expects
               either infercnvpy output (``adata.obsm['X_cnv']``) or Numbat
               output (``adata.obs`` columns with CNV state probabilities).
               For ``spatial``, expects a numeric score in ``adata.obs``
               (e.g. ``'cnv_score'``, ``'tumor_score'``).
        params: :class:`~omicsclaw.spatial.viz.params.VizParams`.
        subtype: ``"heatmap"`` (default) or ``"spatial"``.
        cluster_key: obs column for row colours in heatmap.

    Returns:
        :class:`matplotlib.figure.Figure`
    """
    if params is None:
        params = VizParams()
    if subtype:
        params.subtype = subtype
    if cluster_key:
        params.cluster_key = cluster_key

    st = params.subtype or "heatmap"
    logger.info("Creating CNV visualization: %s", st)

    dispatch = {
        "heatmap": _plot_heatmap,
        "spatial": _plot_spatial,
    }
    if st not in dispatch:
        raise ValueError(
            f"Unknown CNV subtype '{st}'. Choose: 'heatmap' or 'spatial'."
        )
    return dispatch[st](adata, params)


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------


def _plot_heatmap(adata: Any, params: VizParams) -> plt.Figure:
    """Chromosome CNV heatmap.

    Tries infercnvpy first, then falls back to a seaborn heatmap of
    ``adata.obsm['X_cnv']``.
    """
    # Try infercnvpy native plot
    try:
        import cnv as cnvpy
        cluster_key = params.cluster_key
        if not cluster_key:
            for cand in ("leiden", "louvain", "cluster", "cell_type", "celltype"):
                if cand in adata.obs.columns:
                    cluster_key = cand
                    break
        if "X_cnv" in adata.obsm or "cnv" in adata.uns:
            cnvpy.pl.chromosome_heatmap(
                adata,
                groupby=cluster_key,
                dendrogram=True,
                show=False,
            )
            fig = plt.gcf()
            if params.title:
                fig.suptitle(params.title, y=1.02, fontsize=14)
            return fig
    except (ImportError, AttributeError):
        pass

    # Fallback: manual heatmap from X_cnv
    if "X_cnv" not in adata.obsm:
        raise ValueError(
            "CNV results not found. Expected adata.obsm['X_cnv']. "
            "Run spatial-cnv first."
        )

    return _manual_cnv_heatmap(adata, params)


def _manual_cnv_heatmap(adata: Any, params: VizParams) -> plt.Figure:
    """Build a CNV heatmap from adata.obsm['X_cnv'] using seaborn."""
    import seaborn as sns

    cnv_matrix = np.asarray(adata.obsm["X_cnv"])

    # Aggregate by cluster if available
    cluster_key = params.cluster_key
    if cluster_key and cluster_key in adata.obs.columns:
        clusters = adata.obs[cluster_key].values
        unique_clusters = np.unique(clusters)
        aggregated = np.array([
            cnv_matrix[clusters == cl].mean(axis=0)
            for cl in unique_clusters
        ])
        row_labels = list(unique_clusters)
    else:
        # Subsample for large datasets
        max_cells = 500
        if len(adata) > max_cells:
            idx = np.random.choice(len(adata), max_cells, replace=False)
            aggregated = cnv_matrix[idx]
        else:
            aggregated = cnv_matrix
        row_labels = None

    n_rows, n_cols = aggregated.shape
    figsize = params.figure_size or (max(12, n_cols // 30), max(5, n_rows * 0.4 + 2))

    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)
    im = ax.imshow(
        aggregated, cmap="RdBu_r", aspect="auto",
        vmin=-1, vmax=1, interpolation="nearest",
    )
    plt.colorbar(im, ax=ax, label="CNV State", fraction=0.02, pad=0.02)

    if row_labels is not None:
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=9)
        ax.set_ylabel("Cell cluster")
    else:
        ax.set_ylabel("Cell (subsampled)")

    ax.set_xlabel("Genome position (bins)")
    ax.set_title(params.title or "Copy Number Variation Heatmap", fontsize=13, fontweight="bold")
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Spatial CNV map
# ---------------------------------------------------------------------------


def _plot_spatial(adata: Any, params: VizParams) -> plt.Figure:
    """Spatial map of CNV score on tissue."""
    # Find a numeric CNV score in obs
    score_candidates = [
        c for c in adata.obs.columns
        if any(tok in c.lower() for tok in ("cnv", "tumor", "malignant", "aneuploid"))
        and adata.obs[c].dtype.kind in ("f", "i")
    ]
    if not score_candidates:
        # Try to derive from X_cnv mean
        if "X_cnv" in adata.obsm:
            adata.obs["_cnv_score"] = np.asarray(adata.obsm["X_cnv"]).mean(axis=1)
            score_candidates = ["_cnv_score"]
        else:
            raise ValueError(
                "No CNV score column found in adata.obs and no X_cnv in obsm. "
                "Run spatial-cnv first."
            )

    score_col = score_candidates[0]
    logger.info("Plotting CNV spatial map using column: %s", score_col)

    coords = _require_spatial_coords(adata)
    spot_size = auto_spot_size(adata, params.spot_size, basis="spatial")

    figsize = params.figure_size or (10, 8)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    values = adata.obs[score_col].values.astype(float)
    sc = ax.scatter(
        coords[:, 0], coords[:, 1],
        c=values, cmap=params.colormap or "RdBu_r",
        s=spot_size, alpha=params.alpha,
    )
    plt.colorbar(sc, ax=ax, label=score_col)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_title(params.title or f"CNV Score Spatial Map ({score_col})", fontsize=13)
    ax.set_xlabel("Spatial X")
    ax.set_ylabel("Spatial Y")

    # Cleanup temp column
    if "_cnv_score" in adata.obs.columns:
        del adata.obs["_cnv_score"]

    plt.tight_layout()
    return fig
