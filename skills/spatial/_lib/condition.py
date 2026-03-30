"""Spatial condition comparison functions.

Provides pseudobulk aggregation and PyDESeq2/Wilcoxon condition comparison.

Input matrix convention (per-component):
  - pseudobulk aggregation: adata.layers["counts"] (raw) — sum aggregation
                            requires integer-like counts, not log-normalized
  - PyDESeq2:              pseudobulk raw integer counts — NB/GLM model
  - Wilcoxon:              pseudobulk counts internally converted to CPM/log2FC

Usage::

    from skills.spatial._lib.condition import run_condition_comparison, pseudobulk_aggregate
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import sparse, stats

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("pydeseq2", "wilcoxon")

# Pseudobulk + PyDESeq2 require raw counts; Wilcoxon internally normalizes.
COUNT_BASED_METHODS = ("pydeseq2",)

VALID_PYDESEQ2_FIT_TYPES = ("parametric", "mean")
VALID_PYDESEQ2_SIZE_FACTORS_FIT_TYPES = ("ratio", "poscounts", "iterative")
VALID_WILCOXON_ALTERNATIVES = ("two-sided", "less", "greater")

METHOD_PARAM_DEFAULTS = {
    "common": {
        "cluster_key": "leiden",
        "condition_key": "condition",
        "sample_key": "sample_id",
        "min_counts_per_gene": 10,
        "min_samples_per_condition": 2,
        "fdr_threshold": 0.05,
        "log2fc_threshold": 1.0,
    },
    "pydeseq2": {
        "pydeseq2_fit_type": "parametric",
        "pydeseq2_size_factors_fit_type": "ratio",
        "pydeseq2_refit_cooks": True,
        "pydeseq2_alpha": 0.05,
        "pydeseq2_cooks_filter": True,
        "pydeseq2_independent_filter": True,
        "pydeseq2_n_cpus": 1,
    },
    "wilcoxon": {
        "wilcoxon_alternative": "two-sided",
    },
}


def _get_counts_matrix(adata) -> np.ndarray:
    """Return raw counts with fallback/warnings."""
    if "counts" in adata.layers:
        X = adata.layers["counts"]
        logger.info("Pseudobulk: using adata.layers['counts'] (raw counts)")
    elif adata.raw is not None:
        X = adata.raw.X
        logger.warning(
            "Pseudobulk: no 'counts' layer found; using adata.raw. "
            "Ensure adata.raw contains raw counts, not log-normalized values."
        )
    else:
        X = adata.X
        logger.warning(
            "Pseudobulk: no 'counts' layer or adata.raw found; using adata.X. "
            "If adata.X is log-normalized, pseudobulk sums will be statistically invalid. "
            "Ensure preprocessing saves raw counts: adata.layers['counts'] = adata.X.copy()"
        )

    if sparse.issparse(X):
        X = X.toarray()
    X = np.asarray(X)
    if np.any(X < 0):
        X = np.clip(X, 0, None)
    if X.dtype.kind == "f":
        X = np.round(X).astype(int)
    return X


def _validate_condition_design(adata, *, condition_key: str, sample_key: str) -> pd.Series:
    """Validate sample/condition design and return sample -> condition map."""
    if condition_key not in adata.obs.columns:
        raise ValueError(f"Condition key '{condition_key}' not in adata.obs")
    if sample_key not in adata.obs.columns:
        raise ValueError(f"Sample key '{sample_key}' not in adata.obs")

    design = adata.obs[[sample_key, condition_key]].dropna().copy()
    if design.empty:
        raise ValueError("Condition/sample design is empty after dropping missing values.")

    condition_counts = design.groupby(sample_key)[condition_key].nunique()
    bad_samples = condition_counts[condition_counts > 1].index.tolist()
    if bad_samples:
        raise ValueError(
            "Each biological sample must map to exactly one condition. "
            f"Ambiguous samples: {bad_samples[:10]}"
        )

    sample_condition = (
        design.drop_duplicates(subset=[sample_key])
        .set_index(sample_key)[condition_key]
        .astype(str)
    )
    return sample_condition


def pseudobulk_aggregate(adata, *, sample_key: str, cluster_key: str = "leiden") -> dict[str, pd.DataFrame]:
    """Aggregate raw counts to pseudobulk per (sample, cluster)."""
    if sample_key not in adata.obs.columns:
        raise ValueError(f"Sample key '{sample_key}' not in adata.obs")
    if cluster_key not in adata.obs.columns:
        raise ValueError(f"Cluster key '{cluster_key}' not in adata.obs")

    X = _get_counts_matrix(adata)

    clusters = sorted(adata.obs[cluster_key].dropna().astype(str).unique().tolist(), key=str)
    samples = sorted(adata.obs[sample_key].dropna().astype(str).unique().tolist(), key=str)

    cluster_values = adata.obs[cluster_key].astype(str).values
    sample_values = adata.obs[sample_key].astype(str).values

    result: dict[str, pd.DataFrame] = {}
    for cl in clusters:
        rows, row_labels = [], []
        for samp in samples:
            mask = (cluster_values == cl) & (sample_values == samp)
            if np.sum(mask) == 0:
                continue
            row_labels.append(samp)
            rows.append(X[mask].sum(axis=0))
        if len(rows) >= 2:
            result[str(cl)] = pd.DataFrame(rows, index=row_labels, columns=adata.var_names)
    return result


def run_pydeseq2(
    count_df: pd.DataFrame,
    condition_labels: pd.Series,
    reference: str,
    other: str,
    *,
    fit_type: str = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_fit_type"],
    size_factors_fit_type: str = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_size_factors_fit_type"],
    refit_cooks: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_refit_cooks"],
    alpha: float = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_alpha"],
    cooks_filter: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_cooks_filter"],
    independent_filter: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_independent_filter"],
    n_cpus: int | None = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_n_cpus"],
) -> pd.DataFrame:
    """Run PyDESeq2 on pseudobulk counts."""
    from .dependency_manager import require

    require("pydeseq2", feature="DESeq2-style pseudobulk analysis")
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    metadata = pd.DataFrame({"condition": condition_labels.astype(str)}, index=count_df.index)
    dds = DeseqDataSet(
        counts=count_df.astype(int),
        metadata=metadata,
        design="~condition",
        fit_type=fit_type,
        size_factors_fit_type=size_factors_fit_type,
        refit_cooks=refit_cooks,
        n_cpus=n_cpus,
        quiet=True,
    )
    dds.deseq2()

    stat = DeseqStats(
        dds,
        contrast=["condition", other, reference],
        alpha=alpha,
        cooks_filter=cooks_filter,
        independent_filter=independent_filter,
        n_cpus=n_cpus,
        quiet=True,
    )
    stat.summary()

    res = stat.results_df.copy()
    rename_map = {
        "log2FoldChange": "log2fc",
        "lfcSE": "lfc_se",
        "padj": "pvalue_adj",
        "baseMean": "base_mean",
    }
    res = res.rename(columns=rename_map)
    res["gene"] = res.index.astype(str)

    for col in ("base_mean", "log2fc", "lfc_se", "stat", "pvalue", "pvalue_adj"):
        if col not in res.columns:
            res[col] = np.nan

    cols = ["gene", "base_mean", "log2fc", "lfc_se", "stat", "pvalue", "pvalue_adj"]
    return res[cols].reset_index(drop=True)


def run_wilcoxon_pseudobulk(
    count_df: pd.DataFrame,
    condition_labels: pd.Series,
    reference: str,
    *,
    alternative: str = METHOD_PARAM_DEFAULTS["wilcoxon"]["wilcoxon_alternative"],
) -> pd.DataFrame:
    """Wilcoxon rank-sum on pseudobulk log-CPM values."""
    lib_size = count_df.sum(axis=1).replace(0, 1)
    cpm = count_df.div(lib_size, axis=0) * 1e6
    log_cpm = np.log1p(cpm)

    ref_mask = condition_labels == reference
    other_mask = condition_labels != reference
    if np.sum(ref_mask) < 1 or np.sum(other_mask) < 1:
        return pd.DataFrame(columns=["gene", "base_mean", "log2fc", "stat", "pvalue", "pvalue_adj"])

    records = []
    for gene in count_df.columns:
        a = log_cpm.loc[other_mask, gene].values
        b = log_cpm.loc[ref_mask, gene].values
        if np.std(a) < 1e-10 and np.std(b) < 1e-10:
            continue
        try:
            stat, pval = stats.ranksums(a, b, alternative=alternative)
        except Exception:
            continue

        mean_other_cpm = float(cpm.loc[other_mask, gene].mean())
        mean_ref_cpm = float(cpm.loc[ref_mask, gene].mean())
        log2fc = float(np.log2((mean_other_cpm + 1.0) / (mean_ref_cpm + 1.0)))
        base_mean = float(count_df[gene].mean())
        records.append(
            {
                "gene": gene,
                "base_mean": base_mean,
                "log2fc": log2fc,
                "stat": float(stat),
                "pvalue": float(pval),
            }
        )

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["gene", "base_mean", "log2fc", "stat", "pvalue", "pvalue_adj"])

    from statsmodels.stats.multitest import multipletests

    try:
        _, adj, _, _ = multipletests(df["pvalue"], method="fdr_bh")
        df["pvalue_adj"] = adj
    except Exception:
        df["pvalue_adj"] = df["pvalue"]

    return df.sort_values("pvalue_adj").reset_index(drop=True)


def run_condition_comparison(
    adata,
    *,
    condition_key: str,
    sample_key: str,
    reference_condition: str | None = None,
    cluster_key: str = METHOD_PARAM_DEFAULTS["common"]["cluster_key"],
    method: str = "pydeseq2",
    min_counts_per_gene: int = METHOD_PARAM_DEFAULTS["common"]["min_counts_per_gene"],
    min_samples_per_condition: int = METHOD_PARAM_DEFAULTS["common"]["min_samples_per_condition"],
    fdr_threshold: float = METHOD_PARAM_DEFAULTS["common"]["fdr_threshold"],
    log2fc_threshold: float = METHOD_PARAM_DEFAULTS["common"]["log2fc_threshold"],
    pydeseq2_fit_type: str = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_fit_type"],
    pydeseq2_size_factors_fit_type: str = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_size_factors_fit_type"],
    pydeseq2_refit_cooks: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_refit_cooks"],
    pydeseq2_alpha: float = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_alpha"],
    pydeseq2_cooks_filter: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_cooks_filter"],
    pydeseq2_independent_filter: bool = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_independent_filter"],
    pydeseq2_n_cpus: int | None = METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_n_cpus"],
    wilcoxon_alternative: str = METHOD_PARAM_DEFAULTS["wilcoxon"]["wilcoxon_alternative"],
) -> dict:
    """Run pseudobulk condition comparison."""
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")
    if min_counts_per_gene < 1:
        raise ValueError("min_counts_per_gene must be >= 1")
    if min_samples_per_condition < 1:
        raise ValueError("min_samples_per_condition must be >= 1")
    if fdr_threshold <= 0 or fdr_threshold > 1:
        raise ValueError("fdr_threshold must be in (0, 1]")
    if pydeseq2_fit_type not in VALID_PYDESEQ2_FIT_TYPES:
        raise ValueError(f"Invalid pydeseq2_fit_type: {pydeseq2_fit_type}")
    if pydeseq2_size_factors_fit_type not in VALID_PYDESEQ2_SIZE_FACTORS_FIT_TYPES:
        raise ValueError(f"Invalid pydeseq2_size_factors_fit_type: {pydeseq2_size_factors_fit_type}")
    if wilcoxon_alternative not in VALID_WILCOXON_ALTERNATIVES:
        raise ValueError(f"Invalid wilcoxon_alternative: {wilcoxon_alternative}")

    sample_condition = _validate_condition_design(adata, condition_key=condition_key, sample_key=sample_key)
    conditions = sorted(sample_condition.astype(str).unique().tolist(), key=str)
    if len(conditions) < 2:
        raise ValueError(f"Need >= 2 conditions in '{condition_key}', found {conditions}")

    ref = str(reference_condition or conditions[0])
    if ref not in conditions:
        raise ValueError(f"Reference '{ref}' not in conditions: {conditions}")

    sample_counts_by_condition = {
        str(k): int(v)
        for k, v in sample_condition.value_counts().sort_index().items()
    }

    pb_dict = pseudobulk_aggregate(adata, sample_key=sample_key, cluster_key=cluster_key)
    all_de: dict[str, pd.DataFrame] = {}
    comparison_rows: list[dict] = []
    skipped_contrasts: list[dict] = []
    method_used = method

    for cl, count_df in pb_dict.items():
        cond_strs = sample_condition.reindex(count_df.index).astype(str)
        unique_conds = sorted(cond_strs.dropna().unique().tolist(), key=str)
        if len(unique_conds) < 2 or ref not in unique_conds:
            continue

        filtered = count_df.loc[:, count_df.sum(axis=0) >= min_counts_per_gene]
        if filtered.shape[1] < 5:
            skipped_contrasts.append(
                {
                    "cluster": cl,
                    "contrast": f"*_{ref}",
                    "reason": f"fewer than 5 genes remained after min_counts_per_gene={min_counts_per_gene}",
                }
            )
            continue

        for other_c in unique_conds:
            if other_c == ref:
                continue

            mask = cond_strs.isin([ref, other_c])
            filtered_sub = filtered.loc[mask]
            cond_sub = cond_strs.loc[mask]
            sample_counts = cond_sub.value_counts()
            n_ref = int(sample_counts.get(ref, 0))
            n_other = int(sample_counts.get(other_c, 0))

            if n_ref < min_samples_per_condition or n_other < min_samples_per_condition:
                skipped_contrasts.append(
                    {
                        "cluster": cl,
                        "contrast": f"{other_c}_vs_{ref}",
                        "reason": (
                            f"insufficient samples per condition "
                            f"(ref={n_ref}, other={n_other}, required={min_samples_per_condition})"
                        ),
                    }
                )
                continue

            de_df = None
            if method == "pydeseq2":
                try:
                    de_df = run_pydeseq2(
                        filtered_sub,
                        cond_sub,
                        ref,
                        other_c,
                        fit_type=pydeseq2_fit_type,
                        size_factors_fit_type=pydeseq2_size_factors_fit_type,
                        refit_cooks=pydeseq2_refit_cooks,
                        alpha=pydeseq2_alpha,
                        cooks_filter=pydeseq2_cooks_filter,
                        independent_filter=pydeseq2_independent_filter,
                        n_cpus=pydeseq2_n_cpus,
                    )
                    de_df["method"] = "pydeseq2"
                except Exception as exc:
                    logger.warning(
                        "PyDESeq2 failed for cluster %s (%s), falling back to Wilcoxon: %s",
                        cl,
                        other_c,
                        exc,
                    )
                    try:
                        de_df = run_wilcoxon_pseudobulk(
                            filtered_sub,
                            cond_sub,
                            ref,
                            alternative=wilcoxon_alternative,
                        )
                        de_df["method"] = "wilcoxon"
                        method_used = "pydeseq2+wilcoxon_fallback"
                    except Exception as exc2:
                        logger.error("Wilcoxon also failed for cluster %s: %s", cl, exc2)
            else:
                try:
                    de_df = run_wilcoxon_pseudobulk(
                        filtered_sub,
                        cond_sub,
                        ref,
                        alternative=wilcoxon_alternative,
                    )
                    de_df["method"] = "wilcoxon"
                except Exception as exc:
                    logger.error("Wilcoxon failed for cluster %s: %s", cl, exc)

            if de_df is None or de_df.empty:
                skipped_contrasts.append(
                    {
                        "cluster": cl,
                        "contrast": f"{other_c}_vs_{ref}",
                        "reason": "method returned no DE results",
                    }
                )
                continue

            de_df["cluster"] = str(cl)
            de_df["contrast"] = f"{other_c}_vs_{ref}"
            de_df["n_samples_reference"] = n_ref
            de_df["n_samples_other"] = n_other
            all_de[f"{cl}_{other_c}"] = de_df

            sig_mask = de_df["pvalue_adj"].fillna(1.0) < fdr_threshold
            effect_mask = np.abs(de_df["log2fc"].fillna(0.0)) >= log2fc_threshold
            comparison_rows.append(
                {
                    "cluster": str(cl),
                    "contrast": f"{other_c}_vs_{ref}",
                    "method": str(de_df["method"].iloc[0]),
                    "n_samples_reference": n_ref,
                    "n_samples_other": n_other,
                    "n_genes_tested": int(len(de_df)),
                    "n_significant": int(sig_mask.sum()),
                    "n_effect_size_hits": int((sig_mask & effect_mask).sum()),
                }
            )

    global_de = pd.concat(all_de.values(), ignore_index=True) if all_de else pd.DataFrame()
    if not global_de.empty:
        global_de = global_de.sort_values(
            by=["pvalue_adj", "pvalue", "contrast", "cluster"],
            na_position="last",
        ).reset_index(drop=True)

    sig_count = int((global_de["pvalue_adj"] < fdr_threshold).sum()) if not global_de.empty else 0
    effect_hits = (
        int(((global_de["pvalue_adj"] < fdr_threshold) & (np.abs(global_de["log2fc"]) >= log2fc_threshold)).sum())
        if not global_de.empty else 0
    )

    return {
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "conditions": conditions,
        "reference": ref,
        "sample_counts_by_condition": sample_counts_by_condition,
        "n_samples": len(sample_condition),
        "n_clusters_with_pseudobulk": len(pb_dict),
        "n_clusters_tested": len({row["cluster"] for row in comparison_rows}),
        "n_contrasts_tested": len(comparison_rows),
        "n_de_genes_total": len(global_de),
        "n_significant": sig_count,
        "n_effect_size_hits": effect_hits,
        "method": method_used,
        "global_de": global_de,
        "per_cluster_de": all_de,
        "comparison_summary": comparison_rows,
        "skipped_contrasts": skipped_contrasts,
        "cluster_key": cluster_key,
        "condition_key": condition_key,
        "sample_key": sample_key,
        "min_counts_per_gene": min_counts_per_gene,
        "min_samples_per_condition": min_samples_per_condition,
        "fdr_threshold": fdr_threshold,
        "log2fc_threshold": log2fc_threshold,
    }
