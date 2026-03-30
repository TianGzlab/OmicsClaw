"""
============================================================================
LOAD SPATIAL TRANSCRIPTOMICS DATA
============================================================================

Functions:
  - load_visium_heart(): Load V1_Human_Heart example dataset from 10x Genomics
  - load_visium_data(): Load user-provided Visium data (h5ad or Space Ranger)

Usage:
  from load_example_data import load_visium_heart
  adata = load_visium_heart()
"""

from pathlib import Path
from typing import Optional, Union


def load_visium_heart() -> 'anndata.AnnData':
    """
    Load V1_Human_Heart Visium dataset from 10x Genomics.

    Downloads the processed dataset via scanpy's built-in datasets module.
    Contains ~4,247 spots and ~33,538 genes with H&E tissue image.

    Returns
    -------
    AnnData
        Visium spatial transcriptomics data with:
        - .X: count matrix (spots x genes)
        - .obs: spot metadata
        - .obsm['spatial']: spatial coordinates
        - .uns['spatial']: tissue image and scalefactors
    """
    import scanpy as sc

    print("Loading V1_Human_Heart Visium dataset...")
    print("  Source: 10x Genomics Spatial Gene Expression")
    print("  Description: Human heart tissue section")
    print("  Platform: Visium Spatial Gene Expression")
    print("  (First run downloads ~50 MB, subsequent runs use cache)")

    try:
        adata = sc.datasets.visium_sge(sample_id="V1_Human_Heart")
    except AttributeError:
        # Fallback for Python <3.12 (tarfile.data_filter not available)
        print("  Using manual download fallback...")
        adata = _download_visium_manual("V1_Human_Heart")

    # Make variable names unique (critical for some Visium datasets)
    adata.var_names_make_unique()

    # Report dataset summary
    has_image = 'spatial' in adata.uns and len(adata.uns['spatial']) > 0

    print(f"\n✓ Data loaded successfully!")
    print(f"  Spots: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")
    print(f"  Spatial image: {'Yes' if has_image else 'No'}")
    if 'spatial' in adata.obsm:
        print(f"  Spatial coordinates: {adata.obsm['spatial'].shape}")

    return adata


def _download_file(url: str, dest: Path) -> None:
    """Download a file with proper User-Agent header."""
    import urllib.request

    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; scanpy-downloader)'
    })
    with urllib.request.urlopen(req) as response, open(dest, 'wb') as out:
        while True:
            chunk = response.read(8192)
            if not chunk:
                break
            out.write(chunk)


def _download_visium_manual(sample_id: str) -> 'anndata.AnnData':
    """Manual Visium dataset download for Python <3.12 compatibility."""
    import scanpy as sc
    import tarfile

    base_url = "https://cf.10xgenomics.com/samples/spatial-exp/1.1.0"

    cache_dir = Path(sc.settings.datasetdir) / sample_id
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Download H5 file (required by sc.read_visium)
    h5_path = cache_dir / "filtered_feature_bc_matrix.h5"
    if not h5_path.exists():
        h5_url = f"{base_url}/{sample_id}/{sample_id}_filtered_feature_bc_matrix.h5"
        print(f"  Downloading filtered feature-barcode matrix (H5)...")
        _download_file(h5_url, h5_path)

    # Download and extract spatial data
    spatial_dir = cache_dir / "spatial"
    if not spatial_dir.exists():
        spatial_url = f"{base_url}/{sample_id}/{sample_id}_spatial.tar.gz"
        print(f"  Downloading spatial data...")
        tar_path = cache_dir / "spatial.tar.gz"
        _download_file(spatial_url, tar_path)
        with tarfile.open(tar_path, 'r:gz') as tf:
            tf.extractall(cache_dir)
        tar_path.unlink()

    adata = sc.read_visium(cache_dir)
    return adata


def load_visium_data(
    path: Union[str, Path],
    library_id: Optional[str] = None
) -> 'anndata.AnnData':
    """
    Load user-provided Visium data.

    Supports:
    - .h5ad files (AnnData format)
    - Space Ranger output directory (with filtered_feature_bc_matrix/)
    - .h5 files (10x HDF5 format)

    Parameters
    ----------
    path : str or Path
        Path to data file or Space Ranger output directory.
    library_id : str, optional
        Library ID for Space Ranger output.

    Returns
    -------
    AnnData
        Loaded spatial data with spatial coordinates.
    """
    import scanpy as sc

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    if path.suffix == '.h5ad':
        print(f"Loading AnnData from {path}...")
        adata = sc.read_h5ad(path)
    elif path.suffix == '.h5':
        print(f"Loading 10x HDF5 from {path}...")
        adata = sc.read_10x_h5(path)
    elif path.is_dir():
        print(f"Loading Space Ranger output from {path}...")
        adata = sc.read_visium(path, library_id=library_id)
    else:
        raise ValueError(
            f"Unsupported format: {path.suffix}. "
            "Expected .h5ad, .h5, or Space Ranger output directory."
        )

    adata.var_names_make_unique()

    has_image = 'spatial' in adata.uns and len(adata.uns['spatial']) > 0

    print(f"\n✓ Data loaded successfully!")
    print(f"  Spots: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")
    print(f"  Spatial image: {'Yes' if has_image else 'No'}")
    if 'spatial' in adata.obsm:
        print(f"  Spatial coordinates: {adata.obsm['spatial'].shape}")

    return adata


if __name__ == "__main__":
    adata = load_visium_heart()
    print("\nExample data ready for spatial analysis!")

