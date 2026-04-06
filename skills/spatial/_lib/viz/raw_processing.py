"""Visualization helpers for raw spatial FASTQ processing outputs."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_stage_attrition(
    stage_summary_df: pd.DataFrame,
    *,
    title: str = "st_pipeline Read Attrition",
    figure_size: tuple[float, float] = (9.0, 5.0),
) -> plt.Figure | None:
    """Plot retained reads and retention fraction across upstream stages."""
    if stage_summary_df.empty:
        return None

    plot_df = stage_summary_df.copy()
    plot_df["reads_millions"] = pd.to_numeric(plot_df["reads"], errors="coerce") / 1_000_000.0
    plot_df["fraction_of_input"] = pd.to_numeric(
        plot_df["fraction_of_input"],
        errors="coerce",
    )

    fig, ax1 = plt.subplots(figsize=figure_size, dpi=200)
    ax1.bar(
        plot_df["stage_label"],
        plot_df["reads_millions"],
        color="#5b8def",
        alpha=0.9,
    )
    ax1.set_ylabel("Reads (millions)")
    ax1.set_xlabel("Pipeline stage")
    ax1.tick_params(axis="x", rotation=25)

    ax2 = ax1.twinx()
    ax2.plot(
        plot_df["stage_label"],
        plot_df["fraction_of_input"] * 100.0,
        color="#d9485f",
        marker="o",
        linewidth=1.8,
    )
    ax2.set_ylabel("Retention (%)")
    fraction_pct = np.asarray(plot_df["fraction_of_input"] * 100.0, dtype=float)
    finite_fraction = fraction_pct[np.isfinite(fraction_pct)]
    upper = float(finite_fraction.max()) * 1.05 if finite_fraction.size else 100.0
    ax2.set_ylim(0, max(105.0, upper))

    ax1.set_title(title)
    fig.tight_layout()
    return fig


def plot_spot_qc_histograms(
    spot_qc_df: pd.DataFrame,
    *,
    title: str = "Spot-Level Raw Count QC",
    figure_size: tuple[float, float] | None = None,
) -> plt.Figure | None:
    """Plot raw count and feature complexity distributions."""
    if spot_qc_df.empty:
        return None

    metrics = [
        ("total_counts", "Total counts"),
        ("n_genes_by_counts", "Detected genes"),
    ]
    available = [item for item in metrics if item[0] in spot_qc_df.columns]
    if not available:
        return None

    fig, axes = plt.subplots(
        1,
        len(available),
        figsize=figure_size or (5.2 * len(available), 4.5),
        dpi=200,
        squeeze=False,
    )
    axes_flat = axes.flatten()

    for idx, (column, label) in enumerate(available):
        ax = axes_flat[idx]
        values = pd.to_numeric(spot_qc_df[column], errors="coerce").dropna().to_numpy()
        if values.size == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            ax.set_axis_off()
            continue
        ax.hist(values, bins=30, color="#8fd0c1", edgecolor="white")
        ax.axvline(np.median(values), color="#175676", linestyle="--", linewidth=1.2)
        ax.set_title(label)
        ax.set_xlabel(label)
        ax.set_ylabel("Spots")

    fig.suptitle(title, fontsize=13, y=1.02)
    fig.tight_layout()
    return fig


def plot_top_genes_bar(
    top_gene_df: pd.DataFrame,
    *,
    title: str = "Top Detected Genes",
    figure_size: tuple[float, float] = (8.8, 5.8),
) -> plt.Figure | None:
    """Plot the most abundant genes across the raw count matrix."""
    if top_gene_df.empty or "gene" not in top_gene_df.columns or "total_counts" not in top_gene_df.columns:
        return None

    plot_df = top_gene_df.iloc[::-1].copy()
    values = pd.to_numeric(plot_df["total_counts"], errors="coerce").fillna(0.0)

    fig, ax = plt.subplots(figsize=figure_size, dpi=200)
    ax.barh(plot_df["gene"], values, color="#f39c6b")
    ax.set_xlabel("Total counts across all spots")
    ax.set_ylabel("Gene")
    ax.set_title(title)
    fig.tight_layout()
    return fig


def plot_saturation_curve(
    saturation_df: pd.DataFrame,
    *,
    title: str = "Sequencing Saturation Summary",
    figure_size: tuple[float, float] = (10.5, 7.4),
) -> plt.Figure | None:
    """Plot saturation outputs emitted by st_pipeline."""
    if saturation_df.empty or "reads_sampled" not in saturation_df.columns:
        return None

    plot_df = saturation_df.copy()
    reads_sampled = pd.to_numeric(plot_df["reads_sampled"], errors="coerce").to_numpy()
    if reads_sampled.size == 0:
        return None

    panels = [
        ("reads_detected", "Reads kept", "#175676"),
        ("genes_detected", "Genes detected", "#2d6a4f"),
        ("avg_genes_per_spot", "Avg genes / spot", "#9c6644"),
        ("avg_reads_per_spot", "Avg reads / spot", "#7b2cbf"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=figure_size, dpi=200)
    axes_flat = axes.flatten()

    for ax, (column, label, color) in zip(axes_flat, panels, strict=False):
        if column not in plot_df.columns:
            ax.text(0.5, 0.5, "Not available", ha="center", va="center")
            ax.set_axis_off()
            continue
        values = pd.to_numeric(plot_df[column], errors="coerce").to_numpy()
        ax.plot(reads_sampled, values, color=color, marker="o", linewidth=1.8)
        ax.set_xlabel("Reads sampled")
        ax.set_ylabel(label)
        ax.set_title(label)

    fig.suptitle(title, fontsize=13, y=0.98)
    fig.tight_layout()
    return fig
