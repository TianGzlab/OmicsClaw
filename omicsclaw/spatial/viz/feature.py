"""Unified feature visualization for SpatialClaw.

Supports spatial, UMAP, and PCA coordinate systems.
Handles single genes, multiple genes (multi-panel), obs columns,
and ligand-receptor pairs (3-panel layout per pair).

Adapted from ChatSpatial's visualization/feature.py — removed async,
ToolContext, and VisualizationParameters.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy.stats import kendalltau, pearsonr, spearmanr

from .core import (
    VizParams,
    _get_gene_expression,
    add_colorbar,
    auto_spot_size,
    create_figure,
    get_colormap,
    plot_spatial_feature,
    setup_multi_panel_figure,
    validate_features,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LR-pair parsing
# ---------------------------------------------------------------------------


def _parse_lr_pairs(
    features: list[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Split *features* into regular features and (ligand, receptor) pairs.

    Recognises ``"Ligand^Receptor"`` (LIANA format) and
    ``"Ligand_Receptor"`` (both parts capitalised).
    """
    regular: list[str] = []
    lr_pairs: list[tuple[str, str]] = []

    for feat in features:
        if "^" in feat:
            ligand, receptor = feat.split("^", 1)
            lr_pairs.append((ligand, receptor))
        elif "_" in feat and not feat.startswith("_"):
            parts = feat.split("_")
            if len(parts) == 2 and all(p and p[0].isupper() for p in parts):
                lr_pairs.append((parts[0], parts[1]))
            else:
                regular.append(feat)
        else:
            regular.append(feat)

    return regular, lr_pairs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plot_features(
    adata: Any,
    params: Optional[VizParams] = None,
    *,
    feature: Optional[str | list[str]] = None,
    basis: Optional[str] = None,
) -> plt.Figure:
    """Visualise one or more features on spatial / UMAP / PCA coordinates.

    Args:
        adata: AnnData object.
        params: :class:`~omicsclaw.spatial.viz.params.VizParams` instance.
                Keyword shortcuts *feature* and *basis* override params values.
        feature: Gene(s), obs column(s), or LR pairs to plot.
        basis: Coordinate basis — ``"spatial"``, ``"umap"``, or ``"pca"``.

    Returns:
        :class:`matplotlib.figure.Figure`

    Raises:
        ValueError: If coordinates or requested features are not found.
    """
    if params is None:
        params = VizParams()

    if feature is not None:
        params.feature = feature
    if basis is not None:
        params.basis = basis

    basis = params.basis or "spatial"

    # Resolve coordinates ---------------------------------------------------
    if basis == "spatial":
        if "spatial" not in adata.obsm:
            raise ValueError(
                "Spatial coordinates not found in adata.obsm['spatial']. "
                "Run spatial preprocessing first."
            )
        coords = np.asarray(adata.obsm["spatial"])
    elif basis == "umap":
        if "X_umap" not in adata.obsm:
            raise ValueError(
                "UMAP embedding not found. Run sc.tl.umap first."
            )
        coords = np.asarray(adata.obsm["X_umap"])
    elif basis == "pca":
        if "X_pca" not in adata.obsm:
            raise ValueError("PCA embedding not found. Run sc.tl.pca first.")
        coords = np.asarray(adata.obsm["X_pca"])[:, :2]
    else:
        raise ValueError(f"Unknown basis '{basis}'. Use 'spatial', 'umap', or 'pca'.")

    # Normalise feature list ------------------------------------------------
    raw_features: list[str]
    if params.feature is None:
        raw_features = []
    elif isinstance(params.feature, list):
        raw_features = params.feature
    else:
        raw_features = [params.feature]

    if not raw_features:
        # Fall back to first available cluster column
        for candidate in ("leiden", "louvain", "cluster", "cell_type", "celltype"):
            if candidate in adata.obs.columns:
                raw_features = [candidate]
                break
        if not raw_features:
            raise ValueError("No features provided and no clustering column found.")

    # Check for LR pairs ----------------------------------------------------
    regular_feats, lr_pairs = _parse_lr_pairs(raw_features)

    if lr_pairs:
        return _plot_lr_pairs(adata, params, lr_pairs, basis, coords)

    validated = validate_features(adata, regular_feats, max_features=12)
    if not validated:
        raise ValueError(f"None of the requested features exist in the data: {raw_features}")

    logger.info("Plotting %d feature(s) on '%s': %s", len(validated), basis, validated)

    if len(validated) == 1:
        return _plot_single_feature(adata, params, validated[0], basis, coords)
    return _plot_multi_features(adata, params, validated, basis, coords)


# ---------------------------------------------------------------------------
# Single feature
# ---------------------------------------------------------------------------


