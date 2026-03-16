#!/usr/bin/env python3
"""Single-cell trajectory analysis utilities.

Provides 3-level trajectory analysis with graceful degradation:
- Level 1 (scanpy): PAGA + DPT pseudotime + diffusion map (always available)
- Level 2 (scVelo): RNA velocity, latent time (requires spliced/unspliced layers)
- Level 3 (CellRank): Fate probabilities, driver genes (optional)

Based on validated reference scripts from biomni_scripts/scrna-trajectory-scripts/
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def check_velocity_available(adata) -> bool:
    """Check if RNA velocity can be computed (requires spliced/unspliced layers)."""
    has_spliced = "spliced" in adata.layers
    has_unspliced = "unspliced" in adata.layers
    if not (has_spliced and has_unspliced):
        logger.info("RNA velocity requires 'spliced' and 'unspliced' layers")
        return False
    return True


def run_paga_analysis(
    adata,
    cluster_key: str = "leiden",
    n_neighbors: int = 30,
    copy: bool = False,
) -> dict[str, Any]:
    """Run PAGA graph analysis.

    Parameters
    ----------
    adata : AnnData
        AnnData object with neighbor graph computed
    cluster_key : str
        Key in adata.obs for cluster labels
    n_neighbors : int
        Number of neighbors for graph construction
    copy : bool
        Whether to copy adata before modification

    Returns
    -------
    dict with keys:
        - 'connectivities': PAGA connectivity matrix
        - 'connectivities_tree': PAGA tree
        - 'transitions_confidence': Transition confidence scores
    """
    import scanpy as sc

    if copy:
        adata = adata.copy()

    # Ensure neighbors are computed
    if "neighbors" not in adata.uns:
        logger.info("Computing neighbor graph...")
        sc.pp.neighbors(adata, n_neighbors=n_neighbors)

    # Run PAGA
    logger.info(f"Running PAGA with cluster key: {cluster_key}")
    sc.tl.paga(adata, groups=cluster_key)

    result = {
        "connectivities": adata.uns["paga"]["connectivities"].copy(),
        "connectivities_tree": adata.uns["paga"]["connectivities_tree"].copy(),
        "transitions_confidence": adata.uns["paga"].get("transitions_confidence", None),
    }

    return result


def run_diffusion_map(
    adata,
    n_comps: int = 15,
    n_dcs: int = 10,
    copy: bool = False,
) -> dict[str, Any]:
    """Run diffusion map dimensionality reduction.

    Parameters
    ----------
    adata : AnnData
        AnnData object
    n_comps : int
        Number of diffusion components
    n_dcs : int
        Number of diffusion components to use for DPT
    copy : bool
        Whether to copy adata before modification

    Returns
    -------
    dict with keys:
        - 'diffmap': Diffusion map coordinates
        - 'eigvals': Eigenvalues
    """
    import scanpy as sc

    if copy:
        adata = adata.copy()

    logger.info(f"Running diffusion map with {n_comps} components...")
    sc.tl.diffmap(adata, n_comps=n_comps)

    result = {
        "diffmap": adata.obsm["X_diffmap"].copy(),
    }

    return result


def run_dpt_pseudotime(
    adata,
    root_cell_indices: list[int] | None = None,
    root_cluster: str | None = None,
    cluster_key: str = "leiden",
    n_dcs: int = 10,
    copy: bool = False,
) -> dict[str, Any]:
    """Run DPT pseudotime analysis.

    Parameters
    ----------
    adata : AnnData
        AnnData object with diffusion map computed
    root_cell_indices : list of int, optional
        Indices of root cells
    root_cluster : str, optional
        Cluster label to use as root (alternative to root_cell_indices)
    cluster_key : str
        Key in adata.obs for cluster labels
    n_dcs : int
        Number of diffusion components to use
    copy : bool
        Whether to copy adata before modification

    Returns
    -------
    dict with keys:
        - 'pseudotime': DPT pseudotime values
        - 'root_cells': Indices of root cells used
    """
    import scanpy as sc

    if copy:
        adata = adata.copy()

    # Ensure diffusion map is computed
    if "X_diffmap" not in adata.obsm:
        logger.info("Computing diffusion map...")
        sc.tl.diffmap(adata, n_comps=max(15, n_dcs + 5))

    # Determine root cells
    if root_cell_indices is not None:
        root_idx = root_cell_indices[0]  # DPT uses single root
        adata.uns["iroot"] = root_idx
        logger.info(f"Using root cell index: {root_idx}")
    elif root_cluster is not None:
        # Use first cell in root cluster
        cluster_labels = adata.obs[cluster_key]
        if root_cluster not in cluster_labels.values:
            raise ValueError(f"Root cluster '{root_cluster}' not found in {cluster_key}")
        root_idx = np.where(cluster_labels == root_cluster)[0][0]
        adata.uns["iroot"] = root_idx
        logger.info(f"Using root cell {root_idx} from cluster '{root_cluster}'")
    else:
        # Use cell with lowest DPT component as root
        if "iroot" not in adata.uns:
            # Find cell with minimum first diffusion component
            root_idx = np.argmin(adata.obsm["X_diffmap"][:, 1])
            adata.uns["iroot"] = root_idx
            logger.info(f"Auto-detected root cell: {root_idx}")

    # Run DPT
    logger.info("Running DPT pseudotime...")
    sc.tl.dpt(adata, n_dcs=n_dcs)

    result = {
        "pseudotime": adata.obs["dpt_pseudotime"].values.copy(),
        "root_cells": [adata.uns["iroot"]],
    }

    return result


def find_trajectory_genes(
    adata,
    pseudotime_key: str = "dpt_pseudotime",
    n_genes: int = 50,
    method: str = "pearson",
    copy: bool = False,
) -> pd.DataFrame:
    """Find genes correlated with pseudotime (trajectory genes).

    Parameters
    ----------
    adata : AnnData
        AnnData object with pseudotime computed
    pseudotime_key : str
        Key in adata.obs for pseudotime values
    n_genes : int
        Number of top genes to return
    method : str
        Correlation method ('pearson' or 'spearman')
    copy : bool
        Whether to copy adata before modification

    Returns
    -------
    DataFrame with columns: gene, correlation, pvalue
    """
    from scipy import stats

    if pseudotime_key not in adata.obs.columns:
        raise ValueError(f"Pseudotime key '{pseudotime_key}' not found in adata.obs")

    pseudotime = adata.obs[pseudotime_key].values

    # Get expression matrix
    if hasattr(adata.X, "toarray"):
        X = adata.X.toarray()
    else:
        X = adata.X

    logger.info(f"Finding trajectory genes (method={method}, n={n_genes})...")

    correlations = []
    pvalues = []
    genes = []

    for i, gene in enumerate(adata.var_names):
        gene_expr = X[:, i]

        # Skip genes with no variance
        if np.std(gene_expr) < 1e-10:
            correlations.append(0)
            pvalues.append(1)
            genes.append(gene)
            continue

        if method == "pearson":
            r, p = stats.pearsonr(gene_expr, pseudotime)
        elif method == "spearman":
            r, p = stats.spearmanr(gene_expr, pseudotime)
        else:
            raise ValueError(f"Unknown method: {method}")

        correlations.append(r)
        pvalues.append(p)
        genes.append(gene)

    # Create dataframe
    df = pd.DataFrame({
        "gene": genes,
        "correlation": correlations,
        "pvalue": pvalues,
    })

    # Sort by absolute correlation
    df["abs_corr"] = np.abs(df["correlation"])
    df = df.sort_values("abs_corr", ascending=False).head(n_genes)
    df = df.drop(columns=["abs_corr"])

    logger.info(f"Found {len(df)} trajectory-associated genes")

    return df


def run_velocity_analysis(
    adata,
    mode: str = "stochastic",
    n_jobs: int = 4,
    copy: bool = False,
) -> dict[str, Any] | None:
    """Run scVelo RNA velocity analysis.

    Parameters
    ----------
    adata : AnnData
        AnnData object with spliced/unspliced layers
    mode : str
        scVelo mode ('stochastic', 'dynamical', 'steady_state')
    n_jobs : int
        Number of parallel jobs
    copy : bool
        Whether to copy adata before modification

    Returns
    -------
    dict with keys:
        - 'velocity': Velocity vectors
        - 'velocity_graph': Velocity graph
        - 'latent_time': Latent time (if dynamical mode)
    or None if scVelo not available
    """
    try:
        import scvelo as scv
    except ImportError:
        logger.warning("scVelo not installed. Skipping velocity analysis.")
        return None

    if not check_velocity_available(adata):
        logger.warning("Spliced/unspliced layers not found. Skipping velocity analysis.")
        return None

    if copy:
        adata = adata.copy()

    logger.info(f"Running scVelo velocity analysis (mode={mode})...")

    # Filter and normalize
    scv.pp.filter_and_normalize(adata, min_shared_counts=20, n_top_genes=2000)

    # Compute moments
    scv.pp.moments(adata, n_pcs=30, n_neighbors=30)

    # Recover dynamics
    if mode == "dynamical":
        scv.tl.recover_dynamics(adata, n_jobs=n_jobs)

    # Compute velocity
    scv.tl.velocity(adata, mode=mode)

    # Compute velocity graph
    scv.tl.velocity_graph(adata)

    result = {
        "velocity": adata.layers["velocity"].copy() if "velocity" in adata.layers else None,
        "velocity_graph": adata.uns["velocity_graph"].copy() if "velocity_graph" in adata.uns else None,
    }

    # Latent time (dynamical mode only)
    if mode == "dynamical":
        scv.tl.latent_time(adata)
        result["latent_time"] = adata.obs["latent_time"].values.copy()

    logger.info("Velocity analysis complete")

    return result


def plot_paga_graph(
    adata,
    output_dir,
    cluster_key: str = "leiden",
    title: str = "PAGA Graph",
    fontsize: int = 10,
    node_size_scale: float = 1.0,
) -> str | None:
    """Plot PAGA connectivity graph.

    Returns
    -------
    Path to saved figure or None if plotting failed
    """
    import matplotlib.pyplot as plt
    import scanpy as sc
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        fig, ax = plt.subplots(figsize=(10, 8))
        sc.pl.paga(
            adata,
            groups=None,
            threshold=0.03,
            node_size_scale=node_size_scale,
            node_size_power=0.8,
            fontsize=fontsize,
            fontoutline=2,
            frameon=False,
            show=False,
            ax=ax,
        )
        ax.set_title(title, fontsize=14, fontweight="bold")

        fig_path = output_dir / "paga_graph.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved: {fig_path}")
        return str(fig_path)

    except Exception as e:
        logger.warning(f"PAGA plot failed: {e}")
        return None


def plot_pseudotime_umap(
    adata,
    output_dir,
    pseudotime_key: str = "dpt_pseudotime",
    title: str = "Pseudotime",
) -> str | None:
    """Plot pseudotime on UMAP coordinates.

    Returns
    -------
    Path to saved figure or None if plotting failed
    """
    import matplotlib.pyplot as plt
    import scanpy as sc
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        if pseudotime_key not in adata.obs.columns:
            logger.warning(f"{pseudotime_key} not found in adata.obs")
            return None

        fig, ax = plt.subplots(figsize=(8, 6))
        sc.pl.umap(
            adata,
            color=pseudotime_key,
            ax=ax,
            show=False,
            cmap="viridis",
        )
        ax.set_title(title, fontsize=14, fontweight="bold")

        fig_path = output_dir / "pseudotime_umap.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved: {fig_path}")
        return str(fig_path)

    except Exception as e:
        logger.warning(f"Pseudotime UMAP plot failed: {e}")
        return None


def plot_diffusion_components(
    adata,
    output_dir,
    n_components: int = 3,
) -> list[str]:
    """Plot diffusion map components.

    Returns
    -------
    List of paths to saved figures
    """
    import matplotlib.pyplot as plt
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    figures = []

    try:
        if "X_diffmap" not in adata.obsm:
            logger.warning("X_diffmap not found in adata.obsm")
            return figures

        diffmap = adata.obsm["X_diffmap"]
        n_components = min(n_components, diffmap.shape[1] - 1)

        # Pairwise scatter plots
        fig, axes = plt.subplots(1, n_components - 1, figsize=(5 * (n_components - 1), 4))
        if n_components == 2:
            axes = [axes]

        for i in range(1, n_components):
            ax = axes[i - 1]
            ax.scatter(diffmap[:, 1], diffmap[:, i + 1], s=1, alpha=0.5)
            ax.set_xlabel("DC1")
            ax.set_ylabel(f"DC{i + 1}")
            ax.set_title(f"Diffusion Component {i + 1}")

        fig.tight_layout()
        fig_path = output_dir / "diffusion_components.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        figures.append(str(fig_path))
        plt.close()

        logger.info(f"Saved: {fig_path}")

    except Exception as e:
        logger.warning(f"Diffusion components plot failed: {e}")

    return figures


def plot_trajectory_gene_heatmap(
    adata,
    trajectory_genes: pd.DataFrame,
    output_dir,
    pseudotime_key: str = "dpt_pseudotime",
    n_genes: int = 20,
    title: str = "Trajectory Gene Expression",
) -> str | None:
    """Plot heatmap of trajectory genes ordered by pseudotime.

    Returns
    -------
    Path to saved figure or None if plotting failed
    """
    import matplotlib.pyplot as plt
    import seaborn as sns
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        top_genes = trajectory_genes.head(n_genes)["gene"].tolist()

        # Get expression matrix
        if hasattr(adata.X, "toarray"):
            X = adata.X.toarray()
        else:
            X = adata.X

        # Get gene indices
        gene_mask = adata.var_names.isin(top_genes)
        gene_order = [g for g in top_genes if g in adata.var_names]

        if len(gene_order) == 0:
            logger.warning("No trajectory genes found in adata")
            return None

        # Subset expression
        gene_indices = [list(adata.var_names).index(g) for g in gene_order]
        expr = X[:, gene_indices]

        # Order by pseudotime
        pseudotime = adata.obs[pseudotime_key].values
        order = np.argsort(pseudotime)
        expr = expr[order, :]

        # Normalize per gene
        expr = (expr - expr.mean(axis=0)) / (expr.std(axis=0) + 1e-10)

        # Plot
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(
            expr.T,
            xticklabels=False,
            yticklabels=gene_order,
            cmap="RdBu_r",
            center=0,
            ax=ax,
        )
        ax.set_xlabel("Cells (ordered by pseudotime)")
        ax.set_ylabel("Genes")
        ax.set_title(title, fontsize=14, fontweight="bold")

        fig_path = output_dir / "trajectory_gene_heatmap.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved: {fig_path}")
        return str(fig_path)

    except Exception as e:
        logger.warning(f"Trajectory gene heatmap failed: {e}")
        return None


def plot_velocity_stream(
    adata,
    output_dir,
    basis: str = "umap",
    title: str = "RNA Velocity Stream",
) -> str | None:
    """Plot velocity stream plot.

    Returns
    -------
    Path to saved figure or None if plotting failed
    """
    import matplotlib.pyplot as plt
    from pathlib import Path

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import scvelo as scv
    except ImportError:
        logger.warning("scVelo not installed. Skipping velocity stream plot.")
        return None

    try:
        fig, ax = plt.subplots(figsize=(10, 8))
        scv.pl.velocity_embedding_stream(
            adata,
            basis=basis,
            ax=ax,
            show=False,
        )
        ax.set_title(title, fontsize=14, fontweight="bold")

        fig_path = output_dir / "velocity_stream.png"
        fig.savefig(fig_path, dpi=300, bbox_inches="tight")
        plt.close()

        logger.info(f"Saved: {fig_path}")
        return str(fig_path)

    except Exception as e:
        logger.warning(f"Velocity stream plot failed: {e}")
        return None
