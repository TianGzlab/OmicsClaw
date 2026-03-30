"""Spatial statistics toolkit for OmicsClaw.

The current wrapper organizes methods by the primary data structure they consume:

- Cluster-level: cluster labels plus spatial coordinates / spatial graph
- Gene-level: gene expression plus spatial weights
- Network-level: spatial neighborhood graph, optionally aggregated by cluster
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

ANALYSIS_FAMILIES = {
    **{method: "cluster" for method in CLUSTER_ANALYSES},
    **{method: "gene" for method in GENE_ANALYSES},
    **{method: "network" for method in NETWORK_ANALYSES},
}

VALID_RIPLEY_MODES = ("F", "G", "L")
VALID_STATS_CORR_METHODS = ("fdr_bh", "bonferroni", "holm", "sidak")
VALID_CENTRALITY_SCORES = (
    "degree_centrality",
    "average_clustering",
    "closeness_centrality",
)

METHOD_PARAM_DEFAULTS = {
    "common": {
        "analysis_type": "neighborhood_enrichment",
        "cluster_key": "leiden",
        "n_top_genes": 20,
        "stats_n_neighs": 6,
        "stats_n_rings": 1,
        "stats_n_perms": 199,
        "stats_seed": 123,
    },
    "autocorr": {
        "stats_corr_method": "fdr_bh",
        "stats_two_tailed": False,
    },
    "ripley": {
        "ripley_mode": "L",
        "ripley_metric": "euclidean",
        "ripley_n_neigh": 2,
        "ripley_n_simulations": 100,
        "ripley_n_observations": 1000,
        "ripley_max_dist": None,
        "ripley_n_steps": 50,
    },
    "co_occurrence": {
        "coocc_interval": 50,
        "coocc_n_splits": None,
    },
    "local_moran": {
        "local_moran_geoda_quads": False,
    },
    "getis_ord": {
        "getis_star": True,
    },
    "spatial_centrality": {
        "centrality_score": "all",
    },
}


# ---------------------------------------------------------------------------
# Interpretation helpers
# ---------------------------------------------------------------------------


ENRICHMENT_THRESHOLDS = {
    "co_localized": 2.0,
    "segregated": -2.0,
}


def interpret_enrichment_zscore(zscore: float) -> str:
    """Return a short neighborhood-enrichment interpretation."""
    if zscore > ENRICHMENT_THRESHOLDS["co_localized"]:
        return "significantly co-localized"
    if zscore < ENRICHMENT_THRESHOLDS["segregated"]:
        return "significantly segregated"
    return "no strong spatial association"


def interpret_moran_I(value: float) -> str:
    """Return a short Moran's I interpretation."""
    if value > 0.3:
        return "strong positive spatial autocorrelation"
    if value > 0.1:
        return "moderate positive spatial autocorrelation"
    if value > -0.1:
        return "weak or random spatial structure"
    if value > -0.3:
        return "moderate negative spatial autocorrelation"
    return "strong negative spatial autocorrelation"


def interpret_geary_C(value: float) -> str:
    """Return a short Geary's C interpretation."""
    if value < 0.5:
        return "strong positive spatial autocorrelation"
    if value < 0.8:
        return "moderate positive spatial autocorrelation"
    if value < 1.2:
        return "weak or random spatial structure"
    if value < 1.5:
        return "moderate negative spatial autocorrelation"
    return "strong negative spatial autocorrelation"


def interpret_bivariate_moran(value: float) -> str:
    """Return a short bivariate Moran interpretation."""
    if value > 0.2:
        return "positive spatial cross-correlation"
    if value < -0.2:
        return "negative spatial cross-correlation"
    return "weak spatial cross-correlation"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_categorical(adata, column: str) -> None:
    """Convert an obs column to categorical dtype if needed."""
    if column not in adata.obs.columns:
        raise KeyError(f"Column '{column}' not found in adata.obs")
    if not isinstance(adata.obs[column].dtype, pd.CategoricalDtype):
        adata.obs[column] = pd.Categorical(adata.obs[column].astype(str))


def _detect_visium(adata) -> bool:
    """Detect if data likely originates from 10x Visium."""
    if "spatial" in adata.uns:
        for lib_info in adata.uns["spatial"].values():
            if isinstance(lib_info, dict) and "scalefactors" in lib_info:
                return True
    return False


def _graph_params(n_neighs: int, n_rings: int) -> dict:
    return {
        "n_neighs": int(n_neighs),
        "n_rings": int(n_rings),
    }


