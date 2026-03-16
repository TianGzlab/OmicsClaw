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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "peptide-id"
SKILL_VERSION = "0.3.0"

# Canonical amino acids for realistic peptide generation
AMINO_ACIDS = list("ACDEFGHIKLMNPQRSTVWY")


def identify_peptides_demo(n_spectra: int = 1000) -> pd.DataFrame:
    """Generate realistic demo peptide identification results.

    Simulates a typical bottom-up proteomics search engine output
    with realistic identification rate (~40-60%) and score distributions.
    """
    rng = np.random.default_rng(42)
    logger.info(f"Simulating peptide identification for {n_spectra} spectra")

    proteins = [f"P{i:05d}" for i in range(100)]
    peptides = []

    for i in range(n_spectra):
        if rng.random() < 0.50:  # ~50% identification rate (typical for DDA)
            pep_len = rng.integers(7, 25)
            peptide_seq = "".join(rng.choice(AMINO_ACIDS, pep_len))
            charge = int(rng.choice([2, 3, 4], p=[0.45, 0.40, 0.15]))
            mz = rng.uniform(300, 1500)
            mass = mz * charge - charge * 1.00728  # proton mass

            peptides.append({
                "spectrum_id": f"scan_{i+1}",
                "peptide": peptide_seq,
                "protein": rng.choice(proteins),
                "score": round(float(rng.uniform(20, 100)), 2),
                "qvalue": round(float(rng.uniform(0, 0.05)), 6),
                "charge": charge,
                "precursor_mz": round(mz, 4),
                "precursor_mass": round(mass, 4),
                "length": pep_len,
            })

    return pd.DataFrame(peptides)


def load_identification_results(input_path: Path) -> pd.DataFrame:
    """Load peptide identification results from CSV/TSV.

    Handles common column naming conventions from different search engines.
    """
    path = Path(input_path)
    if path.suffix in (".tsv", ".txt"):
        df = pd.read_csv(path, sep="\t")
    else:
        df = pd.read_csv(path)

    # Normalize column names (handle MaxQuant, MSFragger, etc.)
    col_map = {
        "Sequence": "peptide",
        "Modified sequence": "modified_peptide",
        "Proteins": "protein",
        "Leading proteins": "protein",
        "Score": "score",
        "PEP": "pep",
        "Charge": "charge",
        "m/z": "precursor_mz",
        "Mass": "precursor_mass",
    }

    for old_name, new_name in col_map.items():
        if old_name in df.columns and new_name not in df.columns:
            df = df.rename(columns={old_name: new_name})

    logger.info(f"Loaded {len(df)} PSMs from {path.name}")
    return df


def filter_by_fdr(df: pd.DataFrame, fdr_threshold: float = 0.01) -> pd.DataFrame:
    """Filter peptide identifications by FDR (q-value) threshold.

    Reference: Elias & Gygi (2007) target-decoy approach.
    """
    fdr_col = None
    for candidate in ["qvalue", "q-value", "q_value", "PEP", "pep", "fdr"]:
        if candidate in df.columns:
            fdr_col = candidate
            break

    if fdr_col is None:
        logger.warning("No FDR/q-value column found. Returning all results.")
        return df

    n_before = len(df)
    df_filtered = df[df[fdr_col] <= fdr_threshold].copy()
    n_after = len(df_filtered)
    logger.info(f"FDR filtering ({fdr_col} <= {fdr_threshold}): "
                f"{n_before} → {n_after} PSMs ({n_before - n_after} removed)")

    return df_filtered


def compute_summary(peptides: pd.DataFrame, n_spectra: int | None = None) -> dict:
    """Compute identification summary statistics."""
    n_psms = len(peptides)
    n_unique_peptides = peptides["peptide"].nunique() if "peptide" in peptides.columns else n_psms
    n_proteins = peptides["protein"].nunique() if "protein" in peptides.columns else 0

    if n_spectra is None:
        n_spectra = n_psms  # Approximate if actual spectrum count unknown

    summary = {
        "n_spectra": n_spectra,
        "n_psms": n_psms,
        "n_unique_peptides": n_unique_peptides,
        "n_proteins": n_proteins,
        "id_rate": round(float(n_psms / n_spectra * 100), 1) if n_spectra > 0 else 0,
    }

    if "score" in peptides.columns:
        summary["median_score"] = round(float(peptides["score"].median()), 2)

    if "charge" in peptides.columns:
        charge_dist = peptides["charge"].value_counts().to_dict()
        summary["charge_distribution"] = {str(k): int(v) for k, v in sorted(charge_dist.items())}

    return summary


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
        peptides = identify_peptides_demo()
        input_file = None
        n_spectra = 1000
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        peptides = load_identification_results(Path(args.input_path))
        input_file = args.input_path
        n_spectra = args.n_spectra

    # Apply FDR filtering
    peptides = filter_by_fdr(peptides, fdr_threshold=args.fdr)

    logger.info(f"Identified {len(peptides)} peptides after FDR filtering")

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    peptides.to_csv(tables_dir / "peptides.csv", index=False)

    summary = compute_summary(peptides, n_spectra=n_spectra)
    params = {"fdr": args.fdr}

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary,
                      {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Peptide identification complete: {summary.get('n_unique_peptides', 0)} unique peptides, "
          f"{summary['n_proteins']} proteins")


if __name__ == "__main__":
    main()
