#!/usr/bin/env python3
"""Spatial Velocity — method-aware RNA velocity for spatial transcriptomics."""

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
from typing import Any

import matplotlib.pyplot as plt
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
from skills.spatial._lib.dependency_manager import require
from skills.spatial._lib.velocity import (
    SCVELO_METHODS,
    SUPPORTED_METHODS,
    add_demo_velocity_layers,
    run_velocity,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_features,
    plot_velocity,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-velocity"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-velocity/spatial_velocity.py"
BOOL_NEGATIVE_FLAGS = {
    "velocity_use_highly_variable": "--no-velocity-use-highly-variable",
    "velocity_graph_sqrt_transform": "--no-velocity-graph-sqrt-transform",
    "velocity_graph_approx": "--no-velocity-graph-approx",
    "velocity_fit_offset": "--no-velocity-fit-offset",
    "velocity_fit_offset2": "--no-velocity-fit-offset2",
    "dynamical_fit_time": "--no-dynamical-fit-time",
    "dynamical_fit_scaling": "--no-dynamical-fit-scaling",
    "dynamical_fit_steady_states": "--no-dynamical-fit-steady-states",
    "velovi_early_stopping": "--no-velovi-early-stopping",
}


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------


def _json_safe_summary(summary: dict) -> dict:
    out = {}
    for key, value in summary.items():
        if isinstance(value, (pd.DataFrame, pd.Series, np.ndarray)):
            continue
        out[key] = value
    return out


def _format_value(value) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "NA"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.4g}"
    return str(value)


def _markdown_table(
    df: pd.DataFrame,
    *,
    columns: list[str],
    headers: list[str] | None = None,
    limit: int = 10,
) -> list[str]:
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


def _safe_numeric_series(values) -> pd.Series:
    return pd.to_numeric(pd.Series(values), errors="coerce")


def _coerce_obs_value(series: pd.Series) -> np.ndarray:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").fillna(0.0).to_numpy()
    return series.astype(str).to_numpy()


def _params_to_cli_tokens(params: dict) -> list[str]:
    tokens: list[str] = []
    for key, value in params.items():
        if value is None:
            continue
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                tokens.append(flag)
            else:
                negative = BOOL_NEGATIVE_FLAGS.get(key)
                if negative:
                    tokens.append(negative)
            continue
        tokens.extend([flag, str(value)])
    return tokens


def _interpretation_notes(summary: dict) -> list[str]:
    method = summary["method"]
    if method == "stochastic":
        return [
            "- `stochastic` is the default first-pass scVelo model; it is robust, but still depends strongly on the chosen moment graph.",
            "- High `velocity_confidence` supports local directional consistency, not automatic proof of a lineage mechanism.",
        ]
    if method == "deterministic":
        return [
            "- `deterministic` assumes a steady-state approximation and is best framed as a simpler kinetic baseline than `dynamical`.",
            "- If `deterministic` and `stochastic` disagree sharply, inspect graph and preprocessing settings before over-interpreting biology.",
        ]
    if method == "dynamical":
        return [
            "- `dynamical` fits transcription, splicing, and degradation kinetics and should be interpreted together with latent-time support.",
            "- `latent_time` is model-derived ordering, not an absolute biological clock.",
        ]
    return [
        "- `velovi` is a variational posterior model; its latent-time and velocity estimates depend on training settings as well as preprocessing.",
        "- VELOVI outputs are useful for smoother posterior summaries, but users should report `max_epochs`, `n_samples`, and graph settings alongside biological claims.",
    ]


# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------


def _collect_run_configuration(args: argparse.Namespace) -> dict:
    params = {
        "method": args.method,
        "cluster_key": args.cluster_key,
        "velocity_min_shared_counts": args.velocity_min_shared_counts,
        "velocity_n_top_genes": args.velocity_n_top_genes,
        "velocity_n_pcs": args.velocity_n_pcs,
        "velocity_n_neighbors": args.velocity_n_neighbors,
        "velocity_use_highly_variable": args.velocity_use_highly_variable,
        "velocity_graph_n_neighbors": args.velocity_graph_n_neighbors,
        "velocity_graph_sqrt_transform": args.velocity_graph_sqrt_transform,
        "velocity_graph_approx": args.velocity_graph_approx,
    }

    if args.method in SCVELO_METHODS:
        params.update(
            {
                "velocity_fit_offset": args.velocity_fit_offset,
                "velocity_fit_offset2": args.velocity_fit_offset2,
                "velocity_min_r2": args.velocity_min_r2,
                "velocity_min_likelihood": args.velocity_min_likelihood,
            }
        )
    if args.method == "dynamical":
        params.update(
            {
                "dynamical_n_top_genes": args.dynamical_n_top_genes,
                "dynamical_max_iter": args.dynamical_max_iter,
                "dynamical_fit_time": args.dynamical_fit_time,
                "dynamical_fit_scaling": args.dynamical_fit_scaling,
                "dynamical_fit_steady_states": args.dynamical_fit_steady_states,
                "dynamical_n_jobs": args.dynamical_n_jobs,
            }
        )
    if args.method == "velovi":
        params.update(
            {
                "velovi_n_hidden": args.velovi_n_hidden,
                "velovi_n_latent": args.velovi_n_latent,
                "velovi_n_layers": args.velovi_n_layers,
                "velovi_dropout_rate": args.velovi_dropout_rate,
                "velovi_max_epochs": args.velovi_max_epochs,
                "velovi_lr": args.velovi_lr,
                "velovi_weight_decay": args.velovi_weight_decay,
                "velovi_batch_size": args.velovi_batch_size,
                "velovi_n_samples": args.velovi_n_samples,
                "velovi_early_stopping": args.velovi_early_stopping,
            }
        )
    return params


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if bool(args.input_path) == bool(args.demo):
        parser.error("Provide exactly one of --input <file.h5ad> or --demo.")

    if args.velocity_min_shared_counts < 0:
        parser.error("--velocity-min-shared-counts must be >= 0")
    if args.velocity_n_top_genes < 1:
        parser.error("--velocity-n-top-genes must be >= 1")
    if args.velocity_n_pcs < 2:
        parser.error("--velocity-n-pcs must be >= 2")
    if args.velocity_n_neighbors < 2:
        parser.error("--velocity-n-neighbors must be >= 2")
    if args.velocity_graph_n_neighbors is not None and args.velocity_graph_n_neighbors < 1:
        parser.error("--velocity-graph-n-neighbors must be >= 1")

    if args.method in SCVELO_METHODS:
        if args.velocity_min_r2 < 0:
            parser.error("--velocity-min-r2 must be >= 0")
        if args.velocity_min_likelihood < 0:
            parser.error("--velocity-min-likelihood must be >= 0")

    if args.method == "dynamical":
        if args.dynamical_n_top_genes is not None and args.dynamical_n_top_genes < 1:
            parser.error("--dynamical-n-top-genes must be >= 1")
        if args.dynamical_max_iter < 1:
            parser.error("--dynamical-max-iter must be >= 1")
        if args.dynamical_n_jobs is not None and args.dynamical_n_jobs < 1:
            parser.error("--dynamical-n-jobs must be >= 1")

    if args.method == "velovi":
        if args.velovi_n_hidden < 1:
            parser.error("--velovi-n-hidden must be >= 1")
        if args.velovi_n_latent < 1:
            parser.error("--velovi-n-latent must be >= 1")
        if args.velovi_n_layers < 1:
            parser.error("--velovi-n-layers must be >= 1")
        if not 0 <= args.velovi_dropout_rate < 1:
            parser.error("--velovi-dropout-rate must be in [0, 1)")
        if args.velovi_max_epochs < 1:
            parser.error("--velovi-max-epochs must be >= 1")
        if args.velovi_lr <= 0:
            parser.error("--velovi-lr must be > 0")
        if args.velovi_weight_decay < 0:
            parser.error("--velovi-weight-decay must be >= 0")
        if args.velovi_batch_size < 1:
            parser.error("--velovi-batch-size must be >= 1")
        if args.velovi_n_samples < 1:
            parser.error("--velovi-n-samples must be >= 1")


