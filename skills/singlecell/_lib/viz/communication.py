"""Visualization helpers for single-cell cell-cell communication outputs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from .core import QC_PALETTE, apply_singlecell_theme, save_figure

logger = logging.getLogger(__name__)


def _coerce_lr_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if frame.empty:
        return frame
    for col in ("source", "target", "ligand", "receptor", "pathway"):
        if col in frame.columns:
            frame[col] = frame[col].astype(str)
    if "score" in frame.columns:
        frame["score"] = pd.to_numeric(frame["score"], errors="coerce").fillna(0.0)
    if "pvalue" in frame.columns:
        frame["pvalue"] = pd.to_numeric(frame["pvalue"], errors="coerce")
    return frame


def plot_interaction_heatmap(
    lr_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "interaction_heatmap.png",
) -> Path | None:
    """Plot mean interaction strength across sender/receiver groups."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    frame = _coerce_lr_frame(lr_df)
    if frame.empty:
        return None
    matrix = frame.groupby(["source", "target"])["score"].mean().unstack(fill_value=0.0)
    if matrix.empty:
        return None

    apply_singlecell_theme()
    fig, ax = plt.subplots(
        figsize=(max(7.2, 0.8 * len(matrix.columns) + 2.5), max(5.2, 0.6 * len(matrix.index) + 2.0))
    )
    sns.heatmap(
        matrix,
        cmap="YlOrRd",
        linewidths=0.4,
        linecolor="white",
        cbar_kws={"label": "Mean interaction score"},
        ax=ax,
    )
    ax.set_xlabel("Receiver group")
    ax.set_ylabel("Sender group")
    ax.set_title("Mean communication strength", fontsize=17, pad=14)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_top_interactions_bar(
    lr_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    top_n: int = 15,
    filename: str = "top_interactions.png",
) -> Path | None:
    """Plot top ligand-receptor interactions."""
    import matplotlib.pyplot as plt

    frame = _coerce_lr_frame(lr_df)
    if frame.empty:
        return None
    bar = frame.head(top_n).copy()
    bar["label"] = [
        f"{row.source} -> {row.target}\n{row.ligand}-{row.receptor}"
        for row in bar.itertuples()
    ]
    bar = bar.iloc[::-1]

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(10.5, max(5.0, 0.48 * len(bar) + 1.2)))
    palette = plt.cm.OrRd(np.linspace(0.45, 0.9, len(bar)))
    ax.barh(bar["label"], bar["score"], color=palette, edgecolor="white")
    ax.set_xlabel("Interaction score")
    ax.set_ylabel("")
    ax.set_title("Top ligand-receptor interactions", fontsize=17, pad=14)
    xmax = max(float(bar["score"].max()), 1.0)
    ax.set_xlim(0, xmax * 1.14)
    for idx, (_, row) in enumerate(bar.iterrows()):
        ax.text(
            row["score"] + xmax * 0.015,
            idx,
            f"{row['score']:.2f}",
            va="center",
            fontsize=9,
            color="#334155",
        )
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_interaction_dotplot(
    lr_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    top_n: int = 20,
    filename: str = "interaction_dotplot.png",
) -> Path | None:
    """Plot top interaction pairs across sender-receiver groups as a dotplot."""
    import matplotlib.pyplot as plt

    frame = _coerce_lr_frame(lr_df)
    if frame.empty:
        return None
    top = frame.head(top_n).copy()
    top["pair"] = top["ligand"].astype(str) + "-" + top["receptor"].astype(str)
    top["group_pair"] = top["source"].astype(str) + " -> " + top["target"].astype(str)
    if top["pair"].nunique() == 1 or top["group_pair"].nunique() == 1:
        return None

    pairs = list(top["pair"].astype(str).unique())
    group_pairs = list(top["group_pair"].astype(str).unique())
    x_lookup = {label: idx for idx, label in enumerate(group_pairs)}
    y_lookup = {label: idx for idx, label in enumerate(pairs)}
    score = top["score"].to_numpy(dtype=float)
    score_abs = np.abs(score)
    sizes = 80 + (score_abs / max(score_abs.max(), 1e-8)) * 360

    apply_singlecell_theme()
    fig, ax = plt.subplots(
        figsize=(max(8.8, 0.65 * len(group_pairs) + 3.0), max(5.0, 0.45 * len(pairs) + 2.5))
    )
    scatter = ax.scatter(
        [x_lookup[val] for val in top["group_pair"]],
        [y_lookup[val] for val in top["pair"]],
        s=sizes,
        c=score,
        cmap="OrRd",
        alpha=0.95,
        edgecolors="white",
        linewidths=0.6,
    )
    ax.set_xticks(range(len(group_pairs)))
    ax.set_xticklabels(group_pairs, rotation=35, ha="right")
    ax.set_yticks(range(len(pairs)))
    ax.set_yticklabels(pairs)
    ax.set_xlabel("Sender -> receiver")
    ax.set_ylabel("Ligand-receptor pair")
    ax.set_title("Top interaction dotplot", fontsize=17, pad=14)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Interaction score")
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_source_target_bubble(
    sender_receiver_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "source_target_bubble.png",
) -> Path | None:
    """Plot sender/receiver interaction counts and mean scores as a bubble grid."""
    import matplotlib.pyplot as plt

    frame = sender_receiver_df.copy()
    if frame.empty:
        return None
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce").fillna(0.0)
    frame["n_interactions"] = pd.to_numeric(frame["n_interactions"], errors="coerce").fillna(0.0)

    senders = list(pd.Index(frame["source"]).astype(str).unique())
    targets = list(pd.Index(frame["target"]).astype(str).unique())
    x_lookup = {label: idx for idx, label in enumerate(targets)}
    y_lookup = {label: idx for idx, label in enumerate(senders)}
    sizes = np.clip(frame["n_interactions"].to_numpy(), 1.0, None)
    sizes = 80 + (sizes / sizes.max()) * 520 if sizes.size else sizes

    apply_singlecell_theme()
    fig, ax = plt.subplots(
        figsize=(max(7.0, 0.85 * len(targets) + 2.4), max(5.2, 0.68 * len(senders) + 1.8))
    )
    scatter = ax.scatter(
        [x_lookup[str(value)] for value in frame["target"]],
        [y_lookup[str(value)] for value in frame["source"]],
        s=sizes,
        c=frame["score"],
        cmap="YlOrRd",
        alpha=0.92,
        edgecolors="white",
        linewidths=0.7,
    )
    ax.set_xticks(range(len(targets)))
    ax.set_xticklabels(targets, rotation=35, ha="right")
    ax.set_yticks(range(len(senders)))
    ax.set_yticklabels(senders)
    ax.set_xlabel("Receiver group")
    ax.set_ylabel("Sender group")
    ax.set_title("Sender-receiver summary", fontsize=17, pad=14)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Mean interaction score")
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_group_role_summary(
    role_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "group_role_summary.png",
) -> Path | None:
    """Plot outgoing vs incoming communication strength by group."""
    import matplotlib.pyplot as plt

    frame = role_df.copy()
    if frame.empty:
        return None
    frame["outgoing_score"] = pd.to_numeric(frame["outgoing_score"], errors="coerce").fillna(0.0)
    frame["incoming_score"] = pd.to_numeric(frame["incoming_score"], errors="coerce").fillna(0.0)
    frame["cell_type"] = frame["cell_type"].astype(str)

    apply_singlecell_theme()
    width = max(7.2, 0.68 * len(frame) + 3.4)
    fig, axes = plt.subplots(1, 2, figsize=(width, 5.4), sharey=True)
    frame_sorted = frame.sort_values("outgoing_score", ascending=True)
    axes[0].barh(frame_sorted["cell_type"], frame_sorted["outgoing_score"], color="#D97706", alpha=0.92)
    axes[0].set_title("Outgoing strength", fontsize=15, pad=10)
    axes[0].set_xlabel("Score")
    axes[0].set_ylabel("")

    frame_sorted_in = frame.sort_values("incoming_score", ascending=True)
    axes[1].barh(frame_sorted_in["cell_type"], frame_sorted_in["incoming_score"], color="#2563EB", alpha=0.92)
    axes[1].set_title("Incoming strength", fontsize=15, pad=10)
    axes[1].set_xlabel("Score")
    axes[1].set_ylabel("")
    fig.suptitle("Communication roles by group", fontsize=18, y=1.02)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_cellchat_count_weight_heatmaps(
    count_matrix_df: pd.DataFrame,
    weight_matrix_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "cellchat_count_vs_strength.png",
) -> Path | None:
    """Plot CellChat interaction number and strength side by side."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    if count_matrix_df.empty or weight_matrix_df.empty:
        return None
    count = count_matrix_df.copy()
    weight = weight_matrix_df.copy()
    if count.index.name is None:
        count.index = count.index.astype(str)
    if weight.index.name is None:
        weight.index = weight.index.astype(str)
    apply_singlecell_theme()
    fig, axes = plt.subplots(1, 2, figsize=(13.2, max(5.8, 0.55 * len(count.index) + 2.0)))
    sns.heatmap(count, cmap="Blues", linewidths=0.3, linecolor="white", cbar_kws={"label": "Interaction count"}, ax=axes[0])
    axes[0].set_title("Interaction number", fontsize=15, pad=10)
    axes[0].set_xlabel("Receiver group")
    axes[0].set_ylabel("Sender group")

    sns.heatmap(weight, cmap="YlOrRd", linewidths=0.3, linecolor="white", cbar_kws={"label": "Interaction strength"}, ax=axes[1])
    axes[1].set_title("Interaction strength", fontsize=15, pad=10)
    axes[1].set_xlabel("Receiver group")
    axes[1].set_ylabel("")
    fig.suptitle("CellChat communication overview", fontsize=18, y=1.02)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_pathway_summary(
    pathway_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    top_n: int = 15,
    filename: str = "pathway_summary.png",
) -> Path | None:
    """Plot top communication pathways."""
    import matplotlib.pyplot as plt

    frame = pathway_df.copy()
    if frame.empty or "pathway" not in frame.columns:
        return None
    score_col = "score" if "score" in frame.columns else "prob"
    frame[score_col] = pd.to_numeric(frame[score_col], errors="coerce").fillna(0.0)
    top = (
        frame.groupby("pathway", as_index=False)[score_col]
        .mean()
        .sort_values(score_col, ascending=False)
        .head(top_n)
        .iloc[::-1]
    )
    if top.empty:
        return None

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(9.2, max(4.8, 0.42 * len(top) + 1.4)))
    ax.barh(top["pathway"].astype(str), top[score_col], color=QC_PALETTE["bar"], alpha=0.92)
    ax.set_xlabel("Mean pathway score")
    ax.set_ylabel("")
    ax.set_title("Top communication pathways", fontsize=17, pad=14)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_nichenet_ligands(
    ligand_activity_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "nichenet_top_ligands.png",
) -> Path | None:
    """Plot top NicheNet ligands by activity score."""
    import matplotlib.pyplot as plt

    frame = ligand_activity_df.copy()
    if frame.empty:
        return None
    ligand_col = "ligand" if "ligand" in frame.columns else "test_ligand"
    score_col = "pearson" if "pearson" in frame.columns else "score"
    frame[score_col] = pd.to_numeric(frame[score_col], errors="coerce").fillna(0.0)
    top = frame.head(15).iloc[::-1]

    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(8.6, max(4.8, 0.38 * len(top) + 1.4)))
    ax.barh(top[ligand_col].astype(str), top[score_col], color="#238B45", alpha=0.92)
    ax.set_xlabel("Ligand activity score")
    ax.set_ylabel("")
    ax.set_title("Top NicheNet ligands", fontsize=17, pad=14)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_nichenet_ligand_receptor_heatmap(
    ligand_receptor_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "nichenet_ligand_receptor_heatmap.png",
) -> Path | None:
    """Plot NicheNet prioritized ligand-receptor potential as a heatmap."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    frame = ligand_receptor_df.copy()
    if frame.empty:
        return None
    ligand_col = "ligand" if "ligand" in frame.columns else "from"
    receptor_col = "receptor" if "receptor" in frame.columns else "to"
    score_col = "weight" if "weight" in frame.columns else ("score" if "score" in frame.columns else None)
    if score_col is None:
        return None
    frame[score_col] = pd.to_numeric(frame[score_col], errors="coerce").fillna(0.0)
    top_ligands = list(frame.groupby(ligand_col)[score_col].max().sort_values(ascending=False).head(10).index.astype(str))
    top_receptors = list(frame.groupby(receptor_col)[score_col].max().sort_values(ascending=False).head(12).index.astype(str))
    sub = frame[
        frame[ligand_col].astype(str).isin(top_ligands)
        & frame[receptor_col].astype(str).isin(top_receptors)
    ].copy()
    if sub.empty:
        return None
    matrix = (
        sub.groupby([ligand_col, receptor_col])[score_col]
        .max()
        .unstack(fill_value=0.0)
        .reindex(index=top_ligands, columns=top_receptors, fill_value=0.0)
    )
    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(max(8.5, 0.55 * len(matrix.columns) + 3.0), max(5.6, 0.4 * len(matrix.index) + 2.0)))
    sns.heatmap(matrix, cmap="magma", linewidths=0.35, linecolor="white", cbar_kws={"label": "Prior interaction potential"}, ax=ax)
    ax.set_xlabel("Receiver-expressed receptor")
    ax.set_ylabel("Prioritized ligand")
    ax.set_title("NicheNet ligand-receptor heatmap", fontsize=17, pad=14)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)


