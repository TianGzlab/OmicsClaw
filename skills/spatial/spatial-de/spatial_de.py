#!/usr/bin/env python3
"""Spatial DE — marker discovery and two-group differential expression.

This wrapper exposes:

- Scanpy `wilcoxon` / `t-test` for exploratory marker discovery on log-normalized
  expression.
- Sample-aware `pydeseq2` for explicit two-group pseudobulk contrasts built from
  real biological samples.
"""

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
from skills.spatial._lib.de import (
    COUNT_BASED_METHODS,
    METHOD_PARAM_DEFAULTS,
    SCANPY_METHODS,
    SUPPORTED_METHODS,
    VALID_PYDESEQ2_FIT_TYPES,
    VALID_PYDESEQ2_SIZE_FACTORS_FIT_TYPES,
    VALID_SCANPY_CORR_METHODS,
    run_de,
    run_pydeseq2,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_expression,
    plot_features,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-de"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-de/spatial_de.py"
BOOL_NEGATIVE_FLAGS = {
    "filter_markers": "--no-filter-markers",
    "pydeseq2_refit_cooks": "--no-pydeseq2-refit-cooks",
    "pydeseq2_cooks_filter": "--no-pydeseq2-cooks-filter",
    "pydeseq2_independent_filter": "--no-pydeseq2-independent-filter",
}


# ---------------------------------------------------------------------------
# Gallery helpers
# ---------------------------------------------------------------------------


def _prepare_de_plot_state(adata, groupby: str) -> str | None:
    """Ensure shared coordinate aliases and plotting columns are ready."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()

    if groupby in adata.obs.columns and not isinstance(adata.obs[groupby].dtype, pd.CategoricalDtype):
        adata.obs[groupby] = pd.Categorical(adata.obs[groupby].astype(str))

    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute a fallback UMAP so the standard gallery has an embedding view."""
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
        logger.warning("Could not compute UMAP for DE gallery: %s", exc)


def _empty_standardized_de_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "gene",
            "group",
            "comparison",
            "direction",
            "score",
            "log2fc",
            "pvalue",
            "pvalue_adj",
            "neg_log10_pvalue_adj",
            "is_significant",
            "passes_log2fc",
            "passes_abs_log2fc",
            "passes_thresholds",
            "is_effect_hit",
        ]
    )


def _standardize_de_results(summary: dict) -> pd.DataFrame:
    """Normalize Scanpy and PyDESeq2 DE tables into one plotting/export contract."""
    df = summary.get("full_df", pd.DataFrame()).copy()
    if df.empty:
        return _empty_standardized_de_table()

    is_scanpy = summary.get("method") in SCANPY_METHODS
    gene_source = "names" if is_scanpy else "gene"
    lfc_source = "logfoldchanges" if is_scanpy else "log2fc"
    padj_source = "pvals_adj" if is_scanpy else "pvalue_adj"
    pval_source = "pvals" if is_scanpy else "pvalue"
    score_source = "scores" if is_scanpy else "stat"

    out = df.copy()
    if gene_source in out.columns:
        out["gene"] = out[gene_source].astype(str)
    else:
        out["gene"] = out.index.astype(str)

    for target, source in (
        ("score", score_source),
        ("log2fc", lfc_source),
        ("pvalue", pval_source),
        ("pvalue_adj", padj_source),
    ):
        if source in out.columns:
            out[target] = pd.to_numeric(out[source], errors="coerce")
        else:
            out[target] = np.nan

    if "group" not in out.columns:
        out["group"] = str(summary.get("group1") or "")
    out["group"] = out["group"].astype(str)

    if "comparison" not in out.columns:
        if summary.get("two_group"):
            out["comparison"] = f"{summary.get('group1')} vs {summary.get('group2')}"
        else:
            out["comparison"] = out["group"].astype(str) + " vs rest"
    out["comparison"] = out["comparison"].astype(str)

    if "direction" not in out.columns:
        fallback_negative = str(summary.get("group2") or "reference")
        out["direction"] = np.where(
            out["log2fc"].fillna(0.0) >= 0,
            out["group"].astype(str),
            fallback_negative,
        )
    out["direction"] = out["direction"].astype(str)

    fdr_threshold = float(summary.get("fdr_threshold", 0.05))
    log2fc_threshold = float(summary.get("log2fc_threshold", 1.0))

    if "is_significant" in out.columns:
        out["is_significant"] = out["is_significant"].fillna(False).astype(bool)
    else:
        out["is_significant"] = out["pvalue_adj"].fillna(np.inf) <= fdr_threshold

    if "passes_log2fc" in out.columns:
        out["passes_log2fc"] = out["passes_log2fc"].fillna(False).astype(bool)
    else:
        out["passes_log2fc"] = out["log2fc"].fillna(-np.inf) >= log2fc_threshold

    if "passes_abs_log2fc" in out.columns:
        out["passes_abs_log2fc"] = out["passes_abs_log2fc"].fillna(False).astype(bool)
    else:
        out["passes_abs_log2fc"] = out["log2fc"].abs().fillna(0.0) >= log2fc_threshold

    if "passes_thresholds" in out.columns:
        out["passes_thresholds"] = out["passes_thresholds"].fillna(False).astype(bool)
    else:
        out["passes_thresholds"] = out["is_significant"] & out["passes_log2fc"]

    out["is_effect_hit"] = out["is_significant"] & out["passes_abs_log2fc"]
    out["neg_log10_pvalue_adj"] = -np.log10(out["pvalue_adj"].clip(lower=1e-300, upper=1.0))

    preferred = [
        "gene",
        "group",
        "comparison",
        "direction",
        "score",
        "log2fc",
        "pvalue",
        "pvalue_adj",
        "neg_log10_pvalue_adj",
        "is_significant",
        "passes_log2fc",
        "passes_abs_log2fc",
        "passes_thresholds",
        "is_effect_hit",
    ]
    ordered = preferred + [column for column in out.columns if column not in preferred]
    return out.loc[:, ordered]


