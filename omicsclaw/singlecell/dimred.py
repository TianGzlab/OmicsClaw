"""Dimensionality reduction, neighbor graph construction, clustering, and visualization.

Combines functionality from four validated reference scripts:
  - scale_and_pca.py  (scaling, PCA, variance plots, loadings)
  - run_umap.py       (UMAP, t-SNE, diffusion map)
  - cluster_cells.py  (kNN graph, Leiden / Louvain, cluster QC stats)
  - plot_dimreduction.py (UMAP cluster plots, feature plots, styled plots)

All ``print()`` calls have been replaced with ``logger.info()``.
All figure saving goes through :func:`~omicsclaw.singlecell.viz_utils.save_figure`.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from anndata import AnnData

logger = logging.getLogger(__name__)


# ===========================================================================
# Scale & PCA  (from scale_and_pca.py)
# ===========================================================================


def scale_data(
    adata: AnnData,
    max_value: float = 10,
    vars_to_regress: Optional[List[str]] = None,
    use_hvg_only: bool = True,
    inplace: bool = True,
) -> AnnData:
    """Z-score scale the expression matrix, optionally regressing out confounders.

    Parameters
    ----------
    adata
        AnnData object (log-normalized counts expected).
    max_value
        Clip scaled values to ``[-max_value, max_value]``.
    vars_to_regress
        Observation columns to regress out (e.g. ``["total_counts", "pct_counts_mt"]``).
    use_hvg_only
        If ``True`` *and* ``adata.var["highly_variable"]`` exists, scale only on
        highly-variable genes (recommended to avoid noise amplification).
    inplace
        Modify *adata* in place.

    Returns
    -------
    AnnData with scaled ``X`` (or the HVG-subset view when *use_hvg_only*).
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    # Optionally regress out confounders before scaling
    if vars_to_regress:
        missing = [v for v in vars_to_regress if v not in adata.obs.columns]
        if missing:
            logger.warning("Variables not found in adata.obs, skipping regress_out: %s", missing)
            vars_to_regress = [v for v in vars_to_regress if v in adata.obs.columns]
        if vars_to_regress:
            logger.info("Regressing out: %s", vars_to_regress)
            sc.pp.regress_out(adata, vars_to_regress)

    # Determine HVG mask
    hvg_available = "highly_variable" in adata.var.columns
    if use_hvg_only and hvg_available:
        n_hvg = adata.var["highly_variable"].sum()
        logger.info("Scaling on %d highly-variable genes (max_value=%.1f)", n_hvg, max_value)
    else:
        if use_hvg_only and not hvg_available:
            logger.warning("highly_variable column not found; scaling all %d genes", adata.n_vars)
        else:
            logger.info("Scaling all %d genes (max_value=%.1f)", adata.n_vars, max_value)

    sc.pp.scale(adata, max_value=max_value)
    logger.info("Scaling complete. X range: [%.2f, %.2f]", adata.X.min(), adata.X.max())

    return adata


