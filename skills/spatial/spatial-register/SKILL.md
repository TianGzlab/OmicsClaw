---
name: spatial-register
description: >-
  Spatial registration and multi-slice alignment for spatial transcriptomics data.
version: 0.2.0
author: SpatialClaw Team
license: MIT
tags: [spatial, registration, alignment, PASTE, STalign, multi-slice]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "📐"
    homepage: https://github.com/zhou-1314/OmicsClaw
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

1. **Procrustes alignment**: Built-in SVD-based Procrustes transform — always available, no extra deps
2. **Expression-weighted**: Weight coordinate matching by shared gene expression patterns
3. **Optional PASTE**: When `paste-bio` is available, use optimal transport for probabilistic alignment
4. **Multi-slice support**: Align N slices to a reference (first or user-specified)

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (multi-slice) | `.h5ad` | `X`, `obsm["spatial"]`, `obs[slice_key]` | `serial_sections.h5ad` |

## CLI Reference

```bash
python skills/spatial-register/spatial_register.py \
  --input <multi_slice.h5ad> --output <dir>

python skills/spatial-register/spatial_register.py \
  --input <data.h5ad> --output <dir> --method paste --reference-slice slice_1

python skills/spatial-register/spatial_register.py --demo --output /tmp/register_demo
```

## Example Queries

- "Align my serial tissue sections using PASTE"
- "Register these spatial slices via Procrustes"

## Algorithm / Methodology

1. **Validate**: Ensure spatial coordinates and slice labels exist
2. **Reference selection**: Use provided reference slice or the first slice
3. **Procrustes (built-in)**: For each non-reference slice, compute optimal rotation + scaling + translation via SVD to minimise coordinate distances to reference
4. **Optional PASTE**: Use optimal transport with expression cost for probabilistic alignment
5. **Update coordinates**: Store aligned coordinates in `obsm["spatial_aligned"]`

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
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9
- `scipy` >= 1.7

**Optional**:
- `paste-bio` — PASTE optimal transport registration
- `POT` — Python Optimal Transport (used by PASTE)

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
