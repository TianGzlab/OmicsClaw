"""Visualization parameter dataclass for SpatialClaw.

Adapted from ChatSpatial's VisualizationParameters — stripped of
ToolContext / Pydantic / async dependencies to work in SpatialClaw's
synchronous CLI environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VizParams:
    """Unified parameters for all SpatialClaw visualization functions.

    Sensible defaults are provided for every field so callers only need to
    override what they care about.

    Examples::

        # Minimal usage
        p = VizParams(feature="CD8A")

        # Multi-panel spatial figure
        p = VizParams(feature=["CD8A", "CD4", "FOXP3"], basis="spatial",
                      colormap="magma", figure_size=(15, 5))

        # UMAP cluster plot
        p = VizParams(cluster_key="leiden", basis="umap")
    """

    # --- General ---
    figure_size: Optional[tuple[float, float]] = None
    """Figure size in inches (width, height). Auto-computed if None."""

    dpi: int = 200
    """Figure resolution (dots per inch). 200 DPI produces publication-quality
    PNG output suitable for reports and presentations."""

    title: Optional[str] = None
    """Main figure / suptitle. Auto-generated if None."""

    # --- Features ---
    feature: Optional[str | list[str]] = None
    """Gene name(s), obs column(s), or LR pair(s) to visualise."""

    basis: str = "spatial"
    """Coordinate basis: ``"spatial"``, ``"umap"``, or ``"pca"``."""

    cluster_key: Optional[str] = None
    """adata.obs column for cell-type / cluster labels."""

    batch_key: Optional[str] = None
    """adata.obs column for batch labels (integration plots)."""

    # --- Colour ---
    colormap: str = "magma"
    """Matplotlib/seaborn colormap name for continuous data."""

    vmin: Optional[float] = None
    """Minimum value for colour scaling (continuous data)."""

    vmax: Optional[float] = None
    """Maximum value for colour scaling (continuous data)."""

    color_scale: Optional[str] = None
    """Pre-scale values: ``"log"`` (log1p) or ``"sqrt"`` before colouring."""

    # --- Points ---
    spot_size: Optional[float] = None
    """Point/spot size (matplotlib s parameter). Auto-computed if None."""

    alpha: float = 0.8
    """Point opacity (0–1)."""

    # --- Layout ---
    subtype: Optional[str] = None
    """Plot sub-type (method-specific, e.g. ``"violin"``, ``"batch"``)."""

    panel_layout: Optional[tuple[int, int]] = None
    """Explicit (n_rows, n_cols) for multi-panel figures."""

    subplot_wspace: float = 0.3
    """Horizontal spacing between sub-plots."""

    subplot_hspace: float = 0.3
    """Vertical spacing between sub-plots."""

    # --- Decorations ---
    show_colorbar: bool = True
    show_legend: bool = True
    show_axes: bool = True
    add_gene_labels: bool = True

    colorbar_size: str = "5%"
    colorbar_pad: float = 0.1

    # --- Expression subtypes ---
    dotplot_dendrogram: bool = False
    dotplot_swap_axes: bool = False
    dotplot_standard_scale: Optional[str] = None
    dotplot_dot_min: Optional[float] = None
    dotplot_dot_max: Optional[float] = None
    dotplot_smallest_dot: Optional[float] = None
    dotplot_var_groups: Optional[dict[str, Any]] = None

    # --- Correlation ---
    correlation_method: str = "pearson"
    """Correlation method: ``"pearson"``, ``"spearman"``, or ``"kendall"``."""

    show_correlation_stats: bool = True
