---
name: spatial-velocity
description: >-
  RNA velocity and cellular dynamics analysis for spatial transcriptomics data.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [spatial, velocity, RNA velocity, scVelo, dynamics]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--method"
      - "--mode"
    legacy_aliases: [velocity]
    saves_h5ad: true
    requires_preprocessed: true
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

### Unified Data Convention

All RNA velocity methods require **spliced + unspliced count layers** as
their fundamental data source.  These are typically produced during
alignment by velocyto or STARsolo:

```
adata.layers["spliced"]    # spliced mRNA counts per gene per cell
adata.layers["unspliced"]  # unspliced (nascent) mRNA counts per gene per cell
adata.X                    # (optional) preprocessed expression matrix
adata.obsm["spatial"]      # spatial coordinates (for spatial stream plots)
adata.obsm["X_umap"]       # UMAP embedding (for stream plots)
```

After scVelo preprocessing (`filter_and_normalize` + `moments`), the
object also contains:

```
adata.layers["Ms"]         # first-order moments of spliced (neighbor-smoothed)
adata.layers["Mu"]         # first-order moments of unspliced (neighbor-smoothed)
adata.obsp["connectivities"]  # k-NN graph used for moment computation
```

### Method-Specific Input Requirements

| Method | Primary input consumed | Preprocessing required | What the model operates on |
|--------|----------------------|----------------------|---------------------------|
| **stochastic** | `layers["spliced"]` + `layers["unspliced"]` | `filter_and_normalize` + `moments` | Moments (Ms, Mu) + stochastic 2nd-order statistics |
| **deterministic** | `layers["spliced"]` + `layers["unspliced"]` | `filter_and_normalize` + `moments` | Moments (Ms, Mu) via steady-state approximation |
| **dynamical** | `layers["spliced"]` + `layers["unspliced"]` | `filter_and_normalize` + `moments` + `recover_dynamics` | Full kinetic parameters + latent time |
| **velovi** | `layers["Ms"]` + `layers["Mu"]` (moments) | `filter_and_normalize` + `moments` | Moment-smoothed spliced/unspliced via variational inference |

> **stochastic / deterministic / dynamical**: All three scVelo modes
> consume **spliced + unspliced count layers**.  Preprocessing computes
> neighbor-smoothed moments (Ms, Mu) which the velocity model then uses.
> The dynamical mode additionally fits full kinetic parameters via
> `recover_dynamics()`.
>
> **velovi**: Uses the **pre-computed moments (Ms / Mu)** as model input
> (not raw counts), following the official scvi-tools VELOVI tutorial
> (`spliced_layer="Ms"`, `unspliced_layer="Mu"`).  The moments are still
> derived from the original spliced/unspliced count layers.

## CLI Reference

```bash
# Stochastic model (default)
oc run spatial-velocity --input <data.h5ad> --output <report_dir>

# Deterministic model
oc run spatial-velocity --input <data.h5ad> --method deterministic --output <dir>

# Dynamical model (full kinetics)
oc run spatial-velocity --input <data.h5ad> --method dynamical --output <dir>

# VELOVI (variational inference)
oc run spatial-velocity --input <data.h5ad> --method velovi --output <dir>

# Demo mode
oc run spatial-velocity --demo --output /tmp/velo_demo

# Alternative: Via OmicsClaw runner
python omicsclaw.py run spatial-velocity --input <file> --output <dir>
python omicsclaw.py run spatial-velocity --demo
```

## Example Queries

- "Compute RNA velocity and map the arrows onto my tissue"
- "Use scVelo dynamical mode to find directional dynamics"

## Algorithm / Methodology

### Shared Preprocessing (all methods)

