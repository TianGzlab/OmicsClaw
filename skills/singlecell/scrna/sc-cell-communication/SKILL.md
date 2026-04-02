---
name: sc-cell-communication
description: >-
  Cell-cell communication analysis for annotated scRNA-seq data using a built-in
  ligand-receptor scorer, LIANA, or a CellChat R path.
version: 0.2.0
author: OmicsClaw Team
license: MIT
tags: [singlecell, communication, ligand-receptor, liana, cellchat]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--cell-type-key"
      - "--method"
      - "--species"
    param_hints:
      builtin:
        priority: "cell_type_key -> species"
        params: ["cell_type_key", "species"]
        defaults: {cell_type_key: "cell_type", species: "human"}
        requires: ["cell_type_labels_in_obs"]
        tips:
          - "--method builtin: Default lightweight scorer with a small curated ligand-receptor list."
      liana:
        priority: "cell_type_key -> species"
        params: ["cell_type_key", "species"]
        defaults: {cell_type_key: "cell_type", species: "human"}
        requires: ["liana", "cell_type_labels_in_obs"]
        tips:
          - "--method liana: Uses LIANA rank aggregation when the Python package is installed."
      cellchat_r:
        priority: "cell_type_key -> species"
        params: ["cell_type_key", "species"]
        defaults: {cell_type_key: "cell_type", species: "human"}
        requires: ["R_CellChat_stack", "cell_type_labels_in_obs"]
        tips:
          - "--method cellchat_r: R-backed CellChat path."
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
        package: liana
        bins: []
    trigger_keywords:
      - cell communication
      - cell-cell communication
      - ligand receptor
      - cellchat
      - liana
---

# Single-Cell Cell Communication

## Why This Exists

- Without it: ligand-receptor analysis is hard to standardize across tools.
- With it: the same cell-type labels can be reused across built-in and external communication backends.
- Why OmicsClaw: one output contract captures interactions, top pairs, and summary figures.

## Core Capabilities

1. **Three communication backends**: built-in scorer, LIANA, and CellChat.
2. **Shared grouping contract**: one `cell_type_key`-centric interface across all backends.
3. **Stable interaction exports**: full interaction table plus top ranked pairs.
4. **Standard figures**: interaction heatmap and top-interaction summary plot.
5. **Downstream-ready export**: annotated `processed.h5ad`, report, structured result JSON, README, and reproducibility bundle.

## Scope Boundary

Implemented entry paths:

1. `builtin`
2. `liana`
3. `cellchat_r`

The wrapper assumes you already have biologically meaningful labels in `obs`.

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | current direct input path |
| Demo | `--demo` | yes | bundled annotated-example fallback |

### Input Expectations

- Required column: a label column such as `cell_type`, `leiden`, or another supplied `--cell-type-key`.
- The grouping column should reflect biologically interpretable labels, not raw QC groups.
- Communication methods expect annotation or clustering to have already been resolved.

## Workflow

1. Validate the cell-type key.
2. Run the selected communication backend.
3. Rank interactions and extract top pairs.
4. Write interaction tables and summary plots.
5. Save `processed.h5ad`, `report.md`, and `result.json`.

## CLI Reference

```bash
python omicsclaw.py run sc-cell-communication \
  --input data.h5ad --cell-type-key cell_type --output out/

python omicsclaw.py run sc-cell-communication \
  --method liana --input data.h5ad --cell-type-key cell_type --output out/

python omicsclaw.py run sc-cell-communication \
  --method cellchat_r --input data.h5ad --cell-type-key cell_type --output out/
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | communication backend | `builtin`, `liana`, or `cellchat_r` |
| `--cell-type-key` | grouping column | core public control across all methods |
| `--species` | ligand-receptor resource selector | affects database interpretation and matching |

## Algorithm / Methodology

### `builtin`

Current OmicsClaw built-in communication path:

1. uses a compact curated ligand-receptor set
2. aggregates expression by the selected grouping column
3. scores sender-receiver pairs and ranks top interactions

### `liana`

Current OmicsClaw LIANA path:

1. validates the grouping column and species
2. runs LIANA rank aggregation when the Python package is available
3. exports the interaction table under the standard wrapper contract

### `cellchat_r`

Current OmicsClaw CellChat path:

1. exports the expression matrix through the shared H5AD bridge
2. runs the R-backed CellChat workflow
3. reimports ranked interactions into the standard output layout

Important implementation note:

- the grouping column is the main scientific control in this wrapper; the current OmicsClaw surface does not expose the full LIANA or CellChat parameter space

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/lr_interactions.csv`
- `tables/top_interactions.csv`
- `figures/interaction_heatmap.png`
- `figures/top_interactions.png`

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/interaction_heatmap.png`
- `figures/top_interactions.png`

### What Users Should Inspect First

1. `report.md`
2. `figures/interaction_heatmap.png`
3. `tables/top_interactions.csv`
4. `tables/lr_interactions.csv`
5. `processed.h5ad`

## Current Limitations

- The built-in method uses a small curated ligand-receptor set and is intentionally lightweight.
- `cellchat_r` requires a working R environment with CellChat, SingleCellExperiment, and zellkonverter through the shared bridge.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