def run_pca_analysis(
    adata: AnnData,
    n_pcs: int = 50,
    use_hvg_only: bool = True,
    svd_solver: str = "arpack",
    random_state: int = 0,
    inplace: bool = True,
) -> AnnData:
    """Run PCA and verify that loadings are stored.

    Parameters
    ----------
    adata
        Scaled AnnData.
    n_pcs
        Number of principal components to compute.
    use_hvg_only
        Use only highly-variable genes for PCA.
    svd_solver
        SVD solver passed to ``sc.tl.pca``.
    random_state
        Random seed.
    inplace
        Modify in place.

    Returns
    -------
    AnnData with ``X_pca`` in ``.obsm`` and ``PCs`` in ``.varm``.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    n_pcs = min(n_pcs, adata.n_vars - 1, adata.n_obs - 1)
    use_hvg = use_hvg_only and "highly_variable" in adata.var.columns
    logger.info(
        "Running PCA: n_pcs=%d, use_highly_variable=%s, solver=%s",
        n_pcs, use_hvg, svd_solver,
    )

    sc.tl.pca(
        adata,
        n_comps=n_pcs,
        use_highly_variable=use_hvg,
        svd_solver=svd_solver,
        random_state=random_state,
    )

    # Verify loadings
    if "PCs" in adata.varm:
        logger.info(
            "PCA complete. Loadings shape: %s, explained variance (PC1): %.2f%%",
            adata.varm["PCs"].shape,
            adata.uns["pca"]["variance_ratio"][0] * 100,
        )
    else:
        logger.warning("PCA loadings (varm['PCs']) not found after PCA. Some plots may fail.")

    total_var = np.sum(adata.uns["pca"]["variance_ratio"]) * 100
    logger.info("Total explained variance (%d PCs): %.1f%%", n_pcs, total_var)

    return adata


def suggest_n_pcs(
    adata: AnnData,
    min_pcs: int = 15,
    default_pcs: int = 30,
    target_variance: float = 0.85,
) -> int:
    """Auto-suggest the number of PCs from cumulative variance.

    Returns the smaller of *default_pcs* and the number of PCs needed to
    reach *target_variance*, but never fewer than *min_pcs*.

    Parameters
    ----------
    adata
        AnnData with PCA computed.
    min_pcs
        Floor value.
    default_pcs
        Ceiling value.
    target_variance
        Fraction of total variance to reach.
    """
    if "pca" not in adata.uns or "variance_ratio" not in adata.uns["pca"]:
        logger.warning("PCA variance info not found. Returning default_pcs=%d", default_pcs)
        return default_pcs

    cumvar = np.cumsum(adata.uns["pca"]["variance_ratio"])
    hits = np.where(cumvar >= target_variance)[0]
    if len(hits) > 0:
        n_pcs = int(hits[0]) + 1  # 0-indexed → count
    else:
        n_pcs = len(cumvar)
        logger.info(
            "Target variance %.0f%% not reached with %d PCs (got %.1f%%)",
            target_variance * 100, n_pcs, cumvar[-1] * 100,
        )

    suggested = max(min_pcs, min(n_pcs, default_pcs))
    logger.info(
        "Suggested n_pcs=%d (target_var=%.0f%%, cumvar at suggestion=%.1f%%)",
        suggested, target_variance * 100, cumvar[min(suggested - 1, len(cumvar) - 1)] * 100,
    )
    return suggested


def plot_pca_variance(
    adata: AnnData,
    output_dir: Union[str, Path],
    n_pcs: int = 50,
    figsize: Tuple[int, int] = (12, 4),
) -> None:
    """Plot PCA elbow (scree) and cumulative variance side-by-side.

    Saves ``figures/pca_variance.png``.

    Parameters
    ----------
    adata
        AnnData with PCA computed.
    output_dir
        Directory for output (``figures/`` sub-folder).
    n_pcs
        Number of PCs to display.
    figsize
        Figure size.
    """
    from .viz_utils import save_figure

    import matplotlib.pyplot as plt

    if "pca" not in adata.uns:
        logger.warning("PCA not computed yet. Skipping variance plot.")
        return

    var_ratio = adata.uns["pca"]["variance_ratio"]
    n_pcs = min(n_pcs, len(var_ratio))
    pcs = np.arange(1, n_pcs + 1)
    cumvar = np.cumsum(var_ratio[:n_pcs])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

    # Elbow / scree
    ax1.plot(pcs, var_ratio[:n_pcs], "o-", markersize=3, color="#4c72b0")
    ax1.set_xlabel("Principal Component")
    ax1.set_ylabel("Variance Ratio")
    ax1.set_title("PCA Elbow Plot")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.grid(alpha=0.3)

    # Cumulative
    ax2.plot(pcs, cumvar * 100, "o-", markersize=3, color="#dd8452")
    ax2.axhline(85, color="red", linestyle="--", linewidth=1, alpha=0.7, label="85%")
    ax2.set_xlabel("Number of PCs")
    ax2.set_ylabel("Cumulative Variance (%)")
    ax2.set_title("Cumulative Variance Explained")
    ax2.legend()
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    save_figure(fig, output_dir, "pca_variance.png")
    logger.info("Saved PCA variance plots")


def plot_pca_scatter(
    adata: AnnData,
    output_dir: Union[str, Path],
    color: Optional[Union[str, List[str]]] = None,
    components: Optional[List[str]] = None,
    figsize: Tuple[int, int] = (12, 5),
) -> None:
    """Plot PCA scatter for given component pairs.

    Saves ``figures/pca_scatter.png``.

    Parameters
    ----------
    adata
        AnnData with PCA computed.
    output_dir
        Output directory.
    color
        Column(s) in ``adata.obs`` or gene names for colouring.
    components
        Component pair strings, e.g. ``["1,2", "3,4"]``.
    figsize
        Figure size.
    """
    import scanpy as sc
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    if "X_pca" not in adata.obsm:
        logger.warning("PCA not computed. Skipping scatter plot.")
        return

    if components is None:
        components = ["1,2", "3,4"]

    logger.info("Plotting PCA scatter (components=%s, color=%s)", components, color)
    sc.pl.pca(adata, color=color, components=components, show=False, size=15)
    fig = plt.gcf()
    fig.set_size_inches(*figsize)
    save_figure(fig, output_dir, "pca_scatter.png")


def plot_pca_loadings(
    adata: AnnData,
    output_dir: Union[str, Path],
    components: Optional[List[int]] = None,
    n_genes: int = 20,
    figsize: Tuple[int, int] = (8, 6),
) -> None:
    """Plot top loading genes per principal component.

    Saves ``figures/pca_loadings.png``.

    Parameters
    ----------
    adata
        AnnData with PCA computed (needs ``varm['PCs']``).
    output_dir
        Output directory.
    components
        1-indexed PC numbers (default ``[1, 2, 3]``).
    n_genes
        Number of top genes per PC to display.
    figsize
        Figure size.
    """
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    if "PCs" not in adata.varm:
        logger.warning("PCA loadings not found (varm['PCs']). Skipping loadings plot.")
        return

    if components is None:
        components = [1, 2, 3]

    loadings = adata.varm["PCs"]  # (n_vars, n_pcs)
    gene_names = adata.var_names

    # If PCA was run on HVGs only, loadings rows match HVGs
    if loadings.shape[0] != len(gene_names):
        if "highly_variable" in adata.var.columns:
            gene_names = adata.var_names[adata.var["highly_variable"]]
        else:
            logger.warning(
                "Loadings shape %s != n_vars %d. Cannot map gene names.",
                loadings.shape, len(adata.var_names),
            )
            return

    n_panels = len(components)
    fig, axes = plt.subplots(1, n_panels, figsize=(figsize[0] * n_panels / 3, figsize[1]))
    if n_panels == 1:
        axes = [axes]

    for ax, pc in zip(axes, components):
        pc_idx = pc - 1
        if pc_idx >= loadings.shape[1]:
            logger.warning("PC%d exceeds available PCs (%d). Skipping.", pc, loadings.shape[1])
            continue

        pc_loads = loadings[:, pc_idx]
        top_idx = np.argsort(np.abs(pc_loads))[::-1][:n_genes]

        names = [gene_names[i] for i in top_idx]
        values = pc_loads[top_idx]
        colors = ["#e74c3c" if v > 0 else "#3498db" for v in values]

        y_pos = np.arange(len(names))
        ax.barh(y_pos, values, color=colors, edgecolor="none")
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names, fontsize=7)
        ax.invert_yaxis()
        ax.set_xlabel("Loading")
        ax.set_title(f"PC{pc}")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    save_figure(fig, output_dir, "pca_loadings.png")
    logger.info("Saved PCA loadings plot")


# ===========================================================================
# UMAP / t-SNE / Diffusion Map  (from run_umap.py)
# ===========================================================================


def run_umap_reduction(
    adata: AnnData,
    n_neighbors: Optional[int] = None,
    min_dist: float = 0.5,
    spread: float = 1.0,
    random_state: int = 0,
    inplace: bool = True,
) -> AnnData:
    """Compute UMAP embedding from the existing neighbor graph.

    A neighbor graph (``adata.uns['neighbors']``) must already exist.
    If *n_neighbors* is provided and differs from the stored graph, the
    graph is rebuilt first.

    Parameters
    ----------
    adata
        AnnData with precomputed neighbor graph.
    n_neighbors
        If given and the stored graph used a different value, rebuild neighbors.
    min_dist
        UMAP ``min_dist`` parameter.
    spread
        UMAP ``spread`` parameter.
    random_state
        Random seed.
    inplace
        Modify in place.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if "neighbors" not in adata.uns:
        raise ValueError(
            "Neighbor graph not found. Run build_neighbor_graph() first."
        )

    # Optionally rebuild if n_neighbors changed
    if n_neighbors is not None:
        stored_k = adata.uns.get("neighbors", {}).get("params", {}).get("n_neighbors")
        if stored_k is not None and stored_k != n_neighbors:
            logger.info(
                "Rebuilding neighbor graph (stored n_neighbors=%s, requested=%d)",
                stored_k, n_neighbors,
            )
            n_pcs = adata.uns["neighbors"]["params"].get("n_pcs", 30)
            sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs, random_state=random_state)

    logger.info("Computing UMAP (min_dist=%.2f, spread=%.1f)", min_dist, spread)
    sc.tl.umap(adata, min_dist=min_dist, spread=spread, random_state=random_state)
    logger.info("UMAP complete. Shape: %s", adata.obsm["X_umap"].shape)

    return adata


