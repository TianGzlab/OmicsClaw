---
name: spatial-integrate
description: >-
  Multi-sample integration and batch correction for spatial transcriptomics data.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [spatial, integration, batch correction, Harmony, BBKNN, Scanorama]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--batch-key"
      - "--method"
    legacy_aliases: [integrate]
    saves_h5ad: true
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
- **With it**: Automated batch correction with multiple method options producing a corrected joint embedding
- **Why OmicsClaw**: Handles the full integration pipeline from multi-sample h5ad to corrected UMAP

## Workflow

1. **Calculate**: Prepare modalities and sequence representations.
2. **Execute**: Run chosen integration mechanism across sample blocks.
3. **Assess**: Quantify batch mixing versus bio-preservation.
4. **Generate**: Save corrected spatial matrices and compute merged UMAP.
5. **Report**: Synthesize report with mixing scoring metadata.

## Core Capabilities

1. **Harmony integration**: PCA-based iterative correction — fast, robust, always available via `harmonypy`
2. **BBKNN**: Batch-balanced k-nearest neighbours — lightweight, modifies the neighbour graph
3. **Scanorama**: Panoramic stitching via mutual nearest neighbours — optional
4. **PCA fallback**: When no integration library is available, re-compute PCA and flag batch in metadata

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

## CLI Reference

```bash
# Standard usage (Harmony, default)
oc run spatial-integrate --input <merged.h5ad> --output <dir> --batch-key sample_id

# Specify integration method (e.g. Scanorama)
oc run spatial-integrate --input <data.h5ad> --output <dir> --method scanorama --batch-key batch

# Demo mode
oc run spatial-integrate --demo
```

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
5. **Reference**: Korsunsky et al., *Nature Methods* 2019

### BBKNN

1. **Input**: `adata.obsm["X_pca"]` + `adata.obs[batch_key]`
2. **Algorithm**: Constructs a batch-balanced k-nearest-neighbor graph from PCA space (replaces standard graph)
3. **Output**: Modified `adata.obsp["connectivities"]` and `adata.obsp["distances"]`
4. **Post-processing**: Recomputes UMAP from corrected graph
5. **Reference**: Polanski et al., *Bioinformatics* 2020

### Scanorama

1. **Input**: `adata.obsm["X_pca"]` (via scanpy wrapper) + `adata.obs[batch_key]`
2. **Algorithm**: Mutual nearest neighbor stitching across batches (panoramic alignment)
3. **Output**: Corrected embedding stored in `adata.obsm["X_scanorama"]`
4. **Post-processing**: Recomputes neighbors and UMAP from corrected embedding
5. **Note**: The original Scanorama operates on expression matrices; the scanpy wrapper uses PCA for efficiency
6. **Reference**: Hie et al., *Nature Biotechnology* 2019

**Key parameters**:
- `--batch-key`: obs column identifying batches (default: batch)
- `--method`: harmony, bbknn, or scanorama (default: harmony)

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── umap_before.png
│   ├── umap_after.png
│   └── batch_mixing.png
├── tables/
│   └── integration_metrics.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9

**Optional**:
- `harmonypy` — Harmony integration (recommended, lightweight)
- `bbknn` — batch-balanced KNN
- `scanorama` — panoramic stitching

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
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
