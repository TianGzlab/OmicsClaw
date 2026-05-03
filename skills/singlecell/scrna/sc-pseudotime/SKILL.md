---
name: sc-pseudotime
description: >-
  Single-cell pseudotime and lineage inference after clustering, with DPT,
  Palantir, VIA, CellRank, or Slingshot plus post-hoc trajectory gene ranking.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [singlecell, pseudotime, trajectory, dpt, palantir, via, cellrank, slingshot]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--cluster-key"
      - "--use-rep"
      - "--root-cluster"
      - "--root-cell"
      - "--end-clusters"
      - "--n-neighbors"
      - "--n-pcs"
      - "--n-dcs"
      - "--n-genes"
      - "--corr-method"
      - "--palantir-knn"
      - "--palantir-n-components"
      - "--palantir-num-waypoints"
      - "--palantir-max-iterations"
      - "--palantir-seed"
      - "--via-knn"
      - "--via-seed"
      - "--cellrank-n-states"
      - "--cellrank-schur-components"
      - "--cellrank-frac-to-keep"
      - "--cellrank-use-velocity"
      - "--r-enhanced"
    param_hints:
      dpt:
        priority: "cluster_key -> use_rep -> root_cluster/root_cell"
        params: ["cluster_key", "use_rep", "root_cluster", "root_cell"]
        advanced_params: ["n_neighbors", "n_pcs", "n_dcs", "n_genes", "corr_method"]
        defaults: {cluster_key: "leiden", n_neighbors: 15, n_pcs: 50, n_dcs: 10, n_genes: 50, corr_method: "pearson"}
        requires: ["normalized_expression", "cluster_labels_in_obs", "trajectory_representation"]
      palantir:
        priority: "cluster_key -> use_rep -> root_cluster/root_cell"
        params: ["cluster_key", "use_rep", "root_cluster", "root_cell"]
        advanced_params: ["palantir_knn", "palantir_n_components", "palantir_num_waypoints", "palantir_max_iterations", "palantir_seed", "n_genes", "corr_method"]
        defaults: {cluster_key: "leiden", palantir_knn: 30, palantir_n_components: 10, palantir_num_waypoints: 1200, palantir_max_iterations: 25, palantir_seed: 20, n_genes: 50, corr_method: "pearson"}
        requires: ["normalized_expression", "palantir", "explicit_root_choice"]
      via:
        priority: "cluster_key -> use_rep -> root_cluster/root_cell"
        params: ["cluster_key", "use_rep", "root_cluster", "root_cell"]
        advanced_params: ["via_knn", "via_seed", "n_genes", "corr_method"]
        defaults: {cluster_key: "leiden", via_knn: 30, via_seed: 20, n_genes: 50, corr_method: "pearson"}
        requires: ["normalized_expression", "pyVIA", "explicit_root_choice"]
      cellrank:
        priority: "cluster_key -> use_rep -> root_cluster/root_cell -> cellrank_n_states"
        params: ["cluster_key", "use_rep", "root_cluster", "root_cell", "cellrank_n_states"]
        advanced_params: ["cellrank_schur_components", "cellrank_frac_to_keep", "cellrank_use_velocity", "n_genes", "corr_method"]
        defaults: {cluster_key: "leiden", cellrank_n_states: 3, cellrank_schur_components: 20, cellrank_frac_to_keep: 0.3, cellrank_use_velocity: false, n_genes: 50, corr_method: "pearson"}
        requires: ["normalized_expression", "cellrank", "explicit_root_choice"]
      slingshot_r:
        priority: "cluster_key -> use_rep -> root_cluster -> end_clusters"
        params: ["cluster_key", "use_rep", "root_cluster", "end_clusters"]
        advanced_params: ["n_genes", "corr_method"]
        defaults: {cluster_key: "leiden", end_clusters: null, n_genes: 50, corr_method: "pearson"}
        requires: ["normalized_expression", "slingshot", "SingleCellExperiment", "zellkonverter", "explicit_root_choice"]
      monocle3_r:
        priority: "cluster_key -> use_rep -> root_cluster"
        params: ["cluster_key", "use_rep", "root_cluster"]
        advanced_params: ["n_genes", "corr_method"]
        defaults: {cluster_key: "leiden", root_cluster: null, n_genes: 50, corr_method: "pearson"}
        requires: ["normalized_expression", "monocle3", "SingleCellExperiment", "zellkonverter"]
    saves_h5ad: true
    requires_preprocessed: true
    trigger_keywords:
      - pseudotime
      - trajectory
      - lineage
      - diffusion pseudotime
      - palantir
      - via
      - cellrank
      - monocle3
      - slingshot
---

