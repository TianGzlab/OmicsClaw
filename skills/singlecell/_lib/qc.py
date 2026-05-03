"""Quality control metrics, filtering, and QC visualization.

Adapted from validated reference scripts (qc_metrics.py, plot_qc.py, filter_cells.py).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from anndata import AnnData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Species-specific patterns
# ---------------------------------------------------------------------------

def get_species_mito_pattern(species: str) -> str:
    """Return regex pattern for mitochondrial genes.

    Parameters
    ----------
    species
        ``"human"`` or ``"mouse"``.
    """
    patterns = {"human": "MT-", "mouse": "mt-"}
    species = species.lower()
    if species not in patterns:
        raise ValueError("Species must be 'human' or 'mouse'")
    return patterns[species]


def get_species_ribo_pattern(species: str) -> str:
    """Return regex pattern for ribosomal genes.

    Parameters
    ----------
    species
        ``"human"`` or ``"mouse"``.
    """
    patterns = {"human": "^RP[SL]", "mouse": "^Rp[sl]"}
    species = species.lower()
    if species not in patterns:
        raise ValueError("Species must be 'human' or 'mouse'")
    return patterns[species]


# ---------------------------------------------------------------------------
# Tissue-specific QC thresholds
# ---------------------------------------------------------------------------

_TISSUE_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "pbmc": {"min_genes": 200, "max_genes": 2500, "max_mt": 5,
             "description": "Peripheral blood mononuclear cells"},
    "brain": {"min_genes": 200, "max_genes": 6000, "max_mt": 10,
              "description": "Brain tissue (neurons have many genes)"},
    "tumor": {"min_genes": 200, "max_genes": 5000, "max_mt": 20,
              "description": "Tumor samples (higher mt% tolerated)"},
    "kidney": {"min_genes": 200, "max_genes": 4000, "max_mt": 15,
               "description": "Kidney tissue"},
    "liver": {"min_genes": 200, "max_genes": 4000, "max_mt": 15,
              "description": "Liver tissue"},
    "heart": {"min_genes": 200, "max_genes": 4000, "max_mt": 15,
              "description": "Heart tissue (cardiomyocytes have high mt%)"},
    "default": {"min_genes": 200, "max_genes": 4000, "max_mt": 10,
                "description": "General tissue (adjust based on your data)"},
}


def get_tissue_qc_thresholds(tissue: str) -> Dict[str, Any]:
    """Return recommended QC thresholds for a tissue type.

    Parameters
    ----------
    tissue
        One of: ``pbmc``, ``brain``, ``tumor``, ``kidney``, ``liver``,
        ``heart``, ``default``.
    """
    tissue = tissue.lower()
    if tissue not in _TISSUE_THRESHOLDS:
        logger.warning("Tissue '%s' not recognized. Using default thresholds. "
                       "Available: %s", tissue, ", ".join(_TISSUE_THRESHOLDS))
        tissue = "default"

    result = _TISSUE_THRESHOLDS[tissue]
    logger.info("QC thresholds for %s: min_genes=%d, max_genes=%d, max_mt=%.0f%%",
                result["description"], result["min_genes"], result["max_genes"], result["max_mt"])
    return result


# ---------------------------------------------------------------------------
# QC metric calculation
# ---------------------------------------------------------------------------

def calculate_qc_metrics(
    adata: AnnData,
    species: str = "human",
    calculate_ribo: bool = True,
    inplace: bool = True,
) -> AnnData:
    """Calculate QC metrics and add them to ``adata.obs``.

    Adds: ``n_genes_by_counts``, ``total_counts``, ``pct_counts_mt``,
    ``pct_counts_ribo`` (optional), ``log10_total_counts``,
    ``log10_n_genes_by_counts``.

    Parameters
    ----------
    adata
        AnnData with raw counts.
    species
        ``"human"`` or ``"mouse"`` (determines mitochondrial gene pattern).
    calculate_ribo
        Also calculate ribosomal percentage.
    inplace
        Modify *adata* in place.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    logger.info("Calculating QC metrics for %s", species)

    # Mitochondrial genes
    mito_pattern = get_species_mito_pattern(species)
    adata.var["mt"] = adata.var_names.str.startswith(mito_pattern)
    logger.info("  Mitochondrial genes: %d", adata.var["mt"].sum())

    qc_vars = []

    mt_count = int(adata.var["mt"].sum())
    if mt_count > 0:
        qc_vars.append("mt")
    else:
        logger.warning("  No mitochondrial genes matched the selected species prefixes")

    # Ribosomal genes
    if calculate_ribo:
        ribo_pattern = get_species_ribo_pattern(species)
        adata.var["ribo"] = adata.var_names.str.match(ribo_pattern)
        ribo_count = int(adata.var["ribo"].sum())
        logger.info("  Ribosomal genes: %d", ribo_count)
        if ribo_count > 0:
            qc_vars.append("ribo")
        else:
            logger.warning("  No ribosomal genes matched the selected species prefixes")

    if not qc_vars:
        logger.warning("  No species-specific QC feature sets were detected; only counts-based metrics will be computed")

    sc.pp.calculate_qc_metrics(adata, qc_vars=qc_vars, percent_top=None,
                               log1p=False, inplace=True)

    # Log-transformed metrics
    adata.obs["log10_total_counts"] = np.log10(adata.obs["total_counts"] + 1)
    adata.obs["log10_n_genes_by_counts"] = np.log10(adata.obs["n_genes_by_counts"] + 1)

    logger.info("  Median genes/cell: %.0f", adata.obs["n_genes_by_counts"].median())
    logger.info("  Median UMIs/cell: %.0f", adata.obs["total_counts"].median())
    if "pct_counts_mt" in adata.obs.columns:
        logger.info("  Median MT%%: %.2f%%", adata.obs["pct_counts_mt"].median())

    return adata


