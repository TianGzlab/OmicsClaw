"""Protein-table calculations shared by the public library and CLI."""
from __future__ import annotations
import logging
import re
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PTM_MASS_SHIFTS = {
    "Phosphorylation": 79.9663,
    "Acetylation": 42.0106,
    "Methylation": 14.0157,
    "Ubiquitination": 114.0429,  # GG remnant after trypsin
    "Oxidation": 15.9949,
    "Deamidation": 0.9840,
    "Carbamylation": 43.0058,
    "Succinylation": 100.0160,
}


PTM_TARGETS = {
    "Phosphorylation": ["S", "T", "Y"],
    "Acetylation": ["K", "N-term"],
    "Methylation": ["K", "R"],
    "Ubiquitination": ["K"],
    "Oxidation": ["M", "W"],
    "Deamidation": ["N", "Q"],
}


def analyse_ptm_sites(df: pd.DataFrame, loc_threshold: float = 0.75) -> tuple[pd.DataFrame, dict]:
    """Analyze PTM sites from identification results.

    Performs:
    1. Site classification by localization probability
       - Class I: prob >= 0.75 (well-localized)
       - Class II: 0.50 <= prob < 0.75
       - Class III: prob < 0.50 (poorly localized)
    2. PTM type distribution
    3. Amino acid preference analysis
    4. Motif counting (for phosphorylation)

    Reference: Olsen et al. (2006) Cell 127:635-648 (Class I/II/III scheme)
    """
    df = df.copy()

    # Ensure required columns exist
    required = ["protein", "ptm_type"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: '{col}'")

    # Site localization classification (Olsen et al. 2006)
    if "localization_probability" in df.columns:
        conditions = [
            df["localization_probability"] >= loc_threshold,
            df["localization_probability"] >= 0.50,
        ]
        choices = ["Class I", "Class II"]
        df["site_class"] = np.select(conditions, choices, default="Class III")
    else:
        df["site_class"] = "Unknown"

    # PTM type distribution
    ptm_counts = df["ptm_type"].value_counts().to_dict()

    # Amino acid distribution (if available)
    aa_counts = {}
    if "amino_acid" in df.columns:
        aa_counts = df["amino_acid"].value_counts().to_dict()

    # Class distribution
    class_counts = df["site_class"].value_counts().to_dict()

    # Per-protein PTM burden
    ptm_per_protein = df.groupby("protein").size()

    # Phosphorylation-specific analysis
    phospho_stats = {}
    if "Phosphorylation" in ptm_counts:
        phospho = df[df["ptm_type"] == "Phosphorylation"]
        if "amino_acid" in phospho.columns:
            phospho_aa = phospho["amino_acid"].value_counts().to_dict()
            total_phospho = len(phospho)
            phospho_stats = {
                "n_pSer": phospho_aa.get("S", 0),
                "n_pThr": phospho_aa.get("T", 0),
                "n_pTyr": phospho_aa.get("Y", 0),
                "pct_pSer": round(phospho_aa.get("S", 0) / total_phospho * 100, 1) if total_phospho > 0 else 0,
                "pct_pThr": round(phospho_aa.get("T", 0) / total_phospho * 100, 1) if total_phospho > 0 else 0,
                "pct_pTyr": round(phospho_aa.get("Y", 0) / total_phospho * 100, 1) if total_phospho > 0 else 0,
            }

    stats = {
        "n_total_sites": len(df),
        "n_unique_proteins": df["protein"].nunique(),
        "ptm_type_distribution": {str(k): int(v) for k, v in ptm_counts.items()},
        "site_class_distribution": {str(k): int(v) for k, v in class_counts.items()},
        "n_class_I": class_counts.get("Class I", 0),
        "mean_ptm_per_protein": round(float(ptm_per_protein.mean()), 2),
        "max_ptm_per_protein": int(ptm_per_protein.max()),
    }
    if aa_counts:
        stats["amino_acid_distribution"] = {str(k): int(v) for k, v in aa_counts.items()}
    if phospho_stats:
        stats["phosphorylation"] = phospho_stats

    return df, stats


def demo_data(*, random_state: int = 42):
    """Generate realistic PTM analysis demo data.

    Simulates phosphoproteomics experiment output with site localization
    probabilities (similar to MaxQuant Phospho(STY)Sites.txt format).
    """
    rng = np.random.default_rng(random_state)
    n_sites = 200

    proteins = [f"P{i:05d}" for i in range(50)]
    aa_pool = list("ACDEFGHIKLMNPQRSTVWY")

    records = []
    for i in range(n_sites):
        protein = rng.choice(proteins)
        # Generate a window sequence around the modification site
        window_size = 15  # ±7 amino acids around the site
        window = "".join(rng.choice(aa_pool, window_size))

        ptm_type = rng.choice(
            ["Phosphorylation", "Phosphorylation", "Phosphorylation",  # 60% phospho
             "Acetylation", "Oxidation", "Ubiquitination", "Methylation",
             "Deamidation"]
        )

        # Localization probability (higher is better, >0.75 is Class I)
        loc_prob = float(rng.beta(5, 2))  # Skewed toward high confidence

        # Determine the modified amino acid
        if ptm_type == "Phosphorylation":
            mod_aa = rng.choice(["S", "T", "Y"], p=[0.65, 0.25, 0.10])
        elif ptm_type == "Acetylation":
            mod_aa = "K"
        elif ptm_type == "Oxidation":
            mod_aa = "M"
        elif ptm_type == "Ubiquitination":
            mod_aa = "K"
        elif ptm_type == "Methylation":
            mod_aa = rng.choice(["K", "R"])
        else:
            mod_aa = rng.choice(["N", "Q"])

        # Place the modified AA in the center of the window
        center = window_size // 2
        window_list = list(window)
        window_list[center] = mod_aa
        window = "".join(window_list)

        records.append({
            "protein": protein,
            "position": int(rng.integers(1, 800)),
            "amino_acid": mod_aa,
            "ptm_type": ptm_type,
            "localization_probability": round(loc_prob, 4),
            "score": round(float(rng.uniform(10, 200)), 2),
            "intensity": round(float(rng.lognormal(12, 2)), 2),
            "window_sequence": window,
            "peptide": "".join(rng.choice(aa_pool, rng.integers(8, 25))),
        })

    df = pd.DataFrame(records)
    return df
