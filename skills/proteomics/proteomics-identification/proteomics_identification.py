#!/usr/bin/env python3
"""Proteomics Peptide Identification - Identify peptides from MS/MS spectra.

Supports reading peptide identification results from common search engine
output formats (MaxQuant evidence.txt, generic CSV) and applying FDR filtering.

Usage:
    python proteomics_identification.py --input <peptides.csv> --output <dir>
    python proteomics_identification.py --demo --output <dir>
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

SKILL_NAME = "peptide-id"
SKILL_VERSION = "0.5.0"

# Canonical amino acids for realistic peptide generation
AMINO_ACIDS = list("ACDEFGHIKLMNPQRSTVWY")


def write_report(output_dir: Path, summary: dict, input_file: str | None,
                 params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Peptide Identification Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Peptides": str(summary.get("n_unique_peptides", summary.get("n_psms", "N/A"))),
            "Proteins": str(summary["n_proteins"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Total spectra**: {summary.get('n_spectra', 'N/A')}",
        f"- **PSMs (peptide-spectrum matches)**: {summary.get('n_psms', 'N/A')}",
        f"- **Unique peptides**: {summary.get('n_unique_peptides', 'N/A')}",
        f"- **Proteins identified**: {summary['n_proteins']}",
        f"- **Identification rate**: {summary.get('id_rate', 0):.1f}%",
        "",
    ]

    if "median_score" in summary:
        body_lines.append(f"- **Median score**: {summary['median_score']}")

    if "charge_distribution" in summary:
        body_lines.extend(["", "### Charge State Distribution\n"])
        for charge, count in sorted(summary["charge_distribution"].items()):
            body_lines.append(f"- Charge +{charge}: {count}")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python proteomics_identification.py --input <input_file> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def main():
    from skills._sdk.notebook import load_skill
    library = load_skill("proteomics-identification")
    parser = argparse.ArgumentParser(description="Peptide Identification")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--fdr", type=float, default=0.01,
                        help="FDR threshold for filtering (default: 0.01)")
    parser.add_argument("--n-spectra", type=int, default=None,
                        help="Total number of spectra (for identification rate)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        peptides = library.demo_data()
        input_file = None
        n_spectra = 1000
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        peptides = library.read_table(Path(args.input_path))
        input_file = args.input_path
        n_spectra = args.n_spectra

    # Apply FDR filtering
    peptides = library.filter_identifications(peptides, fdr_threshold=args.fdr, n_spectra=n_spectra)

    logger.info(f"Identified {len(peptides)} peptides after FDR filtering")

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    peptides.to_csv(tables_dir / "peptides.csv", index=False)

    diagnostics = library.run_info(peptides, keep=False)
    summary = diagnostics.pop("summary")
    params = {"fdr": args.fdr}

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary,
                      {"params": params, "diagnostics": diagnostics})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Peptide identification complete: {summary.get('n_unique_peptides', 0)} unique peptides, "
          f"{summary['n_proteins']} proteins")


if __name__ == "__main__":
    main()
