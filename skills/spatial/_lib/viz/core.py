"""Core visualization utilities shared across all SpatialClaw viz modules.

Adapted from ChatSpatial's visualization/core.py — removed ToolContext,
VisualizationParameters, and async in favour of VizParams + plain Python.
"""

from __future__ import annotations

import logging
import os
import warnings
from typing import Any, Optional

import matplotlib

os.environ.setdefault("MPLBACKEND", "Agg")
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from mpl_toolkits.axes_grid1 import make_axes_locatable

from .params import VizParams

logger = logging.getLogger(__name__)

plt.ioff()

# ---------------------------------------------------------------------------
# Figure size defaults (width, height) in inches
# ---------------------------------------------------------------------------
FIGURE_DEFAULTS: dict[str, tuple[int, int]] = {
    "spatial": (10, 8),
    "umap": (10, 8),
    "heatmap": (12, 10),
    "violin": (12, 6),
    "dotplot": (10, 8),
    "trajectory": (10, 10),
    "gene_trends": (12, 6),
    "velocity": (10, 8),
    "deconvolution": (10, 8),
    "cell_communication": (10, 10),
    "enrichment": (6, 8),
    "cnv": (12, 8),
    "integration": (16, 12),
    "default": (10, 8),
}

# ---------------------------------------------------------------------------
# Figure creation helpers
# ---------------------------------------------------------------------------


def resolve_figure_size(
    params: VizParams,
    plot_type: str = "default",
    n_panels: Optional[int] = None,
    panel_width: float = 5.0,
    panel_height: float = 4.0,
) -> tuple[float, float]:
    """Return figure size, respecting user override then smart defaults."""
    if params.figure_size:
        return params.figure_size
    if n_panels is not None and n_panels > 1:
        n_cols = min(3, n_panels)
        n_rows = (n_panels + n_cols - 1) // n_cols
        return (min(panel_width * n_cols, 15), min(panel_height * n_rows, 16))
    return FIGURE_DEFAULTS.get(plot_type, FIGURE_DEFAULTS["default"])


def create_figure(
    figsize: tuple[float, float] = (10, 8),
    dpi: int = 200,
) -> tuple[plt.Figure, plt.Axes]:
    """Create a single-panel matplotlib figure."""
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    return fig, ax


def setup_multi_panel_figure(
    n_panels: int,
    params: VizParams,
    default_title: str = "",
    use_tight_layout: bool = False,
) -> tuple[plt.Figure, np.ndarray]:
    """Create a multi-panel figure with auto-computed grid layout.

    Returns (fig, axes_flat) where axes_flat is a 1-D flattened array.
    Unused axes beyond n_panels are hidden automatically.
    """
    if params.panel_layout:
        n_rows, n_cols = params.panel_layout
    else:
        n_cols = min(3, n_panels)
        n_rows = (n_panels + n_cols - 1) // n_cols

    figsize = params.figure_size or (min(5 * n_cols, 15), min(4 * n_rows, 16))

    gridspec_kw = (
        {}
        if use_tight_layout
        else {"wspace": params.subplot_wspace, "hspace": params.subplot_hspace}
    )

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=figsize,
        dpi=params.dpi,
        squeeze=False,
        gridspec_kw=gridspec_kw if gridspec_kw else None,
    )
    axes = axes.flatten()

    title = params.title or default_title
    if title:
        fig.suptitle(title, fontsize=16, y=1.02)

    for i in range(n_panels, len(axes)):
        axes[i].axis("off")

    return fig, axes


