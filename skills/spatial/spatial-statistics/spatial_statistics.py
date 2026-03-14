#!/usr/bin/env python3
"""Spatial Statistics — comprehensive spatial analysis toolkit.

Supports both cluster-level and gene-level spatial statistics:

Cluster-level (require --cluster-key):
  - neighborhood_enrichment:  Pairwise cluster co-localisation z-scores
  - ripley:                   Ripley's L function per cluster
  - co_occurrence:            Pairwise co-occurrence across distances

Gene-level (require --genes or --n-top-genes):
  - moran:            Global Moran's I autocorrelation per gene
  - geary:            Global Geary's C autocorrelation per gene
  - local_moran:      Local Moran's I (LISA) for spatial hotspots
  - getis_ord:        Getis-Ord Gi* local hot/cold spot detection
  - bivariate_moran:  Spatial cross-correlation between two genes

Network-level:
  - network_properties:  Graph topology metrics (degree, clustering coeff)
  - spatial_centrality:  Betweenness/closeness centrality per cluster

Usage:
    python spatial_statistics.py --input <file> --output <dir>
    python spatial_statistics.py --input <file> --analysis-type moran --output <dir>
    python spatial_statistics.py --input <file> --analysis-type getis_ord --genes "EPCAM,VIM" --output <dir>
    python spatial_statistics.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc
import squidpy as sq

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.spatial.adata_utils import (
    get_spatial_key,
    require_preprocessed,
    require_spatial_coords,
    store_analysis_metadata,
)
from omicsclaw.spatial.viz_utils import save_figure
from omicsclaw.spatial.viz import VizParams, plot_spatial_stats

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-statistics"
SKILL_VERSION = "0.2.0"

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


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------


def run_neighborhood_enrichment(
    adata,
    *,
    cluster_key: str = "leiden",
) -> dict:
    """Compute spatial neighbors and neighborhood enrichment z-scores."""
    _ensure_categorical(adata, cluster_key)

    logger.info("Building spatial neighbor graph ...")
    sq.gr.spatial_neighbors(adata)

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

    logger.info(
        "Enrichment z-scores: mean=%.2f, min=%.2f, max=%.2f",
        mean_zscore, min_zscore, max_zscore,
    )

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


def run_ripley(
    adata,
    *,
    cluster_key: str = "leiden",
) -> dict:
    """Compute Ripley's L function per cluster."""
    _ensure_categorical(adata, cluster_key)

    logger.info("Computing Ripley's L function (cluster_key='%s') ...", cluster_key)
    result = sq.gr.ripley(adata, cluster_key=cluster_key, mode="L")

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

    logger.info("Ripley's L computed for %d clusters", len(categories))

    return {
        "analysis_type": "ripley",
        "cluster_key": cluster_key,
        "n_clusters": len(categories),
        "categories": categories,
        "ripley_df": ripley_df,
    }


def run_co_occurrence(
    adata,
    *,
    cluster_key: str = "leiden",
) -> dict:
    """Compute pairwise cluster co-occurrence across spatial distances."""
    _ensure_categorical(adata, cluster_key)

    logger.info("Computing co-occurrence (cluster_key='%s') ...", cluster_key)
    result = sq.gr.co_occurrence(adata, cluster_key=cluster_key)

    categories = list(adata.obs[cluster_key].cat.categories)

    co_occ = None
    interval = None
    uns_key = f"{cluster_key}_co_occurrence"
    if uns_key in adata.uns:
        val = adata.uns[uns_key]
        if isinstance(val, dict):
            co_occ = val.get("occ")
            interval = val.get("interval")

    logger.info("Co-occurrence computed for %d clusters", len(categories))

    return {
        "analysis_type": "co_occurrence",
        "cluster_key": cluster_key,
        "n_clusters": len(categories),
        "categories": categories,
        "co_occ": co_occ,
        "interval": interval,
    }


# ---------------------------------------------------------------------------
# Gene-level helpers
# ---------------------------------------------------------------------------


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


def _ensure_spatial_graph(adata, n_neighs: int = 6) -> None:
    """Build squidpy spatial graph if not already present."""
    if "spatial_connectivities" not in adata.obsp:
        sq.gr.spatial_neighbors(adata, n_neighs=n_neighs, coord_type="generic")


def _get_gene_expression(adata, gene: str) -> np.ndarray:
    """Extract expression vector for a single gene as dense 1D array."""
    idx = list(adata.var_names).index(gene)
    x = adata.X[:, idx]
    if sparse.issparse(x):
        return x.toarray().flatten()
    return np.asarray(x).flatten()


