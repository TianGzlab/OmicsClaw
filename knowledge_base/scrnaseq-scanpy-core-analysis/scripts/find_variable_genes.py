"""
============================================================================
HIGHLY VARIABLE GENES IDENTIFICATION
============================================================================

This script identifies highly variable genes for downstream analysis.

Functions:
  - find_highly_variable_genes(): Identify HVGs using various methods
  - plot_variable_genes(): Visualize highly variable genes

Usage:
  from find_variable_genes import find_highly_variable_genes
  adata = find_highly_variable_genes(adata, n_top_genes=2000)
"""

from pathlib import Path
from typing import Optional, Union

import matplotlib.pyplot as plt
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


def find_highly_variable_genes(
    adata: 'AnnData',
    n_top_genes: int = 2000,
    flavor: str = 'seurat',
    min_mean: float = 0.0125,
    max_mean: float = 3,
    min_disp: float = 0.5,
    subset: bool = False,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Identify highly variable genes.

    Parameters
    ----------
    adata : AnnData
        AnnData object (should be log-normalized)
    n_top_genes : int, optional
        Number of highly variable genes to select (default: 2000)
    flavor : str, optional
        Method for identifying HVGs: 'seurat', 'cell_ranger', 'seurat_v3' (default: 'seurat')
    min_mean : float, optional
        Minimum mean expression (for 'seurat' flavor) (default: 0.0125)
    max_mean : float, optional
        Maximum mean expression (for 'seurat' flavor) (default: 3)
    min_disp : float, optional
        Minimum dispersion (for 'seurat' flavor) (default: 0.5)
    subset : bool, optional
        Subset to highly variable genes (default: False, adds .var['highly_variable'])
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with HVG information if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    print(f"Identifying highly variable genes using '{flavor}' method...")

    if flavor == 'seurat':
        sc.pp.highly_variable_genes(
            adata,
            n_top_genes=n_top_genes,
            min_mean=min_mean,
            max_mean=max_mean,
            min_disp=min_disp,
            subset=subset,
            flavor=flavor
        )
    elif flavor == 'seurat_v3':
        # Seurat v3 method uses raw counts
        if 'counts' not in adata.layers:
            raise ValueError("Seurat v3 method requires raw counts in adata.layers['counts']")
        sc.pp.highly_variable_genes(
            adata,
            n_top_genes=n_top_genes,
            subset=subset,
            flavor=flavor,
            layer='counts'
        )
    else:
        sc.pp.highly_variable_genes(
            adata,
            n_top_genes=n_top_genes,
            subset=subset,
            flavor=flavor
        )

    n_hvg = adata.var['highly_variable'].sum()
    print(f"  Identified {n_hvg} highly variable genes")

    # Always return adata for convenience
    return adata


def plot_variable_genes(
    adata: 'AnnData',
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (8, 6),
    log: bool = True
) -> None:
    """
    Visualize highly variable genes.

    Parameters
    ----------
    adata : AnnData
        AnnData object with HVG information
    output_dir : str or Path, optional
        Output directory for plot (default: ".")
    figsize : tuple, optional
        Figure size (default: (8, 6))
    log : bool, optional
        Use log scale (default: True)

    Returns
    -------
    None
        Saves plot to output_dir
    """
    import scanpy as sc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if 'highly_variable' not in adata.var.columns:
        print("Warning: highly_variable not found. Run find_highly_variable_genes first.")
        return

    print("Plotting highly variable genes...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    fig, ax = plt.subplots(figsize=figsize)
    sc.pl.highly_variable_genes(adata, log=log, show=False)

    output_file = output_dir / "highly_variable_genes"
    fig = plt.gcf()
    _save_plot(fig, output_file, dpi=300)
    plt.close()

    print(f"  Saved: {output_file}")


def filter_to_hvgs(
    adata: 'AnnData',
    inplace: bool = False
) -> 'AnnData':
    """
    Subset AnnData to highly variable genes only.

    Parameters
    ----------
    adata : AnnData
        AnnData object with HVG information
    inplace : bool, optional
        Modify AnnData in place (default: False)

    Returns
    -------
    AnnData
        AnnData object with only highly variable genes
    """
    if 'highly_variable' not in adata.var.columns:
        raise ValueError("highly_variable not found. Run find_highly_variable_genes first.")

    n_genes_before = adata.n_vars
    n_hvg = adata.var['highly_variable'].sum()

    print(f"Subsetting to {n_hvg} highly variable genes...")

    if inplace:
        adata._inplace_subset_var(adata.var['highly_variable'])
        adata_hvg = adata
    else:
        adata_hvg = adata[:, adata.var['highly_variable']].copy()

    print(f"  Reduced from {n_genes_before} to {adata_hvg.n_vars} genes")

    return adata_hvg

