"""Protein-table calculations shared by the public library and CLI."""
from __future__ import annotations
import logging
import re
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

def detect_sample_columns(df: pd.DataFrame) -> list[str]:
    """Auto-detect sample/intensity columns.

    Excludes common metadata columns like protein_id, gene, description.
    Falls back to all numeric columns.
    """
    metadata_keywords = {
        "protein", "gene", "accession", "description", "sequence",
        "id", "name", "organism", "length", "coverage",
    }

    # Try: all numeric columns that don't look like metadata
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    sample_cols = [
        c for c in numeric_cols
        if not any(kw in c.lower() for kw in metadata_keywords)
    ]

    if not sample_cols:
        sample_cols = numeric_cols

    return sample_cols


def qc_proteomics(df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Comprehensive QC for proteomics data.

    Computes:
    - Missing value rate (NaN and zero treated as missing for intensity data)
    - Per-protein CV (coefficient of variation) across samples
    - Intensity distribution statistics
    - Per-sample completeness
    """
    df = df.copy()
    sample_cols = detect_sample_columns(df)
    n_proteins = len(df)
    n_samples = len(sample_cols)

    if n_samples == 0:
        raise ValueError("No intensity/sample columns detected in input data")

    intensities = df[sample_cols].values.astype(float)

    # Missing value analysis: both NaN and 0 are treated as missing
    # (in proteomics, zeros typically represent undetected proteins)
    missing_mask = np.isnan(intensities) | (intensities == 0)
    n_missing = missing_mask.sum()
    total_values = intensities.size
    missing_rate = n_missing / total_values * 100 if total_values > 0 else 0

    # Replace 0/NaN with NaN for calculations
    clean = np.where(intensities > 0, intensities, np.nan)

    # CV calculation (vectorized) - CV = std/mean * 100
    row_means = np.nanmean(clean, axis=1)
    row_stds = np.nanstd(clean, axis=1, ddof=1)  # Use Bessel's correction
    valid_means = row_means > 0
    cv_values = np.full(n_proteins, np.nan)
    cv_values[valid_means] = row_stds[valid_means] / row_means[valid_means] * 100

    # Per-sample completeness
    per_sample_completeness = {}
    for col in sample_cols:
        vals = df[col].values.astype(float)
        detected = np.sum((~np.isnan(vals)) & (vals > 0))
        per_sample_completeness[col] = round(detected / n_proteins * 100, 1)

    # Intensity statistics (non-missing values only)
    nonzero = clean[np.isfinite(clean)]

    stats = {
        "n_proteins": n_proteins,
        "n_samples": n_samples,
        "sample_columns": sample_cols,
        "missing_rate": round(float(missing_rate), 2),
        "n_missing_values": int(n_missing),
        "median_cv": round(float(np.nanmedian(cv_values)), 2),
        "mean_cv": round(float(np.nanmean(cv_values)), 2),
        "mean_intensity": round(float(nonzero.mean()), 2) if len(nonzero) > 0 else 0,
        "median_intensity": round(float(np.median(nonzero)), 2) if len(nonzero) > 0 else 0,
        "dynamic_range_log10": round(
            float(np.log10(nonzero.max() / nonzero.min())), 2
        ) if len(nonzero) > 1 and nonzero.min() > 0 else 0,
        "per_sample_completeness": per_sample_completeness,
    }

    # Add CV distribution
    finite_cvs = cv_values[np.isfinite(cv_values)]
    if len(finite_cvs) > 0:
        stats["cv_below_20pct"] = int((finite_cvs < 20).sum())
        stats["cv_below_30pct"] = int((finite_cvs < 30).sum())
        stats["cv_above_50pct"] = int((finite_cvs > 50).sum())

    logger.info(
        f"QC complete: {n_proteins} proteins, {n_samples} samples, "
        f"{missing_rate:.1f}% missing, median CV={stats['median_cv']:.1f}%"
    )
    return stats, df


def demo_data(*, random_state: int = 42):
    """Generate realistic demo proteomics intensity data."""
    rng = np.random.default_rng(random_state)
    n_proteins = 100
    n_samples = 5

    data = {
        "protein_id": [f"P{i:05d}" for i in range(n_proteins)],
    }

    for i in range(n_samples):
        intensities = rng.lognormal(10, 2, n_proteins)
        # Add ~10% missing values (set to 0)
        intensities[rng.random(n_proteins) < 0.1] = 0
        data[f"sample_{i+1}"] = intensities

    df = pd.DataFrame(data)
    return df
