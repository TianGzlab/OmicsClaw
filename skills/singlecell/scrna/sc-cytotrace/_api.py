"""CytoTRACE-simple complexity scores and potency tables."""
from __future__ import annotations

import json
import logging
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse
from scipy.stats import rankdata

__all__ = ["cytotrace", "run_info", "potency_table", "potency_composition", "potency_figure"]
logger = logging.getLogger(__name__)
_RUN_KEY = "omicsclaw_sc_cytotrace_run"
POTENCY_LABELS = ["Differentiated", "Unipotent", "Oligopotent", "Multipotent", "Pluripotent", "Totipotent"]
POTENCY_BINS = np.linspace(0, 1, len(POTENCY_LABELS) + 1)


def cytotrace(adata, *, n_neighbors: int = 30, layer: str | None = None):
    """Annotate a complexity-based potency proxy in place, preserving X.

    This is CytoTRACE-simple, not the published CytoTRACE or CytoTRACE 2.
    It counts positive expression, smooths rank scores, ranks them again
    and bins them into six relative categories. Existing neighbors are reused.

    :param adata: AnnData with expression and optionally PCA/neighbors.
    :param n_neighbors: Neighbors to construct when absent; default 30.
    :param layer: Expression layer for gene detection; None uses X.
        Use counts or unscaled log expression, not centered/scaled X.
    :returns: The same AnnData with cytotrace_score, cytotrace_gene_count
        and cytotrace_potency in obs; run_info returns diagnostics.
    :raises ValueError: The input is empty, a layer is missing, or neighbors < 1.
    """
    if adata.n_obs == 0 or adata.n_vars == 0:
        raise ValueError("cytotrace requires cells and genes")
    if layer is not None and layer not in adata.layers:
        raise ValueError(f"expression layer {layer!r} is missing")
    if n_neighbors < 1:
        raise ValueError("n_neighbors must be positive")
    summary = _run_cytotrace_simple(adata, n_neighbors=n_neighbors, layer=layer)
    adata.uns[_RUN_KEY] = json.dumps(summary)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read JSON potency diagnostics; keep=False removes them from uns."""
    value = adata.uns.get(_RUN_KEY, "{}") if keep else adata.uns.pop(_RUN_KEY, "{}")
    return json.loads(value)


def potency_table(adata) -> pd.DataFrame:
    """Return per-cell score, category and detected-gene count, indexed by cell."""
    return adata.obs[["cytotrace_score", "cytotrace_potency", "cytotrace_gene_count"]].copy()


def potency_composition(adata) -> pd.DataFrame:
    """Return counts for the six relative potency bins; they are not cell-type calls."""
    counts = adata.obs["cytotrace_potency"].value_counts().reindex(POTENCY_LABELS, fill_value=0)
    return pd.DataFrame({"potency": counts.index.astype(str), "n_cells": counts.to_numpy()})


def potency_figure(adata):
    """Return a matplotlib Figure showing the potency score distribution."""
    from matplotlib import pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(adata.obs["cytotrace_score"], bins=40)
    ax.set(xlabel="CytoTRACE-simple score", ylabel="Cells")
    fig.tight_layout()
    return fig


def _compute_gene_counts(adata, layer=None) -> np.ndarray:
    """Count the number of detected genes per cell (genes with expression > 0)."""
    X = adata.layers[layer] if layer is not None else adata.X
    if sparse.issparse(X):
        return np.asarray((X > 0).sum(axis=1)).ravel().astype(float)
    return np.asarray((X > 0).sum(axis=1)).ravel().astype(float)


def _knn_smooth(values: np.ndarray, adata, n_neighbors: int = 30) -> np.ndarray:
    """Smooth values using KNN from the neighbor graph.

    If a neighbor graph already exists it is reused; otherwise one is built
    from ``X_pca`` or ``X``.
    """
    if "neighbors" not in adata.uns:
        if "X_pca" in adata.obsm:
            sc.pp.neighbors(adata, n_neighbors=n_neighbors, use_rep="X_pca")
        else:
            sc.pp.neighbors(adata, n_neighbors=n_neighbors)

    connectivities = adata.obsp.get("connectivities")
    if connectivities is None:
        logger.warning("No connectivities found; skipping KNN smoothing.")
        return values

    # Row-normalize the connectivities
    if sparse.issparse(connectivities):
        row_sums = np.asarray(connectivities.sum(axis=1)).ravel()
        row_sums[row_sums == 0] = 1.0
        # Diagonal (self) + neighbors
        smoothed = np.asarray(connectivities.dot(values.reshape(-1, 1))).ravel()
        smoothed = (smoothed + values) / (row_sums + 1)
    else:
        row_sums = connectivities.sum(axis=1)
        row_sums[row_sums == 0] = 1.0
        smoothed = (connectivities @ values + values) / (row_sums + 1)

    return smoothed


def _run_cytotrace_simple(
    adata,
    *,
    n_neighbors: int = 30,
    layer: str | None = None,
) -> dict:
    """CytoTRACE-simple: gene expression complexity as a potency proxy.

    Steps:
    1. Count genes detected per cell (gene_count).
    2. Rank-normalize to [0, 1] to produce the CytoTRACE score.
    3. Smooth with KNN graph.
    4. Bin into 6 potency categories.

    Parameters
    ----------
    adata
        AnnData object (normalized or raw counts).
    n_neighbors
        Number of neighbors for KNN smoothing.

    Returns
    -------
    Summary dictionary with method info and score statistics.
    """
    logger.info("Running cytotrace_simple on %d cells x %d genes", adata.n_obs, adata.n_vars)

    # Step 1: Gene detection counts
    gene_counts = _compute_gene_counts(adata, layer=layer)
    logger.info(
        "Gene detection range: %d - %d (mean %.1f)",
        int(gene_counts.min()),
        int(gene_counts.max()),
        gene_counts.mean(),
    )

    # Step 2: Rank-normalize to [0, 1]
    ranked = rankdata(gene_counts)
    raw_score = (ranked - ranked.min()) / max(ranked.max() - ranked.min(), 1)

    # Step 3: KNN smoothing
    smoothed_score = _knn_smooth(raw_score, adata, n_neighbors=n_neighbors)

    # Re-normalize after smoothing
    smoothed_ranked = rankdata(smoothed_score)
    cytotrace_score = (smoothed_ranked - smoothed_ranked.min()) / max(
        smoothed_ranked.max() - smoothed_ranked.min(), 1
    )

    # Step 4: Potency binning
    potency = pd.cut(
        cytotrace_score,
        bins=POTENCY_BINS,
        labels=POTENCY_LABELS,
        include_lowest=True,
    )

    # Store in adata
    adata.obs["cytotrace_score"] = cytotrace_score
    adata.obs["cytotrace_potency"] = potency
    adata.obs["cytotrace_gene_count"] = gene_counts.astype(int)

    # Potency composition
    potency_counts = adata.obs["cytotrace_potency"].value_counts().to_dict()

    # Check for degenerate output
    unique_potency = adata.obs["cytotrace_potency"].nunique()
    degenerate = unique_potency <= 1

    summary = {
        "method": "cytotrace_simple",
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_neighbors": n_neighbors,
        "score_mean": float(np.mean(cytotrace_score)),
        "score_std": float(np.std(cytotrace_score)),
        "score_min": float(np.min(cytotrace_score)),
        "score_max": float(np.max(cytotrace_score)),
        "potency_counts": {str(k): int(v) for k, v in potency_counts.items()},
        "n_potency_categories": unique_potency,
        "degenerate": degenerate,
    }

    if degenerate:
        summary["suggested_actions"] = [
            "The dataset may have too few cells or insufficient gene expression diversity.",
            "Try preprocessing with sc-preprocessing first.",
            "Consider using the full cytotrace2 method with pretrained models.",
        ]
        logger.warning(
            "  *** DEGENERATE OUTPUT: Only %d potency category detected. ***\n"
            "  This usually means the gene expression complexity is too uniform.\n"
            "  How to fix:\n"
            "    Option 1 — Ensure the data has been properly preprocessed (sc-preprocessing).\n"
            "    Option 2 — Check if the data has sufficient gene diversity (>1000 genes).\n",
            unique_potency,
        )

    logger.info("CytoTRACE-simple complete: %d potency categories", unique_potency)
    return summary


# ---------------------------------------------------------------------------
# Visualization
