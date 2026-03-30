"""Spatial Integrate — multi-sample integration and batch correction.

Usage:
    oc run spatial-integration --input <merged.h5ad> --output <dir> --batch-key batch
    oc run spatial-integration --demo --output <dir>
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

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import store_analysis_metadata
from skills.spatial._lib.dependency_manager import is_available
from skills.spatial._lib.integration import (
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    run_integration,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_features,
    plot_integration,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-integrate"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-integrate/spatial_integrate.py"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _with_umap_snapshot(adata, umap_key: str, render_fn):
    """Temporarily expose a stored UMAP snapshot as ``obsm['X_umap']``."""
    if umap_key not in adata.obsm:
        raise KeyError(f"UMAP snapshot '{umap_key}' not found in adata.obsm")

    original_umap = adata.obsm["X_umap"].copy() if "X_umap" in adata.obsm else None
    adata.obsm["X_umap"] = adata.obsm[umap_key]
    try:
        return render_fn()
    finally:
        if original_umap is None:
            del adata.obsm["X_umap"]
        else:
            adata.obsm["X_umap"] = original_umap


def _validate_figure_inputs(adata, summary: dict) -> None:
    """Warn if the expected integration outputs are missing from ``adata``."""
    embedding_key = summary.get("embedding_key")
    representation_type = summary.get("representation_type", "embedding")

    if representation_type == "embedding" and embedding_key not in adata.obsm:
        logger.warning(
            "Expected integrated embedding '%s' was not found in adata.obsm before figure generation.",
            embedding_key,
        )
    if representation_type == "neighbor_graph" and "connectivities" not in adata.obsp:
        logger.warning(
            "Expected integrated neighbor graph was not found in adata.obsp['connectivities'] before figure generation."
        )
    for umap_key in ("X_umap_before_integration", "X_umap_after_integration"):
        if umap_key not in adata.obsm:
            logger.warning(
                "Expected UMAP snapshot '%s' is missing; integration figure generation may be incomplete.",
                umap_key,
            )


def _resolve_batch_key(adata, requested_key: str | None) -> str | None:
    if requested_key and requested_key in adata.obs.columns:
        return requested_key
    for candidate in ("batch", "sample_id", "batch_key", "sample"):
        if candidate in adata.obs.columns:
            return candidate
    return None


def _resolve_cluster_key(adata) -> str | None:
    for candidate in ("leiden", "louvain", "cluster", "cell_type", "celltype"):
        if candidate in adata.obs.columns:
            return candidate
    return None


def _prepare_integration_gallery_context(
    adata,
    summary: dict,
    *,
    batch_key: str | None = None,
) -> dict:
    _validate_figure_inputs(adata, summary)
    return {
        "resolved_batch_key": _resolve_batch_key(adata, batch_key),
        "resolved_cluster_key": _resolve_cluster_key(adata),
    }


def _build_integration_visualization_recipe(
    adata,
    summary: dict,
    context: dict,
) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    batch_key = context.get("resolved_batch_key")
    cluster_key = context.get("resolved_cluster_key")

    if "X_umap_before_integration" in adata.obsm and batch_key:
        plots.append(
            PlotSpec(
                plot_id="integration_umap_before_batch",
                role="overview",
                renderer="integration_umap",
                filename="umap_before_by_batch.png",
                title=f"UMAP by Batch - Before {summary.get('method', 'integration')}",
                description="Pre-integration UMAP colored by batch.",
                params={
                    "subtype": "batch",
                    "snapshot_key": "X_umap_before_integration",
                    "batch_key": batch_key,
                    "figure_size": (8, 6),
                },
                required_obsm=["X_umap_before_integration"],
                required_obs=[batch_key],
            )
        )

    if "X_umap_after_integration" in adata.obsm and batch_key:
        plots.append(
            PlotSpec(
                plot_id="integration_umap_after_batch",
                role="overview",
                renderer="integration_umap",
                filename="umap_by_batch.png",
                title=f"UMAP by Batch - After {summary.get('method', 'integration')}",
                description="Post-integration UMAP colored by batch.",
                params={
                    "subtype": "batch",
                    "snapshot_key": "X_umap_after_integration",
                    "batch_key": batch_key,
                    "figure_size": (8, 6),
                },
                required_obsm=["X_umap_after_integration"],
                required_obs=[batch_key],
            )
        )

    if "X_umap_after_integration" in adata.obsm and cluster_key:
        plots.append(
            PlotSpec(
                plot_id="integration_umap_after_cluster",
                role="diagnostic",
                renderer="integration_umap",
                filename="umap_by_cluster.png",
                title=f"UMAP by Cluster - After {summary.get('method', 'integration')}",
                description="Post-integration UMAP colored by cluster labels to assess biological structure preservation.",
                params={
                    "subtype": "cluster",
                    "snapshot_key": "X_umap_after_integration",
                    "cluster_key": cluster_key,
                    "figure_size": (8, 6),
                },
                required_obsm=["X_umap_after_integration"],
                required_obs=[cluster_key],
            )
        )

    if "X_umap_after_integration" in adata.obsm and batch_key:
        plots.append(
            PlotSpec(
                plot_id="integration_batch_highlight",
                role="diagnostic",
                renderer="integration_umap",
                filename="batch_highlight.png",
                title="Per-Batch Distribution",
                description="Per-batch highlight panels showing how batches distribute after integration.",
                params={
                    "subtype": "highlight",
                    "snapshot_key": "X_umap_after_integration",
                    "batch_key": batch_key,
                    "figure_size": (10, 8),
                },
                required_obsm=["X_umap_after_integration"],
                required_obs=[batch_key],
            )
        )

    if summary.get("batch_sizes"):
        plots.append(
            PlotSpec(
                plot_id="integration_batch_sizes",
                role="supporting",
                renderer="batch_size_barplot",
                filename="batch_sizes.png",
                title="Batch Size Distribution",
                description="Cells or spots contributed by each batch before integration.",
            )
        )

    plots.append(
        PlotSpec(
            plot_id="integration_batch_mixing",
            role="uncertainty",
            renderer="batch_mixing_barplot",
            filename="batch_mixing.png",
            title="Integration Quality",
            description="Batch-mixing entropy before and after integration.",
        )
    )

    if "X_umap_after_integration" in adata.obsm and "batch_entropy_after" in adata.obs.columns:
        plots.append(
            PlotSpec(
                plot_id="integration_batch_entropy_after_umap",
                role="uncertainty",
                renderer="feature_snapshot",
                filename="batch_entropy_after_umap.png",
                title="Post-Integration Local Batch Entropy",
                description="Per-spot local batch entropy projected onto the post-integration UMAP.",
                params={
                    "snapshot_key": "X_umap_after_integration",
                    "feature": "batch_entropy_after",
                    "basis": "umap",
                    "colormap": "viridis",
                    "show_colorbar": True,
                    "show_axes": False,
                    "figure_size": (8, 6),
                },
                required_obsm=["X_umap_after_integration"],
                required_obs=["batch_entropy_after"],
            )
        )

    if "batch_entropy_before" in adata.obs.columns and "batch_entropy_after" in adata.obs.columns:
        plots.append(
            PlotSpec(
                plot_id="integration_batch_entropy_distribution",
                role="uncertainty",
                renderer="batch_entropy_histogram",
                filename="batch_entropy_distribution.png",
                title="Local Batch Entropy Distribution",
                description="Distribution of local batch entropy before and after integration.",
                required_obs=["batch_entropy_before", "batch_entropy_after"],
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-integration-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Integration Standard Gallery",
        description=(
            "Default OmicsClaw integration story plots built from existing integration and "
            "feature-map viz primitives: before/after overviews, diagnostics, supporting summaries, "
            "and uncertainty panels."
        ),
        plots=plots,
    )


def _render_integration_umap(adata, spec: PlotSpec, _context: dict) -> object:
    snapshot_key = spec.params["snapshot_key"]

    def _render():
        params = VizParams(
            batch_key=spec.params.get("batch_key"),
            cluster_key=spec.params.get("cluster_key"),
            title=spec.title,
            figure_size=spec.params.get("figure_size"),
            dpi=int(spec.params.get("dpi", 200)),
        )
        return plot_integration(
            adata,
            params,
            subtype=spec.params.get("subtype"),
        )

    return _with_umap_snapshot(adata, snapshot_key, _render)


def _render_feature_snapshot(adata, spec: PlotSpec, _context: dict) -> object:
    snapshot_key = spec.params["snapshot_key"]

    def _render():
        viz_params = {k: v for k, v in spec.params.items() if k != "snapshot_key"}
        return plot_features(adata, VizParams(**viz_params))

    return _with_umap_snapshot(adata, snapshot_key, _render)


def _render_batch_size_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    batch_sizes = context["summary"].get("batch_sizes", {})
    if not batch_sizes:
        return None

    series = pd.Series(batch_sizes)
    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, max(4, len(series) * 0.45))), dpi=200)
    series.plot.barh(ax=ax, color="#2b8cbe")
    ax.set_xlabel("Number of cells / spots")
    ax.set_title(spec.title or "Batch Size Distribution")
    ax.invert_yaxis()
    fig.tight_layout()
    return fig


def _render_batch_mixing_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    summary = context["summary"]
    before = float(summary.get("batch_mixing_before", 0.0))
    after = float(summary.get("batch_mixing_after", 0.0))
    gain = after - before

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (6.5, 4.5)), dpi=200)
    bars = ax.bar(
        ["Before", "After"],
        [before, after],
        color=["#d95f02", "#1b9e77"],
        edgecolor="black",
        width=0.55,
    )
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Batch mixing entropy (normalized)")
    ax.set_title(spec.title or "Integration Quality")
    for bar, value in zip(bars, (before, after)):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value:.3f}", ha="center")
    ax.text(
        0.98,
        0.05,
        f"gain = {gain:+.3f}",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=10,
        color="#444444",
    )
    fig.tight_layout()
    return fig


def _render_batch_entropy_histogram(adata, spec: PlotSpec, _context: dict) -> object:
    import matplotlib.pyplot as plt

    before = adata.obs["batch_entropy_before"].astype(float)
    after = adata.obs["batch_entropy_after"].astype(float)
    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(before, bins=20, alpha=0.55, color="#d95f02", label="Before", edgecolor="white")
    ax.hist(after, bins=20, alpha=0.55, color="#1b9e77", label="After", edgecolor="white")
    ax.set_xlabel("Local batch entropy")
    ax.set_ylabel("Number of cells / spots")
    ax.set_title(spec.title or "Local Batch Entropy Distribution")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


INTEGRATION_GALLERY_RENDERERS = {
    "integration_umap": _render_integration_umap,
    "feature_snapshot": _render_feature_snapshot,
    "batch_size_barplot": _render_batch_size_barplot,
    "batch_mixing_barplot": _render_batch_mixing_barplot,
    "batch_entropy_histogram": _render_batch_entropy_histogram,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )


def _build_umap_export_table(
    adata,
    umap_key: str,
    *,
    batch_key: str | None,
    cluster_key: str | None,
    entropy_column: str | None,
) -> pd.DataFrame | None:
    if umap_key not in adata.obsm:
        return None

    umap = np.asarray(adata.obsm[umap_key])
    if umap.shape[1] < 2:
        return None

    df = pd.DataFrame(
        {
            "observation": adata.obs_names,
            "umap_1": umap[:, 0],
            "umap_2": umap[:, 1],
        }
    )
    if batch_key and batch_key in adata.obs.columns:
        df["batch_label"] = adata.obs[batch_key].astype(str).to_numpy()
    if cluster_key and cluster_key in adata.obs.columns:
        df["cluster_label"] = adata.obs[cluster_key].astype(str).to_numpy()
    if entropy_column and entropy_column in adata.obs.columns:
        df[entropy_column] = adata.obs[entropy_column].astype(float).to_numpy()
    if "batch_entropy_delta" in adata.obs.columns:
        df["batch_entropy_delta"] = adata.obs["batch_entropy_delta"].astype(float).to_numpy()
    return df


def _export_figure_data(
    adata,
    output_dir: Path,
    summary: dict,
    recipe: VisualizationRecipe,
    artifacts: list,
    context: dict,
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    batch_sizes = summary.get("batch_sizes", {})
    if not batch_sizes:
        batch_key = context.get("resolved_batch_key")
        if batch_key and batch_key in adata.obs.columns:
            batch_sizes = adata.obs[batch_key].astype(str).value_counts().to_dict()
    pd.DataFrame(
        [{"batch": batch, "n_cells": int(count)} for batch, count in batch_sizes.items()]
    ).to_csv(figure_data_dir / "batch_sizes.csv", index=False)

    metrics_df = pd.DataFrame(
        [
                {"metric": "batch_mixing_before", "value": summary["batch_mixing_before"]},
                {"metric": "batch_mixing_after", "value": summary["batch_mixing_after"]},
                {"metric": "batch_mixing_gain", "value": summary.get("batch_mixing_gain", 0.0)},
                {"metric": "method", "value": summary["method"]},
                {"metric": "n_batches", "value": summary.get("n_batches", len(batch_sizes))},
            ]
        )
    metrics_df.to_csv(figure_data_dir / "integration_metrics.csv", index=False)

    before_file = None
    before_df = _build_umap_export_table(
        adata,
        "X_umap_before_integration",
        batch_key=context.get("resolved_batch_key"),
        cluster_key=context.get("resolved_cluster_key"),
        entropy_column="batch_entropy_before",
    )
    if before_df is not None:
        before_file = "umap_before_points.csv"
        before_df.to_csv(figure_data_dir / before_file, index=False)

    after_file = None
    after_df = _build_umap_export_table(
        adata,
        "X_umap_after_integration",
        batch_key=context.get("resolved_batch_key"),
        cluster_key=context.get("resolved_cluster_key"),
        entropy_column="batch_entropy_after",
    )
    if after_df is not None:
        after_file = "umap_after_points.csv"
        after_df.to_csv(figure_data_dir / after_file, index=False)

    corrected_file = None
    embedding_key = summary.get("embedding_key")
    if summary.get("representation_type") == "embedding" and embedding_key in adata.obsm:
        embedding = np.asarray(adata.obsm[embedding_key])
        if embedding.shape[1] >= 2:
            corrected_df = pd.DataFrame(
                {
                    "observation": adata.obs_names,
                    "component_1": embedding[:, 0],
                    "component_2": embedding[:, 1],
                }
            )
            batch_key = context.get("resolved_batch_key")
            cluster_key = context.get("resolved_cluster_key")
            if batch_key and batch_key in adata.obs.columns:
                corrected_df["batch_label"] = adata.obs[batch_key].astype(str).to_numpy()
            if cluster_key and cluster_key in adata.obs.columns:
                corrected_df["cluster_label"] = adata.obs[cluster_key].astype(str).to_numpy()
            corrected_file = "corrected_embedding_points.csv"
            corrected_df.to_csv(figure_data_dir / corrected_file, index=False)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary["method"],
        "batch_key": context.get("resolved_batch_key"),
        "cluster_key": context.get("resolved_cluster_key"),
        "embedding_key": summary.get("embedding_key"),
        "representation_type": summary.get("representation_type"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": [spec.role for spec in recipe.plots],
        "available_files": {
            "batch_sizes": "batch_sizes.csv",
            "integration_metrics": "integration_metrics.csv",
            "umap_before_points": before_file,
            "umap_after_points": after_file,
            "corrected_embedding_points": corrected_file,
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
    summary: dict,
    *,
    batch_key: str | None = None,
    gallery_context: dict | None = None,
) -> list[str]:
    """Render the standard Python integration gallery and export figure-ready data."""
    context = gallery_context or _prepare_integration_gallery_context(
        adata,
        summary,
        batch_key=batch_key,
    )
    recipe = _build_integration_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        INTEGRATION_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-integrate"
        / "r_visualization"
        / "integration_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def _append_cli_flag(command: str, key: str, value) -> str:
    flag = f"--{str(key).replace('_', '-')}"
    if isinstance(value, bool):
        return f"{command} {flag}" if value else command
    if value in (None, ""):
        return command
    return f"{command} {flag} {shlex.quote(str(value))}"


def export_tables(
    output_dir: Path,
    summary: dict,
    *,
    adata=None,
    gallery_context: dict | None = None,
) -> list[str]:
    """Write stable integration tables for downstream analysis."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []
    path = tables_dir / "integration_metrics.csv"
    pd.DataFrame([{
        "metric": "batch_mixing_before", "value": summary["batch_mixing_before"],
    }, {
        "metric": "batch_mixing_after", "value": summary["batch_mixing_after"],
    }, {
        "metric": "batch_mixing_gain", "value": summary.get("batch_mixing_gain", 0.0),
    }, {
        "metric": "method", "value": summary["method"],
    }, {
        "metric": "n_batches", "value": summary["n_batches"],
    }]).to_csv(path, index=False)
    exported.append(str(path))

    path = tables_dir / "batch_sizes.csv"
    pd.DataFrame(
        [{"batch": batch, "n_cells": int(count)} for batch, count in summary["batch_sizes"].items()]
    ).to_csv(path, index=False)
    exported.append(str(path))

    if adata is not None:
        batch_key = gallery_context.get("resolved_batch_key") if gallery_context else None
        cluster_key = gallery_context.get("resolved_cluster_key") if gallery_context else None
        observations = pd.DataFrame(index=adata.obs_names)
        if batch_key in adata.obs.columns:
            observations["batch_label"] = adata.obs[batch_key].astype(str)
        if cluster_key and cluster_key in adata.obs.columns:
            observations["cluster_label"] = adata.obs[cluster_key].astype(str)
        for column in ("batch_entropy_before", "batch_entropy_after", "batch_entropy_delta"):
            if column in adata.obs.columns:
                observations[column] = adata.obs[column].astype(float).to_numpy()
        path = tables_dir / "integration_observations.csv"
        observations.reset_index().rename(columns={"index": "observation"}).to_csv(
            path,
            index=False,
        )
        exported.append(str(path))

    return exported


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
    *,
    adata=None,
    gallery_context: dict | None = None,
) -> None:
    """Write report.md and result.json."""

    header = generate_report_header(
        title="Spatial Multi-Sample Integration Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Batch key": params.get("batch_key", "batch"),
            "Representation": summary.get("embedding_key", "X_pca"),
        },
    )

    representation_label = (
        "Corrected graph"
        if summary.get("representation_type") == "neighbor_graph"
        else "Embedding"
    )
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Batches**: {summary['n_batches']}",
        f"- **Method**: {summary['method']}",
        f"- **{representation_label}**: `{summary['embedding_key']}`",
        f"- **Batch mixing gain**: {summary.get('batch_mixing_gain', 0.0):+.4f}",
        "",
        "### Batch Sizes\n",
        "| Batch | Cells |",
        "|-------|-------|",
    ]
    for b, n in summary["batch_sizes"].items():
        body_lines.append(f"| {b} | {n} |")

    body_lines.extend([
        "",
        "### Integration Quality\n",
        f"- **Batch mixing (before)**: {summary['batch_mixing_before']:.4f}",
        f"- **Batch mixing (after)**: {summary['batch_mixing_after']:.4f}",
        "",
        "Higher mixing entropy (0–1) indicates better batch mixing. "
        "A value of 1.0 means perfect mixing.",
    ])

    if summary.get("method") == "bbknn":
        body_lines.extend(
            [
                "",
                "**BBKNN note**: this method corrects the neighbour graph built from `X_pca`; "
                "it does not create a separate corrected latent embedding.",
            ]
        )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    effective_params = summary.get("effective_params", {})
    if effective_params:
        body_lines.extend(["", "### Effective Method Parameters\n"])
        for k, v in effective_params.items():
            body_lines.append(f"- `{k}`: {v}")

    body_lines.extend([
        "",
        "## Visualization Outputs\n",
        "- `figures/manifest.json`: Standard Python gallery manifest",
        "- `figure_data/`: Figure-ready CSV exports for downstream customization",
        "- `reproducibility/r_visualization.sh`: Optional R visualization entrypoint",
    ])

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "params": params,
        "effective_params": effective_params,
    }
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-integration-gallery",
            "batch_key": gallery_context.get("resolved_batch_key"),
            "cluster_key": gallery_context.get("resolved_cluster_key"),
            "embedding_key": summary.get("embedding_key"),
            "representation_type": summary.get("representation_type"),
        }
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary=summary, data=result_data,
        input_checksum=checksum,
    )


