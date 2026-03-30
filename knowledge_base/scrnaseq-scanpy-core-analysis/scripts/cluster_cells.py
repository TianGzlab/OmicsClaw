"""
============================================================================
CELL CLUSTERING
============================================================================

This script performs graph-based clustering using the Leiden algorithm.

Functions:
  - build_neighbor_graph(): Compute k-nearest neighbors graph
  - cluster_leiden(): Leiden clustering at single resolution
  - cluster_leiden_multiple_resolutions(): Test multiple resolutions
  - plot_clustering_tree(): Visualize clustering hierarchy

Usage:
  from cluster_cells import build_neighbor_graph, cluster_leiden_multiple_resolutions
  adata = build_neighbor_graph(adata, n_neighbors=10, n_pcs=30)
  adata = cluster_leiden_multiple_resolutions(adata, resolutions=[0.4, 0.6, 0.8, 1.0])
"""

from typing import List, Optional

import numpy as np


def build_neighbor_graph(
    adata: 'AnnData',
    n_neighbors: int = 10,
    n_pcs: int = 30,
    metric: str = 'euclidean',
    random_state: int = 0,
    use_rep: Optional[str] = None,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Compute k-nearest neighbors graph.

    Parameters
    ----------
    adata : AnnData
        AnnData object with PCA
    n_neighbors : int, optional
        Number of neighbors (default: 10)
    n_pcs : int, optional
        Number of PCs to use (default: 30). Standard range: 20-30.
    metric : str, optional
        Distance metric (default: 'euclidean')
    random_state : int, optional
        Random seed (default: 0)
    use_rep : str, optional
        Representation to use (e.g., 'X_pca', 'X_scVI'). Default: None (uses X_pca)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with neighbor graph if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    # Determine representation
    if use_rep is not None and use_rep in adata.obsm:
        print(f"Building neighbor graph with k={n_neighbors} using {use_rep}...")
    elif 'X_pca' not in adata.obsm:
        raise ValueError("PCA not found. Run run_pca_analysis first.")
    else:
        print(f"Building neighbor graph with k={n_neighbors}...")

    # Warn if too few PCs
    if n_pcs is not None and n_pcs < 15:
        print(f"  WARNING: n_pcs={n_pcs} is very low. Standard is 20-30 PCs.")
        print(f"     Using <15 PCs risks collapsing distinct cell populations.")

    print(f"  Using {n_pcs} PCs")

    neighbors_kwargs = dict(
        n_neighbors=n_neighbors,
        n_pcs=n_pcs,
        metric=metric,
        random_state=random_state
    )
    if use_rep is not None and use_rep in adata.obsm:
        neighbors_kwargs['use_rep'] = use_rep
    sc.pp.neighbors(adata, **neighbors_kwargs)

    print("  Neighbor graph built successfully")

    # Always return adata for convenience
    return adata


def cluster_leiden(
    adata: 'AnnData',
    resolution: float = 0.8,
    random_state: int = 0,
    key_added: Optional[str] = None,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Perform Leiden clustering at a single resolution.

    Parameters
    ----------
    adata : AnnData
        AnnData object with neighbor graph
    resolution : float, optional
        Resolution parameter (default: 0.8)
    random_state : int, optional
        Random seed (default: 0)
    key_added : str, optional
        Key to add clusters to adata.obs (default: 'leiden_{resolution}')
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with clusters if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if 'neighbors' not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph first.")

    if key_added is None:
        key_added = f'leiden_{resolution}'

    print(f"Clustering with Leiden algorithm (resolution={resolution})...")

    sc.tl.leiden(
        adata,
        resolution=resolution,
        random_state=random_state,
        key_added=key_added
    )

    n_clusters = adata.obs[key_added].nunique()
    print(f"  Identified {n_clusters} clusters")

    # Print cluster sizes
    cluster_sizes = adata.obs[key_added].value_counts().sort_index()
    print(f"  Cluster sizes: min={cluster_sizes.min()}, "
          f"max={cluster_sizes.max()}, "
          f"median={cluster_sizes.median():.0f}")

    # Always return adata for convenience
    return adata


def cluster_leiden_multiple_resolutions(
    adata: 'AnnData',
    resolutions: List[float] = [0.4, 0.6, 0.8, 1.0],
    random_state: int = 0,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Perform Leiden clustering at multiple resolutions.

    Parameters
    ----------
    adata : AnnData
        AnnData object with neighbor graph
    resolutions : list of float, optional
        Resolution parameters to test (default: [0.4, 0.6, 0.8, 1.0])
    random_state : int, optional
        Random seed (default: 0)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with clusters if inplace=False, else None
    """
    if not inplace:
        adata = adata.copy()

    if 'neighbors' not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph first.")

    print(f"Testing {len(resolutions)} resolution parameters...")

    for res in resolutions:
        cluster_leiden(adata, resolution=res, random_state=random_state, inplace=True)

    print("\nClustering summary:")
    print(f"{'Resolution':<12} {'N Clusters':<12} {'Min Size':<12} {'Max Size':<12}")
    print("-" * 50)

    for res in resolutions:
        key = f'leiden_{res}'
        n_clusters = adata.obs[key].nunique()
        cluster_sizes = adata.obs[key].value_counts()
        print(f"{res:<12.2f} {n_clusters:<12} {cluster_sizes.min():<12} {cluster_sizes.max():<12}")

    # Always return adata for convenience
    return adata


def cluster_louvain(
    adata: 'AnnData',
    resolution: float = 0.8,
    random_state: int = 0,
    key_added: Optional[str] = None,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Perform Louvain clustering (alternative to Leiden).

    Parameters
    ----------
    adata : AnnData
        AnnData object with neighbor graph
    resolution : float, optional
        Resolution parameter (default: 0.8)
    random_state : int, optional
        Random seed (default: 0)
    key_added : str, optional
        Key to add clusters to adata.obs (default: 'louvain_{resolution}')
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with clusters if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if 'neighbors' not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph first.")

    if key_added is None:
        key_added = f'louvain_{resolution}'

    print(f"Clustering with Louvain algorithm (resolution={resolution})...")

    sc.tl.louvain(
        adata,
        resolution=resolution,
        random_state=random_state,
        key_added=key_added
    )

    n_clusters = adata.obs[key_added].nunique()
    print(f"  Identified {n_clusters} clusters")

    # Always return adata for convenience
    return adata


def calculate_cluster_qc_stats(
    adata: 'AnnData',
    cluster_key: str = 'leiden_0.8'
) -> 'DataFrame':
    """
    Calculate QC statistics for each cluster.

    Parameters
    ----------
    adata : AnnData
        AnnData object with clusters
    cluster_key : str, optional
        Cluster column in adata.obs (default: 'leiden_0.8')

    Returns
    -------
    DataFrame
        QC statistics per cluster
    """
    import pandas as pd

    if cluster_key not in adata.obs.columns:
        raise ValueError(f"{cluster_key} not found in adata.obs")

    print(f"Calculating QC statistics for clusters in '{cluster_key}'...")

    # Group by cluster
    grouped = adata.obs.groupby(cluster_key)

    # Calculate statistics
    stats = pd.DataFrame({
        'n_cells': grouped.size(),
        'mean_n_genes': grouped['n_genes_by_counts'].mean(),
        'mean_counts': grouped['total_counts'].mean(),
        'mean_pct_mt': grouped['pct_counts_mt'].mean()
    })

    stats = stats.sort_index()

    print("\nCluster QC Statistics:")
    print(stats.to_string())

    return stats

