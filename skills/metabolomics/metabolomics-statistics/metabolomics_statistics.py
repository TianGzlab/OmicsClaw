#!/usr/bin/env python3
"""Metabolomics Statistical Analysis — univariate tests with FDR correction.

Supports Welch's t-test, Wilcoxon rank-sum, one-way ANOVA, and Kruskal-Wallis.

Usage:
    python metabolomics_statistics.py --input <data.csv> --output <dir> --method ttest
    python metabolomics_statistics.py --demo --output <dir>
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
from skills._sdk.notebook import load_skill

logger = logging.getLogger(__name__)

SKILL_NAME = "statistical-analysis"
SKILL_VERSION = "0.5.0"
SUPPORTED_METHODS = ("ttest", "anova", "wilcoxon", "kruskal")


# ---------------------------------------------------------------------------
# BH FDR (same portable implementation as met_diff)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def get_demo_data() -> tuple[pd.DataFrame, list[str], list[str]]:
    """Build the seeded synthetic CLI fixture."""
    from skills.metabolomics._lib.demo import statistics
    data = statistics()
    return data


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Metabolomics Statistical Analysis Report",
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
        f"- **Features tested**: {summary['n_tested']}",
        f"- **Significant (FDR < {params.get('alpha', 0.05)})**: "
        f"{summary['n_significant']} ({summary['sig_rate']:.1f}%)",
        "",
        "## Method Details\n",
    ]
    method_desc = {
        "ttest": "Welch's t-test (unequal variance) with Benjamini-Hochberg FDR correction.",
        "wilcoxon": "Wilcoxon rank-sum (Mann-Whitney U) test with BH FDR correction.",
        "anova": "One-way ANOVA (F-test) with BH FDR correction.",
        "kruskal": "Kruskal-Wallis H test (non-parametric ANOVA) with BH FDR correction.",
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
    cmd = f"python metabolomics_statistics.py --input <input.csv> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Statistical Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="ttest", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument(
        "--group1-prefix",
        default=None,
        help="Column prefix for group 1 (auto-detected in demo mode)",
    )
    parser.add_argument(
        "--group2-prefix",
        default=None,
        help="Column prefix for group 2 (auto-detected in demo mode)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data, group1_cols, group2_cols = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data = pd.read_csv(args.input_path, index_col=0)
        input_file = args.input_path

        # Determine groups from prefixes or fallback to even split
        if args.group1_prefix and args.group2_prefix:
            group1_cols = [c for c in data.columns if c.startswith(args.group1_prefix)]
            group2_cols = [c for c in data.columns if c.startswith(args.group2_prefix)]
        else:
            mid = data.shape[1] // 2
            group1_cols = data.columns[:mid].tolist()
            group2_cols = data.columns[mid:].tolist()
            logger.warning(
                "No --group1-prefix / --group2-prefix given; splitting columns "
                "at midpoint (%d | %d).",
                len(group1_cols),
                len(group2_cols),
            )

        if not group1_cols or not group2_cols:
            raise ValueError(
                "Could not determine group columns. Use --group1-prefix and --group2-prefix."
            )

    logger.info(
        "Input: %d features, %d vs %d samples",
        data.shape[0], len(group1_cols), len(group2_cols),
    )

    library = load_skill("metabolomics-statistics")
    results = library.test_groups(data, method=args.method, alpha=args.alpha, group1_cols=group1_cols, group2_cols=group2_cols)

    library.run_info(results, keep=False)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    results.to_csv(tables_dir / "statistics.csv", index=False)

    sig = results[results["fdr"] < args.alpha]
    sig.to_csv(tables_dir / "significant.csv", index=False)

    summary = {
        "method": args.method,
        "n_tested": len(results),
        "n_significant": len(sig),
        "sig_rate": float(len(sig) / max(len(results), 1) * 100),
    }

    params = {
        "method": args.method,
        "alpha": args.alpha,
    }

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Statistical analysis complete: {summary['n_significant']}/{summary['n_tested']} "
        f"significant features (FDR<{args.alpha})"
    )


if __name__ == "__main__":
    main()
