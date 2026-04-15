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
from sklearn.metrics import silhouette_score

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
    write_replot_hint,
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
from skills.singlecell._lib.viz import (
    plot_cluster_qc_heatmap,
    plot_cluster_size_summary,
    plot_embedding_categorical,
    plot_embedding_comparison,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-clustering"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-clustering/sc_cluster.py"

R_ENHANCED_PLOTS = {
    "plot_embedding_discrete": "r_embedding_discrete.png",
    "plot_embedding_feature": "r_embedding_feature.png",
    "plot_cell_barplot": "r_cell_barplot.png",
    "plot_cell_proportion": "r_cell_proportion.png",
}


def _candidate_embeddings(adata) -> list[str]:
    preferred = [key for key in ("X_pca", "X_harmony", "X_scvi", "X_scanvi", "X_scanorama") if key in adata.obsm]
    if preferred:
        return preferred
    return [str(key) for key in adata.obsm.keys() if str(key).startswith("X_")]


def _embedding_key_from_method(embedding_method: str) -> str:
    mapping = {
        "umap": "X_umap",
        "tsne": "X_tsne",
        "diffmap": "X_diffmap",
        "phate": "X_phate",
    }
    return mapping[embedding_method]


def preflight_sc_clustering(
    adata,
    *,
    cluster_method: str,
    embedding_method: str,
    use_rep: str | None,
    tsne_perplexity: float,
    diffmap_n_comps: int,
    phate_knn: int,
    phate_decay: int,
    n_neighbors: int,
    n_pcs: int,
    resolution: float,
    umap_min_dist: float,
    umap_spread: float,
    tsne_metric: str,
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

    decision.add_guidance(
        "`sc-clustering` is the stage after base preprocessing. It builds a neighbor graph, renders a low-dimensional view, and writes cluster labels."
    )

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

    if embedding_method not in {"umap", "tsne", "diffmap", "phate"}:
        decision.block("`sc-clustering` currently supports `--embedding-method umap`, `tsne`, `diffmap`, or `phate`.")
    if cluster_method not in {"leiden", "louvain"}:
        decision.block("`sc-clustering` currently supports `--cluster-method leiden` or `louvain`.")
    elif cluster_method == "louvain" and not sc_dep_manager.is_available("louvain"):
        decision.block(
            "`louvain` clustering requires the optional Python package `louvain`, which is not installed in the current environment. Install it explicitly before rerunning."
        )
    if embedding_method == "tsne" and tsne_perplexity <= 0:
        decision.block("`--tsne-perplexity` must be greater than 0.")
    if embedding_method == "diffmap" and diffmap_n_comps < 2:
        decision.block("`--diffmap-n-comps` must be at least 2.")
    if embedding_method == "phate" and not sc_dep_manager.is_available("phate"):
        decision.block(
            "`phate` embedding requires the optional Python package `phate`, which is not installed in the current environment. Install it explicitly before rerunning."
        )
    if embedding_method == "phate" and phate_knn < 2:
        decision.block("`--phate-knn` must be at least 2.")

    batch_candidates = _obs_candidates(adata, "batch")
    if batch_candidates and not any(key in adata.obsm for key in ("X_harmony", "X_scvi", "X_scanvi", "X_scanorama")):
        decision.add_guidance(
            f"Potential batch/sample columns were detected: {_format_candidates(batch_candidates)}. If batch effects are expected, consider `sc-batch-integration` before clustering."
        )

    decision.add_guidance(
        f"Current first-pass settings: `embedding_method={embedding_method}`, `cluster_method={cluster_method}`, `n_neighbors={n_neighbors}`, `n_pcs={n_pcs}`, `resolution={resolution}`."
    )
    if embedding_method == "umap":
        decision.add_guidance(
            f"`umap`-specific settings: `umap_min_dist={umap_min_dist}`, `umap_spread={umap_spread}`."
        )
    elif embedding_method == "tsne":
        decision.add_guidance(
            f"`tsne`-specific settings: `tsne_perplexity={tsne_perplexity}`, `tsne_metric={tsne_metric}`."
        )
    elif embedding_method == "phate":
        decision.add_guidance(
            f"`phate`-specific settings: `phate_knn={phate_knn}`, `phate_decay={phate_decay}`."
        )
    else:
        decision.add_guidance(
            f"`diffmap`-specific settings: `diffmap_n_comps={diffmap_n_comps}`."
        )
    decision.add_guidance(
        "After clustering, the usual next steps are `sc-markers` for marker discovery, `sc-cell-annotation` for label transfer, or `sc-de` for group-level comparison."
    )

    return decision


def auto_resolution(
    adata,
    *,
    use_rep: str,
    cluster_method: str = "leiden",
    resolutions: list[float] | None = None,
    n_subsample_reps: int = 5,
    subsample_fraction: float = 0.8,
    random_state: int = 1,
) -> tuple[float, dict]:
    """Find the optimal clustering resolution via bootstrap subsampling + silhouette scoring.

    For each candidate resolution, the method:
    1. Repeatedly subsamples the data (``n_subsample_reps`` times).
    2. Clusters each subsample and builds a co-clustering distance matrix.
    3. Computes the silhouette score of the full-data clustering against the
       co-clustering distances (precomputed metric).
    4. Selects the resolution with the highest silhouette score.

    Parameters
    ----------
    adata
        AnnData with a neighbor graph already built.
    use_rep
        Embedding key used for the neighbor graph (informational; the graph
        must already be present in ``adata.uns['neighbors']``).
    cluster_method
        ``"leiden"`` or ``"louvain"``.
    resolutions
        Candidate resolutions to evaluate.  Default ``[0.4, 0.6, 0.8, 1.0, 1.2, 1.4]``.
    n_subsample_reps
        Number of bootstrap subsampling rounds per resolution.
    subsample_fraction
        Fraction of cells to keep in each subsample.
    random_state
        Random seed.

    Returns
    -------
    best_resolution
        The resolution with the highest silhouette score.
    search_info
        Dictionary with ``silhouette_scores``, ``best_resolution``, and
        ``resolution_df`` (a pandas DataFrame of resolution vs score).
    """
    if resolutions is None:
        resolutions = [0.4, 0.6, 0.8, 1.0, 1.2, 1.4]

    cluster_func = sc.tl.leiden if cluster_method == "leiden" else sc.tl.louvain
    cluster_obs_key = cluster_method

    sample_n = adata.n_obs
    subsample_n = int(sample_n * subsample_fraction)
    rng = np.random.RandomState(random_state)

    silhouette_avg: dict[str, float] = {}
    best_resolution = resolutions[0]
    highest_sil = -1.0

    logger.info("Auto-resolution search over %d candidates: %s", len(resolutions), resolutions)

    for r in resolutions:
        r = round(r, 2)
        r_key = f"{cluster_obs_key}_r{r}"
        logger.info("  Testing resolution %.2f ...", r)

        # Build co-clustering distance matrix via bootstrap subsampling
        subsampling_n = np.zeros((sample_n, sample_n), dtype=np.float32)
        coclustering_n = np.zeros((sample_n, sample_n), dtype=np.float32)

        for _rep in range(n_subsample_reps):
            subsample_idx = rng.choice(sample_n, subsample_n, replace=False)
            sub_adata = adata[subsample_idx].copy()
            cluster_func(sub_adata, resolution=r, key_added=cluster_obs_key)
            cluster_labels = sub_adata.obs[cluster_obs_key].to_numpy()

            for i in range(subsample_n):
                for j in range(i + 1, subsample_n):
                    xi, xj = subsample_idx[i], subsample_idx[j]
                    subsampling_n[xi, xj] += 1
                    subsampling_n[xj, xi] += 1
                    if cluster_labels[i] == cluster_labels[j]:
                        coclustering_n[xi, xj] += 1
                        coclustering_n[xj, xi] += 1

        # Avoid division by zero
        safe_denom = subsampling_n.copy()
        safe_denom[safe_denom == 0] = 1e6
        distance = 1.0 - coclustering_n / safe_denom
        np.fill_diagonal(distance, 0.0)

        # Full-data clustering at this resolution
        cluster_func(adata, resolution=r, key_added=r_key)
        labels = adata.obs[r_key].to_numpy()

        # Need at least 2 distinct labels for silhouette
        n_unique = len(set(labels))
        if n_unique < 2:
            sil = -1.0
        else:
            sil = float(silhouette_score(distance, labels, metric="precomputed"))

        silhouette_avg[str(r)] = sil
        logger.info("    resolution=%.2f  silhouette=%.4f  clusters=%d", r, sil, n_unique)

        if sil > highest_sil:
            highest_sil = sil
            best_resolution = r

    # Set the best clustering as the primary cluster key
    best_key = f"{cluster_obs_key}_r{best_resolution}"
    adata.obs[cluster_obs_key] = adata.obs[best_key]

    # Clean up intermediate resolution columns
    for r in resolutions:
        r = round(r, 2)
        r_key = f"{cluster_obs_key}_r{r}"
        if r_key in adata.obs.columns and r_key != best_key:
            del adata.obs[r_key]

    # Build summary DataFrame
    resolution_df = pd.DataFrame(
        [{"resolution": float(k), "silhouette_score": v} for k, v in silhouette_avg.items()]
    )

    search_info = {
        "silhouette_scores": silhouette_avg,
        "best_resolution": float(best_resolution),
        "highest_silhouette": float(highest_sil),
        "resolution_df": resolution_df,
        "n_subsample_reps": n_subsample_reps,
        "subsample_fraction": subsample_fraction,
    }

    logger.info("Auto-resolution selected: %.2f (silhouette=%.4f)", best_resolution, highest_sil)
    return float(best_resolution), search_info


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
    embedding_method: str = "umap",
    n_neighbors: int = 15,
    n_pcs: int = 50,
    cluster_method: str = "leiden",
    resolution: float = 1.0,
    umap_min_dist: float = 0.5,
    umap_spread: float = 1.0,
    tsne_perplexity: float = 30.0,
    tsne_metric: str = "euclidean",
    diffmap_n_comps: int = 15,
    phate_knn: int = 15,
    phate_decay: int = 40,
) -> tuple[object, dict]:
    sc_dimred_utils.build_neighbor_graph(
        adata,
        n_neighbors=n_neighbors,
        n_pcs=n_pcs,
        use_rep=use_rep,
        inplace=True,
    )
    cluster_key = cluster_method
    if cluster_method == "leiden":
        sc_dimred_utils.cluster_leiden(adata, resolution=resolution, key_added=cluster_key, inplace=True)
    else:
        sc_dimred_utils.cluster_louvain(adata, resolution=resolution, key_added=cluster_key, inplace=True)
    if embedding_method == "umap":
        sc_dimred_utils.run_umap_reduction(
            adata,
            min_dist=umap_min_dist,
            spread=umap_spread,
            inplace=True,
        )
    elif embedding_method == "tsne":
        sc_dimred_utils.run_tsne_reduction(
            adata,
            n_pcs=n_pcs,
            use_rep=use_rep,
            perplexity=tsne_perplexity,
            metric=tsne_metric,
            inplace=True,
        )
    elif embedding_method == "diffmap":
        sc_dimred_utils.run_diffmap(adata, n_comps=diffmap_n_comps, inplace=True)
    else:
        sc_dimred_utils.run_phate_reduction(
            adata,
            use_rep=use_rep,
            knn=phate_knn,
            decay=phate_decay,
            inplace=True,
        )
    embedding_key = _embedding_key_from_method(embedding_method)
    return adata, {"cluster_key": cluster_key, "embedding_key": embedding_key}


def _build_cluster_summary_table(summary: dict) -> pd.DataFrame:
    counts = summary.get("cluster_counts", {})
    total = max(int(summary.get("n_cells", 0)), 1)
    rows = [
        {"cluster": str(cluster), "n_cells": int(count), "proportion_pct": round(int(count) / total * 100, 2)}
        for cluster, count in counts.items()
    ]
    return pd.DataFrame(rows)


def _build_embedding_points_table(adata, cluster_key: str, embedding_key: str, extra_obs: list[str] | None = None) -> pd.DataFrame:
    coords = np.asarray(adata.obsm[embedding_key])
    x_name = "coord1"
    y_name = "coord2"
    frame = pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "embedding_key": embedding_key,
            x_name: coords[:, 0],
            y_name: coords[:, 1],
            cluster_key: adata.obs[cluster_key].astype(str).to_numpy(),
        }
    )
    for key in (extra_obs or []):
        if key in adata.obs.columns:
            frame[key] = adata.obs[key].astype(str).to_numpy()
    return frame


