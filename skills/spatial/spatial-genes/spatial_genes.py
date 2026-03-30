#!/usr/bin/env python3
"""Spatial Genes — find spatially variable genes via multiple methods.

Supported methods:
  - morans:    Moran's I spatial autocorrelation via Squidpy (default)
  - spatialde: Gaussian process regression via SpatialDE
  - sparkx:    Non-parametric kernel test via SPARK-X in R
  - flashs:    Randomized kernel approximation (Python native, fast)

Usage:
    python spatial_genes.py --input <processed.h5ad> --output <dir>
    python spatial_genes.py --demo --output <dir>
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
import scanpy as sc
from scipy import sparse

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer, generate_report_header, write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.genes import (
    COUNT_BASED_METHODS,
    METHOD_DISPATCH,
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    VALID_MORANS_COORD_TYPES,
    VALID_MORANS_CORR_METHODS,
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

SKILL_NAME = "spatial-genes"
SKILL_VERSION = "0.4.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-genes/spatial_genes.py"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _prepare_svg_plot_state(adata) -> str | None:
    """Ensure the standard spatial aliases exist before rendering."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()
    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute a fallback UMAP so the standard gallery has a shared embedding view."""
    if "X_umap" in adata.obsm:
        return
    try:
        if "connectivities" not in adata.obsp:
            if "X_pca" in adata.obsm:
                sc.pp.neighbors(adata, use_rep="X_pca")
            else:
                sc.pp.neighbors(adata)
        sc.tl.umap(adata)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Could not compute UMAP for SVG gallery: %s", exc)


def _extract_gene_values(adata, gene: str) -> np.ndarray:
    values = adata[:, [gene]].X
    if sparse.issparse(values):
        return np.asarray(values.toarray()).reshape(-1)
    return np.asarray(values).reshape(-1)


def _prepare_svg_export_table(svg_df: pd.DataFrame, summary: dict) -> pd.DataFrame:
    csv_df = svg_df.copy()
    if "gene" not in csv_df.columns:
        csv_df["gene"] = csv_df.index

    score_column = summary.get("score_column")
    significance_column = summary.get("significance_column")

    preferred_cols = ["gene"]
    if score_column in csv_df.columns:
        preferred_cols.append(score_column)
    if significance_column and significance_column in csv_df.columns:
        preferred_cols.append(significance_column)
    preferred_cols.extend(
        c
        for c in ["pval", "pval_norm", "qval", "var_norm", "l", "pval_z_sim"]
        if c in csv_df.columns and c not in preferred_cols
    )
    ordered_cols = preferred_cols + [c for c in csv_df.columns if c not in preferred_cols]
    return csv_df.loc[:, ordered_cols]


def _sort_svg_table(svg_df: pd.DataFrame, summary: dict) -> pd.DataFrame:
    score_column = summary.get("score_column")
    significance_column = summary.get("significance_column")
    sortable = _prepare_svg_export_table(svg_df, summary)

    if significance_column and significance_column in sortable.columns:
        sort_cols = [significance_column]
        ascending = [True]
        if score_column and score_column in sortable.columns and score_column != significance_column:
            sort_cols.append(score_column)
            ascending.append(False)
        return sortable.sort_values(sort_cols, ascending=ascending, kind="mergesort")

    if score_column and score_column in sortable.columns:
        return sortable.sort_values(score_column, ascending=False, kind="mergesort")

    return sortable


def _get_top_svg_table(svg_df: pd.DataFrame, summary: dict, n_top: int = 12) -> pd.DataFrame:
    score_column = summary.get("score_column")
    significance_column = summary.get("significance_column")
    export_df = _prepare_svg_export_table(svg_df, summary)
    by_gene = export_df.set_index("gene", drop=False)
    rows: list[dict] = []

    for rank, gene in enumerate(summary.get("top_genes", [])[:n_top], start=1):
        if gene not in by_gene.index:
            continue
        row = by_gene.loc[gene]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        record = row.to_dict()
        record["rank"] = rank
        rows.append(record)

    if rows:
        return pd.DataFrame(rows)

    fallback = _sort_svg_table(svg_df, summary).head(n_top).copy()
    if not fallback.empty:
        fallback["rank"] = np.arange(1, len(fallback) + 1)
        return fallback

    empty_columns = ["rank", "gene"]
    if score_column:
        empty_columns.append(score_column)
    if significance_column and significance_column not in empty_columns:
        empty_columns.append(significance_column)
    return pd.DataFrame(columns=empty_columns)


def _build_significant_svg_table(svg_df: pd.DataFrame, summary: dict) -> pd.DataFrame:
    export_df = _prepare_svg_export_table(svg_df, summary)
    significance_column = summary.get("significance_column")
    score_column = summary.get("score_column")
    if significance_column is None or significance_column not in export_df.columns:
        return export_df.iloc[0:0].copy()

    significant_df = export_df[pd.to_numeric(export_df[significance_column], errors="coerce") < summary["fdr_threshold"]].copy()
    if summary.get("method") == "morans" and score_column and score_column in significant_df.columns:
        significant_df = significant_df[pd.to_numeric(significant_df[score_column], errors="coerce") > 0].copy()

    return _sort_svg_table(significant_df, summary)


def _build_svg_run_summary_table(summary: dict) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "n_genes_tested", "value": summary.get("n_genes_tested")},
        {"metric": "n_significant", "value": summary.get("n_significant")},
        {"metric": "n_top_reported", "value": summary.get("n_top_reported")},
        {"metric": "fdr_threshold", "value": summary.get("fdr_threshold")},
        {"metric": "score_column", "value": summary.get("score_column")},
        {"metric": "score_label", "value": summary.get("score_label")},
        {"metric": "significance_column", "value": summary.get("significance_column")},
        {"metric": "significance_label", "value": summary.get("significance_label")},
    ]
    for key in (
        "n_neighs",
        "n_perms",
        "corr_method",
        "coord_type",
        "run_aeh",
        "min_counts_per_gene",
        "aeh_patterns",
        "aeh_lengthscale",
        "sparkx_num_cores",
        "sparkx_option",
        "sparkx_max_genes",
        "n_random_features",
        "bandwidth",
    ):
        if key in summary:
            rows.append({"metric": key, "value": summary.get(key)})
    return pd.DataFrame(rows)


def _annotate_svg_metrics_to_obs(adata, gallery_genes: list[str]) -> dict[str, str]:
    valid_genes = [gene for gene in gallery_genes if gene in adata.var_names]
    if not valid_genes:
        return {}

    matrix = adata[:, valid_genes].X
    if sparse.issparse(matrix):
        matrix = matrix.toarray()
    else:
        matrix = np.asarray(matrix)

    mean_col = "svg_top_gene_mean_expression"
    max_col = "svg_top_gene_max_expression"
    count_col = "svg_top_gene_detected_count"
    dominant_col = "svg_top_gene_dominant"

    adata.obs[mean_col] = matrix.mean(axis=1)
    adata.obs[max_col] = matrix.max(axis=1)
    adata.obs[count_col] = (matrix > 0).sum(axis=1).astype(int)

    dominant_idx = np.argmax(matrix, axis=1)
    dominant_values = np.array(valid_genes, dtype=object)[dominant_idx]
    dominant_values = np.where(matrix.max(axis=1) > 0, dominant_values, "none")
    adata.obs[dominant_col] = pd.Categorical(dominant_values.astype(str))

    return {
        "mean_expression_col": mean_col,
        "max_expression_col": max_col,
        "detected_count_col": count_col,
        "dominant_gene_col": dominant_col,
    }


def _build_svg_observation_metrics_table(
    adata,
    metric_columns: dict[str, str],
    *,
    spatial_key: str | None,
    embedding_key: str | None,
) -> pd.DataFrame:
    obs_df = pd.DataFrame({"observation": adata.obs_names.astype(str)})

    for column in metric_columns.values():
        if column not in adata.obs.columns:
            continue
        series = adata.obs[column]
        obs_df[column] = series.astype(str) if isinstance(series.dtype, pd.CategoricalDtype) else series.to_numpy()

    if spatial_key and spatial_key in adata.obsm:
        coords = np.asarray(adata.obsm[spatial_key])
        if coords.shape[1] >= 2:
            obs_df["x"] = coords[:, 0]
            obs_df["y"] = coords[:, 1]

    if embedding_key and embedding_key in adata.obsm:
        coords = np.asarray(adata.obsm[embedding_key])
        if coords.shape[1] >= 2:
            obs_df["umap_1"] = coords[:, 0]
            obs_df["umap_2"] = coords[:, 1]

    return obs_df


def _select_gallery_genes(adata, svg_df: pd.DataFrame, summary: dict, limit: int = 8) -> list[str]:
    top_table = _get_top_svg_table(svg_df, summary, n_top=max(limit, summary.get("n_top_reported", limit)))
    genes: list[str] = []
    for gene in top_table.get("gene", []):
        if gene in adata.var_names and gene not in genes:
            genes.append(gene)
        if len(genes) >= limit:
            break
    return genes


def _build_svg_visualization_recipe(
    adata,
    svg_df: pd.DataFrame,
    summary: dict,
    gallery_genes: list[str],
) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    score_column = summary.get("score_column")
    significance_column = summary.get("significance_column")

    if gallery_genes and "spatial" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="svg_spatial_overview",
                role="overview",
                renderer="feature_map",
                filename="top_svg_spatial.png",
                title="Top Spatially Variable Genes",
                description="Top-ranked spatially variable genes projected onto tissue coordinates.",
                params={
                    "feature": gallery_genes,
                    "basis": "spatial",
                    "colormap": "magma",
                    "show_colorbar": True,
                    "show_axes": False,
                    "figure_size": (14, 9),
                },
                required_obsm=["spatial"],
            )
        )

    if gallery_genes and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="svg_umap_overview",
                role="overview",
                renderer="feature_map",
                filename="top_svg_umap.png",
                title="Top SVGs on UMAP",
                description="Embedding view for the top-ranked spatially variable genes.",
                params={
                    "feature": gallery_genes[:6],
                    "basis": "umap",
                    "colormap": "magma",
                    "show_colorbar": True,
                    "show_axes": False,
                    "figure_size": (12, 8),
                },
                required_obsm=["X_umap"],
            )
        )

    if score_column and score_column in svg_df.columns:
        plots.append(
            PlotSpec(
                plot_id="svg_top_scores",
                role="supporting",
                renderer="svg_score_barplot",
                filename="top_svg_scores.png",
                title="Top SVG Scores",
                description="Score summary for the top reported genes.",
                params={"n_top": min(12, max(summary.get("n_top_reported", 0), len(gallery_genes), 6))},
            )
        )

    if score_column and significance_column and significance_column in svg_df.columns:
        plots.append(
            PlotSpec(
                plot_id="svg_score_significance_diagnostic",
                role="diagnostic",
                renderer="svg_score_significance_scatter",
                filename="svg_score_vs_significance.png",
                title="Score vs Significance",
                description="Method score plotted against statistical significance for all tested genes.",
                params={"label_top_n": min(6, max(len(gallery_genes), 4))},
            )
        )

    if summary["method"] == "morans" and "moranI" in adata.uns:
        plots.append(
            PlotSpec(
                plot_id="svg_moran_ranking",
                role="diagnostic",
                renderer="moran_ranking",
                filename="moran_ranking.png",
                title="Moran Ranking Overview",
                description="Top Moran's I genes ranked by spatial autocorrelation.",
                required_uns=["moranI"],
            )
        )

    if significance_column and significance_column in svg_df.columns:
        plots.append(
            PlotSpec(
                plot_id="svg_significance_distribution",
                role="uncertainty",
                renderer="svg_significance_histogram",
                filename="svg_significance_distribution.png",
                title="Significance Distribution",
                description="Distribution of method-specific p-values or q-values across all tested genes.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-svg-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Genes Standard Gallery",
        description=(
            "Default OmicsClaw SVG story plots: overview maps, method diagnostics, "
            "supporting rankings, and uncertainty summaries."
        ),
        plots=plots,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_moran_ranking(adata, spec: PlotSpec, _context: dict) -> object:
    params = VizParams(
        subtype="moran",
        title=spec.title,
        figure_size=spec.params.get("figure_size"),
        dpi=int(spec.params.get("dpi", 200)),
        colormap=spec.params.get("colormap", "viridis"),
    )
    return plot_spatial_stats(adata, params)


def _render_svg_score_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    score_column = context["summary"].get("score_column")
    if score_column is None:
        return None

    top_df = _get_top_svg_table(context["svg_df"], context["summary"], n_top=int(spec.params.get("n_top", 12)))
    if top_df.empty or score_column not in top_df.columns:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, max(4, len(top_df) * 0.45))), dpi=200)
    bar_values = top_df[score_column].astype(float).to_numpy()
    ax.barh(top_df["gene"], bar_values, color="#d95f02", alpha=0.9)
    ax.invert_yaxis()
    ax.set_xlabel(context["summary"].get("score_label", score_column))
    ax.set_title(spec.title or "Top SVG Scores")

    significance_column = context["summary"].get("significance_column")
    if significance_column and significance_column in top_df.columns:
        for idx, row in enumerate(top_df.itertuples(index=False)):
            sig_value = getattr(row, significance_column)
            ax.text(
                bar_values[idx],
                idx,
                f"  {significance_column}={sig_value:.2e}",
                va="center",
                ha="left",
                fontsize=8,
                color="dimgray",
            )

    fig.tight_layout()
    return fig


def _render_svg_score_significance_scatter(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    summary = context["summary"]
    score_column = summary.get("score_column")
    significance_column = summary.get("significance_column")
    if score_column is None or significance_column is None:
        return None

    svg_df = context["svg_df"]
    if score_column not in svg_df.columns or significance_column not in svg_df.columns:
        return None

    plot_df = svg_df.copy()
    if "gene" not in plot_df.columns:
        plot_df["gene"] = plot_df.index
    plot_df = plot_df.loc[:, ["gene", score_column, significance_column]].dropna()
    if plot_df.empty:
        return None

    significance_values = plot_df[significance_column].astype(float).clip(lower=1e-300)
    neglog_significance = -np.log10(significance_values)

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 6)), dpi=200)
    ax.scatter(
        plot_df[score_column].astype(float),
        neglog_significance,
        s=24,
        alpha=0.65,
        color="#3182bd",
        edgecolors="none",
    )
    ax.set_xlabel(summary.get("score_label", score_column))
    ax.set_ylabel(f"-log10({summary.get('significance_label', significance_column)})")
    ax.set_title(spec.title or "Score vs Significance")

    label_top_n = int(spec.params.get("label_top_n", 6))
    top_df = _get_top_svg_table(svg_df, summary, n_top=label_top_n)
    for row in top_df.itertuples(index=False):
        gene = getattr(row, "gene", None)
        if gene is None:
            continue
        gene_row = plot_df.loc[plot_df["gene"] == gene]
        if gene_row.empty:
            continue
        x_val = float(gene_row.iloc[0][score_column])
        y_val = float(-np.log10(max(float(gene_row.iloc[0][significance_column]), 1e-300)))
        ax.text(x_val, y_val, f" {gene}", fontsize=8, color="#08306b")

    fig.tight_layout()
    return fig


def _render_svg_significance_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    summary = context["summary"]
    significance_column = summary.get("significance_column")
    if significance_column is None or significance_column not in context["svg_df"].columns:
        return None

    values = (
        context["svg_df"][significance_column]
        .dropna()
        .astype(float)
        .clip(lower=0.0, upper=1.0)
    )
    if values.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(values, bins=20, color="#756bb1", edgecolor="white", alpha=0.9)
    ax.axvline(summary["fdr_threshold"], color="#cb181d", linestyle="--", linewidth=1.5)
    ax.set_xlabel(summary.get("significance_label", significance_column))
    ax.set_ylabel("Number of genes")
    ax.set_title(spec.title or "Significance Distribution")
    fig.tight_layout()
    return fig


SVG_GALLERY_RENDERERS = {
    "feature_map": _render_feature_map,
    "moran_ranking": _render_moran_ranking,
    "svg_score_barplot": _render_svg_score_barplot,
    "svg_score_significance_scatter": _render_svg_score_significance_scatter,
    "svg_significance_histogram": _render_svg_significance_histogram,
}


def _build_feature_point_table(
    adata,
    basis_key: str,
    basis_columns: tuple[str, str],
    genes: list[str],
    svg_df: pd.DataFrame,
    summary: dict,
) -> pd.DataFrame | None:
    if basis_key not in adata.obsm or not genes:
        return None

    coords = np.asarray(adata.obsm[basis_key])
    if coords.shape[1] < 2:
        return None

    ranked_df = _prepare_svg_export_table(svg_df, summary).set_index("gene", drop=False)
    frames = []
    for rank, gene in enumerate(genes, start=1):
        if gene not in adata.var_names:
            continue
        frame = pd.DataFrame(
            {
                "observation": adata.obs_names,
                basis_columns[0]: coords[:, 0],
                basis_columns[1]: coords[:, 1],
                "gene": gene,
                "rank": rank,
                "expression": _extract_gene_values(adata, gene),
            }
        )
        if gene in ranked_df.index:
            gene_row = ranked_df.loc[gene]
            if isinstance(gene_row, pd.DataFrame):
                gene_row = gene_row.iloc[0]
            score_column = summary.get("score_column")
            significance_column = summary.get("significance_column")
            if score_column and score_column in gene_row.index:
                frame[score_column] = float(gene_row[score_column])
            if significance_column and significance_column in gene_row.index:
                frame[significance_column] = float(gene_row[significance_column])
        frames.append(frame)

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def _prepare_svg_gallery_context(adata, svg_df: pd.DataFrame, summary: dict) -> dict:
    spatial_key = _prepare_svg_plot_state(adata)
    _ensure_umap_for_gallery(adata)
    embedding_key = "X_umap" if "X_umap" in adata.obsm else None

    gallery_genes = _select_gallery_genes(adata, svg_df, summary)
    metric_columns = _annotate_svg_metrics_to_obs(adata, gallery_genes)
    top_df = _get_top_svg_table(
        svg_df,
        summary,
        n_top=max(summary.get("n_top_reported", 0), len(gallery_genes), 8),
    )
    significant_df = _build_significant_svg_table(svg_df, summary)
    run_summary_df = _build_svg_run_summary_table(summary)

    spatial_points_df = None
    if spatial_key is not None:
        spatial_points_df = _build_feature_point_table(
            adata,
            spatial_key,
            ("x", "y"),
            gallery_genes,
            svg_df,
            summary,
        )

    umap_points_df = None
    if embedding_key is not None:
        umap_points_df = _build_feature_point_table(
            adata,
            embedding_key,
            ("umap_1", "umap_2"),
            gallery_genes[:6],
            svg_df,
            summary,
        )

    observation_metrics_df = _build_svg_observation_metrics_table(
        adata,
        metric_columns,
        spatial_key=spatial_key,
        embedding_key=embedding_key,
    )

    return {
        "spatial_key": spatial_key,
        "embedding_key": embedding_key,
        "gallery_genes": gallery_genes,
        "metric_columns": metric_columns,
        "top_df": top_df,
        "significant_df": significant_df,
        "run_summary_df": run_summary_df,
        "spatial_points_df": spatial_points_df,
        "umap_points_df": umap_points_df,
        "observation_metrics_df": observation_metrics_df,
    }


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )


def _export_figure_data(
    adata,
    output_dir: Path,
    svg_df: pd.DataFrame,
    summary: dict,
    recipe: VisualizationRecipe,
    artifacts: list,
    gallery_context: dict,
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    export_df = _prepare_svg_export_table(svg_df, summary)
    export_df.to_csv(figure_data_dir / "svg_results.csv", index=False)

    top_df = gallery_context["top_df"]
    top_df.to_csv(figure_data_dir / "top_svg_scores.csv", index=False)

    significant_df = gallery_context["significant_df"]
    significant_df.to_csv(figure_data_dir / "significant_svgs.csv", index=False)

    run_summary_df = gallery_context["run_summary_df"]
    run_summary_df.to_csv(figure_data_dir / "svg_run_summary.csv", index=False)

    observation_metrics_df = gallery_context["observation_metrics_df"]
    observation_metrics_df.to_csv(figure_data_dir / "svg_observation_metrics.csv", index=False)

    gallery_genes = gallery_context["gallery_genes"]

    spatial_file = None
    spatial_points = gallery_context["spatial_points_df"]
    if spatial_points is not None and not spatial_points.empty:
        spatial_file = "top_svg_spatial_points.csv"
        spatial_points.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_points = gallery_context["umap_points_df"]
    if umap_points is not None and not umap_points.empty:
        umap_file = "top_svg_umap_points.csv"
        umap_points.to_csv(figure_data_dir / umap_file, index=False)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary["method"],
        "score_column": summary.get("score_column"),
        "score_label": summary.get("score_label"),
        "significance_column": summary.get("significance_column"),
        "significance_label": summary.get("significance_label"),
        "fdr_threshold": summary["fdr_threshold"],
        "recipe_id": recipe.recipe_id,
        "gallery_roles": [spec.role for spec in recipe.plots],
        "selected_gallery_genes": gallery_genes,
        "metric_columns": gallery_context.get("metric_columns", {}),
        "available_files": {
            "svg_results": "svg_results.csv",
            "top_svg_scores": "top_svg_scores.csv",
            "significant_svgs": "significant_svgs.csv",
            "run_summary": "svg_run_summary.csv",
            "observation_metrics": "svg_observation_metrics.csv",
            "spatial_points": spatial_file,
            "umap_points": umap_file,
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


def generate_figures(
    adata,
    output_dir: Path,
    svg_df: pd.DataFrame,
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    """Render the standard Python SVG gallery and export figure-ready data."""
    context = gallery_context or _prepare_svg_gallery_context(adata, svg_df, summary)
    recipe = _build_svg_visualization_recipe(adata, svg_df, summary, context["gallery_genes"])
    runtime_context = {"svg_df": svg_df, "summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        SVG_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, svg_df, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-genes"
        / "r_visualization"
        / "svg_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def write_report(
    output_dir: Path,
    svg_df: pd.DataFrame,
    summary: dict,
    input_file: str | None,
    params: dict,
    *,
    gallery_context: dict | None = None,
) -> None:
    """Write report.md and result.json."""
    header = generate_report_header(
        title="Spatially Variable Genes Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "FDR threshold": str(summary["fdr_threshold"]),
            "Score": str(summary.get("score_label", summary.get("score_column", ""))),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Genes tested**: {summary['n_genes_tested']}",
        f"- **Significant SVGs** (FDR < {summary['fdr_threshold']}): {summary['n_significant']}",
        f"- **Top genes reported**: {summary['n_top_reported']}",
    ]

    if gallery_context:
        metric_columns = gallery_context.get("metric_columns", {})
        if metric_columns.get("mean_expression_col"):
            body_lines.append(f"- **Top-SVG mean expression column**: `{metric_columns['mean_expression_col']}`")
        if metric_columns.get("dominant_gene_col"):
            body_lines.append(f"- **Top-SVG dominant gene column**: `{metric_columns['dominant_gene_col']}`")

    method = summary.get("method")
    if method == "morans":
        body_lines.extend(
            [
                f"- **Spatial neighbors**: {summary.get('n_neighs', 0)}",
                f"- **Permutations**: {summary.get('n_perms', 0)}",
                f"- **Correction method**: `{summary.get('corr_method', '')}`",
                f"- **Coordinate type**: `{summary.get('coord_type', '')}`",
            ]
        )
    elif method == "spatialde":
        body_lines.extend(
            [
                f"- **AEH enabled**: {summary.get('run_aeh', False)}",
                f"- **Minimum counts per gene**: {summary.get('min_counts_per_gene', 0)}",
                f"- **AEH patterns used**: {summary.get('aeh_patterns')}",
                f"- **AEH lengthscale used**: {summary.get('aeh_lengthscale')}",
            ]
        )
    elif method == "sparkx":
        body_lines.extend(
            [
                f"- **SPARK-X option**: `{summary.get('sparkx_option', '')}`",
                f"- **SPARK-X cores**: {summary.get('sparkx_num_cores', 1)}",
                f"- **SPARK-X max genes**: {summary.get('sparkx_max_genes', 0)}",
            ]
        )
    elif method == "flashs":
        body_lines.extend(
            [
                f"- **Random features**: {summary.get('n_random_features', 0)}",
                f"- **Bandwidth used**: {summary.get('bandwidth')}",
            ]
        )

    top_df = gallery_context["top_df"] if gallery_context else _get_top_svg_table(svg_df, summary, n_top=20)
    score_label = summary.get("score_label", "Score")
    score_column = summary.get("score_column", "I")
    significance_column = summary.get("significance_column")
    significance_label = summary.get("significance_label", "p-value")
    has_significance = bool(significance_column and significance_column in top_df.columns)
    if not top_df.empty:
        body_lines.extend(["", "### Top Spatially Variable Genes\n"])
        if has_significance:
            body_lines.extend(
                [
                    f"| Rank | Gene | {score_label} | {significance_label} |",
                    "|------|------|-----------|----------------|",
                ]
            )
        else:
            body_lines.extend([f"| Rank | Gene | {score_label} |", "|------|------|-----------|"])

        for _, row in top_df.head(20).iterrows():
            score_value = pd.to_numeric(pd.Series([row.get(score_column)]), errors="coerce").iloc[0]
            if has_significance:
                sig_value = pd.to_numeric(pd.Series([row.get(significance_column)]), errors="coerce").iloc[0]
                body_lines.append(
                    f"| {int(row.get('rank', 0))} | {row.get('gene', '')} | {score_value:.4f} | {sig_value:.2e} |"
                )
            else:
                body_lines.append(f"| {int(row.get('rank', 0))} | {row.get('gene', '')} | {score_value:.4f} |")

    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    body_lines.extend(["", "## Interpretation Notes\n"])
    if method == "morans":
        body_lines.extend(
            [
                "- Moran's I is a spatial autocorrelation statistic; positive values indicate local clustering rather than random spatial placement.",
                "- The result depends on the spatial neighbor graph, so `coord_type`, `n_neighs`, and permutation depth directly affect sensitivity and calibration.",
            ]
        )
    elif method == "spatialde":
        body_lines.extend(
            [
                "- SpatialDE operates on raw counts after NaiveDE stabilization and reports smooth spatial-pattern likelihood ratios with `qval`-based significance.",
                "- AEH pattern grouping is optional and should be interpreted as a secondary clustering of significant genes rather than the main test statistic.",
            ]
        )
    elif method == "sparkx":
        body_lines.extend(
            [
                "- SPARK-X is a count-based kernel test executed through the R backend; its main inferential threshold is the adjusted p-value column when available.",
                "- Wrapper-side gene capping is a runtime control and may reduce the tested gene universe on very large datasets.",
            ]
        )
    else:
        body_lines.extend(
            [
                "- FlashS here is a randomized approximation intended for fast SVG screening on larger datasets.",
                "- Treat strong FlashS hits as prioritization candidates and confirm borderline findings with a slower exact SVG method when needed.",
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

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {"params": params, **summary}
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-svg-gallery",
            "gallery_genes": gallery_context.get("gallery_genes", []),
            **gallery_context.get("metric_columns", {}),
        }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data=result_data,
        input_checksum=checksum,
    )
    _write_r_visualization_helper(output_dir)


def export_tables(
    output_dir: Path,
    svg_df: pd.DataFrame,
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    context = gallery_context or {}
    exported: list[str] = []

    export_df = _prepare_svg_export_table(svg_df, summary)
    path = tables_dir / "svg_results.csv"
    export_df.to_csv(path, index=False)
    exported.append(str(path))

    top_df = context.get("top_df", _get_top_svg_table(svg_df, summary, n_top=20))
    path = tables_dir / "top_svg_scores.csv"
    top_df.to_csv(path, index=False)
    exported.append(str(path))

    significant_df = context.get("significant_df", _build_significant_svg_table(svg_df, summary))
    path = tables_dir / "significant_svgs.csv"
    significant_df.to_csv(path, index=False)
    exported.append(str(path))

    observation_metrics_df = context.get("observation_metrics_df")
    if observation_metrics_df is not None:
        path = tables_dir / "svg_observation_metrics.csv"
        observation_metrics_df.to_csv(path, index=False)
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
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cmd += f" {flag}"
            continue
        if value in (None, ""):
            continue
        cmd += f" {flag} {shlex.quote(str(value))}"

    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore

    env_lines = []
    for pkg in [
        "scanpy",
        "anndata",
        "numpy",
        "pandas",
        "matplotlib",
        "scipy",
        "squidpy",
        "statsmodels",
        "SpatialDE",
        "NaiveDE",
    ]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def get_demo_data(output_dir: Path):
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    with tempfile.TemporaryDirectory(prefix="svg_demo_") as tmpdir:
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmpdir)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")
        h5ad_path = Path(tmpdir) / "processed.h5ad"
        adata = sc.read_h5ad(h5ad_path)
        dest = output_dir / "processed.h5ad"
        if not dest.exists():
            import shutil
            shutil.copy2(h5ad_path, dest)
    return adata, None


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.morans_n_neighs < 1:
        parser.error("--morans-n-neighs must be >= 1")
    if args.morans_n_perms < 0:
        parser.error("--morans-n-perms must be >= 0")
    if args.spatialde_min_counts < 1:
        parser.error("--spatialde-min-counts must be >= 1")
    if args.spatialde_aeh_patterns is not None and args.spatialde_aeh_patterns < 2:
        parser.error("--spatialde-aeh-patterns must be >= 2")
    if args.spatialde_aeh_lengthscale is not None and args.spatialde_aeh_lengthscale <= 0:
        parser.error("--spatialde-aeh-lengthscale must be > 0")
    if args.sparkx_num_cores < 1:
        parser.error("--sparkx-num-cores must be >= 1")
    if args.sparkx_max_genes < 0:
        parser.error("--sparkx-max-genes must be >= 0")
    if args.flashs_n_rand_features < 1:
        parser.error("--flashs-n-rand-features must be >= 1")
    if args.flashs_bandwidth is not None and args.flashs_bandwidth <= 0:
        parser.error("--flashs-bandwidth must be > 0")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    params = {
        "method": args.method,
        "n_top_genes": args.n_top_genes,
        "fdr_threshold": args.fdr_threshold,
    }

    if args.method == "morans":
        params.update(
            {
                "morans_n_neighs": args.morans_n_neighs,
                "morans_n_perms": args.morans_n_perms,
                "morans_corr_method": args.morans_corr_method,
                "morans_coord_type": args.morans_coord_type,
            }
        )
        method_kwargs = {
            "n_neighs": args.morans_n_neighs,
            "n_perms": args.morans_n_perms,
            "corr_method": args.morans_corr_method,
            "coord_type": args.morans_coord_type,
        }
    elif args.method == "spatialde":
        if args.spatialde_no_aeh and (
            args.spatialde_aeh_patterns is not None or args.spatialde_aeh_lengthscale is not None
        ):
            logger.warning(
                "Ignoring --spatialde-aeh-patterns / --spatialde-aeh-lengthscale because --spatialde-no-aeh was set."
            )
        run_aeh = not args.spatialde_no_aeh
        params.update(
            {
                "spatialde_no_aeh": args.spatialde_no_aeh,
                "spatialde_min_counts": args.spatialde_min_counts,
                "spatialde_aeh_patterns": args.spatialde_aeh_patterns if run_aeh else None,
                "spatialde_aeh_lengthscale": args.spatialde_aeh_lengthscale if run_aeh else None,
            }
        )
        method_kwargs = {
            "run_aeh": run_aeh,
            "min_counts_per_gene": args.spatialde_min_counts,
            "aeh_patterns": args.spatialde_aeh_patterns if run_aeh else None,
            "aeh_lengthscale": args.spatialde_aeh_lengthscale if run_aeh else None,
        }
    elif args.method == "sparkx":
        params.update(
            {
                "sparkx_num_cores": args.sparkx_num_cores,
                "sparkx_option": args.sparkx_option,
                "sparkx_max_genes": args.sparkx_max_genes,
            }
        )
        method_kwargs = {
            "num_cores": args.sparkx_num_cores,
            "option": args.sparkx_option,
            "n_max_genes": args.sparkx_max_genes,
        }
    elif args.method == "flashs":
        params.update(
            {
                "flashs_n_rand_features": args.flashs_n_rand_features,
                "flashs_bandwidth": args.flashs_bandwidth,
            }
        )
        method_kwargs = {
            "n_rand_features": args.flashs_n_rand_features,
            "bandwidth": args.flashs_bandwidth,
        }
    else:
        method_kwargs = {}

    return params, method_kwargs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial Genes — SVG detection")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="morans")
    parser.add_argument("--n-top-genes", type=int, default=20)
    parser.add_argument("--fdr-threshold", type=float, default=0.05)
    parser.add_argument(
        "--morans-n-neighs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["morans"]["n_neighs"],
    )
    parser.add_argument(
        "--morans-n-perms",
        type=int,
        default=METHOD_PARAM_DEFAULTS["morans"]["n_perms"],
        help="Permutation depth for Moran's I. Set to 0 to disable permutations.",
    )
    parser.add_argument(
        "--morans-corr-method",
        choices=list(VALID_MORANS_CORR_METHODS),
        default=METHOD_PARAM_DEFAULTS["morans"]["corr_method"],
    )
    parser.add_argument(
        "--morans-coord-type",
        choices=list(VALID_MORANS_COORD_TYPES),
        default=METHOD_PARAM_DEFAULTS["morans"]["coord_type"],
        help="Neighbor graph layout. 'auto' lets Squidpy infer grid vs generic coordinates.",
    )
    parser.add_argument("--spatialde-no-aeh", action="store_true")
    parser.add_argument(
        "--spatialde-min-counts",
        type=int,
        default=METHOD_PARAM_DEFAULTS["spatialde"]["min_counts_per_gene"],
        help="Minimum total counts per gene before running SpatialDE.",
    )
    parser.add_argument("--spatialde-aeh-patterns", type=int, default=None)
    parser.add_argument("--spatialde-aeh-lengthscale", type=float, default=None)
    parser.add_argument(
        "--sparkx-num-cores",
        type=int,
        default=METHOD_PARAM_DEFAULTS["sparkx"]["num_cores"],
    )
    parser.add_argument(
        "--sparkx-option",
        default=METHOD_PARAM_DEFAULTS["sparkx"]["option"],
        help="SPARK-X option argument. The official example uses 'mixture'.",
    )
    parser.add_argument(
        "--sparkx-max-genes",
        type=int,
        default=METHOD_PARAM_DEFAULTS["sparkx"]["n_max_genes"],
        help="Wrapper-level cap for SPARK-X on very large matrices; 0 disables subsetting.",
    )
    parser.add_argument(
        "--flashs-n-rand-features",
        type=int,
        default=METHOD_PARAM_DEFAULTS["flashs"]["n_rand_features"],
    )
    parser.add_argument(
        "--flashs-bandwidth",
        type=float,
        default=METHOD_PARAM_DEFAULTS["flashs"]["bandwidth"],
        help="Optional kernel bandwidth override for FlashS. Default is data-adaptive.",
    )
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data(output_dir)
    elif args.input_path:
        import scanpy as sc

        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr); sys.exit(1)

    params, method_kwargs = _collect_run_configuration(args)

    # Validate input matrix availability for count-based methods.
    if args.method in COUNT_BASED_METHODS and "counts" not in adata.layers:
        if adata.raw is not None:
            logger.warning(
                "Method '%s' expects raw counts in adata.layers['counts']. "
                "Found adata.raw — will copy to layers['counts'].", args.method,
            )
        else:
            logger.warning(
                "Method '%s' expects raw counts in adata.layers['counts'], but none found. "
                "Falling back to adata.X — results may be suboptimal. "
                "Ensure preprocessing saves raw counts with: adata.layers['counts'] = adata.X.copy()",
                args.method,
            )

    run_fn = METHOD_DISPATCH[args.method]
    svg_df, summary = run_fn(
        adata,
        n_top_genes=args.n_top_genes,
        fdr_threshold=args.fdr_threshold,
        **method_kwargs,
    )

    adata.uns["spatial_genes_results"] = svg_df.copy()
    adata.uns["spatial_genes_summary"] = summary.copy()
    gallery_context = _prepare_svg_gallery_context(adata, svg_df, summary)
    adata.uns["spatial_genes_gallery"] = {
        "gallery_genes": gallery_context.get("gallery_genes", []),
        **gallery_context.get("metric_columns", {}),
    }
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)
    generate_figures(adata, output_dir, svg_df, summary, gallery_context=gallery_context)
    export_tables(output_dir, svg_df, summary, gallery_context=gallery_context)
    write_report(output_dir, svg_df, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, input_file)

    adata.write_h5ad(output_dir / "processed.h5ad")
    print(f"SVG detection complete: {summary['n_significant']} significant genes ({summary['method']})")


if __name__ == "__main__":
    main()
