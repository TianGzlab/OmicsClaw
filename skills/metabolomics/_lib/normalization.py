"""Normalization calculations shared by metabolomics entry points."""
import numpy as np
import pandas as pd

SUPPORTED_METHODS = ("median", "quantile", "total", "pqn", "log")

def normalize_median(data: pd.DataFrame) -> pd.DataFrame:
    """Median normalization — scale each sample so its median equals the
    global median-of-medians.

    Standard approach in MetaboAnalyst / Metabolomics Workbench.
    """
    medians = data.median(axis=0)
    global_median = medians.median()
    # Guard against zero-medians
    medians = medians.replace(0, np.nan)
    return data.div(medians, axis=1).mul(global_median)


def normalize_quantile(data: pd.DataFrame) -> pd.DataFrame:
    """Quantile normalization (Bolstad et al., 2003).

    Algorithm:
        1. Sort each column independently.
        2. Compute the row-wise mean of the sorted matrix.
        3. Assign each value the mean that corresponds to its rank.

    This makes all column distributions identical.
    """
    # Step 1: record ranks (average ties)
    ranks = data.rank(method="average", axis=0)

    # Step 2: sort each column, compute row-wise mean of sorted values
    sorted_df = pd.DataFrame(
        np.sort(data.values, axis=0),
        index=data.index,
        columns=data.columns,
    )
    row_means = sorted_df.mean(axis=1).values  # shape (n_features,)

    # Step 3: map ranks → mean values
    # For integer ranks this is a direct lookup; for averaged (tied) ranks
    # we linearly interpolate.
    result = data.copy()
    for col in data.columns:
        col_ranks = ranks[col].values  # 1-based
        # np.interp expects sorted xp; rank positions 1..n map to row_means
        xp = np.arange(1, len(row_means) + 1, dtype=float)
        result[col] = np.interp(col_ranks, xp, row_means)

    return result


def normalize_total(data: pd.DataFrame) -> pd.DataFrame:
    """Total-ion-count (TIC) normalization — scale each sample by its
    column sum, then multiply by the median of all column sums.
    """
    col_sums = data.sum(axis=0)
    global_sum = col_sums.median()
    col_sums = col_sums.replace(0, np.nan)
    return data.div(col_sums, axis=1).mul(global_sum)


def normalize_pqn(data: pd.DataFrame) -> pd.DataFrame:
    """Probabilistic Quotient Normalization (Dieterle et al., 2006).

    The reference spectrum is the **median spectrum** across all samples,
    which is the recommended robust approach for most metabolomics studies.

    Steps:
        1. Compute the reference spectrum as the column-wise median of a
           TIC-prenormalized matrix.
        2. For each sample, compute the quotient of every feature vs. the
           reference.
        3. The normalization factor for the sample is the median of those
           quotients.
        4. Divide each sample by its factor.
    """
    # Pre-normalize by TIC so that overall dilution does not dominate
    col_sums = data.sum(axis=0).replace(0, np.nan)
    prenorm = data.div(col_sums, axis=1).mul(col_sums.median())

    # Reference spectrum: median across samples for each feature
    reference = prenorm.median(axis=1)

    # Quotients
    reference_safe = reference.replace(0, np.nan)
    quotients = prenorm.div(reference_safe, axis=0)

    # Normalization factors: median quotient per sample
    factors = quotients.median(axis=0)
    factors = factors.replace(0, np.nan)

    return data.div(factors, axis=1)


def normalize_log(data: pd.DataFrame) -> pd.DataFrame:
    """Log2 transformation (add pseudo-count of 1)."""
    return np.log2(data + 1)


_DISPATCH: dict[str, callable] = {
    "median": normalize_median,
    "quantile": normalize_quantile,
    "total": normalize_total,
    "pqn": normalize_pqn,
    "log": normalize_log,
}


def dispatch_method(method: str, data: pd.DataFrame) -> pd.DataFrame:
    """Route to the requested normalization method."""
    fn = _DISPATCH.get(method)
    if fn is None:
        raise ValueError(f"Unknown method: {method}. Choose from {SUPPORTED_METHODS}")
    return fn(data)
