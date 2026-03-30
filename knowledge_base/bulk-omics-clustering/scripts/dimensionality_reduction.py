"""
Dimensionality reduction for clustering preprocessing.

This module provides PCA, UMAP, and t-SNE implementations for
reducing dimensionality before clustering or for visualization.
"""

import numpy as np
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from typing import Tuple, Optional, Union
import warnings

# UMAP is optional
try:
    import umap
    UMAP_AVAILABLE = True
except ImportError:
    UMAP_AVAILABLE = False
    warnings.warn("UMAP not available. Install with: pip install umap-learn")


def apply_pca(
    data: np.ndarray,
    n_components: Optional[int] = None,
    variance_threshold: Optional[float] = None,
    plot_variance: bool = False,
    random_state: int = 42
) -> Tuple[np.ndarray, PCA, np.ndarray]:
    """
    Apply Principal Component Analysis (PCA) for dimensionality reduction.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    n_components : int, optional
        Number of components to keep. If None, uses variance_threshold
    variance_threshold : float, optional
        Keep components explaining this fraction of variance (e.g., 0.95)
        Only used if n_components is None
    plot_variance : bool, default=False
        If True, display variance explained information
    random_state : int, default=42
        Random state for reproducibility

    Returns
    -------
    pca_data : np.ndarray
        Transformed data (samples × n_components)
    pca_model : PCA
        Fitted PCA model
    explained_variance : np.ndarray
        Fraction of variance explained by each component
    """

    print("Applying PCA...")

    if n_components is None and variance_threshold is None:
        # Default: keep 95% variance
        variance_threshold = 0.95

    if n_components is not None:
        # Use specified number of components
        pca = PCA(n_components=n_components, random_state=random_state)
    else:
        # Use variance threshold
        pca = PCA(n_components=variance_threshold, random_state=random_state)

    pca_data = pca.fit_transform(data)

    explained_variance = pca.explained_variance_ratio_

    print(f"Reduced from {data.shape[1]} to {pca_data.shape[1]} dimensions")
    print(f"Total variance explained: {explained_variance.sum():.2%}")

    if plot_variance:
        _print_variance_summary(explained_variance)

    return pca_data, pca, explained_variance


def apply_umap(
    data: np.ndarray,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    n_components: int = 2,
    metric: str = "euclidean",
    random_state: int = 42
) -> np.ndarray:
    """
    Apply UMAP (Uniform Manifold Approximation and Projection).

    UMAP is useful for:
    - Non-linear dimensionality reduction
    - Visualization (n_components=2 or 3)
    - Can also be used for clustering (e.g., n_components=10-50)

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    n_neighbors : int, default=15
        Size of local neighborhood (larger = more global structure)
    min_dist : float, default=0.1
        Minimum distance between points in embedding (smaller = more clustered)
    n_components : int, default=2
        Number of dimensions in output (2 for visualization, 10-50 for clustering)
    metric : str, default="euclidean"
        Distance metric (euclidean, manhattan, cosine, correlation)
    random_state : int, default=42
        Random state for reproducibility

    Returns
    -------
    umap_embedding : np.ndarray
        UMAP-transformed data (samples × n_components)
    """

    if not UMAP_AVAILABLE:
        raise ImportError("UMAP not installed. Install with: pip install umap-learn")

    print(f"Applying UMAP (n_components={n_components}, n_neighbors={n_neighbors})...")

    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        n_components=n_components,
        metric=metric,
        random_state=random_state
    )

    umap_embedding = reducer.fit_transform(data)

    print(f"Reduced from {data.shape[1]} to {umap_embedding.shape[1]} dimensions")

    return umap_embedding


def apply_tsne(
    data: np.ndarray,
    n_components: int = 2,
    perplexity: float = 30.0,
    learning_rate: Union[float, str] = "auto",
    n_iter: int = 1000,
    metric: str = "euclidean",
    random_state: int = 42
) -> np.ndarray:
    """
    Apply t-SNE (t-Distributed Stochastic Neighbor Embedding).

    Note: t-SNE is primarily for visualization (2D/3D), not for clustering.
    Distances in t-SNE space are not meaningful.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    n_components : int, default=2
        Number of dimensions in output (typically 2 or 3)
    perplexity : float, default=30.0
        Related to number of nearest neighbors (5-50 typical range)
        Larger datasets can use larger perplexity
    learning_rate : float or "auto", default="auto"
        Learning rate for optimization
    n_iter : int, default=1000
        Number of iterations
    metric : str, default="euclidean"
        Distance metric
    random_state : int, default=42
        Random state for reproducibility

    Returns
    -------
    tsne_embedding : np.ndarray
        t-SNE embedding (samples × n_components)
    """

    print(f"Applying t-SNE (perplexity={perplexity}, n_iter={n_iter})...")
    print("Note: t-SNE is for visualization only, not for clustering input")

    # Recommend PCA preprocessing for large feature spaces
    if data.shape[1] > 50:
        print(f"Warning: {data.shape[1]} features. Consider PCA preprocessing first.")

    tsne = TSNE(
        n_components=n_components,
        perplexity=perplexity,
        learning_rate=learning_rate,
        n_iter=n_iter,
        metric=metric,
        random_state=random_state,
        verbose=0
    )

    tsne_embedding = tsne.fit_transform(data)

    print(f"Reduced from {data.shape[1]} to {tsne_embedding.shape[1]} dimensions")

    return tsne_embedding


