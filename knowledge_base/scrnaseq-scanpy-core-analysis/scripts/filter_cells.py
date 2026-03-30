"""
============================================================================
CELL FILTERING
============================================================================

This script filters cells based on QC metrics and doublet detection.

Functions:
  - run_scrublet_detection(): Detect doublets with Scrublet (per batch)
  - filter_by_mad_outliers(): Filter based on MAD outlier detection
  - filter_cells_by_qc(): Filter cells by custom QC thresholds
  - filter_cells_by_tissue(): Filter using tissue-specific thresholds
  - filter_doublets(): Remove predicted doublets
  - combine_filters_and_apply(): Combine multiple filtering criteria

Usage:
  from filter_cells import run_scrublet_detection, filter_by_mad_outliers
  adata = run_scrublet_detection(adata, batch_key="batch")
  adata_filtered = filter_by_mad_outliers(adata, remove_doublets=True)
"""

from typing import Optional, Union

import numpy as np
import pandas as pd


def filter_cells_by_qc(
    adata: 'AnnData',
    min_genes: int = 200,
    max_genes: Optional[int] = None,
    min_counts: Optional[int] = None,
    max_counts: Optional[int] = None,
    max_mt_percent: Optional[float] = None,
    inplace: bool = False
) -> 'AnnData':
    """
    Filter cells based on QC metrics.

    Parameters
    ----------
    adata : AnnData
        AnnData object with QC metrics
    min_genes : int, optional
        Minimum number of genes per cell (default: 200)
    max_genes : int, optional
        Maximum number of genes per cell (default: None)
    min_counts : int, optional
        Minimum total counts per cell (default: None)
    max_counts : int, optional
        Maximum total counts per cell (default: None)
    max_mt_percent : float, optional
        Maximum mitochondrial percentage (default: None)
    inplace : bool, optional
        Modify AnnData in place (default: False)

    Returns
    -------
    AnnData
        Filtered AnnData object
    """
    n_cells_before = adata.n_obs

    print("Filtering cells by QC metrics...")
    print(f"  Starting with {n_cells_before} cells")

    # Create filter mask
    keep_cells = np.ones(adata.n_obs, dtype=bool)

    # Filter by n_genes
    if min_genes is not None:
        mask = adata.obs['n_genes_by_counts'] >= min_genes
        keep_cells &= mask
        n_removed = (~mask).sum()
        print(f"  Removed {n_removed} cells with < {min_genes} genes")

    if max_genes is not None:
        mask = adata.obs['n_genes_by_counts'] <= max_genes
        keep_cells &= mask
        n_removed = (~mask).sum()
        print(f"  Removed {n_removed} cells with > {max_genes} genes")

    # Filter by total counts
    if min_counts is not None:
        mask = adata.obs['total_counts'] >= min_counts
        keep_cells &= mask
        n_removed = (~mask).sum()
        print(f"  Removed {n_removed} cells with < {min_counts} counts")

    if max_counts is not None:
        mask = adata.obs['total_counts'] <= max_counts
        keep_cells &= mask
        n_removed = (~mask).sum()
        print(f"  Removed {n_removed} cells with > {max_counts} counts")

    # Filter by mitochondrial percentage
    if max_mt_percent is not None:
        mask = adata.obs['pct_counts_mt'] <= max_mt_percent
        keep_cells &= mask
        n_removed = (~mask).sum()
        print(f"  Removed {n_removed} cells with > {max_mt_percent}% MT")

    # Apply filter
    if inplace:
        adata._inplace_subset_obs(keep_cells)
        adata_filtered = adata
    else:
        adata_filtered = adata[keep_cells, :].copy()

    n_cells_after = adata_filtered.n_obs
    retention_rate = 100 * n_cells_after / n_cells_before

    print(f"  Retained {n_cells_after} cells ({retention_rate:.1f}%)")

    return adata_filtered