def _sort_standardized_de_table(de_df: pd.DataFrame) -> pd.DataFrame:
    if de_df.empty:
        return de_df

    sortable = de_df.copy()
    sortable["_abs_log2fc"] = sortable["log2fc"].abs().fillna(0.0)
    sortable["_abs_score"] = sortable["score"].abs().fillna(0.0)
    sortable["_pvalue_adj_sort"] = sortable["pvalue_adj"].fillna(np.inf)
    sortable = sortable.sort_values(
        by=[
            "passes_thresholds",
            "is_effect_hit",
            "is_significant",
            "_abs_log2fc",
            "_abs_score",
            "_pvalue_adj_sort",
            "gene",
        ],
        ascending=[False, False, False, False, False, True, True],
        kind="mergesort",
    )
    return sortable.drop(columns=["_abs_log2fc", "_abs_score", "_pvalue_adj_sort"])


def _get_top_hits_table(summary: dict, *, de_df: pd.DataFrame | None = None, n_top: int = 20) -> pd.DataFrame:
    standardized = de_df if de_df is not None else _standardize_de_results(summary)
    if standardized.empty:
        return pd.DataFrame(
            columns=[
                "rank",
                "gene",
                "group",
                "comparison",
                "direction",
                "score",
                "log2fc",
                "pvalue_adj",
                "is_significant",
                "is_effect_hit",
                "passes_thresholds",
            ]
        )

    sorted_df = _sort_standardized_de_table(standardized)
    if summary.get("two_group"):
        top_df = sorted_df.head(n_top).copy()
    else:
        tested_groups = [str(group) for group in summary.get("tested_groups", [])]
        if not tested_groups:
            tested_groups = sorted_df["group"].astype(str).dropna().unique().tolist()

        per_group = max(1, int(np.ceil(n_top / max(len(tested_groups), 1))))
        selected_rows: list[dict] = []
        used_indices: set[int] = set()

        for group in tested_groups:
            group_df = sorted_df[sorted_df["group"].astype(str) == group].head(per_group)
            for idx, row in group_df.iterrows():
                if idx in used_indices:
                    continue
                used_indices.add(int(idx))
                selected_rows.append(row.to_dict())

        if len(selected_rows) < n_top:
            for idx, row in sorted_df.iterrows():
                if idx in used_indices:
                    continue
                used_indices.add(int(idx))
                selected_rows.append(row.to_dict())
                if len(selected_rows) >= n_top:
                    break

        top_df = pd.DataFrame(selected_rows).head(n_top).copy()

    if top_df.empty:
        return pd.DataFrame(
            columns=[
                "rank",
                "gene",
                "group",
                "comparison",
                "direction",
                "score",
                "log2fc",
                "pvalue_adj",
                "is_significant",
                "is_effect_hit",
                "passes_thresholds",
            ]
        )

    top_df.insert(0, "rank", np.arange(1, len(top_df) + 1))
    keep_cols = [
        "rank",
        "gene",
        "group",
        "comparison",
        "direction",
        "score",
        "log2fc",
        "pvalue_adj",
        "is_significant",
        "is_effect_hit",
        "passes_thresholds",
    ]
    return top_df.loc[:, [column for column in keep_cols if column in top_df.columns]]


def _select_gallery_genes(adata, summary: dict, de_df: pd.DataFrame, limit: int = 10) -> list[str]:
    top_df = _get_top_hits_table(
        summary,
        de_df=de_df,
        n_top=max(limit, int(summary.get("n_top_genes", limit)) * max(1, len(summary.get("tested_groups", [])))),
    )
    genes: list[str] = []
    for gene in top_df.get("gene", []):
        if gene in adata.var_names and gene not in genes:
            genes.append(gene)
        if len(genes) >= limit:
            break
    return genes


def _build_group_de_metrics(summary: dict, de_df: pd.DataFrame) -> pd.DataFrame:
    groups = [str(group) for group in summary.get("groups", [])]
    if de_df.empty:
        return pd.DataFrame(
            {
                "group": groups,
                "n_de_entries": [0] * len(groups),
                "n_significant": [0] * len(groups),
                "n_effect_size_hits": [0] * len(groups),
                "n_marker_hits": [0] * len(groups),
                "median_abs_log2fc": [0.0] * len(groups),
            }
        )

    metrics = (
        de_df.groupby("group", observed=True)
        .agg(
            n_de_entries=("gene", "size"),
            n_significant=("is_significant", "sum"),
            n_effect_size_hits=("is_effect_hit", "sum"),
            n_marker_hits=("passes_thresholds", "sum"),
            median_abs_log2fc=("log2fc", lambda values: float(np.nanmedian(np.abs(values))) if len(values) else 0.0),
        )
        .reset_index()
    )

    if groups:
        metrics = metrics.set_index("group").reindex(groups).fillna(0.0).reset_index()
        metrics = metrics.rename(columns={"index": "group"})

    integer_cols = ["n_de_entries", "n_significant", "n_effect_size_hits", "n_marker_hits"]
    for column in integer_cols:
        metrics[column] = pd.to_numeric(metrics[column], errors="coerce").fillna(0).astype(int)
    metrics["median_abs_log2fc"] = pd.to_numeric(metrics["median_abs_log2fc"], errors="coerce").fillna(0.0)

    return metrics.sort_values(
        by=["n_effect_size_hits", "n_marker_hits", "n_significant", "group"],
        ascending=[False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _annotate_group_de_metrics_to_obs(adata, summary: dict, group_metrics_df: pd.DataFrame) -> dict[str, str]:
    groupby = summary.get("groupby")
    if groupby not in adata.obs.columns or group_metrics_df.empty:
        return {}

    lookup = group_metrics_df.copy()
    lookup["group"] = lookup["group"].astype(str)
    lookup = lookup.set_index("group")
    group_labels = adata.obs[groupby].astype(str)

    mapping = {
        "group_significant_col": ("n_significant", "de_group_n_significant"),
        "group_effect_col": ("n_effect_size_hits", "de_group_n_effect_hits"),
        "group_marker_col": ("n_marker_hits", "de_group_n_marker_hits"),
    }

    resolved: dict[str, str] = {}
    for context_key, (source_column, obs_column) in mapping.items():
        if source_column not in lookup.columns:
            continue
        mapped = group_labels.map(lookup[source_column])
        adata.obs[obs_column] = pd.to_numeric(mapped, errors="coerce").fillna(0.0)
        resolved[context_key] = obs_column

    return resolved


def _build_sample_counts_table(summary: dict) -> pd.DataFrame:
    sample_counts = summary.get("sample_counts_by_group", {})
    return pd.DataFrame(
        [{"group": str(group), "n_samples": int(count)} for group, count in sample_counts.items()]
    )


def _build_run_summary_table(summary: dict, context: dict) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "groupby", "value": summary.get("groupby")},
        {"metric": "comparison_mode", "value": summary.get("comparison_mode")},
        {"metric": "group1", "value": summary.get("group1")},
        {"metric": "group2", "value": summary.get("group2")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "n_groups", "value": summary.get("n_groups")},
        {"metric": "n_de_genes", "value": summary.get("n_de_genes")},
        {"metric": "n_significant", "value": summary.get("n_significant")},
        {"metric": "n_effect_size_hits", "value": summary.get("n_effect_size_hits")},
        {"metric": "n_marker_hits", "value": summary.get("n_marker_hits")},
        {"metric": "fdr_threshold", "value": summary.get("fdr_threshold")},
        {"metric": "log2fc_threshold", "value": summary.get("log2fc_threshold")},
        {"metric": "group_significant_column", "value": context.get("group_significant_col")},
        {"metric": "group_effect_column", "value": context.get("group_effect_col")},
        {"metric": "group_marker_column", "value": context.get("group_marker_col")},
    ]

    if summary.get("method") == "pydeseq2":
        rows.extend(
            [
                {"metric": "sample_key", "value": summary.get("sample_key")},
                {"metric": "design_formula", "value": summary.get("design_formula")},
                {"metric": "paired_design", "value": summary.get("paired_design")},
                {"metric": "n_pseudobulk_rows", "value": summary.get("n_pseudobulk_rows")},
                {"metric": "n_pseudobulk_genes", "value": summary.get("n_pseudobulk_genes")},
                {"metric": "n_samples", "value": summary.get("n_samples")},
                {"metric": "min_cells_per_sample", "value": summary.get("min_cells_per_sample")},
                {"metric": "min_counts_per_gene", "value": summary.get("min_counts_per_gene")},
            ]
        )
    else:
        rows.extend(
            [
                {"metric": "scanpy_corr_method", "value": summary.get("scanpy_corr_method")},
                {"metric": "filter_markers", "value": summary.get("filter_markers")},
                {"metric": "scanpy_rankby_abs", "value": summary.get("scanpy_rankby_abs")},
                {"metric": "scanpy_pts", "value": summary.get("scanpy_pts")},
                {"metric": "scanpy_tie_correct", "value": summary.get("scanpy_tie_correct")},
                {"metric": "min_in_group_fraction", "value": summary.get("min_in_group_fraction")},
                {"metric": "min_fold_change", "value": summary.get("min_fold_change")},
                {"metric": "max_out_group_fraction", "value": summary.get("max_out_group_fraction")},
                {"metric": "filter_compare_abs", "value": summary.get("filter_compare_abs")},
            ]
        )

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

    for column in (
        groupby,
        context.get("group_significant_col"),
        context.get("group_effect_col"),
        context.get("group_marker_col"),
    ):
        if column and column in adata.obs.columns:
            series = adata.obs[column]
            if pd.api.types.is_numeric_dtype(series):
                df[column] = pd.to_numeric(series, errors="coerce").fillna(0.0).to_numpy()
            else:
                df[column] = series.astype(str).to_numpy()
    return df


