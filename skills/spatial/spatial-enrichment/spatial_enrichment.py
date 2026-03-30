#!/usr/bin/env python3
"""Spatial Enrichment — pathway and gene-set enrichment analysis."""

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
from skills.spatial._lib.enrichment import (
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    VALID_DE_CORR_METHODS,
    VALID_DE_METHODS,
    VALID_RANKING_METRICS,
    VALID_SPECIES,
    VALID_SSGSEA_CORREL_NORM_TYPES,
    VALID_SSGSEA_SAMPLE_NORM_METHODS,
    run_enrichment,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_enrichment,
    plot_features,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-enrichment"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-enrichment/spatial_enrichment.py"
BOOL_NEGATIVE_FLAGS = {
    "gsea_ascending": "--no-gsea-ascending",
    "ssgsea_ascending": "--no-ssgsea-ascending",
}


# ---------------------------------------------------------------------------
# Shared table helpers
# ---------------------------------------------------------------------------


def _safe_numeric(value, default: float = 0.0) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return float(default)
    return float(numeric)


def _term_score_column(df: pd.DataFrame) -> str:
    """Choose the most relevant numeric ranking column for plots and reports."""
    for column in ("pvalue_adj", "nes", "score", "es"):
        if column in df.columns and df[column].notna().any():
            return column
    return ""


def _term_score_label(summary: dict) -> str:
    method = str(summary.get("method", "")).lower()
    if method in {"gsea", "ssgsea"}:
        return "NES"
    if method == "enrichr":
        return "Combined score"
    return "Score"


def _sorted_results(df: pd.DataFrame) -> pd.DataFrame:
    """Sort enrichment results for display and figure export."""
    if df.empty:
        return df
    out = df.copy()
    if "pvalue_adj" in out.columns and out["pvalue_adj"].notna().any():
        pvalue_sort = pd.to_numeric(out["pvalue_adj"], errors="coerce").fillna(np.inf)
        pvalue_raw_sort = pd.to_numeric(out.get("pvalue", pd.Series(index=out.index)), errors="coerce").fillna(np.inf)
        out = out.assign(_pvalue_adj_sort=pvalue_sort, _pvalue_sort=pvalue_raw_sort)
        out = out.sort_values(
            ["_pvalue_adj_sort", "_pvalue_sort"],
            ascending=[True, True],
            na_position="last",
            kind="mergesort",
        )
        return out.drop(columns=["_pvalue_adj_sort", "_pvalue_sort"])
    if "nes" in out.columns and out["nes"].notna().any():
        return out.sort_values(
            "nes",
            key=lambda series: pd.to_numeric(series, errors="coerce").abs(),
            ascending=False,
            na_position="last",
            kind="mergesort",
        )
    if "score" in out.columns and out["score"].notna().any():
        return out.sort_values(
            "score",
            key=lambda series: pd.to_numeric(series, errors="coerce").abs(),
            ascending=False,
            na_position="last",
            kind="mergesort",
        )
    return out


def _empty_top_terms_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "rank",
            "group",
            "term",
            "score",
            "pvalue_adj",
            "gene_count",
            "overlap",
            "source",
            "library_mode",
        ]
    )


def _empty_group_metrics_table(groups: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": groups,
            "n_terms": [0] * len(groups),
            "n_significant": [0] * len(groups),
            "top_term": [""] * len(groups),
            "top_stat": [0.0] * len(groups),
            "top_abs_stat": [0.0] * len(groups),
            "best_pvalue_adj": [np.nan] * len(groups),
        }
    )


