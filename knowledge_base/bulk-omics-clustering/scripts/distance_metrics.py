"""
Distance matrix calculation for clustering analysis.

This module provides functions to compute pairwise distances between
samples/features using various distance metrics.
"""

import numpy as np
from scipy.spatial.distance import pdist, squareform
from scipy.stats import spearmanr
from sklearn.metrics.pairwise import cosine_distances
from typing import Optional
import warnings


def calculate_distance_matrix(
    data: np.ndarray,
    metric: str = "euclidean",
    show_distribution: bool = False
) -> np.ndarray:
    """
    Calculate pairwise distance matrix between samples.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    metric : str, default="euclidean"
        Distance metric to use:
        - "euclidean": Euclidean distance
        - "correlation": 1 - Pearson correlation
        - "spearman": 1 - Spearman correlation
        - "manhattan": Manhattan (L1) distance
        - "cosine": Cosine distance
        - "canberra": Canberra distance
        - "chebyshev": Chebyshev distance
    show_distribution : bool, default=False
        If True, print distance distribution statistics

    Returns
    -------
    distance_matrix : np.ndarray
        Pairwise distance matrix (n_samples × n_samples)
    """

    print(f"Calculating {metric} distance matrix...")

    if metric == "correlation":
        # Pearson correlation distance
        # pdist with 'correlation' computes 1 - Pearson correlation
        distances = pdist(data, metric='correlation')
        distance_matrix = squareform(distances)

    elif metric == "spearman":
        # Spearman correlation distance
        n_samples = data.shape[0]
        distance_matrix = np.zeros((n_samples, n_samples))

        for i in range(n_samples):
            for j in range(i + 1, n_samples):
                corr, _ = spearmanr(data[i], data[j])
                # Convert correlation to distance (1 - correlation)
                dist = 1 - corr
                distance_matrix[i, j] = dist
                distance_matrix[j, i] = dist

    elif metric == "cosine":
        # Cosine distance
        distance_matrix = cosine_distances(data)

    elif metric in ["euclidean", "manhattan", "canberra", "chebyshev"]:
        # Use scipy's pdist for these standard metrics
        distances = pdist(data, metric=metric)
        distance_matrix = squareform(distances)

    else:
        raise ValueError(
            f"Unknown metric: {metric}. Choose from: euclidean, correlation, "
            f"spearman, manhattan, cosine, canberra, chebyshev"
        )

    # Ensure diagonal is zero (should be, but numerical precision)
    np.fill_diagonal(distance_matrix, 0)

    # Report statistics
    print(f"Distance matrix shape: {distance_matrix.shape}")

    if show_distribution:
        # Get upper triangle (exclude diagonal)
        upper_triangle = distance_matrix[np.triu_indices_from(distance_matrix, k=1)]

        print(f"\nDistance distribution:")
        print(f"  Min: {upper_triangle.min():.4f}")
        print(f"  25%: {np.percentile(upper_triangle, 25):.4f}")
        print(f"  Median: {np.median(upper_triangle):.4f}")
        print(f"  Mean: {upper_triangle.mean():.4f}")
        print(f"  75%: {np.percentile(upper_triangle, 75):.4f}")
        print(f"  Max: {upper_triangle.max():.4f}")
        print(f"  Std: {upper_triangle.std():.4f}")

    return distance_matrix


def calculate_distance_to_centroid(
    data: np.ndarray,
    centroid: np.ndarray,
    metric: str = "euclidean"
) -> np.ndarray:
    """
    Calculate distance from each sample to a centroid.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    centroid : np.ndarray
        Centroid coordinates (1D array of length = n_features)
    metric : str, default="euclidean"
        Distance metric (same options as calculate_distance_matrix)

    Returns
    -------
    distances : np.ndarray
        1D array of distances from each sample to centroid
    """

    if metric == "euclidean":
        distances = np.sqrt(np.sum((data - centroid) ** 2, axis=1))

    elif metric == "manhattan":
        distances = np.sum(np.abs(data - centroid), axis=1)

    elif metric == "correlation":
        # 1 - Pearson correlation
        centroid_mean = centroid.mean()
        centroid_std = centroid.std()

        distances = np.zeros(data.shape[0])
        for i in range(data.shape[0]):
            data_mean = data[i].mean()
            data_std = data[i].std()

            if data_std == 0 or centroid_std == 0:
                distances[i] = 1.0  # Maximum distance
            else:
                corr = np.corrcoef(data[i], centroid)[0, 1]
                distances[i] = 1 - corr

    elif metric == "cosine":
        # Cosine distance
        centroid_2d = centroid.reshape(1, -1)
        distances = cosine_distances(data, centroid_2d).flatten()

    else:
        raise ValueError(f"Unsupported metric for centroid distance: {metric}")

    return distances


def get_nearest_neighbors(
    distance_matrix: np.ndarray,
    k: int = 5,
    return_distances: bool = False
):
    """
    Find k nearest neighbors for each sample.

    Parameters
    ----------
    distance_matrix : np.ndarray
        Pairwise distance matrix (n_samples × n_samples)
    k : int, default=5
        Number of nearest neighbors to find
    return_distances : bool, default=False
        If True, also return distances to neighbors

    Returns
    -------
    neighbor_indices : np.ndarray
        Array of shape (n_samples, k) with indices of k nearest neighbors
    neighbor_distances : np.ndarray, optional
        Array of shape (n_samples, k) with distances to neighbors
        (only if return_distances=True)
    """

    n_samples = distance_matrix.shape[0]

    if k >= n_samples:
        raise ValueError(f"k ({k}) must be less than number of samples ({n_samples})")

    # For each sample, get indices of k nearest neighbors (excluding self)
    neighbor_indices = np.zeros((n_samples, k), dtype=int)
    neighbor_distances = np.zeros((n_samples, k))

    for i in range(n_samples):
        # Get distances to all other samples (set self-distance to inf)
        distances = distance_matrix[i].copy()
        distances[i] = np.inf

        # Get indices of k smallest distances
        nearest_idx = np.argpartition(distances, k)[:k]
        # Sort them by distance
        nearest_idx = nearest_idx[np.argsort(distances[nearest_idx])]

        neighbor_indices[i] = nearest_idx
        neighbor_distances[i] = distances[nearest_idx]

    if return_distances:
        return neighbor_indices, neighbor_distances
    else:
        return neighbor_indices


def compare_distance_metrics(
    data: np.ndarray,
    metrics: list = None
) -> dict:
    """
    Calculate distance matrices using multiple metrics for comparison.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    metrics : list, optional
        List of metrics to compare. If None, uses common metrics:
        ["euclidean", "correlation", "manhattan", "cosine"]

    Returns
    -------
    distance_matrices : dict
        Dictionary mapping metric name to distance matrix
    """

    if metrics is None:
        metrics = ["euclidean", "correlation", "manhattan", "cosine"]

    print(f"Comparing {len(metrics)} distance metrics...")

    distance_matrices = {}

    for metric in metrics:
        try:
            distance_matrices[metric] = calculate_distance_matrix(
                data, metric=metric, show_distribution=False
            )
            print(f"  ✓ {metric}")
        except Exception as e:
            print(f"  ✗ {metric}: {e}")

    return distance_matrices

