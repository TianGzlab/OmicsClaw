"""
============================================================================
RESULTS EXPORT
============================================================================

This script exports processed data, tables, and figures.

Functions:
  - export_anndata_results(): Export all results from analysis
  - save_h5ad(): Save AnnData object
  - export_expression_matrix(): Export expression matrices
  - export_metadata(): Export cell metadata
  - export_embeddings(): Export dimensionality reduction coordinates

Usage:
  from export_results import export_anndata_results
  export_anndata_results(adata, output_dir='results', cluster_key='cell_type')
"""

import tempfile
import time
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd


def _check_multimodal_data(adata: 'AnnData') -> None:
    """
    Check if AnnData contains multimodal data (ADT/protein, ATAC, etc.)
    that was not analyzed in the RNA-only workflow.

    Prints informational messages so users and reports are clear about
    which modalities were analyzed.
    """
    multimodal_hints = []

    # Check .obsm for protein/ADT embeddings
    if hasattr(adata, 'obsm') and adata.obsm is not None:
        for key in adata.obsm.keys():
            key_lower = key.lower()
            if any(term in key_lower for term in ['adt', 'protein', 'cite', 'antibody']):
                multimodal_hints.append(f"ADT/protein data detected in .obsm['{key}']")
            if any(term in key_lower for term in ['atac', 'peaks', 'chromatin']):
                multimodal_hints.append(f"ATAC/chromatin data detected in .obsm['{key}']")

    # Check .uns for modality info
    if hasattr(adata, 'uns') and adata.uns is not None:
        for key in adata.uns.keys():
            key_lower = key.lower()
            if any(term in key_lower for term in ['adt', 'protein', 'cite']):
                multimodal_hints.append(f"ADT/protein metadata in .uns['{key}']")

    # Check var for feature types (common in 10X multiome/CITE-seq)
    if 'feature_types' in adata.var.columns:
        feature_types = adata.var['feature_types'].unique()
        non_rna = [ft for ft in feature_types
                   if ft not in ['Gene Expression', 'gene_expression', 'Gene']]
        if non_rna:
            multimodal_hints.append(
                f"Non-RNA feature types in .var['feature_types']: {non_rna}"
            )

    if multimodal_hints:
        print(f"\n  [INFO] MULTIMODAL DATA DETECTED:")
        print(f"     This analysis used RNA expression data only.")
        print(f"     Additional modalities found but not analyzed:")
        for hint in multimodal_hints:
            print(f"       - {hint}")
        print(f"     If this is CITE-seq data, ADT/protein features were not included")
        print(f"     in normalization, integration, or clustering.")
        print(f"     Add a note to reports: 'RNA modality only; ADT features not analyzed.'")


def _estimate_h5ad_size_mb(adata: 'AnnData') -> float:
    """Estimate H5AD file size in MB from AnnData dimensions."""
    import scipy.sparse as sp

    total_bytes = 0

    # .X matrix
    if sp.issparse(adata.X):
        total_bytes += adata.X.data.nbytes + adata.X.indices.nbytes + adata.X.indptr.nbytes
    elif adata.X is not None:
        total_bytes += adata.X.nbytes

    # layers
    for layer_name in adata.layers:
        layer = adata.layers[layer_name]
        if sp.issparse(layer):
            total_bytes += layer.data.nbytes + layer.indices.nbytes + layer.indptr.nbytes
        elif hasattr(layer, 'nbytes'):
            total_bytes += layer.nbytes
        else:
            total_bytes += 1024 * 1024  # 1 MB fallback for unknown types

    # .obsm (PCA, UMAP, etc.)
    for key in adata.obsm:
        val = adata.obsm[key]
        if sp.issparse(val):
            total_bytes += val.data.nbytes + val.indices.nbytes + val.indptr.nbytes
        elif hasattr(val, 'nbytes'):
            total_bytes += val.nbytes

    # .obs and .var metadata (rough estimate)
    total_bytes += adata.n_obs * len(adata.obs.columns) * 8
    total_bytes += adata.n_vars * len(adata.var.columns) * 8

    return total_bytes / (1024 * 1024)


