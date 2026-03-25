"""Spatial statistics toolkit.

Comprehensive toolkit for analyzing spatial omics data:
- Cluster-level: neighborhood enrichment, Ripley's L, co-occurrence
- Gene-level: Moran's I, Geary's C, local Moran, Getis-Ord, Bivariate Moran
- Network-level: spatial centrality, network properties

Usage::

    from skills.spatial._lib.statistics import ANALYSIS_REGISTRY, VALID_ANALYSIS_TYPES
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np
import pandas as pd
from scipy import sparse

from .adata_utils import get_spatial_key, require_spatial_coords
from .dependency_manager import require

logger = logging.getLogger(__name__)

CLUSTER_ANALYSES = ("neighborhood_enrichment", "ripley", "co_occurrence")
GENE_ANALYSES = ("moran", "geary", "local_moran", "getis_ord", "bivariate_moran")
NETWORK_ANALYSES = ("network_properties", "spatial_centrality")

VALID_ANALYSIS_TYPES = CLUSTER_ANALYSES + GENE_ANALYSES + NETWORK_ANALYSES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_categorical(adata, column: str) -> None:
    """Convert an obs column to categorical dtype if it isn't already."""
    if column not in adata.obs.columns:
        raise KeyError(f"Column '{column}' not found in adata.obs")
    if not isinstance(adata.obs[column].dtype, pd.CategoricalDtype):
        logger.info("Converting '%s' to categorical", column)
        adata.obs[column] = pd.Categorical(adata.obs[column].astype(str))


def _ensure_spatial_graph(adata, n_neighs: int = 6) -> None:
    """Build squidpy spatial graph if not already present."""
    if "spatial_connectivities" not in adata.obsp:
        require("squidpy", feature="Spatial Graph Toolkit")
        import squidpy as sq
        spatial_key = get_spatial_key(adata) or "spatial"
        sq.gr.spatial_neighbors(adata, n_neighs=n_neighs, coord_type="generic", spatial_key=spatial_key)


def _select_genes(adata, genes: list[str] | None, n_top: int = 20) -> list[str]:
    """Resolve gene list: use explicit genes or pick top HVGs by variance."""
    if genes:
        valid = [g for g in genes if g in adata.var_names]
        if not valid:
            raise ValueError(f"None of the requested genes found: {genes}")
        missing = set(genes) - set(valid)
        if missing:
            logger.warning("Genes not found (skipped): %s", missing)
        return valid

    if "highly_variable" in adata.var.columns:
        hvg = adata.var_names[adata.var["highly_variable"]].tolist()
        return hvg[:n_top]

    X = adata.X.toarray() if sparse.issparse(adata.X) else np.asarray(adata.X)
    var = np.var(X, axis=0)
    top_idx = np.argsort(var)[-n_top:][::-1]
    return [adata.var_names[i] for i in top_idx]


def _get_gene_expression(adata, gene: str) -> np.ndarray:
    """Extract expression vector for a single gene as dense 1D array."""
    idx = list(adata.var_names).index(gene)
    x = adata.X[:, idx]
    if sparse.issparse(x):
        return x.toarray().flatten()
    return np.asarray(x).flatten()


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------


def run_neighborhood_enrichment(adata, *, cluster_key: str = "leiden") -> dict:
    """Compute spatial neighbors and neighborhood enrichment z-scores."""
    require("squidpy", feature="Neighborhood enrichment")
    import squidpy as sq

    _ensure_categorical(adata, cluster_key)
    _ensure_spatial_graph(adata)

    logger.info("Computing neighborhood enrichment (cluster_key='%s') ...", cluster_key)
    sq.gr.nhood_enrichment(adata, cluster_key=cluster_key)

    uns_key = f"{cluster_key}_nhood_enrichment"
    zscore_matrix = adata.uns[uns_key]["zscore"]

    categories = list(adata.obs[cluster_key].cat.categories)
    n_clusters = len(categories)

    zscore_df = pd.DataFrame(
        zscore_matrix,
        index=categories,
        columns=categories,
    )

    mean_zscore = float(np.nanmean(zscore_matrix))
    max_zscore = float(np.nanmax(zscore_matrix))
    min_zscore = float(np.nanmin(zscore_matrix))

    return {
        "analysis_type": "neighborhood_enrichment",
        "cluster_key": cluster_key,
        "n_clusters": n_clusters,
        "categories": categories,
        "mean_zscore": mean_zscore,
        "max_zscore": max_zscore,
        "min_zscore": min_zscore,
        "zscore_df": zscore_df,
    }


