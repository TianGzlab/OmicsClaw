"""
Load, validate, and preprocess longitudinal patient data.

This module consolidates data loading, validation, and preprocessing into a
single function for the standard workflow.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict
import os
import sys

# Import existing modules
try:
    from .load_longitudinal_data import load_and_validate
    from .preprocess_features import preprocess_omics
except ImportError:
    # Fallback for direct execution
    from load_longitudinal_data import load_and_validate
    from preprocess_features import preprocess_omics


def load_and_preprocess_data(
    data_file: str,
    metadata_file: str,
    data_type: str = 'rnaseq',
    min_patients: int = 10,
    min_timepoints: int = 3,
    normalization: str = 'log_cpm',
    batch_correction: bool = False,
    batch_column: str = 'batch',
    filter_low_variance: bool = True,
    variance_threshold: float = 0.1,
    max_features: int = 10000
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Load, validate, and preprocess longitudinal patient data.

    This is the consolidated Step 1 function that combines:
    - Data loading and validation
    - Timepoint structure validation
    - Feature preprocessing and normalization

    Parameters
    ----------
    data_file : str
        Path to data matrix (features × samples)
    metadata_file : str
        Path to sample metadata (must have: sample_id, patient_id, timepoint)
    data_type : str, default='rnaseq'
        Data type: 'rnaseq', 'proteomics', 'metabolomics', 'clinical'
    min_patients : int, default=10
        Minimum number of patients required
    min_timepoints : int, default=3
        Minimum timepoints per patient
    normalization : str, default='log_cpm'
        Normalization method: 'log_cpm', 'log2', 'zscore', 'quantile'
    batch_correction : bool, default=False
        Apply ComBat batch correction
    batch_column : str, default='batch'
        Column name for batch information
    filter_low_variance : bool, default=True
        Remove low-variance features
    variance_threshold : float, default=0.1
        Minimum variance to keep features
    max_features : int, default=10000
        Maximum features to keep (most variable)

    Returns
    -------
    data : pd.DataFrame
        Preprocessed data matrix (features × samples)
    metadata : pd.DataFrame
        Validated sample metadata
    stats : dict
        Preprocessing statistics and validation info

    Raises
    ------
    ValueError
        If data doesn't meet minimum requirements
    FileNotFoundError
        If input files don't exist
    """

    print("\n=== Step 1: Load and Preprocess Data ===\n")

    # Step 1a: Load and validate data structure
    print("Loading data...")
    try:
        data, metadata = load_and_validate(
            data_file=data_file,
            metadata_file=metadata_file,
            min_patients=min_patients,
            min_timepoints=min_timepoints
        )
        print(f"✓ Loaded {data.shape[0]} features × {data.shape[1]} samples")
    except Exception as e:
        print(f"✗ Failed to load data: {e}")
        raise

    # Step 1b: Validate timepoint structure
    print("\nValidating timepoint structure...")
    n_patients = metadata['patient_id'].nunique()
    timepoints_per_patient = metadata.groupby('patient_id').size()
    mean_timepoints = timepoints_per_patient.mean()
    time_range = metadata['timepoint'].max() - metadata['timepoint'].min()

    # Determine sampling pattern
    sampling_regular = (timepoints_per_patient.std() < 1.0)
    pattern = "regular" if sampling_regular else "irregular"

    print(f"✓ {n_patients} patients")
    print(f"✓ {mean_timepoints:.1f} mean timepoints per patient")
    print(f"✓ Time range: {metadata['timepoint'].min():.1f} - {metadata['timepoint'].max():.1f}")
    print(f"✓ Sampling pattern: {pattern}")

    # Step 1c: Preprocess features
    print("\nPreprocessing features...")
    try:
        data_processed = preprocess_omics(
            data=data,
            metadata=metadata,
            data_type=data_type,
            normalization=normalization,
            batch_correction=batch_correction,
            batch_column=batch_column,
            filter_low_variance=filter_low_variance,
            variance_threshold=variance_threshold
        )
        print(f"✓ {data_processed.shape[0]} features after filtering")

        # Limit to most variable features if needed
        if data_processed.shape[0] > max_features:
            print(f"\nReducing to {max_features} most variable features...")
            feature_var = data_processed.var(axis=1)
            top_features = feature_var.nlargest(max_features).index
            data_processed = data_processed.loc[top_features]
            print(f"✓ Kept {max_features} most variable features")

    except Exception as e:
        print(f"✗ Failed to preprocess: {e}")
        raise

    # Compile statistics
    stats = {
        'n_patients': n_patients,
        'n_samples': data_processed.shape[1],
        'n_features_original': data.shape[0],
        'n_features_final': data_processed.shape[0],
        'mean_timepoints_per_patient': mean_timepoints,
        'time_range': time_range,
        'sampling_pattern': pattern,
        'data_type': data_type,
        'normalization': normalization,
        'batch_corrected': batch_correction
    }

    print("\n" + "="*50)
    print("✓ Data loaded and preprocessed successfully!")
    print("="*50 + "\n")

    return data_processed, metadata, stats