def _plot_single_feature(
    adata: Any,
    params: VizParams,
    feature: str,
    basis: str,
    coords: np.ndarray,
) -> plt.Figure:
    fig, ax = create_figure(params.figure_size or (10, 8), dpi=params.dpi)
    spot_size = auto_spot_size(adata, params.spot_size, basis=basis)
    s = spot_size if basis == "spatial" else max(spot_size // 3, 5)

    if feature in adata.var_names:
        values = _get_gene_expression(adata, feature)
        if params.color_scale == "log":
            values = np.log1p(values)
        elif params.color_scale == "sqrt":
            values = np.sqrt(values)

        scatter = ax.scatter(
            coords[:, 0], coords[:, 1],
            c=values, cmap=params.colormap, s=s, alpha=params.alpha,
            vmin=params.vmin, vmax=params.vmax,
        )
        if params.show_colorbar:
            add_colorbar(fig, ax, scatter, params, label=feature)

    elif feature in adata.obs.columns:
        col = adata.obs[feature]
        is_cat = pd.api.types.is_categorical_dtype(col) or col.dtype == object

        if is_cat:
            # Ensure categorical
            if not pd.api.types.is_categorical_dtype(col):
                adata.obs[feature] = col.astype("category")
            categories = adata.obs[feature].cat.categories
            colors = get_colormap(params.colormap, n_colors=len(categories))
            for i, cat in enumerate(categories):
                mask = adata.obs[feature] == cat
                ax.scatter(coords[mask, 0], coords[mask, 1],
                           c=[colors[i]], s=s, alpha=params.alpha, label=cat)
            if params.show_legend:
                ax.legend(loc="center left", bbox_to_anchor=(1, 0.5),
                          fontsize=8, frameon=False)
        else:
            scatter = ax.scatter(
                coords[:, 0], coords[:, 1],
                c=col.values, cmap=params.colormap, s=s, alpha=params.alpha,
                vmin=params.vmin, vmax=params.vmax,
            )
            if params.show_colorbar:
                add_colorbar(fig, ax, scatter, params, label=feature)
    else:
        raise ValueError(f"Feature '{feature}' not found in var_names or obs")

    _label_axes(ax, basis)
    if basis == "spatial":
        ax.invert_yaxis()
    ax.set_title(params.title or f"{feature} ({basis})", fontsize=13)
    if not params.show_axes:
        ax.axis("off")
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Multi-feature grid
# ---------------------------------------------------------------------------


def _plot_multi_features(
    adata: Any,
    params: VizParams,
    features: list[str],
    basis: str,
    coords: np.ndarray,
) -> plt.Figure:
    fig, axes = setup_multi_panel_figure(
        n_panels=len(features),
        params=params,
        default_title="",
        use_tight_layout=False,
    )

    _TEMP_KEY = "_sc_viz_tmp_99"

    for i, feature in enumerate(features):
        if i >= len(axes):
            break
        ax = axes[i]

        if feature in adata.var_names:
            values = _get_gene_expression(adata, feature)
            if params.color_scale == "log":
                values = np.log1p(values)
            elif params.color_scale == "sqrt":
                values = np.sqrt(values)

            vmin = params.vmin if params.vmin is not None else np.percentile(values, 1)
            vmax = params.vmax if params.vmax is not None else np.percentile(values, 99)
            if basis == "umap" and np.sum(values > 0) > 10:
                vmax = np.percentile(values[values > 0], 95)

            if basis == "spatial":
                adata.obs[_TEMP_KEY] = values
                plot_spatial_feature(
                    adata, ax=ax, feature=_TEMP_KEY,
                    params=params, show_colorbar=False,
                )
                if ax.collections:
                    ax.collections[0].set_clim(vmin, vmax)
                    if params.show_colorbar:
                        divider = make_axes_locatable(ax)
                        cax = divider.append_axes(
                            "right", size=params.colorbar_size, pad=params.colorbar_pad
                        )
                        plt.colorbar(ax.collections[0], cax=cax)
                ax.invert_yaxis()
            else:
                scatter = ax.scatter(
                    coords[:, 0], coords[:, 1],
                    c=values, cmap=params.colormap,
                    s=20, alpha=params.alpha, vmin=vmin, vmax=vmax,
                )
                if params.show_colorbar:
                    divider = make_axes_locatable(ax)
                    cax = divider.append_axes(
                        "right", size=params.colorbar_size, pad=params.colorbar_pad
                    )
                    plt.colorbar(scatter, cax=cax)

        elif feature in adata.obs.columns:
            col = adata.obs[feature]
            is_cat = pd.api.types.is_categorical_dtype(col) or col.dtype == object
            if is_cat:
                if not pd.api.types.is_categorical_dtype(col):
                    adata.obs[feature] = col.astype("category")
                cats = adata.obs[feature].cat.categories
                colors = get_colormap(params.colormap, n_colors=len(cats))
                for j, cat in enumerate(cats):
                    mask = adata.obs[feature] == cat
                    ax.scatter(coords[mask, 0], coords[mask, 1],
                               c=[colors[j]], s=20, alpha=params.alpha, label=cat)
            else:
                scatter = ax.scatter(
                    coords[:, 0], coords[:, 1],
                    c=col.values, cmap=params.colormap, s=20, alpha=params.alpha,
                )
                if params.show_colorbar:
                    divider = make_axes_locatable(ax)
                    cax = divider.append_axes(
                        "right", size=params.colorbar_size, pad=params.colorbar_pad
                    )
                    plt.colorbar(scatter, cax=cax)
            if basis == "spatial":
                ax.invert_yaxis()

        if params.add_gene_labels:
            ax.set_title(feature, fontsize=11)
        if not params.show_axes:
            ax.axis("off")

    if _TEMP_KEY in adata.obs:
        del adata.obs[_TEMP_KEY]

    fig.subplots_adjust(
        top=0.92,
        wspace=params.subplot_wspace + 0.1,
        hspace=params.subplot_hspace,
        right=0.98,
    )
    return fig


# ---------------------------------------------------------------------------
# Ligand-receptor pairs (3 panels per pair: ligand | receptor | correlation)
# ---------------------------------------------------------------------------


def _plot_lr_pairs(
    adata: Any,
    params: VizParams,
    lr_pairs: list[tuple[str, str]],
    basis: str,
    coords: np.ndarray,
) -> plt.Figure:
    available = [
        (lig, rec)
        for lig, rec in lr_pairs
        if lig in adata.var_names and rec in adata.var_names
    ]
    if not available:
        raise ValueError(f"None of the LR pairs found in data: {lr_pairs}")

    MAX_PAIRS = 4
    if len(available) > MAX_PAIRS:
        logger.warning("Limiting LR pairs to %d (from %d)", MAX_PAIRS, len(available))
        available = available[:MAX_PAIRS]

    n_panels = len(available) * 3
    fig, axes = setup_multi_panel_figure(
        n_panels=n_panels,
        params=params,
        default_title=f"Ligand–Receptor Pairs ({len(available)})",
        use_tight_layout=True,
    )

    _TEMP_KEY = "_lr_viz_tmp_99"
    ax_idx = 0

    for ligand, receptor in available:
        lig_expr = _get_gene_expression(adata, ligand)
        rec_expr = _get_gene_expression(adata, receptor)

        if params.color_scale == "log":
            lig_expr = np.log1p(lig_expr)
            rec_expr = np.log1p(rec_expr)
        elif params.color_scale == "sqrt":
            lig_expr = np.sqrt(lig_expr)
            rec_expr = np.sqrt(rec_expr)

        for expr, label, gene in [
            (lig_expr, "Ligand", ligand),
            (rec_expr, "Receptor", receptor),
        ]:
            if ax_idx >= len(axes):
                break
            ax = axes[ax_idx]
            if basis == "spatial":
                adata.obs[_TEMP_KEY] = expr
                plot_spatial_feature(
                    adata, ax=ax, feature=_TEMP_KEY, params=params, show_colorbar=False
                )
                if params.show_colorbar and ax.collections:
                    divider = make_axes_locatable(ax)
                    cax = divider.append_axes(
                        "right", size=params.colorbar_size, pad=params.colorbar_pad
                    )
                    plt.colorbar(ax.collections[-1], cax=cax)
                ax.invert_yaxis()
            else:
                scatter = ax.scatter(
                    coords[:, 0], coords[:, 1],
                    c=expr, cmap=params.colormap, s=20, alpha=params.alpha,
                )
                if params.show_colorbar:
                    divider = make_axes_locatable(ax)
                    cax = divider.append_axes(
                        "right", size=params.colorbar_size, pad=params.colorbar_pad
                    )
                    plt.colorbar(scatter, cax=cax)
            if params.add_gene_labels:
                ax.set_title(f"{gene} ({label})", fontsize=10)
            ax_idx += 1

        # Correlation scatter panel
        if ax_idx < len(axes):
            ax = axes[ax_idx]
            if params.correlation_method == "spearman":
                corr, pval = spearmanr(lig_expr, rec_expr)
            elif params.correlation_method == "kendall":
                corr, pval = kendalltau(lig_expr, rec_expr)
            else:
                corr, pval = pearsonr(lig_expr, rec_expr)

            ax.scatter(lig_expr, rec_expr, alpha=params.alpha, s=20)
            ax.set_xlabel(f"{ligand}")
            ax.set_ylabel(f"{receptor}")

            if params.show_correlation_stats:
                ax.set_title(f"r = {corr:.3f}\np = {pval:.2e}", fontsize=10)
            else:
                ax.set_title(f"{ligand} vs {receptor}", fontsize=10)

            z = np.polyfit(lig_expr, rec_expr, 1)
            p_line = np.poly1d(z)
            ax.plot(np.sort(lig_expr), p_line(np.sort(lig_expr)), "r--", alpha=0.8)
            ax_idx += 1

    if _TEMP_KEY in adata.obs:
        del adata.obs[_TEMP_KEY]

    fig.subplots_adjust(top=0.92, wspace=0.1, hspace=0.3, right=0.98)
    return fig


# ---------------------------------------------------------------------------
# Axis label helper
# ---------------------------------------------------------------------------


def _label_axes(ax: plt.Axes, basis: str) -> None:
    labels = {
        "spatial": ("Spatial X", "Spatial Y"),
        "umap": ("UMAP 1", "UMAP 2"),
        "pca": ("PC 1", "PC 2"),
    }
    xlabel, ylabel = labels.get(basis, ("Dim 1", "Dim 2"))
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