def save_h5ad(
    adata: 'AnnData',
    output_file: Union[str, Path],
    compression: Optional[str] = 'lzf'
) -> None:
    """
    Save AnnData object to H5AD format.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    output_file : str or Path
        Output file path
    compression : str, optional
        Compression method: 'gzip', 'lzf', None (default: 'lzf').
        lzf is ~5-10x faster than gzip with ~10-20% larger files.

    Returns
    -------
    None
        Saves file to disk
    """
    # Validate compression parameter
    valid_compressions = {'gzip', 'lzf', None}
    if compression not in valid_compressions:
        raise ValueError(
            f"Invalid compression='{compression}'. "
            f"Allowed: 'gzip', 'lzf', or None. "
            f"Note: H5AD uses 'lzf' (not 'zlib')."
        )

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Print size estimate and compression info
    est_mb = _estimate_h5ad_size_mb(adata)
    n_layers = len(adata.layers)
    comp_label = compression if compression else "none"
    print(f"Saving AnnData object to {output_file}...")
    print(f"  Object: {adata.n_obs} cells x {adata.n_vars} genes, "
          f"{n_layers} layer(s), estimated ~{est_mb:.0f} MB uncompressed")
    print(f"  Compression: {comp_label}")
    if est_mb > 200:
        print(f"  NOTE: Large object — write may take 30-60+ seconds")

    # Temporarily remove problematic .uns keys (no full adata.copy() needed)
    _removed_uns = {}
    _problematic_keys = ['rank_genes_groups_filtered']
    for key in _problematic_keys:
        if key in adata.uns:
            _removed_uns[key] = adata.uns.pop(key)

    # Try primary path, then fallback to temp dir if write fails
    write_targets = [output_file, Path(tempfile.gettempdir()) / output_file.name]
    t0 = time.time()
    try:
        for attempt, target_path in enumerate(write_targets):
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"  Writing H5AD file...")
                adata.write_h5ad(target_path, compression=compression)
                elapsed = time.time() - t0
                print(f"  Write completed in {elapsed:.1f}s")
                # If we used fallback, copy to original location
                if attempt > 0:
                    import shutil
                    shutil.copy2(target_path, output_file)
                    print(f"  (Used fallback write path, copied to {output_file})")
                # Verify file integrity
                file_size_mb = output_file.stat().st_size / (1024 * 1024)
                if file_size_mb < 0.01:
                    print(f"  WARNING: File suspiciously small ({file_size_mb:.3f} MB). May be corrupted.")
                else:
                    print(f"  Saved: {output_file} ({file_size_mb:.1f} MB)")
                break
            except OSError as e:
                if attempt == 0:
                    print(f"  WARNING: Primary write failed: {e}. Trying fallback path...")
                else:
                    raise
    finally:
        # Always restore removed .uns keys
        adata.uns.update(_removed_uns)


