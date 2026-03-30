"""
Load 10X Feature-Barcode Matrices for Pooled CRISPR Screens

This module loads raw 10X h5 feature-barcode matrices containing both gene
expression and sgRNA capture data.
"""

import scanpy as sc
from typing import List
import anndata as ad


def load_single_library(h5_path: str) -> ad.AnnData:
    """
    Load a single 10X h5 feature-barcode matrix.

    Parameters
    ----------
    h5_path : str
        Path to raw_feature_bc_matrix.h5 file

    Returns
    -------
    adata : AnnData
        AnnData object with unique gene names
    """
    print(f"Loading {h5_path}...")
    adata = sc.read_10x_h5(h5_path)

    # Make gene names unique (handles duplicate gene symbols)
    adata.var_names_make_unique()

    print(f"  Loaded {adata.n_obs} cells x {adata.n_vars} features")

    return adata


def load_multiple_libraries(h5_paths: List[str]) -> List[ad.AnnData]:
    """
    Load multiple 10X h5 files for replicate libraries.

    Parameters
    ----------
    h5_paths : list of str
        Paths to h5 files

    Returns
    -------
    adata_list : list of AnnData
        List of AnnData objects, one per library

    Example
    -------
    >>> adata_list = load_multiple_libraries([
    ...     "raw_feature_bc_matrix_lib1.h5",
    ...     "raw_feature_bc_matrix_lib2.h5",
    ...     "raw_feature_bc_matrix_lib3.h5",
    ...     "raw_feature_bc_matrix_lib4.h5"
    ... ])
    """
    adata_list = []

    for h5_path in h5_paths:
        adata = load_single_library(h5_path)
        adata_list.append(adata)

    print(f"\nLoaded {len(adata_list)} libraries total")

    return adata_list