def run_ripley(adata, *, cluster_key: str = "leiden") -> dict:
    """Compute Ripley's L function per cluster."""
    require("squidpy", feature="Ripley's L function")
    import squidpy as sq

    _ensure_categorical(adata, cluster_key)
    spatial_key = get_spatial_key(adata) or "spatial"
    logger.info("Computing Ripley's L function (cluster_key='%s') ...", cluster_key)
    result = sq.gr.ripley(adata, cluster_key=cluster_key, mode="L", spatial_key=spatial_key)

    categories = list(adata.obs[cluster_key].cat.categories)

    ripley_df = None
    if isinstance(result, pd.DataFrame):
        ripley_df = result
    else:
        uns_key = f"{cluster_key}_ripley_L"
        if uns_key in adata.uns:
            val = adata.uns[uns_key]
            if isinstance(val, pd.DataFrame):
                ripley_df = val
            elif isinstance(val, dict) and "L_stat" in val:
                ripley_df = val["L_stat"]

    return {
        "analysis_type": "ripley", "cluster_key": cluster_key,
        "n_clusters": len(categories), "categories": categories,
        "ripley_df": ripley_df,
    }


def run_co_occurrence(adata, *, cluster_key: str = "leiden") -> dict:
    """Compute pairwise cluster co-occurrence across spatial distances."""
    require("squidpy", feature="Co-occurrence analysis")
    import squidpy as sq

    _ensure_categorical(adata, cluster_key)
    spatial_key = get_spatial_key(adata) or "spatial"
    logger.info("Computing co-occurrence (cluster_key='%s') ...", cluster_key)
    sq.gr.co_occurrence(adata, cluster_key=cluster_key, spatial_key=spatial_key)

    categories = list(adata.obs[cluster_key].cat.categories)

    co_occ = None
    interval = None
    uns_key = f"{cluster_key}_co_occurrence"
    if uns_key in adata.uns:
        val = adata.uns[uns_key]
        if isinstance(val, dict):
            co_occ = val.get("occ")
            interval = val.get("interval")

    return {
        "analysis_type": "co_occurrence", "cluster_key": cluster_key,
        "n_clusters": len(categories), "categories": categories,
        "co_occ": co_occ, "interval": interval,
    }


def run_moran(adata, *, genes: list[str] | None = None, n_top_genes: int = 20, n_neighs: int = 6, n_perms: int = 100) -> dict:
    """Global Moran's I for gene-level spatial autocorrelation."""
    require("squidpy", feature="Moran's I")
    import squidpy as sq

    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    logger.info("Computing Moran's I for %d genes ...", len(gene_list))
    try:
        sq.gr.spatial_autocorr(adata, mode="moran", genes=gene_list, n_perms=n_perms, n_jobs=1)
    except Exception as exc:
        logger.warning("spatial_autocorr(moran) failed: %s", exc)
        return {"analysis_type": "moran", "n_genes": len(gene_list), "error": str(exc)}

    df = adata.uns["moranI"].copy()
    df["gene"] = df.index
    df = df.sort_values("I", ascending=False)
    return {
        "analysis_type": "moran", "n_genes": len(gene_list),
        "top_genes": df.head(n_top_genes)["gene"].tolist(),
        "mean_I": float(df["I"].mean()), "results_df": df,
    }


def run_geary(adata, *, genes: list[str] | None = None, n_top_genes: int = 20, n_neighs: int = 6, n_perms: int = 100) -> dict:
    """Global Geary's C — measures spatial autocorrelation."""
    require("squidpy", feature="Geary's C")
    import squidpy as sq

    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    logger.info("Computing Geary's C for %d genes ...", len(gene_list))
    try:
        sq.gr.spatial_autocorr(adata, mode="geary", genes=gene_list, n_perms=n_perms, n_jobs=1)
    except Exception as exc:
        logger.warning("spatial_autocorr(geary) failed: %s", exc)
        return {"analysis_type": "geary", "n_genes": len(gene_list), "error": str(exc)}

    df = adata.uns["gearyC"].copy()
    df["gene"] = df.index
    df = df.sort_values("C", ascending=True)
    return {
        "analysis_type": "geary", "n_genes": len(gene_list),
        "top_genes": df.head(n_top_genes)["gene"].tolist(),
        "mean_C": float(df["C"].mean()), "results_df": df,
    }


