"""
Hierarchical clustering implementation.

This module provides functions for hierarchical (agglomerative) clustering
with various linkage methods and dendrogram visualization.
"""

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster, dendrogram
from scipy.spatial.distance import pdist
from typing import Tuple, Optional
import matplotlib.pyplot as plt


def hierarchical_clustering(
    data: np.ndarray,
    n_clusters: int,
    linkage_method: str = "ward",
    distance_metric: str = "euclidean",
    plot_dendrogram: bool = False,
    dendrogram_path: Optional[str] = None,
    dendrogram_labels: Optional[list] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Perform hierarchical clustering.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    n_clusters : int
        Number of clusters to form
    linkage_method : str, default="ward"
        Linkage method:
        - "ward": Minimizes within-cluster variance (requires euclidean)
        - "average": Average distance between all pairs
        - "complete": Maximum distance between clusters
        - "single": Minimum distance between clusters
    distance_metric : str, default="euclidean"
        Distance metric for computing pairwise distances
        Options: "euclidean", "manhattan", "cosine", "correlation"
        Note: "ward" only works with "euclidean"
    plot_dendrogram : bool, default=False
        If True, plot and display dendrogram
    dendrogram_path : str, optional
        Path to save dendrogram figure
    dendrogram_labels : list, optional
        Sample labels for dendrogram leaves

    Returns
    -------
    linkage_matrix : np.ndarray
        Hierarchical clustering encoded as linkage matrix
    cluster_labels : np.ndarray
        Cluster assignment for each sample (0 to n_clusters-1)
    """

    print(f"Performing hierarchical clustering ({linkage_method} linkage)...")

    # Validate linkage method and distance metric combination
    if linkage_method == "ward" and distance_metric != "euclidean":
        print("Warning: Ward linkage requires Euclidean distance. Switching to Euclidean.")
        distance_metric = "euclidean"

    # Compute linkage matrix
    if linkage_method == "ward" and distance_metric == "euclidean":
        # Ward can work directly on data
        linkage_matrix = linkage(data, method="ward")
    else:
        # Compute pairwise distances first
        distances = pdist(data, metric=distance_metric)
        linkage_matrix = linkage(distances, method=linkage_method)

    # Form flat clusters
    cluster_labels = fcluster(linkage_matrix, n_clusters, criterion='maxclust')

    # Convert to 0-indexed (fcluster returns 1-indexed)
    cluster_labels = cluster_labels - 1

    # Report results
    unique, counts = np.unique(cluster_labels, return_counts=True)
    print(f"Formed {n_clusters} clusters")
    print("Cluster sizes:", dict(zip(unique, counts)))

    # Plot dendrogram if requested
    if plot_dendrogram or dendrogram_path:
        _plot_dendrogram(
            linkage_matrix,
            n_clusters=n_clusters,
            labels=dendrogram_labels,
            save_path=dendrogram_path
        )

    print(f"\n✓ Clustering completed successfully!")

    return linkage_matrix, cluster_labels


def cut_dendrogram_at_height(
    linkage_matrix: np.ndarray,
    height: float
) -> np.ndarray:
    """
    Cut dendrogram at specified height to form clusters.

    Parameters
    ----------
    linkage_matrix : np.ndarray
        Hierarchical clustering linkage matrix
    height : float
        Height at which to cut dendrogram

    Returns
    -------
    cluster_labels : np.ndarray
        Cluster assignments (0-indexed)
    """

    cluster_labels = fcluster(linkage_matrix, height, criterion='distance')
    cluster_labels = cluster_labels - 1  # Convert to 0-indexed

    n_clusters = len(np.unique(cluster_labels))
    print(f"Cut at height {height:.2f} produces {n_clusters} clusters")

    return cluster_labels


def _plot_dendrogram(
    linkage_matrix: np.ndarray,
    n_clusters: Optional[int] = None,
    labels: Optional[list] = None,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (12, 6)
):
    """
    Plot hierarchical clustering dendrogram.

    Parameters
    ----------
    linkage_matrix : np.ndarray
        Linkage matrix from hierarchical clustering
    n_clusters : int, optional
        If provided, draw horizontal line at cut height
    labels : list, optional
        Leaf labels
    save_path : str, optional
        Path to save figure
    figsize : tuple, default=(12, 6)
        Figure size
    """

    fig, ax = plt.subplots(figsize=figsize)

    # Plot dendrogram
    dendro = dendrogram(
        linkage_matrix,
        labels=labels,
        ax=ax,
        leaf_rotation=90,
        leaf_font_size=8
    )

    # Add horizontal line at cluster cut if specified
    if n_clusters is not None:
        # Calculate height for n_clusters
        # The (n_clusters - 1)th merge from the end
        cut_height = linkage_matrix[-(n_clusters - 1), 2]
        ax.axhline(y=cut_height, c='red', linestyle='--', linewidth=2,
                   label=f'Cut for {n_clusters} clusters')
        ax.legend()

    ax.set_xlabel('Sample', fontsize=12)
    ax.set_ylabel('Distance', fontsize=12)
    ax.set_title('Hierarchical Clustering Dendrogram', fontsize=14, fontweight='bold')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Dendrogram saved to {save_path}")

    plt.show()
    plt.close()


def get_dendrogram_heights(linkage_matrix: np.ndarray, n_top: int = 20) -> np.ndarray:
    """
    Get the heights of the top merges in the dendrogram.

    Useful for determining where to cut the dendrogram.

    Parameters
    ----------
    linkage_matrix : np.ndarray
        Linkage matrix from hierarchical clustering
    n_top : int, default=20
        Number of top merges to return

    Returns
    -------
    heights : np.ndarray
        Heights of top n_top merges (sorted descending)
    """

    # Heights are in the third column of linkage matrix
    heights = linkage_matrix[:, 2]

    # Get top heights (largest distance merges)
    top_heights = np.sort(heights)[-n_top:][::-1]

    print("Top merge heights (largest distances):")
    for i, height in enumerate(top_heights, 1):
        print(f"  {i}: {height:.4f}")

    return top_heights


def compare_linkage_methods(
    data: np.ndarray,
    n_clusters: int,
    methods: list = None
) -> dict:
    """
    Compare different linkage methods on the same data.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    n_clusters : int
        Number of clusters to form
    methods : list, optional
        List of linkage methods to compare
        Default: ["ward", "average", "complete", "single"]

    Returns
    -------
    results : dict
        Dictionary mapping method name to (linkage_matrix, cluster_labels)
    """

    if methods is None:
        methods = ["ward", "average", "complete", "single"]

    print(f"\nComparing {len(methods)} linkage methods...")

    results = {}

    for method in methods:
        try:
            linkage_matrix, cluster_labels = hierarchical_clustering(
                data,
                n_clusters=n_clusters,
                linkage_method=method,
                distance_metric="euclidean",
                plot_dendrogram=False
            )

            results[method] = {
                "linkage_matrix": linkage_matrix,
                "cluster_labels": cluster_labels
            }

            print(f"  ✓ {method}")

        except Exception as e:
            print(f"  ✗ {method}: {e}")

    return results

