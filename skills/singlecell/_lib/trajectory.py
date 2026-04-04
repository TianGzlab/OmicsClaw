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


def run_palantir_pseudotime(
    adata,
    *,
    early_cell: str,
    terminal_states: dict[str, str] | None = None,
    knn: int = 30,
    n_components: int = 10,
    num_waypoints: int = 1200,
    max_iterations: int = 25,
    seed: int = 20,
    copy: bool = False,
) -> dict[str, Any]:
    """Run Palantir pseudotime analysis using the official AnnData workflow."""
    import palantir

    if copy:
        adata = adata.copy()

    if early_cell not in adata.obs_names:
        raise ValueError(f"Palantir early_cell '{early_cell}' not found in adata.obs_names")

    if "DM_EigenVectors" not in adata.obsm:
        logger.info("Running Palantir diffusion maps with n_components=%s", n_components)
        palantir.utils.run_diffusion_maps(adata, n_components=n_components)
    if "DM_EigenVectors_multiscaled" not in adata.obsm:
        logger.info("Determining Palantir multiscale space")
        palantir.utils.determine_multiscale_space(adata)

    result = palantir.core.run_palantir(
        adata,
        early_cell=early_cell,
        terminal_states=terminal_states,
        knn=knn,
        num_waypoints=num_waypoints,
        max_iterations=max_iterations,
        seed=seed,
    )
    return {
        "pseudotime": adata.obs["palantir_pseudotime"].values.copy(),
        "entropy": adata.obs["palantir_entropy"].values.copy() if "palantir_entropy" in adata.obs else None,
        "fate_probabilities": adata.obsm["palantir_fate_probabilities"].copy()
        if "palantir_fate_probabilities" in adata.obsm
        else None,
        "result": result,
    }


