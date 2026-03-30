"""
============================================================================
QUALITY CONTROL VISUALIZATION
============================================================================

This script creates QC plots for identifying filtering thresholds.

Functions:
  - plot_qc_violin(): Violin plots of QC metrics
  - plot_qc_scatter(): Scatter plots of QC metrics
  - plot_qc_histograms(): Histograms of QC metrics

Usage:
  from plot_qc import plot_qc_violin, plot_qc_scatter
  plot_qc_violin(adata, output_dir="results/qc")
  plot_qc_scatter(adata, output_dir="results/qc")
"""

from pathlib import Path
from typing import List, Optional, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
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
        print(f"  (SVG export failed - PNG available)")


def plot_qc_violin(
    adata: 'AnnData',
    metrics: Optional[List[str]] = None,
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (12, 4)
) -> None:
    """
    Create violin plots of QC metrics.

    Parameters
    ----------
    adata : AnnData
        AnnData object with QC metrics
    metrics : list of str, optional
        QC metrics to plot (default: ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'])
    output_dir : str or Path, optional
        Output directory for plots (default: ".")
    figsize : tuple, optional
        Figure size (default: (12, 4))

    Returns
    -------
    None
        Saves plots to output_dir
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if metrics is None:
        metrics = ['n_genes_by_counts', 'total_counts', 'pct_counts_mt']

    print(f"Creating QC violin plots for {len(metrics)} metrics...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    fig, axes = plt.subplots(1, len(metrics), figsize=figsize)
    if len(metrics) == 1:
        axes = [axes]

    for i, metric in enumerate(metrics):
        if metric not in adata.obs.columns:
            print(f"  Warning: {metric} not found in adata.obs, skipping")
            continue

        # Create violin plot
        parts = axes[i].violinplot(
            [adata.obs[metric]],
            positions=[0],
            widths=0.7,
            showmeans=True,
            showmedians=True
        )

        # Style
        for pc in parts['bodies']:
            pc.set_facecolor('#8da0cb')
            pc.set_alpha(0.7)

        axes[i].set_ylabel(metric.replace('_', ' ').title())
        axes[i].set_xticks([])
        axes[i].spines['top'].set_visible(False)
        axes[i].spines['right'].set_visible(False)
        axes[i].grid(axis='y', alpha=0.3)

    plt.tight_layout()
    output_file = output_dir / "qc_violin"
    _save_plot(fig, output_file, dpi=300)
    plt.close()


def plot_qc_scatter(
    adata: 'AnnData',
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (12, 4)
) -> None:
    """
    Create scatter plots of QC metrics.

    Parameters
    ----------
    adata : AnnData
        AnnData object with QC metrics
    output_dir : str or Path, optional
        Output directory for plots (default: ".")
    figsize : tuple, optional
        Figure size (default: (12, 4))

    Returns
    -------
    None
        Saves plots to output_dir
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Creating QC scatter plots...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    fig, axes = plt.subplots(1, 3, figsize=figsize)

    # Plot 1: Total counts vs n_genes
    axes[0].scatter(
        adata.obs['total_counts'],
        adata.obs['n_genes_by_counts'],
        s=1,
        alpha=0.3,
        c='#8da0cb'
    )
    axes[0].set_xlabel('Total Counts')
    axes[0].set_ylabel('N Genes')
    axes[0].set_xscale('log')
    axes[0].set_yscale('log')

    # Plot 2: Total counts vs pct_counts_mt
    axes[1].scatter(
        adata.obs['total_counts'],
        adata.obs['pct_counts_mt'],
        s=1,
        alpha=0.3,
        c='#fc8d62'
    )
    axes[1].set_xlabel('Total Counts')
    axes[1].set_ylabel('% Mitochondrial')
    axes[1].set_xscale('log')

    # Plot 3: N genes vs pct_counts_mt
    axes[2].scatter(
        adata.obs['n_genes_by_counts'],
        adata.obs['pct_counts_mt'],
        s=1,
        alpha=0.3,
        c='#66c2a5'
    )
    axes[2].set_xlabel('N Genes')
    axes[2].set_ylabel('% Mitochondrial')
    axes[2].set_xscale('log')

    for ax in axes:
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(alpha=0.3)

    plt.tight_layout()
    output_file = output_dir / "qc_scatter"
    _save_plot(fig, output_file, dpi=300)
    plt.close()


def plot_qc_histograms(
    adata: 'AnnData',
    metrics: Optional[List[str]] = None,
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (12, 4),
    bins: int = 50
) -> None:
    """
    Create histograms of QC metrics.

    Parameters
    ----------
    adata : AnnData
        AnnData object with QC metrics
    metrics : list of str, optional
        QC metrics to plot (default: ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'])
    output_dir : str or Path, optional
        Output directory for plots (default: ".")
    figsize : tuple, optional
        Figure size (default: (12, 4))
    bins : int, optional
        Number of bins for histograms (default: 50)

    Returns
    -------
    None
        Saves plots to output_dir
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if metrics is None:
        metrics = ['n_genes_by_counts', 'total_counts', 'pct_counts_mt']

    print(f"Creating QC histograms for {len(metrics)} metrics...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    fig, axes = plt.subplots(1, len(metrics), figsize=figsize)
    if len(metrics) == 1:
        axes = [axes]

    colors = ['#8da0cb', '#fc8d62', '#66c2a5']

    for i, metric in enumerate(metrics):
        if metric not in adata.obs.columns:
            print(f"  Warning: {metric} not found in adata.obs, skipping")
            continue

        # Create histogram
        axes[i].hist(
            adata.obs[metric],
            bins=bins,
            color=colors[i % len(colors)],
            alpha=0.7,
            edgecolor='black'
        )

        # Add median line
        median_val = adata.obs[metric].median()
        axes[i].axvline(median_val, color='red', linestyle='--', linewidth=2, label=f'Median: {median_val:.1f}')

        axes[i].set_xlabel(metric.replace('_', ' ').title())
        axes[i].set_ylabel('Count')
        axes[i].legend()
        axes[i].spines['top'].set_visible(False)
        axes[i].spines['right'].set_visible(False)
        axes[i].grid(axis='y', alpha=0.3)

    plt.tight_layout()
    output_file = output_dir / "qc_histograms"
    _save_plot(fig, output_file, dpi=300)
    plt.close()


def plot_highest_expr_genes(
    adata: 'AnnData',
    n_top: int = 20,
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (8, 6)
) -> None:
    """
    Plot the highest expressed genes.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    n_top : int, optional
        Number of top genes to plot (default: 20)
    output_dir : str or Path, optional
        Output directory for plots (default: ".")
    figsize : tuple, optional
        Figure size (default: (8, 6))

    Returns
    -------
    None
        Saves plot to output_dir
    """
    import scanpy as sc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Plotting top {n_top} highest expressed genes...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    sc.pl.highest_expr_genes(adata, n_top=n_top, show=False)

    output_file = output_dir / "highest_expr_genes"
    fig = plt.gcf()
    _save_plot(fig, output_file, dpi=300)
    plt.close()