def run_tsne_reduction(
    adata: AnnData,
    n_pcs: Optional[int] = None,
    perplexity: float = 30,
    random_state: int = 0,
    inplace: bool = True,
) -> AnnData:
    """Compute t-SNE embedding.

    Parameters
    ----------
    adata
        AnnData with PCA computed.
    n_pcs
        Number of PCs to use.  ``None`` uses scanpy default.
    perplexity
        t-SNE perplexity.
    random_state
        Random seed.
    inplace
        Modify in place.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if "X_pca" not in adata.obsm:
        logger.warning("PCA not found. Computing PCA with 50 components first.")
        sc.tl.pca(adata, n_comps=min(50, adata.n_vars - 1))

    logger.info("Computing t-SNE (perplexity=%.1f, n_pcs=%s)", perplexity, n_pcs)
    sc.tl.tsne(adata, n_pcs=n_pcs, perplexity=perplexity, random_state=random_state)
    logger.info("t-SNE complete. Shape: %s", adata.obsm["X_tsne"].shape)

    return adata


def run_diffmap(
    adata: AnnData,
    n_comps: int = 15,
    inplace: bool = True,
) -> AnnData:
    """Compute diffusion map embedding.

    Requires a neighbor graph in ``adata.uns['neighbors']``.

    Parameters
    ----------
    adata
        AnnData with neighbor graph.
    n_comps
        Number of diffusion components.
    inplace
        Modify in place.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if "neighbors" not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph() first.")

    logger.info("Computing diffusion map (n_comps=%d)", n_comps)
    sc.tl.diffmap(adata, n_comps=n_comps)
    logger.info("Diffusion map complete. Shape: %s", adata.obsm["X_diffmap"].shape)

    return adata


