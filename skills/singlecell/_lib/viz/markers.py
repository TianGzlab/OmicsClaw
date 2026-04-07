"""Marker-specific visualization helpers for single-cell downstream skills."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure
from .embedding import make_categorical_palette

logger = logging.getLogger(__name__)


def _choose_effect_column(markers: pd.DataFrame) -> str:
    if "logfoldchanges" in markers.columns:
        valid = pd.to_numeric(markers["logfoldchanges"], errors="coerce").notna()
        if valid.any() and valid.mean() >= 0.6:
            return "logfoldchanges"
    if "scores" in markers.columns and pd.to_numeric(markers["scores"], errors="coerce").notna().any():
        return "scores"
    if "logfoldchanges" in markers.columns and pd.to_numeric(markers["logfoldchanges"], errors="coerce").notna().any():
        return "logfoldchanges"
    return "scores"


def _top_markers(markers: pd.DataFrame, n_top: int, *, group_col: str = "group") -> pd.DataFrame:
    if markers.empty or group_col not in markers.columns:
        return markers.iloc[0:0].copy()
    frame = markers.copy()
    sort_cols: list[str] = []
    ascending: list[bool] = []
    if "pvals_adj" in frame.columns and pd.to_numeric(frame["pvals_adj"], errors="coerce").notna().any():
        sort_cols.append("pvals_adj")
        ascending.append(True)
    effect_col = _choose_effect_column(frame)
    sort_cols.append(effect_col)
    ascending.append(False)
    frame = frame.sort_values(sort_cols, ascending=ascending)
    return frame.groupby(group_col, sort=False, observed=False).head(n_top).copy()


def plot_marker_cluster_summary(
    cluster_summary_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "marker_cluster_summary.png",
) -> Path | None:
    """Plot number of exported markers per cluster plus the top gene label."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    if cluster_summary_df.empty:
        logger.warning("Cluster marker summary is empty; skipping %s", filename)
        return None

    frame = cluster_summary_df.copy().sort_values("n_markers", ascending=True)
    apply_singlecell_theme()
    height = max(4.2, 0.45 * len(frame) + 1.2)
    fig, ax = plt.subplots(figsize=(8.8, height))
    use_metric = "n_markers"
    xlabel = "Marker genes exported"
    title = "Marker counts by group"
    if frame["n_markers"].nunique(dropna=False) <= 1 and "top_effect" in frame.columns:
        use_metric = "top_effect"
        xlabel = "Top marker effect"
        title = "Top marker strength by group"

    bars = ax.barh(frame["group"].astype(str), frame[use_metric], color=QC_PALETTE["bar"], alpha=0.92)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Group")
    ax.set_title(title, fontsize=17, pad=14)

    xmax = max(float(frame[use_metric].max()), 1.0)
    for bar, gene in zip(bars, frame["top_gene"].astype(str)):
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


def plot_marker_effect_summary(
    markers: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    n_top: int = 3,
    filename: str = "marker_effect_summary.png",
) -> Path | None:
    """Plot top marker effects grouped by cluster."""
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    top_df = _top_markers(markers, n_top)
    if top_df.empty or "group" not in top_df.columns or "names" not in top_df.columns:
        logger.warning("Top marker summary is empty; skipping %s", filename)
        return None

    effect_col = _choose_effect_column(top_df)
    top_df[effect_col] = pd.to_numeric(top_df[effect_col], errors="coerce")
    top_df = top_df.dropna(subset=[effect_col])
    if top_df.empty:
        return None

    top_df["label"] = top_df["group"].astype(str) + " · " + top_df["names"].astype(str)
    palette = make_categorical_palette(top_df["group"].astype(str).tolist())
    colors = [palette.get(str(group), QC_PALETTE["counts"]) for group in top_df["group"]]

    apply_singlecell_theme()
    height = max(5.0, 0.34 * len(top_df) + 1.5)
    fig, ax = plt.subplots(figsize=(9.4, height))
    bars = ax.barh(top_df["label"], top_df[effect_col], color=colors, alpha=0.95)
    ax.set_xlabel("log fold change" if effect_col == "logfoldchanges" else "ranking score")
    ax.set_ylabel("")
    ax.set_title("Top marker effects by group", fontsize=17, pad=14)

    xpad = max(abs(float(top_df[effect_col].max())), 1.0) * 0.03
    for bar, gene in zip(bars, top_df["names"].astype(str)):
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


