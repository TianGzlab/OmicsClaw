"""
Load example/demo data for clustering analysis testing.

This module provides ALL-like synthetic data for Python users.
For the authentic ALL dataset, use the R implementation (scripts/load_example_data.R).
"""

import numpy as np
import pandas as pd
from typing import Dict, Any
import warnings


def load_example_clustering_data(
    n_top_variable_genes: int = 1000
) -> Dict[str, Any]:
    """
    Load ALL-like synthetic data for clustering analysis testing.

    This function generates synthetic data that mimics the structure of the
    ALL (Acute Lymphoblastic Leukemia) dataset: 128 samples with B-cell and
    T-cell subtypes. This is suitable for testing clustering workflows in Python.

    For the authentic ALL dataset from Bioconductor, use the R implementation:
    source("scripts/load_example_data.R")

    Parameters
    ----------
    n_top_variable_genes : int, default=1000
        Number of features (genes) to generate

    Returns
    -------
    dict
        Dictionary containing:
        - 'data': np.ndarray, normalized data matrix (samples × features)
        - 'metadata': pd.DataFrame, sample annotations with cell type labels
        - 'feature_names': list, gene probe IDs
        - 'sample_names': list, sample identifiers
        - 'description': str, dataset description
        - 'true_labels': np.ndarray, ground truth cell type labels (B vs T)

    Notes
    -----
    - Synthetic data mimicking ALL structure (95 B-cell, 33 T-cell samples)
    - Data is z-score normalized
    - Runtime: <5 seconds
    - For authentic ALL data, use R: source("scripts/load_example_data.R")

    Examples
    --------
    >>> data_dict = load_example_clustering_data()
    >>> print(data_dict['description'])
    >>> data = data_dict['data']  # Shape: (128, 1000)
    >>> metadata = data_dict['metadata']
    """
    print("Loading ALL-like synthetic data for Python testing...")
    print("  Note: For authentic ALL data from Bioconductor, use R implementation")
    print("        source('scripts/load_example_data.R')")

    data_normalized, metadata, feature_names, sample_names = _generate_all_like_data(n_top_variable_genes)

    # Create numeric labels for clustering evaluation
    cell_type_map = {'B': 0, 'T': 1}
    true_labels = np.array([cell_type_map[ct] for ct in metadata['cell_type']])

    print(f"\n✓ Data loaded successfully!")
    print(f"  Data shape: {data_normalized.shape}")
    print(f"  Data type: Synthetic data (z-score normalized)")
    print(f"  Cell types: B-cell-like (n={sum(metadata['cell_type']=='B')}), "
          f"T-cell-like (n={sum(metadata['cell_type']=='T')})")

    return {
        'data': data_normalized,
        'metadata': metadata,
        'feature_names': feature_names,
        'sample_names': sample_names,
        'true_labels': true_labels,
        'description': (
            f"ALL-like synthetic data for Python testing: "
            f"128 samples mimicking B-cell and T-cell ALL subtypes. "
            f"Data is z-score normalized with {n_top_variable_genes} features. "
            f"For authentic ALL data, use R: source('scripts/load_example_data.R')"
        ),
        'n_samples': data_normalized.shape[0],
        'n_features': data_normalized.shape[1],
        'cell_types': ['B-cell-like', 'T-cell-like']
    }


def _generate_all_like_data(n_top_variable_genes: int = 1000):
    """
    Generate synthetic data that mimics ALL dataset structure.

    This creates data similar to the ALL (Acute Lymphoblastic Leukemia) dataset
    with 95 B-cell samples and 33 T-cell samples, with distinct expression patterns.
    """
    # Generate data that mimics ALL structure
    np.random.seed(42)
    n_b_samples = 95
    n_t_samples = 33
    n_samples = n_b_samples + n_t_samples

    # Create distinct B-cell and T-cell patterns
    b_cell_data = np.random.randn(n_b_samples, n_top_variable_genes) + 0.5
    t_cell_data = np.random.randn(n_t_samples, n_top_variable_genes) - 0.5

    data = np.vstack([b_cell_data, t_cell_data])

    # Z-score normalize
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    data_normalized = scaler.fit_transform(data)

    # Create metadata
    sample_names = [f"ALL_{i:03d}" for i in range(n_samples)]
    cell_types = ['B'] * n_b_samples + ['T'] * n_t_samples
    bt_subtypes = ([f"B{i%4+1}" for i in range(n_b_samples)] +
                   [f"T{i%2+1}" for i in range(n_t_samples)])

    metadata = pd.DataFrame({
        'sample_id': sample_names,
        'cell_type': cell_types,
        'bt_subtype': bt_subtypes
    })

    feature_names = [f"Probe_{i:05d}" for i in range(n_top_variable_genes)]

    return data_normalized, metadata, feature_names, sample_names


def load_example_clustering_data_small() -> Dict[str, Any]:
    """
    Load a smaller subset of ALL-like data for very quick testing.

    Returns
    -------
    dict
        Same structure as load_example_clustering_data() but with:
        - 128 samples (same as full dataset)
        - 100 features (vs 1000 default)

    Notes
    -----
    Use this for rapid testing (<5 seconds). For learning, use the
    default load_example_clustering_data() with 1000 features.
    """
    return load_example_clustering_data(n_top_variable_genes=100)


if __name__ == "__main__":
    # Test the function
    print("=" * 80)
    print("Testing Example Data Loader")
    print("=" * 80)

    # Test default parameters
    print("\n1. Loading default example data...")
    data_dict = load_example_clustering_data()
    print(f"\nReturned keys: {list(data_dict.keys())}")
    print(f"Description: {data_dict['description']}")

    # Test small version
    print("\n" + "=" * 80)
    print("2. Loading small example data...")
    small_data_dict = load_example_clustering_data_small()
    print(f"\nReturned keys: {list(small_data_dict.keys())}")
    print(f"Description: {small_data_dict['description']}")

    print("\n" + "=" * 80)
    print("✓ All tests passed!")

