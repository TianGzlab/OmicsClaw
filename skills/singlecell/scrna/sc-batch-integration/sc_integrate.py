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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import ensure_pca, store_analysis_metadata
from skills.singlecell._lib import dimred as sc_dimred_utils
from skills.singlecell._lib import integration as sc_integration_utils
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice, check_data_requirements

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-batch-integration"
SKILL_VERSION = "0.4.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-batch-integration/sc_integrate.py"

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
}

DEFAULT_METHOD = "harmony"


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


def write_standard_run_artifacts(output_dir: Path, result_payload: dict, summary: dict) -> None:
    notebook_path = None
    try:
        from omicsclaw.common.notebook_export import write_analysis_notebook

        notebook_path = write_analysis_notebook(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Batch integration for multi-sample scRNA-seq datasets.",
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
            description="Batch integration for multi-sample scRNA-seq datasets.",
            result_payload=result_payload,
            preferred_method=summary.get("method", DEFAULT_METHOD),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)


def integrate_harmony(adata, batch_key="batch", **kwargs):
    adata = sc_integration_utils.run_harmony_integration(
        adata,
        batch_key=batch_key,
        theta=float(kwargs.get("theta", 2.0)),
        n_pcs=int(kwargs.get("n_pcs", 50)),
    )
    sc.pp.neighbors(adata, use_rep="X_harmony")
    sc.tl.umap(adata)
    return {"method": "harmony", "embedding_key": "X_harmony", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_scvi(adata, batch_key="batch", n_epochs=None, use_gpu=True, **kwargs):
    adata = sc_integration_utils.run_scvi_integration(
        adata,
        batch_key=batch_key,
        max_epochs=n_epochs or 400,
        use_gpu=use_gpu,
    )
    sc.pp.neighbors(adata, use_rep="X_scvi")
    sc.tl.umap(adata)
    return {"method": "scvi", "embedding_key": "X_scvi", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_scanvi(adata, batch_key="batch", n_epochs=None, use_gpu=True, **kwargs):
    labels_key = "cell_type" if "cell_type" in adata.obs.columns else "leiden" if "leiden" in adata.obs.columns else None
    if labels_key is None:
        logger.warning("scANVI requires labels; falling back to scVI latent integration")
        return integrate_scvi(adata, batch_key=batch_key, n_epochs=n_epochs, use_gpu=use_gpu, **kwargs)
    adata = sc_integration_utils.run_scanvi_integration(
        adata,
        batch_key=batch_key,
        labels_key=labels_key,
        max_epochs=n_epochs or 200,
        use_gpu=use_gpu,
    )
    sc.pp.neighbors(adata, use_rep="X_scanvi")
    sc.tl.umap(adata)
    return {"method": "scanvi", "embedding_key": "X_scanvi", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_bbknn(adata, batch_key="batch", **kwargs):
    import bbknn

    ensure_pca(adata)
    logger.info("Running BBKNN on %d batches", adata.obs[batch_key].nunique())
    bbknn.bbknn(adata, batch_key=batch_key)
    sc.tl.umap(adata)
    return {"method": "bbknn", "embedding_key": "X_pca", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_scanorama(adata, batch_key="batch", **kwargs):
    import scanorama

    logger.info("Running Scanorama on %d batches", adata.obs[batch_key].nunique())
    batches = []
    for batch in adata.obs[batch_key].unique():
        batches.append(adata[adata.obs[batch_key] == batch].copy())
    corrected = scanorama.correct_scanpy(batches, return_dimred=True)
    adata.obsm["X_scanorama"] = np.concatenate(corrected[1])
    sc.pp.neighbors(adata, use_rep="X_scanorama")
    sc.tl.umap(adata)
    return {"method": "scanorama", "embedding_key": "X_scanorama", "n_batches": int(adata.obs[batch_key].nunique())}


def integrate_r_method(adata, *, method: str, batch_key: str):
    raise RuntimeError(
        f"R-backed integration method '{method}' is declared but not bundled in the current wrapper. "
        "Use harmony, scvi, scanvi, bbknn, or scanorama in this build."
    )


_METHOD_DISPATCH = {
    "harmony": integrate_harmony,
    "scvi": integrate_scvi,
    "scanvi": integrate_scanvi,
    "bbknn": integrate_bbknn,
    "scanorama": integrate_scanorama,
}


def _ensure_leiden_labels(adata, embedding_key: str, cluster_key: str = "leiden") -> None:
    if cluster_key in adata.obs.columns:
        return
    if embedding_key in adata.obsm:
        sc.pp.neighbors(adata, use_rep=embedding_key)
    elif "neighbors" not in adata.uns:
        ensure_pca(adata)
        sc.pp.neighbors(adata)
    sc.tl.leiden(adata, key_added=cluster_key)


def _build_batch_sizes_table(adata, batch_key: str) -> pd.DataFrame:
    return (
        adata.obs[batch_key]
        .astype(str)
        .value_counts()
        .rename_axis(batch_key)
        .reset_index(name="n_cells")
        .sort_values("n_cells", ascending=False)
        .reset_index(drop=True)
    )


def _build_cluster_sizes_table(adata, label_key: str) -> pd.DataFrame:
    return (
        adata.obs[label_key]
        .astype(str)
        .value_counts()
        .rename_axis(label_key)
        .reset_index(name="n_cells")
        .sort_values("n_cells", ascending=False)
        .reset_index(drop=True)
    )


def _build_batch_mixing_table(adata, batch_key: str, label_key: str) -> pd.DataFrame:
    mix = pd.crosstab(
        adata.obs[label_key].astype(str),
        adata.obs[batch_key].astype(str),
        normalize="index",
    )
    mix.index.name = label_key
    return mix.reset_index()


def _build_umap_points_table(adata, batch_key: str, label_key: str) -> pd.DataFrame:
    if "X_umap" not in adata.obsm:
        return pd.DataFrame(columns=["cell_id", "UMAP1", "UMAP2", batch_key, label_key])
    coords = np.asarray(adata.obsm["X_umap"])
    return pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "UMAP1": coords[:, 0],
            "UMAP2": coords[:, 1],
            batch_key: adata.obs[batch_key].astype(str).to_numpy(),
            label_key: adata.obs[label_key].astype(str).to_numpy(),
        }
    )


def _build_integration_metrics_table(adata, batch_key: str, label_key: str, embedding_key: str) -> pd.DataFrame:
    metrics = {
        "embedding_key": embedding_key,
        "n_batches": int(adata.obs[batch_key].nunique()),
        "n_labels": int(adata.obs[label_key].nunique()),
    }
    try:
        lisi_df = sc_integration_utils.compute_lisi_scores(
            adata,
            batch_key=batch_key,
            label_key=label_key,
            use_rep=embedding_key,
            verbose=False,
        )
        adata.obs["ilisi"] = lisi_df["ilisi"].values
        metrics["mean_ilisi"] = float(lisi_df["ilisi"].mean())
        metrics["median_ilisi"] = float(lisi_df["ilisi"].median())
        if "clisi" in lisi_df.columns:
            adata.obs["clisi"] = lisi_df["clisi"].values
            metrics["mean_clisi"] = float(lisi_df["clisi"].mean())
            metrics["median_clisi"] = float(lisi_df["clisi"].median())
    except Exception as exc:
        logger.warning("LISI diagnostics unavailable: %s", exc)

    try:
        asw = sc_integration_utils.compute_asw_scores(
            adata,
            batch_key=batch_key,
            label_key=label_key,
            use_rep=embedding_key,
            verbose=False,
        )
        metrics["batch_asw"] = float(asw["batch_asw"])
        metrics["celltype_asw"] = float(asw["celltype_asw"])
    except Exception as exc:
        logger.warning("ASW diagnostics unavailable: %s", exc)

    return pd.DataFrame([metrics])


def _prepare_integration_gallery_context(adata, summary: dict, params: dict, output_dir: Path) -> dict:
    batch_key = params["batch_key"]
    label_key = "leiden"
    _ensure_leiden_labels(adata, summary["embedding_key"], cluster_key=label_key)
    return {
        "output_dir": Path(output_dir),
        "batch_key": batch_key,
        "label_key": label_key,
        "batch_sizes_df": _build_batch_sizes_table(adata, batch_key),
        "cluster_sizes_df": _build_cluster_sizes_table(adata, label_key),
        "batch_mixing_df": _build_batch_mixing_table(adata, batch_key, label_key),
        "umap_points_df": _build_umap_points_table(adata, batch_key, label_key),
        "integration_metrics_df": _build_integration_metrics_table(adata, batch_key, label_key, summary["embedding_key"]),
        "integration_summary_df": pd.DataFrame(
            [
                {"metric": "method", "value": summary.get("method")},
                {"metric": "embedding_key", "value": summary.get("embedding_key")},
                {"metric": "n_batches", "value": summary.get("n_batches")},
                {"metric": "n_cells", "value": summary.get("n_cells")},
                {"metric": "batch_key", "value": batch_key},
                {"metric": "label_key", "value": label_key},
            ]
        ),
    }


def _build_integration_visualization_recipe(_adata, summary: dict, context: dict) -> VisualizationRecipe:
    batch_key = context["batch_key"]
    label_key = context["label_key"]
    return VisualizationRecipe(
        recipe_id="standard-sc-batch-integration-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell integration gallery",
        description=f"Default OmicsClaw integration gallery for method '{summary.get('method', '')}'.",
        plots=[
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
                plot_id="integration_umap_cluster",
                role="overview",
                renderer="umap_cluster",
                filename=f"umap_{label_key}.png",
                title="Cluster UMAP",
                description="UMAP colored by Leiden labels after integration.",
                required_obsm=["X_umap"],
                required_obs=[label_key],
            ),
            PlotSpec(
                plot_id="integration_batch_mixing",
                role="diagnostic",
                renderer="batch_mixing_heatmap",
                filename="batch_mixing_heatmap.png",
                title="Batch mixing heatmap",
                description="Per-cluster batch composition after integration.",
            ),
            PlotSpec(
                plot_id="integration_metrics",
                role="supporting",
                renderer="integration_metrics_barplot",
                filename="integration_metrics.png",
                title="Integration diagnostics",
                description="Summary diagnostics including LISI and ASW when available.",
            ),
        ],
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
    label_key = context["label_key"]
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
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(plot_df["metric"], plot_df["value"], color="#4c72b0")
    ax.set_xlabel("Metric")
    ax.set_ylabel("Value")
    ax.set_title("Integration diagnostics")
    plt.xticks(rotation=30, ha="right")
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
    header = generate_report_header(
        title="Single-Cell Batch Integration Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Batches": str(summary["n_batches"]),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Batches**: {summary['n_batches']}",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Embedding key**: {summary['embedding_key']}",
        f"- **Batch key**: `{context.get('batch_key', params.get('batch_key'))}`",
        f"- **Label key**: `{context.get('label_key', 'leiden')}`",
        "",
        "## Parameters\n",
    ]
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
    for key, value in params.items():
        command += f" --{key.replace('_', '-')} {shlex.quote(str(value))}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "seaborn"],
    )


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Batch Integration")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default=DEFAULT_METHOD)
    parser.add_argument("--batch-key", default="batch")
    parser.add_argument("--n-epochs", type=int, default=None)
    parser.add_argument("--no-gpu", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_raw")
        sc.pp.normalize_total(adata)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, n_top_genes=2000)
        sc.pp.pca(adata)
        adata.obs[args.batch_key] = np.random.choice(["batch1", "batch2"], adata.n_obs)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)
    cfg = METHOD_REGISTRY[method]
    check_data_requirements(adata, cfg)

    kwargs = {"batch_key": args.batch_key}
    if cfg.supports_gpu:
        kwargs["use_gpu"] = not args.no_gpu
    if args.n_epochs is not None and "torch" in cfg.dependencies:
        kwargs["n_epochs"] = args.n_epochs

    if method in {"fastmnn", "seurat_cca", "seurat_rpca"}:
        adata, summary = integrate_r_method(adata, method=method, batch_key=args.batch_key)
    else:
        summary = _METHOD_DISPATCH[method](adata, **kwargs)

    summary["n_cells"] = int(adata.n_obs)
    params = {"method": method, "batch_key": args.batch_key}
    if args.n_epochs is not None:
        params["n_epochs"] = args.n_epochs

    gallery_context = _prepare_integration_gallery_context(adata, summary, params, output_dir)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, demo_mode=args.demo)

    store_analysis_metadata(adata, SKILL_NAME, method, params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "method": method,
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
    print(f"Integration complete: {summary['method']} on {summary['n_batches']} batches")


if __name__ == "__main__":
    main()
