#!/usr/bin/env python3
"""Proteomics Structural Analysis — cross-linking MS and structural proteomics.

Usage:
    python struct_proteomics.py --input <data.csv> --output <dir>
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

from omicsclaw.common.report import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "struct-proteomics"
SKILL_VERSION = "0.1.0"


def generate_demo_data(output_dir):
    """Generate synthetic cross-link MS data."""
    n_xlinks = 80
    proteins = [f"P{i:04d}" for i in range(20)]

    data = {
        "protein_a": np.random.choice(proteins, n_xlinks),
        "residue_a": np.random.randint(1, 500, n_xlinks),
        "protein_b": np.random.choice(proteins, n_xlinks),
        "residue_b": np.random.randint(1, 500, n_xlinks),
        "distance_angstrom": np.round(np.random.uniform(5, 35, n_xlinks), 2),
        "score": np.round(np.random.uniform(0.5, 50, n_xlinks), 3),
        "fdr": np.round(np.random.uniform(0.001, 0.1, n_xlinks), 4),
    }

    df = pd.DataFrame(data)
    path = output_dir / "demo_crosslinks.csv"
    df.to_csv(path, index=False)
    logger.info(f"Generated demo XL-MS data: {path}")
    return path


def analyse_crosslinks(data_path):
    """Basic cross-link analysis."""
    df = pd.read_csv(data_path)

    n_total = len(df)
    n_inter = (df["protein_a"] != df["protein_b"]).sum() if {"protein_a", "protein_b"}.issubset(df.columns) else 0
    n_intra = n_total - n_inter

    stats = {
        "n_crosslinks": n_total,
        "n_inter_protein": int(n_inter),
        "n_intra_protein": int(n_intra),
    }
    if "distance_angstrom" in df.columns:
        stats["mean_distance"] = round(float(df["distance_angstrom"].mean()), 2)
    if "fdr" in df.columns:
        stats["n_significant"] = int((df["fdr"] < 0.05).sum())

    return df, stats


def main():
    parser = argparse.ArgumentParser(description="Structural Proteomics / XL-MS Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="xlinkx", choices=["xlinkx", "plink", "xisearch"])
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = generate_demo_data(output_dir)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)

    result_df, stats = analyse_crosslinks(data_path)
    stats["method"] = args.method

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "crosslinks.csv", index=False)

    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Structural analysis complete: {stats['n_crosslinks']} crosslinks "
          f"({stats['n_inter_protein']} inter-protein)")


if __name__ == "__main__":
    main()
