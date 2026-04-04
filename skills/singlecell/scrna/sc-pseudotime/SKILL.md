---
name: sc-pseudotime
description: >-
  Trajectory analysis for single-cell RNA-seq using Scanpy DPT, Palantir, or VIA,
  plus a configurable correlation method for ranking trajectory-associated
  genes.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, trajectory, pseudotime, paga, dpt, palantir, via, cellrank]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--cluster-key"
      - "--corr-method"
      - "--method"
      - "--n-dcs"
      - "--n-genes"
      - "--palantir-knn"
      - "--palantir-max-iterations"
      - "--palantir-num-waypoints"
      - "--palantir-seed"
      - "--via-knn"
      - "--via-seed"
      - "--cellrank-n-states"
      - "--cellrank-schur-components"
      - "--cellrank-frac-to-keep"
      - "--cellrank-use-velocity"
      - "--root-cell"
      - "--root-cluster"
    param_hints:
      dpt:
        priority: "cluster_key -> root_cluster/root_cell -> n_dcs -> n_genes -> corr_method"
        params: ["cluster_key", "root_cluster", "root_cell", "n_dcs", "n_genes", "corr_method"]
        defaults: {cluster_key: "leiden", n_dcs: 10, n_genes: 50, corr_method: "pearson"}
        requires: ["neighbors_graph", "cluster_labels_in_obs", "scanpy"]
        tips:
          - "--method dpt: Public analysis method for the current wrapper."
          - "--corr-method: Used only for ranking trajectory genes after pseudotime has been estimated."
      palantir:
        priority: "cluster_key -> root_cluster/root_cell -> palantir_knn -> palantir_num_waypoints -> palantir_max_iterations -> corr_method"
        params: ["cluster_key", "root_cluster", "root_cell", "palantir_knn", "palantir_num_waypoints", "palantir_max_iterations", "palantir_seed", "n_genes", "corr_method"]
        defaults: {cluster_key: "leiden", palantir_knn: 30, palantir_num_waypoints: 1200, palantir_max_iterations: 25, palantir_seed: 20, n_genes: 50, corr_method: "pearson"}
        requires: ["palantir", "cluster_labels_in_obs", "explicit_root_choice"]
        tips:
          - "--method palantir: Official Palantir AnnData workflow."
          - "--root-cluster or --root-cell is required for the current Palantir wrapper."
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
      - kind: pip
        package: palantir
        bins: []
    trigger_keywords:
      - trajectory
      - pseudotime
      - diffusion pseudotime
      - dpt
      - palantir
      - paga
      - cell fate
      - diffusion map
---

# Single-Cell Pseudotime

## Why This Exists

- Without it: users often conflate trajectory estimation with downstream gene ranking.
- With it: the wrapper separates the trajectory method from the trajectory-gene correlation method.
- Why OmicsClaw: one contract bundles PAGA, diffusion map, DPT, and export tables.

## Core Capabilities

1. **Two explicit trajectory paths**: Scanpy DPT and Palantir, both with separate post-hoc gene ranking.
2. **Transparent root control**: root cluster or root cell can be supplied explicitly.
3. **Trajectory-specific exports**: pseudotime AnnData, trajectory-gene table, and direct figure outputs.
4. **Clear separation of concerns**: trajectory estimation and correlation-based gene ranking are documented as different steps.
5. **Downstream-ready export**: writes `adata_with_trajectory.h5ad`, report, result JSON, README, and notebook artifacts.

## Scope Boundary

Implemented analysis method:

1. `dpt`
2. `palantir`
3. `via`
4. `cellrank`

Separate post-hoc trajectory-gene ranking methods:

1. `pearson`
2. `spearman`

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | preferred | most realistic preprocessed-input path |
| Shared-loader formats | `.h5`, `.loom`, `.csv`, `.tsv`, 10x directory | technically loadable | still need graph / cluster state to be meaningful |
| Demo | `--demo` | yes | bundled fallback |

### Input Expectations

- Required metadata: a cluster column such as `leiden`.
- Expected upstream state: neighbor graph available or recomputable.
- Root choice matters scientifically; the wrapper does not infer biological direction for you.

