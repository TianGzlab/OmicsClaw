#!/usr/bin/env python3
"""Spatial Trajectory — pseudotime and trajectory inference."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import subprocess
import sys
import tempfile
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
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.trajectory import (
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    detect_cluster_key,
    run_trajectory,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_features,
    plot_trajectory,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-trajectory"
SKILL_VERSION = "0.6.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-trajectory/spatial_trajectory.py"


def _detect_pseudotime_key(adata) -> str | None:
    for key in (
        "palantir_pseudotime",
        "dpt_pseudotime",
        "velocity_pseudotime",
        "latent_time",
    ):
        if key in adata.obs.columns:
            return key
    return None


def _detect_entropy_key(adata) -> str | None:
    for key in ("palantir_entropy", "traj_fate_entropy"):
        if key in adata.obs.columns:
            return key
    return None


def _append_cli_flag(command: str, key: str, value: Any) -> str:
    flag = f"--{key.replace('_', '-')}"
    if isinstance(value, bool):
        return f"{command} {flag}" if value else command
    if value in (None, ""):
        return command
    return f"{command} {flag} {shlex.quote(str(value))}"


def _safe_numeric(value, default: float = 0.0) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return float(default)
    return float(numeric)


def _resolve_macrostate_key(adata, summary: dict[str, Any]) -> str | None:
    macro_key = summary.get("macrostate_key")
    if macro_key and macro_key in adata.obs.columns:
        return str(macro_key)
    for key in ("macrostates_fwd", "macrostates", "term_states_fwd"):
        if key in adata.obs.columns:
            return key
    return None


def _cluster_summary_df(summary: dict[str, Any]) -> pd.DataFrame:
    per_cluster = summary.get("per_cluster", {})
    if not per_cluster:
        return pd.DataFrame(columns=["cluster", "mean_pseudotime", "median_pseudotime", "n_cells"])

    return (
        pd.DataFrame(
            [{"cluster": str(cluster), **info} for cluster, info in per_cluster.items()]
        )
        .sort_values("mean_pseudotime", ascending=True, kind="mergesort")
        .reset_index(drop=True)
    )


def _build_top_trajectory_genes_table(summary: dict[str, Any], n_top: int = 20) -> pd.DataFrame:
    genes_df = summary.get("trajectory_genes")
    if not isinstance(genes_df, pd.DataFrame) or genes_df.empty:
        return pd.DataFrame(
            columns=["rank", "gene", "correlation", "abs_correlation", "fdr", "direction", "pvalue"]
        )

    out = genes_df.copy().head(n_top)
    out["correlation"] = pd.to_numeric(out["correlation"], errors="coerce")
    out["fdr"] = pd.to_numeric(out["fdr"], errors="coerce")
    out["pvalue"] = pd.to_numeric(out["pvalue"], errors="coerce")
    out["abs_correlation"] = out["correlation"].abs()
    out.insert(0, "rank", np.arange(1, len(out) + 1))
    keep_cols = ["rank", "gene", "correlation", "abs_correlation", "fdr", "direction", "pvalue"]
    return out.loc[:, keep_cols]


def _build_terminal_states_table(summary: dict[str, Any]) -> pd.DataFrame:
    terminal_states = [str(state) for state in summary.get("terminal_states", [])]
    return pd.DataFrame(
        {"rank": np.arange(1, len(terminal_states) + 1), "terminal_state": terminal_states}
    )


def _build_driver_genes_table(summary: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for terminal_state, genes in summary.get("driver_genes", {}).items():
        for rank, gene in enumerate(genes, start=1):
            rows.append({"terminal_state": str(terminal_state), "rank": rank, "gene": str(gene)})
    return pd.DataFrame(rows, columns=["terminal_state", "rank", "gene"])


def _extract_fate_probability_df(adata, summary: dict[str, Any]) -> pd.DataFrame:
    lineage_key = summary.get("lineage_key")
    if lineage_key and lineage_key in adata.obsm:
        values = adata.obsm[lineage_key]
        if isinstance(values, pd.DataFrame):
            df = values.copy()
        else:
            array = np.asarray(values, dtype=float)
            if array.ndim != 2 or array.shape[0] != adata.n_obs:
                return pd.DataFrame()
            columns = [str(state) for state in summary.get("terminal_states", [])]
            if len(columns) != array.shape[1]:
                columns = [f"terminal_state_{idx + 1}" for idx in range(array.shape[1])]
            df = pd.DataFrame(array, index=adata.obs_names.astype(str), columns=columns)
        df.index = df.index.astype(str)
        return df

    branch_probs = summary.get("palantir_branch_probs")
    if isinstance(branch_probs, pd.DataFrame) and not branch_probs.empty:
        df = branch_probs.copy()
        df.index = df.index.astype(str)
        return df.reindex(adata.obs_names.astype(str))

    if "palantir_branch_probs" in adata.obsm:
        array = np.asarray(adata.obsm["palantir_branch_probs"], dtype=float)
        if array.ndim != 2 or array.shape[0] != adata.n_obs:
            return pd.DataFrame()
        columns = [str(col) for col in adata.uns.get("palantir_branch_prob_columns", [])]
        if len(columns) != array.shape[1]:
            columns = [f"terminal_state_{idx + 1}" for idx in range(array.shape[1])]
        return pd.DataFrame(array, index=adata.obs_names.astype(str), columns=columns)

    return pd.DataFrame()


def _annotate_cluster_pseudotime_to_obs(adata, summary: dict[str, Any], cluster_summary: pd.DataFrame) -> dict[str, str]:
    cluster_key = summary.get("cluster_key")
    if cluster_key not in adata.obs.columns or cluster_summary.empty:
        return {}

    lookup = cluster_summary.copy()
    lookup["cluster"] = lookup["cluster"].astype(str)
    lookup = lookup.set_index("cluster")
    labels = adata.obs[cluster_key].astype(str)

    mapping = {
        "cluster_mean_pt_col": ("mean_pseudotime", "traj_cluster_mean_pt"),
        "cluster_median_pt_col": ("median_pseudotime", "traj_cluster_median_pt"),
    }

    resolved: dict[str, str] = {}
    for context_key, (source_col, obs_col) in mapping.items():
        if source_col not in lookup.columns:
            continue
        adata.obs[obs_col] = pd.to_numeric(labels.map(lookup[source_col]), errors="coerce").fillna(0.0)
        resolved[context_key] = obs_col

    return resolved


def _annotate_fate_metrics_to_obs(adata, fate_prob_df: pd.DataFrame) -> dict[str, str]:
    if fate_prob_df.empty:
        return {}

    prob_df = fate_prob_df.copy()
    for column in prob_df.columns:
        prob_df[column] = pd.to_numeric(prob_df[column], errors="coerce").fillna(0.0)

    values = prob_df.to_numpy(dtype=float)
    if values.size == 0:
        return {}

    row_sums = values.sum(axis=1, keepdims=True)
    normalized = np.divide(values, np.clip(row_sums, 1e-12, None))
    max_idx = values.argmax(axis=1)
    top_state = [
        str(prob_df.columns[idx]) if row_sums[row_index, 0] > 0 else "undetermined"
        for row_index, idx in enumerate(max_idx)
    ]
    max_prob = values.max(axis=1)
    entropy = -np.sum(normalized * np.log2(np.clip(normalized, 1e-12, 1.0)), axis=1)

    adata.obs["traj_terminal_state"] = pd.Categorical(top_state)
    adata.obs["traj_fate_max_prob"] = max_prob.astype(float)
    adata.obs["traj_fate_entropy"] = entropy.astype(float)

    return {
        "terminal_state_col": "traj_terminal_state",
        "fate_max_prob_col": "traj_fate_max_prob",
        "fate_entropy_col": "traj_fate_entropy",
    }


def _build_run_summary_table(summary: dict[str, Any], context: dict) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "cluster_key", "value": summary.get("cluster_key")},
        {"metric": "root_cell", "value": summary.get("root_cell")},
        {"metric": "root_cell_type", "value": summary.get("root_cell_type")},
        {"metric": "pseudotime_key", "value": context.get("pseudotime_key")},
        {"metric": "macrostate_key", "value": context.get("macrostate_key")},
        {"metric": "lineage_key", "value": summary.get("lineage_key")},
        {"metric": "kernel_mode", "value": summary.get("kernel_mode")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "mean_pseudotime", "value": summary.get("mean_pseudotime")},
        {"metric": "max_pseudotime", "value": summary.get("max_pseudotime")},
        {"metric": "n_finite", "value": summary.get("n_finite")},
        {"metric": "n_trajectory_genes", "value": summary.get("n_trajectory_genes")},
        {"metric": "n_macrostates", "value": summary.get("n_macrostates")},
        {"metric": "n_terminal_states", "value": summary.get("n_terminal_states", len(summary.get("terminal_states", [])))},
        {"metric": "n_waypoints", "value": summary.get("n_waypoints")},
        {"metric": "mean_entropy", "value": summary.get("mean_entropy")},
        {"metric": "cluster_mean_pt_column", "value": context.get("cluster_mean_pt_col")},
        {"metric": "cluster_median_pt_column", "value": context.get("cluster_median_pt_col")},
        {"metric": "terminal_state_column", "value": context.get("terminal_state_col")},
        {"metric": "fate_max_prob_column", "value": context.get("fate_max_prob_col")},
        {"metric": "fate_entropy_column", "value": context.get("fate_entropy_col")},
        {"metric": "entropy_key", "value": context.get("entropy_key")},
    ]
    return pd.DataFrame(rows)


def _build_projection_table(adata, summary: dict[str, Any], context: dict, basis: str) -> pd.DataFrame | None:
    cluster_key = summary.get("cluster_key")
    pseudotime_key = context.get("pseudotime_key")
    macrostate_key = context.get("macrostate_key")

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
        cluster_key,
        pseudotime_key,
        macrostate_key,
        context.get("cluster_mean_pt_col"),
        context.get("cluster_median_pt_col"),
        context.get("terminal_state_col"),
        context.get("fate_max_prob_col"),
        context.get("fate_entropy_col"),
        context.get("entropy_key"),
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


def _build_diffmap_export_table(adata, summary: dict[str, Any], context: dict) -> pd.DataFrame | None:
    if "X_diffmap" not in adata.obsm:
        return None

    diffmap = np.asarray(adata.obsm["X_diffmap"])
    if diffmap.ndim != 2 or diffmap.shape[1] < 2:
        return None

    df = pd.DataFrame(
        {
            "observation": adata.obs_names.astype(str),
            "diffmap_1": diffmap[:, 0],
            "diffmap_2": diffmap[:, 1],
        }
    )

    for column in (
        summary.get("cluster_key"),
        context.get("pseudotime_key"),
        context.get("terminal_state_col"),
        context.get("fate_max_prob_col"),
        context.get("entropy_key"),
    ):
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


def _prepare_trajectory_plot_state(adata, cluster_key: str | None, macrostate_key: str | None) -> str | None:
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()

    for column in (cluster_key, macrostate_key):
        if column and column in adata.obs.columns and not isinstance(adata.obs[column].dtype, pd.CategoricalDtype):
            adata.obs[column] = pd.Categorical(adata.obs[column].astype(str))

    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute a fallback UMAP so the standard trajectory gallery has an embedding view."""
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
        logger.warning("Could not compute UMAP for trajectory gallery: %s", exc)