# Single-Cell Pseudotime

## What This Skill Does

`sc-pseudotime` is the trajectory step after clustering. It takes a normalized, cluster-labeled AnnData object, picks a start state, infers a trajectory, then ranks genes associated with that trajectory.

This skill answers questions like:
- which cluster should be treated as the start of a biological transition
- how cells order along a continuous trajectory
- which genes change most strongly along that ordering
- whether the method also supports branch or fate information

## What Should Usually Come Before It

- `sc-preprocessing`
- if needed, `sc-batch-integration`
- `sc-clustering`
- optionally `sc-cell-annotation` if the user wants to define the start state by biology instead of just cluster number

If the user only says “do pseudotime”, the first thing to explain is:
- pseudotime needs a biologically defensible start state
- pseudotime should usually use the same representation that drove clustering or integration

## Matrix / State Requirements

- `X` must represent `normalized_expression`
- a cluster or label column must already exist in `adata.obs`
- at least one trajectory representation must exist; the current wrapper defaults to `X_umap` when it is already present, otherwise it falls back to integrated or PCA embeddings such as `X_harmony`, `X_scvi`, `X_scanvi`, `X_scanorama`, or `X_pca`
- `layers["counts"]` may still exist, but trajectory-gene ranking is performed on normalized `adata.X`

## Public Methods

1. `dpt`
2. `palantir`
3. `via`
4. `cellrank`
5. `slingshot_r`
6. `monocle3_r`

## Beginner-Friendly Method Summary

| Method | Best first use | What it adds |
|--------|----------------|--------------|
| `dpt` | most users’ first trajectory pass | classic diffusion pseudotime after graph construction |
| `palantir` | when entropy / fate probabilities are important | waypoint-based pseudotime and terminal-state probabilities |
| `via` | when users want graph-based terminal-state discovery | fast graph trajectory with branch-aware outputs |
| `cellrank` | when users explicitly want macrostates or fate inference | transition-kernel / fate model on top of a graph |
| `slingshot_r` | when users want explicit branch curves | lineage-centric branch inference through the R bridge |
| `monocle3_r` | when users want principal graph trajectory with branching | Monocle3 principal graph trajectory and pseudotime via R bridge. Produces monocle3_pseudotime in obs and MST trajectory edges. Requires monocle3 R package. |

**Note on monocle3_r root selection**: monocle3_r auto-selects the root principal node by finding the principal graph node nearest to the centroid of the `--root-cluster` cells in UMAP space. If `--root-cluster` is not specified, the largest cluster is used. Pass `--root-cluster <name>` to control trajectory direction.

## Key Parameters

### Always important

- `--method`
- `--cluster-key`
- `--use-rep`
- `--root-cluster` or `--root-cell`
- `--n-genes`
- `--corr-method`

### Method-specific

- `dpt`
  - `--n-neighbors`
  - `--n-pcs`
  - `--n-dcs`
- `palantir`
  - `--palantir-knn`
  - `--palantir-n-components`
  - `--palantir-num-waypoints`
  - `--palantir-max-iterations`
  - `--palantir-seed`
- `via`
  - `--via-knn`
  - `--via-seed`
- `cellrank`
  - `--cellrank-n-states`
  - `--cellrank-schur-components`
  - `--cellrank-frac-to-keep`
  - `--cellrank-use-velocity`
- `slingshot_r`
  - `--end-clusters`
- `monocle3_r`
  - `--root-cluster` (auto-selects largest cluster if not specified)

### Usage Examples

```bash
# Monocle3 pseudotime demo
python omicsclaw.py run sc-pseudotime --demo --method monocle3_r --output /tmp/monocle3_demo

# Monocle3 pseudotime with user data
python omicsclaw.py run sc-pseudotime --input <processed.h5ad> --method monocle3_r --cluster-key leiden --output <dir>

# Monocle3 with explicit root cluster
python omicsclaw.py run sc-pseudotime --input <processed.h5ad> --method monocle3_r --cluster-key cell_type --root-cluster "HSC" --output <dir>
```

## Workflow

