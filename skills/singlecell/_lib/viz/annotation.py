"""Visualization helpers for single-cell annotation outputs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure

logger = logging.getLogger(__name__)


def plot_cell_type_count_barplot(
    counts_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "cell_type_counts.png",
) -> Path | None:
    """Plot cell type counts with proportions."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if counts_df.empty:
        return None

    frame = counts_df.copy().sort_values("n_cells", ascending=True)
    apply_singlecell_theme()
    height = max(4.5, 0.42 * len(frame) + 1.2)
    fig, ax = plt.subplots(figsize=(8.6, height))
    bars = ax.barh(frame["cell_type"].astype(str), frame["n_cells"], color=QC_PALETTE["bar"], alpha=0.92)
    ax.set_xlabel("Cells")
    ax.set_ylabel("Cell type")
    ax.set_title("Cell type counts", fontsize=17, pad=14)

    xmax = max(float(frame["n_cells"].max()), 1.0)
    for bar, pct in zip(bars, frame["proportion_pct"]):
        ax.text(
            bar.get_width() + xmax * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{pct:.1f}%",
            va="center",
            fontsize=9,
            color="#334155",
        )
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_cluster_annotation_heatmap(
    matrix_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    cluster_key: str,
    filename: str = "cluster_to_cell_type_heatmap.png",
) -> Path | None:
    """Plot a normalized cluster-to-cell-type mapping heatmap."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if matrix_df.empty:
        return None

    frame = matrix_df.copy()
    if cluster_key in frame.columns:
        frame = frame.set_index(cluster_key)
    if frame.empty:
        return None

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(max(8.0, 0.55 * frame.shape[1] + 3.5), max(5.0, 0.45 * frame.shape[0] + 2.0)))
    sns.heatmap(
        frame,
        annot=True,
        fmt=".2f",
        cmap="YlOrRd",
        linewidths=0.4,
        cbar_kws={"label": "Fraction of cells"},
        ax=ax,
    )
    ax.set_xlabel("Cell type")
    ax.set_ylabel(cluster_key)
    ax.set_title("Cluster to cell-type mapping", fontsize=17, pad=14)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)
