"""
Run single-cell trajectory inference analysis.

Three-level analysis with graceful degradation:
  Level 1 (scanpy): PAGA + diffusion pseudotime + diffusion map (always available)
  Level 2 (scVelo): RNA velocity, latent time (if scvelo installed + velocity layers)
  Level 3 (CellRank): Fate probabilities, driver genes (if cellrank installed)

Usage:
  from scripts.run_trajectory_analysis import run_trajectory
  results = run_trajectory(adata, root_cell_type="Ductal")
"""

import warnings
import numpy as np
import pandas as pd


def run_trajectory(
    adata,
    root_cell_type="Ductal",
    cluster_key="clusters",
    n_neighbors=30,
    n_pcs=30,
    n_dcs=10,
    run_velocity=True,
    run_cellrank=True,
):
    """
    Run complete trajectory inference pipeline.

    Parameters
    ----------
    adata : AnnData
        Preprocessed scRNA-seq data with clusters and UMAP.
    root_cell_type : str
        Cell type to use as trajectory root (earliest in differentiation).
    cluster_key : str
        Column in adata.obs with cluster/cell type labels.
    n_neighbors : int
        Number of neighbors for graph construction.
    n_pcs : int
        Number of PCs for neighbor computation.
    n_dcs : int
        Number of diffusion components.
    run_velocity : bool
        Whether to attempt RNA velocity (requires scVelo + spliced/unspliced layers).
    run_cellrank : bool
        Whether to attempt CellRank fate mapping (requires cellrank).

    Returns
    -------
    results : dict
        Dictionary with keys:
        - 'pseudotime': pd.Series of pseudotime values per cell
        - 'root_cell': str, barcode of selected root cell
        - 'paga_connectivities': connectivity matrix between clusters
        - 'diffmap': diffusion map coordinates
        - 'trajectory_genes': pd.DataFrame of pseudotime-correlated genes
        - 'velocity_results': dict (if scVelo ran) or None
        - 'cellrank_results': dict (if CellRank ran) or None
        - 'parameters': dict of analysis parameters
    """
    import scanpy as sc

    results = {
        "velocity_results": None,
        "cellrank_results": None,
        "parameters": {
            "root_cell_type": root_cell_type,
            "cluster_key": cluster_key,
            "n_neighbors": n_neighbors,
            "n_pcs": n_pcs,
            "n_dcs": n_dcs,
        },
    }

    # =========================================================================
    # Level 1: Core trajectory (scanpy — always available)
    # =========================================================================
    print("=" * 60)
    print("LEVEL 1: Core Trajectory Analysis (scanpy)")
    print("=" * 60)

    # 1a. Preprocessing for trajectory
    print("\n  Computing neighbors...")
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs)

    # 1b. PAGA (partition-based graph abstraction)
    print("  Running PAGA...")
    sc.tl.paga(adata, groups=cluster_key)
    results["paga_connectivities"] = adata.uns["paga"]["connectivities"].toarray()

    # 1c. Recompute UMAP with PAGA initialization for trajectory-aware layout
    print("  Computing PAGA-initialized UMAP...")
    sc.pl.paga(adata, plot=False)
    sc.tl.umap(adata, init_pos="paga")

    # 1d. Diffusion map for pseudotime
    print("  Computing diffusion map...")
    sc.tl.diffmap(adata, n_comps=n_dcs)
    results["diffmap"] = adata.obsm["X_diffmap"]

    # 1e. Select root cell
    root_cell, root_idx = _select_root_cell(adata, root_cell_type, cluster_key)
    adata.uns["iroot"] = root_idx
    results["root_cell"] = root_cell
    print(f"  Root cell: {root_cell} (type: {root_cell_type})")

    # 1f. Diffusion pseudotime
    print("  Computing diffusion pseudotime...")
    sc.tl.dpt(adata)
    results["pseudotime"] = adata.obs["dpt_pseudotime"].copy()
    _valid_pt = results["pseudotime"][~np.isinf(results["pseudotime"])]
    print(f"  Pseudotime range: [{_valid_pt.min():.3f}, {_valid_pt.max():.3f}]")

    # 1g. Identify trajectory-associated genes
    print("  Identifying trajectory-associated genes...")
    trajectory_genes = _find_trajectory_genes(adata, cluster_key=cluster_key)
    results["trajectory_genes"] = trajectory_genes
    print(f"  Found {len(trajectory_genes)} trajectory-associated genes")

    print("\n✓ Core trajectory analysis complete")

    # =========================================================================
    # Level 2: RNA velocity (scVelo — optional)
    # =========================================================================
    has_velocity_layers = (
        "spliced" in adata.layers and "unspliced" in adata.layers
    )

    if run_velocity and has_velocity_layers:
        print("\n" + "=" * 60)
        print("LEVEL 2: RNA Velocity Analysis (scVelo)")
        print("=" * 60)
        try:
            velocity_results = _run_rna_velocity(adata)
            results["velocity_results"] = velocity_results
            print("\n✓ RNA velocity analysis complete")
        except ImportError:
            print("\n  scVelo not installed — skipping RNA velocity")
            print("  Install with: pip install scvelo")
        except Exception as e:
            print(f"\n  RNA velocity failed: {e}")
            print("  Continuing with core trajectory results")
    elif run_velocity and not has_velocity_layers:
        print("\n  No spliced/unspliced layers — skipping RNA velocity")
    else:
        print("\n  RNA velocity skipped (run_velocity=False)")

    # =========================================================================
    # Level 3: CellRank fate mapping (optional)
    # =========================================================================
    if run_cellrank:
        print("\n" + "=" * 60)
        print("LEVEL 3: CellRank Fate Mapping")
        print("=" * 60)
        try:
            cellrank_results = _run_cellrank(
                adata,
                cluster_key=cluster_key,
                has_velocity=results["velocity_results"] is not None,
            )
            results["cellrank_results"] = cellrank_results
            print("\n✓ CellRank fate mapping complete")
        except ImportError:
            print("\n  CellRank not installed — skipping fate mapping")
            print("  Install with: pip install cellrank")
        except Exception as e:
            print(f"\n  CellRank failed: {e}")
            print("  Continuing with available results")
    else:
        print("\n  CellRank skipped (run_cellrank=False)")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 60)
    print("TRAJECTORY ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"  Cells analyzed: {adata.n_obs:,}")
    print(f"  Root cell type: {root_cell_type}")
    _vpt = results["pseudotime"][~np.isinf(results["pseudotime"])]
    print(f"  Pseudotime range: [{_vpt.min():.3f}, {_vpt.max():.3f}]")
    print(f"  PAGA clusters: {len(adata.obs[cluster_key].unique())}")
    print(f"  Trajectory genes: {len(results['trajectory_genes'])}")
    print(f"  RNA velocity: {'✓' if results['velocity_results'] else '✗'}")
    print(f"  CellRank fates: {'✓' if results['cellrank_results'] else '✗'}")

    print("\n✓ Trajectory analysis completed successfully!")

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _select_root_cell(adata, root_cell_type, cluster_key):
    """
    Select a root cell from the specified cell type.

    Picks the cell with the lowest diffusion component 1 value
    within the root cell type cluster (typically the most 'stem-like').

    Returns
    -------
    root_cell : str
        Cell barcode.
    root_idx : int
        Integer index into adata.obs.
    """
    mask = adata.obs[cluster_key] == root_cell_type
    if mask.sum() == 0:
        available = adata.obs[cluster_key].unique().tolist()
        raise ValueError(
            f"Root cell type '{root_cell_type}' not found. "
            f"Available: {available}"
        )

    # Use diffusion component 1 to pick the most primitive cell
    if "X_diffmap" in adata.obsm:
        dc1 = adata.obsm["X_diffmap"][:, 0]
        # Among root cells, pick the one with extreme DC1 value
        root_cells_idx = np.where(mask)[0]
        dc1_root = dc1[root_cells_idx]
        # Pick the cell at the extreme end (min or max, whichever is more separated)
        if abs(dc1_root.min()) > abs(dc1_root.max()):
            best = root_cells_idx[np.argmin(dc1_root)]
        else:
            best = root_cells_idx[np.argmax(dc1_root)]
    else:
        # Fallback: random cell from root type
        best = np.where(mask)[0][0]

    return adata.obs_names[best], best


def _find_trajectory_genes(adata, cluster_key="clusters", n_top=200):
    """
    Identify genes whose expression correlates with pseudotime.

    Uses Spearman rank correlation between gene expression and
    diffusion pseudotime. Returns top genes ranked by absolute
    correlation with FDR correction.

    Returns
    -------
    pd.DataFrame
        Columns: gene, correlation, pvalue, fdr, direction
    """
    from scipy import stats

    pseudotime = adata.obs["dpt_pseudotime"].values
    valid = ~np.isinf(pseudotime) & ~np.isnan(pseudotime)

    if valid.sum() < 50:
        print("  Warning: Too few cells with valid pseudotime for gene correlation")
        return pd.DataFrame(columns=["gene", "correlation", "pvalue", "fdr", "direction"])

    # Get expression matrix (dense)
    X = adata.X[valid]
    if hasattr(X, "toarray"):
        X = X.toarray()

    pt = pseudotime[valid]

    # Vectorized Spearman correlation: rank-based Pearson for speed
    # Rank pseudotime once
    pt_ranks = stats.rankdata(pt)
    n_cells = len(pt_ranks)

    # Rank all genes at once (column-wise, truly vectorized in scipy >= 1.7)
    X_ranks = stats.rankdata(X, axis=0)

    # Pearson correlation on ranks = Spearman correlation
    pt_centered = pt_ranks - pt_ranks.mean()
    X_centered = X_ranks - X_ranks.mean(axis=0, keepdims=True)

    pt_std = np.sqrt(np.sum(pt_centered ** 2))
    X_std = np.sqrt(np.sum(X_centered ** 2, axis=0))

    # Handle zero-variance genes
    zero_var = X_std < 1e-10
    X_std[zero_var] = 1.0  # Avoid division by zero

    correlations = X_centered.T @ pt_centered / (X_std * pt_std)
    correlations[zero_var] = 0.0
    correlations = np.nan_to_num(correlations, nan=0.0)

    # Compute p-values from correlation using t-distribution
    t_stat = correlations * np.sqrt((n_cells - 2) / (1 - correlations ** 2 + 1e-15))
    pvalues = 2 * stats.t.sf(np.abs(t_stat), df=n_cells - 2)
    pvalues[zero_var] = 1.0
    pvalues = np.nan_to_num(pvalues, nan=1.0)

    # FDR correction (Benjamini-Hochberg)
    from statsmodels.stats.multitest import multipletests

    _, fdr, _, _ = multipletests(pvalues, method="fdr_bh")

    # Build result DataFrame
    gene_names = adata.var_names.tolist()
    df = pd.DataFrame({
        "gene": gene_names,
        "correlation": correlations,
        "pvalue": pvalues,
        "fdr": fdr,
        "direction": ["up" if c > 0 else "down" for c in correlations],
    })

    # Filter and sort
    df = df[df["fdr"] < 0.05].copy()
    df["abs_correlation"] = df["correlation"].abs()
    df = df.sort_values("abs_correlation", ascending=False).head(n_top)
    df = df.drop(columns=["abs_correlation"])

    return df.reset_index(drop=True)


def _run_rna_velocity(adata):
    """
    Run scVelo RNA velocity analysis.

    Uses the dynamical model for most accurate velocity estimates.
    Falls back to stochastic model if dynamical fitting fails.

    Returns
    -------
    dict with keys:
        'model': str ('dynamical' or 'stochastic')
        'velocity_genes': pd.DataFrame of top velocity genes
        'has_latent_time': bool
    """
    import scvelo as scv

    print("  Filtering and normalizing velocity data...")
    scv.pp.filter_and_normalize(adata, min_shared_counts=20)

    print("  Computing moments...")
    scv.pp.moments(adata, n_pcs=30, n_neighbors=30)

    # Try dynamical model first, fall back to stochastic
    model_type = "dynamical"
    try:
        print("  Recovering dynamics (dynamical model)...")
        scv.tl.recover_dynamics(adata, n_jobs=1)
        print("  Computing velocity (dynamical)...")
        scv.tl.velocity(adata, mode="dynamical")
    except Exception as e:
        print(f"  Dynamical model failed ({e}), falling back to stochastic...")
        model_type = "stochastic"
        scv.tl.velocity(adata, mode="stochastic")

    print("  Computing velocity graph...")
    scv.tl.velocity_graph(adata)

    # Latent time (only for dynamical model)
    has_latent_time = False
    if model_type == "dynamical":
        try:
            print("  Computing latent time...")
            scv.tl.latent_time(adata)
            has_latent_time = True
        except Exception:
            print("  Latent time computation failed — skipping")

    # Velocity confidence
    try:
        scv.tl.velocity_confidence(adata)
    except Exception:
        pass

    # Top velocity genes
    velocity_genes = _get_top_velocity_genes(adata)

    return {
        "model": model_type,
        "velocity_genes": velocity_genes,
        "has_latent_time": has_latent_time,
    }


def _get_top_velocity_genes(adata, n_top=50):
    """Extract top velocity genes with fit statistics."""
    if "velocity_genes" not in adata.var.columns:
        return pd.DataFrame(columns=["gene", "fit_likelihood", "velocity_score"])

    vel_genes = adata.var[adata.var["velocity_genes"]].copy()

    score_cols = ["fit_likelihood"]
    for col in score_cols:
        if col not in vel_genes.columns:
            vel_genes[col] = np.nan

    vel_genes = vel_genes.sort_values("fit_likelihood", ascending=False).head(n_top)

    df = pd.DataFrame({
        "gene": vel_genes.index,
        "fit_likelihood": vel_genes["fit_likelihood"].values,
    })
    return df.reset_index(drop=True)


def _run_cellrank(adata, cluster_key="clusters", has_velocity=False):
    """
    Run CellRank fate probability analysis.

    Uses VelocityKernel if RNA velocity is available, otherwise
    falls back to PseudotimeKernel with diffusion pseudotime.

    Returns
    -------
    dict with keys:
        'terminal_states': list of terminal cell types
        'fate_probabilities': pd.DataFrame (cells x terminal states)
        'driver_genes': dict of {terminal_state: pd.DataFrame}
        'kernel_type': str
    """
    import cellrank as cr

    # Choose kernel based on available data
    if has_velocity and "velocity" in adata.layers:
        print("  Using VelocityKernel...")
        kernel_type = "velocity"
        vk = cr.kernels.VelocityKernel(adata)
        vk.compute_transition_matrix()

        ck = cr.kernels.ConnectivityKernel(adata)
        ck.compute_transition_matrix()

        combined_kernel = 0.8 * vk + 0.2 * ck
    else:
        print("  Using PseudotimeKernel (no velocity)...")
        kernel_type = "pseudotime"
        pk = cr.kernels.PseudotimeKernel(adata, time_key="dpt_pseudotime")
        pk.compute_transition_matrix(threshold_scheme="soft")

        ck = cr.kernels.ConnectivityKernel(adata)
        ck.compute_transition_matrix()

        combined_kernel = 0.8 * pk + 0.2 * ck

    # Estimate terminal states
    print("  Estimating terminal states...")
    estimator = cr.estimators.GPCCA(combined_kernel)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        estimator.fit(cluster_key=cluster_key)
        estimator.predict_terminal_states()

    terminal_states = list(estimator.terminal_states.cat.categories)
    print(f"  Terminal states: {terminal_states}")

    # Compute fate probabilities
    print("  Computing fate probabilities...")
    estimator.compute_fate_probabilities()
    fate_probs = estimator.fate_probabilities

    # Convert to DataFrame
    fate_df = pd.DataFrame(
        fate_probs.values if hasattr(fate_probs, 'values') else np.array(fate_probs),
        index=adata.obs_names,
        columns=terminal_states,
    )

    # Identify driver genes per terminal state
    print("  Identifying driver genes...")
    driver_genes = {}
    for state in terminal_states:
        try:
            drivers = estimator.compute_lineage_drivers(
                lineages=[state], return_drivers=True
            )
            if drivers is not None and len(drivers) > 0:
                top = drivers.head(30)
                driver_genes[state] = top.reset_index()
        except Exception:
            driver_genes[state] = pd.DataFrame()

    return {
        "terminal_states": terminal_states,
        "fate_probabilities": fate_df,
        "driver_genes": driver_genes,
        "kernel_type": kernel_type,
    }

