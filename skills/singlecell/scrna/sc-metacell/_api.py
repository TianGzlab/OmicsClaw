"""Metacell assignments and mean-expression aggregates."""
from __future__ import annotations

import json
import logging
import numpy as np
import pandas as pd
from skills.singlecell._lib import metacell as methods

__all__ = ["metacells", "aggregate_metacells", "run_info", "metacell_summary", "cell_to_metacell", "size_distribution_figure"]
_RUN_KEY = "omicsclaw_sc_metacell_run"
logger = logging.getLogger(__name__)


def metacells(adata, *, method: str = "seacells", use_rep: str = "X_pca",
              n_metacells: int = 30, min_iter: int = 10, max_iter: int = 30,
              n_neighbors: int = 15, n_pcs: int = 20, random_state: int = 0,
              celltype_key: str = "leiden"):
    """Annotate input cells and return a new mean-expression metacell AnnData.

    KMeans uses the selected embedding. SEACells falls back to KMeans only
    when its package cannot be imported; a warning and run_info identify the
    fallback. Runtime errors propagate. Counts
    are averaged, not summed, using layers['counts'] when present, else X.
    Input X is preserved; obs['metacell'] receives the assignments.

    :param method: seacells (default) or kmeans.
    :param use_rep: Existing embedding, default X_pca.
    :param n_metacells: Requested aggregates, default 30; at least 2 and fewer than cells.
    :param min_iter: SEACells minimum fitting iterations, default 10.
    :param max_iter: SEACells maximum fitting iterations, default 30.
    :param n_neighbors: Neighbor count for SEACells when its graph is absent, default 15.
    :param n_pcs: PCs for that graph, default 20.
    :param random_state: Seed for KMeans and SEACells initialization, default 0.
    :param celltype_key: SEACells dominant-celltype annotation, default leiden.
        KMeans retains the legacy dominant_label from the first obs column.
    :returns: A new AnnData with mean_expression layer, n_cells and dominant_label.
    :raises ValueError: The method, embedding or numerical parameters are invalid.
    """
    if method not in {"seacells", "kmeans"}:
        raise ValueError("method must be seacells or kmeans")
    if use_rep not in adata.obsm:
        raise ValueError(f"Embedding {use_rep!r} is missing")
    if not 2 <= n_metacells < adata.n_obs:
        raise ValueError("n_metacells must be at least 2 and smaller than n_cells")
    if not 1 <= min_iter <= max_iter or n_neighbors < 2 or n_pcs < 1:
        raise ValueError("invalid iteration or neighbor parameters")
    requested = method
    reason = None
    if method == "seacells":
        try:
            import SEACells  # noqa: F401
        except ImportError:
            method = "kmeans"
            reason = "SEACells package is unavailable; used kmeans"
            logger.warning(reason)
    if method == "seacells":
        if "neighbors" not in adata.uns:
            import scanpy as sc
            sc.pp.neighbors(adata, n_neighbors=n_neighbors,
                            n_pcs=min(n_pcs, adata.obsm[use_rep].shape[1]), random_state=random_state)
        state = np.random.get_state()
        try:
            np.random.seed(random_state)
            result, labels, _ = methods.run_seacells_metacells(
                adata, use_rep=use_rep, n_metacells=n_metacells, min_iter=min_iter,
                max_iter=max_iter, celltype_key=celltype_key,
            )
        finally:
            np.random.set_state(state)
    else:
        result, labels = methods.run_kmeans_metacells(adata, use_rep=use_rep,
                                                     n_metacells=n_metacells, seed=random_state)
    adata.obs["metacell"] = labels.reindex(adata.obs_names).astype(str)
    result.uns[_RUN_KEY] = json.dumps({"requested_method": requested, "executed_method": method,
                                      "fallback_used": reason is not None, "fallback_reason": reason,
                                      "expression_source": "layers.counts" if "counts" in adata.layers else "X",
                                      "aggregation": "mean", "random_state": random_state})
    return result


def aggregate_metacells(adata, labels: pd.Series | None = None):
    """Return mean-expression aggregates for labels, or the input obs['metacell'].

    Labels must cover every cell. Prefer layers['counts'] over X. This is
    not a summed pseudobulk matrix and does not infer biological replicates.
    """
    labels = adata.obs["metacell"] if labels is None else labels.reindex(adata.obs_names)
    if labels.isna().any():
        raise ValueError("metacell labels must cover every cell")
    return methods._aggregate_by_labels(adata, labels)


def run_info(madata, *, keep: bool = True) -> dict:
    """Read requested/executed method and aggregation diagnostics from the result."""
    value = madata.uns.get(_RUN_KEY, "{}") if keep else madata.uns.pop(_RUN_KEY, "{}")
    return json.loads(value)


def metacell_summary(madata) -> pd.DataFrame:
    """Return a copy of the aggregate's size and dominant-label metadata."""
    return madata.obs.copy()


def cell_to_metacell(adata) -> pd.DataFrame:
    """Return cell and metacell columns from the annotated input AnnData."""
    return pd.DataFrame({"cell": adata.obs_names, "metacell": adata.obs["metacell"].astype(str).to_numpy()})


def size_distribution_figure(madata):
    """Return a matplotlib Figure of cells per metacell."""
    from matplotlib import pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(madata.obs["n_cells"], bins=min(30, madata.n_obs))
    ax.set(xlabel="Cells per metacell", ylabel="Metacells")
    fig.tight_layout()
    return fig
