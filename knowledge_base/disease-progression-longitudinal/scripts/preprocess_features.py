"""
Preprocess and normalize features for trajectory analysis.

This module provides functions for normalizing omics data and preparing
features for trajectory analysis.
"""

import pandas as pd
import numpy as np
from typing import Optional, Literal
from sklearn.preprocessing import StandardScaler, QuantileTransformer


def preprocess_omics(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    data_type: Literal['rnaseq', 'proteomics', 'metabolomics', 'clinical'] = 'rnaseq',
    normalization: Literal['log_cpm', 'log2', 'zscore', 'quantile', 'vst'] = 'log_cpm',
    batch_correction: bool = False,
    batch_column: Optional[str] = None,
    filter_low_variance: bool = True,
    variance_threshold: float = 0.1,
    handle_missing: Literal['drop', 'impute', 'none'] = 'drop'
) -> pd.DataFrame:
    """
    Preprocess and normalize omics data.

    Parameters
    ----------
    data : pd.DataFrame
        Feature matrix (features × samples)
    metadata : pd.DataFrame
        Sample metadata
    data_type : str
        Type of omics data: 'rnaseq', 'proteomics', 'metabolomics', 'clinical'
    normalization : str
        Normalization method:
        - 'log_cpm': log2(CPM + 1) for RNA-seq
        - 'log2': log2(x + 1) for proteomics/metabolomics
        - 'zscore': Z-score normalization per feature
        - 'quantile': Quantile normalization
        - 'vst': Variance stabilizing transformation
    batch_correction : bool
        Whether to apply batch correction
    batch_column : str, optional
        Column name for batch information
    filter_low_variance : bool
        Remove low-variance features
    variance_threshold : float
        Variance threshold for filtering (0-1)
    handle_missing : str
        How to handle missing values:
        - 'drop': Drop features with any missing values
        - 'impute': Impute with median
        - 'none': Keep as is

    Returns
    -------
    data_processed : pd.DataFrame
        Preprocessed feature matrix

    Examples
    --------
    >>> data_processed = preprocess_omics(
    ...     data, metadata,
    ...     data_type='rnaseq',
    ...     normalization='log_cpm',
    ...     batch_correction=True,
    ...     batch_column='batch'
    ... )
    """

    print(f"Preprocessing {data_type} data...")
    print(f"  Initial features: {data.shape[0]}")
    print(f"  Samples: {data.shape[1]}")

    # Handle missing values
    if handle_missing == 'drop':
        missing_mask = data.isna().any(axis=1)
        n_missing = missing_mask.sum()
        if n_missing > 0:
            print(f"  Dropping {n_missing} features with missing values")
            data = data.loc[~missing_mask]
    elif handle_missing == 'impute':
        n_missing = data.isna().sum().sum()
        if n_missing > 0:
            print(f"  Imputing {n_missing} missing values with median")
            data = data.apply(lambda x: x.fillna(x.median()), axis=1)

    # Normalization
    print(f"\nApplying {normalization} normalization...")
    data_norm = _normalize_data(data, method=normalization, data_type=data_type)

    # Batch correction
    if batch_correction:
        if batch_column is None or batch_column not in metadata.columns:
            raise ValueError(f"Batch column '{batch_column}' not found in metadata")

        print(f"\nApplying batch correction on column '{batch_column}'...")
        data_norm = _batch_correct(data_norm, metadata, batch_column)

    # Filter low variance features
    if filter_low_variance:
        print(f"\nFiltering low-variance features (threshold={variance_threshold})...")
        data_norm = _filter_variance(data_norm, threshold=variance_threshold)
        print(f"  Retained features: {data_norm.shape[0]}")

    print("\n✓ Preprocessing complete")
    print(f"  Final features: {data_norm.shape[0]}")
    print(f"  Final samples: {data_norm.shape[1]}")

    return data_norm


