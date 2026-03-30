---
name: spatial-trajectory
description: >-
  Trajectory inference and pseudotime analysis for spatial transcriptomics data.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [spatial, trajectory, pseudotime, DPT, CellRank, Palantir]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--method"
      - "--n-states"
      - "--root-cell"
    param_hints:
      dpt:
        priority: "root_cell"
        params: ["root_cell"]
        requires: ["obsm.X_pca", "neighbors_graph"]
      cellrank:
        priority: "root_cell → n_states"
        params: ["root_cell", "n_states"]
        defaults: {n_states: 3}
        requires: ["obsm.X_pca", "neighbors_graph"]
      palantir:
        priority: "root_cell → n_states"
        params: ["root_cell", "n_states"]
        defaults: {n_states: 3}
        requires: ["obsm.X_pca", "neighbors_graph"]
    legacy_aliases: [trajectory]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🛤️"
    homepage: https://github.com/TianGzlab/OmicsClaw
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
- **Why OmicsClaw**: Combines pseudotime with spatial coordinates, structured outputs, and wrapper-generated guides for easier trajectory interpretation

## Workflow

1. **Load**: Read the preprocessed AnnData and verify embeddings and neighbor graphs are available.
2. **Select root**: Use the provided barcode root or the wrapper's automatic root-cell heuristic.
3. **Infer trajectory**: Run DPT, CellRank, or Palantir depending on the requested method and installed dependencies.
4. **Summarize**: Generate pseudotime plots and rank genes associated with trajectory progression.
5. **Report and export**: Write `report.md`, `result.json`, `processed.h5ad`, figures, tables, and the reproducibility bundle.

## Core Capabilities

1. **Diffusion pseudotime (DPT)**: Built-in scanpy DPT — always available, no extra dependencies
2. **Root cell selection**: By specific barcode (`--root-cell`) or automatic selection (max DC1 in the current CLI wrapper)
3. **Trajectory gene correlation**: Spearman correlation with FDR correction to find pseudotime-associated genes
4. **Enhanced CellRank**: Multi-kernel support (Velocity+Connectivity, Pseudotime+Connectivity), terminal state identification, fate probabilities, driver gene detection
5. **Optional Palantir**: When available, use Palantir for multi-scale diffusion-based pseudotime

## Root Cell Selection Strategies

| Strategy | Parameter | Method | Best for |
|----------|-----------|--------|----------|
| Automatic | (default) | Max DC1 value | Quick exploration |
| By barcode | `--root-cell` | Exact cell barcode | Precise control |

## Trajectory Gene Correlation

After pseudotime computation, the system automatically identifies genes whose expression changes along the trajectory:
- **Spearman rank correlation** between each gene's expression and pseudotime
- **FDR correction** (Benjamini-Hochberg) for multiple testing
- Returns top genes with direction (increasing or decreasing along trajectory)

## CellRank Kernel Options

| Kernel combination | When to use |
|---|---|
| VelocityKernel(0.8) + ConnectivityKernel(0.2) | When RNA velocity (spliced/unspliced) data is available |
| PseudotimeKernel(0.8) + ConnectivityKernel(0.2) | When DPT pseudotime is available but not velocity |
| ConnectivityKernel only | Fallback when neither velocity nor pseudotime is available |

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X`, `obsm["X_pca"]`, `uns["neighbors"]` | `preprocessed.h5ad` |

## CLI Reference

```bash
# Standard usage (DPT, default)
oc run spatial-trajectory --input <preprocessed.h5ad> --output <report_dir>

# Explicit root cell
oc run spatial-trajectory \
  --input <data.h5ad> --output <dir> --method dpt --root-cell AACG_1

# CellRank or Palantir
oc run spatial-trajectory --input <data.h5ad> --output <dir> --method cellrank
oc run spatial-trajectory --input <data.h5ad> --output <dir> --method palantir

# Demo mode
oc run spatial-trajectory --demo --output /tmp/traj_demo

# Direct script entrypoint
python skills/spatial/spatial-trajectory/spatial_trajectory.py \
  --input <data.h5ad> --output <dir> --method dpt --root-cell AACG_1
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Infer developmental trajectory mapped onto the spatial slice"
- "Calculate pseudotime progression with CellRank in this data"

## Algorithm / Methodology

1. **Diffusion map**: Compute diffusion components from the neighbor graph
2. **Root selection**: Use provided root cell, or auto-select the cell with the highest diffusion component 1 value
3. **DPT**: Compute diffusion pseudotime from the root cell
4. **Optional CellRank**: Build velocity- or pseudotime-informed transition kernels and compute fate probabilities
5. **Visualisation**: Overlay pseudotime on spatial coordinates and UMAP

## Output Structure

```text
output_directory/
├── README.md
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
    ├── analysis_notebook.ipynb
    └── commands.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Dependencies

**Required**:
- `scanpy` >= 1.9

**Optional**:
- `cellrank` — directed trajectory with fate probabilities
- `palantir` — multi-scale diffusion pseudotime

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Reports follow the standard OmicsClaw reporting and disclaimer convention.
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
