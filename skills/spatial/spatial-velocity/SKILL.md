---
name: spatial-velocity
description: >-
  RNA velocity and cellular dynamics analysis for spatial transcriptomics using
  scVelo stochastic / deterministic / dynamical models or VELOVI, with
  method-aware preprocessing, graph, training controls, and a standardized
  OmicsClaw gallery + figure_data output contract.
version: 0.5.0
author: OmicsClaw Team
license: MIT
tags: [spatial, velocity, rna-velocity, scvelo, velovi, latent-time, cellular-dynamics]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--cluster-key"
    - "--dynamical-fit-scaling"
    - "--dynamical-fit-steady-states"
    - "--dynamical-fit-time"
    - "--dynamical-max-iter"
    - "--dynamical-n-jobs"
    - "--dynamical-n-top-genes"
    - "--method"
    - "--no-dynamical-fit-scaling"
    - "--no-dynamical-fit-steady-states"
    - "--no-dynamical-fit-time"
    - "--no-velocity-fit-offset"
    - "--no-velocity-fit-offset2"
    - "--no-velocity-graph-approx"
    - "--no-velocity-graph-sqrt-transform"
    - "--no-velocity-use-highly-variable"
    - "--no-velovi-early-stopping"
    - "--velocity-fit-offset"
    - "--velocity-fit-offset2"
    - "--velocity-graph-approx"
    - "--velocity-graph-n-neighbors"
    - "--velocity-graph-sqrt-transform"
    - "--velocity-min-likelihood"
    - "--velocity-min-r2"
    - "--velocity-min-shared-counts"
    - "--velocity-n-neighbors"
    - "--velocity-n-pcs"
    - "--velocity-n-top-genes"
    - "--velocity-use-highly-variable"
    - "--velovi-batch-size"
    - "--velovi-dropout-rate"
    - "--velovi-early-stopping"
    - "--velovi-lr"
    - "--velovi-max-epochs"
    - "--velovi-n-hidden"
    - "--velovi-n-latent"
    - "--velovi-n-layers"
    - "--velovi-n-samples"
    - "--velovi-weight-decay"
    param_hints:
      stochastic:
        priority: "velocity_n_neighbors/n_pcs → velocity_fit_offset/min_r2 → velocity_graph_*"
        params: ["cluster_key", "velocity_min_shared_counts", "velocity_n_top_genes",
          "velocity_n_pcs", "velocity_n_neighbors", "velocity_use_highly_variable",
          "velocity_fit_offset", "velocity_fit_offset2", "velocity_min_r2", "velocity_min_likelihood",
          "velocity_graph_n_neighbors", "velocity_graph_sqrt_transform", "velocity_graph_approx"]
        defaults: {cluster_key: "leiden", velocity_min_shared_counts: 30, velocity_n_top_genes: 2000,
          velocity_n_pcs: 30, velocity_n_neighbors: 30, velocity_use_highly_variable: true,
          velocity_fit_offset: false, velocity_fit_offset2: false, velocity_min_r2: 0.01,
          velocity_min_likelihood: 0.001, velocity_graph_n_neighbors: null, velocity_graph_sqrt_transform: null,
          velocity_graph_approx: null}
        requires: ["layers.spliced", "layers.unspliced"]
        tips:
        - "`stochastic` uses official `scv.tl.velocity(mode='stochastic')` after OmicsClaw
          rebuilds moments with the requested preprocessing controls."
        - "--velocity-fit-offset / --velocity-fit-offset2 / --velocity-min-r2 / --velocity-min-likelihood:
          official `scv.tl.velocity()` controls."
        - "--velocity-graph-n-neighbors / --velocity-graph-sqrt-transform / --velocity-graph-approx:
          official `scv.tl.velocity_graph()` controls."
      deterministic:
        priority: "velocity_n_neighbors/n_pcs → velocity_fit_offset/min_r2 → velocity_graph_*"
        params: ["cluster_key", "velocity_min_shared_counts", "velocity_n_top_genes",
          "velocity_n_pcs", "velocity_n_neighbors", "velocity_use_highly_variable",
          "velocity_fit_offset", "velocity_fit_offset2", "velocity_min_r2", "velocity_min_likelihood",
          "velocity_graph_n_neighbors", "velocity_graph_sqrt_transform", "velocity_graph_approx"]
        defaults: {cluster_key: "leiden", velocity_min_shared_counts: 30, velocity_n_top_genes: 2000,
          velocity_n_pcs: 30, velocity_n_neighbors: 30, velocity_use_highly_variable: true,
          velocity_fit_offset: false, velocity_fit_offset2: false, velocity_min_r2: 0.01,
          velocity_min_likelihood: 0.001, velocity_graph_n_neighbors: null, velocity_graph_sqrt_transform: null,
          velocity_graph_approx: null}
        requires: ["layers.spliced", "layers.unspliced"]
        tips:
        - "`deterministic` uses the same scVelo engine as `stochastic` but switches
          to `mode='deterministic'`."
        - "The shared `velocity_*` preprocessing settings are wrapper-level controls
          around the official scVelo preprocessing recipe and materially affect the
          result."
      dynamical:
        priority: "dynamical_n_top_genes/max_iter → velocity_min_r2/min_likelihood
          → velocity_graph_*"
        params: ["cluster_key", "velocity_min_shared_counts", "velocity_n_top_genes",
          "velocity_n_pcs", "velocity_n_neighbors", "velocity_use_highly_variable",
          "velocity_min_r2", "velocity_min_likelihood", "dynamical_n_top_genes", "dynamical_max_iter",
          "dynamical_fit_time", "dynamical_fit_scaling", "dynamical_fit_steady_states",
          "dynamical_n_jobs", "velocity_graph_n_neighbors", "velocity_graph_sqrt_transform",
          "velocity_graph_approx"]
        defaults: {cluster_key: "leiden", velocity_min_shared_counts: 30, velocity_n_top_genes: 2000,
          velocity_n_pcs: 30, velocity_n_neighbors: 30, velocity_use_highly_variable: true,
          velocity_min_r2: 0.01, velocity_min_likelihood: 0.001, dynamical_n_top_genes: null,
          dynamical_max_iter: 10, dynamical_fit_time: true, dynamical_fit_scaling: true,
          dynamical_fit_steady_states: true, dynamical_n_jobs: null, velocity_graph_n_neighbors: null,
          velocity_graph_sqrt_transform: null, velocity_graph_approx: null}
        requires: ["layers.spliced", "layers.unspliced"]
        tips:
        - "--dynamical-n-top-genes / --dynamical-max-iter / --dynamical-fit-time /
          --dynamical-fit-scaling / --dynamical-fit-steady-states / --dynamical-n-jobs:
          official `scv.tl.recover_dynamics()` controls."
        - "`dynamical` additionally exports latent-time support when `scv.tl.latent_time()`
          succeeds."
      velovi:
        priority: "velovi_max_epochs/n_samples → velovi_n_hidden/n_latent/n_layers
          → velocity_graph_*"
        params: ["cluster_key", "velocity_min_shared_counts", "velocity_n_top_genes",
          "velocity_n_pcs", "velocity_n_neighbors", "velocity_use_highly_variable",
          "velovi_n_hidden", "velovi_n_latent", "velovi_n_layers", "velovi_dropout_rate",
          "velovi_max_epochs", "velovi_lr", "velovi_weight_decay", "velovi_batch_size",
          "velovi_n_samples", "velovi_early_stopping", "velocity_graph_n_neighbors",
          "velocity_graph_sqrt_transform", "velocity_graph_approx"]
        defaults: {cluster_key: "leiden", velocity_min_shared_counts: 30, velocity_n_top_genes: 2000,
          velocity_n_pcs: 30, velocity_n_neighbors: 30, velocity_use_highly_variable: true,
          velovi_n_hidden: 256, velovi_n_latent: 10, velovi_n_layers: 1, velovi_dropout_rate: 0.1,
          velovi_max_epochs: 500, velovi_lr: 0.01, velovi_weight_decay: 0.01, velovi_batch_size: 256,
          velovi_n_samples: 25, velovi_early_stopping: true, velocity_graph_n_neighbors: null,
          velocity_graph_sqrt_transform: null, velocity_graph_approx: null}
        requires: ["layers.spliced", "layers.unspliced", "scvi_tools"]
        tips:
        - "OmicsClaw still runs shared scVelo preprocessing first because VELOVI consumes
          moment-smoothed `Ms` / `Mu` layers."
        - "--velovi-n-hidden / --velovi-n-latent / --velovi-n-layers / --velovi-dropout-rate:
          official `scvi.external.VELOVI(...)` model controls."
        - "--velovi-max-epochs / --velovi-lr / --velovi-weight-decay / --velovi-batch-size
          / --velovi-early-stopping: official `VELOVI.train()` controls."
        - "--velovi-n-samples: official posterior-sampling control for `get_velocity()`
          and `get_latent_time()` extraction."
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
    - kind: pip
      package: scvi-tools
      bins: []
    trigger_keywords:
    - RNA velocity
    - cellular dynamics
    - scVelo
    - VELOVI
    - latent time
    - spliced unspliced
    script: spatial_velocity.py
