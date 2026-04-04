---
name: sc-preprocessing
description: >-
  Base scRNA preprocessing after QC: QC-aware filtering, normalization,
  highly variable gene selection, and PCA.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, preprocessing, qc, normalization, hvg, pca]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--min-genes"
      - "--min-cells"
      - "--max-mt-pct"
      - "--n-top-hvg"
      - "--n-pcs"
    param_hints:
      scanpy:
        priority: "min_genes/max_mt_pct -> n_top_hvg -> n_pcs"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000, n_pcs: 50}
        requires: ["raw_counts", "scanpy"]
        tips:
          - "--method scanpy: Python-native base preprocessing up to PCA."
          - "Use `sc-clustering` after this if batch integration is not needed."
      seurat:
        priority: "min_genes/max_mt_pct -> n_top_hvg -> n_pcs"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000, n_pcs: 50}
        requires: ["raw_counts", "Rscript", "Seurat", "SingleCellExperiment", "zellkonverter"]
        tips:
          - "--method seurat: R-backed LogNormalize workflow up to PCA export."
      sctransform:
        priority: "max_mt_pct -> n_top_hvg -> n_pcs"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 3000, n_pcs: 50}
        requires: ["raw_counts", "Rscript", "Seurat", "SingleCellExperiment", "zellkonverter", "sctransform"]
        tips:
          - "--method sctransform: R-backed SCTransform workflow up to PCA export."
      pearson_residuals:
        priority: "min_genes/max_mt_pct -> n_top_hvg -> n_pcs"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000, n_pcs: 50}
        requires: ["raw_counts", "scanpy"]
        tips:
          - "--method pearson_residuals: raw-count HVG selection plus Pearson residual modeling, while exporting a normalized public matrix and PCA."
    legacy_aliases: [sc-preprocess]
    saves_h5ad: true
    requires_preprocessed: false
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "🧫"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - single cell preprocess
      - scRNA preprocessing
      - normalize hvg pca
      - base preprocessing
      - Seurat preprocessing
      - SCTransform preprocessing
---

# 🧫 Single-Cell Base Preprocessing

This skill is the **base preprocessing stage** for scRNA data. It stops at a normalized, PCA-ready object so that users can choose the next branch explicitly:
- go to `sc-batch-integration` if multiple batches need correction
- or go directly to `sc-clustering` if batch correction is not needed

## Why This Exists

- Without it: users manually chain QC-aware filtering, normalization, HVG selection, and PCA with inconsistent defaults.
- With it: one run produces a stable normalized, PCA-ready AnnData plus standard OmicsClaw outputs.
- Why OmicsClaw: the wrapper reuses shared single-cell canonicalization, QC, and filtering logic, and keeps a stable downstream contract.

## Scope Boundary

Implemented methods:
1. `scanpy`
2. `seurat`
3. `sctransform`
4. `pearson_residuals`

This skill does:
1. reuse existing QC state when available, otherwise compute the minimum needed QC metrics
2. filter cells and genes through the shared filtering logic
3. normalize or transform the expression matrix
4. select highly variable genes
5. compute PCA
6. export a normalized, PCA-ready `processed.h5ad`

This skill does not:
1. remove ambient RNA
2. remove doublets
3. perform batch integration
4. build the final neighbor graph, UMAP, or clusters
5. annotate cells or run DE

## Input Expectations

- preferred input: raw-count-like AnnData or a QC-annotated count-oriented object
- if QC metrics already exist, they are reused instead of recomputed
- if the user has not reviewed QC yet and does not provide filtering thresholds, the recommended path is `sc-qc` first
- the public output contract is:
  - `X = normalized_expression`
  - `layers["counts"] = raw_counts`
  - `adata.raw = raw_counts_snapshot`
  - `obsm["X_pca"]` available for downstream `sc-clustering` or `sc-batch-integration`

## Workflow

1. Load input through the shared single-cell loader.
2. Preflight the matrix state, QC state, and method-specific requirements.
3. Reuse existing QC metrics or canonicalize count-like input and compute the minimum needed QC metrics.
4. Apply shared cell/gene filtering.
5. Run the selected normalization / transformation backend.
6. Select HVGs and compute PCA.
7. Export `processed.h5ad`, figures, tables, `figure_data/`, `report.md`, and `result.json`.

## Downstream Branching

After this skill:
- if batch/sample effects are expected: run `sc-batch-integration`
- otherwise: run `sc-clustering`
- if doublets are a concern, run `sc-doublet-detection` before interpreting downstream results

## Output Contract

Successful runs write:
- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/manifest.json`
- `figure_data/manifest.json`
- `tables/preprocess_summary.csv`
- `tables/hvg_summary.csv`
- `tables/pca_variance_ratio.csv`
- `tables/pca_embedding.csv`
- `tables/qc_metrics_per_cell.csv`
