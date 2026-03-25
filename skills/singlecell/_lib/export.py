"""Result export utilities for single-cell analysis.

Provides functions to save processed AnnData objects, expression matrices,
cell metadata, embedding coordinates, and plain-text summary reports.

Public API
----------
save_h5ad
export_expression_matrix
export_metadata
export_embeddings
create_summary_report
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

import pandas as pd

if TYPE_CHECKING:
    from anndata import AnnData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _estimate_h5ad_size_mb(adata: AnnData) -> float:
    """Rough in-memory size estimate in MB."""
    import scipy.sparse as sp

    total_bytes = 0

    # .X
    if sp.issparse(adata.X):
        total_bytes += adata.X.data.nbytes + adata.X.indices.nbytes + adata.X.indptr.nbytes
    elif adata.X is not None:
        total_bytes += adata.X.nbytes

    # layers
    for layer_name in adata.layers:
        layer = adata.layers[layer_name]
        if sp.issparse(layer):
            total_bytes += layer.data.nbytes + layer.indices.nbytes + layer.indptr.nbytes
        elif hasattr(layer, "nbytes"):
            total_bytes += layer.nbytes
        else:
            total_bytes += 1024 * 1024  # 1 MB fallback

    # .obsm
    for key in adata.obsm:
        val = adata.obsm[key]
        if sp.issparse(val):
            total_bytes += val.data.nbytes + val.indices.nbytes + val.indptr.nbytes
        elif hasattr(val, "nbytes"):
            total_bytes += val.nbytes

    # .obs / .var metadata (rough)
    total_bytes += adata.n_obs * len(adata.obs.columns) * 8
    total_bytes += adata.n_vars * len(adata.var.columns) * 8

    return total_bytes / (1024 * 1024)


def _check_multimodal_data(adata: AnnData) -> None:
    """Log informational messages when multimodal data (ADT, ATAC, ...) is present."""
    hints: list[str] = []

    if hasattr(adata, "obsm") and adata.obsm is not None:
        for key in adata.obsm.keys():
            kl = key.lower()
            if any(t in kl for t in ("adt", "protein", "cite", "antibody")):
                hints.append(f"ADT/protein data in .obsm['{key}']")
            if any(t in kl for t in ("atac", "peaks", "chromatin")):
                hints.append(f"ATAC/chromatin data in .obsm['{key}']")

    if hasattr(adata, "uns") and adata.uns is not None:
        for key in adata.uns.keys():
            kl = key.lower()
            if any(t in kl for t in ("adt", "protein", "cite")):
                hints.append(f"ADT/protein metadata in .uns['{key}']")

    if "feature_types" in adata.var.columns:
        feature_types = adata.var["feature_types"].unique()
        non_rna = [ft for ft in feature_types if ft not in ("Gene Expression", "gene_expression", "Gene")]
        if non_rna:
            hints.append(f"Non-RNA feature types: {non_rna}")

    if hints:
        logger.info("MULTIMODAL DATA DETECTED (RNA modality only was analysed):")
        for h in hints:
            logger.info("  %s", h)


# ---------------------------------------------------------------------------
# save_h5ad
# ---------------------------------------------------------------------------


def save_h5ad(
    adata: AnnData,
    output_file: str | Path,
    compression: str | None = "gzip",
) -> None:
    """Save *adata* to H5AD with optional compression.

    Falls back to a temporary directory if the primary write path fails
    (e.g. permission or disk-space issues), then copies the file to the
    intended location.

    After writing, a minimal integrity check is performed (file size > 10 kB).

    Parameters
    ----------
    adata : AnnData
        Object to persist.
    output_file : path-like
        Destination path.
    compression : str or None
        ``'gzip'``, ``'lzf'``, or ``None`` (default ``'gzip'``).
    """
    valid = {"gzip", "lzf", None}
    if compression not in valid:
        raise ValueError(f"Invalid compression='{compression}'.  Allowed: {valid}")

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    est_mb = _estimate_h5ad_size_mb(adata)
    n_layers = len(adata.layers)
    comp_label = compression if compression else "none"
    logger.info(
        "Saving AnnData to %s (%d cells x %d genes, %d layers, ~%.0f MB, compression=%s) ...",
        output_file,
        adata.n_obs,
        adata.n_vars,
        n_layers,
        est_mb,
        comp_label,
    )
    if est_mb > 200:
        logger.info("Large object -- write may take 30-60+ seconds.")

    # temporarily remove problematic .uns keys
    removed_uns: dict[str, object] = {}
    for key in ("rank_genes_groups_filtered",):
        if key in adata.uns:
            removed_uns[key] = adata.uns.pop(key)

    write_targets = [output_file, Path(tempfile.gettempdir()) / output_file.name]
    t0 = time.time()

    try:
        for attempt, target in enumerate(write_targets):
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                adata.write_h5ad(target, compression=compression)
                elapsed = time.time() - t0
                logger.info("Write completed in %.1fs", elapsed)

                if attempt > 0:
                    import shutil

                    shutil.copy2(target, output_file)
                    logger.info("Used fallback write path; copied to %s", output_file)

                file_mb = output_file.stat().st_size / (1024 * 1024)
                if file_mb < 0.01:
                    logger.warning("File suspiciously small (%.3f MB) -- may be corrupted.", file_mb)
                else:
                    logger.info("Saved: %s (%.1f MB)", output_file, file_mb)
                break
            except OSError as exc:
                if attempt == 0:
                    logger.warning("Primary write failed: %s.  Trying fallback ...", exc)
                else:
                    raise
    finally:
        adata.uns.update(removed_uns)


# ---------------------------------------------------------------------------
# export_expression_matrix
# ---------------------------------------------------------------------------


def export_expression_matrix(
    adata: AnnData,
    output_dir: str | Path,
    layer: str | None = None,
    use_raw: bool = False,
    var_names: list[str] | None = None,
    format: str = "csv",  # noqa: A002 -- matches reference API
) -> None:
    """Export expression matrix to CSV or TSV.

    A memory-safety check prevents dense conversion when the resulting
    array would exceed ~2 GB.

    Parameters
    ----------
    adata : AnnData
        AnnData object.
    output_dir : path-like
        Destination directory.
    layer : str, optional
        Layer to export (default ``None`` uses ``adata.X``).
    use_raw : bool
        Export ``adata.raw`` (default ``False``).
    var_names : list of str, optional
        Subset to these gene names.
    format : str
        ``'csv'`` (default) or ``'tsv'``.
    """
    import numpy as np

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting expression matrix ...")

    # -- resolve data source --------------------------------------------------
    if use_raw and adata.raw is not None:
        expr_data = adata.raw.X
        all_var_names = adata.raw.var_names
    elif layer is not None:
        expr_data = adata.layers[layer]
        all_var_names = adata.var_names
    else:
        expr_data = adata.X
        all_var_names = adata.var_names

    # -- dense conversion with safety check -----------------------------------
    if hasattr(expr_data, "toarray"):
        dense_gb = expr_data.shape[0] * expr_data.shape[1] * 8 / (1024**3)
        if dense_gb > 2:
            logger.warning(
                "Dense matrix would require ~%.1f GB (%d x %d).  "
                "Skipping CSV export -- use H5AD for large datasets.",
                dense_gb,
                expr_data.shape[0],
                expr_data.shape[1],
            )
            return
        expr_data = expr_data.toarray()

    expr_data = np.asarray(expr_data)

    expr_df = pd.DataFrame(expr_data, index=adata.obs_names, columns=all_var_names)

    if var_names is not None:
        valid_genes = [g for g in var_names if g in expr_df.columns]
        expr_df = expr_df[valid_genes]
        logger.info("  Subsetting to %d genes", len(valid_genes))

    # -- write ----------------------------------------------------------------
    sep = "\t" if format == "tsv" else ","
    suffix = "tsv" if format == "tsv" else "csv"

    if layer is not None:
        fname = f"expression_matrix_{layer}.{suffix}"
    elif use_raw:
        fname = f"expression_matrix_raw.{suffix}"
    else:
        fname = f"expression_matrix_normalized.{suffix}"

    out_path = output_dir / fname
    expr_df.to_csv(out_path, sep=sep)

    file_mb = out_path.stat().st_size / (1024 * 1024)
    logger.info("Saved: %s (%.1f MB)", out_path, file_mb)


# ---------------------------------------------------------------------------
# export_metadata
# ---------------------------------------------------------------------------


def export_metadata(
    adata: AnnData,
    output_dir: str | Path,
    columns: list[str] | None = None,
) -> None:
    """Export cell metadata to CSV.

    Parameters
    ----------
    adata : AnnData
        AnnData object.
    output_dir : path-like
        Destination directory.
    columns : list of str, optional
        Columns to export (default all).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting cell metadata ...")

    metadata = adata.obs.copy()
    if columns is not None:
        valid_cols = [c for c in columns if c in metadata.columns]
        metadata = metadata[valid_cols]
        logger.info("  Exporting %d columns", len(valid_cols))

    out_path = output_dir / "cell_metadata.csv"
    metadata.to_csv(out_path)
    logger.info("Saved: %s", out_path)


