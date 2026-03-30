"""
Normalization and Scaling

Normalize counts, log-transform, regress out technical covariates, and scale data.
"""

import scanpy as sc
import anndata as ad
from typing import List, Optional


def normalize_and_scale_data(
    adata: ad.AnnData,
    target_sum: float = 1e6,
    exclude_highly_expressed: bool = True,
    regress_out: Optional[List[str]] = None,
    max_value: float = 10,
    save_raw: bool = True,
    n_jobs: int = 4
) -> ad.AnnData:
    """
    Complete normalization and scaling pipeline.

    Parameters
    ----------
    adata : AnnData
        Input AnnData (filtered, raw counts)
    target_sum : float, default=1e6
        Target sum for normalization (CPM: 1e6, TPM-like: 1e4)
    exclude_highly_expressed : bool, default=True
        Exclude highly expressed genes from normalization factor computation
        (e.g., MALAT1 which can dominate total counts)
    regress_out : list of str, optional
        Variables to regress out (e.g., ['n_counts', 'percent_mito'])
        Set to None to skip regression
    max_value : float, default=10
        Maximum value after scaling (clips outliers)
    save_raw : bool, default=True
        Save log-normalized counts in adata.raw before scaling
    n_jobs : int, default=4
        Number of parallel jobs for regression

    Returns
    -------
    adata : AnnData
        Normalized and scaled AnnData
        - adata.raw: log-normalized counts (if save_raw=True)
        - adata.X: scaled, regressed data

    Example
    -------
    >>> adata = normalize_and_scale_data(
    ...     adata,
    ...     target_sum=1e6,
    ...     exclude_highly_expressed=True,
    ...     regress_out=['n_counts'],
    ...     max_value=10
    ... )
    """
    print("Normalizing and scaling data...")

    # Normalize counts
    print(f"\n1. Normalizing to {target_sum} total counts per cell...")
    sc.pp.normalize_total(
        adata,
        target_sum=target_sum,
        exclude_highly_expressed=exclude_highly_expressed
    )

    # Log-transform
    print("2. Log-transforming (log1p)...")
    sc.pp.log1p(adata)

    # Save raw
    if save_raw:
        print("3. Saving log-normalized counts in adata.raw...")
        adata.raw = adata

    # Regress out technical variables
    if regress_out is not None:
        print(f"4. Regressing out: {regress_out}...")
        sc.pp.regress_out(adata, regress_out, n_jobs=n_jobs)
    else:
        print("4. Skipping regression (regress_out=None)")

    # Scale
    print(f"5. Scaling (max_value={max_value})...")
    sc.pp.scale(adata, max_value=max_value)

    print("\nNormalization complete!")
    print("  adata.X: scaled, regressed data (for PCA, UMAP)")
    print("  adata.raw: log-normalized counts (for DE, visualization)")

    return adata


def normalize_only(
    adata: ad.AnnData,
    target_sum: float = 1e6,
    exclude_highly_expressed: bool = True,
    save_raw: bool = False
) -> ad.AnnData:
    """
    Normalization and log-transformation only (no regression or scaling).

    Parameters
    ----------
    adata : AnnData
        Input AnnData (filtered, raw counts)
    target_sum : float, default=1e6
        Target sum for normalization
    exclude_highly_expressed : bool, default=True
        Exclude highly expressed genes from normalization
    save_raw : bool, default=False
        Save raw counts before normalization

    Returns
    -------
    adata : AnnData
        Log-normalized AnnData

    Example
    -------
    >>> adata_norm = normalize_only(adata, target_sum=1e6)
    """
    if save_raw:
        adata.raw = adata.copy()

    # Normalize
    sc.pp.normalize_total(
        adata,
        target_sum=target_sum,
        exclude_highly_expressed=exclude_highly_expressed
    )

    # Log-transform
    sc.pp.log1p(adata)

    print("✓ Normalization complete")
    return adata