---

# 🏎️ Spatial Velocity

You are **Spatial Velocity**, the OmicsClaw skill for RNA velocity, directional
state change, and kinetic / variational temporal ordering in spatial
transcriptomics.

This skill follows the newer OmicsClaw unified template:

- method-specific core parameters stay explicit
- Python figures are the canonical standard gallery
- `figure_data/` is the stable bridge for downstream styling
- optional R plotting is a separate visualization layer, not a second analysis
  engine

## Why This Exists

- RNA velocity is highly sensitive to preprocessing, graph construction, and
  backend choice; hiding those settings behind one generic `--method` is not
  acceptable.
- Spatial users need both embedding-centric and tissue-centric views.
- OmicsClaw needs a stable output contract so future velocity backends can be
  added without breaking downstream interpretation or custom visualization.

## Core Capabilities

1. **scVelo kinetic backends**
   - `stochastic`
   - `deterministic`
   - `dynamical`
2. **Variational posterior backend**
   - `velovi`
3. **Standard OmicsClaw gallery**
   - velocity stream on UMAP / spatial
   - phase portraits
   - spliced / unspliced proportion diagnostics
   - heatmap and PAGA summary panels
   - feature maps for speed, confidence, pseudotime, and latent time when available
4. **Figure-ready exports**
   - `figures/manifest.json`
   - `figure_data/*.csv`
   - `figure_data/manifest.json`
