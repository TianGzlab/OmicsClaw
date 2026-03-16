#!/usr/bin/env python3
"""Proteomics Data Import - Import and convert proteomics data formats.

Supports reading data from common proteomics search engine output formats
(MaxQuant, FragPipe/MSFragger, DIA-NN, generic CSV/TSV) and converting to
a standardized OmicsClaw format.

Usage:
    python proteomics_data_import.py --input <data.txt> --output <dir> --format maxquant
    python proteomics_data_import.py --demo --output <dir>
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

from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "data-import"
SKILL_VERSION = "0.2.0"

SUPPORTED_FORMATS = ("maxquant", "fragpipe", "diann", "generic")


# ---------------------------------------------------------------------------
# Format-specific importers
# ---------------------------------------------------------------------------
def _detect_separator(path: Path) -> str:
    """Auto-detect CSV vs TSV."""
    with open(path, "r") as f:
        first_line = f.readline()
    return "\t" if "\t" in first_line else ","


def import_maxquant(path: Path) -> pd.DataFrame:
    """Import MaxQuant proteinGroups.txt output.

    Expected columns: Protein IDs, Gene names, Intensity columns, etc.
    Reference: Cox & Mann (2008) Nature Biotechnology.
    """
    sep = _detect_separator(path)
    df = pd.read_csv(path, sep=sep)
    logger.info(f"MaxQuant import: {len(df)} rows, {len(df.columns)} columns")

    # Rename key columns to standardized names
    col_map = {
        "Protein IDs": "protein_id",
        "Majority protein IDs": "protein_id",
        "Gene names": "gene_name",
        "Fasta headers": "description",
        "Number of proteins": "n_proteins_in_group",
        "Peptides": "n_peptides",
        "Unique peptides": "n_unique_peptides",
        "Sequence coverage [%]": "sequence_coverage",
        "Mol. weight [kDa]": "mol_weight_kda",
        "Score": "score",
        "Q-value": "qvalue",
    }
    for old, new in col_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    # Identify intensity columns
    intensity_cols = [c for c in df.columns if c.startswith("Intensity ") or c.startswith("LFQ intensity ")]
    if intensity_cols:
        # Rename to shorter sample names
        for col in intensity_cols:
            new_name = col.replace("LFQ intensity ", "LFQ_").replace("Intensity ", "Int_")
            if new_name != col:
                df = df.rename(columns={col: new_name})

    # Filter: remove contaminants and reverse hits if present
    n_before = len(df)
    if "Reverse" in df.columns:
        df = df[df["Reverse"] != "+"]
    if "Potential contaminant" in df.columns:
        df = df[df["Potential contaminant"] != "+"]
    if "Only identified by site" in df.columns:
        df = df[df["Only identified by site"] != "+"]
    n_after = len(df)
    if n_before != n_after:
        logger.info(f"Filtered: {n_before} → {n_after} entries "
                     f"(removed {n_before - n_after} contaminants/reverse/site-only)")

    return df


def import_fragpipe(path: Path) -> pd.DataFrame:
    """Import FragPipe/MSFragger combined_protein.tsv output."""
    sep = _detect_separator(path)
    df = pd.read_csv(path, sep=sep)
    logger.info(f"FragPipe import: {len(df)} rows, {len(df.columns)} columns")

    col_map = {
        "Protein": "protein_id",
        "Protein ID": "protein_id",
        "Gene": "gene_name",
        "Description": "description",
        "Combined Total Peptides": "n_peptides",
        "Combined Unique Peptides": "n_unique_peptides",
        "Combined Spectral Count": "spectral_count",
    }
    for old, new in col_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    return df


def import_diann(path: Path) -> pd.DataFrame:
    """Import DIA-NN report.tsv or pg_matrix output."""
    sep = _detect_separator(path)
    df = pd.read_csv(path, sep=sep)
    logger.info(f"DIA-NN import: {len(df)} rows, {len(df.columns)} columns")

    col_map = {
        "Protein.Group": "protein_id",
        "Protein.Ids": "protein_id",
        "Protein.Names": "gene_name",
        "Genes": "gene_name",
        "First.Protein.Description": "description",
    }
    for old, new in col_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    return df


def import_generic(path: Path) -> pd.DataFrame:
    """Import generic CSV/TSV proteomics data."""
    sep = _detect_separator(path)
    df = pd.read_csv(path, sep=sep)
    logger.info(f"Generic import: {len(df)} rows, {len(df.columns)} columns")

    # Try to identify protein ID column
    id_candidates = ["protein_id", "Protein", "ProteinID", "protein", "accession", "Accession"]
    for cand in id_candidates:
        if cand in df.columns:
            if cand != "protein_id":
                df = df.rename(columns={cand: "protein_id"})
            break

    return df


def _dispatch_import(fmt: str, path: Path) -> pd.DataFrame:
    """Route to format-specific importer."""
    importers = {
        "maxquant": import_maxquant,
        "fragpipe": import_fragpipe,
        "diann": import_diann,
        "generic": import_generic,
    }
    if fmt not in importers:
        raise ValueError(f"Unsupported format: {fmt}. Supported: {list(importers)}")
    return importers[fmt](path)


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------
def generate_demo_data(output_dir: Path) -> Path:
    """Generate demo data mimicking MaxQuant proteinGroups.txt."""
    rng = np.random.default_rng(42)
    n_proteins = 200
    n_samples = 6

    proteins = [f"sp|P{i:05d}|PROT{i}_HUMAN" for i in range(n_proteins)]
    genes = [f"GENE{i}" for i in range(n_proteins)]

    data = {
        "Protein IDs": proteins,
        "Gene names": genes,
        "Number of proteins": [1] * n_proteins,
        "Peptides": rng.integers(2, 30, n_proteins),
        "Unique peptides": rng.integers(1, 25, n_proteins),
        "Sequence coverage [%]": np.round(rng.uniform(5, 80, n_proteins), 1),
        "Mol. weight [kDa]": np.round(rng.uniform(10, 300, n_proteins), 1),
        "Score": np.round(rng.uniform(5, 300, n_proteins), 2),
        "Reverse": [""] * n_proteins,
        "Potential contaminant": [""] * n_proteins,
    }

    # Add sample intensities
    for i in range(n_samples):
        intensities = rng.lognormal(22, 3, n_proteins)
        intensities[rng.random(n_proteins) < 0.05] = 0  # 5% missing
        data[f"Intensity sample_{i+1}"] = np.round(intensities, 0)

    # Add a few contaminants and reverse hits for filtering demo
    data["Reverse"][-3:] = ["+"] * 3
    data["Potential contaminant"][-5:-3] = ["+"] * 2

    df = pd.DataFrame(data)
    path = output_dir / "demo_proteinGroups.txt"
    df.to_csv(path, sep="\t", index=False)
    logger.info(f"Generated demo MaxQuant-style data: {path}")
    return path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write import summary report."""
    header = generate_report_header(
        title="Proteomics Data Import Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Format": stats["format"],
            "Proteins": str(stats["n_proteins"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Input format**: {stats['format']}",
        f"- **Proteins imported**: {stats['n_proteins']}",
        f"- **Columns**: {stats['n_columns']}",
    ]

    if "intensity_columns" in stats:
        body_lines.append(f"- **Intensity/sample columns**: {stats['intensity_columns']}")
    if "n_filtered" in stats and stats["n_filtered"] > 0:
        body_lines.append(f"- **Entries filtered**: {stats['n_filtered']} (contaminants/reverse/site-only)")

    body_lines.extend(["", "## Output\n",
                        "Standardized data saved to `tables/proteins.csv`"])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Proteomics Data Import")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--format", dest="data_format", default="maxquant",
                        choices=list(SUPPORTED_FORMATS),
                        help="Input data format")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = generate_demo_data(output_dir)
        data_format = "maxquant"
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        data_format = args.data_format
        input_file = args.input_path

    df = _dispatch_import(data_format, data_path)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    df.to_csv(tables_dir / "proteins.csv", index=False)

    # Count intensity columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    intensity_like = [c for c in numeric_cols
                      if any(kw in c.lower() for kw in ("intensity", "lfq", "int_", "abundance"))]

    stats = {
        "format": data_format,
        "n_proteins": len(df),
        "n_columns": len(df.columns),
        "intensity_columns": len(intensity_like),
    }

    write_report(output_dir, stats, input_file)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Data import complete: {stats['n_proteins']} proteins from {data_format} format")


if __name__ == "__main__":
    main()