def run_cellrank_pseudotime(
    adata,
    *,
    root_cell: int | None = None,
    root_cluster: str | None = None,
    cluster_key: str = "leiden",
    n_states: int = 3,
    schur_components: int = 20,
    frac_to_keep: float = 0.3,
    use_velocity: bool = False,
    n_dcs: int = 10,
    copy: bool = False,
) -> dict[str, Any]:
    """Run CellRank fate inference using connectivity, pseudotime, or velocity kernels."""
    import scanpy as sc
    import cellrank as cr

    if copy:
        adata = adata.copy()

    if "neighbors" not in adata.uns:
        sc.pp.neighbors(adata)

    dpt_result = run_dpt_pseudotime(
        adata,
        root_cell_indices=[root_cell] if root_cell is not None else None,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        n_dcs=n_dcs,
    )

    ck = cr.kernels.ConnectivityKernel(adata).compute_transition_matrix()
    kernel = ck
    kernel_mode = "connectivity"

    if use_velocity and check_velocity_available(adata):
        try:
            vk = cr.kernels.VelocityKernel(adata).compute_transition_matrix()
            kernel = 0.8 * vk + 0.2 * ck
            kernel_mode = "velocity+connectivity"
        except Exception as exc:
            logger.warning("CellRank VelocityKernel unavailable (%s); falling back to pseudotime/connectivity.", exc)

    if kernel_mode == "connectivity":
        try:
            pk = cr.kernels.PseudotimeKernel(adata, time_key="dpt_pseudotime").compute_transition_matrix(
                frac_to_keep=frac_to_keep,
                n_jobs=1,
                backend="threading",
                show_progress_bar=False,
            )
            kernel = 0.8 * pk + 0.2 * ck
            kernel_mode = "pseudotime+connectivity"
        except Exception as exc:
            logger.warning("CellRank PseudotimeKernel unavailable (%s); using ConnectivityKernel only.", exc)

    if cluster_key in adata.obs.columns and not pd.api.types.is_categorical_dtype(adata.obs[cluster_key]):
        adata.obs[cluster_key] = adata.obs[cluster_key].astype("category")

    effective_schur = min(max(int(schur_components), 2), max(2, adata.n_obs - 1))
    effective_states = min(max(int(n_states), 2), effective_schur)

    estimator = cr.estimators.GPCCA(kernel)
    estimator.compute_schur(n_components=effective_schur)
    estimator.compute_macrostates(
        n_states=effective_states,
        cluster_key=cluster_key if cluster_key in adata.obs.columns else None,
    )

    macro_key = next((key for key in ("macrostates_fwd", "macrostates", "term_states_fwd") if key in adata.obs.columns), None)
    terminal_states: list[str] = []
    lineage_key: str | None = None
    driver_genes: dict[str, list[str]] = {}
    fate_probs = None

    try:
        estimator.predict_terminal_states()
        term_key = next((key for key in ("terminal_states", "term_states_fwd") if key in adata.obs.columns), None)
        if term_key:
            terminal_states = [str(x) for x in adata.obs[term_key].dropna().unique().tolist()]
        estimator.compute_fate_probabilities(
            n_jobs=1,
            backend="threading",
            show_progress_bar=False,
            use_petsc=False,
        )
        lineage_key = next((key for key in ("lineages_fwd", "to_terminal_states") if key in adata.obsm), None)
        if lineage_key:
            fate_probs = np.asarray(adata.obsm[lineage_key], dtype=float)
        for state in terminal_states[:5]:
            try:
                drivers = estimator.compute_lineage_drivers(lineages=state)
                if drivers is not None and not drivers.empty:
                    driver_genes[state] = drivers.head(10).index.astype(str).tolist()
            except Exception as exc:
                logger.warning("CellRank lineage drivers failed for '%s': %s", state, exc)
    except Exception as exc:
        logger.warning("CellRank terminal-state / fate computation failed: %s", exc)

    adata.uns["cellrank_trajectory"] = {
        "kernel_mode": kernel_mode,
        "macrostate_key": macro_key,
        "lineage_key": lineage_key,
        "terminal_states": terminal_states,
        "n_states": effective_states,
        "schur_components": effective_schur,
        "frac_to_keep": frac_to_keep,
        "use_velocity": use_velocity,
        "root_cell": int(dpt_result["root_cells"][0]) if dpt_result["root_cells"] else None,
    }

    return {
        "pseudotime": adata.obs["dpt_pseudotime"].values.copy(),
        "root_cell": int(dpt_result["root_cells"][0]) if dpt_result["root_cells"] else None,
        "root_cell_name": str(adata.obs_names[int(dpt_result["root_cells"][0])]) if dpt_result["root_cells"] else None,
        "kernel_mode": kernel_mode,
        "macrostate_key": macro_key,
        "lineage_key": lineage_key,
        "terminal_states": terminal_states,
        "driver_genes": driver_genes,
        "fate_probabilities": fate_probs.copy() if fate_probs is not None else None,
        "n_macrostates": int(adata.obs[macro_key].nunique()) if macro_key else 0,
    }


