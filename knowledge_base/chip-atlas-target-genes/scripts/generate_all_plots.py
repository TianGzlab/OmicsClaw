"""
Visualization for ChIP-Atlas Target Genes results.

Generates publication-quality plots using plotnine (ggplot2) with Prism theme.
Falls back to matplotlib for plots that require it (heatmap).
"""

import os

import numpy as np
import pandas as pd

# plotnine for publication-quality ggplot2-style figures
from plotnine import (
    ggplot, aes, geom_col, geom_histogram, geom_point,
    geom_vline, geom_label, geom_text, annotate,
    labs, coord_flip, scale_fill_gradient, scale_color_manual,
    theme, element_text,
)
from plotnine_prism import theme_prism

# matplotlib + seaborn for heatmap (clustermap not available in plotnine)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns


def _base_theme():
    """Return Prism theme for all plots."""
    return theme_prism()


def _save_plot(plot, base_path, width=10, height=8, dpi=300):
    """
    Save a plotnine plot to PNG + SVG with graceful fallback.

    Args:
        plot: plotnine ggplot object OR matplotlib Figure
        base_path: Path without extension (e.g., "results/top_targets")
        width, height: Figure dimensions in inches
        dpi: Resolution for PNG
    """
    png_path = base_path + ".png"
    svg_path = base_path + ".svg"

    if hasattr(plot, "save"):
        # plotnine plot
        plot.save(png_path, dpi=dpi, width=width, height=height, verbose=False)
        print(f"   Saved: {png_path}")
        try:
            plot.save(svg_path, width=width, height=height, verbose=False)
            print(f"   Saved: {svg_path}")
        except Exception:
            print("   (SVG export failed, PNG available)")
    else:
        # matplotlib figure
        plot.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        print(f"   Saved: {png_path}")
        try:
            plot.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
            print(f"   Saved: {svg_path}")
        except Exception:
            try:
                from matplotlib.backends.backend_svg import FigureCanvasSVG
                canvas = FigureCanvasSVG(plot)
                with open(svg_path, "w") as f:
                    canvas.print_svg(f)
                print(f"   Saved: {svg_path}")
            except Exception:
                print("   (SVG export failed, PNG available)")
        plt.close(plot)


def generate_all_plots(results, output_dir="target_genes_results", top_n=25):
    """
    Generate all target genes visualizations.

    Creates publication-quality plots using plotnine with Prism theme:
    1. Top target genes barplot
    2. Binding score distribution histogram
    3. Binding heatmap (top genes x top experiments)
    4. STRING vs binding scatter (or binding rate if no STRING data)

    All plots saved in PNG + SVG with graceful fallback.

    Args:
        results: Results dict from run_target_genes_workflow()
        output_dir: Output directory for plot files
        top_n: Number of top genes to show in bar plots (default: 25)
    """
    os.makedirs(output_dir, exist_ok=True)

    target_genes = results["target_genes"]
    experiment_data = results["experiment_data"]
    protein = results["protein"]
    metadata = results["metadata"]

    base = os.path.join(output_dir, "target_genes")

    # Plot 1: Top target genes by average binding score
    _plot_top_targets(target_genes, top_n, protein, metadata, base + "_top_targets")

    # Plot 2: Score distribution histogram
    _plot_score_distribution(target_genes, protein, base + "_score_distribution")

    # Plot 3: Binding heatmap (seaborn clustermap — not available in plotnine)
    _plot_heatmap(target_genes, experiment_data, protein, base + "_heatmap")

    # Plot 4: STRING vs binding (or binding rate fallback)
    _plot_string_vs_binding(target_genes, protein, base + "_string_vs_binding")

    print(f"  ✓ All visualizations generated successfully!")


