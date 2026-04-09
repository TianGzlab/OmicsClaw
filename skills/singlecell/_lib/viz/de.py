"""Differential-expression visualization helpers for single-cell downstream skills."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Union

import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure
from .embedding import make_categorical_palette

logger = logging.getLogger(__name__)


def _natural_group_order(values: list[str]) -> list[str]:
    def _key(value: str) -> tuple[int, object]:
        try:
            num = float(value)
            if num.is_integer():
                return (0, int(num))
            return (0, num)
        except Exception:
            return (1, value)

    unique = list(dict.fromkeys(str(v) for v in values))
    return sorted(unique, key=_key)


def _resolve_effect_column(frame: pd.DataFrame) -> str:
    for column in ("logfoldchanges", "log2FoldChange", "avg_log2FC", "logFC"):
        if column in frame.columns:
            valid = pd.to_numeric(frame[column], errors="coerce").notna()
            if valid.any() and valid.mean() >= 0.6:
                return column
    for column in ("scores", "stat"):
        if column in frame.columns and pd.to_numeric(frame[column], errors="coerce").notna().any():
            return column
    for column in ("logfoldchanges", "log2FoldChange", "avg_log2FC", "logFC"):
        if column in frame.columns and pd.to_numeric(frame[column], errors="coerce").notna().any():
            return column
    return "scores"


def _resolve_gene_column(frame: pd.DataFrame) -> str:
    for column in ("names", "gene"):
        if column in frame.columns:
            return column
    raise KeyError("No gene-like column found in DE results")


def plot_de_effect_summary(
    de_top: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    n_top: int = 3,
    filename: str = "de_effect_summary.png",
) -> Path | None:
    """Plot the strongest DE effect per group as a grouped bar summary."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if de_top.empty or "group" not in de_top.columns:
        return None

    frame = de_top.copy()
    effect_col = _resolve_effect_column(frame)
    gene_col = _resolve_gene_column(frame)
    frame[effect_col] = pd.to_numeric(frame[effect_col], errors="coerce")
    frame = frame.dropna(subset=[effect_col])
    if frame.empty:
        return None

    frame = frame.groupby("group", observed=False).head(n_top).copy()
    frame["label"] = frame["group"].astype(str) + " · " + frame[gene_col].astype(str)
    palette = make_categorical_palette(frame["group"].astype(str).tolist())
    colors = [palette.get(str(group), QC_PALETTE["bar"]) for group in frame["group"]]

    apply_singlecell_theme()
    height = max(4.8, 0.34 * len(frame) + 1.4)
    fig, ax = plt.subplots(figsize=(9.6, height))
    bars = ax.barh(frame["label"], frame[effect_col], color=colors, alpha=0.94)
    ax.set_xlabel("Effect size" if effect_col not in {"scores", "stat"} else "Ranking score")
    ax.set_ylabel("")
    ax.set_title(f"Top {n_top} differential genes per group", fontsize=17, pad=14)

    ordered_groups = _natural_group_order(frame["group"].astype(str).tolist())
    group_positions = {}
    for idx, label in enumerate(frame["label"].tolist()):
        group = str(label).split(" · ", 1)[0]
        group_positions.setdefault(group, []).append(idx)
    for group in ordered_groups[:-1]:
        if group in group_positions:
            split = max(group_positions[group]) + 0.5
            ax.axhline(split, color="#CBD5E1", linewidth=1.0, alpha=0.9)

    xpad = max(abs(float(frame[effect_col].max())), 1.0) * 0.03
    for bar, gene in zip(bars, frame[gene_col].astype(str)):
        ax.text(
            bar.get_width() + xpad if bar.get_width() >= 0 else bar.get_width() - xpad,
            bar.get_y() + bar.get_height() / 2,
            gene,
            va="center",
            ha="left" if bar.get_width() >= 0 else "right",
            fontsize=8.5,
            color="#1F2937",
        )
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_de_group_summary(
    summary_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "de_group_summary.png",
) -> Path | None:
    """Plot DE summary counts by group/cell type with top-gene labels."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if summary_df.empty or "group" not in summary_df.columns:
        return None

    frame = summary_df.copy()
    metric = "n_significant" if "n_significant" in frame.columns else "n_genes"
    frame = frame.sort_values(metric, ascending=True)
    apply_singlecell_theme()
    height = max(4.4, 0.42 * len(frame) + 1.1)
    fig, ax = plt.subplots(figsize=(8.8, height))
    bars = ax.barh(frame["group"].astype(str), frame[metric], color=QC_PALETTE["bar"], alpha=0.92)
    ax.set_xlabel("Significant genes" if metric == "n_significant" else "Genes tested")
    ax.set_ylabel("Group")
    ax.set_title("Differential expression summary by group", fontsize=17, pad=14)

    xmax = max(float(frame[metric].max()), 1.0)
    if "top_gene" in frame.columns:
        for bar, gene in zip(bars, frame["top_gene"].fillna("").astype(str)):
            if not gene:
                continue
            ax.text(
                bar.get_width() + xmax * 0.015,
                bar.get_y() + bar.get_height() / 2,
                gene,
                va="center",
                fontsize=9,
                color="#334155",
            )
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_de_rank_panels(
    de_top: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "rank_genes_groups.png",
) -> Path | None:
    """Plot faceted top-gene bar panels, one panel per group."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if de_top.empty or "group" not in de_top.columns:
        return None

    frame = de_top.copy()
    gene_col = _resolve_gene_column(frame)
    effect_col = _resolve_effect_column(frame)
    frame[effect_col] = pd.to_numeric(frame[effect_col], errors="coerce")
    frame = frame.dropna(subset=[effect_col])
    if frame.empty:
        return None

    ordered_groups = _natural_group_order(frame["group"].astype(str).tolist())
    n_groups = len(ordered_groups)
    ncols = min(4, max(1, n_groups))
    nrows = math.ceil(n_groups / ncols)
    apply_singlecell_theme()
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.8 * ncols, 3.6 * nrows), squeeze=False)
    palette = make_categorical_palette(ordered_groups)

    for ax in axes.ravel():
        ax.set_visible(False)

    for ax, group in zip(axes.ravel(), ordered_groups):
        ax.set_visible(True)
        subset = frame[frame["group"].astype(str) == group].copy().reset_index(drop=True)
        subset["rank"] = range(1, len(subset) + 1)
        color = palette.get(group, QC_PALETTE["accent"])
        ylabels = subset[gene_col].astype(str).tolist()
        ypos = list(range(len(subset)))
        ax.barh(ypos, subset[effect_col], color=color, alpha=0.9)
        ax.set_yticks(ypos)
        ax.set_yticklabels(ylabels, fontsize=9)
        ax.invert_yaxis()
        ax.set_title(f"{group} vs. rest", fontsize=12, pad=8)
        ax.set_xlabel("Ranking score" if effect_col in {"scores", "stat"} else "Effect")
        ax.set_ylabel("")
        ax.grid(True, axis="y", alpha=0.25)

    fig.suptitle("Top differential signals by group", fontsize=18, y=1.01)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)
