"""
TimeAx trajectory alignment for disease progression analysis.

This module implements TimeAx multiple trajectory alignment to reconstruct
consensus disease trajectories from longitudinal patient data.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Optional
import warnings


def run_timeax_alignment(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    patient_column: str = 'patient_id',
    time_column: str = 'timepoint',
    n_iterations: int = 100,
    n_seeds: int = 50,
    validation: bool = True,
    random_state: int = 42
) -> Tuple[object, Dict]:
    """
    Run TimeAx multiple trajectory alignment.

    TimeAx reconstructs a consensus disease trajectory by aligning
    multiple patient trajectories with irregular sampling times.

    Algorithm:
    1. Seed selection: Identify conserved features with coordinated dynamics
    2. Consensus iteration: Align patient trajectories (100 iterations)
    3. Model construction: Build consensus trajectory model
    4. Robustness assessment: Validate model quality

    Parameters
    ----------
    data : pd.DataFrame
        Feature matrix (features × samples)
    metadata : pd.DataFrame
        Sample metadata with patient_id and timepoint columns
    patient_column : str, default='patient_id'
        Column name for patient identifiers
    time_column : str, default='timepoint'
        Column name for timepoint values
    n_iterations : int, default=100
        Number of consensus iterations for trajectory alignment
    n_seeds : int, default=50
        Number of seed features to use for alignment
    validation : bool, default=True
        Whether to run robustness assessment
    random_state : int, default=42
        Random seed for reproducibility

    Returns
    -------
    model : TimeAx model object
        Trained TimeAx model
    results : dict
        Dictionary containing:
        - pseudotime: array of pseudotime values for each sample
        - uncertainty: uncertainty scores for each sample
        - seed_features: list of seed features used
        - robustness: robustness score (if validation=True)
        - feature_importance: importance of each seed feature

    Examples
    --------
    >>> model, results = run_timeax_alignment(
    ...     data, metadata,
    ...     patient_column='patient_id',
    ...     time_column='timepoint',
    ...     n_iterations=100
    ... )
    >>> pseudotime = results['pseudotime']
    >>> print(f"Robustness score: {results['robustness']:.3f}")
    """

    # Try R TimeAx first (primary), fall back to mock for testing
    USING_R = False

    # Try R TimeAx via subprocess
    try:
        from .timeax_r_wrapper import check_r_available, run_timeax_r
    except ImportError:
        try:
            from timeax_r_wrapper import check_r_available, run_timeax_r
        except ImportError:
            check_r_available = None
            run_timeax_r = None

    if check_r_available is not None:
        r_available, msg = check_r_available()
        if r_available:
            USING_R = True
            print("  Using TimeAx R implementation (real algorithm)")
        else:
            print(f"  R TimeAx not available: {msg}")

    # Fall back to mock if R not available
    if not USING_R:
        try:
            from .mock_timeax import run_mock_timeax, MockTimeAxModel
        except ImportError:
            from mock_timeax import run_mock_timeax, MockTimeAxModel
        print("  Note: Using mock TimeAx implementation for testing")
        print("  Install real TimeAx (R package):")
        print('    Rscript -e \'remotes::install_github("amitfrish/TimeAx")\'')

    print("Running TimeAx trajectory alignment...")
    print(f"  Patients: {metadata[patient_column].nunique()}")
    print(f"  Samples: {len(metadata)}")
    print(f"  Features: {data.shape[0]}")
    print(f"  Iterations: {n_iterations}")
    print(f"  Seed features: {n_seeds}")

    if USING_R:
        # Use R TimeAx implementation (real algorithm)
        model, results = run_timeax_r(
            data, metadata,
            patient_column=patient_column,
            time_column=time_column,
            n_iterations=n_iterations,
            n_seeds=n_seeds
        )
    else:
        # Use mock implementation for testing
        model, results = run_mock_timeax(
            data, metadata,
            patient_column=patient_column,
            time_column=time_column,
            n_iterations=n_iterations,
            n_seeds=n_seeds,
            random_state=random_state
        )

    print("\n✓ TimeAx alignment complete")

    return model, results


def project_new_samples(
    model: object,
    new_data: pd.DataFrame,
    new_metadata: pd.DataFrame
) -> np.ndarray:
    """
    Project new samples onto trained TimeAx trajectory.

    Parameters
    ----------
    model : TimeAx model
        Trained TimeAx model from run_timeax_alignment
    new_data : pd.DataFrame
        Feature matrix for new samples (same features as training)
    new_metadata : pd.DataFrame
        Metadata for new samples

    Returns
    -------
    pseudotime : np.ndarray
        Predicted pseudotime for new samples

    Examples
    --------
    >>> new_pseudotime = project_new_samples(model, new_data, new_metadata)
    """

    print("Projecting new samples onto trajectory...")

    # Transpose data (samples × features)
    new_data_t = new_data.T
    new_data_t = new_data_t.loc[new_metadata['sample_id']]

    # Project
    pseudotime = model.predict(new_data_t.values)

    print(f"  Pseudotime range: {pseudotime.min():.3f} - {pseudotime.max():.3f}")

    return pseudotime


def interpret_seed_features(
    seed_features: list,
    feature_importance: np.ndarray,
    top_n: int = 20
) -> pd.DataFrame:
    """
    Interpret seed features driving the trajectory.

    Parameters
    ----------
    seed_features : list
        List of seed feature names
    feature_importance : np.ndarray
        Importance scores for each seed feature
    top_n : int, default=20
        Number of top features to return

    Returns
    -------
    seed_df : pd.DataFrame
        DataFrame with seed features and importance scores
    """

    seed_df = pd.DataFrame({
        'feature': seed_features,
        'importance': feature_importance
    })
    seed_df = seed_df.sort_values('importance', ascending=False)

    print(f"\nTop {top_n} seed features:")
    print(seed_df.head(top_n).to_string(index=False))

    return seed_df

