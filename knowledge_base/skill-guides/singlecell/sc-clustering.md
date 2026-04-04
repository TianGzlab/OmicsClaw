---
doc_id: skill-guide-sc-clustering
title: OmicsClaw Skill Guide — SC Clustering
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-clustering, sc-dimred-cluster]
search_terms: [single-cell clustering, leiden, louvain, UMAP, n_neighbors, resolution, 单细胞聚类]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Clustering

Use this guide when the user already has a normalized, PCA-ready single-cell object and now needs the graph / UMAP / clustering stage.

## When To Run This Skill

Recommended path:
- single batch: `sc-qc -> sc-preprocessing -> sc-clustering`
- multi batch: `sc-qc -> sc-preprocessing -> sc-batch-integration -> sc-clustering`

Do not use this skill on raw counts or before PCA has been computed.

## Input Expectations

- `X = normalized_expression`
- `obsm["X_pca"]` must exist
- if an integrated embedding exists (for example `X_harmony`, `X_scvi`, `X_scanvi`, `X_scanorama`), decide whether clustering should use that embedding instead of plain PCA

## Main Tuning Knobs

Tune in this order:
1. `n_neighbors`
2. clustering resolution
3. embedding choice (`use_rep`) when multiple embeddings exist

Guidance:
- smaller `n_neighbors` emphasizes local structure
- larger `n_neighbors` gives smoother, broader neighborhoods
- higher resolution makes more, finer clusters
- lower resolution merges clusters into coarser groups

## Output Interpretation

- `processed.h5ad` stores the updated neighbor graph, `X_umap`, and clustering labels
- `tables/cluster_summary.csv` is the first table to inspect for cluster sizes
- `figure_data/umap_points.csv` is the stable export for downstream styling or annotation plots