def _plot_top_targets(target_genes, top_n, protein, metadata, base_path):
    """Plot 1: Horizontal bar plot of top target genes by average score."""
    top = target_genes.head(min(top_n, len(target_genes))).copy()

    # Reverse order for coord_flip (bottom-to-top = highest first)
    top["gene"] = pd.Categorical(top["gene"], categories=top["gene"][::-1], ordered=True)

    plot = (
        ggplot(top, aes(x="gene", y="avg_score", fill="binding_rate"))
        + geom_col(alpha=0.85)
        + coord_flip()
        + scale_fill_gradient(low="#FEE08B", high="#D73027")
        + labs(
            title=f"{protein} Top {len(top)} Target Genes",
            subtitle=f"{metadata['total_experiments']} experiments, {metadata['genome']} ±{metadata['distance_kb']}kb",
            x="",
            y="Average MACS2 Binding Score",
            fill="Binding\nRate",
        )
        + _base_theme()
        + theme(
            axis_text_y=element_text(size=7 if len(top) > 15 else 8),
            plot_title=element_text(size=12, weight="bold"),
            plot_subtitle=element_text(size=9),
        )
    )
    _save_plot(plot, base_path)


def _plot_score_distribution(target_genes, protein, base_path):
    """Plot 2: Histogram of average binding scores."""
    df = target_genes[target_genes["avg_score"] > 0].copy()

    if len(df) == 0:
        return

    df["log_score"] = np.log10(df["avg_score"] + 1)

    # Compute exact gene counts at key thresholds
    n_gte50 = (target_genes["avg_score"] >= 50).sum()
    n_gte100 = (target_genes["avg_score"] >= 100).sum()
    n_gte500 = (target_genes["avg_score"] >= 500).sum()

    # Build threshold data for vlines
    thresholds = pd.DataFrame({
        "x": [np.log10(51), np.log10(101), np.log10(501)],
        "label": ["Q=1e-5", "Q=1e-10", "Q=1e-50"],
    })
    thresholds = thresholds[thresholds["x"] <= df["log_score"].max()]

    # Threshold gene counts in subtitle (reliable positioning, always visible to agent)
    median_score = target_genes["avg_score"].median()
    subtitle = (
        f"{len(df)} genes with binding (median: {median_score:.0f}) | "
        f"n\u2265500: {n_gte500}, n\u2265100: {n_gte100}, n\u226550: {n_gte50}"
    )

    plot = (
        ggplot(df, aes(x="log_score"))
        + geom_histogram(bins=50, fill="#4C72B0", alpha=0.8, color="white")
        + geom_vline(
            data=thresholds, mapping=aes(xintercept="x"),
            linetype="dashed", color="#999999", alpha=0.7,
        )
        + labs(
            title=f"{protein} Binding Score Distribution",
            subtitle=subtitle,
            x="log10(Average Binding Score + 1)",
            y="Number of Genes",
        )
        + _base_theme()
        + theme(
            plot_title=element_text(size=12, weight="bold"),
            plot_subtitle=element_text(size=9),
        )
    )
    _save_plot(plot, base_path)


