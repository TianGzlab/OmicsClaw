"""sc-clustering's function library: neighbour graph, Leiden or Louvain clusters, and a 2-D embedding.

In a step: ``clustering = load_skill("sc-clustering")``. The functions compute
and return objects; they read and write no files. The input is a
preprocessed AnnData with an embedding such as ``obsm['X_pca']``.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
import scanpy as sc
from sklearn.metrics import silhouette_score

from skills.singlecell._lib import dimred as sc_dimred_utils
from skills.singlecell._lib.adata_utils import get_matrix_contract, propagate_singlecell_contracts

__all__ = [
    "cluster",
    "auto_resolution",
    "run_info",
    "cluster_summary",
    "embedding_figure",
]

logger = logging.getLogger(__name__)

_RUN_KEY = "omicsclaw_sc_clustering_run"
EMBEDDINGS = ("umap", "tsne", "diffmap", "phate")
METHODS = ("leiden", "louvain")


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def cluster(
    adata,
    *,
    use_rep: str | None = None,
    use_existing_graph: bool = False,
    n_neighbors: int = 15,
    n_pcs: int = 50,
    embedding: str = "umap",
    method: str = "leiden",
    resolution: float = 1.0,
    random_state: int = 0,
    umap_min_dist: float = 0.5,
    umap_spread: float = 1.0,
    tsne_perplexity: float = 30.0,
    tsne_metric: str = "euclidean",
    diffmap_n_comps: int = 15,
    phate_knn: int = 15,
    phate_decay: int = 40,
):
    """Build the neighbour graph, cluster the cells and compute a 2-D embedding, in place.

    Writes ``obs[method]`` (the cluster labels, a categorical of strings),
    ``obsm['X_<embedding>']``, the graph in ``obsp`` and ``uns['neighbors']``, and
    records the cluster key as the primary one in the matrix contract.

    :param use_rep: The ``obsm`` key the graph is built on. Default ``None``: the
        first of ``X_pca``, ``X_harmony``, ``X_scvi``, ``X_scanvi``, ``X_scanorama``
        present. Pass ``X_harmony`` or ``X_scvi`` after batch integration.
    :param n_neighbors: Neighbours per cell in the graph. Default 15, scanpy's default.
        Larger values give smoother, coarser structure.
    :param use_existing_graph: Keep the graph in ``uns['neighbors']`` and ``obsp``
        instead of rebuilding it. Default False; set True after BBKNN. Graph
        construction parameters are then ignored; UMAP and diffusion maps use
        the retained graph, while t-SNE and PHATE still use ``use_rep``.
    :param n_pcs: Components of ``use_rep`` to use. Default 50; pick it from
        sc-preprocessing's ``pca_variance_table`` (the elbow) when the data are small.
    :param embedding: ``"umap"`` (default), ``"tsne"``, ``"diffmap"`` or ``"phate"``.
    :param method: ``"leiden"`` (default) or ``"louvain"``; also the ``obs`` column written.
    :param resolution: Clustering resolution. Default 1.0, scanpy's default. Lower it
        (0.3 to 0.6) for broad cell types, raise it for finer subtypes; or use
        :func:`auto_resolution`.
    :param random_state: Seed for the graph, the clustering and the embedding. Default 0,
        scanpy's default, which makes reruns reproduce the labels.
    :param umap_min_dist: UMAP ``min_dist``. Default 0.5, scanpy's default.
    :param umap_spread: UMAP ``spread``. Default 1.0, scanpy's default.
    :param tsne_perplexity: t-SNE perplexity. Default 30.
    :param tsne_metric: t-SNE distance metric. Default ``"euclidean"``.
    :param diffmap_n_comps: Diffusion-map components. Default 15.
    :param phate_knn: PHATE neighbours. Default 15.
    :param phate_decay: PHATE alpha decay. Default 40.
    :returns: The same AnnData.
    :raises ValueError: no embedding is available, or an unknown method or embedding.
    """
    if method not in METHODS:
        raise ValueError(f"unknown clustering method {method!r}; choose {' or '.join(METHODS)}")
    if embedding not in EMBEDDINGS:
        raise ValueError(f"unknown embedding {embedding!r}; choose one of {', '.join(EMBEDDINGS)}")
    rep = _resolve_use_rep(adata, use_rep)
    adata, keys = _run_clustering(
        adata,
        use_rep=rep,
        use_existing_graph=use_existing_graph,
        embedding_method=embedding,
        n_neighbors=n_neighbors,
        n_pcs=n_pcs,
        cluster_method=method,
        resolution=resolution,
        umap_min_dist=umap_min_dist,
        umap_spread=umap_spread,
        tsne_perplexity=tsne_perplexity,
        tsne_metric=tsne_metric,
        diffmap_n_comps=diffmap_n_comps,
        phate_knn=phate_knn,
        phate_decay=phate_decay,
        random_state=random_state,
    )
    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill="sc-clustering",
        x_kind="normalized_expression",
        raw_kind=get_matrix_contract(adata).get("raw"),
        primary_cluster_key=keys["cluster_key"],
    )
    info = {
        "use_rep": rep,
        "used_existing_graph": use_existing_graph,
        "cluster_key": keys["cluster_key"],
        "embedding_key": keys["embedding_key"],
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
    }
    adata.uns[_RUN_KEY] = json.dumps(info, default=_json_default)
    return adata


def auto_resolution(
    adata,
    *,
    use_rep: str | None = None,
    n_neighbors: int = 15,
    n_pcs: int = 50,
    method: str = "leiden",
    resolutions: list[float] | None = None,
    n_subsample_reps: int = 5,
    subsample_fraction: float = 0.8,
    random_state: int = 1,
) -> pd.DataFrame:
    """Choose a clustering resolution by how stably cells co-cluster under subsampling.

    Builds the neighbour graph, then for every candidate resolution clusters
    ``n_subsample_reps`` random subsamples, turns how often two cells share a
    cluster into a distance, and scores the full-data clustering with the
    silhouette on that distance. The best-scoring clustering is left in
    ``obs[method]``; pass the selected resolution to :func:`cluster`. The cost
    grows with the square of the number of cells.

    :param use_rep: As in :func:`cluster`.
    :param n_neighbors: As in :func:`cluster`.
    :param n_pcs: As in :func:`cluster`.
    :param method: ``"leiden"`` (default) or ``"louvain"``.
    :param resolutions: Candidates. Default ``[0.4, 0.6, 0.8, 1.0, 1.2, 1.4]``.
    :param n_subsample_reps: Subsamples per resolution. Default 5.
    :param subsample_fraction: Fraction of cells in each subsample. Default 0.8.
    :param random_state: Seed for the subsampling. Default 1, the CLI's value.
    :returns: Columns ``resolution``, ``silhouette_score`` and ``selected`` (true on the chosen row).
    """
    rep = _resolve_use_rep(adata, use_rep)
    sc_dimred_utils.build_neighbor_graph(adata, n_neighbors=n_neighbors, n_pcs=n_pcs, use_rep=rep, inplace=True)
    best, info = _search_resolution(
        adata,
        use_rep=rep,
        cluster_method=method,
        resolutions=resolutions,
        n_subsample_reps=n_subsample_reps,
        subsample_fraction=subsample_fraction,
        random_state=random_state,
    )
    table = info["resolution_df"].copy()
    table["selected"] = np.isclose(table["resolution"].astype(float), best)
    return table


def run_info(adata, *, keep: bool = True) -> dict:
    """What :func:`cluster` recorded: ``use_rep``, ``cluster_key``, ``embedding_key`` and the contracts.

    :param keep: Leave the record in ``adata.uns``; ``False`` removes it.
    :returns: The record, or an empty dict when ``cluster`` has not run on *adata*.
    """
    raw = adata.uns.get(_RUN_KEY) if keep else adata.uns.pop(_RUN_KEY, None)
    return json.loads(raw) if raw else {}


def cluster_summary(adata, *, key: str = "leiden") -> pd.DataFrame:
    """Cells per cluster, largest first.

    :param key: The ``obs`` column holding the labels. Default ``"leiden"``.
    :returns: Columns ``cluster``, ``n_cells`` and ``proportion_pct`` (rounded to 2 decimals).
    """
    counts = adata.obs[key].astype(str).value_counts()
    total = max(int(adata.n_obs), 1)
    return pd.DataFrame([
        {"cluster": str(label), "n_cells": int(count), "proportion_pct": round(int(count) / total * 100, 2)}
        for label, count in counts.items()
    ])


def embedding_figure(adata, *, color: str = "leiden", basis: str | None = None):
    """A scatter plot of the 2-D embedding, coloured by an ``obs`` column.

    :param color: The ``obs`` column to colour by. Default ``"leiden"``.
    :param basis: The ``obsm`` key to plot. Default: the first of ``X_umap``,
        ``X_tsne``, ``X_diffmap``, ``X_phate`` present.
    :returns: A matplotlib Figure.
    :raises KeyError: no 2-D embedding is present.
    """
    import matplotlib.pyplot as plt

    key = basis or next((k for k in ("X_umap", "X_tsne", "X_diffmap", "X_phate") if k in adata.obsm), None)
    if key is None:
        raise KeyError("no 2-D embedding in obsm; run cluster() first")
    coords = np.asarray(adata.obsm[key])[:, :2]
    labels = adata.obs[color].astype(str)
    fig, ax = plt.subplots(figsize=(6, 5))
    palette = plt.get_cmap("tab20")
    for index, label in enumerate(sorted(labels.unique(), key=lambda v: (len(v), v))):
        mask = (labels == label).to_numpy()
        ax.scatter(coords[mask, 0], coords[mask, 1], s=4, color=palette(index % 20), label=label, linewidths=0)
    ax.set_xlabel(f"{key[2:]}1")
    ax.set_ylabel(f"{key[2:]}2")
    ax.set_title(f"{key[2:]} coloured by {color}")
    ax.legend(markerscale=3, fontsize=7, frameon=False, bbox_to_anchor=(1.0, 1.0), loc="upper left")
    fig.tight_layout()
    return fig


def _candidate_embeddings(adata) -> list[str]:
    preferred = [key for key in ("X_pca", "X_harmony", "X_scvi", "X_scanvi", "X_scanorama") if key in adata.obsm]
    if preferred:
        return preferred
    return [str(key) for key in adata.obsm.keys() if str(key).startswith("X_")]


def _embedding_key_from_method(embedding_method: str) -> str:
    mapping = {
        "umap": "X_umap",
        "tsne": "X_tsne",
        "diffmap": "X_diffmap",
        "phate": "X_phate",
    }
    return mapping[embedding_method]


def _resolve_use_rep(adata, use_rep: str | None) -> str:
    if use_rep:
        return use_rep
    candidates = _candidate_embeddings(adata)
    if not candidates:
        raise ValueError("No embedding available for clustering.")
    return candidates[0]


def _run_clustering(
    adata,
    *,
    use_rep: str,
    use_existing_graph: bool = False,
    embedding_method: str = "umap",
    n_neighbors: int = 15,
    n_pcs: int = 50,
    cluster_method: str = "leiden",
    resolution: float = 1.0,
    umap_min_dist: float = 0.5,
    umap_spread: float = 1.0,
    tsne_perplexity: float = 30.0,
    tsne_metric: str = "euclidean",
    diffmap_n_comps: int = 15,
    phate_knn: int = 15,
    phate_decay: int = 40,
    random_state: int = 0,
) -> tuple[object, dict]:
    if use_existing_graph:
        neighbors = adata.uns.get("neighbors", {})
        if not neighbors or neighbors.get("connectivities_key", "connectivities") not in adata.obsp:
            raise ValueError("use_existing_graph requires an existing neighbor graph")
    else:
        sc_dimred_utils.build_neighbor_graph(
            adata,
            n_neighbors=n_neighbors,
            n_pcs=n_pcs,
            use_rep=use_rep,
            random_state=random_state,
            inplace=True,
        )
    cluster_key = cluster_method
    if cluster_method == "leiden":
        sc_dimred_utils.cluster_leiden(adata, resolution=resolution, key_added=cluster_key, random_state=random_state, inplace=True)
    else:
        sc_dimred_utils.cluster_louvain(adata, resolution=resolution, key_added=cluster_key, random_state=random_state, inplace=True)
    if embedding_method == "umap":
        sc_dimred_utils.run_umap_reduction(
            adata,
            min_dist=umap_min_dist,
            spread=umap_spread,
            random_state=random_state,
            inplace=True,
        )
    elif embedding_method == "tsne":
        sc_dimred_utils.run_tsne_reduction(
            adata,
            n_pcs=n_pcs,
            use_rep=use_rep,
            perplexity=tsne_perplexity,
            metric=tsne_metric,
            random_state=random_state,
            inplace=True,
        )
    elif embedding_method == "diffmap":
        sc_dimred_utils.run_diffmap(adata, n_comps=diffmap_n_comps, inplace=True)
    else:
        sc_dimred_utils.run_phate_reduction(
            adata,
            use_rep=use_rep,
            knn=phate_knn,
            decay=phate_decay,
            random_state=random_state,
            inplace=True,
        )
    embedding_key = _embedding_key_from_method(embedding_method)
    return adata, {"cluster_key": cluster_key, "embedding_key": embedding_key}


def _search_resolution(
    adata,
    *,
    use_rep: str,
    cluster_method: str = "leiden",
    resolutions: list[float] | None = None,
    n_subsample_reps: int = 5,
    subsample_fraction: float = 0.8,
    random_state: int = 1,
) -> tuple[float, dict]:
    """Find the optimal clustering resolution via bootstrap subsampling + silhouette scoring.

    For each candidate resolution, the method:
    1. Repeatedly subsamples the data (``n_subsample_reps`` times).
    2. Clusters each subsample and builds a co-clustering distance matrix.
    3. Computes the silhouette score of the full-data clustering against the
       co-clustering distances (precomputed metric).
    4. Selects the resolution with the highest silhouette score.

    Parameters
    ----------
    adata
        AnnData with a neighbor graph already built.
    use_rep
        Embedding key used for the neighbor graph (informational; the graph
        must already be present in ``adata.uns['neighbors']``).
    cluster_method
        ``"leiden"`` or ``"louvain"``.
    resolutions
        Candidate resolutions to evaluate.  Default ``[0.4, 0.6, 0.8, 1.0, 1.2, 1.4]``.
    n_subsample_reps
        Number of bootstrap subsampling rounds per resolution.
    subsample_fraction
        Fraction of cells to keep in each subsample.
    random_state
        Random seed.

    Returns
    -------
    best_resolution
        The resolution with the highest silhouette score.
    search_info
        Dictionary with ``silhouette_scores``, ``best_resolution``, and
        ``resolution_df`` (a pandas DataFrame of resolution vs score).
    """
    if resolutions is None:
        resolutions = [0.4, 0.6, 0.8, 1.0, 1.2, 1.4]

    cluster_func = sc.tl.leiden if cluster_method == "leiden" else sc.tl.louvain
    cluster_obs_key = cluster_method

    sample_n = adata.n_obs
    subsample_n = int(sample_n * subsample_fraction)
    rng = np.random.RandomState(random_state)

    silhouette_avg: dict[str, float] = {}
    best_resolution = resolutions[0]
    highest_sil = -1.0

    logger.info("Auto-resolution search over %d candidates: %s", len(resolutions), resolutions)

    for r in resolutions:
        r = round(r, 2)
        r_key = f"{cluster_obs_key}_r{r}"
        logger.info("  Testing resolution %.2f ...", r)

        # Build co-clustering distance matrix via bootstrap subsampling
        subsampling_n = np.zeros((sample_n, sample_n), dtype=np.float32)
        coclustering_n = np.zeros((sample_n, sample_n), dtype=np.float32)

        for _rep in range(n_subsample_reps):
            subsample_idx = rng.choice(sample_n, subsample_n, replace=False)
            sub_adata = adata[subsample_idx].copy()
            cluster_func(sub_adata, resolution=r, key_added=cluster_obs_key)
            cluster_labels = sub_adata.obs[cluster_obs_key].to_numpy()

            for i in range(subsample_n):
                for j in range(i + 1, subsample_n):
                    xi, xj = subsample_idx[i], subsample_idx[j]
                    subsampling_n[xi, xj] += 1
                    subsampling_n[xj, xi] += 1
                    if cluster_labels[i] == cluster_labels[j]:
                        coclustering_n[xi, xj] += 1
                        coclustering_n[xj, xi] += 1

        # Avoid division by zero
        safe_denom = subsampling_n.copy()
        safe_denom[safe_denom == 0] = 1e6
        distance = 1.0 - coclustering_n / safe_denom
        np.fill_diagonal(distance, 0.0)

        # Full-data clustering at this resolution
        cluster_func(adata, resolution=r, key_added=r_key)
        labels = adata.obs[r_key].to_numpy()

        # Need at least 2 distinct labels for silhouette
        n_unique = len(set(labels))
        if n_unique < 2:
            sil = -1.0
        else:
            sil = float(silhouette_score(distance, labels, metric="precomputed"))

        silhouette_avg[str(r)] = sil
        logger.info("    resolution=%.2f  silhouette=%.4f  clusters=%d", r, sil, n_unique)

        if sil > highest_sil:
            highest_sil = sil
            best_resolution = r

    # Set the best clustering as the primary cluster key
    best_key = f"{cluster_obs_key}_r{best_resolution}"
    adata.obs[cluster_obs_key] = adata.obs[best_key]

    # Clean up intermediate resolution columns
    for r in resolutions:
        r = round(r, 2)
        r_key = f"{cluster_obs_key}_r{r}"
        if r_key in adata.obs.columns and r_key != best_key:
            del adata.obs[r_key]

    # Build summary DataFrame
    resolution_df = pd.DataFrame(
        [{"resolution": float(k), "silhouette_score": v} for k, v in silhouette_avg.items()]
    )

    search_info = {
        "silhouette_scores": silhouette_avg,
        "best_resolution": float(best_resolution),
        "highest_silhouette": float(highest_sil),
        "resolution_df": resolution_df,
        "n_subsample_reps": n_subsample_reps,
        "subsample_fraction": subsample_fraction,
    }

    logger.info("Auto-resolution selected: %.2f (silhouette=%.4f)", best_resolution, highest_sil)
    return float(best_resolution), search_info
