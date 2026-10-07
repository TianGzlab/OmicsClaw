"""Write AnnData matrices and metadata for temporary R method inputs."""

from __future__ import annotations

from pathlib import Path
import gzip
import csv

import pandas as pd
from scipy import sparse
from scipy.io import mmwrite

__all__ = ["write_matrix_exchange"]


def write_matrix_exchange(adata, folder: Path, *, obs_columns: list[str] | None = None,
                          compressed: bool = False) -> Path:
    """Write X as genes-by-cells Matrix Market and retain both axis orders.

    Callers select the appropriate expression matrix before calling this
    helper. Counts and log-normalised expression are written without rounding.
    Metadata uses CSV quoting; features and barcodes use 10x TSV files.
    compressed=True writes the three 10x files as gzip for Seurat Read10X.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError("R matrix exchange requires unique cell and feature names")
    for axis in (adata.obs_names, adata.var_names):
        if any(any(character in str(name) for character in "\t\r\n") for name in axis):
            raise ValueError("R matrix exchange names cannot contain tabs or newlines")
    suffix = ".gz" if compressed else ""
    if compressed:
        with gzip.open(folder / "matrix.mtx.gz", "wb") as stream:
            mmwrite(stream, sparse.coo_matrix(adata.X.T))
    else:
        mmwrite(folder / "matrix.mtx", sparse.coo_matrix(adata.X.T))
    pd.Series(adata.obs_names).to_csv(folder / f"barcodes.tsv{suffix}", sep="\t", index=False, header=False,
                                    quoting=csv.QUOTE_NONE)
    pd.DataFrame({"id": adata.var_names, "name": adata.var_names, "type": "Gene Expression"}).to_csv(
        folder / f"features.tsv{suffix}", sep="\t", index=False, header=False, quoting=csv.QUOTE_NONE,
    )
    metadata = adata.obs if obs_columns is None else adata.obs.loc[:, obs_columns]
    metadata.to_csv(folder / "obs.csv", index_label="cell_id")
    return folder
