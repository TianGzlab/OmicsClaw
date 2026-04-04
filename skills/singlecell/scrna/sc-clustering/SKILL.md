---
name: sc-clustering
description: >-
  Build the neighbor graph, run UMAP, and cluster single-cell data from a
  normalized scRNA AnnData object.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, clustering, umap, leiden, louvain]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--cluster-method"
      - "--use-rep"
      - "--n-neighbors"
      - "--n-pcs"
      - "--resolution"
    saves_h5ad: true
    requires_preprocessed: true
    legacy_aliases: [sc-dimred-cluster]
---

# Single-Cell Clustering

This skill starts from a normalized scRNA AnnData and performs:
1. neighbor graph construction
2. UMAP
3. Leiden or Louvain clustering

Expected input:
- `processed.h5ad` from `sc-preprocessing`
- or an integrated object from `sc-batch-integration`
- `X = normalized_expression`
- `obsm["X_pca"]` or another explicit embedding chosen by `--use-rep`

Dependency note:
- `leiden` is the recommended default path.
- `louvain` is optional; if the Python package `louvain` is missing, the skill should stop and ask the user to install it explicitly rather than trying to install it automatically.

Standard output:
- `processed.h5ad`
- `figures/`
- `tables/`
- `figure_data/`
- `report.md`
- `result.json`
