---
name: sc-clustering
description: >-
  Build the neighbor graph, run a low-dimensional embedding, and cluster single-cell data from a
  normalized scRNA AnnData object.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, clustering, embedding, umap, tsne, diffmap, leiden, louvain]
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
    saves_h5ad: true
    requires_preprocessed: true
    legacy_aliases: [sc-dimred-cluster]
---

# Single-Cell Clustering

This skill starts from a normalized scRNA AnnData and performs:
1. neighbor graph construction
2. low-dimensional embedding (`umap`, `tsne`, or `diffmap`)
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
- `--embedding-method`: how to render the low-dimensional view (`umap`, `tsne`, `diffmap`)
- `--cluster-method`: graph clustering backend (`leiden`, `louvain`)
- `--use-rep`: which embedding in `adata.obsm` should drive the neighbor graph
- `--n-neighbors`: local neighborhood size
- `--n-pcs`: number of PCA dimensions when the neighbor graph is built from `X_pca`
- `--resolution`: cluster granularity

Method-specific parameters:
- `umap`: `--umap-min-dist`, `--umap-spread`
- `tsne`: `--tsne-perplexity`, `--tsne-metric`
- `diffmap`: `--diffmap-n-comps`

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
