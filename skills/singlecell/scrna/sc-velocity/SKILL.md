---
name: sc-velocity
description: >-
  Run scVelo on a velocity-ready h5ad using stochastic, dynamical, or
  steady-state modes. Use `sc-velocity-prep` first if spliced/unspliced layers
  are missing.
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
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scvelo
        bins: []
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

## Core Capabilities

1. **Three scVelo modes**: stochastic, dynamical, and steady-state.
2. **Public alias compatibility**: both `--method` and `--mode` map into the same backend selection logic.
3. **Velocity-specific exports**: stream plot, magnitude plot, and optional latent-time view.
4. **Explicit layer contract**: requires `spliced` and `unspliced` layers before execution.
5. **Downstream-ready export**: writes `processed.h5ad`, a compatibility alias `adata_with_velocity.h5ad`, report, result JSON, README, notebook artifacts, and figure-data tables.

## Data / State Requirements

| Requirement | Where it should exist | Why it matters |
|-------------|------------------------|----------------|
| Velocity-ready layers | `layers["spliced"]`, `layers["unspliced"]` | required for every scVelo mode |
| Raw counts source | `layers["counts"]` preferred | retained for downstream provenance and matrix-contract stability |
| Embedding / graph state | `obsm["X_umap"]`, `uns["neighbors"]` preferred | improves interpretability and avoids unnecessary recomputation |

Matrix expectations:

- input object: velocity-ready single-cell AnnData
- output object: `processed.h5ad`
- `adata.X`: `normalized_expression`
- `layers["counts"]`: raw counts
- `adata.raw`: raw-count snapshot

## Scope Boundary

Implemented backends:

1. `scvelo_stochastic`
2. `scvelo_dynamical`
3. `scvelo_steady_state`

Public alias behavior:

1. `--method scvelo_dynamical`
2. `--mode dynamical`

Both point to the same backend selection logic.

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | preferred | most realistic path with velocity layers |
| Loom | `.loom` | technically loadable | useful only when spliced/unspliced layers are present |
| Shared-loader formats | `.h5`, `.csv`, `.tsv`, 10x directory | technically loadable | rarely suitable unless velocity layers survive conversion |
| Demo | `--demo` | yes | bundled fallback |

### Input Expectations

- Required layers: `layers["spliced"]` and `layers["unspliced"]`.
- Expected upstream state: normalized / preprocessed single-cell AnnData.
- Latent time should only be promised for the dynamical path when the fit succeeds.

## Workflow

1. Validate scVelo availability and required layers.
2. Run the selected velocity backend.
3. Generate stream, magnitude, and optional latent-time plots.
4. Save `processed.h5ad`, `report.md`, `result.json`, gallery manifests, and figure-data tables.
5. Record both the public method id and the internal mode used.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-velocity/sc_velocity.py \
  --input <data.h5ad> --method scvelo_stochastic --output <dir>

python skills/singlecell/scrna/sc-velocity/sc_velocity.py \
  --input <data.h5ad> --mode dynamical --n-jobs 8 --output <dir>
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | velocity backend id | accepts `scvelo_stochastic`, `scvelo_dynamical`, or `scvelo_steady_state` |
| `--mode` | scVelo-style alias | accepts `stochastic`, `dynamical`, or `steady_state` |
| `--n-jobs` | parallelism control | runtime knob for scVelo fitting |

## Algorithm / Methodology

Current OmicsClaw `sc-velocity` always:

1. validates the required spliced/unspliced layers
2. resolves the requested public alias into an internal scVelo mode
3. runs velocity estimation
4. renders stream and magnitude figures
5. writes latent-time outputs only when the chosen mode and fit actually support them

Important implementation notes:

- `scvelo_dynamical` and `mode=dynamical` point to the same backend logic.
- latent time is mode- and fit-dependent, not a guaranteed output for every run.

## Output Contract

Successful runs write:

- `processed.h5ad`
- `adata_with_velocity.h5ad`
- `report.md`
- `result.json`
- `figures/velocity_stream.png`
- `figures/velocity_magnitude_umap.png`
- `figures/velocity_magnitude_distribution.png`
- `figures/velocity_top_genes.png`
- `figures/latent_time_umap.png` when latent time is available
- `figures/latent_time_distribution.png` when latent time is available
- `figures/manifest.json`
- `figure_data/manifest.json`
- `tables/velocity_summary.csv`
- `tables/velocity_cells.csv`
- `tables/top_velocity_genes.csv`

### Visualization Contract

The current wrapper writes a standard Python gallery plus plot-ready tables:

- `figures/velocity_stream.png`
- `figures/velocity_magnitude_umap.png`
- `figures/velocity_magnitude_distribution.png`
- `figures/velocity_top_genes.png`
- `figures/latent_time_umap.png` when available
- `figures/latent_time_distribution.png` when available
- `figures/manifest.json`
- `figure_data/manifest.json`
- `tables/velocity_summary.csv`
- `tables/velocity_cells.csv`
- `tables/top_velocity_genes.csv`

### What Users Should Inspect First

1. `report.md`
2. `figures/velocity_stream.png`
3. `figures/velocity_magnitude_umap.png`
4. `figures/latent_time_umap.png` when available
5. `processed.h5ad`

## Current Limitations

- This wrapper depends on spliced/unspliced layers already being present.
- The standard OmicsClaw upstream path is now `sc-velocity-prep` -> `sc-velocity`.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.

## Safety And Guardrails

- Validate `layers['spliced']` and `layers['unspliced']` before promising any velocity run.
- Do not promise latent time for every run; it is tied to the dynamical path and successful fitting.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-velocity-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-velocity.md`.

## Environment Management

- Python extras:
  - `pip install -e ".[singlecell-velocity]"`
- External tools are not required for this modeling step itself, but are required upstream when users still need to generate velocity-ready layers.

Recommended user guidance:

- Do not auto-install scVelo during a normal skill run; if it is missing, ask the user to install the velocity extra explicitly.
- If `spliced` / `unspliced` layers are missing, direct users to `sc-velocity-prep` and clearly state that upstream BAM/STAR tools remain manual installs.

## Workflow Position

**Upstream:** sc-velocity-prep
**Downstream:** Terminal analysis. Consider: sc-pseudotime, sc-cytotrace