# ---------------------------------------------------------------------------
# export_embeddings
# ---------------------------------------------------------------------------


def export_embeddings(
    adata: AnnData,
    output_dir: str | Path,
    embeddings: list[str] | None = None,
) -> None:
    """Export dimensionality-reduction coordinates (PCA, UMAP, Harmony, ...).

    Parameters
    ----------
    adata : AnnData
        AnnData object.
    output_dir : path-like
        Destination directory.
    embeddings : list of str, optional
        ``obsm`` keys to export (default: all keys starting with ``X_``).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting embedding coordinates ...")

    if embeddings is None:
        embeddings = [k for k in adata.obsm.keys() if k.startswith("X_")]

    for emb_key in embeddings:
        if emb_key not in adata.obsm:
            logger.warning("  %s not found -- skipping", emb_key)
            continue

        coords = adata.obsm[emb_key]
        emb_name = emb_key.replace("X_", "").upper()
        n_dims = coords.shape[1]
        col_names = [f"{emb_name}{i + 1}" for i in range(n_dims)]

        coords_df = pd.DataFrame(coords, index=adata.obs_names, columns=col_names)
        out_path = output_dir / f"{emb_key.replace('X_', '')}_coordinates.csv"
        coords_df.to_csv(out_path)
        logger.info("  Saved: %s", out_path)


# ---------------------------------------------------------------------------
# create_summary_report
# ---------------------------------------------------------------------------


def create_summary_report(
    adata: AnnData,
    output_dir: str | Path,
    cluster_key: str = "leiden",
) -> None:
    """Write a plain-text ``analysis_summary.txt`` report.

    Parameters
    ----------
    adata : AnnData
        Processed AnnData.
    output_dir : path-like
        Destination directory.
    cluster_key : str
        Cluster / cell-type column (default ``'leiden'``).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "analysis_summary.txt"

    logger.info("Creating summary report ...")

    lines: list[str] = []
    _sep = "=" * 70

    lines.append(_sep)
    lines.append("SINGLE-CELL RNA-SEQ ANALYSIS SUMMARY")
    lines.append(_sep)
    lines.append("")

    # -- dataset info ---------------------------------------------------------
    lines.append("DATASET INFORMATION")
    lines.append("-" * 70)
    lines.append(f"Total cells: {adata.n_obs}")
    lines.append(f"Total genes: {adata.n_vars}")
    lines.append("")

    # -- QC -------------------------------------------------------------------
    if "n_genes_by_counts" in adata.obs.columns:
        lines.append("QUALITY CONTROL METRICS")
        lines.append("-" * 70)
        lines.append(f"Mean genes per cell: {adata.obs['n_genes_by_counts'].mean():.0f}")
        lines.append(f"Median genes per cell: {adata.obs['n_genes_by_counts'].median():.0f}")
        lines.append(f"Mean UMIs per cell: {adata.obs['total_counts'].mean():.0f}")
        lines.append(f"Median UMIs per cell: {adata.obs['total_counts'].median():.0f}")
        if "pct_counts_mt" in adata.obs.columns:
            lines.append(f"Mean % MT: {adata.obs['pct_counts_mt'].mean():.2f}%")
            lines.append(f"Median % MT: {adata.obs['pct_counts_mt'].median():.2f}%")
        lines.append("")

    # -- clustering -----------------------------------------------------------
    if cluster_key in adata.obs.columns:
        lines.append("CLUSTERING INFORMATION")
        lines.append("-" * 70)
        cluster_counts = adata.obs[cluster_key].value_counts().sort_index()
        lines.append(f"Number of clusters/cell types: {len(cluster_counts)}")
        lines.append("")
        lines.append("Cell type distribution:")
        for cluster, count in cluster_counts.items():
            pct = 100 * count / adata.n_obs
            lines.append(f"  {cluster}: {count} cells ({pct:.1f}%)")
        lines.append("")

    # -- doublet detection ----------------------------------------------------
    if "scrublet_detection" in adata.uns:
        info = adata.uns["scrublet_detection"]
        lines.append("DOUBLET DETECTION")
        lines.append("-" * 70)
        lines.append(
            f"Total doublets detected: {info['total_detected']} ({info['total_detected_pct']:.1f}%)"
        )
        lines.append(f"Expected doublet rate: {info['total_expected_pct']:.1f}%")
        if info.get("auto_rate"):
            lines.append("Rate estimation: Auto-scaled per batch (~0.8% per 1,000 cells)")
        if info.get("batch_stats"):
            for bs in info["batch_stats"]:
                lines.append(
                    f"  {bs['batch']}: {bs['n_cells']} cells, "
                    f"expected={bs['expected_rate']:.1%}, detected={bs['detected_rate']:.1%}"
                )
        lines.append("")

    # -- integration ----------------------------------------------------------
    if "scvi_integration" in adata.uns:
        ii = adata.uns["scvi_integration"]
        lines.append("BATCH INTEGRATION (scVI)")
        lines.append("-" * 70)
        lines.append(f"Batch key: {ii.get('batch_key', 'N/A')}")
        lines.append(f"Latent dimensions: {ii.get('n_latent', 'N/A')}")
        lines.append(f"Epochs trained: {ii.get('epochs_trained', 'N/A')}")
        lines.append(f"Final train loss: {ii.get('final_train_loss', 'N/A')}")
        lines.append(f"Final val loss: {ii.get('final_val_loss', 'N/A')}")
        lines.append("")

    # -- analysis components --------------------------------------------------
    lines.append("ANALYSIS COMPONENTS")
    lines.append("-" * 70)
    if "X_pca" in adata.obsm:
        lines.append(f"PCA: {adata.obsm['X_pca'].shape[1]} components computed")
    if "X_umap" in adata.obsm:
        lines.append("UMAP: computed")
    if "X_tsne" in adata.obsm:
        lines.append("t-SNE: computed")
    if "neighbors" in adata.uns:
        k = adata.uns["neighbors"]["params"].get("n_neighbors", "?")
        lines.append(f"Neighbor graph: k={k}")

    # -- modality -------------------------------------------------------------
    lines.append("")
    lines.append("MODALITY")
    lines.append("-" * 70)
    lines.append("Analysis modality: RNA expression only")
    if "feature_types" in adata.var.columns:
        ft = adata.var["feature_types"].unique().tolist()
        lines.append(f"Feature types in data: {ft}")
        non_rna = [f for f in ft if f not in ("Gene Expression", "gene_expression", "Gene")]
        if non_rna:
            lines.append(f"Additional modalities NOT analysed: {non_rna}")

    lines.append("")
    lines.append(_sep)

    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved: %s", out_path)
