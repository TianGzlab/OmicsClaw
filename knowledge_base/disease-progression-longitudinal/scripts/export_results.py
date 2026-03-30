"""
Export all trajectory analysis results and model objects.

This module provides the export_all() function for Step 4 of the standard workflow.
"""

import pandas as pd
import numpy as np
import pickle
import json
import os
from typing import Dict, Optional, List
from datetime import datetime


def export_all(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    results: Dict,
    output_dir: str = 'trajectory_results',
    include_plots: bool = True
) -> None:
    """
    Export all trajectory analysis results, model objects, and metadata.

    This is the Step 4 function that exports:
    - Pseudotime assignments (CSV)
    - Trajectory features (CSV)
    - Patient summaries (CSV)
    - Model object (pickle) - CRITICAL for downstream use
    - Analysis metadata (JSON)
    - Optional: plots if generated

    Parameters
    ----------
    data : pd.DataFrame
        Preprocessed data matrix (features × samples)
    metadata : pd.DataFrame
        Sample metadata with pseudotime
    results : dict
        Results from run_trajectory_analysis() containing:
        - 'pseudotime': sample pseudotimes
        - 'trajectory_features': significant features
        - 'model': fitted model object
        - 'robustness_score': quality metric
        - 'method': method used
        - 'feature_stats': statistics for all features
    output_dir : str, default='trajectory_results'
        Output directory for all files
    include_plots : bool, default=True
        Whether to copy plot files to export directory

    Returns
    -------
    None
        Saves all outputs to output_dir
    """

    print("\n=== Step 4: Export Results ===\n")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Extract results
    pseudotime = results['pseudotime']
    trajectory_features = results['trajectory_features']
    feature_stats = results['feature_stats']
    model = results.get('model')
    robustness_score = results.get('robustness_score')
    monotonicity_score = results.get('monotonicity_score')
    method = results.get('method', 'unknown')

    # 1. Export pseudotime assignments
    print("Exporting pseudotime assignments...")
    pseudotime_df = pd.DataFrame({
        'sample_id': pseudotime.index,
        'pseudotime': pseudotime.values
    })

    # Add metadata columns if available
    metadata_cols = ['patient_id', 'timepoint']
    for col in metadata_cols:
        if col in metadata.columns:
            pseudotime_df[col] = metadata[col].values

    # Add optional metadata columns
    optional_cols = ['outcome', 'treatment', 'stage', 'batch']
    for col in optional_cols:
        if col in metadata.columns:
            pseudotime_df[col] = metadata[col].values

    pseudotime_file = os.path.join(output_dir, 'pseudotime_assignments.csv')
    pseudotime_df.to_csv(pseudotime_file, index=False)
    print(f"  ✓ {pseudotime_file}")

    # 2. Export trajectory features
    print("Exporting trajectory features...")
    if len(trajectory_features) > 0:
        trajectory_file = os.path.join(output_dir, 'trajectory_features.csv')
        trajectory_features.to_csv(trajectory_file, index=False)
        print(f"  ✓ {trajectory_file}")
        print(f"    ({len(trajectory_features)} significant features)")
    else:
        print("  (No trajectory features found)")

    # 3. Export all feature statistics
    print("Exporting all feature statistics...")
    feature_stats_file = os.path.join(output_dir, 'all_feature_statistics.csv')
    feature_stats.to_csv(feature_stats_file, index=False)
    print(f"  ✓ {feature_stats_file}")

    # 4. Export patient summaries
    print("Exporting patient summaries...")
    patient_summaries = _generate_patient_summaries(metadata, pseudotime)
    patient_file = os.path.join(output_dir, 'patient_summaries.csv')
    patient_summaries.to_csv(patient_file, index=False)
    print(f"  ✓ {patient_file}")

    # 5. CRITICAL: Export model object (pickle)
    print("Exporting model object...")
    if model is not None:
        model_file = os.path.join(output_dir, 'timeax_model.pkl')
        try:
            with open(model_file, 'wb') as f:
                pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"  ✓ {model_file}")
            print(f"    (Load with: model = pickle.load(open('timeax_model.pkl', 'rb')))")
        except Exception as e:
            print(f"  ✗ Failed to save model: {e}")
    else:
        print("  (No model object to save)")

    # 6. Export metadata and parameters
    print("Exporting analysis metadata...")
    analysis_metadata = {
        'analysis_date': datetime.now().isoformat(),
        'method': method,
        'robustness_score': robustness_score if robustness_score is not None else 'N/A',
        'monotonicity_score': monotonicity_score if monotonicity_score is not None else 'N/A',
        'n_samples': len(pseudotime),
        'n_patients': metadata['patient_id'].nunique() if 'patient_id' in metadata.columns else 'N/A',
        'n_features': data.shape[0],
        'n_trajectory_features': len(trajectory_features),
        'pseudotime_range': [float(pseudotime.min()), float(pseudotime.max())],
        'outputs': {
            'pseudotime_assignments': 'pseudotime_assignments.csv',
            'trajectory_features': 'trajectory_features.csv' if len(trajectory_features) > 0 else None,
            'patient_summaries': 'patient_summaries.csv',
            'model_object': 'timeax_model.pkl' if model is not None else None,
            'feature_statistics': 'all_feature_statistics.csv'
        }
    }

    metadata_file = os.path.join(output_dir, 'model_metadata.json')
    with open(metadata_file, 'w') as f:
        json.dump(analysis_metadata, f, indent=2)
    print(f"  ✓ {metadata_file}")

    # 7. List plots if they exist
    print("\nChecking for visualizations...")
    plot_files = [
        'patient_trajectories_pca.png',
        'patient_trajectories_pca.svg',
        'patient_trajectories_umap.png',
        'patient_trajectories_umap.svg',
        'trajectory_heatmap.png',
        'trajectory_heatmap.svg',
        'trajectory_trends.png',
        'trajectory_trends.svg',
        'pseudotime_vs_stage.png',
        'pseudotime_vs_stage.svg',
        'patient_progression.png',
        'patient_progression.svg',
        'seed_feature_heatmap.png',
        'seed_feature_heatmap.svg',
        'timeax_pseudotime_vs_time.png',
        'timeax_progression_rates.png',
        'timeax_seed_dynamics.png',
        'timeax_uncertainty.png',
    ]

    found_plots = []
    for plot_file in plot_files:
        plot_path = os.path.join(output_dir, plot_file)
        if os.path.exists(plot_path):
            found_plots.append(plot_file)

    if found_plots:
        print(f"  ✓ Found {len(found_plots)} visualization files")
    else:
        print("  (No visualization files found - generate with generate_all_plots())")

    # 8. Generate summary report (markdown)
    print("\nGenerating summary report...")
    _generate_summary_report(
        output_dir,
        analysis_metadata,
        pseudotime_df,
        trajectory_features,
        patient_summaries
    )
    print(f"  ✓ {os.path.join(output_dir, 'SUMMARY.txt')}")

    # 9. Generate PDF report (optional - requires reportlab)
    try:
        from scripts.generate_report import generate_report
        generate_report(data, metadata, results, output_dir=output_dir)
    except ImportError:
        try:
            from generate_report import generate_report
            generate_report(data, metadata, results, output_dir=output_dir)
        except ImportError:
            pass
    except Exception as e:
        print(f"  PDF generation skipped: {e}")
        print("  (Markdown report still available)")

    print("\n" + "="*50)
    print("=== Export Complete ===")
    print("="*50)
    print(f"\nAll results saved to: {output_dir}/")
    print(f"\nKey outputs:")
    print(f"  - pseudotime_assignments.csv ({len(pseudotime)} samples)")
    if len(trajectory_features) > 0:
        print(f"  - trajectory_features.csv ({len(trajectory_features)} features)")
    if model is not None:
        print(f"  - timeax_model.pkl (for downstream analysis)")
    print(f"  - model_metadata.json (analysis parameters)")
    print(f"\nNext steps:")
    print(f"  - Review visualizations in {output_dir}/")
    print(f"  - Use trajectory_features.csv for functional enrichment")
    print(f"  - Load model for projecting new samples")
    print()


