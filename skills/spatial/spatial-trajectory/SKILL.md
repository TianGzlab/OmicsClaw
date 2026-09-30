---
name: spatial-trajectory
description: Load when inferring pseudotime / lineage trajectories on a preprocessed spatial AnnData via
  DPT (default — diffusion pseudotime), CellRank (terminal-state + fate-probability), or Palantir (waypoint
  branch probabilities). Skip when the data has spliced/unspliced layers and you want velocity-driven
  dynamics (use spatial-velocity); non-spatial scRNA pseudotime (use sc-pseudotime).
trigger: trajectory, pseudotime, diffusion pseudotime, DPT, CellRank, Palantir, cell fate, lineage
tags:
- spatial
- trajectory
- pseudotime
- dpt
- cellrank
- palantir
- lineage
---

# spatial-trajectory

## When to use

The user has a preprocessed spatial AnnData (`obsm["X_pca"]` or
neighbour graph populated) and wants pseudotime / branching
trajectories. Three backends:

- `dpt` (default) — diffusion pseudotime via `sc.tl.dpt`. Cheap.
  Tunable `--dpt-n-dcs`.
- `cellrank` — GPCCA macrostates, terminal-state probabilities,
  fate maps, driver-gene ranking. Tunables `--cellrank-n-states`,
  `--cellrank-frac-to-keep`, `--cellrank-schur-components`.
- `palantir` — waypoint sampling + multi-scale Markov for branch
  probabilities. Tunables `--palantir-num-waypoints`,
  `--palantir-knn`, `--palantir-n-components`,
  `--palantir-max-iterations`.

Cluster column (`--cluster-key`) auto-detected from `leiden` /
`cell_type` / `celltype` / `annotation` / `cluster` / `clusters`.
For RNA-velocity-driven trajectories use `spatial-velocity`.

## Inputs & Outputs

**Inputs**

- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)
- Expects `obsm`: `X_pca`

**Outputs**

- `tables/cellrank_driver_genes.csv`
- `tables/palantir_branch_probs.csv`
- `tables/trajectory_cluster_summary.csv`
- `tables/trajectory_diffmap_points.csv`
- `tables/trajectory_driver_genes.csv`
- `tables/trajectory_fate_probabilities.csv`
- `tables/trajectory_fate_probabilities_wide.csv`
- `tables/trajectory_genes.csv`
- `tables/trajectory_run_summary.csv`
- `tables/trajectory_spatial_points.csv`
- `tables/trajectory_summary.csv`
- `tables/trajectory_terminal_states.csv`
- `tables/trajectory_umap_points.csv`
- `figures/cellrank_fate_circular.png`
- `figures/cellrank_fate_heatmap.png`
- `figures/cellrank_fate_map.png`
- `figures/cellrank_gene_trends.png`
- `figures/trajectory_cluster_summary.png`
- `figures/trajectory_diffmap.png`
- `figures/trajectory_entropy_distribution.png`
- `figures/trajectory_fate_probability_distribution.png`
- `figures/trajectory_genes_barplot.png`
- `figures/trajectory_pseudotime_distribution.png`
- `figures/trajectory_pseudotime_embedding.png`
- `figures/trajectory_pseudotime_spatial.png`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `dpt_pseudotime`, `traj_terminal_state`, `traj_fate_max_prob`, `traj_fate_entropy`, `palantir_pseudotime`, `palantir_entropy`; `obsm`: `palantir_branch_probs`; `uns`: `iroot`, `palantir_waypoints`, `palantir_branch_prob_columns`

## Flow

1. Load AnnData (`--input`) or build a demo. Auto-detect `--cluster-key` from candidates if not passed.
2. Pick / pin root cell: `--root-cell <barcode>` or auto-pick via expression-rank; write `uns["iroot"]` (`_lib/trajectory.py`).
3. Run chosen backend:
   - `dpt`: `sc.tl.dpt(adata, n_dcs=...)` → `obs["dpt_pseudotime"]`.
   - `cellrank`: build kernel, GPCCA macrostates, terminal states, fate probabilities, driver genes.
   - `palantir`: waypoint sampling, multi-scale Markov, branch probabilities.
4. Compute trajectory genes (correlation with pseudotime) + cluster-mean / median pseudotime summary.
5. Render embedding / spatial / diffmap / fate / gene-trend plots.
6. Save tables + `processed.h5ad` + report.

## Gotchas

- **`--cluster-key` is auto-detected from a candidate list.** `_lib/trajectory.py` (`_CLUSTER_KEY_CANDIDATES`) tries `leiden` → `cell_type` → `celltype` → `annotation` → `cluster` → `clusters` and the auto-detect returns `None` silently when no candidate column has ≥ 2 unique values — cluster summaries then run with `cluster_key = None`. By contrast, an explicit `--cluster-key X` whose column is missing raises `ValueError` at `spatial_trajectory.py`. Pass an explicit key when you want a hard failure on a typo.
- **Both `dpt` and `cellrank` write `obs["dpt_pseudotime"]`.** `_lib/trajectory.py` populates it via `sc.tl.dpt`; CellRank reuses the same call. Palantir writes `obs["palantir_pseudotime"]` instead — **don't expect `dpt_pseudotime` from a Palantir run**.
- **Palantir branch probabilities are conditional + dual-stored.** `_lib/trajectory.py` writes `obsm["palantir_branch_probs"]` (numeric matrix) AND `uns["palantir_branch_prob_columns"]` (terminal-state column names) ONLY when `branch_probs` is non-empty (`if not branch_probs.empty:`). Single-terminal-state runs leave both keys absent. The cells × terminals matrix is also exported as `tables/palantir_branch_probs.csv` when present.
- **CellRank `traj_*` keys are CellRank-only.** `spatial_trajectory.py` writes `obs["traj_terminal_state"]` / `obs["traj_fate_max_prob"]` / `obs["traj_fate_entropy"]` only when the CellRank branch executes — DPT and Palantir runs leave those keys absent.
- **`uns["iroot"]` is an integer index, not a barcode.** `_lib/trajectory.py` writes the integer position into `obs_names`. Downstream tools that reload the AnnData and expect a string barcode need `adata.obs_names[adata.uns["iroot"]]`.

## Key CLI

```bash
# Demo
python skills/spatial/spatial-trajectory/spatial_trajectory.py --demo --output /tmp/traj_demo

# DPT (default)
python skills/spatial/spatial-trajectory/spatial_trajectory.py \
  --input preprocessed.h5ad --output results/ \
  --method dpt --cluster-key leiden --dpt-n-dcs 10

# CellRank with explicit root cell
python skills/spatial/spatial-trajectory/spatial_trajectory.py \
  --input preprocessed.h5ad --output results/ \
  --method cellrank --root-cell BARCODE_42 \
  --cellrank-n-states 5 --cellrank-frac-to-keep 0.3

# Palantir
python skills/spatial/spatial-trajectory/spatial_trajectory.py \
  --input preprocessed.h5ad --output results/ \
  --method palantir --palantir-num-waypoints 1200 --palantir-knn 30
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins
- `references/output_contract.md` — per-method `obs` / `obsm` / `uns` keys
- Adjacent skills: `spatial-preprocess` (upstream), `spatial-domains` (upstream — provides `obs["leiden"]`), `spatial-velocity` (parallel — RNA-velocity-driven dynamics), `sc-pseudotime` (parallel — non-spatial), `spatial-condition` (downstream — DE between trajectory branches)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cellrank`, `matplotlib`, `numpy`, `palantir`, `pandas`, `scanpy`, `scipy`, `scvelo`, `seaborn`, `statsmodels`
