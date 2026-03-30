"""
Export clustering results and statistics.

This module handles exporting cluster assignments, quality metrics,
and supporting data for downstream analysis.
"""

import numpy as np
import pandas as pd
import json
import os
from typing import Optional, List, Dict


def export_all(
    data: np.ndarray,
    cluster_labels: np.ndarray,
    sample_names: List[str],
    feature_names: List[str],
    validation_results: Dict,
    clustering_object: Optional[any] = None,
    cluster_features: Optional[Dict] = None,
    parameters: Optional[Dict] = None,
    output_dir: str = "clustering_results/",
    prefix: str = "clustering"
):
    """
    Export all clustering results including analysis objects for downstream use.

    This is the primary export function that should be used in workflows.
    It saves all results including the clustering analysis objects needed for
    downstream skills.

    Parameters
    ----------
    data : np.ndarray
        Original data matrix (samples × features)
    cluster_labels : np.ndarray
        Cluster assignments
    sample_names : List[str]
        Sample names
    feature_names : List[str]
        Feature names
    validation_results : Dict
        Dictionary of validation metrics
    clustering_object : any, optional
        Clustering object (linkage matrix, fitted model, etc.)
    cluster_features : Dict, optional
        Dictionary of cluster-defining features
    parameters : Dict, optional
        Analysis parameters for reproducibility
    output_dir : str, default="clustering_results/"
        Output directory
    prefix : str, default="clustering"
        Prefix for output files
    """

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n=== Exporting Results ===")
    print(f"Output directory: {output_dir}")

    # 1. Cluster assignments
    export_cluster_assignments(
        cluster_labels,
        sample_names,
        output_path=os.path.join(output_dir, f"{prefix}_assignments.csv")
    )

    # 2. Cluster statistics
    export_cluster_statistics(
        cluster_labels,
        validation_results,
        output_path=os.path.join(output_dir, f"{prefix}_statistics.csv")
    )

    # 3. Validation metrics (JSON)
    export_validation_metrics(
        validation_results,
        output_path=os.path.join(output_dir, f"{prefix}_validation_metrics.json")
    )

    # 4. Cluster features (if provided)
    if cluster_features is not None:
        export_cluster_features(
            cluster_features,
            output_dir=output_dir,
            prefix=prefix
        )

    # 5. Analysis object (CRITICAL for downstream skills)
    if clustering_object is not None:
        import pickle
        obj_path = os.path.join(output_dir, f"{prefix}_analysis_object.pkl")
        with open(obj_path, 'wb') as f:
            pickle.dump(clustering_object, f)
        print(f"  Analysis object: {obj_path}")
        print(f"    (Load with: import pickle; obj = pickle.load(open('{prefix}_analysis_object.pkl', 'rb')))")

    # 6. Data matrix (for downstream analysis)
    data_path = os.path.join(output_dir, f"{prefix}_data_matrix.csv")
    pd.DataFrame(data, columns=feature_names, index=sample_names).to_csv(data_path)
    print(f"  Data matrix: {data_path}")

    # 7. Parameters (if provided)
    if parameters is not None:
        export_parameters(
            parameters,
            output_path=os.path.join(output_dir, f"{prefix}_parameters.json")
        )

    print(f"\n=== Export Complete ===")
    print(f"All files saved to: {output_dir}")


def export_clustering_results(
    cluster_labels: np.ndarray,
    sample_names: List[str],
    validation_results: Dict,
    cluster_features: Optional[Dict] = None,
    output_dir: str = "clustering_results/",
    prefix: str = "clustering"
):
    """
    Export clustering results to files (legacy function).

    Note: For new workflows, use export_all() instead as it saves
    analysis objects needed for downstream skills.

    Parameters
    ----------
    cluster_labels : np.ndarray
        Cluster assignments
    sample_names : List[str]
        Sample names
    validation_results : Dict
        Dictionary of validation metrics
    cluster_features : Dict, optional
        Dictionary of cluster-defining features
    output_dir : str, default="clustering_results/"
        Output directory
    prefix : str, default="clustering"
        Prefix for output files
    """

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    print(f"\nExporting results to {output_dir}...")

    # 1. Cluster assignments
    export_cluster_assignments(
        cluster_labels,
        sample_names,
        output_path=os.path.join(output_dir, f"{prefix}_assignments.csv")
    )

    # 2. Cluster statistics
    export_cluster_statistics(
        cluster_labels,
        validation_results,
        output_path=os.path.join(output_dir, f"{prefix}_statistics.csv")
    )

    # 3. Validation metrics (JSON)
    export_validation_metrics(
        validation_results,
        output_path=os.path.join(output_dir, f"{prefix}_validation_metrics.json")
    )

    # 4. Cluster features (if provided)
    if cluster_features is not None:
        export_cluster_features(
            cluster_features,
            output_dir=output_dir,
            prefix=prefix
        )

    print(f"✓ Results exported to {output_dir}")


def export_cluster_assignments(
    cluster_labels: np.ndarray,
    sample_names: List[str],
    output_path: str
):
    """
    Export cluster assignments to CSV.

    Parameters
    ----------
    cluster_labels : np.ndarray
        Cluster assignments
    sample_names : List[str]
        Sample names
    output_path : str
        Output file path
    """

    df = pd.DataFrame({
        'sample_id': sample_names,
        'cluster': cluster_labels
    })

    df.to_csv(output_path, index=False)
    print(f"  Cluster assignments: {output_path}")