def ensure_qc_metrics(
    adata: AnnData,
    *,
    species: str = "human",
    calculate_ribo: bool = True,
    inplace: bool = True,
) -> AnnData:
    """Return an object with the core QC metrics available in ``adata.obs``."""
    if not inplace:
        adata = adata.copy()

    required = {"n_genes_by_counts", "total_counts", "pct_counts_mt"}
    if required.issubset(set(adata.obs.columns)):
        return adata
    return calculate_qc_metrics(
        adata,
        species=species,
        calculate_ribo=calculate_ribo,
        inplace=True,
    )


# ---------------------------------------------------------------------------
# Outlier detection
# ---------------------------------------------------------------------------

def batch_mad_outlier_detection(
    adata: AnnData,
    batch_key: str = "batch",
    metrics: Optional[List[str]] = None,
    nmads: float = 5,
    inplace: bool = True,
) -> AnnData:
    """Batch-aware MAD outlier detection.

    Adapts to batch-specific distributions instead of fixed thresholds.
    Creates ``adata.obs['outlier']`` (bool) and per-metric columns.

    Parameters
    ----------
    adata
        AnnData with QC metrics.
    batch_key
        Column in ``adata.obs`` for batch labels.
    metrics
        QC metrics to check. Default:
        ``['log10_total_counts', 'log10_n_genes_by_counts', 'pct_counts_mt']``.
    nmads
        Number of MADs from median to define outliers.
    inplace
        Modify in place.
    """
    if not inplace:
        adata = adata.copy()

    if metrics is None:
        metrics = ["log10_total_counts", "log10_n_genes_by_counts", "pct_counts_mt"]

    if batch_key not in adata.obs.columns:
        logger.warning("'%s' not found in adata.obs. Treating as single batch.", batch_key)
        adata.obs[batch_key] = "batch_1"

    # Ensure log metrics exist
    if "log10_total_counts" not in adata.obs.columns:
        adata.obs["log10_total_counts"] = np.log10(adata.obs["total_counts"] + 1)
    if "log10_n_genes_by_counts" not in adata.obs.columns:
        adata.obs["log10_n_genes_by_counts"] = np.log10(adata.obs["n_genes_by_counts"] + 1)

    logger.info("Batch-aware MAD outlier detection (nmads=%s) ...", nmads)
    adata.obs["outlier"] = False

    for metric in metrics:
        if metric not in adata.obs.columns:
            logger.warning("Metric '%s' not found, skipping.", metric)
            continue

        adata.obs[f"outlier_{metric}"] = False

        for batch in adata.obs[batch_key].unique():
            mask = adata.obs[batch_key] == batch
            vals = adata.obs.loc[mask, metric]
            median = np.median(vals)
            mad = np.median(np.abs(vals - median))

            if mad == 0:
                logger.warning("MAD=0 for %s in batch %s, skipping.", metric, batch)
                continue

            lower, upper = median - nmads * mad, median + nmads * mad
            outliers = (vals < lower) | (vals > upper)
            adata.obs.loc[mask, f"outlier_{metric}"] = outliers
            adata.obs.loc[mask, "outlier"] |= outliers

            n_out = outliers.sum()
            if n_out > 0:
                logger.info("  %s [%s]: %d outliers (%.2f - %.2f)",
                            metric, batch, n_out, lower, upper)

    n_total = adata.obs["outlier"].sum()
    logger.info("Total outliers: %d (%.1f%%)", n_total, 100 * n_total / adata.n_obs)
    return adata


