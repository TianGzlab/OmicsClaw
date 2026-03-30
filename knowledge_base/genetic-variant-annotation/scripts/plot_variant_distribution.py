"""
Variant Visualization Module

This module provides functions for creating publication-quality plots of variant data
using plotnine with Prism themes.
"""

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


def _save_plot(plot, base_path, width=8, height=6, dpi=300):
    """
    Save plot in both PNG and SVG formats with graceful fallback.

    Always saves PNG. Always attempts SVG with fallback to base svg() device
    if high-quality svglite fails.

    Parameters
    ----------
    plot : plotnine.ggplot
        Plot object to save
    base_path : str
        Base output path (can end in .png or .svg, both will be created)
    width : float
        Plot width in inches (default: 8)
    height : float
        Plot height in inches (default: 6)
    dpi : int
        Resolution for PNG (default: 300)
    """
    from pathlib import Path

    # Normalize base path (remove extension)
    base = str(Path(base_path).with_suffix(''))

    # Always save PNG
    png_path = f"{base}.png"
    try:
        plot.save(png_path, width=width, height=height, dpi=dpi, format='png')
        print(f"   Saved: {png_path}")
    except Exception as e:
        print(f"   Warning: PNG save failed: {e}")

    # Always try SVG - plotnine handles svglite if available, falls back gracefully
    svg_path = f"{base}.svg"
    try:
        plot.save(svg_path, width=width, height=height, format='svg')
        print(f"   Saved: {svg_path}")
    except Exception as e:
        print(f"   (SVG export failed: {e})")


def plot_consequence_distribution(df, output_file="consequence_distribution.svg", top_n=15):
    """
    Plot distribution of variant consequence types.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with Consequence column
    output_file : str
        Output file path (SVG format)
    top_n : int
        Number of top consequences to show (default: 15)
    """
    if 'Consequence' not in df.columns:
        print("Error: Consequence column not found")
        return

    # Count consequences (split multi-consequences)
    consequences = []
    for cons in df['Consequence'].dropna():
        consequences.extend(str(cons).split('&'))

    cons_df = pd.DataFrame({'Consequence': consequences})
    cons_counts = cons_df['Consequence'].value_counts().head(top_n).reset_index()
    cons_counts.columns = ['Consequence', 'Count']

    # Create plot
    plot = (
        ggplot(cons_counts, aes(x='reorder(Consequence, Count)', y='Count')) +
        geom_bar(stat='identity', fill='#0073C2') +
        coord_flip() +
        labs(
            title='Variant Consequence Distribution',
            x='Consequence Type',
            y='Number of Variants'
        ) +
        theme_prism() +
        theme(figure_size=(8, 6))
    )

    print(f"Saving consequence distribution plot...")
    _save_plot(plot, output_file, width=8, height=6, dpi=300)


def plot_impact_by_chromosome(df, output_file="impact_by_chromosome.svg"):
    """
    Plot variant impact distribution across chromosomes.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with CHROM and IMPACT columns
    output_file : str
        Output file path (SVG format)
    """
    if 'CHROM' not in df.columns or 'IMPACT' not in df.columns:
        print("Error: CHROM or IMPACT column not found")
        return

    # Count by chromosome and impact
    chrom_impact = df.groupby(['CHROM', 'IMPACT']).size().reset_index(name='Count')

    # Order chromosomes
    chrom_order = [str(i) for i in range(1, 23)] + ['X', 'Y', 'MT']
    chrom_impact['CHROM'] = pd.Categorical(
        chrom_impact['CHROM'],
        categories=chrom_order,
        ordered=True
    )
    chrom_impact = chrom_impact.sort_values('CHROM')

    # Create plot
    plot = (
        ggplot(chrom_impact, aes(x='CHROM', y='Count', fill='IMPACT')) +
        geom_bar(stat='identity', position='stack') +
        scale_fill_manual(values={
            'HIGH': '#D32F2F',
            'MODERATE': '#F57C00',
            'LOW': '#FBC02D',
            'MODIFIER': '#7CB342'
        }) +
        labs(
            title='Variant Impact by Chromosome',
            x='Chromosome',
            y='Number of Variants',
            fill='Impact'
        ) +
        theme_prism() +
        theme(
            figure_size=(12, 6),
            axis_text_x=element_text(angle=45, hjust=1)
        )
    )

    print(f"Saving impact by chromosome plot...")
    _save_plot(plot, output_file, width=12, height=6, dpi=300)


def plot_pathogenicity_scores(df, scores=['CADD_PHRED', 'REVEL'], output_file="pathogenicity_scores.svg"):
    """
    Plot distribution of pathogenicity scores.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with pathogenicity score columns
    scores : list
        List of score column names to plot
    output_file : str
        Output file path (SVG format)
    """
    # Prepare data
    plot_data = []
    for score_name in scores:
        if score_name in df.columns:
            score_values = pd.to_numeric(df[score_name], errors='coerce').dropna()
            for val in score_values:
                plot_data.append({'Score_Type': score_name, 'Value': val})

    if not plot_data:
        print("Error: No valid score columns found")
        return

    score_df = pd.DataFrame(plot_data)

    # Create plot
    plot = (
        ggplot(score_df, aes(x='Value', fill='Score_Type')) +
        geom_histogram(bins=30, alpha=0.7, position='identity') +
        facet_wrap('~Score_Type', scales='free') +
        labs(
            title='Pathogenicity Score Distributions',
            x='Score Value',
            y='Count'
        ) +
        theme_prism() +
        theme(figure_size=(10, 5))
    )

    print(f"Saving pathogenicity scores plot...")
    _save_plot(plot, output_file, width=10, height=5, dpi=300)