def _clear_spatial_graph(adata) -> None:
    """Drop previously stored spatial-neighbor artifacts before rebuilding."""
    for key in ("spatial_connectivities", "spatial_distances"):
        if key in adata.obsp:
            del adata.obsp[key]
    if "spatial_neighbors" in adata.uns:
        del adata.uns["spatial_neighbors"]


def _ensure_spatial_graph(
    adata,
    *,
    n_neighs: int = 6,
    n_rings: int = 1,
    force_rebuild: bool = False,
) -> dict:
    """Build or reuse the Squidpy spatial graph."""
    require("squidpy", feature="Spatial Graph Toolkit")
    import squidpy as sq

    request = _graph_params(n_neighs=n_neighs, n_rings=n_rings)
    graph_meta = adata.uns.get("omicsclaw_spatial_graph", {})
    has_graph = "spatial_connectivities" in adata.obsp

    if has_graph and not force_rebuild:
        return {
            "coord_type": graph_meta.get("coord_type", "existing"),
            "spatial_key": graph_meta.get("spatial_key", get_spatial_key(adata) or "spatial"),
            "reused_existing_graph": True,
            **request,
        }

    if force_rebuild and has_graph:
        _clear_spatial_graph(adata)

    spatial_key = get_spatial_key(adata) or "spatial"
    if _detect_visium(adata):
        coord_type = "grid"
        sq.gr.spatial_neighbors(
            adata,
            spatial_key=spatial_key,
            coord_type=coord_type,
            n_neighs=n_neighs,
            n_rings=n_rings,
        )
    else:
        coord_type = "generic"
        sq.gr.spatial_neighbors(
            adata,
            spatial_key=spatial_key,
            coord_type=coord_type,
            n_neighs=n_neighs,
        )

    adata.uns["omicsclaw_spatial_graph"] = {
        "coord_type": coord_type,
        "spatial_key": spatial_key,
        **request,
    }
    return {
        "coord_type": coord_type,
        "spatial_key": spatial_key,
        "reused_existing_graph": False,
        **request,
    }


def _select_genes(adata, genes: list[str] | None, *, n_top: int = 20) -> list[str]:
    """Resolve the gene list used by gene-level analyses."""
    if genes:
        cleaned = []
        seen = set()
        for gene in genes:
            gene = str(gene).strip()
            if gene and gene not in seen:
                cleaned.append(gene)
                seen.add(gene)
        valid = [gene for gene in cleaned if gene in adata.var_names]
        if not valid:
            raise ValueError(f"None of the requested genes were found: {cleaned}")
        missing = sorted(set(cleaned) - set(valid))
        if missing:
            logger.warning("Skipping genes not present in adata.var_names: %s", missing)
        return valid

    if "highly_variable" in adata.var.columns:
        hvg = adata.var_names[adata.var["highly_variable"]].tolist()
        if hvg:
            return hvg[:n_top]

    matrix = adata.X.toarray() if sparse.issparse(adata.X) else np.asarray(adata.X)
    variance = np.var(matrix, axis=0)
    top_idx = np.argsort(variance)[-n_top:][::-1]
    return [str(adata.var_names[idx]) for idx in top_idx]


def _get_gene_expression(adata, gene: str) -> np.ndarray:
    """Extract a dense 1D gene-expression vector."""
    idx = list(adata.var_names).index(gene)
    vector = adata.X[:, idx]
    if sparse.issparse(vector):
        return vector.toarray().ravel()
    return np.asarray(vector).ravel()


def _weights_from_connectivities(adata):
    """Create a row-standardized PySAL weight object from the spatial graph."""
    try:
        from libpysal.weights import WSP
    except ImportError as exc:
        raise ImportError("Spatial local statistics require libpysal.") from exc

    conn = adata.obsp["spatial_connectivities"]
    if not sparse.issparse(conn):
        conn = sparse.csr_matrix(conn)
    w = WSP(conn.tocsr()).to_W(silence_warnings=True)
    w.transform = "r"
    return w


def _preferred_adjusted_pvalue_column(df: pd.DataFrame, corr_method: str) -> str:
    """Choose the most useful adjusted p-value column from Squidpy output."""
    for base in ("pval_sim", "pval_z_sim", "pval_norm"):
        name = f"{base}_{corr_method}"
        if name in df.columns:
            return name
    for base in ("pval_sim", "pval_z_sim", "pval_norm"):
        if base in df.columns:
            return base
    return ""