def _prepare_trajectory_gallery_context(adata, summary: dict[str, Any]) -> dict[str, Any]:
    macrostate_key = _resolve_macrostate_key(adata, summary)
    spatial_key = _prepare_trajectory_plot_state(adata, summary.get("cluster_key"), macrostate_key)
    _ensure_umap_for_gallery(adata)

    context: dict[str, Any] = {
        "cluster_key": summary.get("cluster_key"),
        "pseudotime_key": summary.get("pseudotime_key") or _detect_pseudotime_key(adata),
        "macrostate_key": macrostate_key,
        "spatial_key": spatial_key,
        "cluster_summary_df": _cluster_summary_df(summary),
        "top_genes_df": _build_top_trajectory_genes_table(summary, n_top=20),
        "terminal_states_df": _build_terminal_states_table(summary),
        "driver_genes_df": _build_driver_genes_table(summary),
        "fate_prob_df": _extract_fate_probability_df(adata, summary),
    }
    context.update(_annotate_cluster_pseudotime_to_obs(adata, summary, context["cluster_summary_df"]))
    context.update(_annotate_fate_metrics_to_obs(adata, context["fate_prob_df"]))
    context["entropy_key"] = _detect_entropy_key(adata)
    return context


def _build_trajectory_visualization_recipe(adata, summary: dict[str, Any], context: dict[str, Any]) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    cluster_key = summary.get("cluster_key")
    pseudotime_key = context.get("pseudotime_key")
    macrostate_key = context.get("macrostate_key")
    entropy_key = context.get("entropy_key")

    if pseudotime_key:
        plots.append(
            PlotSpec(
                plot_id="trajectory_pseudotime_embedding",
                role="overview",
                renderer="trajectory_plot",
                filename="trajectory_pseudotime_embedding.png",
                title=f"Pseudotime Embedding ({pseudotime_key})",
                description="Canonical pseudotime embedding rendered through the shared trajectory visualization primitive.",
                params={
                    "subtype": "pseudotime",
                    "feature": pseudotime_key,
                    "basis": "umap" if "X_umap" in adata.obsm else "pca",
                    "colormap": "viridis",
                    "figure_size": (12, 5),
                },
                required_obs=[pseudotime_key],
            )
        )

    if pseudotime_key and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="trajectory_pseudotime_spatial",
                role="overview",
                renderer="feature_map",
                filename="trajectory_pseudotime_spatial.png",
                title="Pseudotime on Tissue",
                description="Per-observation pseudotime projected back onto spatial coordinates.",
                params={
                    "feature": pseudotime_key,
                    "basis": "spatial",
                    "colormap": "viridis",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (10, 8),
                },
                required_obs=[pseudotime_key],
                required_obsm=["spatial"],
            )
        )

    if macrostate_key and macrostate_key in adata.obs.columns:
        basis = "umap" if "X_umap" in adata.obsm else "spatial"
        required_obsm = ["X_umap"] if basis == "umap" else ["spatial"]
        plots.append(
            PlotSpec(
                plot_id="trajectory_macrostates_map",
                role="overview",
                renderer="feature_map",
                filename=f"trajectory_macrostates_{basis}.png",
                title="Trajectory Macrostates",
                description="Categorical macrostate assignments from CellRank projected onto the shared embedding or tissue.",
                params={
                    "feature": macrostate_key,
                    "basis": basis,
                    "colormap": "tab20",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (8, 6) if basis == "umap" else (10, 8),
                },
                required_obs=[macrostate_key],
                required_obsm=required_obsm,
            )
        )

    if "X_diffmap" in adata.obsm and pseudotime_key:
        plots.append(
            PlotSpec(
                plot_id="trajectory_diffmap",
                role="diagnostic",
                renderer="diffmap_scatter",
                filename="trajectory_diffmap.png",
                title="Diffusion Map Diagnostic",
                description="First two diffusion components colored by the active pseudotime signal.",
                required_obs=[pseudotime_key],
                required_obsm=["X_diffmap"],
            )
        )

    if context.get("fate_max_prob_col"):
        basis = "umap" if "X_umap" in adata.obsm else "spatial"
        required_obsm = ["X_umap"] if basis == "umap" else ["spatial"]
        plots.append(
            PlotSpec(
                plot_id="trajectory_fate_confidence_map",
                role="diagnostic",
                renderer="feature_map",
                filename=f"trajectory_fate_confidence_{basis}.png",
                title="Fate Confidence",
                description="Maximum branch or fate probability projected back onto the shared coordinates.",
                params={
                    "feature": context["fate_max_prob_col"],
                    "basis": basis,
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (8, 6) if basis == "umap" else (10, 8),
                },
                required_obs=[context["fate_max_prob_col"]],
                required_obsm=required_obsm,
            )
        )

    if entropy_key:
        basis = "umap" if "X_umap" in adata.obsm else "spatial"
        required_obsm = ["X_umap"] if basis == "umap" else ["spatial"]
        plots.append(
            PlotSpec(
                plot_id="trajectory_entropy_map",
                role="diagnostic",
                renderer="feature_map",
                filename=f"trajectory_entropy_{basis}.png",
                title="Trajectory Entropy",
                description="Palantir entropy or generic fate entropy projected onto the shared coordinates.",
                params={
                    "feature": entropy_key,
                    "basis": basis,
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (8, 6) if basis == "umap" else (10, 8),
                },
                required_obs=[entropy_key],
                required_obsm=required_obsm,
            )
        )

    if not context["cluster_summary_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="trajectory_cluster_summary",
                role="supporting",
                renderer="cluster_summary_barplot",
                filename="trajectory_cluster_summary.png",
                title="Per-Cluster Pseudotime Summary",
                description="Mean and median pseudotime summarized by the resolved cluster or annotation column.",
            )
        )

    if not context["top_genes_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="trajectory_gene_barplot",
                role="supporting",
                renderer="trajectory_gene_barplot",
                filename="trajectory_genes_barplot.png",
                title="Top Trajectory-Correlated Genes",
                description="Genes with the strongest correlation to the active scalar pseudotime ordering.",
            )
        )

    if summary.get("method") == "cellrank" and summary.get("lineage_key") in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="trajectory_cellrank_circular",
                role="supporting",
                renderer="trajectory_plot",
                filename="cellrank_fate_circular.png",
                title="CellRank Circular Fate Projection",
                description="Circular projection of CellRank fate probabilities using the shared trajectory renderer.",
                params={"subtype": "circular", "cluster_key": cluster_key},
                required_obsm=[summary["lineage_key"]],
            )
        )
        if cluster_key and cluster_key in adata.obs.columns:
            plots.append(
                PlotSpec(
                    plot_id="trajectory_cellrank_fate_map",
                    role="supporting",
                    renderer="trajectory_plot",
                    filename="cellrank_fate_map.png",
                    title="CellRank Fate Map",
                    description="Aggregated CellRank fate probabilities by the resolved cluster or annotation column.",
                    params={"subtype": "fate_map", "cluster_key": cluster_key},
                    required_obs=[cluster_key],
                    required_obsm=[summary["lineage_key"]],
                )
            )

        gene_list = context["top_genes_df"]["gene"].astype(str).head(5).tolist()
        if gene_list and pseudotime_key:
            plots.append(
                PlotSpec(
                    plot_id="trajectory_cellrank_gene_trends",
                    role="supporting",
                    renderer="trajectory_plot",
                    filename="cellrank_gene_trends.png",
                    title="CellRank Gene Trends",
                    description="CellRank GAM-smoothed gene trends along the active pseudotime axis.",
                    params={"subtype": "gene_trends", "feature": gene_list, "figure_size": (10, 6)},
                    required_obs=[pseudotime_key],
                )
            )
            plots.append(
                PlotSpec(
                    plot_id="trajectory_cellrank_fate_heatmap",
                    role="uncertainty",
                    renderer="trajectory_plot",
                    filename="cellrank_fate_heatmap.png",
                    title="CellRank Fate Heatmap",
                    description="Smoothed expression heatmap ordered by pseudotime for the strongest trajectory genes.",
                    params={"subtype": "fate_heatmap", "feature": gene_list},
                    required_obs=[pseudotime_key],
                )
            )

    if pseudotime_key:
        plots.append(
            PlotSpec(
                plot_id="trajectory_pseudotime_distribution",
                role="uncertainty",
                renderer="metric_histogram",
                filename="trajectory_pseudotime_distribution.png",
                title="Pseudotime Distribution",
                description="Distribution of the active pseudotime values across observations.",
                params={"metric": pseudotime_key, "xlabel": "Pseudotime"},
                required_obs=[pseudotime_key],
            )
        )

    if context.get("fate_max_prob_col"):
        plots.append(
            PlotSpec(
                plot_id="trajectory_fate_probability_distribution",
                role="uncertainty",
                renderer="metric_histogram",
                filename="trajectory_fate_probability_distribution.png",
                title="Fate Confidence Distribution",
                description="Distribution of the per-observation maximum fate or branch probability.",
                params={"metric": context["fate_max_prob_col"], "xlabel": "Max fate probability"},
                required_obs=[context["fate_max_prob_col"]],
            )
        )

    if entropy_key:
        plots.append(
            PlotSpec(
                plot_id="trajectory_entropy_distribution",
                role="uncertainty",
                renderer="metric_histogram",
                filename="trajectory_entropy_distribution.png",
                title="Trajectory Entropy Distribution",
                description="Distribution of Palantir branch entropy or generic fate entropy values.",
                params={"metric": entropy_key, "xlabel": "Entropy"},
                required_obs=[entropy_key],
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-trajectory-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Trajectory Standard Gallery",
        description=(
            "Default OmicsClaw trajectory story plots: pseudotime overviews, "
            "fate and entropy diagnostics, supporting summaries, and uncertainty "
            "panels built from shared trajectory and feature-map visualization primitives."
        ),
        plots=plots,
    )


def _render_trajectory_plot(adata, spec: PlotSpec, _context: dict) -> object:
    viz_params = VizParams(**spec.params)
    return plot_trajectory(
        adata,
        viz_params,
        subtype=spec.params.get("subtype"),
        cluster_key=spec.params.get("cluster_key"),
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_diffmap_scatter(adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    pseudotime_key = context.get("pseudotime_key")
    if pseudotime_key not in adata.obs.columns or "X_diffmap" not in adata.obsm:
        return None

    diffmap = np.asarray(adata.obsm["X_diffmap"])
    if diffmap.shape[1] < 2:
        return None

    values = pd.to_numeric(adata.obs[pseudotime_key], errors="coerce").fillna(0.0).to_numpy()
    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 6)), dpi=200)
    scatter = ax.scatter(
        diffmap[:, 0],
        diffmap[:, 1],
        c=values,
        cmap=spec.params.get("colormap", "viridis"),
        s=18,
        alpha=0.85,
    )
    root_cell = context["summary"].get("root_cell")
    if root_cell is not None:
        obs_names = adata.obs_names.astype(str)
        matches = np.where(obs_names == str(root_cell))[0]
        if len(matches) > 0:
            idx = int(matches[0])
            ax.scatter(diffmap[idx, 0], diffmap[idx, 1], marker="*", s=120, c="black", edgecolors="white")
    fig.colorbar(scatter, ax=ax, label=pseudotime_key)
    ax.set_xlabel("Diffusion component 1")
    ax.set_ylabel("Diffusion component 2")
    ax.set_title(spec.title or "Diffusion Map Diagnostic")
    fig.tight_layout()
    return fig


