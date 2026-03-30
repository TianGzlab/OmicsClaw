"""
Characterize clusters by identifying distinguishing features.

This module performs statistical tests to find features that differentiate clusters.
"""

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler
from typing import Optional, List
import warnings


def characterize_clusters(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    feature_names: List[str],
    method: str = "anova",
    top_n: int = 50,
    fdr_threshold: float = 0.05,
    plot_heatmap: bool = False,
    output_path: Optional[str] = None
) -> dict:
    """
    Identify features that distinguish clusters.

    Parameters
    ----------
    data : np.ndarray
        Data matrix (samples × features)
    cluster_labels : np.ndarray
        Cluster assignments
    feature_names : List[str]
        Feature names
    method : str, default="anova"
        Statistical test: "anova", "kruskal", or "ttest"
    top_n : int, default=50
        Number of top features to return per cluster
    fdr_threshold : float, default=0.05
        FDR threshold for significance
    plot_heatmap : bool, default=False
        If True, plot heatmap of top features
    output_path : str, optional
        Path to save heatmap

    Returns
    -------
    cluster_features : dict
        Dictionary mapping cluster ID to DataFrame of top features
    """

    print(f"\nCharacterizing clusters using {method}...")

    # Remove noise points
    mask = cluster_labels >= 0
    data_clean = data[mask]
    labels_clean = cluster_labels[mask]

    unique_labels = np.unique(labels_clean)
    n_clusters = len(unique_labels)

    # Test each feature
    feature_results = []

    for i, feature_name in enumerate(feature_names):
        feature_data = data_clean[:, i]

        # Perform statistical test
        if method == "anova":
            # One-way ANOVA across all clusters
            groups = [feature_data[labels_clean == label] for label in unique_labels]
            f_stat, p_value = stats.f_oneway(*groups)

        elif method == "kruskal":
            # Kruskal-Wallis (non-parametric ANOVA)
            groups = [feature_data[labels_clean == label] for label in unique_labels]
            h_stat, p_value = stats.kruskal(*groups)

        else:
            raise ValueError(f"Unknown method: {method}")

        # Calculate mean per cluster
        cluster_means = [feature_data[labels_clean == label].mean() for label in unique_labels]

        feature_results.append({
            'feature': feature_name,
            'p_value': p_value,
            'cluster_means': cluster_means
        })

    # Convert to DataFrame
    results_df = pd.DataFrame(feature_results)

    # FDR correction (Benjamini-Hochberg)
    from statsmodels.stats.multitest import multipletests
    _, fdr, _, _ = multipletests(results_df['p_value'], method='fdr_bh')
    results_df['fdr'] = fdr

    # Filter significant features
    significant = results_df[results_df['fdr'] < fdr_threshold].copy()
    print(f"Found {len(significant)} significant features (FDR < {fdr_threshold})")

    # For each cluster, find top features
    cluster_features = {}

    for cluster_id in unique_labels:
        # Calculate fold change relative to other clusters
        cluster_means_array = np.array(list(results_df['cluster_means']))
        this_cluster_mean = cluster_means_array[:, cluster_id]
        other_clusters_mean = np.delete(cluster_means_array, cluster_id, axis=1).mean(axis=1)

        # Avoid division by zero
        with np.errstate(divide='ignore', invalid='ignore'):
            fold_change = this_cluster_mean / (other_clusters_mean + 1e-10)
            log2_fc = np.log2(fold_change + 1e-10)

        cluster_df = results_df.copy()
        cluster_df['fold_change'] = fold_change
        cluster_df['log2_fc'] = log2_fc
        cluster_df['mean_in_cluster'] = this_cluster_mean
        cluster_df['mean_in_others'] = other_clusters_mean

        # Sort by fold change (descending)
        cluster_df = cluster_df.sort_values('fold_change', ascending=False)

        # Get top N
        top_features = cluster_df.head(top_n)

        cluster_features[int(cluster_id)] = top_features[
            ['feature', 'mean_in_cluster', 'mean_in_others', 'fold_change', 'log2_fc', 'p_value', 'fdr']
        ]

        print(f"\nCluster {cluster_id} top 5 features:")
        print(cluster_features[int(cluster_id)][['feature', 'fold_change', 'fdr']].head())

    # Plot heatmap of top features if requested
    if plot_heatmap or output_path:
        _plot_cluster_features_heatmap(
            data_clean, labels_clean, cluster_features, feature_names, output_path
        )

    return cluster_features


def _plot_cluster_features_heatmap(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    cluster_features: dict,
    feature_names: List[str],
    output_path: Optional[str] = None,
    top_n_per_cluster: int = 10
):
    """Plot heatmap of top features per cluster."""

    import seaborn as sns
    import matplotlib.pyplot as plt

    # Collect top features from each cluster
    top_features_set = set()
    for cluster_id, features_df in cluster_features.items():
        top_features = features_df['feature'].head(top_n_per_cluster).tolist()
        top_features_set.update(top_features)

    # Get indices of these features
    feature_indices = [i for i, name in enumerate(feature_names) if name in top_features_set]

    if len(feature_indices) == 0:
        print("No features to plot")
        return

    # Subset data
    data_subset = data[:, feature_indices]
    feature_subset = [feature_names[i] for i in feature_indices]

    # Z-score normalization
    scaler = StandardScaler()
    data_normalized = scaler.fit_transform(data_subset)

    # Create DataFrame
    df = pd.DataFrame(data_normalized, columns=feature_subset)

    # Sort by cluster
    sort_idx = np.argsort(cluster_labels)
    df_sorted = df.iloc[sort_idx]

    # Cluster colors
    sorted_labels = cluster_labels[sort_idx]
    unique_labels = np.unique(sorted_labels)
    palette = sns.color_palette('Set2', len(unique_labels))
    cluster_colors = [palette[np.where(unique_labels == label)[0][0]] for label in sorted_labels]

    # Create heatmap
    fig = sns.clustermap(
        df_sorted,
        cmap='RdBu_r',
        center=0,
        row_cluster=False,
        col_cluster=True,
        row_colors=cluster_colors,
        figsize=(14, 10),
        cbar_kws={'label': 'Z-score'},
        dendrogram_ratio=0.1
    )

    fig.ax_heatmap.set_xlabel('Features', fontsize=12)
    fig.ax_heatmap.set_ylabel('Samples (sorted by cluster)', fontsize=12)

    if output_path:
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Feature heatmap saved to {output_path}")

    plt.show()
    plt.close()


def compute_cluster_centroids(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    feature_names: List[str]
) -> pd.DataFrame:
    """
    Compute cluster centroids (mean feature values per cluster).

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    cluster_labels : np.ndarray
        Cluster assignments
    feature_names : List[str]
        Feature names

    Returns
    -------
    centroids_df : pd.DataFrame
        DataFrame with centroids (clusters × features)
    """

    unique_labels = np.unique(cluster_labels[cluster_labels >= 0])
    n_features = data.shape[1]

    centroids = np.zeros((len(unique_labels), n_features))

    for i, label in enumerate(unique_labels):
        cluster_mask = cluster_labels == label
        centroids[i] = data[cluster_mask].mean(axis=0)

    centroids_df = pd.DataFrame(
        centroids,
        columns=feature_names,
        index=[f'Cluster_{label}' for label in unique_labels]
    )

    return centroids_df

