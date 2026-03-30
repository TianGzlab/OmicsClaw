"""
============================================================================
SETUP AND DATA IMPORT FOR SCANPY ANALYSIS
============================================================================

This script handles initial setup and data loading for scanpy scRNA-seq analysis.

Functions:
  - setup_scanpy_environment(): Load required Python packages
  - import_10x_data(): Load 10X Genomics CellRanger output
  - import_h5_data(): Load H5 format data
  - import_count_matrix(): Load from CSV/TSV count matrix
  - import_loom_data(): Load from Loom file
  - add_metadata(): Add sample metadata to AnnData

Usage:
  from setup_and_import import setup_scanpy_environment, import_10x_data
  setup_scanpy_environment()
  adata = import_10x_data("path/to/filtered_feature_bc_matrix/")
"""

import os
import warnings
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd


def setup_scanpy_environment(verbose: bool = True) -> None:
    """
    Load required libraries for scanpy analysis.

    Parameters
    ----------
    verbose : bool, optional
        Print version information (default: True)

    Returns
    -------
    None
        Loads packages into environment
    """
    import scanpy as sc
    import matplotlib.pyplot as plt

    # Set scanpy settings
    sc.settings.verbosity = 3  # verbosity: errors (0), warnings (1), info (2), hints (3)
    sc.settings.set_figure_params(dpi=300, facecolor='white', frameon=False)

    # Suppress warnings
    warnings.filterwarnings('ignore', category=FutureWarning)
    warnings.filterwarnings('ignore', category=UserWarning)

    if verbose:
        print("Required libraries loaded successfully")
        print(f"Scanpy version: {sc.__version__}")
        print(f"NumPy version: {np.__version__}")
        print(f"Pandas version: {pd.__version__}")


def import_10x_data(
    data_dir: Union[str, Path],
    var_names: str = 'gene_symbols',
    cache: bool = False,
    min_cells: int = 3,
    min_genes: int = 200
) -> 'AnnData':
    """
    Import 10X Genomics data.

    Parameters
    ----------
    data_dir : str or Path
        Path to directory containing barcodes, features, and matrix files
    var_names : str, optional
        Column name in .var DataFrame to use for gene names (default: 'gene_symbols')
    cache : bool, optional
        Cache the loaded data (default: False)
    min_cells : int, optional
        Minimum number of cells for a gene to be included (default: 3)
    min_genes : int, optional
        Minimum number of genes for a cell to be included (default: 200)

    Returns
    -------
    AnnData
        AnnData object with raw counts
    """
    import scanpy as sc

    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory does not exist: {data_dir}")

    print(f"Loading 10X data from: {data_dir}")

    # Read 10X data
    adata = sc.read_10x_mtx(
        data_dir,
        var_names=var_names,
        cache=cache
    )

    # Filter genes and cells
    if min_cells > 0:
        sc.pp.filter_genes(adata, min_cells=min_cells)
    if min_genes > 0:
        sc.pp.filter_cells(adata, min_genes=min_genes)

    print(f"Created AnnData object: {adata.n_vars} genes x {adata.n_obs} cells")

    return adata


def import_h5_data(
    h5_file: Union[str, Path],
    genome: Optional[str] = None,
    min_cells: int = 3,
    min_genes: int = 200
) -> 'AnnData':
    """
    Import H5 format data from 10X.

    Parameters
    ----------
    h5_file : str or Path
        Path to H5 file
    genome : str, optional
        Genome name if multiple genomes are present
    min_cells : int, optional
        Minimum number of cells for a gene to be included (default: 3)
    min_genes : int, optional
        Minimum number of genes for a cell to be included (default: 200)

    Returns
    -------
    AnnData
        AnnData object with raw counts
    """
    import scanpy as sc

    h5_file = Path(h5_file)
    if not h5_file.exists():
        raise FileNotFoundError(f"H5 file does not exist: {h5_file}")

    print(f"Loading H5 data from: {h5_file}")

    # Read H5 data
    adata = sc.read_10x_h5(h5_file, genome=genome)

    # Filter genes and cells
    if min_cells > 0:
        sc.pp.filter_genes(adata, min_cells=min_cells)
    if min_genes > 0:
        sc.pp.filter_cells(adata, min_genes=min_genes)

    print(f"Created AnnData object: {adata.n_vars} genes x {adata.n_obs} cells")

    return adata


