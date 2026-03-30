"""
Cluster validation metrics and quality assessment.

This module provides comprehensive metrics for evaluating clustering quality:
- Internal validation (silhouette, Davies-Bouldin, Calinski-Harabasz)
- External validation (if true labels known)
- Cluster separation and compactness metrics
"""

import numpy as np
from sklearn.metrics import (
    silhouette_score,
    davies_bouldin_score,
    calinski_harabasz_score,
    adjusted_rand_score,
    adjusted_mutual_info_score,
    fowlkes_mallows_score,
    normalized_mutual_info_score
)
from typing import Optional, List
import warnings


def validate_clustering(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    metrics: str = "all",
    true_labels: Optional[np.ndarray] = None,
    plot_silhouette: bool = False,
    output_path: Optional[str] = None
) -> dict:
    """
    Comprehensive clustering validation using multiple metrics.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    cluster_labels : np.ndarray
        Cluster assignments
    metrics : str or list, default="all"
        Metrics to compute: "all", "internal", "external", or list of metric names
    true_labels : np.ndarray, optional
        True labels (if known) for external validation
    plot_silhouette : bool, default=False
        If True, create detailed silhouette plot
    output_path : str, optional
        Path to save silhouette plot

    Returns
    -------
    validation_results : dict
        Dictionary with validation metrics
    """

    print("\nValidating clustering quality...")

    results = {}

    # Check for noise points (label -1)
    has_noise = -1 in cluster_labels
    if has_noise:
        n_noise = np.sum(cluster_labels == -1)
        print(f"Note: {n_noise} noise points detected (label -1)")

        # Create clean version without noise for some metrics
        clean_mask = cluster_labels >= 0
        data_clean = data[clean_mask]
        labels_clean = cluster_labels[clean_mask]
    else:
        clean_mask = np.ones(len(cluster_labels), dtype=bool)
        data_clean = data
        labels_clean = cluster_labels

    # Check if we have enough clusters
    n_clusters = len(np.unique(labels_clean))
    if n_clusters < 2:
        print("Warning: Less than 2 clusters. Validation metrics not meaningful.")
        return results

    # Internal validation metrics
    if metrics == "all" or metrics == "internal" or "silhouette" in metrics:
        try:
            silhouette = silhouette_score(data_clean, labels_clean)
            results["silhouette_score"] = silhouette
            print(f"  Silhouette score: {silhouette:.3f} (range: [-1, 1], higher is better)")
            _interpret_silhouette(silhouette)
        except Exception as e:
            print(f"  Could not compute silhouette score: {e}")

    if metrics == "all" or metrics == "internal" or "davies_bouldin" in metrics:
        try:
            db_index = davies_bouldin_score(data_clean, labels_clean)
            results["davies_bouldin_index"] = db_index
            print(f"  Davies-Bouldin index: {db_index:.3f} (range: [0, ∞], lower is better)")
            _interpret_davies_bouldin(db_index)
        except Exception as e:
            print(f"  Could not compute Davies-Bouldin index: {e}")

    if metrics == "all" or metrics == "internal" or "calinski" in metrics:
        try:
            ch_score = calinski_harabasz_score(data_clean, labels_clean)
            results["calinski_harabasz_score"] = ch_score
            print(f"  Calinski-Harabasz score: {ch_score:.1f} (range: [0, ∞], higher is better)")
        except Exception as e:
            print(f"  Could not compute Calinski-Harabasz score: {e}")

    # Compute cluster separation and compactness
    if metrics == "all" or metrics == "internal":
        try:
            sep, comp = compute_separation_compactness(data_clean, labels_clean)
            results["separation"] = sep
            results["compactness"] = comp
            results["separation_compactness_ratio"] = sep / comp if comp > 0 else np.inf
            print(f"  Separation: {sep:.3f}")
            print(f"  Compactness: {comp:.3f}")
            print(f"  Separation/Compactness ratio: {sep/comp:.3f} (higher is better)")
        except Exception as e:
            print(f"  Could not compute separation/compactness: {e}")

    # External validation (if true labels provided)
    if true_labels is not None and (metrics == "all" or metrics == "external"):
        print("\nExternal validation (comparison to true labels):")

        # Align labels (remove noise points from both if present)
        if has_noise:
            true_labels_clean = true_labels[clean_mask]
        else:
            true_labels_clean = true_labels

        try:
            ari = adjusted_rand_score(true_labels_clean, labels_clean)
            results["adjusted_rand_index"] = ari
            print(f"  Adjusted Rand Index: {ari:.3f} (range: [-1, 1], 1 = perfect)")
        except Exception as e:
            print(f"  Could not compute ARI: {e}")

        try:
            ami = adjusted_mutual_info_score(true_labels_clean, labels_clean)
            results["adjusted_mutual_info"] = ami
            print(f"  Adjusted Mutual Info: {ami:.3f} (range: [0, 1], 1 = perfect)")
        except Exception as e:
            print(f"  Could not compute AMI: {e}")

        try:
            nmi = normalized_mutual_info_score(true_labels_clean, labels_clean)
            results["normalized_mutual_info"] = nmi
            print(f"  Normalized Mutual Info: {nmi:.3f} (range: [0, 1], 1 = perfect)")
        except Exception as e:
            print(f"  Could not compute NMI: {e}")

        try:
            fmi = fowlkes_mallows_score(true_labels_clean, labels_clean)
            results["fowlkes_mallows_index"] = fmi
            print(f"  Fowlkes-Mallows Index: {fmi:.3f} (range: [0, 1], 1 = perfect)")
        except Exception as e:
            print(f"  Could not compute FMI: {e}")

    # Detailed silhouette plot if requested
    if plot_silhouette or output_path:
        from scripts.optimal_clusters import silhouette_analysis_per_sample
        silhouette_analysis_per_sample(
            data_clean, labels_clean, plot=True, output_path=output_path
        )

    return results


