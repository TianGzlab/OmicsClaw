---
name: spatial-integrate
description: >-
  Multi-sample integration and batch correction for spatial transcriptomics data
  using Harmony, BBKNN, or Scanorama.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [spatial, integration, batch correction, Harmony, BBKNN, Scanorama]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--batch-key"
      - "--method"
      - "--harmony-theta"
      - "--harmony-lambda"
      - "--harmony-max-iter"
      - "--bbknn-neighbors-within-batch"
      - "--bbknn-n-pcs"
      - "--bbknn-trim"
      - "--scanorama-knn"
      - "--scanorama-sigma"
      - "--scanorama-alpha"
      - "--scanorama-batch-size"
    param_hints:
      harmony:
        priority: "harmony_theta → harmony_lambda → harmony_max_iter"
        params: ["batch_key", "harmony_theta", "harmony_lambda", "harmony_max_iter"]
        defaults: {batch_key: "batch", harmony_theta: 2.0, harmony_lambda: 1.0, harmony_max_iter: 10}
        requires: ["obsm.X_pca", "obs.batch_key"]
        tips:
          - "--harmony-theta: Diversity penalty; raise it to encourage stronger batch mixing."
          - "--harmony-lambda: Ridge penalty; smaller values increase correction strength, while `-1` enables Harmony auto-lambda estimation."
          - "--harmony-max-iter: Maximum Harmony outer iterations before convergence."
      bbknn:
        priority: "bbknn_neighbors_within_batch → bbknn_n_pcs → bbknn_trim"
        params: ["batch_key", "bbknn_neighbors_within_batch", "bbknn_n_pcs", "bbknn_trim"]
        defaults: {batch_key: "batch", bbknn_neighbors_within_batch: 3, bbknn_n_pcs: 50, bbknn_trim: null}
        requires: ["obsm.X_pca", "obs.batch_key"]
        tips:
          - "--bbknn-neighbors-within-batch: Main integration knob controlling how many neighbors BBKNN draws from each batch."
          - "--bbknn-n-pcs: Number of PCs used to build the batch-balanced graph; OmicsClaw clamps it to the PCs actually available in `X_pca`."
          - "--bbknn-trim: Optional edge trimming after graph construction; leave unset to keep the package default."
      scanorama:
        priority: "scanorama_knn → scanorama_sigma → scanorama_alpha → scanorama_batch_size"
        params: ["batch_key", "scanorama_knn", "scanorama_sigma", "scanorama_alpha", "scanorama_batch_size"]
        defaults: {batch_key: "batch", scanorama_knn: 20, scanorama_sigma: 15.0, scanorama_alpha: 0.1, scanorama_batch_size: 5000}
        requires: ["obsm.X_pca", "obs.batch_key"]
        tips:
          - "--scanorama-knn: Number of nearest neighbors used while matching batches."
          - "--scanorama-sigma: Gaussian kernel width for smoothing Scanorama correction vectors."
          - "--scanorama-alpha: Alignment-score cutoff controlling which batch matches are accepted."
          - "--scanorama-batch-size: Incremental alignment batch size for large datasets."
    legacy_aliases: [integrate]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🔗"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - multi-sample integration
      - batch correction
      - Harmony
      - BBKNN
      - Scanorama
      - merge samples
---

# 🔗 Spatial Integrate

You are **Spatial Integrate**, a specialised OmicsClaw agent for multi-sample integration and batch effect correction. Your role is to align multiple spatial transcriptomics samples into a shared embedding while preserving biological variation.

## Why This Exists

- **Without it**: Batch effects dominate PCA/UMAP when combining samples, obscuring true biology
- **With it**: Automated batch correction with method-specific tuning guidance and reproducible output bundles
- **Why OmicsClaw**: Handles the full integration pipeline from multi-sample h5ad to corrected embeddings or graphs with consistent reports, guardrails, and wrapper-generated output guidance

## Workflow

1. **Load**: Read the preprocessed multi-sample AnnData and verify the batch column exists.
2. **Validate**: Check that PCA embeddings and upstream preprocessing outputs are available, then collect the selected method's core parameters.
3. **Integrate**: Run Harmony, BBKNN, or Scanorama on the shared latent space or graph.
4. **Re-embed**: Recompute neighbors and UMAP from the corrected representation or graph.
5. **Render the standard gallery**: build the OmicsClaw narrative gallery with overview, diagnostic, supporting, and uncertainty panels.
6. **Export figure-ready data**: write `figure_data/*.csv` and `figure_data/manifest.json` for downstream customization.
7. **Report and export**: Write `report.md`, `result.json`, `processed.h5ad`, figures, tables, and the reproducibility bundle.

## Core Capabilities