def filter_cells_by_tissue(
    adata: 'AnnData',
    tissue: str,
    inplace: bool = False
) -> 'AnnData':
    """
    Filter cells using tissue-specific QC thresholds.

    Parameters
    ----------
    adata : AnnData
        AnnData object with QC metrics
    tissue : str
        Tissue type (e.g., "pbmc", "brain", "tumor")
    inplace : bool, optional
        Modify AnnData in place (default: False)

    Returns
    -------
    AnnData
        Filtered AnnData object
    """
    from qc_metrics import get_tissue_qc_thresholds

    # Get thresholds
    thresholds = get_tissue_qc_thresholds(tissue)

    # Filter cells
    adata_filtered = filter_cells_by_qc(
        adata,
        min_genes=thresholds['min_genes'],
        max_genes=thresholds['max_genes'],
        max_mt_percent=thresholds['max_mt'],
        inplace=inplace
    )

    return adata_filtered


def filter_doublets(
    adata: 'AnnData',
    doublet_score_threshold: Optional[float] = None,
    use_predicted: bool = True,
    inplace: bool = False
) -> 'AnnData':
    """
    Remove predicted doublets.

    Parameters
    ----------
    adata : AnnData
        AnnData object with doublet scores
    doublet_score_threshold : float, optional
        Custom doublet score threshold (default: use predicted_doublet)
    use_predicted : bool, optional
        Use predicted_doublet column (default: True)
    inplace : bool, optional
        Modify AnnData in place (default: False)

    Returns
    -------
    AnnData
        Filtered AnnData object
    """
    n_cells_before = adata.n_obs

    print("Filtering doublets...")
    print(f"  Starting with {n_cells_before} cells")

    # Determine which cells to keep
    if doublet_score_threshold is not None:
        if 'doublet_score' not in adata.obs.columns:
            raise ValueError("doublet_score not found. Run calculate_doublet_scores first.")
        keep_cells = adata.obs['doublet_score'] < doublet_score_threshold
    elif use_predicted and 'predicted_doublet' in adata.obs.columns:
        keep_cells = ~adata.obs['predicted_doublet']
    else:
        raise ValueError("Either doublet_score_threshold must be provided or predicted_doublet must exist")

    n_removed = (~keep_cells).sum()
    print(f"  Removed {n_removed} doublets")

    # Apply filter
    if inplace:
        adata._inplace_subset_obs(keep_cells)
        adata_filtered = adata
    else:
        adata_filtered = adata[keep_cells, :].copy()

    n_cells_after = adata_filtered.n_obs
    retention_rate = 100 * n_cells_after / n_cells_before

    print(f"  Retained {n_cells_after} cells ({retention_rate:.1f}%)")

    return adata_filtered


def _estimate_doublet_rate(n_cells: int) -> float:
    """
    Estimate expected doublet rate based on cell count (10X Chromium).

    On 10X Genomics platforms, the doublet rate scales approximately linearly
    with the number of cells loaded: ~0.8% per 1,000 cells.

    Parameters
    ----------
    n_cells : int
        Number of cells in the sample/batch

    Returns
    -------
    float
        Estimated doublet rate (e.g., 0.04 for 5,000 cells)
    """
    rate = 0.008 * (n_cells / 1000)
    return max(0.01, min(rate, 0.15))  # Clamp to 1-15%


