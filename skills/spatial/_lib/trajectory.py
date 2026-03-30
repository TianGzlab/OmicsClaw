"""Spatial trajectory analysis functions.

Supports three trajectory backends:

- **DPT**: Scanpy diffusion pseudotime on a precomputed neighborhood graph.
- **CellRank**: macrostate / fate inference using a CellRank kernel stack.
- **Palantir**: diffusion-based pseudotime and branch-entropy estimation.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .adata_utils import ensure_neighbors, ensure_pca
from .dependency_manager import require

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = ("dpt", "cellrank", "palantir")

_CLUSTER_KEY_CANDIDATES = (
    "leiden",
    "cell_type",
    "celltype",
    "annotation",
    "cluster",
    "clusters",
)

METHOD_PARAM_DEFAULTS = {
    "dpt": {
        "n_dcs": 10,
    },
    "cellrank": {
        "n_states": 3,
        "schur_components": 20,
        "frac_to_keep": 0.3,
        "use_velocity": False,
    },
    "palantir": {
        "n_components": 10,
        "knn": 30,
        "num_waypoints": 1200,
        "max_iterations": 25,
    },
}


def _prefixed_params(prefix: str, **values) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        result[f"{prefix}_{key}"] = value
    return result


def detect_cluster_key(adata) -> str | None:
    """Auto-detect a cluster / annotation column for trajectory summaries."""
    for key in _CLUSTER_KEY_CANDIDATES:
        if key in adata.obs.columns and adata.obs[key].nunique() >= 2:
            return key
    return None


def _ensure_diffmap(adata, *, min_components: int) -> int:
    """Ensure diffusion map exists with enough components."""
    import scanpy as sc

    ensure_pca(adata)
    ensure_neighbors(adata)

    max_components = max(2, min(adata.obsm["X_pca"].shape[1], adata.n_obs - 1))
    n_components = min(max(min_components, 2), max_components)
    sc.tl.diffmap(adata, n_comps=n_components)
    return n_components


def _resolve_root_cell(
    adata,
    *,
    root_cell: str | None,
    root_cell_type: str | None,
    cluster_key: str | None,
) -> tuple[str, int]:
    """Resolve the root / early cell after diffusion components are available."""
    obs_names = adata.obs_names.astype(str)

    if root_cell is not None:
        root_cell = str(root_cell)
        matches = np.where(obs_names == root_cell)[0]
        if len(matches) == 0:
            raise ValueError(f"Root cell '{root_cell}' not found in adata.obs_names")
        root_idx = int(matches[0])
        logger.info("Using provided root cell: %s", root_cell)
        return root_cell, root_idx

    dc1 = np.asarray(adata.obsm["X_diffmap"][:, 0], dtype=float)

    if root_cell_type is not None:
        if cluster_key is None or cluster_key not in adata.obs.columns:
            raise ValueError(
                "root_cell_type requires a valid cluster_key / annotation column."
            )
        labels = adata.obs[cluster_key].astype(str).values
        mask = labels == str(root_cell_type)
        if not np.any(mask):
            raise ValueError(
                f"Root cell type '{root_cell_type}' not found in '{cluster_key}'."
            )
        candidates = np.where(mask)[0]
        root_idx = int(candidates[np.argmax(dc1[candidates])])
        root_name = str(obs_names[root_idx])
        logger.info(
            "Auto-selected root cell %s from '%s=%s' using max DC1",
            root_name,
            cluster_key,
            root_cell_type,
        )
        return root_name, root_idx

    root_idx = int(np.argmax(dc1))
    root_name = str(obs_names[root_idx])
    logger.info("Auto-selected root cell: %s (max DC1)", root_name)
    return root_name, root_idx


def _summarize_pseudotime(
    adata,
    *,
    pseudotime_key: str,
    cluster_key: str | None,
) -> dict[str, Any]:
    """Summarize scalar pseudotime values globally and per cluster."""
    pseudotime = np.asarray(adata.obs[pseudotime_key], dtype=float)
    finite_mask = np.isfinite(pseudotime)

    per_cluster: dict[str, dict[str, Any]] = {}
    if cluster_key and cluster_key in adata.obs.columns:
        labels = adata.obs[cluster_key].astype(str)
        for label in sorted(labels.unique().tolist(), key=str):
            mask = (labels == str(label)).values & finite_mask
            if np.sum(mask) == 0:
                continue
            values = pseudotime[mask]
            per_cluster[str(label)] = {
                "mean_pseudotime": float(values.mean()),
                "median_pseudotime": float(np.median(values)),
                "n_cells": int(np.sum(mask)),
            }

    return {
        "pseudotime_key": pseudotime_key,
        "mean_pseudotime": float(pseudotime[finite_mask].mean()) if np.any(finite_mask) else 0.0,
        "max_pseudotime": float(pseudotime[finite_mask].max()) if np.any(finite_mask) else 0.0,
        "n_finite": int(np.sum(finite_mask)),
        "per_cluster": per_cluster,
    }


def find_trajectory_genes(
    adata,
    *,
    pseudotime_key: str = "dpt_pseudotime",
    n_top: int = 200,
    fdr_threshold: float = 0.05,
) -> pd.DataFrame:
    """Find genes correlated with pseudotime using Spearman rank correlation."""
    if pseudotime_key not in adata.obs.columns:
        logger.warning("No pseudotime found in '%s'; cannot compute trajectory genes", pseudotime_key)
        return pd.DataFrame()

    from scipy import sparse, stats

    pseudotime = np.asarray(adata.obs[pseudotime_key], dtype=float)
    finite_mask = np.isfinite(pseudotime)
    if finite_mask.sum() < 10:
        logger.warning("Too few cells with finite pseudotime (%d)", finite_mask.sum())
        return pd.DataFrame()

    pt = pseudotime[finite_mask]
    X = adata.X[finite_mask]
    if sparse.issparse(X):
        X = X.toarray()
    X = np.asarray(X)

    n_genes = X.shape[1]
    correlations = np.zeros(n_genes, dtype=float)
    pvalues = np.ones(n_genes, dtype=float)

    for idx in range(n_genes):
        expr = X[:, idx]
        if np.std(expr) < 1e-10:
            continue
        rho, pval = stats.spearmanr(pt, expr)
        correlations[idx] = float(rho)
        pvalues[idx] = float(pval)

    try:
        from statsmodels.stats.multitest import multipletests

        _, fdr_vals, _, _ = multipletests(pvalues, method="fdr_bh")
    except ImportError:
        n = len(pvalues)
        order = np.argsort(pvalues)
        ranked = np.empty(n, dtype=float)
        cumulative = 1.0
        for rank, idx in enumerate(order[::-1], start=1):
            p = pvalues[idx]
            cumulative = min(cumulative, p * n / (n - rank + 1))
            ranked[idx] = cumulative
        fdr_vals = np.clip(ranked, 0, 1)

    results = pd.DataFrame(
        {
            "gene": adata.var_names,
            "correlation": correlations,
            "pvalue": pvalues,
            "fdr": fdr_vals,
            "direction": np.where(correlations > 0, "increasing", "decreasing"),
        }
    )
    results = results[results["fdr"] < fdr_threshold]
    results = results.sort_values("correlation", key=np.abs, ascending=False)
    results = results.head(n_top).reset_index(drop=True)

    logger.info(
        "Found %d trajectory-correlated genes from '%s' (FDR < %.2f)",
        len(results),
        pseudotime_key,
        fdr_threshold,
    )
    return results


def _trajectory_gene_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Convert trajectory-gene dataframe into compact summary fields."""
    if df.empty:
        return {"n_trajectory_genes": 0}

    increasing = df[df["direction"] == "increasing"].head(5)["gene"].tolist()
    decreasing = df[df["direction"] == "decreasing"].head(5)["gene"].tolist()
    return {
        "trajectory_genes": df,
        "n_trajectory_genes": int(len(df)),
        "top_increasing": increasing,
        "top_decreasing": decreasing,
    }


