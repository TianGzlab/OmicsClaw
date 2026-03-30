"""
============================================================================
QUALITY CONTROL METRICS CALCULATION
============================================================================

This script calculates QC metrics for filtering low-quality cells.

Functions:
  - calculate_qc_metrics(): Add QC metrics to AnnData object
  - get_species_mito_pattern(): Get mitochondrial gene pattern for species
  - get_species_ribo_pattern(): Get ribosomal gene pattern for species
  - get_tissue_qc_thresholds(): Get recommended QC thresholds by tissue

Usage:
  from qc_metrics import calculate_qc_metrics
  adata = calculate_qc_metrics(adata, species="human")
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def get_species_mito_pattern(species: str) -> str:
    """
    Get mitochondrial gene pattern for species.

    Parameters
    ----------
    species : str
        Species name ("human" or "mouse")

    Returns
    -------
    str
        Regular expression pattern for mitochondrial genes
    """
    patterns = {
        'human': 'MT-',
        'mouse': 'mt-'
    }

    species = species.lower()
    if species not in patterns:
        raise ValueError("Species must be 'human' or 'mouse'")

    return patterns[species]


def get_species_ribo_pattern(species: str) -> str:
    """
    Get ribosomal gene pattern for species.

    Parameters
    ----------
    species : str
        Species name ("human" or "mouse")

    Returns
    -------
    str
        Regular expression pattern for ribosomal genes
    """
    patterns = {
        'human': '^RP[SL]',
        'mouse': '^Rp[sl]'
    }

    species = species.lower()
    if species not in patterns:
        raise ValueError("Species must be 'human' or 'mouse'")

    return patterns[species]


def calculate_qc_metrics(
    adata: 'AnnData',
    species: str = 'human',
    calculate_ribo: bool = True,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Calculate QC metrics for AnnData object.

    Adds the following metrics to adata.obs:
      - n_genes_by_counts: Number of genes detected per cell
      - total_counts: Total UMI counts per cell
      - pct_counts_mt: Percentage of mitochondrial gene expression
      - pct_counts_ribo: Percentage of ribosomal gene expression (optional)
      - log10_total_counts: Log10 of total counts
      - log10_n_genes_by_counts: Log10 of n_genes

    Parameters
    ----------
    adata : AnnData
        AnnData object
    species : str, optional
        Species name ("human" or "mouse") (default: "human")
    calculate_ribo : bool, optional
        Whether to calculate ribosomal percentage (default: True)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        Modified AnnData object if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    print(f"Calculating QC metrics for {species}")

    # Get mitochondrial gene pattern
    mito_pattern = get_species_mito_pattern(species)

    # Identify mitochondrial genes
    adata.var['mt'] = adata.var_names.str.startswith(mito_pattern)
    n_mito_genes = adata.var['mt'].sum()
    print(f"  Mitochondrial genes identified: {n_mito_genes}")

    # Calculate ribosomal genes if requested
    if calculate_ribo:
        ribo_pattern = get_species_ribo_pattern(species)
        adata.var['ribo'] = adata.var_names.str.match(ribo_pattern)
        n_ribo_genes = adata.var['ribo'].sum()
        print(f"  Ribosomal genes identified: {n_ribo_genes}")

        qc_vars = ['mt', 'ribo']
    else:
        qc_vars = ['mt']

    # Calculate QC metrics
    sc.pp.calculate_qc_metrics(
        adata,
        qc_vars=qc_vars,
        percent_top=None,
        log1p=False,
        inplace=True
    )

    # Add log-transformed metrics
    adata.obs['log10_total_counts'] = np.log10(adata.obs['total_counts'] + 1)
    adata.obs['log10_n_genes_by_counts'] = np.log10(adata.obs['n_genes_by_counts'] + 1)

    # Print summary statistics
    print("\nQC Metrics Summary:")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")
    print(f"  Median genes per cell: {adata.obs['n_genes_by_counts'].median():.0f}")
    print(f"  Median UMIs per cell: {adata.obs['total_counts'].median():.0f}")
    print(f"  Median pct_counts_mt: {adata.obs['pct_counts_mt'].median():.2f}%")

    if calculate_ribo:
        print(f"  Median pct_counts_ribo: {adata.obs['pct_counts_ribo'].median():.2f}%")

    # Always return adata for convenience
    return adata


def get_tissue_qc_thresholds(tissue: str) -> Dict[str, any]:
    """
    Get recommended QC thresholds by tissue type.

    Parameters
    ----------
    tissue : str
        Tissue type (e.g., "pbmc", "brain", "tumor")

    Returns
    -------
    dict
        Dictionary with recommended thresholds
    """
    thresholds = {
        'pbmc': {
            'min_genes': 200,
            'max_genes': 2500,
            'max_mt': 5,
            'description': 'Peripheral blood mononuclear cells'
        },
        'brain': {
            'min_genes': 200,
            'max_genes': 6000,
            'max_mt': 10,
            'description': 'Brain tissue (neurons have many genes)'
        },
        'tumor': {
            'min_genes': 200,
            'max_genes': 5000,
            'max_mt': 20,
            'description': 'Tumor samples (higher mt% tolerated)'
        },
        'kidney': {
            'min_genes': 200,
            'max_genes': 4000,
            'max_mt': 15,
            'description': 'Kidney tissue'
        },
        'liver': {
            'min_genes': 200,
            'max_genes': 4000,
            'max_mt': 15,
            'description': 'Liver tissue'
        },
        'heart': {
            'min_genes': 200,
            'max_genes': 4000,
            'max_mt': 15,
            'description': 'Heart tissue (cardiomyocytes have high mt%)'
        },
        'default': {
            'min_genes': 200,
            'max_genes': 4000,
            'max_mt': 10,
            'description': 'General tissue (adjust based on your data)'
        }
    }

    tissue = tissue.lower()
    if tissue not in thresholds:
        print(f"Tissue '{tissue}' not recognized. Using default thresholds.")
        print(f"Available tissues: {', '.join(thresholds.keys())}")
        tissue = 'default'

    result = thresholds[tissue]
    print(f"Using thresholds for: {result['description']}")
    print(f"  min_genes: {result['min_genes']}")
    print(f"  max_genes: {result['max_genes']}")
    print(f"  max_mt: {result['max_mt']}%")

    return result


def batch_mad_outlier_detection(
    adata: 'AnnData',
    batch_key: str = 'batch',
    metrics: Optional[List[str]] = None,
    nmads: float = 5,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Batch-aware MAD (Median Absolute Deviation) outlier detection.

    This approach adapts to batch-specific distributions instead of using
    fixed thresholds, preventing bias against metabolically active cell types.

    Parameters
    ----------
    adata : AnnData
        AnnData object with QC metrics
    batch_key : str, optional
        Column in adata.obs containing batch labels (default: 'batch')
    metrics : list of str, optional
        QC metrics to check for outliers
        Default: ['log10_total_counts', 'log10_n_genes_by_counts', 'pct_counts_mt']
    nmads : float, optional
        Number of MADs from median to define outliers (default: 5)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        Modified AnnData object if inplace=False, else None

    Notes
    -----
    Creates/updates adata.obs['outlier'] column with boolean flags.
    Also creates per-metric outlier columns: 'outlier_{metric}'
    """
    if not inplace:
        adata = adata.copy()

    if metrics is None:
        metrics = ['log10_total_counts', 'log10_n_genes_by_counts', 'pct_counts_mt']

    # Check if batch column exists
    if batch_key not in adata.obs.columns:
        print(f"Warning: '{batch_key}' not found in adata.obs. Treating as single batch.")
        adata.obs[batch_key] = 'batch_1'

    # Ensure log-transformed metrics exist
    if 'log10_total_counts' not in adata.obs.columns:
        adata.obs['log10_total_counts'] = np.log10(adata.obs['total_counts'] + 1)
    if 'log10_n_genes_by_counts' not in adata.obs.columns:
        adata.obs['log10_n_genes_by_counts'] = np.log10(adata.obs['n_genes_by_counts'] + 1)

    print(f"Performing batch-aware MAD outlier detection (nmads={nmads})...")

    # Initialize outlier column
    adata.obs['outlier'] = False

    # Track outliers per metric
    for metric in metrics:
        if metric not in adata.obs.columns:
            print(f"Warning: Metric '{metric}' not found in adata.obs. Skipping.")
            continue

        adata.obs[f'outlier_{metric}'] = False

        # Process each batch separately
        for batch in adata.obs[batch_key].unique():
            batch_mask = adata.obs[batch_key] == batch
            batch_values = adata.obs.loc[batch_mask, metric]

            # Calculate MAD
            median = np.median(batch_values)
            mad = np.median(np.abs(batch_values - median))

            # Avoid division by zero
            if mad == 0:
                print(f"  Warning: MAD=0 for {metric} in batch {batch}. Skipping.")
                continue

            # Define outlier thresholds
            lower = median - nmads * mad
            upper = median + nmads * mad

            # Identify outliers
            batch_outliers = (batch_values < lower) | (batch_values > upper)

            # Update outlier flags
            adata.obs.loc[batch_mask, f'outlier_{metric}'] = batch_outliers
            adata.obs.loc[batch_mask, 'outlier'] |= batch_outliers

            n_outliers = batch_outliers.sum()
            if n_outliers > 0:
                print(f"  {metric} [{batch}]: {n_outliers} outliers "
                      f"(thresholds: {lower:.2f} - {upper:.2f})")

    # Summary
    n_total_outliers = adata.obs['outlier'].sum()
    pct_outliers = 100 * n_total_outliers / adata.n_obs

    print(f"\nTotal outliers: {n_total_outliers} ({pct_outliers:.1f}%)")
    print(f"Cells passing QC: {adata.n_obs - n_total_outliers} "
          f"({100 - pct_outliers:.1f}%)")

    # Always return adata for convenience
    return adata


