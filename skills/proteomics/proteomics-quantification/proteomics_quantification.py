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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "quantification"
SKILL_VERSION = "0.3.0"
SUPPORTED_METHODS = ("lfq", "spectral_count", "ibaq")


# ---------------------------------------------------------------------------
# Tryptic peptide counting for iBAQ
# ---------------------------------------------------------------------------
def count_theoretical_peptides(sequence: str, min_length: int = 7,
                               max_length: int = 30) -> int:
    """Count theoretical tryptic peptides for a protein sequence.

    Trypsin cleaves after K or R (unless followed by P).
    Only peptides with length in [min_length, max_length] are counted,
    matching MaxQuant's default iBAQ implementation.

    Reference: Schwanhäusser et al. (2011) Nature 473, 337–342.
    """
    if not sequence:
        return 1  # Avoid division by zero

    # Trypsin rule: cleave after K or R, but not before P
    # regex: split after K/R that is NOT followed by P
    peptides = re.split(r'(?<=[KR])(?!P)', sequence.upper())

    # Filter by length (observable peptides only)
    observable = [p for p in peptides if min_length <= len(p) <= max_length]

    return max(len(observable), 1)  # At least 1 to prevent division by zero


# ---------------------------------------------------------------------------
# Quantification methods
# ---------------------------------------------------------------------------
def quantify_lfq(peptides: pd.DataFrame) -> pd.DataFrame:
    """Label-free quantification: sum peptide intensities per protein.

    Reference: Cox et al. (2014) MaxLFQ algorithm, Mol Cell Proteomics.
    Note: This is a simplified LFQ (intensity summation), not the full
    MaxLFQ delayed normalization algorithm.
    """
    logger.info("Performing LFQ quantification (intensity summation)")
    if "intensity" not in peptides.columns:
        raise ValueError("Input requires an 'intensity' column for LFQ")

    proteins = peptides.groupby("protein")["intensity"].sum().reset_index()
    proteins.columns = ["protein", "abundance"]

    # Log2 transform for downstream analysis
    proteins["log2_abundance"] = np.log2(proteins["abundance"].clip(lower=1e-10))

    return proteins


def quantify_spectral_count(peptides: pd.DataFrame) -> pd.DataFrame:
    """Spectral counting quantification: count PSMs per protein.

    Reference: Liu et al. (2004) Anal Chem 76(14), 4193-4201.
    """
    logger.info("Performing spectral count quantification")
    proteins = peptides.groupby("protein").size().reset_index(name="spectral_count")
    proteins.columns = ["protein", "abundance"]
    return proteins


def quantify_ibaq(peptides: pd.DataFrame) -> pd.DataFrame:
    """iBAQ quantification: sum of intensities / number of theoretical peptides.

    iBAQ = Σ(peptide intensities) / #(theoretical tryptic peptides)

    Reference: Schwanhäusser et al. (2011) Global quantification of mammalian
    gene expression control. Nature 473, 337–342.
    """
    logger.info("Performing iBAQ quantification")
    if "intensity" not in peptides.columns:
        raise ValueError("Input requires an 'intensity' column for iBAQ")

    # Sum intensities per protein
    intensity_sums = peptides.groupby("protein")["intensity"].sum()

    # Get theoretical peptide counts
    if "sequence" in peptides.columns:
        # Use actual protein sequences if available
        seqs = peptides.groupby("protein")["sequence"].first()
        theo_peptides = seqs.apply(count_theoretical_peptides)
    elif "n_theoretical_peptides" in peptides.columns:
        # Use pre-computed counts if provided
        theo_peptides = peptides.groupby("protein")["n_theoretical_peptides"].first()
    else:
        # Estimate from observed unique peptides (approximation)
        # Use 1.5× observed unique peptides as a rough estimate
        logger.warning(
            "No 'sequence' or 'n_theoretical_peptides' column found. "
            "Estimating theoretical peptide count from observed peptides."
        )
        unique_peptides = peptides.groupby("protein")["peptide"].nunique()
        theo_peptides = (unique_peptides * 1.5).clip(lower=1).astype(int)

    # iBAQ = total_intensity / theoretical_peptides
    ibaq_values = intensity_sums / theo_peptides.clip(lower=1)

    proteins = pd.DataFrame({
        "protein": ibaq_values.index,
        "abundance": ibaq_values.values,
        "total_intensity": intensity_sums.values,
        "n_theoretical_peptides": theo_peptides.values,
    }).reset_index(drop=True)

    proteins["log2_abundance"] = np.log2(proteins["abundance"].clip(lower=1e-10))

    return proteins


def _dispatch_method(method: str, peptides: pd.DataFrame) -> pd.DataFrame:
    """Route to quantification method."""
    if method == "lfq":
        return quantify_lfq(peptides)
    elif method == "spectral_count":
        return quantify_spectral_count(peptides)
    elif method == "ibaq":
        return quantify_ibaq(peptides)
    else:
        raise ValueError(f"Unknown method: {method}. Supported: {SUPPORTED_METHODS}")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------
def get_demo_data() -> pd.DataFrame:
    """Generate demo peptide data with realistic structure."""
    logger.info("Generating demo peptide data")
    rng = np.random.default_rng(42)

    n_peptides = 500
    n_proteins = 100
    proteins = [f"P{i:05d}" for i in range(n_proteins)]

    # Generate some synthetic protein sequences for iBAQ testing
    aa_alphabet = list("ACDEFGHIKLMNPQRSTVWY")
    sequences = {}
    for p in proteins:
        seq_len = rng.integers(100, 800)
        sequences[p] = "".join(rng.choice(aa_alphabet, seq_len))

    assigned_proteins = rng.choice(proteins, n_peptides)

    peptides = pd.DataFrame({
        "peptide": [f"PEPTIDE{i}" for i in range(n_peptides)],
        "protein": assigned_proteins,
        "intensity": rng.lognormal(10, 2, n_peptides),
        "sequence": [sequences[p] for p in assigned_proteins],
    })
    return peptides


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
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary,
                      {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Quantification complete: {summary['n_proteins']} proteins ({args.method})")


if __name__ == "__main__":
    main()
