"""Visualization helpers for scRNA upstream processing skills."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure

logger = logging.getLogger(__name__)


def plot_fastq_sample_summary(
    sample_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "fastq_q30_summary.png",
) -> None:
    """Plot per-sample Q30 and GC summaries."""
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir = Path(output_dir)
    if sample_df.empty:
        logger.warning("FASTQ sample summary is empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    labels = sample_df["sample_id"].astype(str).tolist()
    x = np.arange(len(labels))
    width = 0.36

    fig, ax = plt.subplots(figsize=(max(6.5, 1.6 * len(labels)), 4.8))
    ax.bar(x - width / 2, sample_df["q30_pct"], width=width, color=QC_PALETTE["counts"], label="Q30 %")
    ax.bar(x + width / 2, sample_df["gc_pct"], width=width, color=QC_PALETTE["genes"], label="GC %")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel("Percent")
    ax.set_title("FASTQ sample-level quality overview")
    ax.legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_fastq_per_base_quality(
    per_base_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "per_base_quality.png",
) -> None:
    """Plot per-base mean quality curves."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if per_base_df.empty:
        logger.warning("Per-base FASTQ summary is empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    for file_name, frame in per_base_df.groupby("file", sort=False):
        ax.plot(frame["position"], frame["mean_quality"], linewidth=1.4, alpha=0.9, label=file_name)
    ax.axhline(30, color=QC_PALETTE["accent"], linestyle="--", linewidth=1.0, label="Q30")
    ax.axhline(20, color=QC_PALETTE["neutral"], linestyle=":", linewidth=1.0, label="Q20")
    ax.set_xlabel("Read position")
    ax.set_ylabel("Mean Phred score")
    ax.set_title("Per-base mean quality")
    if per_base_df["file"].nunique() <= 8:
        ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_count_distributions(
    adata,
    output_dir: Union[str, Path],
    *,
    filename: str = "count_distributions.png",
) -> None:
    """Plot total-count and detected-gene distributions for a count matrix."""
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import seaborn as sns

    output_dir = Path(output_dir)
    apply_singlecell_theme()

    matrix = adata.X
    total_counts = np.asarray(matrix.sum(axis=1)).ravel()
    detected = np.asarray((matrix > 0).sum(axis=1)).ravel()
    frame = pd.DataFrame({"total_counts": total_counts, "detected_genes": detected})

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.6))
    sns.histplot(frame["total_counts"], bins=50, ax=axes[0], color=QC_PALETTE["counts"])
    axes[0].set_title("Total counts per barcode")
    axes[0].set_xlabel("Counts")
    axes[0].set_ylabel("Barcodes")
    axes[0].set_xscale("log")

    sns.histplot(frame["detected_genes"], bins=50, ax=axes[1], color=QC_PALETTE["genes"])
    axes[1].set_title("Detected genes per barcode")
    axes[1].set_xlabel("Genes")
    axes[1].set_ylabel("Barcodes")

    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_barcode_rank(
    filtered_counts,
    output_dir: Union[str, Path],
    *,
    raw_counts=None,
    filename: str = "barcode_rank.png",
) -> None:
    """Plot barcode rank curves for filtered and optional raw barcodes."""
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir = Path(output_dir)
    apply_singlecell_theme()

    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    filtered = np.sort(np.asarray(filtered_counts).ravel())[::-1]
    ax.plot(np.arange(1, len(filtered) + 1), filtered, color=QC_PALETTE["counts"], linewidth=1.8, label="filtered")
    if raw_counts is not None:
        raw = np.sort(np.asarray(raw_counts).ravel())[::-1]
        ax.plot(np.arange(1, len(raw) + 1), raw, color=QC_PALETTE["neutral"], linewidth=1.2, alpha=0.8, label="raw")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Barcode rank")
    ax.set_ylabel("Total counts")
    ax.set_title("Barcode rank curve")
    ax.legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_velocity_layer_summary(
    layer_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "velocity_layer_summary.png",
) -> None:
    """Plot spliced/unspliced/ambiguous molecule totals."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if layer_df.empty:
        logger.warning("Velocity layer summary is empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(6.6, 4.8))
    colors = [QC_PALETTE["counts"], QC_PALETTE["genes"], QC_PALETTE["neutral"]]
    ax.bar(layer_df["layer"], layer_df["molecules"], color=colors[: len(layer_df)])
    ax.set_ylabel("Molecules")
    ax.set_title("Velocity layer totals")
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_velocity_gene_balance(
    gene_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "velocity_gene_balance.png",
) -> None:
    """Plot spliced versus unspliced abundance for top genes."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if gene_df.empty:
        logger.warning("Velocity gene summary is empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(6.2, 5.0))
    ax.scatter(
        gene_df["spliced"],
        gene_df["unspliced"],
        s=18,
        alpha=0.8,
        color=QC_PALETTE["counts"],
        edgecolors="none",
    )
    for _, row in gene_df.head(12).iterrows():
        ax.text(row["spliced"], row["unspliced"], str(row["gene"]), fontsize=7, alpha=0.85)
    ax.set_xlabel("Spliced molecules")
    ax.set_ylabel("Unspliced molecules")
    ax.set_title("Top genes by spliced/unspliced abundance")
    fig.tight_layout()
    save_figure(fig, output_dir, filename)

