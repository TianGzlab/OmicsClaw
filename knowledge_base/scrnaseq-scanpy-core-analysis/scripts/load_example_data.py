"""
============================================================================
LOAD EXAMPLE DATA FOR TESTING
============================================================================

This script loads example single-cell RNA-seq data for testing workflows.

Functions:
  - load_example_data(): Load PBMC 3k example dataset

Usage:
  from load_example_data import load_example_data
  adata = load_example_data()
"""

from typing import Optional


def load_example_data(dataset: str = "pbmc3k") -> 'AnnData':
    """
    Load example single-cell RNA-seq dataset.

    This function loads the PBMC 3k dataset (2,700 PBMCs from a healthy donor)
    from the scanpy datasets collection. Perfect for testing and learning.

    Parameters
    ----------
    dataset : str, optional
        Dataset to load (default: "pbmc3k")
        Options: "pbmc3k", "pbmc68k_reduced"

    Returns
    -------
    AnnData
        Example dataset with raw counts

    Examples
    --------
    >>> adata = load_example_data()
    >>> print(f"Loaded {adata.n_obs} cells and {adata.n_vars} genes")
    """
    import scanpy as sc

    print(f"Loading {dataset} example dataset...")
    print("  Source: 10X Genomics")

    if dataset == "pbmc3k":
        print("  Description: 2,700 PBMCs from a healthy donor")
        print("  Platform: 10X Chromium v1")
        adata = sc.datasets.pbmc3k()
    elif dataset == "pbmc68k_reduced":
        print("  Description: Subsampled PBMC 68k dataset")
        print("  Platform: 10X Chromium")
        adata = sc.datasets.pbmc68k_reduced()
    else:
        raise ValueError(f"Unknown dataset: {dataset}. Options: 'pbmc3k', 'pbmc68k_reduced'")

    print(f"\n✓ Data loaded successfully!")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")

    return adata


if __name__ == "__main__":
    # Test the function
    adata = load_example_data("pbmc3k")
    print("\nExample data ready for analysis!")