def _plot_heatmap(target_genes, experiment_data, protein, base_path,
                  n_genes=20, n_experiments=20):
    """Plot 3: Clustered heatmap of top genes x top experiments (seaborn clustermap)."""
    top_genes = target_genes.head(min(n_genes, len(target_genes)))["gene"].values

    exp_cols = [c for c in experiment_data.columns if c != "gene"]
    if len(exp_cols) == 0 or len(top_genes) == 0:
        return

    # Subset to top genes
    mask = experiment_data["gene"].isin(top_genes)
    heatmap_data = experiment_data[mask].set_index("gene")

    # Select top experiments by mean score across top genes
    exp_means = heatmap_data[exp_cols].apply(pd.to_numeric, errors="coerce").fillna(0).mean(axis=0)
    top_exp_cols = exp_means.nlargest(min(n_experiments, len(exp_cols))).index.tolist()
    heatmap_values = heatmap_data[top_exp_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    heatmap_values = heatmap_values.reindex(top_genes)

    # Extract cell type labels from column headers
    exp_labels = []
    for col in top_exp_cols:
        parts = col.split("|", 1)
        exp_labels.append(parts[1] if len(parts) == 2 else col[:10])
    heatmap_values.columns = exp_labels

    # Count unique cell types for subtitle
    selected_cell_types = set(exp_labels)
    total_cell_types = set()
    for col in exp_cols:
        parts = col.split("|", 1)
        total_cell_types.add(parts[1] if len(parts) == 2 else col)

    # Create clustermap
    g = sns.clustermap(
        heatmap_values,
        cmap="viridis",
        figsize=(12, max(8, len(heatmap_values) * 0.4)),
        dendrogram_ratio=0.1,
        cbar_kws={"label": "MACS2 Binding Score"},
        row_cluster=True,
        col_cluster=True,
        xticklabels=True,
        yticklabels=True,
    )

    # Style labels
    plt.setp(g.ax_heatmap.get_xticklabels(), rotation=45, ha="right", fontsize=7)
    plt.setp(g.ax_heatmap.get_yticklabels(), fontsize=7)
    g.ax_heatmap.set_xlabel("Experiment (Cell Type)", fontsize=10)
    g.ax_heatmap.set_ylabel("Gene", fontsize=10)

    # Title + subtitle disclosing selection criteria
    g.fig.suptitle(
        f"{protein} Binding Heatmap (Top Genes × Experiments)",
        fontsize=12, fontweight="bold", y=1.02,
    )
    g.fig.text(
        0.5, 0.99,
        f"Top {len(heatmap_values)} genes × {len(top_exp_cols)} highest-scoring experiments "
        f"({len(selected_cell_types)} of {len(total_cell_types)} cell types)",
        ha="center", fontsize=8, color="#555555",
    )

    _save_plot(g.fig, base_path)


def _plot_string_vs_binding(target_genes, protein, base_path):
    """Plot 4: STRING score vs binding score scatter."""
    df = target_genes.copy()
    has_string = (df["string_score"] > 0).any()

    if not has_string:
        # Fallback: binding rate vs avg score
        plot = (
            ggplot(df, aes(x="avg_score", y="binding_rate"))
            + geom_point(alpha=0.4, size=1.5, color="#4C72B0")
            + labs(
                title=f"{protein}: Binding Score vs Binding Rate",
                subtitle="No STRING interaction data available for this protein",
                x="Average Binding Score",
                y="Binding Rate (fraction of experiments)",
            )
            + _base_theme()
            + theme(
                plot_title=element_text(size=12, weight="bold"),
                plot_subtitle=element_text(size=9),
            )
        )
        _save_plot(plot, base_path)
        return

    # Has STRING data — plot STRING vs binding
    df["has_string"] = np.where(df["string_score"] > 0, "STRING interaction", "No STRING data")

    # Label top combined-evidence genes
    with_string = df[df["string_score"] > 0].copy()
    if len(with_string) > 0:
        with_string["combined_rank"] = (
            with_string["avg_score"].rank(ascending=False)
            + with_string["string_score"].rank(ascending=False)
        )
        top_labels = with_string.nsmallest(min(8, len(with_string)), "combined_rank")
    else:
        top_labels = pd.DataFrame()

    plot = (
        ggplot(df, aes(x="avg_score", y="string_score", color="has_string"))
        + geom_point(alpha=0.5, size=1.5)
        + scale_color_manual(
            values={"No STRING data": "#CCCCCC", "STRING interaction": "#E74C3C"},
            name="",
        )
        + labs(
            title=f"{protein}: Binding vs STRING Evidence",
            subtitle=f"{len(with_string)} genes with STRING interaction data",
            x="Average Binding Score",
            y="STRING Interaction Score",
        )
        + _base_theme()
        + theme(
            plot_title=element_text(size=12, weight="bold"),
            plot_subtitle=element_text(size=9),
            legend_position="bottom",
        )
    )

    if len(top_labels) > 0:
        plot = plot + geom_label(
            data=top_labels,
            mapping=aes(label="gene"),
            size=7, alpha=0.8, nudge_y=20,
            show_legend=False,
        )

    _save_plot(plot, base_path)

