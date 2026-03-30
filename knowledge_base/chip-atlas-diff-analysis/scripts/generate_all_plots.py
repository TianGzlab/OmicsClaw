"""
Generate ChIP-Atlas diff analysis visualizations (Step 3).

Creates publication-quality plots using plotnine with Prism themes:
1. Volcano plot (logFC vs -log10 Q-value)
2. Chromosome distribution of differential regions (stacked bar)
3. Region size distribution (histogram, log-scale)
4. MA-style plot (mean counts vs logFC)

Exports both PNG (300 DPI) and SVG with graceful fallback.
"""

import os

import numpy as np
import pandas as pd

try:
    from scripts.filter_regions import get_standard_chroms
except ImportError:
    from filter_regions import get_standard_chroms

from plotnine import (
    aes,
    element_text,
    geom_col,
    geom_histogram,
    geom_hline,
    geom_point,
    geom_vline,
    ggplot,
    labs,
    position_dodge,
    scale_color_manual,
    scale_fill_manual,
    scale_x_discrete,
    scale_x_log10,
    theme,
)
from plotnine_prism import theme_prism


def generate_all_plots(results, output_dir="diff_analysis_results", top_n=20):
    """
    Generate all ChIP-Atlas diff analysis visualizations.

    Parameters
    ----------
    results : dict
        Results from run_diff_workflow()
    output_dir : str
        Output directory
    top_n : int
        Number of top regions to label (default: 20)

    Returns
    -------
    str
        Path to volcano plot PNG file

    Verification
    ------------
    Prints "✓ All visualizations generated successfully!"
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("GENERATING VISUALIZATIONS")
    print("=" * 70 + "\n")

    df = results["diff_regions"]
    params = results["parameters"]
    desc_a = params.get("description_a", "Group A")
    desc_b = params.get("description_b", "Group B")
    genome = params.get("genome", "hg38")
    qc_warnings = results.get("qc_warnings", [])

    if len(df) == 0:
        print("   Warning: No differential regions to plot.")
        print("\n✓ All visualizations generated successfully!")
        return None

    # 1. Volcano plot
    print("1. Generating volcano plot...")
    p1 = _plot_volcano(df, desc_a, desc_b)
    _save_plot(p1, output_dir, "volcano_plot")

    # 2. Chromosome distribution
    print("2. Generating chromosome distribution plot...")
    p2 = _plot_chromosome_distribution(df, desc_a, desc_b, qc_warnings=qc_warnings, genome=genome)
    _save_plot(p2, output_dir, "chromosome_distribution", width=10, height=6)

    # 3. Region size distribution
    print("3. Generating region size distribution...")
    p3 = _plot_region_size(df, desc_a, desc_b)
    _save_plot(p3, output_dir, "region_size_distribution")

    # 4. MA plot
    print("4. Generating MA plot...")
    p4 = _plot_ma(df, desc_a, desc_b)
    _save_plot(p4, output_dir, "ma_plot")

    print("\n✓ All visualizations generated successfully!")
    print("=" * 70 + "\n")

    return os.path.join(output_dir, "volcano_plot.png")


def _plot_volcano(df, desc_a, desc_b):
    """Create volcano plot (logFC vs -log10 Q-value)."""
    plot_df = df.copy()
    plot_df["neg_log10_q"] = -np.log10(plot_df["qvalue"].clip(lower=1e-300))

    sig = plot_df["significant"] if "significant" in plot_df.columns else plot_df["qvalue"] < 0.05
    plot_df["group"] = np.where(
        ~sig,
        "Not significant",
        np.where(plot_df["logFC"] > 0, f"{desc_a} enriched", f"{desc_b} enriched"),
    )

    return (
        ggplot(plot_df, aes(x="logFC", y="neg_log10_q", color="group"))
        + geom_point(size=1.5, alpha=0.6)
        + geom_hline(yintercept=-np.log10(0.05), linetype="dashed", color="gray", size=0.5)
        + geom_vline(xintercept=0, linetype="solid", color="gray", size=0.3, alpha=0.5)
        + scale_color_manual(
            values={
                "Not significant": "#95A5A6",
                f"{desc_a} enriched": "#E74C3C",
                f"{desc_b} enriched": "#3498DB",
            }
        )
        + labs(
            title="Volcano Plot",
            x="Log2 Fold Change",
            y="-log10(Q-value)",
            color="Direction",
        )
        + theme_prism()
        + theme(legend_position="bottom")
    )


def _plot_chromosome_distribution(df, desc_a, desc_b, qc_warnings=None, genome=None):
    """Create bar chart of differential regions by standard chromosome."""
    sig_df = df[df["significant"]] if "significant" in df.columns else df[df["qvalue"] < 0.05]

    # Filter to standard chromosomes for this genome to avoid long labels
    standard_chroms = get_standard_chroms(genome)
    std_sig = sig_df[sig_df["chrom"].isin(standard_chroms)]
    n_other = len(sig_df) - len(std_sig)

    # Identify sex chromosome confounds from QC warnings
    sex_chrom_confounds = set()
    if qc_warnings:
        for w in qc_warnings:
            if "sex chromosome confound" in w.get("issue", ""):
                # Extract chromosome name from issue (e.g., "chrY sex chromosome confound")
                chrom = w["issue"].split(" ")[0]
                sex_chrom_confounds.add(chrom.replace("chr", ""))

    chrom_order = _get_chromosome_order(std_sig["chrom"].unique())

    rows = []
    for c in chrom_order:
        label = c.replace("chr", "")
        # Add asterisk to sex chromosome confound labels
        if label in sex_chrom_confounds:
            label = f"{label}*"
        a_n = int(((std_sig["chrom"] == c) & (std_sig["direction"] == "A_enriched")).sum())
        b_n = int(((std_sig["chrom"] == c) & (std_sig["direction"] == "B_enriched")).sum())
        if a_n > 0 or b_n > 0:
            rows.append({"chrom": label, "count": a_n, "group": f"{desc_a} enriched"})
            rows.append({"chrom": label, "count": b_n, "group": f"{desc_b} enriched"})

    if not rows:
        return (
            ggplot(pd.DataFrame({"x": [0], "y": [0]}), aes("x", "y"))
            + labs(title="No significant differential regions by chromosome")
            + theme_prism()
        )

    plot_df = pd.DataFrame(rows)
    active_labels = []
    for c in chrom_order:
        label = c.replace("chr", "")
        if label in sex_chrom_confounds:
            label = f"{label}*"
        if label in plot_df["chrom"].values:
            active_labels.append(label)

    title = "Differential Regions by Chromosome (FDR < 0.05)"
    if n_other > 0:
        title += f"\n({n_other} regions on non-standard contigs not shown)"
    if sex_chrom_confounds:
        title += "\n(* probable sex-chromosome artifact)"

    return (
        ggplot(plot_df, aes(x="chrom", y="count", fill="group"))
        + geom_col(position=position_dodge(preserve="single"), alpha=0.8)
        + scale_fill_manual(
            values={
                f"{desc_a} enriched": "#E74C3C",
                f"{desc_b} enriched": "#3498DB",
            }
        )
        + scale_x_discrete(limits=active_labels)
        + labs(
            title=title,
            x="Chromosome",
            y="Number of Significant Regions",
            fill="Direction",
        )
        + theme_prism()
        + theme(legend_position="bottom")
    )


def _plot_region_size(df, desc_a, desc_b):
    """Create region size distribution histogram (log scale)."""
    if "region_size" not in df.columns or df["region_size"].dropna().empty:
        return (
            ggplot(pd.DataFrame({"x": [0], "y": [0]}), aes("x", "y"))
            + labs(title="No region size data available")
            + theme_prism()
        )

    plot_df = df[["region_size", "direction"]].dropna().copy()
    plot_df = plot_df[plot_df["region_size"] > 0]
    plot_df["group"] = np.where(
        plot_df["direction"] == "A_enriched",
        f"{desc_a} enriched",
        f"{desc_b} enriched",
    )

    return (
        ggplot(plot_df, aes(x="region_size", fill="group"))
        + geom_histogram(bins=30, alpha=0.8, position="dodge")
        + scale_x_log10()
        + scale_fill_manual(
            values={
                f"{desc_a} enriched": "#E74C3C",
                f"{desc_b} enriched": "#3498DB",
            }
        )
        + labs(
            title="Region Size Distribution",
            x="Region Size (bp, log scale)",
            y="Frequency",
            fill="Direction",
        )
        + theme_prism()
        + theme(legend_position="bottom")
    )


def _plot_ma(df, desc_a, desc_b):
    """Create MA-style plot (mean counts vs logFC)."""
    if "mean_count_a" not in df.columns or "mean_count_b" not in df.columns:
        return (
            ggplot(pd.DataFrame({"x": [0], "y": [0]}), aes("x", "y"))
            + labs(title="No count data for MA plot")
            + theme_prism()
        )

    plot_df = df.copy()
    mean_expr = (plot_df["mean_count_a"] + plot_df["mean_count_b"]) / 2
    plot_df["log2_mean_count"] = np.log2(mean_expr.clip(lower=0.1))

    sig = plot_df["significant"] if "significant" in plot_df.columns else plot_df["qvalue"] < 0.05
    plot_df["group"] = np.where(
        ~sig,
        "Not significant",
        np.where(plot_df["logFC"] > 0, f"{desc_a} enriched", f"{desc_b} enriched"),
    )

    return (
        ggplot(plot_df, aes(x="log2_mean_count", y="logFC", color="group"))
        + geom_point(size=1.2, alpha=0.5)
        + geom_hline(yintercept=0, linetype="solid", color="gray", size=0.3, alpha=0.5)
        + scale_color_manual(
            values={
                "Not significant": "#95A5A6",
                f"{desc_a} enriched": "#E74C3C",
                f"{desc_b} enriched": "#3498DB",
            }
        )
        + labs(
            title="MA Plot",
            x="Log2 Mean Normalized Count",
            y="Log2 Fold Change",
            color="Direction",
        )
        + theme_prism()
        + theme(legend_position="bottom")
    )


def _get_chromosome_order(chromosomes):
    """Return chromosomes in natural sort order."""
    def sort_key(chrom):
        name = chrom.replace("chr", "")
        if name.isdigit():
            return (0, int(name))
        return (1, name)

    return sorted(chromosomes, key=sort_key)


def _save_plot(plot, output_dir, base_name, width=8, height=6):
    """Save plotnine plot as both PNG and SVG with graceful fallback."""
    png_path = os.path.join(output_dir, f"{base_name}.png")
    plot.save(png_path, dpi=300, width=width, height=height, verbose=False)
    print(f"   Saved: {png_path}")

    svg_path = os.path.join(output_dir, f"{base_name}.svg")
    try:
        plot.save(svg_path, width=width, height=height, verbose=False)
        print(f"   Saved: {svg_path}")
    except Exception:
        print("   (SVG export failed - PNG available)")