def _build_clustering_summary_table(summary: dict, params: dict) -> pd.DataFrame:
    rows = [
        {"metric": "embedding_method", "value": params.get("embedding_method")},
        {"metric": "embedding_key", "value": params.get("embedding_key")},
        {"metric": "cluster_method", "value": summary.get("cluster_method")},
        {"metric": "cluster_key", "value": summary.get("cluster_key")},
        {"metric": "n_cells", "value": summary.get("n_cells")},
        {"metric": "n_clusters", "value": summary.get("n_clusters")},
        {"metric": "use_rep", "value": params.get("use_rep")},
        {"metric": "n_neighbors", "value": params.get("n_neighbors")},
        {"metric": "n_pcs", "value": params.get("n_pcs")},
        {"metric": "resolution", "value": params.get("resolution")},
    ]
    if params.get("embedding_method") == "umap":
        rows.extend(
            [
                {"metric": "umap_min_dist", "value": params.get("umap_min_dist")},
                {"metric": "umap_spread", "value": params.get("umap_spread")},
            ]
        )
    elif params.get("embedding_method") == "tsne":
        rows.extend(
            [
                {"metric": "tsne_perplexity", "value": params.get("tsne_perplexity")},
                {"metric": "tsne_metric", "value": params.get("tsne_metric")},
            ]
        )
    elif params.get("embedding_method") == "diffmap":
        rows.append({"metric": "diffmap_n_comps", "value": params.get("diffmap_n_comps")})
    elif params.get("embedding_method") == "phate":
        rows.extend(
            [
                {"metric": "phate_knn", "value": params.get("phate_knn")},
                {"metric": "phate_decay", "value": params.get("phate_decay")},
            ]
        )
    return pd.DataFrame(rows)