def run_scrublet_detection(
    adata: 'AnnData',
    batch_key: Optional[str] = None,
    expected_doublet_rate: Optional[float] = None,
    auto_rate: bool = True,
    random_state: int = 0,
    min_counts: int = 2,
    min_cells: int = 3,
    n_prin_comps: int = 30
) -> 'AnnData':
    """
    Run Scrublet doublet detection, optionally per batch.

    Scrublet simulates doublets and uses a k-NN classifier to predict
    which cells are likely to be doublets.

    Parameters
    ----------
    adata : AnnData
        AnnData object (raw or normalized counts)
    batch_key : str, optional
        Column in adata.obs for batch information
        If provided, runs Scrublet separately per batch
    expected_doublet_rate : float, optional
        Expected doublet rate. If None and auto_rate=True, estimates from
        cell count (~0.8% per 1,000 cells for 10X Chromium).
        If None and auto_rate=False, defaults to 0.06.
    auto_rate : bool, optional
        Automatically estimate doublet rate per batch based on cell count
        (default: True). Ignored if expected_doublet_rate is explicitly set.
    random_state : int, optional
        Random seed (default: 0)
    min_counts : int, optional
        Minimum counts for gene filtering (default: 2)
    min_cells : int, optional
        Minimum cells for gene filtering (default: 3)
    n_prin_comps : int, optional
        Number of principal components (default: 30)

    Returns
    -------
    AnnData
        AnnData object with doublet scores and predictions in .obs:
        - doublet_score: Continuous doublet score
        - predicted_doublet: Boolean doublet prediction
    """
    try:
        import scrublet as scr
    except ImportError:
        raise ImportError("scrublet is required. Install with: pip install scrublet")

    print("Running Scrublet doublet detection...")

    # Initialize doublet scores
    doublet_scores = np.zeros(adata.n_obs)
    predicted_doublets = np.zeros(adata.n_obs, dtype=bool)

    # Track per-batch stats for validation
    batch_stats = []

    if batch_key is not None and batch_key in adata.obs.columns:
        # Run per batch
        print(f"  Running separately for each batch ({batch_key})")

        for batch in adata.obs[batch_key].unique():
            batch_mask = adata.obs[batch_key] == batch
            batch_adata = adata[batch_mask, :]
            n_batch_cells = batch_adata.n_obs

            # Determine expected rate for this batch
            if expected_doublet_rate is not None:
                batch_rate = expected_doublet_rate
            elif auto_rate:
                batch_rate = _estimate_doublet_rate(n_batch_cells)
            else:
                batch_rate = 0.06

            print(f"  Batch: {batch} ({n_batch_cells} cells, "
                  f"expected rate: {batch_rate:.1%})")

            # Run scrublet on batch
            scrub = scr.Scrublet(
                batch_adata.X,
                expected_doublet_rate=batch_rate,
                random_state=random_state
            )

            batch_scores, batch_doublets = scrub.scrub_doublets(
                min_counts=min_counts,
                min_cells=min_cells,
                min_gene_variability_pctl=85,
                n_prin_comps=n_prin_comps,
                verbose=False
            )

            # Store results
            doublet_scores[batch_mask] = batch_scores
            predicted_doublets[batch_mask] = batch_doublets

            n_doublets = batch_doublets.sum()
            pct_doublets = 100 * n_doublets / len(batch_doublets)
            print(f"    Predicted doublets: {n_doublets} ({pct_doublets:.1f}%)")

            batch_stats.append({
                'batch': batch,
                'n_cells': n_batch_cells,
                'expected_rate': batch_rate,
                'detected_rate': n_doublets / len(batch_doublets),
                'n_doublets': n_doublets
            })

    else:
        # Run on entire dataset
        n_total = adata.n_obs
        if expected_doublet_rate is not None:
            rate = expected_doublet_rate
        elif auto_rate:
            rate = _estimate_doublet_rate(n_total)
        else:
            rate = 0.06

        print(f"  Running on entire dataset ({n_total} cells, "
              f"expected rate: {rate:.1%})")

        scrub = scr.Scrublet(
            adata.X,
            expected_doublet_rate=rate,
            random_state=random_state
        )

        doublet_scores, predicted_doublets = scrub.scrub_doublets(
            min_counts=min_counts,
            min_cells=min_cells,
            min_gene_variability_pctl=85,
            n_prin_comps=n_prin_comps,
            verbose=False
        )

        n_doublets = predicted_doublets.sum()
        pct_doublets = 100 * n_doublets / n_total
        print(f"  Predicted doublets: {n_doublets} ({pct_doublets:.1f}%)")

        batch_stats.append({
            'batch': 'all',
            'n_cells': n_total,
            'expected_rate': rate,
            'detected_rate': n_doublets / n_total,
            'n_doublets': n_doublets
        })

    # Add to adata
    adata.obs['doublet_score'] = doublet_scores
    adata.obs['predicted_doublet'] = predicted_doublets

    # Validation: warn if detected rate is very different from expected
    total_detected = predicted_doublets.sum()
    total_expected_pct = 100 * sum(s['expected_rate'] * s['n_cells']
                                    for s in batch_stats) / adata.n_obs
    total_detected_pct = 100 * total_detected / adata.n_obs

    if total_detected_pct < total_expected_pct * 0.25:
        print(f"\n  [WARNING] Detected doublet rate ({total_detected_pct:.1f}%) is much "
              f"lower than expected ({total_expected_pct:.1f}%).")
        print(f"     This may indicate:")
        print(f"     - Scrublet's automatic threshold is too strict")
        print(f"     - Data was pre-filtered for doublets upstream")
        print(f"     - Consider lowering doublet_score_threshold in filter_by_mad_outliers()")
        print(f"     - Or inspect doublet score distribution: adata.obs['doublet_score'].hist()")
    elif total_detected_pct > total_expected_pct * 3:
        print(f"\n  [WARNING] Detected doublet rate ({total_detected_pct:.1f}%) is much "
              f"higher than expected ({total_expected_pct:.1f}%).")
        print(f"     This may indicate poor-quality data or over-sensitive detection.")

    # Store doublet detection metadata
    adata.uns['scrublet_detection'] = {
        'batch_stats': batch_stats,
        'total_detected': int(total_detected),
        'total_detected_pct': float(total_detected_pct),
        'total_expected_pct': float(total_expected_pct),
        'auto_rate': auto_rate,
    }

    return adata