def _compute_dpt_pseudotime(
    adata,
    *,
    root_cell: str | None,
    root_cell_type: str | None,
    cluster_key: str | None,
    n_dcs: int,
) -> dict[str, Any]:
    """Compute DPT pseudotime and return core scalar summaries."""
    import scanpy as sc

    _ensure_diffmap(adata, min_components=n_dcs + 1)
    resolved_root_cell, root_idx = _resolve_root_cell(
        adata,
        root_cell=root_cell,
        root_cell_type=root_cell_type,
        cluster_key=cluster_key,
    )
    adata.uns["iroot"] = root_idx

    effective_n_dcs = min(max(int(n_dcs), 2), adata.obsm["X_diffmap"].shape[1])
    sc.tl.dpt(adata, n_dcs=effective_n_dcs)

    summary = _summarize_pseudotime(
        adata,
        pseudotime_key="dpt_pseudotime",
        cluster_key=cluster_key,
    )
    summary.update(
        {
            "root_cell": resolved_root_cell,
            "root_cell_type": root_cell_type,
            "effective_n_dcs": effective_n_dcs,
        }
    )
    return summary


def run_dpt(
    adata,
    *,
    root_cell: str | None = None,
    root_cell_type: str | None = None,
    cluster_key: str | None = None,
    n_dcs: int = METHOD_PARAM_DEFAULTS["dpt"]["n_dcs"],
) -> dict[str, Any]:
    """Run diffusion pseudotime using scanpy."""
    dpt_summary = _compute_dpt_pseudotime(
        adata,
        root_cell=root_cell,
        root_cell_type=root_cell_type,
        cluster_key=cluster_key,
        n_dcs=n_dcs,
    )
    traj_genes_df = find_trajectory_genes(adata, pseudotime_key="dpt_pseudotime")

    return {
        "method": "dpt",
        "cluster_key": cluster_key,
        **dpt_summary,
        **_trajectory_gene_summary(traj_genes_df),
        "effective_params": {
            "cluster_key": cluster_key,
            "root_cell": dpt_summary["root_cell"],
            "root_cell_type": root_cell_type,
            **_prefixed_params("dpt", n_dcs=dpt_summary["effective_n_dcs"]),
        },
    }


