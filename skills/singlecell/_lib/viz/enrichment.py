"""Visualization helpers for single-cell pathway and gene-set scoring."""

from __future__ import annotations

from pathlib import Path
from textwrap import fill
from typing import Sequence

import numpy as np
import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure
from .embedding import embedding_axis_labels, make_categorical_palette


def _wrap_labels(values: Sequence[str], width: int = 26) -> list[str]:
    return [fill(str(value), width=width) for value in values]


def plot_top_gene_sets_bar(
    top_df: pd.DataFrame,
    output_dir: str | Path,
    *,
    filename: str = "top_gene_sets.png",
    title: str = "Top pathway activities",
) -> Path | None:
    """Plot overall top-scoring gene sets."""
    import matplotlib.pyplot as plt

    if top_df.empty:
        return None

    apply_singlecell_theme()
    plot_df = top_df.head(15).iloc[::-1].copy()
    fig, ax = plt.subplots(figsize=(10.0, 6.8))
    colors = [QC_PALETTE["bar"] if value >= 0 else QC_PALETTE["accent"] for value in plot_df["mean_score"]]
    labels = _wrap_labels(plot_df["gene_set"])
    bars = ax.barh(labels, plot_df["mean_score"], color=colors, alpha=0.92, height=0.72)
    ax.set_xlabel("Mean pathway score")
    ax.set_ylabel("Gene set")
    ax.set_title(title, fontsize=17, pad=12)
    ax.axvline(0, color="#9AA5B1", linewidth=1.0, alpha=0.65)
    max_abs = float(np.nanmax(np.abs(plot_df["mean_score"]))) if len(plot_df) else 0.0
    margin = max(0.0001, max_abs * 0.12)
    ax.set_xlim(float(plot_df["mean_score"].min()) - margin, float(plot_df["mean_score"].max()) + margin)
    for bar, value in zip(bars, plot_df["mean_score"]):
        xpos = bar.get_width()
        offset = margin * 0.15
        ha = "left" if xpos >= 0 else "right"
        ax.text(
            xpos + (offset if xpos >= 0 else -offset),
            bar.get_y() + bar.get_height() / 2,
            f"{value:.3f}",
            va="center",
            ha=ha,
            fontsize=9,
            color="#38424B",
        )
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_group_mean_heatmap(
    group_means_df: pd.DataFrame,
    output_dir: str | Path,
    *,
    filename: str = "group_mean_heatmap.png",
    title: str = "Grouped pathway activity heatmap",
) -> Path | None:
    """Plot grouped mean pathway scores as a heatmap."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    if group_means_df.empty:
        return None

    apply_singlecell_theme()
    shown = group_means_df.iloc[:, : min(18, group_means_df.shape[1])].copy()
    if shown.shape[1] > 1:
        shown = shown.loc[:, shown.abs().mean(axis=0).sort_values(ascending=False).index.tolist()]
    fig_height = max(4.8, 0.42 * shown.shape[0] + 2.4)
    fig_width = max(8.8, 0.48 * shown.shape[1] + 3.2)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    sns.heatmap(
        shown,
        cmap="RdBu_r",
        center=0,
        linewidths=0.35,
        linecolor="white",
        cbar_kws={"label": "Mean pathway score"},
        ax=ax,
    )
    ax.set_xlabel("Gene set")
    ax.set_ylabel("Group")
    ax.set_title(title, fontsize=17, pad=12)
    ax.set_xticklabels(_wrap_labels(shown.columns), rotation=40, ha="right")
    ax.set_yticklabels([str(value) for value in shown.index], rotation=0)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_group_mean_dotplot(
    group_means_df: pd.DataFrame,
    group_high_fraction_df: pd.DataFrame,
    output_dir: str | Path,
    *,
    filename: str = "group_mean_dotplot.png",
    title: str = "Grouped pathway activity dotplot",
) -> Path | None:
    """Plot grouped pathway scores with color as mean and size as high-score fraction."""
    import matplotlib.pyplot as plt

    if group_means_df.empty or group_high_fraction_df.empty:
        return None

    common_groups = [group for group in group_means_df.index if group in group_high_fraction_df.index]
    common_terms = [term for term in group_means_df.columns if term in group_high_fraction_df.columns]
    if not common_groups or not common_terms:
        return None

    mean_df = group_means_df.loc[common_groups, common_terms].copy()
    frac_df = group_high_fraction_df.loc[common_groups, common_terms].copy()
    ordered_terms = mean_df.abs().mean(axis=0).sort_values(ascending=False).index.tolist()
    mean_df = mean_df.loc[:, ordered_terms]
    frac_df = frac_df.loc[:, ordered_terms]
    common_terms = ordered_terms

    apply_singlecell_theme()
    fig_width = max(9.2, 0.55 * len(common_terms) + 2.5)
    fig_height = max(4.8, 0.45 * len(common_groups) + 2.2)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    xs: list[int] = []
    ys: list[int] = []
    colors: list[float] = []
    sizes: list[float] = []
    for yi, group in enumerate(common_groups):
        for xi, term in enumerate(common_terms):
            xs.append(xi)
            ys.append(yi)
            colors.append(float(mean_df.loc[group, term]))
            sizes.append(max(18.0, float(frac_df.loc[group, term]) * 220.0))

    scatter = ax.scatter(
        xs,
        ys,
        c=colors,
        s=sizes,
        cmap="RdBu_r",
        edgecolors="white",
        linewidths=0.6,
        alpha=0.95,
    )
    ax.set_xticks(range(len(common_terms)))
    ax.set_xticklabels(_wrap_labels(common_terms), rotation=38, ha="right")
    ax.set_yticks(range(len(common_groups)))
    ax.set_yticklabels([str(group) for group in common_groups])
    ax.set_xlabel("Gene set")
    ax.set_ylabel("Group")
    ax.set_title(title, fontsize=17, pad=12)
    fig.colorbar(scatter, ax=ax, shrink=0.85, label="Mean pathway score")
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_pathway_score_distributions(
    score_long_df: pd.DataFrame,
    output_dir: str | Path,
    *,
    filename: str = "top_pathway_distributions.png",
    title: str = "Top pathway score distributions",
) -> Path | None:
    """Plot grouped score distributions for a small set of top pathways."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    if score_long_df.empty:
        return None

    apply_singlecell_theme()
    pathways = list(dict.fromkeys(score_long_df["gene_set"].astype(str)))[:4]
    plot_df = score_long_df[score_long_df["gene_set"].astype(str).isin(pathways)].copy()
    if plot_df.empty:
        return None

    n_panels = len(pathways)
    fig, axes = plt.subplots(1, n_panels, figsize=(4.8 * n_panels, 5.0), squeeze=False)
    for ax, pathway in zip(axes[0], pathways):
        subset = plot_df[plot_df["gene_set"].astype(str) == pathway].copy()
        x_key = "group" if "group" in subset.columns and subset["group"].nunique() > 1 else None
        if x_key:
            groups = subset["group"].astype(str).unique().tolist()
            palette = make_categorical_palette(groups)
            ymin = float(pd.to_numeric(subset["score"], errors="coerce").min())
            ymax = float(pd.to_numeric(subset["score"], errors="coerce").max())
            y_margin = max(0.05, (ymax - ymin) * 0.08 if np.isfinite(ymax - ymin) else 0.05)
            sns.violinplot(
                data=subset,
                x="group",
                y="score",
                hue="group",
                order=groups,
                palette=palette,
                dodge=False,
                legend=False,
                inner=None,
                cut=2,
                bw_adjust=0.85,
                density_norm="area",
                gridsize=256,
                linewidth=1.0,
                saturation=0.95,
                ax=ax,
            )
            ax.set_xlabel("Group")
            ax.set_xticks(range(len(groups)))
            ax.set_xticklabels(_wrap_labels(groups, width=12), rotation=28, ha="right")
            ax.set_ylim(ymin - y_margin, ymax + y_margin)
        else:
            sns.histplot(data=subset, x="score", bins=24, color=QC_PALETTE["bar"], alpha=0.82, ax=ax)
            ax.set_xlabel("Score")
        ax.set_ylabel("Pathway score")
        ax.set_title(fill(str(pathway), width=24), fontsize=12, pad=8)
    fig.suptitle(title, fontsize=17, y=1.02)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_enrichment_embedding_panels(
    adata,
    output_dir: str | Path,
    *,
    obsm_key: str,
    score_columns: Sequence[str],
    score_labels: dict[str, str] | None = None,
    filename: str = "embedding_top_pathways.png",
    title: str = "Top pathway scores on embedding",
) -> Path | None:
    """Project the strongest pathway scores onto an embedding."""
    import matplotlib.pyplot as plt

    if obsm_key not in adata.obsm or not score_columns:
        return None

    coords = np.asarray(adata.obsm[obsm_key])
    if coords.shape[1] < 2:
        return None

    available = [column for column in score_columns if column in adata.obs.columns]
    if not available:
        return None

    xlab, ylab = embedding_axis_labels(obsm_key)
    top_columns = available[: min(4, len(available))]
    apply_singlecell_theme()
    n_panels = len(top_columns)
    n_cols = 2 if n_panels > 1 else 1
    n_rows = int(np.ceil(n_panels / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(6.0 * n_cols, 5.3 * n_rows), squeeze=False)

    for ax, column in zip(axes.ravel(), top_columns):
        values = pd.to_numeric(adata.obs[column], errors="coerce")
        mask = np.isfinite(values.to_numpy())
        scatter = ax.scatter(
            coords[mask, 0],
            coords[mask, 1],
            c=values.to_numpy()[mask],
            s=11,
            cmap="viridis",
            linewidths=0,
            alpha=0.88,
        )
        label = score_labels.get(column, column) if score_labels else column
        label = str(label).replace("enrich__", "")
        ax.set_title(fill(label, width=24), fontsize=12, pad=8)
        ax.set_xlabel(xlab)
        ax.set_ylabel(ylab)
        fig.colorbar(scatter, ax=ax, shrink=0.82)

    for ax in axes.ravel()[len(top_columns):]:
        ax.axis("off")

    fig.suptitle(title, fontsize=17, y=1.01)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)