def export_expression_matrix(
    adata: 'AnnData',
    output_dir: Union[str, Path] = ".",
    layer: Optional[str] = None,
    use_raw: bool = False,
    var_names: Optional[List[str]] = None,
    format: str = 'csv'
) -> None:
    """
    Export expression matrix to CSV or TSV.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    output_dir : str or Path, optional
        Output directory (default: ".")
    layer : str, optional
        Layer to export (default: None, uses .X)
    use_raw : bool, optional
        Use raw counts (default: False)
    var_names : list of str, optional
        Subset to these genes (default: None, exports all)
    format : str, optional
        File format: 'csv' or 'tsv' (default: 'csv')

    Returns
    -------
    None
        Saves file to disk
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Exporting expression matrix...")

    # Get expression data
    if use_raw and adata.raw is not None:
        expr_data = adata.raw.X
        var_names_all = adata.raw.var_names
    elif layer is not None:
        expr_data = adata.layers[layer]
        var_names_all = adata.var_names
    else:
        expr_data = adata.X
        var_names_all = adata.var_names

    # Convert to dense if sparse (with memory safety check)
    if hasattr(expr_data, 'toarray'):
        dense_gb = expr_data.shape[0] * expr_data.shape[1] * 8 / (1024 ** 3)
        if dense_gb > 2:
            print(f"  WARNING: Dense matrix would require ~{dense_gb:.1f} GB RAM "
                  f"({expr_data.shape[0]} x {expr_data.shape[1]}). "
                  f"Skipping CSV export — use H5AD for large datasets.")
            return
        expr_data = expr_data.toarray()

    # Create dataframe
    expr_df = pd.DataFrame(
        expr_data,
        index=adata.obs_names,
        columns=var_names_all
    )

    # Subset genes if specified
    if var_names is not None:
        valid_genes = [g for g in var_names if g in expr_df.columns]
        expr_df = expr_df[valid_genes]
        print(f"  Subsetting to {len(valid_genes)} genes")

    # Save to file
    sep = '\t' if format == 'tsv' else ','
    suffix = 'tsv' if format == 'tsv' else 'csv'

    if layer is not None:
        output_file = output_dir / f"expression_matrix_{layer}.{suffix}"
    elif use_raw:
        output_file = output_dir / f"expression_matrix_raw.{suffix}"
    else:
        output_file = output_dir / f"expression_matrix_normalized.{suffix}"

    expr_df.to_csv(output_file, sep=sep)

    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"  Saved: {output_file} ({file_size_mb:.1f} MB)")


def export_metadata(
    adata: 'AnnData',
    output_dir: Union[str, Path] = ".",
    columns: Optional[List[str]] = None
) -> None:
    """
    Export cell metadata to CSV.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    output_dir : str or Path, optional
        Output directory (default: ".")
    columns : list of str, optional
        Columns to export (default: None, exports all)

    Returns
    -------
    None
        Saves file to disk
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Exporting cell metadata...")

    # Get metadata
    metadata = adata.obs.copy()

    # Subset columns if specified
    if columns is not None:
        valid_cols = [c for c in columns if c in metadata.columns]
        metadata = metadata[valid_cols]
        print(f"  Exporting {len(valid_cols)} columns")

    # Save to file
    output_file = output_dir / "cell_metadata.csv"
    metadata.to_csv(output_file)

    print(f"  Saved: {output_file}")


