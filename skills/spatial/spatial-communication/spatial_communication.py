#!/usr/bin/env python3
"""Spatial Communication — ligand-receptor interaction analysis.

Supported methods:
  liana        LIANA+ multi-method consensus ranking (default)
  cellphonedb  CellPhoneDB statistical permutation test
  fastccc      FastCCC permutation-free communication analysis
  cellchat_r   CellChat via R
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
from importlib.metadata import PackageNotFoundError
from pathlib import Path

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
from skills.spatial._lib.communication import (
    METHOD_PARAM_DEFAULTS,
    SUPPORTED_METHODS,
    SUPPORTED_SPECIES,
    run_communication,
)
from skills.spatial._lib.dependency_manager import is_available
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_communication,
    plot_features,
    render_plot_specs,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-communication"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-communication/spatial_communication.py"


# ---------------------------------------------------------------------------
# Gallery helpers
# ---------------------------------------------------------------------------


def _prepare_communication_plot_state(adata) -> str | None:
    """Ensure communication outputs are plot-ready."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()
    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute a fallback UMAP for the standard communication gallery."""
    if "X_umap" in adata.obsm or adata.n_obs < 3:
        return

    try:
        if "connectivities" not in adata.obsp:
            n_neighbors = max(2, min(15, adata.n_obs - 1))
            if "X_pca" in adata.obsm:
                sc.pp.neighbors(adata, use_rep="X_pca", n_neighbors=n_neighbors)
            else:
                sc.pp.neighbors(adata, n_neighbors=n_neighbors)
        sc.tl.umap(adata)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Could not compute UMAP for communication gallery: %s", exc)


def _annotate_signaling_roles_to_obs(adata, summary: dict) -> dict[str, str]:
    """Map cell-type-level signaling roles back onto observations."""
    roles_df = summary.get("signaling_roles_df", pd.DataFrame())
    cell_type_key = summary.get("cell_type_key")
    if roles_df.empty or cell_type_key not in adata.obs.columns:
        return {}

    role_lookup = roles_df.copy()
    role_lookup["cell_type"] = role_lookup["cell_type"].astype(str)
    role_lookup = role_lookup.drop_duplicates(subset=["cell_type"]).set_index("cell_type")
    cell_type_labels = adata.obs[cell_type_key].astype(str)

    mapping = {
        "role_col": ("dominant_role", "communication_role"),
        "sender_score_col": ("sender_score", "communication_sender_score"),
        "receiver_score_col": ("receiver_score", "communication_receiver_score"),
        "hub_score_col": ("hub_score", "communication_hub_score"),
        "outgoing_col": ("n_outgoing", "communication_n_outgoing"),
        "incoming_col": ("n_incoming", "communication_n_incoming"),
    }

    resolved: dict[str, str] = {}
    for context_key, (source_col, obs_col) in mapping.items():
        if source_col not in role_lookup.columns:
            continue
        mapped = cell_type_labels.map(role_lookup[source_col])
        if source_col == "dominant_role":
            adata.obs[obs_col] = pd.Categorical(mapped.fillna("unassigned"))
        else:
            adata.obs[obs_col] = pd.to_numeric(mapped, errors="coerce").fillna(0.0)
        resolved[context_key] = obs_col

    return resolved


def _resolve_spatial_score_key(adata) -> str | None:
    for key in adata.obsm.keys():
        key_lower = str(key).lower()
        if "spatial_scores" in str(key) or "ccc" in key_lower or "communication" in key_lower:
            return str(key)
    return None


def _build_source_target_summary(lr_df: pd.DataFrame) -> pd.DataFrame:
    if lr_df.empty or not {"source", "target"}.issubset(lr_df.columns):
        return pd.DataFrame(columns=["source", "target", "n_interactions", "total_score", "mean_score"])

    summary_df = (
        lr_df.groupby(["source", "target"], observed=True)
        .agg(
            n_interactions=("score", "size"),
            total_score=("score", "sum"),
            mean_score=("score", "mean"),
        )
        .reset_index()
        .sort_values("total_score", ascending=False)
        .reset_index(drop=True)
    )
    return summary_df


def _build_top_interactions_table(summary: dict, n_top: int = 20) -> pd.DataFrame:
    top_df = summary.get("top_df", pd.DataFrame()).copy()
    if top_df.empty:
        return pd.DataFrame(
            columns=["ligand", "receptor", "source", "target", "score", "pvalue", "pathway", "rank"]
        )

    top_df = top_df.head(n_top).copy()
    if "pathway" not in top_df.columns:
        top_df["pathway"] = ""
    top_df["rank"] = np.arange(1, len(top_df) + 1)
    ordered_cols = ["rank", "ligand", "receptor", "source", "target", "score", "pvalue", "pathway"]
    return top_df.loc[:, [col for col in ordered_cols if col in top_df.columns]]


def _build_run_summary_table(summary: dict, context: dict) -> pd.DataFrame:
    rows = [
        {"metric": "method", "value": summary.get("method")},
        {"metric": "species", "value": summary.get("species")},
        {"metric": "cell_type_key", "value": summary.get("cell_type_key")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_genes", "value": summary.get("n_genes")},
        {"metric": "n_cell_types", "value": summary.get("n_cell_types")},
        {"metric": "n_interactions_tested", "value": summary.get("n_interactions_tested")},
        {"metric": "n_significant", "value": summary.get("n_significant")},
        {"metric": "role_column", "value": context.get("role_col")},
        {"metric": "hub_score_column", "value": context.get("hub_score_col")},
        {"metric": "spatial_score_key", "value": context.get("spatial_score_key")},
    ]
    return pd.DataFrame(rows)


def _build_projection_table(adata, basis: str, context: dict) -> pd.DataFrame | None:
    cell_type_key = context.get("cell_type_key")

    if basis == "spatial":
        if "spatial" not in adata.obsm:
            return None
        coords = np.asarray(adata.obsm["spatial"])
        df = pd.DataFrame(
            {
                "observation": adata.obs_names.astype(str),
                "x": coords[:, 0],
                "y": coords[:, 1],
            }
        )
    elif basis == "umap":
        if "X_umap" not in adata.obsm:
            return None
        coords = np.asarray(adata.obsm["X_umap"])
        if coords.shape[1] < 2:
            return None
        df = pd.DataFrame(
            {
                "observation": adata.obs_names.astype(str),
                "umap_1": coords[:, 0],
                "umap_2": coords[:, 1],
            }
        )
    else:
        raise ValueError(f"Unsupported basis '{basis}'")

    if cell_type_key and cell_type_key in adata.obs.columns:
        df["cell_type"] = adata.obs[cell_type_key].astype(str).to_numpy()
    for column in (
        context.get("role_col"),
        context.get("sender_score_col"),
        context.get("receiver_score_col"),
        context.get("hub_score_col"),
        context.get("outgoing_col"),
        context.get("incoming_col"),
    ):
        if column and column in adata.obs.columns:
            series = adata.obs[column]
            if pd.api.types.is_numeric_dtype(series):
                df[column] = pd.to_numeric(series, errors="coerce").fillna(0.0).to_numpy()
            else:
                df[column] = series.astype(str).to_numpy()

    return df


def _prepare_communication_gallery_context(adata, summary: dict) -> dict:
    spatial_key = _prepare_communication_plot_state(adata)
    _ensure_umap_for_gallery(adata)

    context = {
        "cell_type_key": summary.get("cell_type_key"),
        "roles_df": summary.get("signaling_roles_df", pd.DataFrame()),
        "pathway_df": summary.get("pathway_df", pd.DataFrame()),
        "lr_df": summary.get("lr_df", pd.DataFrame()),
        "top_df": summary.get("top_df", pd.DataFrame()),
        "source_target_df": _build_source_target_summary(summary.get("lr_df", pd.DataFrame())),
        "spatial_key": spatial_key,
        "spatial_score_key": _resolve_spatial_score_key(adata),
    }
    context.update(_annotate_signaling_roles_to_obs(adata, summary))
    return context


def _build_communication_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    plots: list[PlotSpec] = [
        PlotSpec(
            plot_id="communication_lr_dotplot",
            role="overview",
            renderer="communication_plot",
            filename="lr_dotplot.png",
            title="Top Ligand-Receptor Interactions",
            description="Canonical LR interaction overview using the standardized OmicsClaw communication table.",
            params={
                "subtype": "dotplot",
                "top_n": 20,
                "figure_size": (10, 8),
            },
            required_uns=["ccc_results"],
        ),
        PlotSpec(
            plot_id="communication_lr_heatmap",
            role="overview",
            renderer="communication_plot",
            filename="lr_heatmap.png",
            title="Sender-Receiver Communication Heatmap",
            description="Aggregated sender-to-receiver interaction strength heatmap built from standardized LR results.",
            params={
                "subtype": "heatmap",
                "top_n": 20,
                "figure_size": (8, 6),
            },
            required_uns=["ccc_results"],
        ),
    ]

    if context.get("spatial_score_key"):
        plots.append(
            PlotSpec(
                plot_id="communication_spatial_scores",
                role="diagnostic",
                renderer="communication_plot",
                filename="lr_spatial.png",
                title="Spatial Communication Score Maps",
                description="Spatial communication panels when method-specific per-observation score maps are available.",
                params={
                    "subtype": "spatial",
                    "top_n": 4,
                    "figure_size": (12, 9),
                },
                required_obsm=[context["spatial_score_key"], "spatial"],
            )
        )

    if context.get("role_col") and context.get("spatial_key"):
        plots.append(
            PlotSpec(
                plot_id="communication_role_spatial",
                role="diagnostic",
                renderer="feature_map",
                filename="communication_roles_spatial.png",
                title="Dominant Communication Roles",
                description="Cell-type signaling roles projected back onto tissue coordinates.",
                params={
                    "feature": context["role_col"],
                    "basis": "spatial",
                    "colormap": "tab10",
                    "show_axes": False,
                    "show_legend": True,
                    "figure_size": (10, 8),
                },
                required_obs=[context["role_col"]],
                required_obsm=["spatial"],
            )
        )

    hub_basis = None
    if context.get("hub_score_col") and "X_umap" in adata.obsm:
        hub_basis = "umap"
    elif context.get("hub_score_col") and context.get("spatial_key"):
        hub_basis = "spatial"
    if context.get("hub_score_col") and hub_basis:
        required_obsm = ["X_umap"] if hub_basis == "umap" else ["spatial"]
        plots.append(
            PlotSpec(
                plot_id="communication_hub_score_map",
                role="diagnostic",
                renderer="feature_map",
                filename=f"communication_hub_{hub_basis}.png",
                title="Communication Hub Score",
                description="Per-observation communication hub score mapped onto the shared embedding or tissue coordinates.",
                params={
                    "feature": context["hub_score_col"],
                    "basis": hub_basis,
                    "colormap": "magma",
                    "show_axes": False,
                    "show_colorbar": True,
                    "figure_size": (8, 6) if hub_basis == "umap" else (10, 8),
                },
                required_obs=[context["hub_score_col"]],
                required_obsm=required_obsm,
            )
        )

    if not context["roles_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="communication_signaling_roles",
                role="supporting",
                renderer="signaling_roles_barplot",
                filename="signaling_roles.png",
                title="Signaling Role Summary",
                description="Sender and receiver activity summarized at the cell-type level.",
            )
        )

    if not context["source_target_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="communication_source_target_summary",
                role="supporting",
                renderer="source_target_barplot",
                filename="source_target_summary.png",
                title="Strongest Source-Target Communication Axes",
                description="Top source-target communication channels ranked by total communication score.",
            )
        )

    plots.append(
        PlotSpec(
            plot_id="communication_pvalue_distribution",
            role="uncertainty",
            renderer="pvalue_histogram",
            filename="communication_pvalue_distribution.png",
            title="Interaction P-value Distribution",
            description="Distribution of LR interaction p-values across the standardized communication table.",
            required_uns=["ccc_results"],
        )
    )

    plots.append(
        PlotSpec(
            plot_id="communication_score_vs_significance",
            role="uncertainty",
            renderer="score_pvalue_scatter",
            filename="communication_score_vs_significance.png",
            title="Communication Score vs Significance",
            description="Joint view of standardized communication score and interaction significance.",
            required_uns=["ccc_results"],
        )
    )

    return VisualizationRecipe(
        recipe_id="standard-spatial-communication-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Communication Standard Gallery",
        description=(
            "Default OmicsClaw communication story plots: LR overviews, role diagnostics, "
            "supporting summaries, and uncertainty panels built from shared communication "
            "and feature-map visualization primitives."
        ),
        plots=plots,
    )


def _render_communication_plot(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_communication(
        adata,
        VizParams(
            title=spec.title,
            figure_size=spec.params.get("figure_size"),
            dpi=int(spec.params.get("dpi", 200)),
            colormap=spec.params.get("colormap"),
        ),
        subtype=spec.params.get("subtype"),
        top_n=int(spec.params.get("top_n", 20)),
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_signaling_roles_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    roles_df = context.get("roles_df", pd.DataFrame())
    if roles_df.empty:
        return None

    top_roles = roles_df.head(10).iloc[::-1]
    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (8.5, max(4.5, len(top_roles) * 0.5))),
        dpi=200,
    )
    y = np.arange(len(top_roles))
    ax.barh(y - 0.18, top_roles["sender_score"], height=0.32, color="#1b9e77", label="Sender")
    ax.barh(y + 0.18, top_roles["receiver_score"], height=0.32, color="#d95f02", label="Receiver")
    ax.set_yticks(y)
    ax.set_yticklabels(top_roles["cell_type"])
    ax.set_xlabel("Communication score")
    ax.set_title(spec.title or "Signaling Role Summary")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def _render_source_target_barplot(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    summary_df = context.get("source_target_df", pd.DataFrame())
    if summary_df.empty:
        return None

    top_df = summary_df.head(12).iloc[::-1].copy()
    top_df["label"] = top_df["source"].astype(str) + " -> " + top_df["target"].astype(str)

    fig, ax = plt.subplots(
        figsize=spec.params.get("figure_size", (9, max(4.5, len(top_df) * 0.45))),
        dpi=200,
    )
    ax.barh(top_df["label"], top_df["total_score"], color="#2b8cbe")
    ax.set_xlabel("Total communication score")
    ax.set_title(spec.title or "Strongest Source-Target Communication Axes")
    fig.tight_layout()
    return fig


def _render_pvalue_histogram(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    lr_df = context.get("lr_df", pd.DataFrame())
    if lr_df.empty or "pvalue" not in lr_df.columns:
        return None

    pvalues = pd.to_numeric(lr_df["pvalue"], errors="coerce").dropna()
    if pvalues.empty:
        return None

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(pvalues.clip(lower=0.0, upper=1.0), bins=20, color="#756bb1", edgecolor="white")
    ax.axvline(0.05, color="black", linestyle="--", linewidth=1.2)
    ax.set_xlabel("P-value")
    ax.set_ylabel("Number of interactions")
    ax.set_title(spec.title or "Interaction P-value Distribution")
    fig.tight_layout()
    return fig


def _render_score_pvalue_scatter(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    lr_df = context.get("lr_df", pd.DataFrame())
    if lr_df.empty or not {"score", "pvalue"}.issubset(lr_df.columns):
        return None

    plot_df = lr_df.copy()
    plot_df["score"] = pd.to_numeric(plot_df["score"], errors="coerce").fillna(0.0)
    plot_df["pvalue"] = pd.to_numeric(plot_df["pvalue"], errors="coerce").fillna(1.0).clip(lower=1e-12)
    plot_df["neg_log10_pvalue"] = -np.log10(plot_df["pvalue"])

    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (7.5, 5.5)), dpi=200)
    ax.scatter(
        plot_df["score"],
        plot_df["neg_log10_pvalue"],
        c=np.where(plot_df["pvalue"] < 0.05, "#d95f02", "#8c8c8c"),
        alpha=0.7,
        s=24,
    )
    ax.axhline(-np.log10(0.05), color="black", linestyle="--", linewidth=1.1)
    ax.set_xlabel("Communication score")
    ax.set_ylabel("-log10(p-value)")
    ax.set_title(spec.title or "Communication Score vs Significance")
    fig.tight_layout()
    return fig


COMMUNICATION_GALLERY_RENDERERS = {
    "communication_plot": _render_communication_plot,
    "feature_map": _render_feature_map,
    "signaling_roles_barplot": _render_signaling_roles_barplot,
    "source_target_barplot": _render_source_target_barplot,
    "pvalue_histogram": _render_pvalue_histogram,
    "score_pvalue_scatter": _render_score_pvalue_scatter,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


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

    lr_df = summary.get("lr_df", pd.DataFrame()).copy()
    if lr_df.empty:
        lr_df = pd.DataFrame(columns=["ligand", "receptor", "source", "target", "score", "pvalue"])
    lr_df.to_csv(figure_data_dir / "lr_interactions.csv", index=False)

    _build_top_interactions_table(summary, n_top=50).to_csv(
        figure_data_dir / "top_interactions.csv",
        index=False,
    )

    pathway_df = summary.get("pathway_df", pd.DataFrame()).copy()
    if pathway_df.empty:
        pathway_df = pd.DataFrame(
            columns=["source", "target", "pathway", "n_interactions", "mean_score", "top_ligand", "top_receptor"]
        )
    pathway_df.to_csv(figure_data_dir / "communication_summary.csv", index=False)

    roles_df = summary.get("signaling_roles_df", pd.DataFrame()).copy()
    if roles_df.empty:
        roles_df = pd.DataFrame(
            columns=[
                "cell_type",
                "sender_score",
                "receiver_score",
                "hub_score",
                "dominant_role",
                "n_outgoing",
                "n_incoming",
            ]
        )
    roles_df.to_csv(figure_data_dir / "signaling_roles.csv", index=False)

    source_target_df = context.get("source_target_df", pd.DataFrame()).copy()
    if source_target_df.empty:
        source_target_df = pd.DataFrame(
            columns=["source", "target", "n_interactions", "total_score", "mean_score"]
        )
    source_target_df.to_csv(figure_data_dir / "source_target_summary.csv", index=False)

    _build_run_summary_table(summary, context).to_csv(
        figure_data_dir / "communication_run_summary.csv",
        index=False,
    )

    spatial_file = None
    spatial_df = _build_projection_table(adata, "spatial", context)
    if spatial_df is not None:
        spatial_file = "communication_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    umap_df = _build_projection_table(adata, "umap", context)
    if umap_df is not None:
        umap_file = "communication_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    extra_files: dict[str, str] = {}
    extra_name_map = {
        "cellchat_pathways_df": "cellchat_pathways.csv",
        "cellchat_centrality_df": "cellchat_centrality.csv",
        "cellchat_count_matrix_df": "cellchat_count_matrix.csv",
        "cellchat_weight_matrix_df": "cellchat_weight_matrix.csv",
    }
    for key, df in summary.get("extra_tables", {}).items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            filename = extra_name_map.get(key, f"{key}.csv")
            df.to_csv(figure_data_dir / filename, index=(df.index.name is not None))
            extra_files[key] = filename

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary.get("method"),
        "species": summary.get("species"),
        "cell_type_key": summary.get("cell_type_key"),
        "role_column": context.get("role_col"),
        "hub_score_column": context.get("hub_score_col"),
        "spatial_score_key": context.get("spatial_score_key"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(spec.role for spec in recipe.plots)),
        "available_files": {
            "lr_interactions": "lr_interactions.csv",
            "top_interactions": "top_interactions.csv",
            "communication_summary": "communication_summary.csv",
            "signaling_roles": "signaling_roles.csv",
            "source_target_summary": "source_target_summary.csv",
            "communication_run_summary": "communication_run_summary.csv",
            "communication_spatial_points": spatial_file,
            "communication_umap_points": umap_file,
            **extra_files,
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
    gallery_context: dict | None = None,
) -> list[str]:
    """Render the standard communication gallery and export figure-ready data."""
    context = gallery_context or _prepare_communication_gallery_context(adata, summary)
    recipe = _build_communication_visualization_recipe(adata, summary, context)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        COMMUNICATION_GALLERY_RENDERERS,
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
        / "spatial-communication"
        / "r_visualization"
        / "communication_publication_template.R"
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
    gallery_context: dict | None = None,
) -> list[str]:
    """Write stable communication tables for downstream analysis."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []
    lr_df = summary.get("lr_df", pd.DataFrame())
    if not lr_df.empty:
        path = tables_dir / "lr_interactions.csv"
        lr_df.to_csv(path, index=False)
        exported.append(str(path))

        path = tables_dir / "top_interactions.csv"
        _build_top_interactions_table(summary, n_top=50).to_csv(path, index=False)
        exported.append(str(path))

    pathway_df = summary.get("pathway_df", pd.DataFrame())
    if not pathway_df.empty:
        path = tables_dir / "communication_summary.csv"
        pathway_df.to_csv(path, index=False)
        exported.append(str(path))

    roles_df = summary.get("signaling_roles_df", pd.DataFrame())
    if not roles_df.empty:
        path = tables_dir / "signaling_roles.csv"
        roles_df.to_csv(path, index=False)
        exported.append(str(path))

    source_target_df = (
        gallery_context.get("source_target_df")
        if gallery_context is not None
        else _build_source_target_summary(lr_df)
    )
    if isinstance(source_target_df, pd.DataFrame) and not source_target_df.empty:
        path = tables_dir / "source_target_summary.csv"
        source_target_df.to_csv(path, index=False)
        exported.append(str(path))

    extra_tables = summary.get("extra_tables", {})
    table_name_map = {
        "cellchat_pathways_df": "cellchat_pathways.csv",
        "cellchat_centrality_df": "cellchat_centrality.csv",
        "cellchat_count_matrix_df": "cellchat_count_matrix.csv",
        "cellchat_weight_matrix_df": "cellchat_weight_matrix.csv",
    }
    for key, df in extra_tables.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            path = tables_dir / table_name_map.get(key, f"{key}.csv")
            df.to_csv(path, index=False)
            exported.append(str(path))

    return exported


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
    *,
    gallery_context: dict | None = None,
) -> None:
    """Write report.md and result.json."""
    header = generate_report_header(
        title="Spatial Cell-Cell Communication Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", ""),
            "Cell type key": summary.get("cell_type_key", ""),
            "Species": summary.get("species", ""),
        },
    )

    top_df = _build_top_interactions_table(summary, n_top=15)
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Cell types**: {summary['n_cell_types']}",
        f"- **Method**: {summary['method']}",
        f"- **Species**: {summary['species']}",
        f"- **Interactions tested**: {summary['n_interactions_tested']}",
        f"- **Significant (p < 0.05)**: {summary['n_significant']}",
    ]

    if gallery_context and gallery_context.get("role_col"):
        body_lines.append(f"- **Observation-level role column**: `{gallery_context['role_col']}`")
    if gallery_context and gallery_context.get("hub_score_col"):
        body_lines.append(f"- **Observation-level hub score column**: `{gallery_context['hub_score_col']}`")

    if not top_df.empty:
        body_lines.extend(["", "### Top Interactions\n"])
        body_lines.append("| Ligand | Receptor | Source | Target | Score | Pvalue |")
        body_lines.append("|--------|----------|--------|--------|-------|--------|")
        for _, row in top_df.iterrows():
            body_lines.append(
                f"| {row['ligand']} | {row['receptor']} | {row['source']} | {row['target']} | {row['score']:.4f} | {row['pvalue']:.4f} |"
            )

    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    effective_params = summary.get("effective_params", {})
    if effective_params:
        body_lines.extend(["", "### Effective Method Parameters\n"])
        for key, value in effective_params.items():
            body_lines.append(f"- `{key}`: {value}")

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
    excluded = {
        "lr_df",
        "top_df",
        "pathway_df",
        "signaling_roles_df",
        "extra_tables",
    }
    result_data = {
        "params": params,
        "effective_params": effective_params,
    }
    if gallery_context:
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-communication-gallery",
            "cell_type_key": summary.get("cell_type_key"),
            "role_column": gallery_context.get("role_col"),
            "hub_score_column": gallery_context.get("hub_score_col"),
            "spatial_score_key": gallery_context.get("spatial_score_key"),
        }
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary={key: value for key, value in summary.items() if key not in excluded},
        data=result_data,
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
    for key, value in params.items():
        cmd = _append_cli_flag(cmd, key, value)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as get_version
    except ImportError:
        from importlib_metadata import version as get_version  # type: ignore

    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "scipy"]:
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            pass
        except Exception:
            pass

    for optional_pkg in ["liana", "cellphonedb", "fastccc"]:
        if is_available(optional_pkg):
            try:
                env_lines.append(f"{optional_pkg}=={get_version(optional_pkg)}")
            except Exception:
                pass
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")
    _write_r_visualization_helper(output_dir)


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate demo data via spatial-preprocess and patch in LIANA-friendly gene symbols."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_comm_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Generating demo data via spatial-preprocess ...")
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed:\n{result.stderr}")

        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")

        adata = sc.read_h5ad(processed)
        logger.info("Demo: %d cells × %d genes", adata.n_obs, adata.n_vars)

        valid_genes = [
            "A1BG", "A2M", "AANAT", "ABCA1", "ACE", "ACKR1", "ACKR2", "ACKR3", "ACKR4", "ACTR2",
            "ACVR1", "ACVR1B", "ACVR1C", "ACVR2A", "ACVR2B", "ACVRL1", "ADA", "ADAM10", "ADAM11", "ADAM12",
            "ADAM15", "ADAM17", "ADAM2", "ADAM22", "ADAM23", "ADAM28", "ADAM29", "ADAM7", "ADAM9", "ADAMTS3",
            "ADCY1", "ADCY7", "ADCY8", "ADCY9", "ADCYAP1", "ADCYAP1R1", "ADGRA2", "ADGRB1", "ADGRE2", "ADGRE5",
            "ADGRG1", "ADGRG3", "ADGRG5", "ADGRL1", "ADGRL4", "ADGRV1", "ADIPOQ", "ADIPOR1", "ADIPOR2", "ADM",
            "ADM2", "ADO", "ADORA1", "ADORA2A", "ADORA2B", "ADORA3", "ADRA2A", "ADRA2B", "ADRB1", "ADRB2",
            "ADRB3", "AFDN", "AGER", "AGR2", "AGRN", "AGRP", "AGT", "AGTR1", "AGTR2", "AGTRAP",
            "AHSG", "AIMP1", "ALB", "ALCAM", "ALK", "ALKAL1", "ALKAL2", "ALOX5", "AMBN", "AMELX",
            "AMELY", "AMFR", "AMH", "AMHR2", "ANG", "ANGPT1", "ANGPT2", "ANGPT4", "ANGPTL1", "ANGPTL2",
            "ANGPTL3", "ANGPTL4", "ANGPTL7", "ANOS1", "ANTXR1", "ANXA1", "ANXA2", "APCDD1", "APELA", "APLN",
        ]
        if adata.n_vars > len(valid_genes):
            valid_genes += [f"Gene_dummy_{i}" for i in range(adata.n_vars - len(valid_genes))]
        adata.var_names = valid_genes[: adata.n_vars]
        adata.raw = adata.copy()
        return adata, None


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.liana_expr_prop < 0 or args.liana_expr_prop > 1:
        parser.error("--liana-expr-prop must be between 0 and 1")
    if args.liana_min_cells < 1:
        parser.error("--liana-min-cells must be >= 1")
    if args.liana_n_perms < 1:
        parser.error("--liana-n-perms must be >= 1")

    if args.cellphonedb_iterations < 1:
        parser.error("--cellphonedb-iterations must be >= 1")
    if args.cellphonedb_threshold < 0 or args.cellphonedb_threshold > 1:
        parser.error("--cellphonedb-threshold must be between 0 and 1")

    allowed_single_unit = {"Mean", "Median", "Q2", "Q3"}
    if (
        args.fastccc_single_unit_summary not in allowed_single_unit
        and not args.fastccc_single_unit_summary.startswith("Quantile_")
    ):
        parser.error(
            "--fastccc-single-unit-summary must be one of Mean/Median/Q2/Q3 or start with Quantile_"
        )
    if args.fastccc_min_percentile < 0 or args.fastccc_min_percentile > 1:
        parser.error("--fastccc-min-percentile must be between 0 and 1")

    if args.cellchat_min_cells < 1:
        parser.error("--cellchat-min-cells must be >= 1")
    if not str(args.cellchat_prob_type).strip():
        parser.error("--cellchat-prob-type must be a non-empty string")