def import_count_matrix(
    file_path: Union[str, Path],
    transpose: bool = False,
    sep: Optional[str] = None,
    min_cells: int = 3,
    min_genes: int = 200
) -> 'AnnData':
    """
    Import count matrix from CSV/TSV.

    Parameters
    ----------
    file_path : str or Path
        Path to count matrix file
    transpose : bool, optional
        Transpose matrix (use if cells are rows) (default: False)
    sep : str, optional
        Separator character (default: auto-detect from extension)
    min_cells : int, optional
        Minimum number of cells for a gene to be included (default: 3)
    min_genes : int, optional
        Minimum number of genes for a cell to be included (default: 200)

    Returns
    -------
    AnnData
        AnnData object with raw counts
    """
    import scanpy as sc

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Count matrix file does not exist: {file_path}")

    # Auto-detect separator
    if sep is None:
        if file_path.suffix == '.tsv':
            sep = '\t'
        else:
            sep = ','

    print(f"Loading count matrix from: {file_path}")

    # Read count matrix
    counts = pd.read_csv(file_path, sep=sep, index_col=0)

    # Transpose if needed (scanpy expects genes as rows, cells as columns)
    if transpose:
        counts = counts.T

    # Create AnnData object
    adata = sc.AnnData(counts.T)  # Transpose again for scanpy format (cells × genes)

    # Filter genes and cells
    if min_cells > 0:
        sc.pp.filter_genes(adata, min_cells=min_cells)
    if min_genes > 0:
        sc.pp.filter_cells(adata, min_genes=min_genes)

    print(f"Created AnnData object: {adata.n_vars} genes x {adata.n_obs} cells")

    return adata


def import_loom_data(
    loom_file: Union[str, Path],
    sparse: bool = True,
    cleanup: bool = True
) -> 'AnnData':
    """
    Import Loom format data.

    Parameters
    ----------
    loom_file : str or Path
        Path to Loom file
    sparse : bool, optional
        Store as sparse matrix (default: True)
    cleanup : bool, optional
        Clean up obs and var names (default: True)

    Returns
    -------
    AnnData
        AnnData object with raw counts
    """
    import scanpy as sc

    loom_file = Path(loom_file)
    if not loom_file.exists():
        raise FileNotFoundError(f"Loom file does not exist: {loom_file}")

    print(f"Loading Loom data from: {loom_file}")

    # Read Loom data
    adata = sc.read_loom(loom_file, sparse=sparse, cleanup=cleanup)

    print(f"Created AnnData object: {adata.n_vars} genes x {adata.n_obs} cells")

    return adata


def add_metadata(
    adata: 'AnnData',
    metadata_file: Union[str, Path],
    merge_on: str = 'index'
) -> 'AnnData':
    """
    Add sample metadata to AnnData object.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    metadata_file : str or Path
        Path to metadata CSV file
    merge_on : str, optional
        Column to merge on ('index' for cell barcodes as index) (default: 'index')

    Returns
    -------
    AnnData
        AnnData object with added metadata
    """
    metadata_file = Path(metadata_file)
    if not metadata_file.exists():
        raise FileNotFoundError(f"Metadata file does not exist: {metadata_file}")

    print(f"Loading metadata from: {metadata_file}")

    # Read metadata
    metadata = pd.read_csv(metadata_file)

    # Set index if needed
    if merge_on == 'index' and metadata.index.name is None:
        metadata.set_index(metadata.columns[0], inplace=True)

    # Check for matching cells
    cells_in_obj = set(adata.obs_names)
    cells_in_meta = set(metadata.index)

    common_cells = cells_in_obj & cells_in_meta
    if len(common_cells) == 0:
        raise ValueError("No matching cell barcodes between AnnData object and metadata file")

    # Add metadata
    for col in metadata.columns:
        adata.obs[col] = metadata.loc[adata.obs_names, col]

    print(f"Added {len(metadata.columns)} metadata columns to {len(common_cells)} cells")

    return adata


def load_pbmc3k_example() -> 'AnnData':
    """
    Load example PBMC 3k dataset from scanpy datasets.

    Returns
    -------
    AnnData
        PBMC 3k dataset
    """
    import scanpy as sc

    print("Loading PBMC 3k example dataset...")
    adata = sc.datasets.pbmc3k()

    print(f"Loaded AnnData object: {adata.n_vars} genes x {adata.n_obs} cells")

    return adata

