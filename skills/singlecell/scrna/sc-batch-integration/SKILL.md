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
    - "--n-latent"
    - "--labels-key"
    - "--harmony-theta"
    - "--bbknn-neighbors-within-batch"
    - "--scanorama-knn"
    - "--integration-features"
    - "--integration-pcs"
    - "--simba-n-top-genes"
    - "--simba-n-components"
    - "--simba-k"
    - "--simba-num-workers"
    - "--r-enhanced"
    param_hints:
      harmony:
        priority: "batch_key"
        params: ["batch_key"]
        advanced_params: ["harmony_theta", "integration_pcs"]
        defaults: {batch_key: "batch", harmony_theta: 2.0, integration_pcs: 50}
        requires: ["existing_PCA_or_computeable_PCA", "harmonypy"]
        tips:
        - "--method harmony: Default integration path in the current wrapper."
      scvi:
        priority: "batch_key -> n_epochs -> no_gpu"
        params: ["batch_key", "n_epochs"]
        advanced_params: ["n_latent", "no_gpu"]
        defaults: {batch_key: "batch", n_epochs: 400, n_latent: 30, no_gpu: false}
        requires: ["scvi", "torch"]
        tips:
        - "--n-epochs: Main runtime/optimization knob for scVI."
      scanvi:
        priority: "batch_key -> n_epochs -> no_gpu"
        params: ["batch_key", "labels_key", "n_epochs"]
        advanced_params: ["n_latent", "no_gpu"]
        defaults: {batch_key: "batch", labels_key: null, n_epochs: 200, n_latent: 30,
          no_gpu: false}
        requires: ["scvi", "torch", "labels_in_obs"]
        tips:
        - "If no labels are available, the current wrapper falls back to `scvi`."
      bbknn:
        priority: "batch_key"
        params: ["batch_key"]
        advanced_params: ["bbknn_neighbors_within_batch"]
        defaults: {batch_key: "batch", bbknn_neighbors_within_batch: 3}
        requires: ["bbknn", "existing_PCA_or_computeable_PCA"]
        tips:
        - "--method bbknn: Lightweight graph correction path."
      scanorama:
        priority: "batch_key"
        params: ["batch_key"]
        advanced_params: ["scanorama_knn"]
        defaults: {batch_key: "batch", scanorama_knn: 20}
        requires: ["scanorama"]
        tips:
        - "--method scanorama: Panorama-stitching integration path."
      fastmnn:
        priority: "batch_key"
        params: ["batch_key"]
        advanced_params: ["integration_features", "integration_pcs"]
        defaults: {batch_key: "batch", integration_features: 2000, integration_pcs: 30}
        requires: ["R_batchelor_stack"]
        tips:
        - "--method fastmnn: R-backed batchelor fastMNN path via the shared H5AD bridge."
      seurat_cca:
        priority: "batch_key"
        params: ["batch_key"]
        advanced_params: ["integration_features", "integration_pcs"]
        defaults: {batch_key: "batch", integration_features: 2000, integration_pcs: 30}
        requires: ["R_Seurat_stack"]
        tips:
        - "--method seurat_cca: R-backed Seurat CCA integration path via the shared
          H5AD bridge."
      seurat_rpca:
        priority: "batch_key"
        params: ["batch_key"]
        advanced_params: ["integration_features", "integration_pcs"]
        defaults: {batch_key: "batch", integration_features: 2000, integration_pcs: 30}
        requires: ["R_Seurat_stack"]
        tips:
        - "--method seurat_rpca: R-backed Seurat RPCA integration path via the shared
          H5AD bridge."
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
    script: sc_integrate.py
---

# Single-Cell Batch Integration

## Why This Exists

- Without it: technical batch structure dominates embeddings and cluster separation.
- With it: integrated representations make cross-sample comparison easier.
- Why OmicsClaw: one contract standardizes multiple integration backends and their diagnostics.

## Core Capabilities

1. **Multiple integration backends**: Harmony, scVI, scANVI, BBKNN, Scanorama, plus supported R-backed methods.
2. **Shared batch contract**: one `batch_key`-centric interface across Python and R paths.
3. **Standard integration gallery**: batch-colored UMAP plus label-aware diagnostics when stable labels already exist.
4. **Figure-ready exports**: `figure_data/` CSVs plus a gallery manifest for downstream restyling.
5. **Downstream-ready export**: writes integrated `processed.h5ad`, tables, report, structured result JSON, README, and notebook bundle.

## Scope Boundary

Actively implemented methods in this wrapper:

1. `harmony`
2. `scvi`
3. `scanvi`
4. `bbknn`
5. `scanorama`

Graph-embedding methods (require additional packages):

1. `simba` — SIMBA graph-embedding integration via PBG (requires `simba` package)

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
4. Export integration diagnostics and point the user to `sc-clustering` as the next standard step.
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
| `--n-latent` | latent dimension | used by `scvi` and `scanvi` |
| `--labels-key` | label column | used by `scanvi` |
| `--no-gpu` | force CPU execution | relevant to `scvi` / `scanvi` paths |
| `--harmony-theta` | Harmony diversity penalty | used by `harmony` |
| `--bbknn-neighbors-within-batch` | local neighbors per batch | used by `bbknn` |
| `--scanorama-knn` | panorama neighbor count | used by `scanorama` |
| `--integration-features` | integration features | used by `fastmnn`, `seurat_cca`, `seurat_rpca` |
| `--integration-pcs` | integration PCs | used by `harmony`, `fastmnn`, `seurat_cca`, `seurat_rpca` |
| `--simba-n-top-genes` | variable genes per batch | used by `simba` (default 3000) |
| `--simba-n-components` | components for edge inference | used by `simba` (default 15) |
| `--simba-k` | neighbors for edge inference | used by `simba` (default 15) |
| `--simba-num-workers` | PBG training workers | used by `simba` (default 4) |