def run_local_moran(adata, *, genes: list[str] | None = None, n_top_genes: int = 10, n_neighs: int = 6) -> dict:
    """Local Moran's I (LISA) — identifies spatial hotspots/coldspots per gene."""
    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    from scipy.sparse import csr_matrix
    try:
        from esda.moran import Moran_Local
        from libpysal.weights import W
    except ImportError:
        raise ImportError("Local Moran's I requires esda and libpysal. Install with: pip install esda libpysal")

    conn = adata.obsp["spatial_connectivities"]
    if not isinstance(conn, csr_matrix):
        conn = csr_matrix(conn)

    neighbors_dict = {}
    weights_dict = {}
    for i in range(conn.shape[0]):
        row = conn.getrow(i)
        nbrs = row.indices.tolist()
        if nbrs:
            neighbors_dict[i] = nbrs
            weights_dict[i] = row.data.tolist()
        else:
            neighbors_dict[i] = [i]
            weights_dict[i] = [0.0]

    w = W(neighbors_dict, weights_dict)
    w.transform = "r"

    logger.info("Computing Local Moran's I for %d genes ...", len(gene_list))
    all_results = {}
    for gene in gene_list:
        expr = _get_gene_expression(adata, gene)
        lm = Moran_Local(expr, w, permutations=99)
        n_hotspots = int((lm.p_sim < 0.05).sum())

        all_results[gene] = {
            "n_significant_spots": n_hotspots,
            "mean_local_I": float(np.mean(lm.Is)),
            "global_I_from_local": float(np.mean(lm.Is)),
        }
        adata.obs[f"local_moran_{gene}"] = lm.Is
        adata.obs[f"local_moran_pval_{gene}"] = lm.p_sim

    return {"analysis_type": "local_moran", "n_genes": len(gene_list), "genes": gene_list, "gene_results": all_results}


def run_getis_ord(adata, *, genes: list[str] | None = None, n_top_genes: int = 10, n_neighs: int = 6) -> dict:
    """Getis-Ord Gi* — local hot/cold spot detection."""
    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    from scipy.sparse import csr_matrix
    from scipy.stats import norm

    conn = adata.obsp["spatial_connectivities"]
    if not isinstance(conn, csr_matrix):
        conn = csr_matrix(conn)

    logger.info("Computing Getis-Ord Gi* for %d genes ...", len(gene_list))
    all_results = {}
    for gene in gene_list:
        expr = _get_gene_expression(adata, gene)
        n = len(expr)
        x_mean = np.mean(expr)
        s = np.std(expr)

        if s < 1e-10:
            all_results[gene] = {"n_hotspots": 0, "n_coldspots": 0, "mean_Gi": 0.0}
            adata.obs[f"getis_ord_{gene}"] = np.zeros(n)
            continue

        gi_star = np.zeros(n)
        for i in range(n):
            row = conn.getrow(i)
            nbrs = row.indices
            wts = row.data
            if len(nbrs) == 0:
                continue

            w_sum = wts.sum()
            w_sq_sum = (wts ** 2).sum()
            wx_sum = (wts * expr[nbrs]).sum() + expr[i]
            w_total = w_sum + 1.0

            numerator = wx_sum - x_mean * w_total
            denominator = s * np.sqrt((n * (w_sq_sum + 1.0) - w_total ** 2) / (n - 1))

            if denominator > 1e-10:
                gi_star[i] = numerator / denominator

        p_values = 2 * (1 - norm.cdf(np.abs(gi_star)))
        sig = p_values < 0.05
        all_results[gene] = {
            "n_hotspots": int(np.sum(sig & (gi_star > 0))),
            "n_coldspots": int(np.sum(sig & (gi_star < 0))),
            "mean_Gi": float(np.mean(gi_star)),
        }
        adata.obs[f"getis_ord_{gene}"] = gi_star
        adata.obs[f"getis_ord_pval_{gene}"] = p_values

    return {"analysis_type": "getis_ord", "n_genes": len(gene_list), "genes": gene_list, "gene_results": all_results}


def run_bivariate_moran(adata, *, genes: list[str] | None = None, n_neighs: int = 6) -> dict:
    """Bivariate Moran's I — spatial cross-correlation between gene pairs."""
    require_spatial_coords(adata)
    if not genes or len(genes) < 2:
        raise ValueError("bivariate_moran requires at least 2 genes")

    gene_list = _select_genes(adata, genes[:2])
    if len(gene_list) < 2:
        raise ValueError(f"Need 2 valid genes, found: {gene_list}")

    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    from scipy.sparse import csr_matrix
    conn = adata.obsp["spatial_connectivities"]
    if not isinstance(conn, csr_matrix):
        conn = csr_matrix(conn)

    gene_a, gene_b = gene_list[0], gene_list[1]
    logger.info("Computing Bivariate Moran's I: %s × %s", gene_a, gene_b)

    x, y = _get_gene_expression(adata, gene_a), _get_gene_expression(adata, gene_b)
    x_z = (x - np.mean(x)) / (np.std(x) + 1e-10)
    y_z = (y - np.mean(y)) / (np.std(y) + 1e-10)

    n = len(x_z)
    w_sum, numerator = 0.0, 0.0
    for i in range(n):
        row = conn.getrow(i)
        for j_idx, w in zip(row.indices, row.data):
            numerator += w * x_z[i] * y_z[j_idx]
            w_sum += w

    bivariate_I = numerator / (w_sum + 1e-10)
    return {
        "analysis_type": "bivariate_moran", "gene_a": gene_a, "gene_b": gene_b,
        "bivariate_I": float(bivariate_I),
        "interpretation": ("positive spatial co-expression" if bivariate_I > 0 else "spatial anti-correlation" if bivariate_I < 0 else "no spatial cross-correlation"),
    }