1. **Harmony integration**: PCA-based iterative correction with explicit `theta`, `lambda`, and iteration controls
2. **BBKNN**: Batch-balanced k-nearest neighbours with graph-level tuning (`neighbors_within_batch`, `n_pcs`, `trim`)
3. **Scanorama**: Panoramic stitching via mutual nearest neighbours with explicit matching and smoothing controls
4. **Standard Python gallery**: recipe-driven overview, diagnostic, supporting, and uncertainty figures under `figures/`
5. **Figure-ready data export**: `figure_data/` contains integration plotting contracts for downstream customization
6. **Integration diagnostics**: Batch mixing summary, before/after UMAP-by-batch views, entropy-based uncertainty, and structured reproducibility output
7. **Optional R visualization layer**: bundled `r_visualization/` templates consume `figure_data/` without recomputing integration results

## Visualization Contract

OmicsClaw treats `spatial-integrate` visualization as a two-layer system:

1. **Python standard gallery**: the canonical result layer. This is the default output users should inspect first.
2. **R customization layer**: an optional styling and publication layer that reads `figure_data/` and does not recompute integration results.

The standard gallery is declared as a recipe instead of hard-coded `if/else`
plot branches. Current gallery roles include:

- `overview`: before/after UMAP by batch
- `diagnostic`: UMAP by cluster and per-batch highlight panels
- `supporting`: batch-size summary
- `uncertainty`: batch-mixing entropy bars plus local entropy visualizations

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (multi-sample, preprocessed) | `.h5ad` | `X` (log-norm), `obsm["X_pca"]`, `obs[batch_key]` | `merged_samples.h5ad` |

### Unified Data Convention

After `spatial-preprocess`, the AnnData contains multiple representations.
All three integration methods require **PCA embeddings** from upstream
preprocessing (log-normalized expression → HVG selection → PCA):

```
adata.X                  # log-normalized expression
adata.obsm["X_pca"]      # PCA embeddings (from scaled HVGs) — used by all methods
adata.obs[batch_key]     # batch/sample labels (e.g., "batch", "sample_id")
adata.obsp["connectivities"]  # k-NN neighbor graph
```

### Method-Specific Input Notes

Each method consumes the preprocessed data differently:

| Method | Primary input consumed | What it operates on | Output embedding |
|--------|----------------------|---------------------|-----------------|
| **Harmony** | `obsm["X_pca"]` (PCA embeddings) | Iteratively adjusts PCs to remove batch effects | `X_pca_harmony` |
| **BBKNN** | `obsm["X_pca"]` (PCA embeddings) | Builds batch-balanced k-NN graph from PCA space | Modified `connectivities` graph |
| **Scanorama** | `obsm["X_pca"]` (via scanpy wrapper) | MNN stitching on PCA basis; original method works on expression matrices | `X_scanorama` |

> **Harmony / BBKNN**: Both operate directly on PCA embeddings.  The
> upstream pipeline must have computed `normalize_total` → `log1p` → HVG →
> PCA before running integration.  Neither method touches `adata.X`.

> **Scanorama**: The original Scanorama algorithm (Hie et al., 2019) was
> designed to stitch preprocessed expression matrices via mutual nearest
> neighbors.  The scanpy wrapper `sc.external.pp.scanorama_integrate`
> applies the same algorithm to the PCA basis for computational efficiency.
> For expression-level integration closer to the original paper, users can
> call `scanorama.integrate()` directly on per-batch HVG matrices.
>
> **Current OmicsClaw behavior**: if batches are interleaved in `adata.obs[batch_key]`,
> OmicsClaw temporarily sorts cells by batch before calling the Scanpy wrapper
> and restores the corrected embedding to the original cell order afterward.

## CLI Reference