def _render_cluster_summary_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    cluster_summary = context.get("cluster_summary_df", pd.DataFrame())
    if cluster_summary.empty:
        return None

    plot_df = cluster_summary.copy().iloc[::-1]
    y = np.arange(len(plot_df))
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(plot_df) * 0.5))),
        dpi=200,
    )
    ax.barh(y - 0.18, plot_df["mean_pseudotime"], height=0.32, color="#2b8cbe", label="Mean")
    ax.barh(y + 0.18, plot_df["median_pseudotime"], height=0.32, color="#a6bddb", label="Median")
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["cluster"].astype(str))
    ax.set_xlabel("Pseudotime")
    ax.set_title(spec.title or "Per-Cluster Pseudotime Summary")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def _render_trajectory_gene_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    top_genes = context.get("top_genes_df", pd.DataFrame())
    if top_genes.empty:
        return None

    plot_df = top_genes.head(12).copy().iloc[::-1]
    colors = np.where(plot_df["correlation"] >= 0, "#1b9e77", "#d95f02")
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.8, max(4.8, len(plot_df) * 0.45))),
        dpi=200,
    )
    ax.barh(plot_df["gene"].astype(str), plot_df["correlation"], color=colors, alpha=0.9)
    ax.axvline(0.0, color="black", linestyle="--", linewidth=1.0)
    ax.set_xlabel("Spearman correlation with pseudotime")
    ax.set_ylabel("Gene")
    ax.set_title(spec.title or "Top Trajectory-Correlated Genes")
    fig.tight_layout()
    return fig


