"""
Visualization for upstream regulator analysis results.

Generates 4-panel publication-quality figure:
1. Top Regulators bar chart (regulatory score, colored by direction)
2. Target-DE Overlap stacked bars (up/down/unchanged per TF)
3. Evidence Scatter (ChIP enrichment vs Fisher p, sized by concordance)
4. Regulatory Heatmap (seaborn clustermap, TFs x metrics)
"""

import os

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# --- Theme setup per CLAUDE.md standard ---
sns.set_style("ticks")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Helvetica"]


# Direction color palette
_DIRECTION_COLORS = {
    "activator": "#E74C3C",
    "repressor": "#2E86C1",
    "mixed": "#95A5A6",
}


def _save_plot(fig, base_path, dpi=300):
    """Save a matplotlib figure to PNG + SVG with graceful fallback."""
    png_path = base_path + ".png"
    svg_path = base_path + ".svg"

    fig.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    print(f"   Saved: {png_path}")
    try:
        fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
        print(f"   Saved: {svg_path}")
    except Exception:
        print("   (SVG export failed, PNG available)")
    plt.close(fig)


def _plot_top_regulators(regulon_scores, top_n=15):
    """Panel 1: Top regulators ranked by regulatory score, colored by direction."""
    df = regulon_scores.head(top_n).copy()
    if len(df) == 0:
        return None

    # Reverse for top-at-top horizontal bar
    df = df.iloc[::-1].reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, max(6, top_n * 0.4)))
    colors = [_DIRECTION_COLORS.get(d, "#95A5A6") for d in df["direction"]]
    bars = ax.barh(df["tf"], df["regulatory_score"], color=colors, height=0.7)

    # Add concordance labels
    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(
            row["regulatory_score"] + df["regulatory_score"].max() * 0.02,
            i, f"{row['concordance']:.0%}",
            va="center", fontsize=8,
        )

    ax.set_xlabel("Regulatory Score", fontsize=11)
    ax.set_title("Top Upstream Regulators", fontsize=14, fontweight="bold")
    sns.despine(ax=ax)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=_DIRECTION_COLORS["activator"], label="Activator"),
        Patch(facecolor=_DIRECTION_COLORS["repressor"], label="Repressor"),
        Patch(facecolor=_DIRECTION_COLORS["mixed"], label="Mixed"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", frameon=True)

    fig.tight_layout()
    return fig


def _plot_target_overlap(regulon_scores, top_n=15):
    """Panel 2: Stacked bar showing TF targets classified as up/down/unchanged."""
    df = regulon_scores.head(top_n).copy()
    if len(df) == 0:
        return None

    # Compute unchanged count
    df["n_targets_unchanged"] = df["n_targets_in_background"] - df["n_targets_de_total"]

    # Reverse for top-at-top
    df = df.iloc[::-1].reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, max(6, top_n * 0.4)))

    ax.barh(df["tf"], df["n_targets_de_up"], color="#E74C3C", height=0.7, label="DE Up")
    ax.barh(df["tf"], df["n_targets_de_down"], left=df["n_targets_de_up"],
            color="#2E86C1", height=0.7, label="DE Down")
    ax.barh(df["tf"], df["n_targets_unchanged"],
            left=df["n_targets_de_up"] + df["n_targets_de_down"],
            color="#D5D8DC", height=0.7, label="Not DE")

    ax.set_xlabel("Number of Target Genes", fontsize=11)
    ax.set_title("TF Target Overlap with DE Genes", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", frameon=True)
    sns.despine(ax=ax)

    fig.tight_layout()
    return fig


def _plot_evidence_scatter(regulon_scores):
    """Panel 3: ChIP enrichment vs target overlap significance, sized by concordance."""
    df = regulon_scores.copy()
    if len(df) == 0:
        return None

    df["neg_log10_fisher"] = -np.log10(df["fisher_pvalue"] + 1e-300)
    df["neg_log10_chip_q"] = -np.log10(df["chip_best_qvalue"] + 1e-300)

    # Cap extreme values for display
    cap = 50
    df["neg_log10_fisher"] = df["neg_log10_fisher"].clip(upper=cap)
    df["neg_log10_chip_q"] = df["neg_log10_chip_q"].clip(upper=cap)

    fig, ax = plt.subplots(figsize=(10, 8))

    for direction, color in _DIRECTION_COLORS.items():
        mask = df["direction"] == direction
        if mask.sum() == 0:
            continue
        subset = df[mask]
        ax.scatter(
            subset["neg_log10_chip_q"],
            subset["neg_log10_fisher"],
            s=subset["concordance"] * 200,
            c=color,
            alpha=0.7,
            label=direction.capitalize(),
            edgecolors="white",
            linewidth=0.5,
        )

    # Label top 5 TFs
    for _, row in df.head(5).iterrows():
        ax.annotate(
            row["tf"],
            (row["neg_log10_chip_q"], row["neg_log10_fisher"]),
            textcoords="offset points", xytext=(5, 5),
            fontsize=8,
        )

    ax.set_xlabel("-log10(ChIP Enrichment Q-value)", fontsize=11)
    ax.set_ylabel("-log10(Fisher's P-value)", fontsize=11)
    ax.set_title("Evidence Integration", fontsize=14, fontweight="bold")
    ax.legend(title="Direction", frameon=True)
    sns.despine(ax=ax)

    fig.tight_layout()
    return fig


def _plot_regulatory_heatmap(regulon_scores, top_n=15):
    """Panel 4: Seaborn clustermap of TFs x z-scored metrics."""
    df = regulon_scores.head(top_n).copy()
    if len(df) == 0 or len(df) < 2:
        return None

    # Select metrics for heatmap
    metrics = ["regulatory_score", "concordance", "pct_targets_de"]

    # Add log-transformed values
    df["neg_log10_fisher"] = -np.log10(df["fisher_pvalue"].clip(lower=1e-300))
    df["neg_log10_chip_q"] = -np.log10(df["chip_best_qvalue"].clip(lower=1e-300))
    metrics.extend(["neg_log10_fisher", "neg_log10_chip_q"])

    # Build matrix
    mat = df.set_index("tf")[metrics].copy()
    mat.columns = ["Reg. Score", "Concordance", "% Targets DE",
                    "-log10(Fisher P)", "-log10(ChIP Q)"]

    # Z-score each column for comparable scaling
    mat_z = (mat - mat.mean()) / mat.std().replace(0, 1)

    # Create clustermap
    g = sns.clustermap(
        mat_z,
        cmap="RdBu_r",
        center=0,
        figsize=(10, max(6, len(df) * 0.4)),
        cbar_kws={"label": "Z-score"},
        dendrogram_ratio=0.1,
        linewidths=0.5,
        row_cluster=len(df) >= 3,
        col_cluster=False,
    )
    g.ax_heatmap.set_ylabel("")
    g.fig.suptitle("Regulatory Evidence Heatmap", y=1.02, fontsize=14, fontweight="bold")
    plt.setp(g.ax_heatmap.get_xticklabels(), rotation=45, ha="right", fontsize=9)
    plt.setp(g.ax_heatmap.get_yticklabels(), fontsize=9)

    return g.fig


def generate_all_plots(results, output_dir="regulator_results", top_n=15):
    """
    Generate all upstream regulator visualizations.

    Parameters
    ----------
    results : dict
        Output from run_integration_workflow().
    output_dir : str
        Output directory for plots.
    top_n : int
        Number of top TFs to show in plots.
    """
    os.makedirs(output_dir, exist_ok=True)

    regulon_scores = results["regulon_scores"]
    if len(regulon_scores) == 0:
        print("   No regulons to plot. Skipping visualization.")
        print("✓ All visualizations generated successfully!")
        return

    prefix = os.path.join(output_dir, "upstream_regulators")

    # Panel 1: Top Regulators
    print("\n   Panel 1: Top regulators bar chart")
    p1 = _plot_top_regulators(regulon_scores, top_n=top_n)
    if p1 is not None:
        _save_plot(p1, prefix + "_top_regulators")

    # Panel 2: Target-DE Overlap
    print("   Panel 2: Target-DE overlap")
    p2 = _plot_target_overlap(regulon_scores, top_n=top_n)
    if p2 is not None:
        _save_plot(p2, prefix + "_target_overlap")

    # Panel 3: Evidence Scatter
    print("   Panel 3: Evidence scatter")
    p3 = _plot_evidence_scatter(regulon_scores)
    if p3 is not None:
        _save_plot(p3, prefix + "_evidence_scatter")

    # Panel 4: Regulatory Heatmap
    print("   Panel 4: Regulatory heatmap")
    p4 = _plot_regulatory_heatmap(regulon_scores, top_n=top_n)
    if p4 is not None:
        _save_plot(p4, prefix + "_heatmap")

    print("\n✓ All visualizations generated successfully!")