## Workflow

1. Validate cluster labels and graph availability.
2. Run PAGA.
3. Run diffusion map and DPT pseudotime.
4. Rank trajectory-associated genes with `--corr-method`.
5. Save `adata_with_trajectory.h5ad`, figures, tables, `report.md`, and `result.json`.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py \
  --input <data.h5ad> --method dpt --cluster-key leiden --output <dir>

python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py \
  --input <data.h5ad> --method dpt --root-cluster 0 \
  --n-dcs 10 --n-genes 50 --corr-method spearman --output <dir>

python skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py \
  --input <data.h5ad> --method palantir --root-cluster 0 \
  --palantir-knn 30 --palantir-num-waypoints 1200 --output <dir>
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | trajectory backend | current public values are `dpt`, `palantir`, `via`, and `cellrank` |
| `--cluster-key` | grouping column | used for root selection and summaries |
| `--root-cluster` | root cluster choice | recommended when the start population is known |
| `--root-cell` | root cell override | cell-level alternative to `root-cluster` |
| `--n-dcs` | diffusion components | affects diffusion-map dimensionality |
| `--n-genes` | ranked trajectory-gene count | output-size control |
| `--corr-method` | post-hoc gene ranking method | `pearson` or `spearman` |
| `--palantir-knn` | Palantir graph size | used only by `palantir` |
| `--palantir-num-waypoints` | Palantir waypoint count | used only by `palantir` |
| `--palantir-max-iterations` | Palantir convergence cap | used only by `palantir` |
| `--via-knn` | VIA graph size | used only by `via` |
| `--via-seed` | VIA random seed | used only by `via` |
| `--cellrank-n-states` | CellRank macrostates | used only by `cellrank` |
| `--cellrank-schur-components` | CellRank Schur decomposition size | used only by `cellrank` |
| `--cellrank-frac-to-keep` | CellRank pseudotime kernel sparsification | used only by `cellrank` |
| `--cellrank-use-velocity` | prefer VelocityKernel when available | used only by `cellrank` |

## Algorithm / Methodology

Current OmicsClaw `sc-pseudotime` runs either:

### `dpt`

1. graph validation or recomputation
2. PAGA graph abstraction
3. diffusion map construction
4. DPT pseudotime estimation from the chosen root
5. post-hoc trajectory-gene ranking using `corr_method`

### `palantir`

1. root resolution from `root_cluster` or `root_cell`
2. Palantir diffusion maps and multiscale manifold construction
3. Palantir pseudotime / entropy / fate-probability inference
4. post-hoc trajectory-gene ranking using `corr_method`

Important implementation notes:

- `method` selects the trajectory algorithm.
- `corr_method` only changes how trajectory-associated genes are ranked after pseudotime is estimated.

## Output Contract

Successful runs write:

- `adata_with_trajectory.h5ad`
- `report.md`
- `result.json`
- `tables/trajectory_genes.csv`
- `figures/paga_graph.png`
- `figures/pseudotime_umap.png`
- `figures/diffusion_components*.png`
- `figures/trajectory_gene_heatmap.png`

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/paga_graph.png`
- `figures/pseudotime_umap.png`
- `figures/diffusion_components.png`
- `figures/trajectory_gene_heatmap.png`

### What Users Should Inspect First

1. `report.md`
2. `figures/pseudotime_umap.png`
3. `figures/paga_graph.png`
4. `tables/trajectory_genes.csv`
5. `adata_with_trajectory.h5ad`

## Current Limitations

- `palantir` currently requires an explicit root choice in OmicsClaw.
- `via` requires the optional `pyVIA` dependency and an explicit root choice.
- `cellrank` requires the optional `cellrank` dependency and is intended for terminal-state / fate analysis, not just scalar ordering.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.

## Safety And Guardrails

- Root choice is scientific input, not a cosmetic parameter; state it explicitly before the run.
- `corr_method` changes only the post-hoc gene-ranking step, not the trajectory algorithm itself.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-pseudotime-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-pseudotime.md`.
