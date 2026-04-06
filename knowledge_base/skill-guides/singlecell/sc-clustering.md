---
doc_id: skill-guide-sc-clustering
title: OmicsClaw Skill Guide — SC Clustering
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-clustering, sc-dimred-cluster]
search_terms: [single-cell clustering, leiden, louvain, UMAP, tSNE, diffmap, n_neighbors, resolution, 单细胞聚类]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Clustering

Use this guide when the user already has a normalized, PCA-ready single-cell object and now needs the graph / embedding / clustering stage.

## When To Run This Skill

Recommended path:
- single batch: `sc-qc -> sc-preprocessing -> sc-clustering`
- multi batch: `sc-qc -> sc-preprocessing -> sc-batch-integration -> sc-clustering`

Do not use this skill on raw counts or before PCA has been computed.

## Input Expectations

- `X = normalized_expression`
- `obsm["X_pca"]` must exist
- if an integrated embedding exists (for example `X_harmony`, `X_scvi`, `X_scanvi`, `X_scanorama`), decide whether clustering should use that embedding instead of plain PCA
- choose the rendered low-dimensional view via `embedding_method` (`umap`, `tsne`, `diffmap`)

## Main Tuning Knobs

Tune in this order:
1. `n_neighbors`
2. clustering resolution
3. embedding choice (`use_rep`) when multiple embeddings exist
4. embedding method (`umap`, `tsne`, `diffmap`) for visualization

Guidance:
- smaller `n_neighbors` emphasizes local structure
- larger `n_neighbors` gives smoother, broader neighborhoods
- higher resolution makes more, finer clusters
- lower resolution merges clusters into coarser groups
- `umap` is the default first-pass view
- `tsne` is useful when the user wants a second view of local neighborhoods
- `diffmap` is useful when the user wants a smoother manifold-style embedding

## Output Interpretation

- `processed.h5ad` stores the updated neighbor graph, the selected embedding (`X_umap`, `X_tsne`, or `X_diffmap`), and clustering labels
- `tables/cluster_summary.csv` is the first table to inspect for cluster sizes
- `figure_data/embedding_points.csv` is the stable export for downstream styling or annotation plots

## Typical Next Steps

- if biological identity is still unclear: `sc-markers`
- if formal label transfer is needed: `sc-cell-annotation`
- if groups are now defined and you need statistical comparison: `sc-de`
