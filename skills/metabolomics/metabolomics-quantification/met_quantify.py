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

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import write_result_json
from skills._sdk.notebook import load_skill

logger = logging.getLogger(__name__)

SKILL_NAME = "met-quantify"
SKILL_VERSION = "0.5.0"


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def generate_demo_data(output_dir: Path) -> Path:
    """Build the seeded synthetic CLI fixture."""
    from skills.metabolomics._lib.demo import quantification
    data = quantification()
    path = output_dir / "demo_features.csv"
    data.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Core quantification pipeline
# ---------------------------------------------------------------------------

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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
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

    library = load_skill("metabolomics-quantification")
    result_df = library.quantify(pd.read_csv(data_path), impute=args.impute, normalize=args.normalize)
    summary = library.run_info(result_df, keep=False)

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