def _selected_centrality_scores(score: str | None) -> list[str] | None:
    """Resolve selected Squidpy centrality scores."""
    if score is None:
        return None
    score = str(score).strip()
    if not score or score == "all":
        return None
    selected = []
    for item in score.split(","):
        item = item.strip()
        if item:
            selected.append(item)
    if not selected:
        return None
    invalid = sorted(set(selected) - set(VALID_CENTRALITY_SCORES))
    if invalid:
        raise ValueError(
            f"Invalid centrality score(s): {invalid}. Valid options: {VALID_CENTRALITY_SCORES}"
        )
    return selected


def _top_local_quadrants(q_values: np.ndarray, significant_mask: np.ndarray) -> dict[str, int]:
    """Summarize significant local Moran quadrants."""
    return {
        "high_high": int(np.sum((q_values == 1) & significant_mask)),
        "low_high": int(np.sum((q_values == 2) & significant_mask)),
        "low_low": int(np.sum((q_values == 3) & significant_mask)),
        "high_low": int(np.sum((q_values == 4) & significant_mask)),
    }


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------


def run_neighborhood_enrichment(
    adata,
    *,
    cluster_key: str = "leiden",
    n_neighs: int = 6,
    n_rings: int = 1,
    n_perms: int = 199,
    seed: int | None = 123,
    force_graph_rebuild: bool = False,
) -> dict:
    """Run Squidpy neighborhood enrichment on cluster labels."""
    require("squidpy", feature="Neighborhood enrichment")
    import squidpy as sq

    require_spatial_coords(adata)
    _ensure_categorical(adata, cluster_key)
    graph_info = _ensure_spatial_graph(
        adata,
        n_neighs=n_neighs,
        n_rings=n_rings,
        force_rebuild=force_graph_rebuild,
    )

    sq.gr.nhood_enrichment(
        adata,
        cluster_key=cluster_key,
        n_perms=n_perms,
        seed=seed,
        n_jobs=1,
        show_progress_bar=False,
    )

    uns_key = f"{cluster_key}_nhood_enrichment"
    zscore_matrix = np.asarray(adata.uns[uns_key]["zscore"])
    count_matrix = np.asarray(adata.uns[uns_key]["count"])
    categories = list(adata.obs[cluster_key].cat.categories)

    zscore_df = pd.DataFrame(zscore_matrix, index=categories, columns=categories)
    count_df = pd.DataFrame(count_matrix, index=categories, columns=categories)

    rows = []
    for i, cat_i in enumerate(categories):
        for j, cat_j in enumerate(categories):
            if i >= j:
                continue
            zscore = float(zscore_matrix[i, j])
            rows.append(
                {
                    "cluster_a": str(cat_i),
                    "cluster_b": str(cat_j),
                    "zscore": zscore,
                    "count": float(count_matrix[i, j]),
                    "interpretation": interpret_enrichment_zscore(zscore),
                }
            )
    pair_summary_df = pd.DataFrame(rows).sort_values(
        "zscore",
        key=lambda series: series.abs(),
        ascending=False,
        ignore_index=True,
    )
    significant_pairs = pair_summary_df.loc[pair_summary_df["zscore"].abs() > 2.0].head(20)

    return {
        "analysis_type": "neighborhood_enrichment",
        "analysis_family": ANALYSIS_FAMILIES["neighborhood_enrichment"],
        "cluster_key": cluster_key,
        "categories": [str(x) for x in categories],
        "n_clusters": len(categories),
        "graph_params": graph_info,
        "n_perms": int(n_perms),
        "seed": seed,
        "mean_zscore": float(np.nanmean(zscore_matrix)),
        "max_zscore": float(np.nanmax(zscore_matrix)),
        "min_zscore": float(np.nanmin(zscore_matrix)),
        "zscore_df": zscore_df,
        "count_df": count_df,
        "pair_summary_df": pair_summary_df,
        "significant_pairs": significant_pairs.to_dict(orient="records"),
    }


