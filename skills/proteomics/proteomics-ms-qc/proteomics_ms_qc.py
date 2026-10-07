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

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "ms-qc"
SKILL_VERSION = "0.5.0"


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
    from skills._sdk.notebook import load_skill
    library = load_skill("proteomics-ms-qc")
    parser = argparse.ArgumentParser(description="Proteomics MS-QC")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = output_dir / "demo_proteomics.csv"
        library.demo_data().to_csv(data_path, index=False)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    qc = library.quality_control(pd.read_csv(data_path))
    stats = library.run_info(qc, keep=False)["summary"]

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
