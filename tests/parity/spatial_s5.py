"""Spatial inference baselines recorded before the function-library migration."""

def trajectory_input(path):
    from skills._sdk.notebook import load_demo
    import scanpy as sc

    data = load_demo("spatial_synthetic")
    sc.pp.normalize_total(data, target_sum=10000)
    sc.pp.log1p(data)
    sc.pp.pca(data, n_comps=20, random_state=0)
    sc.pp.neighbors(data, n_neighbors=15, random_state=0)
    sc.tl.umap(data, random_state=0)
    data.obs["leiden"] = data.obs["domain_ground_truth"].astype("category")
    data.write_h5ad(path)


def register(Case, Skill):
    return {
    "spatial-cnv": Skill(
        "skills/spatial/spatial-cnv/spatial_cnv.py", "tests.parity.spatial_s5:api_cnv",
        {"default": Case(("--window-size", "20", "--step", "2"), input=cnv_input)},
    ),
    "spatial-velocity": Skill(
        "skills/spatial/spatial-velocity/spatial_velocity.py", "tests.parity.spatial_s5:api_velocity",
        {"default": Case((), input=velocity_input, exclude={
            key: "scVelo VPT calls unseeded eigsh; the original repeats differed only in these pseudotime columns. Other numeric columns remain strict."
            for key in ("tables/cell_velocity_metrics.csv:velocity_pseudotime",
                        "tables/top_velocity_cells.csv:velocity_pseudotime",
                        "obs_numeric.csv:velocity_pseudotime")})},
    ),
    "spatial-trajectory": Skill(
        "skills/spatial/spatial-trajectory/spatial_trajectory.py",
        "tests.parity.spatial_s5:api_trajectory",
        {"default": Case((), input=trajectory_input, environment={
            key: "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")
        }), "palantir": Case(("--method", "palantir", "--palantir-num-waypoints", "50"), input=trajectory_input)},
    ),
    }


def cnv_input(path):
    import numpy as np
    import scanpy as sc
    trajectory_input(path)
    data = sc.read_h5ad(path)
    data.var["chromosome"] = "chr1"
    data.var["start"] = np.arange(data.n_vars) * 10000
    data.var["end"] = data.var["start"] + 1000
    data.write_h5ad(path)


def velocity_input(path):
    from skills._sdk.notebook import load_demo
    import numpy as np
    data = load_demo("spatial_synthetic")
    rng = np.random.default_rng(0)
    counts = data.X.toarray() if hasattr(data.X, "toarray") else np.asarray(data.X)
    data.layers["spliced"] = rng.poisson(counts * 0.8).astype(float)
    data.layers["unspliced"] = rng.poisson(counts * 0.2 + 1).astype(float)
    data.obs["leiden"] = data.obs["domain_ground_truth"].astype("category")
    data.write_h5ad(path)


def api_cnv(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    data = sc.read_h5ad(input_path)
    library = load_skill("spatial-cnv")
    library.cnv(data, window_size=20, step=2)
    summary = library.run_info(data, keep=False)
    summary.pop("random_state", None)
    return {"adata": data, "tables": {}, "summary": summary}


def api_velocity(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    data = sc.read_h5ad(input_path)
    library = load_skill("spatial-velocity")
    library.velocity(data)
    summary = library.run_info(data, keep=False)
    return {"adata": data, "tables": {
        "cell_velocity_metrics.csv": summary["cell_df"].reset_index(),
        "gene_velocity_summary.csv": summary["gene_df"].reset_index(),
    }}


def api_trajectory(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill

    data = sc.read_h5ad(input_path)
    library = load_skill("spatial-trajectory")
    library.trajectory(data, method="palantir" if case == "palantir" else "dpt",
                       method_params={"palantir_num_waypoints": 50} if case == "palantir" else None)
    summary = library.run_info(data, keep=False)
    summary.pop("random_state", None)
    summary.pop("palantir_waypoint_seed", None)
    import pandas as pd
    return {"adata": data, "summary": {key: value for key, value in summary.items() if not isinstance(value, pd.DataFrame)}, "tables": {}}