def run_ripley(
    adata,
    *,
    cluster_key: str = "leiden",
    ripley_mode: str = "L",
    ripley_metric: str = "euclidean",
    ripley_n_neigh: int = 2,
    ripley_n_simulations: int = 100,
    ripley_n_observations: int = 1000,
    ripley_max_dist: float | None = None,
    ripley_n_steps: int = 50,
    seed: int | None = 123,
) -> dict:
    """Run Squidpy Ripley's statistics on cluster labels."""
    require("squidpy", feature="Ripley's statistics")
    import squidpy as sq

    require_spatial_coords(adata)
    _ensure_categorical(adata, cluster_key)
    spatial_key = get_spatial_key(adata) or "spatial"

    result = sq.gr.ripley(
        adata,
        cluster_key=cluster_key,
        mode=ripley_mode,
        spatial_key=spatial_key,
        metric=ripley_metric,
        n_neigh=ripley_n_neigh,
        n_simulations=ripley_n_simulations,
        n_observations=ripley_n_observations,
        max_dist=ripley_max_dist,
        n_steps=ripley_n_steps,
        seed=seed,
        copy=True,
    )

    stat_key = f"{ripley_mode}_stat"
    stats_df = result.get(stat_key, pd.DataFrame()).copy()
    if not isinstance(stats_df, pd.DataFrame):
        stats_df = pd.DataFrame(stats_df)

    cluster_summary_df = pd.DataFrame()
    if not stats_df.empty and {cluster_key, "stats", "bins"}.issubset(stats_df.columns):
        cluster_summary_df = (
            stats_df.groupby(cluster_key, as_index=False)
            .agg(
                max_stat=("stats", "max"),
                mean_stat=("stats", "mean"),
                max_distance=("bins", "max"),
            )
            .sort_values("max_stat", ascending=False, ignore_index=True)
        )
        cluster_summary_df = cluster_summary_df.rename(columns={cluster_key: "cluster"})

    categories = [str(x) for x in adata.obs[cluster_key].cat.categories]
    return {
        "analysis_type": "ripley",
        "analysis_family": ANALYSIS_FAMILIES["ripley"],
        "cluster_key": cluster_key,
        "categories": categories,
        "n_clusters": len(categories),
        "ripley_mode": ripley_mode,
        "ripley_metric": ripley_metric,
        "ripley_n_neigh": int(ripley_n_neigh),
        "ripley_n_simulations": int(ripley_n_simulations),
        "ripley_n_observations": int(ripley_n_observations),
        "ripley_max_dist": None if ripley_max_dist is None else float(ripley_max_dist),
        "ripley_n_steps": int(ripley_n_steps),
        "seed": seed,
        "results_df": stats_df,
        "cluster_summary_df": cluster_summary_df,
    }


def run_co_occurrence(
    adata,
    *,
    cluster_key: str = "leiden",
    coocc_interval: int = 50,
    coocc_n_splits: int | None = None,
) -> dict:
    """Run Squidpy co-occurrence across distance bins."""
    require("squidpy", feature="Co-occurrence analysis")
    import squidpy as sq

    require_spatial_coords(adata)
    _ensure_categorical(adata, cluster_key)
    spatial_key = get_spatial_key(adata) or "spatial"

    occ, interval = sq.gr.co_occurrence(
        adata,
        cluster_key=cluster_key,
        spatial_key=spatial_key,
        interval=coocc_interval,
        n_splits=coocc_n_splits,
        n_jobs=1,
        show_progress_bar=False,
        copy=True,
    )

    categories = list(adata.obs[cluster_key].cat.categories)
    rows = []
    occ = np.asarray(occ)
    interval = np.asarray(interval)
    n_bins = occ.shape[2] if occ.ndim == 3 else 0
    for i, cat_i in enumerate(categories):
        for j, cat_j in enumerate(categories):
            if occ.ndim != 3:
                continue
            values = occ[i, j, :]
            for bin_idx in range(n_bins):
                rows.append(
                    {
                        "cluster_a": str(cat_i),
                        "cluster_b": str(cat_j),
                        "bin_index": int(bin_idx),
                        "distance_start": float(interval[bin_idx]),
                        "distance_end": float(interval[bin_idx + 1]),
                        "co_occurrence": float(values[bin_idx]),
                    }
                )
    results_df = pd.DataFrame(rows)
    pair_summary_df = pd.DataFrame()
    if not results_df.empty:
        pair_summary_df = (
            results_df.groupby(["cluster_a", "cluster_b"], as_index=False)
            .agg(
                max_co_occurrence=("co_occurrence", "max"),
                mean_co_occurrence=("co_occurrence", "mean"),
            )
            .sort_values("max_co_occurrence", ascending=False, ignore_index=True)
        )

    return {
        "analysis_type": "co_occurrence",
        "analysis_family": ANALYSIS_FAMILIES["co_occurrence"],
        "cluster_key": cluster_key,
        "categories": [str(x) for x in categories],
        "n_clusters": len(categories),
        "coocc_interval": int(coocc_interval),
        "coocc_n_splits": coocc_n_splits,
        "results_df": results_df,
        "pair_summary_df": pair_summary_df,
    }