def _prepare_gallery_context(adata, summary: dict, params: dict, output_dir: Path) -> dict:
    cluster_key = summary["cluster_key"]
    compare_candidates = (
        _obs_candidates(adata, "batch")
        or _obs_candidates(adata, "condition")
        or _obs_candidates(adata, "cell_type")
    )
    compare_key = compare_candidates[0] if compare_candidates else None
    if compare_key and compare_key == cluster_key:
        compare_key = None
    if compare_key and adata.obs[compare_key].astype(str).nunique(dropna=False) <= 1:
        compare_key = None
    if compare_key and adata.obs[compare_key].astype(str).equals(adata.obs[cluster_key].astype(str)):
        compare_key = None
    qc_df = pd.DataFrame()
    if any(col in adata.obs.columns for col in ("n_genes_by_counts", "total_counts", "pct_counts_mt")):
        try:
            qc_df = sc_dimred_utils.calculate_cluster_qc_stats(adata, cluster_key=cluster_key).reset_index()
        except Exception:
            qc_df = pd.DataFrame()
    return {
        "output_dir": Path(output_dir),
        "cluster_key": cluster_key,
        "embedding_key": params["embedding_key"],
        "embedding_method": params["embedding_method"],
        "compare_key": compare_key,
        "cluster_summary_df": _build_cluster_summary_table(summary),
        "embedding_points_df": _build_embedding_points_table(
            adata, cluster_key, params["embedding_key"], [compare_key] if compare_key else []
        ),
        "cluster_qc_df": qc_df,
        "clustering_summary_df": _build_clustering_summary_table(summary, params),
    }


