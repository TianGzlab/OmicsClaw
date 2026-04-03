"""Data loading utilities for single-cell analysis.

Provides multi-format import functions and example data loading.
Adapted from validated reference scripts (setup_and_import.py, load_example_data.py).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from anndata import AnnData

from omicsclaw.common.user_guidance import emit_user_guidance
from .adata_utils import build_standardization_recommendation, ensure_input_contract

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# Data import functions
# ---------------------------------------------------------------------------

def import_10x_data(
    data_dir: Union[str, Path],
    var_names: str = "gene_symbols",
    cache: bool = False,
    min_cells: int = 3,
    min_genes: int = 200,
) -> AnnData:
    """Import 10X Genomics CellRanger output (mtx directory).

    Parameters
    ----------
    data_dir
        Path to directory containing barcodes, features, and matrix files.
    var_names
        Column in .var to use for gene names.
    cache
        Cache the loaded data.
    min_cells
        Minimum cells for a gene to be kept.
    min_genes
        Minimum genes for a cell to be kept.

    Returns
    -------
    AnnData with raw counts.
    """
    import scanpy as sc

    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory does not exist: {data_dir}")

    logger.info("Loading 10X data from: %s", data_dir)
    adata = sc.read_10x_mtx(data_dir, var_names=var_names, cache=cache)

    if min_cells > 0:
        sc.pp.filter_genes(adata, min_cells=min_cells)
    if min_genes > 0:
        sc.pp.filter_cells(adata, min_genes=min_genes)

    logger.info("Created AnnData: %d genes x %d cells", adata.n_vars, adata.n_obs)
    return adata


def import_h5_data(
    h5_file: Union[str, Path],
    genome: Optional[str] = None,
    min_cells: int = 3,
    min_genes: int = 200,
) -> AnnData:
    """Import H5 format data from 10X.

    Parameters
    ----------
    h5_file
        Path to .h5 file.
    genome
        Genome name if multiple genomes present.
    min_cells
        Minimum cells for a gene to be kept.
    min_genes
        Minimum genes for a cell to be kept.

    Returns
    -------
    AnnData with raw counts.
    """
    import scanpy as sc

    h5_file = Path(h5_file)
    if not h5_file.exists():
        raise FileNotFoundError(f"H5 file does not exist: {h5_file}")

    logger.info("Loading H5 data from: %s", h5_file)
    adata = sc.read_10x_h5(h5_file, genome=genome)

    if min_cells > 0:
        sc.pp.filter_genes(adata, min_cells=min_cells)
    if min_genes > 0:
        sc.pp.filter_cells(adata, min_genes=min_genes)

    logger.info("Created AnnData: %d genes x %d cells", adata.n_vars, adata.n_obs)
    return adata


def import_count_matrix(
    file_path: Union[str, Path],
    transpose: bool = False,
    sep: Optional[str] = None,
    min_cells: int = 3,
    min_genes: int = 200,
) -> AnnData:
    """Import count matrix from CSV/TSV.

    Parameters
    ----------
    file_path
        Path to count matrix file.
    transpose
        Transpose matrix (use if genes are rows in the file).
    sep
        Separator character (auto-detect from extension if None).
    min_cells
        Minimum cells for a gene to be kept.
    min_genes
        Minimum genes for a cell to be kept.

    Returns
    -------
    AnnData with raw counts.
    """
    import scanpy as sc

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Count matrix file does not exist: {file_path}")

    if sep is None:
        sep = "\t" if file_path.suffix == ".tsv" else ","

    logger.info("Loading count matrix from: %s", file_path)
    counts = pd.read_csv(file_path, sep=sep, index_col=0)

    if transpose:
        counts = counts.T

    # scanpy expects cells x genes
    adata = sc.AnnData(counts.T)

    if min_cells > 0:
        sc.pp.filter_genes(adata, min_cells=min_cells)
    if min_genes > 0:
        sc.pp.filter_cells(adata, min_genes=min_genes)

    logger.info("Created AnnData: %d genes x %d cells", adata.n_vars, adata.n_obs)
    return adata


def import_loom_data(
    loom_file: Union[str, Path],
    sparse: bool = True,
    cleanup: bool = True,
) -> AnnData:
    """Import Loom format data.

    Parameters
    ----------
    loom_file
        Path to .loom file.
    sparse
        Store as sparse matrix.
    cleanup
        Clean up obs and var names.

    Returns
    -------
    AnnData with raw counts.
    """
    import scanpy as sc

    loom_file = Path(loom_file)
    if not loom_file.exists():
        raise FileNotFoundError(f"Loom file does not exist: {loom_file}")

    logger.info("Loading Loom data from: %s", loom_file)
    adata = sc.read_loom(loom_file, sparse=sparse, cleanup=cleanup)

    logger.info("Created AnnData: %d genes x %d cells", adata.n_vars, adata.n_obs)
    return adata


def add_metadata(
    adata: AnnData,
    metadata_file: Union[str, Path],
    merge_on: str = "index",
) -> AnnData:
    """Add sample metadata to AnnData object.

    Parameters
    ----------
    adata
        AnnData object.
    metadata_file
        Path to metadata CSV file.
    merge_on
        Column to merge on ('index' for cell barcodes as index).

    Returns
    -------
    AnnData with added metadata columns in .obs.
    """
    metadata_file = Path(metadata_file)
    if not metadata_file.exists():
        raise FileNotFoundError(f"Metadata file does not exist: {metadata_file}")

    logger.info("Loading metadata from: %s", metadata_file)
    metadata = pd.read_csv(metadata_file)

    if merge_on == "index" and metadata.index.name is None:
        metadata.set_index(metadata.columns[0], inplace=True)

    common_cells = set(adata.obs_names) & set(metadata.index)
    if len(common_cells) == 0:
        raise ValueError("No matching cell barcodes between AnnData and metadata")

    for col in metadata.columns:
        adata.obs[col] = metadata.loc[adata.obs_names, col]

    logger.info("Added %d metadata columns to %d cells", len(metadata.columns), len(common_cells))
    return adata


# ---------------------------------------------------------------------------
# Example / demo data
# ---------------------------------------------------------------------------


def _ensure_data_dir() -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR


def _demo_candidates(dataset: str) -> list[Path]:
    data_dir = _ensure_data_dir()
    examples_dir = _PROJECT_ROOT / "examples"
    if dataset == "pbmc3k_raw":
        return [
            data_dir / "pbmc3k_raw.h5ad",
            examples_dir / "pbmc3k.h5ad",
        ]
    if dataset == "pbmc3k_processed":
        return [
            data_dir / "pbmc3k_processed.h5ad",
            examples_dir / "pbmc3k_processed.h5ad",
            examples_dir / "pbmc3k.h5ad",
        ]
    if dataset == "pbmc68k_reduced":
        return [
            data_dir / "pbmc68k_reduced.h5ad",
        ]
    raise ValueError(f"Unknown demo dataset: {dataset}")


def load_repo_demo_data(dataset: str = "pbmc3k_raw") -> tuple[AnnData, Path | None]:
    """Load repo-local demo data first, else download and persist under ``data/``.

    Parameters
    ----------
    dataset
        Supported values: ``pbmc3k_raw``, ``pbmc3k_processed``, ``pbmc68k_reduced``.

    Returns
    -------
    tuple
        ``(adata, path_used_or_written)``
    """
    import scanpy as sc

    for candidate in _demo_candidates(dataset):
        if candidate.exists():
            logger.info("Loading local demo data: %s", candidate)
            return sc.read_h5ad(candidate), candidate

    logger.info("Local demo data for %s not found; downloading via scanpy", dataset)
    if dataset == "pbmc3k_raw":
        adata = sc.datasets.pbmc3k()
        out_path = _ensure_data_dir() / "pbmc3k_raw.h5ad"
    elif dataset == "pbmc3k_processed":
        adata = sc.datasets.pbmc3k_processed()
        out_path = _ensure_data_dir() / "pbmc3k_processed.h5ad"
    elif dataset == "pbmc68k_reduced":
        adata = sc.datasets.pbmc68k_reduced()
        out_path = _ensure_data_dir() / "pbmc68k_reduced.h5ad"
    else:  # pragma: no cover
        raise ValueError(f"Unknown demo dataset: {dataset}")

    adata.write_h5ad(out_path)
    logger.info("Downloaded demo data saved to: %s", out_path)
    return adata, out_path

def load_example_data(dataset: str = "pbmc3k") -> AnnData:
    """Load example single-cell RNA-seq dataset.

    Parameters
    ----------
    dataset
        Dataset to load. Options: ``"pbmc3k"``, ``"pbmc68k_reduced"``.

    Returns
    -------
    AnnData with raw counts (pbmc3k) or processed data (pbmc68k_reduced).
    """
    import scanpy as sc

    logger.info("Loading %s example dataset ...", dataset)

    if dataset == "pbmc3k":
        adata, _ = load_repo_demo_data("pbmc3k_raw")
    elif dataset == "pbmc3k_processed":
        adata, _ = load_repo_demo_data("pbmc3k_processed")
    elif dataset == "pbmc68k_reduced":
        adata, _ = load_repo_demo_data("pbmc68k_reduced")
    else:
        raise ValueError(
            f"Unknown dataset: {dataset}. Options: 'pbmc3k', 'pbmc3k_processed', 'pbmc68k_reduced'"
        )

    logger.info("Loaded: %d cells x %d genes", adata.n_obs, adata.n_vars)
    return adata


def smart_load(
    path: Union[str, Path],
    *,
    suggest_standardize: bool = True,
    skill_name: str | None = None,
    preserve_all: bool = False,
    **kwargs,
) -> AnnData:
    """Auto-detect file format and load accordingly.

    Supports: .h5ad, .h5, .loom, .csv, .tsv, and 10X mtx directories.

    When ``preserve_all=True``, count-like loaders disable their default
    cell/gene filtering so downstream skills can decide on QC thresholds.
    """
    import scanpy as sc

    path = Path(path)

    filtered_kwargs = dict(kwargs)
    if preserve_all:
        filtered_kwargs.setdefault("min_cells", 0)
        filtered_kwargs.setdefault("min_genes", 0)

    if path.is_dir():
        adata = import_10x_data(path, **filtered_kwargs)
        if suggest_standardize:
            maybe_warn_standardize_first(adata, source_path=str(path), skill_name=skill_name)
        else:
            ensure_input_contract(adata, source_path=str(path), standardized=False)
        return adata

    suffix = path.suffix.lower()
    if suffix == ".h5ad":
        logger.info("Loading H5AD: %s", path)
        adata = sc.read_h5ad(path)
    elif suffix == ".h5":
        adata = import_h5_data(path, **filtered_kwargs)
    elif suffix == ".loom":
        adata = import_loom_data(path, **kwargs)
    elif suffix in (".csv", ".tsv"):
        adata = import_count_matrix(path, **filtered_kwargs)
    else:
        # Try as h5ad
        logger.info("Unknown extension %s, trying as h5ad ...", suffix)
        adata = sc.read_h5ad(path)

    if suggest_standardize:
        maybe_warn_standardize_first(adata, source_path=str(path), skill_name=skill_name)
    else:
        ensure_input_contract(adata, source_path=str(path))
    return adata


def maybe_warn_standardize_first(
    adata: AnnData,
    *,
    source_path: str | Path | None = None,
    skill_name: str | None = None,
) -> dict:
    """Warn when downstream skills receive input that has not been standardized."""
    source_text = str(source_path) if source_path is not None else None
    contract = ensure_input_contract(adata, source_path=source_text)
    if not contract.get("standardized"):
        emit_user_guidance(
            logger,
            build_standardization_recommendation(source_path=source_text, skill_name=skill_name),
        )
    return contract
