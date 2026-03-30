"""
TWAS Results Visualization

This module provides publication-quality plotting functions for TWAS results
using plotnine with Prism themes.
"""

import pandas as pd
import numpy as np
from plotnine import (ggplot, aes, geom_point, geom_hline, labs,
                      theme_minimal, scale_color_manual, facet_wrap, ylim,
                      geom_abline, coord_equal)
from plotnine_prism import theme_prism

try:
    from adjustText import adjust_text
    HAS_ADJUSTTEXT = True
except ImportError:
    HAS_ADJUSTTEXT = False


def plot_manhattan(twas_results, tissue, threshold, output_file="figures/manhattan.svg", label_top_genes=10):
    """
    Create Manhattan plot of TWAS results with labeled significant genes.

    Parameters
    ----------
    twas_results : pandas.DataFrame
        TWAS results with CHR, BP, TWAS.P, GENE columns
    tissue : str
        Tissue name for plot title
    threshold : float
        Significance threshold line
    output_file : str
        Output file path (SVG format recommended)
    label_top_genes : int
        Number of top significant genes to label (default: 10)
    """
    print(f"Creating Manhattan plot for {tissue}...")

    # Prepare data
    plot_data = twas_results.copy()
    plot_data['-log10P'] = -np.log10(plot_data['TWAS.P'])

    # Alternate chromosome colors
    plot_data['color'] = plot_data['CHR'].apply(lambda x: 'even' if x % 2 == 0 else 'odd')

    # Create cumulative position for x-axis
    plot_data = plot_data.sort_values(['CHR', 'BP'])
    chr_lengths = plot_data.groupby('CHR')['BP'].max()
    chr_starts = {}
    cumulative = 0
    for chrom in range(1, 23):
        chr_starts[chrom] = cumulative
        cumulative += chr_lengths.get(chrom, 0)

    plot_data['x_pos'] = plot_data.apply(
        lambda row: chr_starts.get(row['CHR'], 0) + row['BP'],
        axis=1
    )

    # Significance threshold
    threshold_line = -np.log10(threshold)

    # Get top significant genes for labeling
    sig_genes = plot_data[plot_data['TWAS.P'] < threshold].nsmallest(label_top_genes, 'TWAS.P')

    # Create plot
    p = (
        ggplot(plot_data, aes(x='x_pos', y='-log10P', color='color'))
        + geom_point(size=1.5, alpha=0.7)
        + geom_hline(yintercept=threshold_line, linetype='dashed', color='red', size=0.5)
        + scale_color_manual(values={'odd': '#0072B2', 'even': '#56B4E9'})
        + labs(
            title=f'TWAS Manhattan Plot - {tissue}',
            x='Chromosome',
            y='-log10(P-value)'
        )
        + theme_prism()
    )

    # Add gene labels with adjustText if available
    if HAS_ADJUSTTEXT and len(sig_genes) > 0 and 'GENE' in plot_data.columns:
        import matplotlib.pyplot as plt

        # Draw base plot to get matplotlib figure
        fig = p.draw()
        ax = fig.axes[0]

        # Add labels with adjustText for non-overlapping placement
        texts = [
            ax.text(row['x_pos'], row['-log10P'], row['GENE'],
                   fontsize=8, alpha=0.9, weight='bold')
            for _, row in sig_genes.iterrows()
        ]
        adjust_text(
            texts,
            arrowprops=dict(arrowstyle='->', color='gray', lw=0.5, alpha=0.7),
            expand_points=(1.5, 1.5),
            force_text=(0.5, 0.5)
        )

        # Save the adjusted figure
        fig.savefig(output_file, dpi=300, bbox_inches='tight')
        png_file = output_file.replace('.svg', '.png')
        fig.savefig(png_file, dpi=300, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {output_file}")
        print(f"  Saved: {png_file}")
    else:
        # Save without labels if adjustText not available
        p.save(output_file, dpi=300, width=12, height=6)
        print(f"  Saved: {output_file}")


def plot_qq(pvalues, output_file="figures/qq_plot.svg"):
    """
    Create QQ plot to assess calibration of TWAS results.

    Parameters
    ----------
    pvalues : array-like
        P-values from TWAS
    output_file : str
        Output file path
    """
    print("Creating QQ plot...")

    # Remove NaN values
    pvalues = pvalues[~np.isnan(pvalues)]

    # Sort observed p-values
    observed = -np.log10(np.sort(pvalues))

    # Expected p-values under null
    n = len(pvalues)
    expected = -np.log10(np.arange(1, n + 1) / (n + 1))

    plot_data = pd.DataFrame({
        'expected': expected,
        'observed': observed
    })

    # Create plot
    p = (
        ggplot(plot_data, aes(x='expected', y='observed'))
        + geom_point(color='#0072B2', size=2, alpha=0.6)
        + geom_abline(intercept=0, slope=1, linetype='dashed', color='red')
        + labs(
            title='TWAS QQ Plot',
            x='Expected -log10(P)',
            y='Observed -log10(P)'
        )
        + coord_equal()
        + theme_prism()
    )

    p.save(output_file, dpi=300, width=6, height=6)
    print(f"  Saved: {output_file}")


def plot_regional(twas_results, gwas_sumstats, gene, window_kb=500,
                  output_file="figures/regional.svg"):
    """
    Create regional association plot for a specific gene locus.

    Parameters
    ----------
    twas_results : pandas.DataFrame
        TWAS results
    gwas_sumstats : pandas.DataFrame
        GWAS summary statistics
    gene : str
        Gene symbol to plot
    window_kb : int
        Window size around gene (default: 500kb)
    output_file : str
        Output file path
    """
    print(f"Creating regional plot for {gene}...")

    # Get gene info
    gene_info = twas_results[twas_results['GENE'] == gene].iloc[0]
    chrom = gene_info['CHR']
    gene_start = gene_info['P0']
    gene_end = gene_info['P1']

    # Define window
    window_start = gene_start - window_kb * 1000
    window_end = gene_end + window_kb * 1000

    # Extract GWAS data in window
    gwas_window = gwas_sumstats[
        (gwas_sumstats['CHR'] == chrom) &
        (gwas_sumstats['BP'] >= window_start) &
        (gwas_sumstats['BP'] <= window_end)
    ].copy()

    gwas_window['-log10P'] = -np.log10(gwas_window['P'])

    # Create plot
    p = (
        ggplot(gwas_window, aes(x='BP', y='-log10P'))
        + geom_point(color='#0072B2', size=2, alpha=0.7)
        + labs(
            title=f'Regional Association Plot - {gene}',
            x=f'Position on Chromosome {chrom} (bp)',
            y='-log10(P-value)'
        )
        + theme_prism()
    )

    p.save(output_file, dpi=300, width=10, height=6)
    print(f"  Saved: {output_file}")


def plot_tissue_comparison(twas_results_multi_tissue, gene, output_file="figures/tissue_comparison.svg"):
    """
    Compare TWAS association for a gene across tissues.

    Parameters
    ----------
    twas_results_multi_tissue : pandas.DataFrame
        TWAS results with TISSUE column
    gene : str
        Gene symbol
    output_file : str
        Output file path
    """
    print(f"Creating tissue comparison plot for {gene}...")

    gene_data = twas_results_multi_tissue[
        twas_results_multi_tissue['GENE'] == gene
    ].copy()

    gene_data['-log10P'] = -np.log10(gene_data['TWAS.P'])
    gene_data = gene_data.sort_values('-log10P', ascending=False)

    p = (
        ggplot(gene_data, aes(x='TISSUE', y='-log10P'))
        + geom_point(size=4, color='#0072B2')
        + geom_hline(yintercept=-np.log10(0.05), linetype='dashed', color='red')
        + labs(
            title=f'{gene} - Cross-Tissue TWAS',
            x='Tissue',
            y='-log10(P-value)'
        )
        + theme_prism()
    )

    p.save(output_file, dpi=300, width=10, height=6)
    print(f"  Saved: {output_file}")

