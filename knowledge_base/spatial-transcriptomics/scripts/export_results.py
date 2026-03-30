"""
============================================================================
EXPORT SPATIAL ANALYSIS RESULTS
============================================================================

Functions:
  - export_all(): Export all results from spatial analysis

Usage:
  from export_results import export_all
  export_all(adata, output_dir="visium_results")
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime


def export_all(
    adata: 'anndata.AnnData',
    output_dir: str = "visium_results"
) -> None:
    """
    Export all spatial transcriptomics analysis results.

    Exports:
    1. adata_processed.h5ad — complete processed AnnData (CRITICAL)
    2. spatially_variable_genes.csv — SVGs with Moran's I statistics
    3. cluster_assignments.csv — spot barcodes + cluster + spatial coords
    4. neighborhood_enrichment.csv — cluster-cluster enrichment z-scores
    5. spot_metadata.csv — all obs columns
    6. analysis_summary.txt — human-readable report

    Parameters
    ----------
    adata : AnnData
        Processed AnnData from run_spatial_analysis().
    output_dir : str
        Output directory (default: "visium_results").
    """
    print("\n=== Step 4: Export Results ===\n")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Save processed h5ad (CRITICAL for downstream skills) ---
    print("1. Saving processed AnnData object...")
    h5ad_path = output_dir / "adata_processed.h5ad"
    adata_save = adata.copy()
    # Clean uns for h5ad serialization (remove non-serializable objects)
    _clean_uns_for_h5ad(adata_save)
    adata_save.write_h5ad(h5ad_path, compression='gzip')
    file_size_mb = h5ad_path.stat().st_size / (1024 * 1024)
    print(f"   ✓ {h5ad_path} ({file_size_mb:.1f} MB)")
    print(f"   (Load with: adata = sc.read_h5ad('adata_processed.h5ad'))")

    # --- 2. Spatially variable genes ---
    print("\n2. Exporting spatially variable genes...")
    svg_results = adata.uns.get('svg_results', None)
    if svg_results is not None and len(svg_results) > 0:
        svg_path = output_dir / "spatially_variable_genes.csv"
        svg_results.to_csv(svg_path)
        print(f"   ✓ {svg_path} ({len(svg_results)} genes)")
    else:
        print("   (No SVG results to export)")

    # --- 3. Cluster assignments with spatial coordinates ---
    print("\n3. Exporting cluster assignments...")
    cluster_df = pd.DataFrame({
        'barcode': adata.obs_names,
        'cluster': adata.obs['leiden'].values,
        'spatial_x': adata.obsm['spatial'][:, 0],
        'spatial_y': adata.obsm['spatial'][:, 1],
    })
    if 'total_counts' in adata.obs.columns:
        cluster_df['total_counts'] = adata.obs['total_counts'].values
    if 'n_genes_by_counts' in adata.obs.columns:
        cluster_df['n_genes'] = adata.obs['n_genes_by_counts'].values
    cluster_path = output_dir / "cluster_assignments.csv"
    cluster_df.to_csv(cluster_path, index=False)
    print(f"   ✓ {cluster_path} ({len(cluster_df)} spots)")

    # --- 4. Neighborhood enrichment ---
    print("\n4. Exporting neighborhood enrichment...")
    if 'leiden_nhood_enrichment' in adata.uns:
        zscore = adata.uns['leiden_nhood_enrichment']['zscore']
        clusters = sorted(adata.obs['leiden'].unique(), key=int)
        labels = [str(c) for c in clusters]
        nhood_df = pd.DataFrame(zscore, index=labels, columns=labels)
        nhood_path = output_dir / "neighborhood_enrichment.csv"
        nhood_df.to_csv(nhood_path)
        print(f"   ✓ {nhood_path}")
    else:
        print("   (No neighborhood enrichment results)")

    # --- 5. Full spot metadata ---
    print("\n5. Exporting spot metadata...")
    metadata_path = output_dir / "spot_metadata.csv"
    adata.obs.to_csv(metadata_path)
    print(f"   ✓ {metadata_path} ({len(adata.obs)} spots, {len(adata.obs.columns)} columns)")

    # --- 6. Analysis summary ---
    print("\n6. Generating analysis summary...")
    _write_summary(adata, output_dir)
    print(f"   ✓ {output_dir / 'analysis_summary.txt'}")

    # Final verification
    print("\n" + "=" * 50)
    print("=== Export Complete ===")
    print("=" * 50)
    print(f"\nAll results saved to: {output_dir}/")
    print(f"\nKey outputs:")
    print(f"  - adata_processed.h5ad   (Load with: adata = sc.read_h5ad(...))")
    print(f"  - spatially_variable_genes.csv")
    print(f"  - cluster_assignments.csv")
    print(f"  - neighborhood_enrichment.csv")
    print(f"  - spot_metadata.csv")
    print(f"  - analysis_summary.txt")


def _clean_uns_for_h5ad(adata) -> None:
    """Remove non-serializable objects from uns for h5ad export."""
    keys_to_check = list(adata.uns.keys())
    for key in keys_to_check:
        val = adata.uns[key]
        # Convert numpy int/float to Python native
        if isinstance(val, dict):
            adata.uns[key] = _convert_dict_types(val)
        elif isinstance(val, pd.DataFrame):
            pass  # DataFrames are fine
        elif isinstance(val, np.ndarray):
            pass  # Arrays are fine
        elif isinstance(val, (np.integer, np.floating)):
            adata.uns[key] = val.item()


def _convert_dict_types(d: dict) -> dict:
    """Convert numpy types in dict to native Python for JSON serialization."""
    result = {}
    for k, v in d.items():
        if isinstance(v, (np.integer,)):
            result[k] = int(v)
        elif isinstance(v, (np.floating,)):
            result[k] = float(v)
        elif isinstance(v, np.ndarray):
            result[k] = v
        elif isinstance(v, dict):
            result[k] = _convert_dict_types(v)
        else:
            result[k] = v
    return result


def _write_summary(adata, output_dir: Path) -> None:
    """Write human-readable analysis summary."""
    params = adata.uns.get('spatial_analysis_params', {})

    with open(output_dir / 'analysis_summary.txt', 'w') as f:
        f.write("=" * 70 + "\n")
        f.write("SPATIAL TRANSCRIPTOMICS ANALYSIS SUMMARY\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")

        f.write("DATASET\n")
        f.write("-" * 70 + "\n")
        f.write(f"Spots (after QC):  {adata.n_obs}\n")
        f.write(f"Genes:             {adata.n_vars}\n")
        f.write(f"Clusters (Leiden): {params.get('n_clusters', 'N/A')}\n")
        f.write(f"SVGs (FDR < 0.05): {params.get('n_svgs', 'N/A')}\n\n")

        f.write("QC FILTERING\n")
        f.write("-" * 70 + "\n")
        f.write(f"Initial spots:     {params.get('n_spots_initial', 'N/A')}\n")
        f.write(f"After filtering:   {params.get('n_spots_after', 'N/A')}\n")
        n_init = params.get('n_spots_initial', 0)
        n_after = params.get('n_spots_after', 0)
        if n_init > 0:
            f.write(f"Retention:         {100 * n_after / n_init:.1f}%\n")
        f.write(f"min_genes:         {params.get('min_genes', 'N/A')}\n")
        f.write(f"max_pct_mito:      {params.get('max_pct_mito', 'N/A')}%\n\n")

        f.write("ANALYSIS PARAMETERS\n")
        f.write("-" * 70 + "\n")
        f.write(f"HVGs:              {params.get('n_top_genes', 'N/A')}\n")
        f.write(f"PCA components:    {params.get('n_pcs', 'N/A')}\n")
        f.write(f"Leiden resolution: {params.get('resolution', 'N/A')}\n")
        f.write(f"SVG permutations:  {params.get('svgs_n_perms', 'N/A')}\n\n")

        # Cluster distribution
        if 'leiden' in adata.obs.columns:
            f.write("CLUSTER DISTRIBUTION\n")
            f.write("-" * 70 + "\n")
            for cluster in sorted(adata.obs['leiden'].unique(), key=int):
                count = (adata.obs['leiden'] == cluster).sum()
                pct = 100 * count / adata.n_obs
                f.write(f"  Cluster {cluster:>3}: {count:>5} spots ({pct:>5.1f}%)\n")
            f.write("\n")

        # Top SVGs
        svg_results = adata.uns.get('svg_results', None)
        if svg_results is not None and len(svg_results) > 0:
            f.write("TOP SPATIALLY VARIABLE GENES\n")
            f.write("-" * 70 + "\n")
            top20 = svg_results.head(20)
            for gene, row in top20.iterrows():
                f.write(f"  {gene:<15} Moran's I = {row['I']:.4f}  "
                        f"FDR = {row['pval_norm_fdr_bh']:.2e}\n")
            f.write("\n")

        f.write("=" * 70 + "\n")
        f.write("Pipeline: Squidpy + Scanpy spatial transcriptomics analysis\n")
        f.write("=" * 70 + "\n")

