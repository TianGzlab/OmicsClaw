"""Visualization helpers for single-cell doublet detection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure

logger = logging.getLogger(__name__)


def plot_doublet_score_distribution(
    score_series,
    output_dir: Union[str, Path],
    *,
    filename: str = "doublet_score_distribution.png",
    title: str = "Doublet score distribution",
    threshold: float | None = None,
    expected_rate: float | None = None,
) -> Path | None:
    """Plot the score distribution and optional decision threshold."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    values = pd.to_numeric(pd.Series(score_series), errors="coerce").dropna()
    if values.empty:
        logger.warning("Doublet scores are empty; skipping %s", filename)
        return None

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    ax.hist(values, bins=40, color=QC_PALETTE["counts"], alpha=0.9, edgecolor="white")
    ax.set_xlabel("Doublet score")
    ax.set_ylabel("Cells")
    ax.set_title(title, fontsize=17, pad=14)

    if threshold is not None:
        ax.axvline(threshold, color="#C53030", linestyle="--", linewidth=2, label=f"threshold={threshold:.3f}")
    if expected_rate is not None:
        ax.text(
            0.98,
            0.96,
            f"expected rate: {expected_rate * 100:.1f}%",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=10,
            color="#475569",
            bbox={"boxstyle": "round,pad=0.28", "fc": "white", "ec": "#CBD5E1", "alpha": 0.92},
        )
    if threshold is not None:
        ax.legend(frameon=False, loc="upper left")

    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_doublet_call_summary(
    summary_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "doublet_call_summary.png",
) -> Path | None:
    """Plot singlet vs doublet counts and fractions."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if summary_df.empty:
        logger.warning("Doublet summary is empty; skipping %s", filename)
        return None

    frame = summary_df.copy()
    frame["classification"] = frame["classification"].astype(str)
    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    colors = [QC_PALETTE["genes"], "#C53030"]
    bars = ax.bar(frame["classification"], frame["n_cells"], color=colors[: len(frame)], alpha=0.92)
    ax.set_ylabel("Cells")
    ax.set_xlabel("")
    ax.set_title("Doublet call summary", fontsize=17, pad=14)
    ymax = max(frame["n_cells"].max(), 1)
    for bar, pct in zip(bars, frame["proportion_pct"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + ymax * 0.03,
            f"{pct:.1f}%",
            ha="center",
            va="bottom",
            fontsize=10,
            color="#334155",
        )
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_doublet_score_by_group(
    score_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    group_key: str,
    filename: str = "doublet_score_by_group.png",
) -> Path | None:
    """Plot score distributions stratified by a grouping column."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if score_df.empty or group_key not in score_df.columns or "doublet_score" not in score_df.columns:
        logger.warning("Missing grouped score inputs; skipping %s", filename)
        return None

    frame = score_df[[group_key, "doublet_score"]].copy()
    frame[group_key] = frame[group_key].astype(str)
    frame["doublet_score"] = pd.to_numeric(frame["doublet_score"], errors="coerce")
    frame = frame.dropna(subset=["doublet_score"])
    if frame.empty or frame[group_key].nunique() <= 1:
        return None

    apply_singlecell_theme()
    n_groups = frame[group_key].nunique()
    width = max(7.8, min(12.0, 0.65 * n_groups + 4.5))
    fig, ax = plt.subplots(figsize=(width, 5.4))
    sns.violinplot(
        data=frame,
        x=group_key,
        y="doublet_score",
        inner=None,
        color="#D6E4F0",
        linewidth=0.8,
        ax=ax,
    )
    sns.stripplot(
        data=frame.sample(min(len(frame), 3000), random_state=0),
        x=group_key,
        y="doublet_score",
        color=QC_PALETTE["counts"],
        alpha=0.35,
        size=2.5,
        ax=ax,
    )
    ax.set_title(f"Doublet scores by {group_key}", fontsize=17, pad=14)
    ax.set_xlabel(group_key)
    ax.set_ylabel("Doublet score")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)