def run_via_pseudotime(
    adata,
    *,
    root_cell: int | None = None,
    root_cluster: str | None = None,
    cluster_key: str = "leiden",
    knn: int = 30,
    n_components: int = 10,
    seed: int = 20,
    copy: bool = False,
) -> dict[str, Any]:
    """Run pyVIA pseudotime analysis on a PCA-like embedding."""
    import scanpy as sc

    # pyVIA depends on nptyping aliases that were removed in NumPy 2.x.
    compat_aliases = {
        "bool8": np.bool_,
        "object0": np.object_,
        "int0": np.intp,
        "uint0": np.uintp,
        "uint": np.uint64,
        "float_": np.float64,
        "longfloat": np.longdouble,
        "singlecomplex": np.complex64,
        "complex_": np.complex128,
        "cfloat": np.complex128,
        "clongfloat": np.clongdouble,
        "longcomplex": np.clongdouble,
        "void0": np.void,
        "bytes0": np.bytes_,
        "str0": np.str_,
        "string_": np.bytes_,
        "unicode_": np.str_,
    }
    for alias, target in compat_aliases.items():
        if not hasattr(np, alias):
            setattr(np, alias, target)
    try:
        import pyVIA.core as via
        import pyVIA.utils_via as via_utils
        from scipy.sparse import csr_matrix
    except ImportError as exc:
        raise ImportError("pyVIA is required for method='via'. Install with `pip install pyVIA`.") from exc

    def _patched_get_sparse_from_igraph(graph, weight_attr=None):
        edges = graph.get_edgelist()
        weights = list(graph.es[weight_attr]) if weight_attr else [1] * len(edges)
        if not graph.is_directed():
            reverse_edges = [(v, u) for u, v in edges]
            edges = edges + reverse_edges
            weights = weights + weights[: len(reverse_edges)]
        shape = (graph.vcount(), graph.vcount())
        if edges:
            rows, cols = zip(*edges)
            return csr_matrix((weights, (rows, cols)), shape=shape)
        return csr_matrix(shape)

    # pyVIA 0.2.4 still builds sparse matrices via `csr_matrix((weights, zip(*edges)))`,
    # which breaks on newer SciPy because `zip(*edges)` is an iterator instead of a
    # concrete `(rows, cols)` tuple. Patch both modules before model creation.
    via_utils.get_sparse_from_igraph = _patched_get_sparse_from_igraph
    via.get_sparse_from_igraph = _patched_get_sparse_from_igraph

    if copy:
        adata = adata.copy()

    if root_cell is not None:
        if root_cell < 0 or root_cell >= adata.n_obs:
            raise ValueError(f"root_cell index {root_cell} is out of range for {adata.n_obs} cells")
        root_idx = int(root_cell)
    else:
        if root_cluster is None:
            raise ValueError("VIA requires an explicit root choice via --root-cell or --root-cluster.")
        if cluster_key not in adata.obs.columns:
            raise ValueError(f"Cluster key '{cluster_key}' not found in adata.obs")
        cluster_values = adata.obs[cluster_key].astype(str)
        root_cluster_text = str(root_cluster)
        if root_cluster_text not in set(cluster_values):
            raise ValueError(f"Root cluster '{root_cluster_text}' not found in {cluster_key}")
        root_idx = int(np.where(cluster_values == root_cluster_text)[0][0])

    if "X_pca" in adata.obsm:
        embedding = np.asarray(adata.obsm["X_pca"][:, : max(2, n_components)], dtype=float)
        embedding_key = "X_pca"
    else:
        matrix = adata.X.toarray() if hasattr(adata.X, "toarray") else np.asarray(adata.X)
        embedding = np.asarray(matrix[:, : max(2, n_components)], dtype=float)
        embedding_key = "X"

    labels = adata.obs[cluster_key].astype(str).tolist() if cluster_key in adata.obs.columns else ["unknown"] * adata.n_obs
    logger.info("Running VIA with knn=%s, n_components=%s, root_idx=%s", knn, n_components, root_idx)
    try:
        model = via.VIA(
            embedding,
            labels,
            knn=knn,
            root_user=[root_idx],
            dataset="OmicsClaw",
            random_seed=seed,
        )
        model.run_VIA()

        pseudotime = np.asarray(model.single_cell_pt_markov, dtype=float)
        adata.obs["via_pseudotime"] = pseudotime

        branch_probs = None
        if hasattr(model, "single_cell_bp") and model.single_cell_bp is not None:
            branch_probs = np.asarray(model.single_cell_bp, dtype=float)
            if branch_probs.shape[0] == adata.n_obs:
                adata.obsm["via_fate_probabilities"] = branch_probs

        terminal_clusters = [str(x) for x in getattr(model, "terminal_clusters", [])]
        method_name = "via"
        fallback_reason = None
    except Exception as exc:  # pragma: no cover - validated through smoke tests
        logger.warning("pyVIA failed; falling back to a diffusion-pseudotime compatible path: %s", exc)
        if "X_diffmap" not in adata.obsm:
            sc.tl.diffmap(adata, n_comps=max(15, n_components + 5))
        adata.uns["iroot"] = root_idx
        sc.tl.dpt(adata, n_dcs=max(2, min(n_components, adata.obsm["X_diffmap"].shape[1] - 1)))
        pseudotime = np.asarray(adata.obs["dpt_pseudotime"], dtype=float)
        adata.obs["via_pseudotime"] = pseudotime
        branch_probs = None
        if cluster_key in adata.obs.columns:
            cluster_means = (
                pd.DataFrame({cluster_key: adata.obs[cluster_key].astype(str), "pt": pseudotime})
                .groupby(cluster_key, observed=False)["pt"]
                .mean()
                .sort_values()
            )
            terminal_clusters = [str(x) for x in cluster_means.tail(2).index.tolist()]
        else:
            terminal_clusters = []
        model = None
        method_name = "via_compatible"
        fallback_reason = str(exc)

    adata.uns["via_trajectory"] = {
        "root_cell": root_idx,
        "root_cell_name": str(adata.obs_names[root_idx]),
        "terminal_clusters": terminal_clusters,
        "embedding_key": embedding_key,
        "knn": knn,
        "n_components": n_components,
        "seed": seed,
        "method": method_name,
        "fallback_reason": fallback_reason,
    }
    return {
        "method": method_name,
        "pseudotime": pseudotime.copy(),
        "root_cell": root_idx,
        "root_cell_name": str(adata.obs_names[root_idx]),
        "fate_probabilities": branch_probs.copy() if branch_probs is not None else None,
        "terminal_clusters": terminal_clusters,
        "model": model,
    }


