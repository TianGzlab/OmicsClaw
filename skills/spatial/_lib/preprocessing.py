"""Spatial data preprocessing pipeline.

Provides a standard scanpy-based preprocessing workflow for spatial
transcriptomics data: QC metrics → filtering → normalization → HVG
selection → PCA → neighbors → UMAP → Leiden clustering.

Usage::

    from skills.spatial._lib.preprocessing import preprocess

    adata, summary = preprocess(adata, species="human", n_top_hvg=2000)
"""

from __future__ import annotations

import logging

import numpy as np
import scanpy as sc

from .adata_utils import get_spatial_key, store_analysis_metadata

logger = logging.getLogger(__name__)


def preprocess(
    adata,
    *,
    min_genes: int = 0,
    min_cells: int = 0,
    max_mt_pct: float = 20.0,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    n_neighbors: int = 15,
    leiden_resolution: float = 1.0,
    species: str = "human",
    skill_name: str = "spatial-preprocess",
) -> tuple:
    """Run the full spatial preprocessing pipeline.

    Parameters
    ----------
    adata : AnnData
        Raw spatial transcriptomics data.
    min_genes : int
        Minimum genes per cell for filtering.
    min_cells : int
        Minimum cells per gene for filtering.
    max_mt_pct : float
        Maximum mitochondrial percentage for cell filtering.
    n_top_hvg : int
        Number of highly variable genes to select.
    n_pcs : int
        Number of principal components.
    n_neighbors : int
        Number of neighbors for graph construction.
    leiden_resolution : float
        Resolution for Leiden clustering.
    species : str
        Species for MT gene prefix detection ("human" or "mouse").
    skill_name : str
        Name for metadata storage.

    Returns
    -------
    tuple[AnnData, dict]
        Processed AnnData and summary dictionary.
    """
    n_cells_raw = adata.n_obs
    n_genes_raw = adata.n_vars
    logger.info("Input: %d cells x %d genes", n_cells_raw, n_genes_raw)

    # QC metrics
    mt_prefix = "MT-" if species == "human" else "mt-"
    adata.var["mt"] = adata.var_names.str.startswith(mt_prefix)
    sc.pp.calculate_qc_metrics(
        adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True,
    )

    # Filter
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)
    if max_mt_pct < 100:
        adata = adata[adata.obs["pct_counts_mt"] < max_mt_pct].copy()

    n_cells_filtered = adata.n_obs
    n_genes_filtered = adata.n_vars
    logger.info(
        "After QC: %d cells x %d genes (removed %d cells, %d genes)",
        n_cells_filtered, n_genes_filtered,
        n_cells_raw - n_cells_filtered, n_genes_raw - n_genes_filtered,
    )

    # Preserve raw counts
    adata.raw = adata.copy()

    # Normalize
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # HVG
    n_hvg = min(n_top_hvg, adata.n_vars - 1)
    sc.pp.highly_variable_genes(adata, n_top_genes=n_hvg, flavor="seurat_v3")
    logger.info("Selected %d highly variable genes", adata.var["highly_variable"].sum())

    # Scale + PCA on HVG
    adata_hvg = adata[:, adata.var["highly_variable"]].copy()
    sc.pp.scale(adata_hvg, max_value=10)
    n_comps = min(n_pcs, adata_hvg.n_vars - 1, adata_hvg.n_obs - 1)
    sc.tl.pca(adata_hvg, n_comps=n_comps)

    # Copy embeddings back
    adata.obsm["X_pca"] = adata_hvg.obsm["X_pca"]
    adata.uns["pca"] = adata_hvg.uns.get("pca", {})
    if "PCs" in adata_hvg.varm:
        adata.varm["PCs"] = np.zeros((adata.n_vars, n_comps))
        hvg_mask = adata.var["highly_variable"].values
        adata.varm["PCs"][hvg_mask] = adata_hvg.varm["PCs"]

    # Neighbors + UMAP + Leiden
    n_pcs_use = min(n_comps, 30)
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs_use)
    sc.tl.umap(adata)
    sc.tl.leiden(adata, resolution=leiden_resolution, flavor="igraph")

    n_clusters = adata.obs["leiden"].nunique()
    logger.info("Leiden clustering: %d clusters (resolution=%.2f)", n_clusters, leiden_resolution)

    store_analysis_metadata(
        adata, skill_name, "scanpy_standard",
        params={
            "min_genes": min_genes, "min_cells": min_cells,
            "max_mt_pct": max_mt_pct, "n_top_hvg": n_hvg,
            "n_pcs": n_comps, "n_neighbors": n_neighbors,
            "leiden_resolution": leiden_resolution, "species": species,
        },
    )

    summary = {
        "n_cells_raw": n_cells_raw,
        "n_genes_raw": n_genes_raw,
        "n_cells_filtered": n_cells_filtered,
        "n_genes_filtered": n_genes_filtered,
        "n_hvg": int(adata.var["highly_variable"].sum()),
        "n_clusters": n_clusters,
        "has_spatial": get_spatial_key(adata) is not None,
        "cluster_sizes": adata.obs["leiden"].value_counts().to_dict(),
    }
    return adata, summary