def load_example_data(dataset='gse128959'):
    """
    Load example longitudinal data for testing.

    Parameters
    ----------
    dataset : str, default='gse128959'
        Dataset to load:
        - 'gse128959': Bladder cancer recurrence (18 patients, 84 samples, 17K genes).
          From TimeAx paper (Frishberg et al. 2023). Requires R + sva package.
        - 'synthetic': Generated synthetic data (15 patients, 75 samples, 1000 features).

    Returns
    -------
    data : pd.DataFrame
        Example data matrix (features × samples)
    metadata : pd.DataFrame
        Example metadata with patient_id, timepoint
    """

    if dataset == 'gse128959':
        return _load_gse128959()
    elif dataset == 'synthetic':
        return _load_synthetic()
    else:
        raise ValueError(f"Unknown dataset: {dataset}. Use 'gse128959' or 'synthetic'.")


def _load_gse128959():
    """Load GSE128959 bladder cancer dataset (preprocessed via R)."""
    import subprocess

    print("\n=== Loading GSE128959 Bladder Cancer Dataset ===\n")

    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    expr_file = os.path.join(data_dir, 'gse128959_expression.csv')
    meta_file = os.path.join(data_dir, 'gse128959_metadata.csv')

    if not os.path.exists(expr_file) or not os.path.exists(meta_file):
        # Run R preprocessing script
        r_script = os.path.join(os.path.dirname(__file__), 'load_gse128959.R')
        if not os.path.exists(r_script):
            print("R preprocessing script not found. Falling back to synthetic data.")
            return _load_synthetic()

        print("Running R preprocessing (ComBat batch correction)...")
        print("(First run downloads ~5MB from GitHub, takes ~1 minute)")
        try:
            result = subprocess.run(
                ['Rscript', r_script, os.path.abspath(data_dir)],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                print(f"R preprocessing failed: {result.stderr[:200]}")
                print("Falling back to synthetic data.")
                return _load_synthetic()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("R not available. Falling back to synthetic data.")
            return _load_synthetic()

    data = pd.read_csv(expr_file, index_col=0)
    metadata = pd.read_csv(meta_file)

    print(f"✓ Loaded {data.shape[0]} features × {data.shape[1]} samples")
    print(f"✓ {metadata['patient_id'].nunique()} patients")
    print(f"✓ {metadata.groupby('patient_id').size().mean():.1f} timepoints per patient")
    print(f"✓ Bladder cancer recurrence (GSE128959, TimeAx paper)\n")

    return data, metadata


def _load_synthetic():
    """Load or generate synthetic longitudinal data."""

    print("\n=== Loading Example Synthetic Data ===\n")

    # Check if example data exists locally
    example_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'example')
    data_file = os.path.join(example_dir, 'synthetic_expression.csv')
    metadata_file = os.path.join(example_dir, 'synthetic_metadata.csv')

    if os.path.exists(data_file) and os.path.exists(metadata_file):
        print("Found local example data...")
        data = pd.read_csv(data_file, index_col=0)
        metadata = pd.read_csv(metadata_file)
    else:
        # Generate synthetic data
        print("Generating synthetic longitudinal data...")
        print("(15 patients × 5 timepoints × 1000 features)")

        np.random.seed(42)

        # Create metadata
        patients = [f"Patient_{i:02d}" for i in range(1, 16)]
        timepoints = [0, 1, 3, 6, 12]  # months

        metadata_list = []
        for patient in patients:
            for t in timepoints:
                sample_id = f"{patient}_T{t:02d}"
                metadata_list.append({
                    'sample_id': sample_id,
                    'patient_id': patient,
                    'timepoint': t
                })

        metadata = pd.DataFrame(metadata_list)

        # Create expression data with progression signal
        n_features = 1000
        n_samples = len(metadata)

        # Base expression
        data = np.random.randn(n_features, n_samples) + 10

        # Add trajectory signal to first 100 features
        for i in range(100):
            progression_effect = metadata['timepoint'].values * 0.2
            if i < 50:  # Up-regulated along trajectory
                data[i, :] += progression_effect
            else:  # Down-regulated along trajectory
                data[i, :] -= progression_effect

        # Convert to DataFrame
        feature_names = [f"Gene_{i:04d}" for i in range(n_features)]
        data = pd.DataFrame(data, index=feature_names, columns=metadata['sample_id'])

    print(f"✓ Loaded {data.shape[0]} features × {data.shape[1]} samples")
    print(f"✓ {metadata['patient_id'].nunique()} patients")
    print(f"✓ {metadata.groupby('patient_id').size().mean():.0f} timepoints per patient\n")

    return data, metadata


if __name__ == '__main__':
    """Test the load and preprocess function with example data."""

    # Load example data (synthetic for quick test)
    data, metadata = load_example_data('synthetic')

    # Save to temporary files
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        data_file = f.name
        data.to_csv(data_file)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        metadata_file = f.name
        metadata.to_csv(metadata_file, index=False)

    # Test preprocessing
    data_processed, metadata_out, stats = load_and_preprocess_data(
        data_file=data_file,
        metadata_file=metadata_file,
        data_type='rnaseq',
        min_patients=5,
        min_timepoints=3
    )

    print("\nPreprocessing statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Cleanup
    os.remove(data_file)
    os.remove(metadata_file)