def _ensure_groupby_column(adata, *, groupby: str, parser: argparse.ArgumentParser) -> None:
    """Auto-compute Leiden labels when the default cluster key is missing."""
    if groupby in adata.obs.columns:
        return
    if groupby != "leiden":
        parser.error(
            f"--cluster-key '{groupby}' not found in adata.obs. "
            "Use an existing label column or omit it to auto-compute `leiden`."
        )

    logger.info("No '%s' column found; running minimal Leiden clustering.", groupby)
    work = adata.copy()
    sc.pp.normalize_total(work, target_sum=1e4)
    sc.pp.log1p(work)
    n_hvg = min(2000, max(2, work.n_vars - 1))
    sc.pp.highly_variable_genes(work, n_top_genes=n_hvg, flavor="seurat")
    if "highly_variable" in work.var and int(work.var["highly_variable"].sum()) >= 2:
        work = work[:, work.var["highly_variable"]].copy()

    if work.n_obs < 3 or work.n_vars < 2:
        parser.error("Dataset is too small to auto-compute `leiden`.")

    sc.pp.scale(work, max_value=10)
    n_comps = max(2, min(50, work.n_obs - 1, work.n_vars - 1))
    sc.tl.pca(work, n_comps=n_comps)
    sc.pp.neighbors(work, n_neighbors=min(15, max(2, work.n_obs - 1)), n_pcs=min(30, n_comps))
    sc.tl.leiden(work, resolution=1.0, flavor="igraph")
    adata.obs[groupby] = work.obs["leiden"].astype(str).to_numpy()


# ---------------------------------------------------------------------------
# Gallery table helpers
# ---------------------------------------------------------------------------


def _empty_cluster_summary_table() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "cluster",
            "n_cells",
            "mean_speed",
            "median_speed",
            "mean_confidence",
            "mean_transition_confidence",
            "mean_pseudotime",
            "mean_latent_time",
            "root_fraction",
            "end_fraction",
        ]
    )


def _build_cluster_summary_table(summary: dict) -> pd.DataFrame:
    cell_df = summary.get("cell_df", pd.DataFrame()).copy()
    cluster_key = summary.get("cluster_key")
    if not isinstance(cell_df, pd.DataFrame) or cell_df.empty or cluster_key not in cell_df.columns:
        return _empty_cluster_summary_table()

    work = cell_df.reset_index().copy()
    work[cluster_key] = work[cluster_key].astype(str)

    numeric_cols = [
        "velocity_speed",
        "velocity_confidence",
        "velocity_confidence_transition",
        "velocity_pseudotime",
        "latent_time",
        "root_cells",
        "end_points",
    ]
    for column in numeric_cols:
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")

    agg_spec: dict[str, tuple[str, str]] = {
        "n_cells": ("cell_id", "count"),
    }
    if "velocity_speed" in work.columns:
        agg_spec["mean_speed"] = ("velocity_speed", "mean")
        agg_spec["median_speed"] = ("velocity_speed", "median")
    if "velocity_confidence" in work.columns:
        agg_spec["mean_confidence"] = ("velocity_confidence", "mean")
    if "velocity_confidence_transition" in work.columns:
        agg_spec["mean_transition_confidence"] = ("velocity_confidence_transition", "mean")
    if "velocity_pseudotime" in work.columns:
        agg_spec["mean_pseudotime"] = ("velocity_pseudotime", "mean")
    if "latent_time" in work.columns:
        agg_spec["mean_latent_time"] = ("latent_time", "mean")
    if "root_cells" in work.columns:
        agg_spec["root_fraction"] = ("root_cells", "mean")
    if "end_points" in work.columns:
        agg_spec["end_fraction"] = ("end_points", "mean")

    cluster_summary = (
        work.groupby(cluster_key, observed=True, sort=False)
        .agg(**agg_spec)
        .reset_index()
        .rename(columns={cluster_key: "cluster"})
    )

    for column in _empty_cluster_summary_table().columns:
        if column not in cluster_summary.columns:
            cluster_summary[column] = np.nan

    cluster_summary["n_cells"] = pd.to_numeric(cluster_summary["n_cells"], errors="coerce").fillna(0).astype(int)
    for column in (
        "mean_speed",
        "median_speed",
        "mean_confidence",
        "mean_transition_confidence",
        "mean_pseudotime",
        "mean_latent_time",
        "root_fraction",
        "end_fraction",
    ):
        cluster_summary[column] = pd.to_numeric(cluster_summary[column], errors="coerce")

    return cluster_summary.loc[:, _empty_cluster_summary_table().columns].sort_values(
        by=["mean_speed", "n_cells", "cluster"],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _build_top_cells_table(summary: dict, *, n_top: int = 20) -> pd.DataFrame:
    cell_df = summary.get("cell_df", pd.DataFrame()).copy()
    cluster_key = summary.get("cluster_key")
    if not isinstance(cell_df, pd.DataFrame) or cell_df.empty:
        columns = ["rank", "cell_id"]
        if cluster_key:
            columns.append(cluster_key)
        columns.extend(
            [
                "velocity_speed",
                "velocity_confidence",
                "velocity_confidence_transition",
                "velocity_pseudotime",
                "latent_time",
                "root_cells",
                "end_points",
            ]
        )
        return pd.DataFrame(columns=columns)

    work = cell_df.reset_index().copy()
    if "cell_id" not in work.columns:
        work = work.rename(columns={work.columns[0]: "cell_id"})
    if "velocity_speed" in work.columns:
        work["velocity_speed"] = pd.to_numeric(work["velocity_speed"], errors="coerce")
        work = work.sort_values("velocity_speed", ascending=False, na_position="last", kind="mergesort")
    work = work.head(n_top).copy()
    work.insert(0, "rank", np.arange(1, len(work) + 1))

    keep_columns = [
        "rank",
        "cell_id",
        cluster_key,
        "velocity_speed",
        "velocity_confidence",
        "velocity_confidence_transition",
        "velocity_pseudotime",
        "latent_time",
        "root_cells",
        "end_points",
    ]
    keep_columns = [column for column in keep_columns if column and column in work.columns]
    return work.loc[:, keep_columns]


def _build_top_genes_table(summary: dict, *, n_top: int = 20) -> pd.DataFrame:
    gene_df = summary.get("gene_df", pd.DataFrame()).copy()
    if not isinstance(gene_df, pd.DataFrame) or gene_df.empty:
        return pd.DataFrame(
            columns=[
                "rank",
                "gene",
                "velocity_genes",
                "fit_likelihood",
                "velocity_r2",
                "velocity_qreg_ratio",
                "fit_alpha",
                "fit_beta",
                "fit_gamma",
            ]
        )

    work = gene_df.reset_index().copy()
    if "gene" not in work.columns:
        work = work.rename(columns={work.columns[0]: "gene"})

    sort_by = next(
        (
            column
            for column in ("fit_likelihood", "velocity_r2", "velocity_qreg_ratio", "velocity_gamma")
            if column in work.columns
        ),
        None,
    )
    if sort_by:
        work[sort_by] = pd.to_numeric(work[sort_by], errors="coerce")
        work = work.sort_values(sort_by, ascending=False, na_position="last", kind="mergesort")

    work = work.head(n_top).copy()
    work.insert(0, "rank", np.arange(1, len(work) + 1))

    keep_columns = [
        "rank",
        "gene",
        "velocity_genes",
        "fit_likelihood",
        "velocity_r2",
        "velocity_qreg_ratio",
        "fit_alpha",
        "fit_beta",
        "fit_gamma",
    ]
    for column in keep_columns:
        if column not in work.columns:
            work[column] = np.nan
    return work.loc[:, keep_columns]


def _build_gene_hits_table(summary: dict) -> pd.DataFrame:
    gene_df = summary.get("gene_df", pd.DataFrame()).copy()
    if not isinstance(gene_df, pd.DataFrame) or gene_df.empty:
        return _build_top_genes_table({"gene_df": pd.DataFrame()}, n_top=0)

    work = gene_df.reset_index().copy()
    if "gene" not in work.columns:
        work = work.rename(columns={work.columns[0]: "gene"})
    if "velocity_genes" in work.columns:
        mask = work["velocity_genes"].astype(bool)
        return work.loc[mask].copy()
    return work.copy()


def _build_velocity_summary_table(summary: dict) -> pd.DataFrame:
    rows = [
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "mean_speed", "value": summary.get("mean_speed")},
        {"metric": "median_speed", "value": summary.get("median_speed")},
        {"metric": "mean_confidence", "value": summary.get("mean_confidence")},
        {"metric": "n_velocity_genes", "value": summary.get("n_velocity_genes")},
        {"metric": "has_velocity_pseudotime", "value": summary.get("has_velocity_pseudotime")},
        {"metric": "has_latent_time", "value": summary.get("has_latent_time")},
        {"metric": "n_root_cells", "value": summary.get("n_root_cells")},
        {"metric": "n_end_points", "value": summary.get("n_end_points")},
    ]
    return pd.DataFrame(rows)