def mark_outliers_fixed(
    adata: AnnData,
    tissue: str = "pbmc",
    min_genes: Optional[int] = None,
    max_genes: Optional[int] = None,
    max_mt: Optional[float] = None,
    inplace: bool = True,
) -> AnnData:
    """Mark outliers using fixed tissue-specific thresholds.

    For single-batch data or when tissue-specific guidelines exist.
    Creates ``adata.obs['outlier']`` (bool).

    Parameters
    ----------
    adata
        AnnData with QC metrics.
    tissue
        Tissue type for default thresholds.
    min_genes, max_genes, max_mt
        Override tissue defaults.
    inplace
        Modify in place.
    """
    if not inplace:
        adata = adata.copy()

    thresholds = get_tissue_qc_thresholds(tissue)
    min_genes = min_genes if min_genes is not None else thresholds["min_genes"]
    max_genes = max_genes if max_genes is not None else thresholds["max_genes"]
    max_mt = max_mt if max_mt is not None else thresholds["max_mt"]

    logger.info("Fixed QC thresholds: min_genes=%d, max_genes=%d, max_mt=%.0f%%",
                min_genes, max_genes, max_mt)

    adata.obs["outlier"] = (
        (adata.obs["n_genes_by_counts"] < min_genes)
        | (adata.obs["n_genes_by_counts"] > max_genes)
        | (adata.obs["pct_counts_mt"] > max_mt)
    )
    adata.obs["outlier_low_genes"] = adata.obs["n_genes_by_counts"] < min_genes
    adata.obs["outlier_high_genes"] = adata.obs["n_genes_by_counts"] > max_genes
    adata.obs["outlier_high_mt"] = adata.obs["pct_counts_mt"] > max_mt

    n_total = adata.obs["outlier"].sum()
    logger.info("Outliers: %d (%.1f%%)", n_total, 100 * n_total / adata.n_obs)
    return adata


# ---------------------------------------------------------------------------
# Cell / gene filtering
# ---------------------------------------------------------------------------

def filter_cells_by_qc(
    adata: AnnData,
    min_genes: int = 200,
    max_genes: Optional[int] = None,
    min_counts: Optional[int] = None,
    max_counts: Optional[int] = None,
    max_mt_percent: Optional[float] = None,
    inplace: bool = False,
) -> AnnData:
    """Filter cells based on QC thresholds.

    Parameters
    ----------
    adata
        AnnData with QC metrics.
    min_genes, max_genes
        Gene count bounds.
    min_counts, max_counts
        UMI count bounds.
    max_mt_percent
        Maximum mitochondrial percentage.
    inplace
        Modify in place.
    """
    n_before = adata.n_obs
    logger.info("Filtering cells (starting with %d) ...", n_before)

    keep = np.ones(adata.n_obs, dtype=bool)

    if min_genes is not None:
        m = adata.obs["n_genes_by_counts"] >= min_genes
        logger.info("  < %d genes: %d removed", min_genes, (~m).sum())
        keep &= m
    if max_genes is not None:
        m = adata.obs["n_genes_by_counts"] <= max_genes
        logger.info("  > %d genes: %d removed", max_genes, (~m).sum())
        keep &= m
    if min_counts is not None:
        m = adata.obs["total_counts"] >= min_counts
        logger.info("  < %d counts: %d removed", min_counts, (~m).sum())
        keep &= m
    if max_counts is not None:
        m = adata.obs["total_counts"] <= max_counts
        logger.info("  > %d counts: %d removed", max_counts, (~m).sum())
        keep &= m
    if max_mt_percent is not None:
        m = adata.obs["pct_counts_mt"] <= max_mt_percent
        logger.info("  > %.0f%% MT: %d removed", max_mt_percent, (~m).sum())
        keep &= m

    if inplace:
        adata._inplace_subset_obs(keep)
        result = adata
    else:
        result = adata[keep, :].copy()

    logger.info("Retained %d cells (%.1f%%)", result.n_obs, 100 * result.n_obs / n_before)
    return result


