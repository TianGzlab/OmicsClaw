"""
Determine optimal number of clusters using multiple methods.

This module implements various techniques for selecting k:
- Elbow method
- Silhouette analysis
- Gap statistic
- Calinski-Harabasz index
"""

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, calinski_harabasz_score
from scipy.cluster.hierarchy import linkage, fcluster
from typing import Optional, List
import warnings

# Gap statistic is optional
try:
    from gap_stat import optimalK
    GAP_STAT_AVAILABLE = True
except ImportError:
    GAP_STAT_AVAILABLE = False


def find_optimal_clusters(
    data: np.ndarray,
    method: str = "kmeans",
    k_range: range = range(2, 16),
    metrics: List[str] = None,
    plot_results: bool = False,
    output_path: Optional[str] = None
) -> dict:
    """
    Find optimal number of clusters using multiple metrics.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    method : str, default="kmeans"
        Clustering method: "kmeans", "hierarchical", or "gmm"
    k_range : range, default=range(2, 16)
        Range of k values to test
    metrics : List[str], optional
        Metrics to use: "elbow", "silhouette", "gap", "calinski"
        If None, uses all available metrics
    plot_results : bool, default=False
        If True, plot metric curves
    output_path : str, optional
        Path to save plot

    Returns
    -------
    results : dict
        Dictionary with results for each metric:
        - "optimal_k": dict mapping metric name to optimal k
        - "scores": dict mapping metric name to list of scores
        - "k_values": list of k values tested
    """

    if metrics is None:
        metrics = ["elbow", "silhouette", "calinski"]
        if GAP_STAT_AVAILABLE:
            metrics.append("gap")

    print(f"\nFinding optimal clusters using {method}...")
    print(f"Testing k={min(k_range)} to {max(k_range)}")

    k_values = list(k_range)
    results = {
        "k_values": k_values,
        "scores": {},
        "optimal_k": {}
    }

    # Compute clustering for each k
    all_labels = []
    all_inertias = []

    for k in k_values:
        if method == "kmeans":
            from scripts.kmeans_clustering import kmeans_clustering
            labels, centroids, inertia = kmeans_clustering(
                data, n_clusters=k, n_init=50, random_state=42
            )
            all_inertias.append(inertia)

        elif method == "hierarchical":
            from scripts.hierarchical_clustering import hierarchical_clustering
            _, labels = hierarchical_clustering(
                data, n_clusters=k, linkage_method="ward"
            )

        elif method == "gmm":
            from scripts.model_based_clustering import gmm_clustering
            labels, _, _ = gmm_clustering(
                data, n_components=k, n_init=10, random_state=42
            )

        else:
            raise ValueError(f"Unknown method: {method}")

        all_labels.append(labels)

    # Elbow method (inertia)
    if "elbow" in metrics:
        if method == "kmeans" and all_inertias:
            results["scores"]["elbow"] = all_inertias
            optimal_k = _find_elbow_point(k_values, all_inertias)
            results["optimal_k"]["elbow"] = optimal_k
            print(f"  Elbow method: k = {optimal_k}")
        else:
            print("  Elbow method: Only available for k-means")

    # Silhouette score
    if "silhouette" in metrics:
        silhouette_scores = []
        for k, labels in zip(k_values, all_labels):
            if k >= 2 and len(np.unique(labels)) >= 2:
                score = silhouette_score(data, labels)
                silhouette_scores.append(score)
            else:
                silhouette_scores.append(-1)

        results["scores"]["silhouette"] = silhouette_scores
        optimal_idx = np.argmax(silhouette_scores)
        optimal_k = k_values[optimal_idx]
        results["optimal_k"]["silhouette"] = optimal_k
        print(f"  Silhouette: k = {optimal_k} (score={silhouette_scores[optimal_idx]:.3f})")

    # Calinski-Harabasz index
    if "calinski" in metrics:
        ch_scores = []
        for k, labels in zip(k_values, all_labels):
            if k >= 2 and len(np.unique(labels)) >= 2:
                score = calinski_harabasz_score(data, labels)
                ch_scores.append(score)
            else:
                ch_scores.append(0)

        results["scores"]["calinski"] = ch_scores
        optimal_idx = np.argmax(ch_scores)
        optimal_k = k_values[optimal_idx]
        results["optimal_k"]["calinski"] = optimal_k
        print(f"  Calinski-Harabasz: k = {optimal_k} (score={ch_scores[optimal_idx]:.1f})")

    # Gap statistic
    if "gap" in metrics:
        if GAP_STAT_AVAILABLE:
            print("  Computing gap statistic (this may take a while)...")
            try:
                gap_optimal = _compute_gap_statistic(data, k_range)
                results["optimal_k"]["gap"] = gap_optimal
                print(f"  Gap statistic: k = {gap_optimal}")
            except Exception as e:
                print(f"  Gap statistic failed: {e}")
        else:
            print("  Gap statistic: Not available (install with: pip install gap-stat)")

    # Plot results if requested
    if plot_results or output_path:
        _plot_optimal_k_results(results, output_path)

    # Summary
    print("\nSummary of optimal k values:")
    for metric, k in results["optimal_k"].items():
        print(f"  {metric}: k = {k}")

    return results


def _find_elbow_point(k_values: list, scores: list) -> int:
    """Find elbow point using angle method."""
    # Normalize
    k_norm = (np.array(k_values) - k_values[0]) / (k_values[-1] - k_values[0])
    scores_norm = (np.array(scores) - min(scores)) / (max(scores) - min(scores))

    # Find point with maximum distance to line
    line_vec = np.array([k_norm[-1] - k_norm[0], scores_norm[-1] - scores_norm[0]])
    line_vec_norm = line_vec / np.linalg.norm(line_vec)

    distances = []
    for i in range(len(k_values)):
        point_vec = np.array([k_norm[i] - k_norm[0], scores_norm[i] - scores_norm[0]])
        dist = np.abs(np.cross(line_vec_norm, point_vec))
        distances.append(dist)

    elbow_idx = np.argmax(distances)
    return k_values[elbow_idx]


