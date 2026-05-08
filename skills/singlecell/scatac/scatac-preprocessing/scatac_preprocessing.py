#!/usr/bin/env python3
"""Single-cell ATAC preprocessing with a TF-IDF + LSI workflow."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_NUMBA_CACHE_DIR = Path(tempfile.gettempdir()) / "omicsclaw-numba-cache"
_MPLCONFIGDIR = Path(tempfile.gettempdir()) / "omicsclaw-mplconfig"
_NUMBA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NUMBA_CACHE_DIR", str(_NUMBA_CACHE_DIR))
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIGDIR))

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
import scanpy as sc
import scipy.sparse as sp
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_result_json,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import qc as sc_qc_utils
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib.dimred import plot_umap_clusters
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "scatac-preprocessing"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scatac/scatac-preprocessing/scatac_preprocessing.py"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "tfidf_lsi": MethodConfig(
        name="tfidf_lsi",
        description="Signac-style TF-IDF + LSI workflow in Python",
        dependencies=("scanpy", "sklearn"),
    ),
}

DEFAULT_METHOD = "tfidf_lsi"
PUBLIC_PARAM_KEYS = (
    "method",
    "min_peaks",
    "min_cells",
    "n_top_peaks",
    "tfidf_scale_factor",
    "n_lsi",
    "n_neighbors",
    "leiden_resolution",
)
METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "tfidf_lsi": {
        "method": "tfidf_lsi",
        "min_peaks": 200,
        "min_cells": 5,
        "n_top_peaks": 10000,
        "tfidf_scale_factor": 10000.0,
        "n_lsi": 30,
        "n_neighbors": 15,
        "leiden_resolution": 0.8,
        "peak_selection_metric": "total_counts",
        "lsi_skip_first_component": True,
        "scale_lsi_embeddings": True,
    },
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="scATAC preprocessing")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default=DEFAULT_METHOD)
    parser.add_argument("--min-peaks", type=int, default=None)
    parser.add_argument("--min-cells", type=int, default=None)
    parser.add_argument("--n-top-peaks", type=int, default=None)
    parser.add_argument("--tfidf-scale-factor", type=float, default=None)
    parser.add_argument("--n-lsi", type=int, default=None)
    parser.add_argument("--n-neighbors", type=int, default=None)
    parser.add_argument("--leiden-resolution", type=float, default=None)
    return parser


def _matrix_data_view(matrix) -> np.ndarray:
    if sp.issparse(matrix):
        return matrix.data
    return np.asarray(matrix).ravel()


def _validate_input_matrix(adata) -> None:
    if adata.X is None:
        raise ValueError("Input AnnData has no matrix in `adata.X`.")

    data = _matrix_data_view(adata.X)
    if data.size == 0:
        raise ValueError("Input matrix is empty.")
    if np.any(data < 0):
        raise ValueError("scATAC preprocessing requires a non-negative accessibility matrix.")

    fractional = np.abs(data - np.round(data)) > 1e-6
    if np.any(fractional):
        logger.warning(
            "Input matrix contains non-integer values. Continuing, but TF-IDF + LSI "
            "is intended for raw-count-like or binary accessibility matrices."
        )


def _compute_qc_metrics(adata) -> None:
    counts = adata.X
    total_counts = np.asarray(counts.sum(axis=1)).ravel()
    n_peaks_by_counts = np.asarray((counts > 0).sum(axis=1)).ravel()
    fraction_accessible = n_peaks_by_counts / max(int(adata.n_vars), 1)

    adata.obs["total_counts"] = total_counts.astype(float)
    adata.obs["n_peaks_by_counts"] = n_peaks_by_counts.astype(int)
    adata.obs["fraction_accessible"] = fraction_accessible.astype(float)


def _filter_cells_and_peaks(adata, *, min_peaks: int, min_cells: int):
    _compute_qc_metrics(adata)
    keep_cells = adata.obs["n_peaks_by_counts"] >= min_peaks
    if int(keep_cells.sum()) == 0:
        raise RuntimeError("All cells were removed by `min_peaks`. Lower the threshold.")
    adata = adata[keep_cells.to_numpy(), :].copy()

    keep_peaks = np.asarray((adata.X > 0).sum(axis=0)).ravel() >= min_cells
    if int(keep_peaks.sum()) == 0:
        raise RuntimeError("All peaks were removed by `min_cells`. Lower the threshold.")
    adata = adata[:, keep_peaks].copy()
    _compute_qc_metrics(adata)
    return adata


def _select_top_peaks(adata, *, n_top_peaks: int):
    total_counts = np.asarray(adata.X.sum(axis=0)).ravel()
    n_cells_by_counts = np.asarray((adata.X > 0).sum(axis=0)).ravel()
    adata.var["total_counts"] = total_counts.astype(float)
    adata.var["n_cells_by_counts"] = n_cells_by_counts.astype(int)

    preprocess_state = adata.uns.setdefault("scatac_preprocess", {})
    preprocess_state["n_peaks_after_filter"] = int(adata.n_vars)

    if n_top_peaks >= int(adata.n_vars):
        adata.var["selected_for_lsi"] = True
        preprocess_state["n_selected_peaks"] = int(adata.n_vars)
        return adata

    order = np.argsort(-total_counts, kind="mergesort")
    keep = np.sort(order[:n_top_peaks])
    adata = adata[:, keep].copy()
    adata.var["selected_for_lsi"] = True
    preprocess_state["n_selected_peaks"] = int(adata.n_vars)
    return adata


def _tfidf_normalize(matrix, *, scale_factor: float):
    matrix = matrix.tocsr().astype(np.float32)

    cell_sums = np.asarray(matrix.sum(axis=1)).ravel()
    cell_sums[cell_sums == 0] = 1.0
    tf = matrix.multiply((1.0 / cell_sums)[:, None])

    peak_presence = np.asarray((matrix > 0).sum(axis=0)).ravel().astype(np.float32)
    peak_presence[peak_presence == 0] = 1.0
    idf = matrix.shape[0] / peak_presence

    tfidf = tf.multiply(idf)
    if scale_factor != 1.0:
        tfidf = tfidf.multiply(scale_factor)
    tfidf.data = np.log1p(tfidf.data)
    return tfidf.tocsr()


def preprocess_tfidf_lsi(
    adata,
    *,
    min_peaks: int = 200,
    min_cells: int = 5,
    n_top_peaks: int = 10000,
    tfidf_scale_factor: float = 10000.0,
    n_lsi: int = 30,
    n_neighbors: int = 15,
    leiden_resolution: float = 0.8,
):
    """Implementation-aligned scATAC preprocessing pipeline."""
    logger.info("Input: %d cells x %d peaks", adata.n_obs, adata.n_vars)
    _validate_input_matrix(adata)

    adata = _filter_cells_and_peaks(
        adata,
        min_peaks=min_peaks,
        min_cells=min_cells,
    )
    adata = _select_top_peaks(adata, n_top_peaks=n_top_peaks)

    adata.layers["counts"] = adata.X.copy()
    adata.raw = adata.copy()
    adata.X = _tfidf_normalize(adata.layers["counts"], scale_factor=tfidf_scale_factor)

    max_components = min(int(n_lsi), int(adata.n_obs) - 1, int(adata.n_vars) - 1)
    if max_components < 2:
        raise RuntimeError("Not enough cells or peaks remain to compute a stable LSI embedding.")

    svd = TruncatedSVD(n_components=max_components, random_state=0)
    lsi = svd.fit_transform(adata.X)

    if bool(METHOD_PARAM_DEFAULTS["tfidf_lsi"]["scale_lsi_embeddings"]):
        lsi = StandardScaler().fit_transform(lsi)

    adata.obsm["X_lsi"] = lsi
    adata.varm["LSI"] = svd.components_.T
    variance_ratio = np.asarray(svd.explained_variance_ratio_, dtype=float)
    singular_values = np.asarray(svd.singular_values_, dtype=float)

    graph_start_idx = 1 if max_components > 1 else 0
    graph_rep = lsi[:, graph_start_idx:]
    if graph_rep.shape[1] == 0:
        graph_start_idx = 0
        graph_rep = lsi
    adata.obsm["X_lsi_graph"] = graph_rep
    adata.uns["lsi"] = {
        "variance_ratio": variance_ratio,
        "singular_values": singular_values,
        "skip_first_component": bool(graph_start_idx == 1),
        "graph_component_start": int(graph_start_idx + 1),
        "graph_component_count": int(graph_rep.shape[1]),
    }

    sc.pp.neighbors(adata, use_rep="X_lsi_graph", n_neighbors=n_neighbors)
    sc.tl.umap(adata)
    sc.tl.leiden(
        adata,
        resolution=leiden_resolution,
        key_added="leiden",
        flavor="igraph",
        directed=False,
        n_iterations=2,
    )
    adata.obs["leiden"] = adata.obs["leiden"].astype(str).astype("category")
    adata.obs["preprocess_method"] = "tfidf_lsi"
    return adata


def build_effective_params(method: str, args) -> dict:
    if method not in METHOD_PARAM_DEFAULTS:
        raise ValueError(f"Unknown preprocessing method '{method}'")

    effective = dict(METHOD_PARAM_DEFAULTS[method])
    for key in PUBLIC_PARAM_KEYS:
        if key == "method":
            continue
        value = getattr(args, key, None)
        if value is not None:
            effective[key] = value
    effective["method"] = method
    return effective


def build_public_params(effective_params: dict) -> dict:
    return {key: effective_params[key] for key in PUBLIC_PARAM_KEYS if key in effective_params}


def _build_cluster_summary_table(summary: dict) -> pd.DataFrame:
    cluster_counts = summary.get("cluster_counts", {})
    n_cells = max(int(summary.get("n_cells", 0)), 1)
    rows = [
        {
            "cluster": str(cluster),
            "n_cells": int(count),
            "proportion_pct": round(int(count) / n_cells * 100, 2),
        }
        for cluster, count in cluster_counts.items()
    ]
    if not rows:
        return pd.DataFrame(columns=["cluster", "n_cells", "proportion_pct"])
    return pd.DataFrame(rows).sort_values(["n_cells", "cluster"], ascending=[False, True]).reset_index(drop=True)


def _build_preprocess_summary_table(summary: dict, effective_params: dict) -> pd.DataFrame:
    records = [
        {"metric": "method", "value": str(summary.get("method", effective_params.get("method", "")))},
        {"metric": "n_cells", "value": int(summary.get("n_cells", 0))},
        {"metric": "n_peaks_after_filter", "value": int(summary.get("n_peaks_after_filter", 0))},
        {"metric": "n_selected_peaks", "value": int(summary.get("n_selected_peaks", 0))},
        {"metric": "n_clusters", "value": int(summary.get("n_clusters", 0))},
        {"metric": "min_peaks", "value": effective_params.get("min_peaks")},
        {"metric": "min_cells", "value": effective_params.get("min_cells")},
        {"metric": "n_top_peaks", "value": effective_params.get("n_top_peaks")},
        {"metric": "tfidf_scale_factor", "value": effective_params.get("tfidf_scale_factor")},
        {"metric": "n_lsi_requested", "value": effective_params.get("n_lsi")},
        {"metric": "n_lsi_used", "value": summary.get("n_lsi_used")},
        {"metric": "n_neighbors", "value": effective_params.get("n_neighbors")},
        {"metric": "leiden_resolution", "value": effective_params.get("leiden_resolution")},
    ]
    return pd.DataFrame(records)


def _build_peak_summary_table(adata, n_top: int = 50) -> pd.DataFrame:
    if "total_counts" not in adata.var.columns:
        return pd.DataFrame(columns=["peak", "total_counts", "n_cells_by_counts"])

    peak_df = adata.var.copy()
    peak_df["peak"] = peak_df.index.astype(str)
    peak_df = peak_df.sort_values(
        ["total_counts", "n_cells_by_counts", "peak"],
        ascending=[False, False, True],
    )
    keep_cols = ["peak", "total_counts", "n_cells_by_counts"]
    return peak_df.loc[:, keep_cols].head(n_top).reset_index(drop=True)


def _build_lsi_variance_table(adata) -> pd.DataFrame:
    if "lsi" not in adata.uns or "variance_ratio" not in adata.uns["lsi"]:
        return pd.DataFrame(columns=["component", "variance_ratio", "cumulative_variance_ratio"])
    variance_ratio = np.asarray(adata.uns["lsi"]["variance_ratio"], dtype=float)
    return pd.DataFrame(
        {
            "component": np.arange(1, len(variance_ratio) + 1),
            "variance_ratio": variance_ratio,
            "cumulative_variance_ratio": np.cumsum(variance_ratio),
        }
    )


def _build_umap_points_table(adata, cluster_key: str) -> pd.DataFrame:
    if "X_umap" not in adata.obsm:
        return pd.DataFrame(columns=["cell_id", "UMAP1", "UMAP2", cluster_key])
    coords = np.asarray(adata.obsm["X_umap"])
    data = {
        "cell_id": adata.obs_names.astype(str),
        "UMAP1": coords[:, 0],
        "UMAP2": coords[:, 1],
    }
    if cluster_key in adata.obs.columns:
        data[cluster_key] = adata.obs[cluster_key].astype(str).to_numpy()
    return pd.DataFrame(data)


def _build_qc_metrics_table(adata) -> pd.DataFrame:
    qc_cols = [column for column in ("n_peaks_by_counts", "total_counts", "fraction_accessible") if column in adata.obs.columns]
    if not qc_cols:
        return pd.DataFrame(columns=["cell_id"])
    qc_df = adata.obs.loc[:, qc_cols].copy()
    qc_df.insert(0, "cell_id", adata.obs_names.astype(str))
    return qc_df.reset_index(drop=True)


def _prepare_scatac_gallery_context(adata, summary: dict, effective_params: dict, output_dir: Path) -> dict:
    cluster_key = str(summary.get("cluster_key", "leiden"))
    qc_metric_cols = [column for column in ("n_peaks_by_counts", "total_counts", "fraction_accessible") if column in adata.obs.columns]
    return {
        "output_dir": Path(output_dir),
        "cluster_key": cluster_key,
        "qc_metric_cols": qc_metric_cols,
        "cluster_summary_df": _build_cluster_summary_table(summary),
        "preprocess_summary_df": _build_preprocess_summary_table(summary, effective_params),
        "peak_summary_df": _build_peak_summary_table(adata),
        "lsi_variance_df": _build_lsi_variance_table(adata),
        "umap_points_df": _build_umap_points_table(adata, cluster_key),
        "qc_metrics_df": _build_qc_metrics_table(adata),
    }


def _build_scatac_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    cluster_key = context["cluster_key"]
    plots: list[PlotSpec] = [
        PlotSpec(
            plot_id="scatac_umap_clusters",
            role="overview",
            renderer="umap_clusters",
            filename=f"umap_{cluster_key}.png",
            title="UMAP clusters",
            description="UMAP embedding colored by the default Leiden clustering column.",
            required_obsm=["X_umap"],
            required_obs=[cluster_key],
        ),
        PlotSpec(
            plot_id="scatac_qc_violin",
            role="diagnostic",
            renderer="qc_violin",
            filename="qc_violin.png",
            title="QC metrics violin",
            description="Per-cell accessibility QC metrics after filtering.",
            required_obs=[column for column in context["qc_metric_cols"]],
        ),
        PlotSpec(
            plot_id="scatac_top_peaks",
            role="diagnostic",
            renderer="peak_accessibility",
            filename="top_accessible_peaks.png",
            title="Top accessible peaks",
            description="Most accessible retained peaks in the final feature space.",
        ),
        PlotSpec(
            plot_id="scatac_lsi_variance",
            role="supporting",
            renderer="lsi_variance",
            filename="lsi_variance.png",
            title="LSI variance",
            description="Explained variance across latent semantic indexing components.",
            required_uns=["lsi"],
        ),
    ]
    return VisualizationRecipe(
        recipe_id="standard-scatac-preprocessing-gallery",
        skill_name=SKILL_NAME,
        title="scATAC preprocessing gallery",
        description=f"Default OmicsClaw scATAC preprocessing gallery for method '{summary.get('method', '')}'.",
        plots=plots,
    )


def _gallery_figure_path(output_dir: Path, filename: str) -> Path:
    return Path(output_dir) / "figures" / filename


def _render_qc_violin(adata, spec: PlotSpec, context: dict):
    output_dir = Path(context["output_dir"])
    sc_qc_utils.plot_qc_violin(adata, output_dir, metrics=context.get("qc_metric_cols") or None)
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_umap_clusters(adata, spec: PlotSpec, context: dict):
    output_dir = Path(context["output_dir"])
    plot_umap_clusters(adata, output_dir, cluster_key=context["cluster_key"])
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_peak_accessibility(adata, spec: PlotSpec, context: dict):
    import matplotlib.pyplot as plt

    peak_df = context.get("peak_summary_df", pd.DataFrame())
    if not isinstance(peak_df, pd.DataFrame) or peak_df.empty:
        return None

    top_df = peak_df.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(top_df["peak"], top_df["total_counts"], color="#4c72b0")
    ax.set_xlabel("Total counts")
    ax.set_ylabel("Peak")
    ax.set_title("Top Accessible Peaks")
    ax.grid(axis="x", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    path = _gallery_figure_path(Path(context["output_dir"]), spec.filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _render_lsi_variance(adata, spec: PlotSpec, context: dict):
    import matplotlib.pyplot as plt

    lsi_df = context.get("lsi_variance_df", pd.DataFrame())
    if not isinstance(lsi_df, pd.DataFrame) or lsi_df.empty:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(lsi_df["component"], lsi_df["variance_ratio"], "o-", markersize=3, color="#4c72b0")
    axes[0].set_xlabel("LSI Component")
    axes[0].set_ylabel("Variance Ratio")
    axes[0].set_title("LSI Variance")
    axes[1].plot(
        lsi_df["component"],
        lsi_df["cumulative_variance_ratio"] * 100.0,
        "o-",
        markersize=3,
        color="#dd8452",
    )
    axes[1].set_xlabel("Number of Components")
    axes[1].set_ylabel("Cumulative Variance (%)")
    axes[1].set_title("Cumulative LSI Variance")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    plt.tight_layout()

    path = _gallery_figure_path(Path(context["output_dir"]), spec.filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


SCATAC_GALLERY_RENDERERS = {
    "qc_violin": _render_qc_violin,
    "umap_clusters": _render_umap_clusters,
    "peak_accessibility": _render_peak_accessibility,
    "lsi_variance": _render_lsi_variance,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_figure_data(adata, output_dir: Path, summary: dict, recipe: VisualizationRecipe, artifacts, context: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    available_files: dict[str, str] = {}
    export_map = {
        "preprocess_summary": ("preprocess_summary.csv", context.get("preprocess_summary_df", pd.DataFrame())),
        "cluster_summary": ("cluster_summary.csv", context.get("cluster_summary_df", pd.DataFrame())),
        "peak_summary": ("peak_summary.csv", context.get("peak_summary_df", pd.DataFrame())),
        "lsi_variance_ratio": ("lsi_variance_ratio.csv", context.get("lsi_variance_df", pd.DataFrame())),
        "umap_points": ("umap_points.csv", context.get("umap_points_df", pd.DataFrame())),
        "qc_metrics_per_cell": ("qc_metrics_per_cell.csv", context.get("qc_metrics_df", pd.DataFrame())),
    }
    for key, (filename, df) in export_map.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.to_csv(figure_data_dir / filename, index=False)
            available_files[key] = filename

    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": recipe.recipe_id,
        "method": summary.get("method"),
        "cluster_column": context.get("cluster_key"),
        "available_files": available_files,
        "plots": [
            {
                "plot_id": artifact.plot_id,
                "filename": artifact.filename,
                "status": artifact.status,
                "role": artifact.role,
            }
            for artifact in artifacts
        ],
    }
    _write_figure_data_manifest(output_dir, manifest)
    context["figure_data_files"] = available_files
    context["figure_data_manifest"] = manifest


def generate_figures(adata, output_dir: Path, summary: dict | None = None, *, gallery_context: dict | None = None) -> list[str]:
    summary = summary or {}
    context = gallery_context or {}
    if "output_dir" not in context:
        context["output_dir"] = Path(output_dir)
    recipe = _build_scatac_visualization_recipe(adata, summary, context)
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        SCATAC_GALLERY_RENDERERS,
        context=context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    context["recipe"] = recipe
    context["artifacts"] = artifacts
    return [artifact.path for artifact in artifacts if artifact.status == "rendered" and artifact.path]


def export_tables(output_dir: Path, *, gallery_context: dict | None = None) -> list[str]:
    context = gallery_context or {}
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []

    for filename, key in (
        ("preprocess_summary.csv", "preprocess_summary_df"),
        ("cluster_summary.csv", "cluster_summary_df"),
        ("peak_summary.csv", "peak_summary_df"),
        ("lsi_variance_ratio.csv", "lsi_variance_df"),
        ("qc_metrics_per_cell.csv", "qc_metrics_df"),
    ):
        df = context.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            path = tables_dir / filename
            df.to_csv(path, index=False)
            exported.append(str(path))
    return exported


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    effective_params: dict,
    *,
    gallery_context: dict | None = None,
) -> None:
    context = gallery_context or {}
    cluster_key = context.get("cluster_key", summary.get("cluster_key", "leiden"))
    header = generate_report_header(
        title="scATAC Preprocessing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Cells": str(summary["n_cells"]),
            "Peaks After Filter": str(summary["n_peaks_after_filter"]),
            "Selected Peaks": str(summary["n_selected_peaks"]),
            "Clusters": str(summary["n_clusters"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells after filtering**: {summary['n_cells']}",
        f"- **Peaks after sparsity filtering**: {summary['n_peaks_after_filter']}",
        f"- **Retained peaks for LSI**: {summary['n_selected_peaks']}",
        f"- **LSI components used**: {summary['n_lsi_used']}",
        f"- **Clusters**: {summary['n_clusters']}",
        f"- **Primary cluster column**: `{cluster_key}`",
        "",
        "## Default Gallery\n",
        "- `figures/manifest.json` records the standard Python gallery.",
        "- `figure_data/` contains figure-ready CSV files for optional downstream styling.",
        "",
        "## Effective Parameters\n",
    ]
    for key, value in effective_params.items():
        body_lines.append(f"- `{key}`: {value}")

    cluster_summary_df = context.get("cluster_summary_df")
    if isinstance(cluster_summary_df, pd.DataFrame) and not cluster_summary_df.empty:
        body_lines.extend(["", "## Cluster Summary\n", "| Cluster | Cells | Proportion (%) |", "|---------|-------|----------------|"])
        for row in cluster_summary_df.itertuples(index=False):
            body_lines.append(f"| {row.cluster} | {row.n_cells} | {row.proportion_pct:.2f} |")

    body_lines.extend(
        [
            "",
            "## Notes\n",
            "- This wrapper expects a raw-count-like peak matrix and does not start from fragments or call peaks.",
            "- The final AnnData stores the retained peak space used for TF-IDF + LSI.",
            "",
            "## Output Files\n",
            "- `README.md` — user-first output navigation file.",
            "- `processed.h5ad` — downstream-ready AnnData object in the retained peak space.",
            "- `figures/` — standard OmicsClaw scATAC preprocessing gallery.",
            "- `figure_data/` — CSV exports for optional custom visualization layers.",
            "- `tables/preprocess_summary.csv` — compact run summary.",
            "- `tables/cluster_summary.csv` — cluster size summary.",
            "- `tables/peak_summary.csv` — most accessible retained peaks.",
            "- `tables/lsi_variance_ratio.csv` — LSI variance explained.",
            "- `tables/qc_metrics_per_cell.csv` — retained per-cell QC metrics.",
            "- `reproducibility/commands.sh` — reproducible CLI entrypoint.",
            "- `reproducibility/analysis_notebook.ipynb` — code-first rerun notebook.",
        ]
    )

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def write_reproducibility(output_dir: Path, public_params: dict, input_file: str | None, *, demo_mode: bool = False) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    else:
        command_parts.extend(["--input", "<input.h5ad>"])
    command_parts.extend(["--output", str(output_dir)])
    for key in PUBLIC_PARAM_KEYS:
        if key not in public_params:
            continue
        value = public_params[key]
        if value is None or value == "":
            continue
        command_parts.extend([f"--{key.replace('_', '-')}", str(value)])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")

    packages = ["scanpy", "anndata", "numpy", "pandas", "scipy", "scikit-learn", "matplotlib"]
    env_lines: list[str] = []
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    for pkg in packages:
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + ("\n" if env_lines else ""), encoding="utf-8")


def get_demo_data():
    rng = np.random.default_rng(7)
    cluster_sizes = [60, 60, 60]
    n_cells = sum(cluster_sizes)
    n_peaks = 2000
    matrix = rng.binomial(1, 0.006, size=(n_cells, n_peaks)).astype(np.float32)


    cluster_blocks = [
        slice(0, 500),
        slice(500, 1000),
        slice(1000, 1500),
    ]
    shared_block = slice(1500, 1650)

    labels: list[str] = []
    start = 0
    for cluster_idx, cluster_size in enumerate(cluster_sizes):
        stop = start + cluster_size
        block = cluster_blocks[cluster_idx]
        matrix[start:stop, block] = np.maximum(
            matrix[start:stop, block],
            rng.binomial(1, 0.38, size=(cluster_size, block.stop - block.start)).astype(np.float32),
        )
        matrix[start:stop, shared_block] = np.maximum(
            matrix[start:stop, shared_block],
            rng.binomial(1, 0.16, size=(cluster_size, shared_block.stop - shared_block.start)).astype(np.float32),
        )
        labels.extend([f"cluster_{cluster_idx + 1}"] * cluster_size)
        start = stop

    low_quality = rng.choice(n_cells, size=6, replace=False)
    matrix[low_quality, :] = rng.binomial(1, 0.01, size=(len(low_quality), n_peaks)).astype(np.float32)

    adata = sc.AnnData(sp.csr_matrix(matrix))
    adata.obs_names = [f"cell_{idx:04d}" for idx in range(n_cells)]
    adata.var_names = [f"chr1:{1000 + idx * 50}-{1049 + idx * 50}" for idx in range(n_peaks)]
    adata.obs["demo_group"] = pd.Categorical(labels)
    return adata, None


def build_summary(adata, method: str) -> dict:
    cluster_key = "leiden"
    cluster_counts = adata.obs[cluster_key].astype(str).value_counts().to_dict() if cluster_key in adata.obs else {}
    lsi_info = adata.uns.get("lsi", {})
    preprocess_state = adata.uns.get("scatac_preprocess", {})
    n_neighbors_used = adata.uns.get("neighbors", {}).get("params", {}).get("n_neighbors")
    return {
        "method": method,
        "cluster_key": cluster_key,
        "n_cells": int(adata.n_obs),
        "n_peaks": int(adata.n_vars),
        "n_peaks_after_filter": int(preprocess_state.get("n_peaks_after_filter", adata.n_vars)),
        "n_selected_peaks": int(preprocess_state.get("n_selected_peaks", adata.n_vars)),
        "n_clusters": len(cluster_counts),
        "n_lsi_used": int(adata.obsm["X_lsi"].shape[1]) if "X_lsi" in adata.obsm else 0,
        "n_neighbors_used": int(n_neighbors_used) if n_neighbors_used is not None else None,
        "lsi_graph_component_start": int(lsi_info.get("graph_component_start", 1)),
        "cluster_counts": {str(k): int(v) for k, v in cluster_counts.items()},
    }


def finalize_effective_params(adata, effective_params: dict, summary: dict) -> dict:
    finalized = dict(effective_params)
    finalized["cluster_key"] = summary.get("cluster_key")
    finalized["n_lsi_used"] = summary.get("n_lsi_used")
    finalized["n_neighbors_used"] = summary.get("n_neighbors_used")
    finalized["counts_layer"] = "counts" if "counts" in adata.layers else None
    finalized["raw_available"] = adata.raw is not None
    finalized["graph_rep"] = "X_lsi_graph" if "X_lsi_graph" in adata.obsm else "X_lsi"
    finalized["graph_component_start"] = summary.get("lsi_graph_component_start")
    finalized["retained_peak_space"] = int(adata.n_vars)
    return finalized


def main():
    parser = _build_parser()
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc_io.smart_load(args.input_path)
        input_file = args.input_path

    method = validate_method_choice(args.method, METHOD_REGISTRY)
    effective_params = build_effective_params(method, args)
    public_params = build_public_params(effective_params)

    adata = preprocess_tfidf_lsi(
        adata,
        min_peaks=int(effective_params["min_peaks"]),
        min_cells=int(effective_params["min_cells"]),
        n_top_peaks=int(effective_params["n_top_peaks"]),
        tfidf_scale_factor=float(effective_params["tfidf_scale_factor"]),
        n_lsi=int(effective_params["n_lsi"]),
        n_neighbors=int(effective_params["n_neighbors"]),
        leiden_resolution=float(effective_params["leiden_resolution"]),
    )

    summary = build_summary(adata, method)
    effective_params = finalize_effective_params(adata, effective_params, summary)
    gallery_context = _prepare_scatac_gallery_context(adata, summary, effective_params, output_dir)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, effective_params, gallery_context=gallery_context)
    write_reproducibility(output_dir, public_params, input_file, demo_mode=args.demo)

    store_analysis_metadata(adata, SKILL_NAME, method, effective_params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "method": method,
        "params": public_params,
        "effective_params": effective_params,
        **summary,
        "visualization": {
            "recipe_id": "standard-scatac-preprocessing-gallery",
            "cluster_column": gallery_context.get("cluster_key"),
            "embedding_key": "X_umap" if "X_umap" in adata.obsm else None,
            "latent_key": "X_lsi" if "X_lsi" in adata.obsm else None,
            "counts_layer": "counts" if "counts" in adata.layers else None,
            "selected_peak_column": "selected_for_lsi" if "selected_for_lsi" in adata.var.columns else None,
            "qc_metric_columns": gallery_context.get("qc_metric_cols", []),
            "available_figure_data": gallery_context.get("figure_data_files", {}),
        },
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Preprocessing complete: {summary['n_cells']} cells, {summary['n_clusters']} clusters")


if __name__ == "__main__":
    main()
