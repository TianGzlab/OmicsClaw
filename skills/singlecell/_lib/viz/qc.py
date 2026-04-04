"""QC-oriented visualization primitives for single-cell skills."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure

logger = logging.getLogger(__name__)


_METRIC_LABELS = {
    "n_genes_by_counts": "Detected genes per cell",
    "total_counts": "Total counts per cell",
    "pct_counts_mt": "Mitochondrial fraction (%)",
    "pct_counts_ribo": "Ribosomal fraction (%)",
}

_METRIC_COLORS = {
    "n_genes_by_counts": QC_PALETTE["genes"],
    "total_counts": QC_PALETTE["counts"],
    "pct_counts_mt": QC_PALETTE["mt"],
    "pct_counts_ribo": QC_PALETTE["ribo"],
}


def _metric_label(metric: str) -> str:
    return _METRIC_LABELS.get(metric, metric.replace("_", " ").title())


def _metric_color(metric: str) -> str:
    return _METRIC_COLORS.get(metric, QC_PALETTE["neutral"])


def _metric_series(adata, metric: str) -> pd.Series:
    return pd.Series(adata.obs[metric], dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()


def plot_qc_violin(
    adata,
    output_dir: Union[str, Path],
    metrics: Optional[list[str]] = None,
    figsize: Optional[tuple[float, float]] = None,
) -> None:
    """Create a polished multi-panel violin summary for QC metrics."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    apply_singlecell_theme()

    if metrics is None:
        metrics = ["n_genes_by_counts", "total_counts", "pct_counts_mt"]
    metrics = [metric for metric in metrics if metric in adata.obs.columns]
    if not metrics:
        logger.warning("No QC metrics available for violin plotting")
        return

    if figsize is None:
        figsize = (max(4.4 * len(metrics), 10.0), 4.8)

    fig, axes = plt.subplots(1, len(metrics), figsize=figsize, squeeze=False)
    axes = axes.ravel()

    for ax, metric in zip(axes, metrics):
        values = _metric_series(adata, metric)
        color = _metric_color(metric)
        sns.violinplot(y=values, ax=ax, color=color, cut=0, inner=None, linewidth=0)
        sns.boxplot(
            y=values,
            ax=ax,
            width=0.18,
            color="white",
            showcaps=False,
            boxprops={"facecolor": "white", "edgecolor": "#303030", "linewidth": 1.1},
            whiskerprops={"linewidth": 1.0, "color": "#303030"},
            medianprops={"linewidth": 1.6, "color": QC_PALETTE["accent"]},
            flierprops={"marker": "", "markersize": 0},
        )
        ax.set_title(_metric_label(metric), fontsize=11, pad=10)
        ax.set_ylabel("")
        ax.set_xlabel("")
        ax.set_xticks([])
        ax.text(
            0.03,
            0.96,
            f"median {values.median():.1f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            color="#303030",
            bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "none", "alpha": 0.9},
        )

    fig.suptitle("Single-cell QC distributions", fontsize=15, y=1.03)
    fig.tight_layout()
    save_figure(fig, output_dir, "qc_violin.png")


def plot_qc_scatter(
    adata,
    output_dir: Union[str, Path],
    figsize: Optional[tuple[float, float]] = None,
) -> None:
    """Create QC scatter panels with consistent styling."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    apply_singlecell_theme()

    scatter_cfg = [
        ("total_counts", "n_genes_by_counts", QC_PALETTE["counts"]),
        ("total_counts", "pct_counts_mt", QC_PALETTE["mt"]),
        ("n_genes_by_counts", "pct_counts_mt", QC_PALETTE["mt"]),
        ("total_counts", "pct_counts_ribo", QC_PALETTE["ribo"]),
        ("n_genes_by_counts", "pct_counts_ribo", QC_PALETTE["ribo"]),
    ]
    available_pairs = [(x, y, c) for x, y, c in scatter_cfg if x in adata.obs.columns and y in adata.obs.columns]
    if not available_pairs:
        logger.warning("No QC metric pairs available for scatter plotting")
        return

    if figsize is None:
        figsize = (max(4.2 * len(available_pairs), 12.0), 4.5)

    fig, axes = plt.subplots(1, len(available_pairs), figsize=figsize, squeeze=False)
    axes = axes.ravel()

    point_size = 6 if adata.n_obs < 5000 else 3
    alpha = 0.42 if adata.n_obs < 5000 else 0.18

    for ax, (x, y, color) in zip(axes, available_pairs):
        ax.scatter(
            adata.obs[x],
            adata.obs[y],
            s=point_size,
            alpha=alpha,
            c=color,
            edgecolors="none",
            rasterized=adata.n_obs > 5000,
        )
        ax.set_xlabel(_metric_label(x), fontsize=10)
        ax.set_ylabel(_metric_label(y), fontsize=10)
        if "counts" in x:
            ax.set_xscale("log")
        if "counts" in y and "pct" not in y:
            ax.set_yscale("log")
        ax.set_title(f"{_metric_label(y)} vs {_metric_label(x)}", fontsize=11, pad=10)

    fig.suptitle("QC relationships across cells", fontsize=15, y=1.03)
    fig.tight_layout()
    save_figure(fig, output_dir, "qc_scatter.png")


def plot_qc_histograms(
    adata,
    output_dir: Union[str, Path],
    metrics: Optional[list[str]] = None,
    figsize: Optional[tuple[float, float]] = None,
    bins: int = 50,
) -> None:
    """Create histograms with median markers for available QC metrics."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    apply_singlecell_theme()

    if metrics is None:
        metrics = ["n_genes_by_counts", "total_counts", "pct_counts_mt"]
    metrics = [metric for metric in metrics if metric in adata.obs.columns]
    if not metrics:
        logger.warning("No QC metrics available for histogram plotting")
        return

    if figsize is None:
        figsize = (max(4.2 * len(metrics), 10.0), 4.6)

    fig, axes = plt.subplots(1, len(metrics), figsize=figsize, squeeze=False)
    axes = axes.ravel()

    for ax, metric in zip(axes, metrics):
        values = _metric_series(adata, metric)
        color = _metric_color(metric)
        sns.histplot(values, bins=bins, ax=ax, color=color, alpha=0.92, edgecolor="white", linewidth=0.4)
        median = values.median()
        ax.axvline(median, color=QC_PALETTE["accent"], linestyle="--", linewidth=1.8)
        ax.set_title(_metric_label(metric), fontsize=11, pad=10)
        ax.set_xlabel("")
        ax.set_ylabel("Cells")
        ax.text(
            0.98,
            0.96,
            f"median {median:.1f}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            color="#303030",
            bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "none", "alpha": 0.9},
        )

    fig.suptitle("QC metric distributions", fontsize=15, y=1.03)
    fig.tight_layout()
    save_figure(fig, output_dir, "qc_histograms.png")