def _compute_gap_statistic(data: np.ndarray, k_range: range) -> int:
    """Compute gap statistic to find optimal k."""
    # Use gap_stat library
    optimalK_instance = optimalK(clusterer=KMeans, k_range=k_range)
    optimal_k = optimalK_instance(data)
    return optimal_k


def _plot_optimal_k_results(results: dict, output_path: Optional[str] = None):
    """Plot optimal k results."""
    import matplotlib.pyplot as plt

    metrics = list(results["scores"].keys())
    n_metrics = len(metrics)

    if n_metrics == 0:
        return

    fig, axes = plt.subplots(1, n_metrics, figsize=(5 * n_metrics, 4))

    if n_metrics == 1:
        axes = [axes]

    k_values = results["k_values"]

    for ax, metric in zip(axes, metrics):
        scores = results["scores"][metric]
        ax.plot(k_values, scores, 'o-', linewidth=2, markersize=8)

        # Mark optimal k
        if metric in results["optimal_k"]:
            optimal_k = results["optimal_k"][metric]
            optimal_idx = k_values.index(optimal_k)
            ax.axvline(optimal_k, color='red', linestyle='--', linewidth=2,
                      label=f'Optimal k={optimal_k}')
            ax.plot(optimal_k, scores[optimal_idx], 'ro', markersize=12)

        ax.set_xlabel('Number of clusters (k)', fontsize=12)
        ax.set_ylabel(metric.capitalize() + ' score', fontsize=12)
        ax.set_title(f'{metric.capitalize()} Method', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend()

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nPlot saved to {output_path}")

    plt.show()
    plt.close()


def silhouette_analysis_per_sample(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    plot: bool = True,
    output_path: Optional[str] = None
) -> dict:
    """
    Detailed silhouette analysis for each sample.

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    cluster_labels : np.ndarray
        Cluster assignments
    plot : bool, default=True
        If True, create silhouette plot
    output_path : str, optional
        Path to save plot

    Returns
    -------
    analysis : dict
        Silhouette analysis results including per-sample scores
    """
    from sklearn.metrics import silhouette_samples

    # Compute silhouette score for each sample
    silhouette_vals = silhouette_samples(data, cluster_labels)

    # Overall silhouette score
    overall_score = silhouette_score(data, cluster_labels)

    # Per-cluster analysis
    unique_labels = np.unique(cluster_labels)
    cluster_scores = {}

    for label in unique_labels:
        mask = cluster_labels == label
        cluster_sil = silhouette_vals[mask]
        cluster_scores[int(label)] = {
            "mean": cluster_sil.mean(),
            "median": np.median(cluster_sil),
            "min": cluster_sil.min(),
            "max": cluster_sil.max(),
            "std": cluster_sil.std(),
            "size": mask.sum()
        }

    print("\nSilhouette Analysis:")
    print(f"Overall score: {overall_score:.3f}")
    print("\nPer-cluster scores:")
    print("Cluster\tSize\tMean\tMedian\tMin\tMax")
    print("-" * 60)
    for label, scores in cluster_scores.items():
        print(f"{label}\t{scores['size']}\t{scores['mean']:.3f}\t"
              f"{scores['median']:.3f}\t{scores['min']:.3f}\t{scores['max']:.3f}")

    # Plot silhouette diagram
    if plot or output_path:
        _plot_silhouette_diagram(
            silhouette_vals, cluster_labels, overall_score, output_path
        )

    analysis = {
        "overall_score": overall_score,
        "per_sample_scores": silhouette_vals,
        "per_cluster_scores": cluster_scores
    }

    return analysis


def _plot_silhouette_diagram(
    silhouette_vals: np.ndarray,
    cluster_labels: np.ndarray,
    overall_score: float,
    output_path: Optional[str] = None
):
    """Create silhouette diagram showing per-sample scores."""
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm

    n_clusters = len(np.unique(cluster_labels))

    fig, ax = plt.subplots(figsize=(8, 6))

    y_lower = 10
    unique_labels = np.unique(cluster_labels)

    for i, label in enumerate(unique_labels):
        # Get silhouette scores for this cluster
        cluster_mask = cluster_labels == label
        cluster_silhouette_vals = silhouette_vals[cluster_mask]
        cluster_silhouette_vals.sort()

        size_cluster = cluster_silhouette_vals.shape[0]
        y_upper = y_lower + size_cluster

        color = cm.nipy_spectral(float(i) / n_clusters)
        ax.fill_betweenx(
            np.arange(y_lower, y_upper),
            0,
            cluster_silhouette_vals,
            facecolor=color,
            edgecolor=color,
            alpha=0.7
        )

        # Label clusters
        ax.text(-0.05, y_lower + 0.5 * size_cluster, str(label))

        y_lower = y_upper + 10

    ax.set_title(f'Silhouette Plot (overall score: {overall_score:.3f})',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel('Silhouette coefficient', fontsize=12)
    ax.set_ylabel('Cluster', fontsize=12)

    # Vertical line for average silhouette score
    ax.axvline(x=overall_score, color="red", linestyle="--", linewidth=2,
               label=f'Mean score: {overall_score:.3f}')
    ax.axvline(x=0, color="black", linestyle="-", linewidth=0.5)

    ax.set_xlim([-0.2, 1])
    ax.set_ylim([0, y_lower])
    ax.legend()

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Silhouette plot saved to {output_path}")

    plt.show()
    plt.close()

