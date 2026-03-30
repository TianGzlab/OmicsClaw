"""
============================================================================
DATA NORMALIZATION
============================================================================

This script normalizes scRNA-seq expression data.

Functions:
  - run_standard_normalization(): Standard target sum + log1p normalization
  - run_pearson_residuals(): Pearson residuals normalization
  - plot_normalization_comparison(): Compare before/after normalization

Usage:
  from normalize_data import run_standard_normalization
  adata = run_standard_normalization(adata)
"""

from pathlib import Path
from typing import Optional, Union

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


def _save_plot(fig: plt.Figure, base_path: Union[str, Path], dpi: int = 300) -> None:
    """
    Save plot in both PNG and SVG formats with graceful fallback.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        Figure object to save
    base_path : str or Path
        Base path for output files (without extension)
    dpi : int, optional
        Resolution for PNG (default: 300)

    Returns
    -------
    None
        Saves files to disk
    """
    base_path = Path(base_path)

    # Always save PNG
    png_path = base_path.with_suffix('.png')
    try:
        fig.savefig(png_path, dpi=dpi, bbox_inches='tight', format='png')
        print(f"  Saved: {png_path}")
    except Exception as e:
        print(f"  Warning: PNG export failed: {e}")

    # Always try SVG
    svg_path = base_path.with_suffix('.svg')
    try:
        fig.savefig(svg_path, bbox_inches='tight', format='svg')
        print(f"  Saved: {svg_path}")
    except Exception as e:
        print(f"  (SVG export failed, PNG available)")


