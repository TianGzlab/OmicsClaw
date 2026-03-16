#!/usr/bin/env python3
"""Metabolomics Normalization — Normalize metabolite abundance data.

Supports five methods: median, quantile, total-ion-count, PQN, and log2.

Usage:
    python normalization.py --input <data.csv> --output <dir> --method median
    python normalization.py --demo --output <dir>
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

SKILL_NAME = "normalization"
SKILL_VERSION = "0.3.0"
SUPPORTED_METHODS = ("median", "quantile", "total", "pqn", "log")


# ---------------------------------------------------------------------------
# Normalization methods
# ---------------------------------------------------------------------------

def normalize_median(data: pd.DataFrame) -> pd.DataFrame:
    """Median normalization — scale each sample so its median equals the
    global median-of-medians.

    Standard approach in MetaboAnalyst / Metabolomics Workbench.
    """
    medians = data.median(axis=0)
    global_median = medians.median()
    # Guard against zero-medians
    medians = medians.replace(0, np.nan)
    return data.div(medians, axis=1).mul(global_median)


def normalize_quantile(data: pd.DataFrame) -> pd.DataFrame:
    """Quantile normalization (Bolstad et al., 2003).

    Algorithm:
        1. Sort each column independently.
        2. Compute the row-wise mean of the sorted matrix.
        3. Assign each value the mean that corresponds to its rank.

    This makes all column distributions identical.
    """
    # Step 1: record ranks (average ties)
    ranks = data.rank(method="average", axis=0)

    # Step 2: sort each column, compute row-wise mean of sorted values
    sorted_df = pd.DataFrame(
        np.sort(data.values, axis=0),
        index=data.index,
        columns=data.columns,
    )
    row_means = sorted_df.mean(axis=1).values  # shape (n_features,)

    # Step 3: map ranks → mean values
    # For integer ranks this is a direct lookup; for averaged (tied) ranks
    # we linearly interpolate.
    result = data.copy()
    for col in data.columns:
        col_ranks = ranks[col].values  # 1-based
        # np.interp expects sorted xp; rank positions 1..n map to row_means
        xp = np.arange(1, len(row_means) + 1, dtype=float)
        result[col] = np.interp(col_ranks, xp, row_means)

    return result


def normalize_total(data: pd.DataFrame) -> pd.DataFrame:
    """Total-ion-count (TIC) normalization — scale each sample by its
    column sum, then multiply by the median of all column sums.
    """
    col_sums = data.sum(axis=0)
    global_sum = col_sums.median()
    col_sums = col_sums.replace(0, np.nan)
    return data.div(col_sums, axis=1).mul(global_sum)


def normalize_pqn(data: pd.DataFrame) -> pd.DataFrame:
    """Probabilistic Quotient Normalization (Dieterle et al., 2006).

    The reference spectrum is the **median spectrum** across all samples,
    which is the recommended robust approach for most metabolomics studies.

    Steps:
        1. Compute the reference spectrum as the column-wise median of a
           TIC-prenormalized matrix.
        2. For each sample, compute the quotient of every feature vs. the
           reference.
        3. The normalization factor for the sample is the median of those
           quotients.
        4. Divide each sample by its factor.
    """
    # Pre-normalize by TIC so that overall dilution does not dominate
    col_sums = data.sum(axis=0).replace(0, np.nan)
    prenorm = data.div(col_sums, axis=1).mul(col_sums.median())

    # Reference spectrum: median across samples for each feature
    reference = prenorm.median(axis=1)

    # Quotients
    reference_safe = reference.replace(0, np.nan)
    quotients = prenorm.div(reference_safe, axis=0)

    # Normalization factors: median quotient per sample
    factors = quotients.median(axis=0)
    factors = factors.replace(0, np.nan)

    return data.div(factors, axis=1)


def normalize_log(data: pd.DataFrame) -> pd.DataFrame:
    """Log2 transformation (add pseudo-count of 1)."""
    return np.log2(data + 1)


_DISPATCH: dict[str, callable] = {
    "median": normalize_median,
    "quantile": normalize_quantile,
    "total": normalize_total,
    "pqn": normalize_pqn,
    "log": normalize_log,
}


def dispatch_method(method: str, data: pd.DataFrame) -> pd.DataFrame:
    """Route to the requested normalization method."""
    fn = _DISPATCH.get(method)
    if fn is None:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")
    return fn(data)


# ---------------------------------------------------------------------------
# Demo & report
# ---------------------------------------------------------------------------

def get_demo_data() -> pd.DataFrame:
    """Generate demo metabolomics data with realistic structure."""
    logger.info("Generating demo metabolomics data")
    rng = np.random.default_rng(42)
    n_features = 150
    n_samples = 12

    # Base intensities from log-normal, with varying dilution per sample
    base = rng.lognormal(10, 2, (n_features, n_samples))
    dilution_factors = rng.uniform(0.5, 2.0, n_samples)
    data = base * dilution_factors[np.newaxis, :]

    return pd.DataFrame(
        data,
        columns=[f"sample_{i + 1}" for i in range(n_samples)],
        index=[f"feature_{i + 1}" for i in range(n_features)],
    )


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write comprehensive markdown report."""
    header = generate_report_header(
        title="Metabolite Normalization Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Features": str(summary["n_features"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Features**: {summary['n_features']}",
        f"- **Samples**: {summary['n_samples']}",
        "",
        "## Method Details\n",
    ]
    method_desc = {
        "median": "Scale each sample so that its median equals the global median-of-medians.",
        "quantile": "Quantile normalization (Bolstad et al., 2003): sort → row-mean → rank-assign.",
        "total": "Total-ion-count normalization: scale by column sums.",
        "pqn": "Probabilistic Quotient Normalization (Dieterle et al., 2006): "
               "reference = median spectrum, factor = median quotient.",
        "log": "Log2(x + 1) transformation.",
    }
    body_lines.append(f"> {method_desc.get(summary['method'], 'N/A')}")
    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python metabolomics_normalization.py --input <input.csv> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Metabolite Normalization")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="median", choices=list(SUPPORTED_METHODS))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data = pd.read_csv(args.input_path, index_col=0)
        input_file = args.input_path

    logger.info("Input: %d features × %d samples", data.shape[0], data.shape[1])

    normalized = dispatch_method(args.method, data)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    normalized.to_csv(tables_dir / "normalized.csv")

    summary = {
        "method": args.method,
        "n_features": data.shape[0],
        "n_samples": data.shape[1],
    }

    params = {"method": args.method}

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Normalization complete: {summary['n_features']} features, method={args.method}")


if __name__ == "__main__":
    main()