def run_cellrank(
    adata,
    *,
    root_cell: str | None = None,
    root_cell_type: str | None = None,
    cluster_key: str | None = None,
    dpt_n_dcs: int = METHOD_PARAM_DEFAULTS["dpt"]["n_dcs"],
    n_states: int = METHOD_PARAM_DEFAULTS["cellrank"]["n_states"],
    schur_components: int = METHOD_PARAM_DEFAULTS["cellrank"]["schur_components"],
    frac_to_keep: float = METHOD_PARAM_DEFAULTS["cellrank"]["frac_to_keep"],
    use_velocity: bool = METHOD_PARAM_DEFAULTS["cellrank"]["use_velocity"],
) -> dict[str, Any]:
    """Run CellRank macrostate / fate inference."""
    require("cellrank", feature="CellRank trajectory inference")
    import cellrank as cr

    dpt_summary = _compute_dpt_pseudotime(
        adata,
        root_cell=root_cell,
        root_cell_type=root_cell_type,
        cluster_key=cluster_key,
        n_dcs=dpt_n_dcs,
    )

    kernel_mode = "connectivity"
    effective_frac_to_keep = float(frac_to_keep)
    effective_schur_components = min(max(int(schur_components), 2), max(2, adata.n_obs - 1))
    effective_n_states = min(max(int(n_states), 2), effective_schur_components)

    try:
        ck = cr.kernels.ConnectivityKernel(adata).compute_transition_matrix()
    except Exception as exc:
        raise RuntimeError(
            "CellRank could not build a valid ConnectivityKernel from the current neighbor graph. "
            "Inspect graph connectivity or rerun spatial-preprocess before retrying CellRank."
        ) from exc
    kernel = ck

    if use_velocity:
        try:
            vk = cr.kernels.VelocityKernel(adata).compute_transition_matrix()
            kernel = 0.8 * vk + 0.2 * ck
            kernel_mode = "velocity+connectivity"
            logger.info("CellRank: using VelocityKernel(0.8) + ConnectivityKernel(0.2)")
        except Exception as exc:
            logger.warning(
                "VelocityKernel unavailable (%s); falling back to pseudotime / connectivity",
                exc,
            )

    if kernel_mode == "connectivity":
        try:
            pk = cr.kernels.PseudotimeKernel(
                adata,
                time_key="dpt_pseudotime",
            ).compute_transition_matrix(
                frac_to_keep=effective_frac_to_keep,
                n_jobs=1,
                backend="threading",
                show_progress_bar=False,
            )
            kernel = 0.8 * pk + 0.2 * ck
            kernel_mode = "pseudotime+connectivity"
            logger.info(
                "CellRank: using PseudotimeKernel(0.8) + ConnectivityKernel(0.2)"
            )
        except Exception as exc:
            logger.warning(
                "PseudotimeKernel unavailable (%s); using ConnectivityKernel only",
                exc,
            )

    macro_cluster_key = cluster_key if cluster_key and cluster_key in adata.obs.columns else None
    if macro_cluster_key and not pd.api.types.is_categorical_dtype(adata.obs[macro_cluster_key]):
        adata.obs[macro_cluster_key] = adata.obs[macro_cluster_key].astype("category")

    estimator = cr.estimators.GPCCA(kernel)
    estimator.compute_schur(n_components=effective_schur_components)
    estimator.compute_macrostates(
        n_states=effective_n_states,
        cluster_key=macro_cluster_key,
    )

    macro_key = next(
        (key for key in ("macrostates_fwd", "macrostates", "term_states_fwd") if key in adata.obs.columns),
        None,
    )
    n_macrostates = int(adata.obs[macro_key].nunique()) if macro_key else 0

    terminal_states: list[str] = []
    lineage_key: str | None = None
    driver_genes: dict[str, list[str]] = {}

    try:
        estimator.predict_terminal_states()
        term_key = next(
            (key for key in ("terminal_states", "term_states_fwd") if key in adata.obs.columns),
            None,
        )
        if term_key:
            terminal_states = [str(x) for x in adata.obs[term_key].dropna().unique().tolist()]
        estimator.compute_fate_probabilities(
            n_jobs=1,
            backend="threading",
            show_progress_bar=False,
            use_petsc=False,
        )
        lineage_key = next(
            (key for key in ("lineages_fwd", "to_terminal_states") if key in adata.obsm),
            None,
        )
        for state in terminal_states[:5]:
            try:
                drivers = estimator.compute_lineage_drivers(lineages=state)
                if drivers is not None and not drivers.empty:
                    driver_genes[state] = drivers.head(10).index.astype(str).tolist()
            except Exception as exc:
                logger.warning("CellRank lineage drivers failed for '%s': %s", state, exc)
    except Exception as exc:
        logger.warning("CellRank terminal-state / fate computation failed: %s", exc)

    traj_genes_df = find_trajectory_genes(adata, pseudotime_key="dpt_pseudotime")

    return {
        "method": "cellrank",
        "cluster_key": cluster_key,
        **dpt_summary,
        **_trajectory_gene_summary(traj_genes_df),
        "kernel_mode": kernel_mode,
        "macrostate_key": macro_key,
        "lineage_key": lineage_key,
        "n_macrostates": n_macrostates,
        "terminal_states": terminal_states,
        "driver_genes": driver_genes,
        "effective_params": {
            "cluster_key": cluster_key,
            "root_cell": dpt_summary["root_cell"],
            "root_cell_type": root_cell_type,
            "dpt_n_dcs": dpt_summary["effective_n_dcs"],
            **_prefixed_params(
                "cellrank",
                use_velocity=use_velocity,
                n_states=effective_n_states,
                schur_components=effective_schur_components,
                frac_to_keep=effective_frac_to_keep,
            ),
        },
    }


