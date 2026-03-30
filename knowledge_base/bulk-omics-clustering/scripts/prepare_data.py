"""
Data loading and preparation for clustering analysis.

This module handles:
- Loading data from various formats (CSV, TSV, Excel, HDF5)
- Data normalization
- Missing value handling
- Low variance feature filtering
- Quality checks and reporting
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
from sklearn.impute import SimpleImputer, KNNImputer
from typing import Tuple, Optional, List
import warnings


def load_and_prepare_data(
    data_path: str,
    metadata_path: Optional[str] = None,
    transpose: bool = False,
    normalize_method: Optional[str] = "zscore",
    handle_missing: str = "drop",
    filter_low_variance: bool = True,
    variance_threshold: float = 0.1,
    remove_outliers: bool = False,
    outlier_threshold: float = 3.0
) -> Tuple[np.ndarray, Optional[pd.DataFrame], List[str], List[str]]:
    """
    Load and prepare data for clustering analysis.

    Parameters
    ----------
    data_path : str
        Path to data matrix file (CSV, TSV, Excel, or HDF5)
    metadata_path : str, optional
        Path to metadata file
    transpose : bool, default=False
        If True, transpose matrix (useful if features are in rows)
    normalize_method : str, optional
        Normalization method: "zscore", "minmax", "robust", "log2", or None
    handle_missing : str, default="drop"
        How to handle missing values: "drop", "mean", "median", "knn"
    filter_low_variance : bool, default=True
        Remove features with variance below threshold
    variance_threshold : float, default=0.1
        Variance threshold for feature filtering
    remove_outliers : bool, default=False
        If True, identify and remove outlier samples
    outlier_threshold : float, default=3.0
        Number of standard deviations for outlier detection

    Returns
    -------
    data : np.ndarray
        Prepared data matrix (samples × features)
    metadata : pd.DataFrame or None
        Sample metadata (if provided)
    feature_names : List[str]
        Feature names
    sample_names : List[str]
        Sample names
    """

    # Load data matrix
    print(f"Loading data from {data_path}...")
    if data_path.endswith(('.csv', '.tsv', '.txt')):
        sep = '\t' if data_path.endswith('.tsv') else ','
        data_df = pd.read_csv(data_path, sep=sep, index_col=0)
    elif data_path.endswith(('.xls', '.xlsx')):
        data_df = pd.read_excel(data_path, index_col=0)
    elif data_path.endswith('.h5'):
        data_df = pd.read_hdf(data_path, key='data')
    else:
        raise ValueError(f"Unsupported file format: {data_path}")

    # Transpose if requested
    if transpose:
        print("Transposing data matrix...")
        data_df = data_df.T

    sample_names = list(data_df.index)
    feature_names = list(data_df.columns)

    print(f"Data shape: {data_df.shape[0]} samples × {data_df.shape[1]} features")

    # Load metadata if provided
    metadata = None
    if metadata_path:
        print(f"Loading metadata from {metadata_path}...")
        sep = '\t' if metadata_path.endswith('.tsv') else ','
        metadata = pd.read_csv(metadata_path, sep=sep, index_col=0)

        # Ensure metadata matches data samples
        common_samples = list(set(sample_names) & set(metadata.index))
        if len(common_samples) != len(sample_names):
            print(f"Warning: {len(sample_names) - len(common_samples)} samples missing from metadata")
            data_df = data_df.loc[common_samples]
            metadata = metadata.loc[common_samples]
            sample_names = common_samples

    # Check for missing values
    n_missing = data_df.isnull().sum().sum()
    if n_missing > 0:
        print(f"Found {n_missing} missing values ({n_missing / data_df.size * 100:.2f}%)")
        data_df = _handle_missing_values(data_df, method=handle_missing)

    # Convert to numpy array
    data = data_df.values.astype(float)

    # Check for constant features
    constant_features = np.where(np.std(data, axis=0) == 0)[0]
    if len(constant_features) > 0:
        print(f"Removing {len(constant_features)} constant features (zero variance)")
        keep_features = np.setdiff1d(np.arange(data.shape[1]), constant_features)
        data = data[:, keep_features]
        feature_names = [feature_names[i] for i in keep_features]

    # Filter low variance features
    if filter_low_variance and variance_threshold > 0:
        original_n_features = data.shape[1]
        data, feature_names = _filter_low_variance(
            data, feature_names, threshold=variance_threshold
        )
        print(f"Filtered {original_n_features - data.shape[1]} low-variance features")

    # Remove outlier samples
    if remove_outliers:
        original_n_samples = data.shape[0]
        outlier_mask = _detect_outliers(data, threshold=outlier_threshold)
        if outlier_mask.sum() > 0:
            print(f"Removing {outlier_mask.sum()} outlier samples")
            data = data[~outlier_mask]
            sample_names = [s for i, s in enumerate(sample_names) if not outlier_mask[i]]
            if metadata is not None:
                metadata = metadata.iloc[~outlier_mask]

    # Apply normalization
    if normalize_method:
        print(f"Applying {normalize_method} normalization...")
        data = _normalize_data(data, method=normalize_method)

    # Report final statistics
    print(f"\nFinal data shape: {data.shape[0]} samples × {data.shape[1]} features")
    print(f"Data range: [{data.min():.2f}, {data.max():.2f}]")
    print(f"Mean: {data.mean():.2f}, Std: {data.std():.2f}")

    return data, metadata, feature_names, sample_names


def _handle_missing_values(data_df: pd.DataFrame, method: str) -> pd.DataFrame:
    """Handle missing values using specified method."""
    if method == "drop":
        # Drop samples with any missing values
        data_df = data_df.dropna()
        print(f"Dropped samples with missing values (remaining: {len(data_df)})")

    elif method in ["mean", "median"]:
        strategy = method
        imputer = SimpleImputer(strategy=strategy)
        data_df.iloc[:, :] = imputer.fit_transform(data_df)
        print(f"Imputed missing values using {method}")

    elif method == "knn":
        imputer = KNNImputer(n_neighbors=5)
        data_df.iloc[:, :] = imputer.fit_transform(data_df)
        print("Imputed missing values using KNN (k=5)")

    else:
        raise ValueError(f"Unknown missing value method: {method}")

    return data_df


def _normalize_data(data: np.ndarray, method: str) -> np.ndarray:
    """Apply normalization to data."""
    if method == "zscore":
        scaler = StandardScaler()
        return scaler.fit_transform(data)

    elif method == "minmax":
        scaler = MinMaxScaler()
        return scaler.fit_transform(data)

    elif method == "robust":
        scaler = RobustScaler()
        return scaler.fit_transform(data)

    elif method == "log2":
        # Add small constant to avoid log(0)
        data_positive = data - data.min() + 1
        return np.log2(data_positive)

    else:
        raise ValueError(f"Unknown normalization method: {method}")


def _filter_low_variance(
    data: np.ndarray,
    feature_names: List[str],
    threshold: float
) -> Tuple[np.ndarray, List[str]]:
    """Remove features with variance below threshold."""
    variances = np.var(data, axis=0)
    keep_mask = variances >= threshold

    filtered_data = data[:, keep_mask]
    filtered_features = [f for i, f in enumerate(feature_names) if keep_mask[i]]

    return filtered_data, filtered_features


def _detect_outliers(data: np.ndarray, threshold: float) -> np.ndarray:
    """
    Detect outlier samples using z-score across all features.

    Returns boolean mask where True indicates outlier.
    """
    # Calculate z-scores for each sample (mean across features)
    sample_means = np.mean(data, axis=1)
    z_scores = np.abs((sample_means - sample_means.mean()) / sample_means.std())

    return z_scores > threshold


def get_data_summary(
    data: np.ndarray,
    sample_names: List[str],
    feature_names: List[str]
) -> pd.DataFrame:
    """
    Get summary statistics for the data matrix.

    Returns
    -------
    pd.DataFrame
        Summary statistics including mean, std, min, max per sample
    """
    summary = pd.DataFrame({
        'sample': sample_names,
        'mean': data.mean(axis=1),
        'std': data.std(axis=1),
        'min': data.min(axis=1),
        'max': data.max(axis=1),
        'n_zero': (data == 0).sum(axis=1)
    })

    return summary