## Algorithm / Methodology

### Shared integration contract

Current OmicsClaw `sc-batch-integration` always:

1. validates the requested backend
2. checks that `batch_key` exists
3. runs backend-specific correction or latent-space learning
4. rebuilds neighbors and UMAP in the integrated representation
5. exports one standardized AnnData plus gallery, tables, result JSON, and downstream guidance

### Backend groups

- **Graph / embedding correction**: `harmony`, `bbknn`, `scanorama`
- **Latent-variable models**: `scvi`, `scanvi`
- **R-backed bridges**: `fastmnn`, `seurat_cca`, `seurat_rpca`

Important implementation notes:

- `scanvi` depends on labels; the demo path now injects stable labels, but real inputs still need `cell_type`, `leiden`, `louvain`, or another trustworthy label column.
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

- `overview`: UMAP colored by batch and, when a stable label column already exists, by that label column
- `diagnostic`: batch-mixing heatmap when stable labels already exist
- `supporting`: integration metric summary bar plot

`figure_data/` is the stable hand-off layer for downstream styling without rerunning integration.

### What Users Should Inspect First

1. `report.md`
2. `figures/umap_<batch_key>.png`
3. `figures/batch_mixing_heatmap.png`
4. `tables/integration_summary.csv`
5. `processed.h5ad`

## Downstream Link

- After integration, the default next step is `sc-clustering`.
- Use the embedding reported in `report.md` / `result.json`, for example:
  - `sc-clustering --use-rep X_harmony`
  - `sc-clustering --use-rep X_scvi`
  - `sc-clustering --use-rep X_scanorama`
- If there is no real batch column, do not force integration; return to the standard `sc-preprocessing -> sc-clustering` path.

## Current Limitations

- `fastmnn`, `seurat_cca`, and `seurat_rpca` require a working R environment with batchelor or Seurat plus the H5AD bridge packages.
- The shared runner adds top-level README and notebook-style reproducibility artifacts when notebook export dependencies are available.

## Workflow Position

**Upstream:** sc-preprocessing (when multiple batches are present)
**Downstream:** sc-clustering

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | path | — | Input AnnData file; required unless `--demo` | — |
| `--output` | path | — | Output directory (required) | — |
| `--demo` | flag | `false` | Run with built-in demo data | — |
| `--method` | enum | `harmony` | Integration backend: `harmony`, `scvi`, `scanvi`, `bbknn`, `scanorama`, `simba`, `fastmnn`, `seurat_cca`, `seurat_rpca` | — |
| `--batch-key` | str | `batch` | Obs column containing batch/sample labels | — |
| `--n-epochs` | int | none | Training epochs (scvi, scanvi; defaults: scvi=400, scanvi=200) | — |
| `--no-gpu` | flag | `false` | Force CPU execution for scvi/scanvi | — |
| `--n-latent` | int | none | Latent space dimension (scvi, scanvi; default: 30) | — |
| `--labels-key` | str | none | Obs column with cell type labels (scanvi only) | — |
| `--harmony-theta` | float | none | Harmony diversity penalty (harmony; default: 2.0) | — |
| `--bbknn-neighbors-within-batch` | int | none | Neighbors per batch for BBKNN (bbknn; default: 3) | — |
| `--scanorama-knn` | int | none | Panorama neighbor count (scanorama; default: 20) | — |
| `--integration-features` | int | none | Number of integration features (fastmnn, seurat_cca, seurat_rpca; default: 2000) | — |
| `--integration-pcs` | int | none | Integration PCs (harmony, fastmnn, seurat_cca, seurat_rpca; default: 50/30) | — |
| `--simba-n-top-genes` | int | none | Variable genes per batch for SIMBA (simba; default: 3000) | — |
| `--simba-n-components` | int | none | Components for SIMBA edge inference (simba; default: 15) | — |
| `--simba-k` | int | none | Neighbors for SIMBA edge inference (simba; default: 15) | — |
| `--simba-num-workers` | int | none | PBG training workers for SIMBA (simba; default: 4) | — |
| `--r-enhanced` | flag | `false` | Generate R Enhanced figures via ggplot2 renderers | — |

## R Enhanced Plots

| Renderer | Output file | What it shows | R packages |
|----------|-------------|---------------|------------|
| `plot_embedding_discrete` | `r_embedding_discrete.png` | Cell embedding scatter colored by batch/cluster labels post-integration | ggplot2, ggrepel, cowplot |
| `plot_embedding_feature` | `r_embedding_feature.png` | Cell embedding scatter with continuous feature expression overlay | ggplot2, viridis, cowplot |
| `plot_cell_barplot` | `r_cell_barplot.png` | Cell count bar chart per batch/sample | ggplot2, cowplot |
| `plot_cell_sankey` | `r_cell_sankey.png` | Sankey diagram of cell type transitions across batches (CellStatPlot sankey equivalent) | ggplot2, ggalluvial, cowplot |
