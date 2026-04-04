"""Helpers for metacell construction."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scanpy as sc
from anndata import AnnData
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)


def make_demo_metacell_adata(seed: int = 0) -> AnnData:
    rng = np.random.default_rng(seed)
    n_cells, n_genes = 160, 100
    genes = [f"Gene{i}" for i in range(n_genes)]
    groups = rng.choice(["state_a", "state_b", "state_c"], size=n_cells, p=[0.4, 0.35, 0.25])
    bases = {
        "state_a": rng.gamma(2.0, 1.2, size=n_genes),
        "state_b": rng.gamma(2.3, 1.1, size=n_genes),
        "state_c": rng.gamma(2.7, 1.0, size=n_genes),
    }
    bases["state_a"][:8] += 4
    bases["state_b"][8:16] += 4
    bases["state_c"][16:24] += 4
    rows = []
    for g in groups:
        lib = rng.integers(1500, 3500)
        mu = bases[g] / bases[g].sum() * lib
        rows.append(rng.poisson(np.clip(mu, 0.05, None)))
    adata = AnnData(np.asarray(rows, dtype=float))
    adata.var_names = genes
    adata.obs_names = [f"cell_{i}" for i in range(adata.n_obs)]
    adata.obs["celltype"] = pd.Categorical(groups)
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    sc.pp.pca(adata, n_comps=20)
    sc.pp.neighbors(adata, n_neighbors=12, n_pcs=20)
    sc.tl.umap(adata)
    sc.tl.leiden(adata, key_added="leiden")
    return adata


def _aggregate_by_labels(adata: AnnData, labels: pd.Series) -> AnnData:
    counts = adata.layers["counts"] if "counts" in adata.layers else adata.X
    if hasattr(counts, "toarray"):
        counts = counts.toarray()
    labels = labels.astype(str)
    order = pd.Index(sorted(labels.unique()))
    out = []
    meta = []
    for label in order:
        mask = labels == label
        mat = np.asarray(counts[mask.values, :], dtype=float)
        out.append(mat.mean(axis=0))
        meta.append({
            "metacell": label,
            "n_cells": int(mask.sum()),
            "dominant_label": str(adata.obs.loc[mask, adata.obs.columns[0]].mode().iloc[0]) if len(adata.obs.columns) else "NA",
        })
    madata = AnnData(np.vstack(out))
    madata.var_names = adata.var_names.copy()
    madata.obs = pd.DataFrame(meta).set_index("metacell")
    madata.layers["mean_expression"] = madata.X.copy()
    return madata


def run_kmeans_metacells(adata: AnnData, *, use_rep: str = "X_pca", n_metacells: int = 30, seed: int = 0) -> tuple[AnnData, pd.Series]:
    if use_rep not in adata.obsm:
        raise ValueError(f"Embedding '{use_rep}' not found in adata.obsm")
    labels = KMeans(n_clusters=n_metacells, random_state=seed, n_init=10).fit_predict(adata.obsm[use_rep])
    label_series = pd.Series([f"MC_{x:03d}" for x in labels], index=adata.obs_names, name="metacell")
    madata = _aggregate_by_labels(adata, label_series)
    return madata, label_series


def run_seacells_metacells(
    adata: AnnData,
    *,
    use_rep: str = "X_pca",
    n_metacells: int = 30,
    min_iter: int = 10,
    max_iter: int = 30,
    celltype_key: str = "leiden",
) -> tuple[AnnData, pd.Series, Any]:
    try:
        import SEACells
    except ImportError as exc:  # pragma: no cover
        raise ImportError("SEACells is required for method='seacells'. Install with `pip install SEACells`") from exc

    if use_rep not in adata.obsm:
        raise ValueError(f"Embedding '{use_rep}' not found in adata.obsm")
    model = SEACells.core.SEACells(
        adata,
        build_kernel_on=use_rep,
        n_SEACells=n_metacells,
    )
    model.construct_kernel_matrix()
    model.initialize_archetypes()
    model.fit(min_iter=min_iter, max_iter=max_iter)
    if "SEACell" not in adata.obs:
        raise RuntimeError("SEACells did not populate adata.obs['SEACell']")
    labels = adata.obs["SEACell"].astype(str).rename("metacell")
    madata = _aggregate_by_labels(adata, labels)
    if celltype_key in adata.obs:
        major = adata.obs.groupby(labels, observed=False)[celltype_key].agg(lambda x: x.astype(str).mode().iloc[0])
        madata.obs["dominant_celltype"] = major.reindex(madata.obs.index).astype(str)
    return madata, labels, model