def filter_by_mad_outliers(
    adata: 'AnnData',
    remove_doublets: bool = True,
    doublet_score_threshold: float = 0.25,
    inplace: bool = False
) -> 'AnnData':
    """
    Filter cells based on MAD outlier detection and optionally doublets.

    Requires prior run of batch_mad_outlier_detection() from qc_metrics.

    Parameters
    ----------
    adata : AnnData
        AnnData object with 'outlier' column in .obs
    remove_doublets : bool, optional
        Also remove predicted doublets (default: True)
    doublet_score_threshold : float, optional
        Doublet score threshold (default: 0.25)
        Only used if remove_doublets=True
    inplace : bool, optional
        Modify AnnData in place (default: False)

    Returns
    -------
    AnnData
        Filtered AnnData object
    """
    if 'outlier' not in adata.obs.columns:
        raise ValueError("'outlier' column not found. Run batch_mad_outlier_detection() first.")

    n_cells_before = adata.n_obs

    print("Filtering cells based on MAD outlier detection...")

    # Start with outlier filtering
    keep_cells = ~adata.obs['outlier']
    n_outliers = adata.obs['outlier'].sum()
    print(f"  QC outliers: {n_outliers}")

    # Optionally filter doublets
    if remove_doublets:
        if 'doublet_score' in adata.obs.columns:
            doublet_mask = adata.obs['doublet_score'] >= doublet_score_threshold
            keep_cells &= ~doublet_mask
            n_doublets = doublet_mask.sum()
            print(f"  Doublets (score≥{doublet_score_threshold}): {n_doublets}")
        elif 'predicted_doublet' in adata.obs.columns:
            keep_cells &= ~adata.obs['predicted_doublet']
            n_doublets = adata.obs['predicted_doublet'].sum()
            print(f"  Predicted doublets: {n_doublets}")
        else:
            print("  Warning: No doublet information found. Run run_scrublet_detection() first.")

    # Apply filter
    if inplace:
        adata._inplace_subset_obs(keep_cells)
        adata_filtered = adata
    else:
        adata_filtered = adata[keep_cells, :].copy()

    n_cells_after = adata_filtered.n_obs
    n_removed = n_cells_before - n_cells_after
    retention_rate = 100 * n_cells_after / n_cells_before

    print(f"\nTotal removed: {n_removed} cells")
    print(f"Retained: {n_cells_after} cells ({retention_rate:.1f}%)")

    return adata_filtered