def _build_group_metrics_table(summary: dict) -> pd.DataFrame:
    enrich_df = _sorted_results(summary.get("enrich_df", pd.DataFrame()))
    groups = [str(group) for group in summary.get("groups", [])]
    if not groups and not enrich_df.empty and "group" in enrich_df.columns:
        groups = enrich_df["group"].astype(str).dropna().unique().tolist()

    if enrich_df.empty:
        return _empty_group_metrics_table(groups)

    fdr_threshold = float(summary.get("fdr_threshold", 0.05))
    records: list[dict[str, object]] = []
    for group in groups:
        group_df = enrich_df[enrich_df["group"].astype(str) == group].copy()
        if group_df.empty:
            records.append(_empty_group_metrics_table([group]).iloc[0].to_dict())
            continue

        scores = pd.to_numeric(group_df.get("score"), errors="coerce")
        padj = pd.to_numeric(group_df.get("pvalue_adj"), errors="coerce")
        if scores.notna().any():
            top_idx = scores.abs().fillna(0.0).idxmax()
            top_row = group_df.loc[top_idx]
            top_stat = _safe_numeric(top_row.get("score"), default=0.0)
        else:
            top_row = group_df.iloc[0]
            top_stat = 0.0

        records.append(
            {
                "group": group,
                "n_terms": int(len(group_df)),
                "n_significant": int(padj.fillna(np.inf).le(fdr_threshold).sum()) if padj.notna().any() else 0,
                "top_term": str(top_row.get("term", "")),
                "top_stat": top_stat,
                "top_abs_stat": abs(top_stat),
                "best_pvalue_adj": float(padj.min()) if padj.notna().any() else np.nan,
            }
        )

    metrics_df = pd.DataFrame(records)
    integer_cols = ["n_terms", "n_significant"]
    for column in integer_cols:
        metrics_df[column] = pd.to_numeric(metrics_df[column], errors="coerce").fillna(0).astype(int)
    for column in ("top_stat", "top_abs_stat", "best_pvalue_adj"):
        metrics_df[column] = pd.to_numeric(metrics_df[column], errors="coerce")

    return metrics_df.sort_values(
        by=["n_significant", "top_abs_stat", "n_terms", "group"],
        ascending=[False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _annotate_group_metrics_to_obs(adata, summary: dict, group_metrics_df: pd.DataFrame) -> dict[str, str]:
    groupby = summary.get("groupby")
    if groupby not in adata.obs.columns or group_metrics_df.empty:
        return {}

    lookup = group_metrics_df.copy()
    lookup["group"] = lookup["group"].astype(str)
    lookup = lookup.set_index("group")
    labels = adata.obs[groupby].astype(str)

    mapping = {
        "group_terms_col": ("n_terms", "enrich_group_n_terms"),
        "group_significant_col": ("n_significant", "enrich_group_n_significant"),
        "group_top_stat_col": ("top_stat", "enrich_group_top_stat"),
        "group_top_abs_stat_col": ("top_abs_stat", "enrich_group_top_abs_stat"),
    }

    resolved: dict[str, str] = {}
    for context_key, (source_col, obs_col) in mapping.items():
        if source_col not in lookup.columns:
            continue
        adata.obs[obs_col] = pd.to_numeric(labels.map(lookup[source_col]), errors="coerce").fillna(0.0)
        resolved[context_key] = obs_col

    return resolved


def _build_top_terms_table(summary: dict, n_top: int = 20) -> pd.DataFrame:
    enrich_df = _sorted_results(summary.get("enrich_df", pd.DataFrame()))
    if enrich_df.empty:
        return _empty_top_terms_table()

    groups = [str(group) for group in summary.get("groups", [])]
    if not groups:
        groups = enrich_df["group"].astype(str).dropna().unique().tolist()

    per_group = max(1, int(np.ceil(n_top / max(len(groups), 1))))
    selected_rows: list[dict[str, object]] = []
    used_indices: set[int] = set()

    for group in groups:
        group_df = enrich_df[enrich_df["group"].astype(str) == group].head(per_group)
        for idx, row in group_df.iterrows():
            idx_int = int(idx)
            if idx_int in used_indices:
                continue
            used_indices.add(idx_int)
            selected_rows.append(row.to_dict())

    if len(selected_rows) < n_top:
        for idx, row in enrich_df.iterrows():
            idx_int = int(idx)
            if idx_int in used_indices:
                continue
            used_indices.add(idx_int)
            selected_rows.append(row.to_dict())
            if len(selected_rows) >= n_top:
                break

    top_df = pd.DataFrame(selected_rows).head(n_top).copy()
    if top_df.empty:
        return _empty_top_terms_table()

    top_df.insert(0, "rank", np.arange(1, len(top_df) + 1))
    keep_cols = [
        "rank",
        "group",
        "term",
        "score",
        "pvalue_adj",
        "gene_count",
        "overlap",
        "source",
        "library_mode",
    ]
    for column in keep_cols:
        if column not in top_df.columns:
            top_df[column] = np.nan
    return top_df.loc[:, keep_cols]


def _build_term_group_score_table(summary: dict, n_top_terms: int = 20) -> pd.DataFrame:
    enrich_df = _sorted_results(summary.get("enrich_df", pd.DataFrame()))
    if enrich_df.empty:
        return pd.DataFrame(
            columns=["group", "term", "score", "pvalue_adj", "source", "library_mode", "method_used"]
        )

    priority_df = enrich_df.copy()
    priority_df["score"] = pd.to_numeric(priority_df.get("score"), errors="coerce")
    priority_df["pvalue_adj"] = pd.to_numeric(priority_df.get("pvalue_adj"), errors="coerce")
    term_priority = (
        priority_df.groupby("term", observed=True)
        .agg(
            max_abs_score=("score", lambda values: float(np.nanmax(np.abs(values))) if len(values) else 0.0),
            min_pvalue_adj=("pvalue_adj", lambda values: float(np.nanmin(values)) if pd.notna(values).any() else np.inf),
        )
        .reset_index()
    )
    term_priority = term_priority.sort_values(
        by=["min_pvalue_adj", "max_abs_score", "term"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    selected_terms = term_priority["term"].head(n_top_terms).astype(str).tolist()
    if not selected_terms:
        return pd.DataFrame(
            columns=["group", "term", "score", "pvalue_adj", "source", "library_mode", "method_used"]
        )

    plot_df = priority_df[priority_df["term"].astype(str).isin(selected_terms)].copy()
    plot_df["term"] = pd.Categorical(plot_df["term"].astype(str), categories=selected_terms, ordered=True)
    return plot_df.loc[
        :,
        [column for column in ("group", "term", "score", "pvalue_adj", "source", "library_mode", "method_used") if column in plot_df.columns],
    ].sort_values(["term", "group"], kind="mergesort")


def _build_run_summary_table(summary: dict, context: dict) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "groupby", "value": summary.get("groupby")},
        {"metric": "requested_source", "value": summary.get("requested_source")},
        {"metric": "resolved_source", "value": summary.get("resolved_source")},
        {"metric": "library_mode", "value": summary.get("library_mode")},
        {"metric": "species", "value": summary.get("species")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "n_groups", "value": summary.get("n_groups")},
        {"metric": "n_gene_sets_available", "value": summary.get("n_gene_sets_available")},
        {"metric": "n_terms_tested", "value": summary.get("n_terms_tested")},
        {"metric": "n_significant", "value": summary.get("n_significant")},
        {"metric": "n_groups_with_hits", "value": summary.get("n_groups_with_hits")},
        {"metric": "fdr_threshold", "value": summary.get("fdr_threshold")},
        {"metric": "n_top_terms", "value": summary.get("n_top_terms")},
        {"metric": "de_method", "value": summary.get("de_method")},
        {"metric": "de_corr_method", "value": summary.get("de_corr_method")},
        {"metric": "ranking_metric", "value": summary.get("ranking_metric")},
        {"metric": "group_terms_column", "value": context.get("group_terms_col")},
        {"metric": "group_significant_column", "value": context.get("group_significant_col")},
        {"metric": "group_top_stat_column", "value": context.get("group_top_stat_col")},
        {"metric": "group_top_abs_stat_column", "value": context.get("group_top_abs_stat_col")},
        {"metric": "score_columns", "value": ", ".join(context.get("score_columns", []))},
    ]
    return pd.DataFrame(rows)


def _build_observation_export_table(adata, summary: dict, context: dict, basis: str) -> pd.DataFrame | None:
    groupby = summary.get("groupby")

    if basis == "spatial":
        if "spatial" not in adata.obsm:
            return None
        coords = np.asarray(adata.obsm["spatial"])
        df = pd.DataFrame(
            {
                "observation": adata.obs_names.astype(str),
                "x": coords[:, 0],
                "y": coords[:, 1],
            }
        )
    elif basis == "umap":
        if "X_umap" not in adata.obsm:
            return None
        coords = np.asarray(adata.obsm["X_umap"])
        if coords.shape[1] < 2:
            return None
        df = pd.DataFrame(
            {
                "observation": adata.obs_names.astype(str),
                "umap_1": coords[:, 0],
                "umap_2": coords[:, 1],
            }
        )
    else:
        raise ValueError(f"Unsupported basis '{basis}'")

    export_columns = [
        groupby,
        context.get("group_terms_col"),
        context.get("group_significant_col"),
        context.get("group_top_stat_col"),
        context.get("group_top_abs_stat_col"),
        *context.get("score_columns", []),
    ]
    for column in export_columns:
        if not column or column not in adata.obs.columns:
            continue
        series = adata.obs[column]
        if pd.api.types.is_numeric_dtype(series):
            df[column] = pd.to_numeric(series, errors="coerce").fillna(0.0).to_numpy()
        else:
            df[column] = series.astype(str).to_numpy()
    return df


# ---------------------------------------------------------------------------
# Gallery helpers
# ---------------------------------------------------------------------------


def _prepare_enrichment_plot_state(adata, groupby: str) -> str | None:
    """Ensure enrichment outputs are plot-ready and coordinate aliases exist."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()

    if groupby in adata.obs.columns and not isinstance(adata.obs[groupby].dtype, pd.CategoricalDtype):
        adata.obs[groupby] = pd.Categorical(adata.obs[groupby].astype(str))

    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute a fallback UMAP so the standard enrichment gallery has an embedding view."""
    if "X_umap" in adata.obsm or adata.n_obs < 3:
        return

    try:
        if "connectivities" not in adata.obsp:
            n_neighbors = max(2, min(15, adata.n_obs - 1))
            if "X_pca" in adata.obsm:
                sc.pp.neighbors(adata, use_rep="X_pca", n_neighbors=n_neighbors)
            else:
                sc.pp.neighbors(adata, n_neighbors=n_neighbors)
        sc.tl.umap(adata)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Could not compute UMAP for enrichment gallery: %s", exc)


def _prepare_enrichment_gallery_context(adata, summary: dict) -> dict:
    spatial_key = _prepare_enrichment_plot_state(adata, groupby=summary.get("groupby", "leiden"))
    _ensure_umap_for_gallery(adata)

    context = {
        "groupby": summary.get("groupby"),
        "spatial_key": spatial_key,
        "enrich_df": _sorted_results(summary.get("enrich_df", pd.DataFrame())),
        "top_terms_df": _build_top_terms_table(summary, n_top=max(int(summary.get("n_top_terms", 20)), 20)),
        "group_metrics_df": _build_group_metrics_table(summary),
        "term_group_scores_df": _build_term_group_score_table(
            summary,
            n_top_terms=max(int(summary.get("n_top_terms", 20)), 20),
        ),
        "score_columns": list(summary.get("score_columns", [])),
    }
    context.update(_annotate_group_metrics_to_obs(adata, summary, context["group_metrics_df"]))
    return context


def _build_enrichment_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    groupby = summary.get("groupby")

    if groupby in adata.obs.columns and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="enrichment_group_spatial_context",
                role="overview",
                renderer="feature_map",
                filename="enrichment_group_spatial_context.png",
                title="Grouping Labels on Tissue",
                description="Active enrichment grouping labels projected onto spatial coordinates.",
                params={
                    "feature": groupby,
                    "basis": "spatial",
                    "colormap": "tab10",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (10, 8),
                },
                required_obs=[groupby],
                required_obsm=["spatial"],
            )
        )

    if not context["enrich_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="enrichment_barplot",
                role="overview",
                renderer="enrichment_plot",
                filename="enrichment_barplot.png",
                title="Top Enriched Pathways",
                description="Canonical pathway enrichment barplot built from the standardized enrichment table.",
                params={
                    "subtype": "barplot",
                    "top_n": min(max(int(summary.get("n_top_terms", 20)), 10), 20),
                    "figure_size": (10, 8),
                    "colormap": "viridis",
                    "show_colorbar": True,
                },
                required_uns=["enrichment_results"],
            )
        )
        plots.append(
            PlotSpec(
                plot_id="enrichment_dotplot",
                role="overview",
                renderer="enrichment_plot",
                filename="enrichment_dotplot.png",
                title="Enrichment Overview Dotplot",
                description="Term-level enrichment overview with term size and score/significance encoded in the shared enrichment renderer.",
                params={
                    "subtype": "dotplot",
                    "top_n": min(max(int(summary.get("n_top_terms", 20)), 12), 24),
                    "figure_size": (10, 8),
                    "colormap": "RdBu_r" if summary.get("method") in {"gsea", "ssgsea"} else "viridis",
                },
                required_uns=["enrichment_results"],
            )
        )

    if context.get("group_top_stat_col") and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="enrichment_group_top_stat_spatial",
                role="diagnostic",
                renderer="feature_map",
                filename="enrichment_group_top_stat_spatial.png",
                title="Top Enrichment Statistic on Tissue",
                description="Per-group strongest enrichment statistic projected back onto tissue coordinates.",
                params={
                    "feature": context["group_top_stat_col"],
                    "basis": "spatial",
                    "colormap": "RdBu_r",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (10, 8),
                },
                required_obs=[context["group_top_stat_col"]],
                required_obsm=["spatial"],
            )
        )

    if context.get("score_columns") and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="enrichment_spatial_scores",
                role="diagnostic",
                renderer="enrichment_plot",
                filename="enrichment_spatial_scores.png",
                title="Projected ssGSEA Scores on Tissue",
                description="Top ssGSEA score columns projected back onto spatial coordinates for default OmicsClaw diagnostics.",
                params={
                    "subtype": "spatial",
                    "top_n": min(len(context["score_columns"]), 4),
                    "figure_size": (12, 9),
                    "colormap": "RdBu_r",
                },
                required_obs=[context["score_columns"][0]],
                required_obsm=["spatial"],
            )
        )

    if context.get("group_top_stat_col") and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="enrichment_group_top_stat_umap",
                role="diagnostic",
                renderer="feature_map",
                filename="enrichment_group_top_stat_umap.png",
                title="Top Enrichment Statistic on UMAP",
                description="Per-group strongest enrichment statistic projected onto the shared embedding.",
                params={
                    "feature": context["group_top_stat_col"],
                    "basis": "umap",
                    "colormap": "RdBu_r",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (8, 6),
                },
                required_obs=[context["group_top_stat_col"]],
                required_obsm=["X_umap"],
            )
        )

    if not context["top_terms_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="enrichment_top_terms_summary",
                role="supporting",
                renderer="top_terms_barplot",
                filename="top_enriched_terms.png",
                title="Top Enriched Terms by Group",
                description="Balanced summary of top enriched terms across the tested groups.",
            )
        )

    if not context["group_metrics_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="enrichment_group_metrics",
                role="supporting",
                renderer="group_metric_barplot",
                filename="enrichment_group_metrics.png",
                title="Per-Group Enrichment Burden",
                description="Group-level summary of tested terms and significant enrichment burden.",
            )
        )

    if context.get("score_columns") and groupby in adata.obs.columns:
        plots.append(
            PlotSpec(
                plot_id="enrichment_score_violin",
                role="supporting",
                renderer="enrichment_plot",
                filename="enrichment_score_violin.png",
                title="ssGSEA Score Distribution by Group",
                description="Shared enrichment violin plots summarizing projected ssGSEA score columns by the active grouping.",
                params={
                    "subtype": "violin",
                    "cluster_key": groupby,
                    "top_n": min(len(context["score_columns"]), 4),
                    "figure_size": (12, 8),
                    "colormap": "Set2",
                },
                required_obs=[groupby, context["score_columns"][0]],
            )
        )

    if not context["enrich_df"].empty and "pvalue_adj" in context["enrich_df"].columns and context["enrich_df"]["pvalue_adj"].notna().any():
        plots.append(
            PlotSpec(
                plot_id="enrichment_pvalue_distribution",
                role="uncertainty",
                renderer="pvalue_histogram",
                filename="enrichment_pvalue_distribution.png",
                title="Adjusted P-value Distribution",
                description="Distribution of adjusted p-values across all standardized enrichment entries.",
            )
        )

    if not context["enrich_df"].empty and "score" in context["enrich_df"].columns:
        plots.append(
            PlotSpec(
                plot_id="enrichment_score_distribution",
                role="uncertainty",
                renderer="score_histogram",
                filename="enrichment_score_distribution.png",
                title="Enrichment Score Distribution",
                description="Distribution of enrichment scores or NES values across all tested terms.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-enrichment-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Enrichment Standard Gallery",
        description=(
            "Default OmicsClaw enrichment story plots: grouping context, canonical "
            "enrichment overviews, projected diagnostics, supporting summaries, and "
            "uncertainty panels built from shared enrichment and feature-map renderers."
        ),
        plots=plots,
    )


def _render_enrichment_plot(adata, spec: PlotSpec, context: dict) -> object:
    plot_adata = adata
    subtype = spec.params.get("subtype")
    if subtype in {"spatial", "violin"} and context.get("score_columns"):
        keep_columns = list(dict.fromkeys([context.get("groupby"), *context["score_columns"]]))
        keep_columns = [column for column in keep_columns if column and column in adata.obs.columns]
        plot_adata = adata.copy()
        plot_adata.obs = adata.obs.loc[:, keep_columns].copy()
        plot_adata.uns["enrichment_score_columns"] = list(context["score_columns"])

    viz_params = {
        key: value
        for key, value in spec.params.items()
        if key not in {"top_n", "subtype"}
    }
    return plot_enrichment(
        plot_adata,
        VizParams(title=spec.title, **viz_params),
        subtype=subtype,
        cluster_key=spec.params.get("cluster_key"),
        top_n=int(spec.params.get("top_n", 20)),
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_top_terms_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    top_df = context.get("top_terms_df", pd.DataFrame()).copy()
    if top_df.empty:
        return None

    plot_df = top_df.head(12).copy()
    has_padj = "pvalue_adj" in plot_df.columns and pd.to_numeric(plot_df["pvalue_adj"], errors="coerce").notna().any()
    if has_padj:
        plot_df["plot_value"] = -np.log10(
            pd.to_numeric(plot_df["pvalue_adj"], errors="coerce").clip(lower=1e-300, upper=1.0)
        )
        xlabel = "-log10(adj. p-value)"
        color = "#3182bd"
    else:
        plot_df["plot_value"] = pd.to_numeric(plot_df["score"], errors="coerce").fillna(0.0)
        xlabel = _term_score_label(context["summary"])
        color = "#31a354"

    plot_df["label"] = plot_df["group"].astype(str) + " | " + plot_df["term"].astype(str)
    plot_df = plot_df.iloc[::-1]

    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (10, max(4.8, len(plot_df) * 0.46))),
        dpi=200,
    )
    ax.barh(plot_df["label"], plot_df["plot_value"], color=color, alpha=0.9)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Group | Term")
    ax.set_title(spec.title or "Top Enriched Terms by Group")
    fig.tight_layout()
    return fig


