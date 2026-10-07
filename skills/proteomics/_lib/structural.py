"""Protein-table calculations shared by the public library and CLI."""
from __future__ import annotations
import logging
import re
from pathlib import Path
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CROSSLINKER_CONSTRAINTS = {
    "DSS": 30.0,     # Disuccinimidyl suberate, ~11.4Å spacer + side chains
    "BS3": 30.0,     # Bis(sulfosuccinimidyl) suberate, same as DSS
    "EDC": 20.0,     # Zero-length crosslinker
    "DSSO": 30.0,    # Cleavable crosslinker
    "DSBU": 30.0,    # Cleavable crosslinker
}


def analyse_crosslinks(df: pd.DataFrame, fdr_threshold: float = 0.05,
                       crosslinker: str = "DSS") -> tuple[pd.DataFrame, dict]:
    """Comprehensive cross-link analysis.

    Performs:
    1. FDR filtering
    2. Inter/intra-protein classification
    3. Distance constraint validation
    4. Quality statistics

    Reference: Rappsilber (2011) J Struct Biol 173(3):530-540.
    """
    df = df.copy()
    n_raw = len(df)

    # FDR filtering
    if "fdr" in df.columns:
        df_filtered = df[df["fdr"] <= fdr_threshold].copy()
        n_passed_fdr = len(df_filtered)
        logger.info(f"FDR filtering (≤{fdr_threshold}): {n_raw} → {n_passed_fdr}")
    else:
        df_filtered = df.copy()
        n_passed_fdr = n_raw

    # Inter/intra classification
    has_proteins = {"protein_a", "protein_b"}.issubset(df_filtered.columns)
    if has_proteins:
        df_filtered["link_type"] = np.where(
            df_filtered["protein_a"] == df_filtered["protein_b"],
            "intra-protein",
            "inter-protein",
        )
        n_inter = int((df_filtered["link_type"] == "inter-protein").sum())
        n_intra = int((df_filtered["link_type"] == "intra-protein").sum())
    else:
        n_inter = 0
        n_intra = len(df_filtered)

    # Distance constraint validation
    max_distance = CROSSLINKER_CONSTRAINTS.get(crosslinker.upper(), 30.0)

    if "distance_angstrom" in df_filtered.columns:
        distances = df_filtered["distance_angstrom"]
        n_satisfied = int((distances <= max_distance).sum())
        n_violated = int((distances > max_distance).sum())
        n_checked = int(distances.notna().sum())
        satisfaction_rate = round(n_satisfied / n_checked * 100, 1) if n_checked else None

        df_filtered["constraint_satisfied"] = (distances <= max_distance).astype('boolean').mask(distances.isna())

        dist_stats = {
            "mean_distance": round(float(distances.mean()), 2),
            "median_distance": round(float(distances.median()), 2),
            "min_distance": round(float(distances.min()), 2),
            "max_distance_observed": round(float(distances.max()), 2),
        } if n_checked else {
            key: None for key in ('mean_distance', 'median_distance', 'min_distance', 'max_distance_observed')
        }
    else:
        n_satisfied = None
        n_violated = None
        satisfaction_rate = None
        dist_stats = {}

    # Unique protein pairs
    if has_proteins:
        inter_df = df_filtered[df_filtered["link_type"] == "inter-protein"]
        pairs = set()
        for _, row in inter_df.iterrows():
            pair = tuple(sorted([row["protein_a"], row["protein_b"]]))
            pairs.add(pair)
        n_unique_pairs = len(pairs)
        n_unique_proteins = len(set(df_filtered["protein_a"]) | set(df_filtered["protein_b"]))
    else:
        n_unique_pairs = 0
        n_unique_proteins = 0

    stats = {
        "n_raw_crosslinks": n_raw,
        "n_after_fdr": n_passed_fdr,
        "n_inter_protein": n_inter,
        "n_intra_protein": n_intra,
        "n_unique_protein_pairs": n_unique_pairs,
        "n_unique_proteins": n_unique_proteins,
        "crosslinker": crosslinker,
        "max_distance_constraint": max_distance,
        "n_constraint_satisfied": n_satisfied,
        "n_constraint_violated": n_violated,
        "constraint_satisfaction_rate": satisfaction_rate,
        **dist_stats,
    }

    return df_filtered, stats


def demo_data(*, random_state: int = 42):
    """Generate synthetic cross-link MS data with realistic properties.

    Simulates a typical XL-MS experiment:
    - Mix of inter and intra-protein crosslinks
    - Distance distribution centered around ~15-25Å (typical for DSS/BS3)
    - Score and FDR distributions
    """
    rng = np.random.default_rng(random_state)
    n_xlinks = 200
    proteins = [f"P{i:04d}" for i in range(20)]

    records = []
    for i in range(n_xlinks):
        prot_a = rng.choice(proteins)
        # ~30% inter-protein, ~70% intra-protein (typical ratio)
        if rng.random() < 0.7:
            prot_b = prot_a
        else:
            prot_b = rng.choice([p for p in proteins if p != prot_a])

        res_a = int(rng.integers(1, 500))
        res_b = int(rng.integers(1, 500))

        # Distances: mostly within crosslinker range, some violations
        if rng.random() < 0.85:
            # Within range (realistic crosslinks)
            distance = float(rng.normal(20, 5))
            distance = max(5.0, min(distance, 35.0))
        else:
            # Distance violations (potential false positives)
            distance = float(rng.uniform(30, 50))

        score = float(rng.exponential(15) + 5)
        fdr = float(rng.beta(0.5, 5))  # Skewed toward low FDR

        records.append({
            "protein_a": prot_a,
            "residue_a": res_a,
            "aa_a": rng.choice(["K", "K", "K", "S", "T", "Y"]),  # Mostly Lys
            "protein_b": prot_b,
            "residue_b": res_b,
            "aa_b": rng.choice(["K", "K", "K", "S", "T", "Y"]),
            "distance_angstrom": round(distance, 2),
            "score": round(score, 3),
            "fdr": round(fdr, 4),
            "crosslinker": "DSS",
        })

    df = pd.DataFrame(records)
    return df
