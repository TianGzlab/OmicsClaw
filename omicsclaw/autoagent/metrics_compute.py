"""Standalone metrics computation from processed adata files.

Loads the ``processed.h5ad`` output of any skill and computes quality
metrics *independently* of the skill script.  This avoids modifying
skills and keeps all evaluation logic in the autoagent module.

Strategy dispatch:
    skill type   → what to compute
    clustering   → silhouette, calinski-harabasz, (spatial) local purity
    integration  → iLISI, cLISI, batch ASW, cell-type ASW
    annotation   → n_cell_types, unknown_fraction, mean_confidence
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Embedding search order (most informative first)
_EMBEDDING_PRIORITY = (
    "X_pca",
    "X_harmony",
    "X_scvi",
    "X_scanvi",
    "X_scanorama",
    "X_stagate",
    "X_graphst",
    "X_banksy_pca",
    "X_cellcharter",
)

# Columns that represent "unknown" annotations
_UNKNOWN_LABELS = frozenset({
    "unknown", "unassigned", "nan", "none", "", "na",
    "Unknown", "Unassigned", "NA", "None",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_metrics_from_adata(
    adata_path: Path,
    skill_name: str,
    method: str = "",
    params: dict[str, Any] | None = None,
) -> dict[str, float] | None:
    """Load a processed adata and compute quality metrics for the given skill.

    Returns a dict of ``{metric_name: value}`` or ``None`` if the adata
    cannot be loaded or no strategy matches the skill.
    """
    try:
        import scanpy as sc
        adata = sc.read_h5ad(adata_path)
    except Exception as exc:
        logger.warning("Failed to load adata from %s: %s", adata_path, exc)
        return None

    params = params or {}
    strategy = _resolve_strategy(skill_name)
    if strategy is None:
        logger.info("No adata metrics strategy for skill %r", skill_name)
        return None

    try:
        return strategy(adata, skill_name, method, params)
    except Exception as exc:
        logger.warning("Metrics computation failed for %s: %s", skill_name, exc)
        return None


# ---------------------------------------------------------------------------
# Strategy dispatch
# ---------------------------------------------------------------------------

# Maps canonical skill aliases to computation functions.
# The _resolve_strategy function also handles alias resolution.
_STRATEGY_MAP: dict[str, Any] = {}


def _resolve_strategy(skill_name: str):
    """Find the metrics strategy for a skill, resolving aliases."""
    if skill_name in _STRATEGY_MAP:
        return _STRATEGY_MAP[skill_name]
    # Try alias resolution via registry
    try:
        from omicsclaw.autoagent.metrics_registry import _canonicalize_skill_name
        canonical = _canonicalize_skill_name(skill_name)
        if canonical in _STRATEGY_MAP:
            return _STRATEGY_MAP[canonical]
    except Exception:
        pass
    return None


def _register_strategy(skill_names: list[str], fn) -> None:
    for name in skill_names:
        _STRATEGY_MAP[name] = fn


# ---------------------------------------------------------------------------
# Clustering / spatial domain metrics
# ---------------------------------------------------------------------------


def _compute_clustering_metrics(
    adata,
    skill_name: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, float]:
    """Silhouette, Calinski-Harabasz, and (for spatial) local purity."""
    from sklearn.metrics import calinski_harabasz_score, silhouette_score

    label_col = _infer_label_col(adata, params, skill_name)
    if label_col is None or label_col not in adata.obs.columns:
        logger.warning("No label column found in adata for %s", skill_name)
        return {}

    labels = adata.obs[label_col].astype(str).to_numpy()
    n_unique = len(set(labels))
    if n_unique < 2 or n_unique >= adata.n_obs:
        return {"n_clusters": float(n_unique)}

    embedding = _find_best_embedding(adata, skill_name)
    if embedding is None:
        return {"n_clusters": float(n_unique)}

    result: dict[str, float] = {"n_clusters": float(n_unique)}

    from omicsclaw.autoagent.constants import SILHOUETTE_SAMPLE_SIZE
    sample_size = min(SILHOUETTE_SAMPLE_SIZE, adata.n_obs)
    try:
        result["silhouette"] = round(
            float(silhouette_score(embedding, labels, sample_size=sample_size, random_state=0)),
            4,
        )
    except Exception as exc:
        logger.debug("Silhouette computation failed: %s", exc)

    try:
        result["calinski_harabasz"] = round(
            float(calinski_harabasz_score(embedding, labels)), 2
        )
    except Exception as exc:
        logger.debug("Calinski-Harabasz computation failed: %s", exc)

    # Spatial local purity (only for spatial skills)
    if _is_spatial_skill(skill_name):
        purity = _compute_spatial_local_purity(adata, label_col)
        if purity is not None:
            result["mean_local_purity"] = round(purity, 4)

    return result


_register_strategy(
    ["spatial-domains", "spatial-domain-identification", "sc-clustering"],
    _compute_clustering_metrics,
)


# ---------------------------------------------------------------------------
# Batch integration metrics
# ---------------------------------------------------------------------------


def _compute_integration_metrics(
    adata,
    skill_name: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, float]:
    """iLISI, cLISI, batch ASW, cell-type ASW."""
    batch_key = params.get("batch_key", "batch")
    if batch_key not in adata.obs.columns:
        # Try common alternatives
        for alt in ("batch", "sample", "sample_id"):
            if alt in adata.obs.columns:
                batch_key = alt
                break
        else:
            logger.warning("No batch column found in adata")
            return {}

    n_batches = adata.obs[batch_key].nunique()
    if n_batches < 2:
        return {"n_batches": float(n_batches)}

    embedding_key = _infer_embedding_key(adata, params)
    if embedding_key is None:
        return {"n_batches": float(n_batches)}

    label_key = _infer_annotation_col(adata, params)
    result: dict[str, float] = {"n_batches": float(n_batches)}

    # LISI scores
    try:
        from skills.singlecell._lib.integration import compute_lisi_scores
        lisi_df = compute_lisi_scores(
            adata,
            batch_key=batch_key,
            label_key=label_key if label_key and label_key in adata.obs.columns else None,
            use_rep=embedding_key,
            verbose=False,
        )
        result["mean_ilisi"] = round(float(lisi_df["ilisi"].mean()), 4)
        if "clisi" in lisi_df.columns:
            result["mean_clisi"] = round(float(lisi_df["clisi"].mean()), 4)
    except Exception as exc:
        logger.debug("LISI computation failed: %s", exc)

    # ASW scores
    try:
        from skills.singlecell._lib.integration import compute_asw_scores
        if label_key and label_key in adata.obs.columns:
            asw = compute_asw_scores(
                adata,
                batch_key=batch_key,
                label_key=label_key,
                use_rep=embedding_key,
                verbose=False,
            )
            result["batch_asw"] = round(float(asw["batch_asw"]), 4)
            result["celltype_asw"] = round(float(asw["celltype_asw"]), 4)
    except Exception as exc:
        logger.debug("ASW computation failed: %s", exc)

    return result


_register_strategy(
    ["sc-batch-integration", "spatial-integrate"],
    _compute_integration_metrics,
)


# ---------------------------------------------------------------------------
# Annotation metrics
# ---------------------------------------------------------------------------


def _compute_annotation_metrics(
    adata,
    skill_name: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, float]:
    """n_cell_types, unknown_fraction, mean_confidence."""
    annotation_col = _infer_annotation_col(adata, params)
    if annotation_col is None or annotation_col not in adata.obs.columns:
        logger.warning("No annotation column found in adata for %s", skill_name)
        return {}

    labels = adata.obs[annotation_col].astype(str).to_numpy()
    unique_types = set(labels) - _UNKNOWN_LABELS
    n_total = len(labels)

    result: dict[str, float] = {
        "n_cell_types": float(len(unique_types)),
    }

    # Unknown fraction
    n_unknown = sum(1 for lab in labels if lab in _UNKNOWN_LABELS)
    if n_total > 0:
        result["unknown_fraction"] = round(n_unknown / n_total, 4)

    # Confidence score (if available)
    for score_col in ("annotation_score", "confidence", "score"):
        if score_col in adata.obs.columns:
            vals = adata.obs[score_col].dropna()
            if len(vals) > 0:
                result["mean_confidence"] = round(float(vals.mean()), 4)
            break

    return result


_register_strategy(
    ["sc-cell-annotation", "spatial-annotate", "spatial-cell-annotation"],
    _compute_annotation_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_label_col(
    adata,
    params: dict[str, Any],
    skill_name: str,
) -> str | None:
    """Infer the primary label column from params and adata."""
    # Explicit param
    for key in ("cluster_key", "groupby", "label_key"):
        if key in params and params[key] in adata.obs.columns:
            return params[key]

    # Skill-specific defaults
    defaults = {
        "spatial-domains": "spatial_domain",
        "spatial-domain-identification": "spatial_domain",
        "sc-clustering": "leiden",
    }
    default_col = defaults.get(skill_name)
    if default_col and default_col in adata.obs.columns:
        return default_col

    # Fallback: try common names
    for col in ("spatial_domain", "leiden", "louvain", "cluster", "cell_type"):
        if col in adata.obs.columns:
            return col

    return None


def _infer_annotation_col(
    adata,
    params: dict[str, Any],
) -> str | None:
    """Infer the annotation column."""
    for key in ("cell_type_key", "labels_key", "annotation_col"):
        if key in params and params[key] in adata.obs.columns:
            return params[key]
    for col in ("cell_type", "annotation", "cell_type_annotation"):
        if col in adata.obs.columns:
            return col
    return None


def _infer_embedding_key(
    adata,
    params: dict[str, Any],
) -> str | None:
    """Infer the embedding key from params or adata."""
    # From params
    for key in ("embedding_key", "use_rep"):
        val = params.get(key)
        if val and val in adata.obsm:
            return val

    # Search by priority
    for key in _EMBEDDING_PRIORITY:
        if key in adata.obsm:
            return key

    return None


def _find_best_embedding(adata, skill_name: str) -> np.ndarray | None:
    """Find the best numeric embedding for metric computation."""
    # Method-specific embeddings first
    for key in _EMBEDDING_PRIORITY:
        if key in adata.obsm:
            return np.asarray(adata.obsm[key])

    # Spatial coordinates as fallback (for spatial skills)
    if _is_spatial_skill(skill_name):
        for key in ("spatial", "X_spatial"):
            if key in adata.obsm:
                coords = np.asarray(adata.obsm[key])
                return coords[:, :2] if coords.shape[1] > 2 else coords

    return None


def _is_spatial_skill(skill_name: str) -> bool:
    return "spatial" in skill_name


# ---------------------------------------------------------------------------
# Preprocessing metrics
# ---------------------------------------------------------------------------


def _compute_preprocessing_metrics(
    adata,
    skill_name: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, float]:
    """cell_retention, n_hvgs, n_genes_after from a preprocessed adata."""
    result: dict[str, float] = {}

    result["n_genes_after"] = float(adata.n_vars)

    # HVG count
    if "highly_variable" in adata.var.columns:
        result["n_hvgs"] = float(adata.var["highly_variable"].sum())

    # Cell retention — compare to raw count if available
    n_obs_raw = None
    for key in ("n_obs_raw", "n_obs_before_qc", "raw_n_obs"):
        if key in adata.uns:
            n_obs_raw = adata.uns[key]
            break
    if n_obs_raw is None and "raw" in dir(adata) and adata.raw is not None:
        n_obs_raw = adata.raw.n_obs
    if n_obs_raw is not None and n_obs_raw > 0:
        result["cell_retention"] = round(adata.n_obs / float(n_obs_raw), 4)
    else:
        # No raw reference — report 1.0 (cannot measure loss)
        result["cell_retention"] = 1.0

    # PCA dimensions (bonus)
    if "X_pca" in adata.obsm:
        result["n_pcs"] = float(adata.obsm["X_pca"].shape[1])

    return result


_register_strategy(
    ["sc-preprocessing", "sc-preprocess", "spatial-preprocess"],
    _compute_preprocessing_metrics,
)


# ---------------------------------------------------------------------------
# Differential expression metrics
# ---------------------------------------------------------------------------


def _compute_de_metrics(
    adata,
    skill_name: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, float]:
    """n_de_genes, n_significant, n_marker_hits from rank_genes_groups."""
    if "rank_genes_groups" not in adata.uns:
        logger.info("No rank_genes_groups in adata for %s", skill_name)
        return {}

    import pandas as pd

    try:
        rgg = adata.uns["rank_genes_groups"]
        names = pd.DataFrame(rgg["names"])
        pvals_adj = pd.DataFrame(rgg["pvals_adj"]) if "pvals_adj" in rgg else None
        logfoldchanges = pd.DataFrame(rgg["logfoldchanges"]) if "logfoldchanges" in rgg else None
    except Exception as exc:
        logger.debug("Failed to parse rank_genes_groups: %s", exc)
        return {}

    n_de_genes = float(names.size)
    result: dict[str, float] = {"n_de_genes": n_de_genes}

    fdr_threshold = float(params.get("fdr_threshold", 0.05))
    log2fc_threshold = float(params.get("log2fc_threshold", 1.0))

    if pvals_adj is not None:
        sig_mask = pvals_adj < fdr_threshold
        result["n_significant"] = float(sig_mask.sum().sum())

        if logfoldchanges is not None:
            fc_mask = logfoldchanges.abs() > log2fc_threshold
            result["n_marker_hits"] = float((sig_mask & fc_mask).sum().sum())

    return result


_register_strategy(
    ["sc-de", "spatial-de"],
    _compute_de_metrics,
)


# ---------------------------------------------------------------------------
# Marker gene metrics
# ---------------------------------------------------------------------------


def _compute_marker_metrics(
    adata,
    skill_name: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, float]:
    """n_markers, n_clusters from rank_genes_groups."""
    if "rank_genes_groups" not in adata.uns:
        logger.info("No rank_genes_groups in adata for %s", skill_name)
        return {}

    import pandas as pd

    try:
        rgg = adata.uns["rank_genes_groups"]
        names = pd.DataFrame(rgg["names"])
    except Exception as exc:
        logger.debug("Failed to parse rank_genes_groups: %s", exc)
        return {}

    # n_markers = total non-empty names across all groups
    n_markers = float((names != "").sum().sum())
    n_clusters = float(names.shape[1])

    return {"n_markers": n_markers, "n_clusters": n_clusters}


_register_strategy(
    ["sc-markers"],
    _compute_marker_metrics,
)


# ---------------------------------------------------------------------------
# Deconvolution metrics
# ---------------------------------------------------------------------------


def _compute_deconv_metrics(
    adata,
    skill_name: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, float]:
    """n_cell_types, n_common_genes from deconvolution output."""
    result: dict[str, float] = {}

    # Look for proportion matrix in obsm
    proportion_key = None
    for key in adata.obsm:
        if "proportion" in key.lower() or "deconv" in key.lower():
            proportion_key = key
            break

    if proportion_key is not None:
        proportions = np.asarray(adata.obsm[proportion_key])
        # n_cell_types = columns with non-negligible proportions
        col_sums = proportions.sum(axis=0)
        result["n_cell_types"] = float((col_sums > 0.01).sum())
    else:
        # Fallback: check obs columns for cell type proportions
        prop_cols = [c for c in adata.obs.columns
                     if adata.obs[c].dtype in ("float64", "float32")
                     and not c.startswith("n_")
                     and c not in ("total_counts", "pct_counts_mt")]
        if prop_cols:
            result["n_cell_types"] = float(len(prop_cols))

    result["n_common_genes"] = float(adata.n_vars)

    return result


_register_strategy(
    ["spatial-deconv", "spatial-deconvolution"],
    _compute_deconv_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_spatial_local_purity(
    adata,
    label_col: str,
    k: int | None = None,
) -> float | None:
    """Mean local purity based on spatial k-nearest neighbors."""
    # Find spatial coordinates
    spatial_key = None
    for key in ("spatial", "X_spatial"):
        if key in adata.obsm:
            spatial_key = key
            break
    if spatial_key is None:
        return None

    if label_col not in adata.obs.columns or adata.n_obs < 2:
        return None

    try:
        from omicsclaw.autoagent.constants import SPATIAL_K_NEIGHBORS
        from sklearn.neighbors import NearestNeighbors

        if k is None:
            k = SPATIAL_K_NEIGHBORS
        coords = np.asarray(adata.obsm[spatial_key])[:, :2]
        labels = adata.obs[label_col].astype(str).to_numpy()
        n_neighbors = min(k + 1, adata.n_obs)
        if n_neighbors <= 1:
            return None

        nbrs = NearestNeighbors(n_neighbors=n_neighbors).fit(coords)
        _, indices = nbrs.kneighbors(coords)
        neighbor_idx = indices[:, 1:]  # exclude self
        if neighbor_idx.shape[1] == 0:
            return None

        purity = (labels[neighbor_idx] == labels[:, None]).mean(axis=1)
        return float(purity.mean())
    except Exception as exc:
        logger.debug("Spatial local purity failed: %s", exc)
        return None