def write_reproducibility(output_dir: Path, params: dict, input_file: str | None) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--input <input.h5ad>' if input_file else '--demo'} "
        f"--output {shlex.quote(str(output_dir))}"
    )
    for k, v in params.items():
        cmd = _append_cli_flag(cmd, k, v)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "scipy"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            pass
    for opt in ["harmonypy", "bbknn", "scanorama"]:
        if is_available(opt):
            try:
                env_lines.append(f"{opt}=={_get_version(opt)}")
            except Exception:
                pass
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")
    _write_r_visualization_helper(output_dir)


# ---------------------------------------------------------------------------
# Demo data — create synthetic multi-batch data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate synthetic multi-batch data from preprocess demo."""
    import scanpy as sc

    main_runner = _PROJECT_ROOT / "omicsclaw.py"
    if not main_runner.exists():
        raise FileNotFoundError(f"OmicsClaw runner not found at {main_runner}")

    with tempfile.TemporaryDirectory(prefix="spatial_int_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Running spatial-preprocess --demo into %s", tmp_path)
        # Use centralized router instead of raw script execution
        result = subprocess.run(
            [sys.executable, str(main_runner), "run", "spatial-preprocess", "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed (exit {result.returncode}):\n{result.stderr}"
            )
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)

    rng = np.random.default_rng(42)
    adata.obs["batch"] = rng.choice(["batch_A", "batch_B", "batch_C"], size=adata.n_obs)
    adata.obs["batch"] = pd.Categorical(adata.obs["batch"])

    logger.info("Demo: %d cells, batches=%s", adata.n_obs, adata.obs["batch"].cat.categories.tolist())
    return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.harmony_theta < 0:
        parser.error("--harmony-theta must be >= 0")
    if args.harmony_lambda != -1 and args.harmony_lambda <= 0:
        parser.error("--harmony-lambda must be > 0, or -1 to enable Harmony auto-lambda estimation")
    if args.harmony_max_iter < 1:
        parser.error("--harmony-max-iter must be >= 1")

    if args.bbknn_neighbors_within_batch < 1:
        parser.error("--bbknn-neighbors-within-batch must be >= 1")
    if args.bbknn_n_pcs < 1:
        parser.error("--bbknn-n-pcs must be >= 1")
    if args.bbknn_trim is not None and args.bbknn_trim < 0:
        parser.error("--bbknn-trim must be >= 0")

    if args.scanorama_knn < 1:
        parser.error("--scanorama-knn must be >= 1")
    if args.scanorama_sigma <= 0:
        parser.error("--scanorama-sigma must be > 0")
    if args.scanorama_alpha < 0:
        parser.error("--scanorama-alpha must be >= 0")
    if args.scanorama_batch_size < 1:
        parser.error("--scanorama-batch-size must be >= 1")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    params = {
        "method": args.method,
        "batch_key": args.batch_key,
    }

    if args.method == "harmony":
        params.update(
            {
                "harmony_theta": args.harmony_theta,
                "harmony_lambda": args.harmony_lambda,
                "harmony_max_iter": args.harmony_max_iter,
            }
        )
        method_kwargs = {
            "theta": args.harmony_theta,
            "lamb": args.harmony_lambda,
            "max_iter_harmony": args.harmony_max_iter,
        }
    elif args.method == "bbknn":
        params.update(
            {
                "bbknn_neighbors_within_batch": args.bbknn_neighbors_within_batch,
                "bbknn_n_pcs": args.bbknn_n_pcs,
                "bbknn_trim": args.bbknn_trim,
            }
        )
        method_kwargs = {
            "neighbors_within_batch": args.bbknn_neighbors_within_batch,
            "n_pcs": args.bbknn_n_pcs,
            "trim": args.bbknn_trim,
        }
    elif args.method == "scanorama":
        params.update(
            {
                "scanorama_knn": args.scanorama_knn,
                "scanorama_sigma": args.scanorama_sigma,
                "scanorama_alpha": args.scanorama_alpha,
                "scanorama_batch_size": args.scanorama_batch_size,
            }
        )
        method_kwargs = {
            "knn": args.scanorama_knn,
            "sigma": args.scanorama_sigma,
            "alpha": args.scanorama_alpha,
            "batch_size": args.scanorama_batch_size,
        }
    else:
        method_kwargs = {}

    return params, method_kwargs


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Integrate — multi-sample batch integration",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", default="harmony",
        choices=list(SUPPORTED_METHODS),
    )
    parser.add_argument("--batch-key", default="batch")
    parser.add_argument(
        "--harmony-theta",
        type=float,
        default=METHOD_PARAM_DEFAULTS["harmony"]["theta"],
        help="Harmony diversity clustering penalty; higher values encourage stronger batch mixing.",
    )
    parser.add_argument(
        "--harmony-lambda",
        type=float,
        default=METHOD_PARAM_DEFAULTS["harmony"]["lambda"],
        help="Harmony ridge penalty. Set -1 to enable automatic lambda estimation.",
    )
    parser.add_argument(
        "--harmony-max-iter",
        type=int,
        default=METHOD_PARAM_DEFAULTS["harmony"]["max_iter_harmony"],
        help="Maximum number of Harmony outer iterations.",
    )
    parser.add_argument(
        "--bbknn-neighbors-within-batch",
        type=int,
        default=METHOD_PARAM_DEFAULTS["bbknn"]["neighbors_within_batch"],
        help="Number of neighbours BBKNN draws from each batch.",
    )
    parser.add_argument(
        "--bbknn-n-pcs",
        type=int,
        default=METHOD_PARAM_DEFAULTS["bbknn"]["n_pcs"],
        help="Number of principal components used to build the BBKNN graph.",
    )
    parser.add_argument(
        "--bbknn-trim",
        type=int,
        default=METHOD_PARAM_DEFAULTS["bbknn"]["trim"],
        help="Optional post-processing trim parameter for BBKNN; omit to keep the package default.",
    )
    parser.add_argument(
        "--scanorama-knn",
        type=int,
        default=METHOD_PARAM_DEFAULTS["scanorama"]["knn"],
        help="Number of neighbours used by Scanorama while matching batches.",
    )
    parser.add_argument(
        "--scanorama-sigma",
        type=float,
        default=METHOD_PARAM_DEFAULTS["scanorama"]["sigma"],
        help="Gaussian kernel width for smoothing Scanorama correction vectors.",
    )
    parser.add_argument(
        "--scanorama-alpha",
        type=float,
        default=METHOD_PARAM_DEFAULTS["scanorama"]["alpha"],
        help="Minimum alignment score cutoff for accepting Scanorama matches.",
    )
    parser.add_argument(
        "--scanorama-batch-size",
        type=int,
        default=METHOD_PARAM_DEFAULTS["scanorama"]["batch_size"],
        help="Incremental alignment batch size for Scanorama on large datasets.",
    )
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        import scanpy as sc

        input_path = Path(args.input_path)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    params, method_kwargs = _collect_run_configuration(args)
    summary = run_integration(
        adata,
        method=args.method,
        batch_key=args.batch_key,
        **method_kwargs,
    )

    adata.uns["spatial_integration_summary"] = summary.copy()
    gallery_context = _prepare_integration_gallery_context(
        adata,
        summary,
        batch_key=args.batch_key,
    )
    generate_figures(
        adata,
        output_dir,
        summary,
        batch_key=args.batch_key,
        gallery_context=gallery_context,
    )
    export_tables(
        output_dir,
        summary,
        adata=adata,
        gallery_context=gallery_context,
    )
    write_report(
        output_dir,
        summary,
        input_file,
        params,
        adata=adata,
        gallery_context=gallery_context,
    )
    write_reproducibility(output_dir, params, input_file)

    store_analysis_metadata(
        adata, SKILL_NAME, summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Integration complete ({summary['method']}): "
        f"{summary['n_batches']} batches, "
        f"mixing {summary['batch_mixing_before']:.3f} → {summary['batch_mixing_after']:.3f}"
    )


if __name__ == "__main__":
    main()