def run_moran(
    adata,
    *,
    genes: list[str] | None = None,
    n_top_genes: int = 20,
    n_neighs: int = 6,
    n_rings: int = 1,
    n_perms: int = 199,
    corr_method: str = "fdr_bh",
    two_tailed: bool = False,
    seed: int | None = 123,
    force_graph_rebuild: bool = False,
) -> dict:
    """Run global Moran's I using Squidpy."""
    require("squidpy", feature="Global Moran's I")
    import squidpy as sq

    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    graph_info = _ensure_spatial_graph(
        adata,
        n_neighs=n_neighs,
        n_rings=n_rings,
        force_rebuild=force_graph_rebuild,
    )

    sq.gr.spatial_autocorr(
        adata,
        mode="moran",
        genes=gene_list,
        n_perms=n_perms,
        two_tailed=two_tailed,
        corr_method=corr_method,
        seed=seed,
        n_jobs=1,
        show_progress_bar=False,
    )

    df = adata.uns["moranI"].copy()
    df["gene"] = df.index.astype(str)
    df["interpretation"] = df["I"].astype(float).map(interpret_moran_I)
    df = df.sort_values("I", ascending=False, ignore_index=True)
    pvalue_col = _preferred_adjusted_pvalue_column(df, corr_method)
    if pvalue_col:
        df["is_significant"] = pd.to_numeric(df[pvalue_col], errors="coerce") < 0.05
    else:
        df["is_significant"] = False

    return {
        "analysis_type": "moran",
        "analysis_family": ANALYSIS_FAMILIES["moran"],
        "selected_genes": gene_list,
        "n_genes": len(gene_list),
        "graph_params": graph_info,
        "n_perms": int(n_perms),
        "corr_method": corr_method,
        "two_tailed": bool(two_tailed),
        "seed": seed,
        "mean_I": float(pd.to_numeric(df["I"], errors="coerce").mean()),
        "pvalue_column": pvalue_col,
        "n_significant": int(df["is_significant"].sum()),
        "results_df": df,
    }


def run_geary(
    adata,
    *,
    genes: list[str] | None = None,
    n_top_genes: int = 20,
    n_neighs: int = 6,
    n_rings: int = 1,
    n_perms: int = 199,
    corr_method: str = "fdr_bh",
    two_tailed: bool = False,
    seed: int | None = 123,
    force_graph_rebuild: bool = False,
) -> dict:
    """Run global Geary's C using Squidpy."""
    require("squidpy", feature="Global Geary's C")
    import squidpy as sq

    require_spatial_coords(adata)
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)
    graph_info = _ensure_spatial_graph(
        adata,
        n_neighs=n_neighs,
        n_rings=n_rings,
        force_rebuild=force_graph_rebuild,
    )

    sq.gr.spatial_autocorr(
        adata,
        mode="geary",
        genes=gene_list,
        n_perms=n_perms,
        two_tailed=two_tailed,
        corr_method=corr_method,
        seed=seed,
        n_jobs=1,
        show_progress_bar=False,
    )

    df = adata.uns["gearyC"].copy()
    df["gene"] = df.index.astype(str)
    df["interpretation"] = df["C"].astype(float).map(interpret_geary_C)
    df = df.sort_values("C", ascending=True, ignore_index=True)
    pvalue_col = _preferred_adjusted_pvalue_column(df, corr_method)
    if pvalue_col:
        df["is_significant"] = pd.to_numeric(df[pvalue_col], errors="coerce") < 0.05
    else:
        df["is_significant"] = False

    return {
        "analysis_type": "geary",
        "analysis_family": ANALYSIS_FAMILIES["geary"],
        "selected_genes": gene_list,
        "n_genes": len(gene_list),
        "graph_params": graph_info,
        "n_perms": int(n_perms),
        "corr_method": corr_method,
        "two_tailed": bool(two_tailed),
        "seed": seed,
        "mean_C": float(pd.to_numeric(df["C"], errors="coerce").mean()),
        "pvalue_column": pvalue_col,
        "n_significant": int(df["is_significant"].sum()),
        "results_df": df,
    }


