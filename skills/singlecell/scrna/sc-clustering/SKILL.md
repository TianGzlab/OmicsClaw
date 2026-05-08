---
name: sc-clustering
description: >-
  Build the neighbor graph, run a low-dimensional embedding, and cluster single-cell
  data from a
  normalized scRNA AnnData object.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, clustering, embedding, umap, tsne, diffmap, phate, leiden,
  louvain]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
    - "--embedding-method"
    - "--cluster-method"
    - "--use-rep"
    - "--n-neighbors"
    - "--n-pcs"
    - "--resolution"
    - "--umap-min-dist"
    - "--umap-spread"
    - "--tsne-perplexity"
    - "--tsne-metric"
    - "--diffmap-n-comps"
    - "--phate-knn"
    - "--phate-decay"
    - "--r-enhanced"
    param_hints:
      umap:
        priority: "use_rep -> cluster_method -> n_neighbors/resolution"
        params: ["use_rep", "cluster_method", "n_neighbors", "resolution"]
        advanced_params: ["n_pcs", "umap_min_dist", "umap_spread"]
        defaults: {cluster_method: leiden, n_neighbors: 15, n_pcs: 50, resolution: 1.0,
          umap_min_dist: 0.5, umap_spread: 1.0}
        requires: ["normalized_expression", "embedding_or_pca"]
        tips:
        - "`use_rep` is the most important selector if multiple embeddings are available."
      tsne:
        priority: "use_rep -> cluster_method -> n_neighbors/resolution"
        params: ["use_rep", "cluster_method", "n_neighbors", "resolution"]
        advanced_params: ["n_pcs", "tsne_perplexity", "tsne_metric"]
        defaults: {cluster_method: leiden, n_neighbors: 15, n_pcs: 50, resolution: 1.0,
          tsne_perplexity: 30.0, tsne_metric: euclidean}
        requires: ["normalized_expression", "embedding_or_pca"]
        tips:
        - "`tsne` is mainly for visualization; the clustering still comes from the
          neighbor graph."
      diffmap:
        priority: "use_rep -> cluster_method -> n_neighbors/resolution"
        params: ["use_rep", "cluster_method", "n_neighbors", "resolution"]
        advanced_params: ["n_pcs", "diffmap_n_comps"]
        defaults: {cluster_method: leiden, n_neighbors: 15, n_pcs: 50, resolution: 1.0,
          diffmap_n_comps: 15}
        requires: ["normalized_expression", "embedding_or_pca"]
        tips:
        - "`diffmap` often emphasizes continuous trajectories more than compact clusters."
      phate:
        priority: "use_rep -> cluster_method -> n_neighbors/resolution"
        params: ["use_rep", "cluster_method", "n_neighbors", "resolution"]
        advanced_params: ["n_pcs", "phate_knn", "phate_decay"]
        defaults: {cluster_method: leiden, n_neighbors: 15, n_pcs: 50, resolution: 1.0,
          phate_knn: 15, phate_decay: 40}
        requires: ["normalized_expression", "embedding_or_pca", "phate"]
        tips:
        - "`phate` is optional and may need extra installation before use."
    saves_h5ad: true
    requires_preprocessed: true
    legacy_aliases: [sc-dimred-cluster]
    script: sc_cluster.py
---

# Single-Cell Clustering

This skill starts from a normalized scRNA AnnData and performs:
1. neighbor graph construction
2. low-dimensional embedding (`umap`, `tsne`, `diffmap`, or `phate`)
3. graph clustering (`leiden` or `louvain`)

Expected input:
- `processed.h5ad` from `sc-preprocessing`
- or an integrated object from `sc-batch-integration`
- `X = normalized_expression`
- `obsm["X_pca"]` or another explicit embedding chosen by `--use-rep`

Dependency note:
- `leiden` is the recommended default path.
- `louvain` is optional; if the Python package `louvain` is missing, the skill should stop and ask the user to install it explicitly rather than trying to install it automatically.

Main tuning knobs:
- `--embedding-method`: how to render the low-dimensional view (`umap`, `tsne`, `diffmap`, `phate`)
- `--cluster-method`: graph clustering backend (`leiden`, `louvain`)
- `--use-rep`: which embedding in `adata.obsm` should drive the neighbor graph
- `--n-neighbors`: local neighborhood size
- `--n-pcs`: number of PCA dimensions when the neighbor graph is built from `X_pca`
- `--resolution`: cluster granularity (numeric value or `auto`)