def filter_cells_by_tissue(
    adata: AnnData,
    tissue: str,
    inplace: bool = False,
) -> AnnData:
    """Filter cells using tissue-specific QC thresholds."""
    thresholds = get_tissue_qc_thresholds(tissue)
    return filter_cells_by_qc(
        adata,
        min_genes=thresholds["min_genes"],
        max_genes=thresholds["max_genes"],
        max_mt_percent=thresholds["max_mt"],
        inplace=inplace,
    )


def filter_genes(
    adata: AnnData,
    min_cells: int = 3,
    min_counts: Optional[int] = None,
    inplace: bool = True,
) -> AnnData:
    """Filter genes by minimum cells or counts.

    Parameters
    ----------
    adata
        AnnData object.
    min_cells
        Minimum number of cells expressing a gene.
    min_counts
        Minimum total counts for a gene.
    inplace
        Modify in place.
    """
    import scanpy as sc

    n_before = adata.n_vars
    logger.info("Filtering genes (starting with %d) ...", n_before)

    if not inplace:
        adata = adata.copy()

    if min_cells is not None:
        sc.pp.filter_genes(adata, min_cells=min_cells)
    if min_counts is not None:
        sc.pp.filter_genes(adata, min_counts=min_counts)

    logger.info("Retained %d genes (%.1f%%)", adata.n_vars, 100 * adata.n_vars / n_before)
    return adata


def summarize_filter_statistics(
    adata_before: AnnData,
    adata_after: AnnData,
    *,
    filter_stats: dict[str, int],
) -> dict[str, Any]:
    """Build a stable filtering summary payload."""
    n_cells_before = int(adata_before.n_obs)
    n_cells_after = int(adata_after.n_obs)
    n_genes_before = int(adata_before.n_vars)
    n_genes_after = int(adata_after.n_vars)
    cell_retention_rate = n_cells_after / max(n_cells_before, 1)
    gene_retention_rate = n_genes_after / max(n_genes_before, 1)
    return {
        "n_cells_before": n_cells_before,
        "n_cells_after": n_cells_after,
        "cell_retention_rate": round(cell_retention_rate, 4),
        "cells_retained_pct": round(100 * cell_retention_rate, 2),
        "n_genes_before": n_genes_before,
        "n_genes_after": n_genes_after,
        "gene_retention_rate": round(gene_retention_rate, 4),
        "genes_retained_pct": round(100 * gene_retention_rate, 2),
        "filter_stats": {str(key): int(value) for key, value in filter_stats.items()},
    }