def _prepare_de_gallery_context(adata, summary: dict) -> dict:
    spatial_key = _prepare_de_plot_state(adata, groupby=summary.get("groupby", "leiden"))
    _ensure_umap_for_gallery(adata)

    standardized_df = _standardize_de_results(summary)
    group_metrics_df = _build_group_de_metrics(summary, standardized_df)
    sample_counts_df = _build_sample_counts_table(summary)
    skipped_sample_df = pd.DataFrame(summary.get("skipped_sample_groups", []))
    top_hits_df = _get_top_hits_table(summary, de_df=standardized_df, n_top=20)
    gallery_genes = _select_gallery_genes(adata, summary, standardized_df, limit=10)

    context = {
        "groupby": summary.get("groupby"),
        "spatial_key": spatial_key,
        "standardized_df": standardized_df,
        "group_metrics_df": group_metrics_df,
        "sample_counts_df": sample_counts_df,
        "skipped_sample_df": skipped_sample_df,
        "top_hits_df": top_hits_df,
        "gallery_genes": gallery_genes,
    }
    context.update(_annotate_group_de_metrics_to_obs(adata, summary, group_metrics_df))
    return context


def _build_de_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    groupby = summary.get("groupby")
    gallery_genes = context.get("gallery_genes", [])

    if groupby in adata.obs.columns and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="de_group_spatial_context",
                role="overview",
                renderer="feature_map",
                filename="de_group_spatial_context.png",
                title="Grouping Labels on Tissue",
                description="The active `groupby` labels projected onto spatial coordinates.",
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

    if gallery_genes and groupby in adata.obs.columns:
        plots.append(
            PlotSpec(
                plot_id="de_marker_dotplot",
                role="overview",
                renderer="expression_plot",
                filename="de_marker_dotplot.png",
                title="Top Marker Expression Overview",
                description="Dotplot view of the top differential-expression hits grouped by the active labels.",
                params={
                    "feature": gallery_genes[: min(8, len(gallery_genes))],
                    "cluster_key": groupby,
                    "subtype": "dotplot",
                    "colormap": "viridis",
                    "figure_size": (11, 6),
                    "dotplot_standard_scale": "var",
                },
                required_obs=[groupby],
            )
        )

    if not context["standardized_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="de_volcano_overview",
                role="overview",
                renderer="volcano_plot",
                filename="de_volcano.png",
                title="Differential Expression Volcano Overview",
                description="Effect-size and significance overview for the strongest DE comparisons.",
            )
        )

    if context.get("group_effect_col") and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="de_effect_burden_spatial",
                role="diagnostic",
                renderer="feature_map",
                filename="de_effect_burden_spatial.png",
                title="Effect-Size Hit Burden on Tissue",
                description="Group-level DE effect-size burden mapped back onto tissue coordinates.",
                params={
                    "feature": context["group_effect_col"],
                    "basis": "spatial",
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (10, 8),
                },
                required_obs=[context["group_effect_col"]],
                required_obsm=["spatial"],
            )
        )

    if context.get("group_effect_col") and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="de_effect_burden_umap",
                role="diagnostic",
                renderer="feature_map",
                filename="de_effect_burden_umap.png",
                title="Effect-Size Hit Burden on UMAP",
                description="Group-level DE effect-size burden projected onto the shared embedding.",
                params={
                    "feature": context["group_effect_col"],
                    "basis": "umap",
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (8, 6),
                },
                required_obs=[context["group_effect_col"]],
                required_obsm=["X_umap"],
            )
        )

    if gallery_genes and groupby in adata.obs.columns:
        plots.append(
            PlotSpec(
                plot_id="de_marker_heatmap",
                role="supporting",
                renderer="expression_plot",
                filename="de_marker_heatmap.png",
                title="Top Marker Heatmap",
                description="Aggregated expression heatmap for the strongest DE hits grouped by the active labels.",
                params={
                    "feature": gallery_genes[: min(10, len(gallery_genes))],
                    "cluster_key": groupby,
                    "subtype": "heatmap",
                    "colormap": "viridis",
                    "figure_size": (11, 7),
                },
                required_obs=[groupby],
            )
        )

    if not context["top_hits_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="de_top_hits_barplot",
                role="supporting",
                renderer="top_hits_barplot",
                filename="de_top_hits_barplot.png",
                title="Top Differential Expression Hits",
                description="Top hits ranked by significance and effect size across the tested groups.",
            )
        )

    if not context["group_metrics_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="de_group_metrics",
                role="supporting",
                renderer="group_metric_barplot",
                filename="group_de_burden.png",
                title="Per-Group DE Burden",
                description="Group-level summary of significant and marker-threshold hits.",
            )
        )

    if not context["standardized_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="de_pvalue_distribution",
                role="uncertainty",
                renderer="pvalue_histogram",
                filename="de_pvalue_distribution.png",
                title="Adjusted P-value Distribution",
                description="Distribution of adjusted p-values across all DE entries.",
            )
        )

    if not context["sample_counts_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="de_sample_counts",
                role="uncertainty",
                renderer="sample_count_barplot",
                filename="sample_counts_by_group.png",
                title="Pseudobulk Sample Support",
                description="Number of pseudobulk samples available for each compared group.",
            )
        )

    if not context["skipped_sample_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="de_skipped_sample_groups",
                role="uncertainty",
                renderer="skipped_sample_groups_barplot",
                filename="skipped_sample_groups.png",
                title="Skipped Sample-Group Pseudobulks",
                description="Summary of excluded sample x group pseudobulks grouped by reason.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-de-gallery",
        skill_name=SKILL_NAME,
        title="Spatial DE Standard Gallery",
        description=(
            "Default OmicsClaw DE story plots: grouping context, top-marker summaries, "
            "DE volcano diagnostics, group-level burden maps, and uncertainty panels."
        ),
        plots=plots,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_expression_plot(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_expression(adata, VizParams(**spec.params))


def _render_volcano_plot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    de_df = context.get("standardized_df", pd.DataFrame())
    if de_df.empty:
        return None

    metrics_df = context.get("group_metrics_df", pd.DataFrame())
    if not metrics_df.empty and "group" in metrics_df.columns:
        ordered_groups = metrics_df["group"].astype(str).tolist()
    else:
        ordered_groups = de_df["group"].astype(str).drop_duplicates().tolist()

    selected_groups = ordered_groups[: min(4, len(ordered_groups))]
    if not selected_groups:
        selected_groups = de_df["group"].astype(str).drop_duplicates().tolist()[:4]

    plot_df = de_df[de_df["group"].astype(str).isin(selected_groups)].copy()
    if plot_df.empty:
        return None

    fdr_threshold = float(context["summary"].get("fdr_threshold", 0.05))
    log2fc_threshold = float(context["summary"].get("log2fc_threshold", 1.0))

    n_panels = len(selected_groups)
    n_cols = min(2, max(1, n_panels))
    n_rows = int(np.ceil(n_panels / n_cols))
    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=spec.params.get("figure_size", (6.0 * n_cols, 4.8 * n_rows)),
        dpi=200,
        squeeze=False,
    )
    axes_flat = axes.flatten()

    top_hits_df = context.get("top_hits_df", pd.DataFrame())
    labels_df = top_hits_df[top_hits_df["group"].astype(str).isin(selected_groups)].copy() if not top_hits_df.empty else pd.DataFrame()

    for idx, group in enumerate(selected_groups):
        ax = axes_flat[idx]
        group_df = plot_df[plot_df["group"].astype(str) == group]
        effect_mask = group_df["is_effect_hit"].astype(bool).to_numpy()
        significant_mask = group_df["is_significant"].astype(bool).to_numpy()
        significant_only_mask = significant_mask & ~effect_mask
        other_mask = ~significant_mask
        lfc = group_df["log2fc"].astype(float).to_numpy()
        neg_log_p = group_df["neg_log10_pvalue_adj"].astype(float).to_numpy()

        ax.scatter(lfc[other_mask], neg_log_p[other_mask], c="#8c8c8c", s=8, alpha=0.4, label="Other")
        ax.scatter(
            lfc[significant_only_mask],
            neg_log_p[significant_only_mask],
            c="#4292c6",
            s=10,
            alpha=0.7,
            label="Significant",
        )
        ax.scatter(lfc[effect_mask], neg_log_p[effect_mask], c="#d7301f", s=12, alpha=0.8, label="Effect hit")
        ax.axhline(-np.log10(fdr_threshold), ls="--", c="grey", lw=0.8)
        ax.axvline(-log2fc_threshold, ls="--", c="grey", lw=0.8)
        ax.axvline(log2fc_threshold, ls="--", c="grey", lw=0.8)
        comparison = str(group_df["comparison"].iloc[0]) if not group_df.empty else str(group)
        ax.set_title(comparison, fontsize=11)
        ax.set_xlabel("Log2 fold change")
        ax.set_ylabel("-log10(adj. p-value)")

        if not labels_df.empty:
            panel_labels = labels_df[labels_df["group"].astype(str) == group].head(3)
            for row in panel_labels.itertuples():
                matches = group_df[group_df["gene"].astype(str) == str(row.gene)]
                if matches.empty:
                    continue
                match = matches.iloc[0]
                ax.text(
                    float(match["log2fc"]),
                    float(match["neg_log10_pvalue_adj"]),
                    str(row.gene),
                    fontsize=7,
                    ha="left",
                    va="bottom",
                )

    for idx in range(n_panels, len(axes_flat)):
        axes_flat[idx].axis("off")

    handles, labels = axes_flat[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right", frameon=False, fontsize=8)
    fig.suptitle(spec.title or "Differential Expression Volcano Overview", fontsize=13, y=1.01)
    fig.tight_layout()
    return fig


def _render_top_hits_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    top_hits_df = context.get("top_hits_df", pd.DataFrame())
    if top_hits_df.empty:
        return None

    plot_df = top_hits_df.head(12).copy().iloc[::-1]
    value_column = "log2fc" if plot_df["log2fc"].notna().any() else "score"
    labels = [
        f"{row.group}:{row.gene}" if str(row.group) not in ("", "nan") else str(row.gene)
        for row in plot_df.itertuples()
    ]
    colors = ["#cb181d" if float(value) >= 0 else "#3182bd" for value in plot_df[value_column].fillna(0.0)]

    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (9.0, max(4.5, len(plot_df) * 0.45))),
        dpi=200,
    )
    ax.barh(labels, plot_df[value_column].fillna(0.0), color=colors)
    if value_column == "log2fc":
        ax.axvline(0.0, color="grey", lw=0.8)
        ax.set_xlabel("Log2 fold change")
    else:
        ax.set_xlabel("Score")
    ax.set_title(spec.title or "Top Differential Expression Hits")
    fig.tight_layout()
    return fig


