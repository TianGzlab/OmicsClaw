"""
Load and validate longitudinal patient omics data for trajectory analysis.

This module provides functions to load patient data with temporal information
and validate that it meets the requirements for trajectory analysis.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Optional


def load_and_validate(
    data_file: str,
    metadata_file: str,
    min_patients: int = 10,
    min_timepoints: int = 3,
    data_type: str = 'matrix',  # 'matrix' or 'long'
    transpose: bool = False
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load longitudinal patient data and validate structure.

    Parameters
    ----------
    data_file : str
        Path to data matrix file (features × samples or samples × features)
        Supported formats: CSV, TSV, Excel
    metadata_file : str
        Path to sample metadata file
        Required columns: sample_id, patient_id, timepoint
    min_patients : int, default=10
        Minimum number of patients required
    min_timepoints : int, default=3
        Minimum number of timepoints per patient
    data_type : str, default='matrix'
        'matrix' for wide format (features × samples) or
        'long' for long format (sample, feature, value rows)
    transpose : bool, default=False
        If True, transpose data matrix (samples × features → features × samples)

    Returns
    -------
    data : pd.DataFrame
        Data matrix (features × samples)
    metadata : pd.DataFrame
        Sample metadata with validated columns

    Raises
    ------
    ValueError
        If data doesn't meet minimum requirements

    Examples
    --------
    >>> data, metadata = load_and_validate(
    ...     'expression_matrix.csv',
    ...     'sample_metadata.csv',
    ...     min_patients=10,
    ...     min_timepoints=3
    ... )
    """

    # Load data
    print(f"Loading data from {data_file}...")
    if data_file.endswith('.csv'):
        data = pd.read_csv(data_file, index_col=0)
    elif data_file.endswith(('.tsv', '.txt')):
        data = pd.read_csv(data_file, sep='\t', index_col=0)
    elif data_file.endswith(('.xlsx', '.xls')):
        data = pd.read_excel(data_file, index_col=0)
    else:
        raise ValueError(f"Unsupported file format: {data_file}")

    if transpose:
        data = data.T

    # Load metadata
    print(f"Loading metadata from {metadata_file}...")
    if metadata_file.endswith('.csv'):
        metadata = pd.read_csv(metadata_file)
    elif metadata_file.endswith(('.tsv', '.txt')):
        metadata = pd.read_csv(metadata_file, sep='\t')
    elif metadata_file.endswith(('.xlsx', '.xls')):
        metadata = pd.read_excel(metadata_file)
    else:
        raise ValueError(f"Unsupported file format: {metadata_file}")

    # Validate required columns
    required_cols = ['sample_id', 'patient_id', 'timepoint']
    missing_cols = [col for col in required_cols if col not in metadata.columns]
    if missing_cols:
        raise ValueError(
            f"Metadata missing required columns: {missing_cols}\n"
            f"Required: {required_cols}\n"
            f"Found: {list(metadata.columns)}"
        )

    # Ensure sample_id matches data columns
    if not set(metadata['sample_id']).issubset(set(data.columns)):
        raise ValueError(
            f"Sample IDs in metadata don't match data columns.\n"
            f"Metadata samples: {len(metadata['sample_id'])}\n"
            f"Data columns: {len(data.columns)}"
        )

    # Align data and metadata
    metadata = metadata.set_index('sample_id')
    data = data[metadata.index]
    metadata = metadata.reset_index()

    # Validate timepoint structure
    print("\nValidating timepoint structure...")
    n_patients = metadata['patient_id'].nunique()
    timepoints_per_patient = metadata.groupby('patient_id').size()

    print(f"  Patients: {n_patients}")
    print(f"  Total samples: {len(metadata)}")
    print(f"  Timepoints per patient: {timepoints_per_patient.min()}-{timepoints_per_patient.max()} "
          f"(mean: {timepoints_per_patient.mean():.1f})")

    # Check minimum requirements
    if n_patients < min_patients:
        raise ValueError(
            f"Insufficient patients: {n_patients} < {min_patients} required.\n"
            f"Trajectory analysis requires at least {min_patients} patients."
        )

    insufficient_patients = timepoints_per_patient[timepoints_per_patient < min_timepoints]
    if len(insufficient_patients) > 0:
        print(f"\n  WARNING: {len(insufficient_patients)} patients have <{min_timepoints} timepoints:")
        print(f"  {insufficient_patients.to_dict()}")
        print(f"  Recommend removing these patients or increasing sampling.")

    # Convert timepoint to numeric if needed
    if not pd.api.types.is_numeric_dtype(metadata['timepoint']):
        print("\n  Converting timepoint to numeric...")
        try:
            metadata['timepoint'] = pd.to_numeric(metadata['timepoint'])
        except ValueError:
            raise ValueError(
                "Cannot convert 'timepoint' column to numeric. "
                "Ensure timepoints are numeric values (e.g., days, months)."
            )

    # Summary statistics
    print("\nData summary:")
    print(f"  Features: {data.shape[0]}")
    print(f"  Samples: {data.shape[1]}")
    print(f"  Patients: {n_patients}")
    print(f"  Time range: {metadata['timepoint'].min():.1f} - {metadata['timepoint'].max():.1f}")
    print(f"  Mean timepoints per patient: {timepoints_per_patient.mean():.1f}")

    # Check for missing values
    missing_fraction = data.isna().sum().sum() / (data.shape[0] * data.shape[1])
    if missing_fraction > 0:
        print(f"\n  WARNING: {missing_fraction*100:.1f}% missing values in data")
        if missing_fraction > 0.2:
            print("  Consider imputation or removing features with high missingness")

    print("\n✓ Data validation complete")

    return data, metadata


