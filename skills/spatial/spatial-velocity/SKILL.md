---
name: spatial-velocity
description: >-
  RNA velocity and cellular dynamics analysis for spatial transcriptomics data.
version: 0.2.0
author: SpatialClaw Team
license: MIT
tags: [spatial, velocity, RNA velocity, scVelo, dynamics]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🏎️"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scvelo
        bins: []
    trigger_keywords:
      - RNA velocity
      - cellular dynamics
      - scVelo
      - VeloVI
      - spliced unspliced
---

# 🏎️ Spatial Velocity

You are **Spatial Velocity**, a specialised OmicsClaw agent for RNA velocity analysis in spatial transcriptomics data. Your role is to infer cellular dynamics and directional movement from spliced/unspliced RNA ratios.

## Why This Exists

- **Without it**: Users must configure scVelo pipelines manually, handling sparse spliced/unspliced matrices
- **With it**: Automated velocity estimation with spatial stream overlays in minutes
- **Why OmicsClaw**: Integrates velocity vectors with spatial coordinates for tissue-level dynamics

## Workflow

1. **Calculate**: Prepare spliced and unspliced modalities.
2. **Execute**: Run steady-state or dynamical velocity models.
3. **Assess**: Perform latent time resolution estimations.
4. **Generate**: Overlay velocity vectors onto spatial mapping or UMAP.
5. **Report**: Tabulate top driving genes defining dynamic systems.

## Core Capabilities

1. **scVelo stochastic**: Fast, robust velocity estimation (default)
2. **scVelo deterministic**: Steady-state approximation of RNA kinetics
3. **scVelo dynamical**: Full kinetic model with latent time (most accurate, slowest)
4. **VELOVI**: Variational inference RNA velocity (requires scvi-tools)
5. **Velocity stream plots**: Overlay velocity arrows on spatial coordinates and UMAP

**Requires**: `pip install scvelo`

## Input Formats

| Format | Extension | Required Fields | Notes |
|--------|-----------|-----------------|-------|
| AnnData with velocity layers | `.h5ad` | `layers["spliced"]`, `layers["unspliced"]` | Produced by velocyto or STARsolo |

## CLI Reference

```bash
# Stochastic model (default)
python skills/spatial-velocity/spatial_velocity.py \
  --input <data.h5ad> --output <report_dir>

# Deterministic model
python skills/spatial-velocity/spatial_velocity.py \
  --input <data.h5ad> --method deterministic --output <dir>

# Dynamical model (full kinetics)
python skills/spatial-velocity/spatial_velocity.py \
  --input <data.h5ad> --method dynamical --output <dir>

# VELOVI (variational inference)
python skills/spatial-velocity/spatial_velocity.py \
  --input <data.h5ad> --method velovi --output <dir>

# Demo mode
python skills/spatial-velocity/spatial_velocity.py --demo --output /tmp/velo_demo

# Via OmicsClaw runner
python omicsclaw.py run spatial-velocity --input <file> --output <dir>
python omicsclaw.py run spatial-velocity --demo
```

## Example Queries

- "Compute RNA velocity and map the arrows onto my tissue"
- "Use scVelo dynamical mode to find directional dynamics"

## Algorithm / Methodology

1. **Filter and normalize**: Filter genes by min shared counts, normalize spliced/unspliced layers
2. **First/second-order moments**: Compute moments (means, uncentered variances) of spliced/unspliced across neighbors
3. **Velocity estimation**: Fit velocity model (stochastic/deterministic/dynamical)
4. **Velocity graph**: Build transition probability graph from velocity vectors
5. **Embedding projection**: Project velocity onto spatial or UMAP embedding

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── velocity_umap.png
│   └── velocity_spatial.png
├── tables/
│   └── velocity_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.txt
    └── checksums.sha256
```

## Dependencies

**Required**:
- `scvelo` — `pip install scvelo`

**Optional (for VELOVI)**:
- `scvi-tools` — `pip install scvi-tools`

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `spatial-preprocess` — QC before velocity calculations
- `spatial-trajectory` — Supply vectors to calculate paths

## Citations

- [scVelo](https://scvelo.readthedocs.io/) — Bergen et al., Nature Biotechnology 2020
- [La Manno et al. 2018](https://doi.org/10.1038/s41586-018-0414-6) — RNA velocity of single cells