def _build_run_summary_table(summary: dict, context: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "engine", "value": summary.get("engine")},
        {"metric": "cluster_key", "value": summary.get("cluster_key")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "mean_speed", "value": summary.get("mean_speed")},
        {"metric": "median_speed", "value": summary.get("median_speed")},
        {"metric": "mean_confidence", "value": summary.get("mean_confidence")},
        {"metric": "n_velocity_genes", "value": summary.get("n_velocity_genes")},
        {"metric": "speed_column", "value": context.get("speed_key")},
        {"metric": "confidence_column", "value": context.get("confidence_key")},
        {"metric": "transition_confidence_column", "value": context.get("transition_confidence_key")},
        {"metric": "pseudotime_key", "value": context.get("pseudotime_key")},
        {"metric": "latent_time_key", "value": context.get("latent_time_key")},
        {"metric": "root_cells_column", "value": context.get("root_key")},
        {"metric": "end_points_column", "value": context.get("end_key")},
        {"metric": "cluster_mean_speed_column", "value": context.get("cluster_mean_speed_col")},
        {"metric": "cluster_mean_confidence_column", "value": context.get("cluster_mean_confidence_col")},
        {"metric": "cluster_mean_pseudotime_column", "value": context.get("cluster_mean_pseudotime_col")},
        {"metric": "cluster_mean_latent_time_column", "value": context.get("cluster_mean_latent_time_col")},
    ]

    for prefix, config in (
        ("preprocess", summary.get("preprocess_params", {})),
        ("graph", summary.get("graph_params", {})),
        ("model", summary.get("model_params", {})),
    ):
        if not isinstance(config, dict):
            continue
        for key, value in config.items():
            rows.append({"metric": f"{prefix}_{key}", "value": value})

    return pd.DataFrame(rows)


def _annotate_cluster_metrics_to_obs(adata, summary: dict, cluster_summary_df: pd.DataFrame) -> dict[str, str]:
    cluster_key = summary.get("cluster_key")
    if cluster_key not in adata.obs.columns or cluster_summary_df.empty:
        return {}

    lookup = cluster_summary_df.copy()
    lookup["cluster"] = lookup["cluster"].astype(str)
    lookup = lookup.set_index("cluster")
    labels = adata.obs[cluster_key].astype(str)

    mapping = {
        "cluster_mean_speed_col": ("mean_speed", "velocity_cluster_mean_speed"),
        "cluster_mean_confidence_col": ("mean_confidence", "velocity_cluster_mean_confidence"),
        "cluster_mean_pseudotime_col": ("mean_pseudotime", "velocity_cluster_mean_pseudotime"),
        "cluster_mean_latent_time_col": ("mean_latent_time", "velocity_cluster_mean_latent_time"),
        "cluster_root_fraction_col": ("root_fraction", "velocity_cluster_root_fraction"),
        "cluster_end_fraction_col": ("end_fraction", "velocity_cluster_end_fraction"),
    }

    resolved: dict[str, str] = {}
    for context_key, (source_col, obs_col) in mapping.items():
        if source_col not in lookup.columns:
            continue
        adata.obs[obs_col] = pd.to_numeric(labels.map(lookup[source_col]), errors="coerce").fillna(0.0)
        resolved[context_key] = obs_col

    return resolved


