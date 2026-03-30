#!/usr/bin/env python3
"""Spatial Preprocess — load, QC, normalize, embed, and cluster spatial data."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
import warnings
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs

ensure_runtime_cache_dirs("omicsclaw")

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key
from skills.spatial._lib.loader import SUPPORTED_SPATIAL_PLATFORMS, load_spatial_data
from skills.spatial._lib.preprocessing import (
    METHOD_PARAM_DEFAULTS,
    PREPROCESS_METHOD,
    SUPPORTED_SPECIES,
    TISSUE_PRESETS,
    preprocess,
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

SKILL_NAME = "spatial-preprocess"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-preprocess/spatial_preprocess.py"


# ---------------------------------------------------------------------------
# Gallery helpers
# ---------------------------------------------------------------------------


def _parse_resolutions(value: str | None) -> list[float] | None:
    if value in (None, ""):
        return None
    parsed: list[float] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        parsed.append(float(item))
    return parsed or None


def _append_cli_flag(command: str, key: str, value: Any) -> str:
    flag = f"--{key.replace('_', '-')}"
    if isinstance(value, bool):
        return f"{command} {flag}" if value else command
    if value in (None, ""):
        return command
    return f"{command} {flag} {shlex.quote(str(value))}"


def _prepare_preprocess_plot_state(adata) -> str | None:
    spatial_key = get_spatial_key(adata)
    if spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = np.asarray(adata.obsm["X_spatial"]).copy()
        spatial_key = "spatial"
    elif spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = np.asarray(adata.obsm["spatial"]).copy()

    cluster_columns = ["leiden"] + [
        column for column in adata.obs.columns if str(column).startswith("leiden_res_")
    ]
    for column in cluster_columns:
        if column in adata.obs.columns and not isinstance(adata.obs[column].dtype, pd.CategoricalDtype):
            adata.obs[column] = pd.Categorical(adata.obs[column].astype(str))

    return spatial_key


def _build_cluster_summary_table(summary: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"cluster": str(cluster), "n_cells": int(size)}
        for cluster, size in summary.get("cluster_sizes", {}).items()
    ]
    if not rows:
        return pd.DataFrame(columns=["cluster", "n_cells"])
    return pd.DataFrame(rows).sort_values(
        by=["n_cells", "cluster"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _build_qc_distribution_table(adata) -> pd.DataFrame:
    qc_columns = [
        column
        for column in ("n_genes_by_counts", "total_counts", "pct_counts_mt", "leiden")
        if column in adata.obs.columns
    ]
    if not qc_columns:
        return pd.DataFrame(columns=["observation"])
    qc_df = adata.obs.loc[:, qc_columns].copy()
    qc_df.insert(0, "observation", adata.obs_names.astype(str))
    return qc_df.reset_index(drop=True)


def _build_pca_variance_table(adata) -> pd.DataFrame:
    pca_info = adata.uns.get("pca", {})
    variance_ratio = pca_info.get("variance_ratio")
    variance = pca_info.get("variance")
    if variance_ratio is None:
        return pd.DataFrame(columns=["pc", "variance_ratio", "cumulative_variance_ratio", "variance"])

    ratio = np.asarray(variance_ratio, dtype=float)
    cumulative = np.cumsum(ratio)
    if variance is None:
        variance = np.repeat(np.nan, len(ratio))
    else:
        variance = np.asarray(variance, dtype=float)

    return pd.DataFrame(
        {
            "pc": np.arange(1, len(ratio) + 1),
            "variance_ratio": ratio,
            "cumulative_variance_ratio": cumulative,
            "variance": variance,
        }
    )


def _build_multi_resolution_table(summary: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for resolution, n_clusters in summary.get("multi_resolution", {}).items():
        try:
            resolution_value: float | str = float(resolution)
        except (TypeError, ValueError):
            resolution_value = str(resolution)
        rows.append(
            {
                "resolution": resolution_value,
                "n_clusters": int(n_clusters),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["resolution", "n_clusters"])
    return pd.DataFrame(rows).sort_values(by="resolution", kind="mergesort").reset_index(drop=True)


def _build_run_summary_table(summary: dict[str, Any], context: dict[str, Any]) -> pd.DataFrame:
    effective_params = summary.get("effective_params", {})
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "n_cells_raw", "value": summary.get("n_cells_raw")},
        {"metric": "n_genes_raw", "value": summary.get("n_genes_raw")},
        {"metric": "n_cells_filtered", "value": summary.get("n_cells_filtered")},
        {"metric": "n_genes_filtered", "value": summary.get("n_genes_filtered")},
        {"metric": "n_hvg", "value": summary.get("n_hvg")},
        {"metric": "n_clusters", "value": summary.get("n_clusters")},
        {"metric": "has_spatial", "value": summary.get("has_spatial")},
        {"metric": "cluster_column", "value": context.get("cluster_col")},
        {"metric": "spatial_key", "value": context.get("spatial_key")},
        {"metric": "umap_key", "value": "X_umap" if "X_umap" in context.get("obsm_keys", set()) else None},
        {"metric": "counts_layer", "value": "counts" if "counts" in context.get("layer_keys", set()) else None},
        {"metric": "hvg_column", "value": "highly_variable" if "highly_variable" in context.get("var_keys", set()) else None},
        {"metric": "n_pcs_requested", "value": effective_params.get("n_pcs_requested")},
        {"metric": "n_pcs_computed", "value": summary.get("n_pcs_computed")},
        {"metric": "n_pcs_used", "value": summary.get("n_pcs_used")},
        {"metric": "n_pcs_suggested", "value": summary.get("n_pcs_suggested")},
        {"metric": "n_neighbors", "value": effective_params.get("n_neighbors")},
        {"metric": "leiden_resolution", "value": effective_params.get("leiden_resolution")},
        {"metric": "tissue_preset", "value": summary.get("tissue_preset")},
    ]
    return pd.DataFrame(rows)


def _build_observation_export_table(
    adata,
    basis: str,
    *,
    cluster_col: str | None,
    qc_metric_cols: list[str],
    multi_resolution_cols: list[str],
) -> pd.DataFrame | None:
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

    export_columns = []
    if cluster_col:
        export_columns.append(cluster_col)
    export_columns.extend(qc_metric_cols)
    export_columns.extend(multi_resolution_cols)

    seen: set[str] = set()
    for column in export_columns:
        if not column or column in seen or column not in adata.obs.columns:
            continue
        seen.add(column)
        series = adata.obs[column]
        if pd.api.types.is_numeric_dtype(series):
            df[column] = pd.to_numeric(series, errors="coerce").fillna(0.0).to_numpy()
        else:
            df[column] = series.astype(str).to_numpy()
    return df


def _prepare_preprocess_gallery_context(adata, summary: dict[str, Any]) -> dict[str, Any]:
    spatial_key = _prepare_preprocess_plot_state(adata)
    cluster_col = "leiden" if "leiden" in adata.obs.columns else None
    qc_metric_cols = [
        column
        for column in ("n_genes_by_counts", "total_counts", "pct_counts_mt")
        if column in adata.obs.columns
    ]
    multi_resolution_cols = sorted(
        [column for column in adata.obs.columns if str(column).startswith("leiden_res_")]
    )

    context = {
        "spatial_key": spatial_key,
        "cluster_col": cluster_col,
        "qc_metric_cols": qc_metric_cols,
        "multi_resolution_columns": multi_resolution_cols,
        "cluster_summary_df": _build_cluster_summary_table(summary),
        "qc_distribution_df": _build_qc_distribution_table(adata),
        "pca_variance_df": _build_pca_variance_table(adata),
        "multi_resolution_df": _build_multi_resolution_table(summary),
        "obsm_keys": set(adata.obsm.keys()),
        "layer_keys": set(adata.layers.keys()),
        "var_keys": set(adata.var.columns),
    }
    return context


def _build_preprocess_visualization_recipe(adata, summary: dict[str, Any], context: dict[str, Any]) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    cluster_col = context.get("cluster_col")
    qc_metric_cols = context.get("qc_metric_cols", [])

    if cluster_col and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="preprocess_spatial_clusters",
                role="overview",
                renderer="feature_map",
                filename="spatial_leiden.png",
                title="Leiden Clusters on Tissue",
                description="Primary Leiden clustering projected onto spatial coordinates.",
                params={
                    "feature": cluster_col,
                    "basis": "spatial",
                    "colormap": "tab10",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (10, 8),
                },
                required_obs=[cluster_col],
                required_obsm=["spatial"],
            )
        )

    if cluster_col and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="preprocess_umap_clusters",
                role="overview",
                renderer="feature_map",
                filename="umap_leiden.png",
                title="Leiden Clusters on UMAP",
                description="Primary Leiden clustering projected onto the shared UMAP embedding.",
                params={
                    "feature": cluster_col,
                    "basis": "umap",
                    "colormap": "tab10",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (8, 6),
                },
                required_obs=[cluster_col],
                required_obsm=["X_umap"],
            )
        )

    if context.get("spatial_key") and qc_metric_cols:
        plots.append(
            PlotSpec(
                plot_id="preprocess_qc_spatial",
                role="diagnostic",
                renderer="feature_map",
                filename="qc_metrics_spatial.png",
                title="QC Metrics on Tissue",
                description="Main QC metrics projected onto tissue coordinates after filtering.",
                params={
                    "feature": qc_metric_cols[:3],
                    "basis": "spatial",
                    "colormap": "viridis",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (15, 4.8),
                },
                required_obs=qc_metric_cols[:3],
                required_obsm=["spatial"],
            )
        )

    if not context["cluster_summary_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="preprocess_cluster_sizes",
                role="supporting",
                renderer="cluster_size_barplot",
                filename="cluster_size_barplot.png",
                title="Cluster Size Summary",
                description="Spot or cell counts for the primary Leiden clusters.",
            )
        )

    if not context["pca_variance_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="preprocess_pca_variance",
                role="supporting",
                renderer="pca_variance_curve",
                filename="pca_variance_curve.png",
                title="PCA Variance Guidance",
                description="Explained variance profile used to interpret requested, computed, used, and suggested PC counts.",
            )
        )

    if not context["multi_resolution_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="preprocess_resolution_sweep",
                role="supporting",
                renderer="resolution_sweep_plot",
                filename="leiden_resolution_sweep.png",
                title="Leiden Resolution Sweep",
                description="Cluster counts across the optional multi-resolution Leiden sweep.",
            )
        )

    if not context["qc_distribution_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="preprocess_qc_histograms",
                role="uncertainty",
                renderer="qc_histograms",
                filename="qc_metric_distributions.png",
                title="QC Threshold Context",
                description="Filtered-data distributions for the main QC metrics with effective threshold overlays.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-preprocess-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Preprocess Standard Gallery",
        description=(
            "Default OmicsClaw preprocessing story plots: clustering overview, "
            "QC diagnostics, PCA guidance, and threshold-context summaries."
        ),
        plots=plots,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict[str, Any]) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_cluster_size_barplot(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    cluster_summary_df = context.get("cluster_summary_df", pd.DataFrame())
    if cluster_summary_df.empty:
        return None

    plot_df = cluster_summary_df.iloc[::-1].copy()
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(plot_df) * 0.45))),
        dpi=200,
    )
    ax.barh(plot_df["cluster"].astype(str), plot_df["n_cells"], color="#3182bd")
    ax.set_xlabel("Number of cells or spots")
    ax.set_ylabel("Leiden cluster")
    ax.set_title(spec.title or "Cluster Size Summary")
    fig.tight_layout()
    return fig


def _render_pca_variance_curve(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    pca_variance_df = context.get("pca_variance_df", pd.DataFrame())
    summary = context.get("summary", {})
    if pca_variance_df.empty:
        return None

    plot_df = pca_variance_df.head(20).copy()
    fig, ax1 = plt.subplots(figsize=spec.params.get("figure_size", (8.5, 5.4)), dpi=200)
    ax1.bar(plot_df["pc"], plot_df["variance_ratio"], color="#9ecae1", label="Variance ratio")
    ax1.set_xlabel("Principal component")
    ax1.set_ylabel("Explained variance ratio")

    ax2 = ax1.twinx()
    ax2.plot(
        plot_df["pc"],
        plot_df["cumulative_variance_ratio"],
        color="#08519c",
        marker="o",
        linewidth=1.6,
        label="Cumulative variance",
    )
    ax2.set_ylabel("Cumulative explained variance")
    ax2.set_ylim(0, max(1.0, float(plot_df["cumulative_variance_ratio"].max()) * 1.05))

    for label, value, color in (
        ("Used PCs", summary.get("n_pcs_used"), "#d95f0e"),
        ("Suggested PCs", summary.get("n_pcs_suggested"), "#238b45"),
    ):
        if value:
            ax1.axvline(float(value), color=color, linestyle="--", linewidth=1.2)
            ax1.text(
                float(value),
                ax1.get_ylim()[1] * 0.92,
                label,
                rotation=90,
                va="top",
                ha="right",
                fontsize=8,
                color=color,
            )

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    if handles1 or handles2:
        ax1.legend(handles1 + handles2, labels1 + labels2, frameon=False, loc="upper left")
    ax1.set_title(spec.title or "PCA Variance Guidance")
    fig.tight_layout()
    return fig


def _render_resolution_sweep_plot(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    multi_resolution_df = context.get("multi_resolution_df", pd.DataFrame())
    if multi_resolution_df.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8.0, 4.8)), dpi=200)
    ax.plot(
        pd.to_numeric(multi_resolution_df["resolution"], errors="coerce"),
        multi_resolution_df["n_clusters"],
        color="#6a51a3",
        marker="o",
        linewidth=1.8,
    )
    ax.set_xlabel("Leiden resolution")
    ax.set_ylabel("Number of clusters")
    ax.set_title(spec.title or "Leiden Resolution Sweep")
    fig.tight_layout()
    return fig


def _render_qc_histograms(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    qc_distribution_df = context.get("qc_distribution_df", pd.DataFrame())
    summary = context.get("summary", {})
    if qc_distribution_df.empty:
        return None

    metrics = [
        ("n_genes_by_counts", "Detected genes", summary.get("effective_params", {}).get("min_genes")),
        ("total_counts", "Total counts", None),
        ("pct_counts_mt", "Mitochondrial percent", summary.get("effective_params", {}).get("max_mt_pct")),
    ]
    available = [item for item in metrics if item[0] in qc_distribution_df.columns]
    if not available:
        return None

    fig, axes = plt.subplots(
        1,
        len(available),
        figsize=spec.params.get("figure_size", (5.0 * len(available), 4.4)),
        dpi=200,
        squeeze=False,
    )
    axes_flat = axes.flatten()
    max_genes = summary.get("effective_params", {}).get("max_genes")

    for idx, (column, label, threshold) in enumerate(available):
        ax = axes_flat[idx]
        values = pd.to_numeric(qc_distribution_df[column], errors="coerce").dropna().to_numpy()
        if values.size == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            ax.set_axis_off()
            continue
        ax.hist(values, bins=30, color="#9ecae1", edgecolor="white")
        if threshold not in (None, 0, 0.0):
            ax.axvline(float(threshold), color="#cb181d", linestyle="--", linewidth=1.2)
        if column == "n_genes_by_counts" and max_genes not in (None, 0, 0.0):
            ax.axvline(float(max_genes), color="#636363", linestyle=":", linewidth=1.2)
        ax.set_title(label)
        ax.set_xlabel(column)
        ax.set_ylabel("Cells or spots")

    fig.suptitle(spec.title or "QC Threshold Context", fontsize=13, y=1.02)
    fig.tight_layout()
    return fig


PREPROCESS_GALLERY_RENDERERS = {
    "feature_map": _render_feature_map,
    "cluster_size_barplot": _render_cluster_size_barplot,
    "pca_variance_curve": _render_pca_variance_curve,
    "resolution_sweep_plot": _render_resolution_sweep_plot,
    "qc_histograms": _render_qc_histograms,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def _export_figure_data(
    adata,
    output_dir: Path,
    summary: dict[str, Any],
    recipe: VisualizationRecipe,
    artifacts: list[Any],
    context: dict[str, Any],
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    cluster_summary_df = context["cluster_summary_df"]
    qc_distribution_df = context["qc_distribution_df"]
    pca_variance_df = context["pca_variance_df"]
    multi_resolution_df = context["multi_resolution_df"]
    run_summary_df = _build_run_summary_table(summary, context)

    cluster_summary_df.to_csv(figure_data_dir / "cluster_summary.csv", index=False)
    qc_distribution_df.to_csv(figure_data_dir / "qc_metric_distributions.csv", index=False)
    run_summary_df.to_csv(figure_data_dir / "preprocess_run_summary.csv", index=False)
    pca_variance_df.to_csv(figure_data_dir / "pca_variance_ratio.csv", index=False)

    multi_resolution_file = None
    if not multi_resolution_df.empty:
        multi_resolution_file = "multi_resolution_summary.csv"
        multi_resolution_df.to_csv(figure_data_dir / multi_resolution_file, index=False)

    spatial_file = None
    spatial_df = _build_observation_export_table(
        adata,
        "spatial",
        cluster_col=context.get("cluster_col"),
        qc_metric_cols=context.get("qc_metric_cols", []),
        multi_resolution_cols=context.get("multi_resolution_columns", []),
    )
    if spatial_df is not None:
        spatial_file = "preprocess_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_observation_export_table(
        adata,
        "umap",
        cluster_col=context.get("cluster_col"),
        qc_metric_cols=context.get("qc_metric_cols", []),
        multi_resolution_cols=context.get("multi_resolution_columns", []),
    )
    if umap_df is not None:
        umap_file = "preprocess_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "available_files": {
            "cluster_summary": "cluster_summary.csv",
            "qc_metric_distributions": "qc_metric_distributions.csv",
            "preprocess_run_summary": "preprocess_run_summary.csv",
            "pca_variance_ratio": "pca_variance_ratio.csv",
            "multi_resolution_summary": multi_resolution_file,
            "preprocess_spatial_points": spatial_file,
            "preprocess_umap_points": umap_file,
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
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> list[str]:
    """Render the standard preprocessing gallery and export figure-ready data."""
    context = gallery_context or _prepare_preprocess_gallery_context(adata, summary)
    recipe = _build_preprocess_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        PREPROCESS_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report / exports
# ---------------------------------------------------------------------------


def export_tables(
    output_dir: Path,
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
    adata=None,
) -> list[str]:
    """Export tabular outputs."""
    if gallery_context is not None:
        context = gallery_context
    elif adata is not None:
        context = _prepare_preprocess_gallery_context(adata, summary)
    else:
        context = {}
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []

    cluster_summary_df = context.get("cluster_summary_df")
    if cluster_summary_df is None:
        cluster_summary_df = _build_cluster_summary_table(summary)
    path = tables_dir / "cluster_summary.csv"
    cluster_summary_df.to_csv(path, index=False)
    exported.append(str(path))

    qc_summary_df = pd.DataFrame(
        [
            ("n_cells_raw", summary["n_cells_raw"]),
            ("n_genes_raw", summary["n_genes_raw"]),
            ("n_cells_filtered", summary["n_cells_filtered"]),
            ("n_genes_filtered", summary["n_genes_filtered"]),
            ("n_hvg", summary["n_hvg"]),
            ("n_clusters", summary["n_clusters"]),
            ("n_pcs_computed", summary.get("n_pcs_computed")),
            ("n_pcs_used", summary.get("n_pcs_used")),
            ("n_pcs_suggested", summary.get("n_pcs_suggested")),
        ],
        columns=["metric", "value"],
    )
    path = tables_dir / "qc_summary.csv"
    qc_summary_df.to_csv(path, index=False)
    exported.append(str(path))

    pca_variance_df = context.get("pca_variance_df")
    if pca_variance_df is None and adata is not None:
        pca_variance_df = _build_pca_variance_table(adata)
    if pca_variance_df is not None:
        path = tables_dir / "pca_variance_ratio.csv"
        pca_variance_df.to_csv(path, index=False)
        exported.append(str(path))

    multi_resolution_df = context.get("multi_resolution_df")
    if multi_resolution_df is None:
        multi_resolution_df = _build_multi_resolution_table(summary)
    if not multi_resolution_df.empty:
        path = tables_dir / "multi_resolution_summary.csv"
        multi_resolution_df.to_csv(path, index=False)
        exported.append(str(path))

    return exported


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-preprocess"
        / "r_visualization"
        / "preprocess_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def write_report(
    output_dir: Path,
    summary: dict[str, Any],
    input_file: str | None,
    params: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> None:
    method_name = summary.get("method", PREPROCESS_METHOD)
    context = gallery_context or {}
    header = generate_report_header(
        title="Spatial Preprocessing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": method_name,
            "Species": params.get("species", "human"),
            "Data type": params.get("data_type", "generic"),
        },
    )

    effective_params = summary.get("effective_params", {})
    body_lines = [
        "## Summary\n",
        f"- **Method**: {method_name}",
        f"- **Raw**: {summary['n_cells_raw']} cells x {summary['n_genes_raw']} genes",
        f"- **After QC**: {summary['n_cells_filtered']} cells x {summary['n_genes_filtered']} genes",
        f"- **HVG selected**: {summary['n_hvg']}",
        f"- **Leiden clusters**: {summary['n_clusters']}",
        f"- **Spatial coordinates**: {'Yes' if summary['has_spatial'] else 'No'}",
        f"- **Requested PCs**: {effective_params.get('n_pcs_requested', params.get('n_pcs', 'N/A'))}",
        f"- **Computed PCs**: {summary.get('n_pcs_computed', 'N/A')}",
        f"- **Neighbor graph PCs used**: {summary.get('n_pcs_used', 'N/A')}",
        f"- **Suggested PCs**: {summary.get('n_pcs_suggested', 'N/A')}",
        f"- **Primary Leiden resolution**: {effective_params.get('leiden_resolution', params.get('leiden_resolution', 'N/A'))}",
    ]
    if summary.get("tissue_preset"):
        body_lines.append(f"- **Tissue preset**: {summary['tissue_preset']}")
    if context.get("cluster_col"):
        body_lines.append(f"- **Cluster column**: `{context['cluster_col']}`")
    if context.get("spatial_key"):
        body_lines.append(f"- **Spatial key**: `{context['spatial_key']}`")

    if summary.get("multi_resolution"):
        body_lines.extend(["", "### Multi-resolution clustering\n", "| Resolution | Clusters |", "|------------|----------|"])
        for res, n_clusters in summary["multi_resolution"].items():
            body_lines.append(f"| {res} | {n_clusters} |")

    body_lines.extend(["", "### Cluster sizes\n", "| Cluster | Cells |", "|---------|-------|"])
    for cluster, size in sorted(summary["cluster_sizes"].items(), key=lambda item: str(item[0])):
        body_lines.append(f"| {cluster} | {size} |")

    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    if effective_params:
        body_lines.extend(["", "### Effective Method Parameters\n"])
        for key, value in effective_params.items():
            body_lines.append(f"- `{key}`: {value}")

    body_lines.extend(
        [
            "",
            "## Interpretation Notes\n",
            "- `processed.h5ad` preserves raw counts in both `adata.layers['counts']` and `adata.raw`, while `adata.X` is the log-normalized matrix used by downstream exploratory workflows.",
            "- OmicsClaw reports requested, computed, used, and suggested PC counts separately so graph construction choices stay auditable instead of being hidden behind Scanpy internals.",
            "- The Python gallery is the canonical preprocessing narrative. Optional downstream R styling should consume `figure_data/` instead of recomputing QC, clustering, or embeddings.",
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
    result_data: dict[str, Any] = {
        "method": method_name,
        "params": params,
        "effective_params": effective_params,
        **summary,
    }
    result_data["visualization"] = {
        "recipe_id": "standard-spatial-preprocess-gallery",
        "cluster_column": context.get("cluster_col", "leiden"),
        "spatial_key": context.get("spatial_key"),
        "umap_key": "X_umap" if context.get("obsm_keys") and "X_umap" in context["obsm_keys"] else None,
        "counts_layer": "counts" if context.get("layer_keys") and "counts" in context["layer_keys"] else None,
        "hvg_column": "highly_variable" if context.get("var_keys") and "highly_variable" in context["var_keys"] else None,
        "multi_resolution_columns": context.get("multi_resolution_columns", []),
        "qc_metric_columns": context.get("qc_metric_cols", []),
    }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data=result_data,
        input_checksum=checksum,
    )


def write_reproducibility(
    output_dir: Path,
    params: dict[str, Any],
    summary: dict[str, Any],
    *,
    input_file: str | None,
    demo_mode: bool = False,
) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--demo' if demo_mode else '--input <input_path>'} "
        f"--output {shlex.quote(str(output_dir))}"
    )

    effective_params = summary.get("effective_params", {})

    # Reproducibility uses explicit effective thresholds so future preset changes
    # do not silently alter reruns.
    repro_params = {
        "data_type": params.get("data_type"),
        "species": effective_params.get("species", params.get("species")),
        "min_genes": effective_params.get("min_genes", params.get("min_genes")),
        "min_cells": effective_params.get("min_cells", params.get("min_cells")),
        "max_mt_pct": effective_params.get("max_mt_pct", params.get("max_mt_pct")),
        "max_genes": effective_params.get("max_genes", params.get("max_genes")),
        "n_top_hvg": effective_params.get("n_top_hvg", params.get("n_top_hvg")),
        "n_pcs": effective_params.get("n_pcs_requested", params.get("n_pcs")),
        "n_neighbors": effective_params.get("n_neighbors", params.get("n_neighbors")),
        "leiden_resolution": effective_params.get("leiden_resolution", params.get("leiden_resolution")),
    }
    if params.get("tissue"):
        repro_params["tissue"] = params["tissue"]
    if "resolutions" in effective_params:
        repro_params["resolutions"] = ",".join(str(res) for res in effective_params["resolutions"])
    elif "resolutions" in params:
        repro_params["resolutions"] = params["resolutions"]

    for key, value in repro_params.items():
        command = _append_cli_flag(command, key, value)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n")

    try:
        from importlib.metadata import version as get_version
    except ImportError:
        from importlib_metadata import version as get_version  # type: ignore

    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "squidpy", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            pass
        except Exception:
            pass
    (repro_dir / "environment.txt").write_text("\n".join(env_lines) + ("\n" if env_lines else ""))
    _write_r_visualization_helper(output_dir)


def _build_parser() -> argparse.ArgumentParser:
    defaults = METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]
    parser = argparse.ArgumentParser(
        description="Spatial Preprocess — multi-platform spatial QC, normalization, embedding, and Leiden clustering",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--data-type",
        default="generic",
        choices=list(SUPPORTED_SPATIAL_PLATFORMS),
        help="Input platform hint",
    )
    parser.add_argument(
        "--species",
        default="human",
        choices=list(SUPPORTED_SPECIES),
        help="Species for mitochondrial gene prefix detection",
    )
    parser.add_argument("--min-genes", type=int, default=defaults["min_genes"])
    parser.add_argument("--min-cells", type=int, default=defaults["min_cells"])
    parser.add_argument("--max-mt-pct", type=float, default=defaults["max_mt_pct"])
    parser.add_argument(
        "--max-genes",
        type=int,
        default=defaults["max_genes"],
        help="Max genes per cell or spot (0 disables the upper bound)",
    )
    parser.add_argument(
        "--tissue",
        default=None,
        help=f"Tissue type for QC presets: {', '.join(sorted(TISSUE_PRESETS))}",
    )
    parser.add_argument(
        "--n-top-hvg",
        type=int,
        default=defaults["n_top_hvg"],
        help="Number of highly variable genes to keep",
    )
    parser.add_argument(
        "--n-pcs",
        type=int,
        default=defaults["n_pcs"],
        help="Requested PCA dimensions before internal clipping",
    )
    parser.add_argument(
        "--n-neighbors",
        type=int,
        default=defaults["n_neighbors"],
        help="Neighbors for graph construction",
    )
    parser.add_argument(
        "--leiden-resolution",
        type=float,
        default=defaults["leiden_resolution"],
        help="Primary Leiden clustering resolution",
    )
    parser.add_argument(
        "--resolutions",
        default=None,
        help="Comma-separated Leiden resolutions to explore (for example 0.4,0.6,0.8,1.0)",
    )
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.demo:
        return
    if not args.input_path:
        parser.error("Provide --input or --demo")
    if args.input_path and not Path(args.input_path).exists():
        parser.error(f"Input path not found: {args.input_path}")
    if args.tissue and args.tissue.lower() not in TISSUE_PRESETS:
        parser.error(f"Unknown tissue '{args.tissue}'. Available: {', '.join(sorted(TISSUE_PRESETS))}")
    if args.min_genes < 0 or args.min_cells < 0 or args.max_genes < 0:
        parser.error("Gene and cell count thresholds must be >= 0")
    if not 0 <= args.max_mt_pct <= 100:
        parser.error("--max-mt-pct must be in [0, 100]")
    if args.n_top_hvg <= 0:
        parser.error("--n-top-hvg must be > 0")
    if args.n_pcs <= 0:
        parser.error("--n-pcs must be > 0")
    if args.n_neighbors <= 0:
        parser.error("--n-neighbors must be > 0")
    if args.leiden_resolution <= 0:
        parser.error("--leiden-resolution must be > 0")
    try:
        resolutions = _parse_resolutions(args.resolutions)
    except ValueError as exc:
        parser.error(f"Invalid --resolutions value: {exc}")
    if resolutions and any(res <= 0 for res in resolutions):
        parser.error("All --resolutions values must be > 0")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict[str, Any], list[float] | None]:
    params: dict[str, Any] = {
        "data_type": args.data_type,
        "species": args.species,
        "min_genes": args.min_genes,
        "min_cells": args.min_cells,
        "max_mt_pct": args.max_mt_pct,
        "max_genes": args.max_genes,
        "n_top_hvg": args.n_top_hvg,
        "n_pcs": args.n_pcs,
        "n_neighbors": args.n_neighbors,
        "leiden_resolution": args.leiden_resolution,
    }
    if args.tissue:
        params["tissue"] = args.tissue
    resolutions = _parse_resolutions(args.resolutions)
    if resolutions:
        params["resolutions"] = ",".join(str(res) for res in resolutions)
    return params, resolutions


def get_demo_data():
    """Load the built-in demo dataset."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_visium.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path), str(demo_path)

    logger.info("Demo file not found, generating synthetic data")
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
    from generate_demo_data import generate_demo_visium

    return generate_demo_visium(), None


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
        if args.min_genes == METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["min_genes"]:
            args.min_genes = 5
        if args.n_top_hvg == METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["n_top_hvg"]:
            args.n_top_hvg = 50
        if args.n_pcs == METHOD_PARAM_DEFAULTS[PREPROCESS_METHOD]["n_pcs"]:
            args.n_pcs = 15
        args.data_type = "visium"
    else:
        adata = load_spatial_data(args.input_path, data_type=args.data_type)
        input_file = args.input_path

    params, resolutions = _collect_run_configuration(args)
    adata, summary = preprocess(
        adata,
        resolutions=resolutions,
        **{key: value for key, value in params.items() if key not in {"data_type", "resolutions"}},
    )

    gallery_context = _prepare_preprocess_gallery_context(adata, summary)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, summary, gallery_context=gallery_context, adata=adata)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, summary, input_file=input_file, demo_mode=args.demo)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Preprocessing complete: {summary['n_cells_filtered']} cells, {summary['n_clusters']} clusters"
    )


if __name__ == "__main__":
    main()
