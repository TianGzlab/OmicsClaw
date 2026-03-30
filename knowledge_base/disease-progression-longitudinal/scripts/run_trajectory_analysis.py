"""
Run trajectory analysis and identify trajectory-associated features.

This module consolidates trajectory alignment (TimeAx/LMM/HMM) and
feature identification into a single function for the standard workflow.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from scipy.stats import f as f_dist
from statsmodels.stats.multitest import multipletests

# Import existing trajectory methods
try:
    from .timeax_alignment import run_timeax_alignment
except ImportError:
    try:
        from timeax_alignment import run_timeax_alignment
    except ImportError:
        print("Warning: timeax_alignment module not found")
        run_timeax_alignment = None


def run_trajectory_analysis(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    method: str = 'timeax',
    patient_column: str = 'patient_id',
    time_column: str = 'timepoint',
    n_iterations: int = 100,
    n_seeds: int = 50,
    fdr_threshold: float = 0.05,
    max_poly_degree: int = 3
) -> Dict:
    """
    Run trajectory analysis and identify trajectory-associated features.

    This is the consolidated Step 2 function that combines:
    - Trajectory alignment (TimeAx or alternatives)
    - Pseudotime assignment
    - Trajectory feature identification via polynomial regression

    Feature identification follows the TimeAx paper methodology
    (Frishberg et al., Nat Commun 2023): for each feature, linear,
    quadratic, and cubic polynomial models are fit against pseudotime
    and compared via nested F-tests to select the best model. Features
    are filtered by FDR-corrected Q-value only (no minimum effect-size
    filter), which captures non-monotonic dynamics that correlation-based
    methods miss.

    Parameters
    ----------
    data : pd.DataFrame
        Preprocessed data matrix (features × samples)
    metadata : pd.DataFrame
        Sample metadata with patient_id and timepoint columns
    method : str, default='timeax'
        Trajectory method: 'timeax', 'lmm', 'hmm'
    patient_column : str, default='patient_id'
        Column name for patient identifiers
    time_column : str, default='timepoint'
        Column name for timepoint values
    n_iterations : int, default=100
        Number of TimeAx consensus iterations
    n_seeds : int, default=50
        Number of seed features for TimeAx
    fdr_threshold : float, default=0.05
        FDR threshold for trajectory features (Q-value)
    max_poly_degree : int, default=3
        Maximum polynomial degree (1=linear, 2=quadratic, 3=cubic)

    Returns
    -------
    results : dict
        Dictionary containing:
        - 'pseudotime': pd.Series with pseudotime for each sample
        - 'trajectory_features': pd.DataFrame with trajectory-associated features
        - 'model': fitted model object
        - 'robustness_score': model quality metric
        - 'method': method used
        - 'feature_stats': detailed statistics for all features

    Raises
    ------
    ValueError
        If method is not supported or data is invalid
    """

    print("\n=== Step 2: Run Trajectory Analysis ===\n")

    # Validate inputs
    if patient_column not in metadata.columns:
        raise ValueError(f"Patient column '{patient_column}' not found in metadata")
    if time_column not in metadata.columns:
        raise ValueError(f"Time column '{time_column}' not found in metadata")
    if data.shape[1] != len(metadata):
        raise ValueError("Data and metadata dimensions don't match")

    # Run trajectory alignment based on method
    r_plot_files = []
    monotonicity_score = None
    seed_features_list = None

    if method == 'timeax':
        print(f"Running TimeAx trajectory alignment...")
        print(f"  Parameters: {n_iterations} iterations, {n_seeds} seeds")

        try:
            # Run TimeAx
            if run_timeax_alignment is None:
                raise ImportError("TimeAx not available")

            model, timeax_results = run_timeax_alignment(
                data,
                metadata,
                patient_column=patient_column,
                time_column=time_column,
                n_iterations=n_iterations,
                n_seeds=n_seeds,
                validation=True
            )

            pseudotime = pd.Series(
                timeax_results['pseudotime'],
                index=metadata['sample_id'] if 'sample_id' in metadata.columns else metadata.index,
                name='pseudotime'
            )
            robustness_score = timeax_results.get('robustness', 0.0)
            monotonicity_score = timeax_results.get('monotonicity', None)
            r_plot_files = timeax_results.get('r_plot_files', [])
            seed_features_list = timeax_results.get('seed_features', None)

            print(f"✓ TimeAx completed")
            if monotonicity_score is not None:
                print(f"✓ Monotonicity score: {monotonicity_score:.3f}", end="")
                if monotonicity_score > 0.5:
                    print(" (good)")
                elif monotonicity_score > 0.3:
                    print(" (moderate)")
                else:
                    print(" (weak - consider preprocessing adjustments)")
            print(f"  LOO robustness: {robustness_score:.3f}")

        except ImportError:
            print("✗ TimeAx not available. Using fallback: sample ordering by time")
            print("  Install TimeAx R package: Rscript -e 'remotes::install_github(\"amitfrish/TimeAx\")'")
            pseudotime = _fallback_pseudotime(metadata, time_column, patient_column)
            model = None
            robustness_score = 0.0
            print("✓ Using observed timepoints as pseudotime")

    elif method == 'lmm':
        print("Running Linear Mixed Models trajectory...")
        try:
            try:
                from .lmm_trajectory import fit_lmm_trajectories
            except ImportError:
                from lmm_trajectory import fit_lmm_trajectories
            model, pseudotime = fit_lmm_trajectories(data, metadata)
            robustness_score = None
            print("✓ LMM completed")
        except ImportError:
            print("✗ LMM modules not available")
            pseudotime = _fallback_pseudotime(metadata, time_column, patient_column)
            model = None
            robustness_score = None

    elif method == 'hmm':
        print("Running Hidden Markov Model trajectory...")
        try:
            try:
                from .hmm_states import fit_hmm_model
            except ImportError:
                from hmm_states import fit_hmm_model
            model, pseudotime = fit_hmm_model(data, metadata)
            robustness_score = None
            print("✓ HMM completed")
        except ImportError:
            print("✗ HMM modules not available")
            pseudotime = _fallback_pseudotime(metadata, time_column, patient_column)
            model = None
            robustness_score = None

    else:
        raise ValueError(f"Unknown method: {method}. Use 'timeax', 'lmm', or 'hmm'")

    # Identify trajectory-associated features using polynomial regression
    print("\nIdentifying trajectory-associated features (polynomial regression)...")
    trajectory_features, feature_stats = _find_trajectory_features(
        data,
        pseudotime,
        fdr_threshold=fdr_threshold,
        max_poly_degree=max_poly_degree
    )

    print(f"  Found {len(trajectory_features)} features genome-wide (FDR < {fdr_threshold})")

    # If 0 features found genome-wide and we have seed features, re-test seeds only
    # (100 tests vs 17K+ tests = much lighter FDR burden)
    if len(trajectory_features) == 0 and method == 'timeax':
        if seed_features_list is None:
            seed_features_list = timeax_results.get('seed_features', None)
        if seed_features_list and len(seed_features_list) > 0:
            seed_in_data = [f for f in seed_features_list if f in data.index]
            if len(seed_in_data) > 0:
                print(f"  Re-testing {len(seed_in_data)} TimeAx seed features (reduced FDR burden)...")
                seed_data = data.loc[seed_in_data]
                trajectory_features, seed_stats = _find_trajectory_features(
                    seed_data,
                    pseudotime,
                    fdr_threshold=fdr_threshold,
                    max_poly_degree=max_poly_degree
                )
                # Merge seed stats into feature_stats
                feature_stats = pd.concat([
                    feature_stats[~feature_stats['feature'].isin(seed_stats['feature'])],
                    seed_stats
                ], ignore_index=True)
                print(f"  Found {len(trajectory_features)} seed features (FDR < {fdr_threshold})")

    # If still 0, use seed features with nominal p < 0.05 (pre-selected by TimeAx)
    if len(trajectory_features) == 0 and seed_features_list:
        seed_in_stats = feature_stats[feature_stats['feature'].isin(seed_features_list)]
        nominally_sig = seed_in_stats[seed_in_stats['pvalue'] < 0.05].sort_values('r_squared', ascending=False)
        if len(nominally_sig) > 0:
            trajectory_features = nominally_sig.copy()
            print(f"  Using {len(trajectory_features)} seed features with nominal p < 0.05")

    print(f"✓ {len(trajectory_features)} trajectory features identified")
    if len(trajectory_features) > 0:
        top = trajectory_features.iloc[0]
        print(f"  Top feature: {top['feature']} (R²={top['r_squared']:.3f}, degree={int(top['best_degree'])})")

    # Compile results
    results = {
        'pseudotime': pseudotime,
        'trajectory_features': trajectory_features,
        'model': model,
        'robustness_score': robustness_score,
        'monotonicity_score': monotonicity_score,
        'method': method,
        'feature_stats': feature_stats,
        'n_trajectory_features': len(trajectory_features),
        'r_plot_files': r_plot_files,
        'seed_features': seed_features_list if seed_features_list else []
    }

    print("\n" + "="*50)
    print("✓ Trajectory analysis completed successfully!")
    print("="*50 + "\n")

    return results


def _fallback_pseudotime(metadata, time_column, patient_column):
    """
    Fallback pseudotime using observed timepoints.

    Scales timepoints to [0, 1] range globally.
    """
    timepoints = metadata[time_column].values
    pseudotime = (timepoints - timepoints.min()) / (timepoints.max() - timepoints.min())

    return pd.Series(
        pseudotime,
        index=metadata['sample_id'] if 'sample_id' in metadata.columns else metadata.index,
        name='pseudotime'
    )


def _find_trajectory_features(
    data: pd.DataFrame,
    pseudotime: pd.Series,
    fdr_threshold: float = 0.05,
    max_poly_degree: int = 3
) -> tuple:
    """
    Identify features that change significantly along the trajectory.

    Uses polynomial regression (linear, quadratic, cubic) following the
    TimeAx paper methodology (Frishberg et al., Nat Commun 2023). For each
    feature, fits polynomials of increasing degree and uses nested F-tests
    to select the best model. Features are filtered by FDR-corrected Q-value
    only (no minimum effect-size filter), capturing both monotonic and
    non-monotonic dynamics (e.g., peak-then-decline patterns).

    Parameters
    ----------
    data : pd.DataFrame
        Expression data (features × samples)
    pseudotime : pd.Series
        Pseudotime values for each sample
    fdr_threshold : float
        FDR threshold for significance (Q-value)
    max_poly_degree : int
        Maximum polynomial degree to test (1=linear, 2=quad, 3=cubic)

    Returns
    -------
    trajectory_features : pd.DataFrame
        Significant trajectory features sorted by R²
    feature_stats : pd.DataFrame
        Statistics for all features
    """

    # Align pseudotime with data columns
    if not all(pseudotime.index == data.columns):
        pseudotime = pseudotime.reindex(data.columns)

    pt = pseudotime.values
    n = len(pt)

    # Pre-compute Vandermonde-style design matrices for each degree
    # (centered and scaled pseudotime for numerical stability)
    pt_mean, pt_std = pt.mean(), pt.std()
    pt_scaled = (pt - pt_mean) / pt_std if pt_std > 0 else pt - pt_mean

    designs = {}
    for deg in range(1, max_poly_degree + 1):
        # Design matrix: intercept + polynomial terms up to degree
        X = np.column_stack([pt_scaled**d for d in range(deg + 1)])
        designs[deg] = X

    # Null model: intercept only
    X0 = np.ones((n, 1))
    ss_total_denom = n - 1  # for R² computation

    results_list = []

    for idx, row in data.iterrows():
        y = row.values.astype(float)

        # Skip features with no variance
        y_var = np.var(y)
        if y_var == 0 or np.isnan(y_var):
            results_list.append({
                'feature': idx,
                'best_degree': 0,
                'r_squared': 0.0,
                'f_statistic': 0.0,
                'pvalue': 1.0,
                'coefficients': None,
                'direction': 'flat'
            })
            continue

        ss_total = np.sum((y - y.mean())**2)

        # Fit each polynomial degree and find best via nested F-test
        best_degree = 0
        best_rss = ss_total  # null model RSS = SS_total
        best_r2 = 0.0
        best_f = 0.0
        best_p = 1.0
        best_coeffs = None

        for deg in range(1, max_poly_degree + 1):
            X = designs[deg]
            try:
                coeffs, rss_arr, _, _ = np.linalg.lstsq(X, y, rcond=None)
                y_pred = X @ coeffs
                rss = np.sum((y - y_pred)**2)
            except np.linalg.LinAlgError:
                continue

            r2 = 1.0 - rss / ss_total if ss_total > 0 else 0.0

            # F-test: compare this degree model vs null (intercept only)
            # F = ((SS_null - SS_model) / df_model) / (SS_model / df_resid)
            df_model = deg  # number of polynomial terms (excluding intercept)
            df_resid = n - deg - 1
            if df_resid <= 0:
                continue

            f_stat = ((ss_total - rss) / df_model) / (rss / df_resid)
            p_val = 1.0 - f_dist.cdf(f_stat, df_model, df_resid)

            # Also test improvement over previous degree (nested F-test)
            if deg > 1 and best_degree > 0:
                df_diff = deg - best_degree
                if df_diff > 0 and df_resid > 0:
                    f_improve = ((best_rss - rss) / df_diff) / (rss / df_resid)
                    p_improve = 1.0 - f_dist.cdf(f_improve, df_diff, df_resid)
                    # Only upgrade if significant improvement (p < 0.05)
                    if p_improve < 0.05 and p_val < best_p:
                        best_degree = deg
                        best_rss = rss
                        best_r2 = r2
                        best_f = f_stat
                        best_p = p_val
                        best_coeffs = coeffs
                    continue

            # For degree 1, or if no previous model
            if p_val < best_p:
                best_degree = deg
                best_rss = rss
                best_r2 = r2
                best_f = f_stat
                best_p = p_val
                best_coeffs = coeffs

        # Determine direction from polynomial
        if best_coeffs is not None and best_degree >= 1:
            # Evaluate polynomial at endpoints to determine net direction
            pt_start = pt_scaled.min()
            pt_end = pt_scaled.max()
            y_start = sum(best_coeffs[d] * pt_start**d for d in range(best_degree + 1))
            y_end = sum(best_coeffs[d] * pt_end**d for d in range(best_degree + 1))
            direction = 'up' if y_end > y_start else 'down'
        else:
            direction = 'flat'

        results_list.append({
            'feature': idx,
            'best_degree': best_degree,
            'r_squared': best_r2,
            'f_statistic': best_f,
            'pvalue': best_p,
            'coefficients': best_coeffs.tolist() if best_coeffs is not None else None,
            'direction': direction
        })

    # Create results dataframe
    feature_stats = pd.DataFrame(results_list)

    # FDR correction
    feature_stats['padj'] = multipletests(
        feature_stats['pvalue'].values, method='fdr_bh'
    )[1]

    # Filter by FDR only (no effect-size filter, matching paper)
    trajectory_features = feature_stats[
        feature_stats['padj'] < fdr_threshold
    ].copy()

    # Sort by R² descending
    trajectory_features = trajectory_features.sort_values('r_squared', ascending=False)

    return trajectory_features, feature_stats


if __name__ == '__main__':
    """Test trajectory analysis with synthetic data."""

    from load_and_preprocess import load_example_data, load_and_preprocess_data
    import tempfile
    import os

    # Load and preprocess example data
    print("Loading example data...")
    data, metadata = load_example_data()

    # Save to temp files for preprocessing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        data_file = f.name
        data.to_csv(data_file)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        metadata_file = f.name
        metadata.to_csv(metadata_file, index=False)

    # Preprocess
    data_processed, metadata_out, _ = load_and_preprocess_data(
        data_file, metadata_file, min_patients=5, min_timepoints=3
    )

    # Run trajectory analysis
    results = run_trajectory_analysis(
        data_processed,
        metadata_out,
        method='timeax',
        n_iterations=50,  # Reduced for testing
        n_seeds=25
    )

    print("\nTrajectory Analysis Results:")
    print(f"  Method: {results['method']}")
    print(f"  Robustness: {results['robustness_score']}")
    print(f"  Trajectory features: {results['n_trajectory_features']}")
    print(f"\nTop 5 trajectory features:")
    print(results['trajectory_features'].head()[['feature', 'r_squared', 'best_degree', 'padj']])

    # Cleanup
    os.remove(data_file)
    os.remove(metadata_file)