def _print_variance_summary(explained_variance: np.ndarray, top_n: int = 10):
    """Print summary of variance explained by top components."""

    cumulative_variance = np.cumsum(explained_variance)

    print("\nVariance explained by principal components:")
    print("PC\tIndividual\tCumulative")
    print("-" * 35)

    n_show = min(top_n, len(explained_variance))

    for i in range(n_show):
        print(f"{i+1}\t{explained_variance[i]:.4f}\t\t{cumulative_variance[i]:.4f}")

    if len(explained_variance) > top_n:
        print("...")
        last_idx = len(explained_variance) - 1
        print(f"{last_idx+1}\t{explained_variance[last_idx]:.4f}\t\t{cumulative_variance[last_idx]:.4f}")


def determine_optimal_pca_components(
    data: np.ndarray,
    max_components: Optional[int] = None,
    variance_thresholds: list = [0.80, 0.90, 0.95, 0.99]
) -> dict:
    """
    Determine how many PCA components are needed for different variance thresholds.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    max_components : int, optional
        Maximum number of components to test. If None, uses min(n_samples, n_features)
    variance_thresholds : list, default=[0.80, 0.90, 0.95, 0.99]
        Variance thresholds to report

    Returns
    -------
    results : dict
        Dictionary with keys:
        - "n_components": number of components for each threshold
        - "explained_variance": variance explained by each component
        - "cumulative_variance": cumulative variance explained
    """

    if max_components is None:
        max_components = min(data.shape[0], data.shape[1])

    print(f"Analyzing PCA components (max={max_components})...")

    pca = PCA(n_components=max_components)
    pca.fit(data)

    explained_variance = pca.explained_variance_ratio_
    cumulative_variance = np.cumsum(explained_variance)

    # Find number of components for each threshold
    n_components_dict = {}
    for threshold in variance_thresholds:
        n_comp = np.argmax(cumulative_variance >= threshold) + 1
        n_components_dict[threshold] = n_comp

    print("\nComponents needed for variance thresholds:")
    for threshold, n_comp in n_components_dict.items():
        print(f"  {threshold:.0%} variance: {n_comp} components")

    results = {
        "n_components": n_components_dict,
        "explained_variance": explained_variance,
        "cumulative_variance": cumulative_variance
    }

    return results


def recommend_dimensionality_reduction(
    n_samples: int,
    n_features: int,
    purpose: str = "clustering"
) -> str:
    """
    Recommend dimensionality reduction strategy based on data size and purpose.

    Parameters
    ----------
    n_samples : int
        Number of samples
    n_features : int
        Number of features
    purpose : str, default="clustering"
        Purpose of reduction: "clustering" or "visualization"

    Returns
    -------
    recommendation : str
        Text recommendation
    """

    recommendations = []

    if purpose == "clustering":
        if n_features > 1000:
            recommendations.append("✓ Use PCA before clustering (keep 80-95% variance)")
            recommendations.append(f"  Suggested: {int(min(50, n_samples * 0.5))} components")

        elif n_features > 100:
            recommendations.append("✓ Consider PCA for efficiency (optional)")
            recommendations.append(f"  Suggested: {int(min(30, n_features * 0.5))} components")

        else:
            recommendations.append("✓ Can cluster in original feature space")
            recommendations.append("  PCA not required (<100 features)")

    elif purpose == "visualization":
        recommendations.append("✓ Use UMAP or t-SNE for 2D visualization")

        if n_features > 50:
            recommendations.append("  Preprocess with PCA (50 components) before UMAP/t-SNE")
        else:
            recommendations.append("  Can apply UMAP/t-SNE directly")

        if n_samples > 5000:
            recommendations.append("  Note: t-SNE slow on large data, prefer UMAP")

    return "\n".join(recommendations)

