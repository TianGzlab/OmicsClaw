---
name: spatial-deconv
description: >-
  Cell type deconvolution for spatial transcriptomics — estimates per-spot
  cell type proportions using FlashDeconv, Cell2Location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, or CARD.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [spatial, deconvolution, cell-proportion, flashdeconv, cell2location, rctd, destvi, stereoscope, tangram, spotlight, card]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--cell-type-key"
      - "--method"
      - "--n-epochs"
      - "--no-gpu"
      - "--reference"
    legacy_aliases: [deconv]
    saves_h5ad: true
    requires_preprocessed: true
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

1. **Cell2Location**: Bayesian deep learning with spatial priors (default, scvi-tools, GPU-accelerated)
2. **FlashDeconv**: Ultra-fast O(N) sketching-based deconvolution (CPU, no GPU needed)
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

## Input Matrix Convention

| Method | Main Expression Input | Requires raw counts? | Requires normalized/log? | Extra Required Inputs |
|--------|-----------------------|---------------------:|-------------------------:|-----------------------|
| **Cell2Location** | scRNA reference + spatial counts | **Yes** | No | scRNA cell types; shared genes; expected cells/spot prior |
| **FlashDeconv** | spatial + scRNA reference | **TBD (Flexible)** | **TBD** | scRNA cell type information |
| **RCTD** | scRNA counts + spatial counts | **Yes** | No | spatial coordinates; scRNA cell types; nUMI/total counts |
| **DestVI** | scRNA counts + spatial counts | **Yes** | No (model uses counts) | scRNA cell types; shared genes |
| **Stereoscope** | scRNA counts + spatial counts | **Yes** | No | scRNA cell types; shared genes |
| **Tangram** | scRNA + spatial expression | No | **Yes, typically normalized** | shared genes; training genes; scRNA cell types |
| **SPOTlight** | scRNA reference + spatial matrix | **No (Flexible)** | **Typically normalized** | marker genes/weights; scRNA cell types |
| **CARD** | scRNA counts + spatial counts | **Yes** | No | spatial coordinates; scRNA cell type & sample info |

* **Count-based models** (Cell2Location, RCTD, DestVI, Stereoscope, CARD): Strictly require **raw counts**.
* **Expression mapping / NMF** (Tangram, SPOTlight): Typically use **normalized, non-negative expression matrices**. Do not supply z-scored or scaled data containing negative values.
* **FlashDeconv**: Currently flexible; official documentation TBD. Do not harden to raw counts-only.

## CLI Reference

```bash
# Cell2Location (default, Bayesian, GPU-accelerated, requires raw counts)
oc run spatial-deconv \
  --input <spatial.h5ad> --reference <sc_ref.h5ad> --output <dir>

# FlashDeconv (ultra-fast, CPU-friendly)
oc run spatial-deconv \
  --input <file> --method flashdeconv --reference <ref.h5ad> --output <dir>

# RCTD (R-based, robust, requires raw counts)
oc run spatial-deconv \
  --input <file> --method rctd --reference <ref.h5ad> --output <dir>

# DestVI (multi-resolution VAE, requires raw counts)
oc run spatial-deconv \
  --input <file> --method destvi --reference <ref.h5ad> --output <dir>

# Stereoscope (two-stage probabilistic, requires raw counts)
oc run spatial-deconv \
  --input <file> --method stereoscope --reference <ref.h5ad> --output <dir>

# Tangram (deep learning mapping, expects normalized non-negative matrices)
oc run spatial-deconv \
  --input <file> --method tangram --reference <ref.h5ad> --output <dir>

# SPOTlight (NMF-based, R-based)
oc run spatial-deconv \
  --input <file> --method spotlight --reference <ref.h5ad> --output <dir>

# CARD (spatial correlation, R-based, requires raw counts)
oc run spatial-deconv \
  --input <file> --method card --reference <ref.h5ad> --output <dir>

# Demo (runs internal simulation pipeline)
oc run spatial-deconv --demo --output /tmp/deconv_demo

# --- Direct Script Execution (Alternative) ---
python skills/spatial/spatial-deconv/spatial_deconv.py --demo --output /tmp/deconv_demo
python skills/spatial/spatial-deconv/spatial_deconv.py --input <file> --reference <ref.h5ad> --method rctd --output <dir>
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
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy, anndata, numpy, pandas, scipy, matplotlib

**Optional**:
- `flashdeconv` — FlashDeconv ultra-fast sketching
- `cell2location` + `scvi-tools` — Cell2Location Bayesian method
- `scvi-tools` + `torch` — DestVI and Stereoscope (GPU-accelerated)
- `tangram-sc` — Tangram mapping (GPU-accelerated)
- `R environment` + packages `spacexr`, `SPOTlight`, `CARD` — Executed as isolated memory-safe subprocesses via OmicsClaw `RScriptRunner` (no `rpy2` required)

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
- [FlashDeconv](https://www.biorxiv.org/content/10.64898/2025.12.22.696108v2) — Preprint, *bioRxiv*
- [RCTD](https://doi.org/10.1038/s41587-021-00830-w) — Cable et al., *Nat Biotechnol* 2022
- [DestVI](https://doi.org/10.1038/s41587-022-01272-8) — Lopez et al., *Nat Biotechnol* 2022
- [Stereoscope](https://doi.org/10.1038/s42003-020-01247-y) — Andersson et al., *Commun Biol* 2020
- [Tangram](https://doi.org/10.1038/s41592-021-01264-7) — Biancalani et al., *Nat Methods* 2021
- [SPOTlight](https://doi.org/10.1093/nar/gkab043) — Elosua-Bayes et al., *Nucleic Acids Res* 2021
- [CARD](https://doi.org/10.1038/s41587-022-01273-7) — Ma & Zhou, *Nat Biotechnol* 2022
