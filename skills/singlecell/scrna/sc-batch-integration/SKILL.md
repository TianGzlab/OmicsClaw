---
name: sc-batch-integration
description: >-
  Integrate multi-sample scRNA-seq data with Harmony, scVI, scANVI, BBKNN, or
  Scanorama. The current wrapper also declares several R-backed methods, but
  those paths are not bundled in this build and are documented honestly below.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [singlecell, batch-integration, harmony, scvi, scanorama, bbknn]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--batch-key"
      - "--method"
      - "--n-epochs"
      - "--no-gpu"
    param_hints:
      harmony:
        priority: "batch_key"
        params: ["batch_key"]
        defaults: {batch_key: "batch"}
        requires: ["existing_PCA_or_computeable_PCA", "harmonypy"]
        tips:
          - "--method harmony: Default integration path in the current wrapper."
      scvi:
        priority: "batch_key -> n_epochs -> no_gpu"
        params: ["batch_key", "n_epochs", "no_gpu"]
        defaults: {batch_key: "batch", n_epochs: 400, no_gpu: false}
        requires: ["scvi", "torch"]
        tips:
          - "--n-epochs: Main runtime/optimization knob for scVI."
      scanvi:
        priority: "batch_key -> n_epochs -> no_gpu"
        params: ["batch_key", "n_epochs", "no_gpu"]
        defaults: {batch_key: "batch", n_epochs: 200, no_gpu: false}
        requires: ["scvi", "torch", "labels_in_obs"]
        tips:
          - "If no labels are available, the current wrapper falls back to `scvi`."
      bbknn:
        priority: "batch_key"
        params: ["batch_key"]
        defaults: {batch_key: "batch"}
        requires: ["bbknn", "existing_PCA_or_computeable_PCA"]
        tips:
          - "--method bbknn: Lightweight graph correction path."
      scanorama:
        priority: "batch_key"
        params: ["batch_key"]
        defaults: {batch_key: "batch"}
        requires: ["scanorama"]
        tips:
          - "--method scanorama: Panorama-stitching integration path."
      fastmnn:
        priority: "batch_key"
        params: ["batch_key"]
        defaults: {batch_key: "batch"}
        requires: ["R_batchelor_stack"]
        tips:
          - "Declared in metadata, but the current wrapper raises a runtime error because the R path is not bundled."
      seurat_cca:
        priority: "batch_key"
        params: ["batch_key"]
        defaults: {batch_key: "batch"}
        requires: ["R_Seurat_stack"]
        tips:
          - "Declared but not bundled in this build."
      seurat_rpca:
        priority: "batch_key"
        params: ["batch_key"]
        defaults: {batch_key: "batch"}
        requires: ["R_Seurat_stack"]
        tips:
          - "Declared but not bundled in this build."
    legacy_aliases: [sc-integrate]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - batch integration
      - batch effect
      - harmony
      - scvi
      - bbknn
      - merge samples
---

# Single-Cell Batch Integration

## Why This Exists

- Without it: technical batch structure dominates embeddings and cluster separation.
- With it: integrated representations make cross-sample comparison easier.
- Why OmicsClaw: one contract standardizes multiple integration backends and their diagnostics.

## Scope Boundary

Actively implemented methods in this wrapper:

1. `harmony`
2. `scvi`
3. `scanvi`
4. `bbknn`
5. `scanorama`

Declared but not bundled in this build:

1. `fastmnn`
2. `seurat_cca`
3. `seurat_rpca`

## Input Contract

- Accepted input: preprocessed `.h5ad`
- Required metadata: a batch column such as `batch`, `sample`, or `sample_id`
- Expected state: normalized data plus PCA or data suitable for PCA recomputation

## Workflow Summary

1. Validate batch labels and required dependencies.
2. Run the selected integration backend.
3. Rebuild neighbors/UMAP in the corrected space.
4. Export batch-mixing tables and gallery figures.
5. Write `processed.h5ad`, `report.md`, and `result.json`.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py \
  --input <merged.h5ad> --method harmony --batch-key sample_id --output <dir>

python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py \
  --input <merged.h5ad> --method scvi --batch-key sample_id \
  --n-epochs 400 --output <dir>

python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py \
  --input <merged.h5ad> --method scanorama --batch-key sample_id --output <dir>
```

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/`
- `tables/`
- `reproducibility/commands.sh`

## Current Limitations

- `fastmnn`, `seurat_cca`, and `seurat_rpca` are documented in metadata but intentionally fail at runtime in the current wrapper because their R bridge is not bundled.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