def _render_group_metric_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    metrics_df = context.get("group_metrics_df", pd.DataFrame()).copy()
    if metrics_df.empty:
        return None

    plot_df = metrics_df.head(12).iloc[::-1]
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.8, len(plot_df) * 0.5))),
        dpi=200,
    )

    if plot_df["n_significant"].sum() > 0:
        y = np.arange(len(plot_df))
        ax.barh(y - 0.18, plot_df["n_terms"], height=0.32, color="#9ecae1", label="Terms tested")
        ax.barh(y + 0.18, plot_df["n_significant"], height=0.32, color="#08519c", label="Significant terms")
        ax.set_yticks(y)
        ax.set_yticklabels(plot_df["group"].astype(str))
        ax.set_xlabel("Number of terms")
        ax.legend(frameon=False)
    else:
        ax.barh(plot_df["group"].astype(str), plot_df["top_abs_stat"], color="#756bb1")
        ax.set_xlabel(f"Top |{_term_score_label(context['summary'])}|")

    ax.set_title(spec.title or "Per-Group Enrichment Burden")
    fig.tight_layout()
    return fig


def _render_pvalue_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    enrich_df = context.get("enrich_df", pd.DataFrame())
    if enrich_df.empty or "pvalue_adj" not in enrich_df.columns:
        return None

    values = pd.to_numeric(enrich_df["pvalue_adj"], errors="coerce").dropna()
    if values.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(values.clip(lower=1e-300, upper=1.0), bins=25, color="#756bb1", edgecolor="white")
    ax.axvline(float(context["summary"].get("fdr_threshold", 0.05)), color="black", linestyle="--", linewidth=1.2)
    ax.set_xlabel("Adjusted p-value")
    ax.set_ylabel("Number of term entries")
    ax.set_title(spec.title or "Adjusted P-value Distribution")
    fig.tight_layout()
    return fig


