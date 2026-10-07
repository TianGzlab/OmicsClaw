"""Pseudotime methods on AnnData, without changing process JIT settings."""
from __future__ import annotations

import io
import json
import logging
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import scanpy as sc

from skills._sdk.r_dependency_manager import suggest_r_install
from skills._sdk.r_script_runner import RScriptRunner
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
from skills.singlecell._lib import trajectory as sc_traj
from skills.singlecell._lib.adata_utils import get_matrix_contract, infer_x_matrix_kind
from skills.singlecell._lib.export import save_h5ad

__all__ = ["pseudotime", "run_info", "trajectory_genes", "pseudotime_table",
           "fate_probability_table", "trajectory_curves", "pseudotime_figure"]
logger = logging.getLogger(__name__)
R_SCRIPTS_DIR = _SDK_R_SCRIPTS_DIR
_RUN_KEY = "omicsclaw_sc_pseudotime_run"
_CURVES_KEY = "omicsclaw_sc_pseudotime_curves"


def pseudotime(adata, *, method: str = "dpt", cluster_key: str = "leiden",
               use_rep: str | None = None, root_cluster: str | None = None,
               root_cell: str | int | None = None, end_clusters: list[str] | None = None,
               n_neighbors: int = 15, n_pcs: int = 50, n_dcs: int = 10,
               palantir_knn: int = 30, palantir_n_components: int = 10,
               palantir_num_waypoints: int = 1200, palantir_max_iterations: int = 25,
               palantir_seed: int | None = None, via_knn: int = 30, via_seed: int | None = None,
               cellrank_n_states: int = 3, cellrank_schur_components: int = 20,
               cellrank_frac_to_keep: float = 0.3, cellrank_use_velocity: bool = False,
               random_state: int = 20):
    """Return a copy with pseudotime and backend diagnostics.

    The default representation prefers X_pca; UMAP remains the preferred
    display embedding, not the default inference graph. This function does
    not disable numba JIT. Roots express an analysis assumption, not a
    direction inferred from the pseudotime values.

    :param method: dpt, palantir, via, cellrank, slingshot_r or monocle3_r.
    :param cluster_key: Existing obs grouping column; default leiden.
    :param use_rep: Existing obsm representation; None prefers X_pca.
    :param root_cluster: Optional root group for the selected backend.
    :param root_cell: Optional obs name or integer position.
    :param end_clusters: Optional Slingshot terminal groups.
    :param n_neighbors: DPT/CellRank neighbors; default 15.
    :param n_pcs: PCs for those neighbors; default 50.
    :param n_dcs: Diffusion components used for DPT; default 10.
    :param palantir_knn: Palantir neighbors, default 30.
    :param palantir_n_components: Palantir diffusion components, default 10.
    :param palantir_num_waypoints: Palantir waypoints, default 1200.
    :param palantir_max_iterations: Palantir iterations, default 25.
    :param palantir_seed: Overrides random_state for Palantir; default None.
    :param via_knn: VIA neighbors, default 30.
    :param via_seed: Overrides random_state for VIA; default None.
    :param cellrank_n_states: CellRank states, default 3.
    :param cellrank_schur_components: CellRank Schur components, default 20.
    :param cellrank_frac_to_keep: CellRank state-cell fraction, default 0.3.
    :param cellrank_use_velocity: Couple CellRank to existing velocity; default False.
    :param random_state: Palantir/VIA seed, default 20. DPT retains Scanpy's
        deterministic defaults; R wrappers do not expose a seed.
    :returns: New AnnData with obs['pseudotime']; run_info names the backend
        and original pseudotime column. R curves remain available separately.
    :raises ValueError: The method, grouping, expression contract or embedding is invalid.
    :raises ImportError: An optional backend is missing.
    """
    if method not in {"dpt", "palantir", "via", "cellrank", "slingshot_r", "monocle3_r"}:
        raise ValueError(f"Unsupported pseudotime method: {method}")
    if cluster_key not in adata.obs:
        raise ValueError(f"{cluster_key!r} is missing from obs")
    if min(n_neighbors, n_pcs, n_dcs) < 1:
        raise ValueError("neighbor and component counts must be positive")
    x_kind = get_matrix_contract(adata).get("X") or infer_x_matrix_kind(adata)
    if x_kind != "normalized_expression":
        raise ValueError("sc-pseudotime expects normalized expression")
    if method == "via":
        _prepare_via_runtime()
    use_rep = _resolve_use_rep(adata, use_rep)
    display_embedding = _resolve_display_embedding(adata, use_rep)
    root_cell_idx = _resolve_root_cell(adata, root_cell)
    working = adata.copy()
    curves_df = pd.DataFrame()
    method_summary: dict[str, object]
    if method == "dpt":
        logger.info("Starting DPT workflow...")
        working, method_summary = _run_dpt(
            working,
            use_rep=use_rep,
            cluster_key=cluster_key,
            root_cluster=root_cluster,
            root_cell_idx=root_cell_idx,
            n_neighbors=n_neighbors,
            n_pcs=n_pcs,
            n_dcs=n_dcs,
        )
    elif method == "palantir":
        logger.info("Starting Palantir workflow...")
        working, method_summary = _run_palantir(
            working,
            use_rep=use_rep,
            cluster_key=cluster_key,
            root_cluster=root_cluster,
            root_cell_idx=root_cell_idx,
            palantir_knn=palantir_knn,
            palantir_n_components=palantir_n_components,
            palantir_num_waypoints=palantir_num_waypoints,
            palantir_max_iterations=palantir_max_iterations,
            palantir_seed=random_state if palantir_seed is None else palantir_seed,
        )
    elif method == "via":
        logger.info("Starting VIA workflow...")
        working, method_summary = _run_via(
            working,
            use_rep=use_rep,
            cluster_key=cluster_key,
            root_cluster=root_cluster,
            root_cell_idx=root_cell_idx,
            via_knn=via_knn,
            via_seed=random_state if via_seed is None else via_seed,
            n_dcs=n_dcs,
        )
    elif method == "cellrank":
        logger.info("Starting CellRank workflow...")
        working, method_summary = _run_cellrank(
            working,
            use_rep=use_rep,
            cluster_key=cluster_key,
            root_cluster=root_cluster,
            root_cell_idx=root_cell_idx,
            n_neighbors=n_neighbors,
            n_pcs=n_pcs,
            n_dcs=n_dcs,
            cellrank_n_states=cellrank_n_states,
            cellrank_schur_components=cellrank_schur_components,
            cellrank_frac_to_keep=cellrank_frac_to_keep,
            cellrank_use_velocity=bool(cellrank_use_velocity),
        )
    elif method == "monocle3_r":
        logger.info("Starting Monocle3 R workflow...")
        working, method_summary, curves_df = _run_monocle3_r(
            working,
            use_rep=use_rep,
            cluster_key=cluster_key,
            root_cluster=root_cluster,
        )
    else:
        logger.info("Starting Slingshot R workflow...")
        working, method_summary, curves_df = _run_slingshot_r(
            working,
            use_rep=use_rep,
            cluster_key=cluster_key,
            root_cluster=root_cluster,
            end_clusters=end_clusters,
        )

    pseudotime_key = str(method_summary["pseudotime_key"])
    working.obs["pseudotime"] = pd.to_numeric(working.obs[pseudotime_key], errors="coerce")
    working.uns["omicsclaw_pseudotime"] = {
        "method": method,
        "pseudotime_key": pseudotime_key,
        "display_embedding": display_embedding,
        "use_rep": use_rep,
        "cluster_key": cluster_key,
        "root_cluster": root_cluster,
        "root_cell": method_summary.get("root_cell"),
        "root_cell_name": method_summary.get("root_cell_name"),
    }


    info = {**method_summary, "method": method, "cluster_key": cluster_key, "use_rep": use_rep,
            "display_embedding": display_embedding, "root_cluster": root_cluster}
    working.uns[_RUN_KEY] = json.dumps(info)
    if not curves_df.empty:
        working.uns[_CURVES_KEY] = curves_df.to_json(orient="split")
    return working