def plot_marker_fraction_scatter(
    markers: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    n_top: int = 5,
    filename: str = "marker_fraction_scatter.png",
) -> Path | None:
    """Plot pct-in-group versus pct-out-group for top markers when available."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    required = {"pct_nz_group", "pct_nz_reference", "group", "names"}
    if not required.issubset(markers.columns):
        return None

    frame = _top_markers(markers, n_top)
    if frame.empty:
        return None

    frame["pct_nz_group"] = pd.to_numeric(frame["pct_nz_group"], errors="coerce")
    frame["pct_nz_reference"] = pd.to_numeric(frame["pct_nz_reference"], errors="coerce")
    frame = frame.dropna(subset=["pct_nz_group", "pct_nz_reference"])
    if frame.empty:
        return None
    if (
        float(frame["pct_nz_group"].max() - frame["pct_nz_group"].min()) < 0.05
        and float(frame["pct_nz_reference"].max() - frame["pct_nz_reference"].min()) < 0.05
    ):
        logger.warning("Marker prevalence scatter has too little variation; skipping %s", filename)
        return None

    effect_col = _choose_effect_column(frame)
    effect = pd.to_numeric(frame[effect_col], errors="coerce").fillna(0.0).abs()
    size = 40 + 70 * (effect / max(float(effect.max()), 1.0))

    palette = make_categorical_palette(frame["group"].astype(str).tolist())
    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(7.6, 6.2))
    sns.scatterplot(
        data=frame,
        x="pct_nz_reference",
        y="pct_nz_group",
        hue="group",
        palette=palette,
        size=size,
        sizes=(40, 120),
        linewidth=0.4,
        edgecolor="white",
        alpha=0.88,
        ax=ax,
        legend="brief",
    )
    ax.plot([0, 1], [0, 1], linestyle="--", color="#94A3B8", alpha=0.7)
    ax.set_xlabel("Fraction outside group")
    ax.set_ylabel("Fraction inside group")
    ax.set_title("Marker prevalence by group", fontsize=17, pad=14)
    if ax.get_legend() is not None:
        legend = ax.get_legend()
        legend.set_bbox_to_anchor((1.02, 1.0))
        legend._loc = 2
        legend.set_frame_on(False)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_marker_heatmap(
    adata,
    markers: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    groupby: str,
    n_top: int = 10,
    filename: str = "markers_heatmap.png",
) -> Path | None:
    """Plot a mean-expression heatmap for top markers per group."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if groupby not in adata.obs.columns or "group" not in markers.columns or "names" not in markers.columns:
        return None

    top_df = _top_markers(markers, n_top)
    genes = [gene for gene in top_df["names"].astype(str).tolist() if gene in adata.var_names]
    genes = list(dict.fromkeys(genes))
    if not genes:
        return None

    groups = [str(value) for value in pd.Index(adata.obs[groupby].astype(str)).unique().tolist()]
    mean_expr = pd.DataFrame(index=groups, columns=genes, dtype=float)
    for group in groups:
        mask = adata.obs[groupby].astype(str) == group
        subset = adata[mask, genes].X
        if hasattr(subset, "toarray"):
            subset = subset.toarray()
        mean_expr.loc[group] = np.asarray(subset).mean(axis=0)

    mean_expr = mean_expr.astype(float)
    mean_expr_z = (mean_expr - mean_expr.mean(axis=0)) / (mean_expr.std(axis=0) + 1e-8)
    apply_singlecell_theme()
    g = sns.clustermap(
        mean_expr_z.T,
        cmap="RdBu_r",
        center=0.0,
        figsize=(11.5, max(6.0, 0.18 * len(genes) + 3.4)),
        row_cluster=True,
        col_cluster=False,
        linewidths=0.25,
        cbar_kws={"label": "gene-wise z-score"},
    )
    g.ax_heatmap.set_xlabel(groupby)
    g.ax_heatmap.set_ylabel("Gene")
    g.fig.suptitle(f"Top {n_top} marker genes per {groupby}", fontsize=16, y=1.02)
    return save_figure(g.fig, output_dir, filename)