def run_palantir(
    adata,
    *,
    root_cell: str | None = None,
    root_cell_type: str | None = None,
    cluster_key: str | None = None,
    n_components: int = METHOD_PARAM_DEFAULTS["palantir"]["n_components"],
    knn: int = METHOD_PARAM_DEFAULTS["palantir"]["knn"],
    num_waypoints: int = METHOD_PARAM_DEFAULTS["palantir"]["num_waypoints"],
    max_iterations: int = METHOD_PARAM_DEFAULTS["palantir"]["max_iterations"],
) -> dict[str, Any]:
    """Run Palantir pseudotime and branch-entropy inference."""
    require("palantir", feature="Palantir trajectory inference")
    import scanpy.external as sce

    ensure_pca(adata)
    ensure_neighbors(adata)
    _ensure_diffmap(adata, min_components=max(n_components, 2))

    resolved_root_cell, _ = _resolve_root_cell(
        adata,
        root_cell=root_cell,
        root_cell_type=root_cell_type,
        cluster_key=cluster_key,
    )

    effective_n_components = min(
        max(int(n_components), 2),
        max(2, min(adata.obsm["X_pca"].shape[1], adata.n_obs - 1)),
    )
    effective_knn = min(max(int(knn), 2), max(2, adata.n_obs - 1))
    effective_num_waypoints = min(max(int(num_waypoints), 10), adata.n_obs)
    effective_max_iterations = max(int(max_iterations), 1)

    sce.tl.palantir(
        adata,
        n_components=effective_n_components,
        knn=effective_knn,
    )
    pr_res = sce.tl.palantir_results(
        adata,
        early_cell=resolved_root_cell,
        knn=effective_knn,
        num_waypoints=effective_num_waypoints,
        max_iterations=effective_max_iterations,
    )

    pseudotime = pr_res.pseudotime.reindex(adata.obs_names).astype(float)
    entropy = pr_res.entropy.reindex(adata.obs_names).astype(float)
    branch_probs = pr_res.branch_probs.reindex(adata.obs_names).fillna(0.0)
    waypoints = [str(x) for x in pr_res.waypoints.tolist()]

    adata.obs["palantir_pseudotime"] = pseudotime.values
    adata.obs["palantir_entropy"] = entropy.values
    adata.uns["palantir_waypoints"] = waypoints

    if not branch_probs.empty:
        adata.obsm["palantir_branch_probs"] = branch_probs.to_numpy(dtype=np.float32)
        adata.uns["palantir_branch_prob_columns"] = branch_probs.columns.astype(str).tolist()

    palantir_summary = _summarize_pseudotime(
        adata,
        pseudotime_key="palantir_pseudotime",
        cluster_key=cluster_key,
    )
    traj_genes_df = find_trajectory_genes(adata, pseudotime_key="palantir_pseudotime")

    terminal_states = branch_probs.columns.astype(str).tolist()

    return {
        "method": "palantir",
        "cluster_key": cluster_key,
        "root_cell": resolved_root_cell,
        "root_cell_type": root_cell_type,
        **palantir_summary,
        **_trajectory_gene_summary(traj_genes_df),
        "mean_entropy": float(entropy.mean()) if len(entropy) else 0.0,
        "terminal_states": terminal_states,
        "n_terminal_states": int(len(terminal_states)),
        "n_waypoints": int(len(waypoints)),
        "palantir_branch_probs": branch_probs,
        "effective_params": {
            "cluster_key": cluster_key,
            "root_cell": resolved_root_cell,
            "root_cell_type": root_cell_type,
            **_prefixed_params(
                "palantir",
                n_components=effective_n_components,
                knn=effective_knn,
                num_waypoints=effective_num_waypoints,
                max_iterations=effective_max_iterations,
            ),
        },
    }


