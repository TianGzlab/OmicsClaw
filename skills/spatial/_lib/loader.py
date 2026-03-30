"""Multi-platform spatial transcriptomics data loader.

Supports: Visium (directory / H5 / H5AD), Xenium (Zarr / H5),
MERFISH, Slide-seq, seqFISH, and generic H5AD.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import anndata as ad
import scanpy as sc

from .exceptions import DataError

logger = logging.getLogger(__name__)

SpatialPlatform = Literal[
    "visium", "xenium", "slide_seq", "merfish", "seqfish", "generic"
]


def load_spatial_data(
    data_path: str | Path,
    data_type: SpatialPlatform = "generic",
    *,
    name: str | None = None,
) -> ad.AnnData:
    """Load spatial transcriptomics data from *data_path*.

    Returns an AnnData object with spatial coordinates in
    ``adata.obsm["spatial"]`` when available.
    """
    data_path = Path(data_path)
    if not data_path.exists():
        raise DataError(f"Data path does not exist: {data_path}")

    loader = _LOADERS.get(data_type)
    if loader is None:
        raise DataError(
            f"Unknown data_type '{data_type}'. "
            f"Supported: {list(_LOADERS.keys())}"
        )

    logger.info("Loading %s data from %s", data_type, data_path)
    adata = loader(data_path)

    if name:
        adata.uns["spatial_name"] = name

    _ensure_unique_var_names(adata)
    logger.info(
        "Loaded %d cells x %d genes (spatial coords: %s)",
        adata.n_obs,
        adata.n_vars,
        "spatial" in adata.obsm,
    )
    return adata


# ---------------------------------------------------------------------------
# Platform-specific loaders
# ---------------------------------------------------------------------------


def _load_visium(data_path: Path) -> ad.AnnData:
    """Load 10x Visium data (directory, .h5, or .h5ad)."""
    if data_path.is_dir():
        try:
            return sc.read_visium(data_path)
        except Exception as exc:
            logger.info("sc.read_visium failed for %s (%s); falling back to matrix loaders", data_path, exc)
        h5_candidates = list(data_path.glob("*filtered*feature*bc*matrix*.h5"))
        if h5_candidates:
            return sc.read_10x_h5(h5_candidates[0])
        mtx_dir = data_path / "filtered_feature_bc_matrix"
        if mtx_dir.exists():
            return sc.read_10x_mtx(mtx_dir)
        return sc.read_visium(data_path)

    suffix = data_path.suffix.lower()
    if suffix == ".h5ad":
        return sc.read_h5ad(data_path)
    if suffix in (".h5", ".hdf5"):
        return sc.read_10x_h5(data_path)
    raise DataError(f"Cannot determine Visium format for: {data_path}")


def _load_xenium(data_path: Path) -> ad.AnnData:
    """Load 10x Xenium data (h5ad or zarr)."""
    suffix = data_path.suffix.lower()
    if suffix == ".h5ad":
        return sc.read_h5ad(data_path)
    if suffix == ".zarr" or data_path.is_dir():
        try:
            return ad.read_zarr(data_path)
        except Exception as exc:
            raise DataError(f"Failed to read Xenium zarr: {exc}") from exc
    raise DataError(f"Cannot determine Xenium format for: {data_path}")


def _load_generic(data_path: Path) -> ad.AnnData:
    """Load generic h5ad."""
    suffix = data_path.suffix.lower()
    if suffix == ".h5ad":
        return sc.read_h5ad(data_path)
    raise DataError(
        f"Generic loader expects .h5ad, got: {data_path.suffix}"
    )


def _ensure_unique_var_names(adata: ad.AnnData) -> None:
    """Make var_names unique in-place if needed."""
    if not adata.var_names.is_unique:
        adata.var_names_make_unique()


_LOADERS: dict[str, callable] = {
    "visium": _load_visium,
    "xenium": _load_xenium,
    "slide_seq": _load_generic,
    "merfish": _load_generic,
    "seqfish": _load_generic,
    "generic": _load_generic,
}
