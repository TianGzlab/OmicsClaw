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

SKILL_NAME = "met-diff"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def generate_demo_data(output_dir: Path) -> Path:
    """Generate demo quantified feature table with condition labels."""
    rng = np.random.default_rng(42)
    n_features = 100
    n_per_group = 4

    data = {"feature_id": [f"M{i:04d}" for i in range(n_features)]}

    # Control group
    for s in range(n_per_group):
        data[f"ctrl_{s + 1}"] = np.round(rng.lognormal(10, 1.5, n_features), 2)

    # Treatment group — first 20 features are differentially abundant
    for s in range(n_per_group):
        vals = rng.lognormal(10, 1.5, n_features)
        vals[:20] *= rng.uniform(1.5, 3.0, 20)
        data[f"treat_{s + 1}"] = np.round(vals, 2)

    df = pd.DataFrame(data)
    path = output_dir / "demo_quantified.csv"
    df.to_csv(path, index=False)
    logger.info("Generated demo data: %s", path)
    return path


# ---------------------------------------------------------------------------
# Univariate analysis
# ---------------------------------------------------------------------------

def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR correction (manual, scipy-version-agnostic).

    Identical to R's p.adjust(method="BH") / statsmodels multipletests("fdr_bh").
    """
    pvalues = np.asarray(pvalues, dtype=float)
    n = len(pvalues)
    if n == 0:
        return pvalues

    # Sort p-values and record original order
    order = np.argsort(pvalues)
    sorted_p = pvalues[order]

    # BH adjusted p-value: p_adj[i] = min(p[i] * n / rank[i], 1)
    # enforcing monotonicity from the largest rank downward
    adjusted = np.empty(n, dtype=float)
    adjusted[-1] = sorted_p[-1]  # last rank
    for i in range(n - 2, -1, -1):
        rank = i + 1
        adjusted[i] = min(sorted_p[i] * n / rank, adjusted[i + 1])
    adjusted = np.clip(adjusted, 0, 1)

    # Restore original order
    result = np.empty(n, dtype=float)
    result[order] = adjusted
    return result


def run_univariate(
    df: pd.DataFrame,
    group_a_cols: list[str],
    group_b_cols: list[str],
) -> pd.DataFrame:
    """Run Welch's t-test for each feature between two groups.

    Uses ``scipy.stats.ttest_ind(equal_var=False)`` — Welch's t-test is
    recommended for metabolomics because equal variance cannot be assumed
    across all metabolites.
    """
    from scipy import stats as sp_stats

    records: list[dict] = []
    feature_col = df.columns[0]

    for _, row in df.iterrows():
        a_vals = row[group_a_cols].values.astype(float)
        b_vals = row[group_b_cols].values.astype(float)

        # Guard: if both groups have zero variance, skip test
        if np.std(a_vals) == 0 and np.std(b_vals) == 0:
            pval = 1.0
            tstat = 0.0
        else:
            tstat, pval = sp_stats.ttest_ind(a_vals, b_vals, equal_var=False)

        # Safe log2 fold-change
        mean_a = float(np.mean(a_vals))
        mean_b = float(np.mean(b_vals))
        if mean_a > 0 and mean_b > 0:
            log2fc = np.log2(mean_b / mean_a)
        elif mean_a > 0:
            log2fc = -np.inf
        elif mean_b > 0:
            log2fc = np.inf
        else:
            log2fc = 0.0

        records.append({
            "feature_id": row[feature_col],
            "mean_group_a": round(mean_a, 4),
            "mean_group_b": round(mean_b, 4),
            "log2fc": round(float(log2fc), 4) if np.isfinite(log2fc) else float(log2fc),
            "tstat": round(float(tstat), 4),
            "pvalue": float(pval),
        })

    result = pd.DataFrame(records)

    # FDR correction (Benjamini-Hochberg)
    result["fdr"] = _benjamini_hochberg(result["pvalue"].values)

    return result.sort_values("pvalue").reset_index(drop=True)


# ---------------------------------------------------------------------------
# PCA
# ---------------------------------------------------------------------------

def run_pca(
    df: pd.DataFrame,
    sample_cols: list[str],
    group_a_cols: list[str],
    group_b_cols: list[str],
    output_dir: Path,
) -> np.ndarray:
    """Run PCA and save a labelled scores plot.

    Returns the explained variance ratios.
    """
    from sklearn.decomposition import PCA
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    X = df[sample_cols].values.T  # samples × features
    X = np.nan_to_num(X, nan=0.0)

    n_components = min(2, X.shape[0], X.shape[1])
    pca = PCA(n_components=n_components)
    scores = pca.fit_transform(X)

    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 6))

    # Colour by group
    colours = []
    for col in sample_cols:
        if col in group_a_cols:
            colours.append("steelblue")
        elif col in group_b_cols:
            colours.append("coral")
        else:
            colours.append("grey")

    y_vals = scores[:, 1] if scores.shape[1] > 1 else np.zeros(len(scores))

    ax.scatter(scores[:, 0], y_vals, c=colours, s=60, edgecolors="k", linewidths=0.5)
    for i, name in enumerate(sample_cols):
        ax.annotate(name, (scores[i, 0], y_vals[i]), fontsize=7, alpha=0.8)

    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0] * 100:.1f}%)")
    if scores.shape[1] > 1:
        ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1] * 100:.1f}%)")
    ax.set_title("PCA Scores Plot")
    ax.legend(
        handles=[
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="steelblue", label="Group A"),
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="coral", label="Group B"),
        ],
        loc="best",
    )
    plt.savefig(fig_dir / "pca_scores.png", dpi=150, bbox_inches="tight")
    plt.close()

    return pca.explained_variance_ratio_


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
    de_result = run_univariate(df, group_a_cols, group_b_cols)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    de_result.to_csv(tables_dir / "differential_features.csv", index=False)

    # Significant subset
    sig = de_result[de_result["fdr"] < 0.05]
    sig.to_csv(tables_dir / "significant_features.csv", index=False)

    # PCA
    sample_cols = group_a_cols + group_b_cols
    try:
        run_pca(df, sample_cols, group_a_cols, group_b_cols, output_dir)
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
