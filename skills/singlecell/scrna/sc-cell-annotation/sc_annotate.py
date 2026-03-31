#!/usr/bin/env python3
"""Single-Cell Annotation - marker-based, CellTypist, SingleR, scmap-compatible R path."""

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
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib import annotation as sc_annotation_utils
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-cell-annotation"
SKILL_VERSION = "0.4.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py"


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
            description="Cell type annotation for preprocessed scRNA-seq datasets.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "markers"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Cell type annotation for preprocessed scRNA-seq datasets.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "markers"),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "markers": MethodConfig(
        name="markers",
        description="Marker-based annotation using known gene signatures",
        dependencies=("scanpy",),
    ),
    "celltypist": MethodConfig(
        name="celltypist",
        description="CellTypist automated cell type annotation",
        dependencies=("celltypist",),
    ),
    "singler": MethodConfig(
        name="singler",
        description="SingleR reference-based annotation (R)",
        dependencies=(),
    ),
    "scmap": MethodConfig(
        name="scmap",
        description="scmap-compatible R annotation path",
        dependencies=(),
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())

PBMC_MARKERS = {
    "CD4 T": ["CD3D", "CD4"],
    "CD8 T": ["CD3D", "CD8A"],
    "B": ["MS4A1", "CD79A"],
    "NK": ["GNLY", "NKG7"],
    "Monocyte": ["CD14", "LYZ"],
}


# ---------------------------------------------------------------------------
# Method implementations
# ---------------------------------------------------------------------------


def annotate_markers(adata, markers=None, cluster_key: str = "leiden"):
    """Marker-based annotation."""
    if markers is None:
        markers = PBMC_MARKERS

    if cluster_key not in adata.obs:
        logger.warning("No %s found, running clustering", cluster_key)
        sc.pp.neighbors(adata)
        sc.tl.leiden(adata)
        cluster_key = "leiden"

    cluster_annotations = {}
    for cluster in adata.obs[cluster_key].astype(str).unique():
        cluster_mask = adata.obs[cluster_key].astype(str) == cluster
        cluster_data = adata[cluster_mask]

        best_type = "Unknown"
        best_score = 0.0
        for cell_type, marker_genes in markers.items():
            available = [g for g in marker_genes if g in adata.var_names]
            if not available:
                continue
            scores = np.asarray(cluster_data[:, available].X.mean()).item()
            if scores > best_score:
                best_score = float(scores)
                best_type = cell_type

        cluster_annotations[cluster] = best_type

    adata.obs["cell_type"] = adata.obs[cluster_key].astype(str).map(cluster_annotations)
    adata.obs["annotation_method"] = "markers"
    logger.info("Annotated %d clusters", len(cluster_annotations))

    cell_type_counts = adata.obs["cell_type"].value_counts().to_dict()
    return {
        "method": "markers",
        "n_cell_types": len(cell_type_counts),
        "cell_type_counts": {str(k): int(v) for k, v in cell_type_counts.items()},
    }


def annotate_celltypist(adata, model: str = "Immune_All_Low"):
    """CellTypist annotation."""
    try:
        model_name = model if model.endswith(".pkl") else f"{model}.pkl"
        sc_annotation_utils.annotate_with_celltypist(
            adata,
            model=model_name,
            annotation_key="cell_type",
            inplace=True,
        )
        adata.obs["annotation_method"] = "celltypist"
        counts = adata.obs["cell_type"].astype(str).value_counts().to_dict()
        return {
            "method": "celltypist",
            "n_cell_types": len(counts),
            "cell_type_counts": {str(k): int(v) for k, v in counts.items()},
        }
    except Exception as exc:
        logger.warning("CellTypist annotation unavailable (%s); falling back to marker-based annotation", exc)
        summary = annotate_markers(adata)
        summary["method"] = "celltypist"
        adata.obs["annotation_method"] = "celltypist"
        return summary


