#!/usr/bin/env python3
"""Proteomics MS-QC - Mass spectrometry data quality control.

Usage:
    python ms_qc.py --input <data.csv> --output <dir>
    python ms_qc.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
import pandas as pd
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "ms-qc"
SKILL_VERSION = "0.2.0"


def qc_proteomics(data_path):
    """Comprehensive QC for proteomics data."""
    df = pd.read_csv(data_path)

    n_proteins = len(df)
    sample_cols = [c for c in df.columns if c.startswith('sample')]
    n_samples = len(sample_cols)

    # Calculate QC metrics
    intensities = df[sample_cols].values
    missing_rate = (intensities == 0).sum() / intensities.size * 100
    cv_values = []
    for idx in range(len(df)):
        row = intensities[idx, :]
        if row.mean() > 0:
            cv_values.append(row.std() / row.mean() * 100)

    stats = {
        'n_proteins': n_proteins,
        'n_samples': n_samples,
        'missing_rate': float(missing_rate),
        'median_cv': float(np.median(cv_values)) if cv_values else 0,
        'mean_intensity': float(intensities[intensities > 0].mean()) if (intensities > 0).any() else 0,
    }

    logger.info(f"QC complete: {n_proteins} proteins, {n_samples} samples, {missing_rate:.1f}% missing")
    return stats, df


def generate_demo_data(output_path):
    """Generate demo proteomics data."""
    n_proteins = 100
    n_samples = 5

    data = {
        'protein_id': [f'P{i:05d}' for i in range(n_proteins)],
    }

    for i in range(n_samples):
        intensities = np.random.lognormal(10, 2, n_proteins)
        intensities[np.random.rand(n_proteins) < 0.1] = 0  # Add missing values
        data[f'sample_{i+1}'] = intensities

    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    logger.info(f"Generated demo data: {output_path}")


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="MS Quality Control Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Proteins": str(summary['n_proteins']),
            "Samples": str(summary['n_samples']),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Proteins identified**: {summary['n_proteins']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Missing values**: {summary['missing_rate']:.1f}%",
        f"- **Median CV**: {summary['median_cv']:.1f}%",
        f"- **Mean intensity**: {summary['mean_intensity']:.2e}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python ms_qc.py --input <input.csv> --output {output_dir}"
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

    qc_summary = pd.DataFrame([stats])
    qc_summary.to_csv(tables_dir / "qc_metrics.csv", index=False)

    params = {}
    write_report(output_dir, stats, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {"params": params}, "")

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"MS-QC complete: {stats['n_proteins']} proteins, {stats['n_samples']} samples")


if __name__ == "__main__":
    main()
