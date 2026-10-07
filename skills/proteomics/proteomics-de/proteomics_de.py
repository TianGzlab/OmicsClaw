#!/usr/bin/env python3
"""Proteomics Differential Abundance - Compare protein abundance between conditions.

Implements proper statistical testing with BH FDR correction and
log2 fold-change calculation following proteomics best practices.

Usage:
    python proteomics_de.py --input <data.csv> --output <dir> --method ttest
    python proteomics_de.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

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

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "differential-abundance"
SKILL_VERSION = "0.5.0"
SUPPORTED_METHODS = ("ttest", "welch", "mann_whitney")


# ---------------------------------------------------------------------------
# Differential abundance tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(output_dir: Path, summary: dict, input_file: str | None,
                 params: dict) -> None:
    """Write comprehensive markdown report."""
    header = generate_report_header(
        title="Differential Abundance Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Significant": f"{summary['n_significant']}/{summary['n_tested']}",
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Proteins tested**: {summary['n_tested']}",
        f"- **Significant (padj < {params['alpha']})**: {summary['n_significant']}",
        f"- **Up-regulated**: {summary.get('n_up', 'N/A')}",
        f"- **Down-regulated**: {summary.get('n_down', 'N/A')}",
        "",
        "## Methodology\n",
        "- **Fold change**: log2FC = mean(log2(treatment)) - mean(log2(control))",
        "- **Multiple testing**: Benjamini-Hochberg FDR correction",
        "- **Significance**: padj < alpha (BH-adjusted p-value)",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python proteomics_de.py --output {output_dir} --method {params['method']} --alpha {params['alpha']}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    from skills._sdk.notebook import load_skill
    library = load_skill("proteomics-de")
    parser = argparse.ArgumentParser(description="Differential Abundance Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="ttest", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="Significance threshold for BH-adjusted p-values")
    parser.add_argument("--log2fc-threshold", type=float, default=0.0,
                        help="Minimum absolute log2FC for significance (default: 0)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data = library.demo_data()
        mid = data.shape[1] // 2
        group1_cols, group2_cols = list(data.columns[:mid]), list(data.columns[mid:])
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required")
        data = pd.read_csv(args.input_path, index_col=0)
        mid = data.shape[1] // 2
        group1_cols = data.columns[:mid].tolist()
        group2_cols = data.columns[mid:].tolist()
        input_file = args.input_path

    results = library.differential_abundance(data, group1=group1_cols, group2=group2_cols, method=args.method)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    results.to_csv(tables_dir / "differential_abundance.csv", index=False)

    sig = library.significant(results, alpha=args.alpha, log2fc_threshold=args.log2fc_threshold)
    library.run_info(results, keep=False)
    sig.to_csv(tables_dir / "significant.csv", index=False)

    n_up = int((sig["log2fc"] > 0).sum()) if not sig.empty else 0
    n_down = int((sig["log2fc"] < 0).sum()) if not sig.empty else 0

    summary = {
        "method": args.method,
        "n_tested": len(results),
        "n_significant": len(sig),
        "n_up": n_up,
        "n_down": n_down,
    }
    params = {"method": args.method, "alpha": args.alpha,
              "log2fc_threshold": args.log2fc_threshold}

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary,
                      {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Differential abundance complete: {summary['n_significant']} "
          f"significant proteins ({n_up} up, {n_down} down)")


if __name__ == "__main__":
    main()