def mark_outliers_fixed(
    adata: 'AnnData',
    tissue: str = 'pbmc',
    min_genes: Optional[int] = None,
    max_genes: Optional[int] = None,
    max_mt: Optional[float] = None,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Mark outliers using fixed tissue-specific thresholds.

    Use this for single-batch data or when tissue-specific guidelines exist.
    For multi-batch data, prefer batch_mad_outlier_detection().

    Parameters
    ----------
    adata : AnnData
        AnnData object with QC metrics
    tissue : str, optional
        Tissue type (default: 'pbmc')
    min_genes : int, optional
        Minimum genes per cell (overrides tissue default)
    max_genes : int, optional
        Maximum genes per cell (overrides tissue default)
    max_mt : float, optional
        Maximum mitochondrial percentage (overrides tissue default)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        Modified AnnData object if inplace=False, else None
    """
    if not inplace:
        adata = adata.copy()

    # Get tissue-specific thresholds
    thresholds = get_tissue_qc_thresholds(tissue)

    # Override with user-specified values
    min_genes = min_genes if min_genes is not None else thresholds['min_genes']
    max_genes = max_genes if max_genes is not None else thresholds['max_genes']
    max_mt = max_mt if max_mt is not None else thresholds['max_mt']

    print(f"\nApplying fixed QC thresholds:")
    print(f"  min_genes: {min_genes}")
    print(f"  max_genes: {max_genes}")
    print(f"  max_mt: {max_mt}%")

    # Mark outliers
    adata.obs['outlier'] = (
        (adata.obs['n_genes_by_counts'] < min_genes) |
        (adata.obs['n_genes_by_counts'] > max_genes) |
        (adata.obs['pct_counts_mt'] > max_mt)
    )

    # Track outliers by criterion
    adata.obs['outlier_low_genes'] = adata.obs['n_genes_by_counts'] < min_genes
    adata.obs['outlier_high_genes'] = adata.obs['n_genes_by_counts'] > max_genes
    adata.obs['outlier_high_mt'] = adata.obs['pct_counts_mt'] > max_mt

    # Summary
    n_total_outliers = adata.obs['outlier'].sum()
    pct_outliers = 100 * n_total_outliers / adata.n_obs

    print(f"\nOutlier summary:")
    print(f"  Low genes: {adata.obs['outlier_low_genes'].sum()}")
    print(f"  High genes: {adata.obs['outlier_high_genes'].sum()}")
    print(f"  High MT%: {adata.obs['outlier_high_mt'].sum()}")
    print(f"  Total outliers: {n_total_outliers} ({pct_outliers:.1f}%)")
    print(f"  Cells passing QC: {adata.n_obs - n_total_outliers} "
          f"({100 - pct_outliers:.1f}%)")

    # Always return adata for convenience
    return adata


def calculate_doublet_scores(
    adata: 'AnnData',
    expected_doublet_rate: float = 0.06,
    random_state: int = 0
) -> 'AnnData':
    """
    Calculate doublet scores using scrublet.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    expected_doublet_rate : float, optional
        Expected doublet rate (default: 0.06)
    random_state : int, optional
        Random seed (default: 0)

    Returns
    -------
    AnnData
        AnnData object with doublet scores in .obs
    """
    try:
        import scrublet as scr
    except ImportError:
        raise ImportError("scrublet is required for doublet detection. Install with: pip install scrublet")

    print("Calculating doublet scores with scrublet...")

    # Run scrublet
    scrub = scr.Scrublet(
        adata.X,
        expected_doublet_rate=expected_doublet_rate,
        random_state=random_state
    )

    doublet_scores, predicted_doublets = scrub.scrub_doublets(
        min_counts=2,
        min_cells=3,
        min_gene_variability_pctl=85,
        n_prin_comps=30
    )

    # Add to adata
    adata.obs['doublet_score'] = doublet_scores
    adata.obs['predicted_doublet'] = predicted_doublets

    n_doublets = predicted_doublets.sum()
    pct_doublets = 100 * n_doublets / len(predicted_doublets)

    print(f"  Predicted doublets: {n_doublets} ({pct_doublets:.1f}%)")

    return adata