1. load
2. preflight
3. verify normalized matrix state and trajectory representation
4. resolve root cluster or root cell
5. run method
6. rank trajectory-associated genes with `corr_method`
7. write `processed.h5ad`
8. render figures, tables, and `figure_data`

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/trajectory_genes.csv`
- `tables/pseudotime_cells.csv`
- `tables/trajectory_summary.csv`
- `figure_data/`
- `figures/`

Common figures include:

- `pseudotime_embedding.png`
- `pseudotime_distribution_by_group.png`
- `trajectory_gene_heatmap.png`
- `trajectory_gene_trends.png`
- `fate_probability_heatmap.png` when available
- `paga_graph.png` for `dpt`
- `lineage_curves.png` for `slingshot_r`
- `monocle3_trajectory_graph.png` for `monocle3_r`

## Usual Next Steps

- `sc-pathway-scoring` for lineage signatures
- `sc-enrichment` for statistical pathway interpretation of trajectory genes
- `sc-de` if the user wants condition-level testing after states are stabilized

## Current Guardrails

- do not run pseudotime on raw counts
- do not hide the start state
- do not flatten `method` and `corr_method` into one story
- do not silently switch representations when multiple plausible embeddings exist

For short guardrails see `knowledge_base/knowhows/KH-sc-pseudotime-guardrails.md`.  
For longer method guidance see `knowledge_base/skill-guides/singlecell/sc-pseudotime.md`.

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | — | Input `.h5ad` file | required unless `--demo` |
| `--output` | str | — | Output directory | required |
| `--demo` | flag | off | Run with bundled PBMC3k data | — |
| `--method` | str | `dpt` | Trajectory method: `dpt`, `palantir`, `via`, `cellrank`, `slingshot_r`, `monocle3_r` | validated against METHOD_REGISTRY |
| `--cluster-key` | str | `leiden` | Cluster/label column in `obs` | — |
| `--use-rep` | str | None | Embedding to use (e.g., `X_pca`, `X_harmony`) | auto-detected when omitted |
| `--root-cluster` | str | None | Cluster name to use as trajectory root | — |
| `--root-cell` | str | None | Specific cell (obs_name or integer index) to use as root | — |
| `--end-clusters` | str | None | Comma-separated terminal cluster names | slingshot_r only |
| `--n-neighbors` | int | 15 | KNN size for graph construction | dpt only |
| `--n-pcs` | int | 50 | PCs to use for diffusion map | dpt only |
| `--n-dcs` | int | 10 | Number of diffusion components | dpt only |
| `--n-genes` | int | 50 | Number of trajectory-correlated genes to rank | — |
| `--corr-method` | str | `pearson` | Gene-pseudotime correlation method | choices: pearson, spearman |
| `--palantir-knn` | int | 30 | KNN for Palantir graph | palantir only |
| `--palantir-n-components` | int | 10 | Diffusion components for Palantir | palantir only |
| `--palantir-num-waypoints` | int | 1200 | Waypoints for Palantir | palantir only |
| `--palantir-max-iterations` | int | 25 | Max Palantir iterations | palantir only |
| `--palantir-seed` | int | 20 | Palantir random seed | palantir only |
| `--via-knn` | int | 30 | KNN for VIA graph | via only |
| `--via-seed` | int | 20 | VIA random seed | via only |
| `--cellrank-n-states` | int | 3 | Number of macrostates | cellrank only |
| `--cellrank-schur-components` | int | 20 | Schur decomposition components | cellrank only |
| `--cellrank-frac-to-keep` | float | 0.3 | Fraction of cells to keep for macrostate estimation | cellrank only |
| `--cellrank-use-velocity` | flag | off | Use velocity kernel in CellRank | cellrank only |
| `--r-enhanced` | flag | off | Also render R Enhanced ggplot2 figures | — |

## R Enhanced Plots

Activated by `--r-enhanced`. Files written to `figures/r_enhanced/`.

| Renderer | Output file | figure_data CSV | Plot description | Required R packages |
|----------|-------------|-----------------|------------------|---------------------|
| `plot_pseudotime_lineage` | `r_pseudotime_lineage.png` | `pseudotime_points.csv` | Pseudotime lineage scatter with loess trajectory curves | ggplot2 |
| `plot_pseudotime_dynamic` | `r_pseudotime_dynamic.png` | `trajectory_genes.csv` | Dynamic gene expression trends along pseudotime | ggplot2 |
| `plot_pseudotime_heatmap` | `r_pseudotime_heatmap.png` | `gene_expression.csv` | Heatmap of top trajectory genes ordered by pseudotime | ggplot2, ComplexHeatmap |
| `plot_embedding_discrete` | `r_embedding_discrete.png` | `embedding_points.csv` | UMAP/embedding colored by cluster labels | ggplot2 |
| `plot_embedding_feature` | `r_embedding_feature.png` | `embedding_points.csv` | UMAP/embedding colored by pseudotime score | ggplot2 |
| `plot_cell_density` | `r_cell_density.png` | `embedding_points.csv` | 2D density overlay on embedding | ggplot2, ggdensity |

## Workflow Position

**Upstream:** sc-clustering
**Downstream:** sc-velocity (RNA velocity), sc-gene-programs (temporal gene programs)
