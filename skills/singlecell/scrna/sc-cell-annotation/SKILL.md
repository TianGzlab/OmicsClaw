---
name: sc-cell-annotation
description: >-
  Annotate cell types from preprocessed scRNA-seq data using marker scoring,
  CellTypist, or R-bridge-compatible method stubs. The current wrapper is
  honest about which methods are fully implemented and which ones fall back.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [singlecell, annotation, celltypist, singler, scmap]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--cluster-key"
      - "--method"
      - "--model"
      - "--reference"
    param_hints:
      markers:
        priority: "cluster_key"
        params: ["cluster_key"]
        defaults: {cluster_key: "leiden"}
        requires: ["cluster_labels_in_obs"]
        tips:
          - "--method markers: Fully implemented Python path using built-in marker scoring."
      celltypist:
        priority: "model"
        params: ["model"]
        defaults: {model: "Immune_All_Low"}
        requires: ["celltypist", "normalized_expression_matrix"]
        tips:
          - "--model: CellTypist model name or model file stem."
      singler:
        priority: "reference"
        params: ["reference"]
        defaults: {reference: "HPCA"}
        requires: ["R_SingleR_stack"]
        tips:
          - "The current wrapper exposes `singler`, but if the R bridge is unavailable it falls back to marker-based annotation."
      scmap:
        priority: "reference"
        params: ["reference"]
        defaults: {reference: "HPCA"}
        requires: ["R_scmap_stack"]
        tips:
          - "The current wrapper exposes `scmap`, but currently reuses the same fallback behavior as the R reference path."
    legacy_aliases: [sc-annotate]
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
        package: scanpy
        bins: []
    trigger_keywords:
      - cell type annotation
      - annotate cells
      - celltypist
      - singler
      - marker gene annotation
---

# Single-Cell Cell Annotation

## Why This Exists

- Without it: users hand-label clusters inconsistently or rely on opaque defaults.
- With it: annotation method, reference choice, and output columns are standardized.
- Why OmicsClaw: one wrapper unifies marker-based and reference-style entry paths.

## Scope Boundary

Implemented methods:

1. `markers`
2. `celltypist`

Compatibility stubs with fallback behavior:

1. `singler`
2. `scmap`

## Input Contract

- Accepted input: preprocessed `.h5ad`
- Typical requirements: normalized expression and cluster labels such as `leiden`
- Output labels are written to `obs["cell_type"]`

## Workflow Summary

1. Validate required cluster/reference metadata.
2. Run the selected annotation backend.
3. Standardize output columns such as `cell_type` and `annotation_method`.
4. Export figures, tables, and the annotated AnnData object.
5. Record method/reference settings in `result.json`.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input <processed.h5ad> --method markers --cluster-key leiden --output <dir>

python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input <processed.h5ad> --method celltypist \
  --model Immune_All_Low --output <dir>

python skills/singlecell/scrna/sc-cell-annotation/sc_annotate.py \
  --input <processed.h5ad> --method singler \
  --reference HPCA --output <dir>
```

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/`
- `tables/`
- `reproducibility/commands.sh`

## Current Limitations

- `singler` and `scmap` are exposed as stable method names, but the current wrapper falls back when the R bridge is unavailable.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