def _build_projection_table(adata, summary: dict, context: dict[str, Any], basis: str) -> pd.DataFrame | None:
    cluster_key = summary.get("cluster_key")
    basis = basis.lower()

    if basis == "spatial":
        spatial_key = context.get("spatial_key")
        if not spatial_key or spatial_key not in adata.obsm:
            return None
        coords = np.asarray(adata.obsm[spatial_key])
        if coords.ndim != 2 or coords.shape[1] < 2:
            return None
        df = pd.DataFrame(
            {
                "observation": adata.obs_names.astype(str),
                "x": coords[:, 0],
                "y": coords[:, 1],
            }
        )
        velocity_key = "velocity_spatial"
    elif basis == "umap":
        if "X_umap" not in adata.obsm:
            return None
        coords = np.asarray(adata.obsm["X_umap"])
        if coords.ndim != 2 or coords.shape[1] < 2:
            return None
        df = pd.DataFrame(
            {
                "observation": adata.obs_names.astype(str),
                "umap_1": coords[:, 0],
                "umap_2": coords[:, 1],
            }
        )
        velocity_key = "velocity_umap"
    else:
        raise ValueError(f"Unsupported basis '{basis}'")

    if velocity_key in adata.obsm:
        velocity = np.asarray(adata.obsm[velocity_key])
        if velocity.ndim == 2 and velocity.shape[1] >= 2:
            df["velocity_1"] = velocity[:, 0]
            df["velocity_2"] = velocity[:, 1]

    export_columns = [
        cluster_key,
        context.get("speed_key"),
        context.get("confidence_key"),
        context.get("transition_confidence_key"),
        context.get("pseudotime_key"),
        context.get("latent_time_key"),
        context.get("root_key"),
        context.get("end_key"),
        context.get("cluster_mean_speed_col"),
        context.get("cluster_mean_confidence_col"),
        context.get("cluster_mean_pseudotime_col"),
        context.get("cluster_mean_latent_time_col"),
        context.get("cluster_root_fraction_col"),
        context.get("cluster_end_fraction_col"),
    ]

    for column in export_columns:
        if not column or column not in adata.obs.columns:
            continue
        df[column] = _coerce_obs_value(adata.obs[column])

    return df


# ---------------------------------------------------------------------------
# Gallery helpers
# ---------------------------------------------------------------------------


def _prepare_velocity_plot_state(adata, cluster_key: str | None) -> str | None:
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()

    if cluster_key and cluster_key in adata.obs.columns and not isinstance(adata.obs[cluster_key].dtype, pd.CategoricalDtype):
        adata.obs[cluster_key] = pd.Categorical(adata.obs[cluster_key].astype(str))

    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
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
        logger.warning("Could not compute UMAP for velocity gallery: %s", exc)


def _prepare_velocity_gallery_context(adata, summary: dict) -> dict[str, Any]:
    cluster_key = summary.get("cluster_key")
    spatial_key = _prepare_velocity_plot_state(adata, cluster_key)
    _ensure_umap_for_gallery(adata)

    cluster_summary_df = _build_cluster_summary_table(summary)
    context: dict[str, Any] = {
        "cluster_key": cluster_key,
        "spatial_key": spatial_key,
        "speed_key": "velocity_speed" if "velocity_speed" in adata.obs.columns else None,
        "confidence_key": "velocity_confidence" if "velocity_confidence" in adata.obs.columns else None,
        "transition_confidence_key": (
            "velocity_confidence_transition" if "velocity_confidence_transition" in adata.obs.columns else None
        ),
        "pseudotime_key": "velocity_pseudotime" if "velocity_pseudotime" in adata.obs.columns else None,
        "latent_time_key": "latent_time" if "latent_time" in adata.obs.columns else None,
        "root_key": "root_cells" if "root_cells" in adata.obs.columns else None,
        "end_key": "end_points" if "end_points" in adata.obs.columns else None,
        "cell_df": summary.get("cell_df", pd.DataFrame()).copy(),
        "gene_df": summary.get("gene_df", pd.DataFrame()).copy(),
        "gene_hits_df": _build_gene_hits_table(summary),
        "cluster_summary_df": cluster_summary_df,
        "top_cells_df": _build_top_cells_table(summary, n_top=20),
        "top_genes_df": _build_top_genes_table(summary, n_top=20),
    }
    context.update(_annotate_cluster_metrics_to_obs(adata, summary, cluster_summary_df))
    return context