def combine_filters_and_apply(
    adata: 'AnnData',
    filter_outliers: bool = True,
    filter_doublets: bool = True,
    doublet_score_threshold: float = 0.25,
    inplace: bool = False
) -> 'AnnData':
    """
    Combine multiple filtering criteria and apply.

    Parameters
    ----------
    adata : AnnData
        AnnData object with QC metrics and doublet scores
    filter_outliers : bool, optional
        Filter MAD outliers (default: True)
    filter_doublets : bool, optional
        Filter doublets (default: True)
    doublet_score_threshold : float, optional
        Doublet score threshold (default: 0.25)
    inplace : bool, optional
        Modify AnnData in place (default: False)

    Returns
    -------
    AnnData
        Filtered AnnData object
    """
    n_cells_before = adata.n_obs
    keep_cells = np.ones(adata.n_obs, dtype=bool)

    print("Applying combined filters...")
    print(f"  Starting with {n_cells_before} cells")

    # Filter outliers
    if filter_outliers:
        if 'outlier' in adata.obs.columns:
            outlier_mask = adata.obs['outlier']
            keep_cells &= ~outlier_mask
            n_outliers = outlier_mask.sum()
            print(f"  Removing QC outliers: {n_outliers}")
        else:
            print("  Warning: 'outlier' column not found. Skipping outlier filtering.")

    # Filter doublets
    if filter_doublets:
        if 'doublet_score' in adata.obs.columns:
            doublet_mask = adata.obs['doublet_score'] >= doublet_score_threshold
            keep_cells &= ~doublet_mask
            n_doublets = doublet_mask.sum()
            print(f"  Removing doublets (score≥{doublet_score_threshold}): {n_doublets}")
        elif 'predicted_doublet' in adata.obs.columns:
            doublet_mask = adata.obs['predicted_doublet']
            keep_cells &= ~doublet_mask
            n_doublets = doublet_mask.sum()
            print(f"  Removing predicted doublets: {n_doublets}")
        else:
            print("  Warning: No doublet information found. Skipping doublet filtering.")

    # Apply combined filter
    if inplace:
        adata._inplace_subset_obs(keep_cells)
        adata_filtered = adata
    else:
        adata_filtered = adata[keep_cells, :].copy()

    n_cells_after = adata_filtered.n_obs
    n_removed = n_cells_before - n_cells_after
    retention_rate = 100 * n_cells_after / n_cells_before

    print(f"\nTotal removed: {n_removed} cells")
    print(f"Retained: {n_cells_after} cells ({retention_rate:.1f}%)")

    if retention_rate < 70:
        print("\nWARNING: Retention rate < 70%. Review QC thresholds.")

    return adata_filtered


def filter_genes(
    adata: 'AnnData',
    min_cells: int = 3,
    min_counts: Optional[int] = None,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Filter genes based on expression.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    min_cells : int, optional
        Minimum number of cells expressing a gene (default: 3)
    min_counts : int, optional
        Minimum total counts for a gene (default: None)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        Filtered AnnData object if inplace=False, else None
    """
    import scanpy as sc

    n_genes_before = adata.n_vars

    print("Filtering genes...")
    print(f"  Starting with {n_genes_before} genes")

    if not inplace:
        adata = adata.copy()

    # Filter genes by cells
    if min_cells is not None:
        sc.pp.filter_genes(adata, min_cells=min_cells)

    # Filter genes by counts
    if min_counts is not None:
        sc.pp.filter_genes(adata, min_counts=min_counts)

    n_genes_after = adata.n_vars
    retention_rate = 100 * n_genes_after / n_genes_before

    print(f"  Retained {n_genes_after} genes ({retention_rate:.1f}%)")

    # Always return adata for convenience
    return adata

