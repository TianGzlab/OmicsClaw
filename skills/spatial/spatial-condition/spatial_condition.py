#!/usr/bin/env python3
"""Spatial Condition — pseudobulk condition comparison.

Core analysis functions are in skills.spatial._lib.condition.

Usage:
    python spatial_condition.py --input <preprocessed.h5ad> --output <dir> --condition-key condition --sample-key sample_id
    python spatial_condition.py --demo --output <dir>
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
from skills.spatial._lib.condition import (
    COUNT_BASED_METHODS,
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    VALID_PYDESEQ2_FIT_TYPES,
    VALID_PYDESEQ2_SIZE_FACTORS_FIT_TYPES,
    VALID_WILCOXON_ALTERNATIVES,
    run_condition_comparison,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_features,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-condition"
SKILL_VERSION = "0.3.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-condition/spatial_condition.py"
BOOL_NEGATIVE_FLAGS = {
    "pydeseq2_refit_cooks": "--no-pydeseq2-refit-cooks",
    "pydeseq2_cooks_filter": "--no-pydeseq2-cooks-filter",
    "pydeseq2_independent_filter": "--no-pydeseq2-independent-filter",
}


# ---------------------------------------------------------------------------
# Gallery helpers
# ---------------------------------------------------------------------------


def _prepare_condition_plot_state(adata, condition_key: str, cluster_key: str) -> str | None:
    """Ensure condition-analysis columns and spatial aliases are plot-ready."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()

    for column in (condition_key, cluster_key):
        if column in adata.obs.columns and not isinstance(adata.obs[column].dtype, pd.CategoricalDtype):
            adata.obs[column] = pd.Categorical(adata.obs[column].astype(str))

    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute a fallback UMAP so the standard gallery can expose an embedding view."""
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
        logger.warning("Could not compute UMAP for condition gallery: %s", exc)


def _comparison_summary_df(summary: dict) -> pd.DataFrame:
    comp_df = pd.DataFrame(summary.get("comparison_summary", []))
    if comp_df.empty:
        return pd.DataFrame(
            columns=[
                "cluster",
                "contrast",
                "method",
                "n_samples_reference",
                "n_samples_other",
                "n_genes_tested",
                "n_significant",
                "n_effect_size_hits",
            ]
        )
    return comp_df


def _build_cluster_de_metrics(summary: dict) -> pd.DataFrame:
    comp_df = _comparison_summary_df(summary)
    if comp_df.empty:
        return pd.DataFrame(
            columns=[
                "cluster",
                "n_contrasts_tested",
                "n_significant_total",
                "n_effect_size_hits_total",
                "max_significant_hits",
                "max_effect_size_hits",
            ]
        )

    metrics = (
        comp_df.groupby("cluster", observed=True)
        .agg(
            n_contrasts_tested=("contrast", "size"),
            n_significant_total=("n_significant", "sum"),
            n_effect_size_hits_total=("n_effect_size_hits", "sum"),
            max_significant_hits=("n_significant", "max"),
            max_effect_size_hits=("n_effect_size_hits", "max"),
        )
        .reset_index()
        .sort_values("n_effect_size_hits_total", ascending=False)
        .reset_index(drop=True)
    )
    return metrics


def _annotate_cluster_de_metrics_to_obs(adata, summary: dict) -> dict[str, str]:
    cluster_key = summary.get("cluster_key")
    if cluster_key not in adata.obs.columns:
        return {}

    metrics_df = _build_cluster_de_metrics(summary)
    if metrics_df.empty:
        return {}

    lookup = metrics_df.copy()
    lookup["cluster"] = lookup["cluster"].astype(str)
    lookup = lookup.set_index("cluster")
    cluster_labels = adata.obs[cluster_key].astype(str)

    mapping = {
        "cluster_significant_col": ("n_significant_total", "condition_cluster_n_significant"),
        "cluster_effect_col": ("n_effect_size_hits_total", "condition_cluster_n_effect_hits"),
        "cluster_contrasts_col": ("n_contrasts_tested", "condition_cluster_n_contrasts"),
    }

    resolved: dict[str, str] = {}
    for context_key, (source_col, obs_col) in mapping.items():
        if source_col not in lookup.columns:
            continue
        mapped = cluster_labels.map(lookup[source_col])
        adata.obs[obs_col] = pd.to_numeric(mapped, errors="coerce").fillna(0.0)
        resolved[context_key] = obs_col

    return resolved


def _build_volcano_table(summary: dict) -> pd.DataFrame:
    de = summary.get("global_de", pd.DataFrame()).copy()
    if de.empty:
        return pd.DataFrame(
            columns=[
                "gene",
                "cluster",
                "contrast",
                "log2fc",
                "pvalue",
                "pvalue_adj",
                "neg_log10_pvalue_adj",
                "is_significant",
                "is_effect_hit",
                "method",
            ]
        )

    plot_df = de.copy()
    plot_df["pvalue_adj"] = pd.to_numeric(plot_df["pvalue_adj"], errors="coerce").fillna(1.0).clip(lower=1e-300)
    plot_df["pvalue"] = pd.to_numeric(plot_df["pvalue"], errors="coerce").fillna(1.0).clip(lower=1e-300)
    plot_df["log2fc"] = pd.to_numeric(plot_df["log2fc"], errors="coerce").fillna(0.0)
    plot_df["neg_log10_pvalue_adj"] = -np.log10(plot_df["pvalue_adj"])
    plot_df["is_significant"] = plot_df["pvalue_adj"] < float(summary.get("fdr_threshold", 0.05))
    plot_df["is_effect_hit"] = plot_df["is_significant"] & (
        np.abs(plot_df["log2fc"]) >= float(summary.get("log2fc_threshold", 1.0))
    )
    preferred = [
        "gene",
        "cluster",
        "contrast",
        "log2fc",
        "pvalue",
        "pvalue_adj",
        "neg_log10_pvalue_adj",
        "is_significant",
        "is_effect_hit",
        "method",
    ]
    ordered = preferred + [col for col in plot_df.columns if col not in preferred]
    return plot_df.loc[:, ordered]


def _build_top_genes_table(summary: dict, n_top: int = 20) -> pd.DataFrame:
    volcano_df = _build_volcano_table(summary)
    if volcano_df.empty:
        return pd.DataFrame(columns=["rank", "gene", "cluster", "contrast", "log2fc", "pvalue_adj", "method"])

    sort_df = volcano_df.sort_values(
        by=["is_effect_hit", "is_significant", "pvalue_adj", "neg_log10_pvalue_adj"],
        ascending=[False, False, True, False],
        kind="mergesort",
    ).head(n_top).copy()
    sort_df.insert(0, "rank", np.arange(1, len(sort_df) + 1))
    keep_cols = ["rank", "gene", "cluster", "contrast", "log2fc", "pvalue_adj", "method"]
    return sort_df.loc[:, [col for col in keep_cols if col in sort_df.columns]]


def _build_sample_counts_table(summary: dict) -> pd.DataFrame:
    sample_counts = summary.get("sample_counts_by_condition", {})
    return pd.DataFrame(
        [{"condition": condition, "n_samples": int(count)} for condition, count in sample_counts.items()]
    )


def _build_run_summary_table(summary: dict, context: dict) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "reference_condition", "value": summary.get("reference")},
        {"metric": "condition_key", "value": summary.get("condition_key")},
        {"metric": "sample_key", "value": summary.get("sample_key")},
        {"metric": "cluster_key", "value": summary.get("cluster_key")},
        {"metric": "min_counts_per_gene", "value": summary.get("min_counts_per_gene")},
        {"metric": "min_samples_per_condition", "value": summary.get("min_samples_per_condition")},
        {"metric": "fdr_threshold", "value": summary.get("fdr_threshold")},
        {"metric": "log2fc_threshold", "value": summary.get("log2fc_threshold")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "n_samples", "value": summary.get("n_samples")},
        {"metric": "n_clusters_tested", "value": summary.get("n_clusters_tested")},
        {"metric": "n_contrasts_tested", "value": summary.get("n_contrasts_tested")},
        {"metric": "n_significant", "value": summary.get("n_significant")},
        {"metric": "n_effect_size_hits", "value": summary.get("n_effect_size_hits")},
        {"metric": "cluster_significant_column", "value": context.get("cluster_significant_col")},
        {"metric": "cluster_effect_column", "value": context.get("cluster_effect_col")},
        {"metric": "cluster_contrasts_column", "value": context.get("cluster_contrasts_col")},
    ]
    return pd.DataFrame(rows)


def _build_observation_export_table(adata, summary: dict, context: dict, basis: str) -> pd.DataFrame | None:
    condition_key = summary.get("condition_key")
    sample_key = summary.get("sample_key")
    cluster_key = summary.get("cluster_key")

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
        condition_key,
        sample_key,
        cluster_key,
        context.get("cluster_significant_col"),
        context.get("cluster_effect_col"),
        context.get("cluster_contrasts_col"),
    ):
        if column and column in adata.obs.columns:
            series = adata.obs[column]
            if pd.api.types.is_numeric_dtype(series):
                df[column] = pd.to_numeric(series, errors="coerce").fillna(0.0).to_numpy()
            else:
                df[column] = series.astype(str).to_numpy()
    return df


def _prepare_condition_gallery_context(adata, summary: dict) -> dict:
    spatial_key = _prepare_condition_plot_state(
        adata,
        condition_key=summary.get("condition_key", "condition"),
        cluster_key=summary.get("cluster_key", "leiden"),
    )
    _ensure_umap_for_gallery(adata)

    context = {
        "condition_key": summary.get("condition_key"),
        "sample_key": summary.get("sample_key"),
        "cluster_key": summary.get("cluster_key"),
        "spatial_key": spatial_key,
        "comparison_df": _comparison_summary_df(summary),
        "cluster_metrics_df": _build_cluster_de_metrics(summary),
        "sample_counts_df": _build_sample_counts_table(summary),
    }
    context.update(_annotate_cluster_de_metrics_to_obs(adata, summary))
    return context


def _build_condition_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    condition_key = summary.get("condition_key")

    if condition_key in adata.obs.columns and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="condition_spatial_context",
                role="overview",
                renderer="feature_map",
                filename="condition_spatial_context.png",
                title="Condition Labels on Tissue",
                description="Condition assignments projected onto spatial coordinates for design context.",
                params={
                    "feature": condition_key,
                    "basis": "spatial",
                    "colormap": "tab10",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (10, 8),
                },
                required_obs=[condition_key],
                required_obsm=["spatial"],
            )
        )

    plots.append(
        PlotSpec(
            plot_id="condition_volcano_overview",
            role="overview",
            renderer="volcano_plot",
            filename="pseudobulk_volcano.png",
            title="Pseudobulk Differential Expression Overview",
            description="Global pseudobulk DE volcano plot across all tested contrasts.",
        )
    )

    if context.get("cluster_effect_col") and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="condition_effect_burden_spatial",
                role="diagnostic",
                renderer="feature_map",
                filename="condition_effect_burden_spatial.png",
                title="Condition-Responsive Burden on Tissue",
                description="Cluster-level count of significant effect-size hits mapped back onto tissue coordinates.",
                params={
                    "feature": context["cluster_effect_col"],
                    "basis": "spatial",
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (10, 8),
                },
                required_obs=[context["cluster_effect_col"]],
                required_obsm=["spatial"],
            )
        )

    if context.get("cluster_effect_col") and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="condition_effect_burden_umap",
                role="diagnostic",
                renderer="feature_map",
                filename="condition_effect_burden_umap.png",
                title="Condition-Responsive Burden on UMAP",
                description="Cluster-level DE burden projected onto the shared embedding.",
                params={
                    "feature": context["cluster_effect_col"],
                    "basis": "umap",
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (8, 6),
                },
                required_obs=[context["cluster_effect_col"]],
                required_obsm=["X_umap"],
            )
        )

    if not context["comparison_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="condition_contrast_barplot",
                role="supporting",
                renderer="contrast_barplot",
                filename="condition_de_barplot.png",
                title="Condition-Responsive Genes per Contrast",
                description="Number of significant genes detected per cluster/contrast comparison.",
            )
        )

    if not context["cluster_metrics_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="condition_cluster_metrics",
                role="supporting",
                renderer="cluster_metric_barplot",
                filename="cluster_de_burden.png",
                title="Per-Cluster DE Burden",
                description="Total significant and effect-size hits summarized by cluster.",
            )
        )

    plots.append(
        PlotSpec(
            plot_id="condition_pvalue_distribution",
            role="uncertainty",
            renderer="pvalue_histogram",
            filename="condition_pvalue_distribution.png",
            title="Adjusted P-value Distribution",
            description="Distribution of adjusted p-values across all reported DE entries.",
        )
    )

    if not context["sample_counts_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="condition_sample_counts",
                role="uncertainty",
                renderer="sample_count_barplot",
                filename="sample_counts_by_condition.png",
                title="Replicate Support by Condition",
                description="Number of biological samples available for each condition.",
            )
        )

    if summary.get("skipped_contrasts"):
        plots.append(
            PlotSpec(
                plot_id="condition_skipped_contrasts",
                role="uncertainty",
                renderer="skipped_contrasts_barplot",
                filename="skipped_contrasts.png",
                title="Skipped Contrasts",
                description="Summary of skipped cluster/contrast comparisons grouped by reason.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-condition-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Condition Standard Gallery",
        description=(
            "Default OmicsClaw condition-comparison story plots: design context, "
            "global DE overview, diagnostic burden maps, supporting summaries, "
            "and uncertainty panels."
        ),
        plots=plots,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_volcano_plot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    summary = context["summary"]
    volcano_df = _build_volcano_table(summary)
    if volcano_df.empty:
        return None

    fdr_threshold = float(summary.get("fdr_threshold", 0.05))
    log2fc_threshold = float(summary.get("log2fc_threshold", 1.0))
    effect_mask = volcano_df["is_effect_hit"].astype(bool).to_numpy()
    significant_mask = volcano_df["is_significant"].astype(bool).to_numpy()
    significant_only_mask = significant_mask & ~effect_mask
    other_mask = ~significant_mask
    lfc = volcano_df["log2fc"].astype(float).to_numpy()
    neg_log_p = volcano_df["neg_log10_pvalue_adj"].astype(float).to_numpy()

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 6)), dpi=200)
    ax.scatter(lfc[other_mask], neg_log_p[other_mask], c="#8c8c8c", s=8, alpha=0.45, label="Other")
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
    ax.set_xlabel("Log2 fold change")
    ax.set_ylabel("-log10(adj. p-value)")
    ax.set_title(spec.title or f"Pseudobulk DE Overview vs {summary.get('reference', '')}")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    return fig


def _render_contrast_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    comp_df = context.get("comparison_df", pd.DataFrame())
    if comp_df.empty:
        return None

    plot_df = comp_df.sort_values("n_significant", ascending=True).copy()
    labels = [f"{row.cluster}:{row.contrast}" for row in plot_df.itertuples()]
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4, len(labels) * 0.45))),
        dpi=200,
    )
    ax.barh(labels, plot_df["n_significant"], color="#2b8cbe")
    ax.set_xlabel("Number of significant genes")
    ax.set_ylabel("Cluster / Contrast")
    ax.set_title(spec.title or "Condition-Responsive Genes per Contrast")
    fig.tight_layout()
    return fig


def _render_cluster_metric_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    metrics_df = context.get("cluster_metrics_df", pd.DataFrame())
    if metrics_df.empty:
        return None

    plot_df = metrics_df.head(12).iloc[::-1]
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(plot_df) * 0.5))),
        dpi=200,
    )
    y = np.arange(len(plot_df))
    ax.barh(y - 0.18, plot_df["n_significant_total"], height=0.32, color="#3182bd", label="Significant")
    ax.barh(y + 0.18, plot_df["n_effect_size_hits_total"], height=0.32, color="#e6550d", label="Effect-size hits")
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["cluster"].astype(str))
    ax.set_xlabel("Gene count")
    ax.set_title(spec.title or "Per-Cluster DE Burden")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def _render_pvalue_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    volcano_df = _build_volcano_table(context["summary"])
    if volcano_df.empty:
        return None

    values = volcano_df["pvalue_adj"].astype(float).clip(lower=1e-300, upper=1.0)
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
    ax.bar(sample_counts_df["condition"].astype(str), sample_counts_df["n_samples"], color="#1b9e77")
    ax.set_ylabel("Number of samples")
    ax.set_title(spec.title or "Replicate Support by Condition")
    fig.tight_layout()
    return fig


def _render_skipped_contrasts_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    skipped = context["summary"].get("skipped_contrasts", [])
    if not skipped:
        return None

    skipped_df = pd.DataFrame(skipped)
    reason_counts = skipped_df["reason"].astype(str).value_counts().sort_values(ascending=True)
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(reason_counts) * 0.6))),
        dpi=200,
    )
    ax.barh(reason_counts.index, reason_counts.values, color="#969696")
    ax.set_xlabel("Number of skipped contrasts")
    ax.set_title(spec.title or "Skipped Contrasts")
    fig.tight_layout()
    return fig


CONDITION_GALLERY_RENDERERS = {
    "feature_map": _render_feature_map,
    "volcano_plot": _render_volcano_plot,
    "contrast_barplot": _render_contrast_barplot,
    "cluster_metric_barplot": _render_cluster_metric_barplot,
    "pvalue_histogram": _render_pvalue_histogram,
    "sample_count_barplot": _render_sample_count_barplot,
    "skipped_contrasts_barplot": _render_skipped_contrasts_barplot,
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

    global_de = summary.get("global_de", pd.DataFrame())
    if global_de is not None and not global_de.empty:
        global_de.to_csv(figure_data_dir / "pseudobulk_de.csv", index=False)
    else:
        pd.DataFrame().to_csv(figure_data_dir / "pseudobulk_de.csv", index=False)

    _build_volcano_table(summary).to_csv(figure_data_dir / "pseudobulk_volcano_points.csv", index=False)
    _comparison_summary_df(summary).to_csv(figure_data_dir / "per_cluster_summary.csv", index=False)
    pd.DataFrame(summary.get("skipped_contrasts", [])).to_csv(
        figure_data_dir / "skipped_contrasts.csv",
        index=False,
    )
    context["cluster_metrics_df"].to_csv(figure_data_dir / "cluster_de_metrics.csv", index=False)
    _build_top_genes_table(summary, n_top=50).to_csv(figure_data_dir / "top_de_genes.csv", index=False)
    context["sample_counts_df"].to_csv(figure_data_dir / "sample_counts_by_condition.csv", index=False)
    _build_run_summary_table(summary, context).to_csv(figure_data_dir / "condition_run_summary.csv", index=False)

    spatial_file = None
    spatial_df = _build_observation_export_table(adata, summary, context, "spatial")
    if spatial_df is not None:
        spatial_file = "condition_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_observation_export_table(adata, summary, context, "umap")
    if umap_df is not None:
        umap_file = "condition_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "condition_key": summary.get("condition_key"),
        "sample_key": summary.get("sample_key"),
        "cluster_key": summary.get("cluster_key"),
        "reference_condition": summary.get("reference"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "available_files": {
            "pseudobulk_de": "pseudobulk_de.csv",
            "pseudobulk_volcano_points": "pseudobulk_volcano_points.csv",
            "per_cluster_summary": "per_cluster_summary.csv",
            "skipped_contrasts": "skipped_contrasts.csv",
            "cluster_de_metrics": "cluster_de_metrics.csv",
            "top_de_genes": "top_de_genes.csv",
            "sample_counts_by_condition": "sample_counts_by_condition.csv",
            "condition_run_summary": "condition_run_summary.csv",
            "condition_spatial_points": spatial_file,
            "condition_umap_points": umap_file,
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
    """Render the standard condition gallery and export figure-ready data."""
    context = gallery_context or _prepare_condition_gallery_context(adata, summary)
    recipe = _build_condition_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        CONDITION_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-condition"
        / "r_visualization"
        / "condition_publication_template.R"
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
    """Write report.md, result.json, tables, reproducibility."""
    header = generate_report_header(
        title="Spatial Condition Comparison Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Condition key": params.get("condition_key", ""),
            "Sample key": params.get("sample_key", ""),
            "Cluster key": params.get("cluster_key", ""),
            "Reference": summary.get("reference", ""),
            "Method": summary.get("method", ""),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary.get('method', '')}",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Conditions**: {', '.join(str(c) for c in summary['conditions'])}",
        f"- **Reference condition**: {summary['reference']}",
        f"- **Samples**: {summary['n_samples']}",
        f"- **Clusters with pseudobulk profiles**: {summary['n_clusters_with_pseudobulk']}",
        f"- **Clusters tested**: {summary['n_clusters_tested']}",
        f"- **Contrasts tested**: {summary['n_contrasts_tested']}",
        f"- **Total DE entries**: {summary['n_de_genes_total']}",
        f"- **Significant genes** (padj < {summary['fdr_threshold']}): {summary['n_significant']}",
        f"- **Significant + effect-size hits** (|log2FC| >= {summary['log2fc_threshold']}): {summary['n_effect_size_hits']}",
    ]

    if gallery_context and gallery_context.get("cluster_effect_col"):
        body_lines.append(f"- **Cluster effect-burden column**: `{gallery_context['cluster_effect_col']}`")

    sample_counts = summary.get("sample_counts_by_condition", {})
    if sample_counts:
        body_lines.extend(["", "### Samples Per Condition\n"])
        for condition, count in sample_counts.items():
            body_lines.append(f"- `{condition}`: {count}")

    min_samples = int(summary.get("min_samples_per_condition", 2))
    if sample_counts and any(count < max(3, min_samples) for count in sample_counts.values()):
        body_lines.extend(
            [
                "",
                "Warning: Some conditions have fewer than 3 biological replicates. "
                "Pseudobulk DE remains possible, but statistical power is limited.",
            ]
        )

    top_df = _build_top_genes_table(summary, n_top=20)
    if not top_df.empty:
        body_lines.extend(["", "### Top DE Genes\n"])
        body_lines.append("| Gene | Cluster | Contrast | Log2FC | Adj. p-value | Method |")
        body_lines.append("|------|---------|----------|--------|--------------|--------|")
        for _, row in top_df.iterrows():
            body_lines.append(
                f"| {row['gene']} | {row.get('cluster', '')} | {row.get('contrast', '')} "
                f"| {row['log2fc']:.2f} | {row['pvalue_adj']:.2e} | {row.get('method', '')} |"
            )

    skipped = summary.get("skipped_contrasts", [])
    if skipped:
        body_lines.extend(["", "### Skipped Contrasts\n"])
        for row in skipped[:10]:
            body_lines.append(f"- `{row['cluster']} / {row['contrast']}`: {row['reason']}")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    body_lines.extend(["", "## Interpretation Notes\n"])
    if "pydeseq2" in str(summary.get("method", "")):
        body_lines.extend(
            [
                "- `pydeseq2` models pseudobulk counts with a negative-binomial GLM; its main inferential threshold is the adjusted p-value.",
                "- If PyDESeq2 fell back to Wilcoxon for a contrast, that contrast will be marked explicitly in the exported tables.",
            ]
        )
    else:
        body_lines.extend(
            [
                "- `wilcoxon` here is a pseudobulk fallback on log-CPM-transformed sample profiles.",
                "- Use Wilcoxon results as lower-assumption screening output when replicate counts are too small for a stable NB model.",
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

    summary_for_json = {k: v for k, v in summary.items() if k not in ("global_de", "per_cluster_de")}
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {"params": params, **summary_for_json}
    if gallery_context:
        result_data["visualization"] = {
            "cluster_significant_column": gallery_context.get("cluster_significant_col"),
            "cluster_effect_column": gallery_context.get("cluster_effect_col"),
            "cluster_contrasts_column": gallery_context.get("cluster_contrasts_col"),
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
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    exported: list[str] = []

    global_de = summary["global_de"]
    if not global_de.empty:
        path = tables_dir / "pseudobulk_de.csv"
        global_de.to_csv(path, index=False)
        exported.append(str(path))

    comparison_summary = summary.get("comparison_summary", [])
    if comparison_summary:
        path = tables_dir / "per_cluster_summary.csv"
        pd.DataFrame(comparison_summary).to_csv(path, index=False)
        exported.append(str(path))

    skipped = summary.get("skipped_contrasts", [])
    if skipped:
        path = tables_dir / "skipped_contrasts.csv"
        pd.DataFrame(skipped).to_csv(path, index=False)
        exported.append(str(path))

    return exported


def write_reproducibility(output_dir: Path, params: dict, input_file: str | None) -> None:
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
    for pkg in ["scanpy", "anndata", "scipy", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data — creates synthetic multi-sample / multi-condition data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate synthetic multi-condition data for demo."""
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_cond_demo_") as tmp_dir:
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

    n = adata.n_obs
    rng = np.random.default_rng(42)
    adata.obs["condition"] = pd.Categorical(rng.choice(["treatment", "control"], size=n))
    adata.obs["sample_id"] = [
        f"{c}_s{i}"
        for c, i in zip(
            adata.obs["condition"].astype(str),
            rng.integers(1, 4, size=n),
        )
    ]
    adata.obs["sample_id"] = pd.Categorical(adata.obs["sample_id"].astype(str))

    logger.info("Demo: %d cells, conditions=%s", n, adata.obs["condition"].unique().tolist())
    return adata, None


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.condition_key == args.sample_key:
        parser.error("--condition-key and --sample-key must be different columns")
    if args.min_counts_per_gene < 1:
        parser.error("--min-counts-per-gene must be >= 1")
    if args.min_samples_per_condition < 1:
        parser.error("--min-samples-per-condition must be >= 1")
    if args.fdr_threshold <= 0 or args.fdr_threshold > 1:
        parser.error("--fdr-threshold must be in (0, 1]")
    if args.log2fc_threshold < 0:
        parser.error("--log2fc-threshold must be >= 0")
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
    if args.wilcoxon_alternative not in VALID_WILCOXON_ALTERNATIVES:
        parser.error(f"--wilcoxon-alternative must be one of {VALID_WILCOXON_ALTERNATIVES}")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    params = {
        "method": args.method,
        "condition_key": args.condition_key,
        "sample_key": args.sample_key,
        "cluster_key": args.cluster_key,
        "reference_condition": args.reference_condition,
        "min_counts_per_gene": args.min_counts_per_gene,
        "min_samples_per_condition": args.min_samples_per_condition,
        "fdr_threshold": args.fdr_threshold,
        "log2fc_threshold": args.log2fc_threshold,
    }

    if args.method == "pydeseq2":
        params.update(
            {
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
            "pydeseq2_fit_type": args.pydeseq2_fit_type,
            "pydeseq2_size_factors_fit_type": args.pydeseq2_size_factors_fit_type,
            "pydeseq2_refit_cooks": args.pydeseq2_refit_cooks,
            "pydeseq2_alpha": args.pydeseq2_alpha,
            "pydeseq2_cooks_filter": args.pydeseq2_cooks_filter,
            "pydeseq2_independent_filter": args.pydeseq2_independent_filter,
            "pydeseq2_n_cpus": args.pydeseq2_n_cpus,
        }
    elif args.method == "wilcoxon":
        params["wilcoxon_alternative"] = args.wilcoxon_alternative
        method_kwargs = {"wilcoxon_alternative": args.wilcoxon_alternative}
    else:
        method_kwargs = {}

    return params, method_kwargs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial Condition — pseudobulk condition comparison")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="pydeseq2", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--condition-key", default=METHOD_PARAM_DEFAULTS["common"]["condition_key"])
    parser.add_argument("--sample-key", default=METHOD_PARAM_DEFAULTS["common"]["sample_key"])
    parser.add_argument("--cluster-key", default=METHOD_PARAM_DEFAULTS["common"]["cluster_key"])
    parser.add_argument("--reference-condition", default=None)
    parser.add_argument("--min-counts-per-gene", type=int, default=METHOD_PARAM_DEFAULTS["common"]["min_counts_per_gene"])
    parser.add_argument("--min-samples-per-condition", type=int, default=METHOD_PARAM_DEFAULTS["common"]["min_samples_per_condition"])
    parser.add_argument("--fdr-threshold", type=float, default=METHOD_PARAM_DEFAULTS["common"]["fdr_threshold"])
    parser.add_argument("--log2fc-threshold", type=float, default=METHOD_PARAM_DEFAULTS["common"]["log2fc_threshold"])
    parser.add_argument("--pydeseq2-fit-type", default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_fit_type"])
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
    parser.add_argument("--pydeseq2-alpha", type=float, default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_alpha"])
    parser.add_argument("--pydeseq2-n-cpus", type=int, default=METHOD_PARAM_DEFAULTS["pydeseq2"]["pydeseq2_n_cpus"])
    parser.add_argument("--wilcoxon-alternative", default=METHOD_PARAM_DEFAULTS["wilcoxon"]["wilcoxon_alternative"])
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
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    if args.cluster_key not in adata.obs.columns:
        if args.cluster_key != "leiden":
            parser.error(
                f"--cluster-key '{args.cluster_key}' not found in adata.obs. "
                "Use an existing cluster label or omit it to auto-compute 'leiden'."
            )

        logger.info("No '%s' column — running minimal preprocessing", args.cluster_key)
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        n_hvg = min(2000, max(2, adata.n_vars - 1))
        sc.pp.highly_variable_genes(adata, n_top_genes=n_hvg, flavor="seurat")
        adata_hvg = adata[:, adata.var["highly_variable"]].copy()
        sc.pp.scale(adata_hvg, max_value=10)
        n_comps = min(50, adata_hvg.n_vars - 1, adata_hvg.n_obs - 1)
        n_comps = max(2, n_comps)
        sc.tl.pca(adata_hvg, n_comps=n_comps)
        adata.obsm["X_pca"] = adata_hvg.obsm["X_pca"]
        sc.pp.neighbors(adata, n_neighbors=15, n_pcs=min(n_comps, 30))
        sc.tl.leiden(adata, resolution=1.0, flavor="igraph")

    params, method_kwargs = _collect_run_configuration(args)

    if args.method in COUNT_BASED_METHODS and "counts" not in adata.layers:
        if adata.raw is not None:
            logger.warning(
                "Pseudobulk requires raw counts in adata.layers['counts']. "
                "Found adata.raw — will use it for aggregation."
            )
        else:
            logger.warning(
                "Pseudobulk requires raw counts in adata.layers['counts'], but none found. "
                "Falling back to adata.X — if this is log-normalized, pseudobulk sums "
                "will be statistically invalid (log(a)+log(b) != log(a+b)). "
                "Ensure preprocessing saves raw counts: adata.layers['counts'] = adata.X.copy()"
            )

    summary = run_condition_comparison(
        adata,
        condition_key=args.condition_key,
        sample_key=args.sample_key,
        reference_condition=args.reference_condition,
        cluster_key=args.cluster_key,
        method=args.method,
        min_counts_per_gene=args.min_counts_per_gene,
        min_samples_per_condition=args.min_samples_per_condition,
        fdr_threshold=args.fdr_threshold,
        log2fc_threshold=args.log2fc_threshold,
        **method_kwargs,
    )

    gallery_context = _prepare_condition_gallery_context(adata, summary)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, summary)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, input_file)

    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)
    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Condition comparison complete: {summary['n_contrasts_tested']} contrasts tested, "
        f"{summary['n_significant']} significant DE genes"
    )


if __name__ == "__main__":
    main()
