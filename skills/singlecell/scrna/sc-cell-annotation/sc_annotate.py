#!/usr/bin/env python3
"""Single-Cell Annotation - marker-based, CellTypist, SingleR, scmap-compatible R path."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import tempfile
import sys
from pathlib import Path

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.runtime_env import ensure_runtime_cache_dirs as _ensure_runtime_cache_dirs
_ensure_runtime_cache_dirs()

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import scanpy as sc

from skills._sdk.checksums import sha256_file
from skills._sdk.notebook import load_skill
from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import (
    load_result_json,
    write_result_json,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    get_matrix_contract,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib import annotation as sc_annotation_utils
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import (
    apply_preflight,
    preflight_sc_cell_annotation,
)
from skills.singlecell._lib.viz import (
    plot_cell_type_count_barplot,
    plot_cluster_annotation_heatmap,
    plot_embedding_categorical,
    plot_embedding_comparison,
    plot_embedding_continuous,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-cell-annotation"
SKILL_VERSION = "0.6.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py"

# R Enhanced renderers for this skill.
# Key   = renderer name registered in viz/r/registry.R R_PLOT_REGISTRY
# Value = output filename (written to figures/r_enhanced/)
R_ENHANCED_PLOTS: dict[str, str] = {
    "plot_embedding_discrete": "r_embedding_discrete.png",
    "plot_embedding_feature": "r_embedding_feature.png",
    "plot_cell_barplot": "r_cell_barplot.png",
    "plot_cell_proportion": "r_cell_proportion.png",
    "plot_cell_sankey": "r_cell_sankey.png",
}


def _render_r_enhanced(
    output_dir: Path,
    figure_data_dir: Path,
    r_enhanced: bool,
) -> list[str]:
    """Run R Enhanced rendering pass. Always called after Python figures are complete."""
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths: list[str] = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


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



METHOD_REGISTRY: dict[str, MethodConfig] = {
    "manual": MethodConfig(
        name="manual",
        description="Manual relabeling from a user-supplied cluster-to-cell-type mapping",
        dependencies=(),
    ),
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
    "popv": MethodConfig(
        name="popv",
        description="Reference-mapped consensus annotation (PopV)",
        dependencies=("scanpy",),
    ),
    "knnpredict": MethodConfig(
        name="knnpredict",
        description="Lightweight AnnData-first reference mapping inspired by SCOP KNNPredict",
        dependencies=("scanpy",),
    ),
    "singler": MethodConfig(
        name="singler",
        description="SingleR reference-based annotation (R)",
        dependencies=(),
    ),
    "scmap": MethodConfig(
        name="scmap",
        description="scmap cluster projection (R)",
        dependencies=(),
    ),
    "scsa": MethodConfig(
        name="scsa",
        description="SCSA marker-database annotation via Fisher exact test scoring",
        dependencies=("scanpy",),
    ),
}

SUPPORTED_METHODS = tuple(METHOD_REGISTRY.keys())

def _candidate_cluster_keys(adata) -> list[str]:
    matrix_contract = get_matrix_contract(adata)
    candidates: list[str] = []
    primary = matrix_contract.get("primary_cluster_key")
    if primary and primary in adata.obs.columns:
        candidates.append(str(primary))
    for key in ("leiden", "louvain", "seurat_clusters", "cluster", "cell_type"):
        if key in adata.obs.columns and key not in candidates:
            candidates.append(key)
    return candidates


def _resolve_cluster_key(adata, cluster_key: str | None) -> str | None:
    if cluster_key and cluster_key in adata.obs.columns:
        return cluster_key
    candidates = _candidate_cluster_keys(adata)
    return candidates[0] if candidates else None


def _candidate_embedding_keys(adata) -> list[str]:
    preferred = [key for key in ("X_umap", "X_tsne", "X_pca", "X_scvi", "X_scanvi", "X_harmony", "X_scanorama") if key in adata.obsm]
    if preferred:
        return preferred
    return [str(key) for key in adata.obsm.keys() if str(key).startswith("X_")]


def _build_annotation_embedding_points_table(adata, cluster_key: str | None, embedding_key: str | None) -> pd.DataFrame:
    if embedding_key is None or embedding_key not in adata.obsm:
        return pd.DataFrame(columns=["cell_id", "dim1", "dim2", "cell_type"])
    coords = np.asarray(adata.obsm[embedding_key])
    data = {
        "cell_id": adata.obs_names.astype(str),
        "dim1": coords[:, 0],
        "dim2": coords[:, 1],
        "cell_type": adata.obs["cell_type"].astype(str).to_numpy(),
    }
    if cluster_key and cluster_key in adata.obs.columns:
        data[cluster_key] = adata.obs[cluster_key].astype(str).to_numpy()
    if "annotation_score" in adata.obs.columns:
        data["annotation_score"] = pd.to_numeric(adata.obs["annotation_score"], errors="coerce").to_numpy()
    return pd.DataFrame(data)


def _prepare_annotation_gallery_context(adata, summary: dict, params: dict, output_dir: Path, api) -> dict:
    cluster_key = params.get("cluster_key")
    if cluster_key not in adata.obs.columns:
        cluster_key = _resolve_cluster_key(adata, cluster_key)
    summary["cluster_key"] = cluster_key
    annotation_summary_df = sc_annotation_utils.create_annotation_summary(
        adata,
        output_dir,
        annotation_key="cell_type",
        cluster_key=cluster_key or "leiden",
    )
    embedding_candidates = _candidate_embedding_keys(adata)
    embedding_key = embedding_candidates[0] if embedding_candidates else None
    context = {
        "output_dir": Path(output_dir),
        "cluster_key": cluster_key,
        "embedding_key": embedding_key,
        "annotation_summary_df": annotation_summary_df,
        "cell_type_counts_df": api.annotation_table(adata, key="cell_type"),
        "cluster_annotation_matrix_df": api.cluster_annotation_matrix(adata, cluster_key=cluster_key),
        "annotation_embedding_points_df": _build_annotation_embedding_points_table(adata, cluster_key, embedding_key),
    }
    if "popv_predictions" in adata.uns:
        context["popv_predictions_df"] = adata.uns["popv_predictions"].copy()
    return context


def _build_annotation_visualization_recipe(_adata, summary: dict, context: dict) -> VisualizationRecipe:
    cluster_key = context.get("cluster_key", summary.get("cluster_key", "leiden"))
    return VisualizationRecipe(
        recipe_id="standard-sc-cell-annotation-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell annotation gallery",
        description=f"Default OmicsClaw annotation gallery for method '{summary.get('method', '')}'.",
        plots=[
            PlotSpec(
                plot_id="annotation_embedding",
                role="overview",
                renderer="annotated_embedding",
                filename="embedding_cell_type.png",
                title="Annotated embedding",
                description="Primary embedding colored by inferred cell type labels.",
                required_obs=["cell_type"],
            ),
            PlotSpec(
                plot_id="annotation_embedding_compare",
                role="diagnostic",
                renderer="annotation_embedding_comparison",
                filename="embedding_cluster_vs_cell_type.png",
                title="Cluster vs annotation",
                description="Primary embedding colored by cluster labels and inferred cell types.",
                required_obs=["cell_type"],
            ),
            PlotSpec(
                plot_id="annotation_mapping_heatmap",
                role="diagnostic",
                renderer="annotation_mapping_heatmap",
                filename="cluster_to_cell_type_heatmap.png",
                title="Cluster-to-annotation mapping",
                description="Normalized mapping from cluster labels to inferred cell types.",
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
            PlotSpec(
                plot_id="annotation_score_embedding",
                role="supporting",
                renderer="annotation_score_embedding",
                filename="embedding_annotation_score.png",
                title="Annotation score on embedding",
                description="Continuous annotation score rendered on the primary embedding when available.",
                required_obs=["annotation_score"],
            ),
        ],
    )


def _gallery_figure_path(output_dir: Path, filename: str) -> Path:
    return Path(output_dir) / "figures" / filename


def _render_annotated_umap(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    embedding_key = context.get("embedding_key")
    if not embedding_key:
        return None
    plot_embedding_categorical(
        adata,
        output_dir,
        obsm_key=embedding_key,
        color_key="cell_type",
        filename=spec.filename,
        title="Annotated embedding",
        subtitle=f"Embedding: {embedding_key}",
    )
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_annotation_sankey(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    cluster_key = context["cluster_key"]
    embedding_key = context.get("embedding_key")
    if not cluster_key or not embedding_key:
        return None
    plot_embedding_comparison(
        adata,
        output_dir,
        obsm_key=embedding_key,
        color_keys=[cluster_key, "cell_type"],
        filename=spec.filename,
        title="Cluster vs annotation on embedding",
    )
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_cell_type_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    counts_df = context.get("cell_type_counts_df", pd.DataFrame())
    if counts_df.empty:
        return None
    plot_cell_type_count_barplot(counts_df, context["output_dir"], filename=spec.filename)
    path = _gallery_figure_path(Path(context["output_dir"]), spec.filename)
    return path if path.exists() else None


def _render_annotation_mapping_heatmap(_adata, spec: PlotSpec, context: dict) -> object:
    matrix_df = context.get("cluster_annotation_matrix_df", pd.DataFrame())
    cluster_key = context.get("cluster_key")
    if matrix_df.empty or not cluster_key:
        return None
    plot_cluster_annotation_heatmap(matrix_df, context["output_dir"], cluster_key=cluster_key, filename=spec.filename)
    path = _gallery_figure_path(Path(context["output_dir"]), spec.filename)
    return path if path.exists() else None


def _render_annotation_score_embedding(adata, spec: PlotSpec, context: dict) -> object:
    embedding_key = context.get("embedding_key")
    if not embedding_key or "annotation_score" not in adata.obs.columns:
        return None
    scores = pd.to_numeric(adata.obs["annotation_score"], errors="coerce")
    if scores.isna().all():
        return None
    plot_embedding_continuous(
        adata,
        context["output_dir"],
        obsm_key=embedding_key,
        color_key="annotation_score",
        filename=spec.filename,
        title="Annotation score on embedding",
        subtitle=f"Embedding: {embedding_key}",
        cmap="viridis",
    )
    path = _gallery_figure_path(Path(context["output_dir"]), spec.filename)
    return path if path.exists() else None


ANNOTATION_GALLERY_RENDERERS = {
    "annotated_embedding": _render_annotated_umap,
    "annotation_embedding_comparison": _render_annotation_sankey,
    "annotation_mapping_heatmap": _render_annotation_mapping_heatmap,
    "cell_type_barplot": _render_cell_type_barplot,
    "annotation_score_embedding": _render_annotation_score_embedding,
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
        ("annotation_embedding_points", "annotation_embedding_points.csv", context.get("annotation_embedding_points_df")),
        ("popv_predictions", "popv_predictions.csv", context.get("popv_predictions_df")),
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
        ("popv_predictions.csv", "popv_predictions_df"),
    ):
        df = context.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            path = tables_dir / filename
            df.to_csv(path, index=False)
            exported.append(str(path))
    return exported


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict, *, gallery_context: dict | None = None) -> None:
    """Write the user-facing annotation report."""
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
        f"- **Requested method**: `{summary.get('requested_method', summary['method'])}`",
        f"- **Executed method**: `{summary.get('actual_method', summary['method'])}`",
        f"- **Cell types identified**: {summary['n_cell_types']}",
        f"- **Primary cluster column**: `{context.get('cluster_key', summary.get('cluster_key', 'none'))}`",
    ]
    if summary.get("fallback_reason"):
        body_lines.append(f"- **Fallback note**: {summary['fallback_reason']}")
    if summary.get("expression_source"):
        body_lines.append(f"- **Expression source used**: `{summary['expression_source']}`")

    body_lines.extend([
        "",
        "## Cell Type Distribution\n",
        "| Cell Type | Count | Proportion (%) |",
        "|-----------|-------|----------------|",
    ])

    counts_df = context.get("cell_type_counts_df", pd.DataFrame(columns=["cell_type", "n_cells"]))
    if isinstance(counts_df, pd.DataFrame):
        for row in counts_df.itertuples(index=False):
            body_lines.append(f"| {row.cell_type} | {row.n_cells} | {row.proportion_pct:.2f} |")

    body_lines.extend(["", "## First-pass Settings\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    # Detect all-Unknown and add targeted guidance
    unk_count = summary.get("cell_type_counts", {}).get("Unknown", 0)
    total_types = len(summary.get("cell_type_counts", {}))
    if unk_count and unk_count == total_types:
        body_lines.extend([
            "",
            "## [!] Troubleshooting: All Cells Labeled Unknown\n",
            "All clusters were annotated as **Unknown**. This means the marker genes used do not match",
            "the genes in your dataset. Common causes and solutions:\n",
            "### Cause 1: Wrong tissue type",
            "The default built-in markers cover blood (PBMC), brain, and general tissue (human).",
            "If your data is from a different tissue, provide custom markers:\n",
            "```bash",
            "# Create a JSON file with markers for your tissue:",
            '# my_markers.json: {"Hepatocyte": ["ALB","APOB"], "Cholangiocyte": ["KRT19","SOX9"]}',
            f"python {SCRIPT_REL_PATH} --input <data.h5ad> --output <dir> --method markers --marker-file my_markers.json",
            "```\n",
            "### Cause 2: Mouse or non-human organism",
            "Built-in markers use human gene symbols (UPPERCASE). Mouse genes are Title case (Cd3d vs CD3D).",
            "The skill attempts automatic case-insensitive matching, but for best results:\n",
            "```bash",
            "# Use CellTypist with a mouse-specific model:",
            f"python {SCRIPT_REL_PATH} --input <data.h5ad> --output <dir> --method celltypist --model Mouse_Isocortex_Hippocampus.pkl",
            "```\n",
            "### Cause 3: Try a different annotation method",
            "- **CellTypist** (no reference needed, 100+ pretrained models):",
            '  `python -c "import celltypist; celltypist.models.models_description()"` to list models',
            "- **knnpredict / popv** (needs a labeled reference H5AD):",
            "  Download from [CZ CELLxGENE](https://cellxgene.cziscience.com/)",
            "- **singler / scmap** (needs R environment):",
            "  Uses celldex atlases (HPCA, ImmGen, etc.)\n",
        ])
    elif unk_count:
        body_lines.extend([
            "",
            f"## Note: {unk_count} of {total_types} Cell Types are Unknown\n",
            "Some clusters could not be confidently assigned. Consider:",
            "- Providing more tissue-specific markers via `--marker-file`",
            "- Using a different annotation method (celltypist, knnpredict)",
            "- Reviewing cluster quality with `sc-markers`\n",
        ])

    body_lines.extend(
        [
            "",
            "## Beginner Notes\n",
            "- `sc-cell-annotation` usually follows clustering or marker review.",
            "- Treat these labels as a first biological interpretation layer, then cross-check them with marker genes and cluster structure.",
            "- If labels still look uncertain, compare another annotation method before moving to DE or communication analysis.",
            "",
            "## Recommended Next Steps\n",
            "- If labels remain ambiguous: revisit `sc-markers` or try a different annotation method/reference.",
            "- If labels look stable: continue to `sc-de` or communication analysis using the inferred cell types.",
            "",
            "## Output Files\n",
            "- `processed.h5ad` — annotated AnnData object.",
            "- `figures/embedding_cell_type.png` — primary embedding colored by cell type.",
            "- `figures/embedding_cluster_vs_cell_type.png` — cluster vs annotation comparison on the same embedding.",
            "- `figures/cluster_to_cell_type_heatmap.png` — normalized mapping from cluster labels to cell types.",
            "- `figures/cell_type_counts.png` — cell type counts and proportions.",
            "- `figures/embedding_annotation_score.png` — score map when the method exposes a numeric confidence.",
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
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    else:
        command_parts.extend(["--input", "<input.h5ad>"])
    command_parts.extend(["--output", str(output_dir)])
    for key, value in params.items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if key == "celltypist_majority_voting":
                command_parts.append(flag if value else "--no-celltypist-majority-voting")
            continue
        command_parts.extend([flag, str(value)])
    command = " ".join(shlex.quote(part) for part in command_parts)
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
    parser.add_argument("--reference", default="HPCA", help="SingleR/scmap atlas selector or labeled H5AD path for popv")
    parser.add_argument("--cluster-key", default=None, help="Cluster/label column for marker summaries and marker-based annotation")
    parser.add_argument("--manual-map", default=None, help="Inline manual mapping like '0=T cell;1,2=Myeloid'")
    parser.add_argument("--manual-map-file", default=None, help="Path to manual mapping file (json/csv/tsv/txt)")
    parser.add_argument("--marker-file", default=None, help="Path to custom marker gene file (JSON or CSV) for the markers method")
    parser.add_argument(
        "--celltypist-majority-voting",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable CellTypist majority voting when running the celltypist backend",
    )
    # SCSA-specific parameters
    parser.add_argument("--species", default="Human", help="SCSA species (Human/Mouse)")
    parser.add_argument("--tissue", default="All", help="SCSA tissue filter (e.g. Blood, Brain, All)")
    parser.add_argument("--scsa-foldchange", type=float, default=1.5, help="SCSA DE fold-change threshold")
    parser.add_argument("--scsa-pvalue", type=float, default=0.05, help="SCSA DE p-value threshold")
    parser.add_argument(
        "--r-enhanced", action="store_true",
        help="Generate R Enhanced ggplot2 figures in addition to standard Python plots."
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata = sc_io.load_repo_demo_data("pbmc3k_raw")[0]
        sc.pp.filter_cells(adata, min_genes=200)
        sc.pp.filter_genes(adata, min_cells=3)
        adata.layers["counts"] = adata.X.copy()
        adata.raw = adata.copy()
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.pca(adata)
        sc.pp.neighbors(adata)
        sc.tl.umap(adata)
        try:
            sc.tl.louvain(adata, resolution=0.8, key_added="louvain")
        except Exception:
            sc.tl.leiden(adata, resolution=0.8, key_added="louvain")
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME)
        input_file = args.input_path

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback="markers")

    # --- Demo-mode: generate a synthetic reference for methods that need one ---
    if args.demo and method in {"popv", "knnpredict"} and args.reference == "HPCA":
        import tempfile
        # Build a small labelled reference from the demo data itself:
        # use the cluster labels as pseudo cell-type annotations.
        ref_adata = adata.copy()
        cluster_col = "louvain" if "louvain" in ref_adata.obs.columns else "leiden"
        _demo_label_map = {
            str(i): name
            for i, name in enumerate(
                ["CD4+ T", "CD14+ Mono", "B cell", "CD8+ T", "NK", "FCGR3A+ Mono", "DC", "Platelet"]
            )
        }
        ref_adata.obs["cell_type"] = (
            ref_adata.obs[cluster_col]
            .astype(str)
            .map(lambda x: _demo_label_map.get(x, f"Unknown_{x}"))
        )
        demo_ref_path = Path(tempfile.mktemp(suffix="_demo_ref.h5ad"))
        ref_adata.write_h5ad(demo_ref_path)
        args.reference = str(demo_ref_path)
        logger.info("[demo] Generated synthetic reference at %s", demo_ref_path)

    apply_preflight(
        preflight_sc_cell_annotation(
            adata,
            method=method,
            model=args.model,
            reference=args.reference,
            cluster_key=args.cluster_key,
            celltypist_majority_voting=args.celltypist_majority_voting,
            manual_map=args.manual_map,
            manual_map_file=args.manual_map_file,
            source_path=input_file,
        ),
        logger,
        demo_mode=args.demo,
    )
    api = load_skill(SKILL_NAME)
    adata = api.annotate(
        adata,
        method=method,
        cluster_key=args.cluster_key,
        marker_file=getattr(args, "marker_file", None),
        model=args.model,
        majority_voting=bool(args.celltypist_majority_voting),
        reference=args.reference,
        manual_map=args.manual_map,
        manual_map_file=args.manual_map_file,
        species=getattr(args, "species", "Human"),
        tissue=getattr(args, "tissue", "All"),
        scsa_foldchange=getattr(args, "scsa_foldchange", 1.5),
        scsa_pvalue=getattr(args, "scsa_pvalue", 0.05),
    )
    run = api.run_info(adata, keep=False)
    args.cluster_key = run["cluster_key"]
    summary = run["summary"]
    summary["n_cells"] = int(adata.n_obs)

    params = {"method": method}
    if args.cluster_key:
        params["cluster_key"] = args.cluster_key
    if method == "manual":
        if args.manual_map:
            params["manual_map"] = args.manual_map
        if args.manual_map_file:
            params["manual_map_file"] = args.manual_map_file
    elif method == "celltypist":
        params["model"] = args.model
        params["celltypist_majority_voting"] = args.celltypist_majority_voting
    elif method in {"popv", "knnpredict", "singler", "scmap"}:
        params["reference"] = args.reference
    elif method == "scsa":
        params["species"] = args.species
        params["tissue"] = args.tissue
        params["scsa_foldchange"] = args.scsa_foldchange
        params["scsa_pvalue"] = args.scsa_pvalue

    gallery_context = _prepare_annotation_gallery_context(adata, summary, params, output_dir, api)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, demo_mode=args.demo)

    params["requested_method"] = method
    params["actual_method"] = summary.get("actual_method", method)
    if summary.get("fallback_reason"):
        params["fallback_reason"] = summary["fallback_reason"]

    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind="normalized_expression",
        raw_kind=get_matrix_contract(adata).get("raw"),
        primary_cluster_key=gallery_context.get("cluster_key"),
    )
    store_analysis_metadata(adata, SKILL_NAME, summary.get("actual_method", method), params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""

    # Diagnostic fields for bot/agent to detect annotation quality issues
    _unk = summary.get("cell_type_counts", {}).get("Unknown", 0)
    _total = len(summary.get("cell_type_counts", {}))
    _all_unknown = _unk > 0 and _unk == _total
    annotation_diagnostics = {
        "unknown_count": _unk,
        "total_type_count": _total,
        "all_unknown": _all_unknown,
    }
    if _all_unknown:
        annotation_diagnostics["suggested_actions"] = [
            "Provide custom marker genes via --marker-file markers.json",
            "Switch to CellTypist: --method celltypist --model <tissue_model>.pkl",
            "Use a labeled reference: --method knnpredict --reference <ref.h5ad>",
            "List CellTypist models: python -c \"import celltypist; celltypist.models.models_description()\"",
            "Download references from https://cellxgene.cziscience.com/",
        ]

    result_data = {
        "method": summary.get("actual_method", method),
        "requested_method": summary.get("requested_method", method),
        "actual_method": summary.get("actual_method", method),
        "used_fallback": summary.get("used_fallback", False),
        "fallback_reason": summary.get("fallback_reason", ""),
        "params": params,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        **summary,
        "annotation_diagnostics": annotation_diagnostics,
        "visualization": {
            "recipe_id": "standard-sc-cell-annotation-gallery",
            "cluster_column": gallery_context.get("cluster_key"),
            "annotation_column": "cell_type",
            "embedding_key": gallery_context.get("embedding_key"),
            "available_figure_data": gallery_context.get("figure_data_files", {}),
        },
    }
    result_data["next_steps"] = [
        {"skill": "sc-markers", "reason": "Find marker genes for annotated cell types", "priority": "recommended"},
        {"skill": "sc-de", "reason": "Differential expression between cell types", "priority": "recommended"},
    ]
    result_data["preprocessing_state_after"] = "annotated"
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }

    # R Enhanced figures (only when --r-enhanced flag is set)
    r_enhanced_figures = _render_r_enhanced(
        output_dir=output_dir,
        figure_data_dir=output_dir / "figure_data",
        r_enhanced=args.r_enhanced,
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures

    # ---- User-facing stdout summary (small-white-friendly) ----
    n_types = summary["n_cell_types"]
    unk_count = summary.get("cell_type_counts", {}).get("Unknown", 0)
    total_types = len(summary.get("cell_type_counts", {}))
    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Method: {summary.get('actual_method', method)}")
    print(f"  Cell types identified: {n_types}")
    if summary.get("used_fallback"):
        print(f"  NOTE: Requested '{summary.get('requested_method')}' but fell back to "
              f"'{summary.get('actual_method')}' - {summary.get('fallback_reason', 'see log')}")
    if unk_count and unk_count == total_types:
        print()
        print("  *** ALL cells were labeled 'Unknown' - annotation did not work for this dataset. ***")
        print("  This usually means the built-in marker genes don't match your tissue or organism.")
        print()
        print("  How to fix:")
        print("    Option 1 - Provide your own markers (easiest):")
        print('      Create a JSON file, e.g. my_markers.json:')
        print('        {"T cell": ["CD3D","CD3E"], "Epithelial": ["EPCAM","KRT18"]}')
        print("      Then rerun:")
        print(f"        python {SCRIPT_REL_PATH} --input <your.h5ad> --output {output_dir} --method markers --marker-file my_markers.json")
        print()
        print("    Option 2 - Use CellTypist (100+ pretrained models, no reference needed):")
        print("      List available models:")
        print('        python -c "import celltypist; celltypist.models.models_description()"')
        print("      Pick a model for your tissue, then:")
        print(f"        python {SCRIPT_REL_PATH} --input <your.h5ad> --output {output_dir} --method celltypist --model Immune_All_Low.pkl")
        print()
        print("    Option 3 - Use a labeled reference dataset:")
        print("      Download a reference H5AD from https://cellxgene.cziscience.com/")
        print("      Then:")
        print(f"        python {SCRIPT_REL_PATH} --input <your.h5ad> --output {output_dir} --method knnpredict --reference ref.h5ad")
        print()
    elif unk_count:
        print(f"  WARNING: {unk_count}/{total_types} cell types are 'Unknown'. Consider providing more specific markers via --marker-file.")

    # --- Next-step guidance ---
    print()
    print(">> Next steps:")
    print(f"  - sc-markers: python skills/singlecell/scrna/sc-markers/sc_markers.py --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  - sc-de:      python skills/singlecell/scrna/sc-de/sc_de.py --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
