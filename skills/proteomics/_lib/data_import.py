"""Protein-table calculations shared by the public library and CLI."""
from __future__ import annotations
import logging
import re
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("maxquant", "fragpipe", "diann", "generic")


def _detect_separator(path: Path) -> str:
    """Auto-detect CSV vs TSV."""
    with open(path, "r") as f:
        first_line = f.readline()
    return "\t" if "\t" in first_line else ","


def import_maxquant(df: pd.DataFrame) -> pd.DataFrame:
    """Import MaxQuant proteinGroups.txt output.

    Expected columns: Protein IDs, Gene names, Intensity columns, etc.
    Reference: Cox & Mann (2008) Nature Biotechnology.
    """
    df = df.copy()
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


def import_fragpipe(df: pd.DataFrame) -> pd.DataFrame:
    """Import FragPipe/MSFragger combined_protein.tsv output."""
    df = df.copy()
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


def import_diann(df: pd.DataFrame) -> pd.DataFrame:
    """Import DIA-NN report.tsv or pg_matrix output."""
    df = df.copy()
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


def import_generic(df: pd.DataFrame) -> pd.DataFrame:
    """Import generic CSV/TSV proteomics data."""
    df = df.copy()
    logger.info(f"Generic import: {len(df)} rows, {len(df.columns)} columns")

    # Try to identify protein ID column
    id_candidates = ["protein_id", "Protein", "ProteinID", "protein", "accession", "Accession"]
    for cand in id_candidates:
        if cand in df.columns:
            if cand != "protein_id":
                df = df.rename(columns={cand: "protein_id"})
            break

    return df


def _dispatch_import(fmt: str, df: pd.DataFrame) -> pd.DataFrame:
    """Route to format-specific importer."""
    importers = {
        "maxquant": import_maxquant,
        "fragpipe": import_fragpipe,
        "diann": import_diann,
        "generic": import_generic,
    }
    if fmt not in importers:
        raise ValueError(f"Unsupported format: {fmt}. Supported: {list(importers)}")
    return importers[fmt](df)


def demo_data(*, random_state: int = 42):
    """Generate demo data mimicking MaxQuant proteinGroups.txt."""
    rng = np.random.default_rng(random_state)
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
    return df
