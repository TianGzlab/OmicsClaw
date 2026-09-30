"""Synthetic multi-batch single-cell AnnData for integration-consensus tests.

Builds a small dataset with a clear cell-type structure plus an additive
per-batch shift (the technical effect integration should remove). Deterministic
given ``seed``. Carries raw ``counts`` (for scVI/Scanorama/HVG), a log-normalised
``X``, ``obsm['X_pca']``, and ``obs['batch']`` / ``obs['cell_type']``.

This is a CI **smoke** fixture only — a synthetic shift is not a fair scientific
validation of integration quality (ADR 0029 defers that to real multi-batch
data). It exercises plumbing, artifact schema, the panel, and failure modes.
"""

from __future__ import annotations

import numpy as np


def make_multibatch_adata(
    *,
    n_per_group: int = 50,
    n_batches: int = 2,
    n_types: int = 3,
    n_genes: int = 200,
    batch_strength: float = 1.5,
    seed: int = 0,
):
    """Return a small multi-batch AnnData (``n_batches * n_types * n_per_group`` cells)."""
    import anndata as ad
    import scanpy as sc

    rng = np.random.default_rng(seed)
    # Per-type mean expression programs (shared across batches = the biology).
    type_programs = rng.gamma(shape=1.0, scale=1.0, size=(n_types, n_genes)) * 3.0
    # Per-batch additive shift on a random gene subset (the technical effect).
    batch_shift = np.zeros((n_batches, n_genes))
    for b in range(n_batches):
        affected = rng.choice(n_genes, size=n_genes // 2, replace=False)
        batch_shift[b, affected] = rng.normal(b * batch_strength, 0.2, size=affected.size)

    counts, batches, types = [], [], []
    for b in range(n_batches):
        for t in range(n_types):
            rate = np.clip(type_programs[t] + batch_shift[b], 0.05, None)
            block = rng.poisson(lam=rate, size=(n_per_group, n_genes)).astype(np.float32)
            counts.append(block)
            batches += [f"batch{b}"] * n_per_group
            types += [f"type{t}"] * n_per_group

    X = np.vstack(counts)
    adata = ad.AnnData(X=X.copy())
    adata.obs_names = [f"cell_{i}" for i in range(adata.n_obs)]
    adata.var_names = [f"gene_{j}" for j in range(n_genes)]
    adata.obs["batch"] = batches
    adata.obs["cell_type"] = types
    adata.layers["counts"] = X.copy()

    # Standard log-normalise + PCA so X_pca (the panel baseline) exists.
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, n_comps=min(30, n_genes - 1, adata.n_obs - 1), random_state=seed)
    return adata
