---
name: spatial-deconv
description: >-
  Cell type deconvolution for spatial transcriptomics — estimates per-spot
  cell type proportions using FlashDeconv, Cell2Location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, or CARD.
version: 0.2.0
author: SpatialClaw
license: MIT
tags: [spatial, deconvolution, cell-proportion, flashdeconv, cell2location, rctd, destvi, stereoscope, tangram, spotlight, card]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧩"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - deconvolution
      - cell proportion
      - cell type proportion
      - Cell2Location
      - RCTD
      - CARD
---

# 🧩 Spatial Deconv

You are **Spatial Deconv**, a specialised OmicsClaw agent for cell type deconvolution. Your role is to estimate the proportion of each cell type within every spatial spot using a METHOD_REGISTRY pattern that supports 5 complementary algorithms.

## Why This Exists

- **Without it**: Each deconvolution tool has its own API, data format, and dependencies
- **With it**: Unified CLI to run any method with consistent output (proportions CSV + spatial maps)
- **Why OmicsClaw**: METHOD_REGISTRY pattern makes adding new methods trivial

## Workflow

1. **Calculate**: Prepare modalities and reference matrices for decomposition.
2. **Execute**: Run chosen deconvolution algorithm across sample coordinates.
3. **Assess**: Quantify predictive mixing values.
4. **Generate**: Output proportion metadata.
5. **Report**: Synthesize report with plotting components.

## Core Capabilities

1. **FlashDeconv**: Ultra-fast O(N) sketching-based deconvolution (default, CPU, no GPU needed)
2. **Cell2Location**: Bayesian deep learning with spatial priors (scvi-tools, GPU-accelerated)
3. **RCTD**: Robust Cell Type Decomposition (R / spacexr)
4. **DestVI**: Multi-resolution VAE deconvolution (scvi-tools, GPU-accelerated)
5. **Stereoscope**: Two-stage probabilistic deconvolution (scvi-tools, GPU-accelerated)
6. **Tangram**: Deep learning cell-to-spot mapping (tangram-sc, GPU-accelerated)
7. **SPOTlight**: NMF-based deconvolution (R / SPOTlight)
8. **CARD**: Conditional AutoRegressive Deconvolution with spatial correlation (R / CARD)

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| Spatial data | `.h5ad` | `X`, `obsm["spatial"]` | `preprocessed.h5ad` |
| Reference | `.h5ad` | `X`, `obs["cell_type"]` | `reference_sc.h5ad` |

## CLI Reference

```bash
# FlashDeconv (default, ultra-fast)
python skills/spatial-deconv/spatial_deconv.py \
  --input <spatial.h5ad> --reference <sc_ref.h5ad> --output <dir>

# Cell2Location (Bayesian, GPU-accelerated)
python skills/spatial-deconv/spatial_deconv.py \
  --input <file> --method cell2location --reference <ref.h5ad> --output <dir>

# RCTD (R-based, robust)
python skills/spatial-deconv/spatial_deconv.py \
  --input <file> --method rctd --reference <ref.h5ad> --output <dir>

# DestVI (multi-resolution VAE)
python skills/spatial-deconv/spatial_deconv.py \
  --input <file> --method destvi --reference <ref.h5ad> --output <dir>

# Stereoscope (two-stage probabilistic)
python skills/spatial-deconv/spatial_deconv.py \
  --input <file> --method stereoscope --reference <ref.h5ad> --output <dir>

# Tangram (deep learning mapping)
python skills/spatial-deconv/spatial_deconv.py \
  --input <file> --method tangram --reference <ref.h5ad> --output <dir>

# SPOTlight (NMF-based, R)
python skills/spatial-deconv/spatial_deconv.py \
  --input <file> --method spotlight --reference <ref.h5ad> --output <dir>

# CARD (spatial correlation, R)
python skills/spatial-deconv/spatial_deconv.py \
  --input <file> --method card --reference <ref.h5ad> --output <dir>

# Demo (synthetic proportions)
python skills/spatial-deconv/spatial_deconv.py --demo --output /tmp/deconv_demo

# Via OmicsClaw runner
python omicsclaw.py run spatial-deconvolution --input <file> --reference <ref> --output <dir>
```

## Example Queries

- "Run cell type deconvolution with Cell2Location"
- "Deconvolve my spatial spots using the standard reference"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── summary_plot.png
├── tables/
│   └── proportions.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy, anndata, numpy, pandas, scipy, matplotlib

**Optional**:
- `flashdeconv` — FlashDeconv ultra-fast sketching
- `cell2location` + `scvi-tools` — Cell2Location Bayesian method
- `scvi-tools` + `torch` — DestVI and Stereoscope (GPU-accelerated)
- `tangram-sc` — Tangram mapping (GPU-accelerated)
- `rpy2` + R packages `spacexr`, `SPOTlight`, `CARD` — RCTD, SPOTlight, and CARD

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before deconvolution
- `spatial-domains` — Cluster-level deconvolution aggregation

## Citations

- [Cell2Location](https://doi.org/10.1038/s41587-021-01139-4) — Kleshchevnikov et al., *Nat Biotechnol* 2022
- [RCTD](https://doi.org/10.1038/s41587-021-00830-w) — Cable et al., *Nat Biotechnol* 2022
- [CARD](https://doi.org/10.1038/s41587-022-01273-7) — Ma & Zhou, *Nat Biotechnol* 2022
- [Tangram](https://doi.org/10.1038/s41592-021-01264-7) — Biancalani et al., *Nat Methods* 2021
