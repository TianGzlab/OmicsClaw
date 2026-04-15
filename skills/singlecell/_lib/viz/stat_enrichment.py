"""Visualization primitives for single-cell statistical enrichment."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import networkx as nx

from .core import QC_PALETTE, apply_singlecell_theme, save_figure


def _sort_groups(groups: list[str]) -> list[str]:
    def _key(item: str):
        text = str(item)
        return (0, int(text)) if text.isdigit() else (1, text)

    return sorted(groups, key=_key)


def _display_group_label(group: str) -> str:
    text = str(group)
    return f"cluster {text}" if text.isdigit() else text


def plot_enrichment_top_terms_bar(
    top_df: pd.DataFrame,
    output_dir: Path,
    *,
    filename: str = "top_terms_bar.png",
    title: str = "Top enriched terms by group",
) -> Path | None:
    if top_df.empty:
        return None
    apply_singlecell_theme()
    plot_df = top_df.copy()
    plot_df["group"] = plot_df["group"].astype(str)
    if "pvalue_adj" in plot_df.columns and plot_df["pvalue_adj"].notna().any():
        plot_df["display_score"] = -np.log10(pd.to_numeric(plot_df["pvalue_adj"], errors="coerce").clip(lower=1e-300))
        x_label = "-log10(adjusted p-value)"
    elif "nes" in plot_df.columns and plot_df["nes"].notna().any():
        plot_df["display_score"] = pd.to_numeric(plot_df["nes"], errors="coerce")
        x_label = "NES"
    else:
        plot_df["display_score"] = pd.to_numeric(plot_df.get("score"), errors="coerce")
        x_label = "Score"

    palette = sns.color_palette("tab20", n_colors=max(plot_df["group"].nunique(), 3))
    ordered_groups = _sort_groups(plot_df["group"].dropna().unique().tolist())
    group_to_color = {group: palette[idx % len(palette)] for idx, group in enumerate(ordered_groups)}
    plot_df["y_label"] = plot_df.apply(lambda row: f"{_display_group_label(row['group'])} | {row['term']}", axis=1)

    fig, ax = plt.subplots(figsize=(11, max(5.5, 0.45 * len(plot_df))))
    sns.barplot(
        data=plot_df,
        x="display_score",
        y="y_label",
        hue="group",
        dodge=False,
        palette=group_to_color,
        ax=ax,
    )
    ax.set_title(title, fontsize=18, fontweight="semibold", pad=14)
    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel("")
    ax.legend(title="Group", frameon=False, bbox_to_anchor=(1.01, 1.0), loc="upper left")
    for patch, value in zip(ax.patches, plot_df["display_score"].fillna(0.0).tolist()):
        if math.isfinite(value):
            ax.text(
                patch.get_width() + max(abs(patch.get_width()) * 0.02, 0.05),
                patch.get_y() + patch.get_height() / 2,
                f"{value:.2f}",
                va="center",
                fontsize=9,
                color="#4D4D4D",
            )
    x_min = float(pd.to_numeric(plot_df["display_score"], errors="coerce").min())
    x_max = float(pd.to_numeric(plot_df["display_score"], errors="coerce").max())
    span = max(abs(x_max - x_min), 1.0)
    ax.set_xlim(x_min - 0.08 * span, x_max + 0.18 * span)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_enrichment_group_term_dotplot(
    top_df: pd.DataFrame,
    output_dir: Path,
    *,
    filename: str = "group_term_dotplot.png",
    title: str = "Group-by-term enrichment overview",
) -> Path | None:
    if top_df.empty or "group" not in top_df.columns or "term" not in top_df.columns:
        return None
    apply_singlecell_theme()
    plot_df = top_df.copy()
    if "pvalue_adj" in plot_df.columns and plot_df["pvalue_adj"].notna().any():
        plot_df["dot_size"] = -np.log10(pd.to_numeric(plot_df["pvalue_adj"], errors="coerce").clip(lower=1e-300))
    else:
        plot_df["dot_size"] = 1.0
    if "nes" in plot_df.columns and plot_df["nes"].notna().any():
        plot_df["dot_color"] = pd.to_numeric(plot_df["nes"], errors="coerce")
        cmap = "RdBu_r"
        color_label = "NES"
    else:
        plot_df["dot_color"] = pd.to_numeric(plot_df.get("score"), errors="coerce")
        cmap = "mako"
        color_label = "Score"
    plot_df["group"] = plot_df["group"].astype(str)
    group_order = _sort_groups(plot_df["group"].dropna().unique().tolist())
    display_map = {group: _display_group_label(group) for group in group_order}
    term_order = plot_df.groupby("term")["dot_size"].max().sort_values(ascending=False).index.tolist()
    plot_df["group_display"] = plot_df["group"].map(display_map)
    group_display_order = [display_map[group] for group in group_order]
    plot_df["group_display"] = pd.Categorical(plot_df["group_display"], categories=group_display_order, ordered=True)
    plot_df["term"] = pd.Categorical(plot_df["term"], categories=term_order, ordered=True)

    fig, ax = plt.subplots(figsize=(max(8, 0.9 * len(group_order) + 5), max(5.5, 0.42 * len(term_order))))
    sns.scatterplot(
        data=plot_df,
        x="group_display",
        y="term",
        size="dot_size",
        sizes=(40, 420),
        hue="dot_color",
        palette=cmap,
        hue_norm=None,
        edgecolor="white",
        linewidth=0.6,
        ax=ax,
        legend=False,
    )
    ax.set_title(title, fontsize=18, fontweight="semibold", pad=14)
    ax.set_xlabel("Group", fontsize=12)
    ax.set_ylabel("Term", fontsize=12)
    ax.tick_params(axis="x", labelrotation=0, labelsize=10)
    ax.tick_params(axis="y", labelsize=10)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.2)
    norm = plt.Normalize(plot_df["dot_color"].min(), plot_df["dot_color"].max())
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, shrink=0.75)
    cbar.set_label(color_label)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_enrichment_group_summary(
    summary_df: pd.DataFrame,
    output_dir: Path,
    *,
    filename: str = "group_enrichment_summary.png",
    title: str = "Enrichment summary by group",
) -> Path | None:
    if summary_df.empty:
        return None
    apply_singlecell_theme()
    plot_df = summary_df.copy()
    plot_df["group"] = plot_df["group"].astype(str)
    plot_df = plot_df.set_index("group").loc[_sort_groups(plot_df["group"].tolist())].reset_index()
    plot_df["group_display"] = plot_df["group"].map(_display_group_label)
    fig, axes = plt.subplots(1, 2, figsize=(12, max(4.8, 0.55 * len(plot_df))), gridspec_kw={"width_ratios": [1.2, 1.0]})
    sns.barplot(data=plot_df, y="group_display", x="n_significant", color=QC_PALETTE["bar"], ax=axes[0])
    axes[0].set_title("Significant terms", fontsize=14, fontweight="semibold")
    axes[0].set_xlabel("Count")
    axes[0].set_ylabel("")
    sns.barplot(data=plot_df, y="group_display", x="top_abs_score", color=QC_PALETTE["accent"], ax=axes[1])
    axes[1].set_title("Top absolute effect", fontsize=14, fontweight="semibold")
    axes[1].set_xlabel("Absolute score")
    axes[1].set_ylabel("")
    fig.suptitle(title, fontsize=18, fontweight="semibold", y=1.02)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def compute_running_score_curve(
    ranking: pd.Series,
    gene_set: list[str],
    *,
    weight: float = 1.0,
) -> pd.DataFrame:
    """Compute the classic running enrichment-score curve for a ranked gene list."""
    ranking = ranking.dropna()
    ranking = ranking[~ranking.index.duplicated(keep="first")]
    genes = ranking.index.astype(str).tolist()
    scores = ranking.to_numpy(dtype=float)
    membership = np.array([gene in set(map(str, gene_set)) for gene in genes], dtype=bool)
    n_hits = int(membership.sum())
    if n_hits == 0:
        return pd.DataFrame(columns=["position", "gene", "rank_score", "hit", "running_score"])

    hit_weights = np.abs(scores[membership]) ** float(weight)
    hit_weights_sum = float(hit_weights.sum()) if float(hit_weights.sum()) > 0 else 1.0
    miss_penalty = 1.0 / max(len(genes) - n_hits, 1)
    running = []
    hit_ptr = 0
    current = 0.0
    for idx, (gene, score, is_hit) in enumerate(zip(genes, scores, membership, strict=False), start=1):
        if is_hit:
            current += hit_weights[hit_ptr] / hit_weights_sum
            hit_ptr += 1
        else:
            current -= miss_penalty
        running.append(
            {
                "position": idx,
                "gene": gene,
                "rank_score": float(score),
                "hit": bool(is_hit),
                "running_score": float(current),
            }
        )
    return pd.DataFrame(running)


def plot_gsea_running_score_panels(
    running_tables: dict[tuple[str, str], pd.DataFrame],
    output_dir: Path,
    *,
    filename: str = "gsea_running_scores.png",
    title: str = "Top GSEA running scores",
) -> Path | None:
    valid_items = [(key, table) for key, table in running_tables.items() if not table.empty]
    if not valid_items:
        return None
    apply_singlecell_theme()
    n_panels = len(valid_items)
    n_cols = min(2, n_panels)
    n_rows = math.ceil(n_panels / n_cols)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(12, 4.2 * n_rows), squeeze=False)
    axes_flat = axes.flatten()
    palette = sns.color_palette("Set2", n_colors=n_panels)

    for idx, ((group, term), table) in enumerate(valid_items):
        ax = axes_flat[idx]
        color = palette[idx % len(palette)]
        ax.plot(table["position"], table["running_score"], color=color, linewidth=2.2)
        ax.axhline(0, color="#666666", linestyle="--", linewidth=0.8, alpha=0.6)
        hit_positions = table.loc[table["hit"], "position"].to_numpy()
        if len(hit_positions):
            ymin, ymax = ax.get_ylim()
            tick_top = ymin + 0.12 * (ymax - ymin)
            ax.vlines(hit_positions, ymin=ymin, ymax=tick_top, color="#444444", linewidth=0.8, alpha=0.55)
        ax.set_title(f"{group}: {term}", fontsize=12, fontweight="semibold")
        ax.set_xlabel("Ranked gene position")
        ax.set_ylabel("Running ES")
    for ax in axes_flat[n_panels:]:
        ax.axis("off")
    fig.suptitle(title, fontsize=18, fontweight="semibold", y=1.02)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_enrichment_ridgeplot(
    top_terms_df: pd.DataFrame,
    ranking_df: pd.DataFrame,
    gene_sets: dict[str, list[str]],
    output_dir: Path,
    *,
    filename: str = "ridgeplot.png",
    title: str = "Ranking distributions for enriched terms",
) -> Path | None:
    if top_terms_df.empty or ranking_df.empty:
        return None
    apply_singlecell_theme()

    rows: list[dict[str, object]] = []
    for _, row in top_terms_df.head(8).iterrows():
        group = str(row.get("group", ""))
        term = str(row.get("term", ""))
        genes = set(map(str, gene_sets.get(term, [])))
        if not genes:
            continue
        group_df = ranking_df[ranking_df["group"].astype(str) == group].copy()
        metric = None
        for candidate in ("stat", "scores", "logfoldchanges", "log2FoldChange", "score"):
            if candidate in group_df.columns and pd.to_numeric(group_df[candidate], errors="coerce").notna().any():
                metric = candidate
                break
        if metric is None:
            continue
        hits = group_df[group_df["gene"].astype(str).isin(genes)].copy()
        if hits.empty:
            continue
        hits["value"] = pd.to_numeric(hits[metric], errors="coerce")
        hits["group_term"] = f"{_display_group_label(group)} | {term}"
        rows.extend(hits[["group_term", "value"]].dropna().to_dict(orient="records"))

    if not rows:
        return None

    plot_df = pd.DataFrame(rows)
    order = plot_df.groupby("group_term")["value"].median().sort_values(ascending=False).index.tolist()
    fig, ax = plt.subplots(figsize=(11, max(5, 0.55 * len(order))))
    sns.violinplot(
        data=plot_df,
        x="value",
        y="group_term",
        order=order,
        orient="h",
        inner=None,
        cut=0,
        linewidth=0.9,
        palette=sns.color_palette("crest", n_colors=max(len(order), 3)),
        ax=ax,
    )
    ax.axvline(0, color="#666666", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.set_title(title, fontsize=18, fontweight="semibold", pad=14)
    ax.set_xlabel("Ranking metric value")
    ax.set_ylabel("")
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_enrichment_enrichmap(
    top_terms_df: pd.DataFrame,
    gene_sets: dict[str, list[str]],
    output_dir: Path,
    *,
    filename: str = "enrichmap.png",
    title: str = "Term-overlap network",
) -> Path | None:
    if top_terms_df.empty:
        return None
    apply_singlecell_theme()

    selected = top_terms_df.head(20).copy()
    selected["term"] = selected["term"].astype(str)
    selected["group"] = selected["group"].astype(str)
    if "pvalue_adj" in selected.columns and pd.to_numeric(selected["pvalue_adj"], errors="coerce").notna().any():
        selected = selected.sort_values("pvalue_adj", ascending=True, na_position="last")
    elif "score" in selected.columns and pd.to_numeric(selected["score"], errors="coerce").notna().any():
        selected = selected.sort_values("score", key=lambda s: pd.to_numeric(s, errors="coerce").abs(), ascending=False, na_position="last")
    selected = selected.drop_duplicates(subset=["term"], keep="first").head(12)
    if len(selected) < 2:
        return None

    graph = nx.Graph()
    for _, row in selected.iterrows():
        term = str(row["term"])
        group = _display_group_label(str(row.get("group", "")))
        node_id = term
        score = float(pd.to_numeric(pd.Series([row.get("score")]), errors="coerce").fillna(0.0).iloc[0])
        graph.add_node(node_id, score=score, group=group, term=term, label=term)

    selected_records = selected.to_dict(orient="records")
    for i, row_a in enumerate(selected_records):
        node_a = str(row_a["term"])
        genes_a = set(map(str, gene_sets.get(str(row_a["term"]), [])))
        for row_b in selected_records[i + 1:]:
            node_b = str(row_b["term"])
            genes_b = set(map(str, gene_sets.get(str(row_b["term"]), [])))
            if not genes_a or not genes_b:
                continue
            overlap = len(genes_a & genes_b)
            union = len(genes_a | genes_b)
            if overlap == 0 or union == 0:
                continue
            jaccard = overlap / union
            if jaccard >= 0.1:
                graph.add_edge(node_a, node_b, weight=jaccard, overlap=overlap)

    if graph.number_of_edges() == 0:
        return None

    pos = nx.spring_layout(graph, seed=42, weight="weight")
    fig, ax = plt.subplots(figsize=(11.5, 8.5))
    node_scores = np.array([max(abs(graph.nodes[node].get("score", 0.0)), 0.1) for node in graph.nodes], dtype=float)
    node_sizes = 420 + 950 * (node_scores / max(node_scores.max(), 1.0))
    edge_widths = [1.4 + 8 * graph.edges[edge]["weight"] for edge in graph.edges]
    groups = [graph.nodes[node]["group"] for node in graph.nodes]
    unique_groups = _sort_groups(list(dict.fromkeys(groups)))
    palette = sns.color_palette("Spectral", n_colors=max(len(unique_groups), 3))
    group_to_color = {group: palette[idx % len(palette)] for idx, group in enumerate(unique_groups)}
    node_colors = [group_to_color[graph.nodes[node]["group"]] for node in graph.nodes]
    nx.draw_networkx_edges(graph, pos, width=edge_widths, alpha=0.22, edge_color="#7A7A7A", ax=ax)
    nx.draw_networkx_nodes(
        graph,
        pos,
        node_size=node_sizes,
        node_color=node_colors,
        linewidths=1.2,
        edgecolors="white",
        alpha=0.92,
        ax=ax,
    )

    texts = []
    for node, (x, y) in pos.items():
        label = graph.nodes[node]["label"]
        texts.append(
            ax.text(
                x,
                y,
                label,
                fontsize=8.6,
                fontweight="semibold",
                ha="center",
                va="center",
                color="#1F1F1F",
                bbox={
                    "boxstyle": "round,pad=0.18",
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.82,
                },
                zorder=5,
            )
        )

    try:
        from adjustText import adjust_text

        adjust_text(
            texts,
            ax=ax,
            expand=(1.15, 1.25),
            force_text=(0.45, 0.55),
            force_static=(0.25, 0.25),
            arrowprops={
                "arrowstyle": "-",
                "color": "#8A8A8A",
                "lw": 0.6,
                "alpha": 0.55,
            },
        )
    except Exception:
        pass

    legend_handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor=group_to_color[group],
            markeredgecolor="white",
            markeredgewidth=1.0,
            markersize=10,
            label=group,
        )
        for group in unique_groups
    ]
    if legend_handles:
        ax.legend(
            handles=legend_handles,
            title="Main group",
            frameon=False,
            bbox_to_anchor=(1.02, 1.0),
            loc="upper left",
        )
    ax.set_title(title, fontsize=18, fontweight="semibold", pad=14)
    ax.axis("off")
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)
