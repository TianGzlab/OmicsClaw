"""
K-means clustering and variants.

This module provides K-means, mini-batch K-means, and K-medoids clustering.
"""

import numpy as np
from sklearn.cluster import KMeans, MiniBatchKMeans
from typing import Tuple, Optional
import warnings

# K-medoids is optional (requires scikit-learn-extra)
try:
    from sklearn_extra.cluster import KMedoids
    KMEDOIDS_AVAILABLE = True
except ImportError:
    KMEDOIDS_AVAILABLE = False


def kmeans_clustering(
    data: np.ndarray,
    n_clusters: int,
    method: str = "kmeans",
    n_init: int = 50,
    max_iter: int = 300,
    random_state: int = 42
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Perform K-means clustering or variants.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    n_clusters : int
        Number of clusters to form
    method : str, default="kmeans"
        Clustering method:
        - "kmeans": Standard K-means
        - "minibatch": Mini-batch K-means (faster for large datasets)
        - "kmedoids": K-medoids (more robust to outliers)
    n_init : int, default=50
        Number of times to run with different initializations
        Higher values = more robust but slower
    max_iter : int, default=300
        Maximum number of iterations per run
    random_state : int, default=42
        Random state for reproducibility

    Returns
    -------
    cluster_labels : np.ndarray
        Cluster assignment for each sample (0 to n_clusters-1)
    centroids : np.ndarray
        Coordinates of cluster centers (n_clusters × n_features)
    inertia : float
        Within-cluster sum of squares (lower is better)
    """

    print(f"Performing {method} clustering (k={n_clusters})...")

    if method == "kmeans":
        model = KMeans(
            n_clusters=n_clusters,
            n_init=n_init,
            max_iter=max_iter,
            random_state=random_state
        )

    elif method == "minibatch":
        model = MiniBatchKMeans(
            n_clusters=n_clusters,
            n_init=n_init,
            max_iter=max_iter,
            random_state=random_state,
            batch_size=min(1000, data.shape[0])
        )

    elif method == "kmedoids":
        if not KMEDOIDS_AVAILABLE:
            raise ImportError(
                "K-medoids requires scikit-learn-extra. "
                "Install with: pip install scikit-learn-extra"
            )

        model = KMedoids(
            n_clusters=n_clusters,
            init='k-medoids++',
            max_iter=max_iter,
            random_state=random_state
        )

    else:
        raise ValueError(f"Unknown method: {method}")

    # Fit model
    model.fit(data)

    cluster_labels = model.labels_
    centroids = model.cluster_centers_
    inertia = model.inertia_

    # Report results
    unique, counts = np.unique(cluster_labels, return_counts=True)
    print(f"Formed {n_clusters} clusters")
    print("Cluster sizes:", dict(zip(unique, counts)))
    print(f"Within-cluster sum of squares (inertia): {inertia:.2f}")

    return cluster_labels, centroids, inertia


def predict_cluster_labels(
    new_data: np.ndarray,
    centroids: np.ndarray
) -> np.ndarray:
    """
    Assign new samples to existing clusters based on centroids.

    Parameters
    ----------
    new_data : np.ndarray
        New data matrix (samples × features)
    centroids : np.ndarray
        Cluster centroids (n_clusters × n_features)

    Returns
    -------
    cluster_labels : np.ndarray
        Cluster assignments for new samples
    """

    # Calculate distance from each sample to each centroid
    distances = np.sqrt(((new_data[:, np.newaxis, :] - centroids[np.newaxis, :, :]) ** 2).sum(axis=2))

    # Assign to nearest centroid
    cluster_labels = np.argmin(distances, axis=1)

    return cluster_labels


def get_cluster_centroids(
    data: np.ndarray,
    cluster_labels: np.ndarray
) -> np.ndarray:
    """
    Calculate centroids for given cluster assignments.

    Useful for hierarchical or other methods that don't provide centroids.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    cluster_labels : np.ndarray
        Cluster assignments

    Returns
    -------
    centroids : np.ndarray
        Cluster centroids (n_clusters × n_features)
    """

    n_clusters = len(np.unique(cluster_labels))
    n_features = data.shape[1]

    centroids = np.zeros((n_clusters, n_features))

    for i in range(n_clusters):
        cluster_mask = cluster_labels == i
        centroids[i] = data[cluster_mask].mean(axis=0)

    return centroids


def calculate_inertia(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    centroids: np.ndarray
) -> float:
    """
    Calculate within-cluster sum of squares (inertia).

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    cluster_labels : np.ndarray
        Cluster assignments
    centroids : np.ndarray
        Cluster centroids

    Returns
    -------
    inertia : float
        Within-cluster sum of squares
    """

    inertia = 0.0

    for i in range(len(centroids)):
        cluster_mask = cluster_labels == i
        cluster_data = data[cluster_mask]

        # Sum of squared distances to centroid
        distances_sq = np.sum((cluster_data - centroids[i]) ** 2, axis=1)
        inertia += distances_sq.sum()

    return inertia


def calculate_between_cluster_variance(
    centroids: np.ndarray,
    cluster_sizes: np.ndarray
) -> float:
    """
    Calculate between-cluster variance.

    Parameters
    ----------
    centroids : np.ndarray
        Cluster centroids (n_clusters × n_features)
    cluster_sizes : np.ndarray
        Number of samples in each cluster

    Returns
    -------
    between_variance : float
        Between-cluster sum of squares
    """

    # Overall centroid (weighted by cluster sizes)
    overall_centroid = np.average(centroids, axis=0, weights=cluster_sizes)

    # Sum of squared distances from each centroid to overall centroid
    # weighted by cluster size
    distances_sq = np.sum((centroids - overall_centroid) ** 2, axis=1)
    between_variance = np.sum(cluster_sizes * distances_sq)

    return between_variance


def kmeans_multiple_runs(
    data: np.ndarray,
    k_values: range,
    method: str = "kmeans",
    n_init: int = 50,
    random_state: int = 42
) -> dict:
    """
    Run K-means for multiple k values.

    Useful for elbow method and finding optimal k.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    k_values : range
        Range of k values to test (e.g., range(2, 16))
    method : str, default="kmeans"
        Clustering method
    n_init : int, default=50
        Number of initializations per k
    random_state : int, default=42
        Random state

    Returns
    -------
    results : dict
        Dictionary with keys:
        - "k_values": list of k values tested
        - "inertias": within-cluster sum of squares for each k
        - "cluster_labels": cluster assignments for each k
        - "centroids": centroids for each k
    """

    print(f"\nRunning K-means for k={min(k_values)} to {max(k_values)}...")

    inertias = []
    all_labels = []
    all_centroids = []

    for k in k_values:
        labels, centroids, inertia = kmeans_clustering(
            data,
            n_clusters=k,
            method=method,
            n_init=n_init,
            random_state=random_state
        )

        inertias.append(inertia)
        all_labels.append(labels)
        all_centroids.append(centroids)

        print(f"  k={k}: inertia={inertia:.2f}")

    results = {
        "k_values": list(k_values),
        "inertias": inertias,
        "cluster_labels": all_labels,
        "centroids": all_centroids
    }

    return results


def find_elbow_point(k_values: list, inertias: list) -> int:
    """
    Find elbow point in inertia curve using angle method.

    Parameters
    ----------
    k_values : list
        List of k values
    inertias : list
        Inertia for each k value

    Returns
    -------
    elbow_k : int
        k value at elbow point
    """

    # Normalize to [0, 1] range
    k_norm = (np.array(k_values) - k_values[0]) / (k_values[-1] - k_values[0])
    inertia_norm = (np.array(inertias) - min(inertias)) / (max(inertias) - min(inertias))

    # Find point with maximum distance to line connecting first and last points
    # This is the "elbow"
    line_vec = np.array([k_norm[-1] - k_norm[0], inertia_norm[-1] - inertia_norm[0]])
    line_vec_norm = line_vec / np.linalg.norm(line_vec)

    distances = []
    for i in range(len(k_values)):
        point_vec = np.array([k_norm[i] - k_norm[0], inertia_norm[i] - inertia_norm[0]])
        # Distance to line
        dist = np.abs(np.cross(line_vec_norm, point_vec))
        distances.append(dist)

    elbow_idx = np.argmax(distances)
    elbow_k = k_values[elbow_idx]

    print(f"\nElbow point detected at k={elbow_k}")

    return elbow_k

