"""
Ambient RNA Correction for Single-Cell RNA-seq Data

This module provides functions for removing ambient RNA contamination using
CellBender or SoupX-based approaches.

For detailed guidance, see references/ambient_rna_correction.md
"""

import scanpy as sc
import numpy as np
import pandas as pd
import subprocess
import os
from pathlib import Path
from typing import Union, Optional, Tuple
import warnings


def run_cellbender(
    raw_h5: Union[str, Path],
    expected_cells: int,
    total_droplets: Optional[int] = None,
    output_dir: Union[str, Path] = "results/cellbender",
    epochs: int = 200,
    fpr: float = 0.01,
    use_cuda: bool = True,
    **kwargs
) -> sc.AnnData:
    """
    Run CellBender remove-background to correct ambient RNA.

    CellBender uses a deep generative model to estimate and remove ambient RNA
    contamination from droplet-based scRNA-seq data.

    Parameters
    ----------
    raw_h5 : str or Path
        Path to raw_feature_bc_matrix.h5 file from CellRanger
    expected_cells : int
        Expected number of real cells in the dataset
    total_droplets : int, optional
        Total droplets to include (should be 2-3x expected_cells)
        If None, automatically set to 3x expected_cells
    output_dir : str or Path
        Directory to save CellBender outputs
    epochs : int
        Number of training epochs (default: 200)
    fpr : float
        False positive rate for cell calling (default: 0.01)
    use_cuda : bool
        Use GPU acceleration if available (default: True)
    **kwargs
        Additional arguments passed to cellbender remove-background

    Returns
    -------
    adata : AnnData
        Corrected count matrix as AnnData object

    Notes
    -----
    - Requires CellBender installation: pip install cellbender
    - GPU recommended for speed (10-20x faster than CPU)
    - For high-soup tissues (brain, lung, tumor), set total_droplets = 3x expected_cells
    """
    # Set up paths
    raw_h5 = Path(raw_h5)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if total_droplets is None:
        total_droplets = expected_cells * 3

    output_h5 = output_dir / "cellbender_output.h5"

    # Build command
    cmd = [
        "cellbender", "remove-background",
        "--input", str(raw_h5),
        "--output", str(output_h5),
        "--expected-cells", str(expected_cells),
        "--total-droplets-included", str(total_droplets),
        "--epochs", str(epochs),
        "--fpr", str(fpr)
    ]

    if use_cuda:
        cmd.append("--cuda")

    # Add any additional arguments
    for key, value in kwargs.items():
        cmd.extend([f"--{key.replace('_', '-')}", str(value)])

    print(f"Running CellBender with command:")
    print(" ".join(cmd))

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("CellBender completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"CellBender failed with error:\n{e.stderr}")
        raise

    # Load corrected counts
    adata = sc.read_10x_h5(str(output_h5).replace(".h5", "_filtered.h5"))
    adata.var_names_make_unique()

    # Store metadata
    adata.uns["cellbender"] = {
        "raw_h5": str(raw_h5),
        "expected_cells": expected_cells,
        "total_droplets": total_droplets,
        "epochs": epochs,
        "fpr": fpr
    }

    return adata


def run_soupx_python(
    raw_matrix_dir: Union[str, Path],
    filtered_matrix_dir: Union[str, Path],
    clusters: Optional[np.ndarray] = None,
    output_dir: Union[str, Path] = "results/soupx"
) -> sc.AnnData:
    """
    Run SoupX-based ambient RNA correction using Python/scanpy.

    This is a simplified Python implementation of the SoupX algorithm
    for removing ambient RNA contamination.

    Parameters
    ----------
    raw_matrix_dir : str or Path
        Path to raw_feature_bc_matrix/ directory
    filtered_matrix_dir : str or Path
        Path to filtered_feature_bc_matrix/ directory
    clusters : array-like, optional
        Pre-computed cluster labels for cells
        If None, quick clustering will be performed
    output_dir : str or Path
        Directory to save outputs

    Returns
    -------
    adata : AnnData
        Corrected count matrix as AnnData object

    Notes
    -----
    This is a simplified implementation. For full SoupX functionality,
    use the R version via rpy2 or run R script directly.
    """
    # Load raw and filtered matrices
    adata_raw = sc.read_10x_mtx(raw_matrix_dir)
    adata_filtered = sc.read_10x_mtx(filtered_matrix_dir)

    # Estimate ambient profile from empty droplets
    empty_cells = adata_raw.obs_names[~adata_raw.obs_names.isin(adata_filtered.obs_names)]
    ambient_profile = adata_raw[empty_cells, :].X.sum(axis=0).A1
    ambient_profile = ambient_profile / ambient_profile.sum()

    # Quick clustering if not provided
    if clusters is None:
        sc.pp.normalize_total(adata_filtered, target_sum=1e4)
        sc.pp.log1p(adata_filtered)
        sc.pp.highly_variable_genes(adata_filtered, n_top_genes=2000)
        sc.pp.pca(adata_filtered, n_comps=30)
        sc.pp.neighbors(adata_filtered, n_neighbors=15)
        sc.tl.leiden(adata_filtered, resolution=0.8)
        clusters = adata_filtered.obs["leiden"].values

    # Estimate contamination fraction
    contamination_fraction = estimate_contamination_fraction(
        adata_filtered.X.toarray(),
        ambient_profile,
        clusters
    )

    # Correct counts
    corrected = adata_filtered.X.toarray() - contamination_fraction * ambient_profile
    corrected = np.maximum(corrected, 0)  # No negative counts

    # Create corrected AnnData
    adata_corrected = sc.AnnData(
        X=corrected,
        obs=adata_filtered.obs,
        var=adata_filtered.var
    )

    # Store metadata
    adata_corrected.uns["soupx"] = {
        "contamination_fraction": contamination_fraction,
        "ambient_profile": ambient_profile
    }

    # Save output
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    adata_corrected.write_h5ad(output_dir / "soupx_corrected.h5ad")

    return adata_corrected


def estimate_contamination_fraction(
    counts: np.ndarray,
    ambient_profile: np.ndarray,
    clusters: np.ndarray
) -> float:
    """
    Estimate global contamination fraction.

    Parameters
    ----------
    counts : array-like, shape (n_cells, n_genes)
        Raw count matrix
    ambient_profile : array-like, shape (n_genes,)
        Ambient RNA profile from empty droplets
    clusters : array-like, shape (n_cells,)
        Cluster assignments

    Returns
    -------
    rho : float
        Estimated contamination fraction (0-1)
    """
    # Use marker genes with high specificity
    # Simple heuristic: genes expressed in <10% of clusters
    n_clusters = len(np.unique(clusters))
    cluster_expression = np.zeros((n_clusters, counts.shape[1]))

    for i, cluster in enumerate(np.unique(clusters)):
        cluster_mask = clusters == cluster
        cluster_expression[i, :] = (counts[cluster_mask, :] > 0).mean(axis=0)

    # Marker genes: expressed in few clusters
    marker_mask = (cluster_expression > 0.1).sum(axis=0) <= n_clusters * 0.1

    if marker_mask.sum() < 10:
        # Fallback: use all genes
        marker_mask = np.ones(counts.shape[1], dtype=bool)
        warnings.warn("Few marker genes found, using all genes for contamination estimation")

    # Estimate contamination as correlation between observed and ambient
    observed_profile = counts.mean(axis=0)

    # Correlation-based estimation
    marker_obs = observed_profile[marker_mask]
    marker_amb = ambient_profile[marker_mask]

    # Estimate rho
    rho = np.corrcoef(marker_obs, marker_amb)[0, 1]
    rho = np.clip(rho, 0, 0.5)  # Reasonable range

    return rho


def estimate_contamination(adata: sc.AnnData) -> float:
    """
    Estimate ambient RNA contamination fraction from corrected AnnData.

    Parameters
    ----------
    adata : AnnData
        AnnData object with ambient correction metadata

    Returns
    -------
    contamination : float
        Estimated contamination fraction
    """
    if "cellbender" in adata.uns:
        # Extract from CellBender metadata if available
        # This is approximate - CellBender doesn't directly report this
        return 0.05  # Placeholder
    elif "soupx" in adata.uns:
        return adata.uns["soupx"]["contamination_fraction"]
    else:
        warnings.warn("No ambient correction metadata found")
        return 0.0


def compare_before_after(
    adata_before: sc.AnnData,
    adata_after: sc.AnnData,
    marker_genes: list,
    output_dir: Union[str, Path] = "results/ambient"
):
    """
    Compare expression before and after ambient RNA correction.

    Parameters
    ----------
    adata_before : AnnData
        Data before correction
    adata_after : AnnData
        Data after correction
    marker_genes : list
        List of marker genes to compare
    output_dir : str or Path
        Directory to save comparison plots
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_style("ticks")
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica']

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Compare total counts
    before_counts = adata_before.X.sum(axis=1).A1
    after_counts = adata_after.X.sum(axis=1).A1

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(before_counts, after_counts, alpha=0.3, s=0.5, edgecolors='none')
    ax.set_xlabel("Before Correction")
    ax.set_ylabel("After Correction")
    ax.set_title("Total Counts Before vs After Correction", fontweight='bold')
    sns.despine(ax=ax)

    fig.tight_layout()
    fig.savefig(output_dir / "counts_comparison.png", dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / "counts_comparison.svg", dpi=300, bbox_inches='tight')
    plt.close(fig)

    print(f"Mean counts before: {before_counts.mean():.1f}")
    print(f"Mean counts after: {after_counts.mean():.1f}")
    print(f"Reduction: {(1 - after_counts.mean()/before_counts.mean()) * 100:.1f}%")


# Example usage
if __name__ == "__main__":
    # Example: Run CellBender
    adata = run_cellbender(
        raw_h5="raw_feature_bc_matrix.h5",
        expected_cells=10000,
        output_dir="results/cellbender"
    )

    print(f"Loaded corrected data: {adata.shape[0]} cells, {adata.shape[1]} genes")