def run_local_moran(
    adata,
    *,
    genes: list[str] | None = None,
    n_top_genes: int = 10,
    n_neighs: int = 6,
    n_rings: int = 1,
    n_perms: int = 199,
    seed: int | None = 123,
    local_moran_geoda_quads: bool = False,
    force_graph_rebuild: bool = False,
) -> dict:
    """Run local Moran's I using PySAL."""
    require_spatial_coords(adata)
    graph_info = _ensure_spatial_graph(
        adata,
        n_neighs=n_neighs,
        n_rings=n_rings,
        force_rebuild=force_graph_rebuild,
    )
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)

    try:
        from esda.moran import Moran_Local
    except ImportError as exc:
        raise ImportError("Local Moran's I requires esda.") from exc

    w = _weights_from_connectivities(adata)
    summary_rows = []
    spot_frames = []
    for gene in gene_list:
        expr = np.asarray(_get_gene_expression(adata, gene), dtype=float)
        lm = Moran_Local(
            expr,
            w,
            permutations=n_perms,
            geoda_quads=local_moran_geoda_quads,
            n_jobs=1,
            seed=seed,
        )
        pvals = np.asarray(lm.p_sim)
        local_i = np.asarray(lm.Is)
        quadrants = np.asarray(lm.q)
        significant = pvals < 0.05

        adata.obs[f"local_moran_{gene}"] = local_i
        adata.obs[f"local_moran_pval_{gene}"] = pvals
        adata.obs[f"local_moran_q_{gene}"] = quadrants.astype(int)

        quadrant_counts = _top_local_quadrants(quadrants, significant)
        summary_rows.append(
            {
                "gene": gene,
                "mean_local_I": float(np.nanmean(local_i)),
                "n_significant_spots": int(np.sum(significant)),
                **quadrant_counts,
            }
        )
        spot_frames.append(
            pd.DataFrame(
                {
                    "obs_name": adata.obs_names.astype(str),
                    "gene": gene,
                    "local_I": local_i,
                    "pvalue": pvals,
                    "quadrant": quadrants.astype(int),
                    "is_significant": significant.astype(bool),
                }
            )
        )

    results_df = pd.DataFrame(summary_rows).sort_values(
        ["n_significant_spots", "mean_local_I"],
        ascending=[False, False],
        ignore_index=True,
    )
    spot_df = pd.concat(spot_frames, ignore_index=True) if spot_frames else pd.DataFrame()
    return {
        "analysis_type": "local_moran",
        "analysis_family": ANALYSIS_FAMILIES["local_moran"],
        "selected_genes": gene_list,
        "n_genes": len(gene_list),
        "graph_params": graph_info,
        "n_perms": int(n_perms),
        "seed": seed,
        "local_moran_geoda_quads": bool(local_moran_geoda_quads),
        "results_df": results_df,
        "spot_df": spot_df,
    }


def run_getis_ord(
    adata,
    *,
    genes: list[str] | None = None,
    n_top_genes: int = 10,
    n_neighs: int = 6,
    n_rings: int = 1,
    n_perms: int = 199,
    seed: int | None = 123,
    getis_star: bool = True,
    force_graph_rebuild: bool = False,
) -> dict:
    """Run Getis-Ord Gi* local hotspot analysis using PySAL."""
    require_spatial_coords(adata)
    graph_info = _ensure_spatial_graph(
        adata,
        n_neighs=n_neighs,
        n_rings=n_rings,
        force_rebuild=force_graph_rebuild,
    )
    gene_list = _select_genes(adata, genes, n_top=n_top_genes)

    try:
        from esda.getisord import G_Local
    except ImportError as exc:
        raise ImportError("Getis-Ord Gi* requires esda.") from exc

    w = _weights_from_connectivities(adata)
    summary_rows = []
    spot_frames = []
    for gene in gene_list:
        expr = np.asarray(_get_gene_expression(adata, gene), dtype=float)
        gl = G_Local(
            expr,
            w,
            transform="R",
            permutations=n_perms,
            star=getis_star,
            n_jobs=1,
            seed=seed,
        )
        zscores = np.asarray(gl.Zs)
        pvals = np.asarray(gl.p_sim)
        significant = pvals < 0.05
        hotspots = significant & (zscores > 0)
        coldspots = significant & (zscores < 0)

        adata.obs[f"getis_ord_{gene}"] = zscores
        adata.obs[f"getis_ord_pval_{gene}"] = pvals

        summary_rows.append(
            {
                "gene": gene,
                "mean_gi_z": float(np.nanmean(zscores)),
                "n_hotspots": int(np.sum(hotspots)),
                "n_coldspots": int(np.sum(coldspots)),
            }
        )
        spot_frames.append(
            pd.DataFrame(
                {
                    "obs_name": adata.obs_names.astype(str),
                    "gene": gene,
                    "gi_zscore": zscores,
                    "pvalue": pvals,
                    "is_hotspot": hotspots.astype(bool),
                    "is_coldspot": coldspots.astype(bool),
                }
            )
        )

    results_df = pd.DataFrame(summary_rows).sort_values(
        ["n_hotspots", "n_coldspots", "mean_gi_z"],
        ascending=[False, False, False],
        ignore_index=True,
    )
    spot_df = pd.concat(spot_frames, ignore_index=True) if spot_frames else pd.DataFrame()
    return {
        "analysis_type": "getis_ord",
        "analysis_family": ANALYSIS_FAMILIES["getis_ord"],
        "selected_genes": gene_list,
        "n_genes": len(gene_list),
        "graph_params": graph_info,
        "n_perms": int(n_perms),
        "seed": seed,
        "getis_star": bool(getis_star),
        "results_df": results_df,
        "spot_df": spot_df,
    }


