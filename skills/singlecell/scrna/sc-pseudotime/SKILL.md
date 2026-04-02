---
name: sc-pseudotime
description: >-
  Trajectory analysis for single-cell RNA-seq using the current Scanpy-based
  DPT workflow, plus a configurable correlation method for ranking
  trajectory-associated genes.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [singlecell, trajectory, pseudotime, paga, dpt]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--cluster-key"
      - "--corr-method"
      - "--method"
      - "--n-dcs"
      - "--n-genes"
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
    trigger_keywords:
      - trajectory
      - pseudotime
      - diffusion pseudotime
      - dpt
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

1. **One explicit trajectory path**: Scanpy DPT with separate post-hoc gene ranking.
2. **Transparent root control**: root cluster or root cell can be supplied explicitly.
3. **Trajectory-specific exports**: pseudotime AnnData, trajectory-gene table, and direct figure outputs.
4. **Clear separation of concerns**: trajectory estimation and correlation-based gene ranking are documented as different steps.
5. **Downstream-ready export**: writes `adata_with_trajectory.h5ad`, report, result JSON, README, and notebook artifacts.

## Scope Boundary

Implemented analysis method:

1. `dpt`

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
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | trajectory backend | current public value is `dpt` |
| `--cluster-key` | grouping column | used for root selection and summaries |
| `--root-cluster` | root cluster choice | recommended when the start population is known |
| `--root-cell` | root cell override | cell-level alternative to `root-cluster` |
| `--n-dcs` | diffusion components | affects diffusion-map dimensionality |
| `--n-genes` | ranked trajectory-gene count | output-size control |
| `--corr-method` | post-hoc gene ranking method | `pearson` or `spearman` |

## Algorithm / Methodology

Current OmicsClaw `sc-pseudotime` runs:

1. graph validation or recomputation
2. PAGA graph abstraction
3. diffusion map construction
4. DPT pseudotime estimation from the chosen root
5. post-hoc trajectory-gene ranking using `corr_method`

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

- Only the DPT trajectory path is implemented in the current wrapper.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
