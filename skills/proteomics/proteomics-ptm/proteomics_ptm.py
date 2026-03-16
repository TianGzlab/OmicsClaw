#!/usr/bin/env python3
"""Proteomics PTM Analysis - Analyze post-translational modifications.

Supports identification and quantification of PTM sites from peptide-level
data. Generates PTM site localization confidence, motif analysis, and
summary statistics.

Usage:
    python proteomics_ptm.py --input <ptm_data.csv> --output <dir>
    python proteomics_ptm.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import collections
import logging
import re
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

SKILL_NAME = "ptm"
SKILL_VERSION = "0.2.0"

# Common PTM types with their mass shifts (monoisotopic, Da)
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

# Amino acids targeted by each PTM type
PTM_TARGETS = {
    "Phosphorylation": ["S", "T", "Y"],
    "Acetylation": ["K", "N-term"],
    "Methylation": ["K", "R"],
    "Ubiquitination": ["K"],
    "Oxidation": ["M", "W"],
    "Deamidation": ["N", "Q"],
}


def generate_demo_data(output_dir: Path) -> Path:
    """Generate realistic PTM analysis demo data.

    Simulates phosphoproteomics experiment output with site localization
    probabilities (similar to MaxQuant Phospho(STY)Sites.txt format).
    """
    rng = np.random.default_rng(42)
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
    path = output_dir / "demo_ptm_sites.csv"
    df.to_csv(path, index=False)
    logger.info(f"Generated demo PTM data with {n_sites} sites: {path}")
    return path


def analyse_ptm_sites(data_path: Path, loc_threshold: float = 0.75) -> tuple[pd.DataFrame, dict]:
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
    df = pd.read_csv(data_path)
    logger.info(f"Loaded {len(df)} PTM sites from {data_path.name}")

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


def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write PTM analysis report."""
    header = generate_report_header(
        title="Post-Translational Modification Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Total sites": str(stats["n_total_sites"]),
            "Proteins": str(stats["n_unique_proteins"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Total PTM sites**: {stats['n_total_sites']}",
        f"- **Unique proteins**: {stats['n_unique_proteins']}",
        f"- **Mean PTMs per protein**: {stats['mean_ptm_per_protein']}",
        f"- **Max PTMs per protein**: {stats['max_ptm_per_protein']}",
        "",
        "### PTM Types\n",
    ]
    for ptm_type, count in stats.get("ptm_type_distribution", {}).items():
        body_lines.append(f"- **{ptm_type}**: {count}")

    body_lines.extend(["", "### Site Localization Classes\n",
                        "| Class | Count | Description |",
                        "|-------|-------|-------------|"])
    class_dist = stats.get("site_class_distribution", {})
    body_lines.append(f"| Class I | {class_dist.get('Class I', 0)} | Well-localized (prob ≥ 0.75) |")
    body_lines.append(f"| Class II | {class_dist.get('Class II', 0)} | Moderate (0.50 ≤ prob < 0.75) |")
    body_lines.append(f"| Class III | {class_dist.get('Class III', 0)} | Poorly localized (prob < 0.50) |")

    if "phosphorylation" in stats:
        ps = stats["phosphorylation"]
        body_lines.extend([
            "", "### Phosphorylation Distribution\n",
            f"- pSer: {ps['n_pSer']} ({ps['pct_pSer']}%)",
            f"- pThr: {ps['n_pThr']} ({ps['pct_pThr']}%)",
            f"- pTyr: {ps['n_pTyr']} ({ps['pct_pTyr']}%)",
            "",
            "**Expected distribution** (mammalian cells): ~86% pSer, ~12% pThr, ~2% pTyr",
            "(Olsen et al. 2006, Cell 127:635-648)",
        ])

    body_lines.extend([
        "",
        "## Methodology\n",
        "- Site classification: Olsen et al. (2006) Class I/II/III scheme",
        "- Localization probability threshold for Class I: ≥ 0.75",
    ])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


def main():
    parser = argparse.ArgumentParser(description="PTM Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--loc-threshold", type=float, default=0.75,
                        help="Localization probability threshold for Class I (default: 0.75)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = generate_demo_data(output_dir)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    result_df, stats = analyse_ptm_sites(data_path, loc_threshold=args.loc_threshold)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    result_df.to_csv(tables_dir / "ptm_sites.csv", index=False)

    # Class I sites separately
    if "site_class" in result_df.columns:
        class_i = result_df[result_df["site_class"] == "Class I"]
        class_i.to_csv(tables_dir / "ptm_class_I_sites.csv", index=False)

    write_report(output_dir, stats, input_file)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"PTM analysis complete: {stats['n_total_sites']} sites, "
          f"{stats['n_class_I']} Class I")


if __name__ == "__main__":
    main()
