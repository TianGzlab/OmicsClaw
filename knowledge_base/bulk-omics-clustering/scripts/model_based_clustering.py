"""
Model-based clustering using Gaussian Mixture Models (GMM).

GMMs provide probabilistic (soft) clustering where each sample has
a probability of belonging to each cluster.
"""

import numpy as np
from sklearn.mixture import GaussianMixture
from typing import Tuple, Optional


def gmm_clustering(
    data: np.ndarray,
    n_components: int,
    covariance_type: str = "full",
    n_init: int = 10,
    max_iter: int = 100,
    random_state: int = 42
) -> Tuple[np.ndarray, np.ndarray, GaussianMixture]:
    """
    Perform Gaussian Mixture Model clustering.

    GMM advantages:
    - Soft (probabilistic) clustering
    - Can model overlapping clusters
    - Provides uncertainty estimates
    - Can handle clusters with different sizes and shapes (with "full" covariance)

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    n_components : int
        Number of mixture components (clusters)
    covariance_type : str, default="full"
        Type of covariance parameters:
        - "full": Each component has own covariance matrix (most flexible)
        - "tied": All components share same covariance (assumes similar shapes)
        - "diag": Diagonal covariance (assumes features independent)
        - "spherical": Single variance per component (assumes spherical clusters)
    n_init : int, default=10
        Number of initializations (best result kept)
    max_iter : int, default=100
        Maximum number of EM iterations
    random_state : int, default=42
        Random state for reproducibility

    Returns
    -------
    cluster_labels : np.ndarray
        Hard cluster assignments (most likely component)
    probabilities : np.ndarray
        Soft assignments (samples × n_components probability matrix)
    gmm_model : GaussianMixture
        Fitted GMM model
    """

    print(f"Performing GMM clustering (n_components={n_components}, covariance={covariance_type})...")

    gmm = GaussianMixture(
        n_components=n_components,
        covariance_type=covariance_type,
        n_init=n_init,
        max_iter=max_iter,
        random_state=random_state
    )

    gmm.fit(data)

    # Hard assignments (argmax of probabilities)
    cluster_labels = gmm.predict(data)

    # Soft assignments (posterior probabilities)
    probabilities = gmm.predict_proba(data)

    # Report results
    unique, counts = np.unique(cluster_labels, return_counts=True)
    print(f"Formed {n_components} clusters")
    print("Cluster sizes (hard assignments):", dict(zip(unique, counts)))

    # Model quality metrics
    print(f"\nModel Quality:")
    print(f"  Log-likelihood: {gmm.score(data) * len(data):.2f}")
    print(f"  BIC: {gmm.bic(data):.2f} (lower is better)")
    print(f"  AIC: {gmm.aic(data):.2f} (lower is better)")
    print(f"  Converged: {gmm.converged_}")

    return cluster_labels, probabilities, gmm


def select_gmm_components_bic(
    data: np.ndarray,
    n_components_range: range,
    covariance_type: str = "full",
    n_init: int = 10,
    random_state: int = 42
) -> dict:
    """
    Select optimal number of GMM components using BIC criterion.

    BIC (Bayesian Information Criterion) penalizes model complexity.
    Lower BIC indicates better model.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    n_components_range : range
        Range of n_components to test (e.g., range(2, 16))
    covariance_type : str, default="full"
        Covariance type
    n_init : int, default=10
        Number of initializations per model
    random_state : int, default=42
        Random state

    Returns
    -------
    results : dict
        Dictionary with keys:
        - "n_components_values": list of n_components tested
        - "bic_scores": BIC for each n_components
        - "aic_scores": AIC for each n_components
        - "optimal_n_components_bic": optimal n based on BIC
        - "optimal_n_components_aic": optimal n based on AIC
        - "models": fitted GMM models for each n_components
    """

    print(f"\nSelecting GMM components using BIC/AIC...")
    print(f"Testing n_components from {min(n_components_range)} to {max(n_components_range)}")

    bic_scores = []
    aic_scores = []
    models = []

    for n_comp in n_components_range:
        gmm = GaussianMixture(
            n_components=n_comp,
            covariance_type=covariance_type,
            n_init=n_init,
            max_iter=100,
            random_state=random_state
        )

        gmm.fit(data)

        bic = gmm.bic(data)
        aic = gmm.aic(data)

        bic_scores.append(bic)
        aic_scores.append(aic)
        models.append(gmm)

        print(f"  n={n_comp}: BIC={bic:.2f}, AIC={aic:.2f}")

    # Find optimal n_components (minimum BIC/AIC)
    optimal_idx_bic = np.argmin(bic_scores)
    optimal_idx_aic = np.argmin(aic_scores)

    optimal_n_bic = list(n_components_range)[optimal_idx_bic]
    optimal_n_aic = list(n_components_range)[optimal_idx_aic]

    print(f"\nOptimal n_components:")
    print(f"  BIC: {optimal_n_bic}")
    print(f"  AIC: {optimal_n_aic}")

    results = {
        "n_components_values": list(n_components_range),
        "bic_scores": bic_scores,
        "aic_scores": aic_scores,
        "optimal_n_components_bic": optimal_n_bic,
        "optimal_n_components_aic": optimal_n_aic,
        "models": models
    }

    return results


