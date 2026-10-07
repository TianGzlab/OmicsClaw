#!/usr/bin/env python3
"""Proteomics Quantification - Quantify protein abundance.

Implements three methods:
  - LFQ (Label-Free Quantification): sum of peptide intensities per protein
  - Spectral Count: count of identified spectra per protein
  - iBAQ: sum of intensities / number of theoretical tryptic peptides

Usage:
    python proteomics_quantification.py --input <peptides.csv> --output <dir> --method lfq
    python proteomics_quantification.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import re
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

SKILL_NAME = "quantification"
SKILL_VERSION = "0.5.0"
SUPPORTED_METHODS = ("lfq", "spectral_count", "ibaq")


# ---------------------------------------------------------------------------
# Quantification methods
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(output_dir: Path, summary: dict, input_file: str | None,
                 params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Protein Quantification Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Proteins": str(summary["n_proteins"]),
        },
    )

    method_desc = {
        "lfq": "Label-Free Quantification (intensity summation)",
        "spectral_count": "Spectral counting (PSM count per protein)",
        "ibaq": "iBAQ (intensity / theoretical tryptic peptides)",
    }

    body_lines = [
        "## Summary\n",
        f"- **Method**: {method_desc.get(summary['method'], summary['method'])}",
        f"- **Proteins quantified**: {summary['n_proteins']}",
        "",
        "## Methodology\n",
    ]

    if summary["method"] == "ibaq":
        body_lines.extend([
            "- iBAQ = Σ(peptide intensities) / #(theoretical tryptic peptides)",
            "- Trypsin cleavage: after K/R, not before P",
            "- Observable peptide length: 7–30 amino acids",
            "- Reference: Schwanhäusser et al. (2011) Nature 473:337-342",
        ])
    elif summary["method"] == "lfq":
        body_lines.extend([
            "- Simplified LFQ: sum of peptide intensities per protein",
            "- Reference: Cox et al. (2014) Mol Cell Proteomics",
        ])
    elif summary["method"] == "spectral_count":
        body_lines.extend([
            "- Spectral count: number of peptide-spectrum matches (PSMs)",
            "- Reference: Liu et al. (2004) Anal Chem 76:4193-4201",
        ])

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python proteomics_quantification.py --output {output_dir} --method {params['method']}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    from skills._sdk.notebook import load_skill
    library = load_skill("proteomics-quantification")
    parser = argparse.ArgumentParser(description="Protein Quantification")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="lfq", choices=list(SUPPORTED_METHODS))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        peptides = library.demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required")
        peptides = pd.read_csv(args.input_path)
        input_file = args.input_path

    proteins = library.quantify(peptides, method=args.method)

    library.run_info(proteins, keep=False)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    proteins.to_csv(tables_dir / "protein_abundance.csv", index=False)

    summary = {"method": args.method, "n_proteins": len(proteins)}
    params = {"method": args.method}

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary,
                      {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Quantification complete: {summary['n_proteins']} proteins ({args.method})")


if __name__ == "__main__":
    main()
