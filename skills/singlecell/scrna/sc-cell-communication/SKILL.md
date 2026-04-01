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

## Scope Boundary

Implemented entry paths:

1. `builtin`
2. `liana`
3. `cellchat_r`

The wrapper assumes you already have biologically meaningful labels in `obs`.

## Input Contract

- Accepted input: preprocessed `.h5ad`
- Required column: a label column such as `cell_type`, `leiden`, or another supplied `--cell-type-key`

## Workflow Summary

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

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/lr_interactions.csv`
- `tables/top_interactions.csv`
- `figures/interaction_heatmap.png`
- `figures/top_interactions.png`

## Current Limitations

- The built-in method uses a small curated ligand-receptor set and is intentionally lightweight.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
