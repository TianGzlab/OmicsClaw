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
    - "--normalization-target-sum"
    - "--scanpy-hvg-flavor"
    - "--pearson-hvg-flavor"
    - "--pearson-theta"
    - "--seurat-normalize-method"
    - "--seurat-scale-factor"
    - "--seurat-hvg-method"
    - "--sctransform-regress-mt"
    - "--no-sctransform-regress-mt"
    - "--confirmed-preflight"
    - "--r-enhanced"
    param_hints:
      scanpy:
        priority: "min_genes/max_mt_pct -> n_top_hvg -> n_pcs"
        params: ["min_genes", "max_mt_pct", "n_top_hvg", "n_pcs"]
        advanced_params: ["min_cells", "normalization_target_sum", "scanpy_hvg_flavor"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000,
          n_pcs: 50, normalization_target_sum: 10000.0, scanpy_hvg_flavor: seurat}
        requires: ["raw_counts", "scanpy"]
        tips:
        - "--method scanpy: Python-native base preprocessing up to PCA."
        - "Use `sc-clustering` after this if batch integration is not needed."
      seurat:
        priority: "min_genes/max_mt_pct -> n_top_hvg -> n_pcs"
        params: ["min_genes", "max_mt_pct", "n_top_hvg", "n_pcs"]
        advanced_params: ["min_cells", "seurat_normalize_method", "seurat_scale_factor",
          "seurat_hvg_method"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000,
          n_pcs: 50, seurat_normalize_method: LogNormalize, seurat_scale_factor: 10000.0,
          seurat_hvg_method: vst}
        requires: ["raw_counts", "Rscript", "Seurat", "SingleCellExperiment", "zellkonverter"]
        tips:
        - "--method seurat: R-backed LogNormalize workflow up to PCA export."
      sctransform:
        priority: "max_mt_pct -> n_top_hvg -> n_pcs"
        params: ["min_genes", "max_mt_pct", "n_top_hvg", "n_pcs"]
        advanced_params: ["min_cells", "sctransform_regress_mt"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 3000,
          n_pcs: 50, sctransform_regress_mt: true}
        requires: ["raw_counts", "Rscript", "Seurat", "SingleCellExperiment", "zellkonverter",
          "sctransform"]
        tips:
        - "--method sctransform: R-backed SCTransform workflow up to PCA export."
      pearson_residuals:
        priority: "min_genes/max_mt_pct -> n_top_hvg -> n_pcs"
        params: ["min_genes", "max_mt_pct", "n_top_hvg", "n_pcs"]
        advanced_params: ["min_cells", "pearson_hvg_flavor", "pearson_theta"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000,
          n_pcs: 50, pearson_hvg_flavor: seurat_v3, pearson_theta: 100.0}
        requires: ["raw_counts", "scanpy"]
        tips:
        - "--method pearson_residuals: raw-count HVG selection plus Pearson residual
          modeling, while exporting a normalized public matrix and PCA."
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
    script: sc_preprocess.py
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

Method-specific wrapper controls:
- `scanpy`: `normalization_target_sum`, `scanpy_hvg_flavor`
- `seurat`: `seurat_normalize_method`, `seurat_scale_factor`, `seurat_hvg_method`
- `sctransform`: `sctransform_regress_mt`
- `pearson_residuals`: `pearson_hvg_flavor`, `pearson_theta`

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
- **doublet removal**: `sc-preprocessing` removes doublets automatically during filtering when `predicted_doublet` or `doublet_score` columns (from `sc-doublet-detection`) are present. Pass `--no-remove-doublets` to opt out. Run `sc-doublet-detection` → `sc-preprocessing` to activate.

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

## Workflow Position

- **Upstream step**: `sc-filter` (recommended) or directly from `sc-count` / `sc-qc`
- **Usual next step**: `sc-batch-integration` (multiple batches) or `sc-clustering` (single batch)

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | path | — | Input AnnData file (`.h5ad`); required unless `--demo` | — |
| `--output` | path | — | Output directory (required) | — |
| `--demo` | flag | `false` | Run with built-in demo data | — |
| `--method` | enum | `scanpy` | Preprocessing backend: `scanpy`, `seurat`, `sctransform`, `pearson_residuals` | — |
| `--min-genes` | int | `200` (per method default) | Minimum detected genes per retained cell | Must be >= 0 |
| `--min-cells` | int | `3` (per method default) | Minimum cells expressing a retained gene | Must be >= 0 |
| `--max-mt-pct` | float | `20.0` (per method default) | Maximum mitochondrial percentage | Must be in [0, 100] |
| `--n-top-hvg` | int | `2000` (per method default) | Number of highly variable genes to select | Must be >= 1 |
| `--n-pcs` | int | `50` (per method default) | Number of principal components | Must be >= 1 |
| `--normalization-target-sum` | float | `10000.0` | Total counts per cell after normalization (scanpy only) | Must be >= 1 |
| `--scanpy-hvg-flavor` | enum | `seurat` | HVG selection flavor: `seurat`, `cell_ranger`, `seurat_v3` (scanpy only) | — |
| `--pearson-hvg-flavor` | enum | `seurat_v3` | HVG flavor for Pearson residuals: `seurat_v3`, `seurat` (pearson_residuals only) | — |
| `--pearson-theta` | float | `100.0` | Negative binomial theta for Pearson residuals (pearson_residuals only) | — |
| `--seurat-normalize-method` | enum | `LogNormalize` | Seurat normalization method: `LogNormalize`, `CLR`, `RC` (seurat only) | — |
| `--seurat-scale-factor` | float | `10000.0` | Seurat scale factor (seurat only) | — |
| `--seurat-hvg-method` | enum | `vst` | Seurat HVG method: `vst`, `mvp`, `disp` (seurat only) | — |
| `--sctransform-regress-mt` / `--no-sctransform-regress-mt` | bool | `true` | Regress out mitochondrial percentage in SCTransform (sctransform only) | — |
| `--no-remove-doublets` | flag | off | Disable automatic doublet removal (active when `predicted_doublet` / `doublet_score` columns from `sc-doublet-detection` are present) | — |
| `--doublet-score-threshold` | float | `0.25` | Score cutoff when only `doublet_score` is available | Must be in [0, 1] |
| `--r-enhanced` | flag | `false` | Generate R Enhanced figures via ggplot2 renderers | — |

## R Enhanced Plots

| Renderer | Output file | What it shows | R packages |
|----------|-------------|---------------|------------|
| `plot_embedding_discrete` | `r_embedding_discrete.png` | Cell embedding scatter colored by discrete cluster labels (CellDimPlot equivalent) | ggplot2, ggrepel, cowplot |
| `plot_embedding_feature` | `r_embedding_feature.png` | Cell embedding scatter with continuous feature expression overlay (FeatureDimPlot equivalent) | ggplot2, viridis, cowplot |