def apply_threshold_filtering(
    adata: AnnData,
    *,
    min_genes: int = 200,
    max_genes: Optional[int] = None,
    min_counts: Optional[int] = None,
    max_counts: Optional[int] = None,
    max_mt_percent: Optional[float] = None,
    min_cells: int = 3,
    tissue: str | None = None,
    filter_doublets: bool = True,
    doublet_score_threshold: float = 0.25,
) -> tuple[AnnData, dict[str, Any], dict[str, Any]]:
    """Apply cell and gene filtering with a reusable summary payload.

    Doublet removal (``filter_doublets=True``) is applied automatically when
    ``predicted_doublet`` or ``doublet_score`` columns are present in
    ``adata.obs`` (written by sc-doublet-detection).  If neither column exists
    the step is silently skipped — no error, no change in behaviour.
    """
    effective_params = {
        "min_genes": min_genes,
        "max_genes": max_genes,
        "min_counts": min_counts,
        "max_counts": max_counts,
        "max_mt_percent": max_mt_percent,
        "min_cells": min_cells,
        "tissue": tissue,
        "filter_doublets": filter_doublets,
        "doublet_score_threshold": doublet_score_threshold,
    }
    if tissue:
        thresholds = get_tissue_qc_thresholds(tissue)
        effective_params["min_genes"] = thresholds.get("min_genes", effective_params["min_genes"])
        effective_params["max_genes"] = thresholds.get("max_genes", effective_params["max_genes"])
        effective_params["max_mt_percent"] = thresholds.get("max_mt", effective_params["max_mt_percent"])

    filtered = filter_cells_by_qc(
        adata,
        min_genes=effective_params["min_genes"],
        max_genes=effective_params["max_genes"],
        min_counts=effective_params["min_counts"],
        max_counts=effective_params["max_counts"],
        max_mt_percent=effective_params["max_mt_percent"],
        inplace=False,
    )

    filter_stats: dict[str, int] = {}
    if effective_params["min_genes"] is not None:
        filter_stats["min_genes_removed"] = int((adata.obs["n_genes_by_counts"] < effective_params["min_genes"]).sum())
    if effective_params["max_genes"] is not None:
        filter_stats["max_genes_removed"] = int((adata.obs["n_genes_by_counts"] > effective_params["max_genes"]).sum())
    if effective_params["min_counts"] is not None and "total_counts" in adata.obs:
        filter_stats["min_counts_removed"] = int((adata.obs["total_counts"] < effective_params["min_counts"]).sum())
    if effective_params["max_counts"] is not None and "total_counts" in adata.obs:
        filter_stats["max_counts_removed"] = int((adata.obs["total_counts"] > effective_params["max_counts"]).sum())
    if effective_params["max_mt_percent"] is not None and "pct_counts_mt" in adata.obs:
        filter_stats["mt_removed"] = int((adata.obs["pct_counts_mt"] > effective_params["max_mt_percent"]).sum())
    if "outlier" in adata.obs.columns:
        filter_stats["outliers_removed"] = int(adata.obs["outlier"].sum())

    # --- Doublet removal (auto-detect upstream sc-doublet-detection output) ---
    if filter_doublets:
        has_predicted = "predicted_doublet" in filtered.obs.columns
        has_score = "doublet_score" in filtered.obs.columns
        if has_predicted:
            dbl_mask = filtered.obs["predicted_doublet"].astype(bool)
            n_doublets = int(dbl_mask.sum())
            if n_doublets > 0:
                filter_stats["doublets_removed"] = n_doublets
                filtered = filtered[~dbl_mask, :].copy()
                logger.info("Removed %d doublets (predicted_doublet column)", n_doublets)
        elif has_score:
            dbl_mask = filtered.obs["doublet_score"] >= doublet_score_threshold
            n_doublets = int(dbl_mask.sum())
            if n_doublets > 0:
                filter_stats["doublets_removed"] = n_doublets
                filtered = filtered[~dbl_mask, :].copy()
                logger.info(
                    "Removed %d doublets (doublet_score >= %.2f)", n_doublets, doublet_score_threshold
                )

    filtered = filter_genes(filtered, min_cells=effective_params["min_cells"], inplace=True)
    summary = summarize_filter_statistics(adata, filtered, filter_stats=filter_stats)
    return filtered, summary, effective_params


# ---------------------------------------------------------------------------
# Doublet-related helpers (used by both qc and doublet-detection skill)
# ---------------------------------------------------------------------------

def calculate_doublet_scores(
    adata: AnnData,
    expected_doublet_rate: float = 0.06,
    random_state: int = 0,
) -> AnnData:
    """Calculate doublet scores using Scrublet (simple, single-batch).

    Adds ``doublet_score`` and ``predicted_doublet`` to ``adata.obs``.
    """
    from . import dependency_manager as dm
    scr = dm.require("scrublet", feature="doublet detection")

    logger.info("Calculating doublet scores with Scrublet ...")
    scrub = scr.Scrublet(adata.X, expected_doublet_rate=expected_doublet_rate,
                         random_state=random_state)
    scores, predicted = scrub.scrub_doublets(min_counts=2, min_cells=3,
                                             min_gene_variability_pctl=85,
                                             n_prin_comps=30)
    adata.obs["doublet_score"] = scores
    adata.obs["predicted_doublet"] = predicted

    n_doublets = predicted.sum()
    logger.info("  Predicted doublets: %d (%.1f%%)", n_doublets, 100 * n_doublets / len(predicted))
    return adata


def _estimate_doublet_rate(n_cells: int) -> float:
    """Estimate expected doublet rate for 10X Chromium (~0.8% per 1,000 cells)."""
    rate = 0.008 * (n_cells / 1000)
    return max(0.01, min(rate, 0.15))