def run_standard_normalization(
    adata: 'AnnData',
    target_sum: float = 1e4,
    exclude_highly_expressed: bool = False,
    max_fraction: float = 0.05,
    log_transform: bool = True,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Run standard normalization (target sum + log1p).

    Parameters
    ----------
    adata : AnnData
        AnnData object
    target_sum : float, optional
        Target sum for normalization (default: 1e4)
    exclude_highly_expressed : bool, optional
        Exclude highly expressed genes from target sum calculation (default: False)
    max_fraction : float, optional
        Maximum fraction of counts per cell for a gene (for exclusion) (default: 0.05)
    log_transform : bool, optional
        Apply log1p transformation (default: True)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        Normalized AnnData object if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    print("Running standard normalization...")

    # Store raw counts
    adata.layers['counts'] = adata.X.copy()

    # Normalize to target sum
    sc.pp.normalize_total(
        adata,
        target_sum=target_sum,
        exclude_highly_expressed=exclude_highly_expressed,
        max_fraction=max_fraction,
        inplace=True
    )

    print(f"  Normalized to target sum: {target_sum}")

    # Log transform
    if log_transform:
        sc.pp.log1p(adata)
        print("  Applied log1p transformation")

    print("  Normalization complete")

    # Always return adata for convenience
    return adata


def run_pearson_residuals(
    adata: 'AnnData',
    theta: float = 100,
    clip: Optional[float] = None,
    check_values: bool = True,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Run Pearson residuals normalization.

    This method is an alternative to standard normalization that better
    handles heteroscedasticity in scRNA-seq data.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    theta : float, optional
        Dispersion parameter (default: 100)
    clip : float, optional
        Clip residuals to this value (default: None, uses sqrt(n_obs))
    check_values : bool, optional
        Check for invalid values (default: True)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        Normalized AnnData object if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    print("Running Pearson residuals normalization...")

    # Store raw counts
    adata.layers['counts'] = adata.X.copy()

    # Compute Pearson residuals
    sc.experimental.pp.normalize_pearson_residuals(
        adata,
        theta=theta,
        clip=clip,
        check_values=check_values,
        inplace=True
    )

    print("  Pearson residuals normalization complete")

    # Always return adata for convenience
    return adata


def plot_normalization_comparison(
    adata: 'AnnData',
    gene_name: str,
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (12, 4)
) -> None:
    """
    Compare raw and normalized expression for a gene.

    Parameters
    ----------
    adata : AnnData
        AnnData object with 'counts' layer
    gene_name : str
        Gene name to plot
    output_dir : str or Path, optional
        Output directory for plot (default: ".")
    figsize : tuple, optional
        Figure size (default: (12, 4))

    Returns
    -------
    None
        Saves plot to output_dir
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if gene_name not in adata.var_names:
        print(f"Warning: {gene_name} not found in adata.var_names")
        return

    if 'counts' not in adata.layers:
        print("Warning: 'counts' layer not found. Run normalization first.")
        return

    print(f"Plotting normalization comparison for {gene_name}...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    fig, axes = plt.subplots(1, 3, figsize=figsize)

    # Get expression values
    gene_idx = adata.var_names.get_loc(gene_name)
    raw_expr = adata.layers['counts'][:, gene_idx].toarray().flatten() if hasattr(adata.layers['counts'], 'toarray') else adata.layers['counts'][:, gene_idx].flatten()
    norm_expr = adata.X[:, gene_idx].toarray().flatten() if hasattr(adata.X, 'toarray') else adata.X[:, gene_idx].flatten()

    # Plot 1: Raw counts histogram
    axes[0].hist(raw_expr, bins=50, color='#8da0cb', alpha=0.7, edgecolor='black')
    axes[0].set_xlabel('Raw Counts')
    axes[0].set_ylabel('Frequency')
    axes[0].set_title(f'{gene_name} - Raw')

    # Plot 2: Normalized expression histogram
    axes[1].hist(norm_expr, bins=50, color='#fc8d62', alpha=0.7, edgecolor='black')
    axes[1].set_xlabel('Normalized Expression')
    axes[1].set_ylabel('Frequency')
    axes[1].set_title(f'{gene_name} - Normalized')

    # Plot 3: Scatter plot
    axes[2].scatter(raw_expr, norm_expr, s=1, alpha=0.3, c='#66c2a5')
    axes[2].set_xlabel('Raw Counts')
    axes[2].set_ylabel('Normalized Expression')
    axes[2].set_title('Raw vs Normalized')

    for ax in axes:
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(alpha=0.3)

    plt.tight_layout()
    output_file = output_dir / f"normalization_comparison_{gene_name}"
    fig = plt.gcf()
    _save_plot(fig, output_file, dpi=300)
    plt.close()

    print(f"  Saved: {output_file}")


def plot_library_size_effect(
    adata: 'AnnData',
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (8, 6)
) -> None:
    """
    Plot library size effect before and after normalization.

    Parameters
    ----------
    adata : AnnData
        AnnData object with 'counts' layer
    output_dir : str or Path, optional
        Output directory for plot (default: ".")
    figsize : tuple, optional
        Figure size (default: (8, 6))

    Returns
    -------
    None
        Saves plot to output_dir
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if 'counts' not in adata.layers:
        print("Warning: 'counts' layer not found. Run normalization first.")
        return

    print("Plotting library size effect...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # Calculate mean expression
    raw_counts = adata.layers['counts']
    norm_counts = adata.X

    raw_mean = raw_counts.mean(axis=1).A1 if hasattr(raw_counts, 'A1') else raw_counts.mean(axis=1)
    norm_mean = norm_counts.mean(axis=1).A1 if hasattr(norm_counts, 'A1') else norm_counts.mean(axis=1)

    # Plot 1: Library size vs mean expression (raw)
    axes[0].scatter(adata.obs['total_counts'], raw_mean, s=1, alpha=0.3, c='#8da0cb')
    axes[0].set_xlabel('Library Size')
    axes[0].set_ylabel('Mean Expression')
    axes[0].set_title('Before Normalization')
    axes[0].set_xscale('log')
    axes[0].set_yscale('log')

    # Plot 2: Library size vs mean expression (normalized)
    axes[1].scatter(adata.obs['total_counts'], norm_mean, s=1, alpha=0.3, c='#fc8d62')
    axes[1].set_xlabel('Library Size')
    axes[1].set_ylabel('Mean Expression')
    axes[1].set_title('After Normalization')
    axes[1].set_xscale('log')
    axes[1].set_yscale('log')

    for ax in axes:
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(alpha=0.3)

    plt.tight_layout()
    output_file = output_dir / "library_size_effect"
    fig = plt.gcf()
    _save_plot(fig, output_file, dpi=300)
    plt.close()

    print(f"  Saved: {output_file}")