def run_info(adata, *, keep: bool = True) -> dict:
    """Read method, root and representation diagnostics; keep=False removes the record."""
    value = adata.uns.get(_RUN_KEY, "{}") if keep else adata.uns.pop(_RUN_KEY, "{}")
    return json.loads(value)


def trajectory_genes(adata, *, n_genes: int = 50, method: str = "pearson") -> pd.DataFrame:
    """Rank genes by correlation with pseudotime; method is pearson or spearman."""
    if n_genes < 1 or method not in {"pearson", "spearman"}:
        raise ValueError("n_genes must be positive and method must be pearson or spearman")
    return sc_traj.find_trajectory_genes(adata, pseudotime_key=run_info(adata)["pseudotime_key"],
                                         n_genes=n_genes, method=method)


def pseudotime_table(adata) -> pd.DataFrame:
    """Return cell, display coordinates, group and pseudotime columns."""
    info = run_info(adata)
    return _build_pseudotime_points_table(adata, pseudotime_key=info["pseudotime_key"],
                                         cluster_key=info["cluster_key"], display_key=info["display_embedding"])


def fate_probability_table(adata) -> pd.DataFrame:
    """Return backend fate probabilities averaged by group, or an empty table."""
    info = run_info(adata)
    key = info.get("fate_obsm_key")
    return (_build_fate_summary_table(adata, cluster_key=info["cluster_key"], obsm_key=key)
            if key else pd.DataFrame())


