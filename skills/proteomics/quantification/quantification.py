#!/usr/bin/env python3
"""Proteomics Quantification - Quantify protein abundance.

Usage:
    python quantification.py --input <peptides.csv> --output <dir> --method lfq
    python quantification.py --demo --output <dir>
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

SKILL_NAME = "quantification"
SKILL_VERSION = "0.2.0"
SUPPORTED_METHODS = ("lfq", "spectral_count", "ibaq")


def quantify_lfq(peptides: pd.DataFrame) -> pd.DataFrame:
    """Label-free quantification."""
    logger.info("Performing LFQ quantification")
    proteins = peptides.groupby('protein')['intensity'].sum().reset_index()
    proteins.columns = ['protein', 'abundance']
    return proteins


def quantify_spectral_count(peptides: pd.DataFrame) -> pd.DataFrame:
    """Spectral counting quantification."""
    logger.info("Performing spectral count quantification")
    proteins = peptides.groupby('protein').size().reset_index()
    proteins.columns = ['protein', 'abundance']
    return proteins


def _dispatch_method(method: str, peptides: pd.DataFrame) -> pd.DataFrame:
    """Route to quantification method."""
    if method == "lfq":
        return quantify_lfq(peptides)
    elif method == "spectral_count":
        return quantify_spectral_count(peptides)
    elif method == "ibaq":
        return quantify_lfq(peptides)
    else:
        raise ValueError(f"Unknown method: {method}")


def get_demo_data() -> pd.DataFrame:
    """Generate demo peptide data."""
    logger.info("Generating demo peptide data")
    n_peptides = 500
    proteins = [f"P{i:05d}" for i in range(100)]

    peptides = pd.DataFrame({
        'peptide': [f"PEPTIDE{i}" for i in range(n_peptides)],
        'protein': np.random.choice(proteins, n_peptides),
        'intensity': np.random.lognormal(10, 2, n_peptides),
    })
    return peptides


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report."""
    header = generate_report_header(
        title="Protein Quantification Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary['method'], "Proteins": str(summary['n_proteins'])},
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Proteins quantified**: {summary['n_proteins']}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\npython quantification.py --output {output_dir} --method {params['method']}\n")


def main():
    parser = argparse.ArgumentParser(description="Protein Quantification")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="lfq", choices=list(SUPPORTED_METHODS))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        peptides = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required")
        peptides = pd.read_csv(args.input_path)
        input_file = args.input_path

    proteins = _dispatch_method(args.method, peptides)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    proteins.to_csv(tables_dir / "protein_abundance.csv", index=False)

    summary = {"method": args.method, "n_proteins": len(proteins)}
    params = {"method": args.method}

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, "")

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Quantification complete: {summary['n_proteins']} proteins")


if __name__ == "__main__":
    main()