def _render_metric_histogram(adata, spec: PlotSpec, _context: dict) -> object:
    import matplotlib.pyplot as plt

    metric = spec.params.get("metric")
    if not metric or metric not in adata.obs.columns:
        return None

    values = pd.to_numeric(adata.obs[metric], errors="coerce").dropna()
    if values.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(values, bins=25, color="#756bb1", edgecolor="white")
    ax.set_xlabel(spec.params.get("xlabel", str(metric)))
    ax.set_ylabel("Number of observations")
    ax.set_title(spec.title or str(metric))
    fig.tight_layout()
    return fig


TRAJECTORY_GALLERY_RENDERERS = {
    "trajectory_plot": _render_trajectory_plot,
    "feature_map": _render_feature_map,
    "diffmap_scatter": _render_diffmap_scatter,
    "cluster_summary_barplot": _render_cluster_summary_barplot,
    "trajectory_gene_barplot": _render_trajectory_gene_barplot,
    "metric_histogram": _render_metric_histogram,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def _export_figure_data(
    adata,
    output_dir: Path,
    summary: dict[str, Any],
    recipe: VisualizationRecipe,
    artifacts: list,
    context: dict[str, Any],
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    trajectory_summary = pd.DataFrame(
        [
            {"metric": "n_cells", "value": summary.get("n_cells")},
            {"metric": "n_genes", "value": summary.get("n_genes")},
            {"metric": "mean_pseudotime", "value": summary.get("mean_pseudotime")},
            {"metric": "max_pseudotime", "value": summary.get("max_pseudotime")},
            {"metric": "n_finite", "value": summary.get("n_finite")},
            {"metric": "n_trajectory_genes", "value": summary.get("n_trajectory_genes")},
        ]
    )
    trajectory_summary.to_csv(figure_data_dir / "trajectory_summary.csv", index=False)

    context.get("cluster_summary_df", pd.DataFrame()).to_csv(
        figure_data_dir / "trajectory_cluster_summary.csv",
        index=False,
    )
    top_genes_df = summary.get("trajectory_genes")
    if isinstance(top_genes_df, pd.DataFrame) and not top_genes_df.empty:
        top_genes_df.to_csv(figure_data_dir / "trajectory_genes.csv", index=False)
    else:
        pd.DataFrame().to_csv(figure_data_dir / "trajectory_genes.csv", index=False)

    context.get("terminal_states_df", pd.DataFrame()).to_csv(
        figure_data_dir / "trajectory_terminal_states.csv",
        index=False,
    )
    context.get("driver_genes_df", pd.DataFrame()).to_csv(
        figure_data_dir / "trajectory_driver_genes.csv",
        index=False,
    )
    _build_run_summary_table(summary, context).to_csv(
        figure_data_dir / "trajectory_run_summary.csv",
        index=False,
    )

    fate_prob_file = None
    if not context.get("fate_prob_df", pd.DataFrame()).empty:
        fate_prob_file = "trajectory_fate_probabilities.csv"
        fate_prob_df = context["fate_prob_df"].copy()
        fate_prob_df.index = fate_prob_df.index.astype(str)
        fate_prob_long = (
            fate_prob_df.rename_axis("observation")
            .reset_index()
            .melt(id_vars="observation", var_name="terminal_state", value_name="probability")
        )
        fate_prob_long.to_csv(figure_data_dir / fate_prob_file, index=False)

    spatial_file = None
    spatial_df = _build_projection_table(adata, summary, context, "spatial")
    if spatial_df is not None:
        spatial_file = "trajectory_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_projection_table(adata, summary, context, "umap")
    if umap_df is not None:
        umap_file = "trajectory_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    diffmap_file = None
    diffmap_df = _build_diffmap_export_table(adata, summary, context)
    if diffmap_df is not None:
        diffmap_file = "trajectory_diffmap_points.csv"
        diffmap_df.to_csv(figure_data_dir / diffmap_file, index=False)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "cluster_key": summary.get("cluster_key"),
        "pseudotime_key": context.get("pseudotime_key"),
        "macrostate_key": context.get("macrostate_key"),
        "lineage_key": summary.get("lineage_key"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "available_files": {
            "trajectory_summary": "trajectory_summary.csv",
            "trajectory_cluster_summary": "trajectory_cluster_summary.csv",
            "trajectory_genes": "trajectory_genes.csv",
            "trajectory_terminal_states": "trajectory_terminal_states.csv",
            "trajectory_driver_genes": "trajectory_driver_genes.csv",
            "trajectory_run_summary": "trajectory_run_summary.csv",
            "trajectory_fate_probabilities": fate_prob_file,
            "trajectory_spatial_points": spatial_file,
            "trajectory_umap_points": umap_file,
            "trajectory_diffmap_points": diffmap_file,
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
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> list[str]:
    """Render the standard trajectory gallery and export figure-ready data."""
    context = gallery_context or _prepare_trajectory_gallery_context(adata, summary)
    recipe = _build_trajectory_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        TRAJECTORY_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report / exports
# ---------------------------------------------------------------------------


def _json_ready_summary(summary: dict[str, Any]) -> dict[str, Any]:
    result = dict(summary)
    if isinstance(result.get("trajectory_genes"), pd.DataFrame):
        result["trajectory_genes"] = result["trajectory_genes"].to_dict(orient="records")
    if isinstance(result.get("palantir_branch_probs"), pd.DataFrame):
        result["palantir_branch_probs"] = {
            "n_rows": int(result["palantir_branch_probs"].shape[0]),
            "n_cols": int(result["palantir_branch_probs"].shape[1]),
            "columns": result["palantir_branch_probs"].columns.astype(str).tolist(),
        }
    return result


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-trajectory"
        / "r_visualization"
        / "trajectory_publication_template.R"
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
    """Write markdown report and result JSON."""
    header = generate_report_header(
        title="Spatial Trajectory Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", "dpt"),
            "Cluster key": summary.get("cluster_key", "auto") or "not detected",
            "Root cell": summary.get("root_cell", "auto"),
        },
    )

    effective_params = summary.get("effective_params", {})
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Cluster key**: {summary.get('cluster_key') or 'not detected'}",
        f"- **Root cell**: {summary.get('root_cell', 'auto')}",
        f"- **Pseudotime key**: {summary.get('pseudotime_key', gallery_context.get('pseudotime_key') if gallery_context else 'n/a')}",
        f"- **Mean pseudotime**: {summary.get('mean_pseudotime', 0):.4f}",
        f"- **Max pseudotime**: {summary.get('max_pseudotime', 0):.4f}",
        f"- **Cells with finite pseudotime**: {summary.get('n_finite', 0)}",
        f"- **Trajectory-correlated genes**: {summary.get('n_trajectory_genes', 0)}",
    ]

    if gallery_context and gallery_context.get("fate_max_prob_col"):
        body_lines.append(f"- **Observation-level fate-confidence column**: `{gallery_context['fate_max_prob_col']}`")
    if gallery_context and gallery_context.get("entropy_key"):
        body_lines.append(f"- **Observation-level entropy column**: `{gallery_context['entropy_key']}`")

    if summary["method"] == "cellrank":
        body_lines.extend(
            [
                "",
                "### CellRank Runtime Details\n",
                f"- **Kernel mode**: {summary.get('kernel_mode', 'unknown')}",
                f"- **Macrostates**: {summary.get('n_macrostates', 0)}",
                f"- **Terminal states**: {', '.join(summary.get('terminal_states', [])) or 'not identified'}",
            ]
        )
    elif summary["method"] == "palantir":
        body_lines.extend(
            [
                "",
                "### Palantir Runtime Details\n",
                f"- **Waypoints**: {summary.get('n_waypoints', 0)}",
                f"- **Terminal states**: {', '.join(summary.get('terminal_states', [])) or 'not identified'}",
                f"- **Mean branch entropy**: {summary.get('mean_entropy', 0):.4f}",
            ]
        )

    cluster_summary_df = _cluster_summary_df(summary)
    if not cluster_summary_df.empty:
        body_lines.extend(
            [
                "",
                "### Pseudotime Per Cluster\n",
                "| Cluster | Mean PT | Median PT | Cells |",
                "|---------|---------|-----------|-------|",
            ]
        )
        for _, row in cluster_summary_df.iterrows():
            body_lines.append(
                f"| {row['cluster']} | {row['mean_pseudotime']:.3f} | {row['median_pseudotime']:.3f} | {int(row['n_cells'])} |"
            )

    top_genes_df = _build_top_trajectory_genes_table(summary, n_top=10)
    if not top_genes_df.empty:
        body_lines.extend(
            [
                "",
                "### Top Trajectory Genes\n",
                "| Gene | Correlation | FDR | Direction |",
                "|------|-------------|-----|-----------|",
            ]
        )
        for _, row in top_genes_df.iterrows():
            body_lines.append(
                f"| {row['gene']} | {row['correlation']:.4f} | {row['fdr']:.4g} | {row['direction']} |"
            )

    driver_genes_df = _build_driver_genes_table(summary)
    if not driver_genes_df.empty:
        body_lines.extend(["", "### Driver Genes\n"])
        for terminal_state, group_df in driver_genes_df.groupby("terminal_state", sort=False):
            body_lines.append(f"- **{terminal_state}**: {', '.join(group_df['gene'].astype(str).tolist())}")

    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    if effective_params:
        body_lines.extend(["", "### Effective Method Parameters\n"])
        for key, value in effective_params.items():
            body_lines.append(f"- `{key}`: {value}")

    body_lines.extend(["", "## Interpretation Notes\n"])
    if summary["method"] == "dpt":
        body_lines.extend(
            [
                "- `dpt` here is scalar diffusion pseudotime on the existing preprocessing graph, not a fate-probability model.",
                "- The root choice changes the biological direction of pseudotime and should be reported whenever results are interpreted.",
                "- `trajectory_genes` are genes correlated with the selected scalar pseudotime ordering, not lineage-specific drivers.",
            ]
        )
    elif summary["method"] == "cellrank":
        body_lines.extend(
            [
                "- `cellrank` here builds on the preprocessing graph plus a CellRank kernel stack; its macrostates and fate probabilities should not be flattened into generic pseudotime.",
                "- The reported `kernel_mode` is the actual backend path that ran and may differ from the originally requested preference.",
                "- Driver genes are lineage-oriented CellRank outputs and should be interpreted alongside terminal states and fate confidence.",
            ]
        )
    else:
        body_lines.extend(
            [
                "- `palantir` here provides pseudotime plus branch entropy and branch probabilities when available.",
                "- Palantir branch entropy is not a CellRank fate probability and should be explained separately.",
                "- Waypoint and diffusion-space settings change the inferred manifold geometry and are not cosmetic plotting parameters.",
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
    json_summary = _json_ready_summary(summary)
    result_data: dict[str, Any] = {"params": params, "effective_params": effective_params, **json_summary}
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-trajectory-gallery",
            "pseudotime_key": gallery_context.get("pseudotime_key"),
            "macrostate_key": gallery_context.get("macrostate_key"),
            "cluster_mean_pt_column": gallery_context.get("cluster_mean_pt_col"),
            "cluster_median_pt_column": gallery_context.get("cluster_median_pt_col"),
            "terminal_state_column": gallery_context.get("terminal_state_col"),
            "fate_max_prob_column": gallery_context.get("fate_max_prob_col"),
            "fate_entropy_column": gallery_context.get("fate_entropy_col"),
            "entropy_key": gallery_context.get("entropy_key"),
        }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=json_summary,
        data=result_data,
        input_checksum=checksum,
    )


def export_tables(
    output_dir: Path,
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> list[str]:
    """Export tabular outputs."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []

    trajectory_summary = pd.DataFrame(
        [
            {"metric": "n_cells", "value": summary.get("n_cells")},
            {"metric": "n_genes", "value": summary.get("n_genes")},
            {"metric": "mean_pseudotime", "value": summary.get("mean_pseudotime", np.nan)},
            {"metric": "max_pseudotime", "value": summary.get("max_pseudotime", np.nan)},
            {"metric": "n_finite", "value": summary.get("n_finite", np.nan)},
            {"metric": "n_trajectory_genes", "value": summary.get("n_trajectory_genes", 0)},
        ]
    )
    path = tables_dir / "trajectory_summary.csv"
    trajectory_summary.to_csv(path, index=False)
    exported.append(str(path))

    cluster_summary_df = (
        gallery_context.get("cluster_summary_df")
        if gallery_context is not None
        else _cluster_summary_df(summary)
    )
    path = tables_dir / "trajectory_cluster_summary.csv"
    cluster_summary_df.to_csv(path, index=False)
    exported.append(str(path))

    genes_df = summary.get("trajectory_genes")
    path = tables_dir / "trajectory_genes.csv"
    if isinstance(genes_df, pd.DataFrame):
        genes_df.to_csv(path, index=False)
    else:
        pd.DataFrame().to_csv(path, index=False)
    exported.append(str(path))

    terminal_states_df = (
        gallery_context.get("terminal_states_df")
        if gallery_context is not None
        else _build_terminal_states_table(summary)
    )
    if not terminal_states_df.empty:
        path = tables_dir / "trajectory_terminal_states.csv"
        terminal_states_df.to_csv(path, index=False)
        exported.append(str(path))

        method_specific_path = tables_dir / f"{summary['method']}_terminal_states.csv"
        terminal_states_df[["terminal_state"]].to_csv(method_specific_path, index=False)
        exported.append(str(method_specific_path))

    driver_genes_df = (
        gallery_context.get("driver_genes_df")
        if gallery_context is not None
        else _build_driver_genes_table(summary)
    )
    if not driver_genes_df.empty:
        path = tables_dir / "trajectory_driver_genes.csv"
        driver_genes_df.to_csv(path, index=False)
        exported.append(str(path))

        if summary.get("method") == "cellrank":
            alias_path = tables_dir / "cellrank_driver_genes.csv"
            driver_genes_df.to_csv(alias_path, index=False)
            exported.append(str(alias_path))

    if gallery_context is not None and not gallery_context.get("fate_prob_df", pd.DataFrame()).empty:
        fate_prob_df = gallery_context["fate_prob_df"].copy()
        fate_prob_df.to_csv(tables_dir / "trajectory_fate_probabilities_wide.csv")
        exported.append(str(tables_dir / "trajectory_fate_probabilities_wide.csv"))

    palantir_branch_probs = summary.get("palantir_branch_probs")
    if isinstance(palantir_branch_probs, pd.DataFrame) and not palantir_branch_probs.empty:
        path = tables_dir / "palantir_branch_probs.csv"
        palantir_branch_probs.to_csv(path)
        exported.append(str(path))

    return exported


def write_reproducibility(
    output_dir: Path,
    summary: dict[str, Any],
    params: dict[str, Any],
    input_file: str | None,
    *,
    demo_mode: bool = False,
) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    command = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--demo' if demo_mode else '--input <input.h5ad>'} "
        f"--output {shlex.quote(str(output_dir))}"
    )
    repro_params = {
        "method": params.get("method"),
        "cluster_key": summary.get("cluster_key", params.get("cluster_key")),
        "root_cell": summary.get("root_cell", params.get("root_cell")),
        "root_cell_type": params.get("root_cell_type"),
    }
    repro_params.update(summary.get("effective_params", {}))
    for key, value in repro_params.items():
        command = _append_cli_flag(command, key, value)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n")
    _write_r_visualization_helper(output_dir)

    try:
        from importlib.metadata import version as get_version
    except ImportError:
        from importlib_metadata import version as get_version  # type: ignore

    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "scipy"]:
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            env_lines.append(f"{pkg}=?")
        except Exception:
            env_lines.append(f"{pkg}=?")

    optional_by_method = {
        "cellrank": ["cellrank"],
        "palantir": ["palantir"],
    }
    for pkg in optional_by_method.get(summary["method"], []):
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            env_lines.append(f"{pkg}=?")
        except Exception:
            env_lines.append(f"{pkg}=?")

    requirements_text = "\n".join(dict.fromkeys(env_lines)) + "\n"
    (repro_dir / "requirements.txt").write_text(requirements_text)
    (repro_dir / "environment.txt").write_text(requirements_text)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo and load processed output."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_traj_demo_") as tmp_dir:
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
        logger.info("Loaded demo data: %d cells x %d genes", adata.n_obs, adata.n_vars)
        return adata, None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Spatial Trajectory — pseudotime and trajectory inference",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="dpt", choices=list(SUPPORTED_METHODS))
    parser.add_argument(
        "--cluster-key",
        default=None,
        help="obs column containing cluster / annotation labels (auto-detected if omitted)",
    )
    parser.add_argument("--root-cell", default=None, help="Exact root / early cell barcode")
    parser.add_argument(
        "--root-cell-type",
        default=None,
        help="Select root / early cell from this cluster / annotation label",
    )
    parser.add_argument(
        "--dpt-n-dcs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["dpt"]["n_dcs"],
    )
    parser.add_argument(
        "--cellrank-n-states",
        type=int,
        default=METHOD_PARAM_DEFAULTS["cellrank"]["n_states"],
    )
    parser.add_argument(
        "--cellrank-schur-components",
        type=int,
        default=METHOD_PARAM_DEFAULTS["cellrank"]["schur_components"],
    )
    parser.add_argument(
        "--cellrank-frac-to-keep",
        type=float,
        default=METHOD_PARAM_DEFAULTS["cellrank"]["frac_to_keep"],
    )
    parser.add_argument(
        "--cellrank-use-velocity",
        action="store_true",
        default=METHOD_PARAM_DEFAULTS["cellrank"]["use_velocity"],
    )
    parser.add_argument(
        "--palantir-n-components",
        type=int,
        default=METHOD_PARAM_DEFAULTS["palantir"]["n_components"],
    )
    parser.add_argument(
        "--palantir-knn",
        type=int,
        default=METHOD_PARAM_DEFAULTS["palantir"]["knn"],
    )
    parser.add_argument(
        "--palantir-num-waypoints",
        type=int,
        default=METHOD_PARAM_DEFAULTS["palantir"]["num_waypoints"],
    )
    parser.add_argument(
        "--palantir-max-iterations",
        type=int,
        default=METHOD_PARAM_DEFAULTS["palantir"]["max_iterations"],
    )
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.demo:
        if not args.input_path:
            parser.error("Provide --input or --demo")
        if args.input_path and not Path(args.input_path).exists():
            parser.error(f"Input file not found: {args.input_path}")

    if args.dpt_n_dcs <= 0:
        parser.error("--dpt-n-dcs must be > 0")
    if args.cellrank_n_states <= 1:
        parser.error("--cellrank-n-states must be > 1")
    if args.cellrank_schur_components <= 1:
        parser.error("--cellrank-schur-components must be > 1")
    if not (0 < args.cellrank_frac_to_keep <= 1):
        parser.error("--cellrank-frac-to-keep must be in (0, 1]")
    if args.palantir_n_components <= 1:
        parser.error("--palantir-n-components must be > 1")
    if args.palantir_knn <= 1:
        parser.error("--palantir-knn must be > 1")
    if args.palantir_num_waypoints <= 0:
        parser.error("--palantir-num-waypoints must be > 0")
    if args.palantir_max_iterations <= 0:
        parser.error("--palantir-max-iterations must be > 0")


def _resolve_cluster_key(adata, requested_key: str | None) -> str | None:
    if requested_key:
        if requested_key not in adata.obs.columns:
            raise ValueError(f"Cluster key '{requested_key}' not found in adata.obs")
        return requested_key

    return detect_cluster_key(adata)


def _validate_runtime_inputs(
    adata,
    *,
    cluster_key: str | None,
    root_cell: str | None,
    root_cell_type: str | None,
) -> None:
    if "X_pca" not in adata.obsm:
        raise ValueError(
            "PCA embedding not found in adata.obsm['X_pca']. "
            "Run spatial-preprocess first so trajectory uses an explicit preprocessing state."
        )
    if "neighbors" not in adata.uns:
        raise ValueError(
            "Neighbor graph not found in adata.uns['neighbors']. "
            "Run spatial-preprocess first so trajectory does not silently rebuild the graph."
        )
    if root_cell and str(root_cell) not in adata.obs_names.astype(str):
        raise ValueError(f"Root cell '{root_cell}' not found in adata.obs_names")
    if root_cell_type and not cluster_key:
        raise ValueError(
            "Could not resolve a cluster annotation column for --root-cell-type. "
            "Provide --cluster-key explicitly."
        )
    if root_cell_type and cluster_key and cluster_key not in adata.obs.columns:
        raise ValueError(f"Cluster key '{cluster_key}' not found in adata.obs")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    params: dict[str, Any] = {
        "method": args.method,
        "cluster_key": args.cluster_key,
        "root_cell": args.root_cell,
        "root_cell_type": args.root_cell_type,
    }
    method_kwargs: dict[str, Any] = {}

    if args.method == "dpt":
        params["dpt_n_dcs"] = args.dpt_n_dcs
        method_kwargs["dpt_n_dcs"] = args.dpt_n_dcs
    elif args.method == "cellrank":
        params.update(
            {
                "dpt_n_dcs": args.dpt_n_dcs,
                "cellrank_n_states": args.cellrank_n_states,
                "cellrank_schur_components": args.cellrank_schur_components,
                "cellrank_frac_to_keep": args.cellrank_frac_to_keep,
                "cellrank_use_velocity": args.cellrank_use_velocity,
            }
        )
        method_kwargs.update(
            {
                "dpt_n_dcs": args.dpt_n_dcs,
                "cellrank_n_states": args.cellrank_n_states,
                "cellrank_schur_components": args.cellrank_schur_components,
                "cellrank_frac_to_keep": args.cellrank_frac_to_keep,
                "cellrank_use_velocity": args.cellrank_use_velocity,
            }
        )
    else:
        params.update(
            {
                "palantir_n_components": args.palantir_n_components,
                "palantir_knn": args.palantir_knn,
                "palantir_num_waypoints": args.palantir_num_waypoints,
                "palantir_max_iterations": args.palantir_max_iterations,
            }
        )
        method_kwargs.update(
            {
                "palantir_n_components": args.palantir_n_components,
                "palantir_knn": args.palantir_knn,
                "palantir_num_waypoints": args.palantir_num_waypoints,
                "palantir_max_iterations": args.palantir_max_iterations,
            }
        )

    return params, method_kwargs


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    else:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    resolved_cluster_key = _resolve_cluster_key(adata, args.cluster_key)
    _validate_runtime_inputs(
        adata,
        cluster_key=resolved_cluster_key,
        root_cell=args.root_cell,
        root_cell_type=args.root_cell_type,
    )

    params, method_kwargs = _collect_run_configuration(args)
    params["cluster_key"] = resolved_cluster_key

    summary = run_trajectory(
        adata,
        method=args.method,
        cluster_key=resolved_cluster_key,
        root_cell=args.root_cell,
        root_cell_type=args.root_cell_type,
        **method_kwargs,
    )

    gallery_context = _prepare_trajectory_gallery_context(adata, summary)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, summary, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, summary, params, input_file, demo_mode=args.demo)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Trajectory complete ({summary['method']}): "
        f"root={summary.get('root_cell', 'auto')}, "
        f"pseudotime_key={summary.get('pseudotime_key', 'n/a')}, "
        f"trajectory_genes={summary.get('n_trajectory_genes', 0)}"
    )


if __name__ == "__main__":
    main()