def run_scrublet_detection(
    adata: AnnData,
    batch_key: Optional[str] = None,
    expected_doublet_rate: Optional[float] = None,
    auto_rate: bool = True,
    random_state: int = 0,
    min_counts: int = 2,
    min_cells: int = 3,
    n_prin_comps: int = 30,
) -> AnnData:
    """Run Scrublet doublet detection, optionally per batch.

    When *batch_key* is provided, runs Scrublet separately per batch and
    estimates the expected doublet rate from cell count automatically.

    Adds ``doublet_score``, ``predicted_doublet`` to ``adata.obs`` and
    stores batch stats in ``adata.uns['scrublet_detection']``.
    """
    from . import dependency_manager as dm
    scr = dm.require("scrublet", feature="doublet detection")

    logger.info("Running Scrublet doublet detection ...")

    scores = np.zeros(adata.n_obs)
    predicted = np.zeros(adata.n_obs, dtype=bool)
    batch_stats: list[dict] = []

    batches: list[tuple[str, np.ndarray]]
    if batch_key and batch_key in adata.obs.columns:
        logger.info("  Per-batch mode (batch_key=%s)", batch_key)
        batches = [(b, adata.obs[batch_key] == b) for b in adata.obs[batch_key].unique()]
    else:
        batches = [("all", np.ones(adata.n_obs, dtype=bool))]

    for batch_name, mask in batches:
        batch_adata = adata[mask, :]
        n_cells = batch_adata.n_obs

        if expected_doublet_rate is not None:
            rate = expected_doublet_rate
        elif auto_rate:
            rate = _estimate_doublet_rate(n_cells)
        else:
            rate = 0.06

        logger.info("  Batch %s: %d cells, expected rate %.1f%%", batch_name, n_cells, rate * 100)

        scrub = scr.Scrublet(batch_adata.X, expected_doublet_rate=rate,
                             random_state=random_state)
        b_scores, b_pred = scrub.scrub_doublets(
            min_counts=min_counts, min_cells=min_cells,
            min_gene_variability_pctl=85, n_prin_comps=n_prin_comps, verbose=False,
        )

        scores[mask] = b_scores
        predicted[mask] = b_pred

        n_dbl = b_pred.sum()
        logger.info("    Predicted doublets: %d (%.1f%%)", n_dbl, 100 * n_dbl / n_cells)
        batch_stats.append({
            "batch": batch_name, "n_cells": n_cells, "expected_rate": rate,
            "detected_rate": n_dbl / n_cells, "n_doublets": int(n_dbl),
        })

    adata.obs["doublet_score"] = scores
    adata.obs["predicted_doublet"] = predicted

    # Validation warnings
    total_detected = predicted.sum()
    total_expected_pct = 100 * sum(s["expected_rate"] * s["n_cells"] for s in batch_stats) / adata.n_obs
    total_detected_pct = 100 * total_detected / adata.n_obs

    if total_detected_pct < total_expected_pct * 0.25:
        logger.warning("Detected rate (%.1f%%) << expected (%.1f%%). "
                       "Threshold may be too strict.", total_detected_pct, total_expected_pct)
    elif total_detected_pct > total_expected_pct * 3:
        logger.warning("Detected rate (%.1f%%) >> expected (%.1f%%). "
                       "Check data quality.", total_detected_pct, total_expected_pct)

    adata.uns["scrublet_detection"] = {
        "batch_stats_json": json.dumps(batch_stats),
        "total_detected": int(total_detected),
        "total_detected_pct": float(total_detected_pct),
    }
    return adata