def run_network_properties(adata, *, cluster_key: str = "leiden", n_neighs: int = 6) -> dict:
    """Graph topology metrics of the spatial neighborhood network."""
    require_spatial_coords(adata)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    try:
        import networkx as nx
    except ImportError:
        raise ImportError("network_properties requires networkx: pip install networkx")

    conn = adata.obsp["spatial_connectivities"]
    G = nx.from_scipy_sparse_array(conn) if sparse.issparse(conn) else nx.from_numpy_array(conn)
    logger.info("Analyzing spatial network: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())

    degrees = [d for _, d in G.degree()]
    clustering_coeffs = list(nx.clustering(G).values())

    result = {
        "analysis_type": "network_properties", "n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(),
        "mean_degree": float(np.mean(degrees)), "std_degree": float(np.std(degrees)),
        "mean_clustering_coeff": float(np.mean(clustering_coeffs)), "density": float(nx.density(G)),
    }

    if cluster_key in adata.obs.columns:
        _ensure_categorical(adata, cluster_key)
        per_cluster = {}
        for cat in adata.obs[cluster_key].cat.categories:
            mask = adata.obs[cluster_key] == cat
            sub_degrees = [degrees[n] for n in np.where(mask.values)[0] if n < len(degrees)]
            per_cluster[str(cat)] = {"n_cells": int(mask.sum()), "mean_degree": float(np.mean(sub_degrees)) if sub_degrees else 0}
        result["per_cluster"] = per_cluster

    return result


def run_spatial_centrality(adata, *, cluster_key: str = "leiden", n_neighs: int = 6, sample_size: int = 2000) -> dict:
    """Betweenness and closeness centrality per cluster using squidpy."""
    require("squidpy", feature="Centrality analysis")
    import squidpy as sq

    require_spatial_coords(adata)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)
    _ensure_categorical(adata, cluster_key)

    logger.info("Computing spatial centrality for clusters (cluster_key='%s') ...", cluster_key)
    sq.gr.centrality_scores(adata, cluster_key=cluster_key)

    uns_key = f"{cluster_key}_centrality_scores"
    df = adata.uns.get(uns_key)
    
    per_cluster = {}
    if df is not None:
        for cat in df.index:
            per_cluster[str(cat)] = {
                "betweenness_centrality": float(df.loc[cat, "betweenness_centrality"]) if "betweenness_centrality" in df.columns else 0.0,
                "closeness_centrality": float(df.loc[cat, "closeness_centrality"]) if "closeness_centrality" in df.columns else 0.0,
                "degree_centrality": float(df.loc[cat, "degree_centrality"]) if "degree_centrality" in df.columns else 0.0,
            }

    return {
        "analysis_type": "spatial_centrality", "cluster_key": cluster_key,
        "n_clusters": len(df.index) if df is not None else 0, "per_cluster": per_cluster,
    }


ANALYSIS_REGISTRY: dict[str, Callable] = {
    "neighborhood_enrichment": lambda adata, **kw: run_neighborhood_enrichment(adata, cluster_key=kw.get("cluster_key", "leiden")),
    "ripley": lambda adata, **kw: run_ripley(adata, cluster_key=kw.get("cluster_key", "leiden")),
    "co_occurrence": lambda adata, **kw: run_co_occurrence(adata, cluster_key=kw.get("cluster_key", "leiden")),
    "moran": lambda adata, **kw: run_moran(adata, genes=kw.get("genes"), n_top_genes=kw.get("n_top_genes", 20)),
    "geary": lambda adata, **kw: run_geary(adata, genes=kw.get("genes"), n_top_genes=kw.get("n_top_genes", 20)),
    "local_moran": lambda adata, **kw: run_local_moran(adata, genes=kw.get("genes"), n_top_genes=kw.get("n_top_genes", 10)),
    "getis_ord": lambda adata, **kw: run_getis_ord(adata, genes=kw.get("genes"), n_top_genes=kw.get("n_top_genes", 10)),
    "bivariate_moran": lambda adata, **kw: run_bivariate_moran(adata, genes=kw.get("genes")),
    "network_properties": lambda adata, **kw: run_network_properties(adata, cluster_key=kw.get("cluster_key", "leiden")),
    "spatial_centrality": lambda adata, **kw: run_spatial_centrality(adata, cluster_key=kw.get("cluster_key", "leiden")),
}