# ---------------------------------------------------------------------------
# Gene-level spatial statistics
# ---------------------------------------------------------------------------


def run_moran(
    adata,
    *,
    genes: list[str] | None = None,
    n_top_genes: int = 20,
    n_neighs: int = 6,
    n_perms: int = 100,
) -> dict:
    """Global Moran's I for gene-level spatial autocorrelation."""
    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    logger.info("Computing Moran's I for %d genes ...", len(gene_list))

    try:
        sq.gr.spatial_autocorr(
            adata,
            mode="moran",
            genes=gene_list,
            n_perms=n_perms,
            n_jobs=1,
        )
    except Exception as exc:
        logger.warning("spatial_autocorr(moran) failed: %s", exc)
        return {
            "analysis_type": "moran",
            "n_genes": len(gene_list),
            "error": str(exc),
        }

    df = adata.uns["moranI"].copy()
    df["gene"] = df.index
    df = df.sort_values("I", ascending=False)

    return {
        "analysis_type": "moran",
        "n_genes": len(gene_list),
        "top_genes": df.head(n_top_genes)["gene"].tolist(),
        "mean_I": float(df["I"].mean()),
        "results_df": df,
    }


def run_geary(
    adata,
    *,
    genes: list[str] | None = None,
    n_top_genes: int = 20,
    n_neighs: int = 6,
    n_perms: int = 100,
) -> dict:
    """Global Geary's C — measures spatial autocorrelation (complement to Moran's I).

    C < 1 indicates positive spatial autocorrelation (similar neighbors),
    C > 1 indicates negative autocorrelation (dissimilar neighbors),
    C = 1 indicates spatial randomness.
    """
    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    logger.info("Computing Geary's C for %d genes ...", len(gene_list))

    try:
        sq.gr.spatial_autocorr(
            adata,
            mode="geary",
            genes=gene_list,
            n_perms=n_perms,
            n_jobs=1,
        )
    except Exception as exc:
        logger.warning("spatial_autocorr(geary) failed: %s", exc)
        return {
            "analysis_type": "geary",
            "n_genes": len(gene_list),
            "error": str(exc),
        }

    df = adata.uns["gearyC"].copy()
    df["gene"] = df.index
    df = df.sort_values("C", ascending=True)

    return {
        "analysis_type": "geary",
        "n_genes": len(gene_list),
        "top_genes": df.head(n_top_genes)["gene"].tolist(),
        "mean_C": float(df["C"].mean()),
        "results_df": df,
    }


def run_local_moran(
    adata,
    *,
    genes: list[str] | None = None,
    n_top_genes: int = 10,
    n_neighs: int = 6,
) -> dict:
    """Local Moran's I (LISA) — identifies spatial hotspots/coldspots per gene.

    Uses esda (PySAL) to compute Local Indicators of Spatial Association.
    Each spot gets a local I value and a classification (HH, HL, LH, LL, NS).
    """
    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    from scipy.sparse import csr_matrix

    try:
        from esda.moran import Moran_Local
        from libpysal.weights import W
    except ImportError:
        raise ImportError(
            "Local Moran's I requires esda and libpysal. Install with:\n"
            "  pip install esda libpysal"
        )

    conn = adata.obsp["spatial_connectivities"]
    if not isinstance(conn, csr_matrix):
        conn = csr_matrix(conn)

    neighbors_dict = {}
    weights_dict = {}
    for i in range(conn.shape[0]):
        row = conn.getrow(i)
        nbrs = row.indices.tolist()
        wts = row.data.tolist()
        if nbrs:
            neighbors_dict[i] = nbrs
            weights_dict[i] = wts
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

        sig_mask = lm.p_sim < 0.05
        n_hotspots = int(sig_mask.sum())

        all_results[gene] = {
            "n_significant_spots": n_hotspots,
            "mean_local_I": float(np.mean(lm.Is)),
            "global_I_from_local": float(np.mean(lm.Is)),
        }

        adata.obs[f"local_moran_{gene}"] = lm.Is
        adata.obs[f"local_moran_pval_{gene}"] = lm.p_sim

    return {
        "analysis_type": "local_moran",
        "n_genes": len(gene_list),
        "genes": gene_list,
        "gene_results": all_results,
    }


