"""Pseudotime and lineage inference on preprocessed spatial expression."""

from __future__ import annotations

import numpy as np
import pandas as pd

from skills.spatial._lib.trajectory import detect_cluster_key, run_trajectory
from skills.spatial._lib.inference_result import read_info, store_info

__all__ = ["trajectory", "run_info", "pseudotime_table", "trajectory_genes", "pseudotime_figure"]
_RUN_KEY = "omicsclaw_spatial_trajectory_run"


def trajectory(adata, *, method: str = "dpt", cluster_key: str | None = None,
               root_cell: str | None = None, root_cell_type: str | None = None,
               method_params: dict | None = None, random_state: int = 0,
               palantir_waypoint_seed: int = 20):
    """Infer pseudotime in place from log-normalized X and an existing PCA/graph.

    DPT and CellRank add dpt_pseudotime; Palantir adds palantir_pseudotime.
    CellRank fate calculations can be incomplete; inspect run_info warnings.

    :param adata: AnnData with X_pca and a neighbors graph from preprocessing.
    :param method: dpt (CLI default), cellrank or palantir.
    :param cluster_key: Observation annotation; None detects leiden/cell_type/cluster.
    :param root_cell: Starting barcode; None picks the maximum first diffusion component.
    :param root_cell_type: Restrict automatic root selection to this annotation value.
    :param method_params: Backend options using the CLI names with underscores;
        None retains its defaults, such as dpt_n_dcs=10. See references/parameters.md.
    :param random_state: Seed for diffusion maps and supported backend sampling, default 0.
    :param palantir_waypoint_seed: Palantir waypoint sampling seed, 20 to preserve
        the original CLI backend default independently from diffusion-map seed 0.
    :returns: The same AnnData with pseudotime and JSON run diagnostics.
    :raises ValueError: Missing preprocessing, root or annotation, or invalid method.
    :raises ImportError: A backend is missing; use install_skill_deps.
    """
    if "X_pca" not in adata.obsm:
        raise ValueError("PCA embedding missing; run spatial-preprocess first")
    if "neighbors" not in adata.uns:
        raise ValueError("Neighbor graph missing; run spatial-preprocess first")
    if cluster_key is not None and cluster_key not in adata.obs:
        raise ValueError(f"Cluster key {cluster_key!r} not found in adata.obs")
    cluster_key = cluster_key or detect_cluster_key(adata)
    try:
        summary = run_trajectory(adata, method=method, cluster_key=cluster_key,
                                 root_cell=root_cell, root_cell_type=root_cell_type,
                                 random_state=random_state,
                                 palantir_waypoint_seed=palantir_waypoint_seed,
                                 **(method_params or {}))
    except ImportError as exc:
        raise ImportError(f"{method} backend unavailable: {exc}; use install_skill_deps") from exc
    summary["random_state"] = random_state
    if method == "palantir":
        summary["palantir_waypoint_seed"] = palantir_waypoint_seed
    store_info(adata, _RUN_KEY, summary)
    return adata


def run_info(adata, *, keep: bool = True) -> dict:
    """Read the last run's root, effective parameters and method-specific results.

    :param adata: AnnData returned by trajectory.
    :param keep: True keeps diagnostics; False removes them for CLI serialization.
    :returns: A dictionary, including trajectory gene tables when available.
    """
    return read_info(adata, _RUN_KEY, keep=keep)


def pseudotime_table(adata) -> pd.DataFrame:
    """Return per-spot pseudotime columns in observation order.

    :param adata: AnnData after trajectory inference.
    :returns: A barcode-indexed table of available DPT/Palantir pseudotime and entropy.
    """
    columns = [name for name in ("dpt_pseudotime", "palantir_pseudotime", "palantir_entropy") if name in adata.obs]
    return adata.obs[columns].copy()


def trajectory_genes(adata) -> pd.DataFrame:
    """Return genes correlated with pseudotime from the last inference.

    :param adata: AnnData returned by trajectory; expression was read from X.
    :returns: Gene, correlation, pvalue, fdr and direction columns, or an empty table.
    """
    return run_info(adata).get("trajectory_genes", pd.DataFrame()).copy()


def pseudotime_figure(adata, *, basis: str = "spatial"):
    """Plot inferred pseudotime over coordinates without writing a file.

    :param adata: AnnData returned by trajectory.
    :param basis: Coordinate key, spatial by default; X_umap is also supported.
    :returns: A matplotlib Figure owned by the caller.
    :raises KeyError: Missing coordinates or pseudotime.
    """
    import matplotlib.pyplot as plt

    key = run_info(adata).get("pseudotime_key", "dpt_pseudotime")
    coords = np.asarray(adata.obsm[basis])
    fig, ax = plt.subplots(figsize=(6, 5))
    points = ax.scatter(coords[:, 0], coords[:, 1], c=adata.obs[key], s=16)
    fig.colorbar(points, ax=ax, label=key)
    ax.set(xlabel=basis + " 1", ylabel=basis + " 2")
    fig.tight_layout()
    return fig
