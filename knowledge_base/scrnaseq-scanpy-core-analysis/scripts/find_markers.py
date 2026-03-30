"""
============================================================================
MARKER GENE IDENTIFICATION
============================================================================

This script identifies marker genes for each cluster.

Functions:
  - find_all_cluster_markers(): Find markers for all clusters
  - find_markers_for_cluster(): Find markers for a specific cluster
  - export_marker_tables(): Export marker gene tables
  - plot_top_markers_heatmap(): Heatmap of top marker genes
  - plot_markers_dotplot(): Dot plot of top marker genes

Usage:
  from find_markers import find_all_cluster_markers, plot_top_markers_heatmap
  markers = find_all_cluster_markers(adata, cluster_key='leiden_0.8')
  plot_top_markers_heatmap(adata, markers, output_dir='results/markers')
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

import matplotlib.pyplot as plt
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
        print(f"  (SVG export failed, PNG available)")


def find_all_cluster_markers(
    adata: 'AnnData',
    cluster_key: str = 'leiden_0.8',
    method: str = 'wilcoxon',
    n_genes: Optional[int] = None,
    min_in_group_fraction: float = 0.25,
    min_fold_change: float = 1.0,
    max_out_group_fraction: float = 0.5,
    use_raw: bool = False,
    layer: Optional[str] = None
) -> pd.DataFrame:
    """
    Find marker genes for all clusters.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    cluster_key : str, optional
        Cluster column in adata.obs (default: 'leiden_0.8')
    method : str, optional
        Statistical test: 'wilcoxon', 't-test', 'logreg' (default: 'wilcoxon')
    n_genes : int, optional
        Number of genes to return per cluster (default: None, returns all)
    min_in_group_fraction : float, optional
        Minimum fraction of cells in group expressing gene (default: 0.25)
    min_fold_change : float, optional
        Minimum fold change (in natural log) (default: 1.0)
    max_out_group_fraction : float, optional
        Maximum fraction of cells outside group expressing gene (default: 0.5)
    use_raw : bool, optional
        Use raw counts (default: False)
    layer : str, optional
        Layer to use (default: None)

    Returns
    -------
    DataFrame
        Marker genes for all clusters
    """
    import scanpy as sc

    if cluster_key not in adata.obs.columns:
        raise ValueError(f"{cluster_key} not found in adata.obs")

    print(f"Finding marker genes for all clusters in '{cluster_key}'...")
    print(f"  Method: {method}")
    print(f"  Min in-group fraction: {min_in_group_fraction}")
    print(f"  Min fold change: {min_fold_change}")

    # Run marker gene identification
    sc.tl.rank_genes_groups(
        adata,
        groupby=cluster_key,
        method=method,
        use_raw=use_raw,
        layer=layer,
        n_genes=n_genes
    )

    # Filter markers
    sc.tl.filter_rank_genes_groups(
        adata,
        min_in_group_fraction=min_in_group_fraction,
        min_fold_change=min_fold_change,
        max_out_group_fraction=max_out_group_fraction
    )

    # Convert to dataframe
    result = sc.get.rank_genes_groups_df(adata, group=None)

    n_clusters = adata.obs[cluster_key].nunique()
    print(f"  Found markers for {n_clusters} clusters")
    print(f"  Total markers: {len(result)}")

    return result


def find_markers_for_cluster(
    adata: 'AnnData',
    cluster: str,
    cluster_key: str = 'leiden_0.8',
    method: str = 'wilcoxon',
    n_genes: int = 100
) -> pd.DataFrame:
    """
    Find marker genes for a specific cluster.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    cluster : str
        Cluster ID
    cluster_key : str, optional
        Cluster column in adata.obs (default: 'leiden_0.8')
    method : str, optional
        Statistical test (default: 'wilcoxon')
    n_genes : int, optional
        Number of genes to return (default: 100)

    Returns
    -------
    DataFrame
        Marker genes for the cluster
    """
    import scanpy as sc

    if cluster_key not in adata.obs.columns:
        raise ValueError(f"{cluster_key} not found in adata.obs")

    print(f"Finding marker genes for cluster {cluster}...")

    # Run marker gene identification
    sc.tl.rank_genes_groups(
        adata,
        groupby=cluster_key,
        method=method,
        n_genes=n_genes
    )

    # Get results for specific cluster
    result = sc.get.rank_genes_groups_df(adata, group=cluster)

    print(f"  Found {len(result)} markers")

    return result


def export_marker_tables(
    markers: pd.DataFrame,
    output_dir: Union[str, Path] = ".",
    top_n: Optional[int] = None
) -> None:
    """
    Export marker gene tables to CSV files.

    Parameters
    ----------
    markers : DataFrame
        Marker gene dataframe from find_all_cluster_markers
    output_dir : str or Path, optional
        Output directory (default: ".")
    top_n : int, optional
        Export only top N markers per cluster (default: None, exports all)

    Returns
    -------
    None
        Saves CSV files to output_dir
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting marker tables to {output_dir}...")

    # Export all markers
    if top_n is not None:
        markers_filtered = markers.groupby('group').head(top_n)
        output_file = output_dir / f"cluster_markers_top{top_n}.csv"
    else:
        markers_filtered = markers
        output_file = output_dir / "cluster_markers_all.csv"

    markers_filtered.to_csv(output_file, index=False)
    print(f"  Saved: {output_file}")

    # Export separate file for each cluster
    for cluster in markers['group'].unique():
        cluster_markers = markers[markers['group'] == cluster]
        if top_n is not None:
            cluster_markers = cluster_markers.head(top_n)

        output_file = output_dir / f"markers_cluster_{cluster}.csv"
        cluster_markers.to_csv(output_file, index=False)

    print(f"  Saved individual files for {markers['group'].nunique()} clusters")