def run_bivariate_moran(
    adata,
    *,
    genes: list[str] | None = None,
    n_neighs: int = 6,
    n_rings: int = 1,
    n_perms: int = 199,
    force_graph_rebuild: bool = False,
) -> dict:
    """Run bivariate Moran's I between exactly two genes."""
    require_spatial_coords(adata)
    if not genes or len(genes) != 2:
        raise ValueError("bivariate_moran requires exactly two genes via --genes geneA,geneB")

    try:
        from esda.moran import Moran_BV
    except ImportError as exc:
        raise ImportError("Bivariate Moran requires esda.") from exc

    graph_info = _ensure_spatial_graph(
        adata,
        n_neighs=n_neighs,
        n_rings=n_rings,
        force_rebuild=force_graph_rebuild,
    )
    gene_list = _select_genes(adata, genes, n_top=2)
    if len(gene_list) != 2:
        raise ValueError(f"bivariate_moran requires two valid genes, got {gene_list}")

    w = _weights_from_connectivities(adata)
    gene_a, gene_b = gene_list
    x = np.asarray(_get_gene_expression(adata, gene_a), dtype=float)
    y = np.asarray(_get_gene_expression(adata, gene_b), dtype=float)
    moran_bv = Moran_BV(x, y, w, permutations=n_perms)

    return {
        "analysis_type": "bivariate_moran",
        "analysis_family": ANALYSIS_FAMILIES["bivariate_moran"],
        "selected_genes": gene_list,
        "gene_a": gene_a,
        "gene_b": gene_b,
        "graph_params": graph_info,
        "n_perms": int(n_perms),
        "bivariate_I": float(moran_bv.I),
        "pvalue": float(moran_bv.p_sim),
        "zscore": float(moran_bv.z_sim),
        "interpretation": interpret_bivariate_moran(float(moran_bv.I)),
    }