def _normalize_data(
    data: pd.DataFrame,
    method: str,
    data_type: str
) -> pd.DataFrame:
    """Apply normalization to data."""

    if method == 'log_cpm':
        # Log2(CPM + 1) normalization
        if data_type != 'rnaseq':
            print(f"  Warning: log_cpm typically used for RNA-seq, not {data_type}")

        # Calculate CPM
        library_sizes = data.sum(axis=0)
        cpm = data.div(library_sizes, axis=1) * 1e6
        data_norm = np.log2(cpm + 1)

        print(f"  Applied log2(CPM + 1) normalization")

    elif method == 'log2':
        # Simple log2(x + 1)
        data_norm = np.log2(data + 1)
        print(f"  Applied log2(x + 1) transformation")

    elif method == 'zscore':
        # Z-score per feature
        scaler = StandardScaler()
        data_norm = pd.DataFrame(
            scaler.fit_transform(data.T).T,
            index=data.index,
            columns=data.columns
        )
        print(f"  Applied Z-score normalization")

    elif method == 'quantile':
        # Quantile normalization
        qt = QuantileTransformer(output_distribution='normal', random_state=42)
        data_norm = pd.DataFrame(
            qt.fit_transform(data.T).T,
            index=data.index,
            columns=data.columns
        )
        print(f"  Applied quantile normalization")

    elif method == 'vst':
        # Variance stabilizing transformation (simplified)
        # For real VST, use DESeq2's vst() in R
        print("  Warning: Simplified VST. For true VST, use DESeq2 in R")
        data_norm = np.arcsinh(data)

    else:
        raise ValueError(f"Unknown normalization method: {method}")

    return data_norm


def _batch_correct(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    batch_column: str
) -> pd.DataFrame:
    """
    Apply batch correction using ComBat-style approach.

    Simplified implementation. For full ComBat, use pycombat or R ComBat.
    """

    try:
        from combat.pycombat import pycombat
        print("  Using pyCombat for batch correction")

        # Prepare batch vector
        batch = metadata.set_index('sample_id').loc[data.columns, batch_column]

        # Run ComBat
        data_corrected = pycombat(data, batch)

        return pd.DataFrame(data_corrected, index=data.index, columns=data.columns)

    except ImportError:
        print("  pyCombat not installed. Using simple batch mean centering.")
        print("  For better batch correction, install: pip install combat")

        # Simple batch mean centering
        data_corrected = data.copy()
        batch = metadata.set_index('sample_id').loc[data.columns, batch_column]

        for batch_id in batch.unique():
            batch_mask = (batch == batch_id).values
            batch_mean = data.loc[:, batch_mask].mean(axis=1)
            overall_mean = data.mean(axis=1)

            # Center batch to overall mean
            data_corrected.loc[:, batch_mask] = data.loc[:, batch_mask].sub(batch_mean, axis=0).add(overall_mean, axis=0)

        return data_corrected


def _filter_variance(
    data: pd.DataFrame,
    threshold: float = 0.1
) -> pd.DataFrame:
    """
    Filter features by variance.

    Parameters
    ----------
    data : pd.DataFrame
        Feature matrix
    threshold : float
        Keep features with variance > threshold * median variance

    Returns
    -------
    data_filtered : pd.DataFrame
        Filtered data
    """

    # Calculate variance per feature
    variances = data.var(axis=1)
    median_var = variances.median()

    # Filter
    keep = variances > (threshold * median_var)
    n_removed = (~keep).sum()

    print(f"  Removed {n_removed} low-variance features")

    return data.loc[keep]


def select_variable_features(
    data: pd.DataFrame,
    n_features: int = 5000,
    method: Literal['variance', 'mad', 'cv'] = 'variance'
) -> pd.DataFrame:
    """
    Select most variable features.

    Parameters
    ----------
    data : pd.DataFrame
        Feature matrix
    n_features : int
        Number of features to select
    method : str
        Selection method:
        - 'variance': Highest variance
        - 'mad': Highest median absolute deviation
        - 'cv': Highest coefficient of variation

    Returns
    -------
    data_selected : pd.DataFrame
        Data with selected features
    """

    print(f"Selecting top {n_features} features by {method}...")

    if method == 'variance':
        scores = data.var(axis=1)
    elif method == 'mad':
        scores = data.sub(data.median(axis=1), axis=0).abs().median(axis=1)
    elif method == 'cv':
        scores = data.std(axis=1) / data.mean(axis=1).abs()
    else:
        raise ValueError(f"Unknown method: {method}")

    # Select top features
    top_features = scores.nlargest(n_features).index
    data_selected = data.loc[top_features]

    print(f"  Selected {len(top_features)} features")

    return data_selected

