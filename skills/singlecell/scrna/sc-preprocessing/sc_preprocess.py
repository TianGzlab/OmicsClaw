#!/usr/bin/env python3
"""Single-Cell Preprocessing - Scanpy or Seurat/SCTransform workflows."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import scanpy as sc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib import dimred as sc_dimred_utils
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import preprocessing as sc_preproc_utils
from skills.singlecell._lib import qc as sc_qc_utils
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-preprocessing"
SKILL_VERSION = "0.4.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "scanpy": MethodConfig(
        name="scanpy",
        description="Scanpy preprocessing workflow",
        dependencies=("scanpy", "igraph", "leidenalg"),
    ),
    "seurat": MethodConfig(
        name="seurat",
        description="Seurat LogNormalize workflow (R)",
        dependencies=(),
    ),
    "sctransform": MethodConfig(
        name="sctransform",
        description="Seurat SCTransform workflow (R)",
        dependencies=(),
    ),
}

DEFAULT_METHOD = "scanpy"
PUBLIC_PARAM_KEYS = (
    "method",
    "min_genes",
    "min_cells",
    "max_mt_pct",
    "n_top_hvg",
    "n_pcs",
    "n_neighbors",
    "leiden_resolution",
)
METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "scanpy": {
        "method": "scanpy",
        "min_genes": 200,
        "min_cells": 3,
        "max_mt_pct": 20.0,
        "n_top_hvg": 2000,
        "n_pcs": 50,
        "n_neighbors": 15,
        "leiden_resolution": 1.0,
        "hvg_flavor": "seurat",
        "normalization_target_sum": 10000.0,
        "scale_max_value": 10.0,
    },
    "seurat": {
        "method": "seurat",
        "min_genes": 200,
        "min_cells": 3,
        "max_mt_pct": 20.0,
        "n_top_hvg": 2000,
        "n_pcs": 50,
        "n_neighbors": 20,
        "leiden_resolution": 0.8,
        "normalize_data_method": "LogNormalize",
        "normalize_scale_factor": 10000.0,
        "find_variable_features_method": "vst",
    },
    "sctransform": {
        "method": "sctransform",
        "min_genes": 200,
        "min_cells": 3,
        "max_mt_pct": 20.0,
        "n_top_hvg": 3000,
        "n_pcs": 50,
        "n_neighbors": 20,
        "leiden_resolution": 0.8,
        "sctransform_regress_mt": True,
    },
}


def preprocess_scanpy(
    adata,
    *,
    min_genes: int = 200,
    min_cells: int = 3,
    max_mt_pct: float = 20.0,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    n_neighbors: int = 15,
    leiden_resolution: float = 1.0,
):
    """Implementation-aligned Scanpy preprocessing pipeline."""
    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)

    adata.layers["counts"] = adata.X.copy()
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)

    adata.var["mt"] = adata.var_names.str.startswith("MT-") | adata.var_names.str.startswith("mt-")
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True)
    adata = adata[adata.obs.pct_counts_mt < max_mt_pct, :].copy()
    adata.layers["counts"] = adata.X.copy()

    adata = sc_preproc_utils.run_standard_normalization(
        adata,
        target_sum=float(METHOD_PARAM_DEFAULTS["scanpy"]["normalization_target_sum"]),
        inplace=True,
    )
    # Preserve log-normalized expression before scaling for downstream reuse.
    adata.raw = adata.copy()
    adata = sc_preproc_utils.find_highly_variable_genes(
        adata,
        n_top_genes=n_top_hvg,
        flavor=str(METHOD_PARAM_DEFAULTS["scanpy"]["hvg_flavor"]),
        inplace=True,
    )
    adata = sc_dimred_utils.scale_data(
        adata,
        max_value=float(METHOD_PARAM_DEFAULTS["scanpy"]["scale_max_value"]),
        inplace=True,
    )
    adata = sc_dimred_utils.run_pca_analysis(
        adata,
        n_pcs=n_pcs,
        svd_solver="arpack",
        inplace=True,
    )
    adata = sc_dimred_utils.build_neighbor_graph(
        adata,
        n_neighbors=n_neighbors,
        n_pcs=n_pcs,
        inplace=True,
    )
    adata = sc_dimred_utils.run_umap_reduction(adata, inplace=True)
    adata = sc_dimred_utils.cluster_leiden(
        adata,
        resolution=leiden_resolution,
        key_added="leiden",
        inplace=True,
    )

    return adata


def _choose_counts_matrix(adata):
    """Return the best available raw-count-like matrix for R-backed workflows."""
    if "counts" in adata.layers:
        return adata.layers["counts"]
    if adata.raw is not None and adata.raw.shape == adata.shape:
        return adata.raw.X
    return adata.X


def _build_export_adata(adata):
    """Build an AnnData export where ``X`` contains counts for the R script."""
    export_adata = adata.copy()
    export_adata.obs_names_make_unique()
    export_adata.var_names_make_unique()
    export_adata.X = _choose_counts_matrix(export_adata).copy()
    return export_adata


def _load_seurat_result(
    export_adata,
    *,
    output_dir: Path,
    workflow: str,
    n_neighbors: int,
    n_pcs: int,
):
    """Load Seurat CSV outputs back into a standard AnnData object."""
    obs_df = pd.read_csv(output_dir / "obs.csv", index_col=0)
    pca_df = pd.read_csv(output_dir / "pca.csv", index_col=0)
    umap_df = pd.read_csv(output_dir / "umap.csv", index_col=0)
    hvg_df = pd.read_csv(output_dir / "hvg.csv")
    norm_df = pd.read_csv(output_dir / "X_norm.csv", index_col=0)

    info = {}
    info_path = output_dir / "info.json"
    if info_path.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))

    norm_df = norm_df.T
    norm_df.index = norm_df.index.astype(str)
    norm_df.columns = norm_df.columns.astype(str)
    obs_df.index = obs_df.index.astype(str)
    pca_df.index = pca_df.index.astype(str)
    umap_df.index = umap_df.index.astype(str)

    ordered_cells = [cell for cell in norm_df.index if cell in export_adata.obs_names]
    ordered_genes = [gene for gene in norm_df.columns if gene in export_adata.var_names]
    if not ordered_cells or not ordered_genes:
        raise RuntimeError("Seurat preprocessing returned no overlapping cells or genes")

    norm_df = norm_df.loc[ordered_cells, ordered_genes]
    obs_base = export_adata.obs.loc[ordered_cells].copy()
    var_base = export_adata.var.loc[ordered_genes].copy()

    combined_obs = obs_base.join(obs_df, how="left", rsuffix="_seurat")
    if "seurat_clusters" in combined_obs:
        combined_obs["seurat_clusters"] = combined_obs["seurat_clusters"].astype(str)
        combined_obs["leiden"] = combined_obs["seurat_clusters"]
    if "nFeature_RNA" in combined_obs and "n_genes_by_counts" not in combined_obs:
        combined_obs["n_genes_by_counts"] = pd.to_numeric(combined_obs["nFeature_RNA"], errors="coerce")
    if "nCount_RNA" in combined_obs and "total_counts" not in combined_obs:
        combined_obs["total_counts"] = pd.to_numeric(combined_obs["nCount_RNA"], errors="coerce")
    if "percent.mt" in combined_obs and "pct_counts_mt" not in combined_obs:
        combined_obs["pct_counts_mt"] = pd.to_numeric(combined_obs["percent.mt"], errors="coerce")
    combined_obs["preprocess_method"] = workflow

    hvg_set = set()
    if "gene" in hvg_df.columns:
        hvg_set = {str(gene) for gene in hvg_df["gene"].dropna().astype(str)}
    var_base["highly_variable"] = [gene in hvg_set for gene in var_base.index.astype(str)]

    result = sc.AnnData(X=norm_df.to_numpy(), obs=combined_obs, var=var_base)
    result.layers["counts"] = export_adata[ordered_cells, ordered_genes].X.copy()

    pca_aligned = pca_df.reindex(ordered_cells)
    umap_aligned = umap_df.reindex(ordered_cells)
    if pca_aligned.isna().any().any():
        raise RuntimeError("Seurat preprocessing returned PCA rows that do not align with exported cells")
    if umap_aligned.isna().any().any():
        raise RuntimeError("Seurat preprocessing returned UMAP rows that do not align with exported cells")
    result.obsm["X_pca"] = pca_aligned.to_numpy(dtype=float)
    result.obsm["X_umap"] = umap_aligned.to_numpy(dtype=float)

    if result.obsm["X_pca"].size:
        variance = np.var(result.obsm["X_pca"], axis=0, ddof=1)
        variance = np.clip(variance, a_min=0.0, a_max=None)
        total = float(variance.sum())
        result.uns["pca"] = {
            "variance": variance,
            "variance_ratio": (variance / total) if total > 0 else variance,
        }

    if result.obsm["X_pca"].shape[1] > 0:
        sc.pp.neighbors(
            result,
            use_rep="X_pca",
            n_neighbors=n_neighbors,
            n_pcs=min(n_pcs, result.obsm["X_pca"].shape[1]),
        )

    result.uns["seurat_info"] = info
    # Preserve the returned normalized expression matrix for downstream inspection.
    result.raw = result.copy()
    return result


def run_seurat_preprocessing(
    adata,
    *,
    workflow: str,
    min_genes: int = 200,
    min_cells: int = 3,
    max_mt_pct: float = 20.0,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    n_neighbors: int = 15,
    leiden_resolution: float = 1.0,
):
    """Run the Seurat / SCTransform preprocessing backend via the shared R script."""
    required_packages = ["Seurat", "SingleCellExperiment", "zellkonverter"]
    if workflow == "sctransform":
        required_packages.append("sctransform")
    validate_r_environment(required_r_packages=required_packages)

    export_adata = _build_export_adata(adata)
    logger.info("Running R-backed %s preprocessing on %d cells x %d genes", workflow, export_adata.n_obs, export_adata.n_vars)

    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)

    with tempfile.TemporaryDirectory(prefix="omicsclaw_sc_preprocess_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        r_output_dir = tmpdir / "output"
        basilisk_dir = tmpdir / "basilisk"
        r_output_dir.mkdir(parents=True, exist_ok=True)
        basilisk_dir.mkdir(parents=True, exist_ok=True)
        export_adata.write_h5ad(input_h5ad)

        runner.run_script(
            "sc_seurat_preprocess.R",
            args=[
                str(input_h5ad),
                str(r_output_dir),
                workflow,
                str(min_genes),
                str(min_cells),
                str(max_mt_pct),
                str(n_top_hvg),
                str(n_pcs),
                str(n_neighbors),
                str(leiden_resolution),
            ],
            expected_outputs=["obs.csv", "pca.csv", "umap.csv", "hvg.csv", "X_norm.csv", "info.json"],
            output_dir=r_output_dir,
            env={"BASILISK_EXTERNAL_DIR": str(basilisk_dir)},
        )

        return _load_seurat_result(
            export_adata,
            output_dir=r_output_dir,
            workflow=workflow,
            n_neighbors=n_neighbors,
            n_pcs=n_pcs,
        )


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
        {"metric": "n_genes", "value": int(summary.get("n_genes", 0))},
        {"metric": "n_hvg", "value": int(summary.get("n_hvg", 0))},
        {"metric": "n_clusters", "value": int(summary.get("n_clusters", 0))},
        {"metric": "cluster_key", "value": str(summary.get("cluster_key", "leiden"))},
        {"metric": "min_genes", "value": effective_params.get("min_genes")},
        {"metric": "min_cells", "value": effective_params.get("min_cells")},
        {"metric": "max_mt_pct", "value": effective_params.get("max_mt_pct")},
        {"metric": "n_top_hvg", "value": effective_params.get("n_top_hvg")},
        {"metric": "n_pcs_requested", "value": effective_params.get("n_pcs")},
        {"metric": "n_pcs_used", "value": summary.get("n_pcs_used")},
        {"metric": "n_neighbors", "value": effective_params.get("n_neighbors")},
        {"metric": "leiden_resolution", "value": effective_params.get("leiden_resolution")},
    ]
    return pd.DataFrame(records)


def _build_hvg_summary_table(adata, n_top: int = 50) -> pd.DataFrame:
    if "highly_variable" not in adata.var.columns:
        return pd.DataFrame(columns=["gene"])
    hvg_df = adata.var.loc[adata.var["highly_variable"]].copy()
    if hvg_df.empty:
        return pd.DataFrame(columns=["gene"])

    hvg_df["gene"] = hvg_df.index.astype(str)
    sort_col = ""
    for candidate in ("dispersions_norm", "variances_norm", "dispersions", "means"):
        if candidate in hvg_df.columns:
            sort_col = candidate
            break
    if sort_col:
        hvg_df = hvg_df.sort_values(sort_col, ascending=False, na_position="last")

    keep_cols = ["gene"]
    for column in ("means", "variances", "variances_norm", "dispersions", "dispersions_norm"):
        if column in hvg_df.columns:
            keep_cols.append(column)
    return hvg_df.loc[:, keep_cols].head(n_top).reset_index(drop=True)


def _build_pca_variance_table(adata) -> pd.DataFrame:
    if "pca" not in adata.uns or "variance_ratio" not in adata.uns["pca"]:
        return pd.DataFrame(columns=["pc", "variance_ratio", "cumulative_variance_ratio"])
    variance_ratio = np.asarray(adata.uns["pca"]["variance_ratio"], dtype=float)
    return pd.DataFrame(
        {
            "pc": np.arange(1, len(variance_ratio) + 1),
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
    qc_cols = [column for column in ("n_genes_by_counts", "total_counts", "pct_counts_mt") if column in adata.obs.columns]
    if not qc_cols:
        return pd.DataFrame(columns=["cell_id"])
    qc_df = adata.obs.loc[:, qc_cols].copy()
    qc_df.insert(0, "cell_id", adata.obs_names.astype(str))
    return qc_df.reset_index(drop=True)


def build_effective_params(method: str, args) -> dict:
    """Merge method defaults with user-supplied CLI overrides."""
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
    """Return replayable public parameters for result.json and commands.sh."""
    return {key: effective_params[key] for key in PUBLIC_PARAM_KEYS if key in effective_params}


def _prepare_preprocess_gallery_context(adata, summary: dict, effective_params: dict, output_dir: Path) -> dict:
    cluster_key = str(summary.get("cluster_key", "leiden"))
    qc_metric_cols = [column for column in ("n_genes_by_counts", "total_counts", "pct_counts_mt") if column in adata.obs.columns]
    context = {
        "output_dir": Path(output_dir),
        "cluster_key": cluster_key,
        "qc_metric_cols": qc_metric_cols,
        "cluster_summary_df": _build_cluster_summary_table(summary),
        "preprocess_summary_df": _build_preprocess_summary_table(summary, effective_params),
        "hvg_summary_df": _build_hvg_summary_table(adata),
        "pca_variance_df": _build_pca_variance_table(adata),
        "umap_points_df": _build_umap_points_table(adata, cluster_key),
        "qc_metrics_df": _build_qc_metrics_table(adata),
    }
    return context


def _build_preprocess_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    cluster_key = context["cluster_key"]
    plots: list[PlotSpec] = [
        PlotSpec(
            plot_id="preprocess_umap_clusters",
            role="overview",
            renderer="umap_clusters",
            filename=f"umap_{cluster_key}.png",
            title="UMAP clusters",
            description="UMAP embedding colored by the default clustering column.",
            required_obsm=["X_umap"],
            required_obs=[cluster_key],
        ),
        PlotSpec(
            plot_id="preprocess_qc_violin",
            role="diagnostic",
            renderer="qc_violin",
            filename="qc_violin.png",
            title="QC metrics violin",
            description="Per-cell QC metrics after preprocessing and filtering.",
            required_obs=[column for column in context["qc_metric_cols"]],
        ),
        PlotSpec(
            plot_id="preprocess_hvg",
            role="diagnostic",
            renderer="hvg_plot",
            filename="highly_variable_genes.png",
            title="Highly variable genes",
            description="HVG selection summary from the active preprocessing workflow.",
        ),
        PlotSpec(
            plot_id="preprocess_pca_variance",
            role="supporting",
            renderer="pca_variance",
            filename="pca_variance.png",
            title="PCA variance",
            description="Explained variance across principal components.",
            required_obsm=["X_pca"],
            required_uns=["pca"],
        ),
    ]
    return VisualizationRecipe(
        recipe_id="standard-sc-preprocessing-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell preprocessing gallery",
        description=f"Default OmicsClaw preprocessing gallery for method '{summary.get('method', '')}'.",
        plots=plots,
    )


def _gallery_figure_path(output_dir: Path, filename: str) -> Path:
    return Path(output_dir) / "figures" / filename


def _render_qc_violin(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_qc_utils.plot_qc_violin(adata, output_dir, metrics=context.get("qc_metric_cols") or None)
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_hvg_plot(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_preproc_utils.plot_variable_genes(adata, output_dir)
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_pca_variance(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_dimred_utils.plot_pca_variance(adata, output_dir, n_pcs=min(50, max(2, adata.obsm["X_pca"].shape[1])))
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_umap_clusters(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    cluster_key = context["cluster_key"]
    sc_dimred_utils.plot_umap_clusters(adata, output_dir, cluster_key=cluster_key)
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


PREPROCESS_GALLERY_RENDERERS = {
    "qc_violin": _render_qc_violin,
    "hvg_plot": _render_hvg_plot,
    "pca_variance": _render_pca_variance,
    "umap_clusters": _render_umap_clusters,
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
        "hvg_summary": ("hvg_summary.csv", context.get("hvg_summary_df", pd.DataFrame())),
        "pca_variance_ratio": ("pca_variance_ratio.csv", context.get("pca_variance_df", pd.DataFrame())),
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


def _generate_figures(adata, output_dir: Path, summary: dict, gallery_context: dict | None = None) -> list[str]:
    context = gallery_context or {}
    if "output_dir" not in context:
        context["output_dir"] = Path(output_dir)
    recipe = _build_preprocess_visualization_recipe(adata, summary, context)
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        PREPROCESS_GALLERY_RENDERERS,
        context=context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    context["recipe"] = recipe
    context["artifacts"] = artifacts
    return [artifact.path for artifact in artifacts if artifact.status == "rendered" and artifact.path]


def generate_figures(adata, output_dir: Path, summary: dict | None = None, *, gallery_context: dict | None = None) -> list[str]:
    return _generate_figures(adata, output_dir, summary or {}, gallery_context)


def export_tables(output_dir: Path, summary: dict, *, gallery_context: dict | None = None) -> list[str]:
    context = gallery_context or {}
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []

    for filename, key in (
        ("preprocess_summary.csv", "preprocess_summary_df"),
        ("cluster_summary.csv", "cluster_summary_df"),
        ("hvg_summary.csv", "hvg_summary_df"),
        ("pca_variance_ratio.csv", "pca_variance_df"),
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
    """Write comprehensive report."""
    context = gallery_context or {}
    cluster_key = context.get("cluster_key", summary.get("cluster_key", "leiden"))
    header = generate_report_header(
        title="Single-Cell Preprocessing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Cells": str(summary["n_cells"]),
            "Genes": str(summary["n_genes"]),
            "Clusters": str(summary["n_clusters"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells after QC**: {summary['n_cells']}",
        f"- **Genes after QC**: {summary['n_genes']}",
        f"- **HVGs selected**: {summary['n_hvg']}",
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
            "## Output Files\n",
            "- `README.md` — user-first output navigation file.",
            "- `processed.h5ad` — downstream-ready AnnData object.",
            "- `figures/` — standard OmicsClaw preprocessing gallery.",
            "- `figure_data/` — CSV exports for optional R or custom visualization layers.",
            "- `tables/preprocess_summary.csv` — run summary table.",
            "- `tables/cluster_summary.csv` — cluster size summary.",
            "- `tables/hvg_summary.csv` — top highly variable genes.",
            "- `tables/pca_variance_ratio.csv` — PCA variance explained.",
            "- `tables/qc_metrics_per_cell.csv` — QC metrics retained after filtering.",
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

    packages = ["scanpy", "anndata", "numpy", "pandas", "matplotlib"]
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


def write_standard_run_artifacts(output_dir: Path, result_payload: dict, summary: dict) -> None:
    """Emit wrapper-level README and notebook exports when dependencies allow."""
    notebook_path = None
    try:
        from omicsclaw.common.notebook_export import write_analysis_notebook

        notebook_path = write_analysis_notebook(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell preprocessing with Scanpy, Seurat LogNormalize, or Seurat SCTransform workflows.",
            result_payload=result_payload,
            preferred_method=summary.get("method", DEFAULT_METHOD),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell preprocessing with Scanpy, Seurat LogNormalize, or Seurat SCTransform workflows.",
            result_payload=result_payload,
            preferred_method=summary.get("method", DEFAULT_METHOD),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)


def get_demo_data():
    logger.info("Generating demo single-cell data")
    adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
    return adata, demo_path


def build_summary(adata, method: str) -> dict:
    cluster_key = "leiden" if "leiden" in adata.obs else "seurat_clusters"
    n_hvg = int(adata.var["highly_variable"].sum()) if "highly_variable" in adata.var else 0
    cluster_counts = adata.obs[cluster_key].astype(str).value_counts().to_dict() if cluster_key in adata.obs else {}
    n_pcs_used = int(adata.obsm["X_pca"].shape[1]) if "X_pca" in adata.obsm else 0
    n_neighbors_used = adata.uns.get("neighbors", {}).get("params", {}).get("n_neighbors")
    return {
        "method": method,
        "cluster_key": cluster_key,
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_hvg": n_hvg,
        "n_clusters": len(cluster_counts),
        "n_pcs_used": n_pcs_used,
        "n_neighbors_used": int(n_neighbors_used) if n_neighbors_used is not None else None,
        "cluster_counts": {str(k): int(v) for k, v in cluster_counts.items()},
    }


def finalize_effective_params(adata, effective_params: dict, summary: dict) -> dict:
    """Augment effective parameters with runtime-resolved values."""
    finalized = dict(effective_params)
    finalized["cluster_key"] = summary.get("cluster_key")
    finalized["n_pcs_used"] = summary.get("n_pcs_used")
    finalized["n_neighbors_used"] = summary.get("n_neighbors_used")
    finalized["counts_layer"] = "counts" if "counts" in adata.layers else None
    finalized["raw_available"] = adata.raw is not None

    if finalized.get("method") in {"seurat", "sctransform"}:
        info = adata.uns.get("seurat_info", {})
        if isinstance(info, dict):
            finalized["default_assay"] = info.get("default_assay")
    return finalized


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Preprocessing")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default=DEFAULT_METHOD)
    parser.add_argument("--min-genes", type=int, default=None)
    parser.add_argument("--min-cells", type=int, default=None)
    parser.add_argument("--max-mt-pct", type=float, default=None)
    parser.add_argument("--n-top-hvg", type=int, default=None)
    parser.add_argument("--n-pcs", type=int, default=None)
    parser.add_argument("--n-neighbors", type=int, default=None)
    parser.add_argument("--leiden-resolution", type=float, default=None)
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

    if method == "scanpy":
        adata = preprocess_scanpy(
            adata,
            min_genes=int(effective_params["min_genes"]),
            min_cells=int(effective_params["min_cells"]),
            max_mt_pct=float(effective_params["max_mt_pct"]),
            n_top_hvg=int(effective_params["n_top_hvg"]),
            n_pcs=int(effective_params["n_pcs"]),
            n_neighbors=int(effective_params["n_neighbors"]),
            leiden_resolution=float(effective_params["leiden_resolution"]),
        )
    else:
        adata = run_seurat_preprocessing(
            adata,
            workflow=method,
            min_genes=int(effective_params["min_genes"]),
            min_cells=int(effective_params["min_cells"]),
            max_mt_pct=float(effective_params["max_mt_pct"]),
            n_top_hvg=int(effective_params["n_top_hvg"]),
            n_pcs=int(effective_params["n_pcs"]),
            n_neighbors=int(effective_params["n_neighbors"]),
            leiden_resolution=float(effective_params["leiden_resolution"]),
        )

    adata.uns["omicsclaw_matrix_contract"] = {
        "X": "scaled_expression" if method == "scanpy" else "normalized_expression",
        "raw": "log1p_normalized_expression" if adata.raw is not None else None,
        "layers": {"counts": "raw_counts" if "counts" in adata.layers else None},
        "primary_cluster_key": "leiden",
        "preprocess_method": method,
    }

    summary = build_summary(adata, method)
    effective_params = finalize_effective_params(adata, effective_params, summary)
    gallery_context = _prepare_preprocess_gallery_context(adata, summary, effective_params, output_dir)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, summary, gallery_context=gallery_context)
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
            "recipe_id": "standard-sc-preprocessing-gallery",
            "cluster_column": gallery_context.get("cluster_key"),
            "umap_key": "X_umap" if "X_umap" in adata.obsm else None,
            "counts_layer": "counts" if "counts" in adata.layers else None,
            "hvg_column": "highly_variable" if "highly_variable" in adata.var.columns else None,
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
    write_standard_run_artifacts(output_dir, result_payload, summary)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Preprocessing complete: {summary['n_cells']} cells, {summary['n_clusters']} clusters")


if __name__ == "__main__":
    main()