def _interpret_silhouette(score: float):
    """Provide interpretation of silhouette score."""
    if score > 0.7:
        print("    → Strong, well-separated clusters")
    elif score > 0.5:
        print("    → Reasonable cluster structure")
    elif score > 0.25:
        print("    → Weak cluster structure")
    else:
        print("    → No substantial cluster structure")


def _interpret_davies_bouldin(score: float):
    """Provide interpretation of Davies-Bouldin index."""
    if score < 1.0:
        print("    → Good clustering (compact, separated clusters)")
    elif score < 2.0:
        print("    → Acceptable clustering")
    else:
        print("    → Poor clustering (overlapping or diffuse clusters)")


def compute_separation_compactness(
    data: np.ndarray,
    cluster_labels: np.ndarray
) -> tuple:
    """
    Compute cluster separation and compactness metrics.

    Separation: Average distance between cluster centroids
    Compactness: Average within-cluster distance

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    cluster_labels : np.ndarray
        Cluster assignments

    Returns
    -------
    separation : float
        Average distance between cluster centroids
    compactness : float
        Average within-cluster distance
    """

    unique_labels = np.unique(cluster_labels)
    n_clusters = len(unique_labels)

    # Compute centroids
    centroids = np.zeros((n_clusters, data.shape[1]))
    for i, label in enumerate(unique_labels):
        cluster_mask = cluster_labels == label
        centroids[i] = data[cluster_mask].mean(axis=0)

    # Separation: average distance between centroids
    separation = 0.0
    n_pairs = 0
    for i in range(n_clusters):
        for j in range(i + 1, n_clusters):
            dist = np.linalg.norm(centroids[i] - centroids[j])
            separation += dist
            n_pairs += 1

    if n_pairs > 0:
        separation /= n_pairs
    else:
        separation = 0.0

    # Compactness: average within-cluster distance
    compactness = 0.0
    n_total = 0

    for i, label in enumerate(unique_labels):
        cluster_mask = cluster_labels == label
        cluster_data = data[cluster_mask]

        if len(cluster_data) > 1:
            # Average pairwise distance within cluster
            for i_sample in range(len(cluster_data)):
                for j_sample in range(i_sample + 1, len(cluster_data)):
                    dist = np.linalg.norm(cluster_data[i_sample] - cluster_data[j_sample])
                    compactness += dist
                    n_total += 1

    if n_total > 0:
        compactness /= n_total
    else:
        compactness = 0.0

    return separation, compactness


def compute_cluster_density(
    data: np.ndarray,
    cluster_labels: np.ndarray
) -> dict:
    """
    Compute density metrics for each cluster.

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    cluster_labels : np.ndarray
        Cluster assignments

    Returns
    -------
    densities : dict
        Dictionary mapping cluster label to density metrics
    """

    from sklearn.neighbors import NearestNeighbors

    unique_labels = np.unique(cluster_labels)
    densities = {}

    for label in unique_labels:
        if label == -1:  # Skip noise
            continue

        cluster_mask = cluster_labels == label
        cluster_data = data[cluster_mask]

        if len(cluster_data) < 2:
            densities[int(label)] = {
                "mean_nearest_neighbor_dist": np.nan,
                "std_nearest_neighbor_dist": np.nan
            }
            continue

        # Compute average distance to nearest neighbor within cluster
        k = min(5, len(cluster_data))
        nbrs = NearestNeighbors(n_neighbors=k)
        nbrs.fit(cluster_data)
        distances, _ = nbrs.kneighbors(cluster_data)

        # Use mean of k nearest neighbors
        mean_distances = distances[:, 1:].mean(axis=1)  # Exclude self (distance 0)

        densities[int(label)] = {
            "mean_nearest_neighbor_dist": mean_distances.mean(),
            "std_nearest_neighbor_dist": mean_distances.std(),
            "size": len(cluster_data)
        }

    print("\nCluster Density Analysis:")
    print("Cluster\tSize\tMean NN dist\tStd")
    print("-" * 45)
    for label, metrics in densities.items():
        print(f"{label}\t{metrics['size']}\t{metrics['mean_nearest_neighbor_dist']:.3f}\t\t"
              f"{metrics['std_nearest_neighbor_dist']:.3f}")

    return densities