def plot_highest_expr_genes(
    adata,
    output_dir: Union[str, Path],
    n_top: int = 20,
) -> None:
    """Plot the top expressed genes with a cleaner summary bar chart."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    apply_singlecell_theme()

    logger.info("Plotting top %d highest expressed genes ...", n_top)
    mean_expression = np.asarray(adata.X.mean(axis=0)).ravel()
    df = pd.DataFrame(
        {
            "gene": adata.var_names.astype(str),
            "mean_expression": mean_expression,
        }
    ).sort_values("mean_expression", ascending=False).head(n_top)
    df = df.iloc[::-1].reset_index(drop=True)

    fig_height = max(5.2, 0.34 * n_top + 1.6)
    fig, ax = plt.subplots(figsize=(9.5, fig_height))
    palette = sns.color_palette("blend:#A7D7C5,#005F73", n_colors=len(df))
    ax.barh(df["gene"], df["mean_expression"], color=palette, edgecolor="none")
    ax.set_title("Top expressed genes", fontsize=15, pad=12)
    ax.set_xlabel("Mean expression")
    ax.set_ylabel("")
    ax.grid(axis="x", alpha=0.25)

    fig.tight_layout()
    save_figure(fig, output_dir, "highest_expr_genes.png")


def plot_barcode_rank(
    adata,
    output_dir: Union[str, Path],
) -> None:
    """Plot the barcode-rank curve, a common QC diagnostic for library complexity."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    apply_singlecell_theme()

    if "total_counts" not in adata.obs.columns:
        logger.warning("total_counts not available for barcode-rank plotting")
        return

    counts = np.sort(np.asarray(adata.obs["total_counts"], dtype="float64"))[::-1]
    ranks = np.arange(1, len(counts) + 1)

    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    ax.plot(ranks, counts, color=QC_PALETTE["counts"], linewidth=2.2)
    ax.fill_between(ranks, counts, color=QC_PALETTE["counts"], alpha=0.12)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_title("Barcode-rank curve", fontsize=15, pad=12)
    ax.set_xlabel("Cell rank")
    ax.set_ylabel("Total counts")
    ax.grid(alpha=0.28)
    ax.text(
        0.03,
        0.96,
        f"median counts {np.median(counts):.0f}",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "none", "alpha": 0.9},
    )

    fig.tight_layout()
    save_figure(fig, output_dir, "barcode_rank.png")


def plot_qc_correlation_heatmap(
    adata,
    output_dir: Union[str, Path],
    metrics: Optional[list[str]] = None,
) -> None:
    """Plot correlations among QC metrics for quick pattern review."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    apply_singlecell_theme()

    if metrics is None:
        metrics = ["n_genes_by_counts", "total_counts", "pct_counts_mt", "pct_counts_ribo"]
    metrics = [metric for metric in metrics if metric in adata.obs.columns]
    if len(metrics) < 2:
        logger.warning("Not enough QC metrics available for correlation heatmap plotting")
        return

    corr = pd.DataFrame({metric: _metric_series(adata, metric) for metric in metrics}).corr()
    labels = [_metric_label(metric) for metric in corr.columns]

    fig, ax = plt.subplots(figsize=(6.8, 5.6))
    sns.heatmap(
        corr,
        ax=ax,
        cmap="RdBu_r",
        center=0,
        vmin=-1,
        vmax=1,
        annot=True,
        fmt=".2f",
        square=True,
        linewidths=0.5,
        cbar_kws={"shrink": 0.85, "label": "Pearson r"},
    )
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_yticklabels(labels, rotation=0)
    ax.set_title("QC metric correlation heatmap", fontsize=15, pad=12)

    fig.tight_layout()
    save_figure(fig, output_dir, "qc_correlation_heatmap.png")
