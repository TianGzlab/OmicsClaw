"""Protein-table calculations shared by the public library and CLI."""
from __future__ import annotations
import logging
import re
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

AMINO_ACIDS = list("ACDEFGHIKLMNPQRSTVWY")


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


def demo_data(*, random_state: int = 42):
    n_spectra = 1000
    """Generate realistic demo peptide identification results.

    Simulates a typical bottom-up proteomics search engine output
    with realistic identification rate (~40-60%) and score distributions.
    """
    rng = np.random.default_rng(random_state)
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
