"""
Clustering stability analysis using bootstrap resampling.

This module assesses how robust clustering results are to data perturbations
through bootstrap resampling and consensus clustering.
"""

import numpy as np
from sklearn.cluster import KMeans
from scipy.cluster.hierarchy import linkage, fcluster
from typing import Optional, Callable
import warnings


def stability_analysis(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    clustering_method: str = "kmeans",
    n_bootstrap: int = 100,
    sample_fraction: float = 0.8,
    plot_consensus: bool = False,
    output_path: Optional[str] = None,
    random_state: int = 42
) -> dict:
    """
    Assess clustering stability through bootstrap resampling.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    cluster_labels : np.ndarray
        Original cluster assignments
    clustering_method : str, default="kmeans"
        Clustering method: "kmeans", "hierarchical", "hdbscan", "gmm"
    n_bootstrap : int, default=100
        Number of bootstrap iterations
    sample_fraction : float, default=0.8
        Fraction of samples to include in each bootstrap
    plot_consensus : bool, default=False
        If True, plot consensus matrix heatmap
    output_path : str, optional
        Path to save consensus matrix plot
    random_state : int, default=42
        Random state for reproducibility

    Returns
    -------
    stability_results : dict
        Dictionary with stability metrics:
        - "mean_stability": Average stability score across all samples
        - "per_sample_stability": Stability score for each sample
        - "consensus_matrix": Co-clustering frequency matrix
        - "n_iterations": Number of bootstrap iterations
    """

    print(f"\nPerforming stability analysis ({n_bootstrap} bootstrap iterations)...")

    np.random.seed(random_state)
    n_samples = data.shape[0]
    n_clusters = len(np.unique(cluster_labels[cluster_labels >= 0]))

    # Initialize consensus matrix (co-clustering frequency)
    consensus_matrix = np.zeros((n_samples, n_samples))
    sample_counts = np.zeros((n_samples, n_samples))  # Track how often pairs appear together

    # Bootstrap iterations
    for iteration in range(n_bootstrap):
        # Sample with replacement
        n_sample = int(n_samples * sample_fraction)
        sample_indices = np.random.choice(n_samples, size=n_sample, replace=True)
        unique_indices = np.unique(sample_indices)

        # Get bootstrap sample
        bootstrap_data = data[unique_indices]

        # Perform clustering on bootstrap sample
        try:
            if clustering_method == "kmeans":
                from sklearn.cluster import KMeans
                clusterer = KMeans(n_clusters=n_clusters, n_init=10, random_state=iteration)
                bootstrap_labels = clusterer.fit_predict(bootstrap_data)

            elif clustering_method == "hierarchical":
                linkage_matrix = linkage(bootstrap_data, method="ward")
                bootstrap_labels = fcluster(linkage_matrix, n_clusters, criterion='maxclust') - 1

            elif clustering_method == "hdbscan":
                try:
                    import hdbscan
                    clusterer = hdbscan.HDBSCAN(min_cluster_size=max(5, n_samples // (n_clusters * 2)))
                    bootstrap_labels = clusterer.fit_predict(bootstrap_data)
                except ImportError:
                    print("HDBSCAN not available, falling back to k-means")
                    clusterer = KMeans(n_clusters=n_clusters, n_init=10, random_state=iteration)
                    bootstrap_labels = clusterer.fit_predict(bootstrap_data)

            elif clustering_method == "gmm":
                from sklearn.mixture import GaussianMixture
                gmm = GaussianMixture(n_components=n_clusters, n_init=5, random_state=iteration)
                bootstrap_labels = gmm.fit_predict(bootstrap_data)

            else:
                raise ValueError(f"Unknown clustering method: {clustering_method}")

            # Update consensus matrix
            for i in range(len(unique_indices)):
                for j in range(i + 1, len(unique_indices)):
                    idx_i = unique_indices[i]
                    idx_j = unique_indices[j]

                    # Check if in same cluster
                    if bootstrap_labels[i] == bootstrap_labels[j] and bootstrap_labels[i] >= 0:
                        consensus_matrix[idx_i, idx_j] += 1
                        consensus_matrix[idx_j, idx_i] += 1

                    # Track number of times this pair appears together
                    sample_counts[idx_i, idx_j] += 1
                    sample_counts[idx_j, idx_i] += 1

        except Exception as e:
            warnings.warn(f"Bootstrap iteration {iteration} failed: {e}")
            continue

        if (iteration + 1) % 20 == 0:
            print(f"  Completed {iteration + 1}/{n_bootstrap} iterations")

    # Normalize consensus matrix by number of times each pair appeared
    with np.errstate(divide='ignore', invalid='ignore'):
        consensus_matrix = np.where(sample_counts > 0, consensus_matrix / sample_counts, 0)

    # Set diagonal to 1 (sample always clusters with itself)
    np.fill_diagonal(consensus_matrix, 1.0)

    # Compute stability for each sample
    # Stability = average co-clustering frequency with samples in same original cluster
    per_sample_stability = np.zeros(n_samples)

    for i in range(n_samples):
        if cluster_labels[i] >= 0:
            same_cluster_mask = (cluster_labels == cluster_labels[i]) & (np.arange(n_samples) != i)
            if same_cluster_mask.sum() > 0:
                per_sample_stability[i] = consensus_matrix[i, same_cluster_mask].mean()
            else:
                per_sample_stability[i] = 1.0  # Singleton cluster
        else:
            per_sample_stability[i] = np.nan  # Noise point

    # Overall mean stability
    valid_mask = ~np.isnan(per_sample_stability)
    mean_stability = per_sample_stability[valid_mask].mean() if valid_mask.sum() > 0 else 0.0

    print(f"\nStability Analysis Results:")
    print(f"  Mean stability: {mean_stability:.3f}")
    _interpret_stability(mean_stability)

    # Per-cluster stability
    unique_labels = np.unique(cluster_labels[cluster_labels >= 0])
    print("\nPer-cluster stability:")
    print("Cluster\tStability")
    print("-" * 25)

    for label in unique_labels:
        cluster_mask = cluster_labels == label
        cluster_stability = per_sample_stability[cluster_mask].mean()
        print(f"{label}\t{cluster_stability:.3f}")

    # Plot consensus matrix if requested
    if plot_consensus or output_path:
        _plot_consensus_matrix(
            consensus_matrix, cluster_labels, output_path
        )

    stability_results = {
        "mean_stability": mean_stability,
        "per_sample_stability": per_sample_stability,
        "consensus_matrix": consensus_matrix,
        "n_iterations": n_bootstrap,
        "sample_fraction": sample_fraction
    }

    return stability_results


def _interpret_stability(stability: float):
    """Provide interpretation of stability score."""
    if stability > 0.85:
        print("    → High stability: Clusters are robust and reproducible")
    elif stability > 0.7:
        print("    → Moderate stability: Acceptable but some uncertainty")
    else:
        print("    → Low stability: Clusters may not be reliable")


def _plot_consensus_matrix(
    consensus_matrix: np.ndarray,
    cluster_labels: np.ndarray,
    output_path: Optional[str] = None
):
    """Plot consensus matrix as heatmap."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    # Sort samples by cluster assignment for clearer visualization
    sort_idx = np.argsort(cluster_labels)
    consensus_sorted = consensus_matrix[sort_idx][:, sort_idx]
    labels_sorted = cluster_labels[sort_idx]

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 8))

    # Plot heatmap
    sns.heatmap(
        consensus_sorted,
        cmap='RdBu_r',
        center=0.5,
        vmin=0,
        vmax=1,
        square=True,
        cbar_kws={'label': 'Co-clustering frequency'},
        xticklabels=False,
        yticklabels=False,
        ax=ax
    )

    # Add cluster boundaries
    unique_labels = np.unique(labels_sorted[labels_sorted >= 0])
    boundaries = []
    for label in unique_labels:
        if label >= 0:
            idx = np.where(labels_sorted == label)[0]
            if len(idx) > 0:
                boundaries.append(idx[-1] + 0.5)

    for boundary in boundaries[:-1]:  # Don't draw line at the end
        ax.axhline(boundary, color='black', linewidth=2)
        ax.axvline(boundary, color='black', linewidth=2)

    ax.set_title('Consensus Matrix (Bootstrap Stability)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Samples (sorted by cluster)', fontsize=12)
    ax.set_ylabel('Samples (sorted by cluster)', fontsize=12)

    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"\nConsensus matrix saved to {output_path}")

    plt.show()
    plt.close()


def permutation_test_stability(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    clustering_func: Callable,
    n_permutations: int = 100,
    random_state: int = 42
) -> dict:
    """
    Test clustering stability using permutation test.

    Randomly permute features and re-cluster to assess if clustering
    is robust or due to chance.

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    cluster_labels : np.ndarray
        Original cluster assignments
    clustering_func : Callable
        Function that takes data and returns cluster labels
    n_permutations : int, default=100
        Number of permutations
    random_state : int, default=42
        Random state

    Returns
    -------
    results : dict
        Permutation test results including p-value
    """

    from sklearn.metrics import adjusted_rand_score

    print(f"\nPerforming permutation test ({n_permutations} permutations)...")

    np.random.seed(random_state)

    # Compute baseline clustering quality (silhouette score)
    from sklearn.metrics import silhouette_score
    baseline_score = silhouette_score(data, cluster_labels)

    # Permutation scores
    permuted_scores = []

    for i in range(n_permutations):
        # Permute each feature independently
        permuted_data = data.copy()
        for j in range(data.shape[1]):
            np.random.shuffle(permuted_data[:, j])

        # Cluster permuted data
        try:
            permuted_labels = clustering_func(permuted_data)

            # Compute quality of permuted clustering
            if len(np.unique(permuted_labels)) > 1:
                score = silhouette_score(permuted_data, permuted_labels)
                permuted_scores.append(score)
        except:
            continue

        if (i + 1) % 20 == 0:
            print(f"  Completed {i + 1}/{n_permutations} permutations")

    # Compute p-value: fraction of permuted scores >= baseline
    permuted_scores = np.array(permuted_scores)
    p_value = np.mean(permuted_scores >= baseline_score)

    print(f"\nPermutation Test Results:")
    print(f"  Baseline silhouette: {baseline_score:.3f}")
    print(f"  Mean permuted silhouette: {permuted_scores.mean():.3f}")
    print(f"  P-value: {p_value:.4f}")

    if p_value < 0.05:
        print("    → Clustering is significant (not due to chance)")
    else:
        print("    → Clustering may not be significant")

    results = {
        "baseline_score": baseline_score,
        "permuted_scores": permuted_scores,
        "p_value": p_value,
        "n_permutations": len(permuted_scores)
    }

    return results


def cross_validation_stability(
    data: np.ndarray,
    n_clusters: int,
    clustering_method: str = "kmeans",
    n_folds: int = 5,
    random_state: int = 42
) -> dict:
    """
    Assess clustering stability using cross-validation.

    Split data into folds, cluster each fold, and assess agreement.

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    n_clusters : int
        Number of clusters
    clustering_method : str, default="kmeans"
        Clustering method
    n_folds : int, default=5
        Number of CV folds
    random_state : int, default=42
        Random state

    Returns
    -------
    cv_results : dict
        Cross-validation stability results
    """

    from sklearn.model_selection import KFold
    from sklearn.metrics import adjusted_rand_score

    print(f"\nCross-validation stability ({n_folds} folds)...")

    kfold = KFold(n_splits=n_folds, shuffle=True, random_state=random_state)

    fold_labels = []

    for fold_idx, (train_idx, test_idx) in enumerate(kfold.split(data)):
        train_data = data[train_idx]

        # Cluster training data
        if clustering_method == "kmeans":
            from sklearn.cluster import KMeans
            clusterer = KMeans(n_clusters=n_clusters, n_init=25, random_state=random_state)
            clusterer.fit(train_data)

            # Predict on all data
            all_labels = clusterer.predict(data)

        elif clustering_method == "hierarchical":
            # For hierarchical, cluster all data
            linkage_matrix = linkage(data, method="ward")
            all_labels = fcluster(linkage_matrix, n_clusters, criterion='maxclust') - 1

        elif clustering_method == "gmm":
            from sklearn.mixture import GaussianMixture
            gmm = GaussianMixture(n_components=n_clusters, n_init=5, random_state=random_state)
            gmm.fit(train_data)
            all_labels = gmm.predict(data)

        else:
            raise ValueError(f"Unknown method: {clustering_method}")

        fold_labels.append(all_labels)

    # Compute pairwise agreement between folds
    agreements = []
    for i in range(n_folds):
        for j in range(i + 1, n_folds):
            ari = adjusted_rand_score(fold_labels[i], fold_labels[j])
            agreements.append(ari)

    mean_agreement = np.mean(agreements)

    print(f"  Mean pairwise agreement (ARI): {mean_agreement:.3f}")

    if mean_agreement > 0.8:
        print("    → High cross-validation stability")
    elif mean_agreement > 0.6:
        print("    → Moderate cross-validation stability")
    else:
        print("    → Low cross-validation stability")

    cv_results = {
        "mean_agreement": mean_agreement,
        "pairwise_agreements": agreements,
        "fold_labels": fold_labels
    }

    return cv_results

