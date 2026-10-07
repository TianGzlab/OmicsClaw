---
name: sc-pseudotime
description: Load when ordering cells along a developmental trajectory in a normalised scRNA AnnData via
  DPT, Palantir, VIA, CellRank, Slingshot (R), or Monocle3 (R). Skip when ranking marker genes per cluster
  (use sc-markers); RNA velocity vector fields (use sc-velocity).
trigger: pseudotime, trajectory, lineage, diffusion pseudotime, palantir, via, cellrank, monocle3, slingshot
tags:
- singlecell
- scrna
- pseudotime
- trajectory
- dpt
- palantir
- via
- cellrank
- slingshot
- monocle3
---

# sc-pseudotime

## Use from a step

```python
trajectory = load_skill("sc-pseudotime")
result = trajectory.pseudotime(read_input("clustered.h5ad"), cluster_key="leiden",
                                use_rep="X_pca", root_cluster="0")
write_output(trajectory.pseudotime_table(result), "tables/pseudotime.csv")
write_output(trajectory.trajectory_genes(result), "tables/trajectory_genes.csv")
write_output(trajectory.pseudotime_figure(result), "figures/pseudotime.png")
write_output(result, "intermediate/adata_pseudotime.h5ad")
```

The input is not changed. The PBMC example in `examples/example_step.py`
demonstrates the API; PBMC labels do not validate a differentiation trajectory.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `pseudotime(adata, *, method: str='dpt', cluster_key: str='leiden', use_rep: str | None=None, root_cluster: str | None=None, root_cell: str | int | None=None, end_clusters: list[str] | None=None, n_neighbors: int=15, n_pcs: int=50, n_dcs: int=10, palantir_knn: int=30, palantir_n_components: int=10, palantir_num_waypoints: int=1200, palantir_max_iterations: int=25, palantir_seed: int | None=None, via_knn: int=30, via_seed: int | None=None, cellrank_n_states: int=3, cellrank_schur_components: int=20, cellrank_frac_to_keep: float=0.3, cellrank_use_velocity: bool=False, random_state: int=20)`

Return a copy with pseudotime and backend diagnostics.

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

### `run_info(adata, *, keep: bool=True) -> dict`

Read method, root and representation diagnostics; keep=False removes the record.

### `trajectory_genes(adata, *, n_genes: int=50, method: str='pearson') -> pd.DataFrame`

Rank genes by correlation with pseudotime; method is pearson or spearman.

### `pseudotime_table(adata) -> pd.DataFrame`

Return cell, display coordinates, group and pseudotime columns.

### `fate_probability_table(adata) -> pd.DataFrame`

Return backend fate probabilities averaged by group, or an empty table.

### `trajectory_curves(adata) -> pd.DataFrame`

Return retained R trajectory curves, or an empty table for Python methods.

### `pseudotime_figure(adata)`

Return a matplotlib Figure colored by pseudotime on the display embedding.

<!-- api:end -->

## Methods and parameters

Six methods remain available: DPT, Palantir, VIA, CellRank, Slingshot R and
Monocle3 R. DPT uses Scanpy. Other methods require their named backend;
missing packages raise errors rather than selecting a different method.

`use_rep=None` now prefers X_pca, consistent with preflight. UMAP is still
preferred for display, not the inference graph. Root cells accept obs names
or integer positions. Root and terminal choices are biological assumptions
the caller must justify.

Neighbor/component defaults retain the CLI behavior: 15 neighbors,
50 PCs and 10 DPT components. Palantir defaults to 30 neighbors, 10 diffusion
components, 1200 waypoints and 25 iterations; VIA uses 30 neighbors.
`random_state=20` supplies the Palantir/VIA seed unless their explicit
overrides are given. DPT retains Scanpy's deterministic defaults.

## Gotchas

- The API does not set `NUMBA_DISABLE_JIT`; the compatibility CLI retains
  its existing setting (`sc_pseudotime.py:15`).
- `run_info` reports the chosen representation and root. Check finite
  `obs["pseudotime"]` values; disconnected graphs can produce infinity (`_api.py:183`).
- Existing matrix contracts must identify normalized expression. Root choice
  does not prove direction or causality (`_api.py:28`).
- R wrappers still exchange temporary H5AD, requiring zellkonverter and its
  R/Python setup. This migration does not convert them to MTX. Slingshot and
  Monocle3 have separate explicit package checks (`_api.py:482`, `_api.py:556`).
- VIA applies its existing NumPy compatibility aliases only when invoked (`_api.py:230`).
- `fate_probability_table` is a group mean, not per-cell fate probabilities;
  the per-cell matrix is `obsm["trajectory_fate_probabilities"]` (`_api.py:204`).

## Inputs & Outputs

The API needs normalized expression, an obs grouping and an obsm representation.
It returns an annotated copy plus table/Figure helpers. R curves can be read
through `trajectory_curves`.

CLI files include `processed.h5ad`, `tables/pseudotime_cells.csv`,
`tables/trajectory_genes.csv`, `tables/trajectory_summary.csv`,
`report.md` and `result.json`. Fate-probability and curve tables are
conditional on backend output. Figures and figure-data manifests describe
the plots actually produced.

## Key CLI

```bash
python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py --demo --use-rep X_pca --output /tmp/sc_pt_demo
python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py --input clustered.h5ad --cluster-key leiden --root-cluster 0 --use-rep X_pca --output results/
```

## Dependencies

`anndata`, `cellrank`, `matplotlib`, `numpy`, `palantir`, `pandas`, `pyVIA`, `scanpy`, `scipy`, `scvelo`, `seaborn`
