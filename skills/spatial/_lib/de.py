"""Spatial differential expression utilities.

Provides two analysis layers:

- Scanpy marker discovery (`wilcoxon`, `t-test`) on log-normalized expression.
- Sample-aware pseudobulk PyDESeq2 (`pydeseq2`) on raw integer-like counts.

The PyDESeq2 path is intentionally stricter than the Scanpy path:
it only supports explicit two-group contrasts and requires a real `sample_key`
so OmicsClaw can build pseudobulk replicates instead of fabricating them.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("wilcoxon", "t-test", "pydeseq2")
SCANPY_METHODS = ("wilcoxon", "t-test")
COUNT_BASED_METHODS = ("pydeseq2",)

VALID_SCANPY_CORR_METHODS = ("benjamini-hochberg", "bonferroni")
VALID_PYDESEQ2_FIT_TYPES = ("parametric", "mean")
VALID_PYDESEQ2_SIZE_FACTORS_FIT_TYPES = ("ratio", "poscounts", "iterative")

METHOD_PARAM_DEFAULTS = {
    "common": {
        "groupby": "leiden",
        "n_top_genes": 10,
        "fdr_threshold": 0.05,
        "log2fc_threshold": 1.0,
    },
    "scanpy": {
        "scanpy_corr_method": "benjamini-hochberg",
        "scanpy_rankby_abs": False,
        "scanpy_pts": False,
        "filter_markers": True,
        "min_in_group_fraction": 0.25,
        "min_fold_change": 1.0,
        "max_out_group_fraction": 0.5,
        "filter_compare_abs": False,
    },
    "wilcoxon": {
        "scanpy_tie_correct": False,
    },
    "t-test": {},
    "pydeseq2": {
        "sample_key": "sample_id",
        "min_cells_per_sample": 10,
        "min_counts_per_gene": 10,
        "pydeseq2_fit_type": "parametric",
        "pydeseq2_size_factors_fit_type": "ratio",
        "pydeseq2_refit_cooks": True,
        "pydeseq2_alpha": 0.05,
        "pydeseq2_cooks_filter": True,
        "pydeseq2_independent_filter": True,
        "pydeseq2_n_cpus": 1,
    },
}


def _matrix_to_ndarray(X) -> np.ndarray:
    """Convert dense / sparse / h5py-backed arrays to a NumPy ndarray safely."""
    if sparse.issparse(X):
        return X.toarray()
    if isinstance(X, np.ndarray):
        return X
    try:
        return np.asarray(X)
    except Exception:
        return np.array(X)


def _preview_values(X, limit: int = 1000) -> np.ndarray:
    """Return a 1D preview vector without assuming sparse `.data` semantics."""
    arr = _matrix_to_ndarray(X)
    flat = np.ravel(arr)
    if flat.size == 0:
        return flat
    return flat[: min(limit, flat.size)]


def _ensure_obs_string(adata, key: str) -> pd.Series:
    """Normalize an obs column to string labels for robust CLI comparisons."""
    adata.obs[key] = adata.obs[key].astype(str)
    return adata.obs[key]


def _get_raw_counts(adata) -> np.ndarray:
    """Extract raw integer-like counts for pseudobulk aggregation."""
    if "counts" in adata.layers:
        logger.info("Using raw counts from adata.layers['counts']")
        X = adata.layers["counts"]
    elif adata.raw is not None:
        logger.warning(
            "No 'counts' layer found; using adata.raw.X. "
            "Ensure adata.raw contains raw counts, not normalized values."
        )
        X = adata.raw.X
    else:
        logger.warning(
            "No 'counts' layer or adata.raw found; using adata.X. "
            "If adata.X is log-normalized, pseudobulk sums will be invalid."
        )
        X = adata.X

    X = _matrix_to_ndarray(X)
    if np.any(X < 0):
        raise ValueError("PyDESeq2 requires non-negative counts; detected negative values.")

    if X.dtype.kind == "f":
        sample_vals = _preview_values(X)
        if not np.allclose(sample_vals, np.round(sample_vals)):
            logger.warning(
                "Non-integer counts detected in the pseudobulk input matrix. "
                "Rounding to integers for PyDESeq2."
            )
        X = np.round(X).astype(int)
    elif X.dtype.kind != "i" and X.dtype.kind != "u":
        X = X.astype(int)

    return X


def _warn_if_scanpy_input_looks_like_counts(adata, method: str) -> None:
    """Warn when Scanpy marker discovery seems to be using raw counts."""
    sample_vals = _preview_values(adata.X)
    if sample_vals.size == 0:
        return
    looks_integer = np.issubdtype(sample_vals.dtype, np.integer) or np.allclose(
        sample_vals, np.round(sample_vals)
    )
    try:
        max_val = float(np.nanmax(sample_vals))
    except Exception:
        max_val = 0.0
    if looks_integer and max_val > 50:
        logger.warning(
            "adata.X appears to contain raw count-like values (sample max=%.1f). "
            "Method '%s' expects log-normalized expression in adata.X.",
            max_val,
            method,
        )


def _validate_group_column(
    adata,
    *,
    groupby: str,
    group1: str | None = None,
    group2: str | None = None,
) -> tuple[list[str], bool]:
    """Validate group labels and return sorted group list plus two-group flag."""
    if groupby not in adata.obs.columns:
        raise ValueError(f"Groupby column '{groupby}' not found in adata.obs")

    groups_series = _ensure_obs_string(adata, groupby)
    groups_list = sorted(groups_series.dropna().unique().tolist(), key=str)
    if len(groups_list) < 2:
        raise ValueError(f"Need at least 2 groups for DE, found {len(groups_list)}")

    two_group = group1 is not None and group2 is not None
    if two_group:
        for label, value in [("group1", group1), ("group2", group2)]:
            if str(value) not in groups_list:
                raise ValueError(
                    f"--{label} '{value}' not found in '{groupby}'. Available: {groups_list}"
                )
    return groups_list, two_group


def _extract_rank_genes_groups_df(
    adata,
    *,
    groups: list[str],
    key: str,
    comparison_map: dict[str, str],
) -> pd.DataFrame:
    """Extract Scanpy DE results for all tested groups into a single dataframe."""
    frames: list[pd.DataFrame] = []
    for group in groups:
        df = sc.get.rank_genes_groups_df(adata, group=group, key=key)
        if df.empty:
            continue
        df.insert(0, "group", str(group))
        df["comparison"] = comparison_map[str(group)]
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    for col in ("scores", "logfoldchanges", "pvals", "pvals_adj", "pct_nz_group", "pct_nz_reference"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _annotate_scanpy_results(
    df: pd.DataFrame,
    *,
    fdr_threshold: float,
    log2fc_threshold: float,
) -> pd.DataFrame:
    """Add convenient significance / direction columns to Scanpy-style DE tables."""
    if df.empty:
        return df

    out = df.copy()
    if "names" in out.columns:
        out["names"] = out["names"].astype(str)
    if "logfoldchanges" not in out.columns:
        out["logfoldchanges"] = np.nan
    if "pvals_adj" not in out.columns:
        out["pvals_adj"] = np.nan

    out["direction"] = np.where(
        out["logfoldchanges"].fillna(0.0) >= 0,
        out["group"].astype(str),
        out["comparison"].astype(str).str.split(" vs ").str[-1],
    )
    out["is_significant"] = out["pvals_adj"].fillna(np.inf) <= float(fdr_threshold)
    out["passes_log2fc"] = out["logfoldchanges"].fillna(-np.inf) >= float(log2fc_threshold)
    out["passes_abs_log2fc"] = out["logfoldchanges"].abs().fillna(0.0) >= float(log2fc_threshold)
    out["passes_thresholds"] = out["is_significant"] & out["passes_log2fc"]
    return out


def _extract_gene_map(df: pd.DataFrame, *, n_top_genes: int) -> dict[str, list[str]]:
    """Build a Scanpy-compatible gene map for plotting grouped top hits."""
    if df.empty or "group" not in df.columns or "names" not in df.columns:
        return {}

    gene_map: dict[str, list[str]] = {}
    for group, group_df in df.groupby("group", sort=False):
        genes = [
            str(gene)
            for gene in group_df["names"].dropna().astype(str).tolist()
            if gene and gene.lower() != "nan"
        ]
        genes = genes[:n_top_genes]
        if genes:
            gene_map[str(group)] = genes
    return gene_map


def run_de(
    adata,
    *,
    groupby: str = METHOD_PARAM_DEFAULTS["common"]["groupby"],
    method: str = "wilcoxon",
    n_top_genes: int = METHOD_PARAM_DEFAULTS["common"]["n_top_genes"],
    group1: str | None = None,
    group2: str | None = None,
    fdr_threshold: float = METHOD_PARAM_DEFAULTS["common"]["fdr_threshold"],
    log2fc_threshold: float = METHOD_PARAM_DEFAULTS["common"]["log2fc_threshold"],
    scanpy_corr_method: str = METHOD_PARAM_DEFAULTS["scanpy"]["scanpy_corr_method"],
    scanpy_rankby_abs: bool = METHOD_PARAM_DEFAULTS["scanpy"]["scanpy_rankby_abs"],
    scanpy_pts: bool = METHOD_PARAM_DEFAULTS["scanpy"]["scanpy_pts"],
    scanpy_tie_correct: bool = METHOD_PARAM_DEFAULTS["wilcoxon"]["scanpy_tie_correct"],
    filter_markers: bool = METHOD_PARAM_DEFAULTS["scanpy"]["filter_markers"],
    min_in_group_fraction: float = METHOD_PARAM_DEFAULTS["scanpy"]["min_in_group_fraction"],
    min_fold_change: float = METHOD_PARAM_DEFAULTS["scanpy"]["min_fold_change"],
    max_out_group_fraction: float = METHOD_PARAM_DEFAULTS["scanpy"]["max_out_group_fraction"],
    filter_compare_abs: bool = METHOD_PARAM_DEFAULTS["scanpy"]["filter_compare_abs"],
) -> dict:
    """Run Scanpy marker discovery with optional post-filtering."""
    if method not in SCANPY_METHODS:
        raise ValueError(f"run_de only supports {SCANPY_METHODS}; got '{method}'")

    groups_list, two_group = _validate_group_column(
        adata, groupby=groupby, group1=group1, group2=group2
    )
    _warn_if_scanpy_input_looks_like_counts(adata, method)

    n_cells, n_genes = adata.n_obs, adata.n_vars
    comparison_map: dict[str, str]
    if two_group:
        tested_groups = [str(group1)]
        comparison_map = {str(group1): f"{group1} vs {group2}"}
    else:
        tested_groups = groups_list
        comparison_map = {str(group): f"{group} vs rest" for group in groups_list}

    key = f"rank_genes_groups__{method.replace('-', '_')}"
    key_filtered = f"{key}__filtered"

    rank_kwargs = {
        "groupby": groupby,
        "method": method,
        "n_genes": int(n_genes),
        "corr_method": scanpy_corr_method,
        "rankby_abs": scanpy_rankby_abs,
        "pts": scanpy_pts,
        "key_added": key,
    }
    if method == "wilcoxon":
        rank_kwargs["tie_correct"] = scanpy_tie_correct
    if two_group:
        rank_kwargs["groups"] = [str(group1)]
        rank_kwargs["reference"] = str(group2)

    sc.tl.rank_genes_groups(adata, **rank_kwargs)

    full_df = _extract_rank_genes_groups_df(
        adata, groups=tested_groups, key=key, comparison_map=comparison_map
    )
    full_df = _annotate_scanpy_results(
        full_df,
        fdr_threshold=fdr_threshold,
        log2fc_threshold=log2fc_threshold,
    )

    filtered_df = full_df.copy()
    if filter_markers:
        try:
            sc.tl.filter_rank_genes_groups(
                adata,
                key=key,
                groupby=groupby,
                key_added=key_filtered,
                min_in_group_fraction=min_in_group_fraction,
                min_fold_change=min_fold_change,
                max_out_group_fraction=max_out_group_fraction,
                compare_abs=filter_compare_abs,
            )
            filtered_df = _extract_rank_genes_groups_df(
                adata,
                groups=tested_groups,
                key=key_filtered,
                comparison_map=comparison_map,
            )
            filtered_df = filtered_df.dropna(subset=["names"])
            filtered_df = _annotate_scanpy_results(
                filtered_df,
                fdr_threshold=fdr_threshold,
                log2fc_threshold=log2fc_threshold,
            )
            logger.info(
                "Applied marker filtering: min_in_group_fraction=%.2f, min_fold_change=%.2f, "
                "max_out_group_fraction=%.2f, compare_abs=%s",
                min_in_group_fraction,
                min_fold_change,
                max_out_group_fraction,
                filter_compare_abs,
            )
        except Exception as exc:
            logger.warning("Marker filtering failed; using unfiltered Scanpy output: %s", exc)
        finally:
            if key_filtered in adata.uns:
                del adata.uns[key_filtered]

    if "passes_thresholds" in filtered_df.columns:
        top_source = filtered_df[filtered_df["passes_thresholds"]].copy()
    else:
        top_source = filtered_df.copy()
    if top_source.empty:
        top_source = filtered_df.copy()
    markers_df = (
        top_source.groupby("group", sort=False).head(int(n_top_genes)).reset_index(drop=True)
        if not top_source.empty
        else filtered_df.head(int(n_top_genes)).copy()
    )

    plot_gene_map = _extract_gene_map(markers_df, n_top_genes=int(n_top_genes))
    n_significant = int(full_df["is_significant"].sum()) if "is_significant" in full_df.columns else 0
    n_effect_size_hits = int(
        (full_df["is_significant"] & full_df["passes_abs_log2fc"]).sum()
    ) if {"is_significant", "passes_abs_log2fc"}.issubset(full_df.columns) else 0
    n_marker_hits = int(full_df["passes_thresholds"].sum()) if "passes_thresholds" in full_df.columns else 0

    return {
        "n_cells": n_cells,
        "n_genes": n_genes,
        "n_groups": len(groups_list),
        "groups": groups_list,
        "tested_groups": tested_groups,
        "groupby": groupby,
        "method": method,
        "n_top_genes": int(n_top_genes),
        "two_group": two_group,
        "group1": str(group1) if group1 is not None else None,
        "group2": str(group2) if group2 is not None else None,
        "comparison_mode": "pairwise" if two_group else "cluster_vs_rest",
        "n_de_genes": int(len(full_df)),
        "n_significant": n_significant,
        "n_effect_size_hits": n_effect_size_hits,
        "n_marker_hits": n_marker_hits,
        "markers_df": markers_df,
        "full_df": full_df,
        "plot_gene_map": plot_gene_map,
        "rank_genes_groups_key": key,
        "filter_markers": bool(filter_markers),
        "fdr_threshold": float(fdr_threshold),
        "log2fc_threshold": float(log2fc_threshold),
        "scanpy_corr_method": scanpy_corr_method,
        "scanpy_rankby_abs": bool(scanpy_rankby_abs),
        "scanpy_pts": bool(scanpy_pts),
        "scanpy_tie_correct": bool(scanpy_tie_correct) if method == "wilcoxon" else None,
        "min_in_group_fraction": float(min_in_group_fraction),
        "min_fold_change": float(min_fold_change),
        "max_out_group_fraction": float(max_out_group_fraction),
        "filter_compare_abs": bool(filter_compare_abs),
    }


def _build_pseudobulk_table(
    adata,
    raw_counts: np.ndarray,
    *,
    groupby: str,
    sample_key: str,
    group1: str,
    group2: str,
    min_cells_per_sample: int,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
    """Aggregate raw counts per sample x group for a two-group comparison."""
    groups_series = _ensure_obs_string(adata, groupby)
    sample_series = _ensure_obs_string(adata, sample_key)
    mask = groups_series.isin([str(group1), str(group2)])

    obs = adata.obs.loc[mask, [groupby, sample_key]].copy()
    obs[groupby] = obs[groupby].astype(str)
    obs[sample_key] = obs[sample_key].astype(str)
    counts = raw_counts[mask.to_numpy()]

    records: list[np.ndarray] = []
    meta_records: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    grouped = obs.groupby([sample_key, groupby], sort=True).indices
    for (sample_id, condition), idx in sorted(grouped.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        n_cells = int(len(idx))
        if n_cells < int(min_cells_per_sample):
            skipped.append(
                {
                    "sample_id": str(sample_id),
                    "condition": str(condition),
                    "n_cells": n_cells,
                    "reason": f"n_cells < min_cells_per_sample ({min_cells_per_sample})",
                }
            )
            continue

        row_id = f"{sample_id}__{condition}"
        records.append(np.asarray(counts[idx].sum(axis=0)).ravel())
        meta_records.append(
            {
                "row_id": row_id,
                "sample_id": str(sample_id),
                "condition": str(condition),
                "n_cells": n_cells,
            }
        )

    if not records:
        raise ValueError(
            "No pseudobulk profiles remained after applying min_cells_per_sample. "
            "Lower the threshold or inspect sample/group coverage."
        )

    metadata = pd.DataFrame(meta_records).set_index("row_id")
    counts_df = pd.DataFrame(
        np.vstack(records),
        index=metadata.index,
        columns=adata.var_names.astype(str),
    )
    return counts_df, metadata, skipped


def _choose_pydeseq2_design(
    counts_df: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    group1: str,
    group2: str,
) -> tuple[pd.DataFrame, pd.DataFrame, str, dict[str, int], bool]:
    """Choose unpaired vs paired design based on sample overlap."""
    sample_group_counts = metadata.groupby("sample_id")["condition"].nunique()
    paired_samples = sample_group_counts[sample_group_counts == 2].index.astype(str).tolist()

    if len(paired_samples) >= 2:
        keep_mask = metadata["sample_id"].astype(str).isin(paired_samples)
        paired_counts = counts_df.loc[keep_mask].copy()
        paired_meta = metadata.loc[keep_mask].copy()
        sample_counts = (
            paired_meta["condition"].astype(str).value_counts().reindex([str(group1), str(group2)], fill_value=0)
        )
        if int(sample_counts.min()) >= 2:
            logger.info(
                "PyDESeq2 will use a paired design (~ sample_id + condition) with %d paired samples.",
                len(paired_samples),
            )
            return (
                paired_counts,
                paired_meta,
                "~ sample_id + condition",
                sample_counts.astype(int).to_dict(),
                True,
            )

    sample_counts = metadata["condition"].astype(str).value_counts().reindex(
        [str(group1), str(group2)], fill_value=0
    )
    logger.info("PyDESeq2 will use an unpaired design (~ condition).")
    return counts_df.copy(), metadata.copy(), "~ condition", sample_counts.astype(int).to_dict(), False


def _annotate_pydeseq2_results(
    df: pd.DataFrame,
    *,
    group1: str,
    group2: str,
    fdr_threshold: float,
    log2fc_threshold: float,
) -> pd.DataFrame:
    """Normalize PyDESeq2 result columns to the OmicsClaw output contract."""
    out = df.copy()
    rename_map = {
        "log2FoldChange": "log2fc",
        "lfcSE": "lfc_se",
        "padj": "pvalue_adj",
        "baseMean": "base_mean",
    }
    out = out.rename(columns=rename_map)
    out["gene"] = out.index.astype(str)

    for col in ("base_mean", "log2fc", "lfc_se", "stat", "pvalue", "pvalue_adj"):
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["group"] = str(group1)
    out["comparison"] = f"{group1} vs {group2}"
    out["direction"] = np.where(out["log2fc"].fillna(0.0) >= 0, str(group1), str(group2))
    out["is_significant"] = out["pvalue_adj"].fillna(np.inf) <= float(fdr_threshold)
    out["passes_log2fc"] = out["log2fc"].fillna(-np.inf) >= float(log2fc_threshold)
    out["passes_abs_log2fc"] = out["log2fc"].abs().fillna(0.0) >= float(log2fc_threshold)
    out["passes_thresholds"] = out["is_significant"] & out["passes_log2fc"]
    cols = [
        "gene",
        "group",
        "comparison",
        "direction",
        "base_mean",
        "log2fc",
        "lfc_se",
        "stat",
        "pvalue",
        "pvalue_adj",
        "is_significant",
        "passes_log2fc",
        "passes_abs_log2fc",
        "passes_thresholds",
    ]
    return out[cols].sort_values(
        by=["pvalue_adj", "pvalue", "log2fc"],
        ascending=[True, True, False],
        na_position="last",
    ).reset_index(drop=True)


def run_pydeseq2(
    adata,
    *,
    groupby: str = METHOD_PARAM_DEFAULTS["common"]["groupby"],
    group1: str,
    group2: str,
    sample_key: str = METHOD_PARAM_DEFAULTS["pydeseq2"]["sample_key"],
    n_top_genes: int = METHOD_PARAM_DEFAULTS["common"]["n_top_genes"],
    min_cells_per_sample: int = METHOD_PARAM_DEFAULTS["pydeseq2"]["min_cells_per_sample"],
    min_counts_per_gene: int = METHOD_PARAM_DEFAULTS["pydeseq2"]["min_counts_per_gene"],
    fdr_threshold: float = METHOD_PARAM_DEFAULTS["common"]["fdr_threshold"],
    log2fc_threshold: float = METHOD_PARAM_DEFAULTS["common"]["log2fc_threshold"],
    pydeseq2_fit_type: str = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_fit_type"],
    pydeseq2_size_factors_fit_type: str = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_size_factors_fit_type"],
    pydeseq2_refit_cooks: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_refit_cooks"],
    pydeseq2_alpha: float = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_alpha"],
    pydeseq2_cooks_filter: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_cooks_filter"],
    pydeseq2_independent_filter: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_independent_filter"],
    pydeseq2_n_cpus: int | None = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_n_cpus"],
) -> dict:
    """Run sample-aware pseudobulk DE with PyDESeq2."""
    from .dependency_manager import require

    require("pydeseq2", feature="PyDESeq2 pseudobulk differential expression")
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    if sample_key not in adata.obs.columns:
        raise ValueError(
            f"Sample key '{sample_key}' not found in adata.obs. "
            "PyDESeq2 in spatial-de requires real biological sample labels."
        )

    groups_list, _ = _validate_group_column(
        adata, groupby=groupby, group1=group1, group2=group2
    )
    raw_counts = _get_raw_counts(adata)

    counts_df, metadata, skipped_sample_groups = _build_pseudobulk_table(
        adata,
        raw_counts,
        groupby=groupby,
        sample_key=sample_key,
        group1=str(group1),
        group2=str(group2),
        min_cells_per_sample=int(min_cells_per_sample),
    )

    counts_df = counts_df.loc[:, counts_df.sum(axis=0) >= int(min_counts_per_gene)].copy()
    if counts_df.empty or counts_df.shape[1] == 0:
        raise ValueError(
            "No genes remained after min_counts_per_gene filtering. "
            "Lower the threshold or inspect the counts layer."
        )

    deseq_counts, deseq_meta, design_formula, sample_counts, paired_design = _choose_pydeseq2_design(
        counts_df,
        metadata,
        group1=str(group1),
        group2=str(group2),
    )

    if min(sample_counts.values()) < 2:
        raise ValueError(
            "PyDESeq2 requires at least 2 pseudobulk samples per group after filtering. "
            f"Observed counts: {sample_counts}"
        )

    dds = DeseqDataSet(
        counts=deseq_counts.astype(int),
        metadata=deseq_meta[["sample_id", "condition"]].copy(),
        design=design_formula,
        fit_type=pydeseq2_fit_type,
        size_factors_fit_type=pydeseq2_size_factors_fit_type,
        refit_cooks=bool(pydeseq2_refit_cooks),
        n_cpus=pydeseq2_n_cpus,
        quiet=True,
    )
    dds.deseq2()

    stats = DeseqStats(
        dds,
        contrast=["condition", str(group1), str(group2)],
        alpha=float(pydeseq2_alpha),
        cooks_filter=bool(pydeseq2_cooks_filter),
        independent_filter=bool(pydeseq2_independent_filter),
        n_cpus=pydeseq2_n_cpus,
        quiet=True,
    )
    stats.summary()

    full_df = _annotate_pydeseq2_results(
        stats.results_df.copy(),
        group1=str(group1),
        group2=str(group2),
        fdr_threshold=fdr_threshold,
        log2fc_threshold=log2fc_threshold,
    )

    markers_df = full_df[full_df["passes_thresholds"]].copy()
    if markers_df.empty:
        markers_df = full_df[full_df["direction"] == str(group1)].copy()
    markers_df = markers_df.head(int(n_top_genes)).reset_index(drop=True)

    n_significant = int(full_df["is_significant"].sum())
    n_effect_size_hits = int((full_df["is_significant"] & full_df["passes_abs_log2fc"]).sum())
    n_marker_hits = int(full_df["passes_thresholds"].sum())

    return {
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_groups": len(groups_list),
        "groups": groups_list,
        "tested_groups": [str(group1)],
        "groupby": groupby,
        "method": "pydeseq2",
        "n_top_genes": int(n_top_genes),
        "two_group": True,
        "group1": str(group1),
        "group2": str(group2),
        "comparison_mode": "pairwise",
        "n_de_genes": int(len(full_df)),
        "n_significant": n_significant,
        "n_effect_size_hits": n_effect_size_hits,
        "n_marker_hits": n_marker_hits,
        "n_pseudobulk_rows": int(deseq_counts.shape[0]),
        "n_pseudobulk_genes": int(deseq_counts.shape[1]),
        "n_samples": int(deseq_meta["sample_id"].nunique()),
        "sample_counts_by_group": {str(k): int(v) for k, v in sample_counts.items()},
        "paired_design": bool(paired_design),
        "design_formula": design_formula,
        "sample_key": sample_key,
        "min_cells_per_sample": int(min_cells_per_sample),
        "min_counts_per_gene": int(min_counts_per_gene),
        "skipped_sample_groups": skipped_sample_groups,
        "markers_df": markers_df,
        "full_df": full_df,
        "plot_gene_map": {
            str(group1): markers_df["gene"].dropna().astype(str).head(int(n_top_genes)).tolist()
        },
        "fdr_threshold": float(fdr_threshold),
        "log2fc_threshold": float(log2fc_threshold),
        "pydeseq2_fit_type": pydeseq2_fit_type,
        "pydeseq2_size_factors_fit_type": pydeseq2_size_factors_fit_type,
        "pydeseq2_refit_cooks": bool(pydeseq2_refit_cooks),
        "pydeseq2_alpha": float(pydeseq2_alpha),
        "pydeseq2_cooks_filter": bool(pydeseq2_cooks_filter),
        "pydeseq2_independent_filter": bool(pydeseq2_independent_filter),
        "pydeseq2_n_cpus": pydeseq2_n_cpus,
    }