def export_embeddings(
    adata: 'AnnData',
    output_dir: Union[str, Path] = ".",
    embeddings: Optional[List[str]] = None
) -> None:
    """
    Export dimensionality reduction coordinates.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    output_dir : str or Path, optional
        Output directory (default: ".")
    embeddings : list of str, optional
        Embeddings to export (default: None, exports all)

    Returns
    -------
    None
        Saves files to disk
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Exporting dimensionality reduction coordinates...")

    # Determine which embeddings to export
    if embeddings is None:
        embeddings = [key for key in adata.obsm.keys() if key.startswith('X_')]

    for emb_key in embeddings:
        if emb_key not in adata.obsm:
            print(f"  Warning: {emb_key} not found, skipping")
            continue

        # Get coordinates
        coords = adata.obsm[emb_key]

        # Create column names
        emb_name = emb_key.replace('X_', '').upper()
        n_dims = coords.shape[1]
        col_names = [f'{emb_name}{i+1}' for i in range(n_dims)]

        # Create dataframe
        coords_df = pd.DataFrame(
            coords,
            index=adata.obs_names,
            columns=col_names
        )

        # Save to file
        output_file = output_dir / f"{emb_key.replace('X_', '')}_coordinates.csv"
        coords_df.to_csv(output_file)

        print(f"  Saved: {output_file}")


def export_anndata_results(
    adata: 'AnnData',
    output_dir: Union[str, Path] = "results",
    cluster_key: str = 'cell_type',
    include_raw: bool = True,
    include_normalized: bool = True,
    include_metadata: bool = True,
    include_embeddings: bool = True,
    include_h5ad: bool = True,
) -> None:
    """
    Export all results from scRNA-seq analysis.

    Parameters
    ----------
    adata : AnnData
        Processed AnnData object
    output_dir : str or Path, optional
        Output directory (default: "results")
    cluster_key : str, optional
        Cluster/cell type column (default: 'cell_type')
    include_raw : bool, optional
        Export raw counts (default: True)
    include_normalized : bool, optional
        Export normalized expression (default: True)
    include_metadata : bool, optional
        Export cell metadata (default: True)
    include_embeddings : bool, optional
        Export UMAP/PCA coordinates (default: True)
    include_h5ad : bool, optional
        Save H5AD file (default: True)

    Returns
    -------
    None
        Saves all files to output_dir
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting analysis results to {output_dir}...")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")

    if cluster_key in adata.obs.columns:
        n_clusters = adata.obs[cluster_key].nunique()
        print(f"  Clusters/Cell types: {n_clusters}")

    # Check for multimodal data (CITE-seq ADT, ATAC, etc.)
    _check_multimodal_data(adata)

    # Export H5AD
    if include_h5ad:
        save_h5ad(adata, output_dir / "adata_processed.h5ad")

    # Export expression matrices
    if include_raw and 'counts' in adata.layers:
        export_expression_matrix(
            adata,
            output_dir=output_dir,
            layer='counts',
            format='csv'
        )

    if include_normalized:
        export_expression_matrix(
            adata,
            output_dir=output_dir,
            layer=None,
            format='csv'
        )

    # Export metadata
    if include_metadata:
        export_metadata(adata, output_dir=output_dir)

    # Export embeddings
    if include_embeddings:
        export_embeddings(adata, output_dir=output_dir)

    # Create summary report
    create_summary_report(adata, output_dir, cluster_key)

    print("\n" + "=" * 50)
    print("=== Export Complete ===")
    print("=" * 50)
    print(f"\nAll results saved to: {output_dir}")
    print("  - adata_processed.h5ad (Load with: adata = sc.read_h5ad('adata_processed.h5ad'))")
    print("  - expression matrices (CSV)")
    print("  - cell_metadata.csv")
    print("  - UMAP/PCA coordinates (CSV)")
    print("  - analysis_summary.txt")


