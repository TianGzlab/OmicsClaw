"""
Generate 4-panel ChIP-Atlas enrichment visualization (Step 3).

Creates:
1. Top enriched factors by significance (-log10 q-value bars)
2. P-value distribution (histogram, -log10 scale)
3. Overlap rate vs fold enrichment (scatter, colored by q-value)
4. Volcano plot (fold enrichment vs q-value significance)

Uses plotnine (Grammar of Graphics) with Prism publication theme.
Exports both PNG (300 DPI) and SVG with graceful fallback.
"""

import os
import sys

try:
    import pandas as pd
    import numpy as np
    from plotnine import *
    from plotnine_prism import theme_prism
    import warnings
    warnings.filterwarnings('ignore')
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install plotnine plotnine-prism pandas numpy")
    sys.exit(1)


def _make_unique_labels(labels):
    """Append counter to duplicate labels to ensure uniqueness for Categorical."""
    seen = {}
    result = []
    for label in labels:
        if label in seen:
            seen[label] += 1
            result.append(f"{label} #{seen[label]}")
        else:
            seen[label] = 1
            result.append(label)
    return result


def generate_all_plots(results, output_dir="chipatlas_results", top_n=15):
    """
    Generate 4-panel visualization of ChIP-Atlas enrichment results.

    Parameters:
    -----------
    results : dict
        Results from run_enrichment_workflow()
    output_dir : str
        Output directory
    top_n : int
        Number of top factors to show in bar plots (default: 15)

    Returns:
    --------
    str: Path to PNG file

    Verification:
    -------------
    Prints "✓ All visualizations generated successfully!"
    """

    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "="*70)
    print("GENERATING VISUALIZATIONS")
    print("="*70 + "\n")

    df = results['enrichment_results']

    # Build 4 plotnine panels
    print("1. Generating top enriched factors plot (by significance)...")
    p1 = _plot_top_factors(df, top_n)

    print("2. Generating p-value distribution plot...")
    p2 = _plot_pvalue_distribution(df)

    print("3. Generating overlap rate vs fold enrichment scatter plot...")
    p3 = _plot_overlap_scatter(df)

    print("4. Generating volcano plot (fold enrichment vs significance)...")
    p4 = _plot_volcano(df)

    # Save combined 4-panel figure
    print("\n5. Saving plots...")
    _save_combined(p1, p2, p3, p4, results, output_dir, "chipatlas_enrichment")

    print("\n✓ All visualizations generated successfully!")
    print("="*70 + "\n")

    return os.path.join(output_dir, "chipatlas_enrichment.png")


def _plot_top_factors(df, top_n):
    """Panel 1: Top enriched factors by q-value significance.

    Shows -log10(q-value) bars ranked by significance, filtered to
    experiments with >= 2 gene overlaps to exclude low-overlap noise.
    Annotated with fold enrichment values.
    """
    # Filter to min 2 overlaps, then take top by q-value (already sorted)
    rankable = df[df['regions_with_overlaps'] >= 2].copy()
    if len(rankable) == 0:
        rankable = df.copy()
    top = rankable.head(top_n).copy().reset_index(drop=True)

    top['label'] = top.apply(
        lambda r: f"{r['antigen'][:20]} ({r['cell_type'][:15]})", axis=1
    )
    top['label'] = _make_unique_labels(top['label'])
    top['neg_log10_q'] = -np.log10(top['q_value'].values + 1e-300)

    # Fold enrichment annotation (cap display at 100k)
    top['fe_str'] = top['fold_enrichment'].apply(
        lambda x: f"{x:.0f}x" if x < 100000 else ">100Kx"
    )
    top['annotation'] = top.apply(
        lambda r: f"{r['fe_str']} ({int(r['regions_with_overlaps'])}/{int(r['total_regions'])})", axis=1
    )
    top['label'] = pd.Categorical(top['label'], categories=top['label'].iloc[::-1].tolist())

    # Color by significance tier
    top['sig_tier'] = top['q_value'].apply(
        lambda q: 'q < 0.001' if q < 0.001 else 'q < 0.01' if q < 0.01 else 'q < 0.05' if q < 0.05 else 'n.s.'
    )

    return (
        ggplot(top, aes(x='label', y='neg_log10_q', fill='sig_tier'))
        + geom_col(color='#2C5F8A', size=0.5)
        + geom_text(aes(label='annotation'), ha='left', nudge_y=max(top['neg_log10_q']) * 0.02, size=7)
        + coord_flip()
        + scale_fill_manual(values={
            'q < 0.001': '#1B4F72',
            'q < 0.01': '#2E86C1',
            'q < 0.05': '#85C1E9',
            'n.s.': '#D5D8DC',
        })
        + geom_hline(yintercept=-np.log10(0.05), linetype='dashed', color='red', alpha=0.5)
        + scale_y_continuous(expand=(0.05, 0, 0.20, 0))
        + labs(title=f'Top {top_n} Enriched Factors (by significance)', x='', y='-log10(Q-value)', fill='')
        + theme_prism()
        + theme(figure_size=(8, 6), legend_position='bottom')
    )


