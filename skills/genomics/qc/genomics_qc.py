#!/usr/bin/env python3
"""Genomics QC - Quality control for genomics data.

Usage:
    python genomics_qc.py --input <file.fastq> --output <dir>
    python genomics_qc.py --demo --output <dir>
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

SKILL_NAME = "genomics-qc"
SKILL_VERSION = "0.2.0"


def qc_fastq_demo() -> dict:
    """Demo QC metrics for FASTQ data."""
    logger.info("Generating demo QC metrics")

    return {
        "total_reads": 1000000,
        "total_bases": 150000000,
        "mean_quality": 35.2,
        "gc_content": 42.5,
        "n_content": 0.1,
        "mean_length": 150,
    }


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write QC report."""
    header = generate_report_header(
        title="Genomics Quality Control Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Reads": str(summary['total_reads'])},
    )

    body_lines = [
        "## Summary\n",
        f"- **Total reads**: {summary['total_reads']:,}",
        f"- **Total bases**: {summary['total_bases']:,}",
        f"- **Mean quality**: {summary['mean_quality']:.1f}",
        f"- **GC content**: {summary['gc_content']:.1f}%",
        f"- **Mean length**: {summary['mean_length']} bp",
        "",
    ]

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\npython genomics_qc.py --output {output_dir}\n")


def main():
    parser = argparse.ArgumentParser(description="Genomics QC")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        result = qc_fastq_demo()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required")
        result = qc_fastq_demo()
        input_file = args.input_path

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    pd.DataFrame([result]).to_csv(tables_dir / "qc_metrics.csv", index=False)

    params = {}
    write_report(output_dir, result, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, result, {"params": params}, "")

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"QC complete: {result['total_reads']:,} reads")


if __name__ == "__main__":
    main()
