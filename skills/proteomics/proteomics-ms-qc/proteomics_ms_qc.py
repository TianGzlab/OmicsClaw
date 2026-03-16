#!/usr/bin/env python3
"""Proteomics MS-QC - Mass spectrometry data quality control.

Performs comprehensive QC including missing value analysis, coefficient of
variation (CV), intensity distribution, and sample correlation.

Usage:
    python proteomics_ms_qc.py --input <data.csv> --output <dir>
    python proteomics_ms_qc.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "ms-qc"
SKILL_VERSION = "0.3.0"


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


def qc_proteomics(data_path: str | Path) -> tuple[dict, pd.DataFrame]:
    """Comprehensive QC for proteomics data.

    Computes:
    - Missing value rate (NaN and zero treated as missing for intensity data)
    - Per-protein CV (coefficient of variation) across samples
    - Intensity distribution statistics
    - Per-sample completeness
    """
    df = pd.read_csv(data_path)
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


def generate_demo_data(output_path: str | Path) -> None:
    """Generate realistic demo proteomics intensity data."""
    rng = np.random.default_rng(42)
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
    df.to_csv(output_path, index=False)
    logger.info(f"Generated demo data: {output_path}")


def write_report(output_dir: Path, summary: dict, input_file: str | None,
                 params: dict) -> None:
    """Write comprehensive QC report."""
    header = generate_report_header(
        title="MS Quality Control Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Proteins": str(summary["n_proteins"]),
            "Samples": str(summary["n_samples"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Proteins**: {summary['n_proteins']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Missing values**: {summary['missing_rate']:.1f}% ({summary['n_missing_values']} values)",
        f"- **Median CV**: {summary['median_cv']:.1f}%",
        f"- **Mean CV**: {summary['mean_cv']:.1f}%",
        f"- **Mean intensity**: {summary['mean_intensity']:.2e}",
        f"- **Median intensity**: {summary['median_intensity']:.2e}",
        f"- **Dynamic range (log10)**: {summary.get('dynamic_range_log10', 'N/A')}",
        "",
    ]

    # CV quality assessment
    if "cv_below_20pct" in summary:
        body_lines.extend([
            "### CV Distribution\n",
            f"- CV < 20%: {summary['cv_below_20pct']} proteins (excellent reproducibility)",
            f"- CV < 30%: {summary['cv_below_30pct']} proteins (good reproducibility)",
            f"- CV > 50%: {summary['cv_above_50pct']} proteins (poor reproducibility)",
            "",
        ])

    # Per-sample completeness
    if "per_sample_completeness" in summary:
        body_lines.extend(["### Per-Sample Completeness\n"])
        for col, pct in summary["per_sample_completeness"].items():
            body_lines.append(f"- `{col}`: {pct}%")
        body_lines.append("")

    body_lines.append("## Parameters\n")
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python proteomics_ms_qc.py --input <input.csv> --output {output_dir}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def main():
    parser = argparse.ArgumentParser(description="Proteomics MS-QC")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = output_dir / "demo_proteomics.csv"
        generate_demo_data(data_path)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    stats, df = qc_proteomics(data_path)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    # Remove non-serializable items for CSV
    csv_stats = {k: v for k, v in stats.items()
                 if k not in ("sample_columns", "per_sample_completeness")}
    qc_summary = pd.DataFrame([csv_stats])
    qc_summary.to_csv(tables_dir / "qc_metrics.csv", index=False)

    params = {}
    write_report(output_dir, stats, input_file, params)

    # Simplify stats dict for JSON (remove list/dict that might be too verbose)
    json_stats = {k: v for k, v in stats.items() if k != "sample_columns"}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, json_stats,
                      {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"MS-QC complete: {stats['n_proteins']} proteins, {stats['n_samples']} samples, "
          f"median CV={stats['median_cv']:.1f}%")


if __name__ == "__main__":
    main()
