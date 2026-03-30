"""Spatial data preprocessing pipeline.

Provides a standard scanpy-based preprocessing workflow for spatial
transcriptomics data: QC metrics → filtering → normalization → HVG
selection → PCA → neighbors → UMAP → Leiden clustering.

Tissue-specific QC presets are available for common tissue types,
following best practices from Luecken & Theis (2019) and community
guidelines.

Usage::

    from skills.spatial._lib.preprocessing import preprocess

    adata, summary = preprocess(adata, species="human", n_top_hvg=2000)
    adata, summary = preprocess(adata, tissue="brain", species="human")
"""

from __future__ import annotations

import logging

import numpy as np

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs

ensure_runtime_cache_dirs()

import scanpy as sc

from .adata_utils import get_spatial_key, store_analysis_metadata

logger = logging.getLogger(__name__)

PREPROCESS_METHOD = "scanpy_standard"
SUPPORTED_SPECIES = ("human", "mouse")
METHOD_PARAM_DEFAULTS = {
    PREPROCESS_METHOD: {
        "min_genes": 0,
        "min_cells": 0,
        "max_mt_pct": 20.0,
        "max_genes": 0,
        "n_top_hvg": 2000,
        "n_pcs": 30,
        "n_neighbors": 15,
        "leiden_resolution": 0.5,
        "normalize_target_sum": 1e4,
        "hvg_flavor": "seurat_v3",
        "leiden_flavor": "igraph",
    }
}

# ---------------------------------------------------------------------------
# Tissue-specific QC presets
# ---------------------------------------------------------------------------

TISSUE_PRESETS: dict[str, dict] = {
    "pbmc":    {"max_mt_pct": 5,  "min_genes": 200, "max_genes": 2500},
    "brain":   {"max_mt_pct": 10, "min_genes": 200, "max_genes": 6000},
    "heart":   {"max_mt_pct": 50, "min_genes": 200, "max_genes": 5000},
    "tumor":   {"max_mt_pct": 20, "min_genes": 200, "max_genes": 5000},
    "liver":   {"max_mt_pct": 15, "min_genes": 200, "max_genes": 4000},
    "kidney":  {"max_mt_pct": 15, "min_genes": 200, "max_genes": 4000},
    "lung":    {"max_mt_pct": 15, "min_genes": 200, "max_genes": 5000},
    "gut":     {"max_mt_pct": 20, "min_genes": 200, "max_genes": 5000},
    "skin":    {"max_mt_pct": 10, "min_genes": 200, "max_genes": 4000},
    "muscle":  {"max_mt_pct": 30, "min_genes": 200, "max_genes": 5000},
}


def suggest_n_pcs(adata, variance_threshold: float = 0.85) -> int:
    """Suggest optimal number of PCs based on cumulative variance.

    Returns a recommended PC count that captures at least
    *variance_threshold* of the total variance, clamped to [15, 30].

    Parameters
    ----------
    adata : AnnData
        Must have PCA already computed (``adata.uns['pca']``).
    variance_threshold : float
        Fraction of cumulative variance to capture (default 0.85).

    Returns
    -------
    int
        Recommended number of PCs.
    """
    pca_info = adata.uns.get("pca", {})
    var_ratio = pca_info.get("variance_ratio")
    if var_ratio is None:
        logger.warning("No PCA variance info found; cannot suggest n_pcs")
        return 30

    cumsum = np.cumsum(var_ratio)
    n_target = int(np.searchsorted(cumsum, variance_threshold)) + 1
    recommended = max(15, min(n_target, 30))
    logger.info(
        "PC suggestion: %d PCs capture %.1f%% variance (threshold=%.0f%%)",
        recommended, cumsum[min(recommended - 1, len(cumsum) - 1)] * 100,
        variance_threshold * 100,
    )
    return recommended


