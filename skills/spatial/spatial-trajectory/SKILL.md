---
name: spatial-trajectory
description: >-
  Trajectory inference and pseudotime analysis for spatial transcriptomics
  using DPT, CellRank, or Palantir, with method-specific parameter hints and
  standardized trajectory outputs.
version: 0.6.0
author: OmicsClaw Team
license: MIT
tags: [spatial, trajectory, pseudotime, dpt, cellrank, palantir, cell-fate]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
    - "--method"
    - "--cluster-key"
    - "--root-cell"
    - "--root-cell-type"
    - "--dpt-n-dcs"
    - "--cellrank-n-states"
    - "--cellrank-schur-components"
    - "--cellrank-frac-to-keep"
    - "--cellrank-use-velocity"
    - "--palantir-n-components"
    - "--palantir-knn"
    - "--palantir-num-waypoints"
    - "--palantir-max-iterations"
    param_hints:
      dpt:
        priority: "cluster_key/root_cell/root_cell_type → dpt_n_dcs"
        params: ["cluster_key", "root_cell", "root_cell_type", "dpt_n_dcs"]
        defaults: {cluster_key: "auto", root_cell: null, root_cell_type: null, dpt_n_dcs: 10}
        requires: ["obsm.X_pca", "uns.neighbors"]
        tips:
        - "--cluster-key: wrapper control used for root-cell-type selection and per-cluster
          pseudotime summaries; current OmicsClaw auto-detects common cluster columns
          if omitted."
        - "--root-cell: exact barcode wrapper control; overrides automatic root selection."
        - "--root-cell-type: wrapper control that selects the root from a specified
          annotation group."
        - "--dpt-n-dcs: public `scanpy.tl.dpt` parameter controlling how many diffusion
          components enter pseudotime."
      cellrank:
        priority: "cluster_key/root_cell/root_cell_type → cellrank_use_velocity →
          cellrank_n_states → cellrank_schur_components → cellrank_frac_to_keep"
        params: ["cluster_key", "root_cell", "root_cell_type", "dpt_n_dcs", "cellrank_use_velocity",
          "cellrank_n_states", "cellrank_schur_components", "cellrank_frac_to_keep"]
        defaults: {cluster_key: "auto", root_cell: null, root_cell_type: null, dpt_n_dcs: 10,
          cellrank_use_velocity: false, cellrank_n_states: 3, cellrank_schur_components: 20,
          cellrank_frac_to_keep: 0.3}
        requires: ["obsm.X_pca", "uns.neighbors", "cellrank"]
        tips:
        - "--cellrank-use-velocity: current OmicsClaw wrapper-level preference for
          `VelocityKernel`; if velocity is unavailable the wrapper falls back to pseudotime/connectivity
          or connectivity only and reports the actual kernel mode."
        - "--cellrank-n-states: public `GPCCA.compute_macrostates(n_states=...)` control."
        - "--cellrank-schur-components: public `GPCCA.compute_schur(n_components=...)`
          control."
        - "--cellrank-frac-to-keep: public `PseudotimeKernel.compute_transition_matrix(frac_to_keep=...)`
          control when the pseudotime kernel path is used."
      palantir:
        priority: "cluster_key/root_cell/root_cell_type → palantir_knn → palantir_num_waypoints
          → palantir_n_components → palantir_max_iterations"
        params: ["cluster_key", "root_cell", "root_cell_type", "palantir_n_components",
          "palantir_knn", "palantir_num_waypoints", "palantir_max_iterations"]
        defaults: {cluster_key: "auto", root_cell: null, root_cell_type: null, palantir_n_components: 10,
          palantir_knn: 30, palantir_num_waypoints: 1200, palantir_max_iterations: 25}
        requires: ["obsm.X_pca", "uns.neighbors", "palantir"]
        tips:
        - "--palantir-n-components / --palantir-knn: public `scanpy.external.tl.palantir(...)`
          controls for diffusion-space construction."
        - "--palantir-num-waypoints / --palantir-max-iterations: public `scanpy.external.tl.palantir_results(...)`
          controls for waypoint sampling and pseudotime refinement."
        - "Current OmicsClaw stores Palantir pseudotime and entropy back into AnnData
          instead of pretending the Scanpy wrapper writes them automatically."
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
    - diffusion pseudotime
    - DPT
    - CellRank
    - Palantir
    - cell fate
    - lineage
    script: spatial_trajectory.py