def run_trajectory(
    adata,
    *,
    method: str = "dpt",
    root_cell: str | None = None,
    root_cell_type: str | None = None,
    cluster_key: str | None = None,
    dpt_n_dcs: int = METHOD_PARAM_DEFAULTS["dpt"]["n_dcs"],
    cellrank_n_states: int = METHOD_PARAM_DEFAULTS["cellrank"]["n_states"],
    cellrank_schur_components: int = METHOD_PARAM_DEFAULTS["cellrank"]["schur_components"],
    cellrank_frac_to_keep: float = METHOD_PARAM_DEFAULTS["cellrank"]["frac_to_keep"],
    cellrank_use_velocity: bool = METHOD_PARAM_DEFAULTS["cellrank"]["use_velocity"],
    palantir_n_components: int = METHOD_PARAM_DEFAULTS["palantir"]["n_components"],
    palantir_knn: int = METHOD_PARAM_DEFAULTS["palantir"]["knn"],
    palantir_num_waypoints: int = METHOD_PARAM_DEFAULTS["palantir"]["num_waypoints"],
    palantir_max_iterations: int = METHOD_PARAM_DEFAULTS["palantir"]["max_iterations"],
) -> dict[str, Any]:
    """Dispatch to the selected trajectory method."""
    n_cells = int(adata.n_obs)
    n_genes = int(adata.n_vars)
    logger.info("Input: %d cells x %d genes", n_cells, n_genes)

    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown trajectory method '{method}'. Choose from: {SUPPORTED_METHODS}")

    if method == "dpt":
        result = run_dpt(
            adata,
            root_cell=root_cell,
            root_cell_type=root_cell_type,
            cluster_key=cluster_key,
            n_dcs=dpt_n_dcs,
        )
    elif method == "cellrank":
        result = run_cellrank(
            adata,
            root_cell=root_cell,
            root_cell_type=root_cell_type,
            cluster_key=cluster_key,
            dpt_n_dcs=dpt_n_dcs,
            n_states=cellrank_n_states,
            schur_components=cellrank_schur_components,
            frac_to_keep=cellrank_frac_to_keep,
            use_velocity=cellrank_use_velocity,
        )
    else:
        result = run_palantir(
            adata,
            root_cell=root_cell,
            root_cell_type=root_cell_type,
            cluster_key=cluster_key,
            n_components=palantir_n_components,
            knn=palantir_knn,
            num_waypoints=palantir_num_waypoints,
            max_iterations=palantir_max_iterations,
        )

    return {"n_cells": n_cells, "n_genes": n_genes, **result}
