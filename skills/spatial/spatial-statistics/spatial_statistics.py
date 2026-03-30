#!/usr/bin/env python3
"""Spatial Statistics — method-aware spatial pattern analysis."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.statistics import (
    ANALYSIS_REGISTRY,
    CLUSTER_ANALYSES,
    METHOD_PARAM_DEFAULTS,
    VALID_ANALYSIS_TYPES,
    VALID_CENTRALITY_SCORES,
    VALID_RIPLEY_MODES,
    VALID_STATS_CORR_METHODS,
    run_statistics,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_features,
    plot_spatial_stats,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-statistics"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-statistics/spatial_statistics.py"
BOOL_NEGATIVE_FLAGS = {
    "getis_star": "--no-getis-star",
}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _parse_genes_arg(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    genes = [item.strip() for item in raw.split(",") if item.strip()]
    return genes or None


def _requires_cluster_key(analysis_type: str) -> bool:
    return analysis_type in CLUSTER_ANALYSES or analysis_type == "spatial_centrality"


def _expr_vector(adata, gene: str) -> np.ndarray:
    idx = list(adata.var_names).index(gene)
    vector = adata.X[:, idx]
    if hasattr(vector, "toarray"):
        return vector.toarray().ravel()
    return np.asarray(vector).ravel()


def _json_safe_summary(summary: dict) -> dict:
    excluded = {
        "zscore_df",
        "count_df",
        "pair_summary_df",
        "cluster_summary_df",
        "results_df",
        "spot_df",
        "per_cluster_df",
    }
    out = {}
    for key, value in summary.items():
        if key in excluded:
            continue
        if isinstance(value, (pd.DataFrame, pd.Series, np.ndarray)):
            continue
        out[key] = value
    return out


def _format_value(value) -> str:
    if pd.isna(value):
        return "NA"
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.4g}"
    return str(value)


def _markdown_table(df: pd.DataFrame, columns: list[str], headers: list[str] | None = None, limit: int = 10) -> list[str]:
    if df.empty:
        return ["_No rows available._"]
    headers = headers or columns
    rows = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in df[columns].head(limit).iterrows():
        rows.append("| " + " | ".join(_format_value(row[col]) for col in columns) + " |")
    return rows


def _interpretation_notes(summary: dict) -> list[str]:
    analysis_type = summary["analysis_type"]
    if analysis_type == "neighborhood_enrichment":
        return [
            "- Positive z-scores indicate cluster pairs that appear as neighbors more often than expected by permutation.",
            "- Negative z-scores indicate spatial segregation rather than transcriptional antagonism.",
        ]
    if analysis_type == "ripley":
        return [
            "- Ripley's summary depends on distance scale; interpret cluster tendency across the full curve rather than at one radius only.",
            "- `L(r)` above the CSR expectation indicates clustering at that scale, while lower values suggest regular spacing.",
        ]
    if analysis_type == "co_occurrence":
        return [
            "- Co-occurrence summarizes pairwise proximity across distance bins and is descriptive unless paired with an external null model.",
            "- Strong self-pair curves usually reflect cluster compactness, not automatically biological interaction.",
        ]
    if analysis_type in {"moran", "geary"}:
        return [
            "- Global spatial autocorrelation reflects tissue-scale structure and should be interpreted together with adjusted p-values.",
            "- Moran's I and Geary's C answer the same question with different geometry; do not present them as independent validation if run on the same graph.",
        ]
    if analysis_type == "local_moran":
        return [
            "- Local Moran hotspot counts depend on the chosen graph and permutation count.",
            "- Significant high-high and low-low regions are stronger evidence of local structure than isolated quadrant labels without permutation support.",
        ]
    if analysis_type == "getis_ord":
        return [
            "- Getis-Ord Gi* highlights local hot and cold spots for one gene at a time.",
            "- Hotspot counts should be framed as spatial concentration patterns, not as a standalone differential-expression test.",
        ]
    if analysis_type == "bivariate_moran":
        return [
            "- Bivariate Moran tests whether one gene is high where neighboring spots of another gene are high or low.",
            "- This is spatial cross-correlation, not a cell type interaction model.",
        ]
    if analysis_type == "network_properties":
        return [
            "- Graph density and degree summarize the chosen neighborhood construction, so they should always be reported with the graph parameters.",
            "- A dense graph is not automatically biologically better; it may simply reflect looser spatial-neighbor settings.",
        ]
    return [
        "- Centrality scores summarize cluster placement inside the chosen spatial graph rather than within expression manifolds.",
        "- `degree_centrality`, `average_clustering`, and `closeness_centrality` should be interpreted comparatively across the same graph build only.",
    ]


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _prepare_statistics_plot_state(adata) -> str | None:
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()
    return get_spatial_key(adata)


def _build_analysis_summary_table(summary: dict) -> pd.DataFrame:
    rows = [
        {"metric": "analysis_type", "value": summary.get("analysis_type")},
        {"metric": "analysis_family", "value": summary.get("analysis_family")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_features", "value": summary.get("n_features")},
        {"metric": "cluster_key", "value": summary.get("cluster_key")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "n_clusters", "value": summary.get("n_clusters")},
        {"metric": "n_significant", "value": summary.get("n_significant")},
    ]
    graph_params = summary.get("graph_params", {})
    for key, value in graph_params.items():
        rows.append({"metric": f"graph_{key}", "value": value})
    for key in (
        "n_perms",
        "corr_method",
        "two_tailed",
        "ripley_mode",
        "ripley_metric",
        "ripley_n_simulations",
        "ripley_n_observations",
        "ripley_n_steps",
        "coocc_interval",
        "coocc_n_splits",
        "local_moran_geoda_quads",
        "getis_star",
        "gene_a",
        "gene_b",
        "bivariate_I",
        "pvalue",
        "zscore",
    ):
        if key in summary:
            rows.append({"metric": key, "value": summary.get(key)})
    return pd.DataFrame(rows)


def _top_results_table(summary: dict, n_top: int = 12) -> pd.DataFrame:
    analysis_type = summary["analysis_type"]

    if analysis_type == "neighborhood_enrichment":
        return summary.get("pair_summary_df", pd.DataFrame()).head(n_top).copy()
    if analysis_type == "ripley":
        return summary.get("cluster_summary_df", pd.DataFrame()).head(n_top).copy()
    if analysis_type == "co_occurrence":
        return summary.get("pair_summary_df", pd.DataFrame()).head(n_top).copy()
    if analysis_type in {"moran", "geary", "local_moran", "getis_ord", "spatial_centrality"}:
        return summary.get("results_df", pd.DataFrame()).head(n_top).copy()
    if analysis_type == "network_properties":
        return summary.get("per_cluster_df", pd.DataFrame()).head(n_top).copy()
    if analysis_type == "bivariate_moran":
        return pd.DataFrame(
            [
                {
                    "gene_a": summary.get("gene_a"),
                    "gene_b": summary.get("gene_b"),
                    "bivariate_I": summary.get("bivariate_I"),
                    "pvalue": summary.get("pvalue"),
                    "zscore": summary.get("zscore"),
                }
            ]
        )
    return pd.DataFrame()


def _build_spot_statistics_table(adata, summary: dict, *, spatial_key: str | None) -> pd.DataFrame:
    spot_df = summary.get("spot_df", pd.DataFrame()).copy()
    if spot_df.empty or spatial_key is None or spatial_key not in adata.obsm:
        return spot_df

    coords = np.asarray(adata.obsm[spatial_key])
    if coords.shape[1] < 2:
        return spot_df

    coord_df = pd.DataFrame(
        {
            "obs_name": adata.obs_names.astype(str),
            "x": coords[:, 0],
            "y": coords[:, 1],
        }
    )
    if "obs_name" in spot_df.columns:
        return spot_df.merge(coord_df, on="obs_name", how="left")
    return spot_df


def _prepare_statistics_gallery_context(adata, summary: dict) -> dict:
    spatial_key = _prepare_statistics_plot_state(adata)
    analysis_summary_df = _build_analysis_summary_table(summary)
    top_results_df = _top_results_table(summary)
    spot_statistics_df = _build_spot_statistics_table(adata, summary, spatial_key=spatial_key)

    zscore_long_df = pd.DataFrame()
    zscore_df = summary.get("zscore_df", pd.DataFrame())
    if not zscore_df.empty:
        zscore_long_df = (
            zscore_df.reset_index(names="cluster_a")
            .melt(id_vars="cluster_a", var_name="cluster_b", value_name="zscore")
        )

    local_feature_columns: list[str] = []
    analysis_type = summary["analysis_type"]
    if analysis_type in {"local_moran", "getis_ord"}:
        for gene in summary.get("selected_genes", [])[:4]:
            column = f"{analysis_type}_{gene}"
            if column in adata.obs.columns:
                local_feature_columns.append(column)

    return {
        "analysis_type": analysis_type,
        "cluster_key": summary.get("cluster_key"),
        "spatial_key": spatial_key,
        "analysis_summary_df": analysis_summary_df,
        "top_results_df": top_results_df,
        "results_df": summary.get("results_df", pd.DataFrame()),
        "pair_summary_df": summary.get("pair_summary_df", pd.DataFrame()),
        "cluster_summary_df": summary.get("cluster_summary_df", pd.DataFrame()),
        "per_cluster_df": summary.get("per_cluster_df", pd.DataFrame()),
        "spot_statistics_df": spot_statistics_df,
        "zscore_long_df": zscore_long_df,
        "local_feature_columns": local_feature_columns,
    }


def _build_statistics_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    analysis_type = summary["analysis_type"]
    cluster_key = context.get("cluster_key")
    plots: list[PlotSpec] = []

    if analysis_type == "neighborhood_enrichment":
        plots.append(
            PlotSpec(
                plot_id="stats_neighborhood_overview",
                role="overview",
                renderer="spatial_stats_builtin",
                filename="neighborhood_enrichment_heatmap.png",
                title="Neighborhood Enrichment Z-scores",
                description="Canonical neighborhood-enrichment heatmap from the shared spatial-stats renderer.",
                params={"subtype": "neighborhood", "cluster_key": cluster_key, "colormap": "RdBu_r"},
                required_uns=[f"{cluster_key}_nhood_enrichment"] if cluster_key else [],
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_neighborhood_pairs",
                role="supporting",
                renderer="summary_barplot",
                filename="neighborhood_top_pairs.png",
                title="Strongest Neighborhood Pairs",
                description="Top cluster-pair enrichments by absolute z-score.",
                params={
                    "data_key": "pair_summary_df",
                    "label_cols": ["cluster_a", "cluster_b"],
                    "value_col": "zscore",
                    "top_n": 12,
                    "sort_abs": True,
                    "xlabel": "Z-score",
                    "color": "#3182bd",
                },
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_neighborhood_distribution",
                role="uncertainty",
                renderer="value_histogram",
                filename="neighborhood_zscore_distribution.png",
                title="Neighborhood Z-score Distribution",
                description="Distribution of pairwise neighborhood-enrichment z-scores.",
                params={
                    "data_key": "zscore_long_df",
                    "value_col": "zscore",
                    "xlabel": "Z-score",
                    "color": "#756bb1",
                },
            )
        )

    elif analysis_type == "ripley":
        plots.append(
            PlotSpec(
                plot_id="stats_ripley_overview",
                role="overview",
                renderer="ripley_curves",
                filename="ripley_curves.png",
                title="Ripley Curves By Cluster",
                description="Ripley curves rendered from the exported cluster-by-distance statistics.",
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_ripley_cluster_summary",
                role="supporting",
                renderer="summary_barplot",
                filename="ripley_cluster_max_stat.png",
                title="Ripley Max Statistic By Cluster",
                description="Maximum cluster-specific Ripley summary statistic.",
                params={
                    "data_key": "cluster_summary_df",
                    "label_col": "cluster",
                    "value_col": "max_stat",
                    "top_n": 12,
                    "xlabel": "Max statistic",
                    "color": "#d95f02",
                },
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_ripley_distribution",
                role="uncertainty",
                renderer="value_histogram",
                filename="ripley_stat_distribution.png",
                title="Ripley Statistic Distribution",
                description="Distribution of Ripley statistics across distance bins.",
                params={
                    "data_key": "results_df",
                    "value_col": "stats",
                    "xlabel": "Ripley statistic",
                    "color": "#756bb1",
                },
            )
        )

    elif analysis_type == "co_occurrence":
        plots.append(
            PlotSpec(
                plot_id="stats_coocc_overview",
                role="overview",
                renderer="cooccurrence_curves",
                filename="co_occurrence_curves.png",
                title="Top Co-occurrence Curves",
                description="Top co-occurrence curves rendered from the exported pair-by-distance table.",
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_coocc_pairs",
                role="supporting",
                renderer="summary_barplot",
                filename="co_occurrence_top_pairs.png",
                title="Strongest Co-occurrence Pairs",
                description="Cluster pairs ranked by their maximum co-occurrence value.",
                params={
                    "data_key": "pair_summary_df",
                    "label_cols": ["cluster_a", "cluster_b"],
                    "value_col": "max_co_occurrence",
                    "top_n": 12,
                    "xlabel": "Max co-occurrence",
                    "color": "#3182bd",
                },
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_coocc_distribution",
                role="uncertainty",
                renderer="value_histogram",
                filename="co_occurrence_distribution.png",
                title="Co-occurrence Distribution",
                description="Distribution of co-occurrence values across cluster pairs and bins.",
                params={
                    "data_key": "results_df",
                    "value_col": "co_occurrence",
                    "xlabel": "Co-occurrence",
                    "color": "#756bb1",
                },
            )
        )

    elif analysis_type == "moran":
        plots.append(
            PlotSpec(
                plot_id="stats_moran_overview",
                role="overview",
                renderer="spatial_stats_builtin",
                filename="moran_ranking.png",
                title="Top Moran Genes",
                description="Shared Moran ranking visualization from the spatial-stats renderer.",
                params={"subtype": "moran", "show_colorbar": True},
                required_uns=["moranI"],
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_moran_diagnostic",
                role="diagnostic",
                renderer="autocorr_scatter",
                filename="moran_score_vs_significance.png",
                title="Moran Score vs Significance",
                description="Global Moran score plotted against adjusted significance.",
                params={"score_col": "I"},
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_moran_uncertainty",
                role="uncertainty",
                renderer="autocorr_pvalue_histogram",
                filename="moran_pvalue_distribution.png",
                title="Moran Adjusted p-value Distribution",
                description="Distribution of Moran adjusted p-values or fallback p-values.",
            )
        )

    elif analysis_type == "geary":
        plots.append(
            PlotSpec(
                plot_id="stats_geary_overview",
                role="overview",
                renderer="autocorr_ranking",
                filename="geary_ranking.png",
                title="Top Geary Genes",
                description="Top genes ranked by Geary's C.",
                params={"score_col": "C", "ascending": True, "color": "#3182bd"},
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_geary_diagnostic",
                role="diagnostic",
                renderer="autocorr_scatter",
                filename="geary_score_vs_significance.png",
                title="Geary Score vs Significance",
                description="Geary's C plotted against adjusted significance.",
                params={"score_col": "C"},
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_geary_uncertainty",
                role="uncertainty",
                renderer="autocorr_pvalue_histogram",
                filename="geary_pvalue_distribution.png",
                title="Geary Adjusted p-value Distribution",
                description="Distribution of Geary adjusted p-values or fallback p-values.",
            )
        )

    elif analysis_type in {"local_moran", "getis_ord"}:
        if context.get("local_feature_columns"):
            plots.append(
                PlotSpec(
                    plot_id=f"stats_{analysis_type}_overview",
                    role="overview",
                    renderer="feature_map",
                    filename=f"{analysis_type}_spatial.png",
                    title="Local Spatial Statistics",
                    description="Shared feature-map rendering of local spatial statistic columns.",
                    params={
                        "feature": context.get("local_feature_columns", []),
                        "basis": "spatial",
                        "colormap": "coolwarm",
                        "show_colorbar": True,
                        "show_axes": False,
                        "figure_size": (min(16, max(6, len(context.get("local_feature_columns", [])) * 3.8)), 4.5),
                    },
                    required_obsm=["spatial"],
                )
            )
        value_col = "n_significant_spots" if analysis_type == "local_moran" else "n_hotspots"
        xlabel = "Significant spots" if analysis_type == "local_moran" else "Hotspots"
        plots.append(
            PlotSpec(
                plot_id=f"stats_{analysis_type}_summary",
                role="supporting",
                renderer="summary_barplot",
                filename=f"{analysis_type}_summary_barplot.png",
                title=f"{analysis_type.replace('_', ' ').title()} Summary",
                description="Gene-level summary of local hotspots across selected genes.",
                params={
                    "data_key": "results_df",
                    "label_col": "gene",
                    "value_col": value_col,
                    "top_n": 12,
                    "xlabel": xlabel,
                    "color": "#d95f02",
                },
            )
        )
        plots.append(
            PlotSpec(
                plot_id=f"stats_{analysis_type}_uncertainty",
                role="uncertainty",
                renderer="value_histogram",
                filename=f"{analysis_type}_pvalue_distribution.png",
                title=f"{analysis_type.replace('_', ' ').title()} p-value Distribution",
                description="Distribution of local-statistic permutation p-values across spots.",
                params={
                    "data_key": "spot_statistics_df",
                    "value_col": "pvalue",
                    "xlabel": "Permutation p-value",
                    "color": "#756bb1",
                },
            )
        )

    elif analysis_type == "bivariate_moran":
        plots.append(
            PlotSpec(
                plot_id="stats_bivariate_overview",
                role="overview",
                renderer="bivariate_scatter",
                filename="bivariate_moran_scatter.png",
                title="Bivariate Moran Scatter",
                description="Expression of gene A against the spatial lag of gene B.",
            )
        )
        if summary.get("gene_a") in adata.var_names and summary.get("gene_b") in adata.var_names and "spatial" in adata.obsm:
            plots.append(
                PlotSpec(
                    plot_id="stats_bivariate_supporting",
                    role="supporting",
                    renderer="feature_map",
                    filename="bivariate_moran_spatial.png",
                    title="Bivariate Moran Spatial Context",
                    description="Spatial expression context for the two genes used in bivariate Moran's I.",
                    params={
                        "feature": [summary.get("gene_a"), summary.get("gene_b")],
                        "basis": "spatial",
                        "colormap": "magma",
                        "show_colorbar": True,
                        "show_axes": False,
                        "figure_size": (10, 4.5),
                    },
                    required_obsm=["spatial"],
                )
            )

    elif analysis_type == "network_properties":
        plots.append(
            PlotSpec(
                plot_id="stats_network_overview",
                role="overview",
                renderer="network_degree_histogram",
                filename="network_degree_histogram.png",
                title="Spatial Graph Degree Distribution",
                description="Degree histogram of the constructed or reused spatial graph.",
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_network_supporting",
                role="supporting",
                renderer="summary_barplot",
                filename="network_per_cluster_degree.png",
                title="Per-Cluster Mean Degree",
                description="Per-cluster degree summary when a cluster key is available.",
                params={
                    "data_key": "per_cluster_df",
                    "label_col": "cluster",
                    "value_col": "mean_degree",
                    "top_n": 12,
                    "xlabel": "Mean degree",
                    "color": "#3182bd",
                },
            )
        )

    elif analysis_type == "spatial_centrality":
        plots.append(
            PlotSpec(
                plot_id="stats_centrality_overview",
                role="overview",
                renderer="spatial_stats_builtin",
                filename="centrality_scores.png",
                title="Cluster Centrality Scores",
                description="Shared Squidpy centrality-score plot.",
                params={"subtype": "centrality", "cluster_key": cluster_key},
            )
        )
        plots.append(
            PlotSpec(
                plot_id="stats_centrality_supporting",
                role="supporting",
                renderer="centrality_barplot",
                filename="centrality_scores_barplot.png",
                title="Centrality Score Barplot",
                description="Grouped barplot of selected cluster centrality scores.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-statistics-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Statistics Standard Gallery",
        description="Default OmicsClaw spatial-statistics gallery with overview, supporting, diagnostic, and uncertainty plots when available.",
        plots=plots,
    )


def _render_spatial_stats_builtin(adata, spec: PlotSpec, context: dict) -> object:
    params = VizParams(
        subtype=spec.params.get("subtype"),
        title=spec.title,
        figure_size=spec.params.get("figure_size"),
        dpi=int(spec.params.get("dpi", 200)),
        colormap=spec.params.get("colormap", "viridis"),
        cluster_key=spec.params.get("cluster_key") or context.get("cluster_key"),
        show_colorbar=bool(spec.params.get("show_colorbar", True)),
    )
    return plot_spatial_stats(adata, params)


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    params = VizParams(
        feature=spec.params.get("feature"),
        basis=spec.params.get("basis", "spatial"),
        title=spec.title,
        figure_size=spec.params.get("figure_size"),
        dpi=int(spec.params.get("dpi", 200)),
        colormap=spec.params.get("colormap", "viridis"),
        show_colorbar=bool(spec.params.get("show_colorbar", True)),
        show_axes=bool(spec.params.get("show_axes", False)),
    )
    return plot_features(adata, params)


def _render_ripley_curves(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    stats_df = context.get("results_df", pd.DataFrame())
    cluster_key = context.get("cluster_key", "cluster")
    if stats_df.empty or not {"bins", "stats", cluster_key}.issubset(stats_df.columns):
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    for cluster, group_df in stats_df.groupby(cluster_key, sort=False):
        ax.plot(group_df["bins"].astype(float), group_df["stats"].astype(float), label=str(cluster))
    ax.set_xlabel("Distance")
    ax.set_ylabel(f"Ripley {context['summary'].get('ripley_mode', 'L')}(r)")
    ax.set_title(spec.title or "Ripley Curves By Cluster")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig


def _render_cooccurrence_curves(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    results_df = context.get("results_df", pd.DataFrame())
    pair_summary_df = context.get("pair_summary_df", pd.DataFrame())
    if results_df.empty or pair_summary_df.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    top_pairs = pair_summary_df.head(int(spec.params.get("top_n", 6)))
    for _, row in top_pairs.iterrows():
        mask = (
            (results_df["cluster_a"] == row["cluster_a"])
            & (results_df["cluster_b"] == row["cluster_b"])
        )
        pair_df = results_df.loc[mask]
        if pair_df.empty:
            continue
        ax.plot(
            pair_df["distance_end"].astype(float),
            pair_df["co_occurrence"].astype(float),
            label=f"{row['cluster_a']} | {row['cluster_b']}",
        )
    ax.set_xlabel("Distance")
    ax.set_ylabel("Co-occurrence")
    ax.set_title(spec.title or "Top Co-occurrence Curves")
    ax.legend(loc="best", fontsize=7)
    fig.tight_layout()
    return fig


def _render_summary_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    df = context.get(spec.params.get("data_key", ""), pd.DataFrame())
    value_col = spec.params.get("value_col")
    if df is None or df.empty or value_col not in df.columns:
        return None

    plot_df = df.copy()
    if spec.params.get("label_cols"):
        plot_df["_label"] = plot_df[spec.params["label_cols"]].astype(str).agg(" | ".join, axis=1)
    else:
        label_col = spec.params.get("label_col")
        if label_col is None or label_col not in plot_df.columns:
            return None
        plot_df["_label"] = plot_df[label_col].astype(str)

    values = pd.to_numeric(plot_df[value_col], errors="coerce")
    if values.isna().all():
        return None
    plot_df["_value"] = values
    plot_df["_sort_value"] = values.abs() if spec.params.get("sort_abs", False) else values
    ascending = bool(spec.params.get("ascending", False))
    plot_df = plot_df.sort_values("_sort_value", ascending=ascending).head(int(spec.params.get("top_n", 12)))
    plot_df = plot_df.iloc[::-1]

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, max(4, len(plot_df) * 0.45))), dpi=200)
    ax.barh(plot_df["_label"], plot_df["_value"], color=spec.params.get("color", "#3182bd"), alpha=0.9)
    ax.set_xlabel(spec.params.get("xlabel", value_col))
    ax.set_title(spec.title or value_col.replace("_", " ").title())
    fig.tight_layout()
    return fig


def _render_value_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    df = context.get(spec.params.get("data_key", ""), pd.DataFrame())
    value_col = spec.params.get("value_col")
    if df is None or df.empty or value_col not in df.columns:
        return None

    values = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if values.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(values, bins=int(spec.params.get("bins", 20)), color=spec.params.get("color", "#756bb1"), edgecolor="white", alpha=0.9)
    ax.set_xlabel(spec.params.get("xlabel", value_col))
    ax.set_ylabel("Count")
    ax.set_title(spec.title or value_col.replace("_", " ").title())
    fig.tight_layout()
    return fig


def _render_autocorr_ranking(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    results_df = context.get("results_df", pd.DataFrame())
    score_col = spec.params.get("score_col")
    if results_df.empty or score_col not in results_df.columns or "gene" not in results_df.columns:
        return None

    plot_df = results_df.copy()
    plot_df["_score"] = pd.to_numeric(plot_df[score_col], errors="coerce")
    plot_df = plot_df.dropna(subset=["_score"])
    if plot_df.empty:
        return None

    plot_df = plot_df.sort_values("_score", ascending=bool(spec.params.get("ascending", False))).head(15)
    plot_df = plot_df.iloc[::-1]

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, max(4, len(plot_df) * 0.35))), dpi=200)
    ax.barh(plot_df["gene"], plot_df["_score"], color=spec.params.get("color", "#3182bd"), alpha=0.9)
    ax.set_xlabel(score_col)
    ax.set_title(spec.title or score_col)
    fig.tight_layout()
    return fig


def _render_autocorr_scatter(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    results_df = context.get("results_df", pd.DataFrame()).copy()
    score_col = spec.params.get("score_col")
    pvalue_col = context["summary"].get("pvalue_column")
    if results_df.empty or score_col not in results_df.columns or not pvalue_col or pvalue_col not in results_df.columns:
        return None

    score = pd.to_numeric(results_df[score_col], errors="coerce")
    pvals = pd.to_numeric(results_df[pvalue_col], errors="coerce").clip(lower=1e-300)
    plot_df = pd.DataFrame({"gene": results_df.get("gene", results_df.index.astype(str)), "score": score, "pvalue": pvals}).dropna()
    if plot_df.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 6)), dpi=200)
    ax.scatter(plot_df["score"], -np.log10(plot_df["pvalue"]), s=28, alpha=0.7, color="#3182bd", edgecolors="none")
    ax.set_xlabel(score_col)
    ax.set_ylabel(f"-log10({pvalue_col})")
    ax.set_title(spec.title or "Score vs Significance")

    for _, row in plot_df.head(5).iterrows():
        ax.text(row["score"], -np.log10(row["pvalue"]), f" {row['gene']}", fontsize=8, color="#08306b")

    fig.tight_layout()
    return fig


def _render_autocorr_pvalue_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    results_df = context.get("results_df", pd.DataFrame())
    pvalue_col = context["summary"].get("pvalue_column")
    if results_df.empty or not pvalue_col or pvalue_col not in results_df.columns:
        return None

    values = pd.to_numeric(results_df[pvalue_col], errors="coerce").dropna().clip(lower=0.0, upper=1.0)
    if values.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(values, bins=20, color="#756bb1", edgecolor="white", alpha=0.9)
    ax.set_xlabel(pvalue_col)
    ax.set_ylabel("Number of genes")
    ax.set_title(spec.title or pvalue_col)
    fig.tight_layout()
    return fig


def _render_bivariate_scatter(adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    summary = context["summary"]
    gene_a = str(summary.get("gene_a"))
    gene_b = str(summary.get("gene_b"))
    if gene_a not in adata.var_names or gene_b not in adata.var_names or "spatial_connectivities" not in adata.obsp:
        return None

    conn = adata.obsp["spatial_connectivities"]
    x = _expr_vector(adata, gene_a)
    y = _expr_vector(adata, gene_b)
    lag_y = conn.dot(y)

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (6, 5)), dpi=200)
    ax.scatter(x, lag_y, s=12, alpha=0.65, color="#3182bd", edgecolors="none")
    ax.set_xlabel(f"{gene_a} expression")
    ax.set_ylabel(f"Spatial lag of {gene_b}")
    ax.set_title(spec.title or "Bivariate Moran Scatter")
    fig.tight_layout()
    return fig


def _render_network_degree_histogram(adata, spec: PlotSpec, _context: dict) -> object:
    import matplotlib.pyplot as plt

    if "spatial_connectivities" not in adata.obsp:
        return None

    conn = adata.obsp["spatial_connectivities"]
    degrees = np.asarray(conn.getnnz(axis=1) if hasattr(conn, "getnnz") else np.count_nonzero(conn, axis=1))

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (7, 4.5)), dpi=200)
    ax.hist(degrees, bins=min(30, max(5, len(np.unique(degrees)))), color="#3182bd", edgecolor="white")
    ax.set_xlabel("Node degree")
    ax.set_ylabel("Count")
    ax.set_title(spec.title or "Spatial Graph Degree Distribution")
    fig.tight_layout()
    return fig


def _render_centrality_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    results_df = context.get("results_df", pd.DataFrame())
    if results_df.empty or "cluster" not in results_df.columns:
        return None

    score_cols = [col for col in results_df.columns if col != "cluster"]
    if not score_cols:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    x = np.arange(len(results_df))
    width = 0.8 / max(1, len(score_cols))
    for idx, col in enumerate(score_cols):
        values = pd.to_numeric(results_df[col], errors="coerce").fillna(0.0)
        ax.bar(x + idx * width, values, width=width, label=col)
    ax.set_xticks(x + (len(score_cols) - 1) * width / 2)
    ax.set_xticklabels(results_df["cluster"].astype(str), rotation=30, ha="right")
    ax.set_ylabel("Score")
    ax.set_title(spec.title or "Centrality Score Barplot")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig


STATISTICS_GALLERY_RENDERERS = {
    "spatial_stats_builtin": _render_spatial_stats_builtin,
    "feature_map": _render_feature_map,
    "ripley_curves": _render_ripley_curves,
    "cooccurrence_curves": _render_cooccurrence_curves,
    "summary_barplot": _render_summary_barplot,
    "value_histogram": _render_value_histogram,
    "autocorr_ranking": _render_autocorr_ranking,
    "autocorr_scatter": _render_autocorr_scatter,
    "autocorr_pvalue_histogram": _render_autocorr_pvalue_histogram,
    "bivariate_scatter": _render_bivariate_scatter,
    "network_degree_histogram": _render_network_degree_histogram,
    "centrality_barplot": _render_centrality_barplot,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def _export_figure_data(output_dir: Path, summary: dict, recipe: VisualizationRecipe, artifacts: list, context: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    available_files: dict[str, str | None] = {}

    summary_path = figure_data_dir / "analysis_summary.csv"
    context["analysis_summary_df"].to_csv(summary_path, index=False)
    available_files["analysis_summary"] = summary_path.name

    optional_frames = {
        "results": context.get("results_df"),
        "top_results": context.get("top_results_df"),
        "pair_summary": context.get("pair_summary_df"),
        "cluster_summary": context.get("cluster_summary_df"),
        "per_cluster": context.get("per_cluster_df"),
        "spot_statistics": context.get("spot_statistics_df"),
    }
    file_names = {
        "results": "analysis_results.csv",
        "top_results": "top_results.csv",
        "pair_summary": "pair_summary.csv",
        "cluster_summary": "cluster_summary.csv",
        "per_cluster": "per_cluster_metrics.csv",
        "spot_statistics": "spot_statistics.csv",
    }
    for key, frame in optional_frames.items():
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            path = figure_data_dir / file_names[key]
            frame.to_csv(path, index=False)
            available_files[key] = path.name
        else:
            available_files[key] = None

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "analysis_type": summary.get("analysis_type"),
        "analysis_family": summary.get("analysis_family"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": [spec.role for spec in recipe.plots],
        "available_files": available_files,
        "gallery_outputs": [
            {
                "plot_id": artifact.plot_id,
                "role": artifact.role,
                "filename": artifact.filename,
                "status": artifact.status,
            }
            for artifact in artifacts
        ],
    }
    _write_figure_data_manifest(output_dir, contract)


def generate_figures(
    adata,
    output_dir: Path,
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    """Render the standardized spatial-statistics gallery and export figure data."""
    context = gallery_context or _prepare_statistics_gallery_context(adata, summary)
    recipe = _build_statistics_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        STATISTICS_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report / exports
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
    *,
    gallery_context: dict | None = None,
) -> None:
    """Write the Markdown report and JSON summary."""
    analysis_label = summary["analysis_type"].replace("_", " ").title()
    header = generate_report_header(
        title=f"Spatial Statistics Report — {analysis_label}",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Analysis": summary.get("analysis_type", ""),
            "Family": summary.get("analysis_family", ""),
            "Cluster key": summary.get("cluster_key", ""),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Analysis**: {analysis_label}",
        f"- **Family**: {summary.get('analysis_family', '')}",
        f"- **Cells / spots**: {summary.get('n_cells', 0)}",
        f"- **Genes in matrix**: {summary.get('n_features', 0)}",
    ]

    if summary.get("cluster_key"):
        body_lines.append(f"- **Cluster key**: `{summary.get('cluster_key')}`")
    if summary.get("categories"):
        body_lines.append(
            f"- **Categories**: {', '.join(str(x) for x in summary.get('categories', []))}"
        )
    if summary.get("selected_genes"):
        body_lines.append(
            f"- **Selected genes**: {', '.join(str(x) for x in summary.get('selected_genes', []))}"
        )
    if summary.get("graph_params"):
        gp = summary["graph_params"]
        body_lines.append(
            "- **Spatial graph**: "
            f"coord_type={gp.get('coord_type')}, n_neighs={gp.get('n_neighs')}, "
            f"n_rings={gp.get('n_rings')}, reused_existing_graph={gp.get('reused_existing_graph')}"
        )

    analysis_type = summary["analysis_type"]
    if analysis_type == "neighborhood_enrichment":
        body_lines.extend(
            [
                "",
                "### Neighborhood Summary\n",
                f"- **Permutation count**: {summary.get('n_perms')}",
                f"- **Mean z-score**: {summary.get('mean_zscore', 0.0):.3f}",
                f"- **Max z-score**: {summary.get('max_zscore', 0.0):.3f}",
                f"- **Min z-score**: {summary.get('min_zscore', 0.0):.3f}",
            ]
        )
        pair_summary_df = summary.get("pair_summary_df", pd.DataFrame())
        if not pair_summary_df.empty:
            body_lines.extend(["", "### Strongest Cluster Pairs\n"])
            body_lines.extend(
                _markdown_table(
                    pair_summary_df,
                    ["cluster_a", "cluster_b", "zscore", "count", "interpretation"],
                    ["Cluster A", "Cluster B", "Z-score", "Count", "Interpretation"],
                )
            )

    elif analysis_type == "ripley":
        body_lines.extend(
            [
                "",
                "### Ripley Parameters\n",
                f"- **Mode**: `{summary.get('ripley_mode')}`",
                f"- **Metric**: `{summary.get('ripley_metric')}`",
                f"- **Simulations**: {summary.get('ripley_n_simulations')}",
                f"- **Observations per simulation**: {summary.get('ripley_n_observations')}",
                f"- **Distance steps**: {summary.get('ripley_n_steps')}",
            ]
        )
        cluster_summary_df = summary.get("cluster_summary_df", pd.DataFrame())
        if not cluster_summary_df.empty:
            body_lines.extend(["", "### Cluster Curve Summary\n"])
            body_lines.extend(
                _markdown_table(
                    cluster_summary_df,
                    ["cluster", "max_stat", "mean_stat", "max_distance"],
                    ["Cluster", "Max stat", "Mean stat", "Max distance"],
                )
            )

    elif analysis_type == "co_occurrence":
        body_lines.extend(
            [
                "",
                "### Co-occurrence Parameters\n",
                f"- **Distance bins**: {summary.get('coocc_interval')}",
                f"- **Chunk splits**: {summary.get('coocc_n_splits')}",
            ]
        )
        pair_summary_df = summary.get("pair_summary_df", pd.DataFrame())
        if not pair_summary_df.empty:
            body_lines.extend(["", "### Strongest Co-occurrence Pairs\n"])
            body_lines.extend(
                _markdown_table(
                    pair_summary_df,
                    ["cluster_a", "cluster_b", "max_co_occurrence", "mean_co_occurrence"],
                    ["Cluster A", "Cluster B", "Max co-occurrence", "Mean co-occurrence"],
                )
            )

    elif analysis_type in {"moran", "geary"}:
        stat_col = "I" if analysis_type == "moran" else "C"
        mean_key = "mean_I" if analysis_type == "moran" else "mean_C"
        body_lines.extend(
            [
                "",
                "### Global Autocorrelation Summary\n",
                f"- **Permutation count**: {summary.get('n_perms')}",
                f"- **Multiple-testing correction**: `{summary.get('corr_method')}`",
                f"- **Two-tailed**: {summary.get('two_tailed')}",
                f"- **Mean {stat_col}**: {summary.get(mean_key, 0.0):.3f}",
                f"- **Significant genes**: {summary.get('n_significant', 0)}",
            ]
        )
        results_df = summary.get("results_df", pd.DataFrame())
        if not results_df.empty:
            cols = ["gene", stat_col]
            headers = ["Gene", stat_col]
            pcol = summary.get("pvalue_column")
            if pcol:
                cols.append(pcol)
                headers.append(f"{pcol}")
            cols.append("interpretation")
            headers.append("Interpretation")
            body_lines.extend(["", "### Top Genes\n"])
            body_lines.extend(_markdown_table(results_df, cols, headers))

    elif analysis_type == "local_moran":
        body_lines.extend(
            [
                "",
                "### Local Moran Summary\n",
                f"- **Permutation count**: {summary.get('n_perms')}",
                f"- **GeoDa quadrants**: {summary.get('local_moran_geoda_quads')}",
            ]
        )
        results_df = summary.get("results_df", pd.DataFrame())
        if not results_df.empty:
            body_lines.extend(["", "### Gene-Level Local Hotspots\n"])
            body_lines.extend(
                _markdown_table(
                    results_df,
                    ["gene", "n_significant_spots", "high_high", "low_low", "mean_local_I"],
                    ["Gene", "Significant spots", "High-high", "Low-low", "Mean local I"],
                )
            )

    elif analysis_type == "getis_ord":
        body_lines.extend(
            [
                "",
                "### Getis-Ord Summary\n",
                f"- **Permutation count**: {summary.get('n_perms')}",
                f"- **Star statistic**: {summary.get('getis_star')}",
            ]
        )
        results_df = summary.get("results_df", pd.DataFrame())
        if not results_df.empty:
            body_lines.extend(["", "### Gene-Level Hot / Cold Spots\n"])
            body_lines.extend(
                _markdown_table(
                    results_df,
                    ["gene", "n_hotspots", "n_coldspots", "mean_gi_z"],
                    ["Gene", "Hotspots", "Coldspots", "Mean Gi z-score"],
                )
            )

    elif analysis_type == "bivariate_moran":
        body_lines.extend(
            [
                "",
                "### Bivariate Moran Summary\n",
                f"- **Gene A**: `{summary.get('gene_a')}`",
                f"- **Gene B**: `{summary.get('gene_b')}`",
                f"- **Bivariate I**: {summary.get('bivariate_I', 0.0):.3f}",
                f"- **Permutation p-value**: {summary.get('pvalue', 1.0):.3g}",
                f"- **Simulation z-score**: {summary.get('zscore', 0.0):.3f}",
                f"- **Interpretation**: {summary.get('interpretation', '')}",
            ]
        )

    elif analysis_type == "network_properties":
        results_df = summary.get("results_df", pd.DataFrame())
        if not results_df.empty:
            body_lines.extend(["", "### Network Summary\n"])
            body_lines.extend(
                _markdown_table(
                    results_df,
                    [
                        "n_nodes",
                        "n_edges",
                        "mean_degree",
                        "std_degree",
                        "mean_clustering_coeff",
                        "density",
                        "n_connected_components",
                        "largest_component_size",
                    ],
                    [
                        "Nodes",
                        "Edges",
                        "Mean degree",
                        "Std degree",
                        "Mean clustering",
                        "Density",
                        "Connected components",
                        "Largest component",
                    ],
                    limit=1,
                )
            )
        per_cluster_df = summary.get("per_cluster_df", pd.DataFrame())
        if not per_cluster_df.empty:
            body_lines.extend(["", "### Per-Cluster Degree Summary\n"])
            body_lines.extend(
                _markdown_table(
                    per_cluster_df,
                    ["cluster", "n_cells", "mean_degree", "std_degree"],
                    ["Cluster", "Cells", "Mean degree", "Std degree"],
                )
            )

    elif analysis_type == "spatial_centrality":
        body_lines.extend(
            [
                "",
                "### Centrality Summary\n",
                f"- **Selected scores**: {', '.join(summary.get('selected_scores', []))}",
                f"- **Clusters scored**: {summary.get('n_clusters', 0)}",
            ]
        )
        results_df = summary.get("results_df", pd.DataFrame())
        if not results_df.empty:
            columns = results_df.columns.tolist()
            body_lines.extend(["", "### Centrality Table\n"])
            body_lines.extend(_markdown_table(results_df, columns, [col.replace("_", " ").title() for col in columns]))

    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    body_lines.extend(["", "## Interpretation Notes\n"])
    body_lines.extend(_interpretation_notes(summary))

    body_lines.extend(
        [
            "",
            "## Visualization Outputs\n",
            "- `figures/manifest.json`: Standard Python gallery manifest",
            "- `figure_data/`: Figure-ready CSV exports for downstream customization",
            "- `reproducibility/r_visualization.sh`: Optional R visualization entrypoint",
        ]
    )

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    summary_for_json = _json_safe_summary(summary)
    result_data = {"params": params, **summary_for_json}
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-statistics-gallery",
            "analysis_type": summary.get("analysis_type"),
        }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary_for_json,
        data=result_data,
        input_checksum=checksum,
    )
    _write_r_visualization_helper(output_dir)


def export_tables(
    output_dir: Path,
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    """Export method-specific tables."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []
    analysis_type = summary["analysis_type"]

    def _save_df(df: pd.DataFrame, filename: str) -> None:
        if df.empty:
            return
        path = tables_dir / filename
        df.to_csv(path, index=False)
        exported.append(str(path))

    if gallery_context:
        path = tables_dir / "analysis_summary.csv"
        gallery_context["analysis_summary_df"].to_csv(path, index=False)
        exported.append(str(path))

    if analysis_type == "neighborhood_enrichment":
        zscore_df = summary.get("zscore_df", pd.DataFrame())
        if not zscore_df.empty:
            path = tables_dir / "neighborhood_zscore.csv"
            zscore_df.to_csv(path)
            exported.append(str(path))
        count_df = summary.get("count_df", pd.DataFrame())
        if not count_df.empty:
            path = tables_dir / "neighborhood_counts.csv"
            count_df.to_csv(path)
            exported.append(str(path))
        _save_df(summary.get("pair_summary_df", pd.DataFrame()), "neighborhood_pairs.csv")

    elif analysis_type == "ripley":
        _save_df(summary.get("results_df", pd.DataFrame()), "ripley_curves.csv")
        _save_df(summary.get("cluster_summary_df", pd.DataFrame()), "ripley_cluster_summary.csv")

    elif analysis_type == "co_occurrence":
        _save_df(summary.get("results_df", pd.DataFrame()), "cooccurrence_curves.csv")
        _save_df(summary.get("pair_summary_df", pd.DataFrame()), "cooccurrence_pairs.csv")

    elif analysis_type in {"moran", "geary"}:
        _save_df(summary.get("results_df", pd.DataFrame()), f"{analysis_type}_results.csv")

    elif analysis_type in {"local_moran", "getis_ord"}:
        _save_df(summary.get("results_df", pd.DataFrame()), f"{analysis_type}_summary.csv")
        if gallery_context and isinstance(gallery_context.get("spot_statistics_df"), pd.DataFrame):
            _save_df(gallery_context["spot_statistics_df"], f"{analysis_type}_spots.csv")
        else:
            _save_df(summary.get("spot_df", pd.DataFrame()), f"{analysis_type}_spots.csv")

    elif analysis_type == "bivariate_moran":
        path = tables_dir / "bivariate_moran_summary.csv"
        pd.DataFrame([_json_safe_summary(summary)]).to_csv(path, index=False)
        exported.append(str(path))

    elif analysis_type == "network_properties":
        _save_df(summary.get("results_df", pd.DataFrame()), "network_summary.csv")
        _save_df(summary.get("per_cluster_df", pd.DataFrame()), "network_per_cluster.csv")

    elif analysis_type == "spatial_centrality":
        _save_df(summary.get("results_df", pd.DataFrame()), "centrality_scores.csv")

    return exported


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-statistics"
        / "r_visualization"
        / "stats_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def write_reproducibility(output_dir: Path, params: dict, input_file: str | None) -> None:
    """Write reproducibility helper files."""
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python {SCRIPT_REL_PATH} --output {shlex.quote(str(output_dir))}"
    if input_file:
        cmd += " --input <input.h5ad>"
    else:
        cmd += " --demo"

    for key, value in params.items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cmd += f" {flag}"
            elif key in BOOL_NEGATIVE_FLAGS:
                cmd += f" {BOOL_NEGATIVE_FLAGS[key]}"
            continue
        if value is None:
            continue
        cmd += f" {flag} {shlex.quote(str(value))}"

    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore

    env_lines = []
    for pkg in [
        "anndata",
        "esda",
        "libpysal",
        "matplotlib",
        "networkx",
        "numpy",
        "pandas",
        "scanpy",
        "scipy",
        "squidpy",
    ]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo / validation helpers
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate demo data by running spatial-preprocess first."""
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_statistics_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=240,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed (exit {result.returncode}):\n{result.stderr}"
            )
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)
    return adata, None


def _ensure_groupby_column(
    adata,
    *,
    groupby: str,
    parser: argparse.ArgumentParser,
) -> None:
    """Auto-compute a default Leiden clustering if it is missing."""
    if groupby in adata.obs.columns:
        return
    if groupby != "leiden":
        parser.error(
            f"--cluster-key '{groupby}' not found in adata.obs. "
            "Use an existing label column or omit it to auto-compute `leiden`."
        )

    logger.info("No '%s' column found; running minimal clustering to compute it.", groupby)
    work = adata.copy()
    sc.pp.normalize_total(work, target_sum=1e4)
    sc.pp.log1p(work)

    n_hvg = min(2000, max(2, work.n_vars - 1))
    sc.pp.highly_variable_genes(work, n_top_genes=n_hvg, flavor="seurat")
    if "highly_variable" in work.var and int(work.var["highly_variable"].sum()) >= 2:
        work = work[:, work.var["highly_variable"]].copy()

    if work.n_obs < 3 or work.n_vars < 2:
        parser.error("Dataset is too small to auto-compute `leiden` clusters.")

    sc.pp.scale(work, max_value=10)
    n_comps = max(2, min(50, work.n_obs - 1, work.n_vars - 1))
    sc.tl.pca(work, n_comps=n_comps)
    sc.pp.neighbors(work, n_neighbors=min(15, max(2, work.n_obs - 1)), n_pcs=min(n_comps, 30))
    sc.tl.leiden(work, resolution=1.0, flavor="igraph")
    adata.obs[groupby] = work.obs["leiden"].astype(str).values


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.analysis_type not in ANALYSIS_REGISTRY:
        parser.error(f"--analysis-type must be one of {VALID_ANALYSIS_TYPES}")
    if args.n_top_genes < 1:
        parser.error("--n-top-genes must be >= 1")
    if args.stats_n_neighs < 1:
        parser.error("--stats-n-neighs must be >= 1")
    if args.stats_n_rings < 1:
        parser.error("--stats-n-rings must be >= 1")
    if args.stats_n_perms < 1:
        parser.error("--stats-n-perms must be >= 1")
    if args.stats_corr_method not in VALID_STATS_CORR_METHODS:
        parser.error(f"--stats-corr-method must be one of {VALID_STATS_CORR_METHODS}")
    if args.ripley_mode not in VALID_RIPLEY_MODES:
        parser.error(f"--ripley-mode must be one of {VALID_RIPLEY_MODES}")
    if args.ripley_n_neigh < 1:
        parser.error("--ripley-n-neigh must be >= 1")
    if args.ripley_n_simulations < 1:
        parser.error("--ripley-n-simulations must be >= 1")
    if args.ripley_n_observations < 1:
        parser.error("--ripley-n-observations must be >= 1")
    if args.ripley_n_steps < 2:
        parser.error("--ripley-n-steps must be >= 2")
    if args.ripley_max_dist is not None and args.ripley_max_dist <= 0:
        parser.error("--ripley-max-dist must be > 0")
    if args.coocc_interval < 2:
        parser.error("--coocc-interval must be >= 2")
    if args.coocc_n_splits is not None and args.coocc_n_splits < 1:
        parser.error("--coocc-n-splits must be >= 1")
    if args.centrality_score not in (None, "", "all"):
        invalid = sorted(
            {
                item.strip()
                for item in args.centrality_score.split(",")
                if item.strip() and item.strip() not in VALID_CENTRALITY_SCORES
            }
        )
        if invalid:
            parser.error(
                f"--centrality-score contains invalid value(s) {invalid}. "
                f"Valid options: {VALID_CENTRALITY_SCORES} or 'all'"
            )

    genes = _parse_genes_arg(args.genes)
    if args.analysis_type == "bivariate_moran" and (genes is None or len(genes) != 2):
        parser.error("--analysis-type bivariate_moran requires exactly two genes via --genes geneA,geneB")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    """Build report params and per-method keyword arguments."""
    genes = _parse_genes_arg(args.genes)
    params = {
        "analysis_type": args.analysis_type,
        "cluster_key": args.cluster_key,
    }
    method_kwargs: dict = {}

    force_graph_rebuild = (
        args.stats_n_neighs != METHOD_PARAM_DEFAULTS["common"]["stats_n_neighs"]
        or args.stats_n_rings != METHOD_PARAM_DEFAULTS["common"]["stats_n_rings"]
    )

    if args.analysis_type == "neighborhood_enrichment":
        params.update(
            {
                "stats_n_neighs": args.stats_n_neighs,
                "stats_n_rings": args.stats_n_rings,
                "stats_n_perms": args.stats_n_perms,
                "stats_seed": args.stats_seed,
            }
        )
        method_kwargs = {
            "cluster_key": args.cluster_key,
            "n_neighs": args.stats_n_neighs,
            "n_rings": args.stats_n_rings,
            "n_perms": args.stats_n_perms,
            "seed": args.stats_seed,
            "force_graph_rebuild": force_graph_rebuild,
        }

    elif args.analysis_type == "ripley":
        params.update(
            {
                "ripley_mode": args.ripley_mode,
                "ripley_metric": args.ripley_metric,
                "ripley_n_neigh": args.ripley_n_neigh,
                "ripley_n_simulations": args.ripley_n_simulations,
                "ripley_n_observations": args.ripley_n_observations,
                "ripley_max_dist": args.ripley_max_dist,
                "ripley_n_steps": args.ripley_n_steps,
                "stats_seed": args.stats_seed,
            }
        )
        method_kwargs = {
            "cluster_key": args.cluster_key,
            "ripley_mode": args.ripley_mode,
            "ripley_metric": args.ripley_metric,
            "ripley_n_neigh": args.ripley_n_neigh,
            "ripley_n_simulations": args.ripley_n_simulations,
            "ripley_n_observations": args.ripley_n_observations,
            "ripley_max_dist": args.ripley_max_dist,
            "ripley_n_steps": args.ripley_n_steps,
            "seed": args.stats_seed,
        }

    elif args.analysis_type == "co_occurrence":
        params.update(
            {
                "coocc_interval": args.coocc_interval,
                "coocc_n_splits": args.coocc_n_splits,
            }
        )
        method_kwargs = {
            "cluster_key": args.cluster_key,
            "coocc_interval": args.coocc_interval,
            "coocc_n_splits": args.coocc_n_splits,
        }

    elif args.analysis_type in {"moran", "geary"}:
        params.update(
            {
                "genes": args.genes,
                "n_top_genes": args.n_top_genes,
                "stats_n_neighs": args.stats_n_neighs,
                "stats_n_rings": args.stats_n_rings,
                "stats_n_perms": args.stats_n_perms,
                "stats_corr_method": args.stats_corr_method,
                "stats_two_tailed": args.stats_two_tailed,
                "stats_seed": args.stats_seed,
            }
        )
        method_kwargs = {
            "genes": genes,
            "n_top_genes": args.n_top_genes,
            "n_neighs": args.stats_n_neighs,
            "n_rings": args.stats_n_rings,
            "n_perms": args.stats_n_perms,
            "corr_method": args.stats_corr_method,
            "two_tailed": args.stats_two_tailed,
            "seed": args.stats_seed,
            "force_graph_rebuild": force_graph_rebuild,
        }

    elif args.analysis_type == "local_moran":
        params.update(
            {
                "genes": args.genes,
                "n_top_genes": args.n_top_genes,
                "stats_n_neighs": args.stats_n_neighs,
                "stats_n_rings": args.stats_n_rings,
                "stats_n_perms": args.stats_n_perms,
                "local_moran_geoda_quads": args.local_moran_geoda_quads,
                "stats_seed": args.stats_seed,
            }
        )
        method_kwargs = {
            "genes": genes,
            "n_top_genes": args.n_top_genes,
            "n_neighs": args.stats_n_neighs,
            "n_rings": args.stats_n_rings,
            "n_perms": args.stats_n_perms,
            "seed": args.stats_seed,
            "local_moran_geoda_quads": args.local_moran_geoda_quads,
            "force_graph_rebuild": force_graph_rebuild,
        }

    elif args.analysis_type == "getis_ord":
        params.update(
            {
                "genes": args.genes,
                "n_top_genes": args.n_top_genes,
                "stats_n_neighs": args.stats_n_neighs,
                "stats_n_rings": args.stats_n_rings,
                "stats_n_perms": args.stats_n_perms,
                "getis_star": args.getis_star,
                "stats_seed": args.stats_seed,
            }
        )
        method_kwargs = {
            "genes": genes,
            "n_top_genes": args.n_top_genes,
            "n_neighs": args.stats_n_neighs,
            "n_rings": args.stats_n_rings,
            "n_perms": args.stats_n_perms,
            "seed": args.stats_seed,
            "getis_star": args.getis_star,
            "force_graph_rebuild": force_graph_rebuild,
        }

    elif args.analysis_type == "bivariate_moran":
        params.update(
            {
                "genes": args.genes,
                "stats_n_neighs": args.stats_n_neighs,
                "stats_n_rings": args.stats_n_rings,
                "stats_n_perms": args.stats_n_perms,
            }
        )
        method_kwargs = {
            "genes": genes,
            "n_neighs": args.stats_n_neighs,
            "n_rings": args.stats_n_rings,
            "n_perms": args.stats_n_perms,
            "force_graph_rebuild": force_graph_rebuild,
        }

    elif args.analysis_type == "network_properties":
        params.update(
            {
                "stats_n_neighs": args.stats_n_neighs,
                "stats_n_rings": args.stats_n_rings,
            }
        )
        method_kwargs = {
            "cluster_key": args.cluster_key,
            "n_neighs": args.stats_n_neighs,
            "n_rings": args.stats_n_rings,
            "force_graph_rebuild": force_graph_rebuild,
        }

    elif args.analysis_type == "spatial_centrality":
        params.update(
            {
                "stats_n_neighs": args.stats_n_neighs,
                "stats_n_rings": args.stats_n_rings,
                "centrality_score": args.centrality_score,
            }
        )
        method_kwargs = {
            "cluster_key": args.cluster_key,
            "n_neighs": args.stats_n_neighs,
            "n_rings": args.stats_n_rings,
            "centrality_score": args.centrality_score,
            "force_graph_rebuild": force_graph_rebuild,
        }

    return params, method_kwargs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Statistics — neighborhood, autocorrelation, and spatial graph analysis",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--analysis-type",
        default=METHOD_PARAM_DEFAULTS["common"]["analysis_type"],
        choices=list(VALID_ANALYSIS_TYPES),
    )
    parser.add_argument("--cluster-key", default=METHOD_PARAM_DEFAULTS["common"]["cluster_key"])
    parser.add_argument("--genes", default=None)
    parser.add_argument(
        "--n-top-genes",
        type=int,
        default=METHOD_PARAM_DEFAULTS["common"]["n_top_genes"],
    )
    parser.add_argument(
        "--stats-n-neighs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["common"]["stats_n_neighs"],
    )
    parser.add_argument(
        "--stats-n-rings",
        type=int,
        default=METHOD_PARAM_DEFAULTS["common"]["stats_n_rings"],
    )
    parser.add_argument(
        "--stats-n-perms",
        type=int,
        default=METHOD_PARAM_DEFAULTS["common"]["stats_n_perms"],
    )
    parser.add_argument(
        "--stats-seed",
        type=int,
        default=METHOD_PARAM_DEFAULTS["common"]["stats_seed"],
    )
    parser.add_argument(
        "--stats-corr-method",
        default=METHOD_PARAM_DEFAULTS["autocorr"]["stats_corr_method"],
    )
    parser.add_argument(
        "--stats-two-tailed",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["autocorr"]["stats_two_tailed"],
    )

    parser.add_argument(
        "--ripley-mode",
        default=METHOD_PARAM_DEFAULTS["ripley"]["ripley_mode"],
    )
    parser.add_argument(
        "--ripley-metric",
        default=METHOD_PARAM_DEFAULTS["ripley"]["ripley_metric"],
    )
    parser.add_argument(
        "--ripley-n-neigh",
        type=int,
        default=METHOD_PARAM_DEFAULTS["ripley"]["ripley_n_neigh"],
    )
    parser.add_argument(
        "--ripley-n-simulations",
        type=int,
        default=METHOD_PARAM_DEFAULTS["ripley"]["ripley_n_simulations"],
    )
    parser.add_argument(
        "--ripley-n-observations",
        type=int,
        default=METHOD_PARAM_DEFAULTS["ripley"]["ripley_n_observations"],
    )
    parser.add_argument(
        "--ripley-max-dist",
        type=float,
        default=METHOD_PARAM_DEFAULTS["ripley"]["ripley_max_dist"],
    )
    parser.add_argument(
        "--ripley-n-steps",
        type=int,
        default=METHOD_PARAM_DEFAULTS["ripley"]["ripley_n_steps"],
    )

    parser.add_argument(
        "--coocc-interval",
        type=int,
        default=METHOD_PARAM_DEFAULTS["co_occurrence"]["coocc_interval"],
    )
    parser.add_argument(
        "--coocc-n-splits",
        type=int,
        default=METHOD_PARAM_DEFAULTS["co_occurrence"]["coocc_n_splits"],
    )

    parser.add_argument(
        "--local-moran-geoda-quads",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["local_moran"]["local_moran_geoda_quads"],
    )
    parser.add_argument(
        "--getis-star",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["getis_ord"]["getis_star"],
    )
    parser.add_argument(
        "--centrality-score",
        default=METHOD_PARAM_DEFAULTS["spatial_centrality"]["centrality_score"],
    )

    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        input_path = Path(args.input_path)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(input_path)
        input_file = str(input_path)
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    if _requires_cluster_key(args.analysis_type):
        _ensure_groupby_column(adata, groupby=args.cluster_key, parser=parser)

    params, method_kwargs = _collect_run_configuration(args)
    summary = run_statistics(
        adata,
        analysis_type=args.analysis_type,
        **method_kwargs,
    )
    summary["n_cells"] = int(adata.n_obs)
    summary["n_features"] = int(adata.n_vars)
    gallery_context = _prepare_statistics_gallery_context(adata, summary)
    adata.uns["spatial_statistics_summary"] = {
        "analysis_type": summary.get("analysis_type"),
        "analysis_family": summary.get("analysis_family"),
        "cluster_key": summary.get("cluster_key"),
        "selected_genes": [str(gene) for gene in summary.get("selected_genes", [])],
        "n_cells": int(summary.get("n_cells", 0)),
        "n_features": int(summary.get("n_features", 0)),
        "n_significant": int(summary.get("n_significant", 0)),
    }
    adata.uns["spatial_statistics_gallery"] = {
        "analysis_type": summary.get("analysis_type"),
        "recipe_id": "standard-spatial-statistics-gallery",
    }

    store_analysis_metadata(adata, SKILL_NAME, args.analysis_type, params=params)

    export_tables(output_dir, summary, gallery_context=gallery_context)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, input_file)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(f"Spatial statistics complete: {args.analysis_type.replace('_', ' ')}")


if __name__ == "__main__":
    main()
