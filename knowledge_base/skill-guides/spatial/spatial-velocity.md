---
doc_id: skill-guide-spatial-velocity
title: OmicsClaw Skill Guide — Spatial Velocity
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-velocity, velocity]
search_terms: [spatial velocity, RNA velocity, scvelo, velovi, latent time, pseudotime, spliced, unspliced, velocity graph]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Velocity

## Purpose

Use this guide when you need to decide:

- which velocity backend is appropriate for the user goal
- which shared preprocessing and graph settings should be surfaced first
- how to explain velocity pseudotime, latent time, and uncertainty without
  overstating them
- how to use OmicsClaw's Python gallery and optional R visualization layer
  correctly

## Step 1: Inspect The Data First

Check these items before running:

- `layers["spliced"]` and `layers["unspliced"]`
- whether usable spatial coordinates exist
- whether a cluster label exists or `leiden` needs to be auto-computed
- whether the user needs a fast first pass or a heavier kinetic / variational
  model

Important current-wrapper rule:

- OmicsClaw always rebuilds the shared velocity preprocessing contract for the
  selected run. `velocity_min_shared_counts`, `velocity_n_top_genes`,
  `velocity_n_pcs`, `velocity_n_neighbors`, and `velocity_graph_*` therefore
  belong in the scientific explanation, not only in the command history.

## Step 2: Pick The Method Deliberately

| Method | Best first use | Strong starting parameters | Main caveat |
|---|---|---|---|
| **stochastic** | best default first pass | `velocity_n_neighbors=30`, `velocity_n_pcs=30`, `velocity_min_r2=0.01`, `velocity_min_likelihood=0.001` | graph-dependent, not full kinetics |
| **deterministic** | lighter baseline comparison | same as `stochastic` | can miss transient kinetics |
| **dynamical** | explicit kinetic fitting and latent time | `dynamical_n_top_genes=200~1000`, `dynamical_max_iter=5~10`, `dynamical_n_jobs=1~4` | slower and more data-sensitive |
| **velovi** | variational posterior modeling | `velovi_max_epochs=100~300`, `velovi_n_samples=25` | training settings materially affect the result |

Practical default order:

1. user asks for velocity only -> `stochastic`
2. user wants a simpler baseline -> `deterministic`
3. user explicitly wants kinetic fitting / latent time -> `dynamical`
4. user explicitly wants scVI-style posterior modeling -> `velovi`

## Step 3: Show The Run Contract Before Execution

State the run in a short concrete block, for example:

```text
About to run spatial velocity
  Method: scVelo dynamical
  Shared preprocessing: velocity_min_shared_counts=30, velocity_n_top_genes=2000, velocity_n_pcs=30, velocity_n_neighbors=30
  Kinetic fit: dynamical_n_top_genes=500, dynamical_max_iter=5, dynamical_n_jobs=4
  Graph: velocity_graph_n_neighbors=<default>, velocity_graph_sqrt_transform=<default>, velocity_graph_approx=<default>
```

## Step 4: Tune Shared Parameters Before Blaming Biology

Tune in this order:

1. `velocity_n_neighbors`
2. `velocity_n_pcs`
3. `velocity_n_top_genes`
4. `velocity_graph_*`

Interpretation rule:

- if stream directions, confidence, or velocity-gene rankings move sharply
  after a graph change, that is a graph-sensitivity result, not automatic
  biological contradiction

## Step 5: Method-Specific Tuning Rules

### Stochastic

Tune in this order:

1. shared preprocessing
2. `velocity_fit_offset`
3. `velocity_min_r2`
4. `velocity_min_likelihood`

### Deterministic

Tune in this order:

1. shared preprocessing
2. `velocity_fit_offset`
3. `velocity_min_r2`
4. `velocity_min_likelihood`

Keep preprocessing and graph settings matched if the user is comparing this
directly against `stochastic`.

### Dynamical

Tune in this order:

1. `dynamical_n_top_genes`
2. `dynamical_max_iter`
3. `dynamical_n_jobs`
4. shared preprocessing

Important language rule:

- `latent_time` is a model-derived ordering inside the fitted dynamical model,
  not absolute time

### VELOVI

Tune in this order:

1. `velovi_max_epochs`
2. `velovi_n_samples`
3. `velovi_n_hidden` / `velovi_n_latent` / `velovi_n_layers`
4. shared preprocessing

Important language rule:

- do not summarize VELOVI runs as if they were just "another scVelo mode"

## Step 6: Explain Outputs Carefully

Current OmicsClaw exports include:

- `tables/cell_velocity_metrics.csv`
- `tables/gene_velocity_summary.csv`
- `tables/velocity_gene_hits.csv`
- `tables/velocity_cluster_summary.csv`
- `processed.h5ad`

Key interpretation reminders:

- `velocity_speed` is not lineage confidence
- `velocity_confidence` is not proof of mechanism
- `velocity_pseudotime` is not clock time
- `latent_time` is model-based ordering inside the current fitted contract

## Step 7: Use The Visualization Layers Deliberately

Current `spatial-velocity` separates visualization into two layers:

1. **Python standard gallery**
   - canonical OmicsClaw analysis layer
   - generated automatically during the run
   - built from shared velocity primitives:
     - stream
     - phase
     - proportions
     - heatmap
     - paga

2. **Optional R visualization layer**
   - should read `figure_data/*.csv`
   - should not rerun scVelo or VELOVI
   - is intended for styling, layout refinement, and publication polish

The figure-data layer currently exports:

- `figure_data/velocity_summary.csv`
- `figure_data/velocity_cell_metrics.csv`
- `figure_data/velocity_gene_summary.csv`
- `figure_data/velocity_gene_hits.csv`
- `figure_data/velocity_cluster_summary.csv`
- `figure_data/velocity_top_cells.csv`
- `figure_data/velocity_top_genes.csv`
- `figure_data/velocity_run_summary.csv`
- `figure_data/velocity_spatial_points.csv`
- `figure_data/velocity_umap_points.csv`

## Step 8: What To Say After The Run

- If confidence is low: mention graph sensitivity, weak kinetic signal, or
  noisy spliced / unspliced layers before making lineage claims
- If velocity genes are implausibly high or low: mention filtering and graph
  settings before backend choice
- If pseudotime exists but looks unstable: revisit shared and graph settings
- If latent time exists: explain it only within the current fitted contract
- If VELOVI used reduced epochs for a smoke test: say so explicitly
