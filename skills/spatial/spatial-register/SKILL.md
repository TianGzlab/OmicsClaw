---
name: spatial-register
description: >-
  Spatial registration and multi-slice alignment for spatial transcriptomics data.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [spatial, registration, alignment, PASTE, STalign, multi-slice]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--method"
      - "--reference-slice"
    legacy_aliases: [register]
    saves_h5ad: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "📐"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - spatial registration
      - slice alignment
      - PASTE
      - STalign
      - multi-slice
      - coordinate alignment
---

# 📐 Spatial Register

You are **Spatial Register**, a specialised OmicsClaw agent for spatial registration and multi-slice alignment. Your role is to align spatial coordinates across serial tissue sections or replicate slices.

## Why This Exists

- **Without it**: Users must manually align coordinates across slices using external tools
- **With it**: Automated Procrustes / affine alignment with gene-expression-aware registration
- **Why OmicsClaw**: Combines coordinate geometry with expression similarity for robust registration

## Workflow

1. **Calculate**: Evaluate geometric coordinates for consecutive slices.
2. **Execute**: Deploy probabilistic alignment computing overlap dynamics.
3. **Assess**: Check alignment fidelity indices.
4. **Generate**: Register layers with new bounding coordinates.
5. **Report**: Synthesize report with alignment errors logic.

## Core Capabilities

1. **PASTE registration**: Optimal transport alignment — aligns N slices to a reference using gene-expression-aware probabilistic transport maps (Zeira et al., *Nature Methods* 2022)
2. **STalign registration**: Diffeomorphic mapping via LDDMM — pairwise registration that rasterizes coordinates into images and computes smooth deformation fields (Clifton et al., *Nature Communications* 2023)
3. **Expression-weighted**: Optionally weight alignment by shared gene expression patterns
4. **Multi-slice support**: PASTE supports N slices; STalign handles pairwise registration

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (multi-slice) | `.h5ad` | `X` (expression), `obsm["spatial"]` (coordinates), `obs[slice_key]` | `serial_sections.h5ad` |

### Method-Specific Input Requirements

Both methods require **expression matrix + spatial coordinates** — neither
works on coordinates alone:

| Method | Primary inputs consumed | How expression is used | How coordinates are used |
|--------|----------------------|----------------------|------------------------|
| **PASTE** | `adata.X` (expression) + `obsm["spatial"]` (coords) | Optimal-transport cost combines expression dissimilarity with spatial distance; slices are auto-normalized (`normalize_total` + `log1p`) and subset to common genes | Reference coordinates for transport mapping |
| **STalign** | `adata.X` (expression) + `obsm["spatial"]` (coords) | Expression signal (PC1 of common genes) is rasterized into image intensity for LDDMM; uniform intensity if `--use-expression` is not set | Rasterized to 2-D grid positions for image-based registration |

> **PASTE = expression + coordinates**: PASTE computes a probabilistic
> transport plan from a cost matrix that weighs both gene-expression
> dissimilarity and spatial distance.  The official tutorial normalizes
> each slice and subsets to shared genes before alignment.
>
> **STalign = coordinates + signal matrix**: STalign rasterizes each
> slice's point cloud into a 2-D image, where pixel intensity comes from
> a signal matrix (expression features or uniform).  The official API
> supports passing a full signal matrix `G` (X, Y coords + gene expression);
> this implementation uses PC1 of shared genes as a single-channel signal
> for the LDDMM image path.

## CLI Reference

```bash
# PASTE alignment (multi-slice, default)
oc run spatial-register --input <multi_slice.h5ad> --output <dir>
oc run spatial-register --input <data.h5ad> --method paste --reference-slice "slice_1" --output <dir>

# STalign diffeomorphic registration (pairwise only)
oc run spatial-register --input <two_slices.h5ad> --method stalign --output <dir>
oc run spatial-register --input <data.h5ad> --method stalign \
  --stalign-niter 3000 --stalign-image-size 600 --stalign-a 800 --use-expression --output <dir>

# Demo mode
oc run spatial-register --demo
```

## Example Queries

- "Align my serial tissue sections using PASTE"
- "Register two spatial slices with STalign"
- "Use diffeomorphic mapping to warp my source slice onto the target"

## Algorithm / Methodology

### PASTE (default, multi-slice)

1. **Validate**: Ensure spatial coordinates and slice labels exist (>=2 slices)
2. **Common gene intersection**: Find shared genes across all slices
3. **Normalize**: Subset each slice to common genes, apply `normalize_total` + `log1p` (following the [paste-bio tutorial](https://paste-bio.readthedocs.io/en/latest/tutorial.html))
4. **Reference selection**: Use provided reference slice or the first slice
5. **Optimal transport**: For each non-reference slice, `pst.pairwise_align()` computes a transport plan from a cost that combines **expression dissimilarity + spatial distance**
6. **Coordinate mapping**: Transform source coordinates via the transport matrix
7. **Output**: Aligned coordinates in `obsm["spatial_aligned"]`

**Key parameters**:
- `--reference-slice`: Label of the fixed slice (default: first)

Source: Zeira et al., *Nature Methods* 2022.

### STalign (pairwise)

1. **Validate**: Exactly 2 slices required
2. **Signal preparation**: When `--use-expression` is set, compute PC1 of common genes as per-spot intensity signal (preserves dominant transcriptomic variation); otherwise use uniform weights
3. **Rasterization**: Convert each slice's point cloud (coordinates + signal) to a 2-D image via Gaussian-smoothed accumulation on a regular grid
4. **LDDMM**: Run Large Deformation Diffeomorphic Metric Mapping to compute a smooth deformation field from source image to target image
5. **Coordinate transform**: Apply learned diffeomorphism to warp source spot coordinates
6. **Output**: Warped coordinates in `obsm["spatial_aligned"]`

**Key parameters**:
- `--stalign-image-size`: Raster resolution (default: 400)
- `--stalign-niter`: LDDMM iterations (default: 2000)
- `--stalign-a`: Kernel bandwidth — larger = smoother warp (default: 500)
- `--use-expression`: Use expression-derived signal (PC1) as raster intensity

Source: Clifton et al., *Nature Communications* 2023.

### Method Selection Guide

| Scenario | Recommended method |
|----------|-------------------|
| ≥3 serial sections | PASTE (multi-slice OT) |
| 2 slices, coordinate deformation | STalign (LDDMM) |
| Large expression similarity | PASTE (expression-aware transport) |
| Tissue with complex morphology | STalign (flexible diffeomorphism) |

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── slices_before.png
│   └── slices_after.png
├── tables/
│   └── registration_metrics.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9
- `scipy` >= 1.7
- `numpy`, `pandas`, `matplotlib`

**Optional**:
- `paste-bio` — PASTE optimal transport registration
- `POT` — Python Optimal Transport (used by PASTE)
- `STalign` — Diffeomorphic LDDMM registration (requires PyTorch)
- `torch` — PyTorch (used by STalign)

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before registration
- `spatial-integrate` — Additional sequence integration mapping

## Citations

- [PASTE](https://github.com/raphael-group/paste) — Zeira et al., Nature Methods 2022
- [STalign](https://github.com/JEFworks-Lab/STalign) — Clifton et al., Nature Communications 2023