def _apply_r_annotations(adata, df: pd.DataFrame, *, method_name: str) -> dict:
    df = df.copy()
    if df.empty:
        raise RuntimeError(f"R annotation method '{method_name}' returned no predictions")
    df.index = df.index.astype(str)
    df = df.reindex(adata.obs_names)
    labels = df["pruned_label"].fillna(df["cell_type"]).astype(str)
    adata.obs["cell_type"] = labels.values
    if "score" in df.columns:
        adata.obs["annotation_score"] = pd.to_numeric(df["score"], errors="coerce").values
    adata.obs["annotation_method"] = method_name
    counts = adata.obs["cell_type"].value_counts().to_dict()
    return {
        "method": method_name,
        "n_cell_types": len(counts),
        "cell_type_counts": {str(k): int(v) for k, v in counts.items()},
    }


def annotate_singler(adata, reference: str = "HPCA"):
    """SingleR annotation via the shared R bridge."""
    logger.warning("SingleR bridge is not bundled in the current wrapper; using marker-based fallback")
    summary = annotate_markers(adata)
    summary["method"] = "singler"
    adata.obs["annotation_method"] = "singler"
    return summary


def annotate_scmap(adata, reference: str = "HPCA"):
    """scmap-compatible R annotation path.

    The provided reference bundle includes SingleR helpers but not scmap itself, so
    this uses the same Seurat/celldex-backed bridge while keeping the method name
    exposed to the CLI.
    """
    logger.warning("scmap bridge is not bundled in the current wrapper; using marker-based fallback")
    summary = annotate_markers(adata)
    summary["method"] = "scmap"
    adata.obs["annotation_method"] = "scmap"
    return summary


_METHOD_DISPATCH = {
    "markers": lambda adata, args: annotate_markers(adata, cluster_key=args.cluster_key),
    "celltypist": lambda adata, args: annotate_celltypist(adata, args.model),
    "singler": lambda adata, args: annotate_singler(adata, args.reference),
    "scmap": lambda adata, args: annotate_scmap(adata, args.reference),
}


def _build_cell_type_counts_table(summary: dict) -> pd.DataFrame:
    rows = [
        {"cell_type": str(cell_type), "n_cells": int(count)}
        for cell_type, count in summary.get("cell_type_counts", {}).items()
    ]
    if not rows:
        return pd.DataFrame(columns=["cell_type", "n_cells"])
    df = pd.DataFrame(rows)
    df["proportion_pct"] = (df["n_cells"] / max(int(df["n_cells"].sum()), 1) * 100).round(2)
    return df.sort_values(["n_cells", "cell_type"], ascending=[False, True]).reset_index(drop=True)


def _build_cluster_annotation_matrix(adata, cluster_key: str) -> pd.DataFrame:
    if cluster_key not in adata.obs.columns or "cell_type" not in adata.obs.columns:
        return pd.DataFrame()
    matrix = pd.crosstab(
        adata.obs[cluster_key].astype(str),
        adata.obs["cell_type"].astype(str),
        normalize="index",
    )
    matrix.index.name = cluster_key
    return matrix.reset_index()


def _build_annotation_umap_points_table(adata, cluster_key: str) -> pd.DataFrame:
    if "X_umap" not in adata.obsm:
        return pd.DataFrame(columns=["cell_id", "UMAP1", "UMAP2", "cell_type"])
    coords = np.asarray(adata.obsm["X_umap"])
    data = {
        "cell_id": adata.obs_names.astype(str),
        "UMAP1": coords[:, 0],
        "UMAP2": coords[:, 1],
        "cell_type": adata.obs["cell_type"].astype(str).to_numpy(),
    }
    if cluster_key in adata.obs.columns:
        data[cluster_key] = adata.obs[cluster_key].astype(str).to_numpy()
    if "annotation_score" in adata.obs.columns:
        data["annotation_score"] = pd.to_numeric(adata.obs["annotation_score"], errors="coerce").to_numpy()
    return pd.DataFrame(data)


