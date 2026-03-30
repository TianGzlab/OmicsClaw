#!/usr/bin/env python3
"""Spatial Annotate — cell type annotation for spatial transcriptomics.

Supported methods:
  - marker_based: Marker gene scoring (no reference needed, fast, default)
  - tangram:      Deep learning mapping from scRNA-seq reference (tangram-sc)
  - scanvi:       Semi-supervised VAE transfer learning (scvi-tools)
  - cellassign:   Probabilistic marker-based assignment (scvi-tools)

Usage:
    python spatial_annotate.py --input <preprocessed.h5ad> --output <dir>
    python spatial_annotate.py --demo --output <dir>
    python spatial_annotate.py --input <file> --method tangram --reference <sc_ref.h5ad> --output <dir>
"""

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

import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer, generate_report_header, write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.annotation import (
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    VALID_MARKER_NORMALIZE_OPTIONS,
    VALID_MARKER_OVERLAP_METHODS,
    VALID_MARKER_RANK_METHODS,
    annotate_cellassign,
    annotate_marker_based,
    annotate_scanvi,
    annotate_tangram,
    get_default_signatures,
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

SKILL_NAME = "spatial-annotate"
SKILL_VERSION = "0.4.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-annotate/spatial_annotate.py"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _coerce_probability_frame(values, obs_names, cell_type_names):
    """Return a DataFrame view of a probability matrix when column names are known."""
    if isinstance(values, pd.DataFrame):
        df = values.copy()
        if len(df.index) == len(obs_names):
            df.index = list(obs_names)
        return df

    if cell_type_names is None:
        return None

    if hasattr(values, "values"):
        values = values.values

    if getattr(values, "ndim", None) != 2:
        return None
    if values.shape[0] != len(obs_names) or values.shape[1] != len(cell_type_names):
        return None

    return pd.DataFrame(values, index=list(obs_names), columns=list(cell_type_names))


def _prepare_annotation_plot_state(adata) -> None:
    """Ensure annotation labels and coordinate aliases exist before plotting."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()

    if "cell_type" in adata.obs.columns:
        if not isinstance(adata.obs["cell_type"].dtype, pd.CategoricalDtype):
            adata.obs["cell_type"] = pd.Categorical(adata.obs["cell_type"])
        return

    recovery_specs = [
        ("tangram_ct_pred", "tangram_cell_type_names", None),
        ("scanvi_probabilities", "scanvi_cell_type_names", "scanvi_confidence"),
        ("cellassign_probabilities", "cellassign_cell_type_names", "cellassign_confidence"),
    ]
    for obsm_key, label_key, confidence_key in recovery_specs:
        if obsm_key not in adata.obsm:
            continue
        prob_df = _coerce_probability_frame(
            adata.obsm[obsm_key],
            adata.obs_names,
            adata.uns.get(label_key),
        )
        if prob_df is None or prob_df.empty:
            continue

        adata.obs["cell_type"] = pd.Categorical(prob_df.idxmax(axis=1))
        if confidence_key and confidence_key not in adata.obs.columns:
            adata.obs[confidence_key] = prob_df.max(axis=1).to_numpy()
        logger.info("Recovered cell_type labels from adata.obsm['%s'] for plotting.", obsm_key)
        return


def _ensure_umap_for_gallery(adata) -> None:
    """Compute UMAP if needed for the standard gallery."""
    if "X_umap" in adata.obsm:
        return
    if "connectivities" not in adata.obsp:
        if "X_pca" in adata.obsm:
            sc.pp.neighbors(adata, use_rep="X_pca")
        else:
            sc.pp.neighbors(adata)
    sc.tl.umap(adata)


def _get_annotation_confidence_column(adata) -> str | None:
    for col in ("scanvi_confidence", "cellassign_confidence"):
        if col in adata.obs.columns:
            return col
    return None


def _get_annotation_probability_frame(adata) -> pd.DataFrame | None:
    recovery_specs = [
        ("tangram_ct_pred", "tangram_cell_type_names"),
        ("scanvi_probabilities", "scanvi_cell_type_names"),
        ("cellassign_probabilities", "cellassign_cell_type_names"),
    ]
    for obsm_key, label_key in recovery_specs:
        if obsm_key not in adata.obsm:
            continue
        prob_df = _coerce_probability_frame(
            adata.obsm[obsm_key],
            adata.obs_names,
            adata.uns.get(label_key),
        )
        if prob_df is not None and not prob_df.empty:
            return prob_df
    return None


def _build_annotation_visualization_recipe(adata, summary: dict) -> VisualizationRecipe:
    """Build the default narrative gallery for spatial annotation outputs."""
    plots = [
        PlotSpec(
            plot_id="annotation_spatial_overview",
            role="overview",
            renderer="feature_map",
            filename="cell_type_spatial.png",
            title="Spatial Annotation Overview",
            description="Cell-type labels projected onto the tissue coordinates.",
            params={
                "feature": "cell_type",
                "basis": "spatial",
                "colormap": "tab20",
                "show_axes": False,
                "show_legend": True,
                "figure_size": (10, 8),
            },
            required_obs=["cell_type"],
            required_obsm=["spatial"],
        ),
        PlotSpec(
            plot_id="annotation_umap_overview",
            role="overview",
            renderer="feature_map",
            filename="cell_type_umap.png",
            title="Annotation UMAP Overview",
            description="Cell-type labels displayed on the current low-dimensional embedding.",
            params={
                "feature": "cell_type",
                "basis": "umap",
                "colormap": "tab20",
                "show_axes": False,
                "show_legend": True,
                "figure_size": (10, 8),
            },
            required_obs=["cell_type"],
            required_obsm=["X_umap"],
        ),
        PlotSpec(
            plot_id="annotation_cell_type_distribution",
            role="supporting",
            renderer="category_barplot",
            filename="cell_type_barplot.png",
            title="Cell Type Distribution",
            description="Counts of assigned labels across all spots / cells.",
            params={"feature": "cell_type"},
            required_obs=["cell_type"],
        ),
    ]

    confidence_col = _get_annotation_confidence_column(adata)
    if confidence_col:
        plots.extend(
            [
                PlotSpec(
                    plot_id="annotation_confidence_spatial",
                    role="uncertainty",
                    renderer="feature_map",
                    filename="annotation_confidence_spatial.png",
                    title="Spatial Annotation Confidence",
                    description="Confidence values projected onto spatial coordinates.",
                    params={
                        "feature": confidence_col,
                        "basis": "spatial",
                        "colormap": "viridis",
                        "show_axes": False,
                        "show_colorbar": True,
                        "figure_size": (10, 8),
                    },
                    required_obs=[confidence_col],
                    required_obsm=["spatial"],
                ),
                PlotSpec(
                    plot_id="annotation_confidence_distribution",
                    role="uncertainty",
                    renderer="confidence_histogram",
                    filename="annotation_confidence_histogram.png",
                    title="Annotation Confidence Distribution",
                    description="Distribution of model-derived confidence scores.",
                    params={"feature": confidence_col},
                    required_obs=[confidence_col],
                ),
            ]
        )

    if summary["method"] == "marker_based" and isinstance(adata.uns.get("marker_gene_overlap"), pd.DataFrame):
        plots.append(
            PlotSpec(
                plot_id="annotation_marker_overlap_heatmap",
                role="diagnostic",
                renderer="marker_overlap_heatmap",
                filename="marker_overlap_heatmap.png",
                title="Marker Overlap Heatmap",
                description="Cluster-to-cell-type overlap scores from the Scanpy marker baseline.",
                required_uns=["marker_gene_overlap"],
            )
        )
    elif _get_annotation_probability_frame(adata) is not None:
        plots.append(
            PlotSpec(
                plot_id="annotation_probability_heatmap",
                role="diagnostic",
                renderer="probability_heatmap",
                filename="annotation_probability_heatmap.png",
                title="Annotation Probability Heatmap",
                description="Mean probability assigned to each candidate label after grouping by the predicted label.",
                required_obs=["cell_type"],
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-annotation-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Annotation Standard Gallery",
        description=(
            "Default OmicsClaw story plots for annotation results: overview, "
            "supporting composition, diagnostics, and uncertainty."
        ),
        plots=plots,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    params = VizParams(**spec.params)
    return plot_features(adata, params)


def _render_category_barplot(adata, spec: PlotSpec, _context: dict) -> object:
    import matplotlib.pyplot as plt

    feature = spec.params.get("feature", "cell_type")
    counts = adata.obs[feature].astype(str).value_counts()
    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, max(4, len(counts) * 0.35))), dpi=200)
    counts.plot.barh(ax=ax, color="steelblue")
    ax.set_xlabel("Number of cells")
    ax.set_title(spec.title or "Category Distribution")
    fig.tight_layout()
    return fig


def _render_confidence_histogram(adata, spec: PlotSpec, _context: dict) -> object:
    import matplotlib.pyplot as plt

    feature = spec.params["feature"]
    values = adata.obs[feature].astype(float)
    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(values, bins=20, color="#2b8cbe", edgecolor="white")
    ax.set_xlabel("Confidence")
    ax.set_ylabel("Number of cells")
    ax.set_title(spec.title or "Confidence Distribution")
    fig.tight_layout()
    return fig


def _render_marker_overlap_heatmap(adata, spec: PlotSpec, _context: dict) -> object:
    import matplotlib.pyplot as plt
    import seaborn as sns

    overlap_df = adata.uns["marker_gene_overlap"].T
    fig, ax = plt.subplots(
        figsize=spec.params.get(
            "figure_size",
            (max(6, overlap_df.shape[1] * 0.9), max(4, overlap_df.shape[0] * 0.6)),
        ),
        dpi=200,
    )
    sns.heatmap(overlap_df, cmap="mako", ax=ax)
    ax.set_xlabel("Candidate Cell Type")
    ax.set_ylabel("Cluster")
    ax.set_title(spec.title or "Marker Overlap Heatmap")
    fig.tight_layout()
    return fig


def _render_probability_heatmap(adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt
    import seaborn as sns

    prob_df = context.get("probability_df")
    if prob_df is None or prob_df.empty:
        return None
    grouped = prob_df.groupby(adata.obs["cell_type"].astype(str)).mean()
    grouped = grouped.loc[grouped.index.sort_values()]
    fig, ax = plt.subplots(
        figsize=spec.params.get(
            "figure_size",
            (max(6, grouped.shape[1] * 0.9), max(4, grouped.shape[0] * 0.6)),
        ),
        dpi=200,
    )
    sns.heatmap(grouped, cmap="rocket_r", ax=ax, vmin=0.0, vmax=1.0)
    ax.set_xlabel("Candidate Cell Type")
    ax.set_ylabel("Predicted Label")
    ax.set_title(spec.title or "Annotation Probability Heatmap")
    fig.tight_layout()
    return fig


ANNOTATION_GALLERY_RENDERERS = {
    "feature_map": _render_feature_map,
    "category_barplot": _render_category_barplot,
    "confidence_histogram": _render_confidence_histogram,
    "marker_overlap_heatmap": _render_marker_overlap_heatmap,
    "probability_heatmap": _render_probability_heatmap,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )


def _export_figure_data(
    adata,
    output_dir: Path,
    summary: dict,
    recipe: VisualizationRecipe,
    artifacts: list,
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    _prepare_annotation_plot_state(adata)

    confidence_col = _get_annotation_confidence_column(adata)
    probability_df = _get_annotation_probability_frame(adata)

    base_assignments = pd.DataFrame(index=adata.obs_names)
    base_assignments["cell_type"] = adata.obs["cell_type"].astype(str)
    if confidence_col:
        base_assignments[confidence_col] = adata.obs[confidence_col].astype(float)

    spatial_key = get_spatial_key(adata)
    spatial_points_file = None
    if spatial_key is not None:
        spatial_df = base_assignments.copy()
        spatial_df["x"] = adata.obsm[spatial_key][:, 0]
        spatial_df["y"] = adata.obsm[spatial_key][:, 1]
        spatial_points_file = "annotation_spatial_points.csv"
        spatial_df.reset_index().rename(columns={"index": "observation"}).to_csv(
            figure_data_dir / spatial_points_file,
            index=False,
        )

    umap_points_file = None
    if "X_umap" in adata.obsm:
        umap_df = base_assignments.copy()
        umap_df["umap_1"] = adata.obsm["X_umap"][:, 0]
        umap_df["umap_2"] = adata.obsm["X_umap"][:, 1]
        umap_points_file = "annotation_umap_points.csv"
        umap_df.reset_index().rename(columns={"index": "observation"}).to_csv(
            figure_data_dir / umap_points_file,
            index=False,
        )

    summary_df = pd.DataFrame(
        [
            {"cell_type": ct, "n_cells": n, "proportion": round(n / max(sum(summary["cell_type_counts"].values()), 1) * 100, 2)}
            for ct, n in summary["cell_type_counts"].items()
        ]
    ).sort_values("n_cells", ascending=False)
    summary_df.to_csv(figure_data_dir / "annotation_cell_type_counts.csv", index=False)

    probability_file = None
    if probability_df is not None and not probability_df.empty:
        probability_file = "annotation_probabilities.csv"
        probability_df.reset_index().rename(columns={"index": "observation"}).to_csv(
            figure_data_dir / probability_file,
            index=False,
        )

    overlap_file = None
    overlap_df = adata.uns.get("marker_gene_overlap")
    if isinstance(overlap_df, pd.DataFrame):
        overlap_file = "marker_overlap_scores.csv"
        overlap_df.T.rename_axis("cluster").to_csv(figure_data_dir / overlap_file)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary["method"],
        "cell_type_column": "cell_type",
        "confidence_column": confidence_col,
        "spatial_basis": spatial_key,
        "embedding_basis": "X_umap" if "X_umap" in adata.obsm else None,
        "probability_columns": list(probability_df.columns) if probability_df is not None else None,
        "recommended_palette": "tab20",
        "recipe_id": recipe.recipe_id,
        "gallery_roles": [spec.role for spec in recipe.plots],
        "available_files": {
            "spatial_points": spatial_points_file,
            "umap_points": umap_points_file,
            "cell_type_counts": "annotation_cell_type_counts.csv",
            "probabilities": probability_file,
            "marker_overlap": overlap_file,
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


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Render the standard Python annotation gallery."""
    _prepare_annotation_plot_state(adata)
    if "cell_type" not in adata.obs.columns:
        return []

    _ensure_umap_for_gallery(adata)
    context = {"probability_df": _get_annotation_probability_frame(adata)}
    recipe = _build_annotation_visualization_recipe(adata, summary)
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        ANNOTATION_GALLERY_RENDERERS,
        context=context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _append_cli_flag(command: str, key: str, value) -> str:
    flag = f"--{key.replace('_', '-')}"
    if isinstance(value, bool):
        return f"{command} {flag}" if value else command
    if value in (None, ""):
        return command
    return f"{command} {flag} {shlex.quote(str(value))}"


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-annotate"
        / "r_visualization"
        / "annotation_publication_template.R"
    )
    cmd = (
        f"Rscript {shlex.quote(str(r_template))} "
        f"{shlex.quote(str(output_dir))}"
    )
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def export_tables(output_dir: Path, adata, summary: dict) -> list[str]:
    """Write stable annotation tables for downstream use."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []
    total = sum(summary["cell_type_counts"].values())

    summary_df = pd.DataFrame(
        [
            {"cell_type": ct, "n_cells": n, "proportion": round(n / total * 100, 2)}
            for ct, n in summary["cell_type_counts"].items()
        ]
    ).sort_values("n_cells", ascending=False)
    path = tables_dir / "annotation_summary.csv"
    summary_df.to_csv(path, index=False)
    exported.append(str(path))

    assignments = pd.DataFrame(index=adata.obs_names)
    assignments["cell_type"] = adata.obs["cell_type"].astype(str)
    for col in ("scanvi_confidence", "cellassign_confidence"):
        if col in adata.obs.columns:
            assignments[col] = adata.obs[col].values
    path = tables_dir / "cell_type_assignments.csv"
    assignments.reset_index().rename(columns={"index": "observation"}).to_csv(
        path,
        index=False,
    )
    exported.append(str(path))

    if "cluster_annotations" in summary:
        cluster_df = pd.DataFrame(
            [
                {
                    "cluster": cluster,
                    "cell_type": cell_type,
                    "score": summary.get("cluster_scores", {}).get(cluster),
                }
                for cluster, cell_type in summary["cluster_annotations"].items()
            ]
        )
        path = tables_dir / "cluster_annotations.csv"
        cluster_df.to_csv(path, index=False)
        exported.append(str(path))

    overlap_df = adata.uns.get("marker_gene_overlap")
    if isinstance(overlap_df, pd.DataFrame):
        path = tables_dir / "marker_overlap_scores.csv"
        overlap_df.T.rename_axis("cluster").to_csv(path)
        exported.append(str(path))

    return exported


def write_report(
    output_dir: Path,
    adata,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    header = generate_report_header(
        title="Cell Type Annotation Report", skill_name=SKILL_NAME,
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
    ]
    if "n_clusters" in summary:
        body_lines.append(f"- **Clusters annotated**: {summary['n_clusters']}")
    if "mean_confidence" in summary:
        body_lines.append(f"- **Mean confidence**: {summary['mean_confidence']}")
    if "n_training_genes" in summary:
        body_lines.append(f"- **Training genes used**: {summary['n_training_genes']}")
    if "n_common_genes" in summary:
        body_lines.append(f"- **Common genes used**: {summary['n_common_genes']}")

    body_lines.extend(["", "### Cell type distribution\n",
                        "| Cell Type | Cells | Proportion |",
                        "|-----------|-------|------------|"])
    total = sum(summary["cell_type_counts"].values())
    for ct, count in sorted(summary["cell_type_counts"].items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total else 0
        body_lines.append(f"| {ct} | {count} | {pct:.1f}% |")

    if "cluster_annotations" in summary:
        body_lines.extend(["", "### Cluster to cell type mapping\n",
                            "| Cluster | Cell Type | Score |", "|---------|-----------|-------|"])
        for cl, ct in summary["cluster_annotations"].items():
            score = summary.get("cluster_scores", {}).get(cl, "")
            body_lines.append(f"| {cl} | {ct} | {score} |")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    summary_json = {k: v for k, v in summary.items() if k != "cluster_annotations"}
    probability_df = _get_annotation_probability_frame(adata)
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary_json,
        data={
            "params": params,
            "visualization": {
                "recipe_id": "standard-spatial-annotation-gallery",
                "cell_type_column": "cell_type",
                "confidence_column": _get_annotation_confidence_column(adata),
                "probability_columns": list(probability_df.columns) if probability_df is not None else [],
            },
        },
        input_checksum=checksum,
    )


def write_reproducibility(output_dir: Path, params: dict, input_file: str | None) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    command = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--input <input.h5ad>' if input_file else '--demo'} "
        f"--output {shlex.quote(str(output_dir))}"
    )
    for key, value in params.items():
        command = _append_cli_flag(command, key, value)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n")

    try:
        from importlib.metadata import version as get_version
    except ImportError:
        from importlib_metadata import version as get_version  # type: ignore

    def _pkg_line(candidates: list[str]) -> str:
        for pkg in candidates:
            try:
                return f"{pkg}=={get_version(pkg)}"
            except Exception:
                continue
        return f"{candidates[0]}=?"

    package_groups: list[list[str]] = [
        ["scanpy"],
        ["anndata"],
        ["numpy"],
        ["pandas"],
        ["matplotlib"],
        ["scipy"],
    ]
    optional_by_method = {
        "tangram": [["tangram-sc", "tangram"], ["torch"]],
        "scanvi": [["scvi-tools"], ["torch"]],
        "cellassign": [["scvi-tools"], ["torch"]],
    }
    package_groups.extend(optional_by_method.get(str(params.get("method", "")).lower(), []))
    (repro_dir / "requirements.txt").write_text(
        "\n".join(_pkg_line(candidates) for candidates in package_groups) + "\n"
    )
    _write_r_visualization_helper(output_dir)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def get_demo_data():
    preprocess_script = _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    with tempfile.TemporaryDirectory(prefix="annotate_demo_") as tmpdir:
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", tmpdir],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed: {result.stderr}")
        adata = sc.read_h5ad(Path(tmpdir) / "processed.h5ad")
    return adata, None


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.marker_n_genes < 0:
        parser.error("--marker-n-genes must be >= 0")
    if args.marker_padj_cutoff is not None and not (0 < args.marker_padj_cutoff <= 1):
        parser.error("--marker-padj-cutoff must be in (0, 1]")
    if args.tangram_num_epochs < 1:
        parser.error("--tangram-num-epochs must be >= 1")
    if args.tangram_train_genes < 0:
        parser.error("--tangram-train-genes must be >= 0")
    if args.scanvi_n_hidden < 1:
        parser.error("--scanvi-n-hidden must be >= 1")
    if args.scanvi_n_latent < 1:
        parser.error("--scanvi-n-latent must be >= 1")
    if args.scanvi_n_layers < 1:
        parser.error("--scanvi-n-layers must be >= 1")
    if args.scanvi_max_epochs < 1:
        parser.error("--scanvi-max-epochs must be >= 1")
    if args.cellassign_max_epochs < 1:
        parser.error("--cellassign-max-epochs must be >= 1")
    if args.method in {"tangram", "scanvi"} and not args.reference:
        parser.error(f"--reference is required for {args.method}")
    if args.reference and not Path(args.reference).exists():
        parser.error(f"Reference file not found: {args.reference}")
    if args.method == "cellassign" and args.model and not Path(args.model).exists():
        parser.error(f"Custom marker model not found: {args.model}")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    params = {"method": args.method}

    if args.method == "marker_based":
        overlap_normalize = None if args.marker_overlap_normalize == "none" else args.marker_overlap_normalize
        if args.marker_padj_cutoff is not None and args.marker_n_genes > 0:
            logger.warning(
                "Ignoring --marker-padj-cutoff because Scanpy prioritizes top_n_markers when --marker-n-genes > 0."
            )
        params.update(
            {
                "cluster_key": args.cluster_key,
                "species": args.species,
                "marker_rank_method": args.marker_rank_method,
                "marker_n_genes": args.marker_n_genes,
                "marker_overlap_method": args.marker_overlap_method,
                "marker_overlap_normalize": overlap_normalize,
                "marker_padj_cutoff": args.marker_padj_cutoff,
            }
        )
        method_kwargs = {
            "cluster_key": args.cluster_key,
            "species": args.species,
            "rank_method": args.marker_rank_method,
            "n_marker_genes": args.marker_n_genes,
            "overlap_method": args.marker_overlap_method,
            "overlap_normalize": overlap_normalize,
            "adj_pval_threshold": args.marker_padj_cutoff,
            "min_score": METHOD_PARAM_DEFAULTS["marker_based"]["min_score"],
        }
    elif args.method == "tangram":
        params.update(
            {
                "reference": args.reference,
                "cell_type_key": args.cell_type_key,
                "tangram_num_epochs": args.tangram_num_epochs,
                "tangram_device": args.tangram_device,
                "tangram_train_genes": args.tangram_train_genes,
            }
        )
        method_kwargs = {
            "reference_path": args.reference,
            "cell_type_key": args.cell_type_key,
            "n_epochs": args.tangram_num_epochs,
            "device": args.tangram_device,
            "n_train_genes": args.tangram_train_genes,
        }
    elif args.method == "scanvi":
        params.update(
            {
                "reference": args.reference,
                "cell_type_key": args.cell_type_key,
                "batch_key": args.batch_key,
                "layer": args.layer,
                "scanvi_n_hidden": args.scanvi_n_hidden,
                "scanvi_n_latent": args.scanvi_n_latent,
                "scanvi_n_layers": args.scanvi_n_layers,
                "scanvi_max_epochs": args.scanvi_max_epochs,
            }
        )
        method_kwargs = {
            "reference_path": args.reference,
            "cell_type_key": args.cell_type_key,
            "batch_key": args.batch_key,
            "layer": args.layer,
            "n_hidden": args.scanvi_n_hidden,
            "n_latent": args.scanvi_n_latent,
            "n_layers": args.scanvi_n_layers,
            "max_epochs": args.scanvi_max_epochs,
        }
    elif args.method == "cellassign":
        params.update(
            {
                "species": args.species,
                "model": args.model,
                "batch_key": args.batch_key,
                "layer": args.layer,
                "cellassign_max_epochs": args.cellassign_max_epochs,
            }
        )
        method_kwargs = {
            "max_epochs": args.cellassign_max_epochs,
            "batch_key": args.batch_key,
            "layer": args.layer,
        }
    else:
        method_kwargs = {}

    return params, method_kwargs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial Annotate — multi-method cell type annotation")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="marker_based")
    parser.add_argument("--reference", default=None)
    parser.add_argument(
        "--cell-type-key",
        default=METHOD_PARAM_DEFAULTS["tangram"]["cell_type_key"],
    )
    parser.add_argument(
        "--cluster-key",
        default=METHOD_PARAM_DEFAULTS["marker_based"]["cluster_key"],
    )
    parser.add_argument("--species", default="human", choices=["human", "mouse"])
    parser.add_argument("--batch-key", default=None)
    parser.add_argument("--layer", default=METHOD_PARAM_DEFAULTS["scanvi"]["layer"])
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--marker-rank-method",
        choices=list(VALID_MARKER_RANK_METHODS),
        default=METHOD_PARAM_DEFAULTS["marker_based"]["rank_method"],
    )
    parser.add_argument(
        "--marker-n-genes",
        type=int,
        default=METHOD_PARAM_DEFAULTS["marker_based"]["n_marker_genes"],
        help="Top markers per cluster for Scanpy overlap scoring; set 0 to use all significant markers.",
    )
    parser.add_argument(
        "--marker-overlap-method",
        choices=list(VALID_MARKER_OVERLAP_METHODS),
        default=METHOD_PARAM_DEFAULTS["marker_based"]["overlap_method"],
    )
    parser.add_argument(
        "--marker-overlap-normalize",
        choices=[*VALID_MARKER_NORMALIZE_OPTIONS, "none"],
        default=METHOD_PARAM_DEFAULTS["marker_based"]["overlap_normalize"],
    )
    parser.add_argument("--marker-padj-cutoff", type=float, default=None)
    parser.add_argument(
        "--tangram-num-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["tangram"]["n_epochs"],
    )
    parser.add_argument(
        "--tangram-device",
        default=METHOD_PARAM_DEFAULTS["tangram"]["device"],
        help="Tangram device string such as auto, cpu, cuda:0, or mps.",
    )
    parser.add_argument(
        "--tangram-train-genes",
        type=int,
        default=METHOD_PARAM_DEFAULTS["tangram"]["n_train_genes"],
        help="Number of reference training genes passed to Tangram; use 0 for all shared genes.",
    )
    parser.add_argument(
        "--scanvi-n-hidden",
        type=int,
        default=METHOD_PARAM_DEFAULTS["scanvi"]["n_hidden"],
    )
    parser.add_argument(
        "--scanvi-n-latent",
        type=int,
        default=METHOD_PARAM_DEFAULTS["scanvi"]["n_latent"],
    )
    parser.add_argument(
        "--scanvi-n-layers",
        type=int,
        default=METHOD_PARAM_DEFAULTS["scanvi"]["n_layers"],
    )
    parser.add_argument(
        "--scanvi-max-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["scanvi"]["max_epochs"],
    )
    parser.add_argument(
        "--cellassign-max-epochs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["cellassign"]["max_epochs"],
    )
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    params, method_kwargs = _collect_run_configuration(args)
    logger.info("Running %s with parameters: %s", args.method, params)

    if args.method == "marker_based":
        summary = annotate_marker_based(adata, **method_kwargs)
    elif args.method == "tangram":
        summary = annotate_tangram(adata, **method_kwargs)
    elif args.method == "scanvi":
        summary = annotate_scanvi(adata, **method_kwargs)
    elif args.method == "cellassign":
        if args.model:
            with open(args.model, encoding="utf-8") as f:
                marker_genes = json.load(f)
            summary_marker_source = args.model
        else:
            marker_genes = get_default_signatures(args.species)
            summary_marker_source = f"default_signatures:{args.species}"
        summary = annotate_cellassign(adata, marker_genes=marker_genes, **method_kwargs)
        summary["marker_source"] = summary_marker_source
        summary["species"] = args.species
    else:
        print(f"ERROR: Unknown method {args.method}", file=sys.stderr); sys.exit(1)

    generate_figures(adata, output_dir, summary)
    export_tables(output_dir, adata, summary)
    write_report(output_dir, adata, summary, input_file, params)
    write_reproducibility(output_dir, params, input_file)
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved: %s", h5ad_path)
    print(f"Annotation complete: {summary['n_cell_types']} cell types ({summary['method']})")


if __name__ == "__main__":
    main()
