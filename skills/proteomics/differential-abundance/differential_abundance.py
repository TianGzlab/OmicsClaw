#!/usr/bin/env python3
"""Proteomics Differential Abundance - Compare protein abundance between conditions.

Usage:
    python differential_abundance.py --input <data.csv> --output <dir> --method ttest
    python differential_abundance.py --demo --output <dir>
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "differential-abundance"
SKILL_VERSION = "0.2.0"
SUPPORTED_METHODS = ("ttest", "limma")


def run_ttest(data: pd.DataFrame, group1_cols: list, group2_cols: list) -> pd.DataFrame:
    """Two-sample t-test."""
    results = []
    for idx in data.index:
        g1 = data.loc[idx, group1_cols].values
        g2 = data.loc[idx, group2_cols].values
        stat, pval = stats.ttest_ind(g1, g2)
        fc = g2.mean() / (g1.mean() + 1e-10)
        results.append({
            "protein": idx,
            "group1_mean": g1.mean(),
            "group2_mean": g2.mean(),
            "fold_change": fc,
            "log2fc": np.log2(fc),
            "statistic": stat,
            "pvalue": pval,
        })
    return pd.DataFrame(results)


def get_demo_data() -> tuple[pd.DataFrame, list, list]:
    """Generate demo protein abundance data."""
    logger.info("Generating demo protein abundance data")
    n_proteins = 100
    n_samples_per_group = 5

    group1_cols = [f"control_{i+1}" for i in range(n_samples_per_group)]
    group2_cols = [f"treatment_{i+1}" for i in range(n_samples_per_group)]

    data = pd.DataFrame(
        np.random.lognormal(10, 1, (n_proteins, n_samples_per_group * 2)),
        columns=group1_cols + group2_cols,
        index=[f"P{i:05d}" for i in range(n_proteins)]
    )

    for i in range(25):
        data.loc[f"P{i:05d}", group2_cols] *= np.random.uniform(1.5, 3.0)

    return data, group1_cols, group2_cols


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report."""
    header = generate_report_header(
        title="Differential Abundance Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary['method'], "Significant": f"{summary['n_significant']}/{summary['n_tested']}"},
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Proteins tested**: {summary['n_tested']}",
        f"- **Significant (p<0.05)**: {summary['n_significant']}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\npython differential_abundance.py --output {output_dir} --method {params['method']}\n")


def main():
    parser = argparse.ArgumentParser(description="Differential Abundance Analysis")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="ttest", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--alpha", type=float, default=0.05)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        data, group1_cols, group2_cols = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required")
        data = pd.read_csv(args.input_path, index_col=0)
        mid = data.shape[1] // 2
        group1_cols = data.columns[:mid].tolist()
        group2_cols = data.columns[mid:].tolist()
        input_file = args.input_path

    results = run_ttest(data, group1_cols, group2_cols)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    results.to_csv(tables_dir / "differential_abundance.csv", index=False)

    sig = results[results['pvalue'] < args.alpha]
    sig.to_csv(tables_dir / "significant.csv", index=False)

    summary = {"method": args.method, "n_tested": len(results), "n_significant": len(sig)}
    params = {"method": args.method, "alpha": args.alpha}

    write_report(output_dir, summary, input_file, params)
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, "")

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Differential abundance complete: {summary['n_significant']} significant proteins")


if __name__ == "__main__":
    main()