def trajectory_curves(adata) -> pd.DataFrame:
    """Return retained R trajectory curves, or an empty table for Python methods."""
    data = adata.uns.get(_CURVES_KEY)
    return pd.read_json(io.StringIO(data), orient="split") if data else pd.DataFrame()


def pseudotime_figure(adata):
    """Return a matplotlib Figure colored by pseudotime on the display embedding."""
    from matplotlib import pyplot as plt
    info = run_info(adata)
    coords = np.asarray(adata.obsm[info["display_embedding"]])
    fig, ax = plt.subplots(figsize=(6, 5))
    points = ax.scatter(coords[:, 0], coords[:, 1], c=adata.obs["pseudotime"], s=6)
    fig.colorbar(points, ax=ax, label="Pseudotime")
    fig.tight_layout()
    return fig


def _prepare_via_runtime() -> None:
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


def _candidate_reps(adata) -> list[str]:
    preferred = [key for key in ("X_pca", "X_harmony", "X_scvi", "X_scanvi", "X_scanorama", "X_umap") if key in adata.obsm]
    if preferred:
        return preferred
    return [str(key) for key in adata.obsm.keys() if str(key).startswith("X_") and str(key) not in {"X_umap", "X_tsne", "X_diffmap"}]


def _candidate_display_embeddings(adata) -> list[str]:
    preferred = [key for key in ("X_umap", "X_tsne", "X_phate", "X_diffmap", "X_pca") if key in adata.obsm]
    return preferred or [str(key) for key in adata.obsm.keys() if str(key).startswith("X_")]


def _resolve_use_rep(adata, requested: str | None) -> str:
    if requested:
        if requested not in adata.obsm:
            raise ValueError(f"Embedding `{requested}` was not found in adata.obsm.")
        return requested
    candidates = _candidate_reps(adata)
    if not candidates:
        raise ValueError("No suitable representation was found. Run `sc-preprocessing` or `sc-batch-integration` first.")
    return candidates[0]


def _resolve_display_embedding(adata, use_rep: str) -> str:
    candidates = _candidate_display_embeddings(adata)
    return candidates[0] if candidates else use_rep


def _resolve_root_cell(adata, root_cell: str | None) -> int | None:
    if root_cell is None:
        return None
    token = str(root_cell).strip()
    if token == "":
        return None
    if token in set(adata.obs_names.astype(str)):
        return int(np.where(adata.obs_names.astype(str) == token)[0][0])
    if token.isdigit():
        idx = int(token)
        if 0 <= idx < adata.n_obs:
            return idx
    raise ValueError(f"`--root-cell {root_cell}` was not found. Provide a valid obs_name or integer cell index.")


def _ensure_neighbors_for_rep(adata, *, use_rep: str, n_neighbors: int, n_pcs: int) -> None:
    if use_rep == "X_pca":
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs)
    else:
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, use_rep=use_rep)


