---
name: sc-cell-communication
description: >-
  Cell-cell communication analysis for single-cell RNA-seq using a built-in ligand-receptor scorer,
  LIANA+, or CellChat via the R bridge.
version: 0.1.0
author: OmicsClaw Team
license: MIT
tags: [singlecell, communication, ligand-receptor, liana, cellchat]
---

# Single-Cell Communication

This skill identifies ligand-receptor interactions between annotated cell populations in scRNA-seq data.

## Methods

- `builtin`: lightweight Python fallback with a curated ligand-receptor set
- `liana`: LIANA+ consensus ranking when the Python package is available
- `cellchat_r`: CellChat via `rpy2` + R packages

## Input

- Preprocessed `.h5ad` with a cell type column such as `cell_type`, `leiden`, or `louvain`

## Output

- `report.md`
- `result.json`
- `processed.h5ad`
- `tables/lr_interactions.csv`
- `tables/top_interactions.csv`
- communication figures in `figures/`

## Example

```bash
python omicsclaw.py run sc-cell-communication --input data.h5ad --cell-type-key cell_type --output out/
python omicsclaw.py run sc-cell-communication --method cellchat_r --input data.h5ad --cell-type-key cell_type --output out/
```
