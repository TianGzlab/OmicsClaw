#!/usr/bin/env python3
"""Single-Cell Annotation - marker-based, CellTypist, SingleR, scmap-compatible R path."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import tempfile
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/omicsclaw_mpl")
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/omicsclaw_numba_cache")

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
from skills.singlecell._lib.adata_utils import (
    get_matrix_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib import annotation as sc_annotation_utils
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import (
    _obs_candidates,
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
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-cell-annotation"
SKILL_VERSION = "0.7.0"
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


def _record_annotation_execution(
    adata,
    *,
    requested_method: str,
    actual_method: str,
    fallback_reason: str = "",
) -> None:
    adata.obs["annotation_requested_method"] = requested_method
    adata.obs["annotation_actual_method"] = actual_method
    adata.obs["annotation_method"] = actual_method
    adata.uns["annotation_runtime"] = {
        "requested_method": requested_method,
        "actual_method": actual_method,
        "used_fallback": bool(fallback_reason),
        "fallback_reason": fallback_reason,
    }


def _annotation_summary(
    adata,
    *,
    requested_method: str,
    actual_method: str,
    fallback_reason: str = "",
    expression_source: str | None = None,
) -> dict:
    counts = adata.obs["cell_type"].astype(str).value_counts().to_dict()
    summary = {
        "method": actual_method,
        "requested_method": requested_method,
        "actual_method": actual_method,
        "used_fallback": bool(fallback_reason),
        "fallback_reason": fallback_reason,
        "n_cell_types": len(counts),
        "cell_type_counts": {str(k): int(v) for k, v in counts.items()},
    }
    if expression_source:
        summary["expression_source"] = expression_source
    return summary


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


def annotate_markers(adata, markers=None, cluster_key: str = "leiden"):
    """Marker-based annotation."""
    if markers is None:
        markers = PBMC_MARKERS
    expression_source, expr = "adata.X", adata

    if cluster_key not in adata.obs:
        raise ValueError(
            f"Marker-based annotation requires an existing cluster/label column. `{cluster_key}` was not found in adata.obs."
        )

    cluster_annotations = {}
    expr_var_names = expr.var_names
    for cluster in adata.obs[cluster_key].astype(str).unique():
        cluster_mask = adata.obs[cluster_key].astype(str) == cluster
        cluster_data = adata[cluster_mask]

        best_type = "Unknown"
        best_score = 0.0
        for cell_type, marker_genes in markers.items():
            available = [g for g in marker_genes if g in expr_var_names]
            if not available:
                continue
            scores = np.asarray(cluster_data[:, available].X.mean()).item()
            if scores > best_score:
                best_score = float(scores)
                best_type = cell_type

        cluster_annotations[cluster] = best_type

    adata.obs["cell_type"] = adata.obs[cluster_key].astype(str).map(cluster_annotations)
    adata.obs["annotation_score"] = np.nan
    _record_annotation_execution(
        adata,
        requested_method="markers",
        actual_method="markers",
    )
    logger.info("Annotated %d clusters", len(cluster_annotations))
    return _annotation_summary(
        adata,
        requested_method="markers",
        actual_method="markers",
        expression_source=expression_source,
    )


def annotate_manual(adata, *, cluster_key: str, manual_map: str | None = None, manual_map_file: str | None = None):
    """Apply an explicit user-supplied cluster-to-label mapping."""
    if manual_map_file:
        annotations = sc_annotation_utils.load_manual_annotation_map(manual_map_file)
        mapping_source = str(manual_map_file)
    elif manual_map:
        annotations = sc_annotation_utils.parse_manual_annotation_map(manual_map)
        mapping_source = "inline"
    else:
        raise ValueError("Manual annotation requires --manual-map or --manual-map-file.")

    sc_annotation_utils.annotate_clusters_manual(
        adata,
        annotations=annotations,
        cluster_key=cluster_key,
        annotation_key="cell_type",
        inplace=True,
    )
    adata.obs["annotation_score"] = np.nan
    _record_annotation_execution(
        adata,
        requested_method="manual",
        actual_method="manual",
    )
    summary = _annotation_summary(
        adata,
        requested_method="manual",
        actual_method="manual",
        expression_source="manual_mapping",
    )
    summary["manual_mapping_source"] = mapping_source
    summary["manual_mapping"] = annotations
    return summary


def annotate_celltypist(adata, model: str = "Immune_All_Low", majority_voting: bool = False):
    """CellTypist annotation with explicit fallback recording."""
    celltypist_input, expression_source = sc_annotation_utils.build_celltypist_input_adata(adata)
    is_valid, reason = sc_annotation_utils.validate_celltypist_input_matrix(celltypist_input)
    if not is_valid:
        logger.warning("CellTypist input validation failed: %s", reason)
        annotate_markers(adata)
        _record_annotation_execution(
            adata,
            requested_method="celltypist",
            actual_method="markers",
            fallback_reason=reason,
        )
        summary = _annotation_summary(
            adata,
            requested_method="celltypist",
            actual_method="markers",
            fallback_reason=reason,
            expression_source=expression_source,
        )
        return summary

    try:
        model_name = model if model.endswith(".pkl") else f"{model}.pkl"
        sc_annotation_utils.annotate_with_celltypist(
            celltypist_input,
            model=model_name,
            majority_voting=majority_voting,
            annotation_key="cell_type",
            inplace=True,
        )
        adata.obs["cell_type"] = celltypist_input.obs["cell_type"].values
        if "cell_type_score" in celltypist_input.obs.columns:
            adata.obs["annotation_score"] = pd.to_numeric(celltypist_input.obs["cell_type_score"], errors="coerce").values
        if "cell_type_prob" in celltypist_input.obsm:
            adata.obsm["cell_type_prob"] = celltypist_input.obsm["cell_type_prob"]
        _record_annotation_execution(
            adata,
            requested_method="celltypist",
            actual_method="celltypist",
        )
        return _annotation_summary(
            adata,
            requested_method="celltypist",
            actual_method="celltypist",
            expression_source=expression_source,
        )
    except Exception as exc:
        reason = str(exc)
        logger.warning("CellTypist annotation unavailable (%s); falling back to marker-based annotation", exc)
        annotate_markers(adata)
        _record_annotation_execution(
            adata,
            requested_method="celltypist",
            actual_method="markers",
            fallback_reason=reason,
        )
        summary = _annotation_summary(
            adata,
            requested_method="celltypist",
            actual_method="markers",
            fallback_reason=reason,
            expression_source=expression_source,
        )
    return summary


def annotate_popv(adata, reference: str = "HPCA", cluster_key: str = "leiden"):
    """PopV-style reference mapping with cluster consensus."""
    metadata = sc_annotation_utils.apply_popv_annotation(
        adata,
        reference,
        cluster_key=cluster_key,
    )
    actual_method = metadata.get("backend", "popv")
    _record_annotation_execution(
        adata,
        requested_method="popv",
        actual_method=actual_method,
    )
    summary = _annotation_summary(
        adata,
        requested_method="popv",
        actual_method=actual_method,
        expression_source=metadata.get("expression_source"),
    )
    summary.update(
        {
            "backend": metadata.get("backend"),
            "reference": reference,
            "reference_label_key": metadata.get("reference_label_key"),
            "reference_cell_types": metadata.get("reference_cell_types"),
            "reference_gene_overlap": metadata.get("reference_gene_overlap"),
            "reference_path": metadata.get("reference_path"),
            "popv_methods": metadata.get("popv_methods"),
        }
    )
    return summary


def annotate_knnpredict(adata, reference: str = "HPCA", cluster_key: str = "leiden"):
    """Lightweight reference mapping inspired by SCOP KNNPredict."""
    metadata = sc_annotation_utils.apply_knnpredict_annotation(
        adata,
        reference,
        cluster_key=cluster_key,
    )
    _record_annotation_execution(
        adata,
        requested_method="knnpredict",
        actual_method="knnpredict",
    )
    summary = _annotation_summary(
        adata,
        requested_method="knnpredict",
        actual_method="knnpredict",
        expression_source=metadata.get("expression_source"),
    )
    summary.update(
        {
            "backend": metadata.get("backend"),
            "reference": reference,
            "reference_label_key": metadata.get("reference_label_key"),
            "reference_cell_types": metadata.get("reference_cell_types"),
            "reference_gene_overlap": metadata.get("reference_gene_overlap"),
            "reference_path": metadata.get("reference_path"),
        }
    )
    return summary


def _apply_r_annotations(adata, df: pd.DataFrame, *, requested_method: str, actual_method: str) -> dict:
    df = df.copy()
    if df.empty:
        raise RuntimeError(f"R annotation method '{requested_method}' returned no predictions")
    df.index = df.index.astype(str)
    df = df.reindex(adata.obs_names)
    labels = df["pruned_label"].fillna(df["cell_type"]).astype(str)
    adata.obs["cell_type"] = labels.values
    if "score" in df.columns:
        adata.obs["annotation_score"] = pd.to_numeric(df["score"], errors="coerce").values
    _record_annotation_execution(
        adata,
        requested_method=requested_method,
        actual_method=actual_method,
    )
    return _annotation_summary(adata, requested_method=requested_method, actual_method=actual_method)


def annotate_singler(adata, reference: str = "HPCA"):
    """SingleR annotation via the shared R bridge."""
    validate_r_environment(required_r_packages=["SingleR", "celldex", "SingleCellExperiment", "zellkonverter"])
    export_adata, expression_source = sc_annotation_utils.build_celltypist_input_adata(adata)
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_singler_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        r_home = tmpdir / "r_home"
        xdg_cache = tmpdir / "xdg_cache"
        eh_cache = tmpdir / "experimenthub"
        for path in (r_home, xdg_cache, eh_cache):
            path.mkdir(parents=True, exist_ok=True)
        export_adata.write_h5ad(input_h5ad)
        runner.run_script(
            "sc_singler_annotate.R",
            args=[str(input_h5ad), str(output_dir), reference],
            expected_outputs=["singler_results.csv"],
            output_dir=output_dir,
            env={
                "HOME": str(r_home),
                "XDG_CACHE_HOME": str(xdg_cache),
                "OMICSCLAW_EXPERIMENTHUB_CACHE": str(eh_cache),
                "ZELLKONVERTER_USE_BASILISK": "FALSE",
            },
        )
        df = pd.read_csv(output_dir / "singler_results.csv", index_col=0)
    summary = _apply_r_annotations(adata, df, requested_method="singler", actual_method="singler")
    summary["expression_source"] = expression_source
    summary["reference"] = reference
    return summary


def annotate_scmap(adata, reference: str = "HPCA"):
    """scmap annotation via the shared R bridge."""
    validate_r_environment(required_r_packages=["scmap", "celldex", "SingleCellExperiment", "zellkonverter"])
    export_adata, expression_source = sc_annotation_utils.build_celltypist_input_adata(adata)
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_scmap_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        r_home = tmpdir / "r_home"
        xdg_cache = tmpdir / "xdg_cache"
        eh_cache = tmpdir / "experimenthub"
        for path in (r_home, xdg_cache, eh_cache):
            path.mkdir(parents=True, exist_ok=True)
        export_adata.write_h5ad(input_h5ad)
        runner.run_script(
            "sc_scmap_annotate.R",
            args=[str(input_h5ad), str(output_dir), reference],
            expected_outputs=["scmap_results.csv"],
            output_dir=output_dir,
            env={
                "HOME": str(r_home),
                "XDG_CACHE_HOME": str(xdg_cache),
                "OMICSCLAW_EXPERIMENTHUB_CACHE": str(eh_cache),
                "ZELLKONVERTER_USE_BASILISK": "FALSE",
            },
        )
        df = pd.read_csv(output_dir / "scmap_results.csv", index_col=0)
    summary = _apply_r_annotations(adata, df, requested_method="scmap", actual_method="scmap")
    summary["expression_source"] = expression_source
    summary["reference"] = reference
    return summary


_METHOD_DISPATCH = {
    "manual": lambda adata, args: annotate_manual(
        adata,
        cluster_key=args.cluster_key,
        manual_map=args.manual_map,
        manual_map_file=args.manual_map_file,
    ),
    "markers": lambda adata, args: annotate_markers(adata, cluster_key=args.cluster_key),
    "celltypist": lambda adata, args: annotate_celltypist(adata, args.model, majority_voting=bool(args.celltypist_majority_voting)),
    "popv": lambda adata, args: annotate_popv(adata, args.reference, cluster_key=args.cluster_key),
    "knnpredict": lambda adata, args: annotate_knnpredict(adata, args.reference, cluster_key=args.cluster_key),
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


def _prepare_annotation_gallery_context(adata, summary: dict, params: dict, output_dir: Path) -> dict:
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
        "cell_type_counts_df": _build_cell_type_counts_table(summary),
        "cluster_annotation_matrix_df": _build_cluster_annotation_matrix(adata, cluster_key),
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

    counts_df = context.get("cell_type_counts_df", _build_cell_type_counts_table(summary))
    if isinstance(counts_df, pd.DataFrame):
        for row in counts_df.itertuples(index=False):
            body_lines.append(f"| {row.cell_type} | {row.n_cells} | {row.proportion_pct:.2f} |")

    body_lines.extend(["", "## First-pass Settings\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

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
    parser.add_argument(
        "--celltypist-majority-voting",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable CellTypist majority voting when running the celltypist backend",
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
    )
    resolved_cluster_key = _resolve_cluster_key(adata, args.cluster_key)
    args.cluster_key = resolved_cluster_key
    summary = _METHOD_DISPATCH[method](adata, args)
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

    gallery_context = _prepare_annotation_gallery_context(adata, summary, params, output_dir)
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
        "visualization": {
            "recipe_id": "standard-sc-cell-annotation-gallery",
            "cluster_column": gallery_context.get("cluster_key"),
            "annotation_column": "cell_type",
            "embedding_key": gallery_context.get("embedding_key"),
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
