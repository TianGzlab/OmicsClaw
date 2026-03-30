"""
Visualization functions for patient disease trajectories.

This module provides plotting functions using plotnine (Grammar of Graphics)
with publication-quality aesthetics.
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Literal
from plotnine import *
from plotnine_prism import theme_prism
from sklearn.decomposition import PCA
from umap import UMAP


def plot_trajectories(
    data: pd.DataFrame,
    pseudotime: np.ndarray,
    metadata: pd.DataFrame,
    method: Literal['pca', 'umap', 'tsne'] = 'pca',
    color_by: str = 'pseudotime',
    size_by: Optional[str] = None,
    facet_by: Optional[str] = None,
    add_trajectories: bool = False,
    output_file: str = 'patient_trajectories.svg',
    width: float = 8,
    height: float = 6
):
    """
    Visualize patient trajectories using dimensionality reduction.

    Parameters
    ----------
    data : pd.DataFrame
        Feature matrix (features × samples)
    pseudotime : np.ndarray
        Pseudotime values for each sample
    metadata : pd.DataFrame
        Sample metadata
    method : str
        Dimensionality reduction: 'pca', 'umap', or 'tsne'
    color_by : str
        Column to color points by (default: 'pseudotime')
    size_by : str, optional
        Column to size points by
    facet_by : str, optional
        Column to facet plots by (e.g., 'patient_id')
    add_trajectories : bool
        Draw arrows showing temporal progression
    output_file : str
        Output filename
    width : float
        Plot width in inches
    height : float
        Plot height in inches

    Examples
    --------
    >>> plot_trajectories(
    ...     data, pseudotime, metadata,
    ...     method='pca',
    ...     color_by='pseudotime',
    ...     output_file='trajectories_pca.svg'
    ... )
    """

    print(f"Creating trajectory visualization using {method.upper()}...")

    # Dimensionality reduction
    if method == 'pca':
        reducer = PCA(n_components=2, random_state=42)
        embedding = reducer.fit_transform(data.T)
        var_explained = reducer.explained_variance_ratio_
        xlabel = f'PC1 ({var_explained[0]*100:.1f}%)'
        ylabel = f'PC2 ({var_explained[1]*100:.1f}%)'

    elif method == 'umap':
        reducer = UMAP(n_components=2, random_state=42)
        embedding = reducer.fit_transform(data.T)
        xlabel = 'UMAP1'
        ylabel = 'UMAP2'

    elif method == 'tsne':
        from sklearn.manifold import TSNE
        reducer = TSNE(n_components=2, random_state=42)
        embedding = reducer.fit_transform(data.T)
        xlabel = 't-SNE1'
        ylabel = 't-SNE2'

    else:
        raise ValueError(f"Unknown method: {method}")

    # Create plot dataframe
    plot_df = pd.DataFrame({
        'x': embedding[:, 0],
        'y': embedding[:, 1],
        'sample_id': metadata['sample_id'].values,
        'patient_id': metadata['patient_id'].values,
        'timepoint': metadata['timepoint'].values,
        'pseudotime': pseudotime
    })

    # Add optional columns
    if color_by in metadata.columns:
        plot_df[color_by] = metadata[color_by].values

    if size_by and size_by in metadata.columns:
        plot_df[size_by] = metadata[size_by].values

    # Base plot
    p = (ggplot(plot_df, aes(x='x', y='y'))
         + theme_prism()
         + labs(x=xlabel, y=ylabel, title='Patient Trajectories'))

    # Add points
    if size_by:
        p = p + geom_point(aes(color=color_by, size=size_by), alpha=0.7)
    else:
        p = p + geom_point(aes(color=color_by), size=3, alpha=0.7)

    # Color scale
    if color_by == 'pseudotime':
        p = p + scale_color_gradient(low='#440154', high='#FDE724')  # viridis

    # Add trajectory lines
    if add_trajectories:
        # Sort by patient and time
        plot_df_sorted = plot_df.sort_values(['patient_id', 'timepoint'])

        p = p + geom_path(
            aes(group='patient_id'),
            data=plot_df_sorted,
            arrow=arrow(type='closed', length=0.1),
            alpha=0.3,
            color='gray'
        )

    # Faceting
    if facet_by:
        p = p + facet_wrap(f'~{facet_by}')

    # Save
    p.save(output_file, dpi=300, width=width, height=height)
    print(f"  Saved: {output_file}")

    return p


def plot_pseudotime_distribution(
    pseudotime: np.ndarray,
    metadata: pd.DataFrame,
    group_by: Optional[str] = None,
    output_file: str = 'pseudotime_distribution.svg'
):
    """
    Plot distribution of pseudotime values.

    Parameters
    ----------
    pseudotime : np.ndarray
        Pseudotime values
    metadata : pd.DataFrame
        Sample metadata
    group_by : str, optional
        Column to group by (e.g., 'outcome', 'treatment')
    output_file : str
        Output filename
    """

    print("Creating pseudotime distribution plot...")

    plot_df = pd.DataFrame({
        'pseudotime': pseudotime,
        'sample_id': metadata['sample_id'].values
    })

    if group_by and group_by in metadata.columns:
        plot_df[group_by] = metadata[group_by].values

    # Histogram/density plot
    if group_by:
        p = (ggplot(plot_df, aes(x='pseudotime', fill=group_by))
             + geom_density(alpha=0.5)
             + theme_prism()
             + labs(x='Disease Pseudotime', y='Density',
                    title='Pseudotime Distribution'))
    else:
        p = (ggplot(plot_df, aes(x='pseudotime'))
             + geom_histogram(bins=30, fill='steelblue', alpha=0.7)
             + theme_prism()
             + labs(x='Disease Pseudotime', y='Count',
                    title='Pseudotime Distribution'))

    p.save(output_file, dpi=300, width=6, height=4)
    print(f"  Saved: {output_file}")

    return p


def plot_pseudotime_vs_time(
    pseudotime: np.ndarray,
    metadata: pd.DataFrame,
    output_file: str = 'pseudotime_vs_time.svg'
):
    """
    Plot pseudotime vs. real time to show relationship.

    Parameters
    ----------
    pseudotime : np.ndarray
        Pseudotime values
    metadata : pd.DataFrame
        Sample metadata with 'timepoint' column
    output_file : str
        Output filename
    """

    print("Creating pseudotime vs. real time plot...")

    plot_df = pd.DataFrame({
        'pseudotime': pseudotime,
        'timepoint': metadata['timepoint'].values,
        'patient_id': metadata['patient_id'].values
    })

    # Scatter + lines per patient
    p = (ggplot(plot_df, aes(x='timepoint', y='pseudotime'))
         + geom_point(aes(color='patient_id'), size=2, alpha=0.6)
         + geom_line(aes(group='patient_id', color='patient_id'), alpha=0.3)
         + theme_prism()
         + labs(x='Real Time', y='Disease Pseudotime',
                title='Pseudotime vs. Real Time')
         + theme(legend_position='none'))  # Too many patients for legend

    p.save(output_file, dpi=300, width=7, height=5)
    print(f"  Saved: {output_file}")

    return p

