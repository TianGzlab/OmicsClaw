"""
Visualize Perturbations

Generate UMAP and PCA plots for each perturbation showing outlier classification
and target gene expression.
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import scanpy as sc
import anndata as ad
from typing import Dict, List, Literal, Optional

# Project plotting standard
sns.set_style("ticks")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Helvetica"]


def _save_plot(fig, base_path, dpi=300):
    """Save figure as PNG + SVG with graceful SVG fallback."""
    base_dir = os.path.dirname(base_path)
    if base_dir:
        os.makedirs(base_dir, exist_ok=True)

    # Strip any existing extension
    base_no_ext = os.path.splitext(base_path)[0]

    # Always save PNG
    png_path = f"{base_no_ext}.png"
    fig.savefig(png_path, dpi=dpi, bbox_inches='tight', facecolor='white')
    print(f"   Saved: {png_path}")

    # Always try SVG
    svg_path = f"{base_no_ext}.svg"
    try:
        fig.savefig(svg_path, format='svg', bbox_inches='tight', facecolor='white')
        print(f"   Saved: {svg_path}")
    except Exception:
        print(f"   (SVG export failed, PNG available)")

    plt.close(fig)


def visualize_single_perturbation(
    adata: ad.AnnData,
    gene_name: str,
    gene_col: str = 'gene',
    sgrna_col: str = 'sgRNA',
    color_by: List[str] = ['classification', 'gene', 'sgRNA'],
    plot_types: List[Literal['umap', 'pca']] = ['umap', 'pca'],
    output_dir: str = 'figures/',
    show: bool = False
) -> None:
    """
    Visualize a single perturbation with UMAP/PCA plots.

    Parameters
    ----------
    adata : AnnData
        AnnData for this perturbation (with 'classification' in obs)
    gene_name : str
        Name of the perturbation gene
    gene_col : str, default='gene'
        Column name for perturbation labels
    sgrna_col : str, default='sgRNA'
        Column name for sgRNA labels
    color_by : list of str
        Variables to color by in plots
    plot_types : list of str
        Plot types to generate: 'umap', 'pca'
    output_dir : str, default='figures/'
        Directory to save plots
    show : bool, default=False
        Whether to show plots interactively

    Example
    -------
    >>> visualize_single_perturbation(
    ...     adata_dict['SOX5'],
    ...     'SOX5',
    ...     color_by=['classification', 'gene', 'SOX5', 'sgRNA']
    ... )
    """
    os.makedirs(output_dir, exist_ok=True)

    # Check if target gene is in var_names, add to color_by if present
    color_vars = color_by.copy()
    if gene_name in adata.var_names and gene_name not in color_vars:
        color_vars.insert(2, gene_name)  # Insert after 'gene' column

    # Filter color_vars to only include those that exist
    valid_color_vars = [
        v for v in color_vars
        if v in adata.obs.columns or v in adata.var_names
    ]

    # Generate UMAP plots
    if 'umap' in plot_types:
        if 'X_umap' not in adata.obsm:
            print(f"Warning: UMAP not computed for {gene_name}, skipping UMAP plot")
        else:
            suffix = '_new.pdf' if gene_name in adata.var_names else '.pdf'
            sc.pl.umap(
                adata,
                color=valid_color_vars,
                save=f'_{gene_name}{suffix}',
                show=show
            )

    # Generate PCA plots
    if 'pca' in plot_types:
        if 'X_pca' not in adata.obsm:
            print(f"Warning: PCA not computed for {gene_name}, skipping PCA plot")
        else:
            suffix = '_new.pdf' if gene_name in adata.var_names else '.pdf'
            sc.pl.pca(
                adata,
                color=valid_color_vars,
                save=f'_{gene_name}{suffix}',
                show=show
            )


def visualize_all_perturbations(
    adata_dict: Dict[str, ad.AnnData],
    gene_col: str = 'gene',
    sgrna_col: str = 'sgRNA',
    color_by: List[str] = ['classification', 'gene', 'sgRNA'],
    plot_types: List[Literal['umap', 'pca']] = ['umap', 'pca'],
    output_dir: str = 'figures/',
    show: bool = False
) -> None:
    """
    Generate visualizations for all perturbations.

    Parameters
    ----------
    adata_dict : dict
        Dictionary mapping gene -> AnnData (from detect_perturbed_cells)
    gene_col : str, default='gene'
        Column name for perturbation labels
    sgrna_col : str, default='sgRNA'
        Column name for sgRNA labels
    color_by : list of str
        Base variables to color by (target gene will be added if present)
    plot_types : list of str
        Plot types to generate: 'umap', 'pca'
    output_dir : str, default='figures/'
        Directory to save plots
    show : bool, default=False
        Whether to show plots interactively

    Example
    -------
    >>> visualize_all_perturbations(
    ...     results['adata_dict'],
    ...     color_by=['classification', 'gene', 'sgRNA'],
    ...     plot_types=['umap', 'pca'],
    ...     output_dir='figures/'
    ... )
    """
    print(f"Generating visualizations for {len(adata_dict)} perturbations...")
    print(f"  Plot types: {plot_types}")
    print(f"  Output directory: {output_dir}\n")

    for i, (gene_name, adata) in enumerate(adata_dict.items()):
        if (i + 1) % 10 == 0:
            print(f"Visualizing {i+1}/{len(adata_dict)}: {gene_name}")

        visualize_single_perturbation(
            adata=adata,
            gene_name=gene_name,
            gene_col=gene_col,
            sgrna_col=sgrna_col,
            color_by=color_by,
            plot_types=plot_types,
            output_dir=output_dir,
            show=show
        )

    print(f"\n=== Visualization Complete ===")
    print(f"Plots saved to: {output_dir}")


def plot_hit_summary(
    summary_df,
    output_path: str = 'figures/hit_summary.png',
    top_n: int = 20
) -> None:
    """
    Generate summary plots for hit calling results.

    Parameters
    ----------
    summary_df : DataFrame
        Perturbation summary from detect_perturbed_cells
    output_path : str
        Path to save summary plot (PNG + SVG generated automatically)
    top_n : int, default=20
        Number of top hits to show

    Example
    -------
    >>> plot_hit_summary(
    ...     results['perturbation_summary'],
    ...     output_path='figures/hit_summary.png'
    ... )
    """
    # Sort by outlier fraction
    summary_sorted = summary_df.sort_values('outlier_fraction', ascending=False)

    # Top N hits
    top_hits = summary_sorted.head(top_n)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Plot 1: Outlier fraction
    sns.barplot(
        data=top_hits,
        x='outlier_fraction',
        y='gene',
        hue='is_hit',
        ax=axes[0],
        dodge=False
    )
    axes[0].set_xlabel('Outlier Fraction')
    axes[0].set_ylabel('Perturbation')
    axes[0].set_title(f'Top {top_n} Perturbations by Outlier Fraction')

    # Plot 2: Number of DE genes vs outliers
    sns.scatterplot(
        data=summary_df,
        x='n_de_genes',
        y='n_outliers',
        hue='is_hit',
        size='n_cells',
        ax=axes[1],
        alpha=0.6
    )
    axes[1].set_xlabel('Number of DE Genes')
    axes[1].set_ylabel('Number of Outlier Cells')
    axes[1].set_title('DE Genes vs Outliers')

    plt.tight_layout()
    _save_plot(fig, output_path)
    print(f"✓ Hit summary plot saved")


def create_volcano_plots(
    de_results,
    perturbation: str,
    output_dir: str = 'figures/',
    fdr_threshold: float = 0.05,
    log2fc_threshold: float = 0.5
) -> None:
    """
    Create volcano plot for a perturbation's DE results.

    Parameters
    ----------
    de_results : DataFrame
        DE results with columns: gene, log2fc, pval, qval
    perturbation : str
        Name of the perturbation (for title)
    output_dir : str
        Directory to save plot
    fdr_threshold : float
        FDR threshold for significance line
    log2fc_threshold : float
        Log2FC threshold for significance
    """
    import numpy as np

    os.makedirs(output_dir, exist_ok=True)

    # Create volcano plot
    fig, ax = plt.subplots(figsize=(8, 6))

    # Determine significance
    significant = (de_results['qval'] < fdr_threshold) & (np.abs(de_results['log2fc']) > log2fc_threshold)

    # Plot non-significant
    ax.scatter(
        de_results.loc[~significant, 'log2fc'],
        -np.log10(de_results.loc[~significant, 'pval'] + 1e-300),
        c='gray', alpha=0.5, s=10, label='Not significant'
    )

    # Plot significant
    ax.scatter(
        de_results.loc[significant, 'log2fc'],
        -np.log10(de_results.loc[significant, 'pval'] + 1e-300),
        c='red', alpha=0.7, s=10, label=f'Significant (FDR<{fdr_threshold})'
    )

    # Threshold lines
    ax.axhline(-np.log10(fdr_threshold), color='blue', linestyle='--', linewidth=1, alpha=0.5)
    ax.axvline(-log2fc_threshold, color='blue', linestyle='--', linewidth=1, alpha=0.5)
    ax.axvline(log2fc_threshold, color='blue', linestyle='--', linewidth=1, alpha=0.5)

    # Labels
    ax.set_xlabel('Log2 Fold Change', fontsize=12)
    ax.set_ylabel('-Log10 P-value', fontsize=12)
    ax.set_title(f'Volcano Plot: {perturbation}', fontsize=14, fontweight='bold')
    ax.legend()

    # Save (PNG + SVG)
    output_path = os.path.join(output_dir, f'volcano_{perturbation}.png')
    plt.tight_layout()
    _save_plot(fig, output_path)