def _generate_patient_summaries(metadata: pd.DataFrame, pseudotime: pd.Series) -> pd.DataFrame:
    """
    Generate per-patient trajectory statistics.

    Parameters
    ----------
    metadata : pd.DataFrame
        Sample metadata with patient_id and timepoint
    pseudotime : pd.Series
        Pseudotime values

    Returns
    -------
    patient_summaries : pd.DataFrame
        Per-patient statistics
    """

    if 'patient_id' not in metadata.columns:
        return pd.DataFrame()

    # Add pseudotime to metadata
    metadata_with_pt = metadata.copy()
    metadata_with_pt['pseudotime'] = pseudotime.values

    # Calculate per-patient statistics
    summaries = []
    for patient, group in metadata_with_pt.groupby('patient_id'):
        summary = {
            'patient_id': patient,
            'n_timepoints': len(group),
            'first_timepoint': group['timepoint'].min() if 'timepoint' in group.columns else None,
            'last_timepoint': group['timepoint'].max() if 'timepoint' in group.columns else None,
            'time_span': group['timepoint'].max() - group['timepoint'].min() if 'timepoint' in group.columns else None,
            'first_pseudotime': group['pseudotime'].iloc[0],
            'last_pseudotime': group['pseudotime'].iloc[-1],
            'pseudotime_change': group['pseudotime'].iloc[-1] - group['pseudotime'].iloc[0],
            'mean_pseudotime': group['pseudotime'].mean(),
            'progression_rate': (group['pseudotime'].iloc[-1] - group['pseudotime'].iloc[0]) / max(group['timepoint'].max() - group['timepoint'].min(), 1) if 'timepoint' in group.columns else None
        }
        summaries.append(summary)

    return pd.DataFrame(summaries)