5. **Stable tabular outputs**
   - cell-level metrics
   - gene-level kinetic summaries
   - cluster-level velocity summaries
   - top-cell and top-gene exports

## Input Convention

| Input slot | Used by | Notes |
|---|---|---|
| `adata.layers["spliced"]` | all methods | required |
| `adata.layers["unspliced"]` | all methods | required |
| `adata.obsm["spatial"]` | spatial gallery panels | strongly recommended |
| `adata.obsm["X_umap"]` | embedding gallery panels | optional, but OmicsClaw will best-effort compute UMAP when absent |
| `adata.obs[cluster_key]` | grouped summaries, PAGA, proportions | defaults to `leiden`; OmicsClaw can auto-compute it |

After the shared preprocessing stage, OmicsClaw also expects or creates:

```python
adata.layers["Ms"]   # moment-smoothed spliced counts
adata.layers["Mu"]   # moment-smoothed unspliced counts
```

## Method Contract

All methods share the same first stage:

1. filter / normalize
2. `log1p`
3. HVG selection when requested
4. PCA
5. neighbors
6. moments

That means the following are part of the scientific contract, not mere wrapper
details:

- `velocity_min_shared_counts`
- `velocity_n_top_genes`
- `velocity_n_pcs`
- `velocity_n_neighbors`
- `velocity_use_highly_variable`
- `velocity_graph_*`

## Workflow

1. **Load** the h5ad and verify spliced / unspliced layers exist.
2. **Resolve `cluster_key`** for grouped exports and gallery summaries.
3. **Run shared preprocessing** for the requested velocity contract.
4. **Run the selected backend** with method-specific core parameters only.
5. **Persist velocity results** into stable AnnData slots such as:
   - `obs["velocity_speed"]`
   - `obs["velocity_confidence"]`
   - `obs["velocity_pseudotime"]`
   - `obs["latent_time"]` when available
   - `obs["root_cells"]` / `obs["end_points"]` when available
6. **Build gallery context** from stable `obs`, `obsm`, and exported summary
   tables instead of from transient local variables.
7. **Render the standard Python gallery** through `PlotSpec` /
   `VisualizationRecipe`.
8. **Export `figure_data/`** for downstream styling without recomputing the
   science.

