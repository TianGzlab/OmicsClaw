"""Python-side utilities for R data exchange.

Provides standardized functions for writing data that R scripts can read
(CSV, h5ad) and reading results that R scripts produce.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

__all__ = ["read_r_result_csv"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Write helpers (Python → R)
# ---------------------------------------------------------------------------


def adata_to_csv_exchange(adata, output_dir: str | Path) -> dict[str, Path]:
    """Write an AnnData object to CSV files for R consumption.

    Produces:
      - counts.csv  : gene-expression matrix (cells × genes)
      - obs.csv     : cell metadata
      - var.csv     : gene metadata
      - coords.csv  : spatial coordinates (if available)

    Returns a dict mapping name → file path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # Counts matrix (dense — R reads CSV natively)
    X = adata.X
    if sparse.issparse(X):
        X = X.toarray()
    counts_df = pd.DataFrame(
        X,
        index=adata.obs_names,
        columns=adata.var_names,
    )
    counts_path = output_dir / "counts.csv"
    counts_df.to_csv(counts_path)
    paths["counts"] = counts_path

    # Cell metadata
    obs_path = output_dir / "obs.csv"
    adata.obs.to_csv(obs_path)
    paths["obs"] = obs_path

    # Gene metadata
    var_path = output_dir / "var.csv"
    adata.var.to_csv(var_path)
    paths["var"] = var_path

    # Spatial coordinates (if present)
    if "spatial" in adata.obsm:
        coords = adata.obsm["spatial"]
        coords_df = pd.DataFrame(
            coords[:, :2],
            index=adata.obs_names,
            columns=["x", "y"],
        )
        coords_path = output_dir / "coords.csv"
        coords_df.to_csv(coords_path)
        paths["coords"] = coords_path

    logger.debug("Wrote %d exchange files to %s", len(paths), output_dir)
    return paths


def adata_to_h5ad_exchange(adata, path: str | Path) -> Path:
    """Write an AnnData to h5ad for R to read via zellkonverter.

    Returns the path written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(path)
    return path


# ---------------------------------------------------------------------------
# Read helpers (R → Python)
# ---------------------------------------------------------------------------


def read_r_result_csv(path: str | Path, index_col: int | str | None = 0) -> pd.DataFrame:
    """Read a CSV written by an R script back into a DataFrame.

    Uses ``check_names=False`` semantics — R may mangle column names,
    but we read them as-is.
    """
    return pd.read_csv(path, index_col=index_col)


def read_r_result_json(path: str | Path) -> dict:
    """Read a JSON result file produced by an R script."""
    with open(path) as f:
        return json.load(f)


def read_r_embedding_csv(path: str | Path) -> np.ndarray:
    """Read a numeric matrix CSV (e.g. PCA/UMAP embeddings) as a numpy array.

    Expects the first column to be row names (cell barcodes).
    """
    df = pd.read_csv(path, index_col=0)
    return df.values.astype(np.float64)


# ---------------------------------------------------------------------------
# Generic I/O
# ---------------------------------------------------------------------------


def dataframe_to_csv(df: pd.DataFrame, path: str | Path) -> Path:
    """Write a DataFrame to CSV with index preserved (R reads with row.names=1)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    return path


def csv_to_dataframe(path: str | Path, index_col: int | str | None = 0) -> pd.DataFrame:
    """Read a CSV, treating the first column as the index by default."""
    return pd.read_csv(path, index_col=index_col)
