"""Embedding visualization helpers shared across single-cell downstream skills."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Iterable, Sequence, Union

import numpy as np
import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure

logger = logging.getLogger(__name__)


def embedding_axis_labels(obsm_key: str) -> tuple[str, str]:
    """Return human-readable axis labels for a known embedding key."""
    key = str(obsm_key)
    if key == "X_umap":
        return "UMAP1", "UMAP2"
    if key == "X_tsne":
        return "t-SNE1", "t-SNE2"
    if key == "X_diffmap":
        return "DC1", "DC2"
    if key == "X_phate":
        return "PHATE1", "PHATE2"
    return "Dim1", "Dim2"


def make_categorical_palette(values: Iterable[str]) -> dict[str, str]:
    """Build a stable categorical palette for cluster-like labels."""
    from matplotlib.colors import to_hex
    import seaborn as sns

    unique_values = list(dict.fromkeys(str(v) for v in values))
    if not unique_values:
        return {}

    # Keep binary doublet-style labels visually far apart instead of relying on tab20 ordering.
    normalized = {value.lower() for value in unique_values}
    if normalized <= {"singlet", "doublet"} and normalized:
        palette = {
            "Singlet": "#2B6CB0",
            "Doublet": "#D1495B",
            "singlet": "#2B6CB0",
            "doublet": "#D1495B",
        }
        return {value: palette.get(value, palette.get(value.lower(), "#2B6CB0")) for value in unique_values}

    base = sns.color_palette("tab20", min(len(unique_values), 20))
    if len(unique_values) > 20:
        extra = sns.color_palette("husl", len(unique_values))
        base = extra

    return {value: to_hex(color) for value, color in zip(unique_values, base)}


def _build_embedding_frame(adata, obsm_key: str, extra_obs: Sequence[str] | None = None) -> pd.DataFrame:
    coords = np.asarray(adata.obsm[obsm_key])
    if coords.shape[1] < 2:
        raise ValueError(f"{obsm_key} has fewer than 2 dimensions and cannot be plotted.")

    xlab, ylab = embedding_axis_labels(obsm_key)
    frame = pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            xlab: coords[:, 0],
            ylab: coords[:, 1],
        }
    )
    for key in extra_obs or ():
        if key in adata.obs.columns:
            frame[key] = adata.obs[key].astype(str).to_numpy()
    return frame


def _add_centroid_labels(ax, frame: pd.DataFrame, xcol: str, ycol: str, group_col: str) -> None:
    grouped = frame.groupby(group_col, sort=False)
    if grouped.ngroups == 0 or grouped.ngroups > 25:
        return

    for group_name, grp in grouped:
        if grp.empty:
            continue
        x = float(grp[xcol].median())
        y = float(grp[ycol].median())
        ax.text(
            x,
            y,
            str(group_name),
            fontsize=10,
            weight="semibold",
            ha="center",
            va="center",
            color="#111111",
            bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": "none", "alpha": 0.78},
            zorder=5,
        )


def plot_embedding_categorical(
    adata,
    output_dir: Union[str, Path],
    *,
    obsm_key: str,
    color_key: str,
    filename: str,
    title: str,
    subtitle: str | None = None,
    point_size: float = 11,
    alpha: float = 0.85,
    label_on_data: bool = True,
    legend: bool = True,
) -> Path | None:
    """Plot one embedding colored by a categorical obs column."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if obsm_key not in adata.obsm or color_key not in adata.obs.columns:
        logger.warning("Skipping %s because %s or %s is missing.", filename, obsm_key, color_key)
        return None

    apply_singlecell_theme()
    frame = _build_embedding_frame(adata, obsm_key, [color_key])
    xcol, ycol = embedding_axis_labels(obsm_key)
    palette = make_categorical_palette(frame[color_key].tolist())

    n_groups = frame[color_key].nunique(dropna=False)
    legend_cols = 1 if n_groups <= 12 else 2
    width = 8.2 if n_groups <= 12 else 9.4
    fig, ax = plt.subplots(figsize=(width, 6.4))

    sns.scatterplot(
        data=frame,
        x=xcol,
        y=ycol,
        hue=color_key,
        palette=palette,
        s=point_size,
        linewidth=0,
        alpha=alpha,
        ax=ax,
        legend=legend,
    )
    ax.set_title(title, fontsize=17, pad=14)
    if subtitle:
        fig.text(0.125, 0.965, subtitle, fontsize=10, color="#4A5568", ha="left", va="top")
    ax.set_xlabel(xcol)
    ax.set_ylabel(ycol)

    if label_on_data:
        _add_centroid_labels(ax, frame, xcol, ycol, color_key)

    if legend and ax.get_legend() is not None:
        legend_obj = ax.get_legend()
        legend_obj.set_title(color_key)
        legend_obj.set_bbox_to_anchor((1.02, 1.0))
        legend_obj._loc = 2  # upper left
        legend_obj.set_frame_on(False)
        if legend_cols > 1:
            legend_obj.set_ncols(legend_cols)

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return save_figure(fig, output_dir, filename)


