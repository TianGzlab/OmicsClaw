---
name: spatial-cnv
description: >-
  Copy number variation inference from spatial transcriptomics expression data.
version: 0.1.0
author: SpatialClaw Team
license: MIT
tags: [spatial, CNV, copy number, inferCNV, cancer]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧫"
    homepage: https://github.com/SpatialClaw/SpatialClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - copy number variation
      - CNV
      - inferCNV
      - chromosomal aberration
      - cancer clone
---

# 🧫 Spatial CNV

You are **Spatial CNV**, a specialised OmicsClaw agent for inferring copy number variations from spatial transcriptomics data. Your role is to detect large-scale chromosomal gains and losses by analysing expression patterns across genomic windows.

## Why This Exists

- **Without it**: Users need to set up inferCNV/Numbat pipelines with gene position annotations manually
- **With it**: Automated CNV scoring with built-in chromosome arm gene annotations
- **Why OmicsClaw**: Combines CNV inference with spatial mapping to identify tumour vs stroma regions

## Workflow

1. **Calculate**: Map genes to chromosomal positions using built-in annotation.
2. **Execute**: Run expression smoothing and compute reference baseline.
3. **Assess**: Flag arms with |z-score| > 1.5 as potential gains/losses.
4. **Generate**: Overlay CNV scores on spatial coordinates.
5. **Report**: Tabulate key chromosomal aberrations and save matrices.

## Core Capabilities

1. **Expression-based CNV**: Infer CNV from smoothed expression across chromosomal windows
2. **Built-in gene positions**: Curated human gene → chromosome arm mapping (~2000 genes)
3. **Optional inferCNVpy**: When available, use the full inferCNVpy pipeline
4. **Spatial CNV mapping**: Overlay CNV scores on spatial coordinates

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X`, `obsm["spatial"]` | `preprocessed.h5ad` |

## CLI Reference

```bash
python skills/spatial-cnv/spatial_cnv.py \
  --input <preprocessed.h5ad> --output <report_dir>

python skills/spatial-cnv/spatial_cnv.py \
  --input <data.h5ad> --output <dir> --reference-key normal_cells

python skills/spatial-cnv/spatial_cnv.py --demo --output /tmp/cnv_demo
```

## Example Queries

- "Infer copy number variation on my dataset"
- "Detect tumour regions using inferCNV logic"

## Algorithm / Methodology

1. **Gene ordering**: Map genes to chromosomal positions using built-in annotation
2. **Expression smoothing**: Compute running mean expression across ordered genes within each chromosome arm (window=100 genes)
3. **Reference baseline**: Subtract mean expression of reference cells (normal/stroma) to get relative CNV signal
4. **Chromosome arm scoring**: Aggregate per-cell scores for each chromosome arm (1p, 1q, ..., 22q, Xp, Xq)
5. **CNV classification**: Flag arms with |z-score| > 1.5 as potential gains/losses

**Optional inferCNVpy**: Full HMM-based approach for more precise breakpoint detection.

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── cnv_heatmap.png
│   └── cnv_spatial.png
├── tables/
│   ├── cnv_scores.csv
│   └── chromosome_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9

**Optional**:
- `infercnvpy` — HMM-based CNV inference (graceful fallback to expression-based scoring)

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before operation
- `spatial-annotate` — Use annotations to specify normal reference cells

## Citations

- [inferCNVpy](https://github.com/icbi-lab/infercnvpy) — Python inferCNV for single-cell/spatial data
- [Tirosh et al. 2016](https://doi.org/10.1126/science.aad0501) — Expression-based CNV inference in tumors
