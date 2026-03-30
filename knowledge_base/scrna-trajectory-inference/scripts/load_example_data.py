"""
Load example data for single-cell trajectory inference.

Provides two functions:
  - load_example_data(): Load pancreas endocrinogenesis dataset (Bastidas-Ponce 2019)
  - load_user_data(path): Load and validate user-provided h5ad/rds file

Example dataset: Pancreatic endocrinogenesis (3,696 cells)
  - Progenitor cells differentiate into alpha, beta, delta, epsilon cells
  - Includes spliced/unspliced counts for RNA velocity
  - Available via scvelo.datasets.pancreas()

Usage:
  from scripts.load_example_data import load_example_data
  adata = load_example_data()
"""

import warnings
from pathlib import Path


def load_example_data():
    """
    Load the pancreatic endocrinogenesis dataset (Bastidas-Ponce et al. 2019).

    Downloads ~15 MB h5ad from scVelo's data repository.
    Contains spliced/unspliced counts for RNA velocity analysis.

    Returns
    -------
    adata : AnnData
        Preprocessed AnnData with:
        - .X : spliced counts (log-normalized)
        - .layers['spliced'], .layers['unspliced'] : raw counts for velocity
        - .obs['clusters'] : cell type annotations (8 types)
        - .obsm['X_umap'] : UMAP embedding
        - .var['highly_variable'] : HVG flags

    Raises
    ------
    RuntimeError
        If download or loading fails.
    """
    try:
        import scvelo as scv
    except ImportError:
        raise RuntimeError(
            "scvelo is required for example data. Install with: pip install scvelo"
        )

    print("Loading pancreatic endocrinogenesis dataset (Bastidas-Ponce 2019)...")
    print("  Downloading from scVelo repository (~15 MB)...")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        adata = scv.datasets.pancreas()

    # Validate required slots
    _validate_adata(adata, require_velocity_layers=True)

    print(f"✓ Data loaded successfully!")
    print(f"  Cells: {adata.n_obs:,}")
    print(f"  Genes: {adata.n_vars:,}")
    print(f"  Cell types: {adata.obs['clusters'].nunique()}")
    print(f"  Cell type distribution:")
    for ct, count in adata.obs["clusters"].value_counts().items():
        print(f"    - {ct}: {count} cells ({100 * count / adata.n_obs:.1f}%)")
    print(f"  Layers: {list(adata.layers.keys())}")
    print(f"  Embeddings: {list(adata.obsm.keys())}")

    return adata


def load_user_data(path, cluster_key=None):
    """
    Load and validate a user-provided scRNA-seq dataset.

    Supports .h5ad (AnnData) files. The object should be preprocessed
    (normalized, with PCA/UMAP computed and clusters assigned).

    Parameters
    ----------
    path : str or Path
        Path to .h5ad file.
    cluster_key : str, optional
        Column in .obs containing cluster/cell type labels.
        Auto-detected if not specified.

    Returns
    -------
    adata : AnnData
        Validated AnnData object.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file format is unsupported or data is invalid.
    """
    import scanpy as sc

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix == ".h5ad":
        print(f"Loading AnnData from {path}...")
        adata = sc.read_h5ad(path)
    else:
        raise ValueError(
            f"Unsupported file format: {path.suffix}. "
            "Expected .h5ad (AnnData). "
            "Convert Seurat objects with SeuratDisk::SaveH5Seurat() + Convert()."
        )

    # Auto-detect cluster key
    if cluster_key is None:
        candidates = [
            "clusters",
            "cell_type",
            "celltype",
            "leiden",
            "louvain",
            "cluster",
            "cell_type_ontology_term_id",
        ]
        for c in candidates:
            if c in adata.obs.columns:
                cluster_key = c
                break

    if cluster_key and cluster_key in adata.obs.columns:
        print(f"  Cluster key: '{cluster_key}' ({adata.obs[cluster_key].nunique()} groups)")
    else:
        print("  Warning: No cluster annotations found. PAGA requires clusters.")

    # Check for velocity layers
    has_velocity = "spliced" in adata.layers and "unspliced" in adata.layers
    if has_velocity:
        print("  RNA velocity layers detected (spliced/unspliced)")
    else:
        print("  No velocity layers — RNA velocity will be skipped")

    _validate_adata(adata, require_velocity_layers=False)

    print(f"✓ Data loaded successfully!")
    print(f"  Cells: {adata.n_obs:,}")
    print(f"  Genes: {adata.n_vars:,}")

    return adata


def _validate_adata(adata, require_velocity_layers=False):
    """
    Validate AnnData has minimum required structure.

    Parameters
    ----------
    adata : AnnData
        Object to validate.
    require_velocity_layers : bool
        If True, require spliced/unspliced layers.

    Raises
    ------
    ValueError
        If validation fails.
    """
    if adata.n_obs < 200:
        raise ValueError(
            f"Too few cells ({adata.n_obs}). Trajectory inference needs >= 200 cells "
            "for meaningful results."
        )

    if adata.n_vars < 100:
        raise ValueError(
            f"Too few genes ({adata.n_vars}). Trajectory inference needs >= 100 genes."
        )

    if require_velocity_layers:
        missing = []
        for layer in ["spliced", "unspliced"]:
            if layer not in adata.layers:
                missing.append(layer)
        if missing:
            raise ValueError(
                f"Missing required layers for RNA velocity: {missing}. "
                "These are needed for scVelo analysis."
            )