def compare_covariance_types(
    data: np.ndarray,
    n_components: int,
    covariance_types: list = None,
    n_init: int = 10,
    random_state: int = 42
) -> dict:
    """
    Compare different covariance types for GMM.

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    n_components : int
        Number of components
    covariance_types : list, optional
        List of covariance types to compare
        Default: ["full", "tied", "diag", "spherical"]
    n_init : int, default=10
        Number of initializations
    random_state : int, default=42
        Random state

    Returns
    -------
    results : dict
        Dictionary mapping covariance type to results
    """

    if covariance_types is None:
        covariance_types = ["full", "tied", "diag", "spherical"]

    print(f"\nComparing covariance types for {n_components} components...")

    results = {}

    for cov_type in covariance_types:
        gmm = GaussianMixture(
            n_components=n_components,
            covariance_type=cov_type,
            n_init=n_init,
            max_iter=100,
            random_state=random_state
        )

        gmm.fit(data)

        results[cov_type] = {
            "bic": gmm.bic(data),
            "aic": gmm.aic(data),
            "log_likelihood": gmm.score(data) * len(data),
            "converged": gmm.converged_,
            "model": gmm
        }

        print(f"  {cov_type:12s}: BIC={results[cov_type]['bic']:.2f}, "
              f"AIC={results[cov_type]['aic']:.2f}")

    # Find best by BIC
    best_cov_type = min(results.keys(), key=lambda x: results[x]['bic'])
    print(f"\nBest covariance type (by BIC): {best_cov_type}")

    return results


def get_cluster_uncertainties(
    probabilities: np.ndarray,
    cluster_labels: np.ndarray
) -> dict:
    """
    Analyze cluster assignment uncertainties from GMM probabilities.

    Parameters
    ----------
    probabilities : np.ndarray
        Soft assignment probabilities (samples × n_components)
    cluster_labels : np.ndarray
        Hard cluster assignments

    Returns
    -------
    uncertainties : dict
        Dictionary with uncertainty statistics
    """

    # For each sample, what's the probability of its assigned cluster?
    assigned_probs = probabilities[np.arange(len(cluster_labels)), cluster_labels]

    # Entropy of probability distribution (higher = more uncertain)
    # H = -sum(p * log(p))
    entropy = -np.sum(probabilities * np.log(probabilities + 1e-10), axis=1)

    # Maximum probability (across all clusters)
    max_probs = probabilities.max(axis=1)

    uncertainties = {
        "assigned_probability_mean": assigned_probs.mean(),
        "assigned_probability_median": np.median(assigned_probs),
        "assigned_probability_min": assigned_probs.min(),
        "entropy_mean": entropy.mean(),
        "entropy_max": entropy.max(),
        "n_confident": np.sum(assigned_probs >= 0.8),
        "n_uncertain": np.sum(assigned_probs < 0.5),
        "pct_confident": np.sum(assigned_probs >= 0.8) / len(assigned_probs) * 100,
        "pct_uncertain": np.sum(assigned_probs < 0.5) / len(assigned_probs) * 100
    }

    print("\nCluster Assignment Uncertainties:")
    print(f"  Mean probability (assigned cluster): {uncertainties['assigned_probability_mean']:.3f}")
    print(f"  Confident assignments (>0.8): {uncertainties['n_confident']} ({uncertainties['pct_confident']:.1f}%)")
    print(f"  Uncertain assignments (<0.5): {uncertainties['n_uncertain']} ({uncertainties['pct_uncertain']:.1f}%)")
    print(f"  Mean entropy: {uncertainties['entropy_mean']:.3f}")

    return uncertainties


def get_cluster_overlap(
    probabilities: np.ndarray,
    threshold: float = 0.2
) -> np.ndarray:
    """
    Identify samples that have significant probability in multiple clusters.

    Parameters
    ----------
    probabilities : np.ndarray
        Soft assignment probabilities (samples × n_components)
    threshold : float, default=0.2
        Minimum probability to consider a cluster

    Returns
    -------
    overlap_matrix : np.ndarray
        Matrix showing which clusters overlap (n_components × n_components)
        overlap_matrix[i, j] = number of samples with significant probability
        in both cluster i and cluster j
    """

    n_components = probabilities.shape[1]
    overlap_matrix = np.zeros((n_components, n_components), dtype=int)

    # For each pair of clusters, count samples with significant probability in both
    for i in range(n_components):
        for j in range(i + 1, n_components):
            # Samples with probability >= threshold in both clusters
            overlap = np.sum((probabilities[:, i] >= threshold) &
                           (probabilities[:, j] >= threshold))
            overlap_matrix[i, j] = overlap
            overlap_matrix[j, i] = overlap

    print("\nCluster Overlap Analysis:")
    print(f"(Samples with >{threshold:.0%} probability in multiple clusters)")
    print(overlap_matrix)

    return overlap_matrix


def convert_soft_to_hard(
    probabilities: np.ndarray,
    threshold: float = 0.5
) -> np.ndarray:
    """
    Convert soft (probabilistic) assignments to hard assignments with uncertainty threshold.

    Samples with max probability < threshold are labeled as uncertain (-1).

    Parameters
    ----------
    probabilities : np.ndarray
        Soft assignment probabilities (samples × n_components)
    threshold : float, default=0.5
        Minimum probability to make hard assignment

    Returns
    -------
    cluster_labels : np.ndarray
        Hard assignments (uncertain samples labeled as -1)
    """

    max_probs = probabilities.max(axis=1)
    cluster_labels = probabilities.argmax(axis=1)

    # Mark uncertain samples
    cluster_labels[max_probs < threshold] = -1

    n_uncertain = np.sum(cluster_labels == -1)
    print(f"Hard assignments with threshold {threshold}:")
    print(f"  Uncertain samples: {n_uncertain} ({n_uncertain / len(cluster_labels) * 100:.1f}%)")

    return cluster_labels