```bash
# Standard usage (Harmony, default)
oc run spatial-integration \
  --input <merged.h5ad> --output <dir> --batch-key sample_id

# Harmony tuning
oc run spatial-integration \
  --input <data.h5ad> --method harmony --batch-key batch \
  --harmony-theta 3.0 --harmony-lambda -1 --harmony-max-iter 15 --output <dir>

# BBKNN tuning
oc run spatial-integration \
  --input <data.h5ad> --method bbknn --batch-key sample_id \
  --bbknn-neighbors-within-batch 5 --bbknn-n-pcs 30 --bbknn-trim 60 --output <dir>

# Scanorama tuning
oc run spatial-integration \
  --input <data.h5ad> --method scanorama --batch-key batch \
  --scanorama-knn 30 --scanorama-sigma 12 --scanorama-alpha 0.15 \
  --scanorama-batch-size 4000 --output <dir>

# Demo mode
oc run spatial-integration --demo

# Direct script entrypoint
python skills/spatial/spatial-integrate/spatial_integrate.py \
  --input <merged.h5ad> --method harmony --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Run Harmony to integrate my spatial slices"
- "Correct batch effects across my tissue samples"

## Algorithm / Methodology

### Shared Pipeline

1. **Validate**: Ensure batch key exists in `adata.obs` with ≥2 batches
2. **Check PCA**: Verify `X_pca` is present (from upstream preprocessing: log-normalized → HVG → PCA)
3. **Snapshot**: Save pre-integration UMAP and compute batch mixing entropy (before)
4. **Integrate**: Run selected method on PCA embeddings (see method details below)
5. **Re-embed**: Compute corrected UMAP and neighbours from integrated embedding
6. **Evaluate**: Compute batch mixing entropy (after) for quality assessment

### Harmony

1. **Input**: `adata.obsm["X_pca"]` + `adata.obs[batch_key]`
2. **Algorithm**: Iteratively adjusts principal components to align batches (soft k-means in PC space)
3. **Output**: Corrected embedding stored in `adata.obsm["X_pca_harmony"]`
4. **Post-processing**: Recomputes neighbors (k=15) and UMAP from corrected embedding
5. **Core tuning flags**:
   - `--harmony-theta`: diversity penalty
   - `--harmony-lambda`: ridge penalty (`-1` enables Harmony auto-lambda estimation)
   - `--harmony-max-iter`: maximum Harmony outer iterations
5. **Reference**: Korsunsky et al., *Nature Methods* 2019

### BBKNN

1. **Input**: `adata.obsm["X_pca"]` + `adata.obs[batch_key]`
2. **Algorithm**: Constructs a batch-balanced k-nearest-neighbor graph from PCA space (replaces standard graph)
3. **Output**: Modified `adata.obsp["connectivities"]` and `adata.obsp["distances"]`
4. **Post-processing**: Recomputes UMAP from corrected graph
5. **Core tuning flags**:
   - `--bbknn-neighbors-within-batch`: neighbors per batch
   - `--bbknn-n-pcs`: PCA dimensionality used to build the graph
   - `--bbknn-trim`: optional graph trimming
5. **Reference**: Polanski et al., *Bioinformatics* 2020

### Scanorama

1. **Input**: `adata.obsm["X_pca"]` (via scanpy wrapper) + `adata.obs[batch_key]`
2. **Algorithm**: Mutual nearest neighbor stitching across batches (panoramic alignment)
3. **Output**: Corrected embedding stored in `adata.obsm["X_scanorama"]`
4. **Post-processing**: Recomputes neighbors and UMAP from corrected embedding
5. **Core tuning flags**:
   - `--scanorama-knn`: neighbors used for batch matching
   - `--scanorama-sigma`: Gaussian kernel width
   - `--scanorama-alpha`: minimum alignment score cutoff
   - `--scanorama-batch-size`: incremental alignment batch size
6. **Note**: The original Scanorama operates on expression matrices; the scanpy wrapper uses PCA for efficiency
7. **Reference**: Hie et al., *Nature Biotechnology* 2019

**Shared key parameters**:
- `--batch-key`: obs column identifying batches (default: `batch`)
- `--method`: `harmony`, `bbknn`, or `scanorama` (default: `harmony`)

## Output Structure

```text
output_directory/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── umap_before_by_batch.png
│   ├── umap_by_batch.png
│   ├── umap_by_cluster.png
│   ├── batch_highlight.png
│   ├── batch_sizes.png
│   ├── batch_mixing.png
│   ├── batch_entropy_after_umap.png
│   ├── batch_entropy_distribution.png
│   └── manifest.json
├── figure_data/
│   ├── batch_sizes.csv
│   ├── integration_metrics.csv
│   ├── umap_before_points.csv
│   ├── umap_after_points.csv
│   ├── corrected_embedding_points.csv   # for embedding-returning methods
│   └── manifest.json
├── tables/
│   ├── integration_metrics.csv
│   ├── batch_sizes.csv
│   └── integration_observations.csv
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    └── r_visualization.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh`.

The bundled repo-side R helpers live under:

```text
skills/spatial/spatial-integrate/r_visualization/
├── README.md
└── integration_publication_template.R
```

## Dependencies

**Required**:
- `scanpy` >= 1.9

**Optional**:
- `harmonypy` — Harmony integration (recommended, lightweight)
- `bbknn` — batch-balanced KNN
- `scanorama` — panoramic stitching

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Reports follow the standard OmicsClaw reporting and disclaimer convention.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before integration
- `spatial-annotate` — Label transfer post-integration

## Citations

- [Harmony](https://github.com/immunogenomics/harmony) — Korsunsky et al., Nature Methods 2019
- [BBKNN](https://github.com/Teichlab/bbknn) — Polanski et al., Bioinformatics 2020
- [Scanorama](https://github.com/brianhie/scanorama) — Hie et al., Nature Biotechnology 2019
