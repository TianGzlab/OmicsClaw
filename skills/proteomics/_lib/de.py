"""Protein-table calculations shared by the public library and CLI."""
from __future__ import annotations
import logging
import re
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("ttest", "welch", "mann_whitney")


def benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR correction.

    Reference: Benjamini & Hochberg (1995). Controlling the False Discovery
    Rate: A Practical and Powerful Approach to Multiple Testing. JRSS-B 57(1).

    Returns adjusted p-values (q-values) preserving rank monotonicity.
    """
    n = len(pvalues)
    if n == 0:
        return np.array([])

    # Handle NaN: keep them as NaN in the result
    finite_mask = np.isfinite(pvalues)
    adjusted = np.full_like(pvalues, np.nan, dtype=float)

    if finite_mask.sum() == 0:
        return adjusted

    finite_pvals = pvalues[finite_mask]
    n_finite = len(finite_pvals)

    # Sort p-values and compute BH adjusted values
    sort_idx = np.argsort(finite_pvals)
    sorted_pvals = finite_pvals[sort_idx]
    ranks = np.arange(1, n_finite + 1, dtype=float)

    # BH formula: adjusted_p[i] = p[i] * n / rank[i]
    adj = sorted_pvals * n_finite / ranks

    # Enforce monotonicity (step-up): walk from largest to smallest,
    # ensure each adjusted p is <= the next larger one
    for i in range(n_finite - 2, -1, -1):
        adj[i] = min(adj[i], adj[i + 1])

    # Clip to [0, 1]
    adj = np.clip(adj, 0.0, 1.0)

    # Unsort
    result_finite = np.empty(n_finite, dtype=float)
    result_finite[sort_idx] = adj
    adjusted[finite_mask] = result_finite

    return adjusted


def run_ttest(data: pd.DataFrame, group1_cols: list, group2_cols: list,
              equal_var: bool = True) -> pd.DataFrame:
    """Two-sample t-test with proper log2 fold-change calculation.

    Best practice: log2FC = mean(log2(group2)) - mean(log2(group1))
    This is equivalent to log2(geometric_mean(g2) / geometric_mean(g1))
    and is the standard in proteomics DE analysis.
    """
    results = []
    for protein_id in data.index:
        g1 = data.loc[protein_id, group1_cols].values.astype(float)
        g2 = data.loc[protein_id, group2_cols].values.astype(float)

        # Replace zeros with NaN to avoid log(0)
        g1_clean = np.where(g1 > 0, g1, np.nan)
        g2_clean = np.where(g2 > 0, g2, np.nan)

        # Log2 transform for fold-change calculation
        log2_g1 = np.log2(g1_clean)
        log2_g2 = np.log2(g2_clean)

        # Compute log2 fold-change as difference of means in log-space
        mean_log2_g1 = np.nanmean(log2_g1)
        mean_log2_g2 = np.nanmean(log2_g2)
        log2fc = mean_log2_g2 - mean_log2_g1

        # Statistical test on log2-transformed data (standard for intensity data)
        valid_g1 = log2_g1[np.isfinite(log2_g1)]
        valid_g2 = log2_g2[np.isfinite(log2_g2)]

        if len(valid_g1) >= 2 and len(valid_g2) >= 2:
            stat, pval = stats.ttest_ind(valid_g1, valid_g2, equal_var=equal_var)
        else:
            stat, pval = np.nan, np.nan

        results.append({
            "protein": protein_id,
            "group1_mean": float(np.nanmean(g1)),
            "group2_mean": float(np.nanmean(g2)),
            "log2fc": float(log2fc) if np.isfinite(log2fc) else np.nan,
            "statistic": float(stat) if np.isfinite(stat) else np.nan,
            "pvalue": float(pval) if np.isfinite(pval) else np.nan,
        })

    df = pd.DataFrame(results)

    # Apply BH FDR correction
    if not df.empty:
        df["padj"] = benjamini_hochberg(df["pvalue"].values)

    return df


def run_mann_whitney(data: pd.DataFrame, group1_cols: list,
                     group2_cols: list) -> pd.DataFrame:
    """Mann-Whitney U test (non-parametric alternative)."""
    results = []
    for protein_id in data.index:
        g1 = data.loc[protein_id, group1_cols].values.astype(float)
        g2 = data.loc[protein_id, group2_cols].values.astype(float)

        g1_clean = g1[g1 > 0]
        g2_clean = g2[g2 > 0]

        log2_g1 = np.log2(g1_clean) if len(g1_clean) > 0 else np.array([])
        log2_g2 = np.log2(g2_clean) if len(g2_clean) > 0 else np.array([])

        mean_log2_g1 = np.mean(log2_g1) if len(log2_g1) > 0 else np.nan
        mean_log2_g2 = np.mean(log2_g2) if len(log2_g2) > 0 else np.nan

        log2fc = mean_log2_g2 - mean_log2_g1

        if len(g1_clean) >= 2 and len(g2_clean) >= 2:
            stat, pval = stats.mannwhitneyu(g1_clean, g2_clean,
                                            alternative='two-sided')
        else:
            stat, pval = np.nan, np.nan

        results.append({
            "protein": protein_id,
            "group1_mean": float(np.mean(g1)),
            "group2_mean": float(np.mean(g2)),
            "log2fc": float(log2fc) if np.isfinite(log2fc) else np.nan,
            "statistic": float(stat) if np.isfinite(stat) else np.nan,
            "pvalue": float(pval) if np.isfinite(pval) else np.nan,
        })

    df = pd.DataFrame(results)
    if not df.empty:
        df["padj"] = benjamini_hochberg(df["pvalue"].values)
    return df


def _dispatch_method(method: str, data: pd.DataFrame,
                     group1_cols: list, group2_cols: list) -> pd.DataFrame:
    """Route to differential abundance method."""
    if method == "ttest":
        return run_ttest(data, group1_cols, group2_cols, equal_var=True)
    elif method == "welch":
        return run_ttest(data, group1_cols, group2_cols, equal_var=False)
    elif method == "mann_whitney":
        return run_mann_whitney(data, group1_cols, group2_cols)
    else:
        raise ValueError(f"Unknown method: {method}. Supported: {SUPPORTED_METHODS}")


def demo_data(*, random_state: int = 42):
    """Generate demo protein abundance data with known DE proteins."""
    logger.info("Generating demo protein abundance data")
    n_proteins = 100
    n_samples_per_group = 5

    group1_cols = [f"control_{i+1}" for i in range(n_samples_per_group)]
    group2_cols = [f"treatment_{i+1}" for i in range(n_samples_per_group)]

    rng = np.random.default_rng(random_state)

    data = pd.DataFrame(
        rng.lognormal(10, 1, (n_proteins, n_samples_per_group * 2)),
        columns=group1_cols + group2_cols,
        index=[f"P{i:05d}" for i in range(n_proteins)],
    )

    # Introduce differential abundance for first 25 proteins
    for i in range(25):
        data.loc[f"P{i:05d}", group2_cols] *= rng.uniform(1.5, 3.0)

    return data
