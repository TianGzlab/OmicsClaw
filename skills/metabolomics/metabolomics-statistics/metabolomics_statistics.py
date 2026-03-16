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

SKILL_NAME = "statistical-analysis"
SKILL_VERSION = "0.3.0"
SUPPORTED_METHODS = ("ttest", "anova", "wilcoxon", "kruskal")


# ---------------------------------------------------------------------------
# BH FDR (same portable implementation as met_diff)
# ---------------------------------------------------------------------------

def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR correction with monotone step-down enforcement."""
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    order = np.argsort(pv)
    sorted_p = pv[order]
    adjusted = np.empty(n)
    adjusted[-1] = sorted_p[-1]
    for i in range(n - 2, -1, -1):
        adjusted[i] = min(sorted_p[i] * n / (i + 1), adjusted[i + 1])
    adjusted = np.clip(adjusted, 0, 1)
    result = np.empty(n)
    result[order] = adjusted
    return result


# ---------------------------------------------------------------------------
# Statistical test functions
# ---------------------------------------------------------------------------

def _safe_fold_change(g1_mean: float, g2_mean: float) -> float:
    """Compute log2 fold-change with safe handling of zeros."""
    if g1_mean > 0 and g2_mean > 0:
        return float(np.log2(g2_mean / g1_mean))
    elif g1_mean > 0:
        return -np.inf
    elif g2_mean > 0:
        return np.inf
    return 0.0


def run_ttest(
    data: pd.DataFrame,
    group1_cols: list[str],
    group2_cols: list[str],
) -> pd.DataFrame:
    """Welch's t-test (equal_var=False) — recommended for metabolomics."""
    results = []
    for idx in data.index:
        g1 = data.loc[idx, group1_cols].values.astype(float)
        g2 = data.loc[idx, group2_cols].values.astype(float)

        if np.std(g1) == 0 and np.std(g2) == 0:
            stat_val, pval = 0.0, 1.0
        else:
            stat_val, pval = stats.ttest_ind(g1, g2, equal_var=False)

        results.append({
            "feature": idx,
            "group1_mean": float(g1.mean()),
            "group2_mean": float(g2.mean()),
            "fold_change": float(g2.mean() / g1.mean()) if g1.mean() > 0 else np.nan,
            "log2fc": _safe_fold_change(float(g1.mean()), float(g2.mean())),
            "statistic": float(stat_val),
            "pvalue": float(pval),
        })
    return pd.DataFrame(results)


def run_wilcoxon(
    data: pd.DataFrame,
    group1_cols: list[str],
    group2_cols: list[str],
) -> pd.DataFrame:
    """Wilcoxon rank-sum (Mann-Whitney U) test."""
    results = []
    for idx in data.index:
        g1 = data.loc[idx, group1_cols].values.astype(float)
        g2 = data.loc[idx, group2_cols].values.astype(float)

        try:
            stat_val, pval = stats.ranksums(g1, g2)
        except Exception:
            stat_val, pval = 0.0, 1.0

        results.append({
            "feature": idx,
            "group1_mean": float(g1.mean()),
            "group2_mean": float(g2.mean()),
            "fold_change": float(g2.mean() / g1.mean()) if g1.mean() > 0 else np.nan,
            "log2fc": _safe_fold_change(float(g1.mean()), float(g2.mean())),
            "statistic": float(stat_val),
            "pvalue": float(pval),
        })
    return pd.DataFrame(results)


def run_anova(
    data: pd.DataFrame,
    group1_cols: list[str],
    group2_cols: list[str],
) -> pd.DataFrame:
    """One-way ANOVA (two-group case equivalent to equal-variance t-test).

    For more than two groups, extend group_cols lists or supply a design matrix.
    """
    results = []
    for idx in data.index:
        g1 = data.loc[idx, group1_cols].values.astype(float)
        g2 = data.loc[idx, group2_cols].values.astype(float)

        try:
            stat_val, pval = stats.f_oneway(g1, g2)
        except Exception:
            stat_val, pval = 0.0, 1.0

        results.append({
            "feature": idx,
            "group1_mean": float(g1.mean()),
            "group2_mean": float(g2.mean()),
            "fold_change": float(g2.mean() / g1.mean()) if g1.mean() > 0 else np.nan,
            "log2fc": _safe_fold_change(float(g1.mean()), float(g2.mean())),
            "statistic": float(stat_val),
            "pvalue": float(pval),
        })
    return pd.DataFrame(results)


def run_kruskal(
    data: pd.DataFrame,
    group1_cols: list[str],
    group2_cols: list[str],
) -> pd.DataFrame:
    """Kruskal-Wallis H test (non-parametric ANOVA)."""
    results = []
    for idx in data.index:
        g1 = data.loc[idx, group1_cols].values.astype(float)
        g2 = data.loc[idx, group2_cols].values.astype(float)

        try:
            stat_val, pval = stats.kruskal(g1, g2)
        except Exception:
            stat_val, pval = 0.0, 1.0

        results.append({
            "feature": idx,
            "group1_mean": float(g1.mean()),
            "group2_mean": float(g2.mean()),
            "fold_change": float(g2.mean() / g1.mean()) if g1.mean() > 0 else np.nan,
            "log2fc": _safe_fold_change(float(g1.mean()), float(g2.mean())),
            "statistic": float(stat_val),
            "pvalue": float(pval),
        })
    return pd.DataFrame(results)


_DISPATCH = {
    "ttest": run_ttest,
    "wilcoxon": run_wilcoxon,
    "anova": run_anova,
    "kruskal": run_kruskal,
}


def dispatch_method(
    method: str,
    data: pd.DataFrame,
    group1_cols: list[str],
    group2_cols: list[str],
) -> pd.DataFrame:
    """Route to the requested statistical method."""
    fn = _DISPATCH.get(method)
    if fn is None:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")
    return fn(data, group1_cols, group2_cols)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def get_demo_data() -> tuple[pd.DataFrame, list[str], list[str]]:
    """Generate demo metabolomics data."""
    logger.info("Generating demo metabolomics data")
    rng = np.random.default_rng(42)
    n_features = 100
    n_per_group = 6

    group1_cols = [f"control_{i + 1}" for i in range(n_per_group)]
    group2_cols = [f"treatment_{i + 1}" for i in range(n_per_group)]

    data = pd.DataFrame(
        rng.lognormal(10, 1, (n_features, n_per_group * 2)),
        columns=group1_cols + group2_cols,
        index=[f"metabolite_{i + 1}" for i in range(n_features)],
    )

    # Inject differential features
    for i in range(20):
        data.loc[f"metabolite_{i + 1}", group2_cols] *= rng.uniform(1.5, 3.0)

    return data, group1_cols, group2_cols


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

    results = dispatch_method(args.method, data, group1_cols, group2_cols)

    # FDR correction
    results["fdr"] = _benjamini_hochberg(results["pvalue"].values)

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
