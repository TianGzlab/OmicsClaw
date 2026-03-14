"""SpatialClaw unified visualization package.

Migrated and adapted from ChatSpatial visualization/  (ChatSpatial © 2024).
All async/ToolContext dependencies removed; rewritten for synchronous CLI use.

Quick reference
---------------
.. code-block:: python

    from omicsclaw.spatial.viz import (
        VizParams,
        plot_features,          # spatial / UMAP / PCA feature maps
        plot_expression,        # heatmap / violin / dotplot / correlation
        plot_integration,       # batch UMAP quality (batch / cluster / highlight)
        plot_spatial_stats,     # Moran / neighbourhood / co-occurrence / Ripley
        plot_velocity,          # scVelo stream / phase / proportions / heatmap / paga
        plot_trajectory,        # pseudotime / CellRank fate maps
        plot_deconvolution,     # dominant / diversity / spatial_multi / UMAP
        plot_communication,     # L-R dotplot / heatmap / spatial
        plot_enrichment,        # barplot / dotplot / spatial / violin
        plot_cnv,               # CNV heatmap / spatial
    )

    # Example: plot spatial feature
    fig = plot_features(adata, VizParams(feature="CD8A", basis="spatial"))

    # Example: multi-panel spatial features
    fig = plot_features(adata, VizParams(feature=["CD8A", "CD4", "FOXP3"]))

    # Example: expression heatmap
    fig = plot_expression(adata, VizParams(
        feature=["CD8A", "CD4", "FOXP3"],
        cluster_key="leiden",
        subtype="heatmap",
    ))

    # Example: Moran's I ranking
    fig = plot_spatial_stats(adata, subtype="moran")
"""

from .cnv import plot_cnv
from .communication import plot_communication
from .core import (
    FIGURE_DEFAULTS,
    VizParams,
    add_colorbar,
    auto_spot_size,
    create_figure,
    get_categorical_cmap,
    get_category_colors,
    get_colormap,
    get_diverging_colormap,
    infer_basis,
    plot_spatial_feature,
    resolve_figure_size,
    safe_tight_layout,
    setup_multi_panel_figure,
    validate_features,
)
from .deconvolution import plot_deconvolution
from .enrichment import plot_enrichment
from .expression import plot_expression
from .feature import plot_features
from .integration import plot_integration
from .params import VizParams  # re-export for convenience
from .spatial_stats import plot_spatial_stats
from .trajectory import plot_trajectory
from .velocity import plot_velocity

__all__ = [
    # Parameters
    "VizParams",
    # Core utilities
    "FIGURE_DEFAULTS",
    "create_figure",
    "resolve_figure_size",
    "setup_multi_panel_figure",
    "safe_tight_layout",
    "add_colorbar",
    "get_colormap",
    "get_categorical_cmap",
    "get_category_colors",
    "get_diverging_colormap",
    "plot_spatial_feature",
    "auto_spot_size",
    "infer_basis",
    "validate_features",
    # Plot functions (one per analysis domain)
    "plot_features",
    "plot_expression",
    "plot_integration",
    "plot_spatial_stats",
    "plot_velocity",
    "plot_trajectory",
    "plot_deconvolution",
    "plot_communication",
    "plot_enrichment",
    "plot_cnv",
]