def plot_top_markers_heatmap(
    adata: 'AnnData',
    markers: pd.DataFrame,
    n_top: int = 10,
    cluster_key: str = 'leiden_0.8',
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (12, 8),
    use_raw: bool = False
) -> None:
    """
    Create heatmap of top marker genes using seaborn clustermap.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    markers : DataFrame
        Marker gene dataframe
    n_top : int, optional
        Number of top markers per cluster (default: 10)
    cluster_key : str, optional
        Cluster column in adata.obs (default: 'leiden_0.8')
    output_dir : str or Path, optional
        Output directory (default: ".")
    figsize : tuple, optional
        Figure size (default: (12, 8))
    use_raw : bool, optional
        Use raw counts (default: False)

    Returns
    -------
    None
        Saves heatmap to output_dir
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating marker gene heatmap (top {n_top} per cluster)...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    # Get top markers per cluster
    top_markers = markers.groupby('group').head(n_top)
    marker_genes = top_markers['names'].unique()

    print(f"  Plotting {len(marker_genes)} marker genes")

    # Get expression data
    if use_raw and adata.raw is not None:
        expr_data = adata.raw[:, marker_genes].X
    else:
        expr_data = adata[:, marker_genes].X

    # Convert to dense if sparse
    if hasattr(expr_data, 'toarray'):
        expr_data = expr_data.toarray()

    # Create dataframe
    expr_df = pd.DataFrame(
        expr_data,
        index=adata.obs_names,
        columns=marker_genes
    )

    # Add cluster annotations
    expr_df['cluster'] = adata.obs[cluster_key].values

    # Sort by cluster
    expr_df = expr_df.sort_values('cluster')

    # Prepare for heatmap
    row_colors = expr_df['cluster'].astype('category').cat.codes
    expr_df = expr_df.drop('cluster', axis=1)

    # Create heatmap
    g = sns.clustermap(
        expr_df.T,
        col_cluster=False,
        row_cluster=True,
        cmap='RdBu_r',
        center=0,
        figsize=figsize,
        cbar_kws={'label': 'Expression'},
        yticklabels=True,
        xticklabels=False
    )

    output_file = output_dir / "markers_heatmap"
    fig = plt.gcf()
    _save_plot(fig, output_file, dpi=300)
    plt.close()


def plot_markers_dotplot(
    adata: 'AnnData',
    markers: pd.DataFrame,
    n_top: int = 5,
    cluster_key: str = 'leiden_0.8',
    output_dir: Union[str, Path] = ".",
    figsize: tuple = (12, 6)
) -> None:
    """
    Create dot plot of top marker genes.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    markers : DataFrame
        Marker gene dataframe
    n_top : int, optional
        Number of top markers per cluster (default: 5)
    cluster_key : str, optional
        Cluster column in adata.obs (default: 'leiden_0.8')
    output_dir : str or Path, optional
        Output directory (default: ".")
    figsize : tuple, optional
        Figure size (default: (12, 6))

    Returns
    -------
    None
        Saves dot plot to output_dir
    """
    import scanpy as sc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating marker gene dot plot (top {n_top} per cluster)...")

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    # Get top markers per cluster
    top_markers = markers.groupby('group').head(n_top)
    marker_genes = top_markers['names'].unique()

    print(f"  Plotting {len(marker_genes)} marker genes")

    sc.pl.dotplot(
        adata,
        var_names=marker_genes,
        groupby=cluster_key,
        dendrogram=True,
        show=False
    )

    output_file = output_dir / "markers_dotplot"
    fig = plt.gcf()
    _save_plot(fig, output_file, dpi=300)
    plt.close()