def _generate_summary_report(
    output_dir: str,
    metadata: dict,
    pseudotime_df: pd.DataFrame,
    trajectory_features: pd.DataFrame,
    patient_summaries: pd.DataFrame
) -> None:
    """Generate a human-readable summary report."""

    report_file = os.path.join(output_dir, 'SUMMARY.txt')

    with open(report_file, 'w') as f:
        f.write("="*70 + "\n")
        f.write("DISEASE PROGRESSION TRAJECTORY ANALYSIS - SUMMARY REPORT\n")
        f.write("="*70 + "\n\n")

        f.write(f"Analysis Date: {metadata['analysis_date']}\n")
        f.write(f"Method: {metadata['method']}\n")
        if metadata.get('monotonicity_score', 'N/A') != 'N/A':
            f.write(f"Monotonicity Score: {metadata['monotonicity_score']:.3f}\n")
        if metadata['robustness_score'] != 'N/A':
            f.write(f"LOO Robustness: {metadata['robustness_score']:.3f}\n")
        f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("DATA SUMMARY\n")
        f.write("-" * 70 + "\n")
        f.write(f"Samples: {metadata['n_samples']}\n")
        f.write(f"Patients: {metadata['n_patients']}\n")
        f.write(f"Features analyzed: {metadata['n_features']}\n")
        f.write(f"Trajectory features identified: {metadata['n_trajectory_features']}\n")
        f.write(f"Pseudotime range: [{metadata['pseudotime_range'][0]:.3f}, {metadata['pseudotime_range'][1]:.3f}]\n")
        f.write("\n")

        if len(trajectory_features) > 0:
            f.write("-" * 70 + "\n")
            f.write("TOP 10 TRAJECTORY FEATURES\n")
            f.write("-" * 70 + "\n")
            for idx, row in trajectory_features.head(10).iterrows():
                r2 = row.get('r_squared', row.get('correlation', 0))
                deg = int(row.get('best_degree', 0))
                deg_label = {1: 'lin', 2: 'quad', 3: 'cub'}.get(deg, f'd{deg}')
                f.write(f"{row['feature']:20s}  R²={r2:5.3f}  padj={row['padj']:.2e}  {deg_label:4s}  {row['direction']}\n")
            f.write("\n")

        if len(patient_summaries) > 0:
            f.write("-" * 70 + "\n")
            f.write("PATIENT PROGRESSION STATISTICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mean timepoints per patient: {patient_summaries['n_timepoints'].mean():.1f}\n")
            f.write(f"Mean pseudotime change: {patient_summaries['pseudotime_change'].mean():.3f}\n")
            if 'progression_rate' in patient_summaries.columns and patient_summaries['progression_rate'].notna().any():
                f.write(f"Mean progression rate: {patient_summaries['progression_rate'].mean():.3f} pseudotime/time unit\n")
            f.write("\n")

            # Identify fast vs slow progressors
            median_change = patient_summaries['pseudotime_change'].median()
            fast_progressors = patient_summaries[patient_summaries['pseudotime_change'] > median_change]
            slow_progressors = patient_summaries[patient_summaries['pseudotime_change'] <= median_change]

            f.write(f"Fast progressors (>{median_change:.3f} change): {len(fast_progressors)}\n")
            f.write(f"Slow progressors (≤{median_change:.3f} change): {len(slow_progressors)}\n")
            f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("OUTPUT FILES\n")
        f.write("-" * 70 + "\n")
        for key, value in metadata['outputs'].items():
            if value:
                f.write(f"  {value}\n")
        f.write("\n")

        f.write("="*70 + "\n")


if __name__ == '__main__':
    """Test export function with synthetic data."""

    from load_and_preprocess import load_example_data, load_and_preprocess_data
    from run_trajectory_analysis import run_trajectory_analysis
    from generate_all_plots import generate_all_plots
    import tempfile

    print("Running complete test workflow...\n")

    # Load and preprocess
    data, metadata = load_example_data()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        data_file = f.name
        data.to_csv(data_file)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        metadata_file = f.name
        metadata.to_csv(metadata_file, index=False)

    data_processed, metadata_out, _ = load_and_preprocess_data(
        data_file, metadata_file, min_patients=5, min_timepoints=3
    )

    # Run trajectory analysis
    results = run_trajectory_analysis(
        data_processed, metadata_out, n_iterations=50, n_seeds=25
    )

    # Generate plots
    generate_all_plots(data_processed, metadata_out, results, output_dir='test_export')

    # Export all results
    export_all(data_processed, metadata_out, results, output_dir='test_export')

    print("\nComplete workflow test finished!")
    print("Check test_export/ directory for all outputs")

    # Cleanup
    os.remove(data_file)
    os.remove(metadata_file)

