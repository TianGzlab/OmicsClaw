#!/usr/bin/env python3
"""Metabolomics Normalization - Normalize metabolite abundance data.

Usage:
    python normalization.py --input <data.csv> --output <dir> --method median
    python normalization.py --demo --output <dir>
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
import pandas as pd
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "normalization"
SKILL_VERSION = "0.2.0"
SUPPORTED_METHODS = ("median", "quantile", "total", "pqn", "log")


def normalize_median(data: pd.DataFrame) -> pd.DataFrame:
    """Median normalization."""
    medians = data.median(axis=0)
    return data / medians * medians.median()


def normalize_quantile(data: pd.DataFrame) -> pd.DataFrame:
    """Quantile normalization."""
    rank_mean = data.stack().groupby(data.rank(method='first').stack().astype(int)).mean()
    return data.rank(method='min').stack().astype(int).map(rank_mean).unstack()


def normalize_total(data: pd.DataFrame) -> pd.DataFrame:
    """Total sum normalization."""
    return data / data.sum(axis=0) * data.sum(axis=0).median()


def normalize_pqn(data: pd.DataFrame, ref_sample: int = 0) -> pd.DataFrame:
    """Probabilistic Quotient Normalization."""
    ref = data.iloc[:, ref_sample]
    quotients = data.div(ref, axis=0)
    factors = quotients.median(axis=0)
    return data / factors


def normalize_log(data: pd.DataFrame) -> pd.DataFrame:
    """Log transformation."""
    return np.log2(data + 1)


def _dispatch_method(method: str, data: pd.DataFrame) -> pd.DataFrame:
    """Route to normalization method."""
    if method == "median":
        return normalize_median(data)
    elif method == "quantile":
        return normalize_quantile(data)
    elif method == "total":
        return normalize_total(data)
    elif method == "pqn":
        return normalize_pqn(data)
    elif method == "log":
        return normalize_log(data)
    else:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")


def get_demo_data() -> pd.DataFrame:
    """Generate demo metabolomics data."""
    logger.info("Generating demo metabolomics data")
    n_features = 150
    n_samples = 12
    data = pd.DataFrame(
        np.random.lognormal(10, 2, (n_features, n_samples)),
        columns=[f"sample_{i+1}" for i in range(n_samples)]
    )
    return data


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Metabolite Normalization Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary['method'],
            "Features": str(summary['n_features']),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Features**: {summary['n_features']}",
        f"- **Samples**: {summary['n_samples']}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python normalization.py --input <input.csv> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


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

    logger.info(f"Input: {data.shape[0]} features x {data.shape[1]} samples")

    normalized = _dispatch_method(args.method, data)

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
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, "")

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Normalization complete: {summary['n_features']} features, method={args.method}")


if __name__ == "__main__":
    main()
