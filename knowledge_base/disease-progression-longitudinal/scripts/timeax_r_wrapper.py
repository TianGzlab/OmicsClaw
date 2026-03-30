"""
Python wrapper for calling TimeAx R package via subprocess.

This module provides a bridge between Python and the R TimeAx implementation,
allowing use of the real TimeAx algorithm from Python code.
"""

import pandas as pd
import numpy as np
import subprocess
import os
import tempfile
import shutil
from typing import Tuple, Dict


class RTimeAxModel:
    """Wrapper for TimeAx R model."""

    def __init__(self, model_dir, robustness):
        self.model_dir = model_dir
        self.robustness = robustness
        self.model_path = os.path.join(model_dir, "timeax_model.rds")

        # Load seed features
        seed_df = pd.read_csv(os.path.join(model_dir, "timeax_seed_features.csv"))
        self.seed_features = seed_df['feature'].tolist()

    def predict(self, data):
        """Placeholder for prediction (would need separate R script)."""
        raise NotImplementedError("Prediction on new samples requires separate R script")


def check_r_available():
    """Check if R and TimeAx are available."""
    try:
        result = subprocess.run(
            ['Rscript', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return False, "R not found"

        # Check if TimeAx package is installed
        result = subprocess.run(
            ['Rscript', '-e', 'library(TimeAx); cat("OK")'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0 or "OK" not in result.stdout:
            return False, "TimeAx R package not installed"

        return True, "R and TimeAx available"

    except FileNotFoundError:
        return False, "R not found"
    except subprocess.TimeoutExpired:
        return False, "R check timed out"
    except Exception as e:
        return False, f"Error checking R: {e}"


def run_timeax_r(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    patient_column: str = 'patient_id',
    time_column: str = 'timepoint',
    n_iterations: int = 100,
    n_seeds: int = 50,
    temp_dir: str = None
) -> Tuple[RTimeAxModel, Dict]:
    """
    Run TimeAx via R subprocess.

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
        Number of iterations
    n_seeds : int
        Number of seed features
    temp_dir : str, optional
        Temporary directory for intermediate files

    Returns
    -------
    model : RTimeAxModel
        Model wrapper object
    results : dict
        Results dictionary with pseudotime, uncertainty, etc.
    """

    # Check R availability
    r_available, msg = check_r_available()
    if not r_available:
        raise RuntimeError(f"Cannot run TimeAx R: {msg}")

    # Create temporary directory
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp(prefix='timeax_r_')
        cleanup_temp = True
    else:
        os.makedirs(temp_dir, exist_ok=True)
        cleanup_temp = False

    print(f"  Using temporary directory: {temp_dir}")

    try:
        # Save data to CSV
        data_file = os.path.join(temp_dir, 'data_matrix.csv')
        data.to_csv(data_file)

        # Save metadata to CSV
        metadata_file = os.path.join(temp_dir, 'metadata.csv')
        metadata[['sample_id', patient_column, time_column]].to_csv(
            metadata_file, index=False
        )

        # Output directory
        output_dir = os.path.join(temp_dir, 'results')

        # Find R script
        r_script = os.path.join(
            os.path.dirname(__file__),
            'run_timeax.R'
        )

        if not os.path.exists(r_script):
            raise FileNotFoundError(f"R script not found: {r_script}")

        # Run R script
        print("  Calling TimeAx R script...")
        cmd = [
            'Rscript',
            r_script,
            data_file,
            metadata_file,
            output_dir,
            str(n_iterations),
            str(n_seeds)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes max
        )

        # Print R output
        if result.stdout:
            for line in result.stdout.split('\n'):
                if line.strip():
                    print(f"  {line}")

        if result.returncode != 0:
            print("R script error output:")
            print(result.stderr)
            raise RuntimeError(f"R script failed with exit code {result.returncode}")

        # Load results
        print("\n  Loading results from R...")

        pseudotime_df = pd.read_csv(os.path.join(output_dir, 'timeax_pseudotime.csv'))
        model_info = pd.read_csv(os.path.join(output_dir, 'timeax_model_info.csv'))

        # Extract values
        pseudotime = pseudotime_df['pseudotime'].values
        uncertainty = pseudotime_df['uncertainty'].values

        robustness_row = model_info[model_info['parameter'] == 'robustness_score']
        robustness_score = robustness_row['value'].values[0] if len(robustness_row) > 0 else None

        monotonicity_row = model_info[model_info['parameter'] == 'monotonicity_score']
        monotonicity_score = monotonicity_row['value'].values[0] if len(monotonicity_row) > 0 else None

        # Create model wrapper
        model = RTimeAxModel(output_dir, robustness_score)

        # Collect R-generated plot files
        import glob
        r_plot_files = glob.glob(os.path.join(output_dir, 'timeax_*.png')) + \
                       glob.glob(os.path.join(output_dir, 'timeax_*.svg'))

        # Compile results
        results = {
            'pseudotime': pseudotime,
            'uncertainty': uncertainty,
            'seed_features': model.seed_features,
            'robustness': robustness_score,
            'monotonicity': monotonicity_score,
            'output_dir': output_dir,
            'r_plot_files': r_plot_files
        }

        print(f"  ✓ Results loaded successfully")
        print(f"  ✓ Pseudotime range: [{pseudotime.min():.3f}, {pseudotime.max():.3f}]")
        if monotonicity_score is not None:
            print(f"  ✓ Monotonicity: {monotonicity_score:.3f}")
        if robustness_score is not None:
            print(f"  ✓ LOO robustness: {robustness_score:.3f}")
        if r_plot_files:
            print(f"  ✓ {len(r_plot_files)} TimeAx R plots generated")

        return model, results

    except subprocess.TimeoutExpired:
        raise RuntimeError("TimeAx R script timed out (>10 minutes)")

    except Exception as e:
        # Cleanup on error
        if cleanup_temp and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise

    finally:
        # Keep temp files for inspection (don't cleanup)
        pass


if __name__ == '__main__':
    """Test the R wrapper."""

    print("=== Testing TimeAx R Wrapper ===\n")

    # Check R availability
    r_available, msg = check_r_available()
    print(f"R availability: {msg}")

    if not r_available:
        print("Cannot run test without R and TimeAx")
        exit(1)

    # Create synthetic data
    print("\nGenerating synthetic data...")
    np.random.seed(42)

    n_patients = 10
    n_timepoints = 5
    n_features = 500

    # Generate data with trajectory signal
    data_list = []
    metadata_list = []

    for patient in range(n_patients):
        for t in range(n_timepoints):
            sample_id = f"P{patient}_T{t}"
            metadata_list.append({
                'sample_id': sample_id,
                'patient_id': f'P{patient}',
                'timepoint': t
            })

    n_samples = len(metadata_list)
    data = np.random.randn(n_features, n_samples) + 10

    # Add trajectory signal
    times = np.array([m['timepoint'] for m in metadata_list])
    for i in range(50):  # 50 trajectory features
        data[i, :] += times * (0.5 + np.random.rand())

    data_df = pd.DataFrame(
        data,
        index=[f'Gene_{i}' for i in range(n_features)],
        columns=[m['sample_id'] for m in metadata_list]
    )
    metadata_df = pd.DataFrame(metadata_list)

    print(f"  {n_features} features × {n_samples} samples")

    # Run TimeAx
    print("\nRunning TimeAx R...\n")
    model, results = run_timeax_r(
        data_df,
        metadata_df,
        n_iterations=50,
        n_seeds=25
    )

    print("\n=== Test Complete ===")
    print(f"Pseudotime computed: {len(results['pseudotime'])} samples")
    print(f"Seed features: {len(results['seed_features'])}")
    print(f"Robustness: {results['robustness']:.3f}")

