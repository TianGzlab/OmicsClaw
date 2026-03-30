"""
============================================================================
UMAP DIMENSIONALITY REDUCTION
============================================================================

This script performs UMAP for visualization.

Functions:
  - run_umap_reduction(): Compute UMAP embedding
  - run_tsne_reduction(): Compute t-SNE embedding (alternative)

Usage:
  from run_umap import run_umap_reduction
  adata = run_umap_reduction(adata, n_neighbors=10)
"""

from typing import Optional


def run_umap_reduction(
    adata: 'AnnData',
    n_neighbors: Optional[int] = None,
    min_dist: float = 0.5,
    spread: float = 1.0,
    random_state: int = 0,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Compute UMAP embedding.

    Parameters
    ----------
    adata : AnnData
        AnnData object with neighbor graph
    n_neighbors : int, optional
        Number of neighbors (default: use same as neighbor graph)
    min_dist : float, optional
        Minimum distance parameter (default: 0.5)
    spread : float, optional
        Spread parameter (default: 1.0)
    random_state : int, optional
        Random seed (default: 0)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with UMAP if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if 'neighbors' not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph first.")

    print("Running UMAP...")

    # Get n_neighbors from neighbor graph if not specified
    if n_neighbors is None:
        n_neighbors = adata.uns['neighbors']['params']['n_neighbors']

    print(f"  n_neighbors: {n_neighbors}")
    print(f"  min_dist: {min_dist}")
    print(f"  spread: {spread}")

    sc.tl.umap(
        adata,
        min_dist=min_dist,
        spread=spread,
        random_state=random_state
    )

    print("  UMAP complete")

    # Always return adata for convenience
    return adata


def run_tsne_reduction(
    adata: 'AnnData',
    n_pcs: Optional[int] = None,
    perplexity: float = 30,
    early_exaggeration: float = 12,
    learning_rate: float = 1000,
    random_state: int = 0,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Compute t-SNE embedding (alternative to UMAP).

    Parameters
    ----------
    adata : AnnData
        AnnData object with PCA
    n_pcs : int, optional
        Number of PCs to use (default: None, uses all)
    perplexity : float, optional
        Perplexity parameter (default: 30)
    early_exaggeration : float, optional
        Early exaggeration parameter (default: 12)
    learning_rate : float, optional
        Learning rate (default: 1000)
    random_state : int, optional
        Random seed (default: 0)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with t-SNE if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if 'pca' not in adata.obsm:
        raise ValueError("PCA not found. Run run_pca_analysis first.")

    print("Running t-SNE...")

    if n_pcs is None:
        n_pcs = adata.obsm['X_pca'].shape[1]
        print(f"  Using all {n_pcs} PCs")
    else:
        print(f"  Using {n_pcs} PCs")

    print(f"  perplexity: {perplexity}")

    sc.tl.tsne(
        adata,
        n_pcs=n_pcs,
        perplexity=perplexity,
        early_exaggeration=early_exaggeration,
        learning_rate=learning_rate,
        random_state=random_state
    )

    print("  t-SNE complete")

    # Always return adata for convenience
    return adata


def run_diffmap(
    adata: 'AnnData',
    n_comps: int = 15,
    inplace: bool = True
) -> Optional['AnnData']:
    """
    Compute diffusion map (alternative dimensionality reduction).

    Useful for trajectory inference and continuous processes.

    Parameters
    ----------
    adata : AnnData
        AnnData object with neighbor graph
    n_comps : int, optional
        Number of diffusion components (default: 15)
    inplace : bool, optional
        Modify AnnData in place (default: True)

    Returns
    -------
    AnnData or None
        AnnData object with diffusion map if inplace=False, else None
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if 'neighbors' not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph first.")

    print(f"Running diffusion map with {n_comps} components...")

    sc.tl.diffmap(adata, n_comps=n_comps)

    print("  Diffusion map complete")

    # Always return adata for convenience
    return adata