def _collect_run_configuration(args: argparse.Namespace) -> tuple[dict, dict]:
    params = {
        "method": args.method,
        "cell_type_key": args.cell_type_key,
        "species": args.species,
    }

    if args.method == "liana":
        params.update(
            {
                "liana_expr_prop": args.liana_expr_prop,
                "liana_min_cells": args.liana_min_cells,
                "liana_n_perms": args.liana_n_perms,
                "liana_resource": args.liana_resource,
            }
        )
        method_kwargs = {
            "expr_prop": args.liana_expr_prop,
            "min_cells": args.liana_min_cells,
            "n_perms": args.liana_n_perms,
            "resource": args.liana_resource,
        }
    elif args.method == "cellphonedb":
        params.update(
            {
                "cellphonedb_iterations": args.cellphonedb_iterations,
                "cellphonedb_threshold": args.cellphonedb_threshold,
            }
        )
        method_kwargs = {
            "iterations": args.cellphonedb_iterations,
            "threshold": args.cellphonedb_threshold,
        }
    elif args.method == "fastccc":
        params.update(
            {
                "fastccc_single_unit_summary": args.fastccc_single_unit_summary,
                "fastccc_complex_aggregation": args.fastccc_complex_aggregation,
                "fastccc_lr_combination": args.fastccc_lr_combination,
                "fastccc_min_percentile": args.fastccc_min_percentile,
            }
        )
        method_kwargs = {
            "single_unit_summary": args.fastccc_single_unit_summary,
            "complex_aggregation": args.fastccc_complex_aggregation,
            "lr_combination": args.fastccc_lr_combination,
            "min_percentile": args.fastccc_min_percentile,
        }
    else:
        params.update(
            {
                "cellchat_prob_type": args.cellchat_prob_type,
                "cellchat_min_cells": args.cellchat_min_cells,
            }
        )
        method_kwargs = {
            "prob_type": args.cellchat_prob_type,
            "min_cells": args.cellchat_min_cells,
        }

    return params, method_kwargs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Spatial Communication — ligand-receptor interaction analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default="liana", choices=list(SUPPORTED_METHODS))
    parser.add_argument("--cell-type-key", default="leiden")
    parser.add_argument("--species", default="human", choices=list(SUPPORTED_SPECIES))

    parser.add_argument(
        "--liana-expr-prop",
        type=float,
        default=METHOD_PARAM_DEFAULTS["liana"]["expr_prop"],
    )
    parser.add_argument(
        "--liana-min-cells",
        type=int,
        default=METHOD_PARAM_DEFAULTS["liana"]["min_cells"],
    )
    parser.add_argument(
        "--liana-n-perms",
        type=int,
        default=METHOD_PARAM_DEFAULTS["liana"]["n_perms"],
    )
    parser.add_argument(
        "--liana-resource",
        default=METHOD_PARAM_DEFAULTS["liana"]["resource"],
        choices=["auto", "consensus", "mouseconsensus"],
    )

    parser.add_argument(
        "--cellphonedb-iterations",
        type=int,
        default=METHOD_PARAM_DEFAULTS["cellphonedb"]["iterations"],
    )
    parser.add_argument(
        "--cellphonedb-threshold",
        type=float,
        default=METHOD_PARAM_DEFAULTS["cellphonedb"]["threshold"],
    )

    parser.add_argument(
        "--fastccc-single-unit-summary",
        default=METHOD_PARAM_DEFAULTS["fastccc"]["single_unit_summary"],
    )
    parser.add_argument(
        "--fastccc-complex-aggregation",
        default=METHOD_PARAM_DEFAULTS["fastccc"]["complex_aggregation"],
        choices=["Minimum", "Average"],
    )
    parser.add_argument(
        "--fastccc-lr-combination",
        default=METHOD_PARAM_DEFAULTS["fastccc"]["lr_combination"],
        choices=["Arithmetic", "Geometric"],
    )
    parser.add_argument(
        "--fastccc-min-percentile",
        type=float,
        default=METHOD_PARAM_DEFAULTS["fastccc"]["min_percentile"],
    )

    parser.add_argument(
        "--cellchat-prob-type",
        default=METHOD_PARAM_DEFAULTS["cellchat_r"]["prob_type"],
    )
    parser.add_argument(
        "--cellchat-min-cells",
        type=int,
        default=METHOD_PARAM_DEFAULTS["cellchat_r"]["min_cells"],
    )

    args = parser.parse_args()
    _validate_args(parser, args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        if not Path(args.input_path).exists():
            print(f"ERROR: Input not found: {args.input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input <file.h5ad> or --demo", file=sys.stderr)
        sys.exit(1)

    params, method_kwargs = _collect_run_configuration(args)
    summary = run_communication(
        adata,
        method=args.method,
        cell_type_key=args.cell_type_key,
        species=args.species,
        method_params=method_kwargs,
    )

    gallery_context = _prepare_communication_gallery_context(adata, summary)
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, summary, gallery_context=gallery_context)
    write_report(output_dir, summary, input_file, params, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, input_file)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    adata.write_h5ad(output_dir / "processed.h5ad")
    logger.info("Saved: %s", output_dir / "processed.h5ad")

    print(
        f"Communication complete ({summary['method']}): "
        f"{summary['n_interactions_tested']} interactions tested, "
        f"{summary['n_significant']} significant (p<0.05)"
    )


if __name__ == "__main__":
    main()