def compare_clustering_solutions(
    labels1: np.ndarray,
    labels2: np.ndarray,
    method_names: tuple = ("Method 1", "Method 2")
) -> dict:
    """
    Compare two different clustering solutions.

    Parameters
    ----------
    labels1 : np.ndarray
        Cluster labels from first method
    labels2 : np.ndarray
        Cluster labels from second method
    method_names : tuple, default=("Method 1", "Method 2")
        Names of the two methods for display

    Returns
    -------
    comparison : dict
        Comparison metrics
    """

    print(f"\nComparing {method_names[0]} vs {method_names[1]}:")

    # Remove noise points for comparison
    mask = (labels1 >= 0) & (labels2 >= 0)
    labels1_clean = labels1[mask]
    labels2_clean = labels2[mask]

    comparison = {}

    # Adjusted Rand Index
    ari = adjusted_rand_score(labels1_clean, labels2_clean)
    comparison["adjusted_rand_index"] = ari
    print(f"  Adjusted Rand Index: {ari:.3f}")
    if ari > 0.9:
        print("    → Very similar clusterings")
    elif ari > 0.7:
        print("    → Similar clusterings")
    elif ari > 0.3:
        print("    → Somewhat similar clusterings")
    else:
        print("    → Different clusterings")

    # Mutual Information
    nmi = normalized_mutual_info_score(labels1_clean, labels2_clean)
    comparison["normalized_mutual_info"] = nmi
    print(f"  Normalized Mutual Info: {nmi:.3f}")

    # Basic statistics
    n_clusters1 = len(np.unique(labels1_clean))
    n_clusters2 = len(np.unique(labels2_clean))
    print(f"  Number of clusters: {n_clusters1} vs {n_clusters2}")

    comparison["n_clusters"] = (n_clusters1, n_clusters2)

    return comparison


def identify_problematic_samples(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    threshold: float = 0.0
) -> dict:
    """
    Identify samples with negative silhouette scores (poorly clustered).

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    cluster_labels : np.ndarray
        Cluster assignments
    threshold : float, default=0.0
        Silhouette score threshold for "problematic" (typically 0 or negative)

    Returns
    -------
    problematic_info : dict
        Information about problematic samples
    """

    from sklearn.metrics import silhouette_samples

    silhouette_vals = silhouette_samples(data, cluster_labels)

    problematic_mask = silhouette_vals < threshold
    n_problematic = problematic_mask.sum()

    print(f"\nProblematic Samples (silhouette < {threshold}):")
    print(f"  Total: {n_problematic} ({n_problematic / len(cluster_labels) * 100:.1f}%)")

    # Per-cluster breakdown
    unique_labels = np.unique(cluster_labels)
    per_cluster = {}

    for label in unique_labels:
        cluster_mask = cluster_labels == label
        cluster_problematic = problematic_mask & cluster_mask
        n_cluster_problematic = cluster_problematic.sum()

        per_cluster[int(label)] = {
            "n_problematic": n_cluster_problematic,
            "pct_problematic": n_cluster_problematic / cluster_mask.sum() * 100 if cluster_mask.sum() > 0 else 0,
            "indices": np.where(cluster_problematic)[0].tolist()
        }

    print("\nPer-cluster breakdown:")
    print("Cluster\tProblematic\tPercentage")
    print("-" * 40)
    for label, info in per_cluster.items():
        print(f"{label}\t{info['n_problematic']}\t\t{info['pct_problematic']:.1f}%")

    problematic_info = {
        "n_problematic": n_problematic,
        "pct_problematic": n_problematic / len(cluster_labels) * 100,
        "problematic_indices": np.where(problematic_mask)[0].tolist(),
        "silhouette_scores": silhouette_vals,
        "per_cluster": per_cluster
    }

    return problematic_info