def _render_group_metric_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    metrics_df = context.get("group_metrics_df", pd.DataFrame())
    if metrics_df.empty:
        return None

    plot_df = metrics_df.iloc[::-1]
    y = np.arange(len(plot_df))
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(plot_df) * 0.5))),
        dpi=200,
    )
    ax.barh(y - 0.18, plot_df["n_significant"], height=0.32, color="#3182bd", label="Significant")
    ax.barh(y + 0.18, plot_df["n_marker_hits"], height=0.32, color="#9ecae1", label="Marker hits")
    ax.scatter(plot_df["n_effect_size_hits"], y, color="#d7301f", s=28, label="Effect-size hits", zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["group"].astype(str))
    ax.set_xlabel("Gene count")
    ax.set_title(spec.title or "Per-Group DE Burden")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def _render_pvalue_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    de_df = context.get("standardized_df", pd.DataFrame())
    if de_df.empty:
        return None

    values = de_df["pvalue_adj"].astype(float).clip(lower=1e-300, upper=1.0)
    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(values, bins=25, color="#756bb1", edgecolor="white")
    ax.axvline(float(context["summary"].get("fdr_threshold", 0.05)), color="black", linestyle="--", linewidth=1.2)
    ax.set_xlabel("Adjusted p-value")
    ax.set_ylabel("Number of DE entries")
    ax.set_title(spec.title or "Adjusted P-value Distribution")
    fig.tight_layout()
    return fig