def _build_velocity_visualization_recipe(
    adata,
    summary: dict[str, Any],
    context: dict[str, Any],
) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    cluster_key = summary.get("cluster_key")
    spatial_key = context.get("spatial_key")
    speed_key = context.get("speed_key")
    confidence_key = context.get("confidence_key")
    transition_confidence_key = context.get("transition_confidence_key")
    pseudotime_key = context.get("pseudotime_key")
    latent_time_key = context.get("latent_time_key")

    if "velocity_graph" in adata.uns and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="velocity_stream_umap",
                role="overview",
                renderer="velocity_plot",
                filename="velocity_stream_umap.png",
                title="Velocity Stream on UMAP",
                description="Canonical RNA velocity stream rendered on the standard embedding.",
                params={"subtype": "stream", "basis": "umap", "cluster_key": cluster_key, "figure_size": (10, 8)},
                required_obsm=["X_umap"],
                required_uns=["velocity_graph"],
            )
        )

    if "velocity_graph" in adata.uns and spatial_key:
        plots.append(
            PlotSpec(
                plot_id="velocity_stream_spatial",
                role="overview",
                renderer="velocity_plot",
                filename="velocity_stream_spatial.png",
                title="Velocity Stream on Tissue",
                description="Velocity stream projected onto spatial coordinates for tissue-level interpretation.",
                params={"subtype": "stream", "basis": "spatial", "cluster_key": cluster_key, "figure_size": (10, 8)},
                required_obsm=[spatial_key],
                required_uns=["velocity_graph"],
            )
        )

    if speed_key and spatial_key:
        plots.append(
            PlotSpec(
                plot_id="velocity_speed_spatial",
                role="overview",
                renderer="feature_map",
                filename="velocity_speed_spatial.png",
                title="Velocity Speed on Tissue",
                description="Per-observation velocity speed projected back onto tissue coordinates.",
                params={"feature": speed_key, "basis": "spatial", "colormap": "magma"},
                required_obs=[speed_key],
                required_obsm=[spatial_key],
            )
        )

    if {"velocity", "Ms", "Mu"}.issubset(adata.layers.keys()):
        plots.append(
            PlotSpec(
                plot_id="velocity_phase_portraits",
                role="diagnostic",
                renderer="velocity_plot",
                filename="velocity_phase.png",
                title="Velocity Phase Portraits",
                description="Phase portraits for representative velocity genes using the shared scVelo renderer.",
                params={"subtype": "phase", "cluster_key": cluster_key},
            )
        )

    if "velocity_graph" in adata.uns and (pseudotime_key or latent_time_key):
        plots.append(
            PlotSpec(
                plot_id="velocity_heatmap",
                role="diagnostic",
                renderer="velocity_plot",
                filename="velocity_heatmap.png",
                title="Velocity Heatmap",
                description="Velocity-ordered gene heatmap generated by the shared velocity heatmap primitive.",
                params={"subtype": "heatmap", "cluster_key": cluster_key},
                required_uns=["velocity_graph"],
            )
        )

    if cluster_key in adata.obs.columns and {"spliced", "unspliced"}.issubset(adata.layers.keys()):
        plots.append(
            PlotSpec(
                plot_id="velocity_layer_proportions",
                role="diagnostic",
                renderer="velocity_plot",
                filename="velocity_layer_proportions.png",
                title="Spliced / Unspliced Proportions",
                description="Cluster-level spliced and unspliced count proportions for quality inspection.",
                params={"subtype": "proportions", "cluster_key": cluster_key},
                required_obs=[cluster_key],
            )
        )

    if cluster_key in adata.obs.columns:
        plots.append(
            PlotSpec(
                plot_id="velocity_paga",
                role="diagnostic",
                renderer="velocity_plot",
                filename="velocity_paga.png",
                title=f"PAGA Connectivity ({cluster_key})",
                description="Cluster connectivity view to contextualize velocity transitions.",
                params={"subtype": "paga", "cluster_key": cluster_key},
                required_obs=[cluster_key],
            )
        )

    if not context.get("cluster_summary_df", pd.DataFrame()).empty:
        plots.append(
            PlotSpec(
                plot_id="velocity_cluster_summary",
                role="diagnostic",
                renderer="cluster_summary_barplot",
                filename="velocity_cluster_summary.png",
                title="Cluster Velocity Summary",
                description="Mean cluster-level velocity speed, confidence, and cell count summary.",
                params={"max_clusters": 12, "figure_size": (9, 6)},
            )
        )

    if speed_key and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="velocity_speed_umap",
                role="supporting",
                renderer="feature_map",
                filename="velocity_speed_umap.png",
                title="Velocity Speed on UMAP",
                description="Velocity speed mapped onto the standard embedding for local comparison.",
                params={"feature": speed_key, "basis": "umap", "colormap": "magma"},
                required_obs=[speed_key],
                required_obsm=["X_umap"],
            )
        )

    if pseudotime_key and spatial_key:
        plots.append(
            PlotSpec(
                plot_id="velocity_pseudotime_spatial",
                role="supporting",
                renderer="feature_map",
                filename="velocity_pseudotime_spatial.png",
                title="Velocity Pseudotime on Tissue",
                description="Velocity pseudotime projected back onto spatial coordinates.",
                params={"feature": pseudotime_key, "basis": "spatial", "colormap": "viridis"},
                required_obs=[pseudotime_key],
                required_obsm=[spatial_key],
            )
        )

    if latent_time_key and spatial_key:
        plots.append(
            PlotSpec(
                plot_id="velocity_latent_time_spatial",
                role="supporting",
                renderer="feature_map",
                filename="velocity_latent_time_spatial.png",
                title="Latent Time on Tissue",
                description="Model-derived latent time projected onto the tissue layout when available.",
                params={"feature": latent_time_key, "basis": "spatial", "colormap": "viridis"},
                required_obs=[latent_time_key],
                required_obsm=[spatial_key],
            )
        )

    if not context.get("top_genes_df", pd.DataFrame()).empty:
        plots.append(
            PlotSpec(
                plot_id="velocity_top_genes_barplot",
                role="supporting",
                renderer="gene_summary_barplot",
                filename="velocity_top_genes_barplot.png",
                title="Top Velocity Genes",
                description="Top-ranked velocity-associated genes exported as a compact gene summary panel.",
                params={"max_genes": 15, "figure_size": (9, 6)},
            )
        )

    if confidence_key and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="velocity_confidence_umap",
                role="uncertainty",
                renderer="feature_map",
                filename="velocity_confidence_umap.png",
                title="Velocity Confidence on UMAP",
                description="Per-cell velocity confidence on the embedding for uncertainty review.",
                params={"feature": confidence_key, "basis": "umap", "colormap": "cividis"},
                required_obs=[confidence_key],
                required_obsm=["X_umap"],
            )
        )

    if confidence_key and spatial_key:
        plots.append(
            PlotSpec(
                plot_id="velocity_confidence_spatial",
                role="uncertainty",
                renderer="feature_map",
                filename="velocity_confidence_spatial.png",
                title="Velocity Confidence on Tissue",
                description="Velocity confidence projected back onto spatial coordinates.",
                params={"feature": confidence_key, "basis": "spatial", "colormap": "cividis"},
                required_obs=[confidence_key],
                required_obsm=[spatial_key],
            )
        )

    if transition_confidence_key and "X_umap" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="velocity_transition_confidence_umap",
                role="uncertainty",
                renderer="feature_map",
                filename="velocity_transition_confidence_umap.png",
                title="Transition Confidence on UMAP",
                description="Transition-confidence view for checking local arrow stability.",
                params={"feature": transition_confidence_key, "basis": "umap", "colormap": "plasma"},
                required_obs=[transition_confidence_key],
                required_obsm=["X_umap"],
            )
        )

    if speed_key:
        plots.append(
            PlotSpec(
                plot_id="velocity_speed_distribution",
                role="uncertainty",
                renderer="metric_histogram",
                filename="velocity_speed_distribution.png",
                title="Velocity Speed Distribution",
                description="Distribution of per-cell velocity speed values.",
                params={"feature": speed_key, "bins": 30, "color": "#d95f0e", "figure_size": (8, 5)},
                required_obs=[speed_key],
            )
        )

    if confidence_key:
        plots.append(
            PlotSpec(
                plot_id="velocity_confidence_distribution",
                role="uncertainty",
                renderer="metric_histogram",
                filename="velocity_confidence_distribution.png",
                title="Velocity Confidence Distribution",
                description="Distribution of velocity confidence values for uncertainty assessment.",
                params={"feature": confidence_key, "bins": 30, "color": "#3182bd", "figure_size": (8, 5)},
                required_obs=[confidence_key],
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-velocity-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Velocity Standard Gallery",
        description=(
            "OmicsClaw standard velocity gallery combining shared velocity primitives "
            "with summary views for cluster-, gene-, and uncertainty-level inspection."
        ),
        plots=plots,
    )


def _render_velocity_plot(adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    params = dict(spec.params)
    subtype = params.pop("subtype", None)
    cluster_key = params.pop("cluster_key", context.get("cluster_key"))
    return plot_velocity(
        adata,
        VizParams(**params),
        subtype=subtype,
        cluster_key=cluster_key,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict[str, Any]) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_cluster_summary_barplot(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    summary_df = context.get("cluster_summary_df", pd.DataFrame()).copy()
    if summary_df.empty:
        return None

    max_clusters = int(spec.params.get("max_clusters", 12))
    plot_df = summary_df.head(max_clusters).copy()
    plot_df = plot_df.iloc[::-1]
    y_positions = np.arange(len(plot_df))

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (9, 6)), dpi=int(spec.params.get("dpi", 200)))
    colors = pd.to_numeric(plot_df.get("mean_confidence"), errors="coerce")
    if colors.notna().any():
        color_values = colors.fillna(colors.min())
        cmap = plt.cm.viridis
        norm = plt.Normalize(vmin=float(color_values.min()), vmax=float(color_values.max()) or 1.0)
        bar_colors = cmap(norm(color_values.to_numpy()))
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    else:
        bar_colors = "#2b8cbe"
        sm = None

    ax.barh(y_positions, plot_df["mean_speed"].fillna(0.0), color=bar_colors, alpha=0.92)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(plot_df["cluster"].astype(str).tolist())
    for idx, (_, row) in enumerate(plot_df.iterrows()):
        speed_value = pd.to_numeric(pd.Series([row.get("mean_speed")]), errors="coerce").iloc[0]
        if pd.isna(speed_value):
            speed_value = 0.0
        ax.text(
            float(speed_value),
            y_positions[idx],
            f"  n={int(row.get('n_cells', 0))}",
            va="center",
            ha="left",
            fontsize=9,
        )
    ax.set_xlabel("Mean velocity speed")
    ax.set_ylabel("Cluster")
    ax.set_title(spec.title or "Cluster Velocity Summary")
    ax.grid(axis="x", alpha=0.2)
    if sm is not None:
        cbar = fig.colorbar(sm, ax=ax)
        cbar.set_label("Mean confidence")
    plt.tight_layout()
    return fig


def _render_gene_summary_barplot(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    top_genes_df = context.get("top_genes_df", pd.DataFrame()).copy()
    if top_genes_df.empty:
        return None

    max_genes = int(spec.params.get("max_genes", 15))
    plot_df = top_genes_df.head(max_genes).copy()
    ranking_column = next(
        (
            column
            for column in ("fit_likelihood", "velocity_r2", "velocity_qreg_ratio")
            if column in plot_df.columns and pd.to_numeric(plot_df[column], errors="coerce").notna().any()
        ),
        None,
    )
    if ranking_column is None:
        return None

    plot_df[ranking_column] = pd.to_numeric(plot_df[ranking_column], errors="coerce")
    plot_df = plot_df.sort_values(ranking_column, ascending=True, na_position="last", kind="mergesort")

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (9, 6)), dpi=int(spec.params.get("dpi", 200)))
    colors = np.where(plot_df.get("velocity_genes", False).astype(bool), "#31a354", "#9ecae1")
    ax.barh(plot_df["gene"].astype(str), plot_df[ranking_column].fillna(0.0), color=colors, alpha=0.92)
    ax.set_xlabel(ranking_column.replace("_", " ").title())
    ax.set_ylabel("Gene")
    ax.set_title(spec.title or "Top Velocity Genes")
    ax.grid(axis="x", alpha=0.2)
    plt.tight_layout()
    return fig