def plot_nichenet_ligand_target_heatmap(
    ligand_target_links_df: pd.DataFrame,
    output_dir: Union[str, Path],
    *,
    filename: str = "nichenet_ligand_target_heatmap.png",
) -> Path | None:
    """Plot top NicheNet ligand-target links."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    frame = ligand_target_links_df.copy()
    if frame.empty:
        return None
    ligand_col = "ligand"
    target_col = "target"
    score_col = "weight" if "weight" in frame.columns else ("score" if "score" in frame.columns else None)
    if score_col is None:
        return None
    frame[score_col] = pd.to_numeric(frame[score_col], errors="coerce").fillna(0.0)
    top_ligands = list(frame.groupby(ligand_col)[score_col].max().sort_values(ascending=False).head(10).index.astype(str))
    top_targets = list(frame.groupby(target_col)[score_col].max().sort_values(ascending=False).head(16).index.astype(str))
    sub = frame[
        frame[ligand_col].astype(str).isin(top_ligands)
        & frame[target_col].astype(str).isin(top_targets)
    ].copy()
    if sub.empty:
        return None
    matrix = (
        sub.groupby([ligand_col, target_col])[score_col]
        .max()
        .unstack(fill_value=0.0)
        .reindex(index=top_ligands, columns=top_targets, fill_value=0.0)
    )
    apply_singlecell_theme()
    fig, ax = plt.subplots(figsize=(max(9.0, 0.45 * len(matrix.columns) + 3.2), max(5.8, 0.4 * len(matrix.index) + 2.0)))
    sns.heatmap(matrix, cmap="rocket_r", linewidths=0.35, linecolor="white", cbar_kws={"label": "Regulatory potential"}, ax=ax)
    ax.set_xlabel("Receiver target gene")
    ax.set_ylabel("Prioritized ligand")
    ax.set_title("NicheNet ligand-target heatmap", fontsize=17, pad=14)
    fig.tight_layout()
    return save_figure(fig, Path(output_dir), filename)