def _build_pseudotime_points_table(adata, *, pseudotime_key: str, cluster_key: str, display_key: str) -> pd.DataFrame:
    coords = np.asarray(adata.obsm[display_key])
    return pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "display_embedding": display_key,
            "coord1": coords[:, 0],
            "coord2": coords[:, 1],
            cluster_key: adata.obs[cluster_key].astype(str).to_numpy(),
            "pseudotime": pd.to_numeric(adata.obs[pseudotime_key], errors="coerce").to_numpy(),
        }
    )


def _build_fate_summary_table(adata, *, cluster_key: str, obsm_key: str) -> pd.DataFrame:
    if obsm_key not in adata.obsm:
        return pd.DataFrame()
    matrix = np.asarray(adata.obsm[obsm_key], dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        return pd.DataFrame()
    columns = [f"lineage_{i+1}" for i in range(matrix.shape[1])]
    frame = pd.DataFrame(matrix, columns=columns, index=adata.obs_names.astype(str))
    frame["group"] = adata.obs[cluster_key].astype(str).to_numpy()
    return frame.groupby("group", observed=False)[columns].mean().reset_index()


def _run_dpt(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    root_cell_idx: int | None,
    n_neighbors: int,
    n_pcs: int,
    n_dcs: int,
) -> tuple[object, dict]:
    _ensure_neighbors_for_rep(adata, use_rep=use_rep, n_neighbors=n_neighbors, n_pcs=n_pcs)
    sc_traj.run_paga_analysis(adata, cluster_key=cluster_key, n_neighbors=n_neighbors)
    diffmap_result = sc_traj.run_diffusion_map(adata, n_comps=max(15, n_dcs + 5), n_dcs=n_dcs)
    dpt_result = sc_traj.run_dpt_pseudotime(
        adata,
        root_cell_indices=[root_cell_idx] if root_cell_idx is not None else None,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        n_dcs=n_dcs,
    )
    summary = {
        "backend": "dpt",
        "pseudotime_key": "dpt_pseudotime",
        "root_cell": int(dpt_result["root_cells"][0]) if dpt_result["root_cells"] else None,
        "root_cell_name": str(adata.obs_names[int(dpt_result["root_cells"][0])]) if dpt_result["root_cells"] else None,
        "n_diffusion_components": int(diffmap_result["diffmap"].shape[1]),
    }
    return adata, summary


def _run_palantir(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    root_cell_idx: int | None,
    palantir_knn: int,
    palantir_n_components: int,
    palantir_num_waypoints: int,
    palantir_max_iterations: int,
    palantir_seed: int,
) -> tuple[object, dict]:
    early_cell = sc_traj.resolve_palantir_early_cell(
        adata,
        root_cell=root_cell_idx,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        use_rep=use_rep,
    )
    result = sc_traj.run_palantir_pseudotime(
        adata,
        early_cell=early_cell,
        use_rep=use_rep,
        knn=palantir_knn,
        n_components=palantir_n_components,
        num_waypoints=palantir_num_waypoints,
        max_iterations=palantir_max_iterations,
        seed=palantir_seed,
    )
    if "palantir_fate_probabilities" in adata.obsm:
        adata.obsm["trajectory_fate_probabilities"] = np.asarray(adata.obsm["palantir_fate_probabilities"], dtype=float)
    summary = {
        "backend": "palantir",
        "pseudotime_key": "palantir_pseudotime",
        "root_cell": int(np.where(adata.obs_names.astype(str) == str(early_cell))[0][0]),
        "root_cell_name": str(early_cell),
        "mean_entropy": float(np.nanmean(result["entropy"])) if result.get("entropy") is not None else None,
        "n_terminal_states": int(result["fate_probabilities"].shape[1]) if result.get("fate_probabilities") is not None else 0,
        "fate_obsm_key": "trajectory_fate_probabilities" if "trajectory_fate_probabilities" in adata.obsm else None,
    }
    return adata, summary


def _run_via(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    root_cell_idx: int | None,
    via_knn: int,
    via_seed: int,
    n_dcs: int,
) -> tuple[object, dict]:
    result = sc_traj.run_via_pseudotime(
        adata,
        root_cell=root_cell_idx,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        use_rep=use_rep,
        knn=via_knn,
        n_components=max(2, n_dcs),
        seed=via_seed,
    )
    if "via_fate_probabilities" in adata.obsm:
        adata.obsm["trajectory_fate_probabilities"] = np.asarray(adata.obsm["via_fate_probabilities"], dtype=float)
    summary = {
        "backend": result.get("method", "via"),
        "pseudotime_key": "via_pseudotime",
        "root_cell": int(result["root_cell"]),
        "root_cell_name": str(result["root_cell_name"]),
        "n_terminal_states": int(len(result.get("terminal_clusters", []))),
        "fate_obsm_key": "trajectory_fate_probabilities" if "trajectory_fate_probabilities" in adata.obsm else None,
    }
    return adata, summary


def _run_cellrank(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    root_cell_idx: int | None,
    n_neighbors: int,
    n_pcs: int,
    n_dcs: int,
    cellrank_n_states: int,
    cellrank_schur_components: int,
    cellrank_frac_to_keep: float,
    cellrank_use_velocity: bool,
) -> tuple[object, dict]:
    _ensure_neighbors_for_rep(adata, use_rep=use_rep, n_neighbors=n_neighbors, n_pcs=n_pcs)
    result = sc_traj.run_cellrank_pseudotime(
        adata,
        root_cell=root_cell_idx,
        root_cluster=root_cluster,
        cluster_key=cluster_key,
        n_states=cellrank_n_states,
        schur_components=cellrank_schur_components,
        frac_to_keep=cellrank_frac_to_keep,
        use_velocity=cellrank_use_velocity,
        n_dcs=n_dcs,
    )
    if result.get("fate_probabilities") is not None:
        adata.obsm["trajectory_fate_probabilities"] = np.asarray(result["fate_probabilities"], dtype=float)
    summary = {
        "backend": "cellrank",
        "pseudotime_key": "dpt_pseudotime",
        "root_cell": result.get("root_cell"),
        "root_cell_name": result.get("root_cell_name"),
        "n_terminal_states": int(len(result.get("terminal_states", []))),
        "n_macrostates": int(result.get("n_macrostates", 0)),
        "kernel_mode": result.get("kernel_mode"),
        "fate_obsm_key": "trajectory_fate_probabilities" if "trajectory_fate_probabilities" in adata.obsm else None,
    }
    return adata, summary


def _run_slingshot_r(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
    end_clusters: list[str] | None,
) -> tuple[object, dict, pd.DataFrame]:
    required = ["slingshot", "SingleCellExperiment", "zellkonverter"]
    missing_required = RScriptRunner(scripts_dir=R_SCRIPTS_DIR).get_missing_packages(required)
    if missing_required:
        raise ImportError(
            "Slingshot R dependencies are missing: "
            + ", ".join(missing_required)
            + "\nInstall with:\n"
            + suggest_r_install(missing_required)
        )

    runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=7200)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_slingshot_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        save_h5ad(adata, input_h5ad, compression=None)
        runner.run_script(
            "sc_slingshot_pseudotime.R",
            args=[
                str(input_h5ad),
                str(output_dir),
                cluster_key,
                use_rep,
                root_cluster or "",
                ",".join(end_clusters or []),
            ],
            expected_outputs=["slingshot_pseudotime.csv", "slingshot_branches.csv", "slingshot_curves.csv"],
            output_dir=output_dir,
        )
        pseudotime_df = pd.read_csv(output_dir / "slingshot_pseudotime.csv")
        branch_df = pd.read_csv(output_dir / "slingshot_branches.csv")
        curves_df = pd.read_csv(output_dir / "slingshot_curves.csv")

    pseudotime_df["cell_id"] = pseudotime_df["cell_id"].astype(str)
    pseudotime_df = pseudotime_df.drop_duplicates(subset="cell_id", keep="first")
    pseudotime_df = pseudotime_df.set_index("cell_id").reindex(adata.obs_names.astype(str))
    adata.obs["slingshot_pseudotime"] = pd.to_numeric(pseudotime_df["slingshot_pseudotime"], errors="coerce").to_numpy()
    for col in pseudotime_df.columns:
        if col == "slingshot_pseudotime":
            continue
        adata.obs[f"slingshot_{col}"] = pd.to_numeric(pseudotime_df[col], errors="coerce").to_numpy()

    branch_df["cell_id"] = branch_df["cell_id"].astype(str)
    branch_df = branch_df.drop_duplicates(subset="cell_id", keep="first")
    branch_df = branch_df.set_index("cell_id").reindex(adata.obs_names.astype(str))
    for col in branch_df.columns:
        adata.obs[f"slingshot_branch_{col}"] = branch_df[col].astype(str).to_numpy()

    adata.uns["slingshot_trajectory"] = {
        "use_rep": use_rep,
        "cluster_key": cluster_key,
        "start_cluster": root_cluster,
        "end_clusters": end_clusters or [],
        "n_lineages": int(max(1, len([col for col in pseudotime_df.columns if col != "slingshot_pseudotime"]))),
    }
    summary = {
        "backend": "slingshot_r",
        "pseudotime_key": "slingshot_pseudotime",
        "root_cell": None,
        "root_cell_name": None,
        "n_lineages": int(max(1, len([col for col in pseudotime_df.columns if col != "slingshot_pseudotime"]))),
    }
    return adata, summary, curves_df


