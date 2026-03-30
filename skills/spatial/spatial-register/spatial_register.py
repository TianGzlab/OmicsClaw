#!/usr/bin/env python3
"""Spatial Register — multi-slice alignment and spatial registration."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import subprocess
import sys
import tempfile
import warnings
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs

ensure_runtime_cache_dirs("omicsclaw")

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.register import (
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    VALID_PASTE_DISSIMILARITIES,
    detect_slice_key,
    run_registration,
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

SKILL_NAME = "spatial-register"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-register/spatial_register.py"


# ---------------------------------------------------------------------------
# Gallery helpers
# ---------------------------------------------------------------------------


def _append_cli_flag(command: str, key: str, value: Any) -> str:
    flag = f"--{key.replace('_', '-')}"
    if isinstance(value, bool):
        return f"{command} {flag}" if value else command
    if value in (None, ""):
        return command
    return f"{command} {flag} {shlex.quote(str(value))}"


def _prepare_register_plot_state(adata, slice_key: str) -> str | None:
    spatial_key = get_spatial_key(adata)
    if spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = np.asarray(adata.obsm["X_spatial"]).copy()
        spatial_key = "spatial"
    elif spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = np.asarray(adata.obsm["spatial"]).copy()

    if slice_key in adata.obs.columns and not isinstance(adata.obs[slice_key].dtype, pd.CategoricalDtype):
        adata.obs[slice_key] = pd.Categorical(adata.obs[slice_key].astype(str))

    return spatial_key


def _annotate_registration_metrics_to_obs(adata, summary: dict[str, Any]) -> dict[str, str]:
    if "spatial" not in adata.obsm or "spatial_aligned" not in adata.obsm:
        return {}

    shift_col = "registration_shift_distance"
    reference_col = "registration_is_reference_slice"

    original = np.asarray(adata.obsm["spatial"], dtype=float)
    aligned = np.asarray(adata.obsm["spatial_aligned"], dtype=float)
    adata.obs[shift_col] = np.linalg.norm(aligned - original, axis=1)

    slice_key = summary.get("slice_key")
    reference_slice = str(summary.get("reference_slice"))
    if slice_key in adata.obs.columns:
        adata.obs[reference_col] = adata.obs[slice_key].astype(str) == reference_slice

    return {
        "shift_distance_col": shift_col,
        "reference_slice_col": reference_col,
    }


def _build_shift_summary_table(adata, summary: dict[str, Any], context: dict[str, Any]) -> pd.DataFrame:
    slice_key = summary.get("slice_key")
    shift_col = context.get("shift_distance_col")
    reference_col = context.get("reference_slice_col")
    if slice_key not in adata.obs.columns or not shift_col or shift_col not in adata.obs.columns:
        return pd.DataFrame(
            columns=["slice", "n_observations", "mean_shift", "median_shift", "max_shift", "is_reference"]
        )

    df = pd.DataFrame(
        {
            "slice": adata.obs[slice_key].astype(str).to_numpy(),
            "shift_distance": pd.to_numeric(adata.obs[shift_col], errors="coerce").fillna(0.0).to_numpy(),
            "is_reference": (
                adata.obs[reference_col].astype(bool).to_numpy()
                if reference_col in adata.obs.columns
                else np.zeros(adata.n_obs, dtype=bool)
            ),
        }
    )
    summary_df = (
        df.groupby("slice", observed=True)
        .agg(
            n_observations=("slice", "size"),
            mean_shift=("shift_distance", "mean"),
            median_shift=("shift_distance", "median"),
            max_shift=("shift_distance", "max"),
            is_reference=("is_reference", "max"),
        )
        .reset_index()
    )
    summary_df["is_reference"] = summary_df["is_reference"].astype(bool)
    return summary_df.sort_values(
        by=["is_reference", "slice"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def _build_disparity_table(summary: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"slice": str(slice_name), "disparity": float(value)}
        for slice_name, value in summary.get("disparities", {}).items()
    ]
    if not rows:
        return pd.DataFrame(columns=["slice", "disparity"])
    return pd.DataFrame(rows).sort_values(by="slice", kind="mergesort").reset_index(drop=True)


def _build_registration_metrics_table(shift_summary_df: pd.DataFrame, disparity_df: pd.DataFrame) -> pd.DataFrame:
    if shift_summary_df.empty and disparity_df.empty:
        return pd.DataFrame(
            columns=[
                "slice",
                "n_observations",
                "mean_shift",
                "median_shift",
                "max_shift",
                "is_reference",
                "disparity",
            ]
        )

    if shift_summary_df.empty:
        metrics_df = disparity_df.copy()
        metrics_df["n_observations"] = np.nan
        metrics_df["mean_shift"] = np.nan
        metrics_df["median_shift"] = np.nan
        metrics_df["max_shift"] = np.nan
        metrics_df["is_reference"] = False
        return metrics_df[
            ["slice", "n_observations", "mean_shift", "median_shift", "max_shift", "is_reference", "disparity"]
        ]

    metrics_df = shift_summary_df.copy()
    if disparity_df.empty:
        metrics_df["disparity"] = np.nan
    else:
        metrics_df = metrics_df.merge(disparity_df, on="slice", how="left")
    return metrics_df


def _build_registration_points_table(adata, summary: dict[str, Any], context: dict[str, Any]) -> pd.DataFrame:
    slice_key = summary.get("slice_key")
    shift_col = context.get("shift_distance_col")
    reference_col = context.get("reference_slice_col")

    original = np.asarray(adata.obsm["spatial"], dtype=float)
    aligned = np.asarray(adata.obsm["spatial_aligned"], dtype=float)

    df = pd.DataFrame(
        {
            "observation": adata.obs_names.astype(str),
            "slice": adata.obs[slice_key].astype(str).to_numpy() if slice_key in adata.obs.columns else "",
            "original_x": original[:, 0],
            "original_y": original[:, 1],
            "aligned_x": aligned[:, 0],
            "aligned_y": aligned[:, 1],
            "delta_x": aligned[:, 0] - original[:, 0],
            "delta_y": aligned[:, 1] - original[:, 1],
        }
    )
    if shift_col and shift_col in adata.obs.columns:
        df["shift_distance"] = pd.to_numeric(adata.obs[shift_col], errors="coerce").fillna(0.0).to_numpy()
    if reference_col and reference_col in adata.obs.columns:
        df["is_reference_slice"] = adata.obs[reference_col].astype(bool).to_numpy()
    return df


def _build_run_summary_table(summary: dict[str, Any], context: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "slice_key", "value": summary.get("slice_key")},
        {"metric": "reference_slice", "value": summary.get("reference_slice")},
        {"metric": "n_slices", "value": summary.get("n_slices")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "n_common_genes", "value": summary.get("n_common_genes")},
        {"metric": "mean_disparity", "value": summary.get("mean_disparity")},
        {"metric": "spatial_key", "value": context.get("spatial_key")},
        {"metric": "aligned_key", "value": "spatial_aligned" if context.get("has_aligned") else None},
        {"metric": "shift_distance_column", "value": context.get("shift_distance_col")},
        {"metric": "reference_slice_column", "value": context.get("reference_slice_col")},
    ]

    effective_params = summary.get("effective_params", {})
    for key, value in effective_params.items():
        rows.append({"metric": key, "value": value})

    stalign_params = summary.get("stalign_params")
    if stalign_params:
        for key, value in stalign_params.items():
            rows.append({"metric": f"stalign_runtime_{key}", "value": value})

    return pd.DataFrame(rows)


def _prepare_register_gallery_context(adata, summary: dict[str, Any]) -> dict[str, Any]:
    slice_key = summary.get("slice_key", "slice")
    spatial_key = _prepare_register_plot_state(adata, slice_key)
    context = {
        "spatial_key": spatial_key,
        "slice_key": slice_key,
        "has_aligned": "spatial_aligned" in adata.obsm,
    }
    context.update(_annotate_registration_metrics_to_obs(adata, summary))
    context["shift_summary_df"] = _build_shift_summary_table(adata, summary, context)
    context["disparity_df"] = _build_disparity_table(summary)
    context["metrics_df"] = _build_registration_metrics_table(
        context["shift_summary_df"],
        context["disparity_df"],
    )
    context["points_df"] = _build_registration_points_table(adata, summary, context)
    return context


def _build_register_visualization_recipe(adata, summary: dict[str, Any], context: dict[str, Any]) -> VisualizationRecipe:
    plots: list[PlotSpec] = []
    slice_key = summary.get("slice_key")
    shift_col = context.get("shift_distance_col")

    if slice_key in adata.obs.columns and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="registration_slices_before",
                role="overview",
                renderer="feature_map",
                filename="slices_before.png",
                title="Slices Before Registration",
                description="Observed slice labels projected onto the original spatial coordinates.",
                params={
                    "feature": slice_key,
                    "basis": "spatial",
                    "coords_key": "spatial",
                    "colormap": "tab10",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (10, 8),
                },
                required_obs=[slice_key],
                required_obsm=["spatial"],
            )
        )

    if slice_key in adata.obs.columns and "spatial_aligned" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="registration_slices_after",
                role="overview",
                renderer="feature_map",
                filename="slices_after.png",
                title="Slices After Registration",
                description="Observed slice labels projected onto the aligned coordinate frame.",
                params={
                    "feature": slice_key,
                    "basis": "spatial",
                    "coords_key": "spatial_aligned",
                    "colormap": "tab10",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (10, 8),
                },
                required_obs=[slice_key],
                required_obsm=["spatial_aligned"],
            )
        )

    if shift_col and shift_col in adata.obs.columns and "spatial_aligned" in adata.obsm:
        plots.append(
            PlotSpec(
                plot_id="registration_shift_map",
                role="diagnostic",
                renderer="feature_map",
                filename="registration_shift_map.png",
                title="Registration Shift Magnitude",
                description="Per-observation coordinate displacement after alignment.",
                params={
                    "feature": shift_col,
                    "basis": "spatial",
                    "coords_key": "spatial_aligned",
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (10, 8),
                },
                required_obs=[shift_col],
                required_obsm=["spatial_aligned"],
            )
        )

    if not context["shift_summary_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="registration_shift_summary",
                role="supporting",
                renderer="shift_summary_barplot",
                filename="registration_shift_by_slice.png",
                title="Per-Slice Shift Summary",
                description="Mean and maximum coordinate displacement for each slice after alignment.",
            )
        )

    if not context["disparity_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="registration_disparity_summary",
                role="supporting",
                renderer="disparity_barplot",
                filename="registration_disparities.png",
                title="Per-Slice Registration Disparity",
                description="Method-reported disparity values for non-reference slices when available.",
            )
        )

    if not context["points_df"].empty and context.get("shift_distance_col"):
        plots.append(
            PlotSpec(
                plot_id="registration_shift_distribution",
                role="uncertainty",
                renderer="shift_distribution",
                filename="registration_shift_distribution.png",
                title="Shift Distance Distribution",
                description="Distribution of alignment displacement magnitudes across slices.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-register-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Register Standard Gallery",
        description=(
            "Default OmicsClaw registration story plots: slice overlays before and after alignment, "
            "displacement diagnostics, per-slice summaries, and uncertainty panels."
        ),
        plots=plots,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict[str, Any]) -> object:
    params = dict(spec.params)
    coords_key = params.pop("coords_key", "spatial")
    viz_params = VizParams(**params)

    if coords_key in (None, "spatial"):
        return plot_features(adata, viz_params)

    if coords_key not in adata.obsm:
        return None

    original_spatial = adata.obsm.get("spatial")
    try:
        adata.obsm["spatial"] = np.asarray(adata.obsm[coords_key]).copy()
        return plot_features(adata, viz_params)
    finally:
        if original_spatial is None:
            del adata.obsm["spatial"]
        else:
            adata.obsm["spatial"] = original_spatial


def _render_shift_summary_barplot(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    shift_summary_df = context.get("shift_summary_df", pd.DataFrame())
    if shift_summary_df.empty:
        return None

    plot_df = shift_summary_df.iloc[::-1].copy()
    y = np.arange(len(plot_df))
    colors = ["#1b9e77" if bool(value) else "#3182bd" for value in plot_df["is_reference"]]

    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.8, max(4.5, len(plot_df) * 0.55))),
        dpi=200,
    )
    ax.barh(y, plot_df["mean_shift"], color=colors, alpha=0.85, label="Mean shift")
    ax.scatter(plot_df["max_shift"], y, color="#cb181d", s=34, label="Max shift", zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(plot_df["slice"].astype(str))
    ax.set_xlabel("Coordinate displacement")
    ax.set_title(spec.title or "Per-Slice Shift Summary")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def _render_disparity_barplot(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    disparity_df = context.get("disparity_df", pd.DataFrame())
    if disparity_df.empty:
        return None

    plot_df = disparity_df.iloc[::-1].copy()
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.0, max(4.2, len(plot_df) * 0.55))),
        dpi=200,
    )
    ax.barh(plot_df["slice"].astype(str), plot_df["disparity"], color="#756bb1")
    ax.set_xlabel("Disparity")
    ax.set_title(spec.title or "Per-Slice Registration Disparity")
    fig.tight_layout()
    return fig


def _render_shift_distribution(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    import matplotlib.pyplot as plt

    points_df = context.get("points_df", pd.DataFrame())
    if points_df.empty or "shift_distance" not in points_df.columns:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8.6, 5.2)), dpi=200)
    for idx, (slice_name, group_df) in enumerate(points_df.groupby("slice", sort=True)):
        ax.hist(
            group_df["shift_distance"],
            bins=25,
            histtype="step",
            linewidth=1.6,
            alpha=0.9,
            label=str(slice_name),
        )
    ax.set_xlabel("Shift distance")
    ax.set_ylabel("Number of cells or spots")
    ax.set_title(spec.title or "Shift Distance Distribution")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


REGISTER_GALLERY_RENDERERS = {
    "feature_map": _render_feature_map,
    "shift_summary_barplot": _render_shift_summary_barplot,
    "disparity_barplot": _render_disparity_barplot,
    "shift_distribution": _render_shift_distribution,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def _export_figure_data(
    output_dir: Path,
    summary: dict[str, Any],
    recipe: VisualizationRecipe,
    artifacts: list[Any],
    context: dict[str, Any],
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    points_df = context["points_df"]
    shift_summary_df = context["shift_summary_df"]
    disparity_df = context["disparity_df"]
    run_summary_df = _build_run_summary_table(summary, context)

    points_df.to_csv(figure_data_dir / "registration_points.csv", index=False)
    shift_summary_df.to_csv(figure_data_dir / "registration_shift_by_slice.csv", index=False)
    run_summary_df.to_csv(figure_data_dir / "registration_run_summary.csv", index=False)

    disparity_file = None
    if not disparity_df.empty:
        disparity_file = "registration_disparities.csv"
        disparity_df.to_csv(figure_data_dir / disparity_file, index=False)

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "slice_key": summary.get("slice_key"),
        "reference_slice": summary.get("reference_slice"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "available_files": {
            "registration_points": "registration_points.csv",
            "registration_shift_by_slice": "registration_shift_by_slice.csv",
            "registration_disparities": disparity_file,
            "registration_run_summary": "registration_run_summary.csv",
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


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(
    adata,
    output_dir: Path,
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> list[str]:
    """Render the standard registration gallery and export figure-ready data."""
    context = gallery_context or _prepare_register_gallery_context(adata, summary)
    recipe = _build_register_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        REGISTER_GALLERY_RENDERERS,
        context=runtime_context,
    )
    _export_figure_data(output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


# ---------------------------------------------------------------------------
# Report / exports
# ---------------------------------------------------------------------------


def export_tables(
    output_dir: Path,
    summary: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
    adata=None,
) -> list[str]:
    """Export tabular outputs."""
    if gallery_context is not None:
        context = gallery_context
    elif adata is not None:
        context = _prepare_register_gallery_context(adata, summary)
    else:
        context = {}

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []

    registration_summary_df = pd.DataFrame(
        [
            {"metric": "method", "value": summary.get("method")},
            {"metric": "mean_disparity", "value": summary.get("mean_disparity")},
            {"metric": "n_common_genes", "value": summary.get("n_common_genes", 0)},
            {"metric": "n_slices", "value": summary.get("n_slices")},
            {"metric": "reference_slice", "value": summary.get("reference_slice")},
            {"metric": "slice_key", "value": summary.get("slice_key")},
        ]
    )
    path = tables_dir / "registration_summary.csv"
    registration_summary_df.to_csv(path, index=False)
    exported.append(str(path))

    metrics_df = context.get("metrics_df")
    if metrics_df is None:
        metrics_df = _build_registration_metrics_table(
            context.get("shift_summary_df", pd.DataFrame()),
            context.get("disparity_df", pd.DataFrame()),
        )
    path = tables_dir / "registration_metrics.csv"
    metrics_df.to_csv(path, index=False)
    exported.append(str(path))

    return exported


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-register"
        / "r_visualization"
        / "register_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def write_report(
    output_dir: Path,
    summary: dict[str, Any],
    input_file: str | None,
    params: dict[str, Any],
    *,
    gallery_context: dict[str, Any] | None = None,
) -> None:
    context = gallery_context or {}
    shift_summary_df = context.get("shift_summary_df", pd.DataFrame())
    disparity_df = context.get("disparity_df", pd.DataFrame())

    header = generate_report_header(
        title="Spatial Registration Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", "paste"),
            "Reference slice": summary.get("reference_slice", "auto"),
            "Slices": str(summary.get("n_slices", 0)),
            "Slice key": summary.get("slice_key", params.get("slice_key", "auto")),
        },
    )

    effective_params = summary.get("effective_params", {})
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Slice key**: {summary['slice_key']}",
        f"- **Reference slice**: {summary['reference_slice']}",
        f"- **Slices aligned**: {summary['n_slices']}",
        f"- **Mean disparity**: {summary['mean_disparity']:.6f}",
        "- **Aligned coordinates**: `adata.obsm['spatial_aligned']`",
    ]
    if summary.get("n_common_genes"):
        body_lines.append(f"- **Common genes used**: {summary['n_common_genes']}")
    if context.get("shift_distance_col"):
        body_lines.append(f"- **Shift-distance column**: `{context['shift_distance_col']}`")

    if not disparity_df.empty:
        body_lines.extend(
            [
                "",
                "### Per-Slice Alignment Score\n",
                "| Slice | Alignment Score |",
                "|-------|-----------------|",
            ]
        )
        for row in disparity_df.itertuples():
            body_lines.append(f"| {row.slice} | {float(row.disparity):.6f} |")
        body_lines.extend(
            [
                "",
                "Current OmicsClaw PASTE reporting uses a transport-matrix-derived alignment score proxy for non-reference slices.",
            ]
        )

    if not shift_summary_df.empty:
        body_lines.extend(
            [
                "",
                "### Per-Slice Shift Summary\n",
                "| Slice | N observations | Mean shift | Median shift | Max shift | Reference |",
                "|-------|----------------|------------|--------------|-----------|-----------|",
            ]
        )
        for row in shift_summary_df.itertuples():
            body_lines.append(
                f"| {row.slice} | {int(row.n_observations)} | {float(row.mean_shift):.4f} | "
                f"{float(row.median_shift):.4f} | {float(row.max_shift):.4f} | {bool(row.is_reference)} |"
            )

    stalign_params = summary.get("stalign_params")
    if stalign_params:
        body_lines.extend(
            [
                "",
                "### STalign Runtime Details\n",
                f"- **Image size**: {stalign_params.get('image_size')}",
                f"- **LDDMM iterations**: {stalign_params.get('niter')}",
                f"- **Kernel bandwidth (a)**: {stalign_params.get('a')}",
                f"- **Expression-derived signal**: {stalign_params.get('use_expression')}",
                f"- **Signal type used**: {stalign_params.get('signal_type')}",
                f"- **Device**: {stalign_params.get('device')}",
            ]
        )

    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    if effective_params:
        body_lines.extend(["", "### Effective Method Parameters\n"])
        for key, value in effective_params.items():
            body_lines.append(f"- `{key}`: {value}")

    body_lines.extend(
        [
            "",
            "## Interpretation Notes\n",
            "- `spatial_aligned` stores the registered coordinate system, while the original spatial coordinates remain available for comparison.",
            "- `paste` is not a coordinates-only alignment. It combines expression dissimilarity with spatial distance and should be interpreted as an expression-aware transport alignment.",
            "- `registration_shift_distance` summarizes how far each observation moved during registration; large shifts can indicate strong slice mismatch, large deformation, or heavy transport between coordinate frames.",
        ]
    )

    body_lines.extend(
        [
            "",
            "## Visualization Outputs\n",
            "- `figures/manifest.json`: Standard Python gallery manifest",
            "- `figure_data/`: Figure-ready CSV exports for downstream customization",
            "- `reproducibility/r_visualization.sh`: Optional R visualization entrypoint",
        ]
    )

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data: dict[str, Any] = {
        "params": params,
        "effective_params": effective_params,
        **summary,
    }
    result_data["visualization"] = {
        "recipe_id": "standard-spatial-register-gallery",
        "slice_column": summary.get("slice_key"),
        "spatial_key": context.get("spatial_key"),
        "aligned_coordinate_key": "spatial_aligned" if context.get("has_aligned") else None,
        "shift_distance_column": context.get("shift_distance_col"),
        "reference_slice_column": context.get("reference_slice_col"),
    }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data=result_data,
        input_checksum=checksum,
    )


def write_reproducibility(
    output_dir: Path,
    params: dict[str, Any],
    summary: dict[str, Any],
    *,
    input_file: str | None,
    demo_mode: bool = False,
) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--demo' if demo_mode else '--input <input.h5ad>'} "
        f"--output {shlex.quote(str(output_dir))}"
    )
    repro_params = {
        "method": params.get("method"),
        "slice_key": summary.get("slice_key", params.get("slice_key")),
        "reference_slice": summary.get("reference_slice", params.get("reference_slice")),
    }
    repro_params.update(summary.get("effective_params", {}))
    for key, value in repro_params.items():
        command = _append_cli_flag(command, key, value)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n")

    try:
        from importlib.metadata import version as get_version
    except ImportError:
        from importlib_metadata import version as get_version  # type: ignore

    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "scipy", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            pass
        except Exception:
            pass

    optional_by_method = {
        "paste": ["paste-bio", "pot", "torch"],
        "stalign": ["STalign", "torch"],
    }
    for pkg in optional_by_method.get(summary["method"], []):
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            pass
        except Exception:
            pass
    (repro_dir / "environment.txt").write_text("\n".join(env_lines) + ("\n" if env_lines else ""))
    _write_r_visualization_helper(output_dir)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Spatial Register — multi-slice alignment and registration",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="paste", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--slice-key", default=None, help="obs column containing slice labels")
    parser.add_argument(
        "--reference-slice",
        default=None,
        help="Slice label to use as reference (default: first detected slice)",
    )
    parser.add_argument(
        "--paste-alpha",
        type=float,
        default=METHOD_PARAM_DEFAULTS["paste"]["alpha"],
    )
    parser.add_argument(
        "--paste-dissimilarity",
        default=METHOD_PARAM_DEFAULTS["paste"]["dissimilarity"],
        choices=list(VALID_PASTE_DISSIMILARITIES),
    )
    parser.add_argument(
        "--paste-use-gpu",
        action="store_true",
        default=METHOD_PARAM_DEFAULTS["paste"]["use_gpu"],
    )
    parser.add_argument(
        "--stalign-niter",
        type=int,
        default=METHOD_PARAM_DEFAULTS["stalign"]["niter"],
    )
    parser.add_argument(
        "--stalign-image-size",
        type=int,
        default=METHOD_PARAM_DEFAULTS["stalign"]["image_size"],
    )
    parser.add_argument(
        "--stalign-a",
        type=float,
        default=METHOD_PARAM_DEFAULTS["stalign"]["a"],
    )
    parser.add_argument(
        "--use-expression",
        action="store_true",
        default=METHOD_PARAM_DEFAULTS["stalign"]["use_expression"],
    )
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.demo:
        if not args.input_path:
            parser.error("Provide --input or --demo")
        if args.input_path and not Path(args.input_path).exists():
            parser.error(f"Input file not found: {args.input_path}")

    if args.paste_alpha < 0 or args.paste_alpha > 1:
        parser.error("--paste-alpha must be in [0, 1]")
    if args.stalign_niter <= 0:
        parser.error("--stalign-niter must be > 0")
    if args.stalign_image_size <= 0:
        parser.error("--stalign-image-size must be > 0")
    if args.stalign_a <= 0:
        parser.error("--stalign-a must be > 0")


def _resolve_slice_column(adata, requested_key: str | None) -> str:
    if requested_key:
        if requested_key not in adata.obs.columns:
            raise ValueError(f"Slice key '{requested_key}' not found in adata.obs")
        if adata.obs[requested_key].nunique() < 2:
            raise ValueError(f"Slice key '{requested_key}' must contain at least 2 slices")
        return requested_key

    detected = detect_slice_key(adata)
    if detected is None:
        raise ValueError(
            "Could not detect a slice label column automatically. "
            "Provide --slice-key with a column such as `slice`, `sample`, `section`, `batch`, or `sample_id`."
        )
    return detected


def _validate_reference_slice(adata, slice_key: str, reference_slice: str | None) -> None:
    if reference_slice is None:
        return
    values = adata.obs[slice_key].astype(str)
    if str(reference_slice) not in set(values):
        raise ValueError(
            f"Reference slice '{reference_slice}' not found in '{slice_key}'. "
            f"Available: {sorted(values.unique().tolist())}"
        )


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    params: dict[str, Any] = {
        "method": args.method,
        "slice_key": args.slice_key,
        "reference_slice": args.reference_slice,
    }
    method_kwargs: dict[str, Any] = {}

    if args.method == "paste":
        params.update(
            {
                "paste_alpha": args.paste_alpha,
                "paste_dissimilarity": args.paste_dissimilarity,
                "paste_use_gpu": args.paste_use_gpu,
            }
        )
        method_kwargs.update(
            {
                "alpha": args.paste_alpha,
                "dissimilarity": args.paste_dissimilarity,
                "use_gpu": args.paste_use_gpu,
            }
        )
    else:
        params.update(
            {
                "stalign_niter": args.stalign_niter,
                "stalign_image_size": args.stalign_image_size,
                "stalign_a": args.stalign_a,
                "use_expression": args.use_expression,
            }
        )
        method_kwargs.update(
            {
                "image_size": (args.stalign_image_size, args.stalign_image_size),
                "niter": args.stalign_niter,
                "a": args.stalign_a,
                "use_expression": args.use_expression,
            }
        )

    return params, method_kwargs


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo and synthesize multi-slice data."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_reg_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Running spatial-preprocess --demo into %s", tmp_path)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=180,
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
    n_obs = adata.n_obs
    half = n_obs // 2
    slice_labels = ["slice_1"] * half + ["slice_2"] * (n_obs - half)
    rng.shuffle(slice_labels)
    adata.obs["slice"] = pd.Categorical(slice_labels)

    if "spatial" in adata.obsm:
        coords = adata.obsm["spatial"].copy().astype(float)
        mask = np.array(slice_labels) == "slice_2"
        coords[mask] += rng.uniform(50, 150, size=(mask.sum(), 2))
        adata.obsm["spatial"] = coords
        if "X_spatial" in adata.obsm:
            adata.obsm["X_spatial"] = coords.copy()

    logger.info("Demo: %d cells, slices=%s", n_obs, adata.obs["slice"].cat.categories.tolist())
    return adata, None


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    else:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path

    resolved_slice_key = _resolve_slice_column(adata, args.slice_key)
    _validate_reference_slice(adata, resolved_slice_key, args.reference_slice)
    params, method_kwargs = _collect_run_configuration(args)
    params["slice_key"] = resolved_slice_key

    summary = run_registration(
        adata,
        method=args.method,
        slice_key=resolved_slice_key,
        reference_slice=args.reference_slice,
        **method_kwargs,
    )

    gallery_context = _prepare_register_gallery_context(adata, summary)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, summary, gallery_context=gallery_context, adata=adata)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, summary, input_file=input_file, demo_mode=args.demo)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params={"visualization_recipe": "standard-spatial-register-gallery", **params},
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(
        f"Registration complete ({summary['method']}): "
        f"{summary['n_slices']} slices aligned to '{summary['reference_slice']}', "
        f"mean disparity={summary['mean_disparity']:.4f}"
    )


if __name__ == "__main__":
    main()