def plot_marker_dotplot(
    adata,
    markers: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    groupby: str,
    n_top: int = 5,
    filename: str = "markers_dotplot.png",
) -> Path | None:
    """Plot a custom block-ordered dotplot for top markers per group."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    output_dir = Path(output_dir)
    if groupby not in adata.obs.columns or "group" not in markers.columns or "names" not in markers.columns:
        return None

    top_df = _top_markers(markers, n_top)
    gene_blocks: list[tuple[str, list[str]]] = []
    for group, group_df in top_df.groupby("group", sort=False, observed=False):
        genes = [gene for gene in group_df["names"].astype(str).tolist() if gene in adata.var_names]
        genes = list(dict.fromkeys(genes))
        if genes:
            gene_blocks.append((str(group), genes))
    if not gene_blocks:
        return None

    apply_singlecell_theme()

    ordered_groups = [str(value) for value in pd.Index(adata.obs[groupby].astype(str)).unique().tolist()]
    gene_order: list[str] = []
    source_group_labels: list[str] = []
    block_midpoints: list[tuple[float, str]] = []
    x_cursor = 0
    for source_group, genes in gene_blocks:
        start = x_cursor
        for gene in genes:
            gene_order.append(gene)
            source_group_labels.append(source_group)
            x_cursor += 1
        block_midpoints.append(((start + x_cursor - 1) / 2.0, source_group))

    records: list[dict[str, object]] = []
    expr_cache: dict[str, np.ndarray] = {}
    pct_cache: dict[str, np.ndarray] = {}
    for gene in gene_order:
        vec = adata[:, gene].X
        if hasattr(vec, "toarray"):
            vec = vec.toarray()
        vec = np.asarray(vec).ravel()
        expr_cache[gene] = vec
        pct_cache[gene] = (vec > 0).astype(float)

    for y_group in ordered_groups:
        mask = (adata.obs[groupby].astype(str) == y_group).to_numpy()
        for x_idx, gene in enumerate(gene_order):
            expr = expr_cache[gene][mask]
            pct = pct_cache[gene][mask]
            mean_expr = float(np.mean(expr)) if expr.size else 0.0
            frac_expr = float(np.mean(pct)) if pct.size else 0.0
            records.append(
                {
                    "group": y_group,
                    "gene": gene,
                    "x": x_idx,
                    "mean_expr": mean_expr,
                    "frac_expr": frac_expr,
                }
            )

    frame = pd.DataFrame(records)
    if frame.empty:
        return None

    # Gene-wise min-max scaling makes different marker blocks comparable.
    frame["mean_expr_scaled"] = (
        frame.groupby("gene", observed=False)["mean_expr"]
        .transform(lambda s: (s - s.min()) / (s.max() - s.min() + 1e-8))
    )
    frame["size"] = 10 + 180 * frame["frac_expr"].clip(lower=0, upper=1)

    fig_width = max(12.0, 0.25 * len(gene_order) + 3.5)
    fig_height = max(5.8, 0.55 * len(ordered_groups) + 2.8)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    sns.scatterplot(
        data=frame,
        x="x",
        y="group",
        size="size",
        sizes=(10, 190),
        hue="mean_expr_scaled",
        palette="YlOrRd",
        linewidth=0.4,
        edgecolor="white",
        alpha=0.95,
        legend=False,
        ax=ax,
    )

    for split_idx in range(1, len(gene_order)):
        if source_group_labels[split_idx] != source_group_labels[split_idx - 1]:
            ax.axvline(split_idx - 0.5, color="#CBD5E1", linewidth=1.0, alpha=0.9)

    ax.set_xticks(range(len(gene_order)))
    ax.set_xticklabels(gene_order, rotation=90, fontsize=9)
    ax.set_xlabel("Top marker genes grouped by source cluster")
    ax.set_ylabel(groupby)
    ax.set_title(f"Top {n_top} markers per {groupby}", fontsize=17, pad=18)

    top_ax = ax.secondary_xaxis("top")
    top_ax.set_xticks([mid for mid, _ in block_midpoints])
    top_ax.set_xticklabels([label for _, label in block_midpoints], rotation=90, fontsize=10)
    top_ax.set_xlabel("Source cluster of selected top markers")

    # Size legend
    size_levels = [0.2, 0.4, 0.6, 0.8]
    size_handles = [
        plt.scatter([], [], s=10 + 180 * level, color="#6B7280", alpha=0.75)
        for level in size_levels
    ]
    size_labels = [f"{int(level * 100)}%" for level in size_levels]
    legend1 = ax.legend(
        size_handles,
        size_labels,
        title="Fraction of cells\nin group",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        frameon=False,
    )
    ax.add_artist(legend1)

    # Colorbar
    norm = plt.Normalize(vmin=0.0, vmax=1.0)
    sm = plt.cm.ScalarMappable(cmap="YlOrRd", norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.12)
    cbar.set_label("Mean expression\nscaled per gene")

    fig.tight_layout()
    return save_figure(fig, output_dir, filename)
