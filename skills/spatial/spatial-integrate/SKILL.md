---
name: spatial-integrate
description: >-
  Multi-sample integration and batch correction for spatial transcriptomics data.
version: 0.2.0
author: SpatialClaw Team
license: MIT
tags: [spatial, integration, batch correction, Harmony, BBKNN, Scanorama]
metadata:
  omicsclaw:
    domain: spatial
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
| AnnData (multi-sample) | `.h5ad` | `X`, `obs[batch_key]` | `merged_samples.h5ad` |

## CLI Reference

```bash
python skills/spatial-integrate/spatial_integrate.py \
  --input <merged.h5ad> --output <dir> --batch-key sample_id

python skills/spatial-integrate/spatial_integrate.py \
  --input <data.h5ad> --output <dir> --method harmony --batch-key batch

python skills/spatial-integrate/spatial_integrate.py --demo --output /tmp/integrate_demo
```

## Example Queries

- "Run Harmony to integrate my spatial slices"
- "Correct batch effects across my tissue samples"

## Algorithm / Methodology

1. **Validate**: Ensure batch key exists with ≥2 batches
2. **Preprocessing**: Ensure PCA is computed (from HVGs)
3. **Integration**: Run selected method on PCA embeddings
4. **Re-embed**: Compute corrected UMAP and neighbours from integrated embedding
5. **Evaluate**: Compute batch mixing entropy and silhouette scores

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
    ├── environment.yml
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
