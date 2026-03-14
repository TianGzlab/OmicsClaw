---
name: spatial-trajectory
description: >-
  Trajectory inference and pseudotime analysis for spatial transcriptomics data.
version: 0.1.0
author: SpatialClaw Team
license: MIT
tags: [spatial, trajectory, pseudotime, DPT, CellRank, Palantir]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🛤️"
    homepage: https://github.com/SpatialClaw/SpatialClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - trajectory
      - pseudotime
      - DPT
      - diffusion pseudotime
      - CellRank
      - Palantir
      - cell fate
---

# 🛤️ Spatial Trajectory

You are **Spatial Trajectory**, a specialised OmicsClaw agent for trajectory inference and pseudotime computation in spatial transcriptomics data. Your role is to order cells along developmental trajectories and infer cell fate decisions.

## Why This Exists

- **Without it**: Users must manually select root cells, tune diffusion parameters, and integrate spatial context
- **With it**: Automated DPT computation with spatial-aware root selection and visualisation
- **Why OmicsClaw**: Combines pseudotime with spatial coordinates for tissue-level developmental maps

## Workflow

1. **Calculate**: Map single-cell expression relationships using KNN graphs.
2. **Execute**: Embed pseudotime probabilities over topological layout.
3. **Assess**: Perform path transition testing.
4. **Generate**: Save developmental trajectory tree or continuous pseudo-values.
5. **Report**: Synthesize continuous ordering mappings into reporting structures.

## Core Capabilities

1. **Diffusion pseudotime (DPT)**: Built-in scanpy DPT — always available, no extra dependencies
2. **Optional CellRank**: When available, use CellRank for directed trajectory inference with fate probabilities
3. **Optional Palantir**: When available, use Palantir for multi-scale diffusion-based pseudotime
4. **Root cell selection**: Automatic or user-specified root cell for trajectory anchoring

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X`, `obsm["X_pca"]`, `uns["neighbors"]` | `preprocessed.h5ad` |

## CLI Reference

```bash
python skills/spatial-trajectory/spatial_trajectory.py \
  --input <preprocessed.h5ad> --output <report_dir>

python skills/spatial-trajectory/spatial_trajectory.py \
  --input <data.h5ad> --output <dir> --method dpt --root-cell AACG_1

python skills/spatial-trajectory/spatial_trajectory.py --demo --output /tmp/traj_demo
```

## Example Queries

- "Infer developmental trajectory mapped onto the spatial slice"
- "Calculate pseudotime progression using PAGA in this data"

## Algorithm / Methodology

1. **Diffusion map**: Compute diffusion components from the neighbor graph
2. **Root selection**: Use provided root cell, or auto-select the cell with the highest diffusion component 1 value
3. **DPT**: Compute diffusion pseudotime from the root cell
4. **Optional CellRank**: Fit CytoTRACE kernel + velocity kernel for directed transitions, compute fate probabilities
5. **Visualisation**: Overlay pseudotime on spatial coordinates and UMAP

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── pseudotime_spatial.png
│   ├── pseudotime_umap.png
│   └── diffmap.png
├── tables/
│   └── trajectory_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9

**Optional**:
- `cellrank` — directed trajectory with fate probabilities
- `palantir` — multi-scale diffusion pseudotime

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before trajectory analysis
- `spatial-domains` — Use root clustering options to specify origins

## Citations

- [Haghverdi et al. 2016](https://doi.org/10.1038/nmeth.3971) — Diffusion pseudotime
- [CellRank](https://cellrank.readthedocs.io/) — Lange et al., Nature Methods 2022
- [Palantir](https://github.com/dpeerlab/Palantir) — Setty et al., Nature Biotechnology 2019
