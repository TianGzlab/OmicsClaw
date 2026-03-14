"""Cell type deconvolution visualization for SpatialClaw.

Sub-types:
- ``spatial_multi`` — multi-panel spatial maps per cell type (default)
- ``dominant``      — dominant cell type map (CARD style)
- ``diversity``     — Shannon entropy diversity map
- ``umap``          — UMAP coloured by cell type proportions

Adapted from ChatSpatial visualization/deconvolution.py — removed async/ToolContext.
Requires deconvolution results stored in ``adata.obsm['deconvolution_<method>']``.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import entropy

from .core import (
    VizParams,
    _require_spatial_coords,
    auto_spot_size,
    get_category_colors,
    plot_spatial_feature,
    setup_multi_panel_figure,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared data container
# ---------------------------------------------------------------------------


class DeconvData(NamedTuple):
    proportions: pd.DataFrame
    method: str
    cell_types: list[str]
    proportions_key: str


# ---------------------------------------------------------------------------
# Data retrieval
# ---------------------------------------------------------------------------


def _get_deconv_data(adata: Any, method: Optional[str]) -> DeconvData:
    """Retrieve deconvolution proportions from adata.obsm."""
    # Find available methods
    available = []
    for key in adata.obsm.keys():
        if key.startswith("deconvolution_"):
            m = key[len("deconvolution_"):]
            available.append(m)
    for key in adata.uns.keys():
        if key.startswith("deconvolution_") and key.endswith("_metadata"):
            m = key[len("deconvolution_"): -len("_metadata")]
            if m not in available:
                available.append(m)

    if not available:
        raise ValueError(
            "No deconvolution results found. "
            "Run spatial-deconv first."
        )

    if method is None:
        if len(available) > 1:
            raise ValueError(
                f"Multiple deconvolution results found: {available}. "
                "Specify method= to select one."
            )
        method = available[0]
    elif method not in available:
        raise ValueError(
            f"Deconvolution method '{method}' not found. Available: {available}"
        )

    proportions_key = f"deconvolution_{method}"
    if proportions_key not in adata.obsm:
        raise ValueError(f"Key '{proportions_key}' not found in adata.obsm")

    # Cell type names
    ct_key = f"{proportions_key}_cell_types"
    if ct_key in adata.uns:
        cell_types = list(adata.uns[ct_key])
    else:
        n = adata.obsm[proportions_key].shape[1]
        cell_types = [f"CellType_{i}" for i in range(n)]
        logger.warning("Cell type names not found; using generic labels.")

    proportions = pd.DataFrame(
        adata.obsm[proportions_key],
        index=adata.obs_names,
        columns=cell_types,
    )
    return DeconvData(proportions, method, cell_types, proportions_key)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_deconvolution(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    subtype: Optional[str] = None,
    method: Optional[str] = None,
) -> plt.Figure:
    """Cell type deconvolution visualization.

    Args:
        adata: AnnData object with deconvolution results in ``obsm``.
        params: :class:`~omicsclaw.spatial.viz.params.VizParams`.
        subtype: ``"spatial_multi"`` (default), ``"dominant"``,
                 ``"diversity"``, or ``"umap"``.
        method: Deconvolution method key (e.g. ``"cell2location"``).
                Auto-detected if only one result exists.

    Returns:
        :class:`matplotlib.figure.Figure`
    """
    if params is None:
        params = VizParams()
    if subtype:
        params.subtype = subtype

    st = params.subtype or "spatial_multi"
    logger.info("Creating deconvolution visualization: %s", st)

    dispatch = {
        "spatial_multi": _plot_spatial_multi,
        "dominant": _plot_dominant,
        "diversity": _plot_diversity,
        "umap": _plot_umap_proportions,
    }
    # aliases
    dispatch["dominant_type"] = dispatch["dominant"]
    dispatch["pie"] = dispatch["spatial_multi"]

    if st not in dispatch:
        raise ValueError(
            f"Unknown deconvolution subtype '{st}'. "
            "Choose: 'spatial_multi', 'dominant', 'diversity', 'umap'."
        )
    data = _get_deconv_data(adata, method)
    return dispatch[st](adata, params, data)


# ---------------------------------------------------------------------------
# Sub-types
# ---------------------------------------------------------------------------


def _plot_spatial_multi(adata: Any, params: VizParams, data: DeconvData) -> plt.Figure:
    """Multi-panel spatial map — one panel per cell type."""
    n_types = len(data.cell_types)
    max_types = min(n_types, 12)
    cell_types = data.cell_types[:max_types]

    fig, axes = setup_multi_panel_figure(
        n_panels=max_types,
        params=params,
        default_title=f"Cell Type Proportions ({data.method})",
    )

    _TEMP = "_deconv_viz_tmp"
    for i, ct in enumerate(cell_types):
        ax = axes[i]
        adata.obs[_TEMP] = data.proportions[ct].values
        plot_spatial_feature(
            adata, ax=ax, feature=_TEMP,
            params=VizParams(
                colormap=params.colormap or "viridis",
                spot_size=params.spot_size,
                alpha=params.alpha,
                show_colorbar=True,
                vmin=0, vmax=1,
            ),
            title=ct,
        )
        ax.invert_yaxis()

    if _TEMP in adata.obs:
        del adata.obs[_TEMP]

    plt.tight_layout()
    return fig


def _plot_dominant(adata: Any, params: VizParams, data: DeconvData) -> plt.Figure:
    """Dominant cell type at each spatial spot (CARD style)."""
    dominant_idx = data.proportions.values.argmax(axis=1)
    dominant_types = data.proportions.columns[dominant_idx].values

    coords = _require_spatial_coords(adata)
    spot_size = auto_spot_size(adata, params.spot_size, basis="spatial")

    unique_cats = np.unique(dominant_types)
    n_cats = len(unique_cats)
    colors = get_category_colors(n_cats)
    color_map = {cat: colors[i] for i, cat in enumerate(unique_cats)}

    figsize = params.figure_size or (10, 8)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    for cat in unique_cats:
        mask = dominant_types == cat
        ax.scatter(
            coords[mask, 0], coords[mask, 1],
            c=[color_map[cat]], s=spot_size, alpha=1.0,
            label=cat, edgecolors="none",
        )

    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_title(params.title or f"Dominant Cell Type ({data.method})", fontsize=14)
    ax.set_xlabel("Spatial X")
    ax.set_ylabel("Spatial Y")
    ncol = 2 if n_cats > 15 else 1
    ax.legend(
        bbox_to_anchor=(1.05, 1), loc="upper left",
        ncol=ncol, fontsize=8, markerscale=0.8,
    )
    plt.tight_layout()
    return fig


def _plot_diversity(adata: Any, params: VizParams, data: DeconvData) -> plt.Figure:
    """Shannon entropy diversity map."""
    eps = 1e-10
    proportions_safe = data.proportions.values + eps
    spot_entropy = entropy(proportions_safe.T, base=2)
    max_entropy = np.log2(data.proportions.shape[1])
    norm_entropy = spot_entropy / max_entropy

    coords = _require_spatial_coords(adata)
    spot_size = auto_spot_size(adata, params.spot_size, basis="spatial")

    figsize = params.figure_size or (10, 8)
    fig, ax = plt.subplots(figsize=figsize, dpi=params.dpi)

    scatter = ax.scatter(
        coords[:, 0], coords[:, 1],
        c=norm_entropy, cmap=params.colormap or "viridis",
        s=spot_size, alpha=1.0, edgecolors="none",
        vmin=0, vmax=1,
    )
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("Cell Type Diversity (Shannon Entropy)", rotation=270, labelpad=20)

    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_title(
        params.title or f"Cell Type Diversity ({data.method})\n"
        "(0 = homogeneous, 1 = maximally diverse)",
        fontsize=13,
    )
    ax.set_xlabel("Spatial X")
    ax.set_ylabel("Spatial Y")
    plt.tight_layout()
    return fig


def _plot_umap_proportions(adata: Any, params: VizParams, data: DeconvData) -> plt.Figure:
    """UMAP coloured by cell type proportions (one panel per type)."""
    if "X_umap" not in adata.obsm:
        raise ValueError(
            "UMAP embedding not found. Run sc.tl.umap(adata) first."
        )

    n_types = min(len(data.cell_types), 9)
    cell_types = data.cell_types[:n_types]
    umap = np.asarray(adata.obsm["X_umap"])

    fig, axes = setup_multi_panel_figure(
        n_panels=n_types,
        params=params,
        default_title=f"Cell Type Proportions on UMAP ({data.method})",
    )

    for i, ct in enumerate(cell_types):
        ax = axes[i]
        values = data.proportions[ct].values
        sc = ax.scatter(
            umap[:, 0], umap[:, 1],
            c=values, cmap=params.colormap or "viridis",
            s=params.spot_size or 10, alpha=params.alpha,
            vmin=0, vmax=1,
        )
        if params.show_colorbar:
            plt.colorbar(sc, ax=ax)
        ax.set_title(ct, fontsize=10)
        ax.set_xlabel("UMAP 1", fontsize=9)
        ax.set_ylabel("UMAP 2", fontsize=9)

    plt.tight_layout()
    return fig
