"""
Mock TimeAx implementation for testing.

This is a simplified implementation that mimics TimeAx behavior for testing
the complete workflow without requiring the actual TimeAx package.
"""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from typing import Tuple, Dict


class MockTimeAxModel:
    """Mock TimeAx model for testing."""

    def __init__(self, seed_features, consensus_trajectory, robustness):
        self.seed_features = seed_features
        self.consensus_trajectory = consensus_trajectory
        self.robustness = robustness
        self.feature_importance = {feat: 1.0/len(seed_features) for feat in seed_features}

    def predict(self, data):
        """Project new samples onto the trajectory."""
        # Simple projection using PCA-like approach
        return np.random.rand(data.shape[1])


def run_mock_timeax(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    patient_column: str = 'patient_id',
    time_column: str = 'timepoint',
    n_iterations: int = 100,
    n_seeds: int = 50,
    random_state: int = 42
) -> Tuple[MockTimeAxModel, Dict]:
    """
    Mock TimeAx alignment for testing.

    Simulates the TimeAx algorithm:
    1. Identify seed features (high temporal correlation)
    2. Iteratively align patient trajectories
    3. Compute consensus pseudotime
    4. Assess robustness

    Parameters
    ----------
    data : pd.DataFrame
        Feature matrix (features × samples)
    metadata : pd.DataFrame
        Sample metadata
    patient_column : str
        Patient ID column
    time_column : str
        Timepoint column
    n_iterations : int
        Number of iterations (affects robustness)
    n_seeds : int
        Number of seed features
    random_state : int
        Random seed

    Returns
    -------
    model : MockTimeAxModel
        Trained model object
    results : dict
        Results dictionary with pseudotime, uncertainty, etc.
    """

    np.random.seed(random_state)

    print("Running Mock TimeAx alignment...")
    print(f"  (Using simplified algorithm for testing)")

    # Step 1: Identify seed features (features with high temporal correlation)
    seed_features = _identify_seed_features(data, metadata, time_column, n_seeds)
    print(f"  Selected {len(seed_features)} seed features")

    # Step 2: Iterative alignment (simplified)
    pseudotime_estimates = []
    for iteration in range(min(n_iterations, 20)):  # Limit iterations for speed
        pt = _align_iteration(data, metadata, seed_features, patient_column, time_column)
        pseudotime_estimates.append(pt)

    # Step 3: Compute consensus pseudotime
    pseudotime = np.mean(pseudotime_estimates, axis=0)

    # Normalize to [0, 1]
    pseudotime = (pseudotime - pseudotime.min()) / (pseudotime.max() - pseudotime.min())

    # Step 4: Compute uncertainty and robustness
    uncertainty = np.std(pseudotime_estimates, axis=0) / (np.std(pseudotime_estimates) + 1e-10)

    # Robustness: consistency across iterations
    robustness = 1.0 - np.mean(uncertainty)

    # Add noise based on iterations (more iterations = better robustness)
    robustness_factor = min(n_iterations / 100.0, 1.0)
    robustness = 0.5 + (robustness * 0.4 * robustness_factor)  # Scale to realistic range

    print(f"  Pseudotime range: [{pseudotime.min():.3f}, {pseudotime.max():.3f}]")
    print(f"  Mean uncertainty: {np.mean(uncertainty):.3f}")
    print(f"  Robustness score: {robustness:.3f}")

    # Build consensus trajectory
    consensus_trajectory = _build_consensus_trajectory(
        data, pseudotime, seed_features
    )

    # Create model object
    model = MockTimeAxModel(
        seed_features=seed_features,
        consensus_trajectory=consensus_trajectory,
        robustness=robustness
    )

    # Compile results
    results = {
        'pseudotime': pseudotime,
        'uncertainty': uncertainty,
        'seed_features': seed_features,
        'robustness': robustness,
        'feature_importance': model.feature_importance,
        'n_iterations': n_iterations
    }

    return model, results


def _identify_seed_features(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    time_column: str,
    n_seeds: int
) -> list:
    """Identify features with coordinated temporal dynamics."""

    # Calculate correlation with time for each feature
    timepoints = metadata[time_column].values
    correlations = []

    for idx, row in data.iterrows():
        corr, _ = spearmanr(row.values, timepoints)
        correlations.append((idx, abs(corr)))

    # Sort by absolute correlation
    correlations.sort(key=lambda x: x[1], reverse=True)

    # Select top n_seeds features
    seed_features = [feat for feat, _ in correlations[:n_seeds]]

    return seed_features


def _align_iteration(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    seed_features: list,
    patient_column: str,
    time_column: str
) -> np.ndarray:
    """Single iteration of trajectory alignment."""

    # Extract seed feature data
    seed_data = data.loc[seed_features]

    # Simple alignment: PCA on seed features + time weighting
    pca = PCA(n_components=1, random_state=None)
    pc1 = pca.fit_transform(seed_data.T).flatten()

    # Weight by actual timepoints
    timepoints = metadata[time_column].values
    time_normalized = (timepoints - timepoints.min()) / (timepoints.max() - timepoints.min())

    # Combine PCA projection with time information
    pseudotime = 0.7 * pc1 + 0.3 * time_normalized

    # Add small random perturbation for iteration variability
    pseudotime += np.random.randn(len(pseudotime)) * 0.05

    return pseudotime


def _build_consensus_trajectory(
    data: pd.DataFrame,
    pseudotime: np.ndarray,
    seed_features: list
) -> Dict:
    """Build consensus trajectory model."""

    # Sort samples by pseudotime
    order = np.argsort(pseudotime)

    # Extract seed feature trajectories
    seed_data = data.loc[seed_features].values[:, order]

    consensus = {
        'pseudotime_order': order,
        'seed_trajectories': seed_data,
        'n_samples': len(pseudotime)
    }

    return consensus


if __name__ == '__main__':
    """Test mock TimeAx."""

    # Create synthetic data
    np.random.seed(42)
    n_features = 100
    n_samples = 50

    # Features that change with time
    time = np.linspace(0, 10, n_samples)
    data = np.random.randn(n_features, n_samples)

    # Add trajectory signal to top 20 features
    for i in range(20):
        data[i, :] += time * (0.5 + np.random.rand() * 0.5)

    data_df = pd.DataFrame(data, index=[f'Gene_{i}' for i in range(n_features)])
    metadata_df = pd.DataFrame({
        'sample_id': [f'S{i}' for i in range(n_samples)],
        'patient_id': [f'P{i//5}' for i in range(n_samples)],
        'timepoint': np.tile(np.arange(5), 10)
    })

    # Run mock TimeAx
    model, results = run_mock_timeax(
        data_df, metadata_df,
        n_iterations=50,
        n_seeds=20
    )

    print("\nResults:")
    print(f"  Pseudotime shape: {results['pseudotime'].shape}")
    print(f"  Robustness: {results['robustness']:.3f}")
    print(f"  Seed features: {len(results['seed_features'])}")
    print(f"  Model type: {type(model)}")

