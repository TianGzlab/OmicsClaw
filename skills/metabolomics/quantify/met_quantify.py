#!/usr/bin/env python3
"""Metabolomics Quantification — feature quantification, imputation, normalization.

Usage:
    python met_quantify.py --input <features.csv> --output <dir>
    python met_quantify.py --demo --output <dir>
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

SKILL_NAME = "met-quantify"
SKILL_VERSION = "0.1.0"


def generate_demo_data(output_dir):
    """Generate synthetic metabolomics feature table."""
    n_features = 120
    n_samples = 8

    data = {
        "feature_id": [f"M{i:04d}" for i in range(n_features)],
        "mz": np.round(np.random.uniform(80, 1200, n_features), 4),
        "rt": np.round(np.random.uniform(0.5, 25, n_features), 3),
    }
    for s in range(n_samples):
        intensities = np.random.lognormal(10, 2, n_features)
        # Inject ~10% missing values
        mask = np.random.random(n_features) < 0.1
        intensities[mask] = 0
        data[f"sample_{s+1}"] = np.round(intensities, 2)

    df = pd.DataFrame(data)
    path = output_dir / "demo_features.csv"
    df.to_csv(path, index=False)
    logger.info(f"Generated demo data: {path}")
    return path


def quantify_features(data_path, impute_method="min", norm_method="tic"):
    """Quantify, impute missing values, and normalize."""
    df = pd.read_csv(data_path)

    sample_cols = [c for c in df.columns if c.startswith("sample") or c.startswith("intensity")]
    if not sample_cols:
        # Fallback: assume all numeric columns except feature_id/mz/rt are samples
        non_sample = {"feature_id", "mz", "rt", "name", "id"}
        sample_cols = [c for c in df.columns if c not in non_sample and pd.api.types.is_numeric_dtype(df[c])]

    logger.info(f"Quantifying {len(df)} features across {len(sample_cols)} samples")

    # Impute missing / zero values
    mat = df[sample_cols].copy()
    n_missing_before = (mat == 0).sum().sum() + mat.isna().sum().sum()

    if impute_method == "min":
        min_val = mat[mat > 0].min().min() / 2
        mat = mat.replace(0, np.nan).fillna(min_val)
    elif impute_method == "median":
        for col in sample_cols:
            med = mat[col][mat[col] > 0].median()
            mat[col] = mat[col].replace(0, np.nan).fillna(med)
    elif impute_method == "knn":
        # Placeholder for KNN imputation
        min_val = mat[mat > 0].min().min() / 2
        mat = mat.replace(0, np.nan).fillna(min_val)

    # Normalize
    if norm_method == "tic":
        col_sums = mat.sum(axis=0)
        mat = mat / col_sums * col_sums.median()
    elif norm_method == "median":
        col_medians = mat.median(axis=0)
        mat = mat / col_medians * col_medians.median()
    elif norm_method == "log":
        mat = np.log2(mat + 1)

    df[sample_cols] = mat
    n_missing_after = mat.isna().sum().sum()

    stats = {
        "n_features": len(df),
        "n_samples": len(sample_cols),
        "n_missing_before": int(n_missing_before),
        "n_missing_after": int(n_missing_after),
        "impute_method": impute_method,
        "norm_method": norm_method,
    }

    return df, stats


def main():
    parser = argparse.ArgumentParser(description="Metabolomics Quantification")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--impute", default="min", choices=["min", "median", "knn"])
    parser.add_argument("--normalize", default="tic", choices=["tic", "median", "log"])
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = generate_demo_data(output_dir)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)

    result_df, stats = quantify_features(data_path, args.impute, args.normalize)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "quantified_features.csv", index=False)

    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Quantification complete: {stats['n_features']} features, {stats['n_samples']} samples")


if __name__ == "__main__":
    main()