def filter_doublets(
    adata: AnnData,
    doublet_score_threshold: Optional[float] = None,
    use_predicted: bool = True,
    inplace: bool = False,
) -> AnnData:
    """Remove predicted doublets.

    Parameters
    ----------
    adata
        AnnData with doublet scores.
    doublet_score_threshold
        Custom score threshold (overrides predicted_doublet).
    use_predicted
        Use ``predicted_doublet`` column.
    inplace
        Modify in place.
    """
    n_before = adata.n_obs
    logger.info("Filtering doublets (starting with %d) ...", n_before)

    if doublet_score_threshold is not None:
        if "doublet_score" not in adata.obs.columns:
            raise ValueError("doublet_score not found. Run doublet detection first.")
        keep = adata.obs["doublet_score"] < doublet_score_threshold
    elif use_predicted and "predicted_doublet" in adata.obs.columns:
        keep = ~adata.obs["predicted_doublet"]
    else:
        raise ValueError("Need doublet_score_threshold or predicted_doublet column")

    n_removed = (~keep).sum()
    logger.info("  Removed %d doublets", n_removed)

    if inplace:
        adata._inplace_subset_obs(keep)
        result = adata
    else:
        result = adata[keep, :].copy()

    logger.info("Retained %d cells (%.1f%%)", result.n_obs, 100 * result.n_obs / n_before)
    return result


def filter_by_mad_outliers(
    adata: AnnData,
    remove_doublets: bool = True,
    doublet_score_threshold: float = 0.25,
    inplace: bool = False,
) -> AnnData:
    """Filter cells by MAD outliers and optionally doublets.

    Requires prior call to :func:`batch_mad_outlier_detection`.
    """
    if "outlier" not in adata.obs.columns:
        raise ValueError("'outlier' column not found. Run batch_mad_outlier_detection() first.")

    n_before = adata.n_obs
    logger.info("Filtering by MAD outliers ...")

    keep = ~adata.obs["outlier"]
    logger.info("  QC outliers: %d", adata.obs["outlier"].sum())

    if remove_doublets:
        if "doublet_score" in adata.obs.columns:
            dbl = adata.obs["doublet_score"] >= doublet_score_threshold
            keep &= ~dbl
            logger.info("  Doublets (score >= %.2f): %d", doublet_score_threshold, dbl.sum())
        elif "predicted_doublet" in adata.obs.columns:
            keep &= ~adata.obs["predicted_doublet"]
            logger.info("  Predicted doublets: %d", adata.obs["predicted_doublet"].sum())
        else:
            logger.warning("No doublet info found. Skipping doublet filtering.")

    if inplace:
        adata._inplace_subset_obs(keep)
        result = adata
    else:
        result = adata[keep, :].copy()

    logger.info("Retained %d cells (%.1f%%)", result.n_obs, 100 * result.n_obs / n_before)
    return result


def combine_filters_and_apply(
    adata: AnnData,
    filter_outliers: bool = True,
    filter_doublets_flag: bool = True,
    doublet_score_threshold: float = 0.25,
    inplace: bool = False,
) -> AnnData:
    """Combine MAD outlier + doublet filtering and apply.

    Parameters
    ----------
    adata
        AnnData with QC metrics and optionally doublet scores.
    filter_outliers
        Remove MAD outliers.
    filter_doublets_flag
        Remove doublets.
    doublet_score_threshold
        Score threshold for doublet removal.
    inplace
        Modify in place.
    """
    n_before = adata.n_obs
    keep = np.ones(adata.n_obs, dtype=bool)
    logger.info("Applying combined filters (starting with %d) ...", n_before)

    if filter_outliers and "outlier" in adata.obs.columns:
        m = adata.obs["outlier"]
        keep &= ~m
        logger.info("  QC outliers: %d", m.sum())

    if filter_doublets_flag:
        if "doublet_score" in adata.obs.columns:
            m = adata.obs["doublet_score"] >= doublet_score_threshold
            keep &= ~m
            logger.info("  Doublets (score >= %.2f): %d", doublet_score_threshold, m.sum())
        elif "predicted_doublet" in adata.obs.columns:
            m = adata.obs["predicted_doublet"]
            keep &= ~m
            logger.info("  Predicted doublets: %d", m.sum())

    if inplace:
        adata._inplace_subset_obs(keep)
        result = adata
    else:
        result = adata[keep, :].copy()

    retention = 100 * result.n_obs / n_before
    logger.info("Retained %d cells (%.1f%%)", result.n_obs, retention)
    if retention < 70:
        logger.warning("Retention rate < 70%%. Review QC thresholds.")
    return result


# ---------------------------------------------------------------------------
# QC visualization
# ---------------------------------------------------------------------------

from .viz.qc import (
    plot_barcode_rank,
    plot_highest_expr_genes,
    plot_qc_correlation_heatmap,
    plot_qc_histograms,
    plot_qc_scatter,
    plot_qc_violin,
)
