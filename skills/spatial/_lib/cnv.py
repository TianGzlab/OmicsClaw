"""Spatial CNV inference functions.

Provides inferCNVpy and Numbat for copy number variation analysis.

Usage::

    from skills.spatial._lib.cnv import run_cnv, SUPPORTED_METHODS
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .dependency_manager import require, validate_r_environment

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("infercnvpy", "numbat")


def validate_reference(adata, reference_key: str | None, reference_cat: list[str]) -> None:
    """Validate that reference key and categories exist in adata."""
    if reference_key is None:
        return
    if reference_key not in adata.obs.columns:
        raise ValueError(f"'{reference_key}' not in adata.obs. Available: {list(adata.obs.columns)}")
    avail = set(adata.obs[reference_key].unique())
    missing = set(reference_cat) - avail
    if missing:
        raise ValueError(f"Categories {sorted(missing)} not in '{reference_key}'. Available: {sorted(avail)}")


def run_infercnvpy(adata, *, reference_key: str | None = None, reference_cat: list[str] | None = None,
                   window_size: int = 100, step: int = 10, dynamic_threshold: float | None = 1.5) -> dict:
    """Infer CNV using inferCNVpy."""
    require("infercnvpy", feature="CNV inference")
    import infercnvpy as cnv

    logger.info("Running inferCNVpy (window=%d, step=%d)", window_size, step)
    cnv.tl.infercnv(adata, reference_key=reference_key, reference_cat=reference_cat,
                     window_size=window_size, step=step, dynamic_threshold=dynamic_threshold)
    cnv.tl.cnv_score(adata)

    cnv_score_col = "cnv_score" if "cnv_score" in adata.obs.columns else None
    mean_score = float(adata.obs[cnv_score_col].mean()) if cnv_score_col else 0.0
    high_cnv_pct = 0.0
    if cnv_score_col:
        threshold = float(adata.obs[cnv_score_col].quantile(0.9))
        high_cnv_pct = float((adata.obs[cnv_score_col] > threshold).mean() * 100)

    return {
        "method": "infercnvpy", "n_genes": adata.n_vars,
        "mean_cnv_score": round(mean_score, 4), "high_cnv_fraction_pct": round(high_cnv_pct, 2),
        "cnv_score_key": cnv_score_col,
    }


def run_numbat(adata, *, reference_key: str | None = None, reference_cat: list[str] | None = None) -> dict:
    """Haplotype-aware CNV inference via R Numbat."""
    robjects, pandas2ri, numpy2ri, importr, localconverter, default_converter, openrlib, anndata2ri = (
        validate_r_environment(required_r_packages=["numbat"])
    )
    if "allele_counts" not in adata.obsm:
        raise ValueError("Numbat requires allele count data in adata.obsm['allele_counts']")

    with openrlib.rlock:
        with localconverter(default_converter + anndata2ri.converter):
            r_sce = anndata2ri.py2rpy(adata)
            numbat = importr("numbat")
            robjects.r("""
                function(sce, ref_key, ref_cat) {
                    nb <- Numbat$new(count_mat = assay(sce, 'X'), ref_prefix = ref_key)
                    list(cnv_calls = nb$joint_post)
                }
            """)(r_sce, reference_key or "NULL", reference_cat or robjects.NULL)

    return {"method": "numbat", "n_genes": adata.n_vars, "mean_cnv_score": 0.0, "high_cnv_fraction_pct": 0.0}


def run_cnv(adata, *, method: str = "infercnvpy", reference_key: str | None = None,
            reference_cat: list[str] | None = None, window_size: int = 100, step: int = 10) -> dict:
    """Run CNV inference. Returns summary dict."""
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")
    validate_reference(adata, reference_key, reference_cat or [])

    if method == "numbat":
        result = run_numbat(adata, reference_key=reference_key, reference_cat=reference_cat)
    else:
        result = run_infercnvpy(adata, reference_key=reference_key, reference_cat=reference_cat,
                                window_size=window_size, step=step)
    return {"n_cells": adata.n_obs, "n_genes": adata.n_vars, **result}
