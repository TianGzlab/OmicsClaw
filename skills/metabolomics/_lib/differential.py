"""Welch tests and BH correction for metabolomics contrasts."""
import numpy as np
import pandas as pd

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
