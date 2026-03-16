#!/usr/bin/env python3
"""Proteomics Structural Analysis — cross-linking MS and structural proteomics.

Implements XL-MS data analysis including:
- Cross-link classification (inter/intra-protein)
- Distance constraint validation against common crosslinker limits
- FDR filtering
- Summary statistics and reporting

Usage:
    python struct_proteomics.py --input <crosslinks.csv> --output <dir>
    python struct_proteomics.py --demo --output <dir>
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

SKILL_NAME = "struct-proteomics"
SKILL_VERSION = "0.2.0"

# Common crosslinker distance constraints (Cα-Cα, in Ångströms)
# Reference: Rappsilber (2011) J Struct Biol 173(3):530-540
CROSSLINKER_CONSTRAINTS = {
    "DSS": 30.0,     # Disuccinimidyl suberate, ~11.4Å spacer + side chains
    "BS3": 30.0,     # Bis(sulfosuccinimidyl) suberate, same as DSS
    "EDC": 20.0,     # Zero-length crosslinker
    "DSSO": 30.0,    # Cleavable crosslinker
    "DSBU": 30.0,    # Cleavable crosslinker
}


def generate_demo_data(output_dir: Path) -> Path:
    """Generate synthetic cross-link MS data with realistic properties.

    Simulates a typical XL-MS experiment:
    - Mix of inter and intra-protein crosslinks
    - Distance distribution centered around ~15-25Å (typical for DSS/BS3)
    - Score and FDR distributions
    """
    rng = np.random.default_rng(42)
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
    path = output_dir / "demo_crosslinks.csv"
    df.to_csv(path, index=False)
    logger.info(f"Generated demo XL-MS data ({n_xlinks} crosslinks): {path}")
    return path


def analyse_crosslinks(data_path: Path, fdr_threshold: float = 0.05,
                       crosslinker: str = "DSS") -> tuple[pd.DataFrame, dict]:
    """Comprehensive cross-link analysis.

    Performs:
    1. FDR filtering
    2. Inter/intra-protein classification
    3. Distance constraint validation
    4. Quality statistics

    Reference: Rappsilber (2011) J Struct Biol 173(3):530-540.
    """
    df = pd.read_csv(data_path)
    n_raw = len(df)
    logger.info(f"Loaded {n_raw} crosslinks from {data_path.name}")

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
        satisfaction_rate = round(n_satisfied / len(df_filtered) * 100, 1) if len(df_filtered) > 0 else 0

        df_filtered["constraint_satisfied"] = distances <= max_distance

        dist_stats = {
            "mean_distance": round(float(distances.mean()), 2),
            "median_distance": round(float(distances.median()), 2),
            "min_distance": round(float(distances.min()), 2),
            "max_distance_observed": round(float(distances.max()), 2),
        }
    else:
        n_satisfied = n_passed_fdr
        n_violated = 0
        satisfaction_rate = 100.0
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


def write_report(output_dir: Path, stats: dict, input_file: str | None) -> None:
    """Write structural proteomics report."""
    header = generate_report_header(
        title="Structural Proteomics / XL-MS Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Crosslinks (after FDR)": str(stats["n_after_fdr"]),
            "Crosslinker": stats["crosslinker"],
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Raw crosslinks**: {stats['n_raw_crosslinks']}",
        f"- **After FDR filtering**: {stats['n_after_fdr']}",
        f"- **Inter-protein**: {stats['n_inter_protein']}",
        f"- **Intra-protein**: {stats['n_intra_protein']}",
        f"- **Unique proteins**: {stats['n_unique_proteins']}",
        f"- **Unique protein pairs**: {stats['n_unique_protein_pairs']}",
        "",
        "### Distance Constraints\n",
        f"- **Crosslinker**: {stats['crosslinker']} (max Cα-Cα: {stats['max_distance_constraint']}Å)",
        f"- **Satisfied**: {stats['n_constraint_satisfied']}",
        f"- **Violated**: {stats['n_constraint_violated']}",
        f"- **Satisfaction rate**: {stats['constraint_satisfaction_rate']}%",
    ]

    if "mean_distance" in stats:
        body_lines.extend([
            "",
            "### Distance Distribution\n",
            f"- **Mean**: {stats['mean_distance']}Å",
            f"- **Median**: {stats['median_distance']}Å",
            f"- **Range**: {stats['min_distance']}Å – {stats['max_distance_observed']}Å",
        ])

    body_lines.extend([
        "",
        "## Methodology\n",
        f"- Crosslinker constraints from Rappsilber (2011) J Struct Biol 173:530-540",
        f"- DSS/BS3 max Cα-Cα distance: 30Å (11.4Å spacer + side chain flexibility)",
        f"- FDR filtering applied before distance validation",
    ])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)


def main():
    parser = argparse.ArgumentParser(description="Structural Proteomics / XL-MS Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--crosslinker", default="DSS",
                        choices=list(CROSSLINKER_CONSTRAINTS.keys()),
                        help="Crosslinker type for distance constraints")
    parser.add_argument("--fdr", type=float, default=0.05,
                        help="FDR threshold for filtering")
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

    result_df, stats = analyse_crosslinks(
        data_path,
        fdr_threshold=args.fdr,
        crosslinker=args.crosslinker,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "crosslinks.csv", index=False)

    # Save inter-protein links separately
    if "link_type" in result_df.columns:
        inter = result_df[result_df["link_type"] == "inter-protein"]
        inter.to_csv(tables_dir / "inter_protein_crosslinks.csv", index=False)

    write_report(output_dir, stats, input_file)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Structural analysis complete: {stats['n_after_fdr']} crosslinks "
          f"({stats['n_inter_protein']} inter-protein, "
          f"{stats['constraint_satisfaction_rate']}% satisfy distance constraint)")


if __name__ == "__main__":
    main()