def plot_embedding_comparison(
    adata,
    output_dir: Union[str, Path],
    *,
    obsm_key: str,
    color_keys: Sequence[str],
    filename: str,
    title: str,
    point_size: float = 10,
    alpha: float = 0.82,
) -> Path | None:
    """Plot side-by-side embedding views colored by multiple obs columns."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    available_keys = [key for key in color_keys if key in adata.obs.columns]
    if obsm_key not in adata.obsm or not available_keys:
        logger.warning("Skipping %s because embedding or requested obs columns are missing.", filename)
        return None

    apply_singlecell_theme()
    frame = _build_embedding_frame(adata, obsm_key, available_keys)
    xcol, ycol = embedding_axis_labels(obsm_key)

    n_panels = len(available_keys)
    fig, axes = plt.subplots(1, n_panels, figsize=(6.3 * n_panels, 5.6), squeeze=False)

    for ax, key in zip(axes[0], available_keys):
        palette = make_categorical_palette(frame[key].tolist())
        sns.scatterplot(
            data=frame,
            x=xcol,
            y=ycol,
            hue=key,
            palette=palette,
            s=point_size,
            linewidth=0,
            alpha=alpha,
            ax=ax,
            legend=False,
        )
        ax.set_title(key, fontsize=14, pad=8)
        ax.set_xlabel(xcol)
        ax.set_ylabel(ycol)
        if frame[key].nunique(dropna=False) <= 20:
            _add_centroid_labels(ax, frame, xcol, ycol, key)

    fig.suptitle(title, fontsize=17, y=1.02)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_embedding_continuous(
    adata,
    output_dir: Union[str, Path],
    *,
    obsm_key: str,
    color_key: str,
    filename: str,
    title: str,
    subtitle: str | None = None,
    point_size: float = 11,
    alpha: float = 0.88,
    cmap: str = "viridis",
) -> Path | None:
    """Plot one embedding colored by a continuous obs column."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if obsm_key not in adata.obsm or color_key not in adata.obs.columns:
        logger.warning("Skipping %s because %s or %s is missing.", filename, obsm_key, color_key)
        return None

    values = pd.to_numeric(adata.obs[color_key], errors="coerce")
    if values.isna().all():
        logger.warning("Skipping %s because %s has no numeric values.", filename, color_key)
        return None

    apply_singlecell_theme()
    frame = _build_embedding_frame(adata, obsm_key)
    xcol, ycol = embedding_axis_labels(obsm_key)
    frame[color_key] = values.to_numpy()
    frame = frame.dropna(subset=[color_key])
    if frame.empty:
        logger.warning("Skipping %s because %s has no finite values.", filename, color_key)
        return None

    fig, ax = plt.subplots(figsize=(8.2, 6.4))
    scatter = sns.scatterplot(
        data=frame,
        x=xcol,
        y=ycol,
        hue=color_key,
        palette=cmap,
        s=point_size,
        linewidth=0,
        alpha=alpha,
        ax=ax,
        legend=False,
    )
    ax.set_title(title, fontsize=17, pad=14)
    if subtitle:
        fig.text(0.125, 0.965, subtitle, fontsize=10, color="#4A5568", ha="left", va="top")
    ax.set_xlabel(xcol)
    ax.set_ylabel(ycol)
    norm = plt.Normalize(vmin=float(frame[color_key].min()), vmax=float(frame[color_key].max()))
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.82, pad=0.02)
    cbar.set_label(color_key)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return save_figure(fig, output_dir, filename)


def plot_cluster_size_summary(
    cluster_summary_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "cluster_size_summary.png",
) -> Path | None:
    """Plot cluster sizes and proportions as a horizontal bar summary."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if cluster_summary_df.empty:
        logger.warning("Cluster summary is empty; skipping %s", filename)
        return None

    frame = cluster_summary_df.copy().sort_values("n_cells", ascending=True)
    apply_singlecell_theme()
    height = max(4.0, 0.42 * len(frame) + 1.3)
    fig, ax = plt.subplots(figsize=(8.4, height))
    bars = ax.barh(frame["cluster"].astype(str), frame["n_cells"], color=QC_PALETTE["bar"], alpha=0.92)
    ax.set_xlabel("Cells")
    ax.set_ylabel("Cluster")
    ax.set_title("Cluster size summary")

    xmax = max(frame["n_cells"].max(), 1)
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


def plot_cluster_qc_heatmap(
    cluster_qc_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "cluster_qc_heatmap.png",
) -> Path | None:
    """Plot cluster-level QC means as a compact heatmap."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if cluster_qc_df.empty:
        logger.warning("Cluster QC summary is empty; skipping %s", filename)
        return None

    value_cols = [col for col in ("mean_genes", "mean_counts", "mean_mt") if col in cluster_qc_df.columns]
    frame = cluster_qc_df[value_cols].copy()
    frame = frame.dropna(how="all")
    if frame.empty:
        logger.warning("Cluster QC values are all missing; skipping %s", filename)
        return None

    apply_singlecell_theme()
    height = max(3.8, 0.42 * len(frame) + 1.0)
    fig, ax = plt.subplots(figsize=(7.6, height))
    sns.heatmap(
        frame,
        cmap="YlGnBu",
        annot=True,
        fmt=".1f",
        linewidths=0.5,
        cbar_kws={"shrink": 0.75},
        ax=ax,
    )
    ax.set_title("Cluster-level QC overview")
    ax.set_xlabel("Metric")
    ax.set_ylabel("Cluster")
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)
