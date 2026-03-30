"""
Integration Quality Diagnostics

This module implements metrics to quantify batch integration quality,
including LISI (Local Inverse Simpson's Index) and ASW (Average Silhouette Width).

For methodology and interpretation, see references/integration_methods.md

Functions:
  - compute_lisi_scores(): Calculate iLISI (batch mixing) and cLISI (cell type separation)
  - compute_asw_scores(): Calculate silhouette width for batch and cell type
  - plot_integration_metrics(): Visualize integration quality
  - compare_integration_methods(): Compare multiple integration results

Metrics:
  - iLISI: Integration LISI, measures batch mixing (higher is better, target: n_batches)
  - cLISI: Cell type LISI, measures cell type separation (lower is better, target: 1)
  - Batch ASW: Silhouette for batch (lower is better, target: ~0)
  - Cell type ASW: Silhouette for cell type (higher is better, target: >0.5)

Requirements:
  - harmonypy (for LISI): pip install harmonypy
  - scikit-learn (for ASW): pip install scikit-learn
"""

import scanpy as sc
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Union, List, Dict, Tuple
import warnings
import matplotlib.pyplot as plt


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


def compute_lisi_scores(
    adata: sc.AnnData,
    batch_key: str,
    label_key: Optional[str] = None,
    use_rep: str = 'X_pca',
    perplexity: float = 30,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Compute LISI (Local Inverse Simpson's Index) scores.

    LISI quantifies local batch mixing and cell type separation:
    - iLISI (integration LISI): Batch diversity in local neighborhood
      * Range: 1 (no mixing) to n_batches (perfect mixing)
      * Higher is better
      * Target: Close to number of batches
    - cLISI (cell type LISI): Cell type diversity in local neighborhood
      * Range: 1 (perfect separation) to n_celltypes
      * Lower is better
      * Target: Close to 1

    Parameters
    ----------
    adata : AnnData
        AnnData object with integrated representation
    batch_key : str
        Column in adata.obs containing batch labels
    label_key : str, optional
        Column in adata.obs containing cell type labels
        If None, only iLISI is computed
    use_rep : str, optional
        Key in adata.obsm to use for distance computation (default: 'X_pca')
        Typical: 'X_pca', 'X_scvi', 'X_harmony', 'X_scanvi'
    perplexity : float, optional
        Perplexity for local neighborhood (default: 30)
        Similar to n_neighbors in kNN
    verbose : bool, optional
        Print summary statistics (default: True)

    Returns
    -------
    DataFrame
        DataFrame with columns:
        - 'ilisi': Integration LISI for batch mixing
        - 'clisi': Cell type LISI (if label_key provided)
        Index matches adata.obs

    Notes
    -----
    Requires harmonypy: pip install harmonypy
    LISI computation can be slow for large datasets (>100k cells).

    Examples
    --------
    >>> lisi = compute_lisi_scores(adata, 'batch', 'cell_type', use_rep='X_scvi')
    >>> print(f"Mean iLISI: {lisi['ilisi'].mean():.2f}")
    >>> print(f"Mean cLISI: {lisi['clisi'].mean():.2f}")
    """
    try:
        from harmonypy import compute_lisi
    except ImportError:
        raise ImportError(
            "harmonypy is required for LISI computation.\n"
            "Install with: pip install harmonypy"
        )

    if verbose:
        print("Computing LISI scores...")

    # Check inputs
    if batch_key not in adata.obs.columns:
        raise ValueError(f"Batch key '{batch_key}' not found in adata.obs")

    if label_key is not None and label_key not in adata.obs.columns:
        raise ValueError(f"Label key '{label_key}' not found in adata.obs")

    if use_rep not in adata.obsm:
        raise ValueError(f"Representation '{use_rep}' not found in adata.obsm")

    # Get representation
    X = adata.obsm[use_rep]

    # Prepare metadata
    metadata = adata.obs[[batch_key]].copy()
    if label_key is not None:
        metadata[label_key] = adata.obs[label_key]

    # Compute iLISI (batch mixing)
    if verbose:
        n_batches = adata.obs[batch_key].nunique()
        print(f"  Computing iLISI (batch mixing)...")
        print(f"    Batches: {n_batches}")
        print(f"    Target: {n_batches} (perfect mixing)")

    ilisi = compute_lisi(
        X,
        metadata,
        [batch_key],
        perplexity=perplexity
    )

    results = pd.DataFrame({'ilisi': ilisi[:, 0]}, index=adata.obs.index)

    if verbose:
        print(f"    Mean iLISI: {results['ilisi'].mean():.2f}")
        print(f"    Median iLISI: {results['ilisi'].median():.2f}")

    # Compute cLISI (cell type separation)
    if label_key is not None:
        if verbose:
            n_labels = adata.obs[label_key].nunique()
            print(f"  Computing cLISI (cell type separation)...")
            print(f"    Cell types: {n_labels}")
            print(f"    Target: 1.0 (perfect separation)")

        clisi = compute_lisi(
            X,
            metadata,
            [label_key],
            perplexity=perplexity
        )

        results['clisi'] = clisi[:, 0]

        if verbose:
            print(f"    Mean cLISI: {results['clisi'].mean():.2f}")
            print(f"    Median cLISI: {results['clisi'].median():.2f}")

    if verbose:
        print("  LISI computation complete.\n")

    return results


def compute_asw_scores(
    adata: sc.AnnData,
    batch_key: str,
    label_key: str,
    use_rep: str = 'X_pca',
    metric: str = 'euclidean',
    verbose: bool = True
) -> Dict[str, float]:
    """
    Compute Average Silhouette Width (ASW) scores.

    ASW measures clustering quality:
    - Batch ASW: Silhouette using batch labels
      * Range: -1 to 1
      * Lower is better (batches well-mixed)
      * Target: Close to 0
    - Cell type ASW: Silhouette using cell type labels
      * Range: -1 to 1
      * Higher is better (cell types separated)
      * Target: >0.5

    Parameters
    ----------
    adata : AnnData
        AnnData object with integrated representation
    batch_key : str
        Column in adata.obs containing batch labels
    label_key : str
        Column in adata.obs containing cell type labels
    use_rep : str, optional
        Key in adata.obsm for distance computation (default: 'X_pca')
    metric : str, optional
        Distance metric (default: 'euclidean')
    verbose : bool, optional
        Print summary statistics (default: True)

    Returns
    -------
    dict
        Dictionary with:
        - 'batch_asw': ASW for batch (lower is better)
        - 'celltype_asw': ASW for cell type (higher is better)
        - 'batch_asw_per_label': Per-cell-type batch ASW (DataFrame)
        - 'celltype_asw_per_batch': Per-batch cell type ASW (DataFrame)

    Notes
    -----
    Requires scikit-learn: pip install scikit-learn
    ASW computation can be slow for very large datasets (>200k cells).

    Examples
    --------
    >>> asw = compute_asw_scores(adata, 'batch', 'cell_type', use_rep='X_scvi')
    >>> print(f"Batch ASW: {asw['batch_asw']:.3f} (target: ~0)")
    >>> print(f"Cell type ASW: {asw['celltype_asw']:.3f} (target: >0.5)")
    """
    try:
        from sklearn.metrics import silhouette_score, silhouette_samples
    except ImportError:
        raise ImportError(
            "scikit-learn is required for ASW computation.\n"
            "Install with: pip install scikit-learn"
        )

    if verbose:
        print("Computing ASW scores...")

    # Check inputs
    if batch_key not in adata.obs.columns:
        raise ValueError(f"Batch key '{batch_key}' not found in adata.obs")

    if label_key not in adata.obs.columns:
        raise ValueError(f"Label key '{label_key}' not found in adata.obs")

    if use_rep not in adata.obsm:
        raise ValueError(f"Representation '{use_rep}' not found in adata.obsm")

    # Get representation
    X = adata.obsm[use_rep]
    batch_labels = adata.obs[batch_key].values
    celltype_labels = adata.obs[label_key].values

    # Compute batch ASW (lower is better)
    if verbose:
        print(f"  Computing batch ASW (target: ~0)...")

    batch_asw = silhouette_score(X, batch_labels, metric=metric)
    batch_silhouette_samples = silhouette_samples(X, batch_labels, metric=metric)

    if verbose:
        print(f"    Batch ASW: {batch_asw:.3f}")

    # Compute per-cell-type batch ASW
    batch_asw_per_label = []
    for label in np.unique(celltype_labels):
        mask = celltype_labels == label
        if mask.sum() > 1:  # Need at least 2 cells
            label_asw = batch_silhouette_samples[mask].mean()
            batch_asw_per_label.append({
                'cell_type': label,
                'batch_asw': label_asw,
                'n_cells': mask.sum()
            })

    batch_asw_per_label_df = pd.DataFrame(batch_asw_per_label)

    # Compute cell type ASW (higher is better)
    if verbose:
        print(f"  Computing cell type ASW (target: >0.5)...")

    celltype_asw = silhouette_score(X, celltype_labels, metric=metric)
    celltype_silhouette_samples = silhouette_samples(X, celltype_labels, metric=metric)

    if verbose:
        print(f"    Cell type ASW: {celltype_asw:.3f}")

    # Compute per-batch cell type ASW
    celltype_asw_per_batch = []
    for batch in np.unique(batch_labels):
        mask = batch_labels == batch
        if mask.sum() > 1:
            batch_ct_asw = celltype_silhouette_samples[mask].mean()
            celltype_asw_per_batch.append({
                'batch': batch,
                'celltype_asw': batch_ct_asw,
                'n_cells': mask.sum()
            })

    celltype_asw_per_batch_df = pd.DataFrame(celltype_asw_per_batch)

    if verbose:
        print("  ASW computation complete.\n")

    return {
        'batch_asw': batch_asw,
        'celltype_asw': celltype_asw,
        'batch_asw_per_label': batch_asw_per_label_df,
        'celltype_asw_per_batch': celltype_asw_per_batch_df
    }


def plot_integration_metrics(
    adata: sc.AnnData,
    batch_key: str,
    label_key: str,
    use_rep: str = 'X_pca',
    output_dir: Union[str, Path] = "results/integration_qc",
    method_name: str = "Integration"
):
    """
    Create comprehensive integration quality plots.

    Generates:
    1. UMAP colored by batch and cell type
    2. LISI score distributions (violin plots)
    3. ASW score comparisons (bar plots)
    4. Per-cell-type batch mixing (heatmap)

    Parameters
    ----------
    adata : AnnData
        AnnData object with integrated representation
    batch_key : str
        Column in adata.obs containing batch labels
    label_key : str
        Column in adata.obs containing cell type labels
    use_rep : str, optional
        Representation to use (default: 'X_pca')
    output_dir : str or Path, optional
        Output directory for plots (default: 'results/integration_qc')
    method_name : str, optional
        Integration method name for titles (default: 'Integration')

    Notes
    -----
    Requires seaborn and matplotlib for plotting.
    """
    import seaborn as sns
    import matplotlib.pyplot as plt

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating integration quality plots for {method_name}...")

    # 1. UMAP plots
    print("  Creating UMAP plots...")

    # Compute UMAP if not present
    if 'X_umap' not in adata.obsm:
        sc.pp.neighbors(adata, use_rep=use_rep)
        sc.tl.umap(adata)

    # UMAP by batch
    sc.pl.umap(
        adata,
        color=batch_key,
        title=f'{method_name}: Batch',
        show=False,
        save=False
    )
    fig = plt.gcf()
    _save_plot(fig, output_dir / f'{method_name}_umap_batch', dpi=300)
    plt.close()

    # UMAP by cell type
    sc.pl.umap(
        adata,
        color=label_key,
        title=f'{method_name}: Cell Type',
        show=False,
        save=False
    )
    fig = plt.gcf()
    _save_plot(fig, output_dir / f'{method_name}_umap_celltype', dpi=300)
    plt.close()

    # 2. Compute metrics
    print("  Computing LISI and ASW scores...")
    lisi = compute_lisi_scores(adata, batch_key, label_key, use_rep, verbose=False)
    asw = compute_asw_scores(adata, batch_key, label_key, use_rep, verbose=False)

    # Add to adata.obs for plotting
    adata.obs['ilisi'] = lisi['ilisi'].values
    if 'clisi' in lisi.columns:
        adata.obs['clisi'] = lisi['clisi'].values

    # 3. LISI distribution plots
    print("  Creating LISI distribution plots...")

    # iLISI violin plot
    plot_df = pd.DataFrame({
        'iLISI': adata.obs['ilisi'],
        'Cell Type': adata.obs[label_key]
    })

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.violinplot(data=plot_df, x='Cell Type', y='iLISI', ax=ax)
    ax.set_xlabel('')
    ax.set_ylabel('iLISI (higher = better mixing)')
    ax.set_title(f'{method_name}: Batch Mixing (iLISI)', fontweight='bold')
    plt.xticks(rotation=45, ha='right')
    sns.despine(ax=ax)
    fig.tight_layout()
    fig.savefig(output_dir / f'{method_name}_ilisi_violin.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / f'{method_name}_ilisi_violin.svg', dpi=300, bbox_inches='tight')
    plt.close(fig)

    # cLISI violin plot (if available)
    if 'clisi' in adata.obs.columns:
        plot_df = pd.DataFrame({
            'cLISI': adata.obs['clisi'],
            'Batch': adata.obs[batch_key]
        })

        fig, ax = plt.subplots(figsize=(8, 6))
        sns.violinplot(data=plot_df, x='Batch', y='cLISI', ax=ax)
        ax.set_xlabel('')
        ax.set_ylabel('cLISI (lower = better separation)')
        ax.set_title(f'{method_name}: Cell Type Separation (cLISI)', fontweight='bold')
        sns.despine(ax=ax)
        fig.tight_layout()
        fig.savefig(output_dir / f'{method_name}_clisi_violin.png', dpi=300, bbox_inches='tight')
        fig.savefig(output_dir / f'{method_name}_clisi_violin.svg', dpi=300, bbox_inches='tight')
        plt.close(fig)

    # 4. ASW summary plot
    print("  Creating ASW summary plot...")

    asw_labels = ['Batch ASW\n(lower better)', 'Cell Type ASW\n(higher better)']
    asw_scores = [asw['batch_asw'], asw['celltype_asw']]
    asw_colors = sns.color_palette("Set2", 2)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.bar(asw_labels, asw_scores, color=asw_colors)
    ax.set_ylabel('ASW Score')
    ax.set_title(f'{method_name}: Average Silhouette Width', fontweight='bold')
    sns.despine(ax=ax)
    fig.tight_layout()
    fig.savefig(output_dir / f'{method_name}_asw_summary.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / f'{method_name}_asw_summary.svg', dpi=300, bbox_inches='tight')
    plt.close(fig)

    # 5. Batch mixing heatmap (per cell type)
    print("  Creating batch mixing heatmap...")

    batch_ct_counts = adata.obs.groupby([label_key, batch_key]).size().unstack(fill_value=0)
    batch_ct_proportions = batch_ct_counts.div(batch_ct_counts.sum(axis=1), axis=0)

    g = sns.clustermap(
        batch_ct_proportions,
        cmap='RdBu_r',
        center=0.5,
        cbar_kws={'label': 'Proportion of cells'},
        annot=True,
        fmt='.2f',
        figsize=(10, 8),
        row_cluster=False,
        col_cluster=False,
    )
    g.ax_heatmap.set_title(f'{method_name}: Batch Distribution per Cell Type', fontweight='bold')
    g.ax_heatmap.set_xlabel('Batch')
    g.ax_heatmap.set_ylabel('Cell Type')
    fig = g.fig
    _save_plot(fig, output_dir / f'{method_name}_batch_mixing_heatmap', dpi=300)
    plt.close(fig)

    # Save metrics summary
    metrics_summary = {
        'method': method_name,
        'representation': use_rep,
        'mean_ilisi': float(lisi['ilisi'].mean()),
        'median_ilisi': float(lisi['ilisi'].median()),
        'batch_asw': float(asw['batch_asw']),
        'celltype_asw': float(asw['celltype_asw']),
        'n_batches': int(adata.obs[batch_key].nunique()),
        'n_celltypes': int(adata.obs[label_key].nunique())
    }

    if 'clisi' in lisi.columns:
        metrics_summary['mean_clisi'] = float(lisi['clisi'].mean())
        metrics_summary['median_clisi'] = float(lisi['clisi'].median())

    metrics_file = output_dir / f'{method_name}_metrics_summary.csv'
    pd.DataFrame([metrics_summary]).to_csv(metrics_file, index=False)

    print(f"\n  Plots saved to: {output_dir}")
    print(f"  Metrics summary saved to: {metrics_file}\n")


def compare_integration_methods(
    adata: sc.AnnData,
    batch_key: str,
    label_key: str,
    methods: List[str],
    output_dir: Union[str, Path] = "results/integration_comparison"
):
    """
    Compare multiple integration methods side-by-side.

    Parameters
    ----------
    adata : AnnData
        AnnData object with multiple integration results
    batch_key : str
        Column in adata.obs containing batch labels
    label_key : str
        Column in adata.obs containing cell type labels
    methods : list of str
        List of representation keys to compare (e.g., ['X_pca', 'X_scvi', 'X_harmony'])
    output_dir : str or Path, optional
        Output directory for comparison plots

    Examples
    --------
    >>> # After running multiple integration methods
    >>> compare_integration_methods(
    ...     adata,
    ...     batch_key='batch',
    ...     label_key='cell_type',
    ...     methods=['X_pca', 'X_scvi', 'X_harmony', 'X_scanvi']
    ... )
    """
    import seaborn as sns
    import matplotlib.pyplot as plt

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Comparing integration methods...")

    # Compute metrics for each method
    comparison_results = []

    for method in methods:
        if method not in adata.obsm:
            print(f"  Warning: {method} not found in adata.obsm, skipping...")
            continue

        print(f"  Computing metrics for {method}...")

        # LISI
        lisi = compute_lisi_scores(adata, batch_key, label_key, method, verbose=False)

        # ASW
        asw = compute_asw_scores(adata, batch_key, label_key, method, verbose=False)

        comparison_results.append({
            'Method': method.replace('X_', '').upper(),
            'Mean iLISI': lisi['ilisi'].mean(),
            'Mean cLISI': lisi['clisi'].mean() if 'clisi' in lisi.columns else np.nan,
            'Batch ASW': asw['batch_asw'],
            'Cell Type ASW': asw['celltype_asw']
        })

    results_df = pd.DataFrame(comparison_results)

    # Save comparison table
    results_file = output_dir / 'integration_comparison.csv'
    results_df.to_csv(results_file, index=False)
    print(f"\n  Comparison table saved to: {results_file}")

    # Create comparison plots
    print("  Creating comparison plots...")

    # iLISI comparison
    fig, ax = plt.subplots(figsize=(8, 6))
    palette = sns.color_palette("Set2", n_colors=len(results_df))
    ax.bar(results_df['Method'], results_df['Mean iLISI'], color=palette)
    ax.set_ylabel('Mean iLISI (higher = better)')
    ax.set_title('Integration Quality: Batch Mixing (iLISI)', fontweight='bold')
    sns.despine(ax=ax)
    fig.tight_layout()
    fig.savefig(output_dir / 'comparison_ilisi.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'comparison_ilisi.svg', dpi=300, bbox_inches='tight')
    plt.close(fig)

    # ASW comparison (grouped bar chart)
    asw_comparison = pd.melt(
        results_df[['Method', 'Batch ASW', 'Cell Type ASW']],
        id_vars='Method',
        var_name='Metric',
        value_name='Score'
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=asw_comparison, x='Method', y='Score', hue='Metric', ax=ax)
    ax.set_ylabel('ASW Score')
    ax.set_title('Integration Quality: Average Silhouette Width', fontweight='bold')
    ax.legend(frameon=False)
    sns.despine(ax=ax)
    fig.tight_layout()
    fig.savefig(output_dir / 'comparison_asw.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'comparison_asw.svg', dpi=300, bbox_inches='tight')
    plt.close(fig)

    print(f"\n  Comparison complete! Results in: {output_dir}\n")

    return results_df


# Example usage
if __name__ == "__main__":
    print("Example integration diagnostics workflow:")
    print()
    print("# Compute LISI scores")
    print("lisi = compute_lisi_scores(adata, 'batch', 'cell_type', use_rep='X_scvi')")
    print("print(f\"Mean iLISI: {lisi['ilisi'].mean():.2f}\")")
    print("print(f\"Mean cLISI: {lisi['clisi'].mean():.2f}\")")
    print()
    print("# Compute ASW scores")
    print("asw = compute_asw_scores(adata, 'batch', 'cell_type', use_rep='X_scvi')")
    print("print(f\"Batch ASW: {asw['batch_asw']:.3f}\")")
    print("print(f\"Cell type ASW: {asw['celltype_asw']:.3f}\")")
    print()
    print("# Generate quality plots")
    print("plot_integration_metrics(adata, 'batch', 'cell_type', use_rep='X_scvi', method_name='scVI')")
    print()
    print("# Compare multiple methods")
    print("compare_integration_methods(adata, 'batch', 'cell_type', methods=['X_pca', 'X_scvi', 'X_harmony'])")

