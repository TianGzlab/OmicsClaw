"""Imputation and normalization on feature tables."""
import logging
import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)

def _detect_sample_cols(df: pd.DataFrame) -> list[str]:
    """Auto-detect sample intensity columns."""
    sample_cols = [
        c for c in df.columns
        if c.startswith("sample") or c.startswith("intensity")
    ]
    if not sample_cols:
        non_sample = {"feature_id", "mz", "rt", "name", "id"}
        sample_cols = [
            c for c in df.columns
            if c not in non_sample and pd.api.types.is_numeric_dtype(df[c])
        ]
    return sample_cols


def _count_missing(mat: pd.DataFrame) -> int:
    """Count missing (NaN) and zero values in a numeric matrix."""
    return int((mat == 0).sum().sum() + mat.isna().sum().sum())


def impute_min(mat: pd.DataFrame) -> pd.DataFrame:
    """Replace zeros/NaN with half the global non-zero minimum."""
    mat = mat.replace(0, np.nan)
    positive_vals = mat.values[mat.values > 0]
    fill_val = float(positive_vals.min()) / 2 if len(positive_vals) > 0 else 1.0
    return mat.fillna(fill_val)


def impute_median(mat: pd.DataFrame) -> pd.DataFrame:
    """Replace zeros/NaN with per-column median of non-zero values."""
    mat = mat.replace(0, np.nan)
    for col in mat.columns:
        positive = mat[col][mat[col] > 0]
        fill_val = float(positive.median()) if len(positive) > 0 else 1.0
        mat[col] = mat[col].fillna(fill_val)
    return mat


def impute_knn(mat: pd.DataFrame, n_neighbors: int = 5) -> pd.DataFrame:
    """KNN imputation using sklearn.impute.KNNImputer.

    Missing values (0 and NaN) are first converted to NaN, then imputed using
    the values from the K nearest neighbouring features (rows).
    """
    from sklearn.impute import KNNImputer

    mat = mat.replace(0, np.nan)

    # Transpose: KNNImputer works on rows, and we want to impute across
    # features using sample-neighbour information.
    imputer = KNNImputer(n_neighbors=min(n_neighbors, max(1, mat.shape[0] - 1)))
    imputed = imputer.fit_transform(mat.values)

    return pd.DataFrame(imputed, index=mat.index, columns=mat.columns)


_IMPUTE_DISPATCH = {
    "min": impute_min,
    "median": impute_median,
    "knn": impute_knn,
}


def normalize_tic(mat: pd.DataFrame) -> pd.DataFrame:
    """Total-ion-count normalization."""
    col_sums = mat.sum(axis=0).replace(0, np.nan)
    global_sum = col_sums.median()
    return mat.div(col_sums, axis=1).mul(global_sum)


def normalize_median(mat: pd.DataFrame) -> pd.DataFrame:
    """Median normalization."""
    col_medians = mat.median(axis=0).replace(0, np.nan)
    global_median = col_medians.median()
    return mat.div(col_medians, axis=1).mul(global_median)


def normalize_log(mat: pd.DataFrame) -> pd.DataFrame:
    """Log2(x + 1) transformation."""
    return np.log2(mat + 1)


_NORM_DISPATCH = {
    "tic": normalize_tic,
    "median": normalize_median,
    "log": normalize_log,
}


def quantify_features(
    data: pd.DataFrame,
    impute_method: str = "min",
    norm_method: str = "tic",
) -> tuple[pd.DataFrame, dict]:
    """Quantify, impute missing values, and normalize.

    Returns (processed_df, stats_dict).
    """
    df = data.copy()

    sample_cols = _detect_sample_cols(df)
    if not sample_cols:
        raise ValueError("Could not auto-detect sample columns in the input file.")

    logger.info(
        "Quantifying %d features across %d samples (impute=%s, norm=%s)",
        len(df), len(sample_cols), impute_method, norm_method,
    )

    mat = df[sample_cols].copy()
    if not mat.gt(0).any(axis=0).all():
        raise ValueError('Each sample must contain at least one positive observed intensity')
    n_missing_before = _count_missing(mat)

    # Impute
    impute_fn = _IMPUTE_DISPATCH.get(impute_method)
    if impute_fn is None:
        raise ValueError(f"Unknown impute method: {impute_method}")
    mat = impute_fn(mat)

    # Normalize
    norm_fn = _NORM_DISPATCH.get(norm_method)
    if norm_fn is None:
        raise ValueError(f"Unknown norm method: {norm_method}")
    mat = norm_fn(mat)

    df[sample_cols] = mat
    n_missing_after = _count_missing(mat)

    return df, {
        "n_features": len(df),
        "n_samples": len(sample_cols),
        "n_missing_before": n_missing_before,
        "n_missing_after": n_missing_after,
        "impute_method": impute_method,
        "norm_method": norm_method,
    }