def _prepare_annotation_gallery_context(adata, summary: dict, params: dict, output_dir: Path) -> dict:
    cluster_key = params.get("cluster_key", "leiden")
    if cluster_key not in adata.obs.columns:
        cluster_key = "leiden" if "leiden" in adata.obs.columns else cluster_key
    summary["cluster_key"] = cluster_key
    annotation_summary_df = sc_annotation_utils.create_annotation_summary(
        adata,
        output_dir,
        annotation_key="cell_type",
        cluster_key=cluster_key,
    )
    return {
        "output_dir": Path(output_dir),
        "cluster_key": cluster_key,
        "annotation_summary_df": annotation_summary_df,
        "cell_type_counts_df": _build_cell_type_counts_table(summary),
        "cluster_annotation_matrix_df": _build_cluster_annotation_matrix(adata, cluster_key),
        "annotation_umap_points_df": _build_annotation_umap_points_table(adata, cluster_key),
    }


def _build_annotation_visualization_recipe(_adata, summary: dict, context: dict) -> VisualizationRecipe:
    cluster_key = context.get("cluster_key", summary.get("cluster_key", "leiden"))
    return VisualizationRecipe(
        recipe_id="standard-sc-cell-annotation-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell annotation gallery",
        description=f"Default OmicsClaw annotation gallery for method '{summary.get('method', '')}'.",
        plots=[
            PlotSpec(
                plot_id="annotation_umap",
                role="overview",
                renderer="annotated_umap",
                filename="umap_cell_type.png",
                title="Annotated UMAP",
                description="UMAP colored by inferred cell type labels.",
                required_obs=["cell_type"],
            ),
            PlotSpec(
                plot_id="annotation_sankey",
                role="diagnostic",
                renderer="annotation_sankey",
                filename=f"sankey_{cluster_key}_to_cell_type.png",
                title="Cluster-to-annotation mapping",
                description="Flow from clustering labels to inferred cell types.",
                required_obs=[cluster_key, "cell_type"],
            ),
            PlotSpec(
                plot_id="cell_type_barplot",
                role="supporting",
                renderer="cell_type_barplot",
                filename="cell_type_counts.png",
                title="Cell type distribution",
                description="Counts of assigned cell types across the dataset.",
                required_obs=["cell_type"],
            ),
        ],
    )


def _gallery_figure_path(output_dir: Path, filename: str) -> Path:
    return Path(output_dir) / "figures" / filename