---

# 🛤️ Spatial Trajectory

You are **Spatial Trajectory**, the OmicsClaw skill for pseudotime ordering and
trajectory inference in spatial transcriptomics data. The wrapper now treats
DPT, CellRank, and Palantir as separate backends with different parameter
stories instead of flattening them into one generic "trajectory" narrative.

## Why This Exists

- **Without it**: users often mix up scalar pseudotime, CellRank fate probabilities, and Palantir branch entropy as if they were interchangeable outputs.
- **With it**: one command computes a method-correct trajectory result, exports standardized tables and figures, and records only the parameters relevant to the selected backend.
- **Why OmicsClaw**: root selection, cluster-key handling, and output structure are standardized without erasing method-specific controls.

## Core Capabilities

1. **DPT**: scanpy diffusion pseudotime with explicit `n_dcs` control.
2. **CellRank**: macrostate and fate inference with explicit Schur, macrostate, and pseudotime-kernel controls.
3. **Palantir**: diffusion-space pseudotime, branch entropy, and waypoint-based refinement.
4. **Root selection controls**: choose a specific barcode or a root annotation group, or fall back to the wrapper's auto-root heuristic.
5. **Trajectory gene correlation**: identify genes associated with the selected scalar pseudotime ordering.
6. **Standard Python gallery**: emits a recipe-driven trajectory gallery with overview, diagnostic, supporting, and uncertainty panels backed by the shared `skills/spatial/_lib/viz` layer.
7. **Figure-ready exports**: writes `figure_data/` CSVs plus a gallery manifest so downstream tools can restyle the same trajectory result without recomputing it.
8. **Standardized outputs**: figures, tables, `report.md`, `result.json`, `processed.h5ad`, and reproducibility metadata.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X`, `obsm["X_pca"]`, `uns["neighbors"]` | `processed.h5ad` |

## Method-Specific Input Requirements

| Method | Input requirements | Notes |
|--------|--------------------|-------|
| `dpt` | PCA + neighbor graph | current wrapper computes diffusion map and DPT from the existing preprocessing state |
| `cellrank` | PCA + neighbor graph + `cellrank` install | current wrapper also computes a DPT prepass for root selection / pseudotime guidance |
| `palantir` | PCA + neighbor graph + `palantir` install | current wrapper stores pseudotime and entropy back into AnnData after `palantir_results()` |

Important:
- This skill expects **preprocessed** data; it does not silently rebuild the biological preprocessing state from raw counts.
- CellRank and Palantir are not just "better DPT"; they expose different assumptions and outputs.
- Current OmicsClaw no longer pretends Palantir is supported if the implementation path is missing; the wrapper now calls the real backend.

## Workflow

1. **Load**: read the preprocessed h5ad.
2. **Validate**: confirm PCA and neighbor graph exist, then resolve the cluster key and root specification.
3. **Run the selected backend**.
4. **Store outputs**:
   - DPT: `adata.obs["dpt_pseudotime"]`
   - CellRank: DPT pseudotime plus CellRank macrostates / fate results when available
   - Palantir: `adata.obs["palantir_pseudotime"]`, `adata.obs["palantir_entropy"]`, and branch-probability metadata
5. **Render the standard gallery**: build the OmicsClaw narrative gallery with pseudotime overviews, fate and entropy diagnostics, supporting summaries, and uncertainty panels.
6. **Export figure-ready data**: write `figure_data/*.csv` and `figure_data/manifest.json` for downstream customization.
7. **Report and export**: write `report.md`, `result.json`, `processed.h5ad`, tables, and reproducibility outputs.

## Visualization Contract

OmicsClaw treats `spatial-trajectory` visualization as a two-layer system:

1. **Python standard gallery**: the canonical result layer. This is the
   default output users should inspect first.
2. **R customization layer**: an optional styling and publication layer that
   reads `figure_data/` and does not recompute DPT, CellRank, or Palantir.

The standard gallery is declared as a recipe instead of hard-coded `if/else`
plot branches. Current gallery roles include:

- `overview`: pseudotime embedding, pseudotime-on-tissue, and CellRank
  macrostate context when available
- `diagnostic`: diffusion-map views plus fate-confidence and entropy maps
- `supporting`: cluster-level pseudotime summaries, top trajectory genes, and
  CellRank-specific fate panels or gene trends
- `uncertainty`: pseudotime, fate-probability, and entropy distributions plus
  CellRank fate heatmaps when available

## CLI Reference

```bash
# Default alias used by OmicsClaw
oc run spatial-trajectory \
  --input <processed.h5ad> --output <dir>

# DPT with explicit root selection
oc run spatial-trajectory \
  --input <processed.h5ad> --method dpt \
  --cluster-key leiden --root-cell-type progenitor \
  --dpt-n-dcs 10 --output <dir>

# CellRank with method-specific controls
oc run spatial-trajectory \
  --input <processed.h5ad> --method cellrank \
  --cluster-key leiden --root-cell AAAC... \
  --cellrank-n-states 4 \
  --cellrank-schur-components 20 \
  --cellrank-frac-to-keep 0.3 \
  --cellrank-use-velocity \
  --output <dir>

# Palantir
oc run spatial-trajectory \
  --input <processed.h5ad> --method palantir \
  --cluster-key leiden --root-cell-type progenitor \
  --palantir-n-components 10 \
  --palantir-knn 30 \
  --palantir-num-waypoints 1200 \
  --palantir-max-iterations 25 \
  --output <dir>

# Demo mode
oc run spatial-trajectory --demo --output /tmp/traj_demo

# Direct script entrypoint
python skills/spatial/spatial-trajectory/spatial_trajectory.py \
  --input <processed.h5ad> --method dpt --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun. Direct script execution primarily produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Example Queries

- "Run DPT and explain how the root cell is chosen first."
- "Use CellRank for fate inference and tell me what `n_states` and `frac_to_keep` control."
- "Try Palantir on this spatial dataset and show branch entropy on the embedding."

## Methodology

### DPT

1. verify PCA and neighbor graph
2. compute diffusion map
3. choose a root cell from `--root-cell`, `--root-cell-type`, or the wrapper auto-root heuristic
4. run `scanpy.tl.dpt(n_dcs=...)`
5. correlate gene expression with scalar pseudotime

**Core exposed controls**:
- `cluster_key`
- `root_cell`
- `root_cell_type`
- `dpt_n_dcs`

### CellRank

1. compute a DPT prepass for scalar pseudotime and root handling
2. build a CellRank kernel:
   - `VelocityKernel + ConnectivityKernel` when requested and available
   - otherwise `PseudotimeKernel + ConnectivityKernel`
   - otherwise `ConnectivityKernel` fallback
3. run `GPCCA.compute_schur()` and `GPCCA.compute_macrostates()`
4. attempt terminal-state prediction and fate probabilities
5. retain DPT-based scalar pseudotime summaries for plotting and gene correlation

**Core exposed controls**:
- `cluster_key`
- `root_cell`
- `root_cell_type`
- `dpt_n_dcs`
- `cellrank_use_velocity`
- `cellrank_n_states`
- `cellrank_schur_components`
- `cellrank_frac_to_keep`

### Palantir

1. verify PCA and neighbor graph
2. compute diffusion-space features with `scanpy.external.tl.palantir(...)`
3. choose an early cell from `--root-cell`, `--root-cell-type`, or the wrapper auto-root heuristic
4. run `scanpy.external.tl.palantir_results(...)`
5. write pseudotime / entropy back into AnnData and export branch probabilities when available

**Core exposed controls**:
- `cluster_key`
- `root_cell`
- `root_cell_type`
- `palantir_n_components`
- `palantir_knn`
- `palantir_num_waypoints`
- `palantir_max_iterations`

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── trajectory_pseudotime_embedding.png
│   ├── trajectory_pseudotime_spatial.png
│   ├── trajectory_macrostates_umap.png      # CellRank only
│   ├── trajectory_macrostates_spatial.png   # CellRank only when UMAP absent
│   ├── trajectory_diffmap.png
│   ├── trajectory_fate_confidence_umap.png  # when fate probabilities exist
│   ├── trajectory_entropy_umap.png          # Palantir or generic fate entropy
│   ├── trajectory_cluster_summary.png
│   ├── trajectory_genes_barplot.png
│   ├── cellrank_fate_circular.png           # CellRank only
│   ├── cellrank_fate_map.png                # CellRank only
│   ├── cellrank_gene_trends.png             # CellRank only
│   ├── cellrank_fate_heatmap.png            # CellRank only
│   ├── trajectory_pseudotime_distribution.png
│   ├── trajectory_fate_probability_distribution.png
│   ├── trajectory_entropy_distribution.png
│   └── manifest.json
├── figure_data/
│   ├── trajectory_summary.csv
│   ├── trajectory_cluster_summary.csv
│   ├── trajectory_genes.csv
│   ├── trajectory_terminal_states.csv
│   ├── trajectory_driver_genes.csv
│   ├── trajectory_run_summary.csv
│   ├── trajectory_fate_probabilities.csv
│   ├── trajectory_spatial_points.csv
│   ├── trajectory_umap_points.csv
│   ├── trajectory_diffmap_points.csv
│   └── manifest.json
├── tables/
│   ├── trajectory_summary.csv
│   ├── trajectory_cluster_summary.csv
│   ├── trajectory_genes.csv
│   ├── trajectory_terminal_states.csv
│   ├── trajectory_driver_genes.csv
│   ├── cellrank_terminal_states.csv    # CellRank only
│   ├── cellrank_driver_genes.csv       # CellRank only
│   ├── palantir_terminal_states.csv    # Palantir only
│   └── palantir_branch_probs.csv       # Palantir only, when available
└── reproducibility/
    ├── analysis_notebook.ipynb
    ├── commands.sh
    ├── r_visualization.sh
    ├── requirements.txt
    └── environment.txt
```

## Dependencies

**Required**:
- `scanpy`

**Optional**:
- `cellrank`
- `palantir`

## Safety

- **Local-first**: no data upload.
- **Preprocessing-aware**: do not present silently recomputed neighbors as if they were part of the original preprocessing state.
- **Method-aware**: DPT scalar pseudotime, CellRank fates, and Palantir entropy are different outputs and should be explained differently.
- **Two-layer visualization design**: Python plots are the canonical standard gallery; the optional R layer consumes `figure_data/` for publication-style refinement without recomputing the science.
- **Audit trail**: reports and `result.json` only record the parameters relevant to the selected backend.

## Integration with Orchestrator

**Trigger conditions**:
- trajectory
- pseudotime
- cell fate
- lineage

**Chaining partners**:
- `spatial-preprocess` — preprocessing before trajectory analysis
- `spatial-domains` — use domain or cluster annotations to guide root-cell-type selection

## Citations

- [DPT](https://doi.org/10.1038/nmeth.3971) — Haghverdi et al., *Nature Methods* 2016
- [CellRank](https://doi.org/10.1038/s41592-021-01346-6) — Lange et al., *Nature Methods* 2022
- [Palantir](https://doi.org/10.1038/s41587-019-0068-4) — Setty et al., *Nature Biotechnology* 2019
