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

## When to use

The user has a clustered, normalised scRNA AnnData and wants a
trajectory / pseudotime ordering across the cells. Six methods:

- `dpt` (default) — diffusion pseudotime (Scanpy native).
- `palantir` — Palantir waypoint-based pseudotime + fate probabilities.
- `via` — VIA, scalable lineage with branching.
- `cellrank` — CellRank macrostates + fate probabilities (optionally
  velocity-coupled with `--cellrank-use-velocity`).
- `slingshot_r` — R-backed Slingshot lineage curves.
- `monocle3_r` — R-backed Monocle3 trajectory graph.

Required: a normalised AnnData with a cluster column (`leiden` by
default) and a low-D representation (`obsm["X_pca"]` / `X_harmony` /
etc.). For per-cluster marker ranking use `sc-markers`; for velocity
vector fields (kinetics, not ordering) use `sc-velocity`.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)

**Outputs**

- `tables/cell_metadata.csv`
- `tables/fate_probabilities.csv`
- `tables/gene_expression.csv`
- `tables/monocle3_pseudotime.csv`
- `tables/monocle3_trajectory.csv`
- `tables/pseudotime_cells.csv`
- `tables/pseudotime_points.csv`
- `tables/slingshot_branches.csv`
- `tables/slingshot_curves.csv`
- `tables/slingshot_pseudotime.csv`
- `tables/trajectory_genes.csv`
- `tables/trajectory_summary.csv`
- `figures/monocle3_trajectory_graph.png`
- `figures/r_cell_density.png`
- `figures/r_embedding_discrete.png`
- `figures/r_embedding_feature.png`
- `figures/r_pseudotime_dynamic.png`
- `figures/r_pseudotime_heatmap.png`
- `figures/r_pseudotime_lineage.png`
- `analysis_summary.txt`
- `input.h5ad`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `pseudotime`; `obsm`: `trajectory_fate_probabilities`

## Flow

1. Load AnnData (`--input`) or auto-build a demo with the largest cluster as the root.
2. Validate `cluster_key` exists; require `X = normalized_expression`.
3. Resolve representation (`--use-rep`) — auto-pick from `obsm` if unset.
4. Resolve root cell from `--root-cluster` or `--root-cell` (integer index or `obs_name`).
5. Dispatch to the method-specific runner; the R-backed methods exec via `RScriptRunner` against the bundled R scripts.
6. Build trajectory-gene correlations (`--n-genes`, `--corr-method`).
7. Save `processed.h5ad`, tables, figures, `report.md`, `result.json` (incl. `backend`, `n_clusters`, `n_trajectory_genes`).

## Gotchas

- **Hard-fails when `.X` isn't normalised.** `sc_pseudotime.py` raises `ValueError("`sc-pseudotime` expects normalized expression. Run `sc-preprocessing` first.")` based on the matrix-contract metadata. If you skipped `sc-preprocessing`, the contract check rejects the run before any pseudotime work happens.
- **No suitable representation → hard fail.** `sc_pseudotime.py` raises `ValueError("Embedding `<rep>` was not found in adata.obsm.")` for an explicit-but-missing `--use-rep`; raises `ValueError("No suitable representation was found. Run `sc-preprocessing` or `sc-batch-integration` first.")` when no embedding key resolves.
- **`cluster_key` validated twice.** `sc_pseudotime.py` raises `ValueError("`<key>` was not found in adata.obs.")` for the top-level `--cluster-key`. Default is `leiden`; pass `--cluster-key louvain` (or whatever you have) explicitly.
- **`--root-cell` accepts obs_name OR integer index.** `sc_pseudotime.py` raises `ValueError("`--root-cell <x>` was not found. Provide a valid obs_name or integer cell index.")` if neither resolves. The integer path lets you avoid copy-pasting a long barcode.
- **R-backed methods need a working R env.** `sc_pseudotime.py` raises `ImportError("Slingshot R dependencies are missing: <list>")` (slingshot / SingleCellExperiment / zellkonverter); raises the same shape for Monocle3 (monocle3 / SingleCellExperiment / zellkonverter). Both messages append the full `suggest_r_install(...)` install hint.
- **`result.json["backend"]` records the actually-used backend.** `sc_pseudotime.py` (dpt) / `_run_palantir` (palantir) / `_run_via` (via) / `_run_cellrank` (cellrank) / `_run_slingshot_r` (slingshot_r) / `_run_monocle3_r` (monocle3_r) write the literal backend label. Useful when `--method` was an alias or fell through any future fallback.
- **`--input` is `parser.error`, not a Python `ValueError`.** `sc_pseudotime.py` calls `parser.error("--input is required unless --demo is used")` which exits with code 2 — caller wrappers expecting `SystemExit(1)` or `ValueError` need to handle code 2 separately. Once `--input` is given, `main` raises `FileNotFoundError(f"Input file not found: {input_path}")` for a bad path.

## Key CLI

```bash
# Demo (auto-chooses largest cluster as root)
python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py --demo --output /tmp/sc_pt_demo

# DPT with explicit root cluster
python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py \
  --input clustered.h5ad --output results/ \
  --cluster-key leiden --root-cluster "0" --use-rep X_pca

# Palantir with custom waypoints + seed
python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py \
  --input clustered.h5ad --output results/ \
  --method palantir --root-cell ATCACG-1 \
  --palantir-num-waypoints 1500 --palantir-seed 42

# CellRank coupled with velocity (requires layers from sc-velocity)
python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py \
  --input velocity.h5ad --output results/ \
  --method cellrank --cellrank-use-velocity --cellrank-n-states 5

# Slingshot R lineage curves
python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py \
  --input clustered.h5ad --output results/ \
  --method slingshot_r --cluster-key leiden --root-cluster "0"
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — method selection guide; root-cell heuristics
- `references/output_contract.md` — `obs["pseudotime"]` / `obsm["trajectory_fate_probabilities"]` schema
- Adjacent skills: `sc-clustering` (upstream — produces `obs["leiden"]` + `obsm["X_*"]`), `sc-preprocessing` (upstream — required for normalised `.X`), `sc-velocity` (parallel — kinetics-based ordering, can feed CellRank), `sc-markers` (parallel — cluster-level marker ranking, NOT trajectory)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cellrank`, `matplotlib`, `numpy`, `palantir`, `pandas`, `pyVIA`, `scanpy`, `scipy`, `scvelo`, `seaborn`
