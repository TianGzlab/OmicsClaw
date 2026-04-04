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


def plot_fastq_file_quality(
    per_file_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "fastq_file_quality.png",
) -> None:
    """Plot per-file quality metrics for quick file-level inspection."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if per_file_df.empty:
        logger.warning("Per-file FASTQ summary is empty; skipping %s", filename)
        return

    frame = per_file_df.copy()
    frame["label"] = frame["sample_id"].astype(str) + " / " + frame["read_label"].astype(str)

    apply_singlecell_theme()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.8))
    axes[0].scatter(frame["q30_pct"], frame["adapter_seed_pct"], s=60, color=QC_PALETTE["counts"], alpha=0.85)
    for _, row in frame.iterrows():
        axes[0].text(row["q30_pct"], row["adapter_seed_pct"], row["label"], fontsize=8, alpha=0.85)
    axes[0].set_xlabel("Q30 %")
    axes[0].set_ylabel("Adapter-seed reads %")
    axes[0].set_title("Per-file quality versus adapter signal")

    axes[1].scatter(frame["mean_read_length"], frame["gc_pct"], s=60, color=QC_PALETTE["genes"], alpha=0.85)
    for _, row in frame.iterrows():
        axes[1].text(row["mean_read_length"], row["gc_pct"], row["label"], fontsize=8, alpha=0.85)
    axes[1].set_xlabel("Mean read length")
    axes[1].set_ylabel("GC %")
    axes[1].set_title("Per-file read length versus GC")

    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_fastq_read_structure(
    per_file_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "fastq_read_structure.png",
) -> None:
    """Plot read length and adapter-seed burden for each FASTQ file."""
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir = Path(output_dir)
    if per_file_df.empty:
        logger.warning("FASTQ per-file summary is empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    labels = [
        f"{row.sample_id}:{row.read_label}"
        for row in per_file_df[["sample_id", "read_label"]].itertuples(index=False)
    ]
    x = np.arange(len(labels))
    width = 0.38

    fig, axes = plt.subplots(2, 1, figsize=(max(7.5, 1.4 * len(labels)), 7.2), sharex=True)
    axes[0].bar(x, per_file_df["mean_read_length"], color=QC_PALETTE["genes"], width=width)
    axes[0].set_ylabel("Mean read length")
    axes[0].set_title("Read structure by FASTQ file")

    axes[1].bar(x, per_file_df["adapter_seed_pct"], color=QC_PALETTE["accent"], width=width)
    axes[1].set_ylabel("Adapter-seed %")
    axes[1].set_xlabel("Sample:read")
    axes[1].axhline(1.0, color=QC_PALETTE["neutral"], linestyle="--", linewidth=1.0)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=25, ha="right")
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


def plot_count_complexity_scatter(
    barcode_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "count_complexity_scatter.png",
) -> None:
    """Plot total counts versus detected genes across barcodes."""
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir = Path(output_dir)
    if barcode_df.empty:
        logger.warning("Barcode metrics are empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    ax.scatter(
        barcode_df["total_counts"],
        barcode_df["detected_genes"],
        s=10,
        alpha=0.55,
        color=QC_PALETTE["counts"],
        edgecolors="none",
    )
    ax.set_xscale("log")
    ax.set_xlabel("Total counts")
    ax.set_ylabel("Detected genes")
    ax.set_title("Count complexity per barcode")

    if barcode_df.shape[0] >= 10:
        top = barcode_df.head(10)
        for _, row in top.iterrows():
            ax.text(
                row["total_counts"],
                row["detected_genes"],
                str(row["barcode"]),
                fontsize=6.5,
                alpha=0.7,
            )
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


def plot_count_scatter(
    barcode_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "count_scatter.png",
) -> None:
    """Plot total counts versus detected genes per barcode."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if barcode_df.empty:
        logger.warning("Barcode metrics are empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(6.8, 5.2))
    ax.scatter(
        barcode_df["total_counts"],
        barcode_df["detected_genes"],
        s=10,
        alpha=0.45,
        color=QC_PALETTE["counts"],
        edgecolors="none",
    )
    ax.set_xscale("log")
    ax.set_xlabel("Total counts")
    ax.set_ylabel("Detected genes")
    ax.set_title("Counts versus detected genes per barcode")
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


def plot_velocity_layer_fraction(
    layer_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "velocity_layer_fraction.png",
) -> None:
    """Plot the fraction contributed by each velocity layer."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if layer_df.empty:
        logger.warning("Velocity layer summary is empty; skipping %s", filename)
        return

    frame = layer_df.copy()
    total = float(frame["molecules"].sum())
    if total <= 0:
        logger.warning("Velocity layer totals are zero; skipping %s", filename)
        return
    frame["fraction_pct"] = 100.0 * frame["molecules"] / total

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(6.6, 4.8))
    ax.bar(frame["layer"], frame["fraction_pct"], color=[QC_PALETTE["counts"], QC_PALETTE["genes"], QC_PALETTE["neutral"]][: len(frame)])
    ax.set_ylabel("Percent of molecules")
    ax.set_title("Velocity layer composition")
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_velocity_top_genes_stacked(
    gene_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "velocity_top_genes_stacked.png",
) -> None:
    """Plot stacked spliced/unspliced/ambiguous totals for top velocity genes."""
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir = Path(output_dir)
    if gene_df.empty:
        logger.warning("Velocity gene summary is empty; skipping %s", filename)
        return

    top = gene_df.head(12).copy()
    labels = top["gene"].astype(str).tolist()
    x = np.arange(len(labels))

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(max(7.2, 0.8 * len(labels)), 5.2))
    ax.bar(x, top["spliced"], color=QC_PALETTE["counts"], label="spliced")
    ax.bar(x, top["unspliced"], bottom=top["spliced"], color=QC_PALETTE["genes"], label="unspliced")
    ax.bar(
        x,
        top["ambiguous"],
        bottom=top["spliced"] + top["unspliced"],
        color=QC_PALETTE["neutral"],
        label="ambiguous",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("Molecules")
    ax.set_title("Top velocity genes by layer totals")
    ax.legend(frameon=False, ncol=3, loc="upper right")
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_velocity_top_genes_bar(
    gene_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "velocity_top_genes.png",
) -> None:
    """Plot the genes with the largest mean absolute velocity."""
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir = Path(output_dir)
    if gene_df.empty:
        logger.warning("Velocity gene summary is empty; skipping %s", filename)
        return

    top = gene_df.head(12).copy()
    labels = top["gene"].astype(str).tolist()
    x = np.arange(len(labels))

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(max(7.2, 0.8 * len(labels)), 5.0))
    ax.bar(x, top["mean_abs_velocity"], color=QC_PALETTE["counts"])
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("Mean absolute velocity")
    ax.set_title("Top genes by velocity magnitude")
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_velocity_magnitude_distribution(
    cell_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "velocity_magnitude_distribution.png",
) -> None:
    """Plot the distribution of per-cell velocity magnitudes."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if "velocity_magnitude" not in cell_df.columns or cell_df.empty:
        logger.warning("Velocity cell summary is missing `velocity_magnitude`; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(6.8, 4.8))
    sns.histplot(cell_df["velocity_magnitude"], bins=40, color=QC_PALETTE["counts"], ax=ax)
    ax.set_xlabel("Velocity magnitude")
    ax.set_ylabel("Cells")
    ax.set_title("Velocity magnitude distribution")
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_latent_time_distribution(
    cell_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "latent_time_distribution.png",
) -> None:
    """Plot the distribution of latent time when present."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if "latent_time" not in cell_df.columns or cell_df.empty:
        logger.warning("Velocity cell summary is missing `latent_time`; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(6.8, 4.8))
    sns.histplot(cell_df["latent_time"], bins=40, color=QC_PALETTE["genes"], ax=ax)
    ax.set_xlabel("Latent time")
    ax.set_ylabel("Cells")
    ax.set_title("Latent time distribution")
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_filter_metric_comparison(
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    metrics: list[str],
    filename: str = "filter_comparison.png",
) -> None:
    """Plot before/after QC distributions for filtering workflows."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    metrics = [metric for metric in metrics if metric in before_df.columns and metric in after_df.columns]
    if not metrics:
        logger.warning("No comparable QC metrics found; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, axes = plt.subplots(1, len(metrics), figsize=(max(4.2 * len(metrics), 10.0), 4.8), squeeze=False)
    axes = axes.ravel()

    for ax, metric in zip(axes, metrics):
        combined = pd.concat(
            [
                pd.DataFrame({"state": "Before", "value": before_df[metric].astype(float)}),
                pd.DataFrame({"state": "After", "value": after_df[metric].astype(float)}),
            ],
            ignore_index=True,
        )
        sns.boxplot(
            data=combined,
            x="state",
            y="value",
            palette=[QC_PALETTE["neutral"], QC_PALETTE["counts"]],
            width=0.55,
            ax=ax,
        )
        ax.set_title(metric.replace("_", " ").title(), fontsize=11, pad=10)
        ax.set_xlabel("")
        ax.set_ylabel("")
    fig.suptitle("QC metrics before and after filtering", fontsize=15, y=1.03)
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_filter_retention_summary(
    retention_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "filter_summary.png",
) -> None:
    """Plot before/after retention for cells and genes."""
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir = Path(output_dir)
    if retention_df.empty:
        logger.warning("Retention summary is empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    labels = retention_df["feature"].astype(str).tolist()
    before = retention_df["before"].astype(float).tolist()
    after = retention_df["after"].astype(float).tolist()
    x = np.arange(len(labels))
    width = 0.34

    fig, ax = plt.subplots(figsize=(7.0, 4.8))
    ax.bar(x - width / 2, before, width=width, color=QC_PALETTE["neutral"], label="Before")
    ax.bar(x + width / 2, after, width=width, color=QC_PALETTE["counts"], label="After")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Count")
    ax.set_title("Retention after filtering")
    ax.legend(frameon=False)

    for idx, (before_value, after_value) in enumerate(zip(before, after)):
        pct = 100 * after_value / before_value if before_value else 0
        ax.text(x[idx] + width / 2, after_value, f"{pct:.1f}%", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_filter_threshold_panels(
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    thresholds: dict[str, float | int | None],
    filename: str = "filter_thresholds.png",
) -> None:
    """Plot threshold-aware before/after QC histograms."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    metric_order = [
        ("n_genes_by_counts", "min_genes", "max_genes", "Detected genes"),
        ("total_counts", "min_counts", "max_counts", "Total counts"),
        ("pct_counts_mt", None, "max_mt_percent", "Mitochondrial fraction (%)"),
    ]
    available = [item for item in metric_order if item[0] in before_df.columns and item[0] in after_df.columns]
    if not available:
        logger.warning("No threshold-aware QC metrics found; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, axes = plt.subplots(1, len(available), figsize=(max(4.4 * len(available), 11.0), 4.8), squeeze=False)
    axes = axes.ravel()

    for ax, (metric, lower_key, upper_key, title) in zip(axes, available):
        before_vals = before_df[metric].astype(float)
        after_vals = after_df[metric].astype(float)
        sns.histplot(before_vals, bins=50, ax=ax, color=QC_PALETTE["neutral"], alpha=0.35, stat="density", label="Before")
        sns.histplot(after_vals, bins=50, ax=ax, color=QC_PALETTE["counts"], alpha=0.75, stat="density", label="After")
        lower = thresholds.get(lower_key) if lower_key else None
        upper = thresholds.get(upper_key) if upper_key else None
        if lower is not None:
            ax.axvline(float(lower), color=QC_PALETTE["accent"], linestyle="--", linewidth=1.6)
        if upper is not None:
            ax.axvline(float(upper), color=QC_PALETTE["accent"], linestyle="--", linewidth=1.6)
        ax.set_title(title, fontsize=11, pad=10)
        ax.set_xlabel("")
        ax.set_ylabel("Density")
        if metric == "total_counts":
            ax.set_xscale("log")
        ax.legend(frameon=False, fontsize=8)

    fig.suptitle("Filtering thresholds on QC distributions", fontsize=15, y=1.03)
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_filter_state_scatter(
    state_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "filter_state_scatter.png",
) -> None:
    """Plot retained vs removed cells in QC space."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    required = {"total_counts", "n_genes_by_counts", "state"}
    if state_df.empty or not required.issubset(state_df.columns):
        logger.warning("Filter state dataframe missing required columns; skipping %s", filename)
        return

    apply_singlecell_theme()
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.8))
    palette = {"Retained": QC_PALETTE["counts"], "Removed": QC_PALETTE["accent"]}

    sns.scatterplot(
        data=state_df,
        x="total_counts",
        y="n_genes_by_counts",
        hue="state",
        palette=palette,
        s=10,
        alpha=0.45,
        linewidth=0,
        ax=axes[0],
        rasterized=len(state_df) > 5000,
    )
    axes[0].set_xscale("log")
    axes[0].set_title("Retained vs removed cells", fontsize=11, pad=10)
    axes[0].legend(frameon=False, fontsize=8, title="")

    if "pct_counts_mt" in state_df.columns:
        sns.scatterplot(
            data=state_df,
            x="total_counts",
            y="pct_counts_mt",
            hue="state",
            palette=palette,
            s=10,
            alpha=0.45,
            linewidth=0,
            ax=axes[1],
            legend=False,
            rasterized=len(state_df) > 5000,
        )
        axes[1].set_xscale("log")
        axes[1].set_title("Counts vs mitochondrial fraction", fontsize=11, pad=10)
    else:
        axes[1].axis("off")

    fig.suptitle("Filter decisions in QC space", fontsize=15, y=1.03)
    fig.tight_layout()
    save_figure(fig, output_dir, filename)


def plot_filter_reason_summary(
    reason_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "filter_reason_summary.png",
) -> None:
    """Plot how many cells were flagged by each filtering rule."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if reason_df.empty:
        logger.warning("Filter reason summary is empty; skipping %s", filename)
        return

    apply_singlecell_theme()
    ordered = reason_df.sort_values("count", ascending=True)
    fig_height = max(4.8, 0.55 * len(ordered) + 1.8)
    fig, ax = plt.subplots(figsize=(8.6, fig_height))
    sns.barplot(data=ordered, x="count", y="reason", color=QC_PALETTE["bar"], ax=ax)
    ax.set_title("Cells flagged by each rule", fontsize=15, pad=10)
    ax.set_xlabel("Cells")
    ax.set_ylabel("")
    for idx, row in enumerate(ordered.itertuples(index=False)):
        ax.text(float(row.count), idx, f"  {int(row.count)}", va="center", ha="left", fontsize=9)
    fig.tight_layout()
    save_figure(fig, output_dir, filename)