def _render_sample_count_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    sample_counts_df = context.get("sample_counts_df", pd.DataFrame())
    if sample_counts_df.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (7.5, 4.8)), dpi=200)
    labels = sample_counts_df["group"].astype(str).tolist()
    positions = np.arange(len(labels))
    ax.bar(positions, sample_counts_df["n_samples"], color="#1b9e77")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Number of samples")
    ax.set_title(spec.title or "Pseudobulk Sample Support")
    fig.tight_layout()
    return fig


def _render_skipped_sample_groups_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    skipped_df = context.get("skipped_sample_df", pd.DataFrame())
    if skipped_df.empty or "reason" not in skipped_df.columns:
        return None

    reason_counts = skipped_df["reason"].astype(str).value_counts().sort_values(ascending=True)
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(reason_counts) * 0.6))),
        dpi=200,
    )
    ax.barh(reason_counts.index, reason_counts.values, color="#969696")
    ax.set_xlabel("Number of skipped sample-group pseudobulks")
    ax.set_title(spec.title or "Skipped Sample-Group Pseudobulks")
    fig.tight_layout()
    return fig


DE_GALLERY_RENDERERS = {
    "feature_map": _render_feature_map,
    "expression_plot": _render_expression_plot,
    "volcano_plot": _render_volcano_plot,
    "top_hits_barplot": _render_top_hits_barplot,
    "group_metric_barplot": _render_group_metric_barplot,
    "pvalue_histogram": _render_pvalue_histogram,
    "sample_count_barplot": _render_sample_count_barplot,
    "skipped_sample_groups_barplot": _render_skipped_sample_groups_barplot,
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

    full_df = summary.get("full_df", pd.DataFrame())
    standardized_df = context["standardized_df"]
    top_hits_df = context["top_hits_df"]
    group_metrics_df = context["group_metrics_df"]
    sample_counts_df = context["sample_counts_df"]
    skipped_sample_df = context["skipped_sample_df"]

    full_df.to_csv(figure_data_dir / "de_full.csv", index=False)
    standardized_df.to_csv(figure_data_dir / "de_plot_points.csv", index=False)
    top_hits_df.to_csv(figure_data_dir / "markers_top.csv", index=False)
    top_hits_df.to_csv(figure_data_dir / "top_de_hits.csv", index=False)

    significant_df = standardized_df[
        standardized_df["is_significant"].fillna(False) & standardized_df["passes_abs_log2fc"].fillna(False)
    ].copy()
    significant_df.to_csv(figure_data_dir / "de_significant.csv", index=False)

    group_metrics_df.to_csv(figure_data_dir / "group_de_metrics.csv", index=False)
    sample_counts_df.to_csv(figure_data_dir / "sample_counts_by_group.csv", index=False)
    skipped_sample_df.to_csv(figure_data_dir / "skipped_sample_groups.csv", index=False)
    _build_run_summary_table(summary, context).to_csv(figure_data_dir / "de_run_summary.csv", index=False)

    spatial_file = None
    spatial_df = _build_observation_export_table(adata, summary, context, "spatial")
    if spatial_df is not None:
        spatial_file = "de_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_observation_export_table(adata, summary, context, "umap")
    if umap_df is not None:
        umap_file = "de_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "groupby": summary.get("groupby"),
        "group1": summary.get("group1"),
        "group2": summary.get("group2"),
        "comparison_mode": summary.get("comparison_mode"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "available_files": {
            "markers_top": "markers_top.csv",
            "top_de_hits": "top_de_hits.csv",
            "de_full": "de_full.csv",
            "de_plot_points": "de_plot_points.csv",
            "de_significant": "de_significant.csv",
            "group_de_metrics": "group_de_metrics.csv",
            "de_run_summary": "de_run_summary.csv",
            "sample_counts_by_group": "sample_counts_by_group.csv",
            "skipped_sample_groups": "skipped_sample_groups.csv",
            "de_spatial_points": spatial_file,
            "de_umap_points": umap_file,
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
    """Render the standard DE gallery and export figure-ready data."""
    context = gallery_context or _prepare_de_gallery_context(adata, summary)
    recipe = _build_de_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        DE_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report / exports
# ---------------------------------------------------------------------------


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-de"
        / "r_visualization"
        / "de_publication_template.R"
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
    """Write `report.md` and `result.json`."""
    comparison = (
        f"{summary.get('group1')} vs {summary.get('group2')}"
        if summary.get("two_group")
        else "cluster-vs-rest"
    )
    header = generate_report_header(
        title="Spatial Differential Expression Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", ""),
            "Groupby": summary.get("groupby", ""),
            "Comparison": comparison,
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary.get('method', '')}",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Groups in `{summary['groupby']}`**: {summary['n_groups']}",
        f"- **Tested groups**: {', '.join(str(group) for group in summary.get('tested_groups', []))}",
        f"- **Total DE entries**: {summary.get('n_de_genes', 0)}",
        f"- **Significant genes** (padj < {summary.get('fdr_threshold', 0.05)}): {summary.get('n_significant', 0)}",
        (
            f"- **Significant + effect-size hits** (|log2FC| >= {summary.get('log2fc_threshold', 1.0)}): "
            f"{summary.get('n_effect_size_hits', 0)}"
        ),
        f"- **Marker-threshold hits**: {summary.get('n_marker_hits', 0)}",
    ]

    if gallery_context and gallery_context.get("group_effect_col"):
        body_lines.append(f"- **Group effect-burden column**: `{gallery_context['group_effect_col']}`")

    if summary.get("two_group"):
        body_lines.extend(["", f"### Comparison: {summary.get('group1')} vs {summary.get('group2')}\n"])
    else:
        body_lines.extend(["", "### Cluster-vs-rest marker discovery\n"])

    if summary.get("method") == "pydeseq2":
        body_lines.extend(
            [
                f"- **Pseudobulk design**: `{summary.get('design_formula', '~ condition')}`",
                f"- **Paired design**: {summary.get('paired_design', False)}",
                f"- **Sample key**: `{summary.get('sample_key', '')}`",
                f"- **Pseudobulk rows tested**: {summary.get('n_pseudobulk_rows', 0)}",
                f"- **Genes after count filtering**: {summary.get('n_pseudobulk_genes', 0)}",
            ]
        )
        sample_counts = summary.get("sample_counts_by_group", {})
        if sample_counts:
            body_lines.append("- **Pseudobulk samples per group**:")
            for group, count in sample_counts.items():
                body_lines.append(f"  `{group}` = {count}")
    else:
        body_lines.extend(
            [
                f"- **Scanpy correction**: `{summary.get('scanpy_corr_method', '')}`",
                f"- **Filter markers**: {summary.get('filter_markers', False)}",
                f"- **Rank by abs score**: {summary.get('scanpy_rankby_abs', False)}",
                f"- **Report detection fractions (`pts`)**: {summary.get('scanpy_pts', False)}",
            ]
        )

    top_df = _get_top_hits_table(summary, n_top=20)
    if not top_df.empty:
        body_lines.extend(["", "### Top Hits\n"])
        body_lines.append("| Rank | Gene | Group | Comparison | Score | Log2FC | Adj. p-value | Direction |")
        body_lines.append("|------|------|-------|------------|-------|--------|--------------|-----------|")
        for _, row in top_df.iterrows():
            score_txt = "NA" if pd.isna(row.get("score")) else f"{float(row['score']):.2f}"
            lfc_txt = "NA" if pd.isna(row.get("log2fc")) else f"{float(row['log2fc']):.2f}"
            p_txt = "NA" if pd.isna(row.get("pvalue_adj")) else f"{float(row['pvalue_adj']):.2e}"
            body_lines.append(
                f"| {int(row['rank'])} | {row.get('gene', '')} | {row.get('group', '')} | "
                f"{row.get('comparison', '')} | {score_txt} | {lfc_txt} | {p_txt} | {row.get('direction', '')} |"
            )

    skipped_sample_groups = summary.get("skipped_sample_groups", [])
    if skipped_sample_groups:
        body_lines.extend(["", "### Skipped Sample-Group Pseudobulks\n"])
        for row in skipped_sample_groups[:10]:
            body_lines.append(
                f"- `{row['sample_id']} / {row['condition']}`: {row['reason']} (n_cells={row['n_cells']})"
            )

    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    body_lines.extend(["", "## Interpretation Notes\n"])
    if summary.get("method") == "pydeseq2":
        body_lines.extend(
            [
                "- `pydeseq2` here is a sample-aware pseudobulk analysis, not a cell-level test.",
                "- Positive log2FC means higher in `group1`; negative log2FC means higher in `group2`.",
                "- If the same biological sample contributed to both groups, OmicsClaw used a paired design (`~ sample_id + condition`).",
            ]
        )
    else:
        body_lines.extend(
            [
                "- `wilcoxon` and `t-test` here are exploratory Scanpy marker-discovery methods on log-normalized expression.",
                "- These Scanpy outputs are useful for marker ranking but are not substitute evidence for replicate-aware sample-level inference.",
                "- For biological condition inference with explicit replicates, prefer `spatial-condition` or the `pydeseq2` mode here when the comparison is truly sample-aware.",
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
        if key not in ("markers_df", "full_df", "plot_gene_map", "rank_genes_groups_key")
    }
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {"params": params, **summary_for_json}
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-de-gallery",
            "group_significant_column": gallery_context.get("group_significant_col"),
            "group_effect_column": gallery_context.get("group_effect_col"),
            "group_marker_column": gallery_context.get("group_marker_col"),
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


def export_tables(output_dir: Path, summary: dict) -> list[str]:
    """Export tabular outputs."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []
    top_hits_df = _get_top_hits_table(summary, n_top=20)
    path = tables_dir / "markers_top.csv"
    top_hits_df.to_csv(path, index=False)
    exported.append(str(path))

    full_df = summary.get("full_df", pd.DataFrame())
    path = tables_dir / "de_full.csv"
    full_df.to_csv(path, index=False)
    exported.append(str(path))

    standardized_df = _standardize_de_results(summary)
    significant_df = standardized_df[
        standardized_df["is_significant"].fillna(False) & standardized_df["passes_abs_log2fc"].fillna(False)
    ].copy()
    path = tables_dir / "de_significant.csv"
    significant_df.to_csv(path, index=False)
    exported.append(str(path))

    group_metrics_df = _build_group_de_metrics(summary, standardized_df)
    path = tables_dir / "group_de_metrics.csv"
    group_metrics_df.to_csv(path, index=False)
    exported.append(str(path))

    sample_counts_df = _build_sample_counts_table(summary)
    path = tables_dir / "sample_counts_by_group.csv"
    sample_counts_df.to_csv(path, index=False)
    exported.append(str(path))

    skipped_df = pd.DataFrame(summary.get("skipped_sample_groups", []))
    path = tables_dir / "skipped_sample_groups.csv"
    skipped_df.to_csv(path, index=False)
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
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            for item in value:
                cmd += f" --{key.replace('_', '-')} {shlex.quote(str(item))}"
            continue
        cmd += f" --{key.replace('_', '-')} {shlex.quote(str(value))}"

    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore

    env_lines = []
    for pkg in ["scanpy", "anndata", "scipy", "numpy", "pandas", "matplotlib", "pydeseq2"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo / validation helpers
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate a preprocessed demo plus synthetic biological sample IDs."""
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_de_demo_") as tmp_dir:
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

    rng = np.random.default_rng(42)
    sample_ids = np.array([f"sample_{(i % 4) + 1}" for i in range(adata.n_obs)], dtype=object)
    rng.shuffle(sample_ids)
    adata.obs["sample_id"] = sample_ids
    return adata, None


def _ensure_groupby_column(
    adata,
    *,
    groupby: str,
    parser: argparse.ArgumentParser,
) -> None:
    """Auto-compute the default Leiden labels if they are missing."""
    if groupby in adata.obs.columns:
        return
    if groupby != "leiden":
        parser.error(
            f"--groupby '{groupby}' not found in adata.obs. "
            "Use an existing annotation column or omit it to auto-compute `leiden`."
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
    if (args.group1 is None) ^ (args.group2 is None):
        parser.error("--group1 and --group2 must be provided together")
    if args.n_top_genes < 1:
        parser.error("--n-top-genes must be >= 1")
    if args.fdr_threshold <= 0 or args.fdr_threshold > 1:
        parser.error("--fdr-threshold must be in (0, 1]")
    if args.log2fc_threshold < 0:
        parser.error("--log2fc-threshold must be >= 0")
    if args.scanpy_corr_method not in VALID_SCANPY_CORR_METHODS:
        parser.error(f"--scanpy-corr-method must be one of {VALID_SCANPY_CORR_METHODS}")
    if not 0 <= args.min_in_group_fraction <= 1:
        parser.error("--min-in-group-fraction must be in [0, 1]")
    if args.min_fold_change < 0:
        parser.error("--min-fold-change must be >= 0")
    if not 0 <= args.max_out_group_fraction <= 1:
        parser.error("--max-out-group-fraction must be in [0, 1]")
    if args.min_cells_per_sample < 1:
        parser.error("--min-cells-per-sample must be >= 1")
    if args.min_counts_per_gene < 1:
        parser.error("--min-counts-per-gene must be >= 1")
    if args.pydeseq2_fit_type not in VALID_PYDESEQ2_FIT_TYPES:
        parser.error(f"--pydeseq2-fit-type must be one of {VALID_PYDESEQ2_FIT_TYPES}")
    if args.pydeseq2_size_factors_fit_type not in VALID_PYDESEQ2_SIZE_FACTORS_FIT_TYPES:
        parser.error(
            "--pydeseq2-size-factors-fit-type must be one of "
            f"{VALID_PYDESEQ2_SIZE_FACTORS_FIT_TYPES}"
        )
    if args.pydeseq2_alpha <= 0 or args.pydeseq2_alpha > 1:
        parser.error("--pydeseq2-alpha must be in (0, 1]")
    if args.pydeseq2_n_cpus < 1:
        parser.error("--pydeseq2-n-cpus must be >= 1")
    if args.method == "pydeseq2":
        if args.sample_key == args.groupby:
            parser.error("--sample-key and --groupby must be different for pydeseq2")
        if not args.demo and (args.group1 is None or args.group2 is None):
            parser.error(
                "--method pydeseq2 requires an explicit two-group comparison via --group1 and --group2"
            )


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    params = {
        "method": args.method,
        "groupby": args.groupby,
        "group1": args.group1,
        "group2": args.group2,
        "n_top_genes": args.n_top_genes,
        "fdr_threshold": args.fdr_threshold,
        "log2fc_threshold": args.log2fc_threshold,
    }

    if args.method in SCANPY_METHODS:
        params.update(
            {
                "scanpy_corr_method": args.scanpy_corr_method,
                "scanpy_rankby_abs": args.scanpy_rankby_abs,
                "scanpy_pts": args.scanpy_pts,
                "filter_markers": args.filter_markers,
                "min_in_group_fraction": args.min_in_group_fraction,
                "min_fold_change": args.min_fold_change,
                "max_out_group_fraction": args.max_out_group_fraction,
                "filter_compare_abs": args.filter_compare_abs,
            }
        )
        if args.method == "wilcoxon":
            params["scanpy_tie_correct"] = args.scanpy_tie_correct

        method_kwargs = {
            "scanpy_corr_method": args.scanpy_corr_method,
            "scanpy_rankby_abs": args.scanpy_rankby_abs,
            "scanpy_pts": args.scanpy_pts,
            "filter_markers": args.filter_markers,
            "min_in_group_fraction": args.min_in_group_fraction,
            "min_fold_change": args.min_fold_change,
            "max_out_group_fraction": args.max_out_group_fraction,
            "filter_compare_abs": args.filter_compare_abs,
        }
        if args.method == "wilcoxon":
            method_kwargs["scanpy_tie_correct"] = args.scanpy_tie_correct
    elif args.method == "pydeseq2":
        params.update(
            {
                "sample_key": args.sample_key,
                "min_cells_per_sample": args.min_cells_per_sample,
                "min_counts_per_gene": args.min_counts_per_gene,
                "pydeseq2_fit_type": args.pydeseq2_fit_type,
                "pydeseq2_size_factors_fit_type": args.pydeseq2_size_factors_fit_type,
                "pydeseq2_refit_cooks": args.pydeseq2_refit_cooks,
                "pydeseq2_alpha": args.pydeseq2_alpha,
                "pydeseq2_cooks_filter": args.pydeseq2_cooks_filter,
                "pydeseq2_independent_filter": args.pydeseq2_independent_filter,
                "pydeseq2_n_cpus": args.pydeseq2_n_cpus,
            }
        )
        method_kwargs = {
            "sample_key": args.sample_key,
            "min_cells_per_sample": args.min_cells_per_sample,
            "min_counts_per_gene": args.min_counts_per_gene,
            "pydeseq2_fit_type": args.pydeseq2_fit_type,
            "pydeseq2_size_factors_fit_type": args.pydeseq2_size_factors_fit_type,
            "pydeseq2_refit_cooks": args.pydeseq2_refit_cooks,
            "pydeseq2_alpha": args.pydeseq2_alpha,
            "pydeseq2_cooks_filter": args.pydeseq2_cooks_filter,
            "pydeseq2_independent_filter": args.pydeseq2_independent_filter,
            "pydeseq2_n_cpus": args.pydeseq2_n_cpus,
        }
    else:
        method_kwargs = {}

    return params, method_kwargs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial DE — marker discovery and two-group DE")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--groupby", default=METHOD_PARAM_DEFAULTS["common"]["groupby"])
    parser.add_argument("--group1", default=None)
    parser.add_argument("--group2", default=None)
    parser.add_argument("--method", default="wilcoxon", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--n-top-genes", type=int, default=METHOD_PARAM_DEFAULTS["common"]["n_top_genes"])
    parser.add_argument("--fdr-threshold", type=float, default=METHOD_PARAM_DEFAULTS["common"]["fdr_threshold"])
    parser.add_argument(
        "--log2fc-threshold",
        type=float,
        default=METHOD_PARAM_DEFAULTS["common"]["log2fc_threshold"],
    )

    parser.add_argument(
        "--scanpy-corr-method",
        default=METHOD_PARAM_DEFAULTS["scanpy"]["scanpy_corr_method"],
    )
    parser.add_argument(
        "--scanpy-rankby-abs",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["scanpy"]["scanpy_rankby_abs"],
    )
    parser.add_argument(
        "--scanpy-pts",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["scanpy"]["scanpy_pts"],
    )
    parser.add_argument(
        "--scanpy-tie-correct",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["wilcoxon"]["scanpy_tie_correct"],
    )
    parser.add_argument(
        "--filter-markers",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["scanpy"]["filter_markers"],
    )
    parser.add_argument(
        "--min-in-group-fraction",
        type=float,
        default=METHOD_PARAM_DEFAULTS["scanpy"]["min_in_group_fraction"],
    )
    parser.add_argument(
        "--min-fold-change",
        type=float,
        default=METHOD_PARAM_DEFAULTS["scanpy"]["min_fold_change"],
    )
    parser.add_argument(
        "--max-out-group-fraction",
        type=float,
        default=METHOD_PARAM_DEFAULTS["scanpy"]["max_out_group_fraction"],
    )
    parser.add_argument(
        "--filter-compare-abs",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["scanpy"]["filter_compare_abs"],
    )

    parser.add_argument("--sample-key", default=METHOD_PARAM_DEFAULTS["pydeseq2"]["sample_key"])
    parser.add_argument(
        "--min-cells-per-sample",
        type=int,
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["min_cells_per_sample"],
    )
    parser.add_argument(
        "--min-counts-per-gene",
        type=int,
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["min_counts_per_gene"],
    )
    parser.add_argument(
        "--pydeseq2-fit-type",
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_fit_type"],
    )
    parser.add_argument(
        "--pydeseq2-size-factors-fit-type",
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_size_factors_fit_type"],
    )
    parser.add_argument(
        "--pydeseq2-refit-cooks",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_refit_cooks"],
    )
    parser.add_argument(
        "--pydeseq2-cooks-filter",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_cooks_filter"],
    )
    parser.add_argument(
        "--pydeseq2-independent-filter",
        action=argparse.BooleanOptionalAction,
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_independent_filter"],
    )
    parser.add_argument(
        "--pydeseq2-alpha",
        type=float,
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_alpha"],
    )
    parser.add_argument(
        "--pydeseq2-n-cpus",
        type=int,
        default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_n_cpus"],
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

    _ensure_groupby_column(adata, groupby=args.groupby, parser=parser)

    if args.method == "pydeseq2" and (args.group1 is None or args.group2 is None):
        groups = sorted(adata.obs[args.groupby].astype(str).unique().tolist(), key=str)
        if len(groups) < 2:
            parser.error(f"Need at least two groups in `{args.groupby}` for pydeseq2")
        args.group1, args.group2 = str(groups[0]), str(groups[1])
        logger.warning(
            "No explicit groups supplied for demo PyDESeq2 run; using `%s` vs `%s`.",
            args.group1,
            args.group2,
        )

    if args.method in COUNT_BASED_METHODS and "counts" not in adata.layers:
        if adata.raw is not None:
            logger.warning(
                "No `layers['counts']` found; PyDESeq2 will fall back to `adata.raw`."
            )
        else:
            logger.warning(
                "No `layers['counts']` or `adata.raw` found; PyDESeq2 will fall back to `adata.X`. "
                "If `adata.X` is log-normalized, pseudobulk DE will be statistically invalid."
            )

    params, method_kwargs = _collect_run_configuration(args)

    if args.method in SCANPY_METHODS:
        summary = run_de(
            adata,
            groupby=args.groupby,
            method=args.method,
            n_top_genes=args.n_top_genes,
            group1=args.group1,
            group2=args.group2,
            fdr_threshold=args.fdr_threshold,
            log2fc_threshold=args.log2fc_threshold,
            **method_kwargs,
        )
    else:
        summary = run_pydeseq2(
            adata,
            groupby=args.groupby,
            group1=str(args.group1),
            group2=str(args.group2),
            n_top_genes=args.n_top_genes,
            fdr_threshold=args.fdr_threshold,
            log2fc_threshold=args.log2fc_threshold,
            **method_kwargs,
        )

    gallery_context = _prepare_de_gallery_context(adata, summary)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, summary)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, input_file)
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)
    adata.write_h5ad(output_dir / "processed.h5ad")

    mode = (
        f"{summary['group1']} vs {summary['group2']}"
        if summary.get("two_group")
        else "cluster-vs-rest"
    )
    print(
        "DE complete: "
        f"{summary.get('n_de_genes', 0)} entries, "
        f"{summary.get('n_significant', 0)} significant hits "
        f"({mode}, {summary.get('method')})"
    )


if __name__ == "__main__":
    main()