def _render_metric_histogram(adata, spec: PlotSpec, _context: dict[str, Any]) -> object:
    feature = spec.params.get("feature")
    if not feature or feature not in adata.obs.columns:
        return None

    values = pd.to_numeric(adata.obs[feature], errors="coerce").dropna()
    if values.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=int(spec.params.get("dpi", 200)))
    ax.hist(values, bins=int(spec.params.get("bins", 30)), color=spec.params.get("color", "#3182bd"), alpha=0.9)
    ax.set_xlabel(feature.replace("_", " ").title())
    ax.set_ylabel("Cell count")
    ax.set_title(spec.title or feature.replace("_", " ").title())
    ax.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    return fig


VELOCITY_GALLERY_RENDERERS = {
    "velocity_plot": _render_velocity_plot,
    "feature_map": _render_feature_map,
    "cluster_summary_barplot": _render_cluster_summary_barplot,
    "gene_summary_barplot": _render_gene_summary_barplot,
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

    _build_velocity_summary_table(summary).to_csv(figure_data_dir / "velocity_summary.csv", index=False)
    context.get("cell_df", pd.DataFrame()).reset_index().to_csv(
        figure_data_dir / "velocity_cell_metrics.csv",
        index=False,
    )
    context.get("gene_df", pd.DataFrame()).reset_index().to_csv(
        figure_data_dir / "velocity_gene_summary.csv",
        index=False,
    )
    context.get("gene_hits_df", pd.DataFrame()).to_csv(figure_data_dir / "velocity_gene_hits.csv", index=False)
    context.get("cluster_summary_df", pd.DataFrame()).to_csv(
        figure_data_dir / "velocity_cluster_summary.csv",
        index=False,
    )
    context.get("top_cells_df", pd.DataFrame()).to_csv(figure_data_dir / "velocity_top_cells.csv", index=False)
    context.get("top_genes_df", pd.DataFrame()).to_csv(figure_data_dir / "velocity_top_genes.csv", index=False)
    _build_run_summary_table(summary, context).to_csv(figure_data_dir / "velocity_run_summary.csv", index=False)

    spatial_file = None
    spatial_df = _build_projection_table(adata, summary, context, "spatial")
    if spatial_df is not None:
        spatial_file = "velocity_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_projection_table(adata, summary, context, "umap")
    if umap_df is not None:
        umap_file = "velocity_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    manifest = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "engine": summary.get("engine"),
        "cluster_key": summary.get("cluster_key"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "available_files": {
            "velocity_summary": "velocity_summary.csv",
            "velocity_cell_metrics": "velocity_cell_metrics.csv",
            "velocity_gene_summary": "velocity_gene_summary.csv",
            "velocity_gene_hits": "velocity_gene_hits.csv",
            "velocity_cluster_summary": "velocity_cluster_summary.csv",
            "velocity_top_cells": "velocity_top_cells.csv",
            "velocity_top_genes": "velocity_top_genes.csv",
            "velocity_run_summary": "velocity_run_summary.csv",
            "velocity_spatial_points": spatial_file,
            "velocity_umap_points": umap_file,
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
    _write_figure_data_manifest(output_dir, manifest)


def generate_figures(
    adata,
    output_dir: Path,
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> list[str]:
    """Render the standard velocity gallery and export figure-ready data."""
    context = gallery_context or _prepare_velocity_gallery_context(adata, summary)
    recipe = _build_velocity_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        VELOCITY_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Reports, table exports, and reproducibility
# ---------------------------------------------------------------------------


def export_tables(
    output_dir: Path,
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> list[str]:
    """Write standardized velocity tables."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    context = gallery_context
    if context is None:
        context = {
            "cluster_summary_df": _build_cluster_summary_table(summary),
            "top_cells_df": _build_top_cells_table(summary, n_top=20),
            "top_genes_df": _build_top_genes_table(summary, n_top=20),
            "gene_hits_df": _build_gene_hits_table(summary),
            "cell_df": summary.get("cell_df", pd.DataFrame()).copy(),
            "gene_df": summary.get("gene_df", pd.DataFrame()).copy(),
        }

    table_paths: list[str] = []

    cell_path = tables_dir / "cell_velocity_metrics.csv"
    context.get("cell_df", pd.DataFrame()).to_csv(cell_path)
    table_paths.append(str(cell_path))

    gene_path = tables_dir / "gene_velocity_summary.csv"
    context.get("gene_df", pd.DataFrame()).to_csv(gene_path)
    table_paths.append(str(gene_path))

    hits_path = tables_dir / "velocity_gene_hits.csv"
    context.get("gene_hits_df", pd.DataFrame()).to_csv(hits_path, index=False)
    table_paths.append(str(hits_path))

    cluster_path = tables_dir / "velocity_cluster_summary.csv"
    context.get("cluster_summary_df", pd.DataFrame()).to_csv(cluster_path, index=False)
    table_paths.append(str(cluster_path))

    top_cells_path = tables_dir / "top_velocity_cells.csv"
    context.get("top_cells_df", pd.DataFrame()).to_csv(top_cells_path, index=False)
    table_paths.append(str(top_cells_path))

    top_genes_path = tables_dir / "top_velocity_genes.csv"
    context.get("top_genes_df", pd.DataFrame()).to_csv(top_genes_path, index=False)
    table_paths.append(str(top_genes_path))

    return table_paths


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-velocity"
        / "r_visualization"
        / "velocity_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def write_report(
    output_dir: Path,
    summary: dict[str, Any],
    input_file: str | None,
    params: dict[str, Any],
    figures: list[str],
    tables: list[str],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> None:
    """Write the Markdown report and the JSON result summary."""
    header = generate_report_header(
        title="Spatial RNA Velocity Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Engine": summary["engine"],
            "Cluster key": summary.get("cluster_key", "auto"),
        },
    )

    context = gallery_context or {}
    cluster_summary_df = context.get("cluster_summary_df", _build_cluster_summary_table(summary))
    top_cells_df = context.get("top_cells_df", _build_top_cells_table(summary, n_top=10))
    top_genes_df = context.get("top_genes_df", _build_top_genes_table(summary, n_top=10))

    report_lines = [
        "## Summary",
        "",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Engine**: {summary['engine']}",
        f"- **Cluster key**: {summary.get('cluster_key', 'NA')}",
        f"- **Mean velocity speed**: {summary.get('mean_speed', 0.0):.4f}",
        f"- **Median velocity speed**: {summary.get('median_speed', 0.0):.4f}",
        f"- **Velocity genes**: {_format_value(summary.get('n_velocity_genes'))}",
        f"- **Mean confidence**: {_format_value(summary.get('mean_confidence'))}",
        f"- **Velocity pseudotime key**: {context.get('pseudotime_key', 'NA')}",
        f"- **Latent time key**: {context.get('latent_time_key', 'NA')}",
        "",
        "## Method Notes",
        "",
        *_interpretation_notes(summary),
        "",
    ]

    if not cluster_summary_df.empty:
        cluster_columns = [
            column
            for column in (
                "cluster",
                "n_cells",
                "mean_speed",
                "mean_confidence",
                "mean_pseudotime",
                "mean_latent_time",
            )
            if column in cluster_summary_df.columns
        ]
        cluster_headers = {
            "cluster": "Cluster",
            "n_cells": "Cells",
            "mean_speed": "Mean speed",
            "mean_confidence": "Mean confidence",
            "mean_pseudotime": "Mean pseudotime",
            "mean_latent_time": "Mean latent time",
        }
        report_lines.extend(
            [
                "## Cluster Velocity Summary",
                "",
                *_markdown_table(
                    cluster_summary_df,
                    columns=cluster_columns,
                    headers=[cluster_headers[column] for column in cluster_columns],
                    limit=12,
                ),
                "",
            ]
        )

    if not top_cells_df.empty:
        cell_columns = [
            column
            for column in (
                "cell_id",
                summary["cluster_key"],
                "velocity_speed",
                "velocity_confidence",
                "velocity_pseudotime",
                "latent_time",
            )
            if column in top_cells_df.columns
        ]
        report_lines.extend(
            [
                "## Top Cells By Velocity Speed",
                "",
                *_markdown_table(top_cells_df, columns=cell_columns, limit=10),
                "",
            ]
        )

    if not top_genes_df.empty:
        gene_columns = [
            column
            for column in (
                "gene",
                "velocity_genes",
                "fit_likelihood",
                "velocity_r2",
                "velocity_qreg_ratio",
                "fit_alpha",
                "fit_beta",
                "fit_gamma",
            )
            if column in top_genes_df.columns
        ]
        report_lines.extend(
            [
                "## Top Velocity Genes",
                "",
                *_markdown_table(top_genes_df, columns=gene_columns, limit=10),
                "",
            ]
        )

    report_lines.extend(["## Parameters", ""])
    for key, value in params.items():
        report_lines.append(f"- `{key}`: {_format_value(value)}")

    if summary.get("preprocess_params"):
        report_lines.extend(["", "### Effective Preprocessing Parameters", ""])
        for key, value in summary["preprocess_params"].items():
            report_lines.append(f"- `{key}`: {_format_value(value)}")

    if summary.get("graph_params"):
        report_lines.extend(["", "### Effective Graph Parameters", ""])
        for key, value in summary["graph_params"].items():
            report_lines.append(f"- `{key}`: {_format_value(value)}")

    if summary.get("model_params"):
        report_lines.extend(["", "### Effective Model Parameters", ""])
        for key, value in summary["model_params"].items():
            report_lines.append(f"- `{key}`: {_format_value(value)}")

    report_lines.extend(
        [
            "",
            "## Visualization Outputs",
            "",
            "- `figures/manifest.json`: Standard Python gallery manifest",
            "- `figure_data/`: Figure-ready CSV exports for downstream customization",
            "- `reproducibility/r_visualization.sh`: Optional R visualization entrypoint",
            f"- **Figures generated**: {len(figures)}",
            f"- **Tables generated**: {len(tables)}",
            "",
        ]
    )

    if summary.get("warnings"):
        report_lines.extend(["## Warnings", ""])
        for item in summary["warnings"]:
            report_lines.append(f"- {item}")
        report_lines.append("")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(report_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    summary_for_json = _json_safe_summary(summary)
    result_data: dict[str, Any] = {
        "params": params,
        "effective_params": summary.get("effective_params", params),
        "figures": figures,
        "tables": tables,
    }
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-velocity-gallery",
            "speed_column": gallery_context.get("speed_key"),
            "confidence_column": gallery_context.get("confidence_key"),
            "transition_confidence_column": gallery_context.get("transition_confidence_key"),
            "pseudotime_key": gallery_context.get("pseudotime_key"),
            "latent_time_key": gallery_context.get("latent_time_key"),
            "cluster_mean_speed_column": gallery_context.get("cluster_mean_speed_col"),
            "cluster_mean_confidence_column": gallery_context.get("cluster_mean_confidence_col"),
            "cluster_mean_pseudotime_column": gallery_context.get("cluster_mean_pseudotime_col"),
            "cluster_mean_latent_time_column": gallery_context.get("cluster_mean_latent_time_col"),
            "cluster_root_fraction_column": gallery_context.get("cluster_root_fraction_col"),
            "cluster_end_fraction_column": gallery_context.get("cluster_end_fraction_col"),
        }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary_for_json,
        data=result_data,
        input_checksum=checksum,
    )


def write_reproducibility(
    output_dir: Path,
    *,
    input_file: str | None,
    demo: bool,
    params: dict,
) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    command = ["python", SCRIPT_REL_PATH]
    if demo:
        command.append("--demo")
    else:
        command.extend(["--input", "<input.h5ad>"])
    command.extend(["--output", "<output_dir>"])
    command.extend(_params_to_cli_tokens(params))
    command_text = " ".join(shlex.quote(token) for token in command)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command_text}\n")
    _write_r_visualization_helper(output_dir)

    try:
        from importlib.metadata import PackageNotFoundError, version as _version
    except ImportError:  # pragma: no cover
        from importlib_metadata import PackageNotFoundError, version as _version  # type: ignore

    env_lines: list[str] = []
    for pkg in ("scanpy", "anndata", "numpy", "pandas", "matplotlib", "scipy", "scvelo", "scvi-tools", "torch", "velovi"):
        try:
            env_lines.append(f"{pkg}=={_version(pkg)}")
        except PackageNotFoundError:
            continue
    requirements_text = "\n".join(dict.fromkeys(env_lines)) + "\n"
    (repro_dir / "requirements.txt").write_text(requirements_text)
    (repro_dir / "environment.txt").write_text(requirements_text)


# ---------------------------------------------------------------------------
# Demo data and CLI
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate preprocessed demo data and attach synthetic velocity layers."""
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_velocity_demo_") as tmp_dir:
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
    add_demo_velocity_layers(adata)
    return adata, None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Spatial Velocity — method-aware RNA velocity analysis",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", dest="input_path", help="Input .h5ad file with spliced/unspliced layers")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run on demo data with synthetic velocity layers")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="stochastic", help="Velocity backend")
    parser.add_argument("--cluster-key", default="leiden", help="obs column used for PAGA and grouped exports")

    parser.add_argument("--velocity-min-shared-counts", type=int, default=30, help="Shared preprocessing gene filter before moment construction")
    parser.add_argument("--velocity-n-top-genes", type=int, default=2000, help="Wrapper-level HVG cap before PCA / moments")
    parser.add_argument("--velocity-n-pcs", type=int, default=30, help="Number of PCs used for neighbors and moments")
    parser.add_argument("--velocity-n-neighbors", type=int, default=30, help="Neighbor count used for moments")
    parser.add_argument("--velocity-use-highly-variable", dest="velocity_use_highly_variable", action="store_true", help="Use HVGs during PCA / moment construction")
    parser.add_argument("--no-velocity-use-highly-variable", dest="velocity_use_highly_variable", action="store_false", help="Use the full gene space during PCA / moment construction")
    parser.set_defaults(velocity_use_highly_variable=True)
    parser.add_argument("--velocity-graph-n-neighbors", type=int, default=None, help="Optional override for scVelo velocity_graph n_neighbors")
    parser.add_argument("--velocity-graph-sqrt-transform", dest="velocity_graph_sqrt_transform", action="store_true", help="Enable scVelo velocity_graph sqrt_transform")
    parser.add_argument("--no-velocity-graph-sqrt-transform", dest="velocity_graph_sqrt_transform", action="store_false", help="Disable scVelo velocity_graph sqrt_transform")
    parser.set_defaults(velocity_graph_sqrt_transform=None)
    parser.add_argument("--velocity-graph-approx", dest="velocity_graph_approx", action="store_true", help="Enable scVelo velocity_graph approx mode")
    parser.add_argument("--no-velocity-graph-approx", dest="velocity_graph_approx", action="store_false", help="Disable scVelo velocity_graph approx mode")
    parser.set_defaults(velocity_graph_approx=None)

    parser.add_argument("--velocity-fit-offset", dest="velocity_fit_offset", action="store_true", help="Pass fit_offset=True to scv.tl.velocity")
    parser.add_argument("--no-velocity-fit-offset", dest="velocity_fit_offset", action="store_false", help="Pass fit_offset=False to scv.tl.velocity")
    parser.set_defaults(velocity_fit_offset=False)
    parser.add_argument("--velocity-fit-offset2", dest="velocity_fit_offset2", action="store_true", help="Pass fit_offset2=True to scv.tl.velocity")
    parser.add_argument("--no-velocity-fit-offset2", dest="velocity_fit_offset2", action="store_false", help="Pass fit_offset2=False to scv.tl.velocity")
    parser.set_defaults(velocity_fit_offset2=False)
    parser.add_argument("--velocity-min-r2", type=float, default=0.01, help="Minimum R^2 for scVelo velocity gene filtering")
    parser.add_argument("--velocity-min-likelihood", type=float, default=0.001, help="Minimum likelihood for scVelo velocity gene filtering")

    parser.add_argument("--dynamical-n-top-genes", type=int, default=None, help="recover_dynamics n_top_genes")
    parser.add_argument("--dynamical-max-iter", type=int, default=10, help="recover_dynamics max_iter")
    parser.add_argument("--dynamical-fit-time", dest="dynamical_fit_time", action="store_true", help="Fit latent time during recover_dynamics")
    parser.add_argument("--no-dynamical-fit-time", dest="dynamical_fit_time", action="store_false", help="Disable recover_dynamics fit_time")
    parser.set_defaults(dynamical_fit_time=True)
    parser.add_argument("--dynamical-fit-scaling", dest="dynamical_fit_scaling", action="store_true", help="Fit scaling during recover_dynamics")
    parser.add_argument("--no-dynamical-fit-scaling", dest="dynamical_fit_scaling", action="store_false", help="Disable recover_dynamics fit_scaling")
    parser.set_defaults(dynamical_fit_scaling=True)
    parser.add_argument("--dynamical-fit-steady-states", dest="dynamical_fit_steady_states", action="store_true", help="Fit steady states during recover_dynamics")
    parser.add_argument("--no-dynamical-fit-steady-states", dest="dynamical_fit_steady_states", action="store_false", help="Disable recover_dynamics fit_steady_states")
    parser.set_defaults(dynamical_fit_steady_states=True)
    parser.add_argument("--dynamical-n-jobs", type=int, default=None, help="recover_dynamics parallel jobs")

    parser.add_argument("--velovi-n-hidden", type=int, default=256, help="VELOVI hidden-layer width")
    parser.add_argument("--velovi-n-latent", type=int, default=10, help="VELOVI latent dimensionality")
    parser.add_argument("--velovi-n-layers", type=int, default=1, help="VELOVI hidden-layer count")
    parser.add_argument("--velovi-dropout-rate", type=float, default=0.1, help="VELOVI dropout rate")
    parser.add_argument("--velovi-max-epochs", type=int, default=500, help="VELOVI training epochs")
    parser.add_argument("--velovi-lr", type=float, default=0.01, help="VELOVI optimizer learning rate")
    parser.add_argument("--velovi-weight-decay", type=float, default=0.01, help="VELOVI optimizer weight decay")
    parser.add_argument("--velovi-batch-size", type=int, default=256, help="VELOVI mini-batch size")
    parser.add_argument("--velovi-n-samples", type=int, default=25, help="Posterior samples for VELOVI velocity / latent time")
    parser.add_argument("--velovi-early-stopping", dest="velovi_early_stopping", action="store_true", help="Enable VELOVI early stopping")
    parser.add_argument("--no-velovi-early-stopping", dest="velovi_early_stopping", action="store_false", help="Disable VELOVI early stopping")
    parser.set_defaults(velovi_early_stopping=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _validate_args(parser, args)

    require("scvelo", feature="RNA velocity")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    else:
        input_path = Path(args.input_path)
        if not input_path.exists():
            parser.error(f"Input file not found: {input_path}")
        adata = sc.read_h5ad(input_path)
        input_file = str(input_path)

    _ensure_groupby_column(adata, groupby=args.cluster_key, parser=parser)
    params = _collect_run_configuration(args)
    logger.info("Running %s with parameters: %s", args.method, params)

    summary = run_velocity(adata, **params)
    summary["effective_params"] = params.copy()

    gallery_context = _prepare_velocity_gallery_context(adata, summary)
    figures = generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    tables = export_tables(output_dir, summary, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, figures, tables, gallery_context=gallery_context)
    write_reproducibility(output_dir, input_file=input_file, demo=args.demo, params=params)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved %s", h5ad_path)

    print(
        f"Velocity complete ({summary['method']}): "
        f"mean speed={summary.get('mean_speed', 0.0):.4f}, "
        f"median speed={summary.get('median_speed', 0.0):.4f}"
    )


if __name__ == "__main__":
    main()
