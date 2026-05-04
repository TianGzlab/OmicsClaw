#!/usr/bin/env python3
"""Spatial Domains — identify tissue regions and spatial niches.

Supports multiple algorithms with distinct strengths:
  - leiden:   Graph-based clustering with spatial-weighted neighbors (default, fast)
  - louvain:  Classic graph-based clustering (requires: pip install louvain)
  - spagcn:   Spatial Graph Convolutional Network (coordinate-derived adjacency in the current wrapper)
  - stagate:  Graph attention auto-encoder (PyTorch Geometric)
  - graphst:  Self-supervised contrastive learning (PyTorch)
  - banksy:   Explicit spatial feature augmentation (interpretable)
  - cellcharter:  Neighborhood-aggregated GMM clustering (CSOgroup/cellcharter)

Usage:
    python spatial_domains.py --input <preprocessed.h5ad> --output <dir>
    python spatial_domains.py --demo --output <dir>
    python spatial_domains.py --input <file> --method spagcn --n-domains 7 --output <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import get_spatial_key, store_analysis_metadata
from skills.spatial._lib.domains import (
    SUPPORTED_METHODS,
    dispatch_method,
    refine_spatial_domains,
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

SKILL_NAME = "spatial-domains"
SKILL_VERSION = "0.5.0"
SCRIPT_REL_PATH = "skills/spatial/spatial-domains/spatial_domains.py"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _prepare_domain_plot_state(adata) -> str | None:
    """Ensure coordinate aliases and domain labels are plot-ready."""
    spatial_key = get_spatial_key(adata)
    if spatial_key == "spatial" and "X_spatial" not in adata.obsm:
        adata.obsm["X_spatial"] = adata.obsm["spatial"].copy()
    elif spatial_key == "X_spatial" and "spatial" not in adata.obsm:
        adata.obsm["spatial"] = adata.obsm["X_spatial"].copy()

    if "spatial_domain" in adata.obs.columns and not isinstance(adata.obs["spatial_domain"].dtype, pd.CategoricalDtype):
        adata.obs["spatial_domain"] = pd.Categorical(adata.obs["spatial_domain"])

    return get_spatial_key(adata)


def _ensure_umap_for_gallery(adata) -> None:
    """Compute UMAP if needed for the standard gallery."""
    if "X_umap" in adata.obsm:
        return
    try:
        if "connectivities" not in adata.obsp:
            if "X_pca" in adata.obsm:
                sc.pp.neighbors(adata, use_rep="X_pca")
            else:
                sc.pp.neighbors(adata)
        sc.tl.umap(adata)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Could not compute UMAP for spatial-domains gallery: %s", exc)


def _get_method_embedding_spec(adata, summary: dict) -> dict | None:
    preferred = {
        "stagate": ("X_stagate", "STAGATE embedding"),
        "graphst": ("X_graphst", "GraphST embedding"),
        "banksy": ("X_banksy_pca", "BANKSY PCA"),
        "cellcharter": ("X_cellcharter", "CellCharter embedding"),
    }
    method = summary.get("method")
    if method in preferred:
        key, label = preferred[method]
        if key in adata.obsm and np.asarray(adata.obsm[key]).shape[1] >= 2:
            return {"key": key, "label": label}
    return None


def _compute_domain_neighbor_diagnostics(
    adata,
    *,
    domain_col: str = "spatial_domain",
    k: int = 8,
) -> dict:
    from sklearn.neighbors import NearestNeighbors

    spatial_key = get_spatial_key(adata)
    if spatial_key is None or domain_col not in adata.obs.columns or adata.n_obs < 2:
        return {"purity_col": None, "neighbor_mix_df": None, "neighbor_k": None}

    coords = np.asarray(adata.obsm[spatial_key])[:, :2]
    labels = adata.obs[domain_col].astype(str).to_numpy()
    n_neighbors = min(k + 1, adata.n_obs)
    if n_neighbors <= 1:
        return {"purity_col": None, "neighbor_mix_df": None, "neighbor_k": None}

    nbrs = NearestNeighbors(n_neighbors=n_neighbors).fit(coords)
    _, indices = nbrs.kneighbors(coords)
    neighbor_idx = indices[:, 1:]
    if neighbor_idx.shape[1] == 0:
        return {"purity_col": None, "neighbor_mix_df": None, "neighbor_k": None}

    purity = (labels[neighbor_idx] == labels[:, None]).mean(axis=1)
    adata.obs["domain_local_purity"] = purity.astype(float)

    domains = list(pd.Index(pd.unique(labels)))
    mix_counts = pd.DataFrame(0.0, index=domains, columns=domains)
    for obs_idx, neighbors in enumerate(neighbor_idx):
        src = labels[obs_idx]
        for nb_idx in neighbors:
            mix_counts.loc[src, labels[nb_idx]] += 1.0
    row_sums = mix_counts.sum(axis=1).replace(0.0, np.nan)
    mix_df = mix_counts.div(row_sums, axis=0).fillna(0.0)

    return {
        "purity_col": "domain_local_purity",
        "neighbor_mix_df": mix_df,
        "neighbor_k": int(neighbor_idx.shape[1]),
    }


def _prepare_domain_gallery_context(adata, summary: dict) -> dict:
    _prepare_domain_plot_state(adata)
    _ensure_umap_for_gallery(adata)

    context = {
        "domain_col": "spatial_domain",
        "method_embedding": _get_method_embedding_spec(adata, summary),
    }
    context.update(_compute_domain_neighbor_diagnostics(adata))

    purity_col = context.get("purity_col")
    if purity_col and purity_col in adata.obs.columns:
        summary["mean_local_purity"] = round(float(adata.obs[purity_col].mean()), 4)
        summary["neighbor_k"] = context.get("neighbor_k")

    return context


def _build_domain_visualization_recipe(adata, summary: dict, context: dict) -> VisualizationRecipe:
    plots = [
        PlotSpec(
            plot_id="domain_spatial_overview",
            role="overview",
            renderer="feature_map",
            filename="spatial_domains.png",
            title="Spatial Domains",
            description="Domain labels projected onto tissue coordinates.",
            params={
                "feature": "spatial_domain",
                "basis": "spatial",
                "colormap": "tab20",
                "show_axes": False,
                "show_legend": True,
                "figure_size": (10, 8),
            },
            required_obs=["spatial_domain"],
            required_obsm=["spatial"],
        ),
        PlotSpec(
            plot_id="domain_umap_overview",
            role="overview",
            renderer="feature_map",
            filename="umap_domains.png",
            title="UMAP - Spatial Domains",
            description="Domain labels displayed on the default low-dimensional embedding.",
            params={
                "feature": "spatial_domain",
                "basis": "umap",
                "colormap": "tab20",
                "show_axes": False,
                "show_legend": True,
                "figure_size": (10, 8),
            },
            required_obs=["spatial_domain"],
            required_obsm=["X_umap"],
        ),
        PlotSpec(
            plot_id="domain_size_supporting",
            role="supporting",
            renderer="domain_barplot",
            filename="domain_sizes.png",
            title="Domain Size Distribution",
            description="Counts of spots or cells assigned to each domain.",
            required_obs=["spatial_domain"],
        ),
        PlotSpec(
            plot_id="domain_pca_diagnostic",
            role="diagnostic",
            renderer="feature_map",
            filename="pca_domains.png",
            title="PCA Diagnostic View",
            description="Domain labels shown on the first two PCA components.",
            params={
                "feature": "spatial_domain",
                "basis": "pca",
                "colormap": "tab20",
                "show_axes": True,
                "show_legend": True,
                "figure_size": (10, 8),
            },
            required_obs=["spatial_domain"],
            required_obsm=["X_pca"],
        ),
    ]

    if context.get("neighbor_mix_df") is not None:
        plots.append(
            PlotSpec(
                plot_id="domain_neighbor_mixing",
                role="diagnostic",
                renderer="neighbor_heatmap",
                filename="domain_neighbor_mixing.png",
                title="Domain Neighbor Mixing",
                description="Row-normalized domain co-occurrence among spatial nearest neighbors.",
            )
        )

    purity_col = context.get("purity_col")
    if purity_col and purity_col in adata.obs.columns:
        plots.extend(
            [
                PlotSpec(
                    plot_id="domain_local_purity_spatial",
                    role="uncertainty",
                    renderer="feature_map",
                    filename="domain_local_purity_spatial.png",
                    title="Spatial Domain Local Purity",
                    description="Fraction of nearby spots that share the same domain label.",
                    params={
                        "feature": purity_col,
                        "basis": "spatial",
                        "colormap": "viridis",
                        "show_axes": False,
                        "show_colorbar": True,
                        "figure_size": (10, 8),
                    },
                    required_obs=[purity_col],
                    required_obsm=["spatial"],
                ),
                PlotSpec(
                    plot_id="domain_local_purity_histogram",
                    role="uncertainty",
                    renderer="purity_histogram",
                    filename="domain_local_purity_histogram.png",
                    title="Local Purity Distribution",
                    description="Distribution of local domain-purity scores across all spots.",
                    required_obs=[purity_col],
                ),
            ]
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-domain-gallery",
        skill_name=SKILL_NAME,
        title="Spatial Domains Standard Gallery",
        description=(
            "Default OmicsClaw domain story plots built from existing viz primitives: "
            "overview maps, diagnostics, supporting summaries, and uncertainty panels."
        ),
        plots=plots,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_domain_barplot(adata, spec: PlotSpec, _context: dict) -> object:
    import matplotlib.pyplot as plt

    counts = adata.obs["spatial_domain"].astype(str).value_counts()
    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, max(4, len(counts) * 0.4))), dpi=200)
    counts.plot.barh(ax=ax, color="#2b8cbe")
    ax.set_xlabel("Number of spots / cells")
    ax.set_title(spec.title or "Domain Size Distribution")
    ax.invert_yaxis()
    fig.tight_layout()
    return fig


def _render_neighbor_heatmap(_adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt
    import seaborn as sns

    mix_df = context.get("neighbor_mix_df")
    if mix_df is None or mix_df.empty:
        return None

    fig, ax = plt.subplots(
        figsize=spec.params.get(
            "figure_size",
            (max(5, mix_df.shape[1] * 0.8), max(4, mix_df.shape[0] * 0.6)),
        ),
        dpi=200,
    )
    sns.heatmap(mix_df, cmap="mako", ax=ax, vmin=0.0, vmax=1.0)
    ax.set_xlabel("Neighbor Domain")
    ax.set_ylabel("Source Domain")
    ax.set_title(spec.title or "Domain Neighbor Mixing")
    fig.tight_layout()
    return fig


def _render_purity_histogram(adata, spec: PlotSpec, context: dict) -> object:
    import matplotlib.pyplot as plt

    purity_col = context.get("purity_col")
    if purity_col is None or purity_col not in adata.obs.columns:
        return None

    values = adata.obs[purity_col].astype(float)
    fig, ax = plt.subplots(figsize=spec.params.get("figure_size", (8, 5)), dpi=200)
    ax.hist(values, bins=20, color="#756bb1", edgecolor="white")
    ax.set_xlabel("Local purity")
    ax.set_ylabel("Number of spots / cells")
    ax.set_title(spec.title or "Local Purity Distribution")
    fig.tight_layout()
    return fig


DOMAIN_GALLERY_RENDERERS = {
    "feature_map": _render_feature_map,
    "domain_barplot": _render_domain_barplot,
    "neighbor_heatmap": _render_neighbor_heatmap,
    "purity_histogram": _render_purity_histogram,
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
    context: dict,
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    domain_col = context["domain_col"]
    purity_col = context.get("purity_col")

    counts = adata.obs[domain_col].astype(str).value_counts()
    counts_df = pd.DataFrame(
        [
            {
                "domain": domain,
                "n_cells": int(count),
                "proportion": round(count / max(int(counts.sum()), 1) * 100, 2),
            }
            for domain, count in counts.items()
        ]
    )
    counts_df.to_csv(figure_data_dir / "domain_counts.csv", index=False)

    spatial_file = None
    if "spatial" in adata.obsm:
        spatial_df = pd.DataFrame(
            {
                "observation": adata.obs_names,
                "x": adata.obsm["spatial"][:, 0],
                "y": adata.obsm["spatial"][:, 1],
                "spatial_domain": adata.obs[domain_col].astype(str).to_numpy(),
            }
        )
        if purity_col and purity_col in adata.obs.columns:
            spatial_df[purity_col] = adata.obs[purity_col].astype(float).to_numpy()
        spatial_file = "domain_spatial_points.csv"
        spatial_df.to_csv(figure_data_dir / spatial_file, index=False)

    umap_file = None
    if "X_umap" in adata.obsm:
        umap_df = pd.DataFrame(
            {
                "observation": adata.obs_names,
                "umap_1": adata.obsm["X_umap"][:, 0],
                "umap_2": adata.obsm["X_umap"][:, 1],
                "spatial_domain": adata.obs[domain_col].astype(str).to_numpy(),
            }
        )
        if purity_col and purity_col in adata.obs.columns:
            umap_df[purity_col] = adata.obs[purity_col].astype(float).to_numpy()
        umap_file = "domain_umap_points.csv"
        umap_df.to_csv(figure_data_dir / umap_file, index=False)

    method_embedding_file = None
    method_embedding = context.get("method_embedding")
    if method_embedding is not None:
        embedding = np.asarray(adata.obsm[method_embedding["key"]])
        if embedding.shape[1] >= 2:
            embed_df = pd.DataFrame(
                {
                    "observation": adata.obs_names,
                    "component_1": embedding[:, 0],
                    "component_2": embedding[:, 1],
                    "spatial_domain": adata.obs[domain_col].astype(str).to_numpy(),
                }
            )
            if purity_col and purity_col in adata.obs.columns:
                embed_df[purity_col] = adata.obs[purity_col].astype(float).to_numpy()
            method_embedding_file = "domain_method_embedding_points.csv"
            embed_df.to_csv(figure_data_dir / method_embedding_file, index=False)

    neighbor_mix_file = None
    if context.get("neighbor_mix_df") is not None:
        neighbor_mix_file = "domain_neighbor_mixing.csv"
        context["neighbor_mix_df"].rename_axis("domain").to_csv(
            figure_data_dir / neighbor_mix_file
        )

    contract = {
        "skill": SKILL_NAME,
        "version": SKILL_VERSION,
        "method": summary["method"],
        "domain_column": domain_col,
        "purity_column": purity_col,
        "recipe_id": recipe.recipe_id,
        "gallery_roles": [spec.role for spec in recipe.plots],
        "mean_local_purity": summary.get("mean_local_purity"),
        "available_files": {
            "domain_counts": "domain_counts.csv",
            "spatial_points": spatial_file,
            "umap_points": umap_file,
            "method_embedding_points": method_embedding_file,
            "neighbor_mixing": neighbor_mix_file,
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
    """Render the standard Python domains gallery and export figure-ready data."""
    if "spatial_domain" not in adata.obs.columns:
        logger.warning("No 'spatial_domain' column found; skipping domain figures")
        return []

    context = gallery_context or _prepare_domain_gallery_context(adata, summary)
    recipe = _build_domain_visualization_recipe(adata, summary, context)
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        DOMAIN_GALLERY_RENDERERS,
        context=context,
    )
    _export_figure_data(adata, output_dir, summary, recipe, artifacts, context)
    return [artifact.path for artifact in artifacts if artifact.status == "rendered"]


def _generate_next_steps(summary: dict, n_cells: int | None = None) -> list[str]:
    """Generate actionable next-step suggestions based on actual results."""
    steps = []
    n_domains = summary.get("n_domains", 0)
    method = summary.get("method", "")
    counts = summary.get("domain_counts", {})
    total = sum(counts.values()) if counts else 0

    if n_domains > 15:
        steps.append(
            f"- **Many domains detected ({n_domains})**: Consider lowering "
            "`--resolution` or `--n-domains` for coarser partitioning."
        )
    elif n_domains < 3:
        steps.append(
            f"- **Few domains detected ({n_domains})**: Consider raising "
            "`--resolution` or `--n-domains` for finer partitioning."
        )

    if total > 0:
        max_domain = max(counts.values())
        max_pct = max_domain / total * 100
        if max_pct > 60:
            dominant = [k for k, v in counts.items() if v == max_domain][0]
            steps.append(
                f"- **Domain {dominant} is dominant ({max_pct:.0f}%)**: "
                "This may indicate a batch effect, under-clustering, or "
                "preprocessing issue."
            )

    if n_cells is not None and n_cells > 30000 and method in ("graphst", "spagcn", "stagate"):
        steps.append(
            f"- **Large dataset ({n_cells:,} spots)**: If runtime was long, "
            "reduce `--epochs` in subsequent runs."
        )

    if method == "graphst" and (n_cells is None or n_cells > 5000):
        steps.append(
            "- **GraphST labels can be speckled/noisy on large tissue sections**: "
            "try `--refine` for KNN spatial smoothing, or increase `--epochs` "
            "(e.g., 100-200) for more stable domains."
        )

    if method in ("leiden", "louvain") and n_domains >= 5:
        steps.append(
            "- Consider running downstream `spatial-de` to find marker genes "
            "for each domain."
        )

    return steps


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _write_r_visualization_helper(output_dir: Path) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    r_template = (
        _PROJECT_ROOT
        / "skills"
        / "spatial"
        / "spatial-domains"
        / "r_visualization"
        / "domains_publication_template.R"
    )
    cmd = f"Rscript {shlex.quote(str(r_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def _append_cli_flag(command: str, key: str, value) -> str:
    flag = f"--{key.replace('_', '-')}"
    if isinstance(value, bool):
        return f"{command} {flag}" if value else command
    if value in (None, ""):
        return command
    return f"{command} {flag} {shlex.quote(str(value))}"


def export_tables(
    output_dir: Path,
    adata,
    summary: dict,
    *,
    gallery_context: dict | None = None,
) -> list[str]:
    """Write stable domain tables for downstream analysis."""
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    exported: list[str] = []
    total_cells = sum(summary["domain_counts"].values())
    rows = []
    for domain, count in summary["domain_counts"].items():
        pct = count / total_cells * 100 if total_cells > 0 else 0
        rows.append({"domain": domain, "n_cells": count, "proportion": round(pct, 2)})
    path = tables_dir / "domain_summary.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    exported.append(str(path))

    assignments = pd.DataFrame(index=adata.obs_names)
    assignments["spatial_domain"] = adata.obs["spatial_domain"].astype(str)
    if "domain_local_purity" in adata.obs.columns:
        assignments["domain_local_purity"] = adata.obs["domain_local_purity"].astype(float).to_numpy()
    path = tables_dir / "domain_assignments.csv"
    assignments.reset_index().rename(columns={"index": "observation"}).to_csv(
        path,
        index=False,
    )
    exported.append(str(path))

    if gallery_context and gallery_context.get("neighbor_mix_df") is not None:
        path = tables_dir / "domain_neighbor_mixing.csv"
        gallery_context["neighbor_mix_df"].rename_axis("domain").to_csv(path)
        exported.append(str(path))

    return exported


def write_report(
    output_dir: Path,
    adata,
    summary: dict,
    input_file: str | None,
    params: dict,
    current_params: dict | None = None,
    n_cells: int | None = None,
    gallery_context: dict | None = None,
) -> None:
    """Write report.md and result.json."""
    header = generate_report_header(
        title="Spatial Domain Identification Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Domains identified": str(summary["n_domains"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Domains identified**: {summary['n_domains']}",
    ]
    if "resolution" in summary:
        body_lines.append(f"- **Leiden resolution**: {summary['resolution']}")
    if "n_domains_requested" in summary:
        body_lines.append(f"- **Domains requested**: {summary['n_domains_requested']}")
    if n_cells is not None:
        body_lines.append(f"- **Total cells/spots**: {n_cells:,}")
    if "mean_local_purity" in summary:
        body_lines.append(f"- **Mean local purity**: {summary['mean_local_purity']:.3f}")

    # Running parameters (for reproducibility)
    if current_params:
        body_lines.append("")
        body_lines.append("### Running Parameters\n")
        for k, v in current_params.items():
            if k != "method":
                body_lines.append(f"- `{k}`: **{v}**")

    # Actionable next-step suggestions based on actual results
    next_steps = _generate_next_steps(summary, n_cells)
    if next_steps:
        body_lines.append("")
        body_lines.append("### 💡 Next Steps\n")
        body_lines.extend(next_steps)

    body_lines.extend([
        "",
        "### Domain sizes\n",
        "| Domain | Cells | Proportion |",
        "|--------|-------|------------|",
    ])

    total_cells = sum(summary["domain_counts"].values())
    for domain, count in sorted(
        summary["domain_counts"].items(),
        key=lambda x: int(x[0]) if x[0].isdigit() else x[0],
    ):
        pct = count / total_cells * 100 if total_cells > 0 else 0
        body_lines.append(f"| {domain} | {count} | {pct:.1f}% |")

    body_lines.append("")
    body_lines.append("## Parameters\n")
    for k, v in params.items():
        if v is not None:
            body_lines.append(f"- `{k}`: {v}")

    body_lines.extend([
        "",
        "## Visualization Outputs\n",
        "- `figures/manifest.json`: Standard Python gallery manifest",
        "- `figure_data/`: Figure-ready CSV exports for downstream customization",
        "- `reproducibility/r_visualization.sh`: Optional R visualization entrypoint",
    ])

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "params": params,
        "current_params": current_params or params,
    }
    if gallery_context:
        method_embedding = gallery_context.get("method_embedding") or {}
        result_data["visualization"] = {
            "recipe_id": "standard-spatial-domain-gallery",
            "domain_column": gallery_context.get("domain_col", "spatial_domain"),
            "purity_column": gallery_context.get("purity_col"),
            "method_embedding_key": method_embedding.get("key"),
            "method_embedding_label": method_embedding.get("label"),
            "neighbor_k": gallery_context.get("neighbor_k"),
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
    params: dict,
    *,
    current_params: dict | None = None,
    input_file: str | None = None,
) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    run_params = current_params or params
    cmd = (
        f"python {SCRIPT_REL_PATH} "
        f"{'--input <input.h5ad>' if input_file else '--demo'} "
        f"--output {shlex.quote(str(output_dir))}"
    )
    for k, v in run_params.items():
        cmd = _append_cli_flag(cmd, k, v)

    command_lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        "",
        "# Re-run this analysis with the same key parameters.",
        "# Replace placeholders before running.",
        cmd,
        "",
    ]
    (repro_dir / "commands.sh").write_text("\n".join(command_lines))

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    method = str(params.get("method", "")).lower()

    def _pkg_line(candidates: list[str]) -> str:
        for pkg in candidates:
            try:
                return f"{pkg}=={_get_version(pkg)}"
            except Exception:
                continue
        # Keep the first candidate as the canonical package name in fallback output.
        return f"{candidates[0]}=?"

    # Base dependencies needed for all methods in this skill.
    package_groups: list[list[str]] = [
        ["scanpy"],
        ["anndata"],
        ["squidpy"],
        ["numpy"],
        ["pandas"],
        ["matplotlib"],
        ["scikit-learn"],
    ]

    # Method-specific dependencies (minimal & accurate, avoids unrelated packages).
    # Custom mappings for methods requiring special package names or extra dependencies.
    method_packages: dict[str, list[list[str]]] = {
        "leiden": [["igraph"], ["leidenalg"]],
        "louvain": [["igraph"], ["louvain"]],
        "spagcn": [["torch"], ["SpaGCN"]],
        "stagate": [["torch"], ["torch-geometric", "torch_geometric"]],
        "graphst": [["torch"], ["GraphST"]],
        # Module name is `banksy`, distribution name is commonly `pybanksy`.
        "banksy": [["pybanksy", "banksy"]],
        "cellcharter": [["cellcharter"]],
    }
    
    # Auto-resolve extra packages. If a method isn't explicitly defined above,
    # assume the PyPI package name matches the method name exactly.
    extra_pkgs = method_packages.get(method)
    if extra_pkgs is None and method:
        extra_pkgs = [[method]]
        
    if extra_pkgs:
        package_groups.extend(extra_pkgs)

    env_lines: list[str] = []
    seen: set[str] = set()
    for candidates in package_groups:
        line = _pkg_line(candidates)
        key = line.split("==", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        env_lines.append(line)

    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")
    _write_r_visualization_helper(output_dir)


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data():
    """Load the built-in demo dataset."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_visium.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path), str(demo_path)

    logger.info("Demo file not found, generating synthetic data")
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
    from generate_demo_data import generate_demo_visium
    return generate_demo_visium(), None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def main():
    parser = argparse.ArgumentParser(
        description="Spatial Domains — multi-method tissue region identification",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(SUPPORTED_METHODS), default="leiden")
    parser.add_argument(
        "--data-type",
        default=None,
        help="Input platform hint for method-specific routing (e.g. visium, slide_seq, xenium).",
    )
    parser.add_argument("--n-domains", type=int, default=None, help="Target number of domains (defaults to 7 for GNNs and CellCharter fixed-K mode)")
    parser.add_argument("--epochs", type=int, default=100, help="Max training epochs (for GraphST/SpaGCN/STAGATE)")
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--spatial-weight", type=float, default=0.3)
    # STAGATE network params
    parser.add_argument("--rad-cutoff", type=float, default=None)
    parser.add_argument("--k-nn", type=int, default=6)
    parser.add_argument("--stagate-alpha", type=float, default=0.0, help="Cell type-aware module weight (0 to disable)")
    parser.add_argument("--pre-resolution", type=float, default=0.2, help="STAGATE Louvain pre-clustering resolution")
    # GraphST
    parser.add_argument("--dim-output", type=int, default=64, help="GraphST embedding output dimension")
    # BANKSY param
    parser.add_argument("--lambda-param", type=float, default=0.2, help="Mixing param for spatial vs expression")
    parser.add_argument("--num-neighbours", type=int, default=15, help="Spatial neighbors for feature construction (k_geom)")
    # SpaGCN
    parser.add_argument("--spagcn-p", type=float, default=0.5, help="Spatial neighbor contribution in graph (0 to 1)")
    # CellCharter params
    parser.add_argument("--auto-k", type=str2bool, nargs='?', const=True, default=False, help="Enable automatic selection of the best number of clusters (CellCharter)")
    parser.add_argument("--auto-k-min", type=int, default=2, help="Minimum K to evaluate when auto-k is enabled")
    parser.add_argument("--auto-k-max", type=int, default=None, help="Maximum K to evaluate when auto-k is enabled")
    parser.add_argument("--n-layers", type=int, default=3, help="Number of spatial neighborhood hops to aggregate (CellCharter)")
    parser.add_argument("--use-rep", type=str, default=None, help="Feature representation to use (e.g., X_pca)")
    
    parser.add_argument("--refine", type=str2bool, nargs='?', const=True, default=False)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
        if "X_pca" not in adata.obsm:
            logger.warning(
                "Input data lacks 'X_pca' in obsm. Auto-computing PCA now."
            )
            sc.tl.pca(adata, n_comps=min(50, adata.n_vars - 1))
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    # Ensure GNNs have a default target n_domains if none was passed
    if args.n_domains is None and args.method in ["spagcn", "stagate", "graphst"]:
        logger.info("Method '%s' strictly requires 'n_domains'. Defaulting to 7.", args.method)
        args.n_domains = 7
    if args.n_domains is None and args.method == "cellcharter" and not args.auto_k:
        logger.info("Method '%s' defaults to 'n_domains=7' when auto-k is disabled.", args.method)
        args.n_domains = 7

    # Helpful parameter reminders and current status
    param_tips = {
        "leiden": "1. --resolution (granularity, default 1.0)  2. --spatial-weight (spatial influence, default 0.3)",
        "louvain": "1. --resolution (granularity, default 1.0)  2. --spatial-weight (spatial influence, default 0.3)",
        "spagcn": "1. --spagcn-p (neighborhood cont, default 0.5)  2. --n-domains (clusters)  3. --epochs (default 100)",
        "stagate": "1. --rad-cutoff / --k-nn (spatial network)  2. --stagate-alpha + --pre-resolution (cell type aware)  3. --epochs",
        "graphst": "1. --epochs (default ~600, lower for huge data)  2. --dim-output (default 64)  3. --n-domains",
        "banksy": "1. --lambda-param (0.2 cell-typing / 0.8 domain-finding)  2. --num-neighbours (k_geom, default 15)  3. --resolution / --n-domains",
        "cellcharter": "1. --auto-k (automatic best K) or fixed K=7 by default  2. --n-domains (override fixed K)  3. --n-layers (default 3)  4. --use-rep (e.g., X_pca)"
    }
    
    # Collect current parameters specific to the method
    current_params = {"method": args.method}
    if args.data_type:
        current_params["data_type"] = args.data_type
    if args.method in ["leiden", "louvain", "banksy"]:
        current_params["resolution"] = args.resolution
    if args.method in ["leiden", "louvain"]:
        current_params["spatial_weight"] = args.spatial_weight
    if args.n_domains is not None:
        current_params["n_domains"] = args.n_domains
    if args.epochs is not None and args.method in ["spagcn", "stagate", "graphst"]:
        current_params["epochs"] = args.epochs
    if args.method == "stagate":
        current_params["rad_cutoff"] = args.rad_cutoff
        current_params["k_nn"] = args.k_nn
        current_params["stagate_alpha"] = args.stagate_alpha
        current_params["pre_resolution"] = args.pre_resolution
    if args.method == "banksy":
        current_params["lambda_param"] = args.lambda_param
        current_params["num_neighbours"] = args.num_neighbours
    if args.method == "cellcharter":
        current_params["auto_k"] = args.auto_k
        if args.auto_k:
            current_params["auto_k_min"] = args.auto_k_min
            if args.auto_k_max is not None:
                current_params["auto_k_max"] = args.auto_k_max
        current_params["n_layers"] = args.n_layers
        if args.use_rep is not None:
            current_params["use_rep"] = args.use_rep
    if args.method == "spagcn":
        current_params["spagcn_p"] = args.spagcn_p
    if args.method == "graphst":
        current_params["dim_output"] = args.dim_output

    print("\n" + "="*60)
    print(f"🚀 SPATIAL DOMAIN IDENTIFICATION: {args.method.upper()}")
    print("-" * 60)
    print("🔧 CURRENT RUNNING PARAMETERS:")
    for k, v in current_params.items():
        if k != "method":
            print(f"   • {k}: {v}")
    
    if args.method in param_tips:
        print("\n💡 TUNING TIPS (Priority Checklist):")
        for tip in param_tips[args.method].split("  "):
            print(f"   {tip.strip()}")
    print("="*60 + "\n")

    # Dispatch to the chosen algorithm via _lib
    summary = dispatch_method(
        args.method, adata,
        resolution=args.resolution,
        spatial_weight=args.spatial_weight,
        n_domains=args.n_domains,  # Safe variable
        epochs=args.epochs,
        data_type=args.data_type,
        rad_cutoff=args.rad_cutoff,
        k_nn=args.k_nn,
        stagate_alpha=args.stagate_alpha,
        pre_resolution=args.pre_resolution,
        dim_output=args.dim_output,
        lambda_param=args.lambda_param,
        num_neighbours=args.num_neighbours,
        spagcn_p=args.spagcn_p,
        auto_k=args.auto_k,
        auto_k_min=args.auto_k_min,
        auto_k_max=args.auto_k_max,
        n_layers=args.n_layers,
        use_rep=args.use_rep,
    )

    if args.refine:
        logger.info("Applying spatial KNN refinement ...")
        refined = refine_spatial_domains(adata)
        adata.obs["spatial_domain"] = pd.Categorical(refined)
        summary["domain_counts"] = adata.obs["spatial_domain"].value_counts().to_dict()
        summary["n_domains"] = adata.obs["spatial_domain"].nunique()
        summary["refined"] = True

    params = {"method": args.method, "resolution": args.resolution,
              "spatial_weight": args.spatial_weight, "refine": args.refine}
    if args.n_domains is not None:
        params["n_domains"] = args.n_domains
    if args.epochs is not None:
        params["epochs"] = args.epochs
    if args.data_type:
        params["data_type"] = args.data_type
    if args.method == "stagate":
        params["rad_cutoff"] = args.rad_cutoff
        params["k_nn"] = args.k_nn
        params["stagate_alpha"] = args.stagate_alpha
    if args.method == "banksy":
        params["lambda_param"] = args.lambda_param
        params["num_neighbours"] = args.num_neighbours
    if args.method == "cellcharter":
        params["auto_k"] = args.auto_k
        params["n_layers"] = args.n_layers
        if args.use_rep is not None:
            params["use_rep"] = args.use_rep
    if args.method == "spagcn":
        params["spagcn_p"] = args.spagcn_p
    if args.method == "graphst":
        params["dim_output"] = args.dim_output

    if "spatial_domain" in adata.obs.columns:
        import re
        def _natsort_key(s, _nsre=re.compile('([0-9]+)')):
            return [int(text) if text.isdigit() else text.lower() for text in _nsre.split(str(s))]
        try:
            # Ensure the column is properly categorical before reordering
            adata.obs["spatial_domain"] = adata.obs["spatial_domain"].astype("category")
            cats = adata.obs["spatial_domain"].cat.categories.tolist()
            sorted_cats = sorted(cats, key=_natsort_key)
            adata.obs["spatial_domain"] = adata.obs["spatial_domain"].cat.reorder_categories(sorted_cats)
        except Exception as e:
            logger.debug("Could not naturally sort spatial_domain categories: %s", e)

    gallery_context = _prepare_domain_gallery_context(adata, summary)
    adata.uns["spatial_domains_summary"] = summary.copy()
    generate_figures(adata, output_dir, summary, gallery_context=gallery_context)
    export_tables(output_dir, adata, summary, gallery_context=gallery_context)
    write_report(
        output_dir,
        adata,
        summary,
        input_file,
        params,
        current_params=current_params,
        n_cells=adata.n_obs,
        gallery_context=gallery_context,
    )
    write_reproducibility(
        output_dir,
        params,
        current_params=current_params,
        input_file=input_file,
    )
    store_analysis_metadata(adata, SKILL_NAME, summary["method"], params=params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(f"Domain identification complete: {summary['n_domains']} domains ({summary['method']})")


if __name__ == "__main__":
    main()