## Auto Resolution Selection

When `--resolution auto` is specified, the skill automatically searches for the
optimal clustering resolution using bootstrap subsampling and silhouette scoring:

1. Candidate resolutions (0.4, 0.6, 0.8, 1.0, 1.2, 1.4) are evaluated.
2. For each resolution, the data is subsampled 5 times (80% of cells each).
3. Each subsample is clustered, and a co-clustering distance matrix is built.
4. The silhouette score of the full-data clustering against the co-clustering
   distances is computed.
5. The resolution with the highest silhouette score is selected.

The search results (resolution vs silhouette score) are saved as
`figures/auto_resolution_search.png` and in `result.json` under the
`auto_resolution` key.

**Example:**
```bash
python omicsclaw.py run sc-clustering --demo --resolution auto --output /tmp/clustering_auto
```

Method-specific parameters:
- `umap`: `--umap-min-dist`, `--umap-spread`
- `tsne`: `--tsne-perplexity`, `--tsne-metric`
- `diffmap`: `--diffmap-n-comps`
- `phate`: `--phate-knn`, `--phate-decay`

Typical path:
- if the object still has batch effects: `sc-preprocessing -> sc-batch-integration -> sc-clustering`
- if no batch correction is needed: `sc-preprocessing -> sc-clustering`
- after clustering, continue to `sc-markers`, `sc-cell-annotation`, or `sc-de`

Standard output:
- `processed.h5ad`
- `figures/`
- `tables/`
- `figure_data/`
- `report.md`
- `result.json`

## Workflow Position

**Upstream:** sc-preprocessing (single batch) or sc-batch-integration (multi-batch)
**Downstream:** sc-cell-annotation, sc-markers, sc-pseudotime, sc-velocity-prep, sc-cell-communication, sc-grn

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | path | — | Input AnnData file; required unless `--demo` | — |
| `--output` | path | — | Output directory (required) | — |
| `--demo` | flag | `false` | Run with built-in demo data | — |
| `--embedding-method` | enum | `umap` | Low-dimensional embedding: `umap`, `tsne`, `diffmap`, `phate` | — |
| `--cluster-method` | enum | `leiden` | Graph clustering algorithm: `leiden`, `louvain` | — |
| `--use-rep` | str | auto | Embedding key in `adata.obsm` to drive the neighbor graph (e.g. `X_pca`, `X_harmony`) | — |
| `--n-neighbors` | int | `15` | Number of nearest neighbors for the neighbor graph | Must be >= 2 |
| `--n-pcs` | int | `50` | PCA dimensions used when building the neighbor graph from `X_pca` | Must be >= 1 |
| `--resolution` | str | `1.0` | Clustering resolution; use `auto` for silhouette-based search | Must be > 0 and <= 50 when numeric |
| `--umap-min-dist` | float | `0.5` | UMAP minimum distance between embedded points (umap only) | — |
| `--umap-spread` | float | `1.0` | UMAP effective scale of embedded points (umap only) | — |
| `--tsne-perplexity` | float | `30.0` | t-SNE perplexity (tsne only) | Must be >= 1 |
| `--tsne-metric` | str | `euclidean` | Distance metric for t-SNE (tsne only) | — |
| `--diffmap-n-comps` | int | `15` | Number of diffusion map components (diffmap only) | Must be >= 2 |
| `--phate-knn` | int | `15` | Number of nearest neighbors for PHATE (phate only) | Must be >= 2 |
| `--phate-decay` | int | `40` | Alpha decay for PHATE kernel (phate only) | — |
| `--r-enhanced` | flag | `false` | Generate R Enhanced figures via ggplot2 renderers | — |

## R Enhanced Plots

| Renderer | Output file | What it shows | R packages |
|----------|-------------|---------------|------------|
| `plot_embedding_discrete` | `r_embedding_discrete.png` | Cell embedding scatter colored by cluster labels (CellDimPlot equivalent) | ggplot2, ggrepel, cowplot |
| `plot_embedding_feature` | `r_embedding_feature.png` | Cell embedding scatter with continuous feature expression overlay (FeatureDimPlot equivalent) | ggplot2, viridis, cowplot |
| `plot_cell_barplot` | `r_cell_barplot.png` | Cell count bar chart per cluster (CellStatPlot bar equivalent) | ggplot2, cowplot |
| `plot_cell_proportion` | `r_cell_proportion.png` | Cell proportion stacked bar across groups (CellStatPlot proportion equivalent) | ggplot2, cowplot |
