---
name: sc-velocity
description: >-
  RNA velocity analysis for scRNA-seq using scVelo stochastic, dynamical, or
  steady-state modes. The wrapper now accepts both `--method` and `--mode` as
  public aliases for the velocity backend.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [singlecell, velocity, scvelo, latent-time, dynamics]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--mode"
      - "--n-jobs"
    param_hints:
      scvelo_stochastic:
        priority: "n_jobs"
        params: ["n_jobs"]
        defaults: {n_jobs: 4}
        requires: ["scvelo", "layers.spliced", "layers.unspliced"]
        tips:
          - "--method scvelo_stochastic or --mode stochastic: default velocity path."
      scvelo_dynamical:
        priority: "n_jobs"
        params: ["n_jobs"]
        defaults: {n_jobs: 4}
        requires: ["scvelo", "layers.spliced", "layers.unspliced"]
        tips:
          - "--method scvelo_dynamical or --mode dynamical: computes latent time when the fit succeeds."
      scvelo_steady_state:
        priority: "n_jobs"
        params: ["n_jobs"]
        defaults: {n_jobs: 4}
        requires: ["scvelo", "layers.spliced", "layers.unspliced"]
        tips:
          - "--method scvelo_steady_state or --mode steady_state: steady-state approximation path."
    saves_h5ad: true
    requires_preprocessed: true
    trigger_keywords:
      - rna velocity
      - velocity
      - scvelo
      - spliced unspliced
      - cellular dynamics
      - velovi
      - velocity pseudotime
---

# Single-Cell Velocity

## Why This Exists

- Without it: velocity analyses are hard to standardize because they require special input layers and backend-specific wording.
- With it: velocity backend selection and output naming are consistent across runs.
- Why OmicsClaw: one wrapper captures velocity figures, latent-time summaries, and method provenance.

## Scope Boundary

Implemented backends:

1. `scvelo_stochastic`
2. `scvelo_dynamical`
3. `scvelo_steady_state`

Public alias behavior:

1. `--method scvelo_dynamical`
2. `--mode dynamical`

Both point to the same backend selection logic.

## Input Contract

- Accepted input: `.h5ad`
- Required layers: `layers["spliced"]` and `layers["unspliced"]`
- Expected upstream state: normalized/preprocessed single-cell AnnData

## Workflow Summary

1. Validate scVelo availability and required layers.
2. Run the selected velocity backend.
3. Generate stream, magnitude, and optional latent-time plots.
4. Save `adata_with_velocity.h5ad`, `report.md`, and `result.json`.
5. Record both the public method id and the internal mode used.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-velocity/sc_velocity.py \
  --input <data.h5ad> --method scvelo_stochastic --output <dir>

python skills/singlecell/scrna/sc-velocity/sc_velocity.py \
  --input <data.h5ad> --mode dynamical --n-jobs 8 --output <dir>
```

## Output Contract

Successful runs write:

- `adata_with_velocity.h5ad`
- `report.md`
- `result.json`
- `figures/velocity_stream.png`
- `figures/velocity_magnitude_umap.png`
- `figures/latent_time_umap.png` when latent time is available

## Current Limitations

- This wrapper depends on spliced/unspliced layers already being present.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