def summarize_sampling_pattern(metadata: pd.DataFrame,
                               time_column: str = 'timepoint',
                               patient_column: str = 'patient_id') -> Dict:
    """
    Summarize the temporal sampling pattern.

    Parameters
    ----------
    metadata : pd.DataFrame
        Sample metadata
    time_column : str
        Column name for timepoint values
    patient_column : str
        Column name for patient IDs

    Returns
    -------
    summary : dict
        Dictionary with sampling pattern information
    """

    # Time intervals per patient
    intervals = []
    for patient in metadata[patient_column].unique():
        patient_times = metadata[metadata[patient_column] == patient][time_column].sort_values()
        if len(patient_times) > 1:
            intervals.extend(np.diff(patient_times))

    # Determine if sampling is regular or irregular
    if len(intervals) > 0:
        interval_cv = np.std(intervals) / np.mean(intervals)
        pattern = 'regular' if interval_cv < 0.3 else 'irregular'
    else:
        pattern = 'unknown'

    summary = {
        'n_patients': metadata[patient_column].nunique(),
        'n_samples': len(metadata),
        'timepoints_per_patient': metadata.groupby(patient_column).size().to_dict(),
        'mean_timepoints': metadata.groupby(patient_column).size().mean(),
        'time_range': (metadata[time_column].min(), metadata[time_column].max()),
        'sampling_intervals': intervals,
        'mean_interval': np.mean(intervals) if intervals else None,
        'pattern': pattern,
        'pattern_regularity': 1 - interval_cv if intervals else None
    }

    return summary


def filter_patients_by_timepoints(metadata: pd.DataFrame,
                                  min_timepoints: int = 3,
                                  patient_column: str = 'patient_id') -> pd.DataFrame:
    """
    Filter to keep only patients with sufficient timepoints.

    Parameters
    ----------
    metadata : pd.DataFrame
        Sample metadata
    min_timepoints : int
        Minimum number of timepoints required per patient
    patient_column : str
        Column name for patient IDs

    Returns
    -------
    filtered_metadata : pd.DataFrame
        Filtered metadata with only valid patients
    """

    timepoints_per_patient = metadata.groupby(patient_column).size()
    valid_patients = timepoints_per_patient[timepoints_per_patient >= min_timepoints].index

    n_removed = len(timepoints_per_patient) - len(valid_patients)
    if n_removed > 0:
        print(f"Removing {n_removed} patients with <{min_timepoints} timepoints")

    filtered_metadata = metadata[metadata[patient_column].isin(valid_patients)].copy()
    print(f"Retained {len(valid_patients)} patients, {len(filtered_metadata)} samples")

    return filtered_metadata