def _plot_pvalue_distribution(df):
    """Panel 2: P-value distribution histogram."""
    plot_df = pd.DataFrame({
        'neg_log10_p': -np.log10(df['p_value'].values + 1e-300)
    })

    return (
        ggplot(plot_df, aes(x='neg_log10_p'))
        + geom_histogram(bins=min(30, len(df)), fill='#E8747C', color='#8B1A1A', alpha=0.7)
        + geom_vline(xintercept=-np.log10(0.05), linetype='dashed', color='red', size=1)
        + annotate('text', x=-np.log10(0.05) + 0.3, y=float('inf'),
                   label='p = 0.05', ha='left', va='top', size=8, color='red')
        + labs(title='P-value Distribution', x='-log10(P-value)', y='Frequency')
        + theme_prism()
        + theme(figure_size=(8, 6))
    )


def _plot_overlap_scatter(df):
    """Panel 3: Overlap rate vs fold enrichment scatter, colored by q-value."""
    plot_df = df.copy()
    plot_df['neg_log10_q'] = -np.log10(plot_df['q_value'] + 1e-300)
    # Cap fold enrichment for display to prevent axis distortion
    plot_df['fe_display'] = plot_df['fold_enrichment'].clip(upper=1000)

    return (
        ggplot(plot_df, aes(x='overlap_rate', y='fe_display', color='neg_log10_q'))
        + geom_point(size=2, alpha=0.7)
        + geom_hline(yintercept=2, linetype='dashed', color='gray', alpha=0.5)
        + scale_color_cmap('viridis')
        + labs(
            title='Overlap Rate vs Fold Enrichment',
            x='Overlap Rate (fraction of genes with peaks)',
            y='Fold Enrichment (capped at 1000)',
            color='-log10(Q)',
        )
        + theme_prism()
        + theme(figure_size=(8, 6))
    )


def _plot_volcano(df):
    """Panel 4: Volcano plot — log2(fold enrichment) vs -log10(q-value).

    Replaces the previous region count panel. Shows the relationship between
    effect size and statistical significance. Sentinel fold enrichment values
    are capped at log2(1000) ≈ 10 for display.
    """
    plot_df = df.copy()
    # Cap fold enrichment to avoid log2 of extreme sentinel values
    plot_df['fe_capped'] = plot_df['fold_enrichment'].clip(lower=0.001, upper=1000)
    plot_df['log2_fe'] = np.log2(plot_df['fe_capped'])
    plot_df['neg_log10_q'] = -np.log10(plot_df['q_value'] + 1e-300)

    # Color: significant (q < 0.05) vs not
    plot_df['sig_label'] = np.where(plot_df['q_value'] < 0.05, 'Significant (q < 0.05)', 'Not significant')

    return (
        ggplot(plot_df, aes(x='log2_fe', y='neg_log10_q', color='sig_label'))
        + geom_point(size=1.5, alpha=0.5)
        + geom_vline(xintercept=np.log2(2), linetype='dashed', color='gray', alpha=0.5)
        + geom_hline(yintercept=-np.log10(0.05), linetype='dashed', color='red', alpha=0.5)
        + scale_color_manual(values={'Significant (q < 0.05)': '#E74C3C', 'Not significant': '#BDC3C7'})
        + labs(
            title='Volcano Plot',
            x='log2(Fold Enrichment)',
            y='-log10(Q-value)',
            color='',
        )
        + theme_prism()
        + theme(figure_size=(8, 6), legend_position='bottom')
    )


def _save_combined(p1, p2, p3, p4, results, output_dir, base_name):
    """Save 4-panel combined figure as PNG and SVG.

    Renders each plotnine panel via draw(), composites into a 2x2
    matplotlib grid using canvas buffer.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    for ax, plot in zip(axes.flat, [p1, p2, p3, p4]):
        # Render plotnine plot to matplotlib figure
        pfig = plot.draw()
        pfig.set_size_inches(8, 6)
        pfig.set_dpi(300)
        pfig.canvas.draw()

        # Extract as numpy array from canvas buffer
        w, h = pfig.canvas.get_width_height()
        buf = np.frombuffer(pfig.canvas.buffer_rgba(), dtype=np.uint8).reshape(h, w, 4)

        ax.imshow(buf)
        ax.axis('off')
        plt.close(pfig)

    n_genes = len(results['input_genes'])
    n_exp = len(results['enrichment_results'])
    genome = results['parameters']['genome']
    fig.suptitle(
        f'ChIP-Atlas Peak Enrichment Analysis\n'
        f'{n_genes} genes, {n_exp} experiments, {genome} genome',
        fontsize=16, fontweight='bold', y=0.995
    )
    plt.tight_layout(rect=[0, 0, 1, 0.97])

    # Save PNG
    png_path = os.path.join(output_dir, f"{base_name}.png")
    fig.savefig(png_path, dpi=300, bbox_inches='tight')
    print(f"   Saved: {png_path}")

    # Save SVG
    svg_path = os.path.join(output_dir, f"{base_name}.svg")
    try:
        fig.savefig(svg_path, format='svg', bbox_inches='tight')
        print(f"   Saved: {svg_path}")
    except Exception:
        try:
            from matplotlib.backends.backend_svg import FigureCanvasSVG
            canvas = FigureCanvasSVG(fig)
            with open(svg_path, 'w') as f:
                canvas.print_svg(f)
            print(f"   Saved: {svg_path}")
        except Exception:
            print("   (SVG export failed - PNG available)")

    plt.close(fig)

