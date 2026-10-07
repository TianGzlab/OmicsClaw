"""Univariate metabolomics tests."""
import numpy as np
import pandas as pd
from scipy import stats
SUPPORTED_METHODS = ("ttest", "anova", "wilcoxon", "kruskal")

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

        stat_val, pval = stats.ranksums(g1, g2)

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

        stat_val, pval = stats.f_oneway(g1, g2)

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

        if np.unique(np.concatenate([g1, g2])).size == 1:
            raise ValueError('Kruskal test is undefined when all values are identical')
        stat_val, pval = stats.kruskal(g1, g2)

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