def _build_visualization_recipe(summary: dict) -> VisualizationRecipe:
    cluster_key = summary["cluster_key"]
    return VisualizationRecipe(
        recipe_id="standard-sc-clustering-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell clustering gallery",
        description="Default OmicsClaw gallery for graph construction, embedding, and clustering.",
        plots=[
            PlotSpec(
                plot_id="clustering_embedding",
                role="overview",
                renderer="embedding_clusters",
                filename="embedding_clusters.png",
                title="Embedding clusters",
                description="Primary embedding colored by the active clustering column.",
                required_obs=[cluster_key],
            ),
            PlotSpec(
                plot_id="clustering_embedding_compare",
                role="supporting",
                renderer="embedding_comparison",
                filename="embedding_comparison.png",
                title="Embedding comparison",
                description="Side-by-side view of clusters and the most likely batch/sample grouping.",
                required_obs=[cluster_key],
            ),
            PlotSpec(
                plot_id="clustering_cluster_size",
                role="supporting",
                renderer="cluster_size_summary",
                filename="cluster_size_summary.png",
                title="Cluster sizes",
                description="Per-cluster size and proportion summary.",
                required_obs=[cluster_key],
            ),
            PlotSpec(
                plot_id="clustering_cluster_qc",
                role="supporting",
                renderer="cluster_qc_heatmap",
                filename="cluster_qc_heatmap.png",
                title="Cluster QC overview",
                description="Cluster-level mean genes, counts, and mitochondrial fraction when available.",
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


def _render_embedding_clusters(adata, spec: PlotSpec, context: dict) -> object:
    plot_embedding_categorical(
        adata,
        context["output_dir"],
        obsm_key=context["embedding_key"],
        color_key=context["cluster_key"],
        filename=spec.filename,
        title=f"{context['embedding_method'].upper()} clusters",
        subtitle=f"Embedding: {context['embedding_key']} | cluster: {context['cluster_key']}",
    )
    path = _gallery_figure_path(context["output_dir"], spec.filename)
    return path if path.exists() else None


def _render_embedding_comparison(adata, spec: PlotSpec, context: dict) -> object:
    if not context.get("compare_key"):
        return None
    compare_keys = [context["cluster_key"]]
    compare_keys.append(context["compare_key"])
    plot_embedding_comparison(
        adata,
        context["output_dir"],
        obsm_key=context["embedding_key"],
        color_keys=compare_keys,
        filename=spec.filename,
        title=f"{context['embedding_method'].upper()} comparison view",
    )
    path = _gallery_figure_path(context["output_dir"], spec.filename)
    return path if path.exists() else None


def _render_cluster_size_summary(adata, spec: PlotSpec, context: dict) -> object:
    plot_cluster_size_summary(context["cluster_summary_df"], context["output_dir"], filename=spec.filename)
    path = _gallery_figure_path(context["output_dir"], spec.filename)
    return path if path.exists() else None


def _render_cluster_qc_heatmap(adata, spec: PlotSpec, context: dict) -> object:
    if context["cluster_qc_df"].empty:
        return None
    plot_cluster_qc_heatmap(context["cluster_qc_df"].set_index(context["cluster_key"]), context["output_dir"], filename=spec.filename)
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
    "embedding_clusters": _render_embedding_clusters,
    "embedding_comparison": _render_embedding_comparison,
    "cluster_size_summary": _render_cluster_size_summary,
    "cluster_qc_heatmap": _render_cluster_qc_heatmap,
    "pca_variance": _render_pca_variance,
    "pca_scatter": _render_pca_scatter,
}


def _write_figure_data(output_dir: Path, context: dict, recipe: VisualizationRecipe, artifacts) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    context["cluster_summary_df"].to_csv(figure_data_dir / "cluster_summary.csv", index=False)
    context["embedding_points_df"].to_csv(figure_data_dir / "embedding_points.csv", index=False)
    context["clustering_summary_df"].to_csv(figure_data_dir / "clustering_summary.csv", index=False)
    if not context["cluster_qc_df"].empty:
        context["cluster_qc_df"].to_csv(figure_data_dir / "cluster_qc_summary.csv", index=False)
    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": recipe.recipe_id,
        "available_files": {
            "cluster_summary": "cluster_summary.csv",
            "embedding_points": "embedding_points.csv",
            "clustering_summary": "clustering_summary.csv",
            **({"cluster_qc_summary": "cluster_qc_summary.csv"} if not context["cluster_qc_df"].empty else {}),
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
        f"- **Neighbor graph source**: `{params['use_rep']}`",
        f"- **Embedding method**: `{params['embedding_method']}`",
        f"- **Rendered embedding**: `{params['embedding_key']}`",
        f"- **Cluster method**: {summary['cluster_method']}",
        f"- **Cluster key**: `{summary['cluster_key']}`",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Clusters**: {summary['n_clusters']}",
        "",
        "## Effective Parameters\n",
        f"- `embedding_method`: {params['embedding_method']}",
        f"- `use_rep`: {params['use_rep']}",
        f"- `n_neighbors`: {params['n_neighbors']}",
        f"- `n_pcs`: {params['n_pcs']}",
        f"- `resolution`: {params['resolution']}",
        "",
        "## Beginner Notes\n",
        "- This skill assumes base preprocessing has already produced a normalized, PCA-ready object.",
        "- If likely batch/sample effects are present, consider `sc-batch-integration` before trusting the clusters.",
        "- If you did not override the defaults, this run used the first-pass settings listed above.",
        "",
        "## Recommended Next Steps\n",
        "- Inspect `tables/cluster_summary.csv` and the embedding gallery to judge whether clusters are too coarse or too fragmented.",
        "- If marker discovery is next: run `sc-markers`.",
        "- If cell type interpretation is next: run `sc-cell-annotation`.",
        "- If you need group-level testing after labels are stable: run `sc-de`.",
        "",
        "## Output Files\n",
        "- `processed.h5ad` — clustered AnnData with neighbor graph, embedding coordinates, and cluster labels.",
        "- `figures/` — standard clustering gallery.",
        "- `tables/cluster_summary.csv` — per-cluster cell counts.",
        "- `figure_data/embedding_points.csv` — rendered embedding coordinates for downstream styling.",
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
    for key in (
        "cluster_method",
        "embedding_method",
        "use_rep",
        "n_neighbors",
        "n_pcs",
        "resolution",
        "umap_min_dist",
        "umap_spread",
        "tsne_perplexity",
        "tsne_metric",
        "diffmap_n_comps",
    ):
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


def _save_resolution_search_plot(resolution_df: pd.DataFrame, output_dir: Path) -> None:
    """Save a line plot of silhouette score vs resolution."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(
        resolution_df["resolution"],
        resolution_df["silhouette_score"],
        marker="o",
        color="#2ca02c",
        linewidth=2,
        markersize=8,
    )
    best_idx = resolution_df["silhouette_score"].idxmax()
    best_row = resolution_df.iloc[best_idx]
    ax.axvline(best_row["resolution"], color="#d62728", linestyle="--", alpha=0.7, label=f"Best: {best_row['resolution']:.2f}")
    ax.scatter([best_row["resolution"]], [best_row["silhouette_score"]], color="#d62728", s=120, zorder=5)
    ax.set_xlabel("Resolution", fontsize=12)
    ax.set_ylabel("Silhouette Score", fontsize=12)
    ax.set_title("Auto Resolution Search", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(figures_dir / "auto_resolution_search.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def get_demo_data():
    adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
    return adata


def _render_r_enhanced(output_dir, figure_data_dir, r_enhanced):
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Clustering")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--embedding-method", choices=["umap", "tsne", "diffmap", "phate"], default="umap")
    parser.add_argument("--cluster-method", choices=["leiden", "louvain"], default="leiden")
    parser.add_argument("--use-rep", default=None, help="Embedding in adata.obsm to use, e.g. X_pca or X_harmony")
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--n-pcs", type=int, default=50)
    parser.add_argument("--resolution", type=str, default="1.0",
                        help="Clustering resolution. Use 'auto' for automatic selection via bootstrap silhouette.")
    parser.add_argument("--umap-min-dist", type=float, default=0.5)
    parser.add_argument("--umap-spread", type=float, default=1.0)
    parser.add_argument("--tsne-perplexity", type=float, default=30.0)
    parser.add_argument("--tsne-metric", default="euclidean")
    parser.add_argument("--diffmap-n-comps", type=int, default=15)
    parser.add_argument("--phate-knn", type=int, default=15)
    parser.add_argument("--phate-decay", type=int, default=40)
    parser.add_argument("--r-enhanced", action="store_true", default=False, help="Generate R-enhanced figures via ggplot2 renderers")
    args = parser.parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("n_neighbors", args.n_neighbors, min_val=2)
    v.positive("n_pcs", args.n_pcs, min_val=1)
    if args.resolution != "auto":
        res_val = float(args.resolution)
        v.in_range("resolution", res_val, low=0, high=50, low_exclusive=True)
    v.positive("tsne_perplexity", args.tsne_perplexity, min_val=1)
    v.positive("diffmap_n_comps", args.diffmap_n_comps, min_val=2)
    v.positive("phate_knn", args.phate_knn, min_val=2)
    v.check()

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

    # Parse resolution: either numeric or 'auto'
    use_auto_resolution = args.resolution.lower() == "auto"
    effective_resolution = 1.0 if use_auto_resolution else float(args.resolution)
    auto_resolution_info: dict | None = None

    apply_preflight(
        preflight_sc_clustering(
            adata,
            cluster_method=args.cluster_method,
            embedding_method=args.embedding_method,
            use_rep=args.use_rep,
            tsne_perplexity=args.tsne_perplexity,
            diffmap_n_comps=args.diffmap_n_comps,
            phate_knn=args.phate_knn,
            phate_decay=args.phate_decay,
            n_neighbors=args.n_neighbors,
            n_pcs=args.n_pcs,
            resolution=effective_resolution,
            umap_min_dist=args.umap_min_dist,
            umap_spread=args.umap_spread,
            tsne_metric=args.tsne_metric,
            source_path=input_file,
        ),
        logger,
    )

    use_rep = _resolve_use_rep(adata, args.use_rep)

    if use_auto_resolution:
        # Build neighbor graph first, then search for optimal resolution
        sc_dimred_utils.build_neighbor_graph(
            adata, n_neighbors=args.n_neighbors, n_pcs=args.n_pcs, use_rep=use_rep, inplace=True,
        )
        effective_resolution, auto_resolution_info = auto_resolution(
            adata,
            use_rep=use_rep,
            cluster_method=args.cluster_method,
        )
        print(f"  Auto-resolution selected: {effective_resolution:.2f} "
              f"(silhouette={auto_resolution_info['highest_silhouette']:.4f})")
        # Save the resolution search plot
        _save_resolution_search_plot(auto_resolution_info["resolution_df"], output_dir)

    adata, _ = run_clustering(
        adata,
        use_rep=use_rep,
        embedding_method=args.embedding_method,
        n_neighbors=args.n_neighbors,
        n_pcs=args.n_pcs,
        cluster_method=args.cluster_method,
        resolution=effective_resolution,
        umap_min_dist=args.umap_min_dist,
        umap_spread=args.umap_spread,
        tsne_perplexity=args.tsne_perplexity,
        tsne_metric=args.tsne_metric,
        diffmap_n_comps=args.diffmap_n_comps,
        phate_knn=args.phate_knn,
        phate_decay=args.phate_decay,
    )
    summary = build_summary(adata, cluster_key=args.cluster_method, cluster_method=args.cluster_method)
    if auto_resolution_info:
        summary["auto_resolution"] = {
            "selected_resolution": auto_resolution_info["best_resolution"],
            "highest_silhouette": auto_resolution_info["highest_silhouette"],
            "silhouette_scores": auto_resolution_info["silhouette_scores"],
            "n_subsample_reps": auto_resolution_info["n_subsample_reps"],
            "subsample_fraction": auto_resolution_info["subsample_fraction"],
        }
    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind="normalized_expression",
        raw_kind=get_matrix_contract(adata).get("raw"),
        primary_cluster_key=summary["cluster_key"],
    )

    gallery_context = _prepare_gallery_context(adata, summary, {
        "embedding_method": args.embedding_method,
        "embedding_key": _embedding_key_from_method(args.embedding_method),
        "use_rep": use_rep,
        "n_neighbors": args.n_neighbors,
        "n_pcs": args.n_pcs,
        "resolution": effective_resolution,
        "umap_min_dist": args.umap_min_dist,
        "umap_spread": args.umap_spread,
        "tsne_perplexity": args.tsne_perplexity,
        "tsne_metric": args.tsne_metric,
        "diffmap_n_comps": args.diffmap_n_comps,
        "phate_knn": args.phate_knn,
        "phate_decay": args.phate_decay,
    }, output_dir)
    recipe = _build_visualization_recipe(summary)
    artifacts = render_plot_specs(adata, output_dir, recipe, CLUSTER_GALLERY_RENDERERS, context=gallery_context)
    _write_figure_data(output_dir, gallery_context, recipe, artifacts)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    gallery_context["cluster_summary_df"].to_csv(tables_dir / "cluster_summary.csv", index=False)
    gallery_context["clustering_summary_df"].to_csv(tables_dir / "clustering_summary.csv", index=False)
    gallery_context["embedding_points_df"].to_csv(tables_dir / "embedding_points.csv", index=False)
    if not gallery_context["cluster_qc_df"].empty:
        gallery_context["cluster_qc_df"].to_csv(tables_dir / "cluster_qc_summary.csv", index=False)

    params = {
        "embedding_method": args.embedding_method,
        "embedding_key": _embedding_key_from_method(args.embedding_method),
        "cluster_method": args.cluster_method,
        "use_rep": use_rep,
        "n_neighbors": args.n_neighbors,
        "n_pcs": args.n_pcs,
        "resolution": effective_resolution,
        "resolution_mode": "auto" if use_auto_resolution else "manual",
        "umap_min_dist": args.umap_min_dist,
        "umap_spread": args.umap_spread,
        "tsne_perplexity": args.tsne_perplexity,
        "tsne_metric": args.tsne_metric,
        "diffmap_n_comps": args.diffmap_n_comps,
        "phate_knn": args.phate_knn,
        "phate_decay": args.phate_decay,
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
            "embedding_method": args.embedding_method,
            "embedding_key": _embedding_key_from_method(args.embedding_method),
            "available_figure_data": gallery_context.get("figure_data_files", {}),
        },
        **summary,
    }
    result_data["next_steps"] = [
        {"skill": "sc-cell-annotation", "reason": "Annotate cell types for each cluster", "priority": "recommended"},
        {"skill": "sc-markers", "reason": "Find marker genes for each cluster", "priority": "recommended"},
        {"skill": "sc-pseudotime", "reason": "Optional: infer developmental trajectories", "priority": "optional"},
    ]
    result_data["preprocessing_state_after"] = "clustered"
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)
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

    # --- Next-step guidance ---
    print()
    print(">> Next steps:")
    print(f"  • sc-cell-annotation: python omicsclaw.py run sc-cell-annotation --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  • sc-markers:         python omicsclaw.py run sc-markers --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  • sc-pseudotime:      python omicsclaw.py run sc-pseudotime --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
