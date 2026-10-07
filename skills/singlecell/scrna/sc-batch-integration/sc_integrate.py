#!/usr/bin/env python3
"""Single-Cell Batch Integration - Python and R-backed methods."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc
import seaborn as sns

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.checksums import sha256_file
from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import (
    load_result_json,
    write_result_json,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib import dimred as sc_dimred_utils
from skills._sdk.notebook import load_skill

_api = load_skill("sc-batch-integration")
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice, check_data_requirements
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_batch_integration

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-batch-integration"
SKILL_VERSION = "0.3.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-batch-integration/sc_integrate.py"

R_ENHANCED_PLOTS = {
    # batch-integration exports umap_points.csv with batch/cluster labels.
    # plot_embedding_discrete colors by batch or cluster column.
    # plot_cell_barplot and plot_cell_sankey removed — no cell_type_counts.csv here.
    "plot_embedding_discrete": "r_embedding_discrete.png",
}

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "harmony": MethodConfig(
        name="harmony",
        description="Harmony — fast linear batch correction (harmonypy)",
        dependencies=("harmonypy",),
    ),
    "scvi": MethodConfig(
        name="scvi",
        description="scVI — variational autoencoder integration",
        dependencies=("scvi", "torch"),
        supports_gpu=True,
    ),
    "scanvi": MethodConfig(
        name="scanvi",
        description="scANVI — semi-supervised scVI",
        dependencies=("scvi", "torch"),
        supports_gpu=True,
    ),
    "bbknn": MethodConfig(
        name="bbknn",
        description="BBKNN — batch-balanced k-nearest neighbors",
        dependencies=("bbknn",),
    ),
    "fastmnn": MethodConfig(
        name="fastmnn",
        description="fastMNN — batchelor mutual nearest neighbors (R)",
        dependencies=(),
    ),
    "seurat_cca": MethodConfig(
        name="seurat_cca",
        description="Seurat CCA integration (R)",
        dependencies=(),
    ),
    "seurat_rpca": MethodConfig(
        name="seurat_rpca",
        description="Seurat RPCA integration (R)",
        dependencies=(),
    ),
    "scanorama": MethodConfig(
        name="scanorama",
        description="Scanorama — panoramic stitching integration",
        dependencies=("scanorama",),
    ),
    "simba": MethodConfig(
        name="simba",
        description="SIMBA — graph embedding batch integration via PBG",
        dependencies=("simba",),
    ),
}

DEFAULT_METHOD = "harmony"
SHARED_PARAM_KEYS = ("method", "batch_key")
METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "harmony": {"method": "harmony", "batch_key": "batch", "integration_pcs": 50, "harmony_theta": 2.0},
    "scvi": {"method": "scvi", "batch_key": "batch", "n_epochs": 400, "no_gpu": False, "n_latent": 30},
    "scanvi": {"method": "scanvi", "batch_key": "batch", "n_epochs": 200, "no_gpu": False, "n_latent": 30, "labels_key": None},
    "bbknn": {"method": "bbknn", "batch_key": "batch", "bbknn_neighbors_within_batch": 3},
    "scanorama": {"method": "scanorama", "batch_key": "batch", "scanorama_knn": 20},
    "simba": {"method": "simba", "batch_key": "batch", "simba_n_top_genes": 3000, "simba_n_components": 15, "simba_k": 15, "simba_num_workers": 4},
    "fastmnn": {"method": "fastmnn", "batch_key": "batch", "integration_features": 2000, "integration_pcs": 30},
    "seurat_cca": {"method": "seurat_cca", "batch_key": "batch", "integration_features": 2000, "integration_pcs": 30},
    "seurat_rpca": {"method": "seurat_rpca", "batch_key": "batch", "integration_features": 2000, "integration_pcs": 30},
}
METHOD_PARAM_KEYS: dict[str, tuple[str, ...]] = {
    "harmony": ("integration_pcs", "harmony_theta"),
    "scvi": ("n_epochs", "no_gpu", "n_latent"),
    "scanvi": ("n_epochs", "no_gpu", "n_latent", "labels_key"),
    "bbknn": ("bbknn_neighbors_within_batch",),
    "scanorama": ("scanorama_knn",),
    "simba": ("simba_n_top_genes", "simba_n_components", "simba_k", "simba_num_workers"),
    "fastmnn": ("integration_features", "integration_pcs"),
    "seurat_cca": ("integration_features", "integration_pcs"),
    "seurat_rpca": ("integration_features", "integration_pcs"),
}


def _write_repro_requirements(repro_dir: Path, packages: list[str]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    lines: list[str] = []
    for pkg in packages:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )














def _preferred_label_key(adata) -> str | None:
    for candidate in ("cell_type", "leiden", "louvain", "seurat_clusters"):
        if candidate in adata.obs.columns:
            return candidate
    return None



def _build_cluster_sizes_table(adata, label_key: str | None) -> pd.DataFrame:
    if not label_key or label_key not in adata.obs.columns:
        return pd.DataFrame(columns=["label", "n_cells"])
    return (
        adata.obs[label_key]
        .astype(str)
        .value_counts()
        .rename_axis(label_key)
        .reset_index(name="n_cells")
        .sort_values("n_cells", ascending=False)
        .reset_index(drop=True)
    )



def _build_umap_points_table(adata, batch_key: str, label_key: str | None) -> pd.DataFrame:
    if "X_umap" not in adata.obsm:
        columns = ["cell_id", "UMAP1", "UMAP2", batch_key]
        if label_key:
            columns.append(label_key)
        return pd.DataFrame(columns=columns)
    coords = np.asarray(adata.obsm["X_umap"])
    payload = {
        "cell_id": adata.obs_names.astype(str),
        "UMAP1": coords[:, 0],
        "UMAP2": coords[:, 1],
        batch_key: adata.obs[batch_key].astype(str).to_numpy(),
    }
    if label_key and label_key in adata.obs.columns:
        payload[label_key] = adata.obs[label_key].astype(str).to_numpy()
    return pd.DataFrame(payload)



def _prepare_integration_gallery_context(adata, summary: dict, params: dict, output_dir: Path) -> dict:
    batch_key = params["batch_key"]
    label_key = _preferred_label_key(adata)
    return {
        "output_dir": Path(output_dir),
        "batch_key": batch_key,
        "label_key": label_key,
        "batch_sizes_df": _api.batch_sizes_table(adata, batch_key=batch_key),
        "cluster_sizes_df": _build_cluster_sizes_table(adata, label_key),
        "batch_mixing_df": _api.batch_mixing_table(adata, batch_key=batch_key, label_key=label_key),
        "umap_points_df": _build_umap_points_table(adata, batch_key, label_key),
        "integration_metrics_df": _api.integration_metrics(adata, batch_key=batch_key, label_key=label_key, embedding_key=summary["embedding_key"]),
        "integration_summary_df": pd.DataFrame(
            [
                {"metric": "method", "value": summary.get("method")},
                {"metric": "embedding_key", "value": summary.get("embedding_key")},
                {"metric": "n_batches", "value": summary.get("n_batches")},
                {"metric": "n_cells", "value": summary.get("n_cells")},
                {"metric": "batch_key", "value": batch_key},
                {"metric": "label_key", "value": label_key or ""},
            ]
        ),
    }


def _build_integration_visualization_recipe(_adata, summary: dict, context: dict) -> VisualizationRecipe:
    batch_key = context["batch_key"]
    label_key = context["label_key"]
    plots = [
            PlotSpec(
                plot_id="integration_umap_batch",
                role="overview",
                renderer="umap_batch",
                filename=f"umap_{batch_key}.png",
                title="Batch UMAP",
                description="UMAP colored by batch labels.",
                required_obsm=["X_umap"],
                required_obs=[batch_key],
            ),
            PlotSpec(
                plot_id="integration_metrics",
                role="supporting",
                renderer="integration_metrics_barplot",
                filename="integration_metrics.png",
                title="Integration diagnostics",
                description="Summary diagnostics including LISI and ASW when available.",
            ),
        ]
    if label_key:
        plots.extend(
            [
                PlotSpec(
                    plot_id="integration_umap_cluster",
                    role="overview",
                    renderer="umap_cluster",
                    filename=f"umap_{label_key}.png",
                    title="Label UMAP",
                    description="UMAP colored by the existing label column.",
                    required_obsm=["X_umap"],
                    required_obs=[label_key],
                ),
                PlotSpec(
                    plot_id="integration_batch_mixing",
                    role="diagnostic",
                    renderer="batch_mixing_heatmap",
                    filename="batch_mixing_heatmap.png",
                    title="Batch mixing heatmap",
                    description="Per-label batch composition after integration.",
                ),
            ]
        )
    return VisualizationRecipe(
        recipe_id="standard-sc-batch-integration-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell integration gallery",
        description=f"Default OmicsClaw integration gallery for method '{summary.get('method', '')}'.",
        plots=plots,
    )


def _gallery_figure_path(output_dir: Path, filename: str) -> Path:
    return Path(output_dir) / "figures" / filename


def _render_umap_batch(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_dimred_utils.plot_umap_clusters(adata, output_dir, cluster_key=context["batch_key"])
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_umap_cluster(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_dimred_utils.plot_umap_clusters(adata, output_dir, cluster_key=context["label_key"])
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_batch_mixing_heatmap(_adata, spec: PlotSpec, context: dict) -> object:
    mix_df = context.get("batch_mixing_df", pd.DataFrame())
    label_key = context.get("label_key") or "label"
    if mix_df.empty:
        return None
    matrix = mix_df.set_index(label_key)
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(matrix, cmap="RdBu_r", center=0.5, annot=True, fmt=".2f", ax=ax)
    ax.set_xlabel("Batch")
    ax.set_ylabel(label_key)
    ax.set_title("Batch composition per cluster")
    fig.tight_layout()
    path = _gallery_figure_path(context["output_dir"], spec.filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _render_integration_metrics_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    metrics_df = context.get("integration_metrics_df", pd.DataFrame())
    if metrics_df.empty:
        return None
    row = metrics_df.iloc[0].to_dict()
    records = []
    for key in ("mean_ilisi", "median_ilisi", "batch_asw", "celltype_asw"):
        value = row.get(key)
        if value is None or pd.isna(value):
            continue
        records.append({"metric": key, "value": float(value)})
    if not records:
        return None
    plot_df = pd.DataFrame(records)
    _metric_colors = {
        "mean_ilisi": "#4c72b0",
        "median_ilisi": "#55a868",
        "batch_asw": "#c44e52",
        "celltype_asw": "#8172b2",
    }
    bar_colors = [_metric_colors.get(m, "#4c72b0") for m in plot_df["metric"]]
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(plot_df["metric"], plot_df["value"], color=bar_colors, edgecolor="white", linewidth=0.8)
    for bar, val in zip(bars, plot_df["value"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{val:.3f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_xlabel("Metric", fontsize=11)
    ax.set_ylabel("Value", fontsize=11)
    ax.set_title("Integration diagnostics", fontsize=13, fontweight="bold")
    plt.xticks(rotation=30, ha="right", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    path = _gallery_figure_path(context["output_dir"], spec.filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


INTEGRATION_GALLERY_RENDERERS = {
    "umap_batch": _render_umap_batch,
    "umap_cluster": _render_umap_cluster,
    "batch_mixing_heatmap": _render_batch_mixing_heatmap,
    "integration_metrics_barplot": _render_integration_metrics_barplot,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_figure_data(output_dir: Path, summary: dict, recipe: VisualizationRecipe, artifacts, context: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    available_files: dict[str, str] = {}
    for key, filename, df in (
        ("integration_summary", "integration_summary.csv", context.get("integration_summary_df")),
        ("batch_sizes", "batch_sizes.csv", context.get("batch_sizes_df")),
        ("cluster_sizes", "cluster_sizes.csv", context.get("cluster_sizes_df")),
        ("batch_mixing_matrix", "batch_mixing_matrix.csv", context.get("batch_mixing_df")),
        ("integration_metrics", "integration_metrics.csv", context.get("integration_metrics_df")),
        ("umap_points", "umap_points.csv", context.get("umap_points_df")),
    ):
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.to_csv(figure_data_dir / filename, index=False)
            available_files[key] = filename
    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": recipe.recipe_id,
        "method": summary.get("method"),
        "embedding_key": summary.get("embedding_key"),
        "batch_key": context.get("batch_key"),
        "label_key": context.get("label_key"),
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


def generate_figures(adata, output_dir: Path, summary: dict, *, gallery_context: dict | None = None) -> list[str]:
    context = gallery_context or {}
    if "output_dir" not in context:
        context["output_dir"] = Path(output_dir)
    recipe = _build_integration_visualization_recipe(adata, summary, context)
    artifacts = render_plot_specs(adata, output_dir, recipe, INTEGRATION_GALLERY_RENDERERS, context=context)
    _export_figure_data(output_dir, summary, recipe, artifacts, context)
    context["recipe"] = recipe
    context["artifacts"] = artifacts
    return [artifact.path for artifact in artifacts if artifact.status == "rendered" and artifact.path]


def export_tables(output_dir: Path, *, gallery_context: dict | None = None) -> list[str]:
    context = gallery_context or {}
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    for filename, key in (
        ("integration_summary.csv", "integration_summary_df"),
        ("batch_sizes.csv", "batch_sizes_df"),
        ("cluster_sizes.csv", "cluster_sizes_df"),
        ("batch_mixing_matrix.csv", "batch_mixing_df"),
        ("integration_metrics.csv", "integration_metrics_df"),
    ):
        df = context.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            path = tables_dir / filename
            df.to_csv(path, index=False)
            exported.append(str(path))
    return exported


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict, *, gallery_context: dict | None = None) -> None:
    context = gallery_context or {}
    requested_method = str(summary.get("requested_method", params.get("method", summary["method"])))
    executed_method = str(summary.get("executed_method", summary["method"]))
    fallback_reason = summary.get("fallback_reason")
    header = generate_report_header(
        title="Single-Cell Batch Integration Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": executed_method,
            "Batches": str(summary["n_batches"]),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Requested method**: {requested_method}",
        f"- **Executed method**: {executed_method}",
        f"- **Batches**: {summary['n_batches']}",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Embedding key**: {summary['embedding_key']}",
        f"- **Batch key**: `{context.get('batch_key', params.get('batch_key'))}`",
        f"- **Label key**: `{context.get('label_key') or 'none'}`",
        f"- **Recommended next step**: `sc-clustering --use-rep {summary['embedding_key']}`",
        "",
        "## Parameters\n",
    ]
    if fallback_reason:
        body_lines.insert(8, f"- **Fallback note**: {fallback_reason}")
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")
    body_lines.extend(
        [
            "",
            "## Output Files\n",
            "- `processed.h5ad` — integrated AnnData object.",
            "- `figures/manifest.json` — standard Python gallery manifest.",
            "- `figure_data/` — figure-ready CSV exports for downstream customization.",
            "- `tables/integration_summary.csv` — run summary table.",
            "- `tables/batch_sizes.csv` — cells per batch.",
            "- `tables/cluster_sizes.csv` — cells per integrated cluster.",
            "- `tables/batch_mixing_matrix.csv` — normalized per-cluster batch composition.",
            "- `tables/integration_metrics.csv` — LISI and ASW diagnostics when available.",
            "- `reproducibility/commands.sh` — reproducible CLI entrypoint.",
            "",
            "## Next Step\n",
            f"- If integration looks acceptable, run `sc-clustering --use-rep {summary['embedding_key']}` on `processed.h5ad`.",
        ]
    )
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer, encoding="utf-8")


def write_reproducibility(output_dir: Path, params: dict, *, demo_mode: bool = False) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--demo' if demo_mode else '--input <input.h5ad>'} "
        f"--output {shlex.quote(str(output_dir))}"
    )
    command += f" --method {shlex.quote(str(params['method']))}"
    command += f" --batch-key {shlex.quote(str(params['batch_key']))}"
    command += f" --seed {params.get('seed', 0)}"
    for key, value in params.items():
        if key in {"method", "batch_key"} or value is None or value == "":
            continue
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                command += f" {flag}"
            continue
        command += f" {flag} {shlex.quote(str(value))}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "seaborn"],
    )


def _render_r_enhanced(output_dir, figure_data_dir, r_enhanced):
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Batch Integration")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default=DEFAULT_METHOD)
    parser.add_argument("--batch-key", default="batch")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-epochs", type=int, default=None)
    parser.add_argument("--no-gpu", action="store_true")
    parser.add_argument("--n-latent", type=int, default=None)
    parser.add_argument("--labels-key", default=None)
    parser.add_argument("--harmony-theta", type=float, default=None)
    parser.add_argument("--bbknn-neighbors-within-batch", type=int, default=None)
    parser.add_argument("--scanorama-knn", type=int, default=None)
    parser.add_argument("--integration-features", type=int, default=None)
    parser.add_argument("--integration-pcs", type=int, default=None)
    parser.add_argument("--simba-n-top-genes", type=int, default=None)
    parser.add_argument("--simba-n-components", type=int, default=None)
    parser.add_argument("--simba-k", type=int, default=None)
    parser.add_argument("--simba-num-workers", type=int, default=None)
    parser.add_argument("--r-enhanced", action="store_true", default=False, help="Generate R-enhanced figures via ggplot2 renderers")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_raw")
        adata.layers["counts"] = adata.X.copy()
        sc.pp.normalize_total(adata)
        sc.pp.log1p(adata)
        adata.raw = adata.copy()
        sc.pp.highly_variable_genes(adata, n_top_genes=2000, layer="counts", flavor="seurat_v3")
        sc.pp.pca(adata)
        try:
            processed_demo, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
            label_key = "louvain" if "louvain" in processed_demo.obs.columns else "leiden" if "leiden" in processed_demo.obs.columns else None
            if label_key:
                aligned = processed_demo.obs.reindex(adata.obs_names)[label_key]
                if aligned.notna().any():
                    adata.obs[label_key] = aligned.astype(str)
        except Exception as exc:
            logger.warning("Demo labels unavailable for scanvi-style validation: %s", exc)
        adata.obs[args.batch_key] = np.random.default_rng(args.seed).choice(["batch1", "batch2"], adata.n_obs)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc_io.smart_load(
            args.input_path,
            suggest_standardize=False,
            skill_name=SKILL_NAME,
            preserve_all=True,
        )
        input_file = args.input_path

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)
    effective_params = dict(METHOD_PARAM_DEFAULTS[method])
    effective_params["method"] = method
    effective_params["batch_key"] = args.batch_key
    for key in METHOD_PARAM_KEYS.get(method, ()):
        value = getattr(args, key, None)
        if value is not None:
            effective_params[key] = value
    if method in {"scvi", "scanvi"} and args.no_gpu:
        effective_params["no_gpu"] = True
    apply_preflight(
        preflight_sc_batch_integration(
            adata,
            method=method,
            batch_key=args.batch_key,
            labels_key=effective_params.get("labels_key"),
            effective_params=effective_params,
            source_path=input_file,
        ),
        logger,
        demo_mode=args.demo,
    )
    cfg = METHOD_REGISTRY[method]
    check_data_requirements(adata, cfg)
    adata = _api.integrate(
        adata, method=method, batch_key=args.batch_key, random_state=args.seed,
        harmony_theta=float(effective_params.get("harmony_theta", 2.0)),
        n_pcs=int(effective_params.get("integration_pcs", 50)),
        n_epochs=effective_params.get("n_epochs"), n_latent=int(effective_params.get("n_latent", 30)),
        use_gpu=not bool(effective_params.get("no_gpu", False)), labels_key=effective_params.get("labels_key"),
        bbknn_neighbors_within_batch=int(effective_params.get("bbknn_neighbors_within_batch", 3)),
        scanorama_knn=int(effective_params.get("scanorama_knn", 20)),
        integration_features=int(effective_params.get("integration_features", 2000)),
        integration_pcs=int(effective_params.get("integration_pcs", 30)),
        simba_n_top_genes=int(effective_params.get("simba_n_top_genes", 3000)),
        simba_n_components=int(effective_params.get("simba_n_components", 15)),
        simba_k=int(effective_params.get("simba_k", 15)),
        simba_num_workers=int(effective_params.get("simba_num_workers", 4)),
    )
    summary = _api.run_info(adata, keep=False)["summary"]
    if method != "bbknn":
        sc.pp.neighbors(adata, use_rep=summary["embedding_key"])
    legacy_umap = adata.uns.pop("_omicsclaw_legacy_integration_umap", None)
    if legacy_umap is not None:
        adata.obsm["X_umap"] = legacy_umap
    else:
        sc.tl.umap(adata, random_state=args.seed)

    summary.setdefault("requested_method", method)
    summary.setdefault("executed_method", summary.get("method", method))
    summary.setdefault("fallback_used", summary["requested_method"] != summary["executed_method"])
    summary["n_cells"] = int(adata.n_obs)
    summary["recommended_next_skill"] = "sc-clustering"
    summary["recommended_use_rep"] = summary.get("embedding_key")
    params = {
        **effective_params,
        "seed": args.seed,
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "counts_layer": "counts" if "counts" in adata.layers else None,
        "raw_available": adata.raw is not None,
    }
    if summary.get("fallback_reason"):
        params["fallback_reason"] = summary["fallback_reason"]

    gallery_context = _prepare_integration_gallery_context(adata, summary, params, output_dir)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, demo_mode=args.demo)

    store_analysis_metadata(adata, SKILL_NAME, summary["executed_method"], params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "method": summary["executed_method"],
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "fallback_used": bool(summary.get("fallback_used")),
        "fallback_reason": summary.get("fallback_reason"),
        "params": params,
        **summary,
        "visualization": {
            "recipe_id": "standard-sc-batch-integration-gallery",
            "batch_column": gallery_context.get("batch_key"),
            "label_column": gallery_context.get("label_key"),
            "embedding_key": summary.get("embedding_key"),
            "umap_key": "X_umap" if "X_umap" in adata.obsm else None,
            "available_figure_data": gallery_context.get("figure_data_files", {}),
        },
        "next_step": {
            "skill": "sc-clustering",
            "use_rep": summary.get("embedding_key"),
        },
    }
    result_data["next_steps"] = [
        {"skill": "sc-clustering", "reason": "Identify cell clusters on integrated embedding", "priority": "recommended"},
    ]
    result_data["preprocessing_state_after"] = "normalized"
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"Integration complete: requested={summary['requested_method']}, "
        f"executed={summary['executed_method']} on {summary['n_batches']} batches"
    )

    # --- Next-step guidance ---
    print()
    print(">> Next step: Run sc-clustering on the integrated object")
    print(f"  python skills/singlecell/scrna/sc-clustering/sc_cluster.py --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