def run_getis_ord(
    adata,
    *,
    genes: list[str] | None = None,
    n_top_genes: int = 10,
    n_neighs: int = 6,
) -> dict:
    """Getis-Ord Gi* — local hot/cold spot detection.

    Identifies statistically significant spatial clusters of high (hot)
    or low (cold) gene expression values.
    """
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
        n_hot = int((sig & (gi_star > 0)).sum())
        n_cold = int((sig & (gi_star < 0)).sum())

        all_results[gene] = {
            "n_hotspots": n_hot,
            "n_coldspots": n_cold,
            "mean_Gi": float(np.mean(gi_star)),
        }

        adata.obs[f"getis_ord_{gene}"] = gi_star
        adata.obs[f"getis_ord_pval_{gene}"] = p_values

    return {
        "analysis_type": "getis_ord",
        "n_genes": len(gene_list),
        "genes": gene_list,
        "gene_results": all_results,
    }


def run_bivariate_moran(
    adata,
    *,
    genes: list[str] | None = None,
    n_neighs: int = 6,
) -> dict:
    """Bivariate Moran's I — spatial cross-correlation between gene pairs.

    Measures whether two genes are spatially co-expressed (positive) or
    anti-correlated in space (negative). Requires exactly 2 genes specified
    via --genes "GENE1,GENE2".
    """
    require_spatial_coords(adata)

    if not genes or len(genes) < 2:
        raise ValueError(
            "bivariate_moran requires at least 2 genes: --genes 'GENE1,GENE2'"
        )

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

    x = _get_gene_expression(adata, gene_a)
    y = _get_gene_expression(adata, gene_b)

    x_z = (x - np.mean(x)) / (np.std(x) + 1e-10)
    y_z = (y - np.mean(y)) / (np.std(y) + 1e-10)

    n = len(x_z)
    w_sum = 0.0
    numerator = 0.0
    for i in range(n):
        row = conn.getrow(i)
        for j_idx, w in zip(row.indices, row.data):
            numerator += w * x_z[i] * y_z[j_idx]
            w_sum += w

    bivariate_I = numerator / (w_sum + 1e-10)

    return {
        "analysis_type": "bivariate_moran",
        "gene_a": gene_a,
        "gene_b": gene_b,
        "bivariate_I": float(bivariate_I),
        "interpretation": (
            "positive spatial co-expression" if bivariate_I > 0
            else "spatial anti-correlation" if bivariate_I < 0
            else "no spatial cross-correlation"
        ),
    }


# ---------------------------------------------------------------------------
# Network-level analyses
# ---------------------------------------------------------------------------


