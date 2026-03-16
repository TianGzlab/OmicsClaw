#!/usr/bin/env python3
"""Metabolomics Quantification — feature quantification, imputation, normalization.

Supports three imputation methods (min/2, median, KNN) and three normalization
methods (TIC, median, log2).

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

from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "met-quantify"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def generate_demo_data(output_dir: Path) -> Path:
    """Generate synthetic metabolomics feature table with ~10% missing values."""
    rng = np.random.default_rng(42)
    n_features = 120
    n_samples = 8

    data = {
        "feature_id": [f"M{i:04d}" for i in range(n_features)],
        "mz": np.round(rng.uniform(80, 1200, n_features), 4),
        "rt": np.round(rng.uniform(0.5, 25, n_features), 3),
    }
    for s in range(n_samples):
        intensities = rng.lognormal(10, 2, n_features)
        # Inject ~10 % missing values (set to 0)
        mask = rng.random(n_features) < 0.1
        intensities[mask] = 0
        data[f"sample_{s + 1}"] = np.round(intensities, 2)

    df = pd.DataFrame(data)
    path = output_dir / "demo_features.csv"
    df.to_csv(path, index=False)
    logger.info("Generated demo data: %s", path)
    return path


# ---------------------------------------------------------------------------
# Core quantification pipeline
# ---------------------------------------------------------------------------

def _detect_sample_cols(df: pd.DataFrame) -> list[str]:
    """Auto-detect sample intensity columns."""
    sample_cols = [
        c for c in df.columns
        if c.startswith("sample") or c.startswith("intensity")
    ]
    if not sample_cols:
        non_sample = {"feature_id", "mz", "rt", "name", "id"}
        sample_cols = [
            c for c in df.columns
            if c not in non_sample and pd.api.types.is_numeric_dtype(df[c])
        ]
    return sample_cols


def _count_missing(mat: pd.DataFrame) -> int:
    """Count missing (NaN) and zero values in a numeric matrix."""
    return int((mat == 0).sum().sum() + mat.isna().sum().sum())


def impute_min(mat: pd.DataFrame) -> pd.DataFrame:
    """Replace zeros/NaN with half the global non-zero minimum."""
    mat = mat.replace(0, np.nan)
    positive_vals = mat.values[mat.values > 0]
    fill_val = float(positive_vals.min()) / 2 if len(positive_vals) > 0 else 1.0
    return mat.fillna(fill_val)


def impute_median(mat: pd.DataFrame) -> pd.DataFrame:
    """Replace zeros/NaN with per-column median of non-zero values."""
    mat = mat.replace(0, np.nan)
    for col in mat.columns:
        positive = mat[col][mat[col] > 0]
        fill_val = float(positive.median()) if len(positive) > 0 else 1.0
        mat[col] = mat[col].fillna(fill_val)
    return mat


def impute_knn(mat: pd.DataFrame, n_neighbors: int = 5) -> pd.DataFrame:
    """KNN imputation using sklearn.impute.KNNImputer.

    Missing values (0 and NaN) are first converted to NaN, then imputed using
    the values from the K nearest neighbouring features (rows).
    """
    from sklearn.impute import KNNImputer

    mat = mat.replace(0, np.nan)

    # Transpose: KNNImputer works on rows, and we want to impute across
    # features using sample-neighbour information.
    imputer = KNNImputer(n_neighbors=min(n_neighbors, max(1, mat.shape[0] - 1)))
    imputed = imputer.fit_transform(mat.values)

    return pd.DataFrame(imputed, index=mat.index, columns=mat.columns)


_IMPUTE_DISPATCH = {
    "min": impute_min,
    "median": impute_median,
    "knn": impute_knn,
}


def normalize_tic(mat: pd.DataFrame) -> pd.DataFrame:
    """Total-ion-count normalization."""
    col_sums = mat.sum(axis=0).replace(0, np.nan)
    global_sum = col_sums.median()
    return mat.div(col_sums, axis=1).mul(global_sum)


def normalize_median(mat: pd.DataFrame) -> pd.DataFrame:
    """Median normalization."""
    col_medians = mat.median(axis=0).replace(0, np.nan)
    global_median = col_medians.median()
    return mat.div(col_medians, axis=1).mul(global_median)


def normalize_log(mat: pd.DataFrame) -> pd.DataFrame:
    """Log2(x + 1) transformation."""
    return np.log2(mat + 1)


_NORM_DISPATCH = {
    "tic": normalize_tic,
    "median": normalize_median,
    "log": normalize_log,
}


def quantify_features(
    data_path: Path | str,
    impute_method: str = "min",
    norm_method: str = "tic",
) -> tuple[pd.DataFrame, dict]:
    """Quantify, impute missing values, and normalize.

    Returns (processed_df, stats_dict).
    """
    df = pd.read_csv(data_path)

    sample_cols = _detect_sample_cols(df)
    if not sample_cols:
        raise ValueError("Could not auto-detect sample columns in the input file.")

    logger.info(
        "Quantifying %d features across %d samples (impute=%s, norm=%s)",
        len(df), len(sample_cols), impute_method, norm_method,
    )

    mat = df[sample_cols].copy()
    n_missing_before = _count_missing(mat)

    # Impute
    impute_fn = _IMPUTE_DISPATCH.get(impute_method)
    if impute_fn is None:
        raise ValueError(f"Unknown impute method: {impute_method}")
    mat = impute_fn(mat)

    # Normalize
    norm_fn = _NORM_DISPATCH.get(norm_method)
    if norm_fn is None:
        raise ValueError(f"Unknown norm method: {norm_method}")
    mat = norm_fn(mat)

    df[sample_cols] = mat
    n_missing_after = _count_missing(mat)

    return df, {
        "n_features": len(df),
        "n_samples": len(sample_cols),
        "n_missing_before": n_missing_before,
        "n_missing_after": n_missing_after,
        "impute_method": impute_method,
        "norm_method": norm_method,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write markdown report."""
    header = generate_report_header(
        title="Metabolomics Quantification Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Features": str(summary["n_features"]),
            "Samples": str(summary["n_samples"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Features**: {summary['n_features']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Missing values (before)**: {summary['n_missing_before']}",
        f"- **Missing values (after)**: {summary['n_missing_after']}",
        f"- **Imputation method**: {summary['impute_method']}",
        f"- **Normalization method**: {summary['norm_method']}",
        "",
        "## Method\n",
    ]
    desc = {
        "min": "Half-minimum imputation: missing values replaced with min(positive) / 2.",
        "median": "Per-column median imputation: missing values replaced with median of non-zero values.",
        "knn": "KNN imputation (`sklearn.impute.KNNImputer`): missing values imputed from k=5 neighbours.",
    }
    body_lines.append(f"**Imputation**: {desc.get(summary['impute_method'], 'N/A')}")
    body_lines.append("")

    norm_desc = {
        "tic": "Total-ion-count normalization: scale by column sums.",
        "median": "Median normalization: scale by column medians.",
        "log": "Log2(x + 1) transformation.",
    }
    body_lines.append(f"**Normalization**: {norm_desc.get(summary['norm_method'], 'N/A')}")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)
        input_file = args.input_path

    result_df, summary = quantify_features(data_path, args.impute, args.normalize)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(tables_dir / "quantified_features.csv", index=False)

    params = {"impute": args.impute, "normalize": args.normalize}
    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Quantification complete: {summary['n_features']} features, "
        f"{summary['n_samples']} samples, "
        f"missing {summary['n_missing_before']}→{summary['n_missing_after']}"
    )


if __name__ == "__main__":
    main()