def _render_score_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    enrich_df = context.get("enrich_df", pd.DataFrame())
    if enrich_df.empty or "score" not in enrich_df.columns:
        return None

    scores = pd.to_numeric(enrich_df["score"], errors="coerce").dropna()
    if scores.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(scores, bins=25, color="#1b9e77", edgecolor="white")
    ax.axvline(0.0, color="black", linestyle="--", linewidth=1.0)
    ax.set_xlabel(_term_score_label(context["summary"]))
    ax.set_ylabel("Number of term entries")
    ax.set_title(spec.title or "Enrichment Score Distribution")
    fig.tight_layout()
    return fig


ENRICHMENT_GALLERY_RENDERERS = {
    "enrichment_plot": _render_enrichment_plot,
    "feature_map": _render_feature_map,
    "top_terms_barplot": _render_top_terms_barplot,
    "group_metric_barplot": _render_group_metric_barplot,
    "pvalue_histogram": _render_pvalue_histogram,
    "score_histogram": _render_score_histogram,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def _export_figure_data(
    adata,
    output_dir: Path,
    summary: dict,
    recipe: VisualizationRecipe,
    artifacts: list,
    context: dict,
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    enrich_df = context.get("enrich_df", pd.DataFrame()).copy()
    if enrich_df.empty:
        enrich_df = pd.DataFrame(
            columns=[
                "group",
                "term",
                "gene_set",
                "source",
                "library_mode",
                "engine",
                "method_used",
                "score",
                "nes",
                "es",
                "pvalue",
                "pvalue_adj",
            ]
        )
    enrich_df.to_csv(figure_data_dir / "enrichment_results.csv", index=False)

    significant_df = enrich_df.copy()
    if "pvalue_adj" in significant_df.columns and pd.to_numeric(significant_df["pvalue_adj"], errors="coerce").notna().any():
        significant_df["pvalue_adj"] = pd.to_numeric(significant_df["pvalue_adj"], errors="coerce")
        significant_df = significant_df[
            significant_df["pvalue_adj"].fillna(np.inf) <= float(summary.get("fdr_threshold", 0.05))
        ].copy()
    else:
        significant_df = significant_df.iloc[0:0].copy()
    significant_df.to_csv(figure_data_dir / "enrichment_significant.csv", index=False)

    marker_df = summary.get("marker_df", pd.DataFrame()).copy()
    if marker_df.empty:
        marker_df = pd.DataFrame()
    marker_df.to_csv(figure_data_dir / "ranked_markers.csv", index=False)

    context.get("top_terms_df", _empty_top_terms_table()).to_csv(
        figure_data_dir / "top_enriched_terms.csv",
        index=False,
    )
    context.get("group_metrics_df", pd.DataFrame()).to_csv(
        figure_data_dir / "enrichment_group_metrics.csv",
        index=False,
    )
    context.get("term_group_scores_df", pd.DataFrame()).to_csv(
        figure_data_dir / "enrichment_term_group_scores.csv",
        index=False,
    )
    _build_run_summary_table(summary, context).to_csv(
        figure_data_dir / "enrichment_run_summary.csv",
        index=False,
    )

    spatial_file = None
    spatial_df = _build_observation_export_table(adata, summary, context, "spatial")
    if spatial_df is not None:
        spatial_file = "enrichment_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_observation_export_table(adata, summary, context, "umap")
    if umap_df is not None:
        umap_file = "enrichment_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "groupby": summary.get("groupby"),
        "requested_source": summary.get("requested_source"),
        "resolved_source": summary.get("resolved_source"),
        "library_mode": summary.get("library_mode"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "score_columns": list(context.get("score_columns", [])),
        "available_files": {
            "enrichment_results": "enrichment_results.csv",
            "enrichment_significant": "enrichment_significant.csv",
            "ranked_markers": "ranked_markers.csv",
            "top_enriched_terms": "top_enriched_terms.csv",
            "enrichment_group_metrics": "enrichment_group_metrics.csv",
            "enrichment_term_group_scores": "enrichment_term_group_scores.csv",
            "enrichment_run_summary": "enrichment_run_summary.csv",
            "enrichment_spatial_points": spatial_file,
            "enrichment_umap_points": umap_file,
        },
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


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(
    adata,
    output_dir: Path,
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    """Render the standard enrichment gallery and export figure-ready data."""
    context = gallery_context or _prepare_enrichment_gallery_context(adata, summary)
    recipe = _build_enrichment_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        ENRICHMENT_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _format_top_rows(df: pd.DataFrame, *, method: str) -> list[str]:
    rows: list[str] = []
    if method == "enrichr":
        rows.append("| Group | Gene Set | Score | Overlap | Adj. p-value |")
        rows.append("|-------|----------|-------|---------|--------------|")
        for _, row in df.iterrows():
            score_txt = "NA" if pd.isna(row.get("score")) else f"{float(row['score']):.2f}"
            p_txt = "NA" if pd.isna(row.get("pvalue_adj")) else f"{float(row['pvalue_adj']):.2e}"
            rows.append(
                f"| {row.get('group', '')} | {row.get('term', '')} | {score_txt} | "
                f"{row.get('overlap', '')} | {p_txt} |"
            )
        return rows

    if method == "ssgsea":
        rows.append("| Group | Gene Set | NES | ES |")
        rows.append("|-------|----------|-----|----|")
        for _, row in df.iterrows():
            nes_txt = "NA" if pd.isna(row.get("nes")) else f"{float(row['nes']):.2f}"
            es_txt = "NA" if pd.isna(row.get("es")) else f"{float(row['es']):.2f}"
            rows.append(f"| {row.get('group', '')} | {row.get('term', '')} | {nes_txt} | {es_txt} |")
        return rows

    rows.append("| Group | Gene Set | NES | Adj. p-value | Leading Edge |")
    rows.append("|-------|----------|-----|--------------|--------------|")
    for _, row in df.iterrows():
        nes_txt = "NA" if pd.isna(row.get("nes")) else f"{float(row['nes']):.2f}"
        p_txt = "NA" if pd.isna(row.get("pvalue_adj")) else f"{float(row['pvalue_adj']):.2e}"
        leading = str(row.get("leading_edge", ""))[:60]
        rows.append(
            f"| {row.get('group', '')} | {row.get('term', '')} | {nes_txt} | {p_txt} | {leading} |"
        )
    return rows


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-enrichment"
        / "r_visualization"
        / "enrichment_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
    *,
    gallery_context: dict | None = None,
) -> None:
    """Write report.md and result.json."""
    header = generate_report_header(
        title="Spatial Pathway Enrichment Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", ""),
            "Requested source": summary.get("requested_source", ""),
            "Resolved source": summary.get("resolved_source", ""),
            "Library mode": summary.get("library_mode", ""),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary.get('method', '')}",
        f"- **Cells**: {summary.get('n_cells', 0)}",
        f"- **Genes**: {summary.get('n_genes', 0)}",
        f"- **Grouping column**: `{summary.get('groupby', '')}`",
        f"- **Groups**: {', '.join(str(group) for group in summary.get('groups', []))}",
        f"- **Requested source**: `{summary.get('requested_source', '')}`",
        f"- **Resolved source**: `{summary.get('resolved_source', '')}`",
        f"- **Library mode**: `{summary.get('library_mode', '')}`",
        f"- **Gene sets available after overlap filtering**: {summary.get('n_gene_sets_available', 0)}",
        f"- **Terms tested**: {summary.get('n_terms_tested', 0)}",
        f"- **Significant terms** (padj < {summary.get('fdr_threshold', 0.05)}): {summary.get('n_significant', 0)}",
        f"- **Groups with enrichment hits**: {summary.get('n_groups_with_hits', 0)}",
    ]

    if summary.get("ranking_metric"):
        body_lines.append(f"- **Ranking metric**: `{summary.get('ranking_metric')}`")
    if gallery_context and gallery_context.get("group_significant_col"):
        body_lines.append(
            f"- **Observation-level significant-term column**: `{gallery_context['group_significant_col']}`"
        )
    if gallery_context and gallery_context.get("group_top_stat_col"):
        body_lines.append(
            f"- **Observation-level top-stat column**: `{gallery_context['group_top_stat_col']}`"
        )
    if summary.get("score_columns"):
        body_lines.append(
            f"- **Projected ssGSEA score columns**: {', '.join(summary.get('score_columns', []))}"
        )

    warnings_list = summary.get("warnings", [])
    if warnings_list:
        body_lines.extend(["", "### Warnings\n"])
        for warning in warnings_list:
            body_lines.append(f"- {warning}")

    enrich_df = _sorted_results(summary.get("enrich_df", pd.DataFrame()))
    if not enrich_df.empty:
        top = enrich_df.head(15)
        body_lines.extend(["", "### Top Enriched Terms\n"])
        body_lines.extend(_format_top_rows(top, method=str(summary.get("method", ""))))

    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    body_lines.extend(["", "## Interpretation Notes\n"])
    if summary.get("method") == "enrichr":
        body_lines.extend(
            [
                "- `enrichr` here is an ORA-style enrichment on positive marker genes per group.",
                "- Marker selection depends on the Scanpy ranking step (`de_method`, `de_corr_method`) plus the positive-marker cutoffs.",
                "- If a remote library could not be resolved, OmicsClaw explicitly falls back to a local signature library and reports that in `library_mode`.",
            ]
        )
    elif summary.get("method") == "gsea":
        body_lines.extend(
            [
                "- `gsea` uses a full ranked marker list per group rather than a thresholded marker subset.",
                "- Positive NES means the gene set is enriched toward the top of the ranked list for that group; negative NES means the opposite.",
                "- The ranking metric is wrapper-level and should be reported alongside the gene-set source.",
            ]
        )
    else:
        body_lines.extend(
            [
                "- `ssgsea` here is run on group-level mean expression profiles, not on every spot independently.",
                "- OmicsClaw projects selected group-level ssGSEA scores back onto observations for visualization convenience; this is a display layer, not extra inference.",
                "- ssGSEA scores are best interpreted comparatively across groups rather than as standalone p-value-based significance claims.",
            ]
        )

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

    summary_for_json = {
        key: value
        for key, value in summary.items()
        if key not in ("enrich_df", "marker_df")
    }
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {"params": params, **summary_for_json}
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-enrichment-gallery",
            "group_terms_column": gallery_context.get("group_terms_col"),
            "group_significant_column": gallery_context.get("group_significant_col"),
            "group_top_stat_column": gallery_context.get("group_top_stat_col"),
            "group_top_abs_stat_column": gallery_context.get("group_top_abs_stat_col"),
            "score_columns": list(gallery_context.get("score_columns", [])),
        }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary_for_json,
        data=result_data,
        input_checksum=checksum,
    )