# ===========================================================================
# Neighbor graph & Clustering  (from cluster_cells.py)
# ===========================================================================


def build_neighbor_graph(
    adata: AnnData,
    n_neighbors: int = 10,
    n_pcs: int = 30,
    metric: str = "euclidean",
    random_state: int = 0,
    use_rep: Optional[str] = None,
    inplace: bool = True,
) -> AnnData:
    """Build a k-nearest-neighbor graph.

    Warns when *n_pcs* is low relative to dataset complexity.

    Parameters
    ----------
    adata
        AnnData with PCA (or alternative representation in *use_rep*).
    n_neighbors
        Number of neighbors for the kNN graph.
    n_pcs
        Number of PCs to use (ignored when *use_rep* is set).
    metric
        Distance metric (``euclidean``, ``cosine``, etc.).
    random_state
        Random seed.
    use_rep
        Key in ``adata.obsm`` to use instead of PCA (e.g. ``"X_scVI"``).
    inplace
        Modify in place.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if use_rep is None:
        if "X_pca" not in adata.obsm:
            logger.warning("PCA not found. Computing PCA with 50 components first.")
            sc.tl.pca(adata, n_comps=min(50, adata.n_vars - 1))

        avail_pcs = adata.obsm["X_pca"].shape[1]
        n_pcs = min(n_pcs, avail_pcs)

        if n_pcs < 15:
            logger.warning(
                "Using only %d PCs for neighbors. This may lose biological signal. "
                "Consider n_pcs >= 15.",
                n_pcs,
            )

    logger.info(
        "Building neighbor graph: n_neighbors=%d, n_pcs=%s, metric=%s, use_rep=%s",
        n_neighbors, n_pcs if use_rep is None else "N/A", metric, use_rep,
    )

    kwargs: dict = dict(
        n_neighbors=n_neighbors,
        metric=metric,
        random_state=random_state,
    )
    if use_rep is not None:
        kwargs["use_rep"] = use_rep
    else:
        kwargs["n_pcs"] = n_pcs

    sc.pp.neighbors(adata, **kwargs)
    logger.info("Neighbor graph built successfully")

    return adata


def cluster_leiden(
    adata: AnnData,
    resolution: float = 0.8,
    random_state: int = 0,
    key_added: Optional[str] = None,
    inplace: bool = True,
) -> AnnData:
    """Leiden clustering at a single resolution.

    Parameters
    ----------
    adata
        AnnData with neighbor graph.
    resolution
        Leiden resolution parameter (higher = more clusters).
    random_state
        Random seed.
    key_added
        Key for ``adata.obs``.  Default: ``"leiden_{resolution}"``.
    inplace
        Modify in place.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if "neighbors" not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph() first.")

    if key_added is None:
        key_added = f"leiden_{resolution}"

    logger.info("Running Leiden clustering (resolution=%.2f, key=%s)", resolution, key_added)
    sc.tl.leiden(adata, resolution=resolution, random_state=random_state, key_added=key_added)

    n_clusters = adata.obs[key_added].nunique()
    logger.info("Leiden complete: %d clusters at resolution %.2f", n_clusters, resolution)

    return adata