def _run_monocle3_r(
    adata,
    *,
    use_rep: str,
    cluster_key: str,
    root_cluster: str | None,
) -> tuple[object, dict, pd.DataFrame]:
    """Run Monocle3 principal graph pseudotime via R bridge."""
    import warnings

    required = ["monocle3", "SingleCellExperiment", "zellkonverter"]
    missing_required = RScriptRunner(scripts_dir=R_SCRIPTS_DIR).get_missing_packages(required)
    if missing_required:
        raise ImportError(
            "Monocle3 R dependencies are missing: "
            + ", ".join(missing_required)
            + "\nInstall with:\n"
            + suggest_r_install(missing_required)
        )

    runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=2400)
    with tempfile.TemporaryDirectory(prefix="omicsclaw_monocle3_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_sub = tmpdir / "output"
        output_sub.mkdir(parents=True, exist_ok=True)
        save_h5ad(adata, input_h5ad, compression=None)

        r_cluster_key = cluster_key
        r_use_rep = use_rep if use_rep else "X_umap"
        r_root_cluster = root_cluster or "auto"
        r_root_pr_nodes = "auto"

        runner.run_script(
            "sc_monocle3_r.R",
            args=[
                str(input_h5ad),
                str(output_sub),
                r_cluster_key,
                r_use_rep,
                r_root_cluster,
                r_root_pr_nodes,
            ],
            expected_outputs=["monocle3_pseudotime.csv"],
            output_dir=output_sub,
        )

        pt_csv = output_sub / "monocle3_pseudotime.csv"
        traj_csv = output_sub / "monocle3_trajectory.csv"

        pt_df = pd.read_csv(pt_csv) if pt_csv.exists() else pd.DataFrame()
        traj_df = pd.read_csv(traj_csv) if traj_csv.exists() else pd.DataFrame()

    n_with_pt = 0
    if not pt_df.empty and "monocle3_pseudotime" in pt_df.columns:
        pt_df["cell_id"] = pt_df["cell_id"].astype(str)
        pt_df = pt_df.drop_duplicates(subset="cell_id", keep="first")
        pt_df_indexed = pt_df.set_index("cell_id").reindex(adata.obs_names.astype(str))

        adata.obs["monocle3_pseudotime"] = pd.to_numeric(
            pt_df_indexed["monocle3_pseudotime"], errors="coerce"
        ).to_numpy()
        if "monocle3_cluster" in pt_df_indexed.columns:
            adata.obs["monocle3_cluster"] = (
                pt_df_indexed["monocle3_cluster"].astype(str).to_numpy()
            )
        if "monocle3_partition" in pt_df_indexed.columns:
            adata.obs["monocle3_partition"] = (
                pt_df_indexed["monocle3_partition"].astype(str).to_numpy()
            )
        n_with_pt = int(adata.obs["monocle3_pseudotime"].notna().sum())
    else:
        warnings.warn("Monocle3 pseudotime CSV was empty or missing expected columns")
        adata.obs["monocle3_pseudotime"] = np.nan

    if not traj_df.empty:
        adata.uns["monocle3_trajectory"] = traj_df.to_dict(orient="list")

    summary = {
        "backend": "monocle3_r",
        "pseudotime_key": "monocle3_pseudotime",
        "root_cell": None,
        "root_cell_name": None,
        "n_cells_with_pseudotime": n_with_pt,
    }
    return adata, summary, traj_df
