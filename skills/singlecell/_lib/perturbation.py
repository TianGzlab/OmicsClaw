"""Helpers for single-cell perturbation analysis."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
import scanpy as sc
from anndata import AnnData

from .adata_utils import matrix_looks_count_like

logger = logging.getLogger(__name__)


def make_demo_perturb_adata(seed: int = 0) -> AnnData:
    """Create a small perturbation demo dataset with controls and two perturbations."""
    rng = np.random.default_rng(seed)
    n_cells, n_genes = 180, 80
    genes = [f"Gene{i}" for i in range(n_genes)]
    perts = []
    reps = []
    rows = []

    ctrl = rng.gamma(2.0, 1.0, size=n_genes)
    ko_a = ctrl.copy()
    ko_b = ctrl.copy()
    ko_a[:10] += 4
    ko_b[10:20] += 4

    for pert_name, base in [("NT", ctrl), ("KO_A", ko_a), ("KO_B", ko_b)]:
        for rep in ("r1", "r2"):
            for _ in range(30):
                lib = rng.integers(1500, 3200)
                mu = base / base.sum() * lib
                rows.append(rng.poisson(np.clip(mu, 0.05, None)))
                perts.append(pert_name)
                reps.append(rep)

    adata = AnnData(np.asarray(rows, dtype=float))
    adata.var_names = genes
    adata.obs_names = [f"cell_{i}" for i in range(adata.n_obs)]
    adata.obs["perturbation"] = pd.Categorical(perts)
    adata.obs["replicate"] = pd.Categorical(reps)
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    sc.pp.pca(adata, n_comps=20)
    return adata


def prepare_perturbation_matrix(adata: AnnData) -> str:
    """Ensure Mixscape sees a normalized matrix and report the source used."""
    if matrix_looks_count_like(adata.X):
        counts = adata.X.copy()
        adata.layers["counts"] = counts
        sc.pp.normalize_total(adata)
        sc.pp.log1p(adata)
        return "adata.X(counts->log1p)"
    return "adata.X"


def run_mixscape_workflow(
    adata: AnnData,
    *,
    pert_key: str,
    control: str,
    split_by: str | None = None,
    n_neighbors: int = 20,
    logfc_threshold: float = 0.25,
    pval_cutoff: float = 0.05,
    perturbation_type: str = "KO",
) -> dict[str, Any]:
    import pertpy as pt

    matrix_source = prepare_perturbation_matrix(adata)
    mixscape = pt.tl.Mixscape()
    mixscape.perturbation_signature(
        adata,
        pert_key=pert_key,
        control=control,
        ref_selection_mode="split_by" if split_by else "nn",
        split_by=split_by,
        n_neighbors=n_neighbors,
    )
    mixscape.mixscape(
        adata,
        pert_key=pert_key,
        control=control,
        split_by=split_by,
        logfc_threshold=logfc_threshold,
        pval_cutoff=pval_cutoff,
        perturbation_type=perturbation_type,
    )

    class_col = "mixscape_class"
    global_col = "mixscape_class_global"
    prob_col = f"mixscape_class_p_{perturbation_type.lower()}"
    class_counts = adata.obs[class_col].astype(str).value_counts().rename_axis("class").reset_index(name="n_cells")
    global_counts = adata.obs[global_col].astype(str).value_counts().rename_axis("global_class").reset_index(name="n_cells")

    adata.uns["mixscape_summary"] = {
        "matrix_source": matrix_source,
        "perturbation_key": pert_key,
        "control": control,
        "split_by": split_by,
        "class_column": class_col,
        "global_class_column": global_col,
        "probability_column": prob_col,
    }
    return {
        "method": "mixscape",
        "matrix_source": matrix_source,
        "class_column": class_col,
        "global_class_column": global_col,
        "probability_column": prob_col,
        "class_counts": class_counts,
        "global_counts": global_counts,
    }
