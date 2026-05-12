---
name: spatial-trajectory
description: Load when inferring pseudotime / lineage trajectories on a preprocessed spatial AnnData via DPT (default — diffusion pseudotime), CellRank (terminal-state + fate-probability), or Palantir (waypoint branch probabilities). Skip when the data has spliced/unspliced layers and you want velocity-driven dynamics (use `spatial-velocity`) or for non-spatial scRNA pseudotime (use `sc-pseudotime`).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- spatial
- trajectory
- pseudotime
- dpt
- cellrank
- palantir
- lineage
requires:
- anndata
- scanpy
- numpy
- pandas
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

| Input | Format | Required |
|---|---|---|
| Preprocessed spatial AnnData | `.h5ad` with `obsm["X_pca"]`, neighbour graph (built if missing); optional `obs[cluster_key]` for grouped exports | yes (unless `--demo`) |
| Root cell | `--root-cell <barcode>` (else auto-pick by expression rank) | optional |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | DPT/CellRank: `obs["dpt_pseudotime"]` (set by `sc.tl.dpt` at `_lib/trajectory.py:276`), `uns["iroot"]` (`_lib/trajectory.py:273`); CellRank also: `obs["traj_terminal_state"]`, `obs["traj_fate_max_prob"]`, `obs["traj_fate_entropy"]` (`spatial_trajectory.py:236-238`); Palantir: `obs["palantir_pseudotime"]`, `obs["palantir_entropy"]`, `uns["palantir_waypoints"]` (`_lib/trajectory.py:527-529`); when ≥ 1 branch is non-empty also `obsm["palantir_branch_probs"]` + `uns["palantir_branch_prob_columns"]` (`_lib/trajectory.py:531-533`) |
| Summary | `tables/trajectory_summary.csv` | per-cell pseudotime + cluster |
| Cluster summary | `tables/trajectory_cluster_summary.csv` | per-cluster mean/median pseudotime |
| Trajectory genes | `tables/trajectory_genes.csv` | top correlated with pseudotime |
| Terminal states | `tables/trajectory_terminal_states.csv` + `tables/{method}_terminal_states.csv` | CellRank / Palantir |
| Driver genes | `tables/trajectory_driver_genes.csv` (+ `cellrank_driver_genes.csv` alias) | CellRank only |
| Fate probabilities | `tables/trajectory_fate_probabilities_wide.csv` | CellRank wide form |
| Branch probs | `tables/palantir_branch_probs.csv` | Palantir |
| Run summary | `tables/trajectory_run_summary.csv` | params used |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or build a demo. Auto-detect `--cluster-key` from candidates if not passed.
2. Pick / pin root cell: `--root-cell <barcode>` or auto-pick via expression-rank; write `uns["iroot"]` (`_lib/trajectory.py:273`).
3. Run chosen backend:
   - `dpt`: `sc.tl.dpt(adata, n_dcs=...)` → `obs["dpt_pseudotime"]`.
   - `cellrank`: build kernel, GPCCA macrostates, terminal states, fate probabilities, driver genes.
   - `palantir`: waypoint sampling, multi-scale Markov, branch probabilities.
4. Compute trajectory genes (correlation with pseudotime) + cluster-mean / median pseudotime summary.
5. Render embedding / spatial / diffmap / fate / gene-trend plots.
6. Save tables + `processed.h5ad` + report.

## Gotchas

- **`--cluster-key` is auto-detected from a candidate list.** `_lib/trajectory.py:25-31` (`_CLUSTER_KEY_CANDIDATES`) tries `leiden` → `cell_type` → `celltype` → `annotation` → `cluster` → `clusters` and the auto-detect at `_lib/trajectory.py:62-67` returns `None` silently when no candidate column has ≥ 2 unique values — cluster summaries then run with `cluster_key = None`. By contrast, an explicit `--cluster-key X` whose column is missing raises `ValueError` at `spatial_trajectory.py:1434`. Pass an explicit key when you want a hard failure on a typo.
- **Both `dpt` and `cellrank` write `obs["dpt_pseudotime"]`.** `_lib/trajectory.py:255-280` populates it via `sc.tl.dpt`; CellRank reuses the same call (`_lib/trajectory.py:341`). Palantir writes `obs["palantir_pseudotime"]` instead — **don't expect `dpt_pseudotime` from a Palantir run**.
- **Palantir branch probabilities are conditional + dual-stored.** `_lib/trajectory.py:531-533` writes `obsm["palantir_branch_probs"]` (numeric matrix) AND `uns["palantir_branch_prob_columns"]` (terminal-state column names) ONLY when `branch_probs` is non-empty (`if not branch_probs.empty:` at `_lib/trajectory.py:531`). Single-terminal-state runs leave both keys absent. The cells × terminals matrix is also exported as `tables/palantir_branch_probs.csv` when present.
- **CellRank `traj_*` keys are CellRank-only.** `spatial_trajectory.py:236-238` writes `obs["traj_terminal_state"]` / `obs["traj_fate_max_prob"]` / `obs["traj_fate_entropy"]` only when the CellRank branch executes — DPT and Palantir runs leave those keys absent.
- **`uns["iroot"]` is an integer index, not a barcode.** `_lib/trajectory.py:273` writes the integer position into `obs_names`. Downstream tools that reload the AnnData and expect a string barcode need `adata.obs_names[adata.uns["iroot"]]`.

## Key CLI

```bash
# Demo
python omicsclaw.py run spatial-trajectory --demo --output /tmp/traj_demo

# DPT (default)
python omicsclaw.py run spatial-trajectory \
  --input preprocessed.h5ad --output results/ \
  --method dpt --cluster-key leiden --dpt-n-dcs 10

# CellRank with explicit root cell
python omicsclaw.py run spatial-trajectory \
  --input preprocessed.h5ad --output results/ \
  --method cellrank --root-cell BARCODE_42 \
  --cellrank-n-states 5 --cellrank-frac-to-keep 0.3

# Palantir
python omicsclaw.py run spatial-trajectory \
  --input preprocessed.h5ad --output results/ \
  --method palantir --palantir-num-waypoints 1200 --palantir-knn 30
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins
- `references/output_contract.md` — per-method `obs` / `obsm` / `uns` keys
- Adjacent skills: `spatial-preprocess` (upstream), `spatial-domains` (upstream — provides `obs["leiden"]`), `spatial-velocity` (parallel — RNA-velocity-driven dynamics), `sc-pseudotime` (parallel — non-spatial), `spatial-condition` (downstream — DE between trajectory branches)
