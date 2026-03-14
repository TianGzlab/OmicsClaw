#!/usr/bin/env python3
"""Metabolomics Differential Analysis — PCA, PLS-DA, univariate statistics.

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

from omicsclaw.common.report import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "met-diff"
SKILL_VERSION = "0.1.0"


def generate_demo_data(output_dir):
    """Generate demo quantified feature table with condition labels."""
    n_features = 100
    n_per_group = 4

    data = {"feature_id": [f"M{i:04d}" for i in range(n_features)]}

    # Control group
    for s in range(n_per_group):
        data[f"ctrl_{s+1}"] = np.round(np.random.lognormal(10, 1.5, n_features), 2)
    # Treatment group (some features differentially abundant)
    for s in range(n_per_group):
        vals = np.random.lognormal(10, 1.5, n_features)
        # Inject differential features for first 20
        vals[:20] *= np.random.uniform(1.5, 3.0, 20)
        data[f"treat_{s+1}"] = np.round(vals, 2)

    df = pd.DataFrame(data)
    path = output_dir / "demo_quantified.csv"
    df.to_csv(path, index=False)
    logger.info(f"Generated demo data: {path}")
    return path


def run_univariate(df, group_a_cols, group_b_cols):
    """Run t-test for each feature between two groups."""
    from scipy import stats as sp_stats

    records = []
    feature_col = df.columns[0]

    for idx, row in df.iterrows():
        a_vals = row[group_a_cols].values.astype(float)
        b_vals = row[group_b_cols].values.astype(float)

        if np.std(a_vals) == 0 and np.std(b_vals) == 0:
            pval = 1.0
            tstat = 0.0
        else:
            tstat, pval = sp_stats.ttest_ind(a_vals, b_vals, equal_var=False)

        log2fc = np.log2(np.mean(b_vals) / np.mean(a_vals)) if np.mean(a_vals) > 0 else 0

        records.append({
            "feature_id": row[feature_col],
            "mean_group_a": round(float(np.mean(a_vals)), 4),
            "mean_group_b": round(float(np.mean(b_vals)), 4),
            "log2fc": round(float(log2fc), 4),
            "tstat": round(float(tstat), 4),
            "pvalue": float(pval),
        })

    result = pd.DataFrame(records)
    # FDR correction (Benjamini-Hochberg)
    from scipy.stats import false_discovery_control
    try:
        result["fdr"] = false_discovery_control(result["pvalue"].values, method="bh")
    except Exception:
        # Fallback manual BH
        n = len(result)
        ranked = result["pvalue"].rank()
        result["fdr"] = result["pvalue"] * n / ranked
        result["fdr"] = result["fdr"].clip(upper=1.0)

    return result.sort_values("pvalue").reset_index(drop=True)


def run_pca(df, sample_cols, output_dir):
    """Run PCA and save scores plot."""
    from sklearn.decomposition import PCA
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    X = df[sample_cols].values.T  # samples x features
    X = np.nan_to_num(X, nan=0.0)

    pca = PCA(n_components=min(2, X.shape[0]))
    scores = pca.fit_transform(X)

    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(scores[:, 0], scores[:, 1] if scores.shape[1] > 1 else np.zeros(len(scores)))
    for i, name in enumerate(sample_cols):
        ax.annotate(name, (scores[i, 0], scores[i, 1] if scores.shape[1] > 1 else 0),
                    fontsize=8)
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)")
    if scores.shape[1] > 1:
        ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)")
    ax.set_title("PCA Scores Plot")
    plt.savefig(fig_dir / "pca_scores.png", dpi=150, bbox_inches="tight")
    plt.close()

    return pca.explained_variance_ratio_


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
        raise ValueError(f"Could not find columns starting with '{args.group_a_prefix}' / '{args.group_b_prefix}'")

    # Univariate
    de_result = run_univariate(df, group_a_cols, group_b_cols)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    de_result.to_csv(tables_dir / "differential_features.csv", index=False)

    # PCA
    sample_cols = group_a_cols + group_b_cols
    try:
        run_pca(df, sample_cols, output_dir)
    except Exception as e:
        logger.warning(f"PCA failed: {e}")

    n_sig = int((de_result["fdr"] < 0.05).sum())

    stats = {
        "n_features": len(df),
        "n_group_a": len(group_a_cols),
        "n_group_b": len(group_b_cols),
        "n_significant_fdr05": n_sig,
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, stats, {})

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Differential analysis complete: {n_sig} significant features (FDR<0.05)")


if __name__ == "__main__":
    main()