def preprocess(
    adata,
    *,
    min_genes: int = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["min_genes"],
    min_cells: int = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["min_cells"],
    max_mt_pct: float = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["max_mt_pct"],
    max_genes: int = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["max_genes"],
    n_top_hvg: int = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["n_top_hvg"],
    n_pcs: int = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["n_pcs"],
    n_neighbors: int = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["n_neighbors"],
    leiden_resolution: float = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["leiden_resolution"],
    resolutions: list[float] | None = None,
    tissue: str | None = None,
    species: str = "human",
    skill_name: str = "spatial-preprocess",
) -> tuple:
    """Run the full spatial preprocessing pipeline.

    Parameters
    ----------
    adata : AnnData
        Raw spatial transcriptomics data.
    min_genes : int
        Minimum genes per cell for filtering.
    min_cells : int
        Minimum cells per gene for filtering.
    max_mt_pct : float
        Maximum mitochondrial percentage for cell filtering.
    max_genes : int
        Maximum genes per cell for filtering (0 = no upper limit).
        Automatically set when using tissue presets.
    n_top_hvg : int
        Number of highly variable genes to select.
    n_pcs : int
        Number of principal components.
    n_neighbors : int
        Number of neighbors for graph construction.
    leiden_resolution : float
        Resolution for Leiden clustering (used as primary).
    resolutions : list[float] | None
        Optional list of resolutions to explore (e.g., [0.4, 0.6, 0.8, 1.0]).
        All results stored in ``adata.obs['leiden_res_X']``.
    tissue : str | None
        Tissue type for automatic QC preset selection. One of:
        pbmc, brain, heart, tumor, liver, kidney, lung, gut, skin, muscle.
        Explicit parameters override tissue preset values.
    species : str
        Species for MT gene prefix detection ("human" or "mouse").
    skill_name : str
        Name for metadata storage.

    Returns
    -------
    tuple[AnnData, dict]
        Processed AnnData and summary dictionary.
    """
    if species not in SUPPORTED_SPECIES:
        raise ValueError(f"Unsupported species '{species}'. Supported: {SUPPORTED_SPECIES}")
    if n_top_hvg <= 0:
        raise ValueError("n_top_hvg must be > 0")
    if n_pcs <= 0:
        raise ValueError("n_pcs must be > 0")
    if n_neighbors <= 0:
        raise ValueError("n_neighbors must be > 0")
    if leiden_resolution <= 0:
        raise ValueError("leiden_resolution must be > 0")

    # Apply tissue presets (explicit params take precedence)
    preset_applied = None
    if tissue:
        tissue_lower = tissue.lower()
        if tissue_lower in TISSUE_PRESETS:
            preset = TISSUE_PRESETS[tissue_lower]
            preset_applied = tissue_lower
            if min_genes == 0:
                min_genes = preset["min_genes"]
            if max_mt_pct == 20.0:
                max_mt_pct = preset["max_mt_pct"]
            if max_genes == 0:
                max_genes = preset.get("max_genes", 0)
            logger.info(
                "Applied '%s' tissue preset: min_genes=%d, max_mt_pct=%.0f, max_genes=%d",
                tissue_lower, min_genes, max_mt_pct, max_genes,
            )
        else:
            logger.warning(
                "Unknown tissue '%s'. Available: %s",
                tissue, ", ".join(sorted(TISSUE_PRESETS)),
            )

    n_cells_raw = adata.n_obs
    n_genes_raw = adata.n_vars
    logger.info("Input: %d cells x %d genes", n_cells_raw, n_genes_raw)

    # QC metrics
    mt_prefix = "MT-" if species == "human" else "mt-"
    adata.var["mt"] = adata.var_names.str.startswith(mt_prefix)
    sc.pp.calculate_qc_metrics(
        adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True,
    )

    # Filter
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)
    if max_mt_pct < 100:
        adata = adata[adata.obs["pct_counts_mt"] < max_mt_pct].copy()
    if max_genes > 0:
        adata = adata[adata.obs["n_genes_by_counts"] < max_genes].copy()

    n_cells_filtered = adata.n_obs
    n_genes_filtered = adata.n_vars
    if n_cells_filtered < 2:
        raise ValueError("Too few cells/spots remain after QC filtering (<2). Relax QC thresholds.")
    if n_genes_filtered < 2:
        raise ValueError("Too few genes remain after QC filtering (<2). Relax QC thresholds.")
    logger.info(
        "After QC: %d cells x %d genes (removed %d cells, %d genes)",
        n_cells_filtered, n_genes_filtered,
        n_cells_raw - n_cells_filtered, n_genes_raw - n_genes_filtered,
    )

    # Preserve raw counts in layers for reliable downstream use (DE, HVG)
    adata.layers["counts"] = adata.X.copy()

    # Preserve raw counts
    adata.raw = adata.copy()

    # Normalize
    normalize_target_sum = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["normalize_target_sum"]
    sc.pp.normalize_total(adata, target_sum=normalize_target_sum)
    sc.pp.log1p(adata)

    # HVG
    n_hvg = max(1, min(n_top_hvg, adata.n_vars))
    sc.pp.highly_variable_genes(
        adata,
        n_top_genes=n_hvg,
        flavor=METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["hvg_flavor"],
        layer="counts",
    )
    n_hvg_selected = int(adata.var["highly_variable"].sum())
    logger.info("Selected %d highly variable genes", n_hvg_selected)

    # Scale + PCA on HVG
    adata_hvg = adata[:, adata.var["highly_variable"]].copy()
    sc.pp.scale(adata_hvg, max_value=10)
    n_comps = min(n_pcs, adata_hvg.n_vars - 1, adata_hvg.n_obs - 1)
    if n_comps < 2:
        raise ValueError(
            "Too few observations or HVGs remain to compute PCA (<2 components). "
            "Relax QC thresholds or reduce HVG filtering."
        )
    sc.tl.pca(adata_hvg, n_comps=n_comps)

    # Copy embeddings back
    adata.obsm["X_pca"] = adata_hvg.obsm["X_pca"]
    adata.uns["pca"] = adata_hvg.uns.get("pca", {})
    if "PCs" in adata_hvg.varm:
        adata.varm["PCs"] = np.zeros((adata.n_vars, n_comps))
        hvg_mask = adata.var["highly_variable"].values
        adata.varm["PCs"][hvg_mask] = adata_hvg.varm["PCs"]

    # Log PC recommendation (informational only)
    suggested_pcs = suggest_n_pcs(adata)
    n_pcs_use = min(n_comps, 30)
    if n_pcs_use != suggested_pcs:
        logger.info(
            "Using %d PCs for neighbors (suggested: %d based on variance)",
            n_pcs_use, suggested_pcs,
        )

    # Neighbors + UMAP + Leiden
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs_use)
    sc.tl.umap(adata)
    leiden_flavor = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["leiden_flavor"]
    sc.tl.leiden(adata, resolution=leiden_resolution, flavor=leiden_flavor)

    n_clusters = adata.obs["leiden"].nunique()
    logger.info("Leiden clustering: %d clusters (resolution=%.2f)", n_clusters, leiden_resolution)

    # Multi-resolution clustering exploration
    multi_res_info = {}
    if resolutions:
        for res in resolutions:
            col_name = f"leiden_res_{res}"
            sc.tl.leiden(adata, resolution=res, flavor=leiden_flavor, key_added=col_name)
            n_cl = adata.obs[col_name].nunique()
            multi_res_info[str(res)] = n_cl
            logger.info("  Resolution %.2f: %d clusters", res, n_cl)

    effective_params = {
        "species": species,
        "tissue_preset": preset_applied,
        "min_genes": min_genes,
        "min_cells": min_cells,
        "max_mt_pct": max_mt_pct,
        "max_genes": max_genes,
        "n_top_hvg": n_top_hvg,
        "n_hvg_selected": n_hvg_selected,
        "n_pcs_requested": n_pcs,
        "n_pcs_computed": n_comps,
        "n_pcs_used": n_pcs_use,
        "n_pcs_suggested": suggested_pcs,
        "n_neighbors": n_neighbors,
        "leiden_resolution": leiden_resolution,
        "normalize_target_sum": normalize_target_sum,
        "hvg_flavor": METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["hvg_flavor"],
        "leiden_flavor": leiden_flavor,
    }
    if resolutions:
        effective_params["resolutions"] = list(resolutions)

    store_analysis_metadata(
        adata,
        skill_name,
        PREPROCESS_METHOD,
        params=effective_params,
    )

    summary = {
        "method": PREPROCESS_METHOD,
        "n_cells_raw": n_cells_raw,
        "n_genes_raw": n_genes_raw,
        "n_cells_filtered": n_cells_filtered,
        "n_genes_filtered": n_genes_filtered,
        "n_hvg": n_hvg_selected,
        "n_clusters": n_clusters,
        "has_spatial": get_spatial_key(adata) is not None,
        "cluster_sizes": adata.obs["leiden"].value_counts().to_dict(),
        "n_pcs_computed": n_comps,
        "n_pcs_used": n_pcs_use,
        "n_pcs_suggested": suggested_pcs,
        "tissue_preset": preset_applied,
        "effective_params": effective_params,
    }
    if multi_res_info:
        summary["multi_resolution"] = multi_res_info
    return adata, summary
