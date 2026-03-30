#!/usr/bin/env python3
"""Spatial CNV — copy number variation inference.

Core analysis functions are in ``skills.spatial._lib.cnv``.

Supported methods:
  infercnvpy   Expression-based CNV inference using inferCNVpy (default)
  numbat       Haplotype-aware CNV analysis via R Numbat (requires R installation)

Usage:
    python spatial_cnv.py --input <preprocessed.h5ad> --output <dir>
    python spatial_cnv.py --demo --output <dir>
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
from scipy import sparse

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
from skills.spatial._lib.cnv import (
    COUNT_BASED_METHODS,
    INFERCNVPY_DEFAULT_EXCLUDE_CHROMOSOMES,
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    VALID_NUMBAT_GENOMES,
    run_cnv,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_cnv,
    plot_features,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-cnv"
SKILL_VERSION = "0.3.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-cnv/spatial_cnv.py"


# ---------------------------------------------------------------------------
# Shared table builders
# ---------------------------------------------------------------------------


def _prepare_cnv_plot_state(adata) -> str | None:
    """Ensure spatial aliases and categorical CNV labels are plot-ready."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()

    for column in ("cnv_leiden", "numbat_clone"):
        if column in adata.obs.columns and not isinstance(adata.obs[column].dtype, pd.CategoricalDtype):
            adata.obs[column] = pd.Categorical(adata.obs[column].astype(str))

    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute a fallback UMAP so the gallery can expose a shared embedding view."""
    if "X_umap" in adata.obsm or adata.n_obs < 3:
        return

    try:
        if "connectivities" not in adata.obsp:
            n_neighbors = max(2, min(15, adata.n_obs - 1))
            if "cnv_pca" in adata.obsm:
                sc.pp.neighbors(adata, use_rep="cnv_pca", n_neighbors=n_neighbors)
            elif "X_pca" in adata.obsm:
                sc.pp.neighbors(adata, use_rep="X_pca", n_neighbors=n_neighbors)
            elif "X_cnv" in adata.obsm:
                sc.pp.neighbors(adata, use_rep="X_cnv", n_neighbors=n_neighbors)
            else:
                sc.pp.neighbors(adata, n_neighbors=n_neighbors)
        sc.tl.umap(adata)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Could not compute UMAP for CNV gallery: %s", exc)


def _resolve_cnv_score_key(adata, summary: dict) -> str | None:
    for candidate in (summary.get("cnv_score_key"), "cnv_score", "numbat_p_cnv"):
        if (
            candidate
            and candidate in adata.obs.columns
            and pd.api.types.is_numeric_dtype(adata.obs[candidate])
        ):
            return candidate
    return None


def _resolve_cnv_label_key(adata) -> str | None:
    for candidate in ("cnv_leiden", "numbat_clone", "clone", "tumor_clone"):
        if candidate in adata.obs.columns:
            return candidate
    return None


def _resolve_uncertainty_key(adata) -> str | None:
    for candidate in ("numbat_entropy",):
        if candidate in adata.obs.columns and pd.api.types.is_numeric_dtype(adata.obs[candidate]):
            return candidate
    return None


def _get_cnv_matrix(adata) -> np.ndarray | None:
    if "X_cnv" not in adata.obsm:
        return None

    cnv_matrix = adata.obsm["X_cnv"]
    if sparse.issparse(cnv_matrix):
        return np.asarray(cnv_matrix.toarray())
    return np.asarray(cnv_matrix)


def _compute_cnv_score_series(adata, score_key: str | None) -> tuple[pd.Series | None, str | None]:
    if score_key and score_key in adata.obs.columns:
        return (
            pd.Series(
                adata.obs[score_key].astype(float).to_numpy(),
                index=adata.obs_names,
                name="cnv_score",
            ),
            score_key,
        )

    cnv_matrix = _get_cnv_matrix(adata)
    if cnv_matrix is not None:
        return (
            pd.Series(cnv_matrix.mean(axis=1), index=adata.obs_names, name="cnv_score"),
            "X_cnv_mean",
        )

    return None, None


def _build_cnv_bin_summary_table(adata) -> pd.DataFrame | None:
    cnv_matrix = _get_cnv_matrix(adata)
    if cnv_matrix is None:
        return None

    bin_summary = pd.DataFrame(
        {
            "bin_index": np.arange(cnv_matrix.shape[1]),
            "mean_cnv": cnv_matrix.mean(axis=0),
            "mean_abs_cnv": np.abs(cnv_matrix).mean(axis=0),
            "std_cnv": cnv_matrix.std(axis=0),
        }
    )

    if cnv_matrix.shape[1] == adata.n_vars:
        bin_summary.insert(1, "feature", adata.var_names.astype(str))
        for column in ("chromosome", "start", "end"):
            if column in adata.var.columns:
                bin_summary[column] = adata.var[column].to_numpy()

    return bin_summary


def _build_cnv_group_table(adata, label_key: str | None) -> pd.DataFrame | None:
    if not label_key or label_key not in adata.obs.columns:
        return None

    counts = adata.obs[label_key].astype(str).value_counts()
    total = max(int(counts.sum()), 1)
    return pd.DataFrame(
        [
            {
                "cnv_group": group,
                "n_cells": int(count),
                "proportion_pct": round(count / total * 100, 2),
            }
            for group, count in counts.items()
        ]
    )


def _build_cnv_score_table(adata, context: dict) -> pd.DataFrame:
    df = pd.DataFrame({"observation": adata.obs_names.astype(str)})

    score_series = context.get("score_series")
    score_source = context.get("score_source")
    label_key = context.get("label_key")
    uncertainty_key = context.get("uncertainty_key")

    if score_series is not None:
        df["cnv_score"] = score_series.to_numpy(dtype=float)
        if score_source and score_source in adata.obs.columns and score_source != "cnv_score":
            df[score_source] = adata.obs[score_source].astype(float).to_numpy()

    if label_key and label_key in adata.obs.columns:
        labels = adata.obs[label_key].astype(str).to_numpy()
        df["cnv_group"] = labels
        if label_key != "cnv_group":
            df[label_key] = labels

    if uncertainty_key and uncertainty_key in adata.obs.columns:
        values = adata.obs[uncertainty_key].astype(float).to_numpy()
        df["cnv_uncertainty"] = values
        if uncertainty_key != "cnv_uncertainty":
            df[uncertainty_key] = values

    for column in ("numbat_p_cnv", "numbat_clone", "numbat_entropy", "cnv_leiden"):
        if column not in adata.obs.columns or column in df.columns:
            continue
        series = adata.obs[column]
        if pd.api.types.is_numeric_dtype(series):
            df[column] = series.astype(float).to_numpy()
        else:
            df[column] = series.astype(str).to_numpy()

    return df


def _build_projection_table(adata, basis: str, context: dict) -> pd.DataFrame | None:
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
        raise ValueError(f"Unsupported projection basis '{basis}'")

    score_series = context.get("score_series")
    if score_series is not None:
        df["cnv_score"] = score_series.to_numpy(dtype=float)

    label_key = context.get("label_key")
    if label_key and label_key in adata.obs.columns:
        df["cnv_group"] = adata.obs[label_key].astype(str).to_numpy()

    uncertainty_key = context.get("uncertainty_key")
    if uncertainty_key and uncertainty_key in adata.obs.columns:
        df["cnv_uncertainty"] = adata.obs[uncertainty_key].astype(float).to_numpy()

    return df


def _build_run_summary_table(summary: dict, context: dict) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "mean_cnv_score", "value": summary.get("mean_cnv_score")},
        {"metric": "high_cnv_fraction_pct", "value": summary.get("high_cnv_fraction_pct")},
        {"metric": "score_source", "value": context.get("score_source")},
        {"metric": "label_column", "value": context.get("label_key")},
        {"metric": "uncertainty_column", "value": context.get("uncertainty_key")},
    ]

    if summary.get("high_cnv_threshold") is not None:
        rows.append({"metric": "high_cnv_threshold", "value": summary.get("high_cnv_threshold")})
    if summary.get("n_cnv_clusters") is not None:
        rows.append({"metric": "n_cnv_clusters", "value": summary.get("n_cnv_clusters")})
    if summary.get("n_cnv_calls") is not None:
        rows.append({"metric": "n_cnv_calls", "value": summary.get("n_cnv_calls")})
    if summary.get("n_cnv_groups") is not None:
        rows.append({"metric": "n_cnv_groups", "value": summary.get("n_cnv_groups")})

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _prepare_cnv_gallery_context(adata, summary: dict) -> dict:
    spatial_key = _prepare_cnv_plot_state(adata)
    _ensure_umap_for_gallery(adata)

    score_key = _resolve_cnv_score_key(adata, summary)
    label_key = _resolve_cnv_label_key(adata)
    uncertainty_key = _resolve_uncertainty_key(adata)
    score_series, score_source = _compute_cnv_score_series(adata, score_key)

    if score_series is not None and not score_series.empty:
        summary["cnv_score_min"] = round(float(score_series.min()), 4)
        summary["cnv_score_max"] = round(float(score_series.max()), 4)
        if summary.get("method") == "numbat" and score_source == "numbat_p_cnv":
            summary["high_cnv_threshold"] = 0.5
        else:
            summary["high_cnv_threshold"] = round(float(score_series.quantile(0.9)), 4)

    if label_key and label_key in adata.obs.columns:
        summary["n_cnv_groups"] = int(adata.obs[label_key].astype(str).nunique())

    return {
        "spatial_key": spatial_key,
        "score_key": score_key,
        "score_series": score_series,
        "score_source": score_source,
        "label_key": label_key,
        "uncertainty_key": uncertainty_key,
    }


def _build_cnv_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    plots: list[PlotSpec] = []

    if "X_cnv" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="cnv_heatmap_overview",
                role="overview",
                renderer="cnv_plot",
                filename="cnv_heatmap.png",
                title="CNV Heatmap",
                description="Genome-ordered CNV signal heatmap across inferred CNV bins.",
                params={
                    "subtype": "heatmap",
                    "cluster_key": context.get("label_key"),
                    "figure_size": (12, 8),
                },
                required_obsm=["X_cnv"],
            )
        )

    if context.get("spatial_key") and (context.get("score_series") is not None or "X_cnv" in adata.obsm):
        plots.append(
            PlotSpec(
                plot_id="cnv_spatial_overview",
                role="overview",
                renderer="cnv_plot",
                filename="cnv_spatial.png",
                title="Spatial CNV Score Map",
                description="Cell- or spot-level CNV score projected onto tissue coordinates.",
                params={
                    "subtype": "spatial",
                    "colormap": "RdBu_r",
                    "figure_size": (10, 8),
                },
                required_obsm=["spatial"],
            )
        )

    if context.get("score_key") and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="cnv_score_umap",
                role="diagnostic",
                renderer="feature_map",
                filename="cnv_umap.png",
                title="CNV Score on UMAP",
                description="Embedding view of the cell-level CNV score used for downstream interpretation.",
                params={
                    "feature": context["score_key"],
                    "basis": "umap",
                    "colormap": "RdBu_r",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (8, 6),
                },
                required_obs=[context["score_key"]],
                required_obsm=["X_umap"],
            )
        )

    if context.get("label_key") and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="cnv_group_umap",
                role="diagnostic",
                renderer="feature_map",
                filename="cnv_groups_umap.png",
                title="CNV Groups on UMAP",
                description="CNV-space clusters or clone assignments on the shared embedding.",
                params={
                    "feature": context["label_key"],
                    "basis": "umap",
                    "colormap": "tab20",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (8, 6),
                },
                required_obs=[context["label_key"]],
                required_obsm=["X_umap"],
            )
        )

    if context.get("label_key"):
        plots.append(
            PlotSpec(
                plot_id="cnv_group_sizes",
                role="supporting",
                renderer="category_barplot",
                filename="cnv_group_sizes.png",
                title="CNV Group Size Distribution",
                description="Counts of spots or cells assigned to each CNV cluster or clone.",
            )
        )

    if "X_cnv" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="cnv_bin_summary",
                role="supporting",
                renderer="cnv_bin_profile",
                filename="cnv_bin_summary.png",
                title="CNV Bin Signal Summary",
                description="Mean and absolute CNV signal across genome-ordered bins.",
                required_obsm=["X_cnv"],
            )
        )

    if context.get("score_series") is not None:
        plots.append(
            PlotSpec(
                plot_id="cnv_score_distribution",
                role="uncertainty",
                renderer="score_histogram",
                filename="cnv_score_distribution.png",
                title="CNV Score Distribution",
                description="Distribution of the CNV score and the threshold used to summarize high-CNV cells.",
            )
        )

    if context.get("uncertainty_key") and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="cnv_uncertainty_spatial",
                role="uncertainty",
                renderer="feature_map",
                filename="cnv_uncertainty_spatial.png",
                title="CNV Uncertainty on Tissue",
                description="Method-specific uncertainty metric projected onto spatial coordinates.",
                params={
                    "feature": context["uncertainty_key"],
                    "basis": "spatial",
                    "colormap": "viridis",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (10, 8),
                },
                required_obs=[context["uncertainty_key"]],
                required_obsm=["spatial"],
            )
        )

    if context.get("uncertainty_key"):
        plots.append(
            PlotSpec(
                plot_id="cnv_uncertainty_distribution",
                role="uncertainty",
                renderer="uncertainty_histogram",
                filename="cnv_uncertainty_distribution.png",
                title="CNV Uncertainty Distribution",
                description="Distribution of the method-specific uncertainty metric when available.",
                required_obs=[context["uncertainty_key"]],
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-cnv-gallery",
        skill_name=SKILL_NAME,
        title="Spatial CNV Standard Gallery",
        description=(
            "Default OmicsClaw CNV story plots: overview maps, method diagnostics, "
            "supporting summaries, and uncertainty panels built on shared viz primitives."
        ),
        plots=plots,
    )


def _render_cnv_plot(adata, spec: PlotSpec, context: dict) -> object:
    cluster_key = spec.params.get("cluster_key") or context.get("label_key")
    params = VizParams(
        title=spec.title,
        colormap=spec.params.get("colormap"),
        figure_size=spec.params.get("figure_size"),
        dpi=int(spec.params.get("dpi", 200)),
        cluster_key=cluster_key,
    )
    return plot_cnv(
        adata,
        params,
        subtype=spec.params.get("subtype"),
        cluster_key=cluster_key,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_category_barplot(adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    label_key = context.get("label_key")
    if not label_key or label_key not in adata.obs.columns:
        return None

    counts = adata.obs[label_key].astype(str).value_counts()
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8, max(4, len(counts) * 0.45))),
        dpi=200,
    )
    counts.plot.barh(ax=ax, color="#2b8cbe")
    ax.invert_yaxis()
    ax.set_xlabel("Number of cells / spots")
    ax.set_title(spec.title or "CNV Group Size Distribution")
    fig.tight_layout()
    return fig


def _render_cnv_bin_profile(adata, spec: PlotSpec, _context: dict) -> object:
    import matplotlib.pyplot as plt

    bin_summary = _build_cnv_bin_summary_table(adata)
    if bin_summary is None or bin_summary.empty:
        return None

    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (10, 4.8)),
        dpi=200,
    )
    ax.plot(
        bin_summary["bin_index"],
        bin_summary["mean_cnv"],
        color="#2166ac",
        linewidth=1.6,
        label="mean_cnv",
    )
    ax.plot(
        bin_summary["bin_index"],
        bin_summary["mean_abs_cnv"],
        color="#b2182b",
        linewidth=1.4,
        label="mean_abs_cnv",
    )
    ax.set_xlabel("Genome-ordered bin")
    ax.set_ylabel("Average CNV signal")
    ax.set_title(spec.title or "CNV Bin Signal Summary")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def _render_score_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    score_series = context.get("score_series")
    if score_series is None or score_series.empty:
        return None

    threshold = context["summary"].get("high_cnv_threshold")
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8, 5)),
        dpi=200,
    )
    ax.hist(score_series.astype(float), bins=25, color="#d95f02", edgecolor="white", alpha=0.9)
    if threshold is not None:
        ax.axvline(float(threshold), color="black", linestyle="--", linewidth=1.4)
        ax.text(
            float(threshold),
            ax.get_ylim()[1] * 0.95,
            f" threshold={float(threshold):.3f}",
            va="top",
            ha="left",
            fontsize=9,
        )
    ax.set_xlabel(context.get("score_source") or "cnv_score")
    ax.set_ylabel("Number of cells / spots")
    ax.set_title(spec.title or "CNV Score Distribution")
    fig.tight_layout()
    return fig


def _render_uncertainty_histogram(adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    uncertainty_key = context.get("uncertainty_key")
    if not uncertainty_key or uncertainty_key not in adata.obs.columns:
        return None

    values = adata.obs[uncertainty_key].astype(float)
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8, 5)),
        dpi=200,
    )
    ax.hist(values, bins=25, color="#756bb1", edgecolor="white", alpha=0.9)
    ax.set_xlabel(uncertainty_key)
    ax.set_ylabel("Number of cells / spots")
    ax.set_title(spec.title or "CNV Uncertainty Distribution")
    fig.tight_layout()
    return fig


CNV_GALLERY_RENDERERS = {
    "cnv_plot": _render_cnv_plot,
    "feature_map": _render_feature_map,
    "category_barplot": _render_category_barplot,
    "cnv_bin_profile": _render_cnv_bin_profile,
    "score_histogram": _render_score_histogram,
    "uncertainty_histogram": _render_uncertainty_histogram,
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
    summary: dict,
    recipe: VisualizationRecipe,
    artifacts: list,
    context: dict,
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    score_df = _build_cnv_score_table(adata, context)
    score_df.to_csv(figure_data_dir / "cnv_scores.csv", index=False)

    summary_df = _build_run_summary_table(summary, context)
    summary_df.to_csv(figure_data_dir / "cnv_run_summary.csv", index=False)

    spatial_file = None
    spatial_df = _build_projection_table(adata, "spatial", context)
    if spatial_df is not None:
        spatial_file = "cnv_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_projection_table(adata, "umap", context)
    if umap_df is not None:
        umap_file = "cnv_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    group_file = None
    group_df = _build_cnv_group_table(adata, context.get("label_key"))
    if group_df is not None:
        group_file = "cnv_group_sizes.csv"
        group_df.to_csv(figure_data_dir / group_file, index=False)

    bin_file = None
    bin_df = _build_cnv_bin_summary_table(adata)
    if bin_df is not None:
        bin_file = "cnv_bin_summary.csv"
        bin_df.to_csv(figure_data_dir / bin_file, index=False)

    numbat_calls_file = None
    if "numbat_calls" in adata.uns:
        numbat_calls_file = "numbat_calls.csv"
        pd.DataFrame(adata.uns["numbat_calls"]).to_csv(
            figure_data_dir / numbat_calls_file,
            index=False,
        )

    numbat_clone_post_file = None
    if "numbat_clone_post" in adata.uns:
        numbat_clone_post_file = "numbat_clone_post.csv"
        pd.DataFrame(adata.uns["numbat_clone_post"]).to_csv(
            figure_data_dir / numbat_clone_post_file,
            index=False,
        )

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "score_column": context.get("score_source"),
        "label_column": context.get("label_key"),
        "uncertainty_column": context.get("uncertainty_key"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "available_files": {
            "cnv_scores": "cnv_scores.csv",
            "cnv_run_summary": "cnv_run_summary.csv",
            "cnv_spatial_points": spatial_file,
            "cnv_umap_points": umap_file,
            "cnv_group_sizes": group_file,
            "cnv_bin_summary": bin_file,
            "numbat_calls": numbat_calls_file,
            "numbat_clone_post": numbat_clone_post_file,
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
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    """Render the standard Python CNV gallery and export figure-ready data."""
    context = gallery_context or _prepare_cnv_gallery_context(adata, summary)
    recipe = _build_cnv_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        CNV_GALLERY_RENDERERS,
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
        / "spatial-cnv"
        / "r_visualization"
        / "cnv_publication_template.R"
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
    high_cnv_label = "High-CNV cells (top 10%)"
    if summary.get("method") == "numbat":
        high_cnv_label = "High-CNV cells (`numbat_p_cnv > 0.5`)"

    header = generate_report_header(
        title="Spatial CNV Inference Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", "infercnvpy"),
            "Cells": str(summary.get("n_cells", 0)),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Mean CNV score**: {summary.get('mean_cnv_score', 0):.4f}",
        f"- **{high_cnv_label}**: {summary.get('high_cnv_fraction_pct', 0):.1f}%",
    ]

    if gallery_context and gallery_context.get("score_source"):
        body_lines.append(f"- **Score source**: `{gallery_context['score_source']}`")
    if gallery_context and gallery_context.get("label_key"):
        body_lines.append(f"- **CNV grouping column**: `{gallery_context['label_key']}`")
    if gallery_context and gallery_context.get("uncertainty_key"):
        body_lines.append(f"- **Uncertainty column**: `{gallery_context['uncertainty_key']}`")
    if summary.get("high_cnv_threshold") is not None:
        body_lines.append(f"- **High-CNV threshold**: {summary.get('high_cnv_threshold')}")

    if summary.get("method") == "infercnvpy":
        body_lines.append(f"- **CNV Leiden clusters**: {summary.get('n_cnv_clusters', 0)}")
    if summary.get("method") == "numbat":
        body_lines.append(f"- **Numbat CNV calls**: {summary.get('n_cnv_calls', 0)}")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    body_lines.extend(["", "## Interpretation Notes\n"])
    if summary.get("method") == "infercnvpy":
        body_lines.extend(
            [
                "- `cnv_score` is a cluster-aware anomaly-style summary derived after CNV-space clustering.",
                "- A high score indicates stronger average inferred CNV deviation, not a discrete DNA segment call.",
            ]
        )
    elif summary.get("method") == "numbat":
        body_lines.extend(
            [
                "- `numbat_p_cnv` is a posterior-style summary when clone posterior output is available.",
                "- Segment-level events should be interpreted from the exported Numbat call tables, not only from the scalar score.",
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
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {"params": params}
    if gallery_context:
        result_data["visualization"] = {
            "score_column": gallery_context.get("score_source"),
            "label_column": gallery_context.get("label_key"),
            "uncertainty_column": gallery_context.get("uncertainty_key"),
        }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary={k: v for k, v in summary.items() if isinstance(v, (str, int, float, bool, type(None)))},
        data=result_data,
        input_checksum=checksum,
    )
    _write_r_visualization_helper(output_dir)


def export_tables(
    adata,
    output_dir: Path,
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    """Write compact result tables for downstream inspection."""
    context = gallery_context or _prepare_cnv_gallery_context(adata, summary)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []

    score_path = tables_dir / "cnv_scores.csv"
    _build_cnv_score_table(adata, context).to_csv(score_path, index=False)
    exported.append(str(score_path))

    summary_path = tables_dir / "cnv_run_summary.csv"
    _build_run_summary_table(summary, context).to_csv(summary_path, index=False)
    exported.append(str(summary_path))

    group_df = _build_cnv_group_table(adata, context.get("label_key"))
    if group_df is not None:
        path = tables_dir / "cnv_group_sizes.csv"
        group_df.to_csv(path, index=False)
        exported.append(str(path))

    bin_df = _build_cnv_bin_summary_table(adata)
    if bin_df is not None:
        path = tables_dir / "cnv_bin_summary.csv"
        bin_df.to_csv(path, index=False)
        exported.append(str(path))

    if "numbat_calls" in adata.uns:
        path = tables_dir / "numbat_calls.csv"
        pd.DataFrame(adata.uns["numbat_calls"]).to_csv(path, index=False)
        exported.append(str(path))

    if "numbat_clone_post" in adata.uns:
        path = tables_dir / "numbat_clone_post.csv"
        pd.DataFrame(adata.uns["numbat_clone_post"]).to_csv(path, index=False)
        exported.append(str(path))

    return exported


def write_reproducibility_commands(output_dir: Path, params: dict, input_file: str | None) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    input_arg = "<input.h5ad>" if input_file else "<demo>"
    cmd = f"python {SCRIPT_REL_PATH} --output {shlex.quote(str(output_dir))}"
    if input_file:
        cmd += f" --input {input_arg}"
    else:
        cmd += " --demo"

    for key, value in params.items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cmd += f" {flag}"
            continue
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            for item in value:
                cmd += f" {flag} {shlex.quote(str(item))}"
            continue
        cmd += f" {flag} {shlex.quote(str(value))}"

    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_cnv_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed:\n{result.stderr}")
        adata = sc.read_h5ad(tmp_path / "processed.h5ad")
        rng = np.random.default_rng(42)
        adata.obs["cell_type"] = pd.Categorical(np.where(rng.random(adata.n_obs) < 0.3, "Normal", "Tumor"))

        # Add synthetic genomic positions required by inferCNVpy
        n_genes = adata.n_vars
        chromosomes = [f"chr{c}" for c in rng.integers(1, 23, size=n_genes)]
        starts = rng.integers(100000, 2000000, size=n_genes)
        ends = starts + rng.integers(5000, 50000, size=n_genes)
        adata.var["chromosome"] = chromosomes
        adata.var["start"] = starts
        adata.var["end"] = ends

        return adata, None


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.window_size < 5:
        parser.error("--window-size must be >= 5")
    if args.step < 1:
        parser.error("--step must be >= 1")
    if args.step > args.window_size:
        parser.error("--step must be <= --window-size")
    if args.reference_cat and not args.reference_key and not args.demo:
        parser.error("--reference-cat requires --reference-key")

    if args.infercnv_lfc_clip <= 0:
        parser.error("--infercnv-lfc-clip must be > 0")
    if args.infercnv_dynamic_threshold is not None and args.infercnv_dynamic_threshold <= 0:
        parser.error("--infercnv-dynamic-threshold must be > 0 (or omit it to disable)")
    if args.infercnv_chunksize < 1:
        parser.error("--infercnv-chunksize must be >= 1")
    if args.infercnv_n_jobs < 1:
        parser.error("--infercnv-n-jobs must be >= 1")

    if args.numbat_genome not in VALID_NUMBAT_GENOMES:
        parser.error(f"--numbat-genome must be one of {VALID_NUMBAT_GENOMES}")
    if args.numbat_max_entropy <= 0 or args.numbat_max_entropy > 1:
        parser.error("--numbat-max-entropy must be in (0, 1]")
    if args.numbat_min_llr < 0:
        parser.error("--numbat-min-llr must be >= 0")
    if args.numbat_min_cells < 1:
        parser.error("--numbat-min-cells must be >= 1")
    if args.numbat_ncores < 1:
        parser.error("--numbat-ncores must be >= 1")


def _collect_run_configuration(
    args: argparse.Namespace,
    reference_key: str | None,
    reference_cat: list[str] | None,
) -> tuple[dict, dict]:
    params = {
        "method": args.method,
        "reference_key": reference_key,
        "reference_cat": reference_cat,
    }

    if args.method == "infercnvpy":
        exclude_chromosomes = None if args.infercnv_include_sex_chromosomes else args.infercnv_exclude_chromosomes
        params.update(
            {
                "window_size": args.window_size,
                "step": args.step,
                "infercnv_lfc_clip": args.infercnv_lfc_clip,
                "infercnv_dynamic_threshold": args.infercnv_dynamic_threshold,
                "infercnv_exclude_chromosomes": exclude_chromosomes,
                "infercnv_chunksize": args.infercnv_chunksize,
                "infercnv_n_jobs": args.infercnv_n_jobs,
            }
        )
        method_kwargs = {
            "window_size": args.window_size,
            "step": args.step,
            "infercnv_lfc_clip": args.infercnv_lfc_clip,
            "infercnv_dynamic_threshold": args.infercnv_dynamic_threshold,
            "infercnv_exclude_chromosomes": exclude_chromosomes,
            "infercnv_chunksize": args.infercnv_chunksize,
            "infercnv_n_jobs": args.infercnv_n_jobs,
        }
    elif args.method == "numbat":
        params.update(
            {
                "numbat_genome": args.numbat_genome,
                "numbat_max_entropy": args.numbat_max_entropy,
                "numbat_min_llr": args.numbat_min_llr,
                "numbat_min_cells": args.numbat_min_cells,
                "numbat_ncores": args.numbat_ncores,
            }
        )
        method_kwargs = {
            "numbat_genome": args.numbat_genome,
            "numbat_max_entropy": args.numbat_max_entropy,
            "numbat_min_llr": args.numbat_min_llr,
            "numbat_min_cells": args.numbat_min_cells,
            "numbat_ncores": args.numbat_ncores,
        }
    else:
        method_kwargs = {}

    return params, method_kwargs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial CNV — copy number variation inference")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="infercnvpy", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--reference-key", default=None)
    parser.add_argument("--reference-cat", nargs="+", default=None)
    parser.add_argument("--window-size", type=int, default=METHOD_PARAM_DEFAULTS["infercnvpy"]["window_size"])
    parser.add_argument("--step", type=int, default=METHOD_PARAM_DEFAULTS["infercnvpy"]["step"])
    parser.add_argument("--infercnv-lfc-clip", type=float, default=METHOD_PARAM_DEFAULTS["infercnvpy"]["lfc_clip"])
    parser.add_argument(
        "--infercnv-dynamic-threshold",
        type=float,
        default=METHOD_PARAM_DEFAULTS["infercnvpy"]["dynamic_threshold"],
    )
    parser.add_argument(
        "--infercnv-exclude-chromosomes",
        nargs="+",
        default=list(INFERCNVPY_DEFAULT_EXCLUDE_CHROMOSOMES),
        help="Chromosomes to exclude for inferCNVpy, e.g. chrX chrY",
    )
    parser.add_argument(
        "--infercnv-include-sex-chromosomes",
        action="store_true",
        help="Disable the default inferCNVpy exclusion of chrX/chrY.",
    )
    parser.add_argument("--infercnv-chunksize", type=int, default=METHOD_PARAM_DEFAULTS["infercnvpy"]["chunksize"])
    parser.add_argument("--infercnv-n-jobs", type=int, default=METHOD_PARAM_DEFAULTS["infercnvpy"]["n_jobs"])
    parser.add_argument("--numbat-genome", default=METHOD_PARAM_DEFAULTS["numbat"]["genome"])
    parser.add_argument("--numbat-max-entropy", type=float, default=METHOD_PARAM_DEFAULTS["numbat"]["max_entropy"])
    parser.add_argument("--numbat-min-llr", type=float, default=METHOD_PARAM_DEFAULTS["numbat"]["min_llr"])
    parser.add_argument("--numbat-min-cells", type=int, default=METHOD_PARAM_DEFAULTS["numbat"]["min_cells"])
    parser.add_argument("--numbat-ncores", type=int, default=METHOD_PARAM_DEFAULTS["numbat"]["ncores"])
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
        reference_key, reference_cat = "cell_type", ["Normal"]
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file, reference_key, reference_cat = args.input_path, args.reference_key, args.reference_cat
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    if args.method == "numbat" and (not reference_key or not reference_cat):
        parser.error(
            "Current Numbat wrapper requires --reference-key and --reference-cat "
            "(demo mode sets them automatically)."
        )

    params, method_kwargs = _collect_run_configuration(args, reference_key, reference_cat)

    if args.method in COUNT_BASED_METHODS and "counts" not in adata.layers:
        if adata.raw is not None:
            logger.warning(
                "Method '%s' expects raw integer counts in adata.layers['counts']. "
                "Found adata.raw — will copy to layers['counts'].",
                args.method,
            )
        else:
            logger.warning(
                "Method '%s' expects raw integer counts in adata.layers['counts'], but none found. "
                "Falling back to adata.X — if this is log-normalized, results will be incorrect. "
                "Ensure preprocessing saves raw counts: adata.layers['counts'] = adata.X.copy()",
                args.method,
            )

    summary = run_cnv(
        adata,
        method=args.method,
        reference_key=reference_key,
        reference_cat=reference_cat,
        **method_kwargs,
    )

    gallery_context = _prepare_cnv_gallery_context(adata, summary)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(adata, output_dir, summary, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility_commands(output_dir, params, input_file)
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)
    adata.write_h5ad(output_dir / "processed.h5ad")
    print(
        f"CNV complete ({summary['method']}): "
        f"mean score={summary.get('mean_cnv_score', 0):.4f}"
    )


if __name__ == "__main__":
    main()