def create_summary_report(
    adata: 'AnnData',
    output_dir: Union[str, Path],
    cluster_key: str = 'cell_type'
) -> None:
    """
    Create text summary report of analysis.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    output_dir : str or Path
        Output directory
    cluster_key : str, optional
        Cluster/cell type column (default: 'cell_type')

    Returns
    -------
    None
        Saves report to disk
    """
    output_dir = Path(output_dir)
    output_file = output_dir / "analysis_summary.txt"

    print("Creating summary report...")

    with open(output_file, 'w') as f:
        f.write("=" * 70 + "\n")
        f.write("SINGLE-CELL RNA-SEQ ANALYSIS SUMMARY\n")
        f.write("=" * 70 + "\n\n")

        # Dataset info
        f.write("DATASET INFORMATION\n")
        f.write("-" * 70 + "\n")
        f.write(f"Total cells: {adata.n_obs}\n")
        f.write(f"Total genes: {adata.n_vars}\n\n")

        # QC metrics
        if 'n_genes_by_counts' in adata.obs.columns:
            f.write("QUALITY CONTROL METRICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mean genes per cell: {adata.obs['n_genes_by_counts'].mean():.0f}\n")
            f.write(f"Median genes per cell: {adata.obs['n_genes_by_counts'].median():.0f}\n")
            f.write(f"Mean UMIs per cell: {adata.obs['total_counts'].mean():.0f}\n")
            f.write(f"Median UMIs per cell: {adata.obs['total_counts'].median():.0f}\n")

            if 'pct_counts_mt' in adata.obs.columns:
                f.write(f"Mean % MT: {adata.obs['pct_counts_mt'].mean():.2f}%\n")
                f.write(f"Median % MT: {adata.obs['pct_counts_mt'].median():.2f}%\n")
            f.write("\n")

        # Clustering info
        if cluster_key in adata.obs.columns:
            f.write("CLUSTERING INFORMATION\n")
            f.write("-" * 70 + "\n")
            cluster_counts = adata.obs[cluster_key].value_counts().sort_index()
            f.write(f"Number of clusters/cell types: {len(cluster_counts)}\n\n")

            f.write("Cell type distribution:\n")
            for cluster, count in cluster_counts.items():
                pct = 100 * count / adata.n_obs
                f.write(f"  {cluster}: {count} cells ({pct:.1f}%)\n")
            f.write("\n")

        # Doublet detection info
        if 'scrublet_detection' in adata.uns:
            f.write("DOUBLET DETECTION\n")
            f.write("-" * 70 + "\n")
            scrub_info = adata.uns['scrublet_detection']
            f.write(f"Total doublets detected: {scrub_info['total_detected']} "
                    f"({scrub_info['total_detected_pct']:.1f}%)\n")
            f.write(f"Expected doublet rate: {scrub_info['total_expected_pct']:.1f}%\n")
            if scrub_info.get('auto_rate'):
                f.write("Rate estimation: Auto-scaled per batch (~0.8% per 1,000 cells)\n")
            if scrub_info.get('batch_stats'):
                for bs in scrub_info['batch_stats']:
                    f.write(f"  {bs['batch']}: {bs['n_cells']} cells, "
                            f"expected={bs['expected_rate']:.1%}, "
                            f"detected={bs['detected_rate']:.1%}\n")
            f.write("\n")

        # Integration info
        if 'scvi_integration' in adata.uns:
            f.write("BATCH INTEGRATION (scVI)\n")
            f.write("-" * 70 + "\n")
            int_info = adata.uns['scvi_integration']
            f.write(f"Batch key: {int_info.get('batch_key', 'N/A')}\n")
            f.write(f"Latent dimensions: {int_info.get('n_latent', 'N/A')}\n")
            f.write(f"Epochs trained: {int_info.get('epochs_trained', 'N/A')}\n")
            f.write(f"Final train loss: {int_info.get('final_train_loss', 'N/A')}\n")
            f.write(f"Final val loss: {int_info.get('final_val_loss', 'N/A')}\n")
            f.write("\n")

        # Analysis components
        f.write("ANALYSIS COMPONENTS\n")
        f.write("-" * 70 + "\n")
        if 'X_pca' in adata.obsm:
            n_pcs = adata.obsm['X_pca'].shape[1]
            f.write(f"PCA: {n_pcs} components computed\n")
        if 'X_umap' in adata.obsm:
            f.write("UMAP: computed\n")
        if 'X_tsne' in adata.obsm:
            f.write("t-SNE: computed\n")
        if 'neighbors' in adata.uns:
            k = adata.uns['neighbors']['params']['n_neighbors']
            f.write(f"Neighbor graph: k={k}\n")

        # Modality info
        f.write("\nMODALITY\n")
        f.write("-" * 70 + "\n")
        f.write("Analysis modality: RNA expression only\n")
        if 'feature_types' in adata.var.columns:
            feature_types = adata.var['feature_types'].unique().tolist()
            f.write(f"Feature types in data: {feature_types}\n")
            non_rna = [ft for ft in feature_types
                       if ft not in ['Gene Expression', 'gene_expression', 'Gene']]
            if non_rna:
                f.write(f"Additional modalities NOT analyzed: {non_rna}\n")

        f.write("\n" + "=" * 70 + "\n")

    print(f"  Saved: {output_file}")