def safe_tight_layout(fig: Optional[plt.Figure] = None, **kwargs: Any) -> None:
    """Call tight_layout while suppressing known matplotlib axis-compatibility warnings."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*Axes that are not compatible with tight_layout.*",
            category=UserWarning,
        )
        if fig is not None:
            fig.tight_layout(**kwargs)
        else:
            plt.tight_layout(**kwargs)


def add_colorbar(
    fig: plt.Figure,
    ax: plt.Axes,
    mappable: Any,
    params: VizParams,
    label: str = "",
) -> None:
    """Attach a consistent colorbar to an axis."""
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size=params.colorbar_size, pad=params.colorbar_pad)
    cbar = fig.colorbar(mappable, cax=cax)
    if label:
        cbar.set_label(label, fontsize=10)


# ---------------------------------------------------------------------------
# Colormap utilities
# ---------------------------------------------------------------------------

_CATEGORICAL_CMAPS = {10: "tab10", 20: "tab20", 40: "tab20b"}

_CATEGORICAL_PALETTE_NAMES = {
    "tab10", "tab20", "tab20b", "tab20c",
    "Set1", "Set2", "Set3", "Paired", "Accent", "Dark2", "Pastel1", "Pastel2",
}


def get_categorical_cmap(n_categories: int, user_cmap: Optional[str] = None) -> str:
    """Select the best categorical colormap for the given number of categories."""
    if user_cmap and user_cmap in _CATEGORICAL_PALETTE_NAMES:
        return user_cmap
    for threshold, cmap in sorted(_CATEGORICAL_CMAPS.items()):
        if n_categories <= threshold:
            return cmap
    return "tab20"


def get_category_colors(
    n_categories: int,
    cmap_name: Optional[str] = None,
) -> list[Any]:
    """Return a list of *n_categories* distinct colours."""
    if cmap_name is None:
        cmap_name = get_categorical_cmap(n_categories)
    if cmap_name in ["tab10", "tab20", "Set1", "Set2", "Set3", "Paired", "husl"]:
        return list(sns.color_palette(cmap_name, n_colors=n_categories))
    cmap = plt.get_cmap(cmap_name)
    return [cmap(i / max(n_categories - 1, 1)) for i in range(n_categories)]


def get_colormap(name: str, n_colors: Optional[int] = None) -> Any:
    """Return a colormap or a list of colours for categorical data."""
    if n_colors:
        return get_category_colors(n_colors, name)
    if name in ["tab10", "tab20", "Set1", "Set2", "Set3", "Paired", "husl"]:
        return sns.color_palette(name)
    return plt.get_cmap(name)


def get_diverging_colormap() -> str:
    """Return ``'RdBu_r'`` for symmetric / diverging data."""
    return "RdBu_r"


# ---------------------------------------------------------------------------
# Spatial-plot utilities
# ---------------------------------------------------------------------------


def auto_spot_size(
    adata: Any,
    user_spot_size: Optional[float] = None,
    basis: str = "spatial",
) -> float:
    """Calculate a sensible spot/point size.

    Priority:
    1. *user_spot_size* if provided.
    2. For spatial basis: derived from Visium scalefactors when present.
    3. Adaptive formula: ``clamp(120000 / n_obs, 5, 200)``.
    """
    if user_spot_size is not None:
        return float(user_spot_size)

    if basis == "spatial" and "spatial" in adata.uns:
        spatial_data = adata.uns["spatial"]
        if isinstance(spatial_data, dict) and spatial_data:
            lib_data = next(iter(spatial_data.values()))
            if isinstance(lib_data, dict) and "scalefactors" in lib_data:
                sf = lib_data["scalefactors"]
                spot_diam = sf.get("spot_diameter_fullres")
                if spot_diam and spot_diam > 0:
                    scale = sf.get("tissue_hires_scalef", sf.get("tissue_lowres_scalef", 1.0))
                    return max((spot_diam * scale * 0.5) ** 2, 5.0)

    n_cells = adata.n_obs
    return float(max(min(120000 / n_cells, 200.0), 5.0))


def _get_gene_expression(adata: Any, gene: str) -> np.ndarray:
    """Extract per-cell expression for *gene* as a 1-D float array."""
    idx = adata.var_names.get_loc(gene)
    x = adata.X[:, idx]
    if hasattr(x, "toarray"):
        x = x.toarray().ravel()
    else:
        x = np.asarray(x).ravel()
    return x.astype(float)


def _require_spatial_coords(adata: Any, spatial_key: str = "spatial") -> np.ndarray:
    """Return spatial coordinate array or raise ValueError."""
    if spatial_key not in adata.obsm:
        raise ValueError(
            f"Spatial coordinates not found in adata.obsm['{spatial_key}']. "
            "Run sq.pl before visualising or provide a pre-processed AnnData."
        )
    return np.asarray(adata.obsm[spatial_key])


def plot_spatial_feature(
    adata: Any,
    ax: plt.Axes,
    feature: Optional[str] = None,
    values: Optional[np.ndarray] = None,
    params: Optional[VizParams] = None,
    spatial_key: str = "spatial",
    show_colorbar: bool = True,
    title: Optional[str] = None,
) -> Optional[Any]:
    """Plot a single feature on spatial coordinates.

    Returns the scatter ``PathCollection`` (useful for colorbar), or ``None``
    for categorical data.
    """
    if params is None:
        params = VizParams()

    spot_size = auto_spot_size(adata, params.spot_size, basis=spatial_key)
    coords = _require_spatial_coords(adata, spatial_key)

    # Resolve values --------------------------------------------------------
    if values is not None:
        plot_values = np.asarray(values)
        is_categorical = pd.api.types.is_categorical_dtype(values)
    elif feature is not None:
        if feature in adata.var_names:
            plot_values = _get_gene_expression(adata, feature)
            is_categorical = False
        elif feature in adata.obs.columns:
            col = adata.obs[feature]
            plot_values = col.values
            is_categorical = pd.api.types.is_categorical_dtype(col) or col.dtype == object
        else:
            raise ValueError(f"Feature '{feature}' not found in var_names or obs")
    else:
        raise ValueError("Either 'feature' or 'values' must be provided")

    # Draw ------------------------------------------------------------------
    if is_categorical:
        categories = (
            plot_values.categories
            if hasattr(plot_values, "categories")
            else np.unique(plot_values)
        )
        n_cats = len(categories)
        colors = get_colormap(params.colormap, n_colors=n_cats)
        cat_to_idx = {cat: i for i, cat in enumerate(categories)}
        point_colors = [colors[cat_to_idx[v]] for v in plot_values]

        ax.scatter(
            coords[:, 0], coords[:, 1],
            c=point_colors, s=spot_size, alpha=params.alpha,
        )
        if params.show_legend:
            handles = [
                plt.Line2D([0], [0], marker="o", color="w",
                           markerfacecolor=colors[i], markersize=8)
                for i in range(n_cats)
            ]
            ax.legend(handles, list(categories),
                      loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8)
        mappable = None
    else:
        cmap = get_colormap(params.colormap)
        scatter = ax.scatter(
            coords[:, 0], coords[:, 1],
            c=plot_values, cmap=cmap,
            s=spot_size, alpha=params.alpha,
            vmin=params.vmin, vmax=params.vmax,
        )
        if show_colorbar and params.show_colorbar:
            add_colorbar(plt.gcf(), ax, scatter, params, label=feature or "")
        mappable = scatter

    ax.set_aspect("equal")
    ax.set_xlabel("")
    ax.set_ylabel("")
    if not params.show_axes:
        ax.axis("off")
    if title:
        ax.set_title(title, fontsize=12)

    return mappable


# ---------------------------------------------------------------------------
# Data-inference utilities
# ---------------------------------------------------------------------------


def get_categorical_columns(adata: Any, limit: Optional[int] = None) -> list[str]:
    """Return obs column names whose dtype is object or category."""
    cols = [
        c for c in adata.obs.columns
        if adata.obs[c].dtype.name in ("object", "category")
    ]
    return cols[:limit] if limit is not None else cols


def infer_basis(
    adata: Any,
    preferred: Optional[str] = None,
    priority: Optional[list[str]] = None,
) -> Optional[str]:
    """Infer the best embedding basis available in *adata.obsm*.

    Priority order (default): ``spatial > umap > pca``.
    """
    if priority is None:
        priority = ["spatial", "umap", "pca"]

    if preferred:
        key = preferred if preferred == "spatial" else f"X_{preferred}"
        if key in adata.obsm:
            return preferred

    for basis in priority:
        key = basis if basis == "spatial" else f"X_{basis}"
        if key in adata.obsm:
            return basis

    for key in adata.obsm.keys():
        if key.startswith("X_"):
            return key[2:]

    return None


def validate_features(
    adata: Any,
    features: str | list[str],
    max_features: Optional[int] = None,
    genes_only: bool = False,
) -> list[str]:
    """Return validated feature names present in *adata*.

    Logs a warning (does not raise) for missing features.
    """
    if isinstance(features, str):
        features = [features]

    validated: list[str] = []
    for feat in features:
        if feat in adata.var_names:
            validated.append(feat)
        elif not genes_only:
            if feat in adata.obs.columns or feat in adata.obsm:
                validated.append(feat)
            else:
                logger.warning("Feature '%s' not found in genes, obs, or obsm", feat)
        else:
            logger.warning("Gene '%s' not found in var_names", feat)

    if max_features is not None and len(validated) > max_features:
        logger.warning(
            "Too many features (%d), limiting to %d", len(validated), max_features
        )
        validated = validated[:max_features]

    return validated