def plot_allele_frequency(df, population='gnomAD_AF', output_file="allele_frequency.svg", log_scale=True):
    """
    Plot allele frequency distribution.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with allele frequency column
    population : str
        Allele frequency column name (default: 'gnomAD_AF')
    output_file : str
        Output file path (SVG format)
    log_scale : bool
        Use log scale for x-axis (default: True)
    """
    if population not in df.columns:
        print(f"Error: {population} column not found")
        return

    # Get numeric frequencies
    af = pd.to_numeric(df[population], errors='coerce').dropna()
    af = af[af > 0]  # Remove zeros for log scale

    if len(af) == 0:
        print("Error: No valid allele frequencies found")
        return

    af_df = pd.DataFrame({'Allele_Frequency': af})

    # Create plot
    plot = (
        ggplot(af_df, aes(x='Allele_Frequency')) +
        geom_histogram(bins=50, fill='#0073C2', alpha=0.7) +
        labs(
            title='Allele Frequency Distribution',
            x='Allele Frequency',
            y='Number of Variants'
        ) +
        theme_prism() +
        theme(figure_size=(8, 6))
    )

    if log_scale:
        plot = plot + scale_x_log10()

    print(f"Saving allele frequency plot...")
    _save_plot(plot, output_file, width=8, height=6, dpi=300)


def plot_gene_burden(gene_df, top_n=20, output_file="gene_burden.svg"):
    """
    Plot variants per gene (gene burden).

    Parameters
    ----------
    gene_df : pd.DataFrame
        Gene summary DataFrame with N_Variants column
    top_n : int
        Number of top genes to show (default: 20)
    output_file : str
        Output file path (SVG format)
    """
    if 'N_Variants' not in gene_df.columns:
        print("Error: N_Variants column not found")
        return

    # Get gene column name
    gene_col = 'SYMBOL' if 'SYMBOL' in gene_df.columns else 'Gene'

    if gene_col not in gene_df.columns:
        print("Error: Gene column not found")
        return

    # Top genes
    top_genes = gene_df.nlargest(top_n, 'N_Variants')

    # Create plot
    plot = (
        ggplot(top_genes, aes(x=f'reorder({gene_col}, N_Variants)', y='N_Variants')) +
        geom_bar(stat='identity', fill='#0073C2') +
        coord_flip() +
        labs(
            title=f'Top {top_n} Genes by Variant Count',
            x='Gene',
            y='Number of Variants'
        ) +
        theme_prism() +
        theme(figure_size=(8, 8))
    )

    print(f"Saving gene burden plot...")
    _save_plot(plot, output_file, width=8, height=8, dpi=300)


def plot_variant_quality(df, output_file="variant_quality.svg"):
    """
    Plot variant quality score distribution.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with QUAL column
    output_file : str
        Output file path (SVG format)
    """
    if 'QUAL' not in df.columns:
        print("Error: QUAL column not found")
        return

    qual = pd.to_numeric(df['QUAL'], errors='coerce').dropna()

    if len(qual) == 0:
        print("Error: No valid quality scores found")
        return

    qual_df = pd.DataFrame({'Quality': qual})

    # Create plot
    plot = (
        ggplot(qual_df, aes(x='Quality')) +
        geom_histogram(bins=50, fill='#0073C2', alpha=0.7) +
        geom_vline(xintercept=30, linetype='dashed', color='red', size=1) +
        labs(
            title='Variant Quality Score Distribution',
            x='Quality Score (QUAL)',
            y='Number of Variants'
        ) +
        annotate('text', x=35, y=max(qual_df['Quality'].value_counts()) * 0.9,
                label='Q30 threshold', color='red', ha='left') +
        theme_prism() +
        theme(figure_size=(8, 6))
    )

    print(f"Saving quality distribution plot...")
    _save_plot(plot, output_file, width=8, height=6, dpi=300)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Plot variant distributions')
    parser.add_argument('input_csv', help='Input CSV file with variant annotations')
    parser.add_argument('--consequence', help='Output file for consequence plot')
    parser.add_argument('--impact-chr', help='Output file for impact by chromosome plot')
    parser.add_argument('--scores', help='Output file for pathogenicity scores plot')
    parser.add_argument('--frequency', help='Output file for allele frequency plot')

    args = parser.parse_args()

    # Load data
    df = pd.read_csv(args.input_csv)
    print(f"Loaded {len(df)} variants")

    # Generate requested plots
    if args.consequence:
        plot_consequence_distribution(df, output_file=args.consequence)

    if args.impact_chr:
        plot_impact_by_chromosome(df, output_file=args.impact_chr)

    if args.scores:
        plot_pathogenicity_scores(df, output_file=args.scores)

    if args.frequency:
        plot_allele_frequency(df, output_file=args.frequency)

