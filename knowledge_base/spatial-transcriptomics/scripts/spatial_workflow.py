"""
============================================================================
SPATIAL TRANSCRIPTOMICS ANALYSIS WORKFLOW
============================================================================

Complete Visium spatial analysis: QC -> filtering -> normalization ->
clustering -> spatial neighbors -> SVGs -> neighborhood enrichment ->
co-occurrence.

Functions:
  - run_spatial_analysis(): Execute complete spatial workflow

Usage:
  from spatial_workflow import run_spatial_analysis
  adata = run_spatial_analysis(adata)
"""

import numpy as np
import pandas as pd
from typing import Optional, List


def run_spatial_analysis(
    adata: 'anndata.AnnData',
    min_genes: int = 200,
    min_cells: int = 10,
    max_pct_mito: float = 50.0,
    n_top_genes: int = 2000,
    n_pcs: int = 30,
    resolution: float = 0.8,
    n_neighbors: int = 15,
    svgs_n_perms: int = 100,
    svgs_n_jobs: int = 1,
    output_dir: str = "visium_results"
) -> 'anndata.AnnData':
    """
    Run complete spatial transcriptomics analysis.

    Pipeline:
    1. QC metrics (mitochondrial %, total counts, genes per spot)
    2. Filter spots (min_genes, max_mito)
    3. Normalize + log1p
    4. HVG selection (seurat_v3 on raw counts)
    5. PCA + Neighbors + UMAP + Leiden clustering
    6. Spatial neighbors graph
    7. Spatially variable genes (Moran's I)
    8. Neighborhood enrichment
    9. Co-occurrence analysis

    Parameters
    ----------
    adata : AnnData
        Raw Visium data (from load_example_data).
    min_genes : int
        Minimum genes per spot (default: 200).
    min_cells : int
        Minimum spots per gene (default: 10).
    max_pct_mito : float
        Maximum mitochondrial percentage (default: 50.0; heart tissue is MT-rich).
    n_top_genes : int
        Number of highly variable genes (default: 2000).
    n_pcs : int
        Number of PCA components (default: 30).
    resolution : float
        Leiden clustering resolution (default: 0.8).
    n_neighbors : int
        Number of neighbors for expression graph (default: 15).
    svgs_n_perms : int
        Permutations for Moran's I (default: 100).
    svgs_n_jobs : int
        Parallel jobs for Moran's I (default: 1).
    output_dir : str
        Output directory (default: "visium_results").

    Returns
    -------
    AnnData
        Processed adata with clustering, SVGs, enrichment results attached.
    """
    import scanpy as sc
    import squidpy as sq
    import os

    os.makedirs(output_dir, exist_ok=True)

    print("\n=== Step 2: Spatial Transcriptomics Analysis ===\n")
    n_spots_initial = adata.n_obs

    # --- 1. QC metrics ---
    print("1. Calculating QC metrics...")
    adata.var['mt'] = adata.var_names.str.startswith('MT-')
    sc.pp.calculate_qc_metrics(
        adata, qc_vars=['mt'], percent_top=None, log1p=False, inplace=True
    )
    print(f"   Median genes/spot: {adata.obs['n_genes_by_counts'].median():.0f}")
    print(f"   Median counts/spot: {adata.obs['total_counts'].median():.0f}")
    print(f"   Median %MT: {adata.obs['pct_counts_mt'].median():.1f}%")

    # --- 2. Filter spots ---
    print(f"\n2. Filtering spots (min_genes={min_genes}, max_mito={max_pct_mito}%)...")

    # Store raw counts BEFORE any processing
    adata.layers['counts'] = adata.X.copy()

    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)
    adata = adata[adata.obs['pct_counts_mt'] < max_pct_mito, :].copy()

    n_spots_after = adata.n_obs
    retention = 100 * n_spots_after / n_spots_initial
    print(f"   Spots: {n_spots_initial} -> {n_spots_after} ({retention:.1f}% retained)")

    # --- 3. Normalize ---
    print("\n3. Normalizing (target sum + log1p)...")
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # Store normalized counts for SVG computation later
    adata.layers['normalized'] = adata.X.copy()

    # --- 4. HVG selection ---
    print(f"\n4. Selecting {n_top_genes} highly variable genes...")
    sc.pp.highly_variable_genes(
        adata, n_top_genes=n_top_genes, flavor='seurat_v3',
        layer='counts'
    )
    n_hvgs = adata.var['highly_variable'].sum()
    print(f"   Highly variable genes: {n_hvgs}")

    # --- 5. PCA + Neighbors + UMAP + Leiden ---
    print("\n5. Dimensionality reduction and clustering...")
    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, n_comps=n_pcs, svd_solver='arpack')
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs)
    sc.tl.umap(adata)
    sc.tl.leiden(adata, resolution=resolution, key_added='leiden')

    n_clusters = adata.obs['leiden'].nunique()
    print(f"   PCA: {n_pcs} components")
    print(f"   Leiden clusters: {n_clusters} (resolution={resolution})")

    # --- 6. Spatial neighbors ---
    print("\n6. Building spatial neighbors graph...")
    sq.gr.spatial_neighbors(adata, coord_type='grid', n_neighs=6)
    n_edges = adata.obsp['spatial_connectivities'].nnz
    print(f"   Spatial graph: {n_edges} edges")

    # --- 7. Spatially variable genes (Moran's I) ---
    print(f"\n7. Computing spatially variable genes (Moran's I, n_perms={svgs_n_perms})...")

    # Restore normalized expression for SVG computation (scale modifies X)
    adata.X = adata.layers['normalized'].copy()

    sq.gr.spatial_autocorr(
        adata,
        mode='moran',
        n_perms=svgs_n_perms,
        n_jobs=svgs_n_jobs
    )

    # Extract significant SVGs
    moranI = adata.uns['moranI'].copy()
    svgs = moranI[moranI['pval_norm_fdr_bh'] < 0.05].sort_values('I', ascending=False)
    n_svgs = len(svgs)
    print(f"   Spatially variable genes (FDR < 0.05): {n_svgs}")
    if n_svgs > 0:
        top5 = svgs.index[:5].tolist()
        print(f"   Top SVGs: {', '.join(top5)}")

    # Store SVG results
    adata.uns['svg_results'] = svgs

    # --- 8. Neighborhood enrichment ---
    print("\n8. Computing neighborhood enrichment...")
    sq.gr.nhood_enrichment(adata, cluster_key='leiden')
    print(f"   Enrichment matrix: {n_clusters}x{n_clusters}")

    # --- 9. Co-occurrence ---
    print("\n9. Computing co-occurrence scores...")
    sq.gr.co_occurrence(adata, cluster_key='leiden')
    print(f"   Co-occurrence computed for {n_clusters} clusters")

    # --- Store analysis parameters ---
    adata.uns['spatial_analysis_params'] = {
        'min_genes': min_genes,
        'min_cells': min_cells,
        'max_pct_mito': max_pct_mito,
        'n_top_genes': n_top_genes,
        'n_pcs': n_pcs,
        'resolution': resolution,
        'n_neighbors': n_neighbors,
        'svgs_n_perms': svgs_n_perms,
        'n_spots_initial': int(n_spots_initial),
        'n_spots_after': int(n_spots_after),
        'n_clusters': int(n_clusters),
        'n_svgs': int(n_svgs),
    }

    print("\n" + "=" * 50)
    print("✓ Spatial analysis completed successfully!")
    print("=" * 50)
    print(f"\n  Spots analyzed: {n_spots_after}")
    print(f"  Clusters found: {n_clusters}")
    print(f"  SVGs identified: {n_svgs}")

    return adata