1. **Input validation**: Verify `layers["spliced"]` and `layers["unspliced"]` exist
2. **Filter and normalize**: `scv.pp.filter_and_normalize(min_shared_counts=30)` — simultaneously filters genes and normalizes `X`, `spliced`, and `unspliced` layers (scvelo ≥0.3 API; `n_top_genes` removed)
3. **Log transform**: `sc.pp.log1p(adata)` — log-transform `X` (scvelo ≥0.3 no longer does this inside `filter_and_normalize`)
4. **HVG selection**: `sc.pp.highly_variable_genes(n_top_genes=2000)` — select top variable genes
5. **PCA + Neighbors**: `sc.pp.pca(n_comps=30)` + `sc.pp.neighbors(n_neighbors=30)` — pre-compute neighbor graph (required by scvelo ≥0.4; avoids DeprecationWarning)
6. **Moments**: `scv.pp.moments(n_pcs=30, n_neighbors=30)` — neighbor-smoothed first-order moments (Ms, Mu)

### scVelo Stochastic (default)

- Fits velocity as the residual of spliced vs unspliced using stochastic EM with second-order moments
- Fast and robust; recommended starting point

### scVelo Deterministic

- Steady-state approximation: assumes unspliced/spliced ratio is at equilibrium
- Simplest model; may miss transient dynamics

### scVelo Dynamical

- Runs `scv.tl.recover_dynamics()` to fit full kinetic parameters (transcription, splicing, degradation rates) per gene
- Then estimates velocity from the learned kinetics + computes latent time
- Most accurate but significantly slower

### VELOVI

Follows the **official scvi-tools VELOVI tutorial** exactly:

1. `scv.pp.filter_and_normalize` + `scv.pp.moments` → Ms / Mu layers
2. `velovi.preprocess_data(adata)` — compute initial deterministic velocity priors (regularisation)
3. `VELOVI.setup_anndata(spliced_layer="Ms", unspliced_layer="Mu")` + `model.train(max_epochs=500)`
4. `model.get_velocity(n_samples=25, velo_statistic="mean")` — posterior velocity with sampling
5. `model.get_latent_time(n_samples=25)` → stored in `layers["latent_time_velovi"]`
6. Velocity scaling: `scaling = 20 / t.max(0)`, `velocity /= scaling` (official formula)
7. Kinetic rates stored in `adata.var`: `fit_alpha`, `fit_beta`, `fit_gamma`, `fit_t_`, `fit_scaling`
8. `scv.tl.velocity_graph(adata)` — required for downstream CellRank / stream plots

Requires `scvi-tools` + `velovi`.

### Post-processing (all methods)

4. **Velocity graph**: `scv.tl.velocity_graph()` — cosine-similarity transition probability matrix
5. **Velocity confidence**: `scv.tl.velocity_confidence()` → `velocity_length` and `velocity_confidence` per cell (scVelo stochastic/deterministic/dynamical only)
6. **Velocity pseudotime**: `scv.tl.velocity_pseudotime()` → cell ordering along the velocity field (scVelo modes only)
7. **Embedding projection**: Project velocity onto spatial coordinates or UMAP for stream plots

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad                      # AnnData with velocity layers + obs metadata
├── figures/
│   ├── velocity_stream_umap.png        # velocity stream on UMAP (if X_umap present)
│   ├── velocity_stream_spatial.png     # velocity stream on spatial coords (if available)
│   ├── velocity_phase.png              # phase portrait for top velocity genes
│   ├── velocity_speed_umap.png         # per-cell speed heatmap on UMAP
│   ├── velocity_speed_spatial.png      # per-cell speed heatmap on spatial coords
│   └── velocity_paga.png               # PAGA abstracted graph
├── tables/
│   ├── velocity_speed.csv              # per-cell velocity speed (L2 norm)
│   ├── velocity_confidence.csv         # per-cell velocity confidence (scVelo modes)
│   └── velocity_pseudotime.csv         # per-cell pseudotime ordering (scVelo modes)
└── reproducibility/
    ├── commands.sh
    └── requirements.txt
```

## Dependencies

**Required**:
- `scvelo` — `pip install scvelo`

**Optional (for VELOVI)**:
- `scvi-tools` — `pip install scvi-tools`
- `velovi` — `pip install velovi` (provides `preprocess_data` for initial velocity priors)
- `torch` — `pip install torch` (required by scvi-tools/velovi)

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
- [VELOVI](https://docs.scvi-tools.org/en/stable/tutorials/notebooks/scrna/velovi.html) — Al Bkhetan et al., variational inference for RNA velocity