def run_network_properties(
    adata,
    *,
    cluster_key: str = "leiden",
    n_neighs: int = 6,
    n_rings: int = 1,
    force_graph_rebuild: bool = False,
) -> dict:
    """Summarize the spatial-neighborhood graph topology."""
    require_spatial_coords(adata)
    graph_info = _ensure_spatial_graph(
        adata,
        n_neighs=n_neighs,
        n_rings=n_rings,
        force_rebuild=force_graph_rebuild,
    )

    try:
        import networkx as nx
    except ImportError as exc:
        raise ImportError("Network properties require networkx.") from exc

    conn = adata.obsp["spatial_connectivities"]
    graph = (
        nx.from_scipy_sparse_array(conn)
        if sparse.issparse(conn)
        else nx.from_numpy_array(np.asarray(conn))
    )
    degrees = np.asarray([degree for _, degree in graph.degree()], dtype=float)
    clustering = np.asarray(list(nx.clustering(graph).values()), dtype=float)
    component_sizes = sorted((len(component) for component in nx.connected_components(graph)), reverse=True)

    results_df = pd.DataFrame(
        [
            {
                "n_nodes": int(graph.number_of_nodes()),
                "n_edges": int(graph.number_of_edges()),
                "mean_degree": float(np.mean(degrees)),
                "std_degree": float(np.std(degrees)),
                "mean_clustering_coeff": float(np.mean(clustering)),
                "density": float(nx.density(graph)),
                "n_connected_components": int(len(component_sizes)),
                "largest_component_size": int(component_sizes[0]) if component_sizes else 0,
            }
        ]
    )

    per_cluster_df = pd.DataFrame()
    if cluster_key in adata.obs.columns:
        _ensure_categorical(adata, cluster_key)
        rows = []
        for category in adata.obs[cluster_key].cat.categories:
            mask = (adata.obs[cluster_key] == category).to_numpy()
            cluster_degrees = degrees[mask]
            rows.append(
                {
                    "cluster": str(category),
                    "n_cells": int(mask.sum()),
                    "mean_degree": float(np.mean(cluster_degrees)) if cluster_degrees.size else 0.0,
                    "std_degree": float(np.std(cluster_degrees)) if cluster_degrees.size else 0.0,
                }
            )
        per_cluster_df = pd.DataFrame(rows).sort_values("mean_degree", ascending=False, ignore_index=True)

    return {
        "analysis_type": "network_properties",
        "analysis_family": ANALYSIS_FAMILIES["network_properties"],
        "cluster_key": cluster_key if cluster_key in adata.obs.columns else None,
        "graph_params": graph_info,
        "results_df": results_df,
        "per_cluster_df": per_cluster_df,
    }


def run_spatial_centrality(
    adata,
    *,
    cluster_key: str = "leiden",
    n_neighs: int = 6,
    n_rings: int = 1,
    centrality_score: str | None = "all",
    force_graph_rebuild: bool = False,
) -> dict:
    """Run Squidpy cluster-level graph centrality scores."""
    require("squidpy", feature="Spatial centrality")
    import squidpy as sq

    require_spatial_coords(adata)
    _ensure_categorical(adata, cluster_key)
    graph_info = _ensure_spatial_graph(
        adata,
        n_neighs=n_neighs,
        n_rings=n_rings,
        force_rebuild=force_graph_rebuild,
    )

    selected_scores = _selected_centrality_scores(centrality_score)
    if selected_scores is None:
        df = sq.gr.centrality_scores(
            adata,
            cluster_key=cluster_key,
            score=None,
            n_jobs=1,
            show_progress_bar=False,
            copy=True,
        )
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
    else:
        frames = []
        for score_name in selected_scores:
            score_df = sq.gr.centrality_scores(
                adata,
                cluster_key=cluster_key,
                score=score_name,
                n_jobs=1,
                show_progress_bar=False,
                copy=True,
            )
            if not isinstance(score_df, pd.DataFrame):
                score_df = pd.DataFrame(score_df)
            frames.append(score_df)
        df = pd.concat(frames, axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
    adata.uns[f"{cluster_key}_centrality_scores"] = df.copy()

    results_df = df.copy().reset_index().rename(columns={"index": "cluster"})
    top_clusters = {}
    for column in results_df.columns:
        if column == "cluster":
            continue
        idx = results_df[column].astype(float).idxmax()
        top_clusters[column] = str(results_df.loc[idx, "cluster"])

    return {
        "analysis_type": "spatial_centrality",
        "analysis_family": ANALYSIS_FAMILIES["spatial_centrality"],
        "cluster_key": cluster_key,
        "graph_params": graph_info,
        "selected_scores": selected_scores or list(df.columns),
        "n_clusters": int(len(results_df)),
        "top_clusters": top_clusters,
        "results_df": results_df,
    }


def run_statistics(adata, *, analysis_type: str, **kwargs) -> dict:
    """Dispatch a spatial-statistics analysis by name."""
    if analysis_type not in ANALYSIS_REGISTRY:
        raise ValueError(f"Unknown analysis_type '{analysis_type}'")
    return ANALYSIS_REGISTRY[analysis_type](adata, **kwargs)


ANALYSIS_REGISTRY: dict[str, Callable[..., dict]] = {
    "neighborhood_enrichment": run_neighborhood_enrichment,
    "ripley": run_ripley,
    "co_occurrence": run_co_occurrence,
    "moran": run_moran,
    "geary": run_geary,
    "local_moran": run_local_moran,
    "getis_ord": run_getis_ord,
    "bivariate_moran": run_bivariate_moran,
    "network_properties": run_network_properties,
    "spatial_centrality": run_spatial_centrality,
}
