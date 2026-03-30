"""
Generate all trajectory visualizations with PNG + SVG export.

This module creates publication-quality plots with graceful SVG fallback.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, Optional, List
import os
from sklearn.decomposition import PCA

# Set seaborn theme and Helvetica font (project standard)
sns.set_style("ticks")
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica']

# Try to import UMAP
try:
    from umap import UMAP
    UMAP_AVAILABLE = True
except ImportError:
    UMAP_AVAILABLE = False


def generate_all_plots(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
    results: Dict,
    output_dir: str = 'trajectory_results'
) -> None:
    """
    Generate all trajectory visualizations (PNG + SVG).

    This is the consolidated Step 3 function that creates:
    - PCA trajectory plot
    - UMAP trajectory plot (if available)
    - Trajectory feature heatmap
    - Feature trend plots

    Parameters
    ----------
    data : pd.DataFrame
        Preprocessed data matrix (features × samples)
    metadata : pd.DataFrame
        Sample metadata
    results : dict
        Results from run_trajectory_analysis() containing:
        - 'pseudotime': sample pseudotimes
        - 'trajectory_features': significant features
        - 'robustness_score': quality metric
    output_dir : str, default='trajectory_results'
        Output directory for plots

    Returns
    -------
    None
        Saves plots to output_dir
    """

    print("\n=== Step 3: Generate Visualizations ===\n")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Extract results
    pseudotime = results['pseudotime']
    trajectory_features = results['trajectory_features']

    # Add pseudotime to metadata for plotting
    plot_metadata = metadata.copy()
    plot_metadata['pseudotime'] = pseudotime.values

    # 1. PCA trajectory plot (with patient lines)
    print("Generating PCA trajectory plot...")
    try:
        _plot_pca_trajectory(
            data, plot_metadata,
            output_file=os.path.join(output_dir, 'patient_trajectories_pca')
        )
        print("  ✓ PCA plot saved")
    except Exception as e:
        print(f"  ✗ PCA plot failed: {e}")

    # 2. UMAP trajectory plot (if available)
    if UMAP_AVAILABLE:
        print("Generating UMAP trajectory plot...")
        try:
            _plot_umap_trajectory(
                data, plot_metadata,
                output_file=os.path.join(output_dir, 'patient_trajectories_umap')
            )
            print("  ✓ UMAP plot saved")
        except Exception as e:
            print(f"  ✗ UMAP plot failed: {e}")
    else:
        print("Skipping UMAP plot (umap-learn not installed)")

    # 3. Trajectory feature heatmap
    if len(trajectory_features) > 0:
        print("Generating trajectory feature heatmap...")
        try:
            _plot_trajectory_heatmap(
                data, plot_metadata, trajectory_features,
                output_file=os.path.join(output_dir, 'trajectory_heatmap')
            )
            print("  ✓ Heatmap saved")
        except Exception as e:
            print(f"  ✗ Heatmap failed: {e}")

        # 4. Feature trend plots (top 10)
        print("Generating feature trend plots...")
        try:
            _plot_feature_trends(
                data, plot_metadata, trajectory_features,
                output_file=os.path.join(output_dir, 'trajectory_trends')
            )
            print("  ✓ Trend plots saved")
        except Exception as e:
            print(f"  ✗ Trend plots failed: {e}")
    else:
        print("No trajectory features found - skipping heatmap and trends")

    # 5. Pseudotime vs clinical stage boxplot (biological validation)
    if 'tumor_stage' in metadata.columns:
        print("Generating pseudotime vs tumor stage plot...")
        try:
            _plot_pseudotime_vs_stage(
                plot_metadata,
                output_file=os.path.join(output_dir, 'pseudotime_vs_stage')
            )
            print("  ✓ Stage validation plot saved")
        except Exception as e:
            print(f"  ✗ Stage plot failed: {e}")

    # 6. Per-patient progression plot
    if 'patient_id' in metadata.columns and 'timepoint' in metadata.columns:
        print("Generating per-patient progression plot...")
        try:
            _plot_patient_progression(
                plot_metadata,
                output_file=os.path.join(output_dir, 'patient_progression')
            )
            print("  ✓ Patient progression plot saved")
        except Exception as e:
            print(f"  ✗ Patient progression plot failed: {e}")

    # 7. Seed feature dynamics heatmap (if seed features available)
    seed_features = results.get('seed_features', [])
    if seed_features and len(seed_features) > 0:
        seed_in_data = [f for f in seed_features if f in data.index]
        if len(seed_in_data) > 0:
            print("Generating seed feature dynamics heatmap...")
            try:
                _plot_seed_heatmap(
                    data, plot_metadata, seed_in_data,
                    output_file=os.path.join(output_dir, 'seed_feature_heatmap')
                )
                print("  ✓ Seed feature heatmap saved")
            except Exception as e:
                print(f"  ✗ Seed heatmap failed: {e}")

    # 8. Copy TimeAx R plots if they exist
    r_plot_files = results.get('r_plot_files', [])
    if r_plot_files:
        import shutil
        print("Copying TimeAx R plots...")
        for src_path in r_plot_files:
            dst_path = os.path.join(output_dir, os.path.basename(src_path))
            if os.path.abspath(src_path) != os.path.abspath(dst_path):
                shutil.copy2(src_path, dst_path)
            print(f"  ✓ {os.path.basename(src_path)}")

    print("\n" + "="*50)
    print("✓ All visualizations generated successfully!")
    print("="*50 + "\n")


def _save_plot(fig, base_path: str, width: float = 8, height: float = 6, dpi: int = 300):
    """
    Save plot as both PNG and SVG with graceful fallback.

    Parameters
    ----------
    fig : matplotlib.figure.Figure or plotnine.ggplot
        Figure to save
    base_path : str
        Base file path (without extension)
    width : float
        Width in inches
    height : float
        Height in inches
    dpi : int
        DPI for PNG export
    """

    # Always save PNG
    png_path = f"{base_path}.png"
    fig.savefig(png_path, dpi=dpi, bbox_inches='tight')
    print(f"   Saved: {png_path}")

    # Always try SVG
    svg_path = f"{base_path}.svg"
    try:
        fig.savefig(svg_path, format='svg', bbox_inches='tight')
        print(f"   Saved: {svg_path}")
    except Exception as e:
        print(f"   (SVG export failed)")


def _plot_pca_trajectory(data, metadata, output_file):
    """Create PCA plot colored by pseudotime with patient trajectory lines."""

    # Run PCA
    pca = PCA(n_components=2)
    pca_coords = pca.fit_transform(data.T)

    pseudotime_vals = np.asarray(metadata['pseudotime'])

    plot_df = pd.DataFrame({
        'PC1': pca_coords[:, 0],
        'PC2': pca_coords[:, 1],
        'pseudotime': pseudotime_vals
    }, index=range(len(pseudotime_vals)))

    # Add patient_id and timepoint for trajectory lines
    if 'patient_id' in metadata.columns:
        plot_df['patient_id'] = metadata['patient_id'].values
    if 'timepoint' in metadata.columns:
        plot_df['timepoint'] = metadata['timepoint'].values

    fig, ax = plt.subplots(figsize=(9, 7))

    # Draw patient trajectory lines (connecting same-patient samples by timepoint)
    if 'patient_id' in plot_df.columns and 'timepoint' in plot_df.columns:
        for pid, group in plot_df.groupby('patient_id'):
            group_sorted = group.sort_values('timepoint')
            ax.plot(group_sorted['PC1'], group_sorted['PC2'],
                    color='gray', alpha=0.3, linewidth=0.8, zorder=1)

    # Scatter points colored by pseudotime
    scatter = ax.scatter(
        plot_df['PC1'], plot_df['PC2'],
        c=plot_df['pseudotime'],
        cmap='RdYlBu_r', s=60, alpha=0.85, edgecolors='white',
        linewidth=0.5, zorder=2
    )
    ax.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)')
    ax.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)')
    ax.set_title('Disease Trajectory in Gene Expression Space (PCA)')
    cbar = plt.colorbar(scatter, label='Disease Pseudotime', ax=ax)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    _save_plot(fig, output_file, width=9, height=7)
    plt.close(fig)


def _plot_umap_trajectory(data, metadata, output_file):
    """Create UMAP plot colored by pseudotime."""

    # Run UMAP
    umap = UMAP(n_components=2, random_state=42)
    umap_coords = umap.fit_transform(data.T)

    # Create clean DataFrame with numpy arrays (avoid Series issues)
    pseudotime_vals = np.asarray(metadata['pseudotime'])

    plot_df = pd.DataFrame(
        data={
            'UMAP1': umap_coords[:, 0],
            'UMAP2': umap_coords[:, 1],
            'pseudotime': pseudotime_vals
        },
        index=range(len(pseudotime_vals))
    )

    # Use matplotlib (most compatible)
    fig, ax = plt.subplots(figsize=(8, 6))
    scatter = ax.scatter(
        plot_df['UMAP1'], plot_df['UMAP2'],
        c=plot_df['pseudotime'],
        cmap='RdYlBu_r', s=50, alpha=0.7
    )
    ax.set_xlabel('UMAP1')
    ax.set_ylabel('UMAP2')
    ax.set_title('Patient Trajectory - UMAP')
    plt.colorbar(scatter, label='Pseudotime', ax=ax)
    _save_plot(fig, output_file)
    plt.close(fig)


def _plot_trajectory_heatmap(data, metadata, trajectory_features, output_file, max_features=50):
    """Create clustermap of trajectory features ordered by pseudotime."""

    # Select top features
    top_features = trajectory_features.head(max_features)['feature'].values
    heatmap_data = data.loc[top_features]

    # Sort samples by pseudotime
    sample_order = metadata.sort_values('pseudotime')['sample_id'].values if 'sample_id' in metadata.columns else metadata.sort_values('pseudotime').index
    heatmap_data = heatmap_data[sample_order]

    # Z-score normalization for visualization
    row_means = heatmap_data.mean(axis=1)
    row_stds = heatmap_data.std(axis=1).replace(0, 1)
    heatmap_data_z = heatmap_data.sub(row_means, axis=0).div(row_stds, axis=0)
    heatmap_data_z = heatmap_data_z.clip(-3, 3)

    # Pseudotime color bar for columns
    pt_sorted = metadata.sort_values('pseudotime')['pseudotime'].values
    pt_norm = (pt_sorted - pt_sorted.min()) / (pt_sorted.max() - pt_sorted.min())
    col_colors = plt.cm.RdYlBu_r(pt_norm)

    # Use sns.clustermap (project standard for heatmaps)
    g = sns.clustermap(
        heatmap_data_z,
        cmap='RdBu_r',
        center=0,
        vmin=-3, vmax=3,
        figsize=(12, max(8, len(top_features) * 0.25)),
        cbar_kws={'label': 'Z-score'},
        xticklabels=False,
        yticklabels=True,
        col_cluster=False,  # Keep pseudotime ordering
        row_cluster=True,   # Cluster genes by pattern
        col_colors=col_colors,
        dendrogram_ratio=0.1,
    )
    g.ax_heatmap.set_xlabel('Samples (ordered by pseudotime)', fontsize=10)
    g.ax_heatmap.set_ylabel('')
    g.fig.suptitle(f'Top {len(top_features)} Trajectory Features', fontsize=13, fontweight='bold', y=1.01)
    plt.setp(g.ax_heatmap.get_yticklabels(), fontsize=max(6, min(9, 200 // len(top_features))))

    # Save using clustermap's figure
    png_path = f"{output_file}.png"
    g.savefig(png_path, dpi=300, bbox_inches='tight')
    print(f"   Saved: {png_path}")
    svg_path = f"{output_file}.svg"
    try:
        g.savefig(svg_path, format='svg', bbox_inches='tight')
        print(f"   Saved: {svg_path}")
    except Exception:
        print(f"   (SVG export failed)")
    plt.close(g.fig)


def _plot_feature_trends(data, metadata, trajectory_features, output_file, n_features=10):
    """Plot polynomial fit trends for top trajectory features."""

    # Select top features
    top_features = trajectory_features.head(n_features)
    n_actual = min(n_features, len(top_features))

    # Sort by pseudotime
    sample_order = np.argsort(metadata['pseudotime'].values)
    pseudotime_sorted = metadata['pseudotime'].values[sample_order]

    # Scaled pseudotime (match feature identification)
    pt_mean, pt_std = pseudotime_sorted.mean(), pseudotime_sorted.std()
    pt_scaled = (pseudotime_sorted - pt_mean) / pt_std if pt_std > 0 else pseudotime_sorted - pt_mean

    # Smooth x for fit line
    pt_fit = np.linspace(pseudotime_sorted.min(), pseudotime_sorted.max(), 200)
    pt_fit_scaled = (pt_fit - pt_mean) / pt_std if pt_std > 0 else pt_fit - pt_mean

    # Degree labels
    degree_labels = {1: 'linear', 2: 'quadratic', 3: 'cubic'}

    # Create subplot grid
    nrows = (n_actual + 1) // 2
    ncols = 2
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 2.5 * nrows))
    if nrows == 1:
        axes = np.array([axes]).flatten() if ncols > 1 else np.array([axes])
    else:
        axes = axes.flatten()

    for idx, (_, feature_row) in enumerate(top_features.iterrows()):
        if idx >= n_actual:
            break

        feature = feature_row['feature']
        expression = data.loc[feature].values[sample_order]

        ax = axes[idx]
        ax.scatter(pseudotime_sorted, expression, alpha=0.3, s=20, color='gray')

        # Overlay polynomial fit
        best_degree = int(feature_row.get('best_degree', 1))
        coeffs = feature_row.get('coefficients', None)

        if coeffs is not None and isinstance(coeffs, list) and len(coeffs) > 0:
            # Evaluate stored coefficients
            y_fit = np.zeros(len(pt_fit_scaled))
            for d, c in enumerate(coeffs):
                y_fit += c * pt_fit_scaled**d
            ax.plot(pt_fit, y_fit, color='blue', linewidth=2)
        else:
            # Refit polynomial from data
            try:
                poly_coeffs = np.polyfit(pt_scaled, expression, best_degree)
                y_fit = np.polyval(poly_coeffs, pt_fit_scaled)
                ax.plot(pt_fit, y_fit, color='blue', linewidth=2)
            except Exception:
                pass

        r2 = feature_row.get('r_squared', 0)
        deg_label = degree_labels.get(best_degree, f'deg{best_degree}')
        ax.set_xlabel('Pseudotime')
        ax.set_ylabel('Expression')
        ax.set_title(f"{feature} (R²={r2:.2f}, {deg_label})")

    # Hide unused subplots
    for idx in range(n_actual, len(axes)):
        axes[idx].set_visible(False)

    plt.tight_layout()
    _save_plot(fig, output_file, width=12, height=2.5*nrows)
    plt.close(fig)


def _plot_pseudotime_vs_stage(metadata, output_file):
    """Boxplot of pseudotime by tumor stage — key biological validation."""
    from scipy import stats as sp_stats

    df = metadata.copy()

    # Filter to samples with valid tumor stage
    stage_order = ['Ta', 'T1', 'T2', 'T3', 'T4']
    df = df[df['tumor_stage'].isin(stage_order)].copy()
    if len(df) < 10:
        print("   Too few staged samples for boxplot")
        return

    df['tumor_stage'] = pd.Categorical(df['tumor_stage'], categories=stage_order, ordered=True)

    # Compute Spearman correlation
    stage_map = {s: i for i, s in enumerate(stage_order)}
    stage_num = df['tumor_stage'].map(stage_map).values
    rho, pval = sp_stats.spearmanr(df['pseudotime'].values, stage_num)

    fig, ax = plt.subplots(figsize=(7, 6))

    # Box + strip plot
    stage_groups = [df[df['tumor_stage'] == s]['pseudotime'].values for s in stage_order if s in df['tumor_stage'].values]
    stage_labels = [s for s in stage_order if s in df['tumor_stage'].values]
    positions = list(range(len(stage_labels)))

    bp = ax.boxplot(stage_groups, positions=positions, widths=0.5,
                    patch_artist=True, showfliers=False)

    # Color boxes by stage progression
    colors = plt.cm.RdYlBu_r(np.linspace(0.2, 0.8, len(stage_labels)))
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    # Overlay individual points
    for i, (group, label) in enumerate(zip(stage_groups, stage_labels)):
        jitter = np.random.uniform(-0.15, 0.15, len(group))
        ax.scatter(np.full(len(group), i) + jitter, group,
                   color='black', alpha=0.5, s=30, zorder=3)

    ax.set_xticks(positions)
    ax.set_xticklabels(stage_labels, fontsize=12)
    ax.set_xlabel('Tumor Stage', fontsize=13)
    ax.set_ylabel('Disease Pseudotime', fontsize=13)
    ax.set_title(f'Pseudotime vs Clinical Tumor Stage\n(Spearman ρ = {rho:.3f}, p = {pval:.3e})',
                 fontsize=13, fontweight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    _save_plot(fig, output_file, width=7, height=6)
    plt.close(fig)


def _plot_patient_progression(metadata, output_file):
    """Spaghetti plot of per-patient pseudotime progression over actual time."""
    from scipy import stats as sp_stats

    df = metadata.copy()
    if 'patient_id' not in df.columns or 'timepoint' not in df.columns:
        return

    fig, ax = plt.subplots(figsize=(9, 6))

    # Compute per-patient correlation
    patient_cors = []
    for pid, group in df.groupby('patient_id'):
        group_sorted = group.sort_values('timepoint')
        color = plt.cm.tab20(hash(pid) % 20)
        ax.plot(group_sorted['timepoint'], group_sorted['pseudotime'],
                'o-', color=color, alpha=0.6, linewidth=1.5, markersize=5)

        if len(group) >= 3:
            r, _ = sp_stats.spearmanr(group['timepoint'], group['pseudotime'])
            patient_cors.append(r)

    # Add overall trend line
    from numpy.polynomial import polynomial as P
    coeffs = P.polyfit(df['timepoint'].values, df['pseudotime'].values, 1)
    x_fit = np.linspace(df['timepoint'].min(), df['timepoint'].max(), 100)
    y_fit = P.polyval(x_fit, coeffs)
    ax.plot(x_fit, y_fit, 'k--', linewidth=2, alpha=0.7, label='Overall trend')

    mean_r = np.mean(patient_cors) if patient_cors else 0
    n_pos = sum(1 for r in patient_cors if r > 0) if patient_cors else 0

    ax.set_xlabel('Actual Timepoint (visit number)', fontsize=13)
    ax.set_ylabel('Disease Pseudotime', fontsize=13)
    ax.set_title(f'Per-Patient Pseudotime Progression\n'
                 f'(Mean within-patient ρ = {mean_r:.3f}, {n_pos}/{len(patient_cors)} positive)',
                 fontsize=13, fontweight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(fontsize=10)

    _save_plot(fig, output_file, width=9, height=6)
    plt.close(fig)


def _plot_seed_heatmap(data, metadata, seed_features, output_file, max_features=40):
    """Heatmap of TimeAx seed features ordered by pseudotime."""

    # Select seed features present in data
    features = seed_features[:max_features]
    heatmap_data = data.loc[features]

    # Sort samples by pseudotime
    if 'sample_id' in metadata.columns:
        sample_order = metadata.sort_values('pseudotime')['sample_id'].values
    else:
        sample_order = metadata.sort_values('pseudotime').index
    heatmap_data = heatmap_data[sample_order]

    # Z-score normalization
    row_means = heatmap_data.mean(axis=1)
    row_stds = heatmap_data.std(axis=1)
    row_stds = row_stds.replace(0, 1)
    heatmap_z = heatmap_data.sub(row_means, axis=0).div(row_stds, axis=0)

    # Clip extreme values
    heatmap_z = heatmap_z.clip(-3, 3)

    # Create figure with pseudotime color bar on top
    fig, (ax_cbar, ax_heat) = plt.subplots(
        2, 1, figsize=(12, max(8, len(features) * 0.25 + 2)),
        gridspec_kw={'height_ratios': [1, max(15, len(features))]}
    )

    # Top: pseudotime color bar
    pt_sorted = metadata.sort_values('pseudotime')['pseudotime'].values
    ax_cbar.imshow(pt_sorted.reshape(1, -1), aspect='auto', cmap='RdYlBu_r')
    ax_cbar.set_yticks([])
    ax_cbar.set_xticks([])
    ax_cbar.set_ylabel('Pseudotime', fontsize=10)

    # Bottom: heatmap
    im = ax_heat.imshow(heatmap_z.values, aspect='auto', cmap='RdBu_r',
                         vmin=-3, vmax=3, interpolation='nearest')

    ax_heat.set_yticks(range(len(features)))
    ax_heat.set_yticklabels(features, fontsize=max(6, min(9, 200 // len(features))))
    ax_heat.set_xticks([])
    ax_heat.set_xlabel('Samples (ordered by pseudotime)', fontsize=11)
    ax_heat.set_title(f'TimeAx Seed Feature Dynamics ({len(features)} genes)',
                       fontsize=13, fontweight='bold', pad=5)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax_heat, fraction=0.02, pad=0.02)
    cbar.set_label('Z-score', fontsize=10)

    plt.tight_layout()
    _save_plot(fig, output_file, width=12, height=max(8, len(features) * 0.25 + 2))
    plt.close(fig)


if __name__ == '__main__':
    """Test plot generation with synthetic data."""

    from load_and_preprocess import load_example_data, load_and_preprocess_data
    from run_trajectory_analysis import run_trajectory_analysis
    import tempfile

    print("Loading and processing example data...")
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

    print("\nRunning trajectory analysis...")
    results = run_trajectory_analysis(
        data_processed, metadata_out, n_iterations=50, n_seeds=25
    )

    print("\nGenerating plots...")
    generate_all_plots(data_processed, metadata_out, results, output_dir='test_plots')

    print("\nCheck test_plots/ directory for generated visualizations")

    # Cleanup
    os.remove(data_file)
    os.remove(metadata_file)