def export_cluster_statistics(
    cluster_labels: np.ndarray,
    validation_results: Dict,
    output_path: str
):
    """
    Export cluster statistics summary.

    Parameters
    ----------
    cluster_labels : np.ndarray
        Cluster assignments
    validation_results : Dict
        Validation metrics
    output_path : str
        Output file path
    """

    # Count clusters
    unique_labels = np.unique(cluster_labels[cluster_labels >= 0])
    n_noise = np.sum(cluster_labels == -1)

    # Basic statistics
    stats_list = []

    for label in unique_labels:
        cluster_mask = cluster_labels == label
        n_samples = cluster_mask.sum()

        stats_list.append({
            'cluster': int(label),
            'n_samples': int(n_samples),
            'percentage': float(n_samples / len(cluster_labels) * 100)
        })

    stats_df = pd.DataFrame(stats_list)

    # Add overall metrics
    overall_stats = pd.DataFrame([{
        'cluster': 'Overall',
        'n_samples': len(cluster_labels) - n_noise,
        'percentage': (len(cluster_labels) - n_noise) / len(cluster_labels) * 100
    }])

    if n_noise > 0:
        noise_stats = pd.DataFrame([{
            'cluster': 'Noise',
            'n_samples': n_noise,
            'percentage': n_noise / len(cluster_labels) * 100
        }])
        stats_df = pd.concat([stats_df, noise_stats], ignore_index=True)

    stats_df = pd.concat([stats_df, overall_stats], ignore_index=True)

    # Add validation metrics as separate columns
    for metric, value in validation_results.items():
        if isinstance(value, (int, float, np.number)):
            stats_df[metric] = value

    stats_df.to_csv(output_path, index=False)
    print(f"  Cluster statistics: {output_path}")


def export_validation_metrics(
    validation_results: Dict,
    output_path: str
):
    """
    Export validation metrics to JSON.

    Parameters
    ----------
    validation_results : Dict
        Validation metrics
    output_path : str
        Output file path
    """

    # Convert numpy types to Python types for JSON serialization
    def convert_numpy(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: convert_numpy(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy(item) for item in obj]
        else:
            return obj

    metrics_serializable = convert_numpy(validation_results)

    with open(output_path, 'w') as f:
        json.dump(metrics_serializable, f, indent=2)

    print(f"  Validation metrics: {output_path}")


def export_cluster_features(
    cluster_features: Dict,
    output_dir: str,
    prefix: str = "clustering"
):
    """
    Export cluster-defining features to CSV files.

    Parameters
    ----------
    cluster_features : Dict
        Dictionary mapping cluster ID to features DataFrame
    output_dir : str
        Output directory
    prefix : str
        Prefix for filenames
    """

    # Export per-cluster files
    for cluster_id, features_df in cluster_features.items():
        output_path = os.path.join(
            output_dir,
            f"{prefix}_cluster{cluster_id}_features.csv"
        )
        features_df.to_csv(output_path, index=False)

    print(f"  Cluster features: {len(cluster_features)} files")

    # Also create combined file
    combined_list = []
    for cluster_id, features_df in cluster_features.items():
        df_copy = features_df.copy()
        df_copy['cluster'] = cluster_id
        combined_list.append(df_copy)

    if combined_list:
        combined_df = pd.concat(combined_list, ignore_index=True)
        combined_path = os.path.join(output_dir, f"{prefix}_all_cluster_features.csv")
        combined_df.to_csv(combined_path, index=False)
        print(f"  Combined features: {combined_path}")


def export_parameters(
    parameters: Dict,
    output_path: str
):
    """
    Export clustering parameters for reproducibility.

    Parameters
    ----------
    parameters : Dict
        Dictionary of parameters used
    output_path : str
        Output file path
    """

    def convert_numpy(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {key: convert_numpy(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy(item) for item in obj]
        else:
            return obj

    params_serializable = convert_numpy(parameters)

    with open(output_path, 'w') as f:
        json.dump(params_serializable, f, indent=2)

    print(f"Parameters exported to {output_path}")


def create_analysis_report(
    cluster_labels: np.ndarray,
    sample_names: List[str],
    validation_results: Dict,
    parameters: Dict,
    output_path: str
):
    """
    Create a markdown report summarizing the analysis.

    Parameters
    ----------
    cluster_labels : np.ndarray
        Cluster assignments
    sample_names : List[str]
        Sample names
    validation_results : Dict
        Validation metrics
    parameters : Dict
        Analysis parameters
    output_path : str
        Output file path
    """

    with open(output_path, 'w') as f:
        f.write("# Clustering Analysis Report\n\n")

        # Summary
        f.write("## Summary\n\n")
        n_samples = len(cluster_labels)
        n_clusters = len(np.unique(cluster_labels[cluster_labels >= 0]))
        n_noise = np.sum(cluster_labels == -1)

        f.write(f"- **Total samples**: {n_samples}\n")
        f.write(f"- **Number of clusters**: {n_clusters}\n")
        if n_noise > 0:
            f.write(f"- **Noise points**: {n_noise} ({n_noise/n_samples*100:.1f}%)\n")
        f.write("\n")

        # Cluster sizes
        f.write("## Cluster Sizes\n\n")
        f.write("| Cluster | Size | Percentage |\n")
        f.write("|---------|------|------------|\n")

        unique_labels = np.unique(cluster_labels[cluster_labels >= 0])
        for label in unique_labels:
            size = np.sum(cluster_labels == label)
            pct = size / n_samples * 100
            f.write(f"| {label} | {size} | {pct:.1f}% |\n")

        f.write("\n")

        # Validation metrics
        f.write("## Validation Metrics\n\n")
        for metric, value in validation_results.items():
            if isinstance(value, (int, float, np.number)):
                f.write(f"- **{metric}**: {value:.3f}\n")

        f.write("\n")

        # Parameters
        f.write("## Parameters\n\n")
        f.write("