## Visualization Contract

OmicsClaw treats `spatial-velocity` visualization as a two-layer system:

1. **Python standard gallery**
   - the canonical analysis output
   - generated during the main run
   - built primarily from shared `_lib/viz` velocity primitives:
     - `stream`
     - `phase`
     - `proportions`
     - `heatmap`
     - `paga`
   - plus a small number of skill-specific summary plots

2. **Optional R visualization layer**
   - reads `figure_data/`
   - focuses on styling, layout, manuscript composition, and publication polish
   - must not rerun scVelo or VELOVI internally

This means:

- Python figures are the default OmicsClaw narrative users should interpret
  first.
- `figure_data/*.csv` is the stable handoff for downstream beautification.
- `reproducibility/r_visualization.sh` is an entrypoint for that optional layer.

## CLI Reference

```bash
# Default stochastic scVelo run
oc run spatial-velocity \
  --input <processed.h5ad> --output <dir>

# Deterministic comparison run
oc run spatial-velocity \
  --input <processed.h5ad> \
  --method deterministic \
  --velocity-min-r2 0.02 \
  --velocity-min-likelihood 0.005 \
  --output <dir>

# Lightweight dynamical smoke test
oc run spatial-velocity \
  --input <processed.h5ad> \
  --method dynamical \
  --dynamical-n-top-genes 500 \
  --dynamical-max-iter 5 \
  --dynamical-n-jobs 4 \
  --output <dir>

# VELOVI
oc run spatial-velocity \
  --input <processed.h5ad> \
  --method velovi \
  --velovi-max-epochs 200 \
  --velovi-n-samples 25 \
  --output <dir>

# Demo
oc run spatial-velocity --demo --output /tmp/velocity_demo
```

## Output Structure

```text
<output_dir>/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── manifest.json
│   ├── velocity_stream_umap.png
│   ├── velocity_stream_spatial.png
│   ├── velocity_phase.png
│   ├── velocity_layer_proportions.png
│   ├── velocity_heatmap.png
│   ├── velocity_paga.png
│   └── ...
├── figure_data/
│   ├── manifest.json
│   ├── velocity_summary.csv
│   ├── velocity_cell_metrics.csv
│   ├── velocity_gene_summary.csv
│   ├── velocity_gene_hits.csv
│   ├── velocity_cluster_summary.csv
│   ├── velocity_top_cells.csv
│   ├── velocity_top_genes.csv
│   ├── velocity_run_summary.csv
│   ├── velocity_spatial_points.csv
│   └── velocity_umap_points.csv
├── tables/
│   ├── cell_velocity_metrics.csv
│   ├── gene_velocity_summary.csv
│   ├── velocity_gene_hits.csv
│   ├── velocity_cluster_summary.csv
│   ├── top_velocity_cells.csv
│   └── top_velocity_genes.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    ├── environment.txt
    └── r_visualization.sh
```

## Method Notes

### `stochastic`

- Best default first pass.
- Still graph-sensitive and not a full kinetic model.

### `deterministic`

- Simpler steady-state baseline.
- Useful as a comparison against `stochastic` or `dynamical` when the user
  wants to separate graph sensitivity from heavier model complexity.

### `dynamical`

- Adds kinetic fitting and latent-time support.
- Runtime and convergence cost are materially higher.
- `latent_time` is a fitted ordering, not clock time.

### `velovi`

- Uses a variational posterior model after the shared moment construction step.
- Training settings are scientifically relevant and must be reported.

## Safety

- **Do not hide preprocessing choices**: they materially change velocity,
  confidence, and pseudotime.
- **Do not oversell time**: `velocity_pseudotime` and `latent_time` are
  model-derived orderings.
- **Do not mix backend semantics**: scVelo kinetics and VELOVI posteriors are
  not interchangeable labels.
- **Keep visualization layers separated**: R templates read `figure_data/` and
  must not rerun the backend.

## Dependencies

- Required:
  - `scanpy`
  - `anndata`
  - `scvelo`
- Optional by method:
  - `scvi-tools`
  - `velovi`

## Citations

- Bergen V, et al. *Generalizing RNA velocity to transient cell states through
  dynamical modeling*. Nat Biotechnol. 2020.
- Gayoso A, et al. *VELOVI: deep generative modeling of RNA velocity*. 2024.
