"""Parsing and calculations for epigenomics."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd


def parse_peaks_bed(bed_path: Path) -> pd.DataFrame:
    """Parse a BED or narrowPeak file into a DataFrame.

    Handles both formats:
    - BED3-BED6: chrom, start, end [, name, score, strand]
    - narrowPeak (BED6+4): + signalValue, pValue, qValue, peak

    Per BED spec, coordinates are 0-based half-open [start, end).
    """
    column_names = [
        "chrom", "start", "end", "name", "score", "strand",
        "signal_value", "pvalue", "qvalue", "peak_offset",
    ]

    try:
        # Try narrowPeak (10 columns)
        df = pd.read_csv(
            bed_path, sep="\t", header=None,
            names=column_names[:10],
            comment="#",
        )
    except Exception:
        try:
            # Try BED6
            df = pd.read_csv(
                bed_path, sep="\t", header=None,
                names=column_names[:6],
                comment="#",
            )
        except Exception:
            # Fallback: BED3
            df = pd.read_csv(
                bed_path, sep="\t", header=None,
                names=["chrom", "start", "end"],
                comment="#",
            )

    # Compute peak width
    df["width"] = df["end"] - df["start"]

    return df

def parse_peaks_csv(csv_path: Path) -> pd.DataFrame:
    """Parse peaks from CSV (internal format)."""
    df = pd.read_csv(csv_path)
    if "width" not in df.columns and "start" in df.columns and "end" in df.columns:
        df["width"] = df["end"] - df["start"]
    return df

def compute_peak_stats(df: pd.DataFrame, assay: str = "chip-seq") -> dict:
    """Compute comprehensive peak statistics.

    Summarizes peak widths and available score columns. No FRiP is computed.
    """
    n_peaks = len(df)
    widths = df["width"].values

    stats = {
        "n_peaks": n_peaks,
        "total_peak_coverage_bp": int(widths.sum()),
        "mean_peak_width": int(np.mean(widths)),
        "median_peak_width": int(np.median(widths)),
        "min_peak_width": int(widths.min()),
        "max_peak_width": int(widths.max()),
        "n_chromosomes": int(df["chrom"].nunique()),
        "assay": assay,
    }

    # Width distribution quartiles
    stats["peak_width_q25"] = int(np.percentile(widths, 25))
    stats["peak_width_q75"] = int(np.percentile(widths, 75))

    # Score statistics
    if "score" in df.columns:
        scores = pd.to_numeric(df["score"], errors="coerce").dropna()
        if len(scores) > 0:
            stats["mean_score"] = round(float(scores.mean()), 2)
            stats["median_score"] = round(float(scores.median()), 2)

    # Fold enrichment statistics
    if "signal_value" in df.columns:
        fe = pd.to_numeric(df["signal_value"], errors="coerce").dropna()
        if len(fe) > 0:
            stats["mean_fold_enrichment"] = round(float(fe.mean()), 3)
            stats["median_fold_enrichment"] = round(float(fe.median()), 3)
    elif "fold_enrichment" in df.columns:
        fe = pd.to_numeric(df["fold_enrichment"], errors="coerce").dropna()
        if len(fe) > 0:
            stats["mean_fold_enrichment"] = round(float(fe.mean()), 3)
            stats["median_fold_enrichment"] = round(float(fe.median()), 3)

    # p-value / q-value statistics
    for col_name, stat_prefix in [("pvalue", "pvalue"), ("qvalue", "qvalue")]:
        if col_name in df.columns:
            vals = pd.to_numeric(df[col_name], errors="coerce").dropna()
            if len(vals) > 0:
                # Convert -log10(p) to actual p-value if values are positive and large
                if vals.median() > 1:
                    # Values are -log10(p)
                    stats[f"median_{stat_prefix}_neglog10"] = round(float(vals.median()), 2)
                    stats[f"n_{stat_prefix}_significant"] = int((vals >= -np.log10(0.05)).sum())
                else:
                    stats[f"median_{stat_prefix}"] = float(vals.median())
                    stats[f"n_{stat_prefix}_significant"] = int((vals < 0.05).sum())

    # Per-chromosome distribution
    chrom_counts = df["chrom"].value_counts().to_dict()
    stats["peaks_per_chrom"] = chrom_counts

    # Assay-specific expectations
    if assay == "atac-seq":
        # ATAC-seq: expect narrower peaks (200-500 bp typical for nucleosome-free)
        stats["expected_peak_width_range"] = "150-500 bp (nucleosome-free regions)"
    elif assay == "chip-seq":
        stats["expected_peak_width_range"] = "200-2000 bp (depends on histone/TF)"
    elif assay == "cut-tag":
        stats["expected_peak_width_range"] = "150-300 bp (typically narrow)"

    return stats
