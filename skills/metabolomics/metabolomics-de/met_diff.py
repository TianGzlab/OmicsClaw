#!/usr/bin/env python3
"""Metabolomics Differential Analysis — PCA, PLS-DA, univariate statistics.

Performs Welch's t-test with Benjamini-Hochberg FDR correction, log2 fold-change,
and optional PCA visualisation.

Usage:
    python met_diff.py --input <features.csv> --output <dir>
    python met_diff.py --demo --output <dir>
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

SKILL_NAME = "met-diff"
SKILL_VERSION = "0.5.0"


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def generate_demo_data(output_dir: Path) -> Path:
    """Build the seeded synthetic CLI fixture."""
    from skills.metabolomics._lib.demo import de
    data = de()
    path = output_dir / "demo_quantified.csv"
    data.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Univariate analysis
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
        title="Metabolomics Differential Analysis Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Significant (FDR<0.05)": str(summary.get("n_significant_fdr05", 0)),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Features**: {summary['n_features']}",
        f"- **Group A samples**: {summary['n_group_a']}",
        f"- **Group B samples**: {summary['n_group_b']}",
        f"- **Significant (FDR < 0.05)**: {summary['n_significant_fdr05']}",
        "",
        "## Method\n",
        "Welch's t-test (`scipy.stats.ttest_ind(equal_var=False)`) with "
        "Benjamini-Hochberg FDR correction.",
        "",
        "## Parameters\n",
    ]
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
    parser = argparse.ArgumentParser(description="Metabolomics Differential Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--group-a-prefix", default="ctrl")
    parser.add_argument("--group-b-prefix", default="treat")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data_path = generate_demo_data(output_dir)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        data_path = Path(args.input_path)

    df = pd.read_csv(data_path)

    group_a_cols = [c for c in df.columns if c.startswith(args.group_a_prefix)]
    group_b_cols = [c for c in df.columns if c.startswith(args.group_b_prefix)]

    if not group_a_cols or not group_b_cols:
        raise ValueError(
            f"Could not find columns starting with '{args.group_a_prefix}' / "
            f"'{args.group_b_prefix}'"
        )

    # Univariate analysis
    library = load_skill("metabolomics-de")
    de_result = library.differential_expression(df, group_a_prefix=args.group_a_prefix, group_b_prefix=args.group_b_prefix)

    library.run_info(de_result, keep=False)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    de_result.to_csv(tables_dir / "differential_features.csv", index=False)

    # Significant subset
    sig = de_result[de_result["fdr"] < 0.05]
    sig.to_csv(tables_dir / "significant_features.csv", index=False)

    # PCA
    sample_cols = group_a_cols + group_b_cols
    try:
        figure = library.pca_figure(df, group_a_prefix=args.group_a_prefix, group_b_prefix=args.group_b_prefix)
        (output_dir / "figures").mkdir(exist_ok=True)
        figure.savefig(output_dir / "figures" / "pca_scores.png", dpi=150, bbox_inches="tight")
    except Exception as e:
        logger.warning("PCA failed: %s", e)

    n_sig = int(len(sig))

    summary = {
        "n_features": len(df),
        "n_group_a": len(group_a_cols),
        "n_group_b": len(group_b_cols),
        "n_significant_fdr05": n_sig,
    }
    params = {
        "group_a_prefix": args.group_a_prefix,
        "group_b_prefix": args.group_b_prefix,
    }

    write_report(output_dir, summary, args.input_path if not args.demo else None, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Differential analysis complete: {n_sig} significant features (FDR<0.05)")


if __name__ == "__main__":
    main()