def cluster_leiden_multiple_resolutions(
    adata: AnnData,
    resolutions: Optional[List[float]] = None,
    random_state: int = 0,
    inplace: bool = True,
) -> AnnData:
    """Run Leiden clustering at multiple resolutions and log a summary.

    Stores results as ``adata.obs["leiden_{res}"]`` for each resolution.

    Parameters
    ----------
    adata
        AnnData with neighbor graph.
    resolutions
        List of resolution values to sweep.
    random_state
        Random seed.
    inplace
        Modify in place.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if resolutions is None:
        resolutions = [0.4, 0.6, 0.8, 1.0]

    if "neighbors" not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph() first.")

    logger.info("Running Leiden at %d resolutions: %s", len(resolutions), resolutions)

    summary_rows: list[dict] = []
    for res in resolutions:
        key = f"leiden_{res}"
        sc.tl.leiden(adata, resolution=res, random_state=random_state, key_added=key)
        n_clusters = adata.obs[key].nunique()
        summary_rows.append({"resolution": res, "n_clusters": n_clusters, "key": key})
        logger.info("  resolution=%.2f -> %d clusters", res, n_clusters)

    adata.uns["leiden_resolution_sweep"] = summary_rows

    # Log summary table
    logger.info("Resolution sweep summary:")
    for row in summary_rows:
        logger.info("  res=%.2f  clusters=%d  key=%s", row["resolution"], row["n_clusters"], row["key"])

    return adata


def cluster_louvain(
    adata: AnnData,
    resolution: float = 0.8,
    random_state: int = 0,
    key_added: Optional[str] = None,
    inplace: bool = True,
) -> AnnData:
    """Louvain clustering (legacy alternative to Leiden).

    Parameters
    ----------
    adata
        AnnData with neighbor graph.
    resolution
        Louvain resolution.
    random_state
        Random seed.
    key_added
        Key for ``adata.obs``.  Default: ``"louvain_{resolution}"``.
    inplace
        Modify in place.
    """
    import scanpy as sc

    if not inplace:
        adata = adata.copy()

    if "neighbors" not in adata.uns:
        raise ValueError("Neighbor graph not found. Run build_neighbor_graph() first.")

    if key_added is None:
        key_added = f"louvain_{resolution}"

    logger.info("Running Louvain clustering (resolution=%.2f, key=%s)", resolution, key_added)
    sc.tl.louvain(adata, resolution=resolution, random_state=random_state, key_added=key_added)

    n_clusters = adata.obs[key_added].nunique()
    logger.info("Louvain complete: %d clusters at resolution %.2f", n_clusters, resolution)

    return adata


def calculate_cluster_qc_stats(
    adata: AnnData,
    cluster_key: str = "leiden_0.8",
) -> pd.DataFrame:
    """Calculate per-cluster QC summary statistics.

    Parameters
    ----------
    adata
        AnnData with clustering and QC metrics.
    cluster_key
        Column in ``adata.obs`` containing cluster labels.

    Returns
    -------
    DataFrame indexed by cluster with columns:
    ``n_cells``, ``pct_cells``, ``mean_genes``, ``mean_counts``, ``mean_mt``.
    """
    if cluster_key not in adata.obs.columns:
        raise ValueError(f"Cluster key '{cluster_key}' not found in adata.obs")

    logger.info("Calculating cluster QC stats for '%s'", cluster_key)

    groups = adata.obs.groupby(cluster_key)

    stats: dict[str, list] = {
        "n_cells": [],
        "pct_cells": [],
        "mean_genes": [],
        "mean_counts": [],
        "mean_mt": [],
    }
    cluster_ids: list = []

    for name, grp in groups:
        cluster_ids.append(name)
        n = len(grp)
        stats["n_cells"].append(n)
        stats["pct_cells"].append(100 * n / adata.n_obs)

        if "n_genes_by_counts" in grp.columns:
            stats["mean_genes"].append(grp["n_genes_by_counts"].mean())
        else:
            stats["mean_genes"].append(np.nan)

        if "total_counts" in grp.columns:
            stats["mean_counts"].append(grp["total_counts"].mean())
        else:
            stats["mean_counts"].append(np.nan)

        if "pct_counts_mt" in grp.columns:
            stats["mean_mt"].append(grp["pct_counts_mt"].mean())
        else:
            stats["mean_mt"].append(np.nan)

    df = pd.DataFrame(stats, index=cluster_ids)
    df.index.name = cluster_key

    logger.info("Cluster QC stats (%d clusters):", len(df))
    for idx, row in df.iterrows():
        logger.info(
            "  Cluster %s: n=%d (%.1f%%), genes=%.0f, counts=%.0f, mt=%.1f%%",
            idx, row["n_cells"], row["pct_cells"],
            row["mean_genes"], row["mean_counts"], row["mean_mt"],
        )

    return df


# ===========================================================================
# Visualization  (from plot_dimreduction.py)
# ===========================================================================


def plot_umap_clusters(
    adata: AnnData,
    output_dir: Union[str, Path],
    cluster_key: str = "leiden_0.8",
    figsize: Tuple[int, int] = (8, 6),
    palette: Optional[Union[str, Sequence[str]]] = None,
) -> None:
    """Plot UMAP coloured by cluster labels with legend on data.

    Saves ``figures/umap_{cluster_key}.png``.

    Parameters
    ----------
    adata
        AnnData with UMAP and clustering.
    output_dir
        Output directory.
    cluster_key
        Column in ``adata.obs`` for colouring.
    figsize
        Figure size.
    palette
        Colour palette (passed to ``sc.pl.umap``).
    """
    import scanpy as sc
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    if "X_umap" not in adata.obsm:
        logger.warning("UMAP not found. Skipping cluster plot.")
        return
    if cluster_key not in adata.obs.columns:
        logger.warning("Cluster key '%s' not found. Skipping.", cluster_key)
        return

    logger.info("Plotting UMAP clusters (%s)", cluster_key)
    sc.pl.umap(
        adata,
        color=cluster_key,
        palette=palette,
        legend_loc="on data",
        legend_fontsize=8,
        frameon=False,
        show=False,
        size=15,
    )
    fig = plt.gcf()
    fig.set_size_inches(*figsize)

    filename = f"umap_{cluster_key}.png"
    save_figure(fig, output_dir, filename)


def plot_clustering_comparison(
    adata: AnnData,
    output_dir: Union[str, Path],
    resolutions: Optional[List[float]] = None,
    figsize: Tuple[int, int] = (16, 4),
) -> None:
    """Plot multi-panel UMAPs comparing clustering resolutions.

    Saves ``figures/clustering_comparison.png``.

    Parameters
    ----------
    adata
        AnnData with UMAP and multiple Leiden results.
    output_dir
        Output directory.
    resolutions
        Resolution values to display (must have corresponding
        ``leiden_{res}`` keys in ``adata.obs``).
    figsize
        Figure size.
    """
    import scanpy as sc
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    if "X_umap" not in adata.obsm:
        logger.warning("UMAP not found. Skipping comparison plot.")
        return

    if resolutions is None:
        resolutions = [0.4, 0.6, 0.8, 1.0]

    # Keep only resolutions that exist
    keys = [f"leiden_{r}" for r in resolutions if f"leiden_{r}" in adata.obs.columns]
    if not keys:
        logger.warning("No leiden_* columns found for resolutions %s. Skipping.", resolutions)
        return

    logger.info("Plotting clustering comparison for %d resolutions", len(keys))

    n_panels = len(keys)
    fig_w = max(figsize[0], 4 * n_panels)
    fig, axes = plt.subplots(1, n_panels, figsize=(fig_w, figsize[1]))
    if n_panels == 1:
        axes = [axes]

    coords = adata.obsm["X_umap"]
    for ax, key in zip(axes, keys):
        cats = adata.obs[key].astype("category")
        n_clusters = cats.nunique()
        ax.scatter(
            coords[:, 0], coords[:, 1],
            c=cats.cat.codes, cmap="tab20", s=1, alpha=0.6, rasterized=True,
        )
        ax.set_title(f"{key} ({n_clusters} clusters)", fontsize=10)
        ax.set_xlabel("UMAP1")
        ax.set_ylabel("UMAP2")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    plt.tight_layout()
    save_figure(fig, output_dir, "clustering_comparison.png")


def plot_feature_umap(
    adata: AnnData,
    output_dir: Union[str, Path],
    features: List[str],
    use_raw: bool = False,
    layer: Optional[str] = None,
    ncols: int = 3,
    cmap: str = "viridis",
) -> None:
    """Plot multi-gene UMAP grid.

    Saves ``figures/feature_umap.png``.

    Parameters
    ----------
    adata
        AnnData with UMAP.
    output_dir
        Output directory.
    features
        Gene names or ``adata.obs`` columns to plot.
    use_raw
        Pull expression values from ``adata.raw``.
    layer
        Layer to use for expression values.
    ncols
        Number of columns in the grid.
    cmap
        Colour map for continuous features.
    """
    import scanpy as sc
    import matplotlib.pyplot as plt
    from .viz_utils import save_figure

    if "X_umap" not in adata.obsm:
        logger.warning("UMAP not found. Skipping feature plot.")
        return

    # Filter features that actually exist
    valid: list[str] = []
    for f in features:
        if f in adata.obs.columns:
            valid.append(f)
        elif f in adata.var_names:
            valid.append(f)
        elif use_raw and adata.raw is not None and f in adata.raw.var_names:
            valid.append(f)
        else:
            logger.warning("Feature '%s' not found. Skipping.", f)

    if not valid:
        logger.warning("No valid features to plot.")
        return

    logger.info("Plotting feature UMAP for %d features", len(valid))

    nrows = math.ceil(len(valid) / ncols)
    fig_height = max(4, 4 * nrows)
    fig_width = max(4, 4 * ncols)

    sc.pl.umap(
        adata,
        color=valid,
        use_raw=use_raw,
        layer=layer,
        ncols=ncols,
        cmap=cmap,
        frameon=False,
        show=False,
        size=10,
    )
    fig = plt.gcf()
    fig.set_size_inches(fig_width, fig_height)
    save_figure(fig, output_dir, "feature_umap.png")


def plot_umap_styled(
    adata: AnnData,
    output_dir: Union[str, Path],
    color_by: str,
    figsize: Tuple[int, int] = (8, 6),
    point_size: float = 0.5,
) -> None:
    """Seaborn-styled UMAP with manual palette for categorical data.

    For categorical columns with <= 20 categories, uses a curated palette.
    For continuous columns, uses a viridis colour map.

    Saves ``figures/umap_styled_{color_by}.png``.

    Parameters
    ----------
    adata
        AnnData with UMAP.
    output_dir
        Output directory.
    color_by
        Column in ``adata.obs`` or gene name.
    figsize
        Figure size.
    point_size
        Scatter point size.
    """
    import matplotlib.pyplot as plt
    import seaborn as sns
    from .viz_utils import save_figure

    if "X_umap" not in adata.obsm:
        logger.warning("UMAP not found. Skipping styled plot.")
        return

    coords = adata.obsm["X_umap"]
    logger.info("Plotting styled UMAP (color_by=%s)", color_by)

    sns.set_style("white")
    fig, ax = plt.subplots(1, 1, figsize=figsize)

    # Determine if colouring by obs column or gene expression
    if color_by in adata.obs.columns:
        values = adata.obs[color_by]
    elif color_by in adata.var_names:
        # Get expression from .X (scaled) or .raw
        gene_idx = list(adata.var_names).index(color_by)
        expr = adata.X[:, gene_idx]
        if hasattr(expr, "toarray"):
            expr = expr.toarray().ravel()
        else:
            expr = np.asarray(expr).ravel()
        values = pd.Series(expr, index=adata.obs_names, name=color_by)
    else:
        logger.warning("'%s' not found in adata.obs or var_names. Skipping.", color_by)
        plt.close(fig)
        return

    is_categorical = hasattr(values, "cat") or values.dtype == object or values.dtype.name == "category"

    if is_categorical:
        values = values.astype("category")
        categories = values.cat.categories
        n_cats = len(categories)

        if n_cats <= 20:
            palette = sns.color_palette("tab20", n_colors=n_cats)
        else:
            palette = sns.color_palette("husl", n_colors=n_cats)

        cat_to_color = dict(zip(categories, palette))
        colors = [cat_to_color[v] for v in values]

        ax.scatter(
            coords[:, 0], coords[:, 1],
            c=colors, s=point_size, alpha=0.7, edgecolors="none", rasterized=True,
        )

        # Build legend
        from matplotlib.lines import Line2D
        handles = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor=cat_to_color[c],
                   markersize=6, label=str(c))
            for c in categories
        ]
        if n_cats <= 20:
            ax.legend(
                handles=handles, loc="center left", bbox_to_anchor=(1.02, 0.5),
                frameon=False, fontsize=7, ncol=max(1, n_cats // 15),
            )
        else:
            logger.info("Too many categories (%d) for legend. Omitting.", n_cats)
    else:
        # Continuous
        sc = ax.scatter(
            coords[:, 0], coords[:, 1],
            c=values, cmap="viridis", s=point_size, alpha=0.7,
            edgecolors="none", rasterized=True,
        )
        plt.colorbar(sc, ax=ax, shrink=0.6, label=color_by)

    ax.set_xlabel("UMAP1")
    ax.set_ylabel("UMAP2")
    ax.set_title(color_by)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    sns.despine(ax=ax)

    plt.tight_layout()
    # Sanitise filename
    safe_name = color_by.replace("/", "_").replace(" ", "_")
    save_figure(fig, output_dir, f"umap_styled_{safe_name}.png")