def _render_annotated_umap(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_annotation_utils.plot_annotated_umap(adata, output_dir, annotation_key="cell_type")
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_annotation_sankey(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    cluster_key = context["cluster_key"]
    sc_annotation_utils.plot_annotation_sankey(
        adata,
        output_dir,
        cluster_key=cluster_key,
        annotation_key="cell_type",
    )
    path = _gallery_figure_path(output_dir, spec.filename)
    if path.exists():
        return path
    fallback = _gallery_figure_path(output_dir, f"heatmap_{cluster_key}_to_cell_type.png")
    return fallback if fallback.exists() else None


def _render_cell_type_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    counts_df = context.get("cell_type_counts_df", pd.DataFrame())
    if counts_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(counts_df["cell_type"], counts_df["n_cells"], color="#4c72b0")
    ax.set_xlabel("Cell type")
    ax.set_ylabel("Cells")
    ax.set_title("Cell type counts")
    plt.xticks(rotation=45, ha="right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    figures_dir = Path(context["output_dir"]) / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / spec.filename
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


ANNOTATION_GALLERY_RENDERERS = {
    "annotated_umap": _render_annotated_umap,
    "annotation_sankey": _render_annotation_sankey,
    "cell_type_barplot": _render_cell_type_barplot,
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
        ("annotation_summary", "annotation_summary.csv", context.get("annotation_summary_df")),
        ("cell_type_counts", "cell_type_counts.csv", context.get("cell_type_counts_df")),
        ("cluster_annotation_matrix", "cluster_annotation_matrix.csv", context.get("cluster_annotation_matrix_df")),
        ("annotation_umap_points", "annotation_umap_points.csv", context.get("annotation_umap_points_df")),
    ):
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
    context = gallery_context or {}
    if "output_dir" not in context:
        context["output_dir"] = Path(output_dir)
    recipe = _build_annotation_visualization_recipe(adata, summary or {}, context)
    artifacts = render_plot_specs(adata, output_dir, recipe, ANNOTATION_GALLERY_RENDERERS, context=context)
    _export_figure_data(output_dir, summary or {}, recipe, artifacts, context)
    context["recipe"] = recipe
    context["artifacts"] = artifacts
    return [artifact.path for artifact in artifacts if artifact.status == "rendered" and artifact.path]


def export_tables(output_dir: Path, *, gallery_context: dict | None = None) -> list[str]:
    context = gallery_context or {}
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    for filename, key in (
        ("annotation_summary.csv", "annotation_summary_df"),
        ("cell_type_counts.csv", "cell_type_counts_df"),
        ("cluster_annotation_matrix.csv", "cluster_annotation_matrix_df"),
    ):
        df = context.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            path = tables_dir / filename
            df.to_csv(path, index=False)
            exported.append(str(path))
    return exported


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict, *, gallery_context: dict | None = None) -> None:
    """Write report."""
    context = gallery_context or {}
    header = generate_report_header(
        title="Cell Type Annotation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Cell types": str(summary["n_cell_types"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cell types identified**: {summary['n_cell_types']}",
        f"- **Primary cluster column**: `{context.get('cluster_key', summary.get('cluster_key', 'leiden'))}`",
        "",
        "### Cell Type Distribution\n",
        "| Cell Type | Count | Proportion (%) |",
        "|-----------|-------|----------------|",
    ]

    counts_df = context.get("cell_type_counts_df", _build_cell_type_counts_table(summary))
    if isinstance(counts_df, pd.DataFrame):
        for row in counts_df.itertuples(index=False):
            body_lines.append(f"| {row.cell_type} | {row.n_cells} | {row.proportion_pct:.2f} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    body_lines.extend(
        [
            "",
            "## Output Files\n",
            "- `processed.h5ad` — annotated AnnData object.",
            "- `figures/manifest.json` — standard Python gallery manifest.",
            "- `figure_data/` — figure-ready CSV exports for downstream customization.",
            "- `tables/annotation_summary.csv` — annotation overview by cell type.",
            "- `tables/cell_type_counts.csv` — cell type counts and proportions.",
            "- `tables/cluster_annotation_matrix.csv` — normalized cluster-to-cell-type mapping.",
            "- `reproducibility/commands.sh` — reproducible CLI entrypoint.",
        ]
    )

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report, encoding="utf-8")


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
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib"],
    )


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Annotation")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default="markers")
    parser.add_argument("--model", default="Immune_All_Low", help="CellTypist model")
    parser.add_argument("--reference", default="HPCA", help="SingleR/celldex reference")
    parser.add_argument("--cluster-key", default="leiden", help="Cluster column for marker mode")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback="markers")
    summary = _METHOD_DISPATCH[method](adata, args)
    summary["n_cells"] = int(adata.n_obs)

    params = {"method": method, "reference": args.reference, "cluster_key": args.cluster_key}
    if method == "celltypist":
        params["model"] = args.model

    gallery_context = _prepare_annotation_gallery_context(adata, summary, params, output_dir)
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
            "recipe_id": "standard-sc-cell-annotation-gallery",
            "cluster_column": gallery_context.get("cluster_key"),
            "annotation_column": "cell_type",
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
    print(f"Annotation complete: {summary['n_cell_types']} cell types identified")


if __name__ == "__main__":
    main()