def export_tables(
    output_dir: Path,
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    """Export enrichment tables."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []
    enrich_df = _sorted_results(summary.get("enrich_df", pd.DataFrame()))

    path = tables_dir / "enrichment_results.csv"
    enrich_df.to_csv(path, index=False)
    exported.append(str(path))

    significant_df = enrich_df.copy()
    if not significant_df.empty and "pvalue_adj" in significant_df.columns and significant_df["pvalue_adj"].notna().any():
        significant_df["pvalue_adj"] = pd.to_numeric(significant_df["pvalue_adj"], errors="coerce")
        significant_df = significant_df[
            significant_df["pvalue_adj"].fillna(np.inf) <= float(summary.get("fdr_threshold", 0.05))
        ].copy()
    else:
        significant_df = significant_df.iloc[0:0].copy()
    path = tables_dir / "enrichment_significant.csv"
    significant_df.to_csv(path, index=False)
    exported.append(str(path))

    marker_df = summary.get("marker_df", pd.DataFrame())
    path = tables_dir / "ranked_markers.csv"
    marker_df.to_csv(path, index=False)
    exported.append(str(path))

    top_terms_df = (
        gallery_context.get("top_terms_df")
        if gallery_context is not None
        else _build_top_terms_table(summary, n_top=max(int(summary.get("n_top_terms", 20)), 20))
    )
    path = tables_dir / "top_enriched_terms.csv"
    top_terms_df.to_csv(path, index=False)
    exported.append(str(path))

    group_metrics_df = (
        gallery_context.get("group_metrics_df")
        if gallery_context is not None
        else _build_group_metrics_table(summary)
    )
    path = tables_dir / "enrichment_group_metrics.csv"
    group_metrics_df.to_csv(path, index=False)
    exported.append(str(path))

    return exported


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
        if isinstance(value, bool):
            if value:
                cmd += f" --{key.replace('_', '-')}"
            elif key in BOOL_NEGATIVE_FLAGS:
                cmd += f" {BOOL_NEGATIVE_FLAGS[key]}"
            continue
        if value is None:
            continue
        cmd += f" --{key.replace('_', '-')} {shlex.quote(str(value))}"

    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    _write_r_visualization_helper(output_dir)

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore

    env_lines = []
    for pkg in ["scanpy", "anndata", "scipy", "numpy", "pandas", "matplotlib", "gseapy"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo and load the resulting processed.h5ad."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_enrich_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Running spatial-preprocess --demo into %s", tmp_path)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed (exit {result.returncode}):\n{result.stderr}"
            )
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)
        logger.info("Loaded demo: %d cells x %d genes", adata.n_obs, adata.n_vars)
        return adata, None


def _ensure_groupby_column(adata, *, groupby: str, parser: argparse.ArgumentParser) -> None:
    """Auto-compute the default Leiden labels if they are missing."""
    if groupby in adata.obs.columns:
        return
    if groupby != "leiden":
        parser.error(
            f"--groupby '{groupby}' not found in adata.obs. "
            "Use an existing grouping column or omit it to auto-compute `leiden`."
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
    if args.method not in SUPPORTED_METHODS:
        parser.error(f"--method must be one of {SUPPORTED_METHODS}")
    if args.species not in VALID_SPECIES:
        parser.error(f"--species must be one of {VALID_SPECIES}")
    if args.de_method not in VALID_DE_METHODS:
        parser.error(f"--de-method must be one of {VALID_DE_METHODS}")
    if args.de_corr_method not in VALID_DE_CORR_METHODS:
        parser.error(f"--de-corr-method must be one of {VALID_DE_CORR_METHODS}")
    if args.fdr_threshold <= 0 or args.fdr_threshold > 1:
        parser.error("--fdr-threshold must be in (0, 1]")
    if args.n_top_terms < 1:
        parser.error("--n-top-terms must be >= 1")
    if args.enrichr_padj_cutoff <= 0 or args.enrichr_padj_cutoff > 1:
        parser.error("--enrichr-padj-cutoff must be in (0, 1]")
    if args.enrichr_log2fc_cutoff < 0:
        parser.error("--enrichr-log2fc-cutoff must be >= 0")
    if args.enrichr_max_genes < 1:
        parser.error("--enrichr-max-genes must be >= 1")
    if args.gsea_ranking_metric not in VALID_RANKING_METRICS:
        parser.error(f"--gsea-ranking-metric must be one of {VALID_RANKING_METRICS}")
    if args.gsea_min_size < 1 or args.gsea_max_size < args.gsea_min_size:
        parser.error("--gsea-min-size must be >= 1 and <= --gsea-max-size")
    if args.gsea_permutation_num < 10:
        parser.error("--gsea-permutation-num must be >= 10")
    if args.gsea_weight < 0:
        parser.error("--gsea-weight must be >= 0")
    if args.gsea_threads < 1:
        parser.error("--gsea-threads must be >= 1")
    if args.ssgsea_sample_norm_method not in VALID_SSGSEA_SAMPLE_NORM_METHODS:
        parser.error(
            f"--ssgsea-sample-norm-method must be one of {VALID_SSGSEA_SAMPLE_NORM_METHODS}"
        )
    if args.ssgsea_correl_norm_type not in VALID_SSGSEA_CORREL_NORM_TYPES:
        parser.error(
            f"--ssgsea-correl-norm-type must be one of {VALID_SSGSEA_CORREL_NORM_TYPES}"
        )
    if args.ssgsea_min_size < 1 or args.ssgsea_max_size < args.ssgsea_min_size:
        parser.error("--ssgsea-min-size must be >= 1 and <= --ssgsea-max-size")
    if args.ssgsea_weight < 0:
        parser.error("--ssgsea-weight must be >= 0")
    if args.ssgsea_threads < 1:
        parser.error("--ssgsea-threads must be >= 1")
    if args.gene_set_file is not None and not Path(args.gene_set_file).exists():
        parser.error(f"--gene-set-file not found: {args.gene_set_file}")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    params = {
        "method": args.method,
        "groupby": args.groupby,
        "source": args.source,
        "species": args.species,
        "gene_set": args.gene_set,
        "gene_set_file": args.gene_set_file,
        "fdr_threshold": args.fdr_threshold,
        "n_top_terms": args.n_top_terms,
        "de_method": args.de_method,
        "de_corr_method": args.de_corr_method,
    }

    if args.method == "enrichr":
        params.update(
            {
                "enrichr_padj_cutoff": args.enrichr_padj_cutoff,
                "enrichr_log2fc_cutoff": args.enrichr_log2fc_cutoff,
                "enrichr_max_genes": args.enrichr_max_genes,
            }
        )
        method_kwargs = {
            "enrichr_padj_cutoff": args.enrichr_padj_cutoff,
            "enrichr_log2fc_cutoff": args.enrichr_log2fc_cutoff,
            "enrichr_max_genes": args.enrichr_max_genes,
        }
    elif args.method == "gsea":
        params.update(
            {
                "gsea_ranking_metric": args.gsea_ranking_metric,
                "gsea_min_size": args.gsea_min_size,
                "gsea_max_size": args.gsea_max_size,
                "gsea_permutation_num": args.gsea_permutation_num,
                "gsea_weight": args.gsea_weight,
                "gsea_ascending": args.gsea_ascending,
                "gsea_threads": args.gsea_threads,
                "gsea_seed": args.gsea_seed,
            }
        )
        method_kwargs = {
            "gsea_ranking_metric": args.gsea_ranking_metric,
            "gsea_min_size": args.gsea_min_size,
            "gsea_max_size": args.gsea_max_size,
            "gsea_permutation_num": args.gsea_permutation_num,
            "gsea_weight": args.gsea_weight,
            "gsea_ascending": args.gsea_ascending,
            "gsea_threads": args.gsea_threads,
            "gsea_seed": args.gsea_seed,
        }
    else:
        params.update(
            {
                "ssgsea_sample_norm_method": args.ssgsea_sample_norm_method,
                "ssgsea_correl_norm_type": args.ssgsea_correl_norm_type,
                "ssgsea_min_size": args.ssgsea_min_size,
                "ssgsea_max_size": args.ssgsea_max_size,
                "ssgsea_weight": args.ssgsea_weight,
                "ssgsea_ascending": args.ssgsea_ascending,
                "ssgsea_threads": args.ssgsea_threads,
                "ssgsea_seed": args.ssgsea_seed,
            }
        )
        method_kwargs = {
            "ssgsea_sample_norm_method": args.ssgsea_sample_norm_method,
            "ssgsea_correl_norm_type": args.ssgsea_correl_norm_type,
            "ssgsea_min_size": args.ssgsea_min_size,
            "ssgsea_max_size": args.ssgsea_max_size,
            "ssgsea_weight": args.ssgsea_weight,
            "ssgsea_ascending": args.ssgsea_ascending,
            "ssgsea_threads": args.ssgsea_threads,
            "ssgsea_seed": args.ssgsea_seed,
        }

    return params, method_kwargs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Enrichment — pathway and gene-set enrichment analysis"
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="enrichr", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--groupby", default=METHOD_PARAM_DEFAULTS["common"]["groupby"])
    parser.add_argument("--source", default=METHOD_PARAM_DEFAULTS["common"]["source"])
    parser.add_argument("--species", default=METHOD_PARAM_DEFAULTS["common"]["species"])
    parser.add_argument("--gene-set", default=None)
    parser.add_argument("--gene-set-file", default=None)
    parser.add_argument("--fdr-threshold", type=float, default=METHOD_PARAM_DEFAULTS["common"]["fdr_threshold"])
    parser.add_argument("--n-top-terms", type=int, default=METHOD_PARAM_DEFAULTS["common"]["n_top_terms"])
    parser.add_argument("--de-method", default=METHOD_PARAM_DEFAULTS["common"]["de_method"])
    parser.add_argument("--de-corr-method", default=METHOD_PARAM_DEFAULTS["common"]["de_corr_method"])

    parser.add_argument(
        "--enrichr-padj-cutoff",
        type=float,
        default=METHOD_PARAM_DEFAULTS["enrichr"]["enrichr_padj_cutoff"],
    )
    parser.add_argument(
        "--enrichr-log2fc-cutoff",
        type=float,
        default=METHOD_PARAM_DEFAULTS["enrichr"]["enrichr_log2fc_cutoff"],
    )
    parser.add_argument(
        "--enrichr-max-genes",
        type=int,
        default=METHOD_PARAM_DEFAULTS["enrichr"]["enrichr_max_genes"],
    )

    parser.add_argument(
        "--gsea-ranking-metric",
        default=METHOD_PARAM_DEFAULTS["gsea"]["gsea_ranking_metric"],
    )
    parser.add_argument("--gsea-min-size", type=int, default=METHOD_PARAM_DEFAULTS["gsea"]["gsea_min_size"])
    parser.add_argument("--gsea-max-size", type=int, default=METHOD_PARAM_DEFAULTS["gsea"]["gsea_max_size"])
    parser.add_argument(
        "--gsea-permutation-num",
        type=int,
        default=METHOD_PARAM_DEFAULTS["gsea"]["gsea_permutation_num"],
    )
    parser.add_argument("--gsea-weight", type=float, default=METHOD_PARAM_DEFAULTS["gsea"]["gsea_weight"])
    parser.add_argument(
        "--gsea-ascending",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["gsea"]["gsea_ascending"],
    )
    parser.add_argument("--gsea-threads", type=int, default=METHOD_PARAM_DEFAULTS["gsea"]["gsea_threads"])
    parser.add_argument("--gsea-seed", type=int, default=METHOD_PARAM_DEFAULTS["gsea"]["gsea_seed"])

    parser.add_argument(
        "--ssgsea-sample-norm-method",
        default=METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_sample_norm_method"],
    )
    parser.add_argument(
        "--ssgsea-correl-norm-type",
        default=METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_correl_norm_type"],
    )
    parser.add_argument("--ssgsea-min-size", type=int, default=METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_min_size"])
    parser.add_argument("--ssgsea-max-size", type=int, default=METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_max_size"])
    parser.add_argument("--ssgsea-weight", type=float, default=METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_weight"])
    parser.add_argument(
        "--ssgsea-ascending",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_ascending"],
    )
    parser.add_argument("--ssgsea-threads", type=int, default=METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_threads"])
    parser.add_argument("--ssgsea-seed", type=int, default=METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_seed"])

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

    _ensure_groupby_column(adata, groupby=args.groupby, parser=parser)

    params, method_kwargs = _collect_run_configuration(args)
    summary = run_enrichment(
        adata,
        method=args.method,
        groupby=args.groupby,
        source=args.source,
        species=args.species,
        gene_set=args.gene_set,
        gene_set_file=args.gene_set_file,
        fdr_threshold=args.fdr_threshold,
        n_top_terms=args.n_top_terms,
        de_method=args.de_method,
        de_corr_method=args.de_corr_method,
        **method_kwargs,
    )

    gallery_context = _prepare_enrichment_gallery_context(adata, summary)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, summary, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, input_file)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved enriched AnnData: %s", h5ad_path)

    print(
        f"Enrichment complete ({summary['method']}): "
        f"{summary.get('n_terms_tested', 0)} terms tested, "
        f"{summary.get('n_significant', 0)} significant"
    )


if __name__ == "__main__":
    main()
