"""
============================================================================
DATA SCALING AND PCA
============================================================================

This script scales data and performs PCA dimensionality reduction.

Functions:
  - scale_data(): Scale expression data and regress out unwanted variation
  - run_pca_analysis(): Perform PCA
  - plot_pca_variance(): Plot variance explained by PCs
  - plot_pca_scatter(): Create PCA scatter plots
  - plot_pca_loadings(): Plot PC loadings

Usage:
  from scale_and_pca import scale_data, run_pca_analysis
  adata = scale_data(adata, vars_to_regress=['total_counts', 'pct_counts_mt'])
  adata = run_pca_analysis(adata, n_pcs=50)
"""

from pathlib import Path
from typing import List, Optional, Union

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


def scale_data(
    adata: 'AnnData',
    max_value: Optional[float] = 10,
    vars_to_regress: Optional[List[str]] = None,
    use_hvg_only: bool = True,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Scale expression data and optionally regress out unwanted variation.

    Parameters
    ----------
    adata : AnnData
        AnnData object (should be log-normalized)
    max_value : float, optional
        Clip values exceeding this threshold (default: 10, None for no clipping)
    vars_to_regress : list of str, optional
        Variables to regress out (e.g., ['total_counts', 'pct_counts_mt'])
    use_hvg_only : bool, optional
        Use only highly variable genes (default: True)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        Scaled AnnData object if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    print("Scaling data...")

    # Regress out unwanted variation
    if vars_to_regress is not None:
        print(f"  Regressing out: {', '.join(vars_to_regress)}")
        sc.pp.regress_out(adata, keys=vars_to_regress)

    # Scale to unit variance and zero mean
    if use_hvg_only and 'highly_variable' in adata.var.columns:
        n_hvg = adata.var['highly_variable'].sum()
        print(f"  Scaling {n_hvg} highly variable genes")
    else:
        print(f"  Scaling all {adata.n_vars} genes")

    sc.pp.scale(adata, max_value=max_value)

    print("  Scaling complete")

    # Always return adata for convenience
    return adata


def run_pca_analysis(
    adata: 'AnnData',
    n_pcs: int = 50,
    use_hvg_only: bool = True,
    svd_solver: str = 'arpack',
    random_state: int = 0,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Perform PCA dimensionality reduction.

    Parameters
    ----------
    adata : AnnData
        AnnData object (should be scaled)
    n_pcs : int, optional
        Number of principal components to compute (default: 50)
    use_hvg_only : bool, optional
        Use only highly variable genes (default: True)
    svd_solver : str, optional
        SVD solver: 'arpack', 'randomized', 'auto' (default: 'arpack')
    random_state : int, optional
        Random seed (default: 0)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with PCA if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    print(f"Running PCA with {n_pcs} components...")

    if use_hvg_only and 'highly_variable' in adata.var.columns:
        n_hvg = adata.var['highly_variable'].sum()
        print(f"  Using {n_hvg} highly variable genes")
    else:
        print(f"  Using all {adata.n_vars} genes")

    sc.tl.pca(
        adata,
        n_comps=n_pcs,
        use_highly_variable=use_hvg_only,
        svd_solver=svd_solver,
        random_state=random_state
    )

    # Verify PCA loadings are correct
    if use_hvg_only and 'highly_variable' in adata.var.columns and 'PCs' in adata.varm:
        n_hvg = int(adata.var['highly_variable'].sum())
        nonzero_rows = int((np.abs(adata.varm['PCs']).sum(axis=1) > 0).sum())
        if nonzero_rows != n_hvg:
            print(f"  WARNING: Expected {n_hvg} non-zero loading rows, got {nonzero_rows}")
            print(f"     PCA may have been run on the wrong object. Use sc.tl.pca(adata, use_highly_variable=True)")
        else:
            print(f"  PCA loadings verified: {nonzero_rows} HVG rows have non-zero loadings")

    # Calculate variance explained
    var_ratio = adata.uns['pca']['variance_ratio']
    cumsum_var = np.cumsum(var_ratio)

    print(f"  PC1-10 explain {100*cumsum_var[9]:.1f}% of variance")
    print(f"  PC1-20 explain {100*cumsum_var[19]:.1f}% of variance")
    print(f"  PC1-30 explain {100*cumsum_var[29]:.1f}% of variance")

    # Always return adata for convenience
    return adata


def suggest_n_pcs(
    adata: 'AnnData',
    min_pcs: int = 15,
    default_pcs: int = 30,
    target_variance: float = 0.85
) -> int:
    """
    Suggest number of PCs based on cumulative variance explained.

    Parameters
    ----------
    adata : AnnData
        AnnData object with PCA computed
    min_pcs : int, optional
        Minimum PCs to recommend (default: 15)
    default_pcs : int, optional
        Default/maximum PCs to recommend (default: 30)
    target_variance : float, optional
        Target cumulative variance fraction (default: 0.85)

    Returns
    -------
    int
        Recommended number of PCs
    """
    if 'pca' not in adata.uns:
        print(f"  PCA not found. Returning default: {default_pcs}")
        return default_pcs

    var_ratio = adata.uns['pca']['variance_ratio']
    cumsum = np.cumsum(var_ratio)

    # Find where cumulative variance reaches target
    n_target = int(np.searchsorted(cumsum, target_variance) + 1)
    recommended = max(min_pcs, min(n_target, default_pcs))

    print(f"  Suggested n_pcs: {recommended} ({target_variance:.0%} variance at PC{n_target}, safe default: {default_pcs})")
    if recommended < 20:
        print(f"  WARNING: Using <20 PCs risks underfitting. Consider 20-30 PCs.")

    return recommended


def plot_pca_variance(
    adata: 'AnnData',
    n_pcs: int = 50,
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (12, 4)
) -> None:
    """
    Plot variance explained by principal components.

    Parameters
    ----------
    adata : AnnData
        AnnData object with PCA
    n_pcs : int, optional
        Number of PCs to plot (default: 50)
    output_dir : str or Path, optional
        Output directory for plot (default: ".")
    figsize : tuple, optional
        Figure size (default: (12, 4))

    Returns
    -------
    None
        Saves plot to output_dir
    """
    import scanpy as sc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if 'pca' not in adata.uns:
        print("Warning: PCA not found. Run run_pca_analysis first.")
        return

    print("Plotting PCA variance...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # Plot 1: Variance explained by each PC (elbow plot)
    var_ratio = adata.uns['pca']['variance_ratio'][:n_pcs]
    axes[0].plot(range(1, len(var_ratio) + 1), var_ratio, 'o-', color='#8da0cb')
    axes[0].set_xlabel('Principal Component')
    axes[0].set_ylabel('Variance Explained')
    axes[0].set_title('Scree Plot')
    axes[0].grid(alpha=0.3)

    # Plot 2: Cumulative variance explained
    cumsum_var = np.cumsum(var_ratio)
    axes[1].plot(range(1, len(cumsum_var) + 1), cumsum_var, 'o-', color='#fc8d62')
    axes[1].axhline(y=0.9, color='red', linestyle='--', label='90% variance')
    axes[1].set_xlabel('Principal Component')
    axes[1].set_ylabel('Cumulative Variance Explained')
    axes[1].set_title('Cumulative Variance')
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    for ax in axes:
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    plt.tight_layout()
    output_file = output_dir / "pca_variance"
    fig = plt.gcf()
    _save_plot(fig, output_file, dpi=300)
    plt.close()

    print(f"  Saved: {output_file}")


def plot_pca_scatter(
    adata: 'AnnData',
    color: Optional[Union[str, List[str]]] = None,
    components: List[str] = ['1,2', '3,4'],
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (12, 5)
) -> None:
    """
    Create PCA scatter plots.

    Parameters
    ----------
    adata : AnnData
        AnnData object with PCA
    color : str or list of str, optional
        Color cells by these variables (default: None)
    components : list of str, optional
        PC pairs to plot (default: ['1,2', '3,4'])
    output_dir : str or Path, optional
        Output directory for plots (default: ".")
    figsize : tuple, optional
        Figure size (default: (12, 5))

    Returns
    -------
    None
        Saves plots to output_dir
    """
    import scanpy as sc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if 'pca' not in adata.obsm:
        print("Warning: PCA not found. Run run_pca_analysis first.")
        return

    print("Plotting PCA scatter plots...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    # Create plots
    for comp_pair in components:
        sc.pl.pca(
            adata,
            color=color,
            components=comp_pair,
            show=False
        )

        output_file = output_dir / f"pca_scatter_{comp_pair.replace(',', '_')}"
        fig = plt.gcf()
        _save_plot(fig, output_file, dpi=300)
        plt.close()

        print(f"  Saved: {output_file}")


def plot_pca_loadings(
    adata: 'AnnData',
    components: List[int] = [1, 2, 3],
    n_genes: int = 20,
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (8, 6)
) -> None:
    """
    Plot genes with highest loadings for each PC.

    Parameters
    ----------
    adata : AnnData
        AnnData object with PCA
    components : list of int, optional
        PCs to plot (1-indexed) (default: [1, 2, 3])
    n_genes : int, optional
        Number of top genes to show per PC (default: 20)
    output_dir : str or Path, optional
        Output directory for plot (default: ".")
    figsize : tuple, optional
        Figure size per component (default: (8, 6))

    Returns
    -------
    None
        Saves plots to output_dir
    """
    import scanpy as sc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if 'pca' not in adata.uns:
        print("Warning: PCA not found. Run run_pca_analysis first.")
        return

    print("Plotting PCA loadings...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    for comp in components:
        # Convert to 0-indexed
        comp_idx = comp - 1

        fig, ax = plt.subplots(figsize=figsize)
        sc.pl.pca_loadings(
            adata,
            components=comp,
            show=False,
            ax=ax
        )

        output_file = output_dir / f"pca_loadings_PC{comp}"
        fig = plt.gcf()
        _save_plot(fig, output_file, dpi=300)
        plt.close()

        print(f"  Saved: {output_file}")