def resolve_palantir_early_cell(
    adata,
    *,
    root_cell: int | None = None,
    root_cluster: str | None = None,
    cluster_key: str = "leiden",
) -> str:
    """Resolve an explicit early cell for the Palantir workflow."""
    import palantir

    if root_cell is not None:
        if root_cell < 0 or root_cell >= adata.n_obs:
            raise ValueError(f"root_cell index {root_cell} is out of range for {adata.n_obs} cells")
        return str(adata.obs_names[root_cell])

    if root_cluster is None:
        raise ValueError("Palantir requires an explicit root choice via --root-cell or --root-cluster.")
    if cluster_key not in adata.obs.columns:
        raise ValueError(f"Cluster key '{cluster_key}' not found in adata.obs")

    labels = adata.obs[cluster_key].astype(str)
    root_cluster_text = str(root_cluster)
    if root_cluster_text not in set(labels):
        raise ValueError(f"Root cluster '{root_cluster_text}' not found in {cluster_key}")

    if "DM_EigenVectors" not in adata.obsm:
        palantir.utils.run_diffusion_maps(adata, n_components=10)
    if "DM_EigenVectors_multiscaled" not in adata.obsm:
        palantir.utils.determine_multiscale_space(adata)

    return str(palantir.utils.early_cell(adata, celltype=root_cluster_text, celltype_column=cluster_key))


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

    # Get expression matrix; prefer log-normalized raw when available
    matrix = adata.raw.X if adata.raw is not None and adata.raw.shape == adata.shape else adata.X
    var_names = adata.raw.var_names if adata.raw is not None and adata.raw.shape == adata.shape else adata.var_names
    if hasattr(matrix, "toarray"):
        X = matrix.toarray()
    else:
        X = matrix

    logger.info(f"Finding trajectory genes (method={method}, n={n_genes})...")

    correlations = []
    pvalues = []
    genes = []

    for i, gene in enumerate(var_names):
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

    # Filter and normalize using the current scVelo API.
    scv.pp.filter_and_normalize(adata, min_shared_counts=20)

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

        if "X_umap" not in adata.obsm:
            logger.info("X_umap not found; recomputing UMAP for plotting")
            sc.pp.neighbors(adata)
            sc.tl.umap(adata)

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
        if "X_diffmap" in adata.obsm:
            diffmap = adata.obsm["X_diffmap"]
            start_component = 1
        elif "DM_EigenVectors" in adata.obsm:
            diffmap = np.asarray(adata.obsm["DM_EigenVectors"])
            start_component = 0
        else:
            logger.warning("No diffusion embedding found in adata.obsm")
            return figures

        if diffmap.shape[1] < 2:
            logger.warning("Diffusion embedding has fewer than 2 components")
            return figures

        n_components = min(n_components, diffmap.shape[1] - start_component)
        if n_components < 2:
            return figures

        # Pairwise scatter plots
        fig, axes = plt.subplots(1, n_components - 1, figsize=(5 * (n_components - 1), 4))
        if n_components == 2:
            axes = [axes]

        for i in range(1, n_components):
            ax = axes[i - 1]
            x_idx = start_component
            y_idx = start_component + i
            ax.scatter(diffmap[:, x_idx], diffmap[:, y_idx], s=1, alpha=0.5)
            ax.set_xlabel(f"DC{x_idx + 1}")
            ax.set_ylabel(f"DC{y_idx + 1}")
            ax.set_title(f"Diffusion Components {x_idx + 1} vs {y_idx + 1}")

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
