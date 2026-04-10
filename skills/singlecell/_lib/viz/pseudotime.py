"""Pseudotime visualization helpers shared across single-cell trajectory skills."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure
from .embedding import embedding_axis_labels, make_categorical_palette, plot_embedding_continuous

logger = logging.getLogger(__name__)


def plot_pseudotime_embedding(
    adata,
    output_dir: str | Path,
    *,
    obsm_key: str,
    pseudotime_key: str,
    filename: str = "pseudotime_embedding.png",
    title: str = "Pseudotime on embedding",
    root_cell_name: str | None = None,
) -> Path | None:
    """Plot pseudotime on an embedding and optionally highlight the root cell."""
    path = plot_embedding_continuous(
        adata,
        output_dir,
        obsm_key=obsm_key,
        color_key=pseudotime_key,
        filename=filename,
        title=title,
        subtitle=f"Embedding: {obsm_key}",
        cmap="viridis",
    )
    if path is None or not root_cell_name or obsm_key not in adata.obsm or root_cell_name not in set(adata.obs_names.astype(str)):
        return path

    import matplotlib.pyplot as plt

    apply_singlecell_theme()
    coords = np.asarray(adata.obsm[obsm_key])
    idx = int(np.where(adata.obs_names.astype(str) == str(root_cell_name))[0][0])
    xlab, ylab = embedding_axis_labels(obsm_key)
    frame = pd.DataFrame({xlab: coords[:, 0], ylab: coords[:, 1], pseudotime_key: pd.to_numeric(adata.obs[pseudotime_key], errors="coerce")})
    fig, ax = plt.subplots(figsize=(8.2, 6.4))
    scatter = ax.scatter(
        frame[xlab],
        frame[ylab],
        c=frame[pseudotime_key],
        cmap="viridis",
        s=10,
        linewidths=0,
        alpha=0.88,
    )
    ax.scatter(
        [coords[idx, 0]],
        [coords[idx, 1]],
        s=140,
        c=QC_PALETTE["accent"],
        marker="*",
        edgecolors="white",
        linewidths=0.9,
        zorder=6,
    )
    ax.text(
        coords[idx, 0],
        coords[idx, 1],
        "root",
        fontsize=10,
        weight="semibold",
        color=QC_PALETTE["accent"],
        va="bottom",
        ha="left",
    )
    ax.set_title(title, fontsize=17, pad=12)
    ax.set_xlabel(xlab)
    ax.set_ylabel(ylab)
    cbar = fig.colorbar(scatter, ax=ax, shrink=0.82, pad=0.02)
    cbar.set_label("pseudotime")
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_pseudotime_distribution_by_group(
    pseudotime_df: pd.DataFrame,
    output_dir: str | Path,
    *,
    group_col: str,
    pseudotime_col: str,
    filename: str = "pseudotime_distribution_by_group.png",
) -> Path | None:
    """Plot pseudotime distributions across groups."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    frame = pseudotime_df[[group_col, pseudotime_col]].copy()
    frame[group_col] = frame[group_col].astype(str)
    frame[pseudotime_col] = pd.to_numeric(frame[pseudotime_col], errors="coerce")
    frame = frame.dropna(subset=[pseudotime_col])
    if frame.empty:
        logger.warning("No finite pseudotime values for %s", filename)
        return None

    ordered_groups = sorted(frame[group_col].unique().tolist(), key=lambda x: (not str(x).isdigit(), str(x)))
    palette = make_categorical_palette(ordered_groups)

    apply_singlecell_theme()
    fig_width = max(8.5, 0.65 * len(ordered_groups) + 3.8)
    fig, ax = plt.subplots(figsize=(fig_width, 5.8))
    sns.violinplot(
        data=frame,
        x=group_col,
        y=pseudotime_col,
        hue=group_col,
        order=ordered_groups,
        palette=palette,
        inner="box",
        cut=0,
        linewidth=0.8,
        ax=ax,
        legend=False,
    )
    ax.set_title("Pseudotime distribution by group", fontsize=16, pad=10)
    ax.set_xlabel(group_col)
    ax.set_ylabel("pseudotime")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_trajectory_gene_trends(
    adata,
    trajectory_genes: pd.DataFrame,
    output_dir: str | Path,
    *,
    pseudotime_key: str,
    n_genes: int = 8,
    filename: str = "trajectory_gene_trends.png",
) -> Path | None:
    """Plot smoothed gene-expression trends across pseudotime for top genes."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    if pseudotime_key not in adata.obs.columns or trajectory_genes.empty:
        return None

    genes = [str(gene) for gene in trajectory_genes["gene"].astype(str).tolist() if gene in set(adata.var_names.astype(str))]
    genes = genes[: max(1, min(n_genes, len(genes)))]
    if not genes:
        return None

    matrix = adata[:, genes].X
    if hasattr(matrix, "toarray"):
        matrix = matrix.toarray()
    expr = np.asarray(matrix, dtype=float)
    pseudotime = pd.to_numeric(adata.obs[pseudotime_key], errors="coerce").to_numpy()
    valid = np.isfinite(pseudotime)
    if not valid.any():
        return None

    expr = expr[valid, :]
    pseudotime = pseudotime[valid]
    order = np.argsort(pseudotime)
    expr = expr[order, :]
    pseudotime = pseudotime[order]

    # Bin cells to produce stable smooth trends without assuming fancy GAM deps.
    n_bins = min(40, max(12, int(round(math.sqrt(len(pseudotime))))))
    bins = np.linspace(float(pseudotime.min()), float(pseudotime.max()), n_bins + 1)
    centers = (bins[:-1] + bins[1:]) / 2.0
    trend_rows: list[dict[str, object]] = []
    for gene_idx, gene in enumerate(genes):
        values = expr[:, gene_idx]
        assignments = np.digitize(pseudotime, bins[1:-1], right=False)
        for bin_idx in range(n_bins):
            mask = assignments == bin_idx
            if not np.any(mask):
                continue
            trend_rows.append(
                {
                    "gene": gene,
                    "pseudotime_bin": float(centers[bin_idx]),
                    "mean_expression": float(np.mean(values[mask])),
                }
            )
    trends = pd.DataFrame(trend_rows)
    if trends.empty:
        return None

    apply_singlecell_theme()
    n_panels = len(genes)
    n_cols = 2 if n_panels > 1 else 1
    n_rows = math.ceil(n_panels / n_cols)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(7.2 * n_cols, 3.0 * n_rows), squeeze=False)
    palette = sns.color_palette("crest", n_panels)
    for ax, gene, color in zip(axes.flatten(), genes, palette):
        sub = trends[trends["gene"] == gene]
        ax.plot(sub["pseudotime_bin"], sub["mean_expression"], color=color, linewidth=2.3)
        ax.fill_between(sub["pseudotime_bin"], 0, sub["mean_expression"], color=color, alpha=0.14)
        ax.set_title(gene, fontsize=12)
        ax.set_xlabel("pseudotime")
        ax.set_ylabel("mean expression")
    for ax in axes.flatten()[len(genes):]:
        ax.axis("off")
    fig.suptitle("Top trajectory gene trends", fontsize=17, y=1.02)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_fate_probability_heatmap(
    fate_df: pd.DataFrame,
    output_dir: str | Path,
    *,
    filename: str = "fate_probability_heatmap.png",
) -> Path | None:
    """Plot average lineage/fate probabilities per group."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    if fate_df.empty:
        return None

    value_cols = [col for col in fate_df.columns if col not in {"group"}]
    if not value_cols:
        return None

    heatmap_df = fate_df.copy().set_index("group")[value_cols]
    heatmap_df = heatmap_df.dropna(how="all")
    if heatmap_df.empty:
        return None

    apply_singlecell_theme()
    fig_width = max(6.6, 0.62 * len(value_cols) + 2.8)
    fig_height = max(4.2, 0.55 * len(heatmap_df) + 1.6)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    sns.heatmap(
        heatmap_df,
        cmap="YlGnBu",
        annot=True,
        fmt=".2f",
        linewidths=0.4,
        cbar_kws={"shrink": 0.78},
        ax=ax,
    )
    ax.set_title("Fate probability overview", fontsize=16, pad=10)
    ax.set_xlabel("terminal state / lineage")
    ax.set_ylabel("group")
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_slingshot_curves(
    points_df: pd.DataFrame,
    curves_df: pd.DataFrame,
    output_dir: str | Path,
    *,
    basis_name: str,
    group_col: str,
    filename: str = "lineage_curves.png",
) -> Path | None:
    """Plot Slingshot lineage curves on the trajectory basis."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    if points_df.empty or curves_df.empty:
        return None

    xcol = "coord1"
    ycol = "coord2"
    groups = points_df[group_col].astype(str).tolist()
    palette = make_categorical_palette(groups)

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(8.6, 6.6))
    sns.scatterplot(
        data=points_df,
        x=xcol,
        y=ycol,
        hue=group_col,
        palette=palette,
        s=12,
        linewidth=0,
        alpha=0.78,
        ax=ax,
        legend=False,
    )
    for lineage, sub in curves_df.groupby("lineage", sort=False):
        sub = sub.sort_values("order")
        ax.plot(sub[xcol], sub[ycol], linewidth=2.4, alpha=0.95, label=str(lineage))
    ax.set_title("Slingshot lineage curves", fontsize=16, pad=10)
    ax.set_xlabel(f"{basis_name} 1")
    ax.set_ylabel(f"{basis_name} 2")
    if curves_df["lineage"].nunique() <= 8:
        ax.legend(frameon=False, loc="best", title="lineage")
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)