def run_network_properties(
    adata,
    *,
    cluster_key: str = "leiden",
    n_neighs: int = 6,
) -> dict:
    """Graph topology metrics of the spatial neighborhood network."""
    require_spatial_coords(adata)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)

    try:
        import networkx as nx
    except ImportError:
        raise ImportError("network_properties requires networkx: pip install networkx")

    conn = adata.obsp["spatial_connectivities"]
    if sparse.issparse(conn):
        G = nx.from_scipy_sparse_array(conn)
    else:
        G = nx.from_numpy_array(conn)

    logger.info("Analyzing spatial network: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())

    degrees = [d for _, d in G.degree()]
    clustering_coeffs = list(nx.clustering(G).values())

    result = {
        "analysis_type": "network_properties",
        "n_nodes": G.number_of_nodes(),
        "n_edges": G.number_of_edges(),
        "mean_degree": float(np.mean(degrees)),
        "std_degree": float(np.std(degrees)),
        "mean_clustering_coeff": float(np.mean(clustering_coeffs)),
        "density": float(nx.density(G)),
    }

    if cluster_key in adata.obs.columns:
        _ensure_categorical(adata, cluster_key)
        per_cluster = {}
        for cat in adata.obs[cluster_key].cat.categories:
            mask = adata.obs[cluster_key] == cat
            nodes = np.where(mask.values)[0]
            sub_degrees = [degrees[n] for n in nodes if n < len(degrees)]
            per_cluster[str(cat)] = {
                "n_cells": int(mask.sum()),
                "mean_degree": float(np.mean(sub_degrees)) if sub_degrees else 0,
            }
        result["per_cluster"] = per_cluster

    return result


def run_spatial_centrality(
    adata,
    *,
    cluster_key: str = "leiden",
    n_neighs: int = 6,
    sample_size: int = 2000,
) -> dict:
    """Betweenness and closeness centrality per cluster in the spatial graph.

    For large graphs (>sample_size nodes), centrality is estimated on a
    random subsample for performance.
    """
    require_spatial_coords(adata)
    _ensure_spatial_graph(adata, n_neighs=n_neighs)
    _ensure_categorical(adata, cluster_key)

    try:
        import networkx as nx
    except ImportError:
        raise ImportError("spatial_centrality requires networkx: pip install networkx")

    conn = adata.obsp["spatial_connectivities"]
    if sparse.issparse(conn):
        G = nx.from_scipy_sparse_array(conn)
    else:
        G = nx.from_numpy_array(conn)

    n_nodes = G.number_of_nodes()
    logger.info("Computing spatial centrality for %d nodes ...", n_nodes)

    if n_nodes > sample_size:
        k = sample_size
        betweenness = nx.betweenness_centrality(G, k=k, seed=42)
        logger.info("Used sampled betweenness (k=%d) for performance", k)
    else:
        betweenness = nx.betweenness_centrality(G)

    closeness = nx.closeness_centrality(G)

    per_cluster = {}
    for cat in adata.obs[cluster_key].cat.categories:
        mask = adata.obs[cluster_key] == cat
        nodes = np.where(mask.values)[0]
        bet_vals = [betweenness.get(int(n), 0) for n in nodes]
        clo_vals = [closeness.get(int(n), 0) for n in nodes]
        per_cluster[str(cat)] = {
            "n_cells": int(mask.sum()),
            "mean_betweenness": float(np.mean(bet_vals)) if bet_vals else 0,
            "mean_closeness": float(np.mean(clo_vals)) if clo_vals else 0,
        }

    return {
        "analysis_type": "spatial_centrality",
        "cluster_key": cluster_key,
        "n_nodes": n_nodes,
        "per_cluster": per_cluster,
        "global_mean_betweenness": float(np.mean(list(betweenness.values()))),
        "global_mean_closeness": float(np.mean(list(closeness.values()))),
    }


# ---------------------------------------------------------------------------
# Analysis registry (dispatch table)
# ---------------------------------------------------------------------------


_ANALYSIS_REGISTRY: dict[str, callable] = {
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


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate spatial statistics figures using the SpatialClaw viz library."""
    figures: list[str] = []
    analysis_type = summary.get("analysis_type", "")
    cluster_key = summary.get("cluster_key")

    viz_subtype_map = {
        "neighborhood_enrichment": ("neighborhood", "nhood_enrichment.png"),
        "co_occurrence": ("co_occurrence", "co_occurrence.png"),
        "ripley": ("ripley", "ripley.png"),
        "moran": ("moran", "moran_ranking.png"),
        "centrality": ("centrality", "centrality_scores.png"),
    }

    if analysis_type in viz_subtype_map:
        subtype, fname = viz_subtype_map[analysis_type]
        try:
            fig = plot_spatial_stats(
                adata,
                VizParams(cluster_key=cluster_key),
                subtype=subtype,
            )
            p = save_figure(fig, output_dir, fname)
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate %s figure: %s", analysis_type, exc)
    else:
        # Generic: try Moran ranking if available
        if "moranI" in adata.uns:
            try:
                fig = plot_spatial_stats(adata, subtype="moran")
                p = save_figure(fig, output_dir, "moran_ranking.png")
                figures.append(str(p))
            except Exception as exc:
                logger.warning("Could not generate Moran ranking: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write report.md, result.json, tables, reproducibility."""

    analysis_label = summary["analysis_type"].replace("_", " ").title()
    cluster_key = summary.get("cluster_key")
    extra_meta = {"Analysis": summary["analysis_type"]}
    if cluster_key:
        extra_meta["Cluster key"] = cluster_key
    header = generate_report_header(
        title=f"Spatial Statistics — {analysis_label}",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata=extra_meta,
    )

    body_lines = ["## Summary\n", f"- **Analysis**: {analysis_label}"]
    if cluster_key:
        body_lines.append(f"- **Cluster key**: `{cluster_key}`")
    if "n_clusters" in summary:
        body_lines.append(f"- **Clusters**: {summary['n_clusters']}")
    if "categories" in summary:
        body_lines.append(f"- **Categories**: {', '.join(str(c) for c in summary['categories'])}")

    if summary["analysis_type"] == "neighborhood_enrichment":
        body_lines.extend([
            "",
            "### Neighborhood Enrichment\n",
            f"- **Mean z-score**: {summary['mean_zscore']:.3f}",
            f"- **Max z-score**: {summary['max_zscore']:.3f}",
            f"- **Min z-score**: {summary['min_zscore']:.3f}",
            "",
            "Positive z-scores indicate spatial co-localisation (enrichment); "
            "negative z-scores indicate avoidance (depletion).",
            "",
            "See `tables/enrichment_zscore.csv` for the full z-score matrix.",
        ])

    elif summary["analysis_type"] == "ripley":
        body_lines.extend([
            "",
            "### Ripley's L Function\n",
            "L(r) > r indicates spatial clustering at distance r; "
            "L(r) < r indicates regularity/dispersion.",
        ])
        if summary.get("ripley_df") is not None:
            body_lines.append(f"- Results table rows: {len(summary['ripley_df'])}")

    elif summary["analysis_type"] == "co_occurrence":
        body_lines.extend([
            "",
            "### Co-occurrence\n",
            "Pairwise cluster co-occurrence ratios across spatial distance intervals.",
        ])

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    report_path = output_dir / "report.md"
    report_path.write_text(report)
    logger.info("Wrote %s", report_path)

    # result.json — exclude large non-serialisable objects
    serialisable = {
        k: v for k, v in summary.items()
        if k not in ("zscore_df", "ripley_df", "co_occ", "interval")
    }
    checksum = (
        sha256_file(input_file)
        if input_file and Path(input_file).exists()
        else ""
    )
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=serialisable,
        data={"params": params, **serialisable},
        input_checksum=checksum,
    )

    # tables/
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    if summary["analysis_type"] == "neighborhood_enrichment":
        summary["zscore_df"].to_csv(tables_dir / "enrichment_zscore.csv")
        logger.info("Wrote %s", tables_dir / "enrichment_zscore.csv")

    if summary["analysis_type"] == "ripley" and summary.get("ripley_df") is not None:
        summary["ripley_df"].to_csv(tables_dir / "ripley_L.csv", index=False)
        logger.info("Wrote %s", tables_dir / "ripley_L.csv")

    # reproducibility/
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_statistics.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        if v is not None:
            cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines = []
    for pkg in ["squidpy", "scanpy", "anndata", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data — runs spatial-preprocess --demo via subprocess
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo to generate a preprocessed h5ad."""
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "preprocess" / "spatial_preprocess.py"

    if not preprocess_script.exists():
        raise FileNotFoundError(
            f"spatial-preprocess script not found at {preprocess_script}. "
            "Run from the SpatialClaw project root."
        )

    demo_dir = Path(tempfile.mkdtemp(prefix="spatialstats_demo_"))
    logger.info("Running spatial-preprocess --demo -> %s", demo_dir)

    result = subprocess.run(
        [sys.executable, str(preprocess_script), "--demo", "--output", str(demo_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("spatial-preprocess failed:\n%s", result.stderr)
        raise RuntimeError(f"spatial-preprocess --demo failed (exit {result.returncode})")

    processed_path = demo_dir / "processed.h5ad"
    if not processed_path.exists():
        raise FileNotFoundError(
            f"Expected processed.h5ad at {processed_path} after spatial-preprocess"
        )

    adata = sc.read_h5ad(processed_path)
    return adata, str(processed_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Statistics — comprehensive spatial analysis toolkit",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--analysis-type",
        default="neighborhood_enrichment",
        choices=list(VALID_ANALYSIS_TYPES),
        help=f"Analysis type (default: neighborhood_enrichment). Options: {', '.join(VALID_ANALYSIS_TYPES)}",
    )
    parser.add_argument(
        "--cluster-key",
        default="leiden",
        help="obs column with cluster labels (default: leiden)",
    )
    parser.add_argument(
        "--genes",
        default=None,
        help="Comma-separated gene names for gene-level analyses (e.g. 'EPCAM,VIM')",
    )
    parser.add_argument(
        "--n-top-genes",
        type=int,
        default=20,
        help="Number of top genes to analyze if --genes not specified (default: 20)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    require_spatial_coords(adata)

    analysis_type = args.analysis_type
    cluster_key = args.cluster_key

    if analysis_type in CLUSTER_ANALYSES and cluster_key not in adata.obs.columns:
        logger.error(
            "Cluster key '%s' not found in adata.obs for %s. Available: %s",
            cluster_key, analysis_type, list(adata.obs.columns),
        )
        sys.exit(1)

    gene_list = None
    if args.genes:
        gene_list = [g.strip() for g in args.genes.split(",") if g.strip()]

    params = {
        "analysis_type": analysis_type,
        "cluster_key": cluster_key,
        "genes": args.genes,
        "n_top_genes": args.n_top_genes,
    }

    run_fn = _ANALYSIS_REGISTRY.get(analysis_type)
    if run_fn is None:
        print(f"ERROR: Unknown analysis type '{analysis_type}'", file=sys.stderr)
        sys.exit(1)

    summary = run_fn(
        adata,
        cluster_key=cluster_key,
        genes=gene_list,
        n_top_genes=args.n_top_genes,
    )

    store_analysis_metadata(
        adata, SKILL_NAME, analysis_type, params=params,
    )

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    analysis_label = analysis_type.replace("_", " ")
    print(f"Spatial statistics complete: {analysis_label}")


if __name__ == "__main__":
    main()
