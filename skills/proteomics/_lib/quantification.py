"""Protein-table calculations shared by the public library and CLI."""
from __future__ import annotations
import logging
import re
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("lfq", "spectral_count", "ibaq")


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
        raise ValueError('iBAQ requires sequence or n_theoretical_peptides')

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


def demo_data(*, random_state: int = 42):
    """Generate demo peptide data with realistic structure."""
    logger.info("Generating demo peptide data")
    rng = np.random.default_rng(random_state)

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
