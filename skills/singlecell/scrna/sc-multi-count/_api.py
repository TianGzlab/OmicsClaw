"""Merge count matrices without writing files."""

from __future__ import annotations

import json

import anndata
import numpy as np
import pandas as pd
from scipy import sparse

from skills.singlecell._lib.upstream import standardize_count_adata

__all__ = ["merge_samples", "barcode_metrics", "per_sample_summary", "sample_composition_figure", "run_info"]


def merge_samples(adatas, *, sample_ids=None, sample_key="sample_id", join="outer"):
    """Merge .X counts, align features and return a standardized copy.

    Inputs are not modified. Missing features in an outer join become zeros.
    Existing sample labels are kept; sample_ids supplies missing labels and,
    when given, prefixes each input's barcodes. With no IDs, existing barcodes
    are kept and duplicate names get numeric suffixes; missing sample labels
    become sample_1, sample_2, etc. Like the CLI, this does not test whether .X
    holds integer counts. Standardize external inputs before merging them.
    """
    adatas = list(adatas)
    if len(adatas) < 2:
        raise ValueError("at least two sample matrices are required")
    if join not in {"inner", "outer"}:
        raise ValueError("join must be inner or outer")
    if sample_ids is not None and len(sample_ids) != len(adatas):
        raise ValueError("sample_ids must have one value per input")
    parts = []
    for index, adata in enumerate(adatas):
        part = adata.copy()
        label = str(sample_ids[index]) if sample_ids is not None else f"sample_{index + 1}"
        if sample_key not in part.obs:
            part.obs[sample_key] = label
        if sample_ids is not None:
            part.obs_names = [f"{label}_{name}" for name in part.obs_names]
            part.obs_names_make_unique()
        parts.append(part)
    merged = anndata.concat(parts, join=join)
    merged.obs_names_make_unique()
    if not sparse.issparse(merged.X):
        merged.X = np.nan_to_num(merged.X, nan=0.0)
    merged.obs[sample_key] = merged.obs[sample_key].astype(str)
    result, _ = standardize_count_adata(
        merged, skill_name="sc-multi-count", method="merge", source_label="multi_sample_merge", warnings=[],
    )
    result.uns["sc_multi_count_run"] = json.dumps({
        "requested_method": "merge", "executed_method": "merge", "fallback_reason": None,
        "input_samples": len(parts), "sample_key": sample_key, "join": join,
    })
    return result


def barcode_metrics(adata, *, sample_key="sample_id"):
    """Return per-barcode .X counts and detected features, sorted by total counts."""
    return pd.DataFrame({
        "barcode": adata.obs_names.astype(str),
        "sample_id": adata.obs[sample_key].to_numpy(),
        "total_counts": np.asarray(adata.X.sum(axis=1)).ravel(),
        "detected_genes": np.asarray((adata.X > 0).sum(axis=1)).ravel(),
    }).sort_values("total_counts", ascending=False).reset_index(drop=True)


def per_sample_summary(adata, *, sample_key="sample_id"):
    """Return cell counts, median counts/features and summed UMIs for each sample."""
    return barcode_metrics(adata, sample_key=sample_key).groupby("sample_id", dropna=False).agg(
        n_cells=("barcode", "count"), median_counts=("total_counts", "median"),
        median_genes=("detected_genes", "median"), total_umis=("total_counts", "sum"),
    ).reset_index()


def sample_composition_figure(adata, *, sample_key="sample_id"):
    """Return a Figure showing each sample's cell count; do not write it."""
    import matplotlib.pyplot as plt

    table = per_sample_summary(adata, sample_key=sample_key)
    figure, axis = plt.subplots(figsize=(max(6, len(table) * 0.8), 4))
    axis.bar(table["sample_id"], table["n_cells"], color="#4C72B0", edgecolor="white")
    axis.set(xlabel="Sample", ylabel="Number of cells", title="Cell count per sample")
    if len(table) > 6:
        axis.tick_params(axis="x", labelrotation=45)
    figure.tight_layout()
    return figure


def run_info(adata, *, keep: bool = True):
    """Return merge diagnostics; keep=False removes the run record."""
    key = "sc_multi_count_run"
    raw = adata.uns.get(key, "{}") if keep else adata.uns.pop(key, "{}")
    return json.loads(raw)
