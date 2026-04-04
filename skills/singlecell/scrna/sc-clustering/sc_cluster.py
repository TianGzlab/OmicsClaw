#!/usr/bin/env python3
"""Single-Cell Clustering - neighbors, UMAP, and graph clustering."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
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
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import dimred as sc_dimred_utils
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib.preflight import apply_preflight, PreflightDecision, _obs_candidates, _format_candidates
from skills.singlecell._lib import dependency_manager as sc_dep_manager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-clustering"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-clustering/sc_cluster.py"


def _candidate_embeddings(adata) -> list[str]:
    preferred = [key for key in ("X_pca", "X_harmony", "X_scvi", "X_scanvi", "X_scanorama") if key in adata.obsm]
    if preferred:
        return preferred
    return [str(key) for key in adata.obsm.keys() if str(key).startswith("X_")]


def preflight_sc_clustering(
    adata,
    *,
    cluster_method: str,
    use_rep: str | None,
    source_path: str | None = None,
) -> PreflightDecision:
    decision = PreflightDecision(SKILL_NAME)
    ensure_input_contract(adata, source_path=source_path)

    matrix_contract = get_matrix_contract(adata)
    x_kind = matrix_contract.get("X") or infer_x_matrix_kind(adata)
    if x_kind != "normalized_expression":
        decision.block(
            "`sc-clustering` expects normalized expression from `sc-preprocessing` or an integrated embedding workflow."
        )
        return decision

    candidates = _candidate_embeddings(adata)
    if use_rep:
        if use_rep not in adata.obsm:
            decision.require_field(
                "use_rep",
                f"`--use-rep {use_rep}` was not found. Available embeddings: {_format_candidates(candidates)}.",
                aliases=["use_rep", "embedding", "embedding_key"],
                flag="--use-rep",
            )
    else:
        if not candidates:
            decision.block(
                "`sc-clustering` needs an embedding such as `X_pca`, `X_harmony`, or `X_scvi`. Run `sc-preprocessing` first, or use an integrated object."
            )
        elif len(candidates) > 1:
            decision.require_field(
                "use_rep",
                f"Multiple embeddings are available: {_format_candidates(candidates)}. Confirm which one should drive neighbors/UMAP/clustering.",
                aliases=["use_rep", "embedding", "embedding_key"],
                flag="--use-rep",
                choices=candidates,
            )
        else:
            decision.add_guidance(f"`sc-clustering` will use `{candidates[0]}` as the active embedding.")

    if cluster_method not in {"leiden", "louvain"}:
        decision.block("`sc-clustering` currently supports `--cluster-method leiden` or `louvain`.")
    elif cluster_method == "louvain" and not sc_dep_manager.is_available("louvain"):
        decision.block(
            "`louvain` clustering requires the optional Python package `louvain`, which is not installed in the current environment. Install it explicitly before rerunning."
        )

    batch_candidates = _obs_candidates(adata, "batch")
    if batch_candidates and not any(key in adata.obsm for key in ("X_harmony", "X_scvi", "X_scanvi", "X_scanorama")):
        decision.add_guidance(
            f"Potential batch/sample columns were detected: {_format_candidates(batch_candidates)}. If batch effects are expected, consider `sc-batch-integration` before clustering."
        )

    return decision


def _resolve_use_rep(adata, use_rep: str | None) -> str:
    if use_rep:
        return use_rep
    candidates = _candidate_embeddings(adata)
    if not candidates:
        raise ValueError("No embedding available for clustering.")
    return candidates[0]


def run_clustering(
    adata,
    *,
    use_rep: str,
    n_neighbors: int = 15,
    n_pcs: int = 50,
    cluster_method: str = "leiden",
    resolution: float = 1.0,
) -> tuple[object, dict]:
    sc_dimred_utils.build_neighbor_graph(
        adata,
        n_neighbors=n_neighbors,
        n_pcs=n_pcs,
        use_rep=use_rep,
        inplace=True,
    )
    sc_dimred_utils.run_umap_reduction(adata, inplace=True)
    cluster_key = cluster_method
    if cluster_method == "leiden":
        sc_dimred_utils.cluster_leiden(adata, resolution=resolution, key_added=cluster_key, inplace=True)
    else:
        sc_dimred_utils.cluster_louvain(adata, resolution=resolution, key_added=cluster_key, inplace=True)
    return adata, {"cluster_key": cluster_key}


def _build_cluster_summary_table(summary: dict) -> pd.DataFrame:
    counts = summary.get("cluster_counts", {})
    total = max(int(summary.get("n_cells", 0)), 1)
    rows = [
        {"cluster": str(cluster), "n_cells": int(count), "proportion_pct": round(int(count) / total * 100, 2)}
        for cluster, count in counts.items()
    ]
    return pd.DataFrame(rows)


def _build_umap_points_table(adata, cluster_key: str) -> pd.DataFrame:
    coords = np.asarray(adata.obsm["X_umap"])
    return pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "UMAP1": coords[:, 0],
            "UMAP2": coords[:, 1],
            cluster_key: adata.obs[cluster_key].astype(str).to_numpy(),
        }
    )


def _build_clustering_summary_table(summary: dict, params: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric": "cluster_method", "value": summary.get("cluster_method")},
            {"metric": "cluster_key", "value": summary.get("cluster_key")},
            {"metric": "n_cells", "value": summary.get("n_cells")},
            {"metric": "n_clusters", "value": summary.get("n_clusters")},
            {"metric": "use_rep", "value": params.get("use_rep")},
            {"metric": "n_neighbors", "value": params.get("n_neighbors")},
            {"metric": "n_pcs", "value": params.get("n_pcs")},
            {"metric": "resolution", "value": params.get("resolution")},
        ]
    )


def _prepare_gallery_context(adata, summary: dict, params: dict, output_dir: Path) -> dict:
    cluster_key = summary["cluster_key"]
    return {
        "output_dir": Path(output_dir),
        "cluster_key": cluster_key,
        "cluster_summary_df": _build_cluster_summary_table(summary),
        "umap_points_df": _build_umap_points_table(adata, cluster_key),
        "clustering_summary_df": _build_clustering_summary_table(summary, params),
    }


def _build_visualization_recipe(summary: dict) -> VisualizationRecipe:
    cluster_key = summary["cluster_key"]
    return VisualizationRecipe(
        recipe_id="standard-sc-clustering-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell clustering gallery",
        description="Default OmicsClaw gallery for graph construction, UMAP, and clustering.",
        plots=[
            PlotSpec(
                plot_id="clustering_umap",
                role="overview",
                renderer="umap_clusters",
                filename=f"umap_{cluster_key}.png",
                title="UMAP clusters",
                description="UMAP embedding colored by the active clustering column.",
                required_obsm=["X_umap"],
                required_obs=[cluster_key],
            ),
            PlotSpec(
                plot_id="clustering_pca_variance",
                role="supporting",
                renderer="pca_variance",
                filename="pca_variance.png",
                title="PCA variance",
                description="Explained variance across principal components.",
                required_obsm=["X_pca"],
                required_uns=["pca"],
            ),
            PlotSpec(
                plot_id="clustering_pca_scatter",
                role="supporting",
                renderer="pca_scatter",
                filename="pca_scatter.png",
                title="PCA embedding",
                description="First two principal components colored by cluster labels.",
                required_obsm=["X_pca"],
                required_obs=[cluster_key],
            ),
        ],
    )


def _gallery_figure_path(output_dir: Path, filename: str) -> Path:
    return Path(output_dir) / "figures" / filename


def _render_umap_clusters(adata, spec: PlotSpec, context: dict) -> object:
    sc_dimred_utils.plot_umap_clusters(adata, context["output_dir"], cluster_key=context["cluster_key"])
    path = _gallery_figure_path(context["output_dir"], spec.filename)
    return path if path.exists() else None


def _render_pca_variance(adata, spec: PlotSpec, context: dict) -> object:
    sc_dimred_utils.plot_pca_variance(adata, context["output_dir"], n_pcs=min(50, adata.obsm["X_pca"].shape[1]))
    path = _gallery_figure_path(context["output_dir"], spec.filename)
    return path if path.exists() else None


def _render_pca_scatter(adata, spec: PlotSpec, context: dict) -> object:
    sc_dimred_utils.plot_pca_scatter(adata, context["output_dir"], color=context["cluster_key"])
    path = _gallery_figure_path(context["output_dir"], spec.filename)
    return path if path.exists() else None


CLUSTER_GALLERY_RENDERERS = {
    "umap_clusters": _render_umap_clusters,
    "pca_variance": _render_pca_variance,
    "pca_scatter": _render_pca_scatter,
}


def _write_figure_data(output_dir: Path, context: dict, recipe: VisualizationRecipe, artifacts) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    context["cluster_summary_df"].to_csv(figure_data_dir / "cluster_summary.csv", index=False)
    context["umap_points_df"].to_csv(figure_data_dir / "umap_points.csv", index=False)
    context["clustering_summary_df"].to_csv(figure_data_dir / "clustering_summary.csv", index=False)
    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": recipe.recipe_id,
        "available_files": {
            "cluster_summary": "cluster_summary.csv",
            "umap_points": "umap_points.csv",
            "clustering_summary": "clustering_summary.csv",
        },
        "plots": [
            {"plot_id": artifact.plot_id, "filename": artifact.filename, "status": artifact.status, "role": artifact.role}
            for artifact in artifacts
        ],
    }
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    context["figure_data_files"] = manifest["available_files"]


def write_report(output_dir: Path, summary: dict, params: dict, input_file: str | None, *, gallery_context: dict) -> None:
    header = generate_report_header(
        title="Single-Cell Clustering Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Clustering": summary["cluster_method"],
            "Cells": str(summary["n_cells"]),
            "Clusters": str(summary["n_clusters"]),
        },
    )
    body = [
        "## Summary\n",
        f"- **Embedding used**: `{params['use_rep']}`",
        f"- **Cluster method**: {summary['cluster_method']}",
        f"- **Cluster key**: `{summary['cluster_key']}`",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Clusters**: {summary['n_clusters']}",
        "",
        "## Effective Parameters\n",
        f"- `n_neighbors`: {params['n_neighbors']}",
        f"- `n_pcs`: {params['n_pcs']}",
        f"- `resolution`: {params['resolution']}",
        "",
        "## Output Files\n",
        "- `processed.h5ad` — clustered AnnData with `neighbors`, `X_umap`, and cluster labels.",
        "- `figures/` — standard clustering gallery.",
        "- `tables/cluster_summary.csv` — per-cluster cell counts.",
        "- `figure_data/umap_points.csv` — UMAP coordinates for downstream styling.",
    ]
    report = header + "\n".join(body) + "\n" + generate_report_footer()
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def write_reproducibility(output_dir: Path, params: dict, input_file: str | None, *, demo_mode: bool = False) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    else:
        command_parts.extend(["--input", "<input.h5ad>"])
    command_parts.extend(["--output", str(output_dir)])
    for key in ("cluster_method", "use_rep", "n_neighbors", "n_pcs", "resolution"):
        value = params.get(key)
        if value not in (None, ""):
            command_parts.extend([f"--{key.replace('_', '-')}", str(value)])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")


def build_summary(adata, *, cluster_key: str, cluster_method: str) -> dict:
    cluster_counts = adata.obs[cluster_key].astype(str).value_counts().to_dict()
    return {
        "cluster_key": cluster_key,
        "cluster_method": cluster_method,
        "n_cells": int(adata.n_obs),
        "n_clusters": len(cluster_counts),
        "cluster_counts": {str(k): int(v) for k, v in cluster_counts.items()},
    }


def get_demo_data():
    adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
    return adata


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Clustering")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--cluster-method", choices=["leiden", "louvain"], default="leiden")
    parser.add_argument("--use-rep", default=None, help="Embedding in adata.obsm to use, e.g. X_pca or X_harmony")
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--n-pcs", type=int, default=50)
    parser.add_argument("--resolution", type=float, default=1.0)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata = get_demo_data()
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME)
        input_file = args.input_path

    apply_preflight(
        preflight_sc_clustering(
            adata,
            cluster_method=args.cluster_method,
            use_rep=args.use_rep,
            source_path=input_file,
        ),
        logger,
    )

    use_rep = _resolve_use_rep(adata, args.use_rep)
    adata, _ = run_clustering(
        adata,
        use_rep=use_rep,
        n_neighbors=args.n_neighbors,
        n_pcs=args.n_pcs,
        cluster_method=args.cluster_method,
        resolution=args.resolution,
    )
    summary = build_summary(adata, cluster_key=args.cluster_method, cluster_method=args.cluster_method)
    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind="normalized_expression",
        raw_kind=get_matrix_contract(adata).get("raw"),
        primary_cluster_key=summary["cluster_key"],
    )

    gallery_context = _prepare_gallery_context(adata, summary, {
        "use_rep": use_rep,
        "n_neighbors": args.n_neighbors,
        "n_pcs": args.n_pcs,
        "resolution": args.resolution,
    }, output_dir)
    recipe = _build_visualization_recipe(summary)
    artifacts = render_plot_specs(adata, output_dir, recipe, CLUSTER_GALLERY_RENDERERS, context=gallery_context)
    _write_figure_data(output_dir, gallery_context, recipe, artifacts)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    gallery_context["cluster_summary_df"].to_csv(tables_dir / "cluster_summary.csv", index=False)
    gallery_context["clustering_summary_df"].to_csv(tables_dir / "clustering_summary.csv", index=False)
    gallery_context["umap_points_df"].to_csv(tables_dir / "umap_points.csv", index=False)

    params = {
        "cluster_method": args.cluster_method,
        "use_rep": use_rep,
        "n_neighbors": args.n_neighbors,
        "n_pcs": args.n_pcs,
        "resolution": args.resolution,
    }
    write_report(output_dir, summary, params, input_file, gallery_context=gallery_context)
    write_reproducibility(output_dir, params, input_file, demo_mode=args.demo)

    store_analysis_metadata(adata, SKILL_NAME, args.cluster_method, params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "params": params,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        "visualization": {
            "recipe_id": recipe.recipe_id,
            "cluster_column": summary["cluster_key"],
            "umap_key": "X_umap",
            "available_figure_data": gallery_context.get("figure_data_files", {}),
        },
        **summary,
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Single-cell graph construction, UMAP, and clustering.",
        result_payload=result_payload,
        preferred_method=args.cluster_method,
    )

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Clusters: {summary['n_clusters']}")


if __name__ == "__main__":
    main()
