"""
Density-based clustering (DBSCAN and HDBSCAN).

This module provides density-based clustering methods that can find
arbitrary-shaped clusters and identify noise/outliers.
"""

import numpy as np
from sklearn.cluster import DBSCAN
from typing import Tuple, Optional
import warnings

# HDBSCAN is optional but recommended
try:
    import hdbscan
    HDBSCAN_AVAILABLE = True
except ImportError:
    HDBSCAN_AVAILABLE = False
    warnings.warn("HDBSCAN not available. Install with: pip install hdbscan")


def hdbscan_clustering(
    data: np.ndarray,
    min_cluster_size: int = 10,
    min_samples: Optional[int] = None,
    metric: str = "euclidean",
    cluster_selection_method: str = "eom",
    plot_hierarchy: bool = False
) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Perform HDBSCAN (Hierarchical Density-Based Spatial Clustering).

    HDBSCAN advantages:
    - Automatically determines number of clusters
    - Finds arbitrary-shaped clusters
    - Identifies noise/outliers (label = -1)
    - More stable than DBSCAN
    - Provides cluster membership probabilities

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    min_cluster_size : int, default=10
        Minimum number of samples in a cluster
        Smaller = more clusters; Larger = fewer, denser clusters
    min_samples : int, optional
        Number of samples in neighborhood for core point
        If None, uses min_cluster_size
        Higher = more conservative (denser clusters)
    metric : str, default="euclidean"
        Distance metric
    cluster_selection_method : str, default="eom"
        Method for selecting clusters from hierarchy:
        - "eom": Excess of Mass (default, good general choice)
        - "leaf": Selects leaf clusters (more granular)
    plot_hierarchy : bool, default=False
        If True, plot cluster hierarchy

    Returns
    -------
    cluster_labels : np.ndarray
        Cluster assignments (noise points labeled as -1)
    probabilities : np.ndarray
        Cluster membership probabilities (0-1)
    n_clusters : int
        Number of clusters found (excluding noise)
    """

    if not HDBSCAN_AVAILABLE:
        raise ImportError("HDBSCAN not installed. Install with: pip install hdbscan")

    print(f"Performing HDBSCAN clustering...")
    print(f"  min_cluster_size={min_cluster_size}, min_samples={min_samples}")

    if min_samples is None:
        min_samples = min_cluster_size

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric=metric,
        cluster_selection_method=cluster_selection_method,
        prediction_data=True  # Enable prediction on new data
    )

    cluster_labels = clusterer.fit_predict(data)
    probabilities = clusterer.probabilities_

    # Count clusters (excluding noise = -1)
    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    n_noise = np.sum(cluster_labels == -1)

    print(f"\nFound {n_clusters} clusters")
    print(f"Noise points: {n_noise} ({n_noise / len(cluster_labels) * 100:.1f}%)")

    # Report cluster sizes
    if n_clusters > 0:
        unique_labels = np.unique(cluster_labels[cluster_labels >= 0])
        sizes = [np.sum(cluster_labels == label) for label in unique_labels]
        print("Cluster sizes:", dict(zip(unique_labels, sizes)))

    # Plot hierarchy if requested
    if plot_hierarchy and hasattr(clusterer, 'condensed_tree_'):
        try:
            import matplotlib.pyplot as plt
            clusterer.condensed_tree_.plot(select_clusters=True, selection_palette=plt.cm.viridis)
            plt.title('HDBSCAN Cluster Hierarchy')
            plt.show()
        except Exception as e:
            print(f"Could not plot hierarchy: {e}")

    return cluster_labels, probabilities, n_clusters


def dbscan_clustering(
    data: np.ndarray,
    eps: float,
    min_samples: int = 5,
    metric: str = "euclidean"
) -> Tuple[np.ndarray, int]:
    """
    Perform DBSCAN (Density-Based Spatial Clustering of Applications with Noise).

    Note: HDBSCAN is generally preferred as it doesn't require eps parameter.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    eps : float
        Maximum distance between samples to be considered neighbors
        Critical parameter - requires tuning
    min_samples : int, default=5
        Minimum samples in neighborhood for core point
    metric : str, default="euclidean"
        Distance metric

    Returns
    -------
    cluster_labels : np.ndarray
        Cluster assignments (noise points labeled as -1)
    n_clusters : int
        Number of clusters found (excluding noise)
    """

    print(f"Performing DBSCAN clustering (eps={eps}, min_samples={min_samples})...")

    clusterer = DBSCAN(
        eps=eps,
        min_samples=min_samples,
        metric=metric
    )

    cluster_labels = clusterer.fit_predict(data)

    # Count clusters (excluding noise = -1)
    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    n_noise = np.sum(cluster_labels == -1)

    print(f"\nFound {n_clusters} clusters")
    print(f"Noise points: {n_noise} ({n_noise / len(cluster_labels) * 100:.1f}%)")

    if n_clusters > 0:
        unique_labels = np.unique(cluster_labels[cluster_labels >= 0])
        sizes = [np.sum(cluster_labels == label) for label in unique_labels]
        print("Cluster sizes:", dict(zip(unique_labels, sizes)))

    return cluster_labels, n_clusters


def estimate_dbscan_eps(
    data: np.ndarray,
    min_samples: int = 5,
    percentile: float = 90
) -> float:
    """
    Estimate eps parameter for DBSCAN using k-distance plot.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    min_samples : int, default=5
        min_samples parameter to use
    percentile : float, default=90
        Percentile of k-distances to use as eps estimate

    Returns
    -------
    eps : float
        Estimated eps parameter
    """

    from sklearn.neighbors import NearestNeighbors

    print(f"Estimating DBSCAN eps parameter (k={min_samples})...")

    # Fit k-nearest neighbors
    nbrs = NearestNeighbors(n_neighbors=min_samples)
    nbrs.fit(data)

    # Get distances to k-th nearest neighbor
    distances, _ = nbrs.kneighbors(data)
    k_distances = np.sort(distances[:, -1])

    # Use specified percentile as eps estimate
    eps = np.percentile(k_distances, percentile)

    print(f"Suggested eps: {eps:.4f} ({percentile}th percentile of k-distances)")
    print(f"k-distance range: [{k_distances.min():.4f}, {k_distances.max():.4f}]")

    return eps


def tune_hdbscan_min_cluster_size(
    data: np.ndarray,
    min_cluster_sizes: list,
    metric: str = "euclidean"
) -> dict:
    """
    Try different min_cluster_size values to find optimal setting.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    min_cluster_sizes : list
        List of min_cluster_size values to try
    metric : str, default="euclidean"
        Distance metric

    Returns
    -------
    results : dict
        Dictionary with results for each min_cluster_size:
        - "n_clusters": number of clusters found
        - "n_noise": number of noise points
        - "cluster_labels": cluster assignments
    """

    if not HDBSCAN_AVAILABLE:
        raise ImportError("HDBSCAN not installed")

    print(f"\nTuning HDBSCAN min_cluster_size parameter...")

    results = {}

    for mcs in min_cluster_sizes:
        labels, probs, n_clusters = hdbscan_clustering(
            data,
            min_cluster_size=mcs,
            metric=metric,
            plot_hierarchy=False
        )

        n_noise = np.sum(labels == -1)

        results[mcs] = {
            "n_clusters": n_clusters,
            "n_noise": n_noise,
            "noise_pct": n_noise / len(labels) * 100,
            "cluster_labels": labels,
            "probabilities": probs
        }

        print(f"  min_cluster_size={mcs}: {n_clusters} clusters, {n_noise} noise ({n_noise/len(labels)*100:.1f}%)")

    return results


def get_cluster_persistence(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    probabilities: np.ndarray,
    threshold: float = 0.5
) -> dict:
    """
    Analyze cluster persistence/stability from HDBSCAN probabilities.

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    cluster_labels : np.ndarray
        Cluster assignments from HDBSCAN
    probabilities : np.ndarray
        Cluster membership probabilities from HDBSCAN
    threshold : float, default=0.5
        Probability threshold for "confident" assignments

    Returns
    -------
    persistence_info : dict
        Dictionary with persistence statistics per cluster
    """

    unique_labels = np.unique(cluster_labels[cluster_labels >= 0])

    persistence_info = {}

    for label in unique_labels:
        mask = cluster_labels == label
        cluster_probs = probabilities[mask]

        persistence_info[int(label)] = {
            "size": mask.sum(),
            "mean_probability": cluster_probs.mean(),
            "median_probability": np.median(cluster_probs),
            "min_probability": cluster_probs.min(),
            "n_confident": np.sum(cluster_probs >= threshold),
            "pct_confident": np.sum(cluster_probs >= threshold) / len(cluster_probs) * 100
        }

    print("\nCluster Persistence Analysis:")
    print("Cluster\tSize\tMean Prob\tConfident %")
    print("-" * 50)
    for label, info in persistence_info.items():
        print(f"{label}\t{info['size']}\t{info['mean_probability']:.3f}\t\t{info['pct_confident']:.1f}%")

    return persistence_info

