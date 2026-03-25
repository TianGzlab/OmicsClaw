"""Ambient RNA removal utilities for single-cell analysis.

Provides CellBender and SoupX-based methods for estimating and removing
ambient RNA contamination from droplet-based scRNA-seq data.

Adapted from validated reference scripts (remove_ambient_rna.py).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

if TYPE_CHECKING:
    from anndata import AnnData

from . import dependency_manager as dm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CellBender
# ---------------------------------------------------------------------------


def run_cellbender(
    raw_h5: Union[str, Path],
    expected_cells: int,
    total_droplets: Optional[int] = None,
    output_dir: Union[str, Path] = "results/cellbender",
    epochs: int = 200,
    fpr: float = 0.01,
    use_cuda: bool = True,
    **kwargs: Any,
) -> AnnData:
    """Run CellBender ``remove-background`` via CLI subprocess.

    CellBender uses a deep generative model to distinguish cell-containing
    droplets from empty droplets and to remove ambient RNA counts.

    Parameters
    ----------
    raw_h5
        Path to raw (unfiltered) 10X ``.h5`` file from CellRanger.
    expected_cells
        Expected number of real cells in the dataset.
    total_droplets
        Total number of droplets to consider.  When *None*, defaults to
        ``3 * expected_cells`` which is a widely used heuristic.
    output_dir
        Directory to write CellBender output files.
    epochs
        Number of training epochs for the variational autoencoder.
    fpr
        Target false-positive rate for ambient count removal.
    use_cuda
        Attempt to run on GPU.  Falls back to CPU if CUDA is unavailable.
    **kwargs
        Additional CLI flags forwarded to ``cellbender remove-background``
        as ``--key value`` pairs.

    Returns
    -------
    AnnData
        Corrected count matrix loaded from the CellBender output file,
        with metadata stored in ``adata.uns["cellbender"]``.

    Raises
    ------
    FileNotFoundError
        If *raw_h5* does not exist.
    RuntimeError
        If the CellBender command exits with a non-zero status.
    """
    import scanpy as sc

    raw_h5 = Path(raw_h5)
    if not raw_h5.exists():
        raise FileNotFoundError(f"Raw H5 file not found: {raw_h5}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_h5 = output_dir / "cellbender_output.h5"

    if total_droplets is None:
        total_droplets = 3 * expected_cells
        logger.info(
            "total_droplets not specified; defaulting to 3 x expected_cells = %d",
            total_droplets,
        )

    # Verify cellbender CLI is available
    if shutil.which("cellbender") is None:
        raise RuntimeError(
            "CellBender CLI not found on PATH.\n"
            "Install: pip install cellbender\n"
            "See: https://cellbender.readthedocs.io/"
        )

    # Build CLI command
    cmd = [
        "cellbender", "remove-background",
        "--input", str(raw_h5),
        "--output", str(output_h5),
        "--expected-cells", str(expected_cells),
        "--total-droplets-included", str(total_droplets),
        "--epochs", str(epochs),
        "--fpr", str(fpr),
    ]
    if use_cuda:
        cmd.append("--cuda")

    # Forward extra keyword arguments as CLI flags
    for key, value in kwargs.items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cmd.append(flag)
        else:
            cmd.extend([flag, str(value)])

    logger.info("Running CellBender: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Log stderr for diagnostics
        logger.error("CellBender stderr:\n%s", result.stderr)
        raise RuntimeError(
            f"CellBender exited with code {result.returncode}.\n"
            f"stderr: {result.stderr[:2000]}"
        )

    if result.stdout:
        logger.info("CellBender stdout:\n%s", result.stdout[-1000:])

    # CellBender writes an output file with the corrected matrix.
    # The actual filename may have a suffix appended (e.g. _filtered.h5).
    # Try the expected output first, then fall back to the filtered variant.
    output_filtered = output_dir / "cellbender_output_filtered.h5"
    if output_filtered.exists():
        load_path = output_filtered
    elif output_h5.exists():
        load_path = output_h5
    else:
        raise FileNotFoundError(
            f"CellBender output not found. Expected: {output_h5} or {output_filtered}"
        )

    logger.info("Loading CellBender output from: %s", load_path)
    adata = sc.read_10x_h5(str(load_path))

    # Store metadata for downstream retrieval
    adata.uns["cellbender"] = {
        "raw_h5": str(raw_h5),
        "output_h5": str(load_path),
        "expected_cells": expected_cells,
        "total_droplets": total_droplets,
        "epochs": epochs,
        "fpr": fpr,
        "use_cuda": use_cuda,
    }

    logger.info(
        "CellBender complete: %d cells x %d genes", adata.n_obs, adata.n_vars
    )
    return adata


# ---------------------------------------------------------------------------
# SoupX (Python implementation)
# ---------------------------------------------------------------------------


def _quick_cluster(adata_filtered: AnnData, resolution: float = 0.5) -> np.ndarray:
    """Perform quick Leiden clustering for SoupX when no clusters are provided.

    Parameters
    ----------
    adata_filtered
        Filtered AnnData (cells only, raw counts).
    resolution
        Leiden clustering resolution.

    Returns
    -------
    numpy.ndarray
        Cluster labels as an integer array aligned to ``adata_filtered.obs_names``.
    """
    import scanpy as sc

    logger.info("No clusters provided; performing quick Leiden clustering ...")
    tmp = adata_filtered.copy()
    sc.pp.normalize_total(tmp, target_sum=1e4)
    sc.pp.log1p(tmp)
    sc.pp.highly_variable_genes(tmp, n_top_genes=2000, subset=True)
    sc.pp.scale(tmp, max_value=10)
    sc.tl.pca(tmp, n_comps=min(30, tmp.n_vars - 1))
    sc.pp.neighbors(tmp, n_neighbors=15, n_pcs=min(30, tmp.obsm["X_pca"].shape[1]))
    sc.tl.leiden(tmp, resolution=resolution)

    clusters = tmp.obs["leiden"].astype(int).values
    n_clusters = len(np.unique(clusters))
    logger.info("Quick clustering produced %d clusters", n_clusters)
    return clusters


def _estimate_ambient_profile(raw_matrix: np.ndarray, cell_mask: np.ndarray) -> np.ndarray:
    """Estimate the ambient RNA profile from empty droplets.

    Empty droplets are those *not* in the filtered (cell-containing) set.
    The ambient profile is the normalised mean expression across empty
    droplets.

    Parameters
    ----------
    raw_matrix
        Raw count matrix (all droplets, genes as columns).
    cell_mask
        Boolean mask indicating which rows are real cells.

    Returns
    -------
    numpy.ndarray
        Ambient expression profile (length = number of genes), normalised
        to sum to 1.
    """
    from scipy import sparse

    empty_mask = ~cell_mask

    if sparse.issparse(raw_matrix):
        empty_counts = np.asarray(raw_matrix[empty_mask].sum(axis=0)).flatten()
    else:
        empty_counts = np.asarray(raw_matrix[empty_mask].sum(axis=0)).flatten()

    total = empty_counts.sum()
    if total == 0:
        logger.warning("No counts in empty droplets; returning uniform ambient profile")
        return np.ones(raw_matrix.shape[1]) / raw_matrix.shape[1]

    ambient_profile = empty_counts / total
    logger.info(
        "Ambient profile estimated from %d empty droplets (%.0f total counts)",
        empty_mask.sum(),
        total,
    )
    return ambient_profile


def estimate_contamination_fraction(
    counts: np.ndarray,
    ambient_profile: np.ndarray,
    clusters: np.ndarray,
) -> float:
    """Estimate the global ambient RNA contamination fraction (rho).

    Uses a marker-gene heuristic: genes expressed in fewer than 10 %% of
    clusters are considered cluster-specific markers.  For these genes the
    expected ambient contribution can be estimated by comparing observed
    counts in "off" clusters (where the gene should not be expressed) to
    the ambient profile, yielding a correlation-based contamination
    estimate.

    Parameters
    ----------
    counts
        Cell-by-gene count matrix (dense or sparse).
    ambient_profile
        Normalised ambient expression vector (length = n_genes).
    clusters
        Integer cluster labels aligned to rows of *counts*.

    Returns
    -------
    float
        Estimated contamination fraction, clipped to ``[0, 0.5]``.
    """
    from scipy import sparse

    if sparse.issparse(counts):
        counts_dense = np.asarray(counts.toarray())
    else:
        counts_dense = np.asarray(counts)

    unique_clusters = np.unique(clusters)
    n_clusters = len(unique_clusters)

    if n_clusters < 2:
        logger.warning(
            "Only %d cluster(s) found; cannot estimate contamination via "
            "marker-gene heuristic. Returning default rho=0.1",
            n_clusters,
        )
        return 0.1

    # ---- Per-cluster mean expression ----
    cluster_means = np.zeros((n_clusters, counts_dense.shape[1]))
    for i, cl in enumerate(unique_clusters):
        mask = clusters == cl
        cluster_means[i] = counts_dense[mask].mean(axis=0)

    # Binarise: a gene is "expressed" in a cluster if its mean > 0.5
    expressed = cluster_means > 0.5
    # Fraction of clusters where gene is expressed
    frac_expressed = expressed.sum(axis=0) / n_clusters

    # Marker genes: expressed in < 10% of clusters (but at least 1)
    marker_mask = (frac_expressed > 0) & (frac_expressed < 0.10)
    n_markers = marker_mask.sum()

    if n_markers < 5:
        # Relax threshold to < 20%
        marker_mask = (frac_expressed > 0) & (frac_expressed < 0.20)
        n_markers = marker_mask.sum()
        logger.info("Relaxed marker threshold to <20%% of clusters (%d markers)", n_markers)

    if n_markers == 0:
        logger.warning("No suitable marker genes found; returning default rho=0.1")
        return 0.1

    logger.info("Using %d marker genes for contamination estimation", n_markers)

    # ---- Correlation-based estimation ----
    # For each marker gene, compute contamination in clusters where it is OFF
    rho_estimates: list[float] = []
    marker_indices = np.where(marker_mask)[0]

    for gene_idx in marker_indices:
        off_clusters = unique_clusters[~expressed[:, gene_idx]]
        if len(off_clusters) == 0:
            continue

        off_mask = np.isin(clusters, off_clusters)
        observed_mean = counts_dense[off_mask, gene_idx].mean()
        total_mean = counts_dense[off_mask].mean(axis=0).sum()

        if total_mean == 0:
            continue

        # Expected ambient contribution for this gene
        ambient_expected = ambient_profile[gene_idx] * total_mean
        if ambient_expected > 0:
            rho_gene = observed_mean / ambient_expected
            rho_estimates.append(rho_gene)

    if len(rho_estimates) == 0:
        logger.warning("Could not compute any rho estimates; returning default 0.1")
        return 0.1

    rho = float(np.median(rho_estimates))
    rho = float(np.clip(rho, 0.0, 0.5))

    logger.info(
        "Estimated contamination fraction rho=%.4f (from %d marker genes)",
        rho,
        len(rho_estimates),
    )
    return rho


def run_soupx_python(
    raw_matrix_dir: Union[str, Path],
    filtered_matrix_dir: Union[str, Path],
    clusters: Optional[np.ndarray] = None,
    output_dir: Union[str, Path] = "results/soupx",
) -> AnnData:
    """Pure-Python implementation of the SoupX ambient RNA removal workflow.

    Reads raw (unfiltered) and filtered (cell-containing) count matrices,
    estimates an ambient RNA profile from empty droplets, computes a
    contamination fraction, and subtracts the estimated ambient counts.

    Parameters
    ----------
    raw_matrix_dir
        Directory with raw (unfiltered) CellRanger output
        (``barcodes.tsv``, ``features.tsv``/``genes.tsv``, ``matrix.mtx``).
    filtered_matrix_dir
        Directory with filtered CellRanger output (cells only).
    clusters
        Pre-computed cluster labels for filtered cells.  If *None*, a quick
        Leiden clustering is performed automatically.
    output_dir
        Directory to save corrected output and diagnostic files.

    Returns
    -------
    AnnData
        Corrected count matrix with ambient RNA removed.  Metadata is
        stored in ``adata.uns["soupx"]``.

    Raises
    ------
    FileNotFoundError
        If either matrix directory does not exist.
    """
    import scanpy as sc
    from scipy import sparse

    raw_matrix_dir = Path(raw_matrix_dir)
    filtered_matrix_dir = Path(filtered_matrix_dir)
    output_dir = Path(output_dir)

    if not raw_matrix_dir.exists():
        raise FileNotFoundError(f"Raw matrix directory not found: {raw_matrix_dir}")
    if not filtered_matrix_dir.exists():
        raise FileNotFoundError(
            f"Filtered matrix directory not found: {filtered_matrix_dir}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Load data ----
    logger.info("Loading raw matrix from: %s", raw_matrix_dir)
    adata_raw = sc.read_10x_mtx(str(raw_matrix_dir), var_names="gene_symbols")

    logger.info("Loading filtered matrix from: %s", filtered_matrix_dir)
    adata_filtered = sc.read_10x_mtx(str(filtered_matrix_dir), var_names="gene_symbols")

    logger.info(
        "Raw: %d droplets x %d genes  |  Filtered: %d cells x %d genes",
        adata_raw.n_obs,
        adata_raw.n_vars,
        adata_filtered.n_obs,
        adata_filtered.n_vars,
    )

    # ---- Align gene space ----
    shared_genes = list(set(adata_raw.var_names) & set(adata_filtered.var_names))
    shared_genes.sort()
    adata_raw = adata_raw[:, shared_genes].copy()
    adata_filtered = adata_filtered[:, shared_genes].copy()
    logger.info("Shared gene space: %d genes", len(shared_genes))

    # ---- Quick clustering if needed ----
    if clusters is None:
        clusters = _quick_cluster(adata_filtered)
    else:
        if len(clusters) != adata_filtered.n_obs:
            raise ValueError(
                f"Cluster labels length ({len(clusters)}) does not match "
                f"number of filtered cells ({adata_filtered.n_obs})"
            )

    # ---- Estimate ambient profile ----
    cell_barcodes = set(adata_filtered.obs_names)
    cell_mask = np.array([bc in cell_barcodes for bc in adata_raw.obs_names])
    raw_X = adata_raw.X
    ambient_profile = _estimate_ambient_profile(raw_X, cell_mask)

    # ---- Estimate contamination fraction ----
    rho = estimate_contamination_fraction(
        adata_filtered.X, ambient_profile, clusters
    )

    # ---- Correct counts ----
    logger.info("Correcting counts with rho=%.4f ...", rho)
    filtered_X = adata_filtered.X

    if sparse.issparse(filtered_X):
        cell_totals = np.asarray(filtered_X.sum(axis=1)).flatten()
    else:
        cell_totals = np.asarray(filtered_X.sum(axis=1)).flatten()

    # Expected ambient counts per cell = rho * cell_total * ambient_profile
    ambient_counts = rho * cell_totals[:, np.newaxis] * ambient_profile[np.newaxis, :]

    if sparse.issparse(filtered_X):
        corrected = np.asarray(filtered_X.toarray()) - ambient_counts
    else:
        corrected = np.asarray(filtered_X) - ambient_counts

    # Floor at zero — counts cannot be negative
    corrected = np.maximum(corrected, 0)
    # Round to integers (count data)
    corrected = np.round(corrected).astype(np.float32)

    adata_corrected = adata_filtered.copy()
    adata_corrected.X = sparse.csr_matrix(corrected)

    # ---- Store metadata ----
    adata_corrected.uns["soupx"] = {
        "method": "soupx_python",
        "rho": float(rho),
        "n_raw_droplets": int(adata_raw.n_obs),
        "n_empty_droplets": int((~cell_mask).sum()),
        "n_cells": int(adata_filtered.n_obs),
        "n_genes": int(len(shared_genes)),
        "raw_matrix_dir": str(raw_matrix_dir),
        "filtered_matrix_dir": str(filtered_matrix_dir),
    }

    # Save corrected data
    out_path = output_dir / "soupx_corrected.h5ad"
    adata_corrected.write_h5ad(out_path)
    logger.info("Saved SoupX-corrected data to: %s", out_path)

    logger.info(
        "SoupX correction complete: %d cells x %d genes (rho=%.4f)",
        adata_corrected.n_obs,
        adata_corrected.n_vars,
        rho,
    )
    return adata_corrected


# ---------------------------------------------------------------------------
# Contamination estimation (post-hoc)
# ---------------------------------------------------------------------------


def estimate_contamination(adata: AnnData) -> float:
    """Retrieve the estimated contamination fraction from a corrected AnnData.

    Reads from ``adata.uns["cellbender"]`` or ``adata.uns["soupx"]``,
    depending on which method was used.

    Parameters
    ----------
    adata
        AnnData object that has been processed by :func:`run_cellbender`
        or :func:`run_soupx_python`.

    Returns
    -------
    float
        Estimated contamination fraction.  Returns ``NaN`` if no ambient
        removal metadata is found.
    """
    if "soupx" in adata.uns:
        rho = adata.uns["soupx"].get("rho", float("nan"))
        logger.info("Contamination fraction from SoupX: %.4f", rho)
        return float(rho)

    if "cellbender" in adata.uns:
        fpr = adata.uns["cellbender"].get("fpr", float("nan"))
        logger.info(
            "CellBender target FPR: %.4f (exact rho not stored; "
            "use CellBender logs for per-cell estimates)",
            fpr,
        )
        return float(fpr)

    logger.warning(
        "No ambient removal metadata found in adata.uns. "
        "Run run_cellbender() or run_soupx_python() first."
    )
    return float("nan")


# ---------------------------------------------------------------------------
# Before / after comparison
# ---------------------------------------------------------------------------


def compare_before_after(
    adata_before: AnnData,
    adata_after: AnnData,
    marker_genes: list[str],
    output_dir: Union[str, Path],
) -> None:
    """Compare total counts before and after ambient RNA removal.

    Creates a scatter plot of per-cell total counts (before vs. after) and,
    for each supplied marker gene, a side-by-side comparison of expression
    distributions.

    Parameters
    ----------
    adata_before
        AnnData **before** ambient RNA removal (raw / filtered counts).
    adata_after
        AnnData **after** ambient RNA removal (corrected counts).
    marker_genes
        List of gene symbols to highlight.  Genes not present in both
        objects are silently skipped.
    output_dir
        Directory where figures will be saved via ``save_figure``.
    """
    from .viz_utils import save_figure

    import matplotlib.pyplot as plt
    from scipy import sparse

    output_dir = Path(output_dir)

    # ---- Align cells ----
    shared_cells = list(
        set(adata_before.obs_names) & set(adata_after.obs_names)
    )
    if len(shared_cells) == 0:
        logger.warning(
            "No shared cell barcodes between before and after objects; "
            "skipping comparison."
        )
        return

    before = adata_before[shared_cells, :]
    after = adata_after[shared_cells, :]

    logger.info("Comparing %d shared cells before/after ambient removal", len(shared_cells))

    # ---- Total counts scatter ----
    if sparse.issparse(before.X):
        counts_before = np.asarray(before.X.sum(axis=1)).flatten()
    else:
        counts_before = np.asarray(before.X.sum(axis=1)).flatten()

    if sparse.issparse(after.X):
        counts_after = np.asarray(after.X.sum(axis=1)).flatten()
    else:
        counts_after = np.asarray(after.X.sum(axis=1)).flatten()

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(counts_before, counts_after, s=1, alpha=0.3, color="#8da0cb")

    # Diagonal reference line
    max_val = max(counts_before.max(), counts_after.max())
    ax.plot([0, max_val], [0, max_val], "r--", linewidth=1, label="y = x")

    ax.set_xlabel("Total Counts (Before)")
    ax.set_ylabel("Total Counts (After)")
    ax.set_title("Ambient RNA Removal: Total Counts")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.3)

    save_figure(fig, output_dir, "ambient_total_counts_scatter.png")

    # ---- Per-marker-gene comparison ----
    shared_genes = list(set(before.var_names) & set(after.var_names))
    valid_markers = [g for g in marker_genes if g in shared_genes]

    if not valid_markers:
        logger.warning(
            "None of the supplied marker genes (%s) found in both objects; "
            "skipping per-gene comparison.",
            ", ".join(marker_genes),
        )
        return

    n_markers = len(valid_markers)
    fig, axes = plt.subplots(1, n_markers, figsize=(4 * n_markers, 4), squeeze=False)
    axes = axes.flatten()

    for i, gene in enumerate(valid_markers):
        if sparse.issparse(before[:, gene].X):
            expr_before = np.asarray(before[:, gene].X.toarray()).flatten()
        else:
            expr_before = np.asarray(before[:, gene].X).flatten()

        if sparse.issparse(after[:, gene].X):
            expr_after = np.asarray(after[:, gene].X.toarray()).flatten()
        else:
            expr_after = np.asarray(after[:, gene].X).flatten()

        axes[i].scatter(
            expr_before, expr_after, s=1, alpha=0.3, color="#fc8d62"
        )
        gene_max = max(expr_before.max(), expr_after.max(), 1)
        axes[i].plot(
            [0, gene_max], [0, gene_max], "r--", linewidth=1
        )
        axes[i].set_xlabel("Before")
        axes[i].set_ylabel("After")
        axes[i].set_title(gene)
        axes[i].spines["top"].set_visible(False)
        axes[i].spines["right"].set_visible(False)
        axes[i].grid(alpha=0.3)

    plt.suptitle("Marker Gene Expression: Before vs After", y=1.02)
    plt.tight_layout()
    save_figure(fig, output_dir, "ambient_marker_genes_comparison.png")

    logger.info(
        "Saved before/after comparison plots for %d marker genes to %s",
        len(valid_markers),
        output_dir,
    )
