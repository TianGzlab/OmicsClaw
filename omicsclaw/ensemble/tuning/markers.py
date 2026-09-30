"""Marker genes of candidate partitions: ``python -m omicsclaw.ensemble.tuning.markers``.

For each K one representative partition is described:

- compact: every domain's share of observations and its top three marker genes;
- full (for the K asked for in full): every domain's share, the share of its
  observations whose 10 nearest spatial neighbours mostly carry the same
  label, its centroid on coordinates scaled to ``[0, 1]``, and its top five
  markers with log2 fold change and the share of expressing observations in
  and out of the domain;
- nesting, between consecutive K of the full set: for each domain of the
  finer partition, the coarser domain holding most of it and that share.

The document also describes the data (:func:`describe_data`): sizes, median
counts and genes per observation, the coordinate span, preprocessing settings,
``obsm`` keys and the number of batches; the only ``obs`` column read is
``batch``.

Markers are ``scanpy.tl.rank_genes_groups(method="wilcoxon")`` on ``X`` (the
log-normalised matrix), once per K; above 20000 observations on a sample of
20000 stratified by label. Domains are named by their labels.

Input: ``--spec`` JSON (see :func:`compute`). Output: ``--output`` JSON.
Runs under the skill interpreter.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

__all__ = ["compute", "describe_data", "main", "nesting", "rank_markers", "stratified_sample"]

PREPROCESS_UNS = "spatialclaw_spatial-preprocess"
PREPROCESS_KEYS = (
    "max_mt_pct", "min_genes", "min_cells", "max_genes", "n_top_hvg", "n_pcs_used",
    "n_neighbors", "normalize_target_sum",
)

COMPACT_TOP = 3
FULL_TOP = 5
NEIGHBOURS = 10
MAX_OBS = 20_000
SAMPLE_SEED = 0


def _read_labels(path: str) -> dict[str, str]:
    import pandas as pd

    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    return dict(zip(table["obs_id"], table["label"]))


def stratified_sample(labels: np.ndarray, limit: int) -> np.ndarray:
    """Sorted indices of at most *limit* observations, stratified by label."""
    n = labels.shape[0]
    if n <= limit:
        return np.arange(n)
    rng = np.random.default_rng(SAMPLE_SEED)
    chosen = []
    for value in np.unique(labels):
        members = np.flatnonzero(labels == value)
        take = max(1, int(round(limit * members.size / n)))
        chosen.append(rng.choice(members, size=min(take, members.size), replace=False))
    return np.sort(np.concatenate(chosen))


def rank_markers(adata, labels: np.ndarray, top: int) -> dict[str, list[dict[str, Any]]]:
    """Top *top* Wilcoxon markers of each label with at least two observations.

    :returns: ``{label: [{gene, log2fc, pct_in, pct_out}]}``; empty when fewer
        than two labels qualify.
    """
    import scanpy as sc

    work = adata.copy()
    work.obs["_domain"] = labels.astype(str)
    work.obs["_domain"] = work.obs["_domain"].astype("category")
    counts = work.obs["_domain"].value_counts()
    keep = counts[counts >= 2].index
    work = work[work.obs["_domain"].isin(keep)].copy()
    work.obs["_domain"] = work.obs["_domain"].cat.remove_unused_categories()
    if work.obs["_domain"].nunique() < 2:
        return {}
    sc.tl.rank_genes_groups(work, "_domain", method="wilcoxon", pts=True, n_genes=top, use_raw=False)
    result = work.uns["rank_genes_groups"]
    groups = result["names"].dtype.names
    pts = result.get("pts")
    pts_rest = result.get("pts_rest")
    out: dict[str, list[dict[str, Any]]] = {}
    for group in groups:
        genes = []
        for row in range(min(top, len(result["names"][group]))):
            gene = str(result["names"][group][row])
            entry: dict[str, Any] = {"gene": gene}
            if "logfoldchanges" in result:
                value = float(result["logfoldchanges"][group][row])
                entry["log2fc"] = round(value, 3) if np.isfinite(value) else None
            if pts is not None and gene in pts.index:
                entry["pct_in"] = round(float(pts.loc[gene, group]), 3)
            if pts_rest is not None and gene in pts_rest.index:
                entry["pct_out"] = round(float(pts_rest.loc[gene, group]), 3)
            genes.append(entry)
        out[str(group)] = genes
    return out


def _same_label_share(coords: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    from scipy.spatial import cKDTree

    k = min(NEIGHBOURS, coords.shape[0] - 1)
    _, idx = cKDTree(coords).query(coords, k=k + 1)
    neighbours = np.asarray(idx)[:, 1:]
    same = (labels[neighbours] == labels[:, None]).mean(axis=1)
    return {str(v): round(float(same[labels == v].mean()), 4) for v in np.unique(labels)}


def nesting(fine: np.ndarray, coarse: np.ndarray) -> list[dict[str, Any]]:
    """For each domain of *fine*, the domain of *coarse* holding most of it, and that share."""
    rows = []
    for value in sorted(np.unique(fine), key=_natural):
        members = coarse[fine == value]
        names, counts = np.unique(members, return_counts=True)
        top = int(np.argmax(counts))
        rows.append({"domain": str(value), "into": str(names[top]),
                     "share": round(float(counts[top] / members.size), 4)})
    return rows


def _natural(value: Any) -> tuple:
    text = str(value)
    return (0, int(text)) if text.lstrip("-").isdigit() else (1, text)


def describe_data(adata, coords: np.ndarray) -> dict[str, Any]:
    """Sizes, per-observation medians, coordinate span, preprocessing and batches of *adata*."""
    import scipy.sparse as sp

    matrix = adata.layers["counts"] if "counts" in adata.layers else adata.X
    if sp.issparse(matrix):
        totals = np.asarray(matrix.sum(axis=1)).ravel()
        detected = np.diff(matrix.tocsr().indptr)
    else:
        dense = np.asarray(matrix)
        totals = dense.sum(axis=1)
        detected = (dense > 0).sum(axis=1)
    span = coords.max(axis=0) - coords.min(axis=0)
    record = adata.uns.get(PREPROCESS_UNS) or {}
    params = dict(record.get("params") or {}) if isinstance(record, Mapping) else {}
    preprocessing = {key: _plain(params[key]) for key in PREPROCESS_KEYS if key in params}
    batches = None
    if "batch" in adata.obs.columns:
        batches = int(adata.obs["batch"].nunique())
    return {
        "n_obs": int(adata.n_obs),
        "n_vars": int(adata.n_vars),
        "median_counts": float(np.median(totals)) if totals.size else None,
        "median_genes": float(np.median(detected)) if detected.size else None,
        "x_span": round(float(span[0]), 3),
        "y_span": round(float(span[1]), 3),
        "species": _plain(params.get("species")) if params.get("species") else None,
        "preprocessing": preprocessing,
        "obsm_keys": sorted(str(key) for key in adata.obsm.keys()),
        "n_batches": batches,
    }


def _plain(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def compute(spec: Mapping[str, Any]) -> dict[str, Any]:
    """The markers document for *spec*.

    :param spec: ``input`` (the ``.h5ad``), ``partitions`` (``[{k, labels,
        method, trial}]``, one per K), ``full`` (the K described in full),
        and optionally ``coords_obsm`` (default ``spatial``).
    """
    import anndata

    adata = anndata.read_h5ad(spec["input"])
    obs_ids = [str(x) for x in adata.obs_names]
    coords_key = spec.get("coords_obsm", "spatial")
    coords = np.asarray(adata.obsm[coords_key], dtype=np.float64)[:, :2]
    span = coords.max(axis=0) - coords.min(axis=0)
    span[span == 0] = 1.0
    scaled = (coords - coords.min(axis=0)) / span
    full_ks = {int(k) for k in spec.get("full", [])}
    compact: dict[str, Any] = {}
    detailed: dict[str, Any] = {}
    label_arrays: dict[int, np.ndarray] = {}
    for item in spec["partitions"]:
        k = int(item["k"])
        mapping = _read_labels(item["labels"])
        labels = np.asarray([mapping.get(name, "") for name in obs_ids], dtype=object).astype(str)
        label_arrays[k] = labels
        chosen = stratified_sample(labels, MAX_OBS)
        view = adata[chosen]
        top = FULL_TOP if k in full_ks else COMPACT_TOP
        ranked = rank_markers(view, labels[chosen], top)
        values, counts = np.unique(labels, return_counts=True)
        share = {str(v): round(float(c / labels.size), 4) for v, c in zip(values, counts)}
        order = sorted(share, key=_natural)
        compact[str(k)] = {
            "k": k,
            "method": item.get("method"),
            "trial": item.get("trial"),
            "params": item.get("params"),
            "domains": [
                {"domain": d, "share": share[d], "genes": [g["gene"] for g in ranked.get(d, [])[:COMPACT_TOP]]}
                for d in order
            ],
        }
        if k in full_ks:
            same = _same_label_share(coords, labels)
            domains = []
            for d in order:
                members = labels == d
                centroid = scaled[members].mean(axis=0)
                domains.append({
                    "domain": d,
                    "share": share[d],
                    "same_label_neighbours": same.get(d),
                    "centroid": [round(float(centroid[0]), 3), round(float(centroid[1]), 3)],
                    "markers": ranked.get(d, [])[:FULL_TOP],
                })
            detailed[str(k)] = {"k": k, "method": item.get("method"), "trial": item.get("trial"),
                                "params": item.get("params"), "domains": domains}
    nested = []
    ordered = sorted(k for k in full_ks if k in label_arrays)
    for coarse_k, fine_k in zip(ordered, ordered[1:]):
        nested.append({"coarse": coarse_k, "fine": fine_k,
                       "rows": nesting(label_arrays[fine_k], label_arrays[coarse_k])})
    return {
        "schema": "omicsclaw.ensemble.markers/1",
        "data": describe_data(adata, coords),
        "method": "wilcoxon",
        "max_obs": MAX_OBS,
        "compact": compact,
        "full": detailed,
        "nesting": nested,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Marker genes of candidate partitions.")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    document = compute(spec)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, args.output)
    print("MARKERS=" + json.dumps({"path": str(args.output)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
