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

## Scope Boundary

Implemented analysis method:

1. `dpt`

Separate post-hoc trajectory-gene ranking methods:

1. `pearson`
2. `spearman`

## Input Contract

- Accepted input: preprocessed `.h5ad`
- Required metadata: a cluster column such as `leiden`
- Expected upstream state: neighbor graph available or recomputable

## Workflow Summary

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

## Current Limitations

- Only the DPT trajectory path is implemented in the current wrapper.
- This skill does not yet emit the same README/notebook bundle as `sc-qc` and `sc-preprocessing`.
