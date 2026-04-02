---
name: sc-batch-integration
description: >-
  Integrate multi-sample scRNA-seq data with Harmony, scVI, scANVI, BBKNN,
  Scanorama, or supported R-backed integration methods.
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
          - "--method fastmnn: R-backed batchelor fastMNN path via the shared H5AD bridge."
      seurat_cca:
        priority: "batch_key"
        params: ["batch_key"]
        defaults: {batch_key: "batch"}
        requires: ["R_Seurat_stack"]
        tips:
          - "--method seurat_cca: R-backed Seurat CCA integration path via the shared H5AD bridge."
      seurat_rpca:
        priority: "batch_key"
        params: ["batch_key"]
        defaults: {batch_key: "batch"}
        requires: ["R_Seurat_stack"]
        tips:
          - "--method seurat_rpca: R-backed Seurat RPCA integration path via the shared H5AD bridge."
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

## Core Capabilities

1. **Multiple integration backends**: Harmony, scVI, scANVI, BBKNN, Scanorama, plus supported R-backed methods.
2. **Shared batch contract**: one `batch_key`-centric interface across Python and R paths.
3. **Standard integration gallery**: batch-colored UMAP, cluster-colored UMAP, batch-mixing heatmap, and integration metric plot.
4. **Figure-ready exports**: `figure_data/` CSVs plus a gallery manifest for downstream restyling.
5. **Downstream-ready export**: writes integrated `processed.h5ad`, tables, report, structured result JSON, README, and notebook bundle.

## Scope Boundary

Actively implemented methods in this wrapper:

1. `harmony`
2. `scvi`
3. `scanvi`
4. `bbknn`
5. `scanorama`

R-backed methods (require corresponding R packages):

1. `fastmnn`
2. `seurat_cca`
3. `seurat_rpca`

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | current direct input path |
| Demo | `--demo` | yes | bundled merged-example fallback |

### Input Expectations

- Required metadata: a batch column such as `batch`, `sample`, or `sample_id`.
- Expected state: normalized data plus PCA or data suitable for PCA recomputation.
- `harmony`, `bbknn`, and `scanorama` operate on normalized / PCA-ready representations.
- `scvi`, `scanvi`, `fastmnn`, `seurat_cca`, and `seurat_rpca` should preserve raw counts in `layers["counts"]` when available.

## Workflow

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

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | integration backend | `harmony`, `scvi`, `scanvi`, `bbknn`, `scanorama`, `fastmnn`, `seurat_cca`, or `seurat_rpca` |
| `--batch-key` | batch metadata column | core public control across all backends |
| `--n-epochs` | training/runtime control | used by `scvi` and `scanvi` |
| `--no-gpu` | force CPU execution | relevant to `scvi` / `scanvi` paths |

## Algorithm / Methodology

### Shared integration contract

Current OmicsClaw `sc-batch-integration` always:

1. validates the requested backend
2. checks that `batch_key` exists
3. runs backend-specific correction or latent-space learning
4. rebuilds neighbors and UMAP in the integrated representation
5. exports one standardized AnnData plus gallery, tables, and result JSON

### Backend groups

- **Graph / embedding correction**: `harmony`, `bbknn`, `scanorama`
- **Latent-variable models**: `scvi`, `scanvi`
- **R-backed bridges**: `fastmnn`, `seurat_cca`, `seurat_rpca`

Important implementation notes:

- `scanvi` depends on labels; when labels are absent the current wrapper can fall back to `scvi`.
- R-backed paths rely on the shared H5AD bridge rather than native Seurat object input.

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/manifest.json`
- `figure_data/manifest.json`
- `tables/integration_summary.csv`
- `tables/batch_sizes.csv`
- `reproducibility/commands.sh`

### Visualization Contract

The current standard Python gallery is recipe-based and uses:

- `overview`: UMAP colored by batch and by the active label column
- `diagnostic`: batch-mixing heatmap
- `supporting`: integration metric summary bar plot

`figure_data/` is the stable hand-off layer for downstream styling without rerunning integration.

### What Users Should Inspect First

1. `report.md`
2. `figures/umap_<batch_key>.png`
3. `figures/batch_mixing_heatmap.png`
4. `tables/integration_summary.csv`
5. `processed.h5ad`

## Current Limitations

- `fastmnn`, `seurat_cca`, and `seurat_rpca` require a working R environment with batchelor or Seurat plus the H5AD bridge packages.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
