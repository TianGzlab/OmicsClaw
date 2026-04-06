---
doc_id: skill-guide-sc-preprocessing
title: OmicsClaw Skill Guide — SC Base Preprocessing
doc_type: method-reference
domains: [singlecell]
related_skills: [sc-preprocessing, sc-preprocess]
search_terms: [single-cell preprocessing, Scanpy preprocessing, Seurat preprocessing, SCTransform, QC filtering, HVG, PCA, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — SC Base Preprocessing

Use this guide when the user needs the **base preprocessing stage** of scRNA analysis: QC-aware filtering, normalization, HVG selection, and PCA.

## Purpose

Use this guide when you need to decide:
- whether the input is suitable for preprocessing right now
- which of `scanpy`, `pearson_residuals`, `seurat`, or `sctransform` fits the user's goal
- how to explain and tune QC, HVG, and PCA without pretending preprocessing already finished clustering

## Step 1: Inspect The Data First

Before running preprocessing, check:
- matrix state and raw-count provenance
- whether QC metrics already exist and can be reused
- whether the user has already reviewed QC distributions
- whether batch/sample structure suggests a later integration step
- whether doublets are likely to matter before downstream interpretation

Practical workflow rule:
- if the user has not looked at QC yet and does not provide filtering thresholds, prefer `sc-qc` first
- after base preprocessing, either go to `sc-batch-integration` or directly to `sc-clustering`
- do not tell users that preprocessing already completed UMAP and clustering

## Step 2: Choose The Method Deliberately

### `scanpy`
- pure Python base preprocessing
- normalized expression + HVGs + PCA
- wrapper-specific knobs: `normalization_target_sum`, `scanpy_hvg_flavor`

### `pearson_residuals`
- raw-count HVG selection plus Pearson residual modeling
- still exports a normalized public matrix plus PCA-ready object
- wrapper-specific knobs: `pearson_hvg_flavor`, `pearson_theta`

### `seurat`
- Seurat LogNormalize path up to PCA export
- use when the user explicitly wants a Seurat-style preprocessing branch
- wrapper-specific knobs: `seurat_normalize_method`, `seurat_scale_factor`, `seurat_hvg_method`

### `sctransform`
- Seurat SCTransform path up to PCA export
- use when the user explicitly wants SCTransform normalization
- wrapper-specific knob: `sctransform_regress_mt`

## Step 3: Tune Parameters In A Stable Order

Tune in this order:
1. `min_genes`
2. `max_mt_pct`
3. `min_cells`
4. `n_top_hvg`
5. `n_pcs`

These are the main first-pass controls in the current wrapper.

## Step 4: What This Skill Produces

Successful runs produce:
- normalized `processed.h5ad`
- `layers["counts"]` preserved as raw counts
- `adata.raw` preserved as a raw-count snapshot
- `obsm["X_pca"]` for downstream integration or clustering

## Step 5: Where To Go Next

- if there are multiple batches or donors: `sc-batch-integration`
- if no batch correction is needed: `sc-clustering`
- if doublets are a concern: `sc-doublet-detection`